"""Recompute final force labels and characterize correction size on all DigiTac contacts.

Run: python derive_digitac.py samples.csv OUT
Requires NumPy and pandas. All torques in the source are bias-subtracted only.
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd


def up_in_tool(roll, pitch):
    """R.T @ [0,0,1]; R = Rz(yaw) Ry(pitch) Rx(roll)."""
    return np.column_stack((-np.sin(pitch), np.cos(pitch)*np.sin(roll),
                            np.cos(pitch)*np.cos(roll)))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('samples',type=Path)
    parser.add_argument('out',type=Path)
    args=parser.parse_args()
    df=pd.read_csv(args.samples)
    assert len(df)==10000 and not df[['seed','pose_number']].duplicated().any()
    assert not df.isna().any().any() and df.image.is_unique
    assert df.groupby('seed').size().eq(250).all() and df.seed.nunique()==40
    force=df[['f_x','f_y','f_z']].to_numpy()
    labels=df[['fc_x','fc_y','fc_z']].to_numpy()
    up=up_in_tool(df.roll,df.pitch)
    pre=up_in_tool(df.roll_pre,df.pitch_pre)
    correction=.087*9.81*(up-pre)
    reconstruction=force+correction
    df['force_label_max_abs_residual_N']=np.abs(reconstruction-labels).max(axis=1)
    df['correction_norm_N']=np.linalg.norm(correction,axis=1)
    df['correction_largest_axis_N']=np.abs(correction).max(axis=1)
    df['force_plate_normal_N']=np.einsum('ij,ij->i',up,labels)
    parallel=labels-up*df.force_plate_normal_N.to_numpy()[:,None]
    df['force_plate_tangent_norm_N']=np.linalg.norm(parallel,axis=1)
    df['attained_z_group']=np.where(df.p_z<0,'below_zero','at_or_above_zero')
    args.out.mkdir(exist_ok=True,parents=True)
    for name,keys in [('digitac-session-corrections',['batch','sensor','seed']),
                      ('digitac-load-support',['batch','attained_z_group'])]:
        rows=[]
        for group,x in df.groupby(keys,sort=True):
            row=dict(zip(keys,group))
            row.update(samples=len(x),flagged_torn_images=int(x.image_torn.sum()),min_attained_z_mm=x.p_z.min(),
                       max_attained_z_mm=x.p_z.max(),median_correction_norm_N=x.correction_norm_N.median(),
                       p95_correction_norm_N=x.correction_norm_N.quantile(.95),max_correction_norm_N=x.correction_norm_N.max(),
                       rows_any_axis_correction_over_one_resolution=(x.correction_largest_axis_N>1/16).sum(),
                       max_abs_reconstructed_label_error_N=x.force_label_max_abs_residual_N.max(),
                       median_force_plate_normal_N=x.force_plate_normal_N.median(),p95_force_plate_normal_N=x.force_plate_normal_N.quantile(.95),
                       median_tangential_force_norm_N=x.force_plate_tangent_norm_N.median(),p95_tangential_force_norm_N=x.force_plate_tangent_norm_N.quantile(.95))
            rows.append(row)
        pd.DataFrame(rows).to_csv(args.out/(name+'.csv'),index=False,lineterminator='\n',float_format='%.9g')


if __name__=='__main__':
    main()
