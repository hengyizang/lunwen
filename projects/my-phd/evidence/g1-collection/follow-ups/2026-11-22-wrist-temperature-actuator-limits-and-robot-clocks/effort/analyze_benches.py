"""Produce per-file and per-class audits from downloaded, content-pinned releases."""
import argparse
import csv
import hashlib
import io
from pathlib import Path
from zipfile import ZipFile

import numpy as np
from openpyxl import load_workbook

def dump(path,rows):
    with path.open('w',newline='',encoding='utf8') as f:
        w=csv.DictWriter(f,list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)

def workbook(path,out):
    assert hashlib.sha256(path.read_bytes()).hexdigest()=='85203c4b3ad6fbdd05221e1be7fd41ce733376c0f316d7fd5542b604a6854605'
    w=load_workbook(path,read_only=True,data_only=True);summary=[];segments=[];prior={}
    for sh in w:
        if sh.title=='Description':
            continue
        header=None;rows=[];incomplete=0
        for row in sh.iter_rows(max_col=12,values_only=True):
            if row[0]=='time':
                header=row
            elif header and any(isinstance(v,(float,int)) for v in row):
                if all(isinstance(v,(float,int)) for v in row):rows.append(row)
                else:incomplete+=1
        assert header[-3:]==('MotorVoltage','MotorStatus','PWM')
        a=np.asarray(rows,dtype=float);assert np.isfinite(a).all()
        breaks=np.flatnonzero(np.diff(a[:,0])<=0)+1
        for seq,part in enumerate(np.split(a,breaks),1):
            digest=hashlib.sha256(part.astype('<f8').tobytes()).hexdigest()
            previous=prior.setdefault(digest,f'{sh.title}#{seq}')
            segments.append(dict(sheet=sh.title,ordinal=seq,complete_rows=len(part),t_start_us=int(part[0,0]),t_stop_us=int(part[-1,0]),elapsed_s=round((part[-1,0]-part[0,0])/1e6,6),sha256_of_12_columns_little_endian_float64=digest,first_identical_segment=previous))
        t,speed,current,v,status,pwm=a[:,[0,2,4,9,10,11]].T
        vabs=abs(v); maximum=pwm==255;zero=pwm==0
        assert np.isin(status,[0,1,2]).all() and ((pwm>=0)&(pwm<=255)).all()
        summary.append(dict(sheet=sh.title,complete_rows=len(a),incomplete_numeric_rows=incomplete,last_time_minus_first_time_s=round((t[-1]-t[0])/1e6,6),nonincreasing_t_samples=int(sum(np.diff(t)<=0)),median_step_us=np.median(np.diff(t)),pwm_zero=int(sum(zero)),pwm_255=int(sum(maximum)),brake_status_rows=int(sum(status==0)),pwm_zero_abs_terminal_V_median=(round(float(np.median(vabs[zero])),4) if zero.any() else ''),pwm_255_abs_terminal_V_median=(round(float(np.median(vabs[maximum])),4) if maximum.any() else ''),max_abs_terminal_V=vabs.max(),max_abs_current_A=abs(current).max(),max_abs_speed_rpm=abs(speed).max()))
    w.close();dump(out/'dc-sheets.csv',summary);dump(out/'dc-clock-segments.csv',segments)

def cycles(path,out):
    assert hashlib.md5(path.read_bytes()).hexdigest()=='bb2ec1590f44dc9214946345aa2250d7'
    result=[]
    with ZipFile(path) as z:
        assert z.testzip() is None
        names={f.lower():f for f in z.namelist()}
        for car in ['small','mid']:
            for cycle in ['artemis','bcdc','wltp']:
                arrays={};t=None
                for field,dirname,suffix in [('rpm','torque_speed_data','speed_rpm'),('torque','torque_speed_data','torque_nm'),('pin','measurement_results','input_power'),('pout','measurement_results','output_power')]:
                    filename=f'induction_motor/measurement_results/drive_cycle_{dirname}/{car}_sized_vehicle/{cycle}_{suffix}.csv'
                    data=np.loadtxt(io.BytesIO(z.read(names[filename])),delimiter=',',skiprows=1)
                    assert data.shape[1]==2 and np.isfinite(data).all()
                    if t is None:t=data[:,0]
                    else:assert np.array_equal(t,data[:,0])
                    arrays[field]=data[:,1]
                assert np.all(np.diff(t)>0)
                rpm,torque,pin,pout=arrays.values()
                pref=rpm*torque*(2*np.pi/60)
                # Compare the released power channel to the reference-based calculation, without inverting low speed.
                result.append(dict(vehicle=car,cycle=cycle,common_time_points=len(t),span_s=round(t[-1]-t[0],5),reference_torque_min_Nm=round(min(torque),5),reference_torque_max_Nm=round(max(torque),5),zero_reference_speed=int(sum(rpm==0)),negative_reference_torque=int(sum(torque<0)),max_abs_reference_power_W=round(max(abs(pref)),4),max_abs_released_output_power_W=round(max(abs(pout)),4),reference_vs_released_output_power_rmse_W=round(float(np.sqrt(np.mean((pref-pout)**2))),6),max_abs_difference_W=round(max(abs(pref-pout)),6),mean_electrical_input_minus_released_output_W=round(float(np.mean(pin-pout)),4)))
    dump(out/'im-drive-cycles.csv',result)

def classes(path,out):
    assert hashlib.md5(path.read_bytes()).hexdigest()=='ee31df11fc4fa98ab759ca1de7d52b3c'
    with path.open(encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
    labels=[r['Class'].strip() for r in rows];summaries=[]
    for label in sorted(set(labels)):
        inds=[i for i,x in enumerate(labels) if x==label]; sub=[rows[i] for i in inds];u=[float(r['u_max']) for r in sub]
        other=[float(r['u_max']) for r in rows if r['Class'].strip()!=label]
        summaries.append(dict(label=label,rows=len(sub),first_record_index_1based=min(inds)+1,last_record_index_1based=max(inds)+1,blocks=1+sum(b!=a+1 for a,b in zip(inds,inds[1:])),u_max_min=min(u),u_max_median=round(float(np.median(u)),5),u_max_max=max(u),other_class_rows_in_inclusive_u_max_range=sum(min(u)<=v<=max(u) for v in other),duplicate_numeric_feature_rows_within_label=len(sub)-len(set(tuple(float(v) for k,v in r.items() if k!='Class') for r in sub))))
    dump(out/'delta-feature-classes.csv',summaries)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('dc_workbook',type=Path);p.add_argument('induction_zip',type=Path);p.add_argument('servo_csv',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=True);cycles(a.induction_zip,a.output);classes(a.servo_csv,a.output);workbook(a.dc_workbook,a.output)
