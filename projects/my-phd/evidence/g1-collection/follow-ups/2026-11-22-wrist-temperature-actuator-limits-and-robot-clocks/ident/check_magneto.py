"""Check five measured identification/validation logs, using Python, NumPy and SciPy.
python check_magneto.py output [--cache input-directory]
The output describes files and a small set of counts; acquisition arrays remain upstream.
"""
import argparse
import csv
import hashlib
import io
from pathlib import Path
from urllib.parse import quote
from urllib.request import urlopen
import numpy as np
from scipy.io import loadmat

COMMIT='bc0778f97a156d4ea5158725e09068d438e59a39'
RAWPREFIX='https://raw.githubusercontent.com/gergelytakacs/AutomationShield/'+COMMIT+'/'
M='matlab/examples/MagnetoShield/'
S='simulink/examples/MagnetoShield/MagnetoShield_AlternativeModel_Examples/'
INPUTS=[
 (M+'MagnetoShield_ID_Data.mat','PID identification',0.00325),
 (M+'R2/ID_PID_1300us.mat','PID identification (R2 filename)',0.0013),
 (M+'R2/ID_PID_4000us.mat','PID identification (R2 filename)',0.004),
 (S+'Identification/Identif_Data/Data.mat','LQR identification',None),
 (S+'Models_comparison/Data_time.mat','PID time-domain holdout as described in associated comparison materials',None)
]
def read(p,path):
    if path is not None and path.is_file():return path.read_bytes()
    with urlopen(RAWPREFIX+quote(p),timeout=45) as r:return r.read()
def main():
    pa=argparse.ArgumentParser(description=__doc__);pa.add_argument('output',type=Path);pa.add_argument('--cache',type=Path)
    args=pa.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    rows=[]
    for path,role,ts in INPUTS:
        raw=read(path,args.cache/('aut-'+path.replace('/','__')) if args.cache else None)
        d=loadmat(io.BytesIO(raw),squeeze_me=True)
        if 'result' in d:y,u,current=d['result'].T
        else:
            y=d['y'];u=d['u'];current=d['I'] if 'I' in d else d['i'];ts=float(d['Ts'])
        assert len(y)==len(u)==len(current) and np.isfinite(np.column_stack([y,u,current])).all()
        zero=u==0; twelve=u==12.
        if 't' in d:
            assert len(d['t'])==len(y) and np.max(abs(np.diff(d['t'])-ts))<1e-10
        row=dict(file=path,version=COMMIT,role=role,bytes=len(raw),
                 git_blob=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest(),
                 sha256=hashlib.sha256(raw).hexdigest(),samples=len(u),nominal_dt_s=ts,
                 has_explicit_time=int('t' in d),has_reference=int('ref' in d),
                 min_logged_u_V=float(u.min()),max_logged_u_V=float(u.max()),zero_V_rows=int(zero.sum()),
                 zero_V_positive_coil_current_rows=int(np.sum(zero&(current>0))),
                 zero_V_max_current_mA=float(current[zero].max()) if zero.any() else '',
                 equal_12V_rows=int(twelve.sum()),min_position_mm=float(y.min()),max_position_mm=float(y.max()),
                 min_current_mA=float(current.min()),max_current_mA=float(current.max()))
        rows.append(row)
        if 'ref' in d:
            freq_path=S+'Models_comparison/Data_frequency.mat'
            freq_raw=read(freq_path,args.cache/('aut-'+freq_path.replace('/','__')) if args.cache else None)
            freq=loadmat(io.BytesIO(freq_raw),struct_as_record=False,squeeze_me=True)['dataf']
            assert float(freq.Ts)==ts and freq.Domain=='Frequency'
            comparisons=[]
            for name,val,stored,scale in [('u',u,freq.InputData,1),('y',y,freq.OutputData[:,0],.001),('i',current,freq.OutputData[:,1],.001)]:
                calculated=np.fft.rfft(val-val.mean())*scale/np.sqrt(len(val))
                difference=calculated-stored
                comparisons.append(dict(time_file=path,frequency_file=freq_path,channel=name,bins=len(stored),
                    time_to_SI_scale=scale,frequency_file_sha256=hashlib.sha256(freq_raw).hexdigest(),
                    relative_L2_difference=np.linalg.norm(difference)/np.linalg.norm(stored),
                    max_abs_difference=np.max(abs(difference))))
            with (args.output/'magnetic-fft-identity.csv').open('w',newline='') as fo:
                writer=csv.DictWriter(fo,fieldnames=list(comparisons[0]),lineterminator='\n')
                writer.writeheader();writer.writerows(comparisons)
    with (args.output/'magnetic-input-current.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
if __name__=='__main__':main()
