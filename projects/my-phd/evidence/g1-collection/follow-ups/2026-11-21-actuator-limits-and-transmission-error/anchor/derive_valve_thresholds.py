"""Verify measured opening/closing intervals and printed event pairs in Zenodo 21263963."""
import argparse
from bisect import bisect_left, bisect_right
import csv
from datetime import datetime
import hashlib
import io
from pathlib import Path
import statistics
from zipfile import ZipFile


def table(archive,name):
    return list(csv.DictReader(io.StringIO(archive.read(name).decode('utf-8-sig'))))


def write(path,rows):
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=rows[0],lineterminator='\n')
        w.writeheader()
        w.writerows(rows)


def valve_results(z):
    path='zenodo-deposit/data/valve/chapter_5_3_hysteresis_raw_test1.csv'
    records=table(z,path)
    groups=[]
    for name,group in [('15',[r for r in records if r['P_water_kPa']=='15']),
                       ('55',[r for r in records if r['P_water_kPa']=='55']),
                       ('pooled',records)]:
        closing=[abs(float(r['P_threshold_kPa'])) for r in group if r['direction']=='close']
        opening=[abs(float(r['P_threshold_kPa'])) for r in group if r['direction']=='open']
        groups.append(dict(water_side_kPa=name,specimens=len({r['sample_id'] for r in group}),
                           closing_trials=len(closing),opening_trials=len(opening),
                           closing_abs_mean_kPa=statistics.mean(closing),opening_abs_mean_kPa=statistics.mean(opening),
                           mean_abs_threshold_separation_kPa=round(statistics.mean(closing)-statistics.mean(opening),6),
                           smallest_cross_pair_margin_kPa=round(min(closing)-max(opening),6),
                           reported_video_frame_identifiers=sum(bool(r['video_frame'].strip()) for r in group)))
    return groups


def trace_results(z):
    base='zenodo-deposit/data/integration/'
    summary={r['label']:r for r in table(z,base+'summary_n11.csv') if r['label'].startswith(('P','S'))}
    trials=[]
    for name in sorted(n for n in z.namelist() if n.startswith((base+'porcine/',base+'silicone/')) and n.endswith('.csv')):
        rows=table(z,name)
        pressure=[float(r['Pressure']) for r in rows]
        stamps=[datetime.strptime(r['PC Time Stamp'],'%Y/%m/%d-%H:%M:%S.%f') for r in rows]
        t=[(s-stamps[0]).total_seconds() for s in stamps]
        steps=[b-a for a,b in zip(t,t[1:])]
        assert min(steps)>=0
        trial=Path(name).stem
        r=dict(member=name,trial=trial,sha256=hashlib.sha256(z.read(name)).hexdigest(),pressure_rows=len(t),
               identical_PC_time_steps=sum(v==0 for v in steps),
               equal_time_changed_pressure=sum(stamps[i]==stamps[i+1] and pressure[i]!=pressure[i+1] for i in range(len(stamps)-1)),
               median_PC_step_s=round(statistics.median(steps),6),min_PC_step_s=round(min(steps),6),
               max_PC_step_s=round(max(steps),6),min_kPa=min(pressure),max_kPa=max(pressure),
               included_in_published_summary=int(trial in summary),published_trigger_to_cycle_min_s='',
               compatible_pressure_and_duration_pairs='',first_matching_trigger_row_1based='',
               first_matching_min_row_1based='')
        if trial in summary:
            s=summary[trial]
            p0,p1,dt=map(float,[s['P_trigger_kPa'],s['P_cycle_min_kPa'],s['t_cycle_s']])
            matches=[]
            for i,p in enumerate(pressure):
                if round(p,2)!=p0:
                    continue
                lo=bisect_left(t,t[i]+dt-.050000001,lo=i+1)
                hi=bisect_right(t,t[i]+dt+.050000001,lo=lo)
                for j in range(lo,hi):
                    if round(pressure[j],2)==p1 and min(pressure[i:j+1])>=p1-.005:
                        matches.append((i+1,j+1))
            r.update(published_trigger_to_cycle_min_s=dt,compatible_pressure_and_duration_pairs=len(matches),
                     first_matching_trigger_row_1based=matches[0][0] if matches else '',
                     first_matching_min_row_1based=matches[0][1] if matches else '')
        trials.append(r)
    return trials


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('archive',type=Path)
    p.add_argument('output',type=Path)
    args=p.parse_args()
    args.output.mkdir(exist_ok=True,parents=True)
    with ZipFile(args.archive) as z:
        write(args.output/'anchor-valve-separation.csv',valve_results(z))
        write(args.output/'anchor-pressure-records.csv',trace_results(z))
