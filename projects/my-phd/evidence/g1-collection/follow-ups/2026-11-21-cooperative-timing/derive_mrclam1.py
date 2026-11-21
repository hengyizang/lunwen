"""Reproduce two non-trajectory tables from all pinned MR.CLAM Dataset 1 files."""
import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from decimal import Decimal
from math import isfinite
from pathlib import Path
from statistics import median


def records(path, width):
    with path.open(encoding="ascii", newline=None) as stream:
        for line_number, line in enumerate(stream, 1):
            fields = line.partition("#")[0].split()
            if not fields:
                continue
            if len(fields) != width or not all(isfinite(float(field)) for field in fields):
                raise ValueError(f"Invalid numeric row at {path.name} line {line_number}")
            yield fields


def timestamps(path, width):
    return [Decimal(row[0]) for row in records(path, width)]


def descending_steps(times):
    return sum(b < a for a, b in zip(times, times[1:]))


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0], lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def derive(data, destination):
    manifest_path = Path(__file__).with_name("mrclam1-source.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for entry in manifest["files"]:
        content = (data / entry["name"]).read_bytes()
        if len(content) != entry["bytes"] or hashlib.sha256(content).hexdigest() != entry["sha256"]:
            raise ValueError(f"Input differs from pinned bytes: {entry['name']}")
    barcode_map = {int(code): int(subject) for subject, code in records(data / "Barcodes.dat", 2)}
    if len(barcode_map) != 20 or set(barcode_map.values()) != set(range(1, 21)):
        raise ValueError("Expected twenty unique subjects and barcodes")
    landmarks = [int(row[0]) for row in records(data / "Landmark_Groundtruth.dat", 5)]
    if sorted(landmarks) != list(range(6, 21)):
        raise ValueError("Expected fifteen distinct landmark ground truths")

    robots, pairs = [], []
    for observer in range(1, 6):
        measured_times = []
        by_mobile = defaultdict(list)
        landmarks_seen = Counter()
        unknown = Counter()
        for time, code, _distance, _bearing in records(data / f"Robot{observer}_Measurement.dat", 4):
            time = Decimal(time)
            measured_times.append(time)
            subject = barcode_map.get(int(code))
            if subject is None:
                unknown[int(code)] += 1
            elif subject <= 5:
                by_mobile[subject].append(time)
            else:
                landmarks_seen[subject] += 1
        gt = timestamps(data / f"Robot{observer}_Groundtruth.dat", 4)
        odometry = timestamps(data / f"Robot{observer}_Odometry.dat", 3)
        robot_rows = sum(len(times) for target, times in by_mobile.items() if target != observer)
        if len(measured_times) != robot_rows + len(by_mobile[observer]) + sum(landmarks_seen.values()) + sum(unknown.values()):
            raise ValueError("Unreconciled measurement count")
        robots.append({
            "observer": observer, "measurement_rows": len(measured_times),
            "unique_measurement_times": len(set(measured_times)),
            "other_robot_rows": robot_rows, "self_rows": len(by_mobile[observer]),
            "landmark_rows": sum(landmarks_seen.values()), "distinct_landmarks_seen": len(landmarks_seen),
            "unmapped_rows": sum(unknown.values()),
            "unmapped_barcode_counts": " ".join(f"{code}={count}" for code, count in sorted(unknown.items())),
            "measurement_span_s": max(measured_times) - min(measured_times),
            "groundtruth_rows": len(gt), "odometry_rows": len(odometry),
            "measurement_time_reversals": descending_steps(measured_times),
            "groundtruth_time_reversals": descending_steps(gt),
            "odometry_time_reversals": descending_steps(odometry),
        })
        for target in range(1, 6):
            if target == observer:
                continue
            times = sorted(set(by_mobile[target]))
            gaps = [b - a for a, b in zip(times, times[1:])]
            pairs.append({
                "observing_robot": observer, "observed_robot": target, "sighting_rows": len(by_mobile[target]),
                "distinct_sighting_times": len(times),
                "median_gap_between_distinct_sightings_s": median(gaps) if gaps else "",
                "max_gap_between_distinct_sightings_s": max(gaps) if gaps else "",
            })
    destination.mkdir(parents=True, exist_ok=True)
    write_csv(destination / "mrclam1-robots.csv", robots)
    write_csv(destination / "mrclam1-directed-sightings.csv", pairs)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data", type=Path, help="Folder with the 17 original-format .dat files")
    parser.add_argument("output", type=Path)
    options = parser.parse_args()
    derive(options.data, options.output)
