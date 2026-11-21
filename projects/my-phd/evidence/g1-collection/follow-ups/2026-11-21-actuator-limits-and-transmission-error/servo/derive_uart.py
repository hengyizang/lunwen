"""Summarize servo telemetry and reproduce the directional loaded and released position gaps.

python derive_uart.py ZENODO_RELEASE.zip OUTPUT_DIR
"""
import argparse
import csv
from collections import defaultdict
from datetime import datetime
import hashlib
import io
from itertools import groupby
import json
from pathlib import Path
import re
import statistics
from zipfile import ZipFile


def write(path, rows):
    with path.open('w', newline='', encoding='utf-8') as stream:
        writer=csv.DictWriter(stream, fieldnames=rows[0], lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def spans(flags):
    for active, entries in groupby(enumerate(flags), key=lambda x:x[1]):
        if active:
            selected=[i for i,_ in entries]
            yield selected[0],selected[-1]+1


def extract_windows(rows,cfg):
    def matches(row, motor, target, tolerance):
        pos=row[f'pos ({motor})']
        return row[f'target pos ({motor})']==str(target) and pos!='' and abs(int(pos)-target)<=tolerance

    home=[all(r[f'target pos ({m})']==str(cfg['home_position']) for m in cfg['home_motor_ids'])
          for r in rows]
    assert not cfg['require_home_position_match']
    pullers=cfg['actuated_motors']
    windows=[]
    for left,right in spans(home):
        if right-left<cfg['min_segment_samples']:
            continue
        sub=rows[left:right]
        relaxed=list(spans(all(matches(r,m['motor_id'],m['relaxed_target'],m['relaxed_tolerance'])
                               for m in pullers) for r in sub))
        for m in pullers:
            load=spans(matches(r,m['motor_id'],m['stretched_target'],m['stretched_tolerance']) for r in sub)
            for i,j in load:
                windows.append((m['motor_id'],'loaded',left+i,left+j))
                release=next(((a,b) for a,b in relaxed if a>=j),None)
                if release:
                    windows.append((m['motor_id'],'released',left+release[0],left+release[1]))
    return windows


def analyze(z,name,cfg):
    data=z.read(name)
    rows=list(csv.DictReader(io.StringIO(data.decode('utf-8-sig'))))
    fname=Path(name).name
    times=[datetime.fromisoformat(r['timestamp'].replace('Z','+00:00')) for r in rows]
    dt=[round((b-a).total_seconds()*1000,4) for a,b in zip(times,times[1:])]
    assert min(dt)>0
    coverage=[]
    for m in sorted(int(re.fullmatch(r'pos \((\d+)\)',c)[1]) for c in rows[0] if c.startswith('pos (')):
        both=[r for r in rows if r[f'pos ({m})']!='' and r[f'target pos ({m})']!='']
        fields=[f'{k} ({m})' for k in ('pos','speed','load','current','temp','status','moving')]
        vectors=[tuple(r[key] for key in fields) for r in rows]
        coverage.append(dict(file=fname,sha256=hashlib.sha256(data).hexdigest(),motor=m,rows=len(rows),
                             role='DUT' if m in cfg['report_motor_ids'] else
                             'puller' if m in [e['motor_id'] for e in cfg['actuated_motors']] else 'additional logger channel',
                             target_and_position_rows=len(both), complete_telemetry_vectors=sum(all(v) for v in vectors),
                             adjacent_identical_complete_vectors=sum(bool(all(a)) and a==b for a,b in zip(vectors,vectors[1:])),
                             median_host_interval_ms=statistics.median(dt), min_host_interval_ms=min(dt),max_host_interval_ms=max(dt)))
    intervals=extract_windows(rows,cfg)
    areas=defaultdict(list)
    window_rows=[]
    for pull,phase,i,j in intervals:
        for dut in cfg['report_motor_ids']:
            vals=[int(row[f'pos ({dut})']) for row in rows[i:j] if row[f'pos ({dut})']!='']
            if not vals:continue
            window_rows.append(dict(file=fname,puller=pull,phase=phase,dut=dut,
                                    row_start_zero_based=i,row_end_exclusive=j,valid_positions=len(vals),
                                    mean_position_counts=round(statistics.mean(vals),8)))
            areas[pull,phase,dut].extend(vals)
    gaps=[]
    a,b=(m['motor_id'] for m in cfg['actuated_motors'])
    for dut in cfg['report_motor_ids']:
        for phase in ('loaded','released'):
            x,y=areas[a,phase,dut],areas[b,phase,dut]
            # Repeated release windows are retained here to match the upstream phase definition.
            gap=abs(statistics.mean(x)-statistics.mean(y)) if x and y else None
            gaps.append(dict(file=fname,dut=dut,state=phase,first_puller=a,second_puller=b,
                             first_puller_position_rows=len(x),second_puller_position_rows=len(y),
                             abs_directional_mean_gap_counts='' if gap is None else round(gap,8)))
    return coverage,window_rows,gaps


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('archive',type=Path)
    p.add_argument('out',type=Path)
    a=p.parse_args()
    cov,windows,gaps=[],[],[]
    with ZipFile(a.archive) as z:
        for name in sorted(n for n in z.namelist() if '/logs/' in n and n.endswith('.csv')):
            stem=Path(name).stem
            cfgname='m4' if stem.endswith('single_3250') else 'm5' if stem.endswith('single') else 'm1_m2'
            cfg=json.loads(z.read(next(n for n in z.namelist() if n.endswith(f'/config_{cfgname}.json'))))
            c,w,g=analyze(z,name,cfg)
            cov.extend(c)
            windows.extend(w)
            gaps.extend(g)
    a.out.mkdir(parents=True,exist_ok=True)
    for label,rows in [('telemetry',cov),('windows',windows),('directional-gaps',gaps)]:
        write(a.out/f'uart-{label}.csv',rows)


if __name__=='__main__':
    main()
