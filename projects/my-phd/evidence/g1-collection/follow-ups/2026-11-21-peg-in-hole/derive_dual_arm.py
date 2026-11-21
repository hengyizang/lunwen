"""Derive contact-class counts and sensor-vector magnitudes from Mendeley v1.

Usage: python derive_dual_arm.py SOURCE.zip OUTPUT_DIRECTORY
The two source members are verified against the repository's v1 fingerprints.
Force and moment units are left native. No inter-sensor alignment is assumed.
"""
import argparse
import csv
import hashlib
import io
import math
from collections import Counter
from pathlib import Path
from zipfile import ZipFile

MEMBERS = (
    ("data_ft_2056.csv", "train", "4cc4de8798fde10b93cc3e1136f7a1ee55e34b7dc87697157abfe4c31cb9123d"),
    ("data_ft_159.csv", "validation", "443b714fbd30416450af6a61f2e35dda0a7a3272c475e7855bd27db1a864712a"),
)
GROUPS = {
    "sensor1_force_native": ("fx1", "fy1", "fz1"),
    "sensor1_moment_native": ("mx1", "my1", "mz1"),
    "sensor2_force_native": ("fx2", "fy2", "fz2"),
    "sensor2_moment_native": ("mx2", "my2", "mz2"),
}
AXES = [axis for axes in GROUPS.values() for axis in axes]


def write_csv(path, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def derive(archive, output):
    records = []
    class_counts = []
    with ZipFile(archive) as z:
        for name, split, expected_sha in MEMBERS:
            payload = z.read(name)
            if hashlib.sha256(payload).hexdigest() != expected_sha:
                raise ValueError(f"Unexpected SHA-256 for {name}")
            reader = csv.DictReader(io.StringIO(payload.decode("utf-8-sig")))
            if reader.fieldnames != ["", "y", *AXES]:
                raise ValueError(f"Unexpected columns in {name}")
            counts = Counter()
            for row in reader:
                sensor = {k: float(row[k]) for k in AXES}
                if not all(math.isfinite(v) for v in sensor.values()):
                    raise ValueError(f"Nonfinite measurement in {name}")
                contact_class = int(row["y"])
                record = {"split": split, "source_index": int(row[""]), "contact_class": contact_class}
                for field, axes in GROUPS.items():
                    record[field] = format(math.sqrt(sum(sensor[k] ** 2 for k in axes)), ".10g")
                records.append(record)
                counts[contact_class] += 1
            for contact_class, count in sorted(counts.items()):
                class_counts.append({"split": split, "contact_class": contact_class, "rows": count})
    output.mkdir(parents=True, exist_ok=True)
    write_csv(output / "dual-arm-contact-magnitudes.csv", records)
    write_csv(output / "dual-arm-class-counts.csv", class_counts)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    derive(args.archive, args.output)
