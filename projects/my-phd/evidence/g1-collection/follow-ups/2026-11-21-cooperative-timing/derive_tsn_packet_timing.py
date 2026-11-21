"""Recompute CORA DATA1885 v1.0 summaries from the 20 original receiver logs."""
import argparse
import csv
import hashlib
import io
import json
import statistics
import sys
import urllib.request
from pathlib import Path

METADATA = ("https://dataverse.csuc.cat/api/datasets/:persistentId/versions/1.0"
            "?persistentId=doi:10.34810/data1885")
DOWNLOAD = "https://dataverse.csuc.cat/api/access/datafile/"


def source_files(paths, metadata):
    if metadata:
        release = json.loads(metadata.read_bytes())["data"]
    else:
        with urllib.request.urlopen(METADATA, timeout=60) as response:
            release = json.load(response)["data"]
    if (release["datasetPersistentId"].lower(), release["versionNumber"],
            release["versionMinorNumber"]) != ("doi:10.34810/data1885", 1, 0):
        raise ValueError("Expected CORA DATA1885 v1.0 release metadata")
    records = [r for r in release["files"] if r["label"].startswith("receiver_")
               and r["directoryLabel"].startswith("data/results/")]
    if len(records) != 20:
        raise ValueError("Expected 20 receiver reports in the release")
    by_digest = {}
    accepted_names = set()
    for r in records:
        f = r["dataFile"]
        if f["checksum"]["type"].upper() != "MD5":
            raise ValueError("Unexpected publisher checksum algorithm")
        by_digest[f["checksum"]["value"]] = r
        accepted_names.update([str(f["id"]), r["label"]])
    candidates = set()
    for p in paths:
        if p.is_dir():
            candidates.update(x for x in p.rglob("*") if x.name in accepted_names and x.is_file())
        else:
            candidates.add(p)
    found = set()
    for p in sorted(candidates):
        content = p.read_bytes()
        digest = hashlib.md5(content).hexdigest()
        r = by_digest.get(digest)
        if r is None or len(content) != r["dataFile"]["filesize"]:
            raise ValueError(f"File failed v1.0 checksum/length verification: {p}")
        if digest not in found:
            yield r, content
            found.add(digest)
    missing = set(by_digest) - found
    if missing:
        raise ValueError(f"Missing {len(missing)} receiver files: " +
                         ", ".join(sorted(str(by_digest[d]["dataFile"]["id"]) for d in missing)))


def summarize(record, content, exact):
    f = record["dataFile"]
    rows = [tuple(map(int, line.split())) for line in content.splitlines()]
    if len(rows) != 10000 or any(len(row) != 7 for row in rows):
        raise ValueError(f"Unexpected receiver schema or count: {f['id']}")
    seq, _, tx, hw, near_hw, _, _ = zip(*rows)
    if seq != tuple(range(10000)):
        raise ValueError(f"Unexpected sequence: {f['id']}")
    wifi = record["directoryLabel"] == "data/results/NUC"
    if wifi and any(hw):
        raise ValueError(f"Unexpected hardware timestamp on Wi-Fi: {f['id']}")
    rx = [r + 37_000_000_000 for r in near_hw] if wifi else hw
    latency = [r - t for r, t in zip(rx, tx)]
    intervals = [b - a for a, b in zip(rx, rx[1:])]
    if (min(latency) < 0 or min(intervals) < 0 or
            any(b < a for a, b in zip(tx, tx[1:])) or rx[-1] <= rx[0]):
        raise ValueError(f"Invalid time order: {f['id']}")
    # Twice the exact trapezoidal area in ns². No epoch time passes through float.
    area2 = sum(2 * age * dt + dt * dt for age, dt in zip(latency, intervals))
    duration = rx[-1] - rx[0]
    n = len(seq)
    ordered = sorted(latency)
    result = {
        "source_path": record["directoryLabel"] + "/" + record["label"],
        "download_url": DOWNLOAD + str(f["id"]), "bytes": len(content),
        "publisher_verified_md5": f["checksum"]["value"],
        "sha256": hashlib.sha256(content).hexdigest(),
        "packet_rows": n, "seq_first": seq[0], "seq_last": seq[-1],
        "internal_seq_gaps": 0, "rx_clock": "rxtime_plus_37s" if wifi else "hwtime",
        "latency_min_us": ordered[0] / 1000,
        "latency_median_us": statistics.median(ordered) / 1000,
        "latency_mean_us": round(statistics.mean(latency) / 1000, 6),
        "latency_p95_nearest_rank_us": ordered[(95 * n + 99) // 100 - 1] / 1000,
        "latency_max_us": ordered[-1] / 1000,
        "transport_age_time_mean_us": round(area2 / (2 * duration) / 1000, 6),
    }
    if exact:
        result.update(latency_sum_ns=sum(latency), transport_age_twice_area_ns2=area2,
                      observation_duration_ns=duration)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", type=Path, nargs="+",
                        help="directory (recursive) or original receiver files")
    parser.add_argument("--metadata", type=Path, help="offline v1.0 Dataverse API JSON")
    parser.add_argument("--output", type=Path, help="CSV output (default stdout)")
    parser.add_argument("--exact", action="store_true", help="append exact integer totals")
    args = parser.parse_args()
    rows = [summarize(r, c, args.exact) for r, c in source_files(args.inputs, args.metadata)]
    rows.sort(key=lambda r: r["source_path"])
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=rows[0], lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    if args.output:
        args.output.write_bytes(buffer.getvalue().encode("utf-8"))
    else:
        sys.stdout.write(buffer.getvalue())


if __name__ == "__main__":
    main()
