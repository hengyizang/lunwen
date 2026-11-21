"""Read the smallest complete labeled-wrench archive per object in the RBO deposit.

python derive_rbo_wrench.py zenodo-1036660.json interactions_index.csv ARCHIVES OUT
Uses Python 3.11+ and NumPy. Bytes remain in the source archives.
"""
import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
import csv
import gzip
import hashlib
import io
import json
from pathlib import Path
import tarfile
import numpy as np


FORCE_BIAS=np.array([-.927,1.122,1.332])  # N, authors' arXiv v1 p. 5, Interaction Wrenches
TORQUE_BIAS=np.array([.104,.027,-.033])   # N m in the sensor frame
MASS_KG=.163
COM_M=.015
G=9.80665


def selected(registry,interactions):
    files={f['key']:f for f in json.loads(registry.read_text())['files']}
    by_object=defaultdict(list)
    with interactions.open(newline='') as f:
        for row in csv.DictReader(f):
            if row['force/torque sensor used']=='1':
                by_object[row['Object']].append(files[row['Name']+'_o.tar.gz'])
    return [(obj,min(items,key=lambda f:(f['size'],f['key']))) for obj,items in sorted(by_object.items())]


def extract(path,meta):
    if path.stat().st_size!=meta['size']:raise ValueError('Partial archive '+path.name)
    with path.open('rb') as f:
        if 'md5:'+hashlib.file_digest(f,'md5').hexdigest()!=meta['checksum']:
            raise ValueError('Archive MD5 differs from fixed release')
    members={}
    with gzip.open(path,'rb') as stream, tarfile.open(fileobj=stream,mode='r|',bufsize=512*1024) as tf:
        for m in tf:
            if m.isfile() and (m.name.endswith('/ft_sensor_netft_data.csv') or m.name.endswith('_joint_states.csv')):
                key='joint' if m.name.endswith('_joint_states.csv') else 'ft'
                if key in members:raise ValueError('Ambiguous member selection')
                members[key]=(m.name,tf.extractfile(m).read())
    return members


def first_run(t,mask):
    # Require 30 ms of sampled persistence; start anew across recording gaps >100 ms.
    first=None
    for i,yes in enumerate(mask):
        if not yes:
            first=None
            continue
        if first is None or (i and t[i]-t[i-1]>100_000_000):
            first=t[i]
        if t[i]-first>=30_000_000:
            return int(first)
    return None


def measurements(member):
    return list(csv.DictReader(io.StringIO(member[1].decode('utf-8-sig'))))


def stream_time(rows):
    t=np.array([int(r['field.header.stamp']) for r in rows],dtype=np.int64)
    if np.any(np.diff(t)<0):raise ValueError('Backward header time detected')
    return t


def nearest_lag(times,reference):
    # Both are sorted. Operate only inside their observed overlap.
    i=np.searchsorted(reference,times)
    i=np.minimum(i,len(reference)-1)
    j=np.maximum(0,i-1)
    return np.minimum(abs(reference[i]-times),abs(reference[j]-times))


def summarize(params):
    directory,obj,meta=params
    path=directory/meta['key']
    contents=extract(path,meta)
    coverage=dict(object=obj,archive=path.name,bytes=path.stat().st_size,verified_publisher_md5=meta['checksum'])
    for key in ('ft','joint'):
        if key in contents:
            coverage[key+'_member']=contents[key][0]
            coverage[key+'_sha256']=hashlib.sha256(contents[key][1]).hexdigest()
        else:
            coverage[key+'_member']=''
            coverage[key+'_sha256']=''
    if not contents.get('ft') or not contents.get('joint'):
        raise ValueError('Missing numeric topics in '+path.name)
    ft,js=measurements(contents['ft']),measurements(contents['joint'])
    ft_t,js_t=stream_time(ft),stream_time(js)
    force,torque=[np.array([[float(r[f'field.wrench.{signal}.{axis}']) for axis in 'xyz'] for r in ft])
                  for signal in ('force','torque')]
    if not np.isfinite(force).all() or not np.isfinite(torque).all():raise ValueError('Nonfinite wrench')
    t0=max(ft_t[0],js_t[0]);t1=min(ft_t[-1],js_t[-1])
    fs=(ft_t>=t0)&(ft_t<=t1);jsel=(js_t>=t0)&(js_t<=t1)
    nearest=nearest_lag(ft_t[fs],js_t[jsel])
    biased_force=force-FORCE_BIAS
    biased_torque=torque-TORQUE_BIAS
    gforce=MASS_KG*G;garm=gforce*COM_M
    coverage.update(ft_rows=len(ft),joint_rows=len(js),wrench_unique_header_ns=len(np.unique(ft_t)),
                    joint_unique_header_ns=len(np.unique(js_t)),raw_ft_frames='|'.join(sorted({row['field.header.frame_id'] for row in ft})),
                    ft_overlap_rows=int(fs.sum()),joint_overlap_rows=int(jsel.sum()),
                    exact_shared_unique_header_ns=len(np.intersect1d(ft_t,js_t)),
                    overlap_nearest_joint_header_p95_ms=round(float(np.quantile(nearest,.95))/1e6,5),
                    raw_moment_norm_median_nm=round(float(np.median(np.linalg.norm(torque,axis=1))),8),
                    minus_published_bias_moment_norm_median_nm=round(float(np.median(np.linalg.norm(biased_torque,axis=1))),8),
                    moment_norm_above_static_tool_gravity_bound=int(np.count_nonzero(np.linalg.norm(biased_torque,axis=1)>garm)),
                    force_norm_above_static_tool_weight=int(np.count_nonzero(np.linalg.norm(biased_force,axis=1)>gforce)))
    ft_base=fs&(ft_t<t0+250_000_000)
    js_base=jsel&(js_t<t0+250_000_000)
    ft_delta=np.linalg.norm(force[fs]-np.median(force[ft_base],axis=0),axis=1)
    motion=[]
    for c in js[0]:
        if not c.startswith('field.position'):continue
        suffix=c.removeprefix('field.position')
        q=np.array([float(row[c]) if row[c] else np.nan for row in js])
        q0=np.nanmedian(q[js_base])
        lo,hi=np.nanquantile(q[jsel],[.05,.95])
        delta=hi-lo
        if not np.isfinite(delta) or delta<=1e-8:continue
        crossing=first_run(js_t[jsel],abs(q[jsel]-q0)>.05*delta)
        if crossing is not None:motion.append((crossing,js[0]['field.name'+suffix]))
    earliest,jn=min(motion) if motion else (None,'')
    events=[]
    for threshold in (1,2,4):
        first=first_run(ft_t[fs],ft_delta>threshold)
        events.append(dict(object=obj,archive=path.name,force_change_threshold_n=threshold,baseline_window_ms=250,
                           persistence_ms=30,eligible_joints_with_threshold_crossing=len(motion),earliest_joint=jn,
                           earliest_motion_after_overlap_start_ms='' if earliest is None else round((earliest-int(t0))/1e6,6),
                           force_change_after_overlap_start_ms='' if first is None else round((first-int(t0))/1e6,6),
                           force_minus_joint_change_ms='' if first is None or earliest is None else round((first-earliest)/1e6,6)))
    return coverage,events


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('registry','interactions','archives','output'):p.add_argument(name,type=Path)
    a=p.parse_args()
    pairs=selected(a.registry,a.interactions)
    a.output.mkdir(parents=True,exist_ok=True)
    with ThreadPoolExecutor(3) as pool:
        data=list(pool.map(summarize,[(a.archives,obj,meta) for obj,meta in pairs]))
    for filename,rows in [('rbo-wrench-samples.csv',[r for r,_ in data]),('rbo-change-thresholds.csv',[x for _,j in data for x in j])]:
        with (a.output/filename).open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=rows[0],lineterminator='\n')
            w.writeheader()
            w.writerows(rows)


if __name__=='__main__':
    main()
