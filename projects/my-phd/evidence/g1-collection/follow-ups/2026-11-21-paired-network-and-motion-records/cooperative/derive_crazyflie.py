"""Compare directed range channels and motion capture in seven civil indoor swarm flight CSVs.
Run against the fixed shushuai3/multi-robot-localization repository checkout.
"""
import argparse
import hashlib
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd


def rounded(x):
    return round(float(x), 7)


def pose(frame, i):
    start = 46+7*i
    xyz = frame[:,start:start+3]
    norm = np.linalg.norm(frame[:,start+3:start+7],axis=1)
    return xyz, np.isfinite(xyz).all(axis=1) & (norm>=0.95) & (norm<=1.05)


def analyze(path, nodes):
    a = np.loadtxt(path, delimiter=',')
    if a.shape[1] != 81 or not np.isfinite(a[:,0]).all():
        raise ValueError('Unexpected flight table')
    t = a[:,0].astype(np.int64)
    dt = np.diff(t)
    if not np.all(t==a[:,0]) or np.any(dt<=0):
        raise ValueError('Unexpected tick')
    poses = [pose(a,i) for i in range(nodes)]
    rows = []
    by = []
    for i,j in combinations(range(nodes),2):
        forward = a[:,5+9*i+j]
        reverse = a[:,5+9*j+i]
        xyz_i, ok_i = poses[i]
        xyz_j, ok_j = poses[j]
        reference = np.linalg.norm(xyz_i-xyz_j,axis=1)
        paired = (forward>0) & (reverse>0) & np.isfinite(forward) & np.isfinite(reverse)
        eligible = (dt>=9)&(dt<=11)&paired[1:]&paired[:-1]
        cf,cr = np.diff(forward)!=0,np.diff(reverse)!=0
        by.append(dict(file=path.name, a=i, b=j, both_positive_samples=int(paired.sum()),
                       unequal_reciprocal_samples=int(np.count_nonzero(paired & (forward!=reverse))),
                       adjacent_9_to_11_ms_both_positive=int(eligible.sum()),
                       only_forward_value_changed=int(np.count_nonzero(eligible & cf & ~cr)),
                       only_reverse_value_changed=int(np.count_nonzero(eligible & ~cf & cr)),
                       both_values_changed=int(np.count_nonzero(eligible & cf & cr)),
                       neither_value_changed=int(np.count_nonzero(eligible & ~cf & ~cr))))
        for start,end,value in ((i,j,forward),(j,i,reverse)):
            valid = ok_i & ok_j & np.isfinite(value) & (value>0)
            metres = value[valid]/1000
            ref = reference[valid]
            err = metres-ref
            err_code = (metres - (0.048*metres + 0.6508))-ref
            err_v1 = (metres - (0.072*metres + 0.62))-ref
            rows.append(dict(file=path.name, from_robot=start, to_robot=end,
                             positive_and_two_valid_poses=int(valid.sum()),
                             median_signed_raw_error_m=rounded(np.median(err)),
                             median_abs_raw_error_m=rounded(np.median(abs(err))),
                             median_abs_code_bias_only_error_m=rounded(np.median(abs(err_code))),
                             median_abs_v1_bias_only_error_m=rounded(np.median(abs(err_v1)))))
    summary = dict(file=path.name, release_label='noisy' if 'old' in path.stem else 'noise-free',
                   robots=nodes, rows=len(t), rows_with_nonfinite_field=int(np.count_nonzero(~np.isfinite(a).all(axis=1))), ticks_first_ms=t[0], ticks_last_ms=t[-1],
                   span_s=rounded((t[-1]-t[0])/1000), adjacent_tick_median_ms=np.median(dt),
                   adjacent_tick_max_ms=int(dt.max()), adjacent_outside_9_to_11_ms=int(np.count_nonzero((dt<9)|(dt>11))),
                   csv_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    # A shared coordinate tuple would indicate reused motion capture samples, even if ticks differ.
    xyz0,q0=poses[0]
    xyz1,q1=poses[1]
    tuples = set(map(tuple,np.c_[xyz0[q0&q1],xyz1[q0&q1]]))
    return summary,rows,by,tuples


def main(root,out):
    out.mkdir(parents=True,exist_ok=True)
    files,errors,changes,signatures=[],[],[],{}
    for path in sorted((root/'dataset').glob('dat*.csv')):
        name=path.name
        n=3 if name.startswith(('dat01','dat02')) else 4
        summary,rows,by,tuples=analyze(path,n)
        files.append(summary)
        errors.extend(rows)
        changes.extend(by)
        signatures[name]=tuples
    if len(files)!=7:
        raise ValueError('Expected 7 flight files')
    overlap=[dict(first=a,second=b,distinct_valid_first=len(signatures[a]),
                  distinct_valid_second=len(signatures[b]),exact_shared_pose_pairs=len(signatures[a]&signatures[b]))
             for a,b in combinations(signatures,2)]
    freq=[]
    for path in sorted((root/'dataset').glob('freq*.csv')):
        a=np.loadtxt(path,delimiter=',')
        for c,values in enumerate(a.T):
            freq.append(dict(file=path.name,column_ordinal=c+1,rows=len(a),columns=a.shape[1],
                             changed_adjacent_rows=int(np.count_nonzero(np.diff(values))),
                             unchanged_adjacent_rows=int(np.count_nonzero(np.diff(values)==0)),
                             file_sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    for name,rows in [('flights',files),('range-check',errors),('direction-pairs',changes),
                      ('cross-file-overlap',overlap),('frequency-files',freq)]:
        pd.DataFrame(rows).to_csv(out/('crazyflie-'+name+'.csv'),index=False)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('repository',type=Path)
    parser.add_argument('out',type=Path)
    args=parser.parse_args()
    main(args.repository,args.out)
