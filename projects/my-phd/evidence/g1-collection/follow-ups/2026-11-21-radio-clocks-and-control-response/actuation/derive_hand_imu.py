"""Measure per-take kinematic lags on the distributed two-IMU telemetry.

Usage: python derive_hand_imu.py PATH_TO_CHECKOUT OUTPUT_DIRECTORY
NumPy is the sole third-party dependency.
"""
import argparse
import csv
import hashlib
from pathlib import Path

import numpy as np


MAX_LAG = 200
AXES = ("x", "y", "z")


def rail_rows(gyro):
    # Published logger encodes signed 16-bit counts at 131 LSB per deg/s to 4 decimals.
    counts = np.rint(gyro * 131).astype(np.int64)
    if np.any(np.abs(gyro - counts / 131) > 0.000051):
        raise ValueError("Unrecognized angular-velocity encoding")
    return np.any((counts == -32768) | (counts == 32767), axis=1)


def peak_lag(robot, leader, robot_rail, leader_rail, mask_rails):
    # Keep the same robot-side central time window for each candidate lag.
    n = len(robot)
    target = robot[MAX_LAG:n-MAX_LAG]
    target_valid = ~robot_rail[MAX_LAG:n-MAX_LAG]
    best = None
    for k in range(-MAX_LAG, MAX_LAG + 1):
        start = MAX_LAG - k
        stop = n - MAX_LAG - k
        x = leader[start:stop]
        y = target
        if mask_rails:
            valid = target_valid & ~leader_rail[start:stop]
            x, y = x[valid], y[valid]
        x = x - x.mean()
        y = y - y.mean()
        correlation = float(np.sum(x*y) / np.sqrt(np.sum(x*x)*np.sum(y*y)))
        if best is None or correlation > best[0]:
            best = (correlation, k, len(x))
    return best


def read_take(file):
    values = np.genfromtxt(file, delimiter=",", names=True)
    time = values["t_us"].astype(np.int64)
    increments = np.diff(time)
    if (increments <= 0).any():
        raise ValueError(f"Check clock discontinuity in {file}")
    # m1 = robot, m2 = human per the dataset documentation.
    gyros = [np.column_stack([values[f"m{i}_g{axis}_dps"] for axis in AXES])
             for i in (1, 2)]
    if not all(np.isfinite(g).all() for g in gyros):
        raise ValueError(f"Nonfinite gyro signal in {file}")
    rails = [rail_rows(v) for v in gyros]
    robot, leader = [np.linalg.norm(g, axis=1) for g in gyros]
    group, take = file.stem.rsplit("_", 1)
    row = dict(file=file.name, stack=group, take=int(take), rows=len(time),
               sha256=hashlib.sha256(file.read_bytes()).hexdigest(),
               first_logger_us=int(time[0]), last_logger_us=int(time[-1]),
               min_step_us=int(increments.min()), median_step_us=float(np.median(increments)),
               max_step_us=int(increments.max()), step_over_1p5_ms=int((increments>1500).sum()),
               robot_gyro_rail_rows=int(rails[0].sum()), leader_gyro_rail_rows=int(rails[1].sum()))
    for tag, exclude in (("all", False), ("no_rail_pairs", True)):
        score, shift, pairs = peak_lag(robot, leader, *rails, mask_rails=exclude)
        sample_us = time[MAX_LAG:len(time)-MAX_LAG]
        other_us = time[MAX_LAG-shift:len(time)-MAX_LAG-shift]
        valid = (~rails[0][MAX_LAG:len(time)-MAX_LAG] &
                 ~rails[1][MAX_LAG-shift:len(time)-MAX_LAG-shift]) if exclude else slice(None)
        row[f"{tag}_peak_lag_rows"] = shift
        row[f"{tag}_median_pair_time_difference_ms"] = float(np.median((sample_us-other_us)[valid])/1000)
        row[f"{tag}_peak_pearson_r"] = round(score,7)
        row[f"{tag}_lag_pairs"] = pairs
    return row


def save(path, rows):
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, rows[0].keys(), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkout", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    rows = [read_take(f) for f in sorted((args.checkout/"inputs").glob("*.csv"))]
    if len(rows)!=21 or len({r["sha256"] for r in rows})!=21:
        raise ValueError("Expected 21 distinct input recordings")
    groups = []
    for group in sorted({r["stack"] for r in rows}):
        part = [r for r in rows if r["stack"]==group]
        out = dict(stack=group,takes=len(part),rows=sum(r["rows"] for r in part),
                   robot_gyro_rail_rows=sum(r["robot_gyro_rail_rows"] for r in part),
                   leader_gyro_rail_rows=sum(r["leader_gyro_rail_rows"] for r in part))
        for tag in ("all","no_rail_pairs"):
            lags = [r[f"{tag}_median_pair_time_difference_ms"] for r in part]
            out[f"{tag}_min_take_lag_ms"] = min(lags)
            out[f"{tag}_median_take_lag_ms"] = float(np.median(lags))
            out[f"{tag}_max_take_lag_ms"] = max(lags)
        groups.append(out)
    args.output.mkdir(parents=True,exist_ok=True)
    save(args.output/"hand-imu-takes.csv",rows)
    save(args.output/"hand-imu-stacks.csv",groups)


if __name__ == "__main__":
    main()
