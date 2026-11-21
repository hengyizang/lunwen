"""Reconstruct the pre-clip pump command using both published parameterizations.

Usage: python derive_two_tank.py Dataset.zip Dataset_v2.zip output_dir
Requires numpy and pandas. No measured data are written to the output.
"""
import argparse
import csv
import hashlib
import io
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import pandas as pd

SIGNALS = ['Level_pct', 'Control_Signal_pct', 'Setpoint_pct', 'Error_pct', 'Kp', 'a1', 'a2', 'b1']


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def array_digest(frame):
    # Use a canonical numeric representation independent of CSV formatting and column order.
    return digest(frame[SIGNALS].to_numpy(dtype='<f8').tobytes(order='C'))


def write(path, rows):
    with path.open('w', encoding='utf-8', newline='') as fp:
        writer = csv.DictWriter(fp, fieldnames=rows[0], lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def numbers(frame):
    return frame.apply(pd.to_numeric, errors='coerce')


def old_index(z):
    index = {}
    for name in sorted(z.namelist()):
        if name.lower().endswith('.csv') and '__MACOSX/' not in name:
            raw = z.read(name)
            table = pd.read_csv(io.BytesIO(raw))
            # Some v1 exports have an empty trailing row. Only remove wholly missing signals.
            clean = numbers(table[SIGNALS]).dropna(how='all')
            if clean.isna().any().any() or len(clean) != 30600:
                raise ValueError(name)
            k = array_digest(clean)
            if k in index:
                raise ValueError(f'duplicate v1 file data: {name}')
            index[k] = (name, digest(raw), len(table)-len(clean))
    return index


def run(name, data, index):
    df = pd.read_csv(io.BytesIO(data))
    if len(df) != 30600 or not np.array_equal(df['Time_s'], np.arange(len(df))):
        raise ValueError(f'invalid run length/index: {name}')
    key = array_digest(df)
    old_name, old_sha, empty = index.pop(key)
    e = df['Error_pct'].to_numpy()
    u = df['Control_Signal_pct'].to_numpy()
    if not np.allclose(e, df['Setpoint_pct'] - df['Level_pct'], atol=0.000001, rtol=0):
        raise ValueError(f'inconsistent error: {name}')
    # The first two samples use the offset PID, with zero-filled error history.
    startup = []
    for k in (0, 1):
        previous_error = 0.0 if k == 0 else e[k-1]
        startup.append(2*e[k] + 0.1*sum(e[:k+1]) + 0.5*(e[k]-previous_error) + 50)
    # k>=2: delay and disturbance act on the measured process, not on the controller's error-history indexing.
    delta_e = e[2:] - e[1:-1]
    delta2_e = e[2:] - 2*e[1:-1] + e[:-2]
    kp, ki, kd = (df[c].to_numpy()[2:] for c in ['Kp','Ki','Kd'])
    prior_u = u[1:-1]
    gain_request = prior_u + kp*delta_e + ki*e[2:] + kd*delta2_e
    # Independent expression directly from the same rounded a1, a2, b1 and the Dahlin tuning T=1 s, B=3.
    # Kp = -(a1+2*a2)*Q/b1; Kd = a2*Q/b1; Ki = (1+a1+a2)*Q/b1.
    a1,a2,b1 = (df[c].to_numpy()[2:] for c in ['a1','a2','b1'])
    q = -np.expm1(-1/3)
    model_request = prior_u + q/b1*(-(a1+2*a2)*delta_e + (1+a1+a2)*e[2:] + a2*delta2_e)
    if not all(np.isfinite(v).all() for v in (gain_request, model_request, u)) or np.any((u<0)|(u>100)):
        raise ValueError(f'nonfinite or out-of-bounds command: {name}')
    tol = 0.01 # percentage points; guard against reconstructing from rounded published gains.
    expected = u[2:]
    low = (gain_request < -tol) & (model_request < -tol)
    high = (gain_request > 100+tol) & (model_request > 100+tol)
    g_resid = np.abs(np.clip(gain_request,0,100)-expected)
    m_resid = np.abs(np.clip(model_request,0,100)-expected)
    dual_low = low & (expected==0)
    dual_high = high & (expected==100)
    dropout = df['Sensor_Dropout'].to_numpy()[2:].astype(bool)
    # DAQ_Write uses MATLAB round on a non-negative percentage, then sends one unsigned byte.
    # These are reconstructed serial values, not observed motor voltage measurements.
    serial_byte = np.floor(255*u/100+0.5).astype(int)
    coverage = dict(member_v2=name,sha256_v2=digest(data),member_v1=old_name,sha256_v1=old_sha,
                    unchanged_eight_fields_float64_sha256=key,removed_v1_empty_rows=empty,
                    recorded_rows=len(df),adaptive_rows=len(expected),distinct_exported_timestamps=df['Timestamp'].nunique(),
                    nominal_time_last_s=int(df.Time_s.iloc[-1]),flagged_dropout_rows=int(df.Sensor_Dropout.sum()),
                    logged_zero_rows=int(sum(u==0)),logged_full_rows=int(sum(u==100)),
                    host_formula_byte_zero=int(sum(serial_byte==0)),host_formula_byte_255=int(sum(serial_byte==255)),
                    positive_command_rounds_to_byte_zero=int(sum((u>0)&(serial_byte==0))),
                    below_100_command_rounds_to_byte_255=int(sum((u<100)&(serial_byte==255))))
    result = dict(member=name,adaptive_rows=len(expected),
                  startup_max_abs_clipped_residual_pct_points=f'{max(abs(np.clip(startup,0,100)-u[:2])):.8g}',
                  gains_clipped_residual_max_pct_points=f'{max(g_resid):.8g}',
                  model_clipped_residual_max_pct_points=f'{max(m_resid):.8g}',
                  gains_clipped_residual_gt_0p01=int(sum(g_resid>tol)),
                  model_clipped_residual_gt_0p01=int(sum(m_resid>tol)),
                  dual_replay_low_and_logged_zero=int(dual_low.sum()),
                  dual_replay_high_and_logged_100=int(dual_high.sum()),
                  logged_zero_other=int(sum(expected==0)-dual_low.sum()),
                  logged_100_other=int(sum(expected==100)-dual_high.sum()),
                  dual_low_while_logged_above_0=int(sum(low & (expected>0))),
                  dual_high_while_logged_below_100=int(sum(high & (expected<100))),
                  high_and_sensor_dropout_same_step=int(sum(dual_high & dropout)),
                  low_and_sensor_dropout_same_step=int(sum(dual_low & dropout)),
                  gain_request_min_pct=f'{min(gain_request):.7f}',gain_request_max_pct=f'{max(gain_request):.7f}')
    return coverage,result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ('old','new','out'):
        parser.add_argument(arg,type=Path)
    a=parser.parse_args()
    with ZipFile(a.old) as v1, ZipFile(a.new) as v2:
        index=old_index(v1)
        runs=[run(n,v2.read(n),index) for n in sorted(v2.namelist()) if n.endswith('.csv') and '/__MACOSX/' not in n]
    if len(runs)!=25 or index:
        raise ValueError('release matching was not one-to-one')
    a.out.mkdir(parents=True,exist_ok=True)
    write(a.out/'two-tank-files.csv',[x[0] for x in runs])
    write(a.out/'two-tank-reconstruction.csv',[x[1] for x in runs])


if __name__=='__main__':
    main()
