"""Recompute nominal one-minute winding-temperature changes, keeping whole profiles out.
Usage: python derive_motor_thermal.py kaggle_v3_download.zip OUTPUT_DIRECTORY
Requires numpy and pandas. The test-window current and speed are measured inputs;
this is a conditional change estimate, not a forecast of the future inputs.
"""
import argparse
from pathlib import Path
from zipfile import ZipFile
import numpy as np
import pandas as pd


def windows(profile):
    n=len(profile)
    start=np.arange(0,n-120,120)
    end=start+120
    id_=profile.i_d.to_numpy()
    iq=profile.i_q.to_numpy()
    speed=profile.motor_speed.to_numpy()
    winding=profile.stator_winding.to_numpy()
    current_squared=(id_/100)**2+(iq/100)**2
    def block_mean(v):
        return v[:len(start)*120].reshape(-1,120).mean(axis=1)
    x=np.column_stack((np.ones(len(start)),block_mean(current_squared),
                       block_mean(np.abs(speed)/1000),
                       (profile.coolant.to_numpy()[start]-winding[start])/20,
                       (profile.stator_yoke.to_numpy()[start]-winding[start])/20))
    return x,winding[end]-winding[start]


def output_csv(path,rows):
    pd.DataFrame(rows).to_csv(path,index=False,float_format='%.9f',lineterminator='\n')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('archive',type=Path)
    p.add_argument('out',type=Path)
    a=p.parse_args()
    a.out.mkdir(exist_ok=True,parents=True)
    with ZipFile(a.archive) as z, z.open('measures_v2.csv') as f:
        frame=pd.read_csv(f)
    if not np.isfinite(frame.to_numpy()).all():
        raise ValueError('Nonfinite data in the fixed release')
    runs=frame.profile_id.ne(frame.profile_id.shift()).sum()
    if runs!=frame.profile_id.nunique():
        raise ValueError('Disjoint profile blocks')
    summaries=[]
    pieces=[]
    for pid,group in frame.groupby('profile_id',sort=True):
        x,y=windows(group)
        pieces.append((pid,x,y))
        summaries.append(dict(profile_id=pid,rows=len(group),minute_changes=len(y),
            first_winding_C=group.stator_winding.iloc[0], min_winding_C=group.stator_winding.min(),
            max_winding_C=group.stator_winding.max(),min_pm_C=group.pm.min(),max_pm_C=group.pm.max(),
            min_coolant_C=group.coolant.min(),max_coolant_C=group.coolant.max(),
            min_speed_rpm=group.motor_speed.min(),max_speed_rpm=group.motor_speed.max(),
            min_torque_release_nm=group.torque.min(),max_torque_release_nm=group.torque.max(),
            max_dq_current_norm_a=np.hypot(group.i_d,group.i_q).max(),
            min_60s_winding_change_C=y.min(),max_60s_winding_change_C=y.max()))
    output_csv(a.out/'motor-thermal-profiles.csv',summaries)
    scores=[]
    models={'persistence':0,'electrical_and_speed':3,'electrical_speed_and_initial_thermal_gradients':5}
    for held,x,y in pieces:
        trainx=np.concatenate([xt for pid,xt,_ in pieces if pid!=held])
        trainy=np.concatenate([yt for pid,_,yt in pieces if pid!=held])
        for label,k in models.items():
            if k:
                beta,_,rank,_=np.linalg.lstsq(trainx[:,:k],trainy,rcond=None)
                pred=x[:,:k]@beta
            else:
                pred=np.zeros(len(x))
                rank=0
            residual=pred-y
            scores.append(dict(heldout_profile=held,model=label,train_windows=len(trainy),
                test_windows=len(y),design_rank=rank,rmse_C=np.sqrt(np.mean(residual**2)),
                mae_C=np.mean(np.abs(residual)),sum_abs_error_C=np.abs(residual).sum(),
                sum_squared_error_C2=residual@residual))
    output_csv(a.out/'motor-thermal-profile-holdout.csv',scores)
    scores=pd.DataFrame(scores)
    totals=[]
    for name,group in scores.groupby('model',sort=True):
        n=group.test_windows.sum()
        totals.append(dict(model=name,heldout_profiles=len(group),test_windows=n,
            pooled_rmse_C=np.sqrt(group.sum_squared_error_C2.sum()/n),
            pooled_mae_C=group.sum_abs_error_C.sum()/n,
            median_profile_rmse_C=group.rmse_C.median()))
    output_csv(a.out/'motor-thermal-models.csv',totals)


if __name__=='__main__':
    main()
