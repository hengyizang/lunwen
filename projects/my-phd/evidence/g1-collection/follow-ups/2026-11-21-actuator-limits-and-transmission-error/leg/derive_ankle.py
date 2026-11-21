"""Summarize bilateral exoskeleton torque per versioned OSF CSV and controller.
Run with Python 3, NumPy and pandas: python derive_ankle.py Data_NMC_Balance_Ankle.zip.zip OUT
"""
import argparse
import csv
import hashlib
import io
from collections import defaultdict
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import pandas as pd

EXPECTED = "e96405d601d1b29f4b6bf5560978bc7160bcb4d12e916e5824108edc144f6f2e"


def write(path, rows):
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=rows[0], lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def number(value):
    return "" if not np.isfinite(value) else f"{value:.8f}"


def summarize(archive, name, groups):
    body = archive.read(name)
    side_columns = {s: [s + "_DesiredTorque_Nm", s + "_JointTorque_Nm"] for s in ("LA", "RA")}
    cols = ["time", *side_columns["LA"], *side_columns["RA"]]
    df = pd.read_csv(io.BytesIO(body), usecols=cols)
    t = df["time"].to_numpy()
    if not np.isfinite(t).all() or not (np.diff(t) > 0).all():
        raise ValueError("Invalid time in " + name)
    subject, condition, file = name.split("/")
    steady = condition == "SteadyState"
    mode = Path(file).stem if steady else condition
    kind = "steady" if steady else Path(file).stem.split("_")[0]
    result = dict(member=name, sha256=hashlib.sha256(body).hexdigest(), subject=subject,
                  condition=mode, trial_type=kind, rows=len(t), first_s=number(t[0]),
                  last_s=number(t[-1]), max_abs_interval_minus_10ms_s=number(max(abs(np.diff(t)-.01))))
    for side, pair in side_columns.items():
        desired, actual = df[pair].to_numpy().T
        valid = np.isfinite(desired) & np.isfinite(actual)
        v, a = desired[valid], actual[valid]
        residual = a-v
        sumsq = float(np.dot(residual, residual))
        zero = v == 0
        params = dict(pairs=len(v), missing=len(t)-len(v), desired_peak_abs_nm=number(np.abs(v).max()) if len(v) else "",
                      applied_peak_abs_nm=number(np.abs(a).max()) if len(a) else "",
                      signed_error_mean_nm=number(residual.mean()) if len(v) else "",
                      rmse_nm=number(np.sqrt(sumsq/len(v))) if len(v) else "",
                      both_finite_desired_zero=int(zero.sum()),
                      abs_applied_gt_1nm_given_zero=int((zero & (abs(a)>1)).sum()),
                      abs_desired_ge_100nm=int((abs(v)>=100).sum()), abs_applied_ge_100nm=int((abs(a)>=100).sum()))
        result.update({side+"_"+key:value for key,value in params.items()})
        groups[(mode,kind,side)].append((subject,len(t),len(v),sumsq,params))
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("archive", type=Path)
    p.add_argument("out", type=Path)
    args=p.parse_args()
    with args.archive.open("rb") as input_file:
        if hashlib.file_digest(input_file,"sha256").hexdigest()!=EXPECTED:
            raise ValueError("Unexpected OSF archive")
    groups=defaultdict(list)
    with ZipFile(args.archive) as archive:
        names=sorted(n for n in archive.namelist() if n.startswith("subject_") and n.endswith(".csv"))
        rows=[summarize(archive,n,groups) for n in names]
    unique={r["sha256"] for r in rows}
    if len(unique)!=len(rows):
        raise ValueError("Duplicate CSVs in archive: resolve before pooling")
    pooled=[]
    for (condition,trial_type,side),items in sorted(groups.items()):
        n=sum(v[2] for v in items)
        pooled.append(dict(condition=condition,trial_type=trial_type,ankle=side,participant_codes=len({v[0] for v in items}),
                           files=len(items),published_grid_rows=sum(v[1] for v in items),finite_pairs=n,
                           pooled_rmse_nm=number(np.sqrt(sum(v[3] for v in items)/n)) if n else "",
                           desired_zero_pairs=sum(v[4]["both_finite_desired_zero"] for v in items),
                           abs_applied_gt_1nm_given_zero=sum(v[4]["abs_applied_gt_1nm_given_zero"] for v in items)))
    args.out.mkdir(exist_ok=True,parents=True)
    write(args.out/"ankle-torque-trials.csv",rows)
    write(args.out/"ankle-torque-conditions.csv",pooled)


if __name__=="__main__":
    main()
