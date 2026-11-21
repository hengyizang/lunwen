"""Check released event windows, reconstructed wrench reference and alternative force crossings.
python derive_sixth.py LOCAL_HF_CHECKOUT OUTPUT_DIRECTORY; requires h5py and numpy.
"""
import argparse
import csv
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import h5py
import numpy as np


def write(path,rows):
    with path.open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=rows[0],lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def max_error(a,b,valid):
    return float(np.max(np.abs(np.asarray(a)[valid]-np.asarray(b)[valid]))) if np.any(valid) else ''


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('source',type=Path)
    p.add_argument('output',type=Path)
    args=p.parse_args()
    files,timings=[],[]
    sensor_lines=defaultdict(list)
    for path in sorted(args.source.glob('*/*/data.h5')):
        with h5py.File(path) as f:
            scenario=path.relative_to(args.source).parts[0]
            valid=f['contact/force_valid'][:].astype(bool)
            times=f['time_ns'][:].astype(np.int64)
            row=dict(file=str(path.relative_to(args.source)),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                     scenario=scenario,pair_id=f.attrs['pair_id'],contact_link=f['contact/contact_link_name'][()].decode(),
                     frames=len(times),grid_median_dt_ms=round(np.median(np.diff(times))/1e6,6),force_valid_frames=int(valid.sum()),
                     native_sensor_rows=0,native_crc_matches=0,native_flag_unverified=0,
                     native_sensor_median_step_ms='',native_record_median_step_ms='',
                     event_at_exact_grid_sample='',event_force_valid='',event_force_norm_N='',
                     max_force_reconstruction_N='',max_pelvis_origin_moment_reconstruction_Nm='')
            if 'sensor' in f:
                meta=json.loads(f['metadata_json'][()])
                native=f['native/sensor']
                src=meta['sensor_id']
                sensor_lines[src].append(native['source_csv_line'][:].astype(np.int64))
                scalar=(f['sensor/fz_clean_N'][:].astype(float)-float(f['sensor/baseline_N'][()]))*float(f['contact/gain'][()])*float(f['contact/sensor_polarity'][()])
                force=f['contact/force_pelvis_N'][:].astype(float)
                arm=f['contact/contact_point_pelvis_m'][:].astype(float)
                predicted=scalar[:,None]*f['contact/force_axis_pelvis'][:]
                moment=f['contact/moment_about_pelvis_origin_pelvis_Nm'][:]
                event=int(f['event_time_ns'][()])
                offset=(times-event)/1e9
                event_ix=np.flatnonzero(times==event)
                mag=np.linalg.norm(force,axis=1)
                has=bool(len(event_ix)==1 and valid[event_ix[0]])
                row.update(native_sensor_rows=len(native['sensor_time_ns']),
                           native_sensor_median_step_ms=round(np.median(np.diff(native['sensor_time_ns'][:]))/1e6,6),
                           native_record_median_step_ms=round(np.median(np.diff(native['record_time_ns'][:]))/1e6,6),
                           native_crc_matches=int(native['crc_matches'][:].sum()),
                           native_flag_unverified=int(native['unverified'][:].sum()),
                           event_at_exact_grid_sample=int(len(event_ix)==1),event_force_valid=int(has),
                           event_force_norm_N=round(mag[event_ix[0]],7) if has else '',
                           max_force_reconstruction_N=max_error(predicted,force,valid),
                           max_pelvis_origin_moment_reconstruction_Nm=max_error(np.cross(arm,force),moment,valid))
                for threshold in (2,5,10):
                    above=valid & (mag>=threshold)
                    ix=[i for i in range(1,len(times)-2) if -.5<=offset[i]<=.5 and valid[i-1] and not above[i-1]
                        and np.all(above[i:i+3]) and times[i+2]-times[i-1]==60_000_000]
                    timings.append(dict(pair_id=row['pair_id'],link=row['contact_link'],threshold_N=threshold,
                                        candidate_rises=len(ix),unique_rise_minus_event_ms=round(offset[ix[0]]*1000,5) if len(ix)==1 else ''))
            files.append(row)
    if not files:raise ValueError('No HDF5 recordings')
    origins=[]
    for src,trials in sorted(sensor_lines.items()):
        cells=np.concatenate(trials)
        origins.append(dict(source_sensor_recording=src,stand_windows=len(trials),native_rows=len(cells),
                            distinct_source_csv_lines=len(np.unique(cells)),repeated_source_lines=len(cells)-len(np.unique(cells))))
    args.output.mkdir(parents=True,exist_ok=True)
    for name,values in [('windows',files),('crossings',timings),('source-recordings',origins)]:
        write(args.output/f'sixth-{name}.csv',values)


if __name__=='__main__':
    main()
