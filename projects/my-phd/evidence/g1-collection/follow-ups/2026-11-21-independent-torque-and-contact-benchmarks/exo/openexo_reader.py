"""Recalculate OpenExo pulse and walking summaries. Requires SciPy and openpyxl.

    python openexo_reader.py DOWNLOAD_CACHE OUTPUT_DIRECTORY

Raw binary inputs are verified against fixed Git blob IDs from openexo-source.json.
"""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

from openpyxl import load_workbook
from scipy.io import loadmat


def fetch(cache, source, suffix):
    item = next(x for x in source["inputs"] if x["path"].endswith(suffix))
    path = cache / item["path"]
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        url = ("https://raw.githubusercontent.com/" + source["repository"] + "/"
               + source["fixed_commit"] + "/" + quote(item["path"]))
        req = Request(url, headers={"User-Agent": "openexo-g1-research"})
        with urlopen(req, timeout=90) as response:
            data = response.read()
    else:
        data = path.read_bytes()
    header = f"blob {len(data)}\0".encode("ascii")
    if hashlib.sha1(header + data).hexdigest() != item["git_blob_sha1"]:
        raise ValueError(f"Git blob SHA-1 mismatch in {path}")
    if not path.exists():
        path.write_bytes(data)
    return path


def clean(value):
    if isinstance(value, float):
        return format(value, ".6f").rstrip("0").rstrip(".") if value != 0 else "0"
    return value


def write(path, columns, records):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(columns.split(","))
        writer.writerows([clean(x) for x in row] for row in records)


def pulses(path, joint, sign):
    data = loadmat(path)["data"]
    values = data[:, 0].reshape(-1, 3)
    channels = data[:, 1].reshape(-1, 3)
    if not (channels == (100, 200, 300)).all():
        raise ValueError(f"Changed multiplexing in {path}")
    commands = values[:, 0] * sign
    measured = values[:, 1] * sign
    times = values[:, 2]
    start = 0
    count = 0
    for end in range(1, len(commands) + 1):
        if end < len(commands) and commands[end] == commands[start]:
            continue
        cmd = commands[start]
        if cmd:
            count += 1
            trace = measured[start:end]
            t = times[start:end]
            t10 = next((float(ms) for x, ms in zip(trace, t) if x >= .1 * cmd), None)
            t90 = next((float(ms) for x, ms in zip(trace, t) if x >= .9 * cmd), None)
            rise = t90 - t10 if t90 is not None and t10 is not None else None
            tail = trace[math.floor(.8 * len(trace)):]
            yield [joint, count, start, len(t), float(cmd), float(t[0]), float(t[-1]),
                   t10, t90, rise, float(max(trace)), float(sum(tail) / len(tail)),
                   int((t[1:] < t[:-1]).sum())]
        start = end


def walking(path, joint, sign):
    sheet = load_workbook(path, read_only=True, data_only=True)
    try:
        channels = {}
        for row in sheet.active.values:
            if row[0] in ("LSetP", "LTorque"):
                channels[row[0]] = row[1:]
    finally:
        sheet.close()
    pairs = [(sign * cmd, sign * measured)
             for cmd, measured in zip(channels["LSetP"], channels["LTorque"])
             if isinstance(cmd, (int, float)) and isinstance(measured, (int, float))
             and math.isfinite(cmd) and math.isfinite(measured)]
    for label in ("all", "nonzero_command", "zero_command"):
        subset = [(c, m) for c, m in pairs
                  if label == "all" or (label == "nonzero_command") == (c != 0)]
        commands, measured = zip(*subset)
        errors = [m - c for c, m in subset]
        n = len(errors)
        yield [joint, label, n, min(commands), max(commands), min(measured), max(measured),
               sum(errors) / n, math.sqrt(sum(e * e for e in errors) / n)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cache", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.mkdir(exist_ok=True, parents=True)
    source = json.loads(Path(__file__).with_name("openexo-source.json").read_text(encoding="utf-8"))
    step_rows, walk_rows = [], []
    for joint, filename, sign in (("ankle", "AnkleStep.mat", -1), ("hip", "Step.mat", 1)):
        prefix = "/Engineering/" + joint.capitalize()
        steps = fetch(args.cache, source, prefix + "/Step_Response/" + filename)
        walk = fetch(args.cache, source, prefix + "/RMSE/Walk_Test.xlsx")
        step_rows.extend(pulses(steps, joint, sign))
        walk_rows.extend(walking(walk, joint, sign))
    write(args.output / "openexo-step-pulses.csv",
          "joint,pulse,start_sample_zero_based,paired_samples,command_Nm,t_first_ms,t_last_ms,"
          "first_at_10pct_ms,first_at_90pct_ms,sampled_rise_ms,measured_peak_Nm,"
          "mean_last_20pct_Nm,backward_time_steps", step_rows)
    write(args.output / "openexo-walking.csv",
          "joint,selection,finite_left_pairs,command_min_Nm,command_max_Nm,measured_min_Nm,"
          "measured_max_Nm,mean_measured_minus_command_Nm,rmse_Nm", walk_rows)


if __name__ == "__main__":
    main()
