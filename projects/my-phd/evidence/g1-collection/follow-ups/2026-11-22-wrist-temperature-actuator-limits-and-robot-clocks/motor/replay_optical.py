"""python replay_optical.py extracted_RAR_directory output_directory (SciPy, NumPy, pandas)."""
import argparse,csv,hashlib
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.io import loadmat

def write(out,name,rows):
    with (out/name).open('w',newline='') as f:
        w=csv.DictWriter(f,rows[0],lineterminator='\n');w.writeheader();w.writerows(rows)

def compare(key,quantity,method,tr,vr,to,vo):
    kr=np.isfinite(tr)&np.isfinite(vr);ko=np.isfinite(to)&np.isfinite(vo)
    r=tr[kr];v=vr[kr];t=to[ko];y=vo[ko]
    assert (np.diff(t)>0).all() and (np.diff(r)>0).all()
    sel=(r>=t.min())&(r<=t.max())
    # Evaluate optical measurements on the recorded times of the independent reference.
    # No extrapolation, phase tuning, clock correction or estimate of pointwise uncertainty.
    errors=np.interp(r[sel],t,y)-v[sel]
    idx=np.searchsorted(t,r[sel]);left=np.maximum(0,idx-1);right=np.minimum(len(t)-1,idx)
    return dict(test=key,quantity=quantity,method=method,reference_slots=len(tr),reference_finite=len(r),optical_slots=len(to),optical_finite=len(t),matched_reference=len(errors),median_reference_dt_ms=round(np.median(np.diff(r))*1000,5),median_optical_dt_ms=round(np.median(np.diff(t))*1000,5),max_nearest_time_gap_ms=round(np.minimum(abs(t[left]-r[sel]),abs(t[right]-r[sel])).max()*1000,5),mean_optical_minus_reference=round(errors.mean(),7),rmse_native=round(np.sqrt(np.mean(errors**2)),7),max_abs_error_native=round(abs(errors).max(),7))

def mat(p):return {k:v for k,v in loadmat(p,squeeze_me=True).items() if not k.startswith('_')}
def analyze(directory,out):
    root=next(directory.rglob('Readme.txt')).parent;out.mkdir(parents=True,exist_ok=True)
    files=[]
    for f in sorted(root.rglob('*')):
        if f.is_file():files.append(dict(path=f.relative_to(root).as_posix(),bytes=f.stat().st_size,sha256=hashlib.sha256(f.read_bytes()).hexdigest()))
    write(out,'optical-files.csv',files)
    results=[];fits=[]
    for folder in sorted((root/'Calibration_data').iterdir()):
        torque=mat(folder/'torque.mat');twist=mat(folder/'twist.mat');pre='D' if folder.name.startswith('Rising') else 'A'
        for rpm in [1600,1700,1800,1900,'all']:
            suffix='all' if rpm=='all' else pre+str(rpm)
            x=twist['twist_'+suffix];y=torque['torque_'+suffix]
            mask=np.isfinite(x)&np.isfinite(y);x=x[mask];y=y[mask]
            slope,intercept=np.polyfit(x,y,1);err=slope*x+intercept-y
            fits.append(dict(method=folder.name,rpm=rpm,finite_pairs=len(x),slope_Nm_per_native_twist=round(slope,7),intercept_Nm=round(intercept,7),fit_rmse_Nm=round(np.sqrt(np.mean(err**2)),7),note='pooled source array; overlaps rpm strata' if rpm=='all' else 'within-speed fit to calibration pairs'))
    for f in sorted(root.rglob('*.csv')):
        df=pd.read_csv(f);c=df.columns
        q='torque_Nm' if 'Torque' in c[1] else 'speed_rpm'
        for j in range(2,len(c),2):
            results.append(compare(f.stem,q,c[j+1].split(' - ')[-1],df.iloc[:,0].to_numpy(),df.iloc[:,1].to_numpy(),df.iloc[:,j].to_numpy(),df.iloc[:,j+1].to_numpy()))
    for file in sorted(root.glob('Steady state tests/*/Torque/*.mat')):
        m=mat(file);key=file.parent.parent.name
        if key.startswith('1700'):
            tr=m['TimeMag1'];v=m['TorqueMag1']
            methods=[(s,m[f'TimesOptical_{s}1'],m[f'TorqueNmOptical_{s}1']) for s in ['RE','CC']]
        else:
            tr=m['TimesMagtrol3'];v=m['TorqueNmMagtrol3']
            methods=[(s,m[f'TimesOptical3_{s}'],m[f'TorqueNmOptical3_{s}']) for s in ['RE','CC']]
        for method,t,y in methods:results.append(compare(key,'torque_Nm',method,tr,v,t,y))
    write(out,'optical-clock-matched.csv',results);write(out,'optical-calibration.csv',fits)
if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('data',type=Path);ap.add_argument('out',type=Path);a=ap.parse_args();analyze(a.data,a.out)
