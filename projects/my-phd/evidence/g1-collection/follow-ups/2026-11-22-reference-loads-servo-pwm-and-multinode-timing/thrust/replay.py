"""Reproduce the static, dynamic and restrained-vehicle summaries.

python replay.py CACHE_DIR OUTPUT_DIR
Requires Python 3, numpy, pandas and openpyxl. Create both output paths or allow
this script to create them. ZIP range reads need a server supporting HTTP 206.
"""
import csv
import hashlib
import io
import json
from pathlib import Path
import struct
import sys
import time
from urllib.request import Request, urlopen
import zipfile
import zlib

import numpy as np
from openpyxl import load_workbook
import pandas as pd

HERE = Path(__file__).resolve().parent
BLUE = 'https://cad.bluerobotics.com/'
MATH = 'https://www.mathworks.com/matlabcentral/mlc-downloads/downloads/submissions/65919/versions/2/download/zip'
FILES = {
    'T200.xlsx': (BLUE + 'T200-Public-Performance-Data-10-20V-September-2019.xlsx', '1399b76df7a176cfbb08760c11731199053336e7d92182dece11824c73285085'),
    'T500.xlsx': (BLUE + 'T500-Public-Performance-Data-12-24V-August-2022.xlsx', '52b5c5c49eb7a01bdb3acd137f0940e85a358fe730b307485431b14142842d9f'),
    'mw2.zip': (MATH, 'd9f4e850afb51bf97d86587c5b2790e0c46c82d3dc5098618f1fbfab190d9f6b'),
}
ARCHIVES = {
    'edin': ('https://datashare.ed.ac.uk/server/api/core/bitstreams/b19818b2-6efa-460d-997d-efa9ce8dde00/content', 1101302360),
    'rov': ('https://zenodo.org/records/15976877/files/rov_tether_dataset.zip', 224135111),
}

def get(url, bounds=None):
    headers = {'User-Agent': 'public evidence directory/1'}
    if bounds:
        start, end, size = bounds
        url += '?g1range=%d-%d' % (start, end)
        headers['Range'] = 'bytes=%d-%d' % (start, end)
    for attempt in range(3):
        try:
            with urlopen(Request(url, headers=headers), timeout=45) as response:
                if bounds:
                    assert response.status == 206 and response.headers['Content-Range'] == 'bytes %d-%d/%d' % bounds
                return response.read()
        except OSError:
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)

def cached(path, digest, reader):
    if path.exists():
        data = path.read_bytes()
    else:
        data = reader()
        assert hashlib.sha256(data).hexdigest() == digest, path
        path.write_bytes(data)
    assert hashlib.sha256(data).hexdigest() == digest, path
    return path

def retrieve_member(record):
    url, size = ARCHIVES[record['source']]
    h = record['header_offset']
    head = get(url, (h, h + 29, size))
    assert head[:4] == b'PK\x03\x04'
    name_len, extra = struct.unpack_from('<HH', head, 26)
    start = h + 30 + name_len + extra
    compressed = get(url, (start, start + record['compressed_bytes'] - 1, size))
    assert record['compression'] == 8
    data = zlib.decompress(compressed, -15)
    assert len(data) == record['size'] and '%08x' % zlib.crc32(data) == record['crc32']
    return data

def write_csv(out, name, rows):
    with (out / name).open('w', newline='') as f:
        w = csv.DictWriter(f, rows[0].keys(), lineterminator='\n')
        w.writeheader()
        w.writerows(rows)

def static(cache, out):
    records = []
    for model in ['T200', 'T500']:
        book = load_workbook(cache / (model + '.xlsx'), read_only=True, data_only=True)
        for sheet in book.worksheets[1:]:
            a = np.array([r[:7] for r in sheet.values if isinstance(r[0], (float, int))], dtype=float)
            pwm, rpm, force = a[:,0], a[:,1], a[:,5]
            assert np.array_equal(pwm, np.arange(1100, 1901, 4))
            stopped = pwm[(rpm == 0) & (force == 0)]
            assert np.all(np.diff(stopped) == 4)
            records.append(dict(model=model, sheet=sheet.title, points=len(a), reverse_1100_kgf=round(force[0],6), forward_1900_kgf=round(force[-1],6), positive_to_abs_negative_endpoint_ratio=round(force[-1] / abs(force[0]),6), published_zero_low_us=int(stopped.min()), published_zero_high_us=int(stopped.max()), published_zero_points=len(stopped)))
        book.close()
    write_csv(out, 'static-voltage-sheets.csv', records)

def dynamic(cache, out):
    records = []
    with zipfile.ZipFile(cache / 'mw2.zip') as z:
        for name in sorted(z.namelist()):
            if not name.endswith('.csv'):
                continue
            data=z.read(name)
            frame=pd.read_csv(io.BytesIO(data))
            t,p,f = frame.to_numpy().T
            assert np.isfinite(frame).all().all() and np.allclose(np.diff(t), .002)
            records.append(dict(member=name,sha256=hashlib.sha256(data).hexdigest(),rows=len(t),first_s=t[0],last_s=t[-1],interval_ms=2,command_min_us=int(p.min()),command_max_us=int(p.max()),distinct_command_values=len(np.unique(p)),force_min_lb=f.min(),force_median_lb=np.median(f),force_max_lb=f.max(),negative_force_samples=int((f<0).sum())))
    write_csv(out, 'dynamic-force-files.csv', records)

def restrained(cache, out):
    commands = ['still','forward','backward','left','right','upwards','downwards','yaw left','yaw right','forward transient','backward transient','left transient','right transient','upwards transient','downwards transient','yaw left transient','yaw right transient','still']
    records=[]
    for i,cmd in enumerate(commands,1):
        stem='Mot%02d_CaptureTime.txt' % i
        def load(kind):
            source = cache/('edin_'+kind+'_'+stem)
            if (i, kind) == (17, 'RD'):
                lines = source.read_text().splitlines()
                for line_no in [6170,6171,6172,6173,6174,6175,6499,6500]:
                    fields = lines[line_no-1].split()
                    assert len(fields)==40 and fields[2:5]==['NaN','d','NaN']
                    del fields[3]
                    lines[line_no-1]=' '.join(fields)
                return pd.read_csv(io.StringIO('\n'.join(lines)),sep=r'\s+',skiprows=[1])
            return pd.read_csv(source,sep=r'\s+',skiprows=[1])
        raw,proc=load('RD'),load('PD')
        assert np.array_equal(raw.time,proc.time)
        load_cols=['LC%d' % j for j in range(1,9)]
        record=dict(run='Mot%02d'%i,condition_table_5=cmd,rows=len(raw),paired_time_points=True,first_s=raw.time.iloc[0],last_s=raw.time.iloc[-1],time_step_median_s=round(raw.time.diff().median(),6),complete_raw_load_rows=raw[load_cols].notna().all(axis=1).sum())
        for axis in 'xyz':
            fields=['F%s%d' % (axis,j) for j in range(1,9)]
            f=proc[fields].sum(axis=1,min_count=8).dropna()
            record.update({axis+'_rows':len(f),axis+'_mean_net_tether_component_N':round(f.mean(),5),axis+'_p05_N':round(f.quantile(.05),5),axis+'_p95_N':round(f.quantile(.95),5)})
        records.append(record)
    write_csv(out, 'restrained-runs.csv', records)

def tether(cache, out):
    rows=[]
    for n in ['rc-in','rc-out','qtm_rov','tension']:
        d=pd.read_csv(cache/('rov_'+n+'.csv'))
        assert d.time.is_monotonic_increasing
        cs=d.columns[1:].tolist()
        if n.startswith('rc-'):
            cs=['channel%d'%i for i in range(1,7)]
        elif n=='qtm_rov':
            cs=['rov_origin_'+t for t in 'xyz']
        rows.append(dict(member=n+'.csv',rows=len(d),selected_channels=' | '.join(cs),complete_selected_rows=int(d[cs].notna().all(axis=1).sum()),first_s=d.time.iloc[0],last_s=d.time.iloc[-1],median_dt_s=round(d.time.diff().median(),8),duplicate_time_steps=int((d.time.diff()==0).sum())))
    write_csv(out, 'tether-streams.csv', rows)

if __name__=='__main__':
    cache,out=map(Path,sys.argv[1:3])
    for p in [cache,out]:
        p.mkdir(parents=True,exist_ok=True)
    for n,(url,digest) in FILES.items():
        cached(cache/n,digest,lambda: get(url))
    for rec in json.loads((HERE/'selected-members.json').read_text()):
        dst=cache/(rec['source']+'_'+Path(rec['path']).name)
        cached(dst,rec['sha256'],lambda: retrieve_member(rec))
    static(cache,out)
    dynamic(cache,out)
    restrained(cache,out)
    tether(cache,out)

