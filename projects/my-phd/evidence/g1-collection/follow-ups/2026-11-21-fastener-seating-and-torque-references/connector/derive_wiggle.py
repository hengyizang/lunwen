"""Audit deposited connector repeat files and paired human-session acquisition exports.
Usage: python derive_wiggle.py FIGSHARE_dataset.zip OUTPUT. Requires NumPy.
"""
import argparse
import csv
import hashlib
import io
from itertools import groupby
from pathlib import Path, PurePosixPath
import re
from zipfile import ZipFile
import numpy as np


def write(path, rows):
    with path.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=rows[0],lineterminator='\n')
        w.writeheader()
        w.writerows(rows)


def mechanical_runs(z):
    series=[]
    segments=[]
    for name in sorted(n for n in z.namelist() if re.search(r'/S_FIG8[bcd]_\d+\.txt$',n)):
        panel,trial=re.search(r'S_FIG8([bcd])_(\d+)\.txt$',name).groups()
        data=z.read(name)
        a=np.loadtxt(io.BytesIO(data))
        if a.shape[1]!=11 or not np.isfinite(a).all():
            raise ValueError(name)
        # Non-headered S8 files only. Names are based on plotted groups in Fig. S8.
        t=a[:,0]
        displacements=a[:,4:6]
        angle=a[:,6]
        scale=np.max(np.abs(angle))
        pre=int(np.flatnonzero(np.abs(angle)>=0.1*scale)[0])
        before=np.median(displacements[max(0,pre-100):pre],axis=0)
        last=np.median(displacements[-100:],axis=0)
        phase=np.select([angle>0.8*scale,angle< -0.8*scale],[1,-1],default=0)
        extremes=[]
        for side,indices in groupby(enumerate(phase),key=lambda pair:pair[1]):
            if not side:continue
            ids=np.array([i for i,_ in indices])
            vals=side*angle[ids]
            extreme_ids=ids[vals==vals.max()]
            extremes.append((int(extreme_ids[len(extreme_ids)//2]),side))
        for (i,left),(j,right) in zip(extremes,extremes[1:]):
            if left==right:
                raise ValueError(f'Double extremum in {name}')
            delta=displacements[j]-displacements[i]
            segments.append(dict(file=PurePosixPath(name).name,panel=panel,trial=int(trial),
                                 start_row_zero_based=i,end_row_zero_based=j,from_angle_sign=left,to_angle_sign=right,
                                 duration_s=round(t[j]-t[i],7),disp_col5_change_mm=round(delta[0],7),
                                 disp_col6_change_mm=round(delta[1],7),mean_change_mm=round(delta.mean(),7),
                                 minimum_of_model_leg_force_columns_8_9_N=round(np.min(a[i:j+1,7:9]),7)))
        series.append(dict(member=name,panel=panel,connector={'b':'LCB30 2-pin','c':'Power plug 3-pin','d':'D-sub 25-pin'}[panel],
                           trial=int(trial),sha256=hashlib.sha256(data).hexdigest(),rows=len(a),
                           first_s=t[0],last_s=t[-1],max_error_against_1ms_step_s=f'{np.max(np.abs(np.diff(t)-0.001)):.6g}',
                           timing_anchor_s=t[pre],turn_pairs=len(extremes)-1,
                           col5_change_from_anchor_to_end_mm=round(last[0]-before[0],7),
                           col6_change_from_anchor_to_end_mm=round(last[1]-before[1],7),
                           max_abs_col5_minus_col6_mm=round(np.max(np.abs(displacements[:,0]-displacements[:,1])),7),
                           max_abs_positive_negative_friction_bounds_sum=round(np.max(abs(a[:,9]+a[:,10])),8)))
    return series,segments


def human_sessions(z):
    names=set(z.namelist())
    result=[]
    for ft in sorted(n for n in names if '/ft_data/emg_exp/' in n and n.endswith('.csv')):
        emg=ft.replace('/ft_data/','/emg_data/').removesuffix('.csv')+'_emg.csv'
        if emg not in names:raise ValueError(ft)
        b=z.read(ft)
        m=z.read(emg)
        lines=b.decode('utf-8-sig').splitlines()
        start=next(i for i,line in enumerate(lines) if line.startswith('Name\tFT_F_LPF'))
        # Alternating scope-channel sample counters and numeric measurements. The trailing line is EOF.
        data=np.loadtxt(io.StringIO('\n'.join(s for s in lines[start+1:] if s.strip() and s.strip()!='EOF')),delimiter='\t')
        if data.shape[1]!=12 or not np.all(np.isfinite(data)):raise ValueError(ft)
        idx=data[:,::2]
        tags=m.decode('utf-8-sig').splitlines()
        offset=next(i for i,line in enumerate(tags) if line.startswith('Time[s],'))
        parsed=list(csv.reader(tags[offset+1:]))
        # Some recordings append quoted summary rows in the first column, not sampled times.
        footer={'Maximum, uV','Minimum, uV','Mean, uV'}
        numeric=[r for r in parsed if r and r[0] not in footer]
        emgdata=np.asarray(numeric,dtype=float)
        if not np.all(np.isfinite(emgdata)):raise ValueError(emg)
        fb=next(int(s.split('\t')[1]) for s in lines if s.startswith('Starttime of export'))
        fe=next(int(s.split('\t')[1]) for s in lines if s.startswith('Endtime of export'))
        dur=(fe-fb)*1e-7  # Windows FILETIME ticks in the export header
        result.append(dict(ft_member=ft,ft_sha256=hashlib.sha256(b).hexdigest(),
                           emg_member=emg,emg_sha256=hashlib.sha256(m).hexdigest(),
                           ft_rows=len(data),ft_channels=data.shape[1]//2,identical_channel_indices=int((idx==idx[:,[0]]).all()),
                           ft_span_header_s=round(dur,7),ft_first_index=idx[0,0],ft_last_index=idx[-1,0],
                           emg_rows=len(emgdata),excluded_emg_summary_rows=sum(bool(r) and r[0] in footer for r in parsed),emg_channels=emgdata.shape[1]-1,emg_first_s=emgdata[0,0],
                           emg_last_s=emgdata[-1,0],equal_row_counts=int(len(data)==len(emgdata)),
                           emg_minus_ft_span_s=round(emgdata[-1,0]-emgdata[0,0]-dur,7)))
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('zipfile',type=Path)
    p.add_argument('output',type=Path)
    a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=True)
    with ZipFile(a.zipfile) as z:
        rr,ss=mechanical_runs(z)
        human=human_sessions(z)
    for fname,table in [('wiggle-runs',rr),('wiggle-half-cycles',ss),('wiggle-session-timing',human)]:
        write(a.output/(fname+'.csv'),table)


if __name__=='__main__':
    main()
