"""Summarize the DFKI v2 hardware leaderboards from an unmodified pinned checkout."""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
from statistics import median


def summarize(checkout, source):
    record = checkout / source["path"]
    data = record.read_bytes()
    if len(data) != source["bytes"] or hashlib.sha256(data).hexdigest() != source["sha256"]:
        raise ValueError(f"Source bytes differ from manifest: {record}")
    with record.open(newline="", encoding="ascii") as stream:
        reader = csv.DictReader(stream)
        columns = reader.fieldnames
        if not columns or len(columns) != len(set(columns)):
            raise ValueError(f"Missing or duplicate columns: {record}")
        rows = []
        for row in reader:
            if None in row or any(v is None for v in row.values()):
                raise ValueError(f"Incomplete row: {record}")
            values = {k: float(v) for k, v in row.items()}
            if not all(math.isfinite(v) for v in values.values()):
                raise ValueError(f"Nonfinite values: {record}")
            rows.append(values)
    _, platform, variant, _, controller, experiment, _ = Path(source["path"]).parts
    active = {"acrobot": 2, "pendubot": 1}[platform]
    times = [row["time"] for row in rows]
    dt = [b-a for a, b in zip(times, times[1:])]
    if not dt or min(dt) <= 0:
        raise ValueError(f"Expected strictly increasing recorded times: {record}")
    cmd = [row[f"tau_con{active}"] for row in rows]
    feedback = [row[f"tau_meas{active}"] for row in rows]
    # Count exact representations of a visible reference level without assuming a limit.
    at_five = [abs(x) == 5.0 for x in cmd]
    return {
        "source_path": source["path"], "platform": platform, "condition": variant,
        "controller": controller, "experiment": experiment, "active_joint": active,
        "samples": len(rows), "start_s": times[0], "end_s": times[-1],
        "median_step_s": median(dt), "max_step_s": max(dt),
        "controller_torque_min_Nm": min(cmd), "controller_torque_max_Nm": max(cmd),
        "feedback_torque_min_Nm": min(feedback), "feedback_torque_max_Nm": max(feedback),
        "rows_abs_controller_torque_eq_5_Nm": sum(at_five),
        "rows_abs_controller_torque_gt_5_Nm": sum(abs(x) > 5.0 for x in cmd),
        "desired_trajectory_torque_columns": int(all(f"tau_des{i}" in columns for i in (1, 2))),
        "perturbation_torque_columns": int(all(f"tau_pert{i}" in columns for i in (1, 2))),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkout", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    manifest_path = Path(__file__).with_name("leaderboard-source.json")
    manifest = json.loads(manifest_path.read_text())
    runs = [summarize(args.checkout, source) for source in manifest["csv_files"]]
    with args.output.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=runs[0], lineterminator="\n")
        writer.writeheader()
        writer.writerows(runs)


if __name__ == "__main__":
    main()
