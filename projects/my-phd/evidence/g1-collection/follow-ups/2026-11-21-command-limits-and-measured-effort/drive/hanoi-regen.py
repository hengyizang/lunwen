"""Audit all 32 described brake-bench recordings, respecting measured time and session.
Usage: python hanoi-regen.py RAW_DIR OUTPUT_DIR (numpy).
"""
import csv
import hashlib
import io
import sys
import zipfile
from pathlib import Path

import numpy as np

raw, out = map(Path, sys.argv[1:])
out.mkdir(parents=True, exist_ok=True)
source = raw / 'du_lieu.zip'
assert hashlib.md5(source.read_bytes()).hexdigest() == '646f7efe2ea845245bfd3a5458047a4c'

def rows(archive, name):
    return list(csv.DictReader(io.StringIO(archive.read(name).decode('utf-8-sig'))))

fields = ['run','session','class','rows','t_span_s','min_dt_s','max_dt_s',
          'max_T_pb_ref_Nm','max_I_pb_A','speed_ref_rmse_all_kmh',
          'braking_endpoint_pairs','braking_duration_s','braking_charge_Wh',
          'braking_net_battery_Wh','braking_peak_charge_A','braking_rms_speed_error_kmh',
          'coast_gain_points','coast_median_brake_field_A_per_requested_Nm']
fmt = lambda x: f'{x:.6f}'
with zipfile.ZipFile(source) as z, (out / 'hanoi-regen-runs.csv').open('w', newline='') as f:
    index = next(n for n in z.namelist() if n.endswith('/TT_file_thu.csv'))
    base = index.rsplit('/', 1)[0]
    conditions = rows(z, index)
    assert len(set(r['ten'] for r in conditions)) == len(conditions) == 32
    writer = csv.writer(f, lineterminator='\n')
    writer.writerow(fields)
    for cond in conditions:
        run = cond['ten']
        data = rows(z, f'{base}/data/{run}.csv')
        def vec(key):
            a = np.array([float(r[key]) for r in data])
            assert np.isfinite(a).all()
            return a
        t, v, ref, a, u, ib, ipb, tref = map(vec, ('t_s','v_kmh','v_ref_kmh','a_ref_ms2',
                                                    'U_V','I_b_A','I_pb_A','T_pb_ref_Nm'))
        dt = np.diff(t)
        assert (dt > 0).all()
        braking = a > 0
        pairs = braking[:-1] & braking[1:]
        power = u * ib
        def energy(watts):
            return np.sum((watts[:-1] + watts[1:])[pairs] * dt[pairs] / 2) / 3600
        # Source coast tests contain run-up. Isolate the zero-acceleration-reference
        # portion at meaningful brake torque and small measured battery current.
        coast = (cond['loai'] == 'coast') & (a == 0) & (np.abs(ib) <= 0.3) & (tref >= 2)
        err = v - ref
        writer.writerow([run,cond['buoi'],cond['loai'],len(t),fmt(t[-1]-t[0]),fmt(dt.min()),
                         fmt(dt.max()),fmt(tref.max()),fmt(ipb.max()),fmt(np.sqrt(np.mean(err**2))),
                         int(pairs.sum()),fmt(dt[pairs].sum()),
                         fmt(energy(np.maximum(power,0))) if pairs.any() else '',
                         fmt(energy(power)) if pairs.any() else '',
                         fmt(max(0, ib[braking].max())) if braking.any() else '',
                         fmt(np.sqrt(np.mean(err[braking]**2))) if braking.any() else '',
                         int(coast.sum()),fmt(np.median(ipb[coast]/tref[coast])) if coast.any() else ''])
