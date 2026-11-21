"""Audit the iCub human recordings and the released motion-reference comparisons.

Input is the complete Zenodo 5596856 ZIP. Needs Python and NumPy. Numeric axes
are compared only within the same task/channel/trial and undisplaced row index.
"""
import argparse
from collections import defaultdict
import csv
import hashlib
from pathlib import Path, PurePosixPath
import re
import zipfile
import numpy as np


def save(path, rows):
    with path.open("w",newline="") as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]),lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("zip",type=Path)
    parser.add_argument("output",type=Path)
    args=parser.parse_args()
    reference=defaultdict(dict)
    training=defaultdict(dict)
    with zipfile.ZipFile(args.zip) as archive:
        for entry in archive.infolist():
            p=PurePosixPath(entry.filename)
            if p.suffix!=".csv":
                continue
            _,split,task,*rest=p.parts
            with archive.open(entry) as data:
                a=np.loadtxt(data,delimiter=",",ndmin=2)
            if not np.isfinite(a).all():
                raise ValueError(f"Nonfinite trajectory in {p}")
            if split in ("training","validation"):
                prefix,number=re.fullmatch(r"(pr|p|c|r|)([0-9]+)",p.stem).groups()
                training[(split,task,int(number))][prefix or "q"]=a.shape
            else:
                if a.shape[1]!=2:
                    raise ValueError(f"Expected two columns in {p}")
                regime,number= (rest[0],int(rest[1])) if split=="prediction" else ("compensated",int(rest[0]))
                k=(task,number,p.stem)
                digest=hashlib.sha256(a[:,1].astype("<f8").tobytes()).hexdigest()
                diff=a[:,0]-a[:,1]
                leading_zeros=int(np.argmax(a[:,0]!=0)) if np.any(a[:,0]!=0) else len(a)
                reference[k][regime]=dict(n=len(a),obs_digest=digest,
                                          rmse=float(np.sqrt(np.mean(np.square(diff)))),
                                          leading_zeros=leading_zeros)
    shapes=[]
    for (split,task,n),series in sorted(training.items()):
        row=dict(split=split,task=task,trial=n)
        for k in ("q","r","p","pr","c"):
            rows,cols=series.get(k,("",""))
            row[k+"_rows"]=rows
            row[k+"_cols"]=cols
        row["q_r_lengths_match"]=int(row["q_rows"]==row["r_rows"] and row["q_rows"]!="")
        row["p_pr_lengths_match"]=int(row["p_rows"]==row["pr_rows"] and row["p_rows"]!="")
        shapes.append(row)
    result=[]
    for (task,n,channel),comparisons in sorted(reference.items()):
        if set(comparisons)!={"compensated","no_obs","recognition","half","fourth"}:
            raise ValueError(f"Incomplete conditions: {task}, {n}, {channel}")
        predictions=[comparisons[k] for k in ("no_obs","recognition","half","fourth")]
        row=dict(task=task,trial=n,channel=channel,
                 prediction_obs_sequence_count=len({v["obs_digest"] for v in predictions}),
                 compensated_obs_same_as_no_obs=int(comparisons["compensated"]["obs_digest"]==comparisons["no_obs"]["obs_digest"]))
        for k in ("no_obs","recognition","fourth","half","compensated"):
            summary=comparisons[k]
            row[k+"_rows"]=summary["n"]
            row[k+"_rmse_native_units"]=round(summary["rmse"],10)
            row[k+"_leading_zero_reference_rows"]=summary["leading_zeros"]
        result.append(row)
    args.output.mkdir(exist_ok=True,parents=True)
    save(args.output/"icub-human-retargeted-shapes.csv",shapes)
    save(args.output/"icub-reference-comparisons.csv",result)


if __name__=="__main__":
    main()
