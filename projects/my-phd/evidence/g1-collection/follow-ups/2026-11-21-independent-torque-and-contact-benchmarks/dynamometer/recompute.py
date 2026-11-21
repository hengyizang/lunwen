"""Rebuild the six original CSV summaries from immutable public Git objects.

Python 3.10+. Run: python recompute.py OUTPUT_DIR [--cache INPUT_CACHE_DIR]
Checks byte size and git-blob SHA-1 on downloads and cached inputs.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import csv
import hashlib
import io
import json
import math
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent


def download(arguments):
    source, entry, cache = arguments
    path = entry["path"]
    cached = cache / entry["git_blob_sha1"]
    if cached.exists():
        data = cached.read_bytes()
    else:
        url = source["source_url_template"].replace("{path}", quote(path))
        with urlopen(Request(url, headers={"User-Agent": "G1-release-evidence"}), timeout=90) as resp:
            data = resp.read()
    blob = hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()
    if blob != entry["git_blob_sha1"] or len(data) != entry["bytes"]:
        raise ValueError(f"Upstream version mismatch: {path}")
    if not cached.exists():
        cached.write_bytes(data)
    return path, data.decode("utf-8-sig")


def write(out, filename, fields, rows):
    with (out / filename).open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(fields.split(","))
        writer.writerows(rows)


def parse(data):
    return list(csv.DictReader(io.StringIO(data)))


def odrive(out, source, files):
    a, b = source["raw_paths"]
    if files[a] != files[b]:
        raise ValueError("Published copies of the operating-point table differ")
    # First three lines are the run timestamp, names and units.
    data = [list(map(float, row)) for row in list(csv.reader(io.StringIO(files[a])))[3:]]
    eligible = [row for row in data if len(row) == 19 and all(map(math.isfinite, row))]
    value = lambda index: [x[index] for x in eligible]
    values = [len(data), len(eligible), len({v for v in value(11) if v > 0}),
              sum(r[10] * r[11] < 0 for r in eligible), value(1).count(0), value(2).count(0)]
    for k, precision in ((9, 1), (10, 6), (11, 6)):
        values.extend(f"{v:.{precision}f}" for v in (min(value(k)), max(value(k))))
    write(out, "odrive-operating-points.csv",
          "rows,finite_19_columns,distinct_positive_speed_requests,measured_speed_opposite_request,zero_input_current,zero_input_power,min_torque_Nmm,max_torque_Nmm,min_absorber_speed_rad_s,max_absorber_speed_rad_s,min_speed_request_rad_s,max_speed_request_rad_s",
          [values])


def steering(out, source, files):
    rows = []
    for entry in source["source_files"]:
        p = entry["path"]
        if not p.startswith("data/raw/bench_phase1/test"):
            continue
        trial = parse(files[p])
        fields = ["pos_cmd_deg", "time_s", "vel_meas_deg_s", "torque_meas_Nm", "iq_meas_A"]
        data = [r for r in trial if all(r[n] and math.isfinite(float(r[n])) for n in fields)]
        iq = [float(r["iq_meas_A"]) for r in data]
        err = [abs(float(r["torque_meas_Nm"]) - .55 * i) for r, i in zip(data, iq)]
        record = [p, entry["git_blob_sha1"], len(trial), len(data),
                  f"{max(map(abs,iq)):.4f}", f"{max(err):.8f}", sum(abs(i) >= 10 for i in iq)]
        if "/test5_" in p:
            speed = [float(r["vel_meas_deg_s"]) for r in data if float(r["pos_cmd_deg"]) == 50]
            record.extend([len(speed), f"{max(speed):.3f}"])
        else:
            record.extend(["", ""])
        rows.append(record)
    write(out, "steering-bench-runs.csv",
          "path,source_git_blob_sha1,rows,common_finite_rows,peak_abs_iq_A,max_abs_tau_minus_0p55_iq_Nm,rows_abs_iq_ge_10A,rows_at_positive_50_deg_step,peak_forward_speed_at_positive_step_deg_s",
          rows)
    path = "data/raw/bench_phase1/calibration_finalff_torque.csv"
    static = parse("\n".join(l for l in files[path].splitlines() if not l.startswith("#")))
    est = max(abs(float(r["tau_meas_Nm"]) - .55 * float(r["iq_meas_A"])) for r in static)
    gap = max(abs(float(r["tau_meas_Nm"]) - float(r["tau_dem_Nm"])) for r in static)
    write(out, "steering-static-calibration.csv",
          "levels,largest_abs_tau_minus_0p55_iq_Nm,largest_abs_measured_minus_requested_Nm",
          [[len(static), f"{est:.8f}", f"{gap:.8f}"]])


def bldc(out, source, files):
    entries = [x for x in source["source_files"] if x["path"].endswith(".csv")]
    write(out, "bldc-source-files.csv", "path,source_git_blob_sha1,rows",
          [[x["path"], x["git_blob_sha1"], len(parse(files[x["path"]]))] for x in entries])
    loads = []
    for r in parse(files["data/raw/torque_verification_raw.csv"]):
        m = float(r["mechanical_torque_Nm"])
        e = float(r["electrical_torque_Nm"])
        loads.append([r["load_condition"], f"{m:.2f}", f"{e:.2f}", f"{e-m:.3f}",
                      f"{100*abs(e-m)/m:.5f}", f"{float(r['difference_percent']):.1f}"])
    write(out, "bldc-load-comparison.csv",
          "load_condition,mechanical_Nm,electrical_Nm,electrical_minus_mechanical_Nm,abs_gap_pct_of_mechanical,source_difference_percent", loads)
    model = parse(files["data/processed/model_vs_experiment.csv"])
    ref = [float(r["experimental_speed_rpm"])-float(r["model_speed_rpm"]) for r in model]
    given = [float(r["error_rpm"]) for r in model]
    rms = lambda values: math.sqrt(sum(x*x for x in values)/len(values))
    discrepancy = max(abs(x-y) for x, y in zip(ref, given))
    write(out, "bldc-speed-comparison.csv",
          "rows,recomputed_speed_rmse_rpm,stored_error_rmse_rpm,publication_abstract_rmse_rpm,max_abs_row_error_disagreement_rpm",
          [[len(ref), f"{rms(ref):.6f}", f"{rms(given):.6f}", "14.8", f"{discrepancy:.6f}"]])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--cache", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    cache = args.cache or args.output / ".source-cache"
    cache.mkdir(parents=True, exist_ok=True)
    for release, extract in [("bldc", bldc), ("odrive", odrive), ("steering", steering)]:
        source = json.loads((HERE / f"{release}-source.json").read_text(encoding="utf-8"))
        needed = [entry for entry in source["source_files"] if entry["path"].endswith(".csv")]
        # Read identical published objects once even if multiple paths reference them.
        unique = {r["git_blob_sha1"]: r for r in needed}
        with ThreadPoolExecutor(6) as pool:
            by_path = dict(pool.map(download, ((source, e, cache) for e in unique.values())))
        files = {e["path"]: by_path[unique[e["git_blob_sha1"]]["path"]] for e in needed}
        extract(args.output, source, files)
