"""Compare within-platform fits to leave-one-platform-out transfer on the same test rows.

Usage: python derive_transfer.py FETCH_ROOT OUTPUT_DIRECTORY
Uses only the six complete fixed ZIPs. SHA-256 must match their upstream LFS receipt.
For each held-out platform, segment number % 5 == 0 selects its exclusive test set.
The within-platform fit uses the other segments of that platform. The transfer fit
uses non-test segments of the other five platforms, pooled with equal weight per
eligible row. Both are ordinary least squares with the same five predictors.
For each nonempty test segment we also compare its two RMSEs with equal weight
per segment. Segment percentiles describe dispersion, not sampling uncertainty.
Segment-level separation does not imply disjoint drivers, routes or dates.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import pandas as pd

PLATFORMS=('GENESIS_G70_2018','HYUNDAI_IONIQ_ELECTRIC_LIMITED_2019','KIA_SELTOS_2021',
           'KIA_SPORTAGE_HYBRID_5TH_GEN','KIA_STINGER_2022','TOYOTA_AVALON_HYBRID_2022')
INPUTS=('steer','steerFiltered')
TARGETS=('latAccelSteeringAngle','latAccelLocalizer')
COLUMNS=[*INPUTS,*TARGETS,'t','roll','vEgo','latActive','steeringPressed','latAccelDesired']


def pooled(parts):
    return tuple(sum(p[j] for p in parts) for j in range(4))


def summarize(root):
    training,testing={},{}
    for platform in PLATFORMS:
        path=root/'steer'/(platform+'.zip')
        index=json.loads((root/'steer-index'/platform/'index.json').read_text())
        with path.open('rb') as stream:
            assert index['complete_sha_checked'] and hashlib.file_digest(stream,'sha256').hexdigest()==index['lfs_sha256']
        batches={i:[] for i in INPUTS}
        with ZipFile(path) as archive:
            for name in sorted(n for n in archive.namelist() if n.endswith('.csv')):
                with archive.open(name) as source:
                    frame=pd.read_csv(source,usecols=COLUMNS)
                assert frame.latActive.dtype==bool and frame.steeringPressed.dtype==bool
                use=frame.latActive & ~frame.steeringPressed & np.isfinite(frame[COLUMNS]).all(axis=1)
                d=frame.loc[use]
                if d.empty:
                    continue
                y=d[list(TARGETS)].to_numpy()
                yy=(y*y).sum(axis=0)
                test=int(Path(name).stem)%5==0
                for i in INPUTS:
                    u=d[i].to_numpy()
                    x=np.column_stack((np.ones(len(d)),u,u*abs(u),u*d.vEgo/20,d.roll))
                    moments=(len(d),x.T@x,x.T@y,yy)
                    if test:
                        testing.setdefault((platform,i),[]).append(moments)
                    else:
                        batches[i].append(moments)
        training.update({(platform,i):(len(batches[i]),pooled(batches[i])) for i in INPUTS})
    return training,testing


def coefficients(s):
    assert np.linalg.matrix_rank(s[1])==5
    return np.linalg.lstsq(s[1],s[2],rcond=None)[0]


def rmse(s,beta):
    err=s[3]-2*(beta*s[2]).sum(axis=0)+(beta*(s[1]@beta)).sum(axis=0)
    assert min(err)>-1e-7
    return np.sqrt(np.maximum(err,0)/s[0])


def main(root,out):
    training,testing=summarize(root)
    rows=[]
    for platform in PLATFORMS:
        for i in INPUTS:
            nlocal,local=training[platform,i]
            others=[training[p,i] for p in PLATFORMS if p!=platform]
            transfer=pooled([s for _,s in others])
            mlocal=coefficients(local);mxfer=coefficients(transfer)
            segments=testing[platform,i]
            overall=pooled(segments)
            local_error=rmse(overall,mlocal); xfer_error=rmse(overall,mxfer)
            deltas=np.array([rmse(s,mxfer)-rmse(s,mlocal) for s in segments])
            for j,target in enumerate(TARGETS):
                q=np.percentile(deltas[:,j],[10,50,90])
                rows.append(dict(test_platform=platform,input=i,target=target,
                    within_train_segments=nlocal,within_train_rows=local[0],
                    other_five_train_segments=sum(n for n,_ in others),other_five_train_rows=transfer[0],
                    test_segments=len(segments),test_rows=overall[0],
                    within_rmse_m_s2=round(local_error[j],8),other_five_rmse_m_s2=round(xfer_error[j],8),
                    transfer_minus_within_rmse_m_s2=round(xfer_error[j]-local_error[j],8),
                    transfer_over_within_rmse=round(xfer_error[j]/local_error[j],8),
                    test_segments_worse_after_transfer=int(sum(deltas[:,j]>0)),
                    segment_delta_p10_m_s2=round(q[0],8),segment_delta_median_m_s2=round(q[1],8),
                    segment_delta_p90_m_s2=round(q[2],8)))
    out.mkdir(exist_ok=True,parents=True)
    with (out/'road-transfer.csv').open('w',newline='') as stream:
        w=csv.DictWriter(stream,fieldnames=rows[0],lineterminator='\n')
        w.writeheader();w.writerows(rows)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input',type=Path);parser.add_argument('output',type=Path)
    args=parser.parse_args();main(args.input,args.output)
