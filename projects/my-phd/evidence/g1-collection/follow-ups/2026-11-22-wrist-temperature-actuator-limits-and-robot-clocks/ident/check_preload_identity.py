"""Recompute the preload column identities on the two Darus-5160 releases of preload error.
python check_preload_identity.py output [--cache input-directory]
First run check_transmission.py to make the checked file manifest.
"""
import argparse
import csv
import hashlib
import io
from pathlib import Path
from urllib.request import urlopen
import numpy as np

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path);p.add_argument('--cache',type=Path)
    args=p.parse_args()
    rows=[]
    with (args.output/'transmission-files.csv').open() as meta:
        for f in csv.DictReader(meta):
            if f['series']!='5160' or f['file'] not in ('Fig_7_Preload_errors.tab','Fig_10_Compensation_validation_motion.tab'):continue
            cache=args.cache/('d5160-'+f['file']) if args.cache else None
            raw=cache.read_bytes() if cache and cache.exists() else urlopen(f['access_url'],timeout=60).read()
            assert hashlib.sha256(raw).hexdigest()==f['sha256']
            stream=io.BytesIO(raw);header=stream.readline().decode().strip().split(',')
            d=dict(zip(header,np.loadtxt(stream,delimiter=',',ndmin=2).T))
            half=(d['T_M2']-d['T_M1'])/2
            residual=d['e_pl']-(d['T_pl_d']-abs(half))
            rows.append(dict(file=f['file'],rows=len(half),T_pl_present=int('T_pl' in d),
                max_abs_stored_T_pl_minus_half_T2_minus_T1_Nm=np.max(abs(d['T_pl']-half)) if 'T_pl' in d else '',
                stored_T_pl_min_Nm=d['T_pl'].min() if 'T_pl' in d else '',
                stored_T_pl_max_Nm=d['T_pl'].max() if 'T_pl' in d else '',
                max_abs_e_pl_minus_target_minus_magnitude_of_half_difference_Nm=np.max(abs(residual)),
                rms_e_pl_minus_target_minus_magnitude_of_half_difference_Nm=np.sqrt(np.mean(residual**2))))
    assert len(rows)==2
    with (args.output/'preload-column-identity.csv').open('w',newline='') as fo:
        w=csv.DictWriter(fo,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
if __name__=='__main__':main()
