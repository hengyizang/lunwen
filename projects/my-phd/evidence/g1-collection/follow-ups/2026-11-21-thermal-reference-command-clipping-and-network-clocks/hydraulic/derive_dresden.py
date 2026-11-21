"""Compare independent repeat runs, drive channels, and both published FRF prediction tasks.
Pass Heindel2021_dataset.zip (or the sparse ZIP made by fetch_dresden.py) and an output directory.
"""
import argparse
import csv
import json
from pathlib import Path
from zipfile import ZipFile
import numpy as np


def read_trace(z, stem):
    meta=json.loads(z.read(stem+'.json'))
    names=meta['channel_names']
    if meta['sampling_interval']!=0.001 or len(names)!=meta['channel_number']:
        raise ValueError(stem)
    result={}
    for index,(name,unit) in enumerate(zip(names,meta['units']),1):
        x=np.frombuffer(z.read(f'{stem}_cn_{index}.float32'),dtype='<f4').astype(float)
        if not np.isfinite(x).all() or (unit!='kN' if name.startswith('Force') else unit!='mm'):
            raise ValueError(stem+' '+name)
        canonical=name.removesuffix(' - Unfilt.').replace('ForceComp','Force')
        if canonical in result:
            raise ValueError('Repeated channel '+name)
        result[canonical]=x
    return result


def rms(x):
    return round(np.sqrt(np.mean(x*x)),9)


def main(path,out):
    rows=[]
    with ZipFile(path) as z:
        paths=sorted(n[:-5] for n in z.namelist() if n.startswith('measurement_data/test_data/') and '/out_' in n and n.endswith('_1.json'))
        for path in paths:
            condition,member=path.split('/')[-2:]
            name=member[4:-2]
            input_stem=f'measurement_data/test_data/{condition}/in_{name}'
            commands=read_trace(z,input_stem) if input_stem+'.json' in z.namelist() else {}
            measured=[read_trace(z,f'measurement_data/test_data/{condition}/out_{name}_{i}') for i in (1,2)]
            virtual=[read_trace(z,f'FRF_predictions/Force_from_Disp/test_data/{condition}/FRFCalc_from_Disp_{name}_{i}') for i in (1,2)]
            forward=read_trace(z,f'FRF_predictions/Sensors_from_Drive/test_data/{condition}/FRFCalc_from_in_{name}')
            for axis in 'XYZ':
                channel='Force'+axis
                x1,x2=[m[channel] for m in measured]
                c=commands.get(channel,np.array([]))
                f=forward[channel]
                v1,v2=[v[channel] for v in virtual]
                pos1,pos2=[m['Displacement'+axis] for m in measured]
                predicted_pos=forward['Displacement'+axis]
                if len(set(map(len,[x1,x2,v1,v2,pos1,pos2])))!=1:
                    raise ValueError('Unaligned record lengths '+path)
                rows.append(dict(family=condition,drive_member=name,axis=axis,samples_per_repetition=len(x1),drive_rows=len(c),forward_prediction_rows=len(f),
                    drive_min_kN=round(min(c),7) if len(c) else '',drive_max_kN=round(max(c),7) if len(c) else '',
                    measured_minus_drive_rms_rep1_kN=rms(x1-c) if len(c)==len(x1) else '',measured_minus_drive_rms_rep2_kN=rms(x2-c) if len(c)==len(x2) else '',
                    force_repeat_difference_rms_kN=rms(x2-x1),position_repeat_difference_rms_mm=rms(pos2-pos1),
                    forward_force_rmse_rep1_kN=rms(f-x1) if len(f)==len(x1) else '',forward_force_rmse_rep2_kN=rms(f-x2) if len(f)==len(x2) else '',
                    virtual_force_rmse_rep1_kN=rms(v1-x1),virtual_force_rmse_rep2_kN=rms(v2-x2),
                    forward_position_rmse_rep1_mm=rms(predicted_pos-pos1) if len(predicted_pos)==len(pos1) else '',forward_position_rmse_rep2_mm=rms(predicted_pos-pos2) if len(predicted_pos)==len(pos2) else ''))
    out.mkdir(parents=True,exist_ok=True)
    with (out/'dresden-force-repeats.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,rows[0],lineterminator='\n');w.writeheader();w.writerows(rows)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('archive',type=Path);p.add_argument('output',type=Path)
    args=p.parse_args()
    main(args.archive,args.output)
