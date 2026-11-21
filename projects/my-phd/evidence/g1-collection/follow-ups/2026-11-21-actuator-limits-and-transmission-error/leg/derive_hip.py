"""Reproduce summaries for paired actuated-hip logs at the acquisition's first Git revision.
Usage: python derive_hip.py PATH_TO_REPOSITORY OUT
The source card identifies the revision and SHA-256 of the included files.
"""
import argparse
import csv
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd


def write(path, rows):
    with path.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=rows[0],lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def num(x):
    return "" if not np.isfinite(x) else f"{x:.8f}"


def runs(mask):
    bounds=np.diff(np.r_[False,mask,False].astype(int))
    lengths=np.flatnonzero(bounds==-1)-np.flatnonzero(bounds==1)
    return len(lengths), int(max(lengths,default=0))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("source",type=Path)
    p.add_argument("out",type=Path)
    args=p.parse_args()
    root=args.source/"RealData/2026_9_2"
    files=sorted([*root.glob("*/tcn_lb/tcn_*.csv"),*root.glob("*/samsung/samsung_*.csv")])
    if len(files)!=12:
        raise ValueError("Expected four TCN and eight Samsung telemetry files")
    summary=[]
    hips=[]
    for f in files:
        df=pd.read_csv(f,encoding="utf-8-sig")
        tcn="teensy_seq" in df
        source=str(f.relative_to(args.source))
        times=df["timestamp" if tcn else "elapsed_s"].to_numpy()
        if not np.isfinite(times).all() or np.any(np.diff(times)<0):
            raise ValueError("Invalid timestamp in "+source)
        if tcn:
            seq=df["teensy_seq"].to_numpy(int)
            if np.any((seq<0)|(seq>65535)):
                raise ValueError("Unexpected unsigned sequence field")
            deltas=np.diff(seq)%65536
        ident=dict(source=source,mode="TCN" if tcn else "Samsung")
        endpoint=8 if tcn else 5
        summary.append(dict(**ident,sha256=hashlib.sha256(f.read_bytes()).hexdigest(),
                            rows=len(df),first_s=num(times[0]),last_s=num(times[-1]),
                            median_dt_s=num(np.median(np.diff(times))),same_time_adjacent=int((np.diff(times)==0).sum()),
                            repeated_sequence_steps=int((deltas==0).sum()) if tcn else "",
                            modulo_sequence_gaps_gt1=int((deltas>1).sum()) if tcn else "",
                            decreases_in_published_seq=int((np.diff(seq)<0).sum()) if tcn else ""))
        for side in ("left","right"):
            cmd=df[side+("_cmd_nm" if tcn else "_command_torque_nm")].to_numpy()
            act=df[side+("_actual_nm" if tcn else "_actual_torque_nm")].to_numpy()
            if not np.isfinite(cmd).all():
                raise ValueError("Unexpected missing command in "+source)
            mask=np.abs(cmd)==endpoint
            positions=np.isfinite(act)
            residual=act[positions]-cmd[positions]
            raw=df[side+"_raw_tcn_nm"].to_numpy() if tcn else None
            streak,longest=runs(mask)
            hips.append(dict(**ident,side=side,rows=len(df),endpoint_reference_nm=endpoint,
                             finite_raw_model_outputs=int(np.isfinite(raw).sum()) if tcn else "",
                             finite_telemetry=int(positions.sum()),cmd_abs_max_nm=num(np.abs(cmd).max()),
                             feedback_abs_max_nm=num(np.abs(act[positions]).max()),cmd_abs_at_endpoint=int(mask.sum()),
                             cmd_abs_above_endpoint=int((np.abs(cmd)>endpoint).sum()),endpoint_runs=streak,longest_endpoint_run_rows=longest,
                             raw_abs_over_endpoint=int((abs(raw)>endpoint).sum()) if tcn else "",
                             raw_abs_over_and_cmd_at_endpoint=int(((abs(raw)>endpoint)&mask).sum()) if tcn else "",
                             raw_abs_within_and_cmd_at_endpoint=int(((abs(raw)<=endpoint)&mask).sum()) if tcn else "",
                             missing_raw_and_cmd_at_endpoint=int((~np.isfinite(raw)&mask).sum()) if tcn else "",
                             feedback_abs_over_reference=int((np.abs(act)>endpoint).sum()),
                             same_row_feedback_minus_cmd_rmse_nm=num(np.sqrt(np.mean(residual**2)))))
    args.out.mkdir(exist_ok=True,parents=True)
    write(args.out/"hip-control-files.csv",summary)
    write(args.out/"hip-command-endpoints.csv",hips)


if __name__=="__main__":
    main()
