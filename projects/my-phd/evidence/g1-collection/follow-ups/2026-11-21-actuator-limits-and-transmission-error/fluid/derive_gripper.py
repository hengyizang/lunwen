"""Check raw vs calculated sensor channels and CSV support in Zenodo 23005291."""
import argparse
import csv
from datetime import datetime
import hashlib
import io
from itertools import combinations
import math
from pathlib import Path
from zipfile import ZipFile


def write(path, rows):
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=rows[0],lineterminator='\n')
        w.writeheader()
        w.writerows(rows)


def inspect(archive_path):
    reports=[]
    runs={}
    with ZipFile(archive_path) as z:
        for name in sorted(z.namelist()):
            if not name.endswith('.csv'):
                continue
            data=z.read(name)
            read=csv.DictReader(io.StringIO(data.decode('utf-8-sig')))
            raw=list(read)
            present=[r for r in raw if any(r.values())]
            complete=[r for r in present if all(r.values())]
            meta=dict(archive=archive_path.name,member=name,sha256=hashlib.sha256(data).hexdigest(),kind='fitted_parameters' if 'Finger' in read.fieldnames else 'acquired_series',
                      nonheader_rows=len(raw),blank_rows=len(raw)-len(present),partial_rows=len(present)-len(complete),
                      complete_rows=len(complete),unique_timestamp_labels='',adjacent_equal_timestamps='',pressure_field='',pressure_min='',pressure_max='',pressure_predictions_match_3dp='',max_abs_pressure_residual_kpa='')
            if 'Timestamp' in read.fieldnames:
                t=[datetime.strptime(r['Timestamp'],'%m/%d/%Y %H:%M') for r in complete]
                if not all(b>=a for a,b in zip(t,t[1:])):
                    raise ValueError(name+' time moved backwards')
                pk=next(k for k in ('System Pressure','Predicted Pressure','Pressure Value') if k in read.fieldnames)
                pressure=[float(r[pk]) for r in complete]
                assert all(math.isfinite(p) for p in pressure)
                meta.update(unique_timestamp_labels=len(set(t)),adjacent_equal_timestamps=sum(a==b for a,b in zip(t,t[1:])),
                            pressure_field=pk,pressure_min=min(pressure),pressure_max=max(pressure))
                if pk=='System Pressure':
                    # Part 2, Program S5, generates this column from the archived two-decimal voltage.
                    errors=[]
                    for row,p in zip(complete,pressure):
                        v=float(row['Potentiometer Voltage'])
                        predicted=float(format(.5263*v*v+18.5199*v+1.9964,'.3f'))
                        errors.append(abs(p-predicted))
                    meta.update(pressure_predictions_match_3dp=sum(e<1e-9 for e in errors),
                                max_abs_pressure_residual_kpa=max(errors))
                    runs[name]=[tuple(r[k] for k in read.fieldnames) for r in complete]
            reports.append(meta)
    return reports,runs


def compare(runs):
    out=[]
    for a,b in combinations(sorted(runs),2):
        aa,bb=runs[a],runs[b]
        prefix=next((i for i,(v,w) in enumerate(zip(aa,bb)) if v!=w),min(len(aa),len(bb)))
        out.append(dict(first=a,second=b,rows_first=len(aa),rows_second=len(bb),identical_initial_complete_rows=prefix))
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('source_dir',type=Path)
    p.add_argument('output',type=Path)
    args=p.parse_args()
    all_files=[]
    runs={}
    for name in ('Data S1 - Blocking data.zip','Data S2 - Gripping data.zip'):
        file_rows,series=inspect(args.source_dir/name)
        all_files.extend(file_rows)
        runs.update(series)
    args.output.mkdir(exist_ok=True,parents=True)
    write(args.output/'gripper-csv-audit.csv',all_files)
    write(args.output/'gripper-grasp-prefixes.csv',compare(runs))
