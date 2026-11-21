"""Compare three pinned Harvard Dataverse releases and prepared-vs-monitor labels.
Usage: python derive_crimp.py DIRECTORY OUTPUT (crimp-v1.pkl, crimp_force_curves_dataset.pkl [v2], crimp-v3.pkl).
Python 3, pandas and NumPy.
"""
import argparse
import csv
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd


def write(path, rows):
    with path.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=rows[0],lineterminator='\n')
        w.writeheader()
        w.writerows(rows)


def load_verified(path,expected):
    with path.open('rb') as f:
        observed=hashlib.file_digest(f,'md5').hexdigest()
    if observed!=expected:
        raise ValueError(f'File differs from the fixed release: {path.name}')
    frame=pd.read_pickle(path).set_index('CrimpID')
    if frame.index.has_duplicates:
        raise ValueError('Duplicate CrimpID')
    return frame


def compare(old,new,v):
    shared=old.index.intersection(new.index)
    counts={}
    condition_labels=['Wire_cross-section_conductor','Main_label_string','Main-label_encoded','Sub_label_string',
                      'Sub_label_encoded','Binary_label_encoded','CFM_label_encoded']
    offsets=[]
    for field in ('Force_curve_raw','Force_curve_baseline','Force_curve_RoI'):
        mismatch=0
        for a,b in zip(old.loc[shared,field],new.loc[shared,field]):
            if not np.array_equal(a,b):
                mismatch+=1
            if field=='Force_curve_baseline':
                difference=np.asarray(a)-np.asarray(b)
                if np.ptp(difference)!=0:
                    raise ValueError('Nonconstant version difference in baseline')
                offsets.append(difference[0])
        counts[field]=mismatch
    label_changes=sum(any(old.at[k,c]!=new.at[k,c] for c in condition_labels) for k in shared)
    return dict(from_version=v,to_version=v+1,matched_ids=len(shared),
                removed_ids='|'.join(str(int(x)) for x in sorted(set(old.index)-set(new.index))),
                added_ids='|'.join(str(int(x)) for x in sorted(set(new.index)-set(old.index))),
                labels_or_material_changed=label_changes,raw_changed=counts['Force_curve_raw'],
                baseline_changed=counts['Force_curve_baseline'],roi_changed=counts['Force_curve_RoI'],
                min_old_minus_new_baseline_count=min(offsets),max_old_minus_new_baseline_count=max(offsets))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('directory',type=Path)
    p.add_argument('output',type=Path)
    args=p.parse_args()
    releases=[('crimp-v1.pkl','f1c39c33177631850e2daa65121205ef'),
              ('crimp_force_curves_dataset.pkl','1fb170027a907c3f292150e5b9dd39cd'),
              ('crimp-v3.pkl','41631f2f1701cedca4be391eb567f4de')]
    frames=[load_verified(args.directory/f,md5) for f,md5 in releases]
    versions=[]
    for i,frame in enumerate(frames,1):
        raw=frame.Force_curve_raw
        bas=frame.Force_curve_baseline
        roi=frame.Force_curve_RoI
        versions.append(dict(version=i,crimps=len(frame),raw_points=sum(map(len,raw)),finite_raw_and_complete_roi=sum(
            np.isfinite(x).all() and len(x)==3566 and len(z)==500 for x,z in zip(raw,roi)),
            first_value_minus_raw_matches=sum(np.array_equal(x[0]-x,y) for x,y in zip(raw,bas)),
            baseline_1575_to_2074_matches_roi=sum(np.array_equal(y[1575:2075],z) for y,z in zip(bas,roi)),
            distinct_raw_waves=len({hashlib.sha256(np.asarray(x,dtype='<f8').tobytes()).digest() for x in raw})))
    labels=[]
    for (size,sub),frame in frames[-1].groupby(['Wire_cross-section_conductor','Sub_label_string']):
        actual=frame.Binary_label_encoded.to_numpy(dtype=int)
        mon=frame.CFM_label_encoded.to_numpy(dtype=int)
        labels.append(dict(section_mm2=size,prepared_condition=sub,crimps=len(frame),
                           prep_ok_monitor_ok=int(sum((actual==0)&(mon==0))),
                           prep_ok_monitor_nok=int(sum((actual==0)&(mon==1))),
                           prep_nok_monitor_ok=int(sum((actual==1)&(mon==0))),
                           prep_nok_monitor_nok=int(sum((actual==1)&(mon==1)))))
    args.output.mkdir(parents=True,exist_ok=True)
    write(args.output/'crimp-versions.csv',versions)
    write(args.output/'crimp-cross-version.csv',[compare(frames[i],frames[i+1],i+1) for i in range(2)])
    write(args.output/'crimp-quality-labels.csv',labels)


if __name__=='__main__':
    main()
