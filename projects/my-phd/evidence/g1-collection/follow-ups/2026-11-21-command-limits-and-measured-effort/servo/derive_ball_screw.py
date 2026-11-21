"""Audit the request, inverter, independent table and nut-force records on a ball screw bench."""
import argparse
from pathlib import Path
import h5py
import numpy as np
import pandas as pd
from dataverse_servo import verified, write_table


def rms(x):
    return np.sqrt(np.mean(x**2))


def aligned(path):
    required={'u_motor [rot]','M_KGT_act','x_meas_motor','x_meas_table','v_meas_motor',
              'v_meas_table','v_ref','traj_KGT[0]','traj_KGT[1]','F_des_LDD','F_nut_sum','lastError','sigEnable'}
    with h5py.File(path) as h:
        g=h[next(k for k in h if not k.startswith('#'))]
        xs=[h[ref[0]][()].ravel() for ref in g['X/Data']]
        d={}; t=xs[0]; worst=0
        for field,ref,ix in zip(g['Y/Name'],g['Y/Data'],g['Y/XIndex']):
            key=''.join(map(chr,h[field[0]][()].ravel()))
            if key not in required and not key.startswith('F_nut_'):
                continue
            grid=xs[int(h[ix[0]][()].ravel()[0])-1]
            series=h[ref[0]][()].ravel()
            assert len(grid)==len(series) and np.isfinite(series).all() and np.all(np.diff(grid)>0)
            j=np.searchsorted(grid,t).clip(0,len(grid)-1)
            left=(j-1).clip(0,len(grid)-1)
            j=np.where(abs(grid[left]-t)<abs(grid[j]-t),left,j)
            discrepancy=max(abs(grid[j]-t))
            if discrepancy>0.0001251:
                raise ValueError(f'Unpaired signal {key} ({discrepancy} s)')
            worst=max(worst,discrepancy)
            d[key]=series[j]
        assert (required-{'F_nut_sum'})<=d.keys()
    return t,d,worst


def prbs(path):
    d=pd.read_csv(path,sep=';',decimal=',').to_numpy()
    t,u,y=d.T; dt=np.median(np.diff(t)); assert np.allclose(np.diff(t),dt)
    mid=len(y)//2
    def design(k,lag):
        return np.stack([y[k-1],u[k-lag],np.ones(len(k))],axis=1)
    train=np.arange(16,mid); test=np.arange(mid,len(y))
    fits=[]
    for delay in range(17):
        a=design(train,delay); coef=np.linalg.lstsq(a,y[train],rcond=None)[0]
        fits.append((rms(a@coef-y[train]),delay,coef))
    train_error,delay,coef=min(fits,key=lambda fit:fit[0])
    return dict(samples=len(y),dt_ms=dt,train_fit_rows=len(train),test_rows=len(test),
                request_low_N=min(u),request_high_N=max(u),actual_min_N=min(y),actual_max_N=max(y),
                rows_actual_abs_above_request_envelope=int(sum(abs(y)>max(abs(u)))),
                selected_input_lag_samples=delay,output_ar1=coef[0],input_gain=coef[1],intercept_N=coef[2],
                train_one_step_rmse_N=train_error,test_one_step_rmse_N=rms(design(test,delay)@coef-y[test]),
                persistence_test_one_step_rmse_N=rms(y[test]-y[test-1]))


def main(root,out,n):
    runs=[];maps=[];raw_map={};interlocks=[]
    for name,folder,path in verified(root,n):
        if name.endswith('.csv') and n==2563:
            write_table(out/'direct-drive-prbs.csv',[prbs(path)])
        if not name.endswith('.mat'):
            continue
        t,d,worst=aligned(path)
        qref=d['traj_KGT[0]']; qmotor=d['x_meas_motor']; qtable=d['x_meas_table']
        u=d['u_motor [rot]']; torque=d['M_KGT_act']; f=d.get('F_nut_sum')
        row=dict(folder=folder,file=name,matched_grid_rows=len(t),median_grid_dt_ms=1e3*np.median(np.diff(t)),
                 max_matched_clock_difference_us=worst*1e6,
                 table_ref_position_rmse_um=1e6*rms(qref-qtable),motor_table_position_rmse_um=1e6*rms(qmotor-qtable),
                 motor_commanded_torque_min_Nm=min(u),motor_commanded_torque_max_Nm=max(u),
                 inverter_torque_min_Nm=min(torque),inverter_torque_max_Nm=max(torque),
                 command_inverter_torque_rmse_Nm=rms(u-torque),disturbance_command_min_N=min(d['F_des_LDD']),
                 disturbance_command_max_N=max(d['F_des_LDD']),nut_force_min_N=min(f) if f is not None else '',
                 nut_force_max_N=max(f) if f is not None else '',nut_force_rms_N=rms(f) if f is not None else '',
                 motor_velocity_request_rmse_mm_s=1000*rms(d['v_ref']-d['v_meas_motor']),
                 table_velocity_request_rmse_mm_s=1000*rms(d['v_ref']-d['v_meas_table']),
                 motor_table_velocity_rmse_mm_s=1000*rms(d['v_meas_motor']-d['v_meas_table']))
        if n==2563:
            vals=[d.get(f'F_nut_{i}') for i in range(1,5)]
            row['max_abs_component_sum_difference_N']=max(abs(sum(vals)-f)) if all(v is not None for v in vals) else ''
            if name.startswith('SP_'):
                speed=int(name.split('_')[1][1:]);direction=name.split('_')[2].split('.')[0]
                keep=(abs(abs(d['traj_KGT[1]'])-speed/1000)<speed/100000)&(qref>=0.02)&(qref<0.70)
                bins=np.floor(qref[keep]*100).astype(int)
                binned={int(b):np.median(f[keep][bins==b]) for b in np.unique(bins)}
                raw_map[direction,speed]=binned
        elif n==3109:
            enable=d['sigEnable'];code=d['lastError']
            row['disabled_rows']=int(sum(enable==0))
            row['nonzero_error_rows']=int(sum(code!=0))
            for j in np.where((enable[1:]==0)&(enable[:-1]==1))[0]+1:
                after=np.arange(j,len(t))
                next_enable=np.where(enable[after]!=0)[0]
                if len(next_enable):
                    after=after[:next_enable[0]]
                before=np.arange(max(0,j-10),j)
                interlocks.append(dict(folder=folder,file=name,event_row_zero_based=int(j),
                    event_time_s=t[j],prior_code=code[j-1],event_code=code[j],
                    disabled_rows=len(after),prior_10ms_command_mean_Nm=u[before].mean(),
                    first_disabled_command_Nm=u[j],last_disabled_command_Nm=u[after[-1]],
                    disabled_command_range_Nm=np.ptp(u[after]),first_disabled_inverter_Nm=torque[j],
                    last_disabled_inverter_Nm=torque[after[-1]],disabled_inverter_absmax_Nm=max(abs(torque[after])),
                    disabled_table_start_m=qtable[j],disabled_table_end_m=qtable[after[-1]],
                    disabled_table_span_mm=1000*np.ptp(qtable[after]),
                    nut_force_min_N=min(f) if f is not None else '',nut_force_max_N=max(f) if f is not None else '',
                    nut_min_rows=int(sum(f==min(f))) if f is not None else '',nut_max_rows=int(sum(f==max(f))) if f is not None else ''))
        runs.append(row)
    prefix='ball-screw-force-compensation' if n==2563 else 'ball-screw-pi-velocity'
    write_table(out/(prefix+'-runs.csv'),runs)
    if n==3109:
        write_table(out/'ball-screw-disable-events.csv',interlocks)
    if n==2563:
        for (direction,speed),target in sorted(raw_map.items()):
            peers=[other for (dr,sp),other in raw_map.items() if dr==direction and sp!=speed]
            common=sorted(set(target).intersection(*(set(p) for p in peers)))
            actual=np.array([target[b] for b in common])
            train=np.array([[p[b] for b in common] for p in peers])
            pred=np.median(train,axis=0)
            maps.append(dict(direction=direction,heldout_speed_mm_s=speed,training_runs=len(peers),bins=len(common),
                             bin_median_force_map_test_rmse_N=rms(pred-actual),
                             position_independent_training_median_test_rmse_N=rms(np.median(train)-actual)))
        write_table(out/'ball-screw-spatial-force-holdout.csv',maps)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('input',type=Path); p.add_argument('output',type=Path)
    p.add_argument('release',type=int,choices=(2563,3109))
    args=p.parse_args(); main(args.input,args.output,args.release)
