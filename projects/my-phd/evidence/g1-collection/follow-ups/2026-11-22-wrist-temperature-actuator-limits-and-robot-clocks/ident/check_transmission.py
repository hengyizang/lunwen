"""Check the numeric table exports of Darus 3759 and 5160 (Python 3 and NumPy).
python check_transmission.py output [--cache input-directory]
Inputs are Dataverse's original CSV representations of files listed as ingested .tab.
"""
import argparse
import csv
import hashlib
import io
import itertools
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.request import urlopen
import numpy as np

BASE = 'https://darus.uni-stuttgart.de/api/'
PROJECTIONS = {3759: ['time','x_d','x_T','x_M','T_M','e_x'],
               5160: ['time','x_d','x_T','x_M1','x_M2','T_M1','T_M2']}
def write(path, rows):
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n')
        w.writeheader()
        w.writerows(rows)
def read_file(item, cache):
    series,f=item
    df=f['dataFile']; label=f['label']
    url=BASE+'access/datafile/'+str(df['id'])+'?format=original'
    path=cache/f'd{series}-{label}' if cache else None
    md5=hashlib.md5()
    sha=hashlib.sha256()
    total=0
    columns={}
    groups={}
    def track(b):
        nonlocal total
        total+=len(b)
        md5.update(b)
        sha.update(b)
    with (path.open('rb') if path and path.exists() else urlopen(url,timeout=120)) as fh:
        header=fh.readline()
        track(header)
        names=header.decode('utf-8-sig').strip().split(',')
        ix={n:i for i,n in enumerate(names)}
        # These files supply discrete commanded loads, preload and compensation.
        selectors=[] if not label.startswith(('Fig_9_','Fig_10_','Fig_11_')) else [
            n for n in ('F_ext','F_LDD','T_pl_d','Compensation') if n in ix]
        common=PROJECTIONS[series]
        channels=[n for n in common if n in ix]
        supports_projection=channels==common
        while lines:=list(itertools.islice(fh,8192)):
            blob=b''.join(lines)
            track(blob)
            a=np.loadtxt(io.BytesIO(blob),delimiter=',',ndmin=2)
            if a.shape[1]!=len(names) or not np.isfinite(a).all():
                raise ValueError((label,a.shape,'unexpected data'))
            for name,col in zip(names,a.T):
                z=columns.setdefault(name,[0,np.inf,-np.inf,0.])
                z[0]+=len(col);z[1]=min(z[1],float(col.min()));z[2]=max(z[2],float(col.max()))
                z[3]+=float(np.sum(col*col))
            if selectors:
                keys,inv=np.unique(a[:,[ix[n] for n in selectors]],axis=0,return_inverse=True)
                if len(keys)>300:raise ValueError((label,'selected column varies continuously'))
                pieces=[(tuple(k),a[inv==i]) for i,k in enumerate(keys)]
            else: pieces=[((),a)]
            for key,part in pieces:
                z=groups.setdefault(key,dict(n=0,hash=hashlib.sha256(),sse=0.,ssep=0.,
                                    max_abs_e=0.,max_res=0.,time_restarts=0,last_t=None))
                z['n']+=len(part)
                if 'time' in ix:
                    tc=part[:,ix['time']];z['time_restarts']+=int(np.sum(np.diff(tc)<=0))
                    if z['last_t'] is not None:z['time_restarts']+=int(tc[0]<=z['last_t'])
                    z['last_t']=tc[-1]
                if supports_projection:
                    vals=part[:,[ix[k] for k in common]].astype('<f8',copy=True)
                    vals[vals==0]=0  # normalize the sign bit of exact zeros
                    z['hash'].update(np.ascontiguousarray(vals).tobytes())
                if 'e_x' in ix:
                    ev=part[:,ix['e_x']];z['sse']+=float(np.sum(ev*ev))
                    z['max_abs_e']=max(z['max_abs_e'],float(np.max(np.abs(ev))))
                    if 'x_d' in ix and 'x_T' in ix:
                        r=part[:,ix['x_d']]-part[:,ix['x_T']]-ev
                        z['max_res']=max(z['max_res'],float(abs(r).max()))
                if 'e_pl' in ix:z['ssep']+=float(np.sum(part[:,ix['e_pl']]**2))
    assert md5.hexdigest()==df['checksum']['value'] and total==df['originalFileSize'],(label,md5.hexdigest(),total)
    manifest=dict(series=series,file=label,access_url=url,original_bytes=total,
                  original_md5=md5.hexdigest(),sha256=sha.hexdigest(),numeric_rows=next(iter(columns.values()))[0],
                  columns=' | '.join(names))
    stats=[dict(series=series,file=label,channel=n,samples=z[0],min_native=z[1],max_native=z[2],
                rms_native=np.sqrt(z[3]/z[0])) for n,z in columns.items()]
    conditional=[]
    for key,z in sorted(groups.items()):
        conditional.append(dict(series=series,file=label,
            condition=' | '.join(f'{n}={v:g}' for n,v in zip(selectors,key)) or 'all',
            rows=z['n'],nonincreasing_time_steps=z['time_restarts'] if 'time' in ix else '',
            rms_position_error_native=np.sqrt(z['sse']/z['n']) if 'e_x' in ix else '',
            max_abs_position_error_native=z['max_abs_e'] if 'e_x' in ix else '',
            max_abs_desired_minus_table_minus_stored_error=z['max_res'] if {'x_d','x_T','e_x'}<=ix.keys() else '',
            rms_preload_error_native=np.sqrt(z['ssep']/z['n']) if 'e_pl' in ix else '',
            common_channel_hash=z['hash'].hexdigest() if supports_projection else ''))
    return manifest,stats,conditional

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path);p.add_argument('--cache',type=Path)
    args=p.parse_args();args.output.mkdir(exist_ok=True,parents=True)
    tasks=[]
    for series in (3759,5160):
        url=BASE+f'datasets/:persistentId/versions/1.0?persistentId=doi:10.18419/DARUS-{series}'
        version=json.load(urlopen(url,timeout=45))['data']
        tasks.extend((series,f) for f in version['files'] if f['label'].endswith('.tab'))
    with ThreadPoolExecutor(4) as pool: result=list(pool.map(lambda e:read_file(e,args.cache),tasks))
    write(args.output/'transmission-files.csv',[e[0] for e in result])
    write(args.output/'transmission-channels.csv',[row for e in result for row in e[1]])
    write(args.output/'transmission-conditions.csv',[row for e in result for row in e[2]])
if __name__=='__main__':main()
