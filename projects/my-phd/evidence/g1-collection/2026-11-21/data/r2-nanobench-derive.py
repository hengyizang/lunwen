"""Rebuild a per-sample NanoBench table with Python 3 (standard library).

python r2-nanobench-derive.py SOURCE_DIRECTORY OUTPUT.csv.gz
Provide the four source CSVs named in the sibling nanobench-provenance.json.
"""
import argparse
import csv
from decimal import Decimal
import gzip
import hashlib
import io
import json
import math
from pathlib import Path

MOTORS = tuple(f"motor_motor_m{i}" for i in range(1, 5))
VICON = ("px", "py", "pz")
EKF = tuple(f"est_stateEstimate_{axis}" for axis in "xyz")
FIELDS = ("trial", "sample_in_trial", "relative_time_s", "motor_pwm_mean",
          "motor_pwm_range", "position_difference_norm_m", "motor_state",
          "missing_columns")


def finite_fields(row, names):
    values, missing = [], []
    for name in names:
        try:
            value = float(row[name])
        except (TypeError, ValueError):
            value = math.nan
        if not math.isfinite(value):
            missing.append(name)
        values.append(value)
    return values, missing


def derive(source_dir, output):
    provenance = Path(__file__).with_name("nanobench-provenance.json")
    files = sorted((item for item in json.loads(provenance.read_text())["files"]
                    if item["path"].endswith(".csv")), key=lambda item: item["path"])
    if len(files) != 4:
        raise ValueError("Expected four pinned input recordings")
    with output.open("wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as packed:
        with io.TextIOWrapper(packed, encoding="utf-8", newline="") as text:
            writer = csv.writer(text, lineterminator="\n")
            writer.writerow(FIELDS)
            for item in files:
                path = source_dir / item["local_filename"]
                if hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]:
                    raise ValueError(f"Wrong input SHA-256 for {path.name}")
                with path.open(newline="", encoding="utf-8-sig") as source:
                    reader = csv.DictReader(source)
                    if not set(("t",) + MOTORS + VICON + EKF).issubset(reader.fieldnames):
                        raise ValueError(f"Missing expected header in {path.name}")
                    first_time = None
                    count = 0
                    for count, row in enumerate(reader, start=1):
                        stamp = Decimal(row["t"]) if row["t"] else None
                        if stamp is not None and not stamp.is_finite():
                            stamp = None
                        if count == 1:
                            first_time = stamp
                        delta = "" if stamp is None or first_time is None else format(stamp - first_time, "f")
                        motors, missing_m = finite_fields(row, MOTORS)
                        positions, missing_p = finite_fields(row, VICON + EKF)
                        missing = missing_m + missing_p
                        if stamp is None:
                            missing.append("t")
                        mean = spread = distance = ""
                        state = "missing_pwm"
                        if not missing_m:
                            mean = format(math.fsum(motors) / 4, ".12g")
                            spread = format(max(motors) - min(motors), ".12g")
                            state = "four_commands_zero" if all(v == 0 for v in motors) else "any_command_nonzero"
                        if not missing_p:
                            distance = format(math.dist(positions[:3], positions[3:]), ".12g")
                        writer.writerow((path.stem, count, delta, mean, spread, distance,
                                         state, "|".join(missing)))
                    if count != item["row_count"]:
                        raise ValueError(f"Unexpected number of records in {path.name}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_directory", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    derive(args.source_directory, args.output)
