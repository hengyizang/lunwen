"""Read the original Zenodo records 4556924, 3627901 and 6399688.
Download each record's files as ID-original_filename under INPUT before running.
Python 3, NumPy and SciPy. Writes only aggregate statistics.
"""
import argparse
import csv
import hashlib
import io
import re
from pathlib import Path
from zipfile import ZipFile
import numpy as np
from scipy.io import loadmat


def csv_out(out,name,rows):
    with (out/name).open('w',newline='') as f:
        writer=csv.DictWriter(f,rows[0],lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def longest_run(values):
    edges=np.diff(np.r_[False,values,False].astype(int))
    return int(np.max(np.flatnonzero(edges==-1)-np.flatnonzero(edges==1),initial=0))


def belgrade(src,out):
    rows=[]
    for f in sorted(src.glob('4556924-T*.txt')):
        signal=f.name.split('-',1)[1]
        trajectory,rate=re.fullmatch(r'(T\d+)_(\d+)\.txt',signal).groups()
        rate=int(rate)
        v=np.loadtxt(f)
        if v.ndim!=1 or not np.isfinite(v).all():raise ValueError(signal)
        below=v<0
        above=v>10
        rows.append(dict(file=signal,sha256=hashlib.sha256(f.read_bytes()).hexdigest(),trajectory=trajectory,
            rate_Hz=rate,samples=len(v),min_V=v.min(),max_V=v.max(),below_zero=below.sum(),equal_zero=(v==0).sum(),
            strictly_above_10=above.sum(),exactly_10=(v==10).sum(),longest_below_zero_samples=longest_run(below),
            longest_above_10_samples=longest_run(above),adjacent_equal_samples=np.count_nonzero(np.diff(v)==0),
            distinct_stored_values=len(np.unique(v))))
    if len(rows)!=12:raise ValueError('Expected twelve voltage files')
    csv_out(out,'belgrade-regulator-voltage.csv',rows)


def soft(src,out):
    rows=[]
    for path in sorted(src.glob('3627901-*.zip')):
        with ZipFile(path) as z:
            if z.testzip() is not None:raise ValueError(path)
            matfile=next(x for x in z.namelist() if x.endswith('.mat'))
            arrays=loadmat(io.BytesIO(z.read(matfile)))
            protocol=next(k for k in ('tip','three point','pulling') if k in path.name.lower())
            for n in sorted(z.namelist()):
                parsed=re.fullmatch(r'[DP](\d+)_(\d+)\.csv',n)
                if not parsed:continue
                dat=z.read(n)
                a=np.loadtxt(io.BytesIO(dat),delimiter=',')
                if a.shape[1]!=8 or not np.isfinite(a).all():raise ValueError(n)
                match=[k for k,v in arrays.items() if not k.startswith('_') and v.shape==a.shape and np.array_equal(a,v)]
                baseline=(a[:,0]==0)&(np.max(np.abs(a[:,1:7]),axis=1)>1e6)
                if np.any(np.flatnonzero(baseline)>0):raise ValueError('Noninitial flagged row '+n)
                b=a[~baseline]
                # Each module contributes two perpendicular load-cell channels. Norm is invariant to their sign.
                module_norms=np.linalg.norm(b[:,1:7].reshape(-1,3,2),axis=2)*0.00981
                peaks=np.max(module_norms,axis=0)
                rows.append(dict(protocol=protocol,source_file=n,csv_sha256=hashlib.sha256(dat).hexdigest(),
                    mat_identical_array=' | '.join(match),filename_pressure_level=parsed[1],replicate=parsed[2],
                    source_rows=len(a),flagged_initial_rows=int(baseline.sum()),measurement_rows=len(b),
                    nonincreasing_time_steps=int(np.sum(np.diff(b[:,0])<=0)),
                    median_pressure_channel_native=round(float(np.median(b[:,-1])),6),
                    peak_module1_vector_norm_N=round(peaks[0],6),peak_module2_vector_norm_N=round(peaks[1],6),
                    peak_module3_vector_norm_N=round(peaks[2],6)))
    if len(rows)!=93:raise ValueError('Unexpected trial-file inventory')
    csv_out(out,'soft-loadcell-files.csv',rows)


def planar(src,out):
    inventory=[]; trials=[]
    with ZipFile(src/'6399688-Positioning_system_data.zip') as z:
        if z.testzip() is not None:raise ValueError('ZIP CRC')
        by_axis={}
        for name in sorted(z.namelist()):
            payload=z.read(name);a=np.loadtxt(io.BytesIO(payload))
            if a.ndim!=1 or not np.isfinite(a).all():raise ValueError(name)
            inventory.append(dict(file=name,sha256=hashlib.sha256(payload).hexdigest(),samples=len(a),
                min_native=a.min(),max_native=a.max(),first_native=a[0],last_native=a[-1],distinct_values=len(np.unique(a))))
            by_axis[name]=a
        for i in range(1,31):
            for axis in 'xy':
                a=by_axis[f'{axis}-0k_v{i}.txt']; ref=by_axis[f'{axis}_normal_v0.txt']
                n=min(len(a),len(ref))
                diff=a[:n]-ref[:n]
                # Relative sample-index mismatch only; no resampling, optimized lag, or inferred time delay.
                trials.append(dict(trial=i,axis=axis,encoder_rows=len(a),reference_rows=len(ref),
                    paired_prefix_rows=n,unpaired_reference_tail_rows=len(ref)-n,
                    prefix_bias_native=round(float(diff.mean()),6),prefix_rmse_native=round(float(np.sqrt(np.mean(diff**2))),6),
                    prefix_peak_abs_native=np.abs(diff).max(),encoder_first_at_90000=int(np.flatnonzero(a>=90000)[0]),
                    reference_first_at_90000=int(np.flatnonzero(ref>=90000)[0])))
    csv_out(out,'planar-file-inventory.csv',inventory)
    csv_out(out,'planar-reference-overlap.csv',trials)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('input',type=Path);p.add_argument('output',type=Path)
    args=p.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    belgrade(args.input,args.output);soft(args.input,args.output);planar(args.input,args.output)
