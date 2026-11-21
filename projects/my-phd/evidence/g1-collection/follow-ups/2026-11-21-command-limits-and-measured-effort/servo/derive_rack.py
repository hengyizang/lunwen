"""Compare separate motor and slide readouts on author-indexed gain schedules."""
import argparse
from pathlib import Path
import numpy as np
import pandas as pd
from dataverse_servo import verified,write_table


def rms(x):
    return float(np.sqrt(np.mean(np.square(x))))


def main(root,out):
    files={n:p for n,_,p in verified(root,6333)}
    fig2=pd.read_csv(files['figure2_data.csv'])
    pos=fig2.TE_x_S.to_numpy()
    if not np.all(np.diff(pos)>0):raise ValueError('Non-monotone lookup table')
    width=(fig2.TE_plus-fig2.TE_minus)*1e6
    envelope=[dict(grid_points=len(pos),position_min_m=pos[0],position_max_m=pos[-1],
                   width_min_um=width.min(),width_median_um=width.median(),width_max_um=width.max(),
                   inverted_raw_widths=int((width<0).sum()),inverted_adjusted_widths=int((width<20).sum()))]
    runs=[]; pairs=[]
    for fig in (3,5):
        df=pd.read_csv(files[f'figure{fig}_data.csv'])
        groups={int(i):v.reset_index(drop=True) for i,v in df.groupby('meas_idx')}
        for i,v in groups.items():
            desired,slide,motor=v.x_Sdes.to_numpy(),v.x_S.to_numpy(),v.x_M.to_numpy()
            in_grid=(slide>=pos[0]) & (slide<=pos[-1])
            # Published figure offsets narrow the band by 10 um on each side.
            upper=np.interp(slide,pos,fig2.TE_plus)
            lower=np.interp(slide,pos,fig2.TE_minus)
            delta=motor-slide
            masked=in_grid & ((upper-lower)>=20e-6)
            runs.append(dict(figure=fig,trace=i,rows=len(v),time_s=v.time.iloc[-1]-v.time.iloc[0],
                             non_0p5ms_intervals=int(np.count_nonzero(np.abs(np.diff(v.time)-0.0005)>1e-9)),
                             desired_slide_rms_um=rms(desired-slide)*1e6,desired_motor_rms_um=rms(desired-motor)*1e6,
                             motor_minus_slide_p01_um=np.quantile(delta,.01)*1e6,motor_minus_slide_p99_um=np.quantile(delta,.99)*1e6,
                             max_abs_slide_error_um=np.max(np.abs(desired-slide))*1e6,
                             on_grid_rows=int(in_grid.sum()),outside_raw_band=int(np.sum(in_grid & ((delta<lower)|(delta>upper)))),
                             valid_adjusted_band_rows=int(masked.sum()),outside_adjusted_band=int(np.sum(masked & ((delta<lower+1e-5)|(delta>upper-1e-5)))),
                             gain_nonbaseline_rows=int(np.sum(v.K_v!=20)) if fig==5 else '',
                             gain_max_per_s=v.K_v.max() if fig==5 else ''))
        if fig==5:
            for on in (1,3,5,7):
                a,b=groups[on],groups[on+1]
                n=min(len(a),len(b));a,b=a.iloc[:n],b.iloc[:n]
                if not np.array_equal(a.time,b.time):raise ValueError('Unmatched time grid')
                ea=(a.x_Sdes-a.x_S).to_numpy()*1e6;eb=(b.x_Sdes-b.x_S).to_numpy()*1e6
                # Crop long stationary tails equally, using the commanded position only.
                moving=(np.abs(np.gradient(a.x_Sdes.to_numpy(),0.0005))>.001)&(np.abs(np.gradient(b.x_Sdes.to_numpy(),0.0005))>.001)
                pairs.append(dict(figure=5,on_index=on,off_index=on+1,peak_commanded_acceleration_m_per_s2=.7 if on<5 else 1.,
                                  common_rows=n,max_abs_reference_difference_um=np.max(np.abs(a.x_Sdes-b.x_Sdes))*1e6,
                                  moving_rows=int(moving.sum()),on_moving_rms_um=rms(ea[moving]),off_moving_rms_um=rms(eb[moving]),
                                  on_moving_peak_um=np.max(np.abs(ea[moving])),off_moving_peak_um=np.max(np.abs(eb[moving])),
                                  on_common_rms_um=rms(ea),off_common_rms_um=rms(eb)))
    for name,data in [('rack-transmission-map',envelope),('rack-tracking-runs',runs),('rack-gain-pairs',pairs)]:
        write_table(out/(name+'.csv'),data)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('root',type=Path);p.add_argument('out',type=Path)
    args=p.parse_args();main(args.root,args.out)
