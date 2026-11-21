"""Audit recorded tendon-bench inputs, displacement and replay. Usage: python derive_tendon.py CHECKOUT OUT."""
import hashlib
from pathlib import Path
import sys
import numpy as np
import pandas as pd


def main(root, out):
    rows, files = [], []
    def read(path):
        p=root/path
        df=pd.read_csv(p)
        files.append(dict(path=str(path), bytes=p.stat().st_size, sha256=hashlib.sha256(p.read_bytes()).hexdigest(), rows=len(df)))
        return df
    train=Path("controllers/g2p-closed-loop/datasets")
    for p in sorted((root/train).glob("*_dirty.csv")):
        d=read(p.relative_to(root))
        ticks=d.tick.to_numpy()
        for side in ["flex", "extend"]:
            prefix=side+"_myobrick_"
            pwm=d[prefix+"pwm"].to_numpy()
            disp=d[prefix+"torque_encoder"].to_numpy()
            pos=d[prefix+"pos_encoder"].to_numpy()
            run=d[prefix+"in_running_state"].to_numpy()
            assert run.dtype==bool and np.isfinite(pwm).all()
            mask=run[:-1] & run[1:] & (np.diff(ticks)==1) & (pwm[:-1]!=0)
            rows.append(dict(file=p.name,side=side,tick_first=ticks[0],tick_last=ticks[-1],rows=len(d),
                nonconsecutive_steps=(np.diff(ticks)!=1).sum(), running_samples=run.sum(), stopped_samples=(~run).sum(),
                nonzero_requested_pwm=(pwm!=0).sum(),stopped_with_nonzero_requested_pwm=((~run)&(pwm!=0)).sum(),
                safety_pressed_with_nonzero_requested_pwm=(d.safety_switch_pressed&(pwm!=0)).sum(),
                requested_pwm_min=pwm.min(), requested_pwm_max=pwm.max(),
                displacement_min_raw=disp.min(),displacement_max_raw=disp.max(),
                running_nonzero_pwm_pairs=mask.sum(),unchanged_next_displacement=(mask&(np.diff(disp)==0)).sum(),
                unchanged_next_displacement_and_motor_position=(mask&(np.diff(disp)==0)&(np.diff(pos)==0)).sum()))
    original=read(Path("evaluator/eval_paths/validation_run.csv"))
    base=Path("evaluator/outputs/validation_run")
    way=read(base/"2023-02-02_17-06-54_waypoints.csv")
    actual=read(base/"2023-02-02_17-06-54_bench_states.csv")
    cols=[c for c in original if c!="timestamp"]
    assert np.array_equal(original[cols].values,way[cols].values)
    a=actual.timestamp.to_numpy()
    t=way.timestamp.to_numpy()
    assert np.all(np.diff(a)>0) and np.all(np.diff(t)>0)
    common=(a>=t[0])&(a<=t[-1])
    use=a[common]
    left=np.searchsorted(t,use,side="right")-1
    summary=[]
    for method, target in [("linear_interpolation",np.interp(use,t,way.angle)),
                            ("previous_waypoint",way.angle.to_numpy()[left])]:
        err=actual.angle.to_numpy()[common]-target
        shift=(t-t[0])-(original.timestamp-original.timestamp.iloc[0])
        summary.append(dict(target_alignment=method, waypoints=len(t), measured_states=len(a),
            overlapping_states=len(use), outside_target_interval=(~common).sum(), overlap_span_s=use[-1]-use[0],
            fields_equal_in_released_and_sent_waypoints=len(cols),max_residual_after_timestamp_rebase_s=np.max(abs(shift)),
            actual_minus_target_bias_sensor_units=err.mean(), mae_sensor_units=np.mean(abs(err)),
            rmse_sensor_units=np.sqrt(np.mean(err**2)),max_abs_error_sensor_units=np.max(abs(err))))
    for name, rr in [("tendon-input-audit",rows),("tendon-validation",summary),("tendon-files",files)]:
        pd.DataFrame(rr).to_csv(out/(name+".csv"),index=False,float_format="%.9g",lineterminator="\n")


if __name__=="__main__":
    main(Path(sys.argv[1]),Path(sys.argv[2]))
