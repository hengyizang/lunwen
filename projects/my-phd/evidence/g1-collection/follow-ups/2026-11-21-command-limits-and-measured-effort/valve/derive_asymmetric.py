"""Audit voltage endpoints and measured motion of the three public cylinder experiments.

Usage: python derive_asymmetric.py PATH_CONTAINING_ORIGINAL_CSVS OUT
Requires NumPy and pandas. Each controller is a separately acquired trace on the
published experiment grid; no between-controller difference is a same-event measurement.
"""
from pathlib import Path
import argparse
import numpy as np
import pandas as pd


def episodes(mask):
    changes = np.diff(np.r_[False, mask, False].astype(int))
    return list(zip(np.where(changes == 1)[0], np.where(changes == -1)[0]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('out', type=Path)
    args = parser.parse_args()
    args.out.mkdir(exist_ok=True, parents=True)
    runs, plateaus = [], []
    for exp, filename in enumerate(['exp1_sinusoidal.csv','exp2_step.csv','exp3_full_stroke.csv'], 1):
        df = pd.read_csv(args.input / filename)
        time = df.iloc[:,0].to_numpy()
        assert np.allclose(np.diff(time), .02, atol=1e-8, rtol=0)
        target = df.iloc[:,1].to_numpy()
        variants = [
            [('PSO-PID','PID_Act_mm',None,'PID_Err_mm'),('MPC-DOB','DOB_Act_mm',None,'DOB_Err_mm'),('MPC-RBF','RRRBF_Act_mm',None,'RRRBF_Err_mm')],
            [('PSO-PID','PID_Pos_mm','PID_Vol_V','PID_h'),('MPC-RBF','MPCRBF_Pos_mm','MPCRBF_Vol_V','MPCRBF_h'),('RBF-MPC-CBF','CBF_Pos_mm','CBF_Vol_V','CBF_h')],
            [('PSO-PID','Pos_PID','Vol_PID','Time_PID'),('MPC-RBF','Pos_MPC','Vol_MPC','Time_MPC'),('RBF-MPC-CBF','Pos_CBF','Vol_CBF','Time_CBF')]
        ][exp-1]
        for method, poscol, voltcol, auxcol in variants:
            pos = df[poscol].to_numpy()
            extra = df[auxcol].to_numpy()
            err = target - pos
            row = dict(experiment=exp, controller=method, rows=len(df), sample_period_s=.02,
                       min_position_mm=pos.min(), max_position_mm=pos.max(), rmse_mm=np.sqrt(np.mean(err**2)),
                       peak_abs_error_mm=np.abs(err).max(), over_105mm_observations=int((pos>105).sum()),
                       over_104_4mm_observations=int((pos>104.4).sum()))
            if exp == 1:row['published_error_disagreement_max_mm']=np.abs(extra-err).max()
            if exp == 2:row['published_margin_disagreement_max_mm']=np.abs(extra-(df.Safety_Limit_mm-pos)).max()
            if exp == 3:
                row['compute_times_zero']=int((extra==0).sum())
                row['compute_times_over_20ms']=int((extra>20).sum())
                row['compute_time_peak_ms']=extra.max()
            if voltcol:
                voltage=df[voltcol].to_numpy()
                row['voltage_outside_documented_limits']=int((np.abs(voltage)>6.5+1e-9).sum())
                for polarity, level in [('low',-6.5),('high',6.5)]:
                    mask=np.isclose(voltage,level,atol=1e-9,rtol=0)
                    spans=episodes(mask)
                    row[polarity+'_limit_rows']=int(mask.sum())
                    row[polarity+'_episodes']=len(spans)
                    for start,end in spans:
                        plateaus.append(dict(experiment=exp,controller=method,voltage_v=level,start_s=time[start],
                                             end_sample_s=time[end-1],samples=end-start,
                                             first_position_mm=pos[start],last_position_mm=pos[end-1],
                                             position_span_mm=np.ptp(pos[start:end]),
                                             position_change_within_span_mm=pos[end-1]-pos[start]))
            runs.append(row)
    for name, values in [('asymmetric-controller-traces',runs),('asymmetric-voltage-plateaus',plateaus)]:
        pd.DataFrame(values).to_csv(args.out/(name+'.csv'),index=False,float_format='%.9g',lineterminator='\n')


if __name__ == '__main__':
    main()
