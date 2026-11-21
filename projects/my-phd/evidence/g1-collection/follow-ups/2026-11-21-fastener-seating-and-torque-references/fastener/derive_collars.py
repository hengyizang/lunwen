"""Audit physical wrench windows in KR16 collar installation logs. Python + NumPy.
python derive_collars.py DATASET_ZIP OUTPUT_DIR
"""
import argparse
import csv
import hashlib
import io
from pathlib import Path
from zipfile import ZipFile
import numpy as np


def save(path,rows):
    with path.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=rows[0],lineterminator='\n')
        w.writeheader()
        w.writerows(rows)


def first_three(mask,t):
    k=np.flatnonzero(mask[:-2]&mask[1:-1]&mask[2:])
    return round(float(t[k[0]]),6) if len(k) else ''


def characterize(a,meta,data):
    t=a[:,0]
    step=np.diff(t)
    assert np.isfinite(a).all() and np.all(step>0)
    size=len(t)
    half=size//2
    same=(size%2==0 and np.array_equal(a[:half,1:13],a[half:,1:13]))
    retained=half if same else size
    s=a[:retained]
    # Initial reference is descriptive; neither contact-free state nor eye-hand calibration is certified.
    fz,mz=s[:,9],s[:,12]
    nz=min(len(s),20)
    f0=float(np.median(fz[:nz]))
    m0=float(np.median(mz[:nz]))
    return dict(experiment=meta['experiment_id'],manual_outcome=meta['label'],idx=int(meta['idx']),
                sha256=hashlib.sha256(data).hexdigest(),metadata_individual_time=float(meta['individual_time']),
                source_rows=size,exact_doubled_pose_wrench=int(same),retained_rows=retained,
                retained_last_time_s=round(float(s[-1,0]),6),
                min_time_step_s=round(float(step.min()),7),max_time_step_s=round(float(step.max()),7),
                rows_with_unequal_velocity_between_copies=(int(np.sum(np.any(a[:half,13:]!=a[half:,13:],axis=1))) if same else ''),
                initial_fz_median_n=round(f0,7),initial_mz_median_nm=round(m0,7),
                max_abs_axial_torque_nm=round(float(np.max(abs(mz))),7),
                max_abs_axial_torque_minus_initial_nm=round(float(np.max(abs(mz-m0))),7),
                max_moment_norm_nm=round(float(np.linalg.norm(s[:,10:13],axis=1).max()),7),
                peak_negative_fz_n=round(float(fz.min()),7),
                first_3_consecutive_fz_drop_5n_s=first_three(fz<=f0-5,s[:,0]),
                first_3_consecutive_fz_drop_10n_s=first_three(fz<=f0-10,s[:,0]),
                first_3_consecutive_fz_drop_20n_s=first_three(fz<=f0-20,s[:,0]))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive',type=Path)
    parser.add_argument('out',type=Path)
    a=parser.parse_args()
    with ZipFile(a.archive) as z:
        meta=list(csv.DictReader(io.StringIO(z.read(next(n for n in z.namelist() if n.endswith('/meta.csv'))).decode())))
        names={Path(n).stem:n for n in z.namelist() if '/data/' in n and n.endswith('.csv')}
        assert len(names)==len(meta)==len({m['experiment_id'] for m in meta})
        trials=[]
        expected=b'time,x,y,z,rotx,roty,rotz,fx,fy,fz,mx,my,mz,vx,vy,vz,vrotx,vroty,vrotz'
        for m in sorted(meta,key=lambda item:int(item['idx'])):
            data=z.read(names[m['experiment_id']])
            assert data.splitlines()[0]==expected
            matrix=np.loadtxt(io.BytesIO(data),skiprows=1,delimiter=',')
            trials.append(characterize(matrix,m,data))
    groups=[]
    for label in sorted({trial['manual_outcome'] for trial in trials}):
        subset=[r for r in trials if r['manual_outcome']==label]
        row=dict(manual_outcome=label,trials=len(subset),source_rows=sum(r['source_rows'] for r in subset),
                 retained_rows=sum(r['retained_rows'] for r in subset),
                 exactly_doubled=sum(r['exact_doubled_pose_wrench'] for r in subset))
        for field in ['max_abs_axial_torque_nm','max_abs_axial_torque_minus_initial_nm','peak_negative_fz_n',
                      'first_3_consecutive_fz_drop_5n_s','first_3_consecutive_fz_drop_20n_s']:
            values=[s[field] for s in subset if s[field]!='']
            row.update({f'{field}_{k}':round(float(np.percentile(values,q)),7) if values else ''
                        for k,q in [('min',0),('median',50),('max',100)]})
        groups.append(row)
    a.out.mkdir(exist_ok=True,parents=True)
    save(a.out/'collar-wrist-trials.csv',trials)
    save(a.out/'collar-manual-outcomes.csv',groups)


if __name__=='__main__':
    main()
