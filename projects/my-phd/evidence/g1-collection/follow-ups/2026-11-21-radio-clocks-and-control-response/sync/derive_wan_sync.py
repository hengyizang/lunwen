"""Characterize the live ROA-Granada runs in Zenodo 16794348.
Usage: python derive_wan_sync.py WAN_ZIP OUTPUT_DIRECTORY (NumPy required).
"""
import argparse
import csv
import hashlib
import io
from collections import defaultdict
from pathlib import Path
from zipfile import ZipFile

import numpy as np


def load_streams(data):
    streams = defaultdict(lambda: ([], []))
    for row in csv.DictReader(io.TextIOWrapper(io.BytesIO(data),encoding="utf-8-sig",newline="")):
        times, values = streams[row["variable"]]
        times.append(int(row["timestamp"]))
        values.append(int(row["value"]))
    return {key: (np.asarray(times,dtype=np.int64),np.asarray(values,dtype=np.int64))
            for key,(times,values) in streams.items()}


def record(rows_path, rows):
    with rows_path.open("w",newline="",encoding="utf-8") as file:
        out=csv.DictWriter(file,fieldnames=rows[0].keys(),lineterminator="\n")
        out.writeheader()
        out.writerows(rows)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("archive",type=Path)
    p.add_argument("output",type=Path)
    args=p.parse_args()
    if hashlib.md5(args.archive.read_bytes()).hexdigest()!="0f6c4653a2b0bfd35c0dfa6f508f47b9":
        raise ValueError("Unexpected release checksum")
    rows, clocks, network = [], [], []
    with ZipFile(args.archive) as z:
        paths=sorted(n for n in z.namelist() if n.startswith("dataset/roa/") and n.endswith(".csv"))
        if len(paths)!=14:raise ValueError("Incomplete live network set")
        for path in paths:
            data=z.read(path)
            streams=load_streams(data)
            for key,(times,values) in sorted(streams.items()):
                absolute=np.abs(values)
                rows.append(dict(file=path,sha256=hashlib.sha256(data).hexdigest(),
                                 variable=key,observations=len(times),distinct_stamp_values=len(np.unique(times)),
                                 min_timestamp_ns=int(times.min()),max_timestamp_ns=int(times.max()),
                                 adjacent_backsteps=int((np.diff(times)<0).sum()),
                                 signed_median_ns=float(np.median(values)),abs_median_ns=float(np.median(absolute)),
                                 abs_p95_ns=round(float(np.quantile(absolute,0.95)),6),abs_max_ns=int(absolute.max())))
            if "offset_true" in streams:
                t,ref=streams["offset_true"]
                raw=streams.get("offset_raw")
                measured=streams.get("offset_filt")
                clocks.append(dict(file=path,tool=path.split("/")[2],external_reference_rows=len(t),
                                   external_signed_median_ns=float(np.median(ref)),
                                   external_abs_median_ns=float(np.median(np.abs(ref))),
                                   external_abs_p95_ns=round(float(np.quantile(np.abs(ref),0.95)),6),
                                   software_raw_rows=len(raw[0]) if raw is not None else "",
                                   software_raw_abs_median_ns=float(np.median(np.abs(raw[1]))) if raw is not None else "",
                                   software_filtered_rows=len(measured[0]) if measured is not None else "",
                                   shared_exact_time_values_true_raw=len(np.intersect1d(t,raw[0])) if raw is not None else ""))
            if set(streams)=={"delay_s2c","delay_c2s"}:
                t1,a=streams["delay_s2c"]
                t2,b=streams["delay_c2s"]
                ma,mb=float(np.median(a)),float(np.median(b))
                network.append(dict(file=path,downlink_n=len(t1),uplink_n=len(t2),
                                    downlink_median_ns=ma,uplink_median_ns=mb,
                                    half_difference_of_directional_medians_ns=(ma-mb)/2,
                                    shared_exact_time_values=len(np.intersect1d(t1,t2))))
    if len(clocks)!=8 or len(network)!=6:raise ValueError("Unexpected live-network conditions")
    args.output.mkdir(parents=True,exist_ok=True)
    record(args.output/'wan-live-streams.csv',rows)
    record(args.output/'wan-clock-offsets.csv',clocks)
    record(args.output/'wan-directional-delays.csv',network)

if __name__=='__main__':
    main()
