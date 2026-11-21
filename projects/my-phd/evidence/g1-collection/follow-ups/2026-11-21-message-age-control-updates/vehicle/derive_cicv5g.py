"""Recompute one timing row per physical urban frequency trial in CICV5G v1.0.0."""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
from statistics import median
from zipfile import ZipFile


def timing_rows(content):
    lines = content.decode("utf-8-sig").splitlines()
    if lines[0].split()[:3] != ["pub_time(ms)", "sub_time(ms)", "delay(ms)"]:
        raise ValueError("Unexpected first three columns")
    result = []
    for line in lines[1:]:
        if line.strip():
            # Only read the three timing fields; the remaining fields are unnecessary.
            a, b, c, _ = line.split(maxsplit=3)
            sent, received, delay = int(a), int(b), int(c)
            if received - sent != delay or delay < 0:
                raise ValueError("Inconsistent or negative RTT")
            result.append((sent, received, delay))
    return result


def describe(rows, path):
    parts = PurePosixPath(path).parts
    period = int(parts[-4].removesuffix("ms"))
    network = parts[-3]
    gaps = [v[0] - u[0] for u, v in zip(rows, rows[1:])]
    intervals = [v[1] - u[1] for u, v in zip(rows, rows[1:])]
    if min(gaps) <= 0 or min(intervals) < 0:
        raise ValueError("Unexpected ordering; new analysis needed for stale updates")
    latencies = sorted(row[2] for row in rows)
    twice_area = sum(2 * row[2] * dt + dt * dt for row, dt in zip(rows, intervals))
    span = sum(intervals)
    return {
        "nominal_publish_period_ms": period, "network_label": network,
        "source_repeat": int(parts[-1].split("-")[-1].removesuffix(".txt")),
        "completed_echo_cycles": len(rows),
        "recorded_publish_interval_median_ms": median(gaps), "recorded_publish_interval_max_ms": max(gaps),
        "rtt_min_ms": min(latencies), "rtt_median_ms": median(latencies),
        "rtt_p95_nearest_rank_ms": latencies[math.ceil(0.95 * len(rows)) - 1],
        "rtt_max_ms": max(latencies),
        "adjacent_receive_ties_ms_resolution": intervals.count(0),
        "next_publish_precedes_prior_echo_pairs": sum(b[0] < a[1] for a, b in zip(rows, rows[1:])),
        "observed_receive_span_ms": span, "publish_to_echo_age_twice_integral_ms2": twice_area,
        "publish_to_echo_time_mean_age_ms": format(twice_area / (2 * span), ".6f")
    }


def run(archive_path, output):
    source = json.loads(Path(__file__).with_name("cicv5g-source.json").read_text())
    z = source["archive"]
    if archive_path.stat().st_size != z["bytes"]:
        raise ValueError("Unexpected archive size")
    digest = hashlib.sha256()
    with archive_path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != z["sha256"]:
        raise ValueError("Archive differs from pinned version")
    groups = {}
    with ZipFile(archive_path) as archive:
        for record in source["selected_input_files"]:
            name = record["path"]
            if not name.endswith(".txt"):
                continue
            content = archive.read(z["zip_root"] + "/" + name)
            if len(content) != record["size"] or hashlib.sha256(content).hexdigest() != record["sha256"]:
                raise ValueError(f"Unexpected member: {name}")
            groups.setdefault(str(PurePosixPath(name).parent), {})[name] = timing_rows(content)
    summaries = []
    all_times = []
    for dirname, files in sorted(groups.items()):
        merged = files.pop(dirname + "/all.txt")
        if merged != [row for name in sorted(files) for row in files[name]]:
            raise ValueError("Combined timing records differ from individual runs")
        for name in sorted(files):
            values = files[name]
            summaries.append(describe(values, name))
            all_times.append((values[0][0], values[-1][1]))
    if len(summaries) != 20 or len(groups) != 6:
        raise ValueError("Unexpected trial count")
    windows = sorted(all_times)
    if any(b[0] <= a[1] for a, b in zip(windows, windows[1:])):
        raise ValueError("Overlapping trial windows")
    with output.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=summaries[0], lineterminator="\n")
        w.writeheader()
        w.writerows(summaries)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    run(args.archive, args.output)
