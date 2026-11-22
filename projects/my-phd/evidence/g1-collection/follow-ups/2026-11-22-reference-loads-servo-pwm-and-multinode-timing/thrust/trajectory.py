"""Audit the pinned tank trajectory release; no raw observations are redistributed."""
from concurrent.futures import ThreadPoolExecutor
from urllib.request import Request,urlopen
from pathlib import Path
import csv,hashlib,io,json,sys
import numpy as np
import pandas as pd
REPO='oceansystemslab/Bluerov2_trajectory_dataset'
REV='5104d15d2f9756ff45b4b0ed2b95d284a6e30e43'
def get(u):return urlopen(Request(u,headers={'User-Agent':'G1 public research directory'}),timeout=40).read()
def audit(e):
 u='https://raw.githubusercontent.com/'+REPO+'/'+REV+'/'+e['path'];b=get(u)
 assert hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()==e['sha']
 df=pd.read_csv(io.BytesIO(b));p=df[['pwm'+str(i) for i in range(1,9)]].to_numpy();cmd=df[['u_pwm'+str(i) for i in range(1,9)]].to_numpy()
 a=df.iloc[:,0].to_numpy(); pose=df[['x','y','z','qx','qy','qz','qw']].to_numpy()
 return dict(path=e['path'],git_blob=e['sha'],sha256=hashlib.sha256(b).hexdigest(),rows=len(df),cols=len(df.columns),first_field=df.columns[0],index_sequential=bool(np.array_equal(a,np.arange(len(df)))),rows_with_all_eight_pwm_finite=int(np.isfinite(p).all(axis=1).sum()),pwm_us_min=float(np.nanmin(p)),pwm_us_max=float(np.nanmax(p)),channel_samples_eq_1100=int((p==1100).sum()),channel_samples_eq_1900=int((p==1900).sum()),all_pose_fields_finite=int(np.isfinite(pose).all(axis=1).sum()),has_explicit_time=any(s.lower() in {'t','time','stamp','timestamp'} for s in df.columns))
if __name__=='__main__':
 out=Path(sys.argv[1]);tree=json.loads(get('https://api.github.com/repos/'+REPO+'/git/trees/'+REV+'?recursive=1'));assert not tree['truncated']
 entries=[e for e in tree['tree'] if e['path'].startswith('dataset/odom') and e['path'].endswith('.csv')];assert len(set(e['sha'] for e in entries))==len(entries)
 with ThreadPoolExecutor(4) as p:rows=list(p.map(audit,entries))
 with (out/'tank-trajectory-files.csv').open('w',newline='') as f:
  w=csv.DictWriter(f,rows[0].keys(),lineterminator='\n');w.writeheader();w.writerows(rows)

