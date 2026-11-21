"""Audit each axis in the DaRUS five-axis release and independently recompute Cartesian error."""
import argparse
import numpy as np
import pandas as pd
from dataverse_servo import verified, write_table
from pathlib import Path


def rms(values):
    return np.sqrt(np.mean(values**2))


def main(root, out):
    axes, norms, observer = [], [], []
    for name, group, path in verified(root, 6114):
        if not name.endswith('.csv'):
            continue
        d = pd.read_csv(path)
        if name == 'ObserverTestSet.csv':
            delta = 1e6 * (d.x_des - d.x_act).to_numpy()
            observer.append(dict(file=name,rows=len(d),position_rmse_um=rms(delta),
                                 absolute_position_error_p99_um=np.percentile(abs(delta),99),
                                 maximum_absolute_position_error_um=max(abs(delta))))
            continue
        # Mixed ISO-8601 formats occur when a whole-second timestamp omits fractions.
        ticks = pd.to_datetime(d.t, format='mixed', utc=True).to_numpy(dtype='datetime64[ns]').astype('int64')
        assert (np.diff(ticks) > 0).all() and len(np.unique(d.id)) == 1
        common = dict(directory=group,file=name,record_id=int(d.id.iloc[0]),rows=len(d),
                      median_dt_us=np.median(np.diff(ticks))/1000,largest_dt_us=max(np.diff(ticks))/1000)
        squares = np.zeros(len(d))
        for axis in 'xyzbc':
            des, load, motor, torque, vdes, vadd = (d[f'{axis}_{q}'].to_numpy()
                for q in ('x_d','x_l','x_m','tau_m','v_d','v_d_add'))
            assert np.isfinite(np.array([des,load,motor,torque,vdes,vadd])).all()
            unit = 'um' if axis in 'xyz' else 'urad'
            error = 1e6 * (des - load)
            axes.append(dict(**common,axis=axis,position_metric_unit=unit,
                             desired_load_rmse=rms(error),desired_motor_rmse=1e6*rms(des-motor),
                             motor_load_rmse=1e6*rms(motor-load),desired_load_peak_abs=max(abs(error)),
                             motor_torque_min_Nm=np.min(torque),motor_torque_max_Nm=np.max(torque),
                             velocity_command_unit='m/s' if axis in 'xyz' else 'rad/s',
                             nominal_command_velocity_absmax=max(abs(vdes)),additive_command_velocity_absmax=max(abs(vadd))))
            if axis in 'xyz':
                squares += error**2
        if 'e_3d' in d:
            reconstructed = np.sqrt(squares)
            published = d.e_3d.to_numpy()*1e6
            diff = np.abs(reconstructed-published)
            norms.append(dict(**common,stored_rms_um=rms(published),recomputed_rms_um=rms(reconstructed),
                              max_abs_disagreement_um=max(diff),rows_disagreeing_over_1_nm=int(sum(diff>0.001))))
    for filename, rows in [('five-axis-channel-audit.csv',axes),('five-axis-norm-check.csv',norms),
                            ('five-axis-observer-set.csv',observer)]:
        write_table(out/filename,rows)


if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('input',type=Path); p.add_argument('output',type=Path)
    args=p.parse_args(); main(args.input,args.output)
