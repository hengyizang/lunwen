"""Recompute small public validation-file aggregates with Python 3.10+ and NumPy.
Usage: python measure.py [--cache DIR] [--output DIR]. Use an empty cache to fetch originals.
"""
import argparse
import csv
import hashlib
import io
import re
import zipfile
from collections import Counter
from pathlib import Path
from urllib.request import Request, urlopen

import numpy as np

HERE = Path(__file__).resolve().parent


def save(path, fields, rows):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(fields)
        writer.writerows(rows)


def read_input(row, cache):
    path = cache / row["file"] if cache else None
    if path is not None and path.exists():
        data = path.read_bytes()
    else:
        with urlopen(Request(row["url"], headers={"User-Agent": "G1-public-research/1.0"}), timeout=60) as response:
            data = response.read()
    digest = hashlib.sha256(data).hexdigest()
    if digest != row["sha256"]:
        raise ValueError(f"File hash changed for {row['file']}: {digest}")
    return data


def torch_rows(name, data):
    events = re.findall(r"^Mk\d+=(Rest|Start|Box),[^,]*,(\d+)", data.decode("utf-8-sig"), re.M)
    counter = Counter(key for key, unused in events)
    previous_trigger = None
    paired = []
    for key, text in events:
        sample = int(text)
        if key != "Box":
            previous_trigger = sample
        elif previous_trigger is not None and sample > previous_trigger:
            paired.append(sample - previous_trigger)
            previous_trigger = None
    clean = [x for x in paired if x <= 100]
    groups = [("all_one_to_one", paired), ("positive_up_to_100", clean)]
    if "external" in name:
        groups.append(("positive_up_to_100_drop_last_sensitivity", clean[:-1]))
    for rule, seq in groups:
        x = np.array(seq)
        stats = [round(float(v), 3) for v in (x.mean(), np.median(x), np.percentile(x, 95), x.max())]
        yield [name, rule, counter["Rest"] + counter["Start"], counter["Box"], len(paired), len(seq), *stats]


def pcd_rows(name, data, seen_members):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for item in archive.infolist():
            if item.is_dir() or item.filename.startswith("__MACOSX/"):
                continue
            body = archive.read(item)
            digest = hashlib.sha256(body).hexdigest()
            known = digest in seen_members
            seen_members.add(digest)
            suffix = Path(item.filename).suffix
            if suffix == ".csv":
                reader = csv.DictReader(io.StringIO(body.decode("utf-8-sig")))
                times = [float(row["timestamp"]) for row in reader]
                yield [name, item.filename, digest, int(known), "controller CSV", len(times), 0, round(times[-1] - times[0], 6), int(np.sum(np.diff(times) <= 0)), ""]
            elif suffix == ".vmrk":
                markers = re.findall(rb"^Mk\d+=Response,\s*R\s*(\d+),(\d+)", body, re.M)
                sequence = [int(entry[1]) for entry in markers]
                codes = Counter(int(entry[0]) for entry in markers)
                yield [name, item.filename, digest, int(known), "recorder marker", len(sequence), len(codes), "", int(np.sum(np.diff(sequence) <= 0)), " ".join(f"R{k}={v}" for k, v in sorted(codes.items()))]


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--cache", type=Path)
    parser.add_argument("--output", type=Path, default=HERE)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    with (HERE / "file-manifest.csv").open() as f:
        files = list(csv.DictReader(f))
    pcd, torch = [], []
    seen = set()
    # Process the combined motor archive first so the separately posted duplicate is explicit.
    for row in sorted(files, key=lambda r: r["file"]):
        group, name = row["group"], row["file"]
        if group == "pcd":
            pcd.extend(pcd_rows(name, read_input(row, args.cache), seen))
        if group == "torch" and name.endswith(".vmrk"):
            torch.extend(torch_rows(name, read_input(row, args.cache)))
    save(args.output / "pcd-validation-files.csv",
         ["archive", "member", "member_sha256", "duplicate_bytes_in_prior_member", "stream", "samples_or_responses", "distinct_response_codes", "controller_duration_s", "nonincreasing_positions", "response_counts"], pcd)
    save(args.output / "torch-marker-check.csv",
         ["file", "pair_rule", "source_triggers", "mic_boxes", "positive_one_to_one_pairs", "retained", "mean_sample_steps", "median_sample_steps", "p95_sample_steps", "max_sample_steps"], torch)


if __name__ == "__main__":
    main()
