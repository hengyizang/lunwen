"""Audit torque-command/ADC logs, archived copies and fixed-trial generalisation.
Usage: python derive_tmotor.py CHECKOUT OUT. Requires numpy and pandas.
"""
import csv
import hashlib
from pathlib import Path
import sys
import numpy as np
import pandas as pd


def design(data):
    current = data[:,4]/(.091*9)
    vel = data[:,5]
    shape = np.sign(vel)*abs(vel)/(.1+abs(vel))
    return np.column_stack((np.ones(len(data)), 9*.091*current, -9*abs(current)*current, -shape, -abs(current)*shape))


def main(root, out):
    base = root/"src/TMotorCANControl/test"
    mit_header=["loop_time","motor_torque_command","adc_measured_torque","motor_measured_torque","motor_measured_current","motor_measured_speed"]
    logs, final, comparisons, servo = [], {}, [], []
    plateaus=[]
    known={}
    canonical={}
    for folder in ["saved_logs","servo_can"]:
        for path in sorted((base/folder).rglob("*.csv")):
            with path.open(newline="") as f:
                rdr=csv.reader(f)
                head=next(rdr,[])
                if head!=mit_header and "Futek Torque (Nm)" not in head:
                    continue
                data=list(rdr)
            name=str(path.relative_to(root))
            digest=hashlib.sha256(path.read_bytes()).hexdigest()
            rep=known.setdefault(digest,name)
            # Preserve textual cells and header, ignoring CSV dialect and line endings.
            cell_hash=hashlib.sha256(("\x1f".join(head)+"\n"+"\n".join("\x1f".join(row) for row in data)).encode()).hexdigest()
            record=dict(file=name,sha256=digest,first_path_with_these_bytes=rep,
                        csv_cell_sha256=cell_hash,first_path_with_these_cells=canonical.setdefault(cell_hash,name),rows=len(data))
            if head==mit_header:
                widths={len(row) for row in data}
                assert widths.issubset({6,7})
                extra=[float(row[6]) for row in data if len(row)==7]
                a=np.array([row[:6] for row in data],float)
                assert np.isfinite(a).all()
                record.update(rows_with_extra_field=len(extra), extra_field_min=min(extra,default=np.nan), extra_field_max=max(extra,default=np.nan),
                    nonincreasing_time_steps=(np.diff(a[:,0])<=0).sum(), max_abs_command_Nm=np.max(abs(a[:,1])),
                    adc_min_as_logged_Nm=a[:,2].min(),adc_max_as_logged_Nm=a[:,2].max(),
                    controller_torque_min_Nm=a[:,3].min(),controller_torque_max_Nm=a[:,3].max())
                logs.append(record)
                if path.parent.name=="sys_ID_final":
                    final[path.name]=a[1:]
                    starts=np.flatnonzero(np.r_[True, np.diff(a[:,1])!=0, True])
                    for start,stop in zip(starts[:-1],starts[1:]):
                        size=stop-start
                        if size<5:
                            continue
                        # Last ceil(n/4) observations of each exact, repeated setpoint.
                        tail=a[stop-(size+3)//4:stop]
                        command=a[start,1]
                        plateaus.append(dict(file=path.name,first_row_zero_based=start,
                            plateau_rows=size,tail_rows=len(tail),command_Nm=command,
                            observed_duration_s=a[stop-1,0]-a[start,0],
                            median_tail_negated_adc_Nm=np.median(-tail[:,2]),
                            median_tail_controller_Nm=np.median(tail[:,3]),
                            tail_adc_minus_command_median_Nm=np.median(-tail[:,2]-command),
                            tail_adc_p10_Nm=np.quantile(-tail[:,2],.1),
                            tail_adc_p90_Nm=np.quantile(-tail[:,2],.9)))
            else:
                assert all(len(row)==len(head) for row in data)
                frame=pd.DataFrame(data,columns=head)
                required=["Futek Torque (Nm)","ADC Voltage (V)","velocity (Rad/S)","i_q","duty"]
                if "des velocity" in head:
                    required.append("des velocity")
                v=frame[required].apply(pd.to_numeric)
                assert np.isfinite(v.values).all()
                if len(v):
                    tare=v["ADC Voltage (V)"]-v["Futek Torque (Nm)"]/40
                    record.update(implied_tare_median_V=tare.median(),implied_tare_span_V=tare.max()-tare.min(),
                        futek_min_Nm=v["Futek Torque (Nm)"].min(),futek_max_Nm=v["Futek Torque (Nm)"].max(),
                        max_abs_logged_duty=v["duty"].abs().max(),max_abs_logged_iq_A=v["i_q"].abs().max(),
                        max_abs_readback_speed_rad_s=v["velocity (Rad/S)"].abs().max())
                    if "des velocity" in head:
                        err=v["velocity (Rad/S)"]-v["des velocity"]
                        record.update(max_abs_des_speed_rad_s=v["des velocity"].abs().max(),
                            speed_rmse_rad_s=np.sqrt(np.mean(err**2)))
                record["has_desired_speed"]="des velocity" in head
                servo.append(record)

    training=final["trial8.csv"]
    X=design(training)
    coeff,_,rank,_=np.linalg.lstsq(X,-training[:,2],rcond=None)
    assert rank==5
    for name,data in sorted(final.items()):
        target=-data[:,2]
        pred=design(data)@coeff
        err=pred-target
        comparisons.append(dict(fit_trial="trial8.csv",eval_trial=name,same_file_as_fit=name=="trial8.csv",
            evaluated_rows=len(err),model_absolute_mean_error_Nm=abs(err.mean()) if abs(err.mean())>1e-12 else 0.0,model_rmse_Nm=np.sqrt(np.mean(err**2)),
            model_mae_Nm=np.mean(abs(err)),controller_vs_negated_adc_rmse_Nm=np.sqrt(np.mean((data[:,3]-target)**2)),
            command_vs_negated_adc_rmse_Nm=np.sqrt(np.mean((data[:,1]-target)**2)),
            abs_cmd_above_training_max_count=(abs(data[:,1])>abs(training[:,1]).max()).sum(),
            abs_logged_current_above_training_max_count=(abs(data[:,4])>abs(training[:,4]).max()).sum()))
    for name, rows in [("tmotor-torque-files",logs),("tmotor-servo-files",servo),("tmotor-cross-trial",comparisons),("tmotor-plateaus",plateaus)]:
        pd.DataFrame(rows).to_csv(out/(name+".csv"),index=False,float_format="%.9g",lineterminator="\n")


if __name__=="__main__":
    main(Path(sys.argv[1]),Path(sys.argv[2]))
