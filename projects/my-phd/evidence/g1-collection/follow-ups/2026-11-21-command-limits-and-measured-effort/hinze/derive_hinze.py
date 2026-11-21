"""Audit two Hinze ball-screw releases and compare exact identities with two shared-rig releases.

python derive_hinze.py RAW OUT OLD
RAW is populated by fetch_hinze.py for 3003 and 3152. OLD is populated by
../servo/fetch_servo_release.py for 2563 and 3109. Requires NumPy and h5py.
"""
import argparse
import csv
import hashlib
import itertools
import json
from pathlib import Path
import re

import h5py
import numpy as np


def write(path,rows):
    with path.open('w',newline='') as stream:
        w=csv.DictWriter(stream,fieldnames=rows[0],lineterminator='\n')
        w.writeheader();w.writerows(rows)


def signals(path,prior):
    required={'x_meas_table'} if prior else {'x_meas_table','x_meas_motor','traj_KGT[0]','traj_KGT[1]',
                     'u_motor [rot]','M_KGT_act','F_des_LDD','v_meas_table'}
    optional=set() if prior else {'F_nut_sum','sigEnable','lastError'}
    with h5py.File(path) as h:
        g=h[next(k for k in h if not k.startswith('#'))]
        clocks=[h[r[0]][()].ravel() for r in g['X/Data']]
        t=clocks[0]
        values={}; residues={}
        for n,r,ix in zip(g['Y/Name'],g['Y/Data'],g['Y/XIndex']):
            name=''.join(map(chr,h[n[0]][()].ravel()))
            if name not in required|optional:continue
            grid=clocks[int(h[ix[0]][()].ravel()[0])-1]
            raw=h[r[0]][()].ravel()
            if name=='x_meas_table':
                identity=hashlib.sha256(raw.astype('<f8').tobytes()).hexdigest()
            if prior:continue
            ix=np.searchsorted(grid,t).clip(0,len(grid)-1)
            left=(ix-1).clip(0,len(grid)-1)
            ix=np.where(abs(grid[ix]-t)<=abs(grid[left]-t),ix,left)
            assert np.isfinite(raw).all()
            residues[name]=abs(t-grid[ix])
            values[name]=raw[ix]
        if not prior:
            assert required<=values.keys()
            residual=np.maximum.reduce(list(residues.values()))
            aligned=residual<=0.0001251
            n_missing=int((~aligned).sum())
            values={k:v[aligned] for k,v in values.items()};t=t[aligned]
            values['unaligned']=n_missing
            values['max_residual']=max(residual[aligned])
    return t,values,identity


def rms(v):
    return np.sqrt(np.mean(v*v))


def main(root,out,old):
    out.mkdir(exist_ok=True,parents=True)
    near=[];identities={};matched={}
    for n in (2563,3109,3003,3152):
        prior=n in (2563,3109)
        home=old if prior else root
        version=json.loads((home/f'meta{n}.json').read_text())['data']
        version=version.get('latestVersion',version)
        digests=set();traces=set();runs=[];stick=[];steps=[];cruise=[];faults=[]
        for entry in version['files']:
            f=entry['dataFile'];path=home/str(n)/str(f['id']);name=f.get('originalFileName',f['filename'])
            folder=entry.get('directoryLabel','')
            content=path.read_bytes()
            assert len(content)==f.get('originalFileSize',f['filesize']) and hashlib.md5(content).hexdigest()==f['md5']
            digests.add(hashlib.sha256(content).hexdigest())
            if not name.endswith('.mat'):continue
            pair=(n==2563 and name in ('SP_v25_forw.mat','SP_v25_backw.mat')) or (n==3003 and name.startswith('const_vel_'))
            t,d,trace=signals(path,prior and not pair)
            if pair:
                q=d['traj_KGT[0]'];v=d['traj_KGT[1]']
                direction=1 if max(v)>0.02 else -1
                use=(abs(v-direction*.025)<.00025)&(q>=.02)&(q<.70)
                ix=np.floor(q[use]*100).astype(int)
                vals=[d['F_nut_sum'][use],1e6*(q-d['x_meas_table'])[use]]
                stats={b:[np.median(z[ix==b]) for z in vals] for b in np.unique(ix)}
                matched[n,direction]=(name,stats,max(abs(d['F_des_LDD'])))
            traces.add(trace)
            if prior:continue
            pos=d['x_meas_table'];motor=d['x_meas_motor'];q=d['traj_KGT[0]'];v=d['traj_KGT[1]']
            u=d['u_motor [rot]'];inv=d['M_KGT_act'];force=d['F_des_LDD']
            err=1e6*(q-pos)
            common=dict(directory=folder,file=name)
            moving=abs(v)>.01
            runs.append(dict(**common,command_grid_rows=len(t),excluded_unpaired_rows=d['unaligned'],max_residual_us=1e6*d['max_residual'],grid_dt_ms=1e3*np.median(np.diff(t)),
                planned_table_position_rmse_um=rms(err),motor_table_position_rmse_um=1e6*rms(motor-pos),
                planned_table_position_rmse_moving_um=rms(err[moving]) if moving.any() else '',moving_rows=int(sum(moving)),
                torque_request_absmax_Nm=max(abs(u)),inverter_torque_absmax_Nm=max(abs(inv)),
                command_inverter_rmse_Nm=rms(u-inv),disturbance_force_request_absmax_N=max(abs(force)),
                independently_measured_nut_force_absmax_N=max(abs(d['F_nut_sum'])) if 'F_nut_sum' in d else '',
                nonzero_error_rows=int(sum(d['lastError']!=0)) if 'lastError' in d else '',
                disabled_rows=int(sum(d['sigEnable']==0)) if 'sigEnable' in d else ''))
            if n==3003:
                enable=d['sigEnable'];errcode=d['lastError']
                for j in np.where((enable[1:]==0)&(enable[:-1]==1))[0]+1:
                    end=j+1
                    while end<len(t) and enable[end]==0:end+=1
                    span=slice(j,end)
                    faults.append(dict(**common,event_s=t[j],prior_code=errcode[j-1],event_code=errcode[j],
                        disabled_rows=end-j,disabled_interval_nonzero_code_rows=int(sum(errcode[span]!=0)),
                        first_disabled_request_Nm=u[j],final_disabled_request_Nm=u[end-1],
                        disabled_request_range_Nm=np.ptp(u[span]),first_disabled_inverter_Nm=inv[j],
                        final_disabled_inverter_Nm=inv[end-1],disabled_table_span_mm=1e3*np.ptp(pos[span])))
            if name.startswith('F_mot_sine'):
                match=re.fullmatch(r'F_mot_sine_F(\d+)_(\d+)_(\d+)Hz.mat',name)
                amp,whole,fraction=match.groups()
                stick.append(dict(**common,nominal_axial_excitation_N=int(amp),nominal_frequency_Hz=float(whole+'.'+fraction),
                    command_torque_absmax_Nm=max(abs(u)),motor_travel_um=1e6*np.ptp(motor),table_travel_um=1e6*np.ptp(pos),
                    measured_nut_force_peak_to_peak_N=np.ptp(d['F_nut_sum']),max_abs_table_velocity_mm_s=1000*max(abs(d['v_meas_table']))))
            if re.fullmatch(r'const_v_\d+.mat',name):
                speed=int(name.split('_')[-1].split('.')[0])
                for direction in (-1,1):
                    # Require the commanded speed and independently measured speed to agree within 5%.
                    mask=(abs(v-direction*speed/1000)<=speed*.00005)&(abs(d['v_meas_table']-direction*speed/1000)<=speed*.00005)
                    if not mask.any():continue
                    cruise.append(dict(**common,nominal_speed_mm_s=speed,direction=direction,accepted_rows=int(mask.sum()),
                           median_requested_torque_Nm=np.median(u[mask]),median_inverter_torque_Nm=np.median(inv[mask]),
                           median_measured_nut_force_N=np.median(d['F_nut_sum'][mask]),median_motor_minus_table_um=1e6*np.median((motor-pos)[mask])))
            if name=='DStep.mat':
                events=np.where((abs(force[1:]-force[:-1])>500)&(abs(force[:-1])<250))[0]+1
                assert len(events)==2
                for j in events:
                    pre=(t>=t[j]-.1)&(t<t[j])
                    post=(t>=t[j])&(t<t[j]+.1)
                    baseline=np.median(err[pre])
                    steps.append(dict(**common,step_time_s=t[j],commanded_step_N=force[j]-force[j-1],
                          prior_100ms_median_table_error_um=baseline,first_100ms_peak_baseline_adjusted_table_error_um=max(abs(err[post]-baseline)),
                          first_100ms_motor_table_peak_um=1e6*max(abs((motor-pos)[post]))))
        identities[n]=len(version['files']),digests,traces
        if not prior:
            write(out/f'darus-{n}-runs.csv',runs)
            if n==3003:
                write(out/'friction-sine-motion.csv',stick);write(out/'friction-cruise.csv',cruise)
                write(out/'friction-disable-events.csv',faults)
            else:write(out/'position-disturbance-steps.csv',steps)
    for a,b in itertools.combinations(identities,2):
        ka,da,ta=identities[a];kb,db,tb=identities[b]
        near.append(dict(release_a=a,release_b=b,files_a=ka,files_b=kb,distinct_original_files_a=len(da),
            distinct_original_files_b=len(db),shared_original_sha256=len(da&db),
            distinct_full_table_encoder_series_a=len(ta),distinct_full_table_encoder_series_b=len(tb),
            shared_full_native_table_encoder_array_sha256=len(ta&tb)))
    write(out/'shared-bench-file-identity.csv',near)
    pairs=[]
    for direction in (-1,1):
        a,x,fu=matched[2563,direction];b,y,fc=matched[3003,direction]
        bins=sorted(set(x)&set(y))
        assert len(bins)==68
        fx,ex=np.array([x[k] for k in bins]).T
        fy,ey=np.array([y[k] for k in bins]).T
        pairs.append(dict(direction=direction,uncompensated_file=a,compensated_file=b,common_10mm_bins=len(bins),
              uncompensated_force_request_absmax_N=fu,compensated_force_request_absmax_N=fc,
              uncompensated_nut_force_bin_medians_centered_rms_N=rms(fx-np.median(fx)),
              compensated_nut_force_bin_medians_centered_rms_N=rms(fy-np.median(fy)),
              uncompensated_position_error_bin_medians_rms_um=rms(ex),compensated_position_error_bin_medians_rms_um=rms(ey)))
    write(out/'paired-25mm-compensation.csv',pairs)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('raw',type=Path);p.add_argument('out',type=Path);p.add_argument('older_raw',type=Path)
    a=p.parse_args();main(a.raw,a.out,a.older_raw)
