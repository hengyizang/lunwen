"""Audit CARMA 1 released 20 Hz bins and logger reports, keeping runs separate.

python derive_fhwa.py full.csv[.gz] run-list.json OUTPUT
Python 3.11+, pandas, NumPy. Per-run scratch is created in a temporary directory.
"""
import argparse
from contextlib import ExitStack
import csv
import gzip
import json
from pathlib import Path
import tempfile

import numpy as np
import pandas as pd


VEHICLES = {'bl':'black', 'grn':'green', 'gry':'grey', 'ag':'silver', 'wt':'white'}


def split_runs(path, directory, counts):
    found = {run: 0 for run in counts}
    opener = gzip.open if path.suffix == '.gz' else open
    with opener(path, 'rb') as src, ExitStack() as stack:
        header = src.readline()
        if not header.startswith(b'Run,'): raise ValueError('Unexpected FHWA table')
        outputs = {}
        for run in found:
            f = stack.enter_context(gzip.open(directory / f'{run}.gz', 'wb', compresslevel=1))
            f.write(header)
            outputs[run] = f
        for line in src:
            run = int(line.split(b',', 1)[0])
            outputs[run].write(line)
            found[run] += 1
    if found != counts: raise ValueError('Counts differ from Socrata per-run query')


def as_number(df, key):
    return pd.to_numeric(df[key], errors='raise').to_numpy(dtype=float)


def table(df, name, path):
    df.to_csv(path / name, index=False, float_format='%.8g', lineterminator='\n')


def speed_rows(df, run, vehicle, grid_end):
    # Evaluate both lags on identical support. Keep holes as missing.
    signal = np.full(grid_end+1, np.nan)
    reference = signal.copy()
    indices = df['_tick'].to_numpy(dtype=int)
    signal[indices] = as_number(df, 'speed_CACC-'+vehicle)
    reference[indices] = as_number(df, 'velocity_fwd_PINPOINT-'+vehicle)
    delay = 320
    x, current, earlier = signal[delay:], reference[delay:], reference[:-delay]
    mask = np.isfinite(x) & np.isfinite(current) & np.isfinite(earlier)
    x, current, earlier = x[mask], current[mask], earlier[mask]
    result = dict(run=run, vehicle=VEHICLES[vehicle], cacc_speed_bins=int(np.isfinite(signal).sum()),
                  pinpoint_speed_bins=int(np.isfinite(reference).sum()), common_0s_and_16s_bins=len(x))
    def mean_error(values):
        return float(np.sqrt(np.mean((x-values)**2))) if len(x) else None
    result.update(reference_p95_minus_p05_m_per_s=(np.quantile(current,.95)-np.quantile(current,.05)) if len(x) else None,
                  rmse_to_current_pinpoint_m_per_s=mean_error(current),
                  rmse_to_16s_earlier_pinpoint_m_per_s=mean_error(earlier))
    cmd = as_number(df, 'acc_axle_torque_cmd_axle_torque_request-'+vehicle)
    injected = as_number(df, 'research_bus_injected_torque_CACC_MAB-'+vehicle)
    accel = as_number(df, 'accel_fwd_PINPOINT-'+vehicle)
    result.update(axle_request_bins=int(np.isfinite(cmd).sum()), research_injection_bins=int(np.isfinite(injected).sum()),
                  request_and_pinpoint_accel_same_bin=int((np.isfinite(cmd)&np.isfinite(accel)).sum()))
    return result


def endpoint_rows(df, run, vehicle, other):
    # Suffix and prefix are reported independently, without assuming a universal RF timestamp.
    mask = lambda x: np.isfinite(x)
    own = VEHICLES[vehicle]
    a = as_number(df, f'{other}_admas_sos-{vehicle}')
    p = as_number(df, f'{other}_prism_sos-{vehicle}')
    ta = as_number(df, f'{other}_admas_too-{vehicle}')
    tp = as_number(df, f'{other}_prism_too-{vehicle}')
    sa = as_number(df, f'{own}_admas_too-{vehicle}')
    sp = as_number(df, f'{own}_prism_too-{vehicle}')
    paired = mask(a) & mask(p)
    result = dict(run=run, vehicle_suffix=own, other_colour_prefix=other,
                  finite_admas_sos=int(mask(a).sum()), finite_prism_sos=int(mask(p).sum()),
                  paired_sos=int(paired.sum()), paired_negative_admas=int((a[paired]<0).sum()),
                  paired_negative_prism=int((p[paired]<0).sum()), paired_opposite_sign=int((a[paired]*p[paired]<0).sum()))
    for tag, own_t, peer_t, metric in [('admas',sa,ta,a), ('prism',sp,tp,p)]:
        valid = mask(own_t)&mask(peer_t)&mask(metric)
        result[tag+'_both_too_and_sos'] = int(valid.sum())
        result[tag+'_equal_too_nonzero_sos'] = int((valid&(own_t==peer_t)&(metric!=0)).sum())
        result[tag+'_too_with_fractional_seconds'] = int((mask(peer_t)&(peer_t!=np.trunc(peer_t))).sum())
        result[tag+'_paired_sos_median_ms'] = float(np.median(metric[paired])*1000) if paired.any() else None
    return result


# Eight five-vehicle speed-profile runs in Table 12 that form the four Hybrid
# and four CACC evaluations in Figs. 18–25. Use the dataset's actual 2016 UTC.
PROFILES = {
    '07/27/2016 15:16': ('Hybrid', ('wt','gry','grn','ag')),
    '07/27/2016 16:27': ('Hybrid', ('gry','grn','ag','wt')),
    '07/27/2016 16:34': ('Hybrid', ('grn','ag','wt','gry')),
    '07/27/2016 16:41': ('Hybrid', ('ag','wt','gry','grn')),
    '07/28/2016 14:56': ('CACC', ('wt','ag','gry','grn')),
    '07/28/2016 15:04': ('CACC', ('ag','gry','grn','wt')),
    '07/28/2016 15:15': ('CACC', ('gry','grn','wt','ag')),
    '07/28/2016 15:22': ('CACC', ('grn','wt','ag','gry')),
}


def profile_events(ticks, values, decreasing):
    # 52.5 mph is the midpoint between the prescribed 60 and 45 mph plateaus.
    # A missing interval longer than 150 ms breaks both conditioning and crossing.
    midpoint=52.5*0.44704
    valid=np.isfinite(values)
    armed=False
    base_start=cross_start=last=None
    events=[]
    for tick,speed in zip(ticks[valid],values[valid]):
        if last is None or tick-last>3:
            base_start=cross_start=None
            armed=False
        last=tick
        base=speed>25 if decreasing else speed<21
        beyond=speed<midpoint if decreasing else speed>midpoint
        if base:
            if base_start is None:base_start=tick
            if tick-base_start>=100:armed=True
        else:base_start=None
        if armed and beyond:
            if cross_start is None:cross_start=tick
            if tick-cross_start>=8:
                events.append(cross_start/20)
                armed=False
                cross_start=None
        else:cross_start=None
    return events


def compare_motion(clean, run):
    start=clean.iloc[0]['bin_utc_time_formatted'][:16]
    if start not in PROFILES:return []
    mode,followers=PROFILES[start]
    ticks=clean['_tick'].to_numpy()
    results=[]
    first_down=None
    for decreasing in (True,False):
        events={v:profile_events(ticks,as_number(clean,'velocity_fwd_PINPOINT-'+v),decreasing)
                for v in ('bl',*followers)}
        times=events['bl']
        if decreasing:
            first_down=times[0] if times else None
        else:
            times=[t for t in times if first_down is not None and t>first_down]
        for n,leader_time in enumerate(times[:1],1):
            for position,v in enumerate(followers,1):
                near=[t for t in events[v] if abs(t-leader_time)<=15]
                results.append(dict(run=run,mode=mode,leader_event=n,direction='down' if decreasing else 'up',
                                    speed_threshold_mph=52.5,leader_colour='black',follower_position=position,
                                    follower_colour=VEHICLES[v],leader_elapsed_s=leader_time,
                                    candidates_within_15s=len(near),follower_elapsed_s=near[0] if len(near)==1 else None,
                                    follower_minus_leader_s=near[0]-leader_time if len(near)==1 else None))
    return results


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('bulk',type=Path)
    p.add_argument('run_list',type=Path)
    p.add_argument('output',type=Path)
    args=p.parse_args()
    counts={int(x['run']):int(x['n']) for x in json.loads(args.run_list.read_text())}
    runs, links, speeds, motions = [], [], [], []
    args.output.mkdir(exist_ok=True,parents=True)
    with tempfile.TemporaryDirectory() as tmp:
        folder=Path(tmp)
        split_runs(args.bulk,folder,counts)
        for run in sorted(counts):
            src=pd.read_csv(folder/f'{run}.gz',low_memory=False)
            if len(src.columns)!=478:raise ValueError('Unexpected source column count')
            distinct=src.drop_duplicates().copy()
            ticks=as_number(distinct,'elapsed_time (s)')*20
            if not np.allclose(ticks,np.rint(ticks),rtol=0,atol=1e-5):raise ValueError('Off-grid elapsed time')
            distinct['_tick']=np.rint(ticks).astype(int)
            conflict=distinct['_tick'].duplicated(keep=False)
            clean=distinct.loc[~conflict].sort_values('_tick')
            runs.append(dict(run=run, source_rows=len(src), excess_identical_478_field_rows=len(src)-len(distinct),
                             conflicting_elapsed_bins=distinct.loc[conflict,'_tick'].nunique(),
                             distinct_rows_in_conflict=int(conflict.sum()), retained_unique_bins=len(clean),
                             first_formatted_utc=clean.iloc[0]['bin_utc_time_formatted'],
                             last_formatted_utc=clean.iloc[-1]['bin_utc_time_formatted']))
            motions.extend(compare_motion(clean,run))
            for v,own in VEHICLES.items():
                speeds.append(speed_rows(clean,run,v,int(distinct['_tick'].max())))
                links.extend(endpoint_rows(clean,run,v,other) for other in VEHICLES.values() if other!=own)
    for data,name in [(runs,'fhwa-run-coverage.csv'),(links,'fhwa-logger-comparison.csv'),(speeds,'fhwa-vehicle-channels.csv'),(motions,'fhwa-paired-motion.csv')]:
        table(pd.DataFrame(data),name,args.output)


if __name__=='__main__':
    main()
