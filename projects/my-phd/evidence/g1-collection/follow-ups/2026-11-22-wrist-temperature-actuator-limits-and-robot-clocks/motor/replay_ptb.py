"""Usage: python replay_ptb.py PTB_download.zip out_dir. Requires numpy and pandas."""
import argparse, csv, hashlib, io
from pathlib import Path
from zipfile import ZipFile
import numpy as np
import pandas as pd

def save(output,name,rows):
    with (output/name).open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=rows[0],lineterminator='\n');w.writeheader();w.writerows(rows)

def read(z,name):
    with z.open('720.20190411/'+name) as f:
        return pd.read_csv(f,sep='\t',skiprows=2,encoding='latin1').dropna(axis='columns',how='all')

def edges(frame):
    times=frame['Time'].to_numpy()
    v=frame['Time sync'].to_numpy()>0
    return {sense:times[np.flatnonzero(mask)+1] for sense,mask in
            [('rising',~v[:-1]&v[1:]),('falling',v[:-1]&~v[1:])]}

def paired(ref,local):
    # Same-polarity edges, symmetric 50 ms interval, unique on both loggers.
    a=np.searchsorted(local,ref-0.05);b=np.searchsorted(local,ref+0.05,side='right')
    sel=np.flatnonzero(b-a==1); matches=local[a[sel]]
    keep=np.searchsorted(ref,matches+0.05,side='right')-np.searchsorted(ref,matches-0.05)==1
    return (matches[keep]-ref[sel[keep]])*1000

def analyze(archive,output):
    output.mkdir(exist_ok=True,parents=True);windows=[];clocks=[];raw=[];hyst=[]
    with ZipFile(archive) as z:
        assert z.testzip() is None
        for rep in range(1,5):
            signals={}
            for who in ['ntb','tts']:
                name=f'aligned_measurement_data/rep{rep}_data_{who}.asc'
                f=read(z,name);t=f['Time'].to_numpy()
                assert np.isfinite(f.to_numpy()).all() and (np.diff(t)>0).all()
                raw.append(dict(repeat=rep,instrument=who,rows=len(f),columns=len(f.columns),span_s=round(t[-1]-t[0],8),nominal_hz=1200 if who=='ntb' else 150,median_sample_ms=round(float(np.median(np.diff(t))*1000),6),torque_min_kNm=f.Mx.min(),torque_max_kNm=f.Mx.max(),crc32=f"{z.getinfo('720.20190411/'+name).CRC:08x}"))
                signals[who]=f
            nt,tt=signals['ntb'],signals['tts'];nt_edges,tt_edges=edges(nt),edges(tt)
            for sense in nt_edges:
                d=paired(tt_edges[sense],nt_edges[sense])
                clocks.append(dict(repeat=rep,edge=sense,ntb_edges=len(nt_edges[sense]),reference_edges=len(tt_edges[sense]),uniquely_paired=len(d),median_local_minus_reference_ms=round(float(np.median(d)),6),p95_abs_ms=round(float(np.quantile(abs(d),.95)),6),max_abs_ms=round(float(max(abs(d))),6)))
            summary=read(z,f'results/rep{rep}_averaged_torque_values.asc')
            start=read(z,f'results/rep{rep}_averaging_sequences.asc')
            assert list(summary.iloc[:,0])==list(start.iloc[:,0])
            tare=summary.loc[summary.iloc[:,0].str.contains('taring')].iloc[0]
            time=nt['Time'].to_numpy();rpm=nt['n'].to_numpy()
            revolutions=np.r_[0,np.cumsum((rpm[1:]+rpm[:-1])*np.diff(time)/120)]
            pairs={}
            for i,r in summary.iterrows():
                label=r.iloc[0];t0=float(start.iloc[i,1]);rref=float(r.iloc[1]-tare.iloc[1]);rlocal=float(r.iloc[3]-tare.iloc[3])
                row=dict(repeat=rep,index=i+1,source_step=label,start_table_s=t0 if np.isfinite(t0) else '',source_tared_ref_kNm=round(rref,7),source_tared_local_kNm=round(rlocal,7),local_minus_ref_kNm=round(rlocal-rref,7))
                for wait in [0,20]:
                    if not np.isfinite(t0):continue
                    begin=t0+wait;a=np.searchsorted(time,begin)
                    if a>=len(time):continue
                    reached=np.flatnonzero(revolutions[a:]-revolutions[a]>=6)
                    if len(reached)==0:continue
                    end=a+reached[0]
                    stop=time[end]
                    row[f'window{wait}_span_s']=round(float(stop-begin),5)
                    for who,src in [('ntb',r.iloc[3]),('tts',r.iloc[1])]:
                        f=signals[who];times=f['Time'].to_numpy()
                        l=np.searchsorted(times,begin);u=np.searchsorted(times,stop)
                        row[f'window{wait}_{who}_mean_minus_source_kNm']=round(float(f['Mx'].iloc[l:u].mean()-src),7)
                for wait in [0,20]:
                    for col in ['span_s','ntb_mean_minus_source_kNm','tts_mean_minus_source_kNm']:row.setdefault(f'window{wait}_{col}','')
                windows.append(row)
                if label.endswith(('inc','dec')):pairs[(label.split()[0],label.split()[-1])]=rlocal-rref
            for (level,sense),value in pairs.items():
                if sense=='inc' and (level,'dec') in pairs:
                    hyst.append(dict(repeat=rep,nominal_kNm=level,delta_inc_kNm=round(value,7),delta_dec_kNm=round(pairs[level,'dec'],7),dec_minus_inc_error_kNm=round(pairs[level,'dec']-value,7)))
    for filename,items in [('ptb-aligned-files.csv',raw),('ptb-clock-edges.csv',clocks),('ptb-calibration-steps.csv',windows),('ptb-reversal.csv',hyst)]:save(output,filename,items)
if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('zip',type=Path);ap.add_argument('output',type=Path);a=ap.parse_args();analyze(a.zip,a.output)
