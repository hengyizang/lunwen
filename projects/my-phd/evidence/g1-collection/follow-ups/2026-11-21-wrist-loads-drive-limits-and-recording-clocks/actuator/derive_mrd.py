"""Summarize each numeric MRDLab bench log using its frozen Git blob and README scaling.

Usage: python derive_mrd.py OUTPUT_DIRECTORY CACHE_DIRECTORY
Dependencies: Python 3, NumPy. The cache keeps verified source files on the local machine.
"""
import argparse
import concurrent.futures
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import time
import urllib.request

import numpy as np

REPOSITORY = "MRDLab/mis-tool-characterization"
COMMIT = "03658b2ccefef9adceebc38dd4a17bd6e190cd2e"
TORQUE_NM_PER_COUNT = 0.000039811


def fetch(url):
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=45) as response:
                return response.read()
        except OSError:
            if attempt == 3:
                raise
            time.sleep(1 + attempt)


def summarize(record, cache):
    path = record["path"]
    blob = record["sha"]
    local = cache / blob
    data = local.read_bytes() if local.exists() else fetch(
        f"https://raw.githubusercontent.com/{REPOSITORY}/{COMMIT}/{path}"
    )
    actual = hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()
    if actual != blob or len(data) != record["size"]:
        raise ValueError(f"Source integrity mismatch for {path}")
    if not local.exists():
        local.write_bytes(data)
    x = np.loadtxt(io.BytesIO(data), comments="%", delimiter=",", ndmin=2)
    if x.shape[1] != 10 or not np.isfinite(x).all():
        raise ValueError(f"Unexpected numeric data for {path}")
    clock, back_nm, current, front_nm, front_cmd, back_cmd = (
        x[:, 0], x[:, 2] * TORQUE_NM_PER_COUNT, x[:, 3],
        x[:, 5] * TORQUE_NM_PER_COUNT, x[:, 6], x[:, 7]
    )
    differences = np.diff(clock)
    rail = np.abs(back_cmd) == 1
    changes = np.diff(np.r_[False, rail, False].astype(int))
    starts, stops = np.flatnonzero(changes == 1), np.flatnonzero(changes == -1)
    def bounds(values):
        return (round(float(np.min(values)), 9), round(float(np.max(values)), 9))
    outside = np.abs(back_cmd) > 1
    changes_outside = np.diff(np.r_[False, outside, False].astype(int))
    intervals = []
    for start, stop in zip(np.flatnonzero(changes_outside == 1), np.flatnonzero(changes_outside == -1)):
        sl = slice(start, stop)
        intervals.append([path, blob, int(start), int(stop - 1), int(stop - start),
                          *bounds(clock[sl]), *bounds(back_cmd[sl]), *bounds(current[sl]),
                          *bounds(back_nm[sl]), *bounds(front_nm[sl])])
    return [
        path, blob, len(data), len(x), round(float(clock[0]), 6),
        round(float(clock[-1]), 6), round(float(np.median(differences)), 7),
        int(np.count_nonzero(differences <= 0)), *bounds(back_cmd),
        int(np.count_nonzero(back_cmd == -1)), int(np.count_nonzero(back_cmd == 1)),
        int(np.count_nonzero(np.abs(back_cmd) > 1)), int(len(starts)),
        int(np.max(stops - starts, initial=0)), *bounds(current),
        *bounds(back_nm), *bounds(front_cmd), *bounds(front_nm),
    ], intervals


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_directory", type=Path)
    parser.add_argument("cache_directory", type=Path)
    args = parser.parse_args()
    args.cache_directory.mkdir(parents=True, exist_ok=True)
    args.output_directory.mkdir(parents=True, exist_ok=True)
    tree = json.loads(fetch(f"https://api.github.com/repos/{REPOSITORY}/git/trees/{COMMIT}?recursive=1"))
    if tree["truncated"]:
        raise ValueError("Incomplete revision tree")
    files = sorted((r for r in tree["tree"] if r["type"] == "blob" and
                    re.fullmatch(r"data/[^/]+/\d+\.txt", r["path"], re.I)), key=lambda r: r["path"])
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        rows = list(pool.map(lambda r: summarize(r, args.cache_directory), files))
    header = [
        "path", "git_blob_sha1", "bytes", "samples", "first_time_native", "last_time_native",
        "median_dt_native", "nonincreasing_time_steps", "back_command_min", "back_command_max",
        "back_command_at_minus1", "back_command_at_plus1", "back_command_outside_unit",
        "absolute_unit_endpoint_spells", "longest_absolute_unit_endpoint_samples",
        "back_measured_current_min_A", "back_measured_current_max_A",
        "back_transducer_min_Nm", "back_transducer_max_Nm", "front_command_native_min", "front_command_native_max",
        "front_transducer_min_Nm", "front_transducer_max_Nm",
    ]
    with (args.output_directory / "mrd-bench-runs.csv").open("w", newline="") as output:
        writer = csv.writer(output, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(row for row, intervals in rows)
    with (args.output_directory / "mrd-command-excursions.csv").open("w", newline="") as output:
        writer = csv.writer(output, lineterminator="\n")
        writer.writerow(["path", "git_blob_sha1", "first_sample_zero_based", "last_sample_zero_based",
                         "samples", "first_time_native", "last_time_native", "back_command_min", "back_command_max",
                         "back_measured_current_min_A", "back_measured_current_max_A", "back_transducer_min_Nm",
                         "back_transducer_max_Nm", "front_transducer_min_Nm", "front_transducer_max_Nm"])
        for row, intervals in rows:
            writer.writerows(intervals)


if __name__ == "__main__":
    main()
