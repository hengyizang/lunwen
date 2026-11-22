"""Summarize every archived USB visual-servo controller CSV from the pinned IBVS tree."""
import argparse
import csv
import hashlib
import io
import json
import math
import statistics
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import quote
from urllib.request import urlopen

REPO='RafieHanania/FYP-RoboticInsertion'
COMMIT='05ae5aa8d98ed40d373dba32914fe04d629ab5c8'
TREE='509d97b505017e5f6d7a977af1a62cb26750bcdb'
def csvout(path, rows):
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=rows[0],lineterminator='\n');w.writeheader();w.writerows(rows)
def main(cache,output):
    tree=json.load(urlopen('https://api.github.com/repos/'+REPO+'/git/trees/'+TREE+'?recursive=1'))
    assert tree['sha']==TREE and not tree['truncated']
    files=[e for e in tree['tree'] if e['type']=='blob' and e['path'].endswith('.csv') and e['path'].startswith(('data_analysis/', 'misc/controller_log.csv/'))]
    assert len(files)==77 and len({f['sha'] for f in files})==77
    def read(e):
        path=e['path'];c=cache/path if cache else None
        if c and c.is_file(): raw=c.read_bytes()
        else: raw=urlopen('https://raw.githubusercontent.com/'+REPO+'/'+COMMIT+'/'+quote(path),timeout=45).read()
        digest=hashlib.sha1(f'blob {len(raw)}\0'.encode()+raw).hexdigest()
        assert digest==e['sha']
        reader=csv.DictReader(io.StringIO(raw.decode('utf-8-sig')));rows=list(reader); fields=reader.fieldnames
        assert len(fields) in (25,38) and all(None not in r for r in rows)
        ts=[float(r['time']) for r in rows]
        valid=[r for r in rows if r['det_valid'].casefold()=='true']
        assert len(valid)+sum(r['det_valid'].casefold()=='false' for r in rows)==len(rows)
        nonzero=sum(any(float(r[k])!=0 for k in ('vx','vy','vz','wx','wy','wz')) for r in rows)
        stamps=[float(r['det_t']) for r in valid]
        delta=[(b-a)*1000 for a,b in zip(ts,ts[1:])]
        file_stats=dict(file=path,git_blob_sha1=digest,bytes=len(raw),columns=len(fields),rows=len(rows),valid_detection_rows=len(valid),distinct_valid_detection_times=len(set(stamps)),nonzero_output_rows=nonzero,nonmonotone_or_repeated_logger_steps=sum(d<=0 for d in delta),median_logger_step_ms=round(statistics.median(delta),5) if delta else '')
        pairs=[]
        if len(fields)==38:
            for axis in 'xyz':
                pairs_in=[(float(r['v_tcp_'+axis]),float(r['v'+axis])) for r in rows if r['v_tcp_'+axis]!='']
                assert len(pairs_in)>0 and all(math.isfinite(x) and math.isfinite(y) for x,y in pairs_in)
                cap=max(abs(q) for _,q in pairs_in)
                mismatches=sum(abs(max(-cap,min(cap,x))-q)>1e-9 for x,q in pairs_in)
                pairs.append(dict(file=path,axis=axis,pairs=len(pairs_in),observed_max_abs_output=cap,raw_values_strictly_outside_observed_envelope=sum(abs(x)>cap+1e-9 for x,_ in pairs_in),output_different_from_raw=sum(abs(x-q)>1e-9 for x,q in pairs_in),clamp_at_observed_envelope_mismatches=mismatches))
        return file_stats,pairs
    with ThreadPoolExecutor(4) as pool:result=list(pool.map(read,files))
    csvout(output/'usb-controller-files.csv',[r for r,_ in result]);csvout(output/'usb-observed-clips.csv',[a for _,rs in result for a in rs])

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path);p.add_argument('--cache',type=Path)
    a=p.parse_args();main(a.cache,a.output)
