"""Read Farias et al. v4. Python 3 + NumPy. Run: python derive_clamp.py RELEASE.zip OUT."""
import argparse
import csv
import hashlib
import io
from itertools import product
from pathlib import Path
from zipfile import ZipFile
import numpy as np


def write(path, rows):
    with path.open('w',newline='',encoding='utf-8') as stream:
        writer=csv.DictWriter(stream,fieldnames=rows[0],lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def fmt(v):
    return round(float(v),8)


def first_crossing_angle(x,y,level):
    idx=np.flatnonzero((y[:-1]<level)&(y[1:]>=level))
    if not len(idx):
        return None
    i=idx[0]
    return x[i]+(level-y[i])*(x[i+1]-x[i])/(y[i+1]-y[i])


def force_at_angle(x,y,pos):
    exact=y[x==pos].tolist()
    between=(np.minimum(x[:-1],x[1:])<pos)&(np.maximum(x[:-1],x[1:])>pos)
    ix=np.flatnonzero(between)
    candidates=exact+[y[i]+(y[i+1]-y[i])*(pos-x[i])/(x[i+1]-x[i]) for i in ix]
    return (len(candidates),fmt(candidates[0]) if len(candidates)==1 else '')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive',type=Path)
    parser.add_argument('out',type=Path)
    a=parser.parse_args()
    rows=[]
    with ZipFile(a.archive) as z:
        names=z.namelist()
        raw=z.read(next(n for n in names if n.endswith('/table_2.csv'))).decode('utf-8-sig')
        for spec in csv.reader(io.StringIO(raw),delimiter=';'):
            if not spec[0].isdigit():
                continue
            i=int(spec[0])
            channels={}
            out=dict(test=i,replicate_label=int(spec[1]),nominal_friction=float(spec[2]),
                     speed_level_as_published=int(spec[3]),coating_level=int(spec[4]),hardness_hv=int(spec[5]),
                     reported_stick_slip_factor=float(spec[6]),reported_preload_kn=float(spec[7]),reported_torque_nm=float(spec[8]))
            for channel in ('torque','force'):
                member=next(n for n in names if n.endswith(f'raw_data_{channel}_test_{i:02d}{channel[0]}.csv'))
                blob=z.read(member)
                x,y=np.loadtxt(io.BytesIO(blob),delimiter=',',skiprows=1,unpack=True)
                assert np.isfinite([x,y]).all()
                channels[channel]=(x,y)
                out.update({f'{channel}_sha256':hashlib.sha256(blob).hexdigest(),f'{channel}_rows':len(y),
                            f'{channel}_backward_angle_steps':int(sum(np.diff(x)<0)),
                            f'{channel}_equal_angle_steps':int(sum(np.diff(x)==0)),
                            f'{channel}_curve_max':fmt(y.max()),f'{channel}_final':fmt(y[-1])})
            tx,ty=channels['torque']
            fx,fy=channels['force']
            crossing=first_crossing_angle(tx,ty,40)
            assert crossing is not None
            candidates,force=force_at_angle(fx,fy,crossing)
            out.update(identical_angle_arrays=int(np.array_equal(tx,fx)),
                       first_40Nm_angle_deg=fmt(crossing),
                       force_values_intersecting_40Nm_angle=candidates,
                       interpolated_force_at_40Nm_kn=force)
            rows.append(out)
    assert len(rows)==48
    pairs=[]
    for speed,coat,hard in product((10,200),(-1,1),(135,430)):
        group=[r for r in rows if (r['speed_level_as_published'],r['coating_level'],r['hardness_hv'])==(speed,coat,hard)]
        low,high=([r for r in group if r['nominal_friction']==mu] for mu in (.1,.2))
        assert len(low)==len(high)==3
        record=dict(speed_level_as_published=speed,coating_level=coat,hardness_hv=hard,runs_per_cell=3)
        for col,unit in [('reported_preload_kn','preload_kn'),('reported_torque_nm','torque_nm'),('interpolated_force_at_40Nm_kn','preload_at_40Nm_kn')]:
            for label,condition in [('low',low),('high',high)]:
                vals=[x[col] for x in condition if x[col]!='']
                record[f'{label}_mu_{unit}']=fmt(np.median(vals)) if vals else ''
                record[f'{label}_mu_{unit}_n']=len(vals)
        pairs.append(record)
    a.out.mkdir(exist_ok=True,parents=True)
    write(a.out/'clamp-force-torque-runs.csv',rows)
    write(a.out/'clamp-friction-contrasts.csv',pairs)


if __name__=='__main__':
    main()
