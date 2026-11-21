"""Predict near-start measured joint torque of completely held-out nominal masses.

Usage: python derive_panda_load_holdout.py pandasparse.zip output_directory.
Only one pre-specified motion basename per physical configuration is eligible.
"""
from pathlib import Path
import io
import json
import sys
from zipfile import ZipFile

import numpy as np

from fetch_panda_members import selections
from derive_panda import write


def main(archive,output):
    output.mkdir(parents=True,exist_ok=True)
    runs=[]
    with ZipFile(archive) as z:
        paired,chosen=selections(z)
        for raw,reduced in sorted(paired.items()):
            config,tool=raw.split("/")[1].split()
            cfg="Exp_cfg/exp"+config+".json"
            if cfg not in chosen:
                continue
            nominal=json.loads(z.read(cfg))["total_mass"]
            m=np.loadtxt(io.BytesIO(z.read(reduced)),ndmin=2)
            early=m[m[:,0]<=0.1]
            runs.append((config,tool,nominal,len(early),np.median(early[:,1:8],axis=0),
                         np.abs(early[:,8:15]).max(),np.median(early[:,15:22],axis=0)))
    y=np.stack([row[-1] for row in runs])
    mass=np.array([row[2] for row in runs])
    # Nominal settings can differ in their last floating point bit; round only for splitting.
    groups=mass.round(6)
    tool=np.array([row[1] for row in runs])
    X=np.column_stack([np.ones(len(runs)),(tool=="end2").astype(float),mass])
    outputs=[]
    for i,run in enumerate(runs):
        train=groups!=groups[i]
        coef,_,rank,_=np.linalg.lstsq(X[train],y[train],rcond=None)
        assert rank==3
        prediction=X[i]@coef
        baseline=np.median(y[train & (tool==tool[i])],axis=0)
        pose=run[4]
        training_poses=np.stack([other[4] for other,ok in zip(runs,train) if ok])
        nearest=np.linalg.norm(training_poses-pose,axis=1).min()
        for j in range(7):
            outputs.append(dict(condition_id=run[0],tool_directory=run[1],reported_total_mass=run[2],
                start_window_rows=run[3],start_window_max_abs_dq_rad_per_s=run[5],
                nearest_train_start_pose_l2_rad=nearest,train_runs=int(train.sum()),
                mass_outside_train_range=int(mass[i]<mass[train].min() or mass[i]>mass[train].max()),
                joint=j+1,observed_median_Nm=y[i,j],predicted_Nm=prediction[j],
                tool_median_baseline_Nm=baseline[j],model_error_Nm=prediction[j]-y[i,j],
                baseline_error_Nm=baseline[j]-y[i,j]))
    write(output/"panda-load-holdouts.csv",outputs)


if __name__=="__main__":
    main(Path(sys.argv[1]),Path(sys.argv[2]))
