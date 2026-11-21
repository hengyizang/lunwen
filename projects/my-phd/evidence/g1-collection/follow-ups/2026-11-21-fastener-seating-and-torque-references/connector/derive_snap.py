"""Usage: python derive_snap.py DS.04.CERTH.SnapFitForceProfiles.zip OUTPUT. Needs NumPy and SciPy."""
import argparse
import csv
import hashlib
import io
from pathlib import Path
from zipfile import ZipFile
import numpy as np
from scipy.io import loadmat


def write(path, rows):
    with path.open('w', newline='', encoding='utf-8') as stream:
        writer=csv.DictWriter(stream,fieldnames=rows[0],lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def first_array(archive, name):
    arrays=[v for k,v in loadmat(io.BytesIO(archive.read(name))).items() if not k.startswith('_')]
    data,=arrays
    return data


def summarize(archive):
    rows=[]
    for name in sorted(n for n in archive.namelist() if n.endswith('.mat') and 'Labels' not in n):
        signals=first_array(archive,name)
        labels=first_array(archive,name.replace('.mat','_Labels.mat')).reshape(-1)
        fields=signals.dtype.names
        if len(labels)!=len(fields):
            raise ValueError(f'Label count differs from signal count in {name}')
        for i,(field,label) in enumerate(zip(fields,labels),1):
            force=signals[field][0,0].reshape(-1)
            if not len(force) or not np.all(np.isfinite(force)):
                raise ValueError(field)
            # Trial labels occupy an unkeyed vector. Pair with the original MAT struct order.
            rows.append(dict(geometry=name.split('/')[0].split()[0], split='Training' if 'Training' in name else 'Testing',
                             member=name,mat_field=field,field_order=i,numeric_label=int(label),
                             samples=len(force),numeric_sha256=hashlib.sha256(force.astype('<f8').tobytes()).hexdigest(),
                             first_value=force[0],last_value=force[-1],peak_to_peak=np.ptp(force),
                             max_prior_peak_drop=np.max(np.maximum.accumulate(force)-force),
                             peak_less_tail_median=np.max(force)-np.median(force[-max(1,len(force)//10):])))
    return rows


def evaluate(rows):
    result=[]
    for geometry in sorted({r['geometry'] for r in rows}):
        train=[r for r in rows if r['geometry']==geometry and r['split']=='Training']
        test=[r for r in rows if r['geometry']==geometry and r['split']=='Testing']
        y=np.array([r['numeric_label'] for r in train])
        actual=np.array([r['numeric_label'] for r in test])
        for feature in ('samples','peak_to_peak','max_prior_peak_drop','peak_less_tail_median'):
            x=np.array([r[feature] for r in train])
            levels=np.unique(x)
            # Include the two constant classifiers. Ties favor ascending direction then lowest threshold.
            cuts=np.r_[np.nextafter(float(levels[0]),-np.inf),(levels[:-1]+levels[1:])/2,np.nextafter(float(levels[-1]),np.inf)]
            best=-1
            held=np.array([r[feature] for r in test])
            for direction in (1,-1):
                for threshold in cuts:
                    yp=direction*x>direction*threshold
                    score=(yp[y==1].mean()+(~yp[y==0]).mean())/2
                    if score>best:
                        best,way,t=score,direction,threshold
            pred=way*held>way*t
            result.append(dict(geometry=geometry,feature=feature,train_trials=len(train),test_trials=len(test),
                               predicts_numeric_one='above' if way==1 else 'below',threshold=t,
                               train_balanced_accuracy=round(best,7),
                               true_0_pred_0=int(sum((actual==0)&~pred)),true_0_pred_1=int(sum((actual==0)&pred)),
                               true_1_pred_0=int(sum((actual==1)&~pred)),true_1_pred_1=int(sum((actual==1)&pred)),
                               test_balanced_accuracy=round((pred[actual==1].mean()+(~pred[actual==0]).mean())/2,7)))
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('archive',type=Path)
    p.add_argument('output',type=Path)
    a=p.parse_args()
    a.output.mkdir(exist_ok=True,parents=True)
    with ZipFile(a.archive) as archive:
        rows=summarize(archive)
    write(a.output/'snap-trials.csv',rows)
    write(a.output/'snap-heldout-features.csv',evaluate(rows))


if __name__=='__main__':
    main()
