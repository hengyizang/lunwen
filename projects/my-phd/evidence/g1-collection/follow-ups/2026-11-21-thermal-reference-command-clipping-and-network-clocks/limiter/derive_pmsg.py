"""Fetch the immutable 3-phase PMSG subdirectory and compute controller/shaft channel checks.
Usage: python derive_pmsg.py OUTPUT [--cache DIR] [--workers 6]
NumPy and SciPy required. Caching stores JSON summaries by Git blob in the cache only.
"""
import argparse
import csv
import hashlib
import io
import json
import math
import re
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.request import Request,urlopen

import numpy as np
from scipy.io import loadmat

REPO='InnovaPower/MitDev-Eletrica'
REV='e02fba475cf82b375412a7382143dc29da5241ef'


def fetch(url):
    for attempt in range(4):
        try:
            with urlopen(Request(url,headers={'User-Agent':'G1-public-file-research'}),timeout=40) as r:
                return r.read()
        except OSError:
            if attempt==3:raise
            time.sleep(2**attempt)


def summarize(blob):
    path=blob['path']
    raw=fetch(f'https://raw.githubusercontent.com/{REPO}/{REV}/{path}')
    if len(raw)!=blob['size'] or hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()!=blob['sha']:
        raise ValueError('Git content mismatch: '+path)
    mat=loadmat(io.BytesIO(raw),simplify_cells=True)
    k='t Torq_mec Torq_ele Iq_ref Iq Id_ref Id Da Db Dc Va_ref Vb_ref Vc_ref Va Vb Vc Vdc Spd Fault_relay Package_loss'.split()
    n=len(mat['t'])
    if n==0 or any(np.asarray(mat[i]).shape!=(n,) or not np.isfinite(mat[i]).all() for i in k):
        raise ValueError('Nonfinite or unaligned vector: '+path)
    speed,torque = map(int,re.search(r'_S(\d+)_T(\d+)\.mat$',path).groups())
    tq=mat['Torq_mec']
    raw_duty=np.stack([0.5+mat['V'+phase+'_ref']/mat['Vdc'] for phase in 'abc'])
    logged=np.stack([mat['D'+phase] for phase in 'abc'])
    phase_err=np.stack([mat['V'+phase]-mat['V'+phase+'_ref'] for phase in 'abc'])
    rmse=lambda x:round(float(np.sqrt(np.mean(x*x))),7)
    return dict(file=Path(path).name,git_blob=blob['sha'],bytes=len(raw),
        nominal_speed_rpm=speed,nominal_mechanical_torque_magnitude_Nm=torque/10,
        samples=n,duration_s=round(float(mat['t'][-1]-mat['t'][0]),7),
        non_50us_intervals=int((abs(np.diff(mat['t'])-0.00005)>1e-10).sum()),
        measured_shaft_mean_Nm=round(float(tq.mean()),7),
        measured_shaft_distinct=len(np.unique(tq)),
        calculated_electromagnetic_mean_Nm=round(float(mat['Torq_ele'].mean()),7),
        calculated_over_minus_measured_means=round(float(mat['Torq_ele'].mean()/(-tq.mean())),7),
        reported_speed_rad_s_over_nominal_mech_rad_s=round(float(mat['Spd'].mean()/(speed*2*math.pi/60)),7),
        iq_reference_mean_A=round(float(mat['Iq_ref'].mean()),7),iq_tracking_rmse_A=rmse(mat['Iq']-mat['Iq_ref']),
        id_tracking_rmse_A=rmse(mat['Id']-mat['Id_ref']),
        min_duty=float(logged.min()),max_duty=float(logged.max()),
        phase_duty_equal_0_or_1=int(((logged==0)|(logged==1)).sum()),
        phase_duty_outside_0_1=int(((logged<0)|(logged>1)).sum()),
        phase_duty_vs_ref_plus_half_max_abs=float(np.max(np.abs(raw_duty-logged))),
        phase_voltage_tracking_rmse_V=rmse(phase_err),
        relay_high_samples=int((mat['Fault_relay']>0).sum()),
        package_loss_max_native=float(mat['Package_loss'].max()),
        package_loss_negative_steps=int((np.diff(mat['Package_loss'])<0).sum()))


def run(out,cache,workers,tree_file):
    tree=json.loads(tree_file.read_text() if tree_file else fetch(f'https://api.github.com/repos/{REPO}/git/trees/{REV}?recursive=1'))
    assert tree['sha']==REV and not tree['truncated']
    files=[x for x in tree['tree'] if x['path'].startswith('PMSG-3phase-Dataset/') and x['path'].endswith('.mat')]
    assert len(files)==225 and len({x['sha'] for x in files})==225
    def record(blob):
        target=cache/(blob['sha']+'.json') if cache else None
        if target and target.exists():
            return json.loads(target.read_text())
        ret=summarize(blob)
        if target:
            cache.mkdir(exist_ok=True,parents=True); target.write_text(json.dumps(ret))
        return ret
    with ThreadPoolExecutor(workers) as ex:
        rows=list(ex.map(record,files))
    out.mkdir(exist_ok=True,parents=True)
    with (out/'pmsg-operating-points.csv').open('w',newline='') as handle:
        w=csv.DictWriter(handle,rows[0],lineterminator='\n');w.writeheader();w.writerows(rows)
    print('Decoded:',len(rows),'files;',sum(r['samples'] for r in rows),'rows.')


if __name__=='__main__':
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('output',type=Path);cli.add_argument('--cache',type=Path);cli.add_argument('--workers',type=int,default=6);cli.add_argument('--tree-file',type=Path)
    args=cli.parse_args(); run(args.output,args.cache,args.workers,args.tree_file)

