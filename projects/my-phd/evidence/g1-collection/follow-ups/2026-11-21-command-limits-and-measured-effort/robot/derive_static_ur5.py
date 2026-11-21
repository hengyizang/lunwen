"""Compare row splits and inferred pose-block splits in the Nottingham static UR5 data.

Usage: python derive_static_ur5.py directory_containing_original_csv output_dir
"""
import csv
from pathlib import Path
import sys

import numpy as np
from scipy.spatial import cKDTree


def write(path, rows):
    with path.open("w", newline="") as stream:
        writer=csv.DictWriter(stream,fieldnames=rows[0],lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main(raw, output):
    output.mkdir(parents=True,exist_ok=True)
    q, v, u = [np.loadtxt(raw/(name+"_reduced.csv"),delimiter=",")
               for name in ("Positions","Velocities","Efforts")]
    assert q.shape == u.shape == v.shape and q.shape[1]==6
    assert np.isfinite(q).all() and np.isfinite(u).all() and (v==0).all()
    keep=~((q==0).all(axis=1) & (u==0).all(axis=1))
    original_rows=np.nonzero(keep)[0]+1
    q,u=q[keep],u[keep]
    distances=np.linalg.norm(np.diff(q,axis=0),axis=1)
    blocks,results=[],[]
    splits=[("interleaved_row", "", np.arange(len(q))%5)]
    for threshold in (0.005,0.01,0.02):
        ids=np.r_[0,np.cumsum(distances>threshold)]
        splits.append(("inferred_pose_block",threshold,ids%5))
        for block in np.unique(ids):
            idx=ids==block
            blocks.append(dict(threshold=threshold,block_id=block,
                original_first_row=int(original_rows[idx][0]),original_last_row=int(original_rows[idx][-1]),
                rows=int(idx.sum()),unique_angles=len(np.unique(q[idx],axis=0)),
                max_6d_current_span=float(np.linalg.norm(np.ptp(u[idx],axis=0)))))
    write(output/"ur5-static-blocks.csv",blocks)
    for scheme, threshold, folds in splits:
        all_errors=[]; all_baseline=[]; all_dist=[]
        for fold in range(5):
            test=folds==fold; train=~test
            # Exact repeats in the training set receive equal weight after averaging per pose.
            pose,index,counts=np.unique(q[train],axis=0,return_inverse=True,return_counts=True)
            avg=np.zeros((len(pose),6))
            np.add.at(avg,index,u[train])
            avg/=counts[:,None]
            dist,near=cKDTree(pose).query(q[test],k=1)
            all_errors.append(avg[near]-u[test])
            all_baseline.append(np.median(u[train],axis=0)-u[test])
            all_dist.append(dist)
        error=np.vstack(all_errors); baseline=np.vstack(all_baseline); dist=np.concatenate(all_dist)
        for j in range(6):
            results.append(dict(scheme=scheme,threshold=threshold,
                joint_column=j+1,test_rows=len(dist),test_rows_with_exact_training_pose=int((dist==0).sum()),
                median_nearest_training_angle_distance=np.median(dist),
                mae=np.abs(error[:,j]).mean(),rmse=np.sqrt(np.mean(error[:,j]**2)),
                median_baseline_rmse=np.sqrt(np.mean(baseline[:,j]**2))))
    write(output/"ur5-static-holdouts.csv",results)


if __name__=="__main__":
    main(Path(sys.argv[1]),Path(sys.argv[2]))
