"""Audit registered tests, serial T records and published maxima for TTnet v2.1.

Usage: python derive_ttnet.py data_raw.zip PATH_TO_data_processed OUTPUT_DIR
"""
import argparse
import csv
import hashlib
import io
import math
import re
import statistics
from collections import defaultdict
from pathlib import Path
from zipfile import ZipFile


def rows(file):
    with file.open(newline="", encoding="utf-8") as source:
        return list(csv.DictReader(source))


def write(path, data):
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=data[0], lineterminator="\n")
        writer.writeheader()
        writer.writerows(data)


def serial_times(content):
    """Observer timestamps refer to serial prints. T is a firmware-reported interval in us."""
    times = defaultdict(set)
    sequence = defaultdict(list)
    for line in content.splitlines():
        fields = line.split(b",", 4)
        if len(fields) != 5:
            continue
        stamp = re.search(rb"\[\s*(\d+)\] T:\s*(\d+)\s*$", fields[4])
        if stamp:
            node = int(fields[2])
            value = int(stamp[2])
            times[node].add(value)
            sequence[node].append(value)
    return times, sequence


def audit_series(archive, processed, series):
    admissions = archive.read(f"data_raw/{series}/{series}.txt").decode()
    booked = set(map(int, re.findall(r"Test ID:\s*(\d+)", admissions)))
    node_data = defaultdict(list)
    for node in rows(processed/series/f"{series}_all.csv"):
        node_data[int(node["test_number"])].append(node)
    metrics = {int(r["test_number"]):r for r in rows(processed/series/f"{series}_metrics.csv")}
    names = [f for f in archive.namelist() if f.startswith(f"data_raw/{series}/") and f.endswith("/serial.csv")]
    runs, conditions = [], defaultdict(list)
    for name in sorted(names):
        config_text = archive.read(name.replace("serial.csv", "testsummary.csv")).decode()
        config = next(csv.DictReader(io.StringIO(config_text)))
        test = int(config["test_number"])
        if test not in booked:
            raise ValueError(f"No accepted registration for {series}/{test}")
        data = archive.read(name)
        times, sequence = serial_times(data)
        published = node_data[test]
        accepted = [n for n in published if n["T_round"].strip().lower() not in ("","nan")]
        retained_values = [int(float(n["T_round"])) for n in accepted]
        supported = sum(v in times[int(n["node_id"])] for n,v in zip(accepted,retained_values))
        first = sum(bool(sequence[int(n["node_id"])]) and sequence[int(n["node_id"])][0]==v
                    for n,v in zip(accepted,retained_values))
        reported = metrics[test]["T_round"].strip().lower()
        maximum = max(retained_values, default=None)
        if (reported not in ("","nan") and float(reported)!=maximum) or supported!=len(accepted):
            raise ValueError(f"Serial/processed round time mismatch in {test}")
        payload, slots = int(config["L_payload_size"]), int(config["B_n_slots"])
        row = dict(series=series, test_id=test, payload_bytes=payload, slots=slots,
                   serial_member=name, serial_sha256=hashlib.sha256(data).hexdigest(),
                   processed_node_rows=len(published), accepted_node_rounds=len(accepted),
                   omitted_node_rounds=len(published)-len(accepted), matched_serial_T=supported,
                   matched_first_serial_T=first,
                   published_max_round_us="" if reported in ("","nan") else int(float(reported)))
        runs.append(row)
        conditions[(payload, slots)].append(row)
    tested = {r["test_id"] for r in runs}
    if tested != set(metrics) or tested != set(node_data):
        raise ValueError("Different run coverage in raw and published files")
    groups = []
    for (payload, slots), subset in sorted(conditions.items()):
        usable = sorted(r["published_max_round_us"] for r in subset if r["published_max_round_us"]!="")
        groups.append(dict(series=series, payload_bytes=payload, slots=slots,
                           run_archives=len(subset), with_published_max=len(usable),
                           accepted_node_rounds=sum(r["accepted_node_rounds"] for r in subset),
                           omitted_node_rounds=sum(r["omitted_node_rounds"] for r in subset),
                           median_run_max_ms=statistics.median(usable)/1000,
                           empirical_nearest_rank_p95_run_max_ms=usable[math.ceil(.95*len(usable))-1]/1000,
                           max_run_max_ms=max(usable)/1000))
    rejected = admissions.count("Please correct the following errors:")
    totals = dict(series=series, intended_registrations=540, accepted_registrations=len(booked),
                  reported_registration_errors=rejected, raw_serial_logs=len(runs),
                  accepted_ids_without_archives="|".join(map(str,sorted(booked-tested))),
                  runs_with_published_max=sum(r["published_max_round_us"]!="" for r in runs),
                  processed_node_rows=sum(r["processed_node_rows"] for r in runs),
                  accepted_node_rounds=sum(r["accepted_node_rounds"] for r in runs))
    return runs, groups, totals


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for arg in ("archive","processed","out"):
        parser.add_argument(arg,type=Path)
    args=parser.parse_args()
    with args.archive.open("rb") as source:
        if hashlib.file_digest(source,"md5").hexdigest()!="cd71d109d322ee309a2272ce80424cd6":
            raise ValueError("Archive differs from Zenodo release v2.1")
    runs, groups, totals = [], [], []
    with ZipFile(args.archive) as archive:
        for s in ("serie1","serie2","serie3"):
            records, settings, summary = audit_series(archive,args.processed,s)
            runs.extend(records)
            groups.extend(settings)
            totals.append(summary)
    args.out.mkdir(exist_ok=True,parents=True)
    for name, data in [("runs",runs),("conditions",groups),("coverage",totals)]:
        write(args.out/f"ttnet-{name}.csv",data)


if __name__=="__main__":
    main()
