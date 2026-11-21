"""Usage: python volvo_bench.py RAW OUT 2|3 (RAW contains that release's two archives).
Requires numpy, scipy, h5py, and for ESR2 libarchive-c with RAR-capable libarchive.
"""
import csv
import hashlib
import io
from pathlib import Path
import re
import sys
import zipfile
import h5py
import numpy as np
from scipy import signal
from scipy.io import loadmat

raw, out = map(Path, sys.argv[1:3])
out.mkdir(parents=True, exist_ok=True)
fmt = lambda a: f'{a:.6f}'
rms = lambda v: np.sqrt(np.mean(v*v))

def table(name, fields, rows):
    with (out / name).open('w', newline='') as f:
        w = csv.writer(f, lineterminator='\n')
        w.writerow(fields.split())
        w.writerows(rows)

def clock(t):
    dt = np.diff(t)
    assert np.isfinite(t).all() and np.all(dt > 0)
    return np.median(dt)

def read_hdf(blob, channels):
    with h5py.File(io.BytesIO(blob)) as h:
        capture = h[next(k for k in h if not k.startswith('#'))]
        t = capture['X/Data'][...].ravel()
        y = capture['Y']
        values = {}
        for pn, vn in zip(y['Path'][...].ravel(), y['Data'][...].ravel()):
            name = ''.join(map(chr, h[pn][...].ravel())).split('/')[-1]
            if name in channels:
                v = h[vn][...].ravel()
                assert v.shape == t.shape and np.isfinite(v).all()
                values[name] = v
        assert set(values) == set(channels)
        return t, values

def objectmat(blob):
    return loadmat(io.BytesIO(blob), squeeze_me=True, struct_as_record=False)

def esr2():
    import libarchive
    logs, spectra, rack, car = [], [], [], []
    with zipfile.ZipFile(raw / 'ESR2_SteerByWireForceFeedback.zip') as z:
        for m in sorted(k for k in z.namelist() if k.endswith('.mat')):
            b = z.read(m)
            o = next(v for k,v in objectmat(b).items() if not k.startswith('_'))
            t = o.X[0].Data
            y = {v.Name:v.Data for v in o.Y if v.XIndex == 1}
            dt = clock(t)
            name = Path(m).stem
            p, q = y['CLcommTorque'], y['ActualCLTorque']
            logs.append([name,len(t),fmt(dt),fmt(rms(q-p)),fmt(rms(y['MmotREQ']-p)),
                         fmt(rms(y['MtbAct']-y['MtbRef'])),fmt(rms(y['TS_torque']-y['MtbAct'])),
                         fmt(np.ptp(y['MmotREQ'])),fmt(np.ptp(q)),hashlib.sha256(b).hexdigest()])
            if 'FreqResp' not in name:
                continue
            cfg = dict(fs=1/dt, nperseg=1024, noverlap=512, window='hann', detrend='constant')
            f, pp = signal.welch(p, **cfg)
            _, pq = signal.csd(p, q, **cfg)
            _, coh = signal.coherence(p, q, **cfg)
            for lo, hi in [(0.5,2),(2,5),(5,10),(10,20)]:
                band = (f>=lo) & (f<hi)
                supported = band & (pp>=0.001*np.max(pp)) & (coh>=0.5)
                spectra.append([name,lo,hi,int(band.sum()),int(supported.sum()),
                                fmt(np.median(np.abs(pq[supported]/pp[supported]))) if supported.any() else '',
                                fmt(np.median(coh[supported])) if supported.any() else ''])
    with libarchive.file_reader(str(raw / 'ESR2_ElectricPowerAssistedSteering.rar')) as arc:
        for member in arc:
            if not member.pathname.endswith('.mat'):
                continue
            b = b''.join(member.get_blocks())
            name = Path(member.pathname).stem
            digest = hashlib.sha256(b).hexdigest()
            if '_TestRigData/' in member.pathname:
                keys = ['DISP_DEMANDED_POSITION_DL','DISP_ACTUAL_POSITION_DL',
                        'DISP_DEMANDED_POSITION_DR','DISP_ACTUAL_POSITION_DR','DISP_ACTUAL_TORQUE_SR']
                t, y = read_hdf(b, keys)
                demand, actual, dem_r, act_r, trq = (y[k] for k in keys)
                err = (actual-np.mean(actual))-(demand-np.mean(demand))
                rack.append([name,len(t),fmt(clock(t)),fmt(np.ptp(demand)),fmt(np.ptp(actual)),
                             fmt(np.ptp(dem_r)),fmt(np.ptp(act_r)),fmt(rms(err)),fmt(np.ptp(trq)),digest])
            else:
                d = objectmat(b)
                for k in sorted(x for x in d if not x.startswith('_')):
                    t, v = d[k].T
                    car.append([name,k,len(t),fmt(clock(t)),fmt(t[-1]-t[0]),fmt(v.min()),fmt(v.max()),digest])
    table('esr2-wheel.csv','run points median_dt_s command_actual_rmse_Nm motorrequest_command_rmse_native torsion_reference_rmse_native sensor_filtered_torsion_rmse_native request_span_native actual_motor_torque_span_Nm member_sha256',logs)
    table('esr2-frequency.csv','run low_Hz high_Hz bins supported_bins median_H1_magnitude median_coherence',spectra)
    table('esr2-rack.csv','run points median_dt_s left_request_span_native left_actual_span_native right_request_span_native right_actual_span_native left_centered_tracking_rmse_native actual_steering_torque_span_native member_sha256',sorted(rack))
    table('esr2-vehicle.csv','run signal points median_dt_s duration_s min_native max_native member_sha256',sorted(car))

def esr3():
    rig, blocks, models, clockrows = [], {}, [], []
    keys = ['DISP_ACTUAL_ANGLE_SR','DISP_DEMANDED_ANGLE_SR','DISP_ACTUAL_POSITION_DR',
            'DISP_DEMANDED_POSITION_DR','DISP_ACTUAL_TORQUE_SR','DISP_ACTUAL_VELOCITY_SR']
    with zipfile.ZipFile(raw / 'ESR3_EPAS_measurement&validation.zip') as z:
        for m in sorted(k for k in z.namelist() if '/steering_hil_measurement_2/' in k and k.endswith('.mat')):
            b=z.read(m)
            t,y = read_hdf(b, keys)
            a,d,x,c,trq,v = (y[k] for k in keys)
            name=Path(m).stem
            rig.append([name,len(t),fmt(clock(t)),fmt(np.ptp(d)),fmt(np.ptp(a)),fmt(rms(a-d)),
                        fmt(np.ptp(c)),fmt(np.ptp(x)),fmt(rms(x-c)),fmt(np.ptp(trq)),
                        hashlib.sha256(b).hexdigest()])
            match=re.fullmatch(r'(25|26|27|28)_Robot_(\d+)degps_LinActDisconn',name)
            if match:
                # Interior, nearly constant-speed strokes; identical rule at each speed.
                speed=int(match[2])
                use=(np.abs(a)<=400) & (np.abs(np.abs(v)-speed)<=0.1*speed)
                blocks[name]=(v[use],trq[use])
    # Fit 13 and 23 deg/s runs and evaluate distinct 37 and 45 deg/s files.
    train=[b for k,b in blocks.items() if k.startswith(('25_','26_'))]
    v0,y0=map(np.concatenate,zip(*train))
    for model in ('coulomb','coulomb_viscous'):
        def design(v):
            features=[np.ones_like(v),np.sign(v)]
            if model=='coulomb_viscous':
                features.append(v)
            return np.column_stack(features)
        beta=np.linalg.lstsq(design(v0),y0,rcond=None)[0]
        for name,(v,y) in sorted(blocks.items()):
            models.append([model,name,'fit' if name.startswith(('25_','26_')) else 'holdout',len(v),
                           *[fmt(c) for c in beta],*([''] if len(beta)==2 else []),
                           fmt(rms(design(v)@beta-y))])
    with zipfile.ZipFile(raw / 'ESR3_HIL&DILtests.zip') as z:
        for m in sorted(k for k in z.namelist() if k.endswith('.mat')):
            b=z.read(m); d=objectmat(b); obj=d['MyData']
            ht=obj.Time.data; hk=d['time']
            # Search by recorded clock and test the entire contiguous value vector.
            def subset(full,selected,coord0,part0):
                start=np.searchsorted(coord0,part0[0])
                return np.array_equal(full[start:start+len(selected)],selected,equal_nan=True)
            rec=np.isfinite(d['Measurement']); vtime=d['Measurement'][rec]
            data=[Path(m).stem,len(ht),fmt(clock(ht)),len(hk),
                  all(subset(getattr(obj,k).data,d[j],ht,hk)
                      for k,j in [('Time','time'),('Steer_WhlAng','SWA'),('Steer_WhlTrq','SWT')]),
                  len(vtime),fmt(clock(vtime)),int(np.unique(d['iepas'][rec]).size),
                  int(np.unique(d['uepas'][rec]).size)]
            aligned=''
            n=0
            if 'VehicleTest' in d:
                objv=d['VehicleTest'];n=len(objv.time)
                aligned=all(subset(d[j][rec], getattr(objv,k),vtime,objv.time) for k,j in
                            [('time','Measurement'),('swa','swa'),('swt','swt1'),('iepas','iepas'),('uepas','uepas')])
            clockrows.append([*data,n,aligned,hashlib.sha256(b).hexdigest()])
    table('esr3-rig.csv','run points median_dt_s demanded_angle_span_deg actual_angle_span_deg angle_rmse_deg demanded_right_position_span_mm actual_right_position_span_mm position_rmse_mm actual_steering_torque_span_Nm member_sha256',rig)
    table('esr3-friction.csv','model run partition points offset_Nm sign_velocity_coef_Nm velocity_coef_Nm_per_degps measured_torque_rmse_Nm',models)
    table('esr3-clock.csv','file MyData_points MyData_dt_s top_clock_points top_angle_torque_time_exact_MyData_subset measurement_finite_points measurement_dt_s measurement_distinct_iepas measurement_distinct_uepas VehicleTest_points VehicleTest_exact_measurement_subset member_sha256',clockrows)

input_md5 = {
    '2': {'ESR2_SteerByWireForceFeedback.zip':'9e92b745609cd47d82c5fc61691aebd8',
          'ESR2_ElectricPowerAssistedSteering.rar':'8f6a4abf55646fe17b28a8ede2e69508'},
    '3': {'ESR3_EPAS_measurement&validation.zip':'74d631b6e7b13d95e2bced89a13f2600',
          'ESR3_HIL&DILtests.zip':'9614ffa5f7377f9260c71d3a3bddfe12'}}
for filename, expected in input_md5[sys.argv[3]].items():
    with (raw/filename).open('rb') as source:
        assert hashlib.file_digest(source,'md5').hexdigest() == expected
if sys.argv[3]=='2':
    esr2()
elif sys.argv[3]=='3':
    esr3()
else:
    raise ValueError('Select 2 or 3')
