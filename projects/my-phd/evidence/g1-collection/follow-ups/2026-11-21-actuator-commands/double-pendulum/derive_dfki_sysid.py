"""Recompute per-file signal coverage from physical double-pendulum system identification records."""
import argparse
import csv
import hashlib
import itertools
import json
import math
import statistics
from pathlib import Path


def headers_with_joints(names):
    return [f"{name}{joint}" for name in names for joint in (1, 2)]


legacy = ["time", *headers_with_joints(["pos", "vel", "tau"])]
measured = ["time", *headers_with_joints(["pos_meas", "vel_meas", "pos_filt", "vel_filt"])]
controller = headers_with_joints(["tau_con", "tau_fric", "tau_meas"])
desired = headers_with_joints(["pos_des", "vel_des"])
schemas = {
    tuple(legacy): "single_torque_pair",
    tuple(measured + controller): "controller_and_motor_feedback",
    tuple(measured + desired + controller + headers_with_joints(["tau_des"])): "controller_feedback_and_reference",
}


def summarize(root, entry):
    path = root / entry["path"]
    data = path.read_bytes()
    if len(data) != entry["bytes"] or hashlib.sha256(data).hexdigest() != entry["sha256"]:
        raise ValueError(f"Source bytes differ: {path}")
    with path.open(encoding="ascii", newline="") as stream:
        reader = csv.reader(stream)
        header = tuple(x.strip() for x in next(reader))
        schema = schemas[header]
        times = []
        signals = {field: [] for field in header if field.startswith("tau")}
        for line_no, row in enumerate(reader, 2):
            values = list(map(float, row))
            if len(values) != len(header) or not all(math.isfinite(x) for x in values):
                raise ValueError(f"Invalid finite numeric row: {path}:{line_no}")
            record = dict(zip(header, values))
            times.append(record["time"])
            for field, values in signals.items():
                values.append(record[field])
    dt = [b - a for a, b in itertools.pairwise(times)]
    summary = {
        "source_path": entry["path"],
        "design": entry["path"].split("/")[2],
        "schema": schema,
        "rows": len(times),
        "first_time_s": format(times[0], ".9f"),
        "last_time_s": format(times[-1], ".9f"),
        "median_dt_s": format(statistics.median(dt), ".9f"),
        "max_dt_s": format(max(dt), ".9f"),
        "duplicate_time_steps": dt.count(0),
        "backward_time_steps": sum(x < 0 for x in dt),
    }
    for prefix in ("tau", "tau_con", "tau_fric", "tau_meas", "tau_des"):
        for joint in (1, 2):
            field = f"{prefix}{joint}"
            values = signals.get(field)
            summary[f"{field}_min_Nm"] = "" if values is None else format(min(values), ".9g")
            summary[f"{field}_max_Nm"] = "" if values is None else format(max(values), ".9g")
            if prefix == "tau_des":
                summary[f"{field}_nonzero_rows"] = "" if values is None else sum(x != 0 for x in values)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_root", type=Path, help="checkout root or download directory preserving source paths")
    parser.add_argument("output", type=Path, help="output CSV file")
    parser.add_argument("--manifest", type=Path, default=Path(__file__).with_name("dfki-sysid-source.json"))
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    records = [f for f in manifest["files"] if f["type"] == "record"]
    results = [summarize(args.source_root, entry) for entry in records]
    with args.output.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=results[0], lineterminator="\n")
        writer.writeheader()
        writer.writerows(results)


if __name__ == "__main__":
    main()
