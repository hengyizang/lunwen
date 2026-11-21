"""Summarize Hannover parallel-robot contact datasets from their three original ZIPs.

python derive_parallel.py INPUT_DIR OUTPUT_DIR
Requires numpy and pandas.
"""
import argparse
import csv
import hashlib
import io
from pathlib import Path
from zipfile import ZipFile
import numpy as np
import pandas as pd


def write(path, rows):
    with path.open('w',newline='',encoding='utf-8') as stream:
        writer=csv.DictWriter(stream,fieldnames=rows[0],lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def norm2(frame, prefix):
    return np.linalg.norm(frame[[prefix+'1',prefix+'2']].to_numpy(),axis=1)


def stable_rises(signal, threshold, dwell):
    high=signal>=threshold
    changes=np.flatnonzero(high[1:] & ~high[:-1])+1
    return np.array([i for i in changes if i>=dwell and i+dwell<=len(high)
                     and not np.any(high[i-dwell:i]) and np.all(high[i:i+dwell])],dtype=int)


def segment_events(block, label, segment, dwell):
    ref=norm2(block,'F_ext_fts_proj_mobPlat_CS0_N_Nm_')
    est=norm2(block,'F_ext_est_mobPlat_CS0_N_Nm_')
    results=[]
    for threshold in (2,5,10):
        a=stable_rises(ref,threshold,dwell)
        b=stable_rises(est,threshold,dwell)
        # One F/T event and one observer event must select each other uniquely within 100 ms.
        close=np.abs(a[:,None]-b[None,:])<=100
        unique=close & (close.sum(0)[None,:]==1) & (close.sum(1)[:,None]==1)
        ii,jj=np.nonzero(unique)
        gaps=b[jj]-a[ii]
        results.append(dict(segment=segment,body=label[0],chain=label[1],link=label[2],location=label[3],
                            threshold_N=threshold,dwell_samples_each_side=dwell,fts_events=len(a),observer_events=len(b),unique_pairs=len(gaps),
                            ref_without_candidate=int((close.sum(1)==0).sum()),ref_ambiguous=int((close.sum(1)>1).sum()),
                            ref_single_shared_candidate=int((close.sum(1)==1).sum())-len(gaps),
                            earlier=int((gaps<0).sum()),simultaneous=int((gaps==0).sum()),later=int((gaps>0).sum()),
                            min_est_minus_fts_ms=int(min(gaps)) if len(gaps) else '',
                            median_est_minus_fts_ms=float(np.median(gaps)) if len(gaps) else '',
                            max_est_minus_fts_ms=int(max(gaps)) if len(gaps) else ''))
    return results


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('source',type=Path)
    p.add_argument('output',type=Path)
    a=p.parse_args()
    files,axes,events=[],[],[]
    for task in ('classification_body','classification_type','regression_location_force'):
        with ZipFile(a.source/(task+'.zip')) as z:
            for member in sorted(n for n in z.namelist() if n.endswith('.csv')):
                raw=z.read(member)
                df=pd.read_csv(io.BytesIO(raw))
                ts=df.t_s.to_numpy()
                dt=np.diff(ts)
                projected='F_ext_fts_proj_mobPlat_CS0_N_Nm_1' in df
                groups=df.groupby('collided_body') if 'collided_body' in df else df.groupby('clamping_collision')
                files.append(dict(member=member,sha256=hashlib.sha256(raw).hexdigest(),rows=len(df),columns=df.shape[1],
                                  raw_six_axis_measured=int('F_ext_fts_N_Nm_6' in df),projected_reference=int(projected),
                                  nonfinite=int((~np.isfinite(df.to_numpy())).sum()),backward_time_steps=int((dt<0).sum()),
                                  equal_time_steps=int((dt==0).sum()),non_1ms_steps=int((~np.isclose(dt,.001,rtol=0,atol=1e-8)).sum()),
                                  dt_median_ms=round(1000*np.median(dt),5)))
                if projected:
                    for label,block in groups:
                        for i,unit in [(1,'N'),(2,'N'),(3,'Nm')]:
                            err=(block[f'F_ext_est_mobPlat_CS0_N_Nm_{i}']-block[f'F_ext_fts_proj_mobPlat_CS0_N_Nm_{i}']).to_numpy()
                            axes.append(dict(member=member,collided_body=int(label),component=i,unit=unit,rows=len(block),
                                             mean_error=round(err.mean(),8),rmse=round(np.sqrt(np.mean(err**2)),8),
                                             p95_abs_error=round(np.percentile(np.abs(err),95),8)))
                if task=='regression_location_force':
                    for seq,idx in enumerate(np.split(np.arange(len(ts)),np.flatnonzero(~np.isclose(dt,.001,rtol=0,atol=1e-8))+1),1):
                        block=df.iloc[idx]
                        labels=block[['collided_body','chain','link','location']].drop_duplicates()
                        if len(labels)!=1:raise ValueError('Inconsistent labels in continuous time run.')
                        for dwell in (1,5,10):
                            events.extend(segment_events(block,labels.iloc[0].to_list(),seq,dwell))
    a.output.mkdir(parents=True,exist_ok=True)
    for name,data in [('sources',files),('wrench-reference',axes),('force-crossings',events)]:
        write(a.output/f'parallel-{name}.csv',data)


if __name__=='__main__':
    main()
