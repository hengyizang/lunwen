"""Verify and summarize the CTU Delta wheel-assembly CSV using Python 3."""
import argparse
import csv
import hashlib
import itertools
import json
import math
import struct
from collections import Counter
from pathlib import Path

CHANNELS = ("Force_x", "Force_y", "Force_z", "Torque_x", "Torque_y", "Torque_z")
LABEL_SOURCE = {
    1: "vision_CNN", 2: "vision_CNN", 3: "invalid_day", 4: "invalid_day",
    5: "human", 6: "human",
}


def summarize(idx, rows):
    labels = set()
    days = set()
    minima = [math.inf] * 6
    maxima = [-math.inf] * 6
    previous = None
    repeated = 0
    digest = hashlib.sha256()
    for n, row in enumerate(rows, 1):
        labels.add(row["label"])
        days.add(int(row["meas_id"]))
        vals = tuple(float(row[k]) for k in CHANNELS)
        if not all(math.isfinite(v) for v in vals):
            raise ValueError(f"Nonfinite channel in episode {idx}")
        repeated += int(vals == previous)
        previous = vals
        digest.update(struct.pack(">6d", *vals))
        for axis, value in enumerate(vals):
            minima[axis] = min(minima[axis], value)
            maxima[axis] = max(maxima[axis], value)
    if len(days) != 1 or len(labels) != 1 or not labels <= {"True", "False"}:
        raise ValueError(f"Day or outcome varies within episode {idx}")
    day = days.pop()
    result = {
        "episode_id": idx, "meas_id": day, "released_label": labels.pop(),
        "label_source_or_status": LABEL_SOURCE[day], "samples": n,
        "nominal_span_s": format((n - 1) * .004, ".3f"),
        "consecutive_identical_six_axis_rows": repeated, "wrench_sequence_sha256": digest.hexdigest(),
    }
    for name, lo, hi in zip(CHANNELS, minima, maxima):
        result[name.lower() + "_min_native"] = lo
        result[name.lower() + "_max_native"] = hi
    return result


def write(path, rows):
    with path.open("w", encoding="utf-8", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=rows[0], lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_csv", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    manifest = json.loads(Path(__file__).with_name("wheel-source.json").read_text())
    spec = next(s for s in manifest["checked_files"] if s["name"] == "ForceTorqueTimeSeries.csv")
    if args.source_csv.stat().st_size != spec["bytes"] or hashlib.sha256(args.source_csv.read_bytes()).hexdigest() != spec["sha256"]:
        raise ValueError("CSV differs from version 1.0.0")
    with args.source_csv.open(encoding="ascii", newline="") as stream:
        records = csv.DictReader(stream)
        if records.fieldnames != ["idx", "label", "meas_id", *CHANNELS]:
            raise ValueError(f"Unexpected columns {records.fieldnames}")
        trials = [summarize(i, group) for i, group in itertools.groupby(records, key=lambda r: int(r["idx"]))]
    if [r["episode_id"] for r in trials] != list(range(1, 525)):
        raise ValueError("Unexpected, missing or interleaved episodes")
    days = []
    for day, source in LABEL_SOURCE.items():
        group = [r for r in trials if r["meas_id"] == day]
        counts = Counter(r["released_label"] for r in group)
        days.append({"meas_id": day, "label_source_or_status": source, "episodes": len(group),
                     "released_true": counts["True"], "released_false": counts["False"],
                     "sensor_rows": sum(r["samples"] for r in group),
                     "consecutive_identical_six_axis_rows": sum(r["consecutive_identical_six_axis_rows"] for r in group)})
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write(args.output_dir / "wheel-episodes.csv", trials)
    write(args.output_dir / "wheel-days.csv", days)


if __name__ == "__main__":
    main()
