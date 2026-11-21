"""Summarize the pinned Neural Actuation Dataset (raw CSVs, no video or Parquet)."""
import argparse
import csv
import hashlib
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

TREE_DIGEST = "ce56b2adbc653f521540eef145999da581ee74183a14a013375995acc27e88e7"


def write_table(path, rows):
    with path.open("w", encoding="utf-8", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=rows[0], lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def channels(frame, prefix, count):
    return frame[[f"{prefix}{i}" for i in range(1, count + 1)]].to_numpy(dtype=float)


def describe(platform, frame):
    v = frame[["force_x", "force_y", "force_z"]].to_numpy()
    valid = v != -999
    fields = {"force_all3_valid": int(valid.all(axis=1).sum()),
              "force_z_only": int((valid[:, 2] & ~valid[:, 0] & ~valid[:, 1]).sum()),
              "force_all3_missing": int((~valid).all(axis=1).sum())}
    if sum(fields.values()) != len(frame):
        raise ValueError("Unexpected force sentinel pattern")
    if platform == "Franka":
        requested = channels(frame, "tau_d", 7)
        measured = channels(frame, "tau", 7)
        quiet = (requested == 0).all(axis=1)
        fields["all_tau_d_zero_rows"] = int(quiet.sum())
        fields["all_tau_d_zero_measured_nonzero_rows"] = int((quiet & (measured != 0).any(axis=1)).sum())
        fields["nonzero_velocity_command_rows"] = int((channels(frame, "vel_d", 7) != 0).any(axis=1).sum())
    if platform == "SO-101":
        load = channels(frame, "load", 6)
        current = channels(frame, "current", 6)
        # 1000 is a value observed in this release; no firmware limit is assumed.
        fields["load_abs1000_joint_samples"] = int((np.abs(load) == 1000).sum())
        fields["load_nonzero_current_zero_joint_samples"] = int(((load != 0) & (current == 0)).sum())
    return fields


def make_tables(source, target):
    files = sorted((source / "data").rglob("*.csv"))
    names = {}
    manifest = []
    # Keep a train file if a byte-identical copy also appears in the test split.
    preference = sorted(files, key=lambda p: ("test" in p.parts, p.as_posix()))
    digests = {}
    for p in preference:
        data = p.read_bytes()
        sha = hashlib.sha256(data).hexdigest()
        oid = hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()
        name = str(p.relative_to(source).as_posix())
        names.setdefault(sha, name)
        digests[p] = (oid, sha)
        manifest.append(f"{name}\t{oid}\n")
    if hashlib.sha256("".join(sorted(manifest)).encode()).hexdigest() != TREE_DIGEST:
        raise ValueError("Input directory does not match the pinned 485-file release")

    files_out = []
    condition_values = defaultdict(list)
    platforms = defaultdict(Counter)
    ranges = defaultdict(list)
    metrics = ("force_all3_valid", "force_z_only", "force_all3_missing", "all_tau_d_zero_rows",
               "all_tau_d_zero_measured_nonzero_rows", "nonzero_velocity_command_rows",
               "load_abs1000_joint_samples", "load_nonzero_current_zero_joint_samples")
    for path in files:
        name = path.relative_to(source).as_posix()
        subset = name.split("/")[1]
        platform = {"so101": "SO-101", "franka": "Franka"}.get(subset, "OMX")
        frame = pd.read_csv(path, float_precision="round_trip")
        if not np.isfinite(frame.to_numpy(dtype=float)).all():
            raise ValueError(f"Unexpected nonfinite values in {name}")
        steps = np.diff(frame.timestamp)
        if not np.all(steps > 0):
            raise ValueError(f"Non-increasing timestamps in {name}")
        oid, sha = digests[path]
        representative = names[sha]
        unique = name == representative
        group = platforms[platform]
        group["deposited_paths"] += 1
        group["deposited_rows"] += len(frame)
        detail = describe(platform, frame)
        split = next(v for v in name.split("/") if v in ("train", "validation", "test"))
        files_out.append({"path": name, "git_blob_sha1": oid, "sha256": sha, "representative": representative,
                          "platform": platform, "subset": subset, "split": split, "rows": len(frame),
                          "median_step_ms": f"{np.median(steps) * 1000:.6f}",
                          **{k: detail.get(k, "") for k in metrics}})
        if subset == "motor_condition":
            # The condition-specific reference set appears a second time under free motion.
            # Use it once within the 40-file comparison regardless of the global representative.
            err = np.abs(frame.goal_pos3 - frame.pos3)
            condition_values[path.parts[-3]].append((
                sha, len(frame), float(np.median(err)), float(np.median(np.abs(frame.current3))),
                float(np.median(np.abs(frame.pwm3)))))
        if not unique:
            continue
        group["unique_files"] += 1
        group["unique_rows"] += len(frame)
        group.update(detail)
        definitions = {
            "OMX": (5, (("goal_pos", "rad"), ("pos", "rad"), ("current", "mA"), ("pwm", "counts"))),
            "SO-101": (6, (("goal_pos", "rad"), ("pos", "rad"), ("current", "counts"), ("load", "counts"))),
            "Franka": (7, (("cmd_pos", "rad"), ("tau_d", "N m"), ("tau", "N m"), ("tau_ext", "N m"),
                           ("vel_d", "rad/s"))),
        }
        count, definitions_for_platform = definitions[platform]
        for prefix, unit in definitions_for_platform:
            values = channels(frame, prefix, count)
            for j in range(count):
                col = values[:, j]
                ranges[(platform, prefix, unit, j + 1)].append(
                    (len(col), int(np.count_nonzero(col)), float(np.min(col)), float(np.max(col))))
    platform_rows = []
    for platform, counts in sorted(platforms.items()):
        column_names = ("deposited_paths", "deposited_rows", "unique_files", "unique_rows") + metrics
        platform_rows.append({"platform": platform, **{k: counts.get(k, "") for k in column_names}})
    channel_rows = []
    for (platform, prefix, unit, j), records in sorted(ranges.items()):
        channel_rows.append({"platform": platform, "channel": prefix, "joint": j, "unit": unit,
                             "files": len(records), "samples": sum(v[0] for v in records),
                             "nonzero_samples": sum(v[1] for v in records),
                             "observed_min": min(v[2] for v in records), "observed_max": max(v[3] for v in records)})
    conditions = []
    for condition, values in sorted(condition_values.items()):
        if len(values) != 10 or len({row[0] for row in values}) != 10:
            raise ValueError(f"Unexpected source coverage for {condition}")
        conditions.append({"task": condition, "distinct_trajectories_in_task": len(values),
                           "recorded_rows": sum(row[1] for row in values),
                           "median_of_run_median_abs_goal_minus_pos3_rad": round(float(np.median([r[2] for r in values])), 8),
                           "median_of_run_median_abs_current3_mA": round(float(np.median([r[3] for r in values])), 8),
                           "median_of_run_median_abs_pwm3_counts": round(float(np.median([r[4] for r in values])), 8)})
    target.mkdir(parents=True, exist_ok=True)
    write_table(target / "nad-omx-condition.csv", conditions)
    write_table(target / "nad-files.csv", files_out)
    write_table(target / "nad-platforms.csv", platform_rows)
    write_table(target / "nad-channel-ranges.csv", channel_rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="snapshot root containing data/")
    parser.add_argument("output", type=Path)
    opts = parser.parse_args()
    make_tables(opts.source, opts.output)
