"""Inspect every PATU655Stress v2 CSV. Requires NumPy and pandas."""
import argparse
import csv
import hashlib
import io
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import pandas as pd


def export(path,rows):
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=rows[0],lineterminator='\n')
        w.writeheader()
        w.writerows(rows)


def channel(frame, axis, filename):
    ix,cmd=(1,'Ulift[V]') if axis=='lift' else (2,'Ujib[V]')
    command=frame[cmd].to_numpy()
    stroke=frame[f'S{ix}[mm]'].to_numpy()
    pa=frame[f'PA{ix}[bar]'].to_numpy()
    pb=frame[f'PB{ix}[bar]'].to_numpy()
    finite=np.isfinite(command)&np.isfinite(stroke)&np.isfinite(pa)&np.isfinite(pb)
    if not finite.all():
        raise ValueError(f'Unexpected nonfinite value in {filename}: {axis}')
    # Use integer mV only for grouping constant nominal commands.
    mv=np.rint(1000*command).astype(np.int64)
    starts=np.r_[0,np.flatnonzero(np.diff(mv)!=0)+1]
    ends=np.r_[starts[1:],len(mv)]
    long=(ends-starts)>=8
    left,right=starts[long],ends[long]
    net=stroke[right-1]-stroke[left]
    return dict(member=filename,axis=axis,paired_rows=len(command),
                u_min_V=float(command.min()),u_max_V=float(command.max()),
                distinct_command_mV=len(np.unique(mv)),
                stroke_min_mm=float(stroke.min()),stroke_max_mm=float(stroke.max()),
                pa_minus_pb_p05_bar=float(np.quantile(pa-pb,.05)),pa_minus_pb_p95_bar=float(np.quantile(pa-pb,.95)),
                constant_intervals_8_or_more_rows=len(net),
                such_intervals_at_least_1mm_net_travel=int(np.count_nonzero(np.abs(net)>=1)),
                max_abs_net_travel_in_a_constant_interval_mm=float(np.max(np.abs(net))) if len(net) else '')


def run(archive,output):
    trials=[]
    channels=[]
    with ZipFile(archive) as z:
        for filename in sorted(n for n in z.namelist() if n.endswith('.csv')):
            raw=z.read(filename)
            frame=pd.read_csv(io.BytesIO(raw),dtype={'Time[epoch_ms]':'int64'})
            if frame.shape[1]!=20:
                raise ValueError(filename+' schema')
            stamps=frame['Time[epoch_ms]'].to_numpy()
            dt=np.diff(stamps)
            signals=frame.iloc[:,1:].to_numpy()
            repeats=np.all(signals[1:]==signals[:-1],axis=1)
            keep=np.r_[True,~repeats]
            new_dt=np.diff(stamps[keep])
            first=int(stamps[0])
            # As printed, first timestamps are about 1.75e18. ns yields calendar dates in 2025.
            stamp_date=pd.Timestamp(first,unit='ns',tz='UTC').strftime('%Y-%m-%d')
            load=int(Path(filename).parent.name.removesuffix('KG'))
            row=dict(member=filename,load_kg_folder=load,sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw),
                     rows=len(stamps),n_channels_including_timestamp=frame.shape[1],
                     nonfinite_measurement_cells=int((~np.isfinite(frame.iloc[:,1:].to_numpy())).sum()),
                     first_raw_timestamp=first,last_raw_timestamp=int(stamps[-1]),first_utc_date_if_ns=stamp_date,
                     adjacent_identical_all_19_channels=int(repeats.sum()),
                     identical_transitions_first_of_each_pair=int(repeats[::2].sum()),
                     identical_transitions_between_pairs=int(repeats[1::2].sum()),
                     channel_updates_collapsing_adjacent_repeats=int(keep.sum()),
                     update_Hz_if_ns_collapsing_adjacent_repeats=1e9/float(np.median(new_dt)),
                     adjacent_equal_timestamp=int(np.count_nonzero(dt==0)),backward_timestamp=int(np.count_nonzero(dt<0)),
                     minimum_raw_step=int(dt.min()),median_raw_step=float(np.median(dt)),maximum_raw_step=int(dt.max()),
                     sample_Hz_if_ns=1e9/float(np.median(dt)),
                     supply_p50_bar=float(frame['PS[bar]'].median()),return_p50_bar=float(frame['PT[bar]'].median()))
            trials.append(row)
            channels.extend(channel(frame,axis,filename) for axis in ('lift','jib'))
    output.mkdir(parents=True,exist_ok=True)
    export(output/'patu-acquisitions.csv',trials)
    export(output/'patu-valve-and-stroke.csv',channels)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mendeley_zip',type=Path)
    p.add_argument('output',type=Path)
    args=p.parse_args()
    run(args.mendeley_zip,args.output)
