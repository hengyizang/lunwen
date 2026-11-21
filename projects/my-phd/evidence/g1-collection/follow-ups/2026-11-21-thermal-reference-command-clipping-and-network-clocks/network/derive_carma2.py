"""Usage: python derive_carma2.py CARMA2.csv Testing_Logs_-_CARMA_2.xlsx OUTPUT_DIRECTORY

Requires Python 3.11+ and openpyxl. Produces CC BY-SA 3.0 derivatives of USDOT's CARMA 2
(10.21949/1504485). Retains one state only if all non-runid cells agree.
"""
import csv
import hashlib
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

from openpyxl import load_workbook

source, logbook, output = map(Path, sys.argv[1:4])
with logbook.open("rb") as handle:
    if hashlib.file_digest(handle,"sha256").hexdigest() != "fe93cd4286d3cfa195e564fb9e6f4357d4af4a48f4a776f5829cc5904dca60dc":
        raise ValueError("Testing log has changed")
workbook = load_workbook(logbook, data_only=True, read_only=True)
meta = {}
for run, start, stop, *fields in list(workbook.active.values)[1:]:
    roles = dict(zip(("BLACK","GREEN","GREY","SILVER","WHITE","TRUCK1"), fields[:6]))
    meta[run] = (roles, *fields[6:9])
workbook.close()
expected_sha256 = "05e048e678d640715e9cfbc583931a11b7e467af8b30e27c64e60716f7fe1e42"
with source.open("rb") as handle:
    if hashlib.file_digest(handle, "sha256").hexdigest() != expected_sha256:
        raise ValueError("Source has changed. Re-audit source version before comparing hashes.")
output.mkdir(exist_ok=True, parents=True)
raw_counts = Counter()
measurements = defaultdict(set)
all_cells = defaultdict(set)
with source.open(newline="") as handle:
    reader = csv.reader(handle)
    header = next(reader)
    keep = [i for i, name in enumerate(header) if not name.lower().startswith("runid_")]
    irun, ielapsed = map(header.index, ["RunNo", "Elapsed_Time"])
    for row in reader:
        assert len(row) == len(header) and all("\x1f" not in item for item in row)
        key = int(row[irun]), float(row[ielapsed])
        raw_counts[key] += 1
        measurements[key].add(hashlib.sha256("\x1f".join(row[i] for i in keep).encode()).digest())
        all_cells[key].add(hashlib.sha256("\x1f".join(row).encode()).digest())

def write_csv(name, rows):
    with (output / name).open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0], lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

checks = []
for run in sorted(set(key[0] for key in raw_counts)):
    bins = [key for key in raw_counts if key[0] == run]
    checks.append(dict(run=run, raw_rows=sum(raw_counts[k] for k in bins), unique_run_time_bins=len(bins),
        bins_repeated=sum(raw_counts[k] > 1 for k in bins), max_raw_rows_per_bin=max(raw_counts[k] for k in bins),
        distinct_full_rows=sum(len(all_cells[k]) for k in bins),
        bins_agree_excluding_runid=sum(len(measurements[k]) == 1 for k in bins),
        bins_conflict_excluding_runid=sum(len(measurements[k]) > 1 for k in bins)))
write_csv("carma2-bin-quality.csv", checks)

channels = dict(
    p29="acc_axle_torque_cmd_axle_torque_request",
    p5_immediate="p5_commanded_axle_torque_immediate", p5_predicted="p5_commanded_axle_torque_predicted",
    injected="research_bus_injected_torque_cacc_mab", gps_m_s="velocity_fwd_admas",
    acceleration="p29_actual_vehicle_acceleration", brake="brklightflag_srx")
vehicles = [name.removeprefix("veh_color_") for name in header if name.startswith("veh_color_")]
fields = {v: {short: header.index(field + "_" + v) for short, field in channels.items()} for v in vehicles}
mode_col = {v: header.index("command_mode_cacc_" + v) for v in vehicles}
seen = set()
stats = defaultdict(Counter)
minimum, maximum = {}, {}
with source.open(newline="") as handle:
    reader = csv.reader(handle)
    next(reader)
    for row in reader:
        bin_key = int(row[irun]), float(row[ielapsed])
        if bin_key in seen or len(measurements[bin_key]) != 1:
            continue
        seen.add(bin_key)
        for v in vehicles:
            if not any(row[i] for i in fields[v].values()):
                continue
            group = (bin_key[0], v, row[mode_col[v]])
            n = stats[group]
            n["observed_bins"] += 1
            val = {label: float(row[i]) for label, i in fields[v].items() if row[i]}
            assert all(math.isfinite(x) for x in val.values())
            for name, x in val.items():
                n[name + "_n"] += 1
                minimum[group, name] = min(minimum.get((group,name), x), x)
                maximum[group, name] = max(maximum.get((group,name), x), x)
            if "p29" not in val:
                continue
            torque = val["p29"]
            n["p29_at_minus500"] += torque == -500
            n["p29_at_2000"] += torque == 2000
            n["p29_below_minus500"] += torque < -500
            n["p29_above_2000"] += torque > 2000
            for other in ("p5_immediate", "p5_predicted", "injected"):
                if other in val:
                    n["paired_p29_" + other] += 1
                    n["exactly_equal_p29_" + other] += torque == val[other]
            if torque == -500:
                n["p29_minus500_with_brake"] += "brake" in val
                n["p29_minus500_brake_lit"] += val.get("brake") == 1
                n["p29_minus500_with_gps_speed"] += "gps_m_s" in val
summary = []
for group,n in sorted(stats.items()):
    roles, application, route, procedure = meta[group[0]]
    row = dict(run=group[0], vehicle=group[1], logged_role=roles[group[1]], application=application,
               route=route, procedure=procedure, recorded_command_mode=group[2], observed_bins=n["observed_bins"])
    for name in channels:
        row[name + "_n"] = n[name + "_n"]
        row[name + "_min"] = minimum.get((group,name),"")
        row[name + "_max"] = maximum.get((group,name),"")
    for k in ("p29_at_minus500", "p29_at_2000", "p29_below_minus500", "p29_above_2000",
              "paired_p29_p5_immediate", "exactly_equal_p29_p5_immediate", "paired_p29_p5_predicted",
              "exactly_equal_p29_p5_predicted", "paired_p29_injected", "exactly_equal_p29_injected",
              "p29_minus500_with_brake", "p29_minus500_brake_lit", "p29_minus500_with_gps_speed"):
        row[k] = n[k]
    summary.append(row)
write_csv("carma2-command-audit.csv", summary)
