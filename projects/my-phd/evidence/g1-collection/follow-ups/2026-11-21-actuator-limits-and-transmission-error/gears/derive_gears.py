"""Audit both complete Bauer et al. transmission-error deposits; fit a simple held-out angular lookup.

python derive_gears.py RAW_DIRECTORY OUTPUT_DIRECTORY
RAW_DIRECTORY must contain 4454.json, 5760.json, and the original file-ID-named downloads.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
import numpy as np


def save(path, rows):
    with path.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=rows[0],lineterminator='\n')
        w.writeheader()
        w.writerows(rows)


def fmt(x):
    return float(f'{x:.10g}')


def data_rows(raw, number):
    meta=json.loads((raw/f'{number}.json').read_text())['data']
    version=meta.get('latestVersion',meta)
    for row in sorted(version['files'],key=lambda item:item['dataFile']['id']):
        f=row['dataFile']
        orig=f.get('originalFileName',f['filename'])
        path=raw/(str(f['id'])+Path(orig).suffix)
        data=path.read_bytes()
        if hashlib.md5(data).hexdigest()!=f['md5']:
            raise ValueError(f"Wrong input bytes for {f['id']}")
        if orig.endswith('.csv'):
            arr=np.loadtxt(path,delimiter=',',skiprows=1)
            if not np.isfinite(arr).all():
                raise ValueError(f'Nonfinite array in {orig}')
            yield row.get('directoryLabel',''),orig,f['id'],hashlib.sha256(data).hexdigest(),arr


def cycloid(raw,out):
    runs,validation=[],[]
    curves={}
    for split,filename,fid,digest,a in data_rows(raw,'4454'):
        torque,speed,temp=map(float,re.fullmatch(r'tau_load=([-.\d]+)_theta_dot=([-.\d]+)_T=([-.\d]+)\.csv',filename).groups())
        theta,error=a.T
        # Equal angular weight, 720 bins covering one revolution in a fixed common frame.
        bins=np.floor(np.mod(theta,2*np.pi)*720/(2*np.pi)).astype(int).clip(0,719)
        count=np.bincount(bins,minlength=720)
        if min(count)==0:raise ValueError(f'Incomplete angular coverage in {filename}')
        curve=np.bincount(bins,weights=error,minlength=720)/count
        curves[fid]=curve
        runs.append(dict(file_id=fid,split=split,filename=filename,sha256=digest,rows=len(a),
                         load_nm=torque,speed_rad_s=speed,lubricant_c=temp,
                         covered_bins=len(count),min_rows_per_bin=min(count),
                         mean_te_mrad=fmt(1000*np.mean(curve)),
                         centered_rms_te_mrad=fmt(1000*np.std(curve)),
                         mean_abs_te_mrad=fmt(1000*np.mean(abs(curve)))))
    for row in (r for r in runs if r['split']=='validation'):
        candidates=[r for r in runs if r['split']=='identification' and r['speed_rad_s']*row['speed_rad_s']>0]
        cols=['load_nm','speed_rad_s','lubricant_c']
        coords=np.array([[r[c] for c in cols] for r in candidates])
        distance=np.linalg.norm((coords-np.array([row[c] for c in cols]))/np.ptp(coords,axis=0),axis=1)
        k=int(np.argmin(distance))
        y=curves[row['file_id']]
        trial=curves[candidates[k]['file_id']]
        pool=np.mean([curves[r['file_id']] for r in candidates],axis=0)
        def rmse(delta):return fmt(1000*np.sqrt(np.mean(delta**2)))
        validation.append(dict(validation_file_id=row['file_id'],neighbor_identification_file_id=candidates[k]['file_id'],
                               same_direction_candidate_files=len(candidates), normalized_distance=fmt(distance[k]),
                               bins=720, pooled_curve_rmse_mrad=rmse(y-pool), nearest_curve_rmse_mrad=rmse(y-trial),
                               centered_pooled_rmse_mrad=rmse((y-pool)-np.mean(y-pool)),
                               centered_nearest_rmse_mrad=rmse((y-trial)-np.mean(y-trial))))
    save(out/'cycloidal-runs.csv',runs)
    save(out/'cycloidal-heldout.csv',validation)


def staubli(raw,out):
    runs,pairs=[],[]
    conditions={}
    for folder,filename,fid,digest,a in data_rows(raw,'5760'):
        split,axis=folder.split('/')
        speed=float(filename.split('=')[1].removesuffix('.csv'))
        theta,q,err=a.T
        crop={'axis_1':(-140,164),'axis_2':(-90,80),'axis_3':(-65,115)}[axis]
        # Axis 1 has no validation comparison. Its plot uses motor angle, so only crop 2/3 here.
        keep=(np.rad2deg(q)>=crop[0]) & (np.rad2deg(q)<=crop[1]) if axis!='axis_1' else np.ones(len(q),bool)
        row=dict(file_id=fid,group=split,axis=axis,speed_set_rad_s=speed,sha256=digest,rows=len(q),
                 unique_setpoints=len(np.unique(q)),whole_mae_mrad=fmt(1000*np.mean(abs(err))),
                 interval_rows=int(keep.sum()),interval_mae_mrad=fmt(1000*np.mean(abs(err[keep]))))
        runs.append(row)
        conditions[axis,speed,split]=(row,q.copy(),keep)
    for (axis,speed,split),(rv,qv,kv) in sorted(conditions.items()):
        if split!='validation':continue
        ri,qi,ki=conditions[axis,speed,'identification']
        same=qi.shape==qv.shape and np.array_equal(qi,qv)
        pairs.append(dict(axis=axis,speed_set_rad_s=speed,baseline_file_id=ri['file_id'],
                          compensated_file_id=rv['file_id'],exact_same_setpoint_series=int(same),
                          baseline_crop_rows=int(ki.sum()),compensated_crop_rows=int(kv.sum()),
                          baseline_crop_mae_mrad=ri['interval_mae_mrad'],
                          compensated_crop_mae_mrad=rv['interval_mae_mrad'],
                          crop_mae_change_pct=fmt(100*(rv['interval_mae_mrad']/ri['interval_mae_mrad']-1))))
    save(out/'staubli-runs.csv',runs)
    save(out/'staubli-compensation.csv',pairs)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('raw',type=Path)
    p.add_argument('output',type=Path)
    p.add_argument('--only',choices=('4454','5760'))
    a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=True)
    if a.only!='4454':staubli(a.raw,a.output)
    if a.only!='5760':cycloid(a.raw,a.output)


if __name__=='__main__':
    main()
