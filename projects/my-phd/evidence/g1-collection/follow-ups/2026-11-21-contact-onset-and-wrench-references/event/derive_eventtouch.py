"""Summarize physical and FEM records for 15 mm PLA and Ecoflex 00-10 spheres.
Input is a local mirror of the selected paths under the pinned Hugging Face tree.
Usage: python derive_eventtouch.py INPUT_ROOT OUTPUT_DIR
"""
import argparse
import csv
import hashlib
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

AXES = ("fx", "fy", "fz", "mx", "my", "mz")
SENSORS = ("digit", "s1", "s2", "s3")
OBJECTS = ("ball_0010_15", "ball_PLA_15")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def table(path):
    with path.open(encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def write(path, records):
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=records[0].keys(), lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)


def summarize_run(root, path):
    relative = path.parent.relative_to(root)
    sensor, obj, pose, depth = relative.parts
    physical = table(path)
    fem_path = path.with_name("fem_sensor.csv")
    fem = table(fem_path)
    # The source supplies frame indices on the simulation side only.
    if [int(r["frame"]) for r in fem] != list(range(len(fem))):
        raise ValueError(f"Unexpected FEM frame numbering: {relative}")
    raw_fields = ["device_raw_" + a for a in AXES]
    corrected = ["corrected_" + a + ("_N" if a.startswith("f") else "_Nm") for a in AXES]
    valid = [r for r in physical if r["sensor_ros_time_ns"]]
    for r in physical:
        if not r["sensor_ros_time_ns"] and any(r[k] for k in raw_fields + corrected):
            raise ValueError(f"Timestamp missing on a nonempty wrench row: {relative}")
    time = np.array([int(r["sensor_ros_time_ns"]) for r in valid], dtype=np.int64)
    raw = np.array([[float(r[k]) for k in raw_fields] for r in valid])
    corr = np.array([[float(r[k]) for k in corrected] for r in valid])
    if not (np.isfinite(raw).all() and np.isfinite(corr).all()):
        raise ValueError(f"Incomplete wrench values: {relative}")
    diff = raw - corr
    dt = np.diff(time)
    equal = dt == 0
    phase = Counter(r["phase"] for r in valid)
    images = [r["camera_image_path"] for r in valid if r.get("camera_image_path")]
    common = dict(sensor=sensor, object=obj, pose=pose, depth_directory=depth)
    run = dict(**common, real_sha256=sha(path), fem_sha256=sha(fem_path),
               archived_real_rows=len(physical), complete_wrench_rows=len(valid),
               missing_wrench_rows=len(physical)-len(valid), fem_rows=len(fem),
               distinct_sensor_time_values=len(set(time.tolist())),
               adjacent_time_backsteps=int((dt < 0).sum()), adjacent_same_stamp=int(equal.sum()),
               same_stamp_raw_changed=int((equal & np.any(raw[1:] != raw[:-1], axis=1)).sum()),
               same_stamp_corrected_changed=int((equal & np.any(corr[1:] != corr[:-1], axis=1)).sum()),
               linked_image_paths=len(images), distinct_linked_image_paths=len(set(images)),
               phase_counts="|".join(f"{k}={v}" for k,v in sorted(phase.items())))
    axes = []
    for j, a in enumerate(AXES):
        delta = diff[:, j]
        center = float(np.median(delta))
        axes.append(dict(**common, axis=a, unit="N" if j<3 else "Nm",
                         recorded_rows=len(delta), median_raw_minus_corrected=round(center,10),
                         within_run_range_raw_minus_corrected=round(float(np.ptp(delta)),10),
                         rms_about_median=round(float(np.sqrt(np.mean((delta-center)**2))),10)))
    return run, axes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    runs, axes = [], []
    for sensor in SENSORS:
        for obj in OBJECTS:
            files = sorted((args.root/sensor/obj).glob("*/*/real_sensor.csv"))
            if len(files) != (60 if sensor == "s3" else 50):
                raise ValueError(f"Incomplete subset: {sensor}/{obj}")
            for f in files:
                run, axis_rows = summarize_run(args.root, f)
                runs.append(run)
                axes.extend(axis_rows)
    groups = defaultdict(list)
    for r in axes:
        groups[(r["sensor"], r["object"], r["axis"], r["unit"])].append(r)
    summary = []
    for (sensor, obj, axis, unit), rows in sorted(groups.items()):
        spans = [r["within_run_range_raw_minus_corrected"] for r in rows]
        summary.append(dict(sensor=sensor, object=obj, axis=axis, unit=unit, condition_directories=len(rows),
                            median_within_run_range=round(float(np.median(spans)),10),
                            min_within_run_range=min(spans), max_within_run_range=max(spans)))
    args.output.mkdir(exist_ok=True, parents=True)
    write(args.output/"eventtouch-recordings.csv", runs)
    write(args.output/"eventtouch-corrections.csv", axes)
    write(args.output/"eventtouch-by-sensor.csv", summary)


if __name__ == "__main__":
    main()
