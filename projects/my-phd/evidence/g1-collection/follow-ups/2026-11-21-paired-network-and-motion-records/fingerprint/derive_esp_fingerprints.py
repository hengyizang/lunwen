"""Audit released time axes, static location repeats and per-location held-out Wi-Fi FTM.

Usage: python derive_esp_fingerprints.py ESP32C3_WiFi_FTM_RSSI.zip OUT   (NumPy).
"""
from argparse import ArgumentParser
import csv
import hashlib
import io
from pathlib import Path
from zipfile import ZipFile
import numpy as np


def number(value):
    return round(float(value),7)


def save(path, items):
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=items[0],lineterminator='\n')
        w.writeheader()
        w.writerows(items)


def collect(z, name):
    raw=z.read(name)
    mat=np.loadtxt(io.BytesIO(raw),delimiter=',')
    campaign=Path(name).parent.name
    split=Path(name).stem.split('_')[0]
    times=mat[:,0]
    xy=mat[:,1:3]
    # Day 1 has only eight timing channels. Remaining files interleave FTM and RSSI.
    if mat.shape[1] not in (11,19) or not np.isfinite(mat).all():raise ValueError('Unexpected columns or nonfinite features')
    ft=mat[:,3:] if mat.shape[1]==11 else mat[:,3::2]
    breaks=np.flatnonzero(np.any(xy[1:]!=xy[:-1],axis=1))+1
    blocks=np.split(np.arange(len(mat)),breaks)
    distinct=len(np.unique(xy,axis=0))
    if distinct!=len(blocks):raise ValueError('Position revisited inside release split')
    position=[]
    site_features=[]
    for index,idx in enumerate(blocks,1):
        sub=ft[idx]
        delta_t=np.rint(np.diff(times[idx])*1e6).astype(np.int64)
        if len(idx)<2 or np.any(delta_t<=0):raise ValueError('Unexpected within-site time sequence')
        both_equal=np.all(sub[1:]==sub[:-1],axis=1)
        n_changed=np.sum(sub[1:]!=sub[:-1],axis=1)
        position.append(dict(campaign=campaign,split=split,position_block=index,rows=len(idx),
           first_local_s=number(times[idx[0]]),last_local_s=number(times[idx[-1]]),
           positive_intervals=len(delta_t),intervals_10ms=int((delta_t==10000).sum()),
           intervals_20ms=int((delta_t==20000).sum()),min_delta_ms=number(delta_t.min()/1000),
           max_delta_ms=number(delta_t.max()/1000),all_eight_ftm_unchanged=int(both_equal.sum()),
           exactly_one_ftm_changed=int((n_changed==1).sum()),all_eight_ftm_changed=int((n_changed==8).sum())))
        site_features.append((xy[idx[0]],np.median(sub,axis=0)))
    info=dict(campaign=campaign,split=split,archive_member=name,member_sha256=hashlib.sha256(raw).hexdigest(),
       rows=len(mat),columns=mat.shape[1],ftm_channels=ft.shape[1],rssi_channels=mat.shape[1]-11,
       distinct_positions=distinct,strict_time_reversals_between_positions=int((times[breaks]<times[breaks-1]).sum()),
       equal_time_at_position_switch=int((times[breaks]==times[breaks-1]).sum()),continuous_within_position_intervals=len(mat)-len(blocks),
       all_eight_ftm_unchanged=sum(x['all_eight_ftm_unchanged'] for x in position),
       ftm_min_as_stored=number(ft.min()),ftm_max_as_stored=number(ft.max()))
    return info,position,site_features


def compare(train,test,site):
    coords=np.array([point for point,_ in train]);features=np.array([vec for _,vec in train])
    # Each training position contributes once to the per-channel scale, irrespective of dwell length.
    scale=np.quantile(features,.75,axis=0)-np.quantile(features,.25,axis=0)
    if np.any(scale<=0):raise ValueError('Unusable training channel scale')
    out=[]
    for i,(xy,vec) in enumerate(test,1):
        geometry=np.linalg.norm(coords-xy,axis=1)
        dist=np.linalg.norm((features-vec)/scale,axis=1)
        choices=np.flatnonzero(dist==dist.min())
        if len(choices)!=1:raise ValueError('Feature-space ties need a policy')
        best=int(choices[0])
        out.append(dict(campaign=site,test_position=i,training_positions=len(coords),
            coincident_training_coordinates=int((geometry==0).sum()),
            nearest_training_coordinate_m=number(geometry.min()),ftm_selected_training_position=best+1,
            normalized_ftm_feature_distance=number(dist[best]),
            ftm_nearest_fingerprint_position_error_m=number(geometry[best])))
    return out


def main():
    p=ArgumentParser(description=__doc__);p.add_argument('zip',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    results,sites,heldout=[],[],[]
    pairs={}
    with ZipFile(a.zip) as z:
        for name in sorted(k for k in z.namelist() if k.endswith('.csv')):
            result,position,features=collect(z,name)
            results.append(result);sites.extend(position)
            pairs.setdefault(result['campaign'],{})[result['split']]=features
    for campaign,sets in pairs.items():
        if 'TEST' in sets:heldout.extend(compare(sets['TRAIN'],sets['TEST'],campaign))
    a.output.mkdir(parents=True,exist_ok=True)
    for name,items in [('esp32-files',results),('esp32-position-blocks',sites),('esp32-heldout-locations',heldout)]:
        save(a.output/(name+'.csv'),items)


if __name__=='__main__':
    main()
