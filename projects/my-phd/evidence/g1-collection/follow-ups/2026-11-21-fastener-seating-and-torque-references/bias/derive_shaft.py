"""Audit this release's shaft wrench, external force labels and orientation associations.

python derive_shaft.py data.tar.gz RAW_BAG_ARCHIVES_OR_METADATA_DIRECTORY OUTPUT_DIRECTORY
Input two may contain the four original ZIP archives, or metadata.yaml files extracted
from them preserving archive and run names. Requires NumPy, pandas and PyYAML.
"""
import argparse
import csv
import hashlib
import io
from pathlib import Path
import tarfile
from zipfile import ZipFile
import numpy as np
import pandas as pd
import yaml


def write_csv(path, rows):
    with path.open('w',newline='',encoding='utf-8') as f:
        wr=csv.DictWriter(f,fieldnames=rows[0],lineterminator='\n')
        wr.writeheader()
        wr.writerows(rows)


def list_metadata(folder):
    archives=['Free.zip','Palpation.zip','Traction.zip','Teleop_compressed.zip']
    for name in archives:
        file=folder/name
        if file.is_file():
            with ZipFile(file) as z:
                for path in z.namelist():
                    if path.endswith('/metadata.yaml') and '__MACOSX' not in path:
                        yield name,path,z.read(path)
        else:
            for meta in sorted(file.rglob('metadata.yaml')):
                yield name,str(meta.relative_to(file)),meta.read_bytes()


def describe_meta(data):
    info=yaml.safe_load(data)['rosbag2_bagfile_information']
    counts={t['topic_metadata']['name']:t['message_count'] for t in info['topics_with_message_count']}
    return info['duration']['nanoseconds'],counts


def rmse(residual):
    return round(float(np.sqrt(np.mean(np.sum(residual**2,axis=1)))),9)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('prepared',type=Path)
    p.add_argument('metadata_folder',type=Path)
    p.add_argument('out',type=Path)
    a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=True)
    meta={}
    for archive,path,data in list_metadata(a.metadata_folder):
        key=Path(path).parent.name
        assert key not in meta
        dur,counts=describe_meta(data)
        meta[key]=(dur,counts,archive,hashlib.sha256(data).hexdigest())
    sessions,heldout=[],[]
    free={}
    with tarfile.open(a.prepared,'r:*') as z:
        datafiles={Path(m.name).parent.name:m for m in z if m.name.endswith('.csv')}
        assert set(datafiles)==set(meta)
        for key,m in sorted(datafiles.items()):
            d=z.extractfile(m).read()
            frame=pd.read_csv(io.BytesIO(d),usecols=['fx','fy','fz','tx','ty','tz','ati_fx','ati_fy','ati_fz'])
            tau=frame[['tx','ty','tz']].to_numpy()
            force=frame[['fx','fy','fz']].to_numpy()
            ati=frame[['ati_fx','ati_fy','ati_fz']].to_numpy()
            assert np.isfinite(frame.to_numpy()).all()
            dur,c,archive,digest=meta[key]
            is_free=key.startswith('Free_') or '_F_' in key
            same_hex=(np.diff(np.column_stack([force,tau]),axis=0)==0).all(axis=1)
            stats=dict(bag=key,raw_archive=archive,metadata_sha256=digest,
                       csv_sha256=hashlib.sha256(d).hexdigest(),rows=len(tau),bag_duration_s=round(dur*1e-9,7),
                       named_free=int(is_free),ati_topic_listed=int('/ati_data' in c),ati_messages=c.get('/ati_data',0),
                       hex_messages=c.get('/HEX10/wrench',0),all_zero_ati_force_rows=int((ati==0).all(axis=1).sum()),
                       adjacent_identical_shaft_wrenches=int(same_hex.sum()),
                       shaft_force_norm_median_N=round(float(np.median(np.linalg.norm(force,axis=1))),6),
                       shaft_fz_below_minus_19N=int((force[:,2]<-19).sum()),
                       shaft_fz_above_plus_25N=int((force[:,2]>25).sum()),
                       shaft_fz_min_N=round(float(force[:,2].min()),6),shaft_fz_max_N=round(float(force[:,2].max()),6),
                       ati_force_norm_median_N=round(float(np.median(np.linalg.norm(ati,axis=1))),6),
                       shaft_torque_norm_median_native=round(float(np.median(np.linalg.norm(tau,axis=1))),8),
                       shaft_torque_norm_p95_native=round(float(np.percentile(np.linalg.norm(tau,axis=1),95)),8))
            sessions.append(stats)
            if is_free:
                aux=z.extractfile(m.name.removesuffix('.csv')+'.npz').read()
                stats['free_npz_sha256']=hashlib.sha256(aux).hexdigest()
                with np.load(io.BytesIO(aux),allow_pickle=False) as f:
                    rot=f['rotations'].astype(float)
                assert rot.shape==(len(frame),3,3)
                x=np.column_stack([np.ones(len(tau)),rot[:,:,2]])
                free[key]=(x,tau)
            else:
                stats['free_npz_sha256']=''
    auto=sorted(k for k in free if k.startswith('Free_'))
    for key,(x,y) in sorted(free.items()):
        training=[k for k in auto if k!=key]
        xt=np.concatenate([free[k][0] for k in training])
        yt=np.concatenate([free[k][1] for k in training])
        coef,_,rank,_=np.linalg.lstsq(xt,yt,rcond=None)
        heldout.append(dict(test_bag=key,training_bags='|'.join(training),training_rows=len(yt),
                            test_rows=len(y),design_rank=rank,
                            mean_baseline_vector_rmse_native=rmse(y-yt.mean(axis=0)),
                            orientation_proxy_vector_rmse_native=rmse(y-x@coef)))
    write_csv(a.out/'shaft-reference-coverage.csv',sessions)
    write_csv(a.out/'shaft-free-holdout.csv',heldout)


if __name__=='__main__':
    main()
