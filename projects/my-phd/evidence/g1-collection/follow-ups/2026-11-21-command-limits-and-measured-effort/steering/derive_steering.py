"""Audit fixed platform ZIP inventories, boundary members and entire available ZIPs.

python derive_steering.py <fetch-root> <output-directory>
Requires pandas and numpy. For the six full archives fetch the six smallest files
from the fixed tree into ROOT/steer/ before running fetch_steering.py.
"""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import pandas as pd

INPUTS = ['steer', 'steerFiltered']
TARGETS = ['latAccelSteeringAngle', 'latAccelLocalizer']
COLUMNS = INPUTS + TARGETS + ['t', 'roll', 'vEgo', 'latActive', 'steeringPressed', 'latAccelDesired']


def write_rows(path, rows):
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0], lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def segment(platform, name, data, fits):
    frame = pd.read_csv(io.BytesIO(data), usecols=COLUMNS)
    for flag in ['latActive', 'steeringPressed']:
        assert frame[flag].dtype == bool
    active = frame.latActive & ~frame.steeringPressed
    eligible = active & np.isfinite(frame[COLUMNS]).all(axis=1)
    v = frame.loc[eligible]
    change = (v.steer - v.steerFiltered).abs()
    time_step = np.diff(frame.t)
    def rms(x):
        return round(float(np.sqrt(np.mean(x*x))), 8) if len(x) else ''
    rec = dict(platform=platform, member=name, sha256=hashlib.sha256(data).hexdigest(),
               rows=len(frame), active_without_driver=int(active.sum()), common_finite=len(v),
               time_steps_outside_0p1s_by_1ms=int(np.sum(abs(time_step-.1)>.001)),
               command_difference_gt_0p05=int((change>.05).sum()), command_difference_gt_0p1=int((change>.1).sum()),
               input_abs_ge_0p995=int((v.steer.abs()>=.995).sum()),
               filtered_abs_ge_0p995=int((v.steerFiltered.abs()>=.995).sum()),
               input_abs_gt_1p000001=int((v.steer.abs()>1.000001).sum()), filtered_abs_gt_1p000001=int((v.steerFiltered.abs()>1.000001).sum()),
               command_difference_rms=rms(change), endpoint_difference_rms_m_s2=rms(v[TARGETS[0]]-v[TARGETS[1]]),
               desired_minus_angle_rms_m_s2=rms(v.latAccelDesired-v[TARGETS[0]]),
               desired_minus_localizer_rms_m_s2=rms(v.latAccelDesired-v[TARGETS[1]]))
    if fits is not None and len(v):
        split = 'test' if int(Path(name).stem)%5 == 0 else 'train'
        y = v[TARGETS].to_numpy()
        for key in INPUTS:
            u = v[key].to_numpy()
            x = np.column_stack((np.ones(len(u)), u, u*abs(u), u*v.vEgo/20, v.roll))
            state = fits.setdefault((split,key), [0, np.zeros((5,5)), np.zeros((5,2)), np.zeros(2)])
            state[0] += len(u)
            state[1] += x.T@x
            state[2] += x.T@y
            state[3] += (y*y).sum(axis=0)
    return rec


def main(root, out):
    out.mkdir(exist_ok=True, parents=True)
    segments, platforms, models, synthetic = [], [], [], []
    for receipt in sorted((root/'steer-index').glob('*/index.json')):
        index = json.loads(receipt.read_text())
        name = index['platform']
        whole = root/'steer'/(name+'.zip')
        count_before = len(segments)
        fits = {}
        if index['complete_sha_checked']:
            with whole.open('rb') as f:assert hashlib.file_digest(f,'sha256').hexdigest()==index['lfs_sha256']
            with ZipFile(whole) as archive:
                for member in sorted(m for m in archive.namelist() if m.endswith('.csv')):
                    segments.append(segment(name,member,archive.read(member),fits))
            for key in INPUTS:
                train, test = fits['train',key], fits['test',key]
                beta = np.linalg.lstsq(train[1], train[2],rcond=None)[0]
                err = test[3] - 2*(beta*test[2]).sum(axis=0) + (beta*(test[1]@beta)).sum(axis=0)
                for j, target in enumerate(TARGETS):
                    row = dict(platform=name, input=key, target=target, train_rows=train[0], test_rows=test[0],
                               test_rmse_m_s2=round(np.sqrt(max(0,err[j])/test[0]),8),
                               normal_matrix_rank=np.linalg.matrix_rank(train[1]))
                    row.update({k:round(float(b),8) for k,b in zip(['intercept','linear','signed_square','speed_interaction','roll'],beta[:,j])})
                    models.append(row)
        else:
            for entry in index['selected']:
                b = (receipt.parent/Path(entry['name']).name).read_bytes()
                assert hashlib.sha256(b).hexdigest()==entry['sha256']
                if name == 'SYNTHETIC_V0':
                    frame = pd.read_csv(io.BytesIO(b))
                    assert set(frame.columns) == {'t','vEgo','aEgo','roll','targetLateralAcceleration','steerCommand'}
                    synthetic.append(dict(platform=name,member=entry['name'],sha256=entry['sha256'],
                                          rows=len(frame),fields='|'.join(frame.columns)))
                else:
                    segments.append(segment(name,entry['name'],b,None))
        platforms.append({**{k:v for k,v in index.items() if k!='selected'}, 'road_schema_decoded_members':len(segments)-count_before, 'synthetic_schema_decoded_members':len(synthetic) if name=='SYNTHETIC_V0' else 0})
    write_rows(out/'road-platforms.csv',platforms)
    write_rows(out/'road-segments.csv',segments)
    write_rows(out/'road-holdout.csv',models)
    write_rows(out/'road-synthetic-boundaries.csv',synthetic)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('root',type=Path);p.add_argument('out',type=Path)
    args=p.parse_args()
    main(args.root,args.out)
