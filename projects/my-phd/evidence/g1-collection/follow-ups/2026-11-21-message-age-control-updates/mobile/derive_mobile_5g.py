"""Recalculate Lapland ROS1 and UPV n40 summaries from two pinned Zenodo releases."""
import argparse
import csv
import hashlib
import io
import json
import math
import re
from datetime import time
from pathlib import Path
from statistics import mean, median
from zipfile import ZipFile


def summarize(values):
    ordered = sorted(values)
    if not ordered or not all(math.isfinite(v) and v >= 0 for v in ordered):
        raise ValueError("Expected nonnegative finite timing measurements")
    return {k: round(v, 6) for k, v in [
        ("min", ordered[0]), ("median", median(ordered)),
        ("mean", mean(ordered)), ("p95_nearest_rank", ordered[math.ceil(.95*len(ordered))-1]),
        ("max", ordered[-1]),
    ]}


def write(path, rows):
    with path.open("w", encoding="utf-8", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=rows[0], lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def checked_path(source, entry):
    path = source / entry["file"]
    if path.stat().st_size != entry["bytes"] or hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
        raise ValueError(f"Release differs: {path.name}")
    return path


def lapland(path):
    with path.open(encoding="ascii", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != ["timestamp", "latency_ms"]:
            raise ValueError(f"Unexpected columns: {path.name}")
        readings = list(reader)
    ts = [float(row["timestamp"]) for row in readings]
    rtt = [float(row["latency_ms"]) for row in readings]
    gaps = [b-a for a, b in zip(ts, ts[1:])]
    if not all(math.isfinite(g) and g>0 for g in gaps):
        raise ValueError(f"Check timestamp order: {path.name}")
    return {"source_file": path.name, "rtt_rows": len(rtt), "observed_span_s": round(ts[-1]-ts[0], 6),
            "median_logger_interval_ms": round(median(gaps)*1000, 6),
            "max_logger_interval_ms": round(max(gaps)*1000, 6),
            **{f"rtt_{k}_ms": v for k, v in summarize(rtt).items()},
            "rtt_over_100_ms": sum(v>100 for v in rtt)}


def upv_handset(raw, test, handset):
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig", errors="strict")), delimiter=";")
    rows = list(reader)
    values = [float(r["RTT"]) for r in rows if r["RTT"].strip()]
    times = [time.fromisoformat(r["Time"]) for r in rows if r["RTT"].strip()]
    both = sum(bool(r["RTT"].strip() and r["Velocity"].strip()) for r in rows)
    return {"archive_test_folder": test, "ue": handset, "event_rows": len(rows),
            "rtt_values": len(values), "velocity_values": sum(bool(r["Velocity"].strip()) for r in rows),
            "rtt_and_velocity_same_row": both, "distinct_rtt_clock_values": len(set(times)),
            "cross_scenario_use": "unresolved file/time mapping" if test in (1,2) else "as deposited; separate device clocks",
            **{f"ping_rtt_{k}_source_units": v for k, v in summarize(values).items()}}


def upv_network(raw, test):
    rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
    ticks = [int(r["timestamp"]) for r in rows]
    if ticks != list(range(2000,ticks[-1]+1,2000)):
        raise ValueError(f"Unexpected reporting grid in test {test}")
    retained = rows if test != 2 else [r for r in rows if int(r["timestamp"])<=ticks[-1]-60000]
    delays = [float(r["One-Way Delay"]) for r in retained if r["One-Way Delay"]!="N/A"]
    final = rows[-1]
    return {"test": test, "export_windows": len(rows), "retained_windows": len(retained),
            "retained_valid_delay_windows": len(delays), "excluded_last_minute_windows": len(rows)-len(retained),
            **{f"one_way_delay_window_{k}_ms": v for k, v in summarize(delays).items()},
            "whole_export_final_estimated_error_ms": final["Estimated Error"],
            "whole_export_final_maximum_error_ms": final["Maximum Error"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_folder", type=Path)
    parser.add_argument("output_folder", type=Path)
    args = parser.parse_args()
    manifest = json.loads(Path(__file__).with_name("mobile-5g-sources.json").read_text())
    results = [lapland(checked_path(args.input_folder,r)) for r in manifest["lapland"]["verified_inputs"]]
    archive = checked_path(args.input_folder,manifest["upv"]["verified_inputs"][0])
    handsets, networks = [], []
    with ZipFile(archive) as z:
        if z.testzip():
            raise ValueError("Archive member CRC mismatch")
        for member in z.namelist():
            path = Path(member)
            if len(path.parts) < 3:
                continue
            match = re.fullmatch(r"Test_([1-6])", path.parts[1])
            if not match: continue
            test = int(match.group(1))
            if path.name == "ixchariot.csv":
                networks.append(upv_network(z.read(member), test))
            else:
                device = re.fullmatch(r"Test[ _]\d+[ _](Asus|S25)\.csv",path.name,re.I)
                if device:
                    handsets.append(upv_handset(z.read(member),test,device.group(1).upper()))
    if sorted(r['test'] for r in networks)!=list(range(1,7)) or {(r['archive_test_folder'],r['ue']) for r in handsets}!={(i,j) for i in range(1,7) for j in ('ASUS','S25')} or len(handsets)!=12:
        raise ValueError("Unexpected file coverage")
    args.output_folder.mkdir(exist_ok=True,parents=True)
    write(args.output_folder/"lapland-ros1-rtt.csv",results)
    write(args.output_folder/"upv-handset-ping.csv",sorted(handsets,key=lambda r:(r["archive_test_folder"],r["ue"])))
    write(args.output_folder/"upv-network-windows.csv",sorted(networks,key=lambda r:r["test"]))


if __name__ == "__main__":
    main()
