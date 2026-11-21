"""Audit speed-dependent clipping and torque-map agreement in RWTH's release.
Usage: python rwth-ipm.py RAW_DIR OUTPUT_DIR (numpy and scipy).
"""
import csv
import hashlib
import sys
from pathlib import Path

import numpy as np
from scipy.interpolate import RegularGridInterpolator
from scipy.io import loadmat

raw, out = map(Path, sys.argv[1:])
out.mkdir(parents=True, exist_ok=True)
def read(name, expected):
    path = raw / name
    assert hashlib.md5(path.read_bytes()).hexdigest() == expected
    return loadmat(path, squeeze_me=True)

meas = read('dq_Flux_Torque_500Arms.mat', '82b5bc67bae547be8604671069d879d6')
torque = RegularGridInterpolator((meas['iq_vec'], meas['id_vec']),
                                  meas['IdIq_Tem_POS_grid_plot'],
                                  bounds_error=False, fill_value=np.nan)
modes = [('SPWM', '0.8', 'bb8e819c77e7797460a49adae7af3859'),
         ('SVPWM', '0.924', '0a7623ecad4b12772e5399e93daff433')]
cols = ['method', 'n_rpm','torque_lower_Nm','torque_upper_Nm','abs_motoring_limit_kW',
        'requests_total','requests_outside_limits','finite_current_points',
        'finite_interpolated_torque_points','outside_with_finite_current',
        'within_with_valid_torque','outside_with_valid_torque','max_dq_norm_A',
        'within_requested_torque_rmse_Nm','outside_requested_torque_rmse_Nm',
        'outside_clipped_torque_rmse_Nm']
def rmse(valid, e):
    return f'{np.sqrt(np.mean(e[valid] ** 2)):.6f}' if valid.any() else ''

with (out / 'rwth-ipm-envelope.csv').open('w', newline='') as f:
    w = csv.writer(f, lineterminator='\n')
    w.writerow(cols)
    for mode, mod, checksum in modes:
        ref = read(f'SetpointLUT_m{mod}_500Arms.mat', checksum)
        target = ref['T_vec'].astype(float)
        for j, n in enumerate(ref['n_vec']):
            lo, hi = ref['n_Tmin_grid'][j], ref['n_Tmax_grid'][j]
            id_, iq = ref['nT_id_grid'][:, j], ref['nT_iq_grid'][:, j]
            estimate = torque(np.column_stack([iq, id_]))
            finite = np.isfinite(iq) & np.isfinite(id_)
            valid = np.isfinite(estimate)
            outside = (target < lo) | (target > hi)
            within_ok, outside_ok = ~outside & valid, outside & valid
            err = estimate - target
            w.writerow([mode, n,f'{lo:.6f}',f'{hi:.6f}',f'{hi*n*np.pi/30000:.6f}',
                        len(target),int(outside.sum()),int(finite.sum()),int(valid.sum()),
                        int((outside & finite).sum()),int(within_ok.sum()),int(outside_ok.sum()),
                        f'{np.nanmax(np.hypot(id_, iq)):.6f}',rmse(within_ok,err),
                        rmse(outside_ok,err),rmse(outside_ok,estimate-np.clip(target,lo,hi))])
