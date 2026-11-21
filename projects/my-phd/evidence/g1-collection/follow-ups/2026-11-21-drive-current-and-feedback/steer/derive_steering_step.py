"""Reproduce Test 5 position-step summaries from a pinned source checkout (Python 3.11+)."""
import argparse
import csv
from decimal import Decimal
import hashlib
import io
import json
from pathlib import Path
import re
from statistics import fmean, median


def average(values):
    return round(fmean(values), 9)


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as out:
        writer = csv.DictWriter(out, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def summary(file):
    match = re.fullmatch(r"t5_load_(\d\.\d)Nm_rep(\d{2})\.csv", file.name)
    if not match:
        raise ValueError(f"Unexpected filename {file}")
    load, rep = float(match[1]), int(match[2])
    data = file.read_bytes()
    rows = list(csv.DictReader(io.StringIO(data.decode("utf-8-sig"))))
    cond = f"load_{load:.1f}Nm"
    for row in rows:
        if int(row["rep_id"]) != rep or row["condition"] != cond or float(row["torque_cmd_Nm"]) != load:
            raise ValueError(f"Condition mismatch in {file}")
        if float(row["vel_cmd_deg_s"]) != 0:
            raise ValueError(f"Unexpected velocity feedforward in {file}")
    def values(name):
        return [float(r[name]) for r in rows]
    times = values("time_s")
    steps_ms = [round(1000*(b-a), 4) for a,b in zip(times,times[1:])]
    if min(steps_ms) <= 0:
        raise ValueError(f"Nonmonotone host time in {file}")
    commands = values("pos_cmd_deg")
    step = commands.index(50.0)
    if not step or commands[:step] != [-50.0]*step or commands[step:] != [50.0]*(len(rows)-step):
        raise ValueError(f"Unexpected command step in {file}")
    speeds = values("vel_meas_deg_s")
    positions = values("pos_meas_deg")
    current = values("iq_meas_A")
    volts = values("vbus_V")
    peaks = speeds[step:]
    peak = step + peaks.index(max(peaks))
    tail = [abs(50.0-p) for t,p in zip(times,positions) if t >= 0.8]
    torque_delta = [abs(Decimal(r["torque_meas_Nm"])-Decimal("0.55")*Decimal(r["iq_meas_A"])) for r in rows]
    return {"file":file.name,"sha256":hashlib.sha256(data).hexdigest(),"load_setting_Nm":load,
            "repetition":rep,"rows":len(rows),"rows_before_step":step,
            "step_first_time_s":times[step],"last_time_s":times[-1],
            "min_host_dt_ms":min(steps_ms),"median_host_dt_ms":median(steps_ms),"max_host_dt_ms":max(steps_ms),
            "position_at_first_poststep_sample_deg":positions[step],
            "poststep_peak_forward_speed_deg_s":max(peaks),"time_from_step_to_first_peak_s":round(times[peak]-times[step],4),
            "poststep_peak_abs_iq_A":max(abs(x) for x in current[step:]),
            "prerise_mean_iq_A":average(current[:step]),"poststep_position_max_deg":max(positions[step:]),
            "t_ge_0p8s_mean_abs_position_error_deg":average(tail),
            "whole_trace_peak_abs_iq_A":max(abs(x) for x in current),
            "whole_trace_peak_forward_speed_deg_s":max(speeds),
            "vbus_min_V":min(volts),"vbus_max_V":max(volts),
            "vbus_rows_outside_stock_mock_range":sum(v<23.9 or v>24.1 for v in volts),
            "position_rows_off_stock_mock_grid":sum(Decimal(r["pos_meas_deg"])%Decimal("0.125")!=0 for r in rows),
            "torque_vs_0p55iq_largest_abs_discrepancy_Nm":str(max(torque_delta))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkout", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    manifest = json.loads((Path(__file__).parent / "steering-step-source.json").read_text())["trace_sha256"]
    path = args.checkout / "data/raw/bench_phase1/test5_torque_speed_load"
    traces = [summary(f) for f in sorted(path.glob("*.csv"))]
    if {r["file"]: r["sha256"] for r in traces} != manifest:
        raise ValueError("Trace files differ from the pinned release")
    groups = []
    for load in sorted({r["load_setting_Nm"] for r in traces}):
        subset = [r for r in traces if r["load_setting_Nm"]==load]
        if {r["repetition"] for r in subset} != set(range(1,6)):
            raise ValueError(f"Unexpected repetitions for load {load}")
        groups.append({"load_setting_Nm":load,"traces":len(subset),"rows":sum(r["rows"] for r in subset),
                       "prestep_rows":sum(r["rows_before_step"] for r in subset),
                       "mean_of_trace_peaks_deg_s":average(r["whole_trace_peak_forward_speed_deg_s"] for r in subset),
                       "poststep_mean_of_peaks_deg_s":average(r["poststep_peak_forward_speed_deg_s"] for r in subset),
                       "poststep_min_of_peaks_deg_s":min(r["poststep_peak_forward_speed_deg_s"] for r in subset),
                       "poststep_max_of_peaks_deg_s":max(r["poststep_peak_forward_speed_deg_s"] for r in subset),
                       "mean_of_peak_abs_current_A":average(r["whole_trace_peak_abs_iq_A"] for r in subset),
                       "poststep_mean_of_peak_abs_current_A":average(r["poststep_peak_abs_iq_A"] for r in subset),
                       "mean_of_late_mean_abs_position_error_deg":average(r["t_ge_0p8s_mean_abs_position_error_deg"] for r in subset)})
    args.output.mkdir(parents=True,exist_ok=True)
    write_csv(args.output/"steering-step-traces.csv",traces)
    write_csv(args.output/"steering-step-groups.csv",groups)


if __name__ == "__main__":
    main()
