"""Reproduce timing summaries for all raw idUS cart-pole hardware recordings."""
import argparse
import csv
import hashlib
import io
import math
import re
import statistics
from collections import Counter
from pathlib import Path
from zipfile import ZipFile

RAW = re.compile(r"data/raw/(trajectories|balancing)/(?:MPC/|SECLOC/)?(MPC|SECLOC)_(T\d{2}|BAL)_R(\d+)\.csv")
ARCHIVE_MD5 = "3b54517dbe3ed306a707017d20ee131c"


def summarize(z, name, match):
    data = z.read(name)
    stream = io.TextIOWrapper(io.BytesIO(data), encoding="utf-8-sig", newline="")
    fields = csv.reader(line for line in stream if line.strip() and not line.startswith("#"))
    header = next(fields)
    chip_i, command_i, flag_i, step_i = [header.index(k) for k in
        ("time_chip", "Q", "controller_update_applied", "controller_steptime")]
    # The first and last board times bound each recording. A few interior
    # readings jump far outside that range and return on the very next row.
    last_line = data.rstrip().rsplit(b"\n", 1)[-1].decode("utf-8")
    end_chip = float(next(csv.reader([last_line]))[chip_i])
    previous_chip_valid = False
    condition, mode, trajectory, rep = match.groups()
    skip_i = header.index("secloc_gate_skipped") if mode == "SECLOC" else None
    skip2_i = header.index("secloc_skipped_update") if mode == "SECLOC" else None
    counts = Counter()
    compute = []
    execution_intervals_us = []
    previous_execution_chip = None
    continuous_since_execution = True
    first_chip = last_chip = last_flag = last_q = None
    max_dt = consecutive_holds = max_holds = 0
    for samples, row in enumerate(fields, 1):
        if len(row) != len(header):
            raise ValueError(f"Malformed source row: {name}, {samples}")
        chip, q = float(row[chip_i]), float(row[command_i])
        flag, step = int(row[flag_i]), float(row[step_i])
        if flag not in (0, 1) or not all(math.isfinite(v) for v in (chip, q, step)):
            raise ValueError(f"Invalid timing or update: {name}, {samples}")
        if skip_i is not None and (int(row[skip_i]) != 1-flag or int(row[skip2_i]) != 1-flag):
            counts["skip_flag_disagreements"] += 1
        if flag:
            counts["updates"] += 1
            compute.append(step)
            consecutive_holds = 0
        else:
            consecutive_holds += 1
            max_holds = max(max_holds, consecutive_holds)
        if first_chip is None:
            first_chip = chip
            if not math.isfinite(end_chip) or end_chip <= first_chip:
                raise ValueError(f"Unusable recording time boundaries: {name}")
        chip_valid = first_chip <= chip <= end_chip
        if not chip_valid:
            counts["out_of_span_clock_rows"] += 1
        if last_chip is not None and (not chip_valid or not previous_chip_valid):
            counts["clock_invalid_pairs"] += 1
            continuous_since_execution = False
        elif last_chip is not None:
            delta_us = round((chip-last_chip)*1_000_000)
            ticks = round(delta_us/10000)
            max_dt = max(max_dt, delta_us)
            # Require agreement with the nominal grid to 1 ms before assigning a missing tick count.
            if ticks < 1 or abs(delta_us-10000*ticks)>1000:
                counts["off_grid_intervals"] += 1
                continuous_since_execution = False
            elif ticks>1:
                counts["gap_intervals"] += 1
                continuous_since_execution = False
                counts["missing_grid_ticks"] += ticks-1
            else:
                # The published command is delayed by one recorded row. Compare only single-tick neighbors.
                counts["update_pairs" if last_flag else "hold_pairs"] += 1
                if abs(q-last_q)>1e-7:
                    counts["changes_after_update" if last_flag else "changes_after_hold"] += 1
                elif last_flag and abs(abs(q)-1.0) <= 1e-7 and abs(abs(last_q)-1.0) <= 1e-7:
                    counts["unchanged_after_update_at_bound"] += 1
        if flag:
            if previous_execution_chip is not None:
                if continuous_since_execution:
                    execution_intervals_us.append(round((chip - previous_execution_chip) * 1_000_000))
                else:
                    counts["execution_intervals_across_gaps"] += 1
            previous_execution_chip = chip
            continuous_since_execution = True
        previous_chip_valid = chip_valid
        last_chip, last_flag, last_q = chip, flag, q
    usable_pairs = counts["gap_intervals"] + counts["off_grid_intervals"] + counts["update_pairs"] + counts["hold_pairs"]
    if counts["clock_invalid_pairs"] + usable_pairs != samples - 1:
        raise ValueError(f"Recorded-step accounting mismatch: {name}")
    count = counts["updates"]
    execution_intervals_us.sort()
    n = len(execution_intervals_us)
    if n + counts["execution_intervals_across_gaps"] != max(0, count - 1):
        raise ValueError(f"Execution interval accounting mismatch: {name}")
    return {"source_member":name,"sha256":hashlib.sha256(data).hexdigest(),
            "mode":mode,"task":condition,"target_sequence":trajectory,"repetition":int(rep),
            "recorded_rows":samples,"controller_executions":count,"skipped_rows":samples-count,
            "skip_flag_disagreements":counts["skip_flag_disagreements"],
            "max_consecutive_skipped_observed_rows":max_holds,
            "continuous_execution_intervals":n,
            "execution_intervals_across_gaps":counts["execution_intervals_across_gaps"],
            "median_continuous_execution_interval_ms":statistics.median(execution_intervals_us)/1000 if n else "",
            "p95_continuous_execution_interval_ms":execution_intervals_us[math.ceil(0.95*n)-1]/1000 if n else "",
            "max_continuous_execution_interval_ms":execution_intervals_us[-1]/1000 if n else "",
            "board_span_s":round(last_chip-first_chip,6),"max_board_step_us":max_dt,
            "out_of_span_clock_rows":counts["out_of_span_clock_rows"],"clock_invalid_pairs":counts["clock_invalid_pairs"],
            "gap_intervals":counts["gap_intervals"],"inferred_missing_grid_ticks":counts["missing_grid_ticks"],
            "off_grid_intervals":counts["off_grid_intervals"],
            "one_tick_pairs_after_update":counts["update_pairs"],"changed_Q_after_update":counts["changes_after_update"],
            "unchanged_Q_after_update_at_normalized_bound":counts["unchanged_after_update_at_bound"],
            "one_tick_pairs_after_hold":counts["hold_pairs"],"changed_Q_after_hold":counts["changes_after_hold"],
            "median_compute_ms_on_executed_rows":round(1000*statistics.median(compute),6) if compute else ""}


def write(path, rows):
    with path.open("w", encoding="utf-8", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=rows[0], lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("output", type=Path)
    args=parser.parse_args()
    with args.archive.open("rb") as source:
        if hashlib.file_digest(source,"md5").hexdigest()!=ARCHIVE_MD5:
            raise ValueError("Archive differs from the institutional release")
    with ZipFile(args.archive) as z:
        names=[n for n in z.namelist() if n.startswith("data/raw/") and n.endswith(".csv")]
        if len(set(names))!=1010 or len(names)!=1010:
            raise ValueError("Unexpected number of raw CSVs")
        runs=[]
        for name in sorted(names):
            match=RAW.fullmatch(name)
            if not match: raise ValueError(f"Unexpected raw experiment: {name}")
            runs.append(summarize(z,name,match))
    groups=[]
    for mode,task in sorted({(r["mode"],r["task"]) for r in runs}):
        subset=[r for r in runs if (r["mode"],r["task"])==(mode,task)]
        if len(subset)!=(5 if task=="balancing" else 500):
            raise ValueError("Unexpected condition coverage")
        summary={"mode":mode,"task":task,"runs":len(subset)}
        for k in ("recorded_rows","controller_executions","skipped_rows","skip_flag_disagreements",
                  "out_of_span_clock_rows","clock_invalid_pairs","gap_intervals","inferred_missing_grid_ticks","off_grid_intervals","continuous_execution_intervals",
                  "execution_intervals_across_gaps","one_tick_pairs_after_update",
                  "changed_Q_after_update","unchanged_Q_after_update_at_normalized_bound","one_tick_pairs_after_hold","changed_Q_after_hold"):
            summary[k]=sum(r[k] for r in subset)
        observed = [r["max_continuous_execution_interval_ms"] for r in subset
                    if r["max_continuous_execution_interval_ms"] != ""]
        summary["max_continuous_execution_interval_ms"] = max(observed) if observed else ""
        groups.append(summary)
    args.output.mkdir(parents=True,exist_ok=True)
    write(args.output/"cartpole-runs.csv",runs)
    write(args.output/"cartpole-groups.csv",groups)


if __name__=="__main__":
    main()
