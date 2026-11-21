"""Compute cycle summaries and chronological held-out fits for the two micromanipulator runs.

python derive_piezo.py SUPPLEMENT.zip OUTPUT_DIR
Requires Python and NumPy. No figure digitization or model-generated observations.
"""
import argparse
import csv
import hashlib
import io
from pathlib import Path
from zipfile import ZipFile
import numpy as np


def write(path, rows):
    with path.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0], lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def crossings(t, y, u, center, rising):
    left, right = u[:-1] - center, u[1:] - center
    mask = ((left <= 0) & (right > 0)) if rising else ((left > 0) & (right <= 0))
    idx = np.flatnonzero(mask)
    frac = -left[idx] / (right[idx] - left[idx])
    return idx, t[idx] + frac * (t[idx+1] - t[idx]), y[idx] + frac * (y[idx+1] - y[idx])


def summarize(name, data):
    t, y, u = np.loadtxt(io.BytesIO(data), delimiter=',', usecols=(1, 2, 3), unpack=True)
    if not (np.isfinite([t,y,u]).all() and np.all(np.diff(t)>0)):
        raise ValueError('Non-finite or unordered samples: '+name)
    keep = (t > 5) if '150' in name else np.ones(len(t),dtype=bool)
    report = dict(member=name, sha256=hashlib.sha256(data).hexdigest(), rows=len(t),
                  start_s=t[0], end_s=t[-1], median_sample_interval_us=round(np.median(np.diff(t))*1e6,5),
                  first_nonzero_input_time_s=t[np.flatnonzero(u!=0)[0]], retained_rows=int(keep.sum()))
    t,y,u = t[keep], y[keep], u[keep]
    mid = (u.min()+u.max())/2
    scale=(u.max()-u.min())/2
    start, rt, ry = crossings(t,y,u,mid,True)
    fall, ft, fy = crossings(t,y,u,mid,False)
    cycles=[]
    for k,(i,j) in enumerate(zip(start,start[1:])):
        down = np.where((ft>rt[k]) & (ft<rt[k+1]))[0]
        if len(down)!=1:raise ValueError('Cycle lacks a unique falling crossing')
        q=down[0]
        # Interpolate both boundaries to the identical input voltage before integration.
        v = np.r_[mid, u[i+1:j+1], mid]
        d = np.r_[ry[k], y[i+1:j+1], ry[k+1]]
        area = np.sum((d[1:]+d[:-1])/2*np.diff(v))
        cycles.append(dict(member=name, cycle=k+1, rising_time_s=round(rt[k],9),
                           period_s=round(rt[k+1]-rt[k],9), rising_y_um=round(ry[k],7),
                           falling_y_um=round(fy[q],7), rising_minus_falling_um=round(ry[k]-fy[q],7),
                           signed_integral_y_du_um_v=round(area,7)))
    cutoff=start[len(cycles)//2]
    idx=np.arange(len(u))
    train=(idx>start[0]) & (idx<=cutoff)
    test=(idx>cutoff) & (idx<=start[-1])
    x=(u-mid)/scale
    features=np.column_stack([np.ones(len(x)),x,x**2,x**3])
    # Tag voltage direction by the most recent non-flat step, within the same run.
    delta=np.sign(np.diff(u,prepend=u[0]))
    prev=np.maximum.accumulate(np.where(delta!=0,idx,0))
    direction=delta[prev]
    fits=[]
    for model,A in [('cubic_voltage',features),('cubic_voltage_separate_directions',np.column_stack([features, direction[:,None]*features]))]:
        coef,_,rank,_=np.linalg.lstsq(A[train],y[train],rcond=None)
        resid=y[test]-A[test]@coef
        fits.append(dict(member=name, model=model, training_cycles=len(cycles)//2,
                         heldout_cycles=len(cycles)-len(cycles)//2, training_rows=int(train.sum()),
                         test_rows=int(test.sum()),matrix_rank=int(rank),
                         chronological_test_rmse_um=round(np.sqrt(np.mean(resid**2)),7)))
    report.update(raw_retained_min_input_v=u.min(),raw_retained_max_input_v=u.max(),
                  midpoint_v=mid, complete_cycles=len(cycles),
                  median_rising_minus_falling_um=round(np.median([c['rising_minus_falling_um'] for c in cycles]),7))
    return report,cycles,fits


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('supplement',type=Path)
    p.add_argument('output',type=Path)
    args=p.parse_args()
    runs,cycles,fits=[],[],[]
    with ZipFile(args.supplement) as z:
        for name in ['data/h50us.csv','data/hysteresis_v_150_1hz.csv']:
            r,c,f=summarize(name,z.read(name))
            runs.append(r)
            cycles.extend(c)
            fits.extend(f)
    args.output.mkdir(exist_ok=True,parents=True)
    for name,table in [('runs',runs),('cycles',cycles),('fits',fits)]:
        write(args.output/f'piezo-{name}.csv',table)


if __name__=='__main__':
    main()
