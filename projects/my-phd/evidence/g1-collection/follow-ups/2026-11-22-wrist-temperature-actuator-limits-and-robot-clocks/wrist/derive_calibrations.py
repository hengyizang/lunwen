"""Compute aggregate comparisons from the versioned JPL PDF and Cornell capture CSVs.

Usage: python derive_calibrations.py CL21_2256.pdf path/to/HS2026-1D-curvature output_dir
Cornell checkout: 7d321a0db2554c696fe0ef9511187b50ae80fb0b. Requires PyMuPDF.
"""
import argparse
import csv
import hashlib
import math
from collections import defaultdict
from pathlib import Path
from statistics import fmean

import fitz

def write(root, name, rows):
    with (root/name).open('w',newline='',encoding='utf-8') as stream:
        out=csv.DictWriter(stream,fieldnames=list(rows[0]),lineterminator='\n')
        out.writeheader()
        out.writerows(rows)

def analyze_jpl(path, output):
    assert hashlib.md5(path.read_bytes()).hexdigest()=='ba07af1596873521fe7969e8605410d7'
    rows=[]
    with fitz.open(path) as pdf:
        shapes=pdf[10].get_drawings()
        assert len(shapes)==56
        for block,(metric,unit,max_value,axes) in enumerate([
            ('absolute','N',180,('Fx','Fy','Fz')),('absolute','N m',8,('Mx','My','Mz')),
            ('relative','N',50,('Fx','Fy','Fz')),('relative','N m',5,('Mx','My','Mz'))]):
            base=14*block
            frame=shapes[base+2]['rect']
            heights=[]
            for series in range(4):
                rects=shapes[base+4+series]['items']
                assert len(rects)==3 and all(item[0]=='re' for item in rects)
                assert all(abs(item[1].y1-frame.y1)<0.02 for item in rects)
                heights.append([item[1].height for item in rects])
            for side,name in enumerate(('A','B')):
                for i,axis in enumerate(axes):
                    before=heights[side][i]
                    after=heights[side+2][i]
                    rows.append(dict(metric=metric,axis=axis,redundant_side=name,unit=unit,
                        plotted_error_reduction_approx=round((before-after)*max_value/frame.height,2),
                        plotted_error_reduction_percent_approx=round(100*(before-after)/before,1)))
    assert len(rows)==24
    write(output,'jpl-figure7-contrasts.csv',rows)

def rms_error(a,b):
    return math.sqrt(fmean((x-y)**2 for x,y in zip(a,b)))

def analyze_cornell(path,output):
    trials=[]
    windows=[]
    inventory=[]
    for f in sorted(path.rglob('*.csv')):
        rel=f.relative_to(path).as_posix()
        blob=f.read_bytes()
        digest=hashlib.sha1(b'blob '+str(len(blob)).encode()+b'\0'+blob).hexdigest()
        with f.open() as stream:
            if rel=='MLPtraining/sensor_data.csv':
                header=stream.readline().strip().split()
                assert len(header)==17 and header[-1]=='kappa'
                values=[list(map(float,line.split())) for line in stream if line.strip()]
                assert all(len(r)==17 and all(map(math.isfinite,r)) for r in values)
                count=len(values)
                note='Zero-load labelled curvature examples; distinct kappa values '+str(len({r[-1] for r in values}))
            elif rel.startswith('calibration_code/calibration_data/'):
                rows=list(csv.DictReader(stream));by_step=defaultdict(list)
                for row in rows:
                    assert len(row)==18
                    by_step[int(row['Step'])].append(row)
                count=len(rows)
                note='Signed ATI Fz with 16 resistive nodes and recorded step ID'
                for step,rr in sorted(by_step.items()):
                    load=[float(x['FT_Z']) for x in rr]
                    central=[sum(float(x[k]) for k in ('S5','S6','S9','S10')) for x in rr]
                    trials.append(dict(file=f.name,step=step,samples=len(rr),
                        mean_signed_reference_N=round(fmean(load),5),min_reference_N=round(min(load),5),
                        max_reference_N=round(max(load),5),mean_central_four_sum=round(fmean(central),5)))
            elif rel.startswith('validation/daily_objects/'):
                rr=list(csv.DictReader(stream))
                count=len(rr)
                note='Static hold window, simultaneous columns as stored; no per-row timestamps'
                ref=[float(x['ft_z']) for x in rr]
                flat=[float(x['force_c0']) for x in rr]
                aware=[float(x['force_curv']) for x in rr]
                token=f.stem.split('_ref')[1].split('_')[0]
                windows.append(dict(object=f.parent.name,file=f.name,rows=count,target_N=token,stored_curvatures='|'.join(sorted({x['curvature'] for x in rr})),
                    mean_reference_N=round(fmean(ref),5),flat_error_rms_N=round(rms_error(ref,flat),5),
                    curved_error_rms_N=round(rms_error(ref,aware),5),
                    flat_minus_curved_MAE_N=round(fmean(abs(x-z)-abs(y-z) for x,y,z in zip(flat,aware,ref)),5)))
            else:
                continue
        inventory.append(dict(file=rel,git_blob_sha1=digest,bytes=len(blob),rows=count,note=note))
    assert len(trials)==96 and sum(r['samples'] for r in trials)==9600
    assert len(windows)==25 and len(inventory)==33
    write(output,'cornell-calibration-steps.csv',trials)
    write(output,'cornell-hold-windows.csv',windows)
    write(output,'cornell-files.csv',inventory)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for arg in ('pdf','checkout','output'):
        parser.add_argument(arg,type=Path)
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    analyze_jpl(args.pdf,args.output)
    analyze_cornell(args.checkout,args.output)
