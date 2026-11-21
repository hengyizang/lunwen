"""Summarize the two-KR3 Zenodo v1 release. Uses Python 3.11+ standard library."""

import argparse
import csv
import hashlib
import io
import math
from pathlib import Path
import re
from statistics import fmean, median
from zipfile import ZipFile


SOURCE_MD5 = "efe9394bf2579f380832eed6d501c614"
TRACE_NAME = re.compile(r"Robot_(R[12])/collector_(\d+)_(\d+)\.csv")
COLUMNS = [f"Iststrom_A{i} (A)" for i in range(1, 7)] + ["Sample"]


def excursions(values, threshold):
    """Group A2 positive excursions. Return indices into the original trace."""
    groups = []
    for i, value in enumerate(values):
        if value > threshold:
            if not groups or i - groups[-1][-1] > 150:
                groups.append([])
            groups[-1].append(i)
    return groups


def write_csv(output, name, rows):
    with (output / name).open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def trace_summary(content, name, robot, mass, series):
    reader = csv.reader(io.StringIO(content.decode("utf-8")), delimiter=";")
    if next(reader) != COLUMNS:
        raise ValueError(f"Unexpected columns in {name}")
    currents = [[] for axis in range(6)]
    samples = []
    for values in reader:
        if len(values) != 7:
            raise ValueError(f"Invalid row in {name}")
        for axis, value in enumerate(values[:-1]):
            amps = float(value)
            if not math.isfinite(amps):
                raise ValueError(f"Invalid current in {name}")
            currents[axis].append(amps)
        samples.append(int(values[-1]))
    steps = [b-a for a, b in zip(samples, samples[1:])]
    row = {"robot":robot,"series":series,"payload_g":mass,"source_member":name,
           "sha256":hashlib.sha256(content).hexdigest(),"trace_rows":len(samples),
           "first_sample_value":samples[0],"last_sample_value":samples[-1],
           "min_sample_increment":min(steps),"max_sample_increment":max(steps),
           "increments_equal_to_four":steps.count(4)}
    for axis, channel in enumerate(currents, 1):
        row[f"a{axis}_min_A"] = round(min(channel), 9)
        row[f"a{axis}_max_A"] = round(max(channel), 9)
        row[f"a{axis}_rms_A"] = round(math.sqrt(fmean(x*x for x in channel)), 9)
    a2 = currents[1]
    selected = excursions(a2, 1.0)
    row["clusters_over_0p8A"] = len(excursions(a2, 0.8))
    row["clusters_over_1p0A"] = len(selected)
    row["clusters_over_1p2A"] = len(excursions(a2, 1.2))
    peaks = []
    previous_peak = None
    for number, group in enumerate(selected, 1):
        peak = max(group, key=a2.__getitem__)
        peaks.append({"robot":robot,"series":series,"payload_g":mass,"cluster_in_trace":number,
                      "first_row_over_1A_zero_based":group[0],"last_row_over_1A_zero_based":group[-1],
                      "rows_over_1A":len(group),"peak_row_zero_based":peak,
                      "peak_A":round(a2[peak], 9),"peak_sample_value":samples[peak],
                      "rows_since_previous_peak":"" if previous_peak is None else peak-previous_peak})
        previous_peak = peak
    return row, peaks


def compare_payloads(traces):
    # Pair by increasing stack rank; actual masses on the two units may differ.
    conditions = []
    mass_lists = {r: sorted({t["payload_g"] for t in traces if t["robot"] == r}) for r in ("R1","R2")}
    if any(len(masses) != 16 for masses in mass_lists.values()):
        raise ValueError("Unexpected payload grid")
    for rank, (m1,m2) in enumerate(zip(mass_lists["R1"], mass_lists["R2"]), 1):
        row = {"stack_rank":rank, "r1_payload_g":m1,"r2_payload_g":m2,"r2_minus_r1_payload_g":m2-m1}
        for robot, mass in (("R1",m1),("R2",m2)):
            group = [t for t in traces if t["robot"] == robot and t["payload_g"] == mass]
            if len(group) != 4 or len({t["series"] for t in group}) != 4:
                raise ValueError("Unexpected recording count")
            rms = [t["a2_rms_A"] for t in group]
            prefix = robot.lower()
            row[f"{prefix}_recordings"] = len(group)
            row[f"{prefix}_a2_rms_min_A"] = min(rms)
            row[f"{prefix}_a2_rms_median_A"] = round(median(rms),9)
            row[f"{prefix}_a2_rms_max_A"] = max(rms)
        row["r2_minus_r1_a2_rms_median_A"] = round(row["r2_a2_rms_median_A"]-row["r1_a2_rms_median_A"],9)
        conditions.append(row)
    return conditions


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive",type=Path)
    parser.add_argument("output",type=Path)
    args=parser.parse_args()
    with args.archive.open("rb") as source:
        if hashlib.file_digest(source, "md5").hexdigest() != SOURCE_MD5:
            raise ValueError("Archive differs from the published Zenodo v1 checksum")
    traces, peaks = [], []
    with ZipFile(args.archive) as z:
        members = sorted(name for name in z.namelist() if name.lower().endswith(".csv"))
        if len(members) != 128 or len(set(members)) != len(members):
            raise ValueError("Unexpected trace coverage")
        for name in members:
            parsed = TRACE_NAME.fullmatch(name)
            if parsed is None:
                raise ValueError(f"Unexpected member: {name}")
            robot, mass, series = parsed.groups()
            if int(series) not in (range(1,5) if robot=="R1" else range(5,9)):
                raise ValueError(f"Unexpected series: {name}")
            row, extracted = trace_summary(z.read(name), name, robot, int(mass), int(series))
            traces.append(row)
            peaks.extend(extracted)
    args.output.mkdir(parents=True,exist_ok=True)
    write_csv(args.output, "kr3-current-traces.csv", sorted(traces,key=lambda r:(r["series"],r["payload_g"])))
    write_csv(args.output, "kr3-current-excursions.csv", sorted(peaks,key=lambda r:(r["series"],r["payload_g"],r["cluster_in_trace"])))
    write_csv(args.output, "kr3-payload-pairs.csv", compare_payloads(traces))


if __name__ == "__main__":
    main()
