"""Audit Zenodo 23874408 in memory. Python 3, numpy, pandas. Optional cache holds original ZIPs."""
import argparse,csv,hashlib,io,json,math,time
from pathlib import Path
from urllib.request import urlopen
from zipfile import ZipFile
import numpy as np
import pandas as pd

BASE='https://zenodo.org/api/records/23874408'
def readfile(f,cache):
    if cache and (cache/f['key']).is_file(): data=(cache/f['key']).read_bytes()
    else:
        for attempt in range(3):
            try:
                with urlopen(f['links']['self'],timeout=180) as r: data=r.read()
                break
            except OSError:
                if attempt==2:raise
                time.sleep(3)
    assert len(data)==f['size'] and 'md5:'+hashlib.md5(data).hexdigest()==f['checksum'],f['key']
    return data

def table(what):return list(csv.DictReader(io.StringIO(what.decode('utf-8-sig'))))
def write(root,n,items):
    with (root/n).open('w',newline='') as f:
        w=csv.DictWriter(f,items[0],lineterminator='\n');w.writeheader();w.writerows(items)

def runs(z,path,meta,reported):
    names=['position','witness','actual','offset','packed']
    f=pd.read_csv(z.open(path),header=None,usecols=[1,3,4,8,17],names=names)
    assert np.isfinite(f[names].to_numpy()).all()
    p=f['packed'].to_numpy(dtype=np.int64);legacy=meta['layout']!='v2'
    number=((p>>16)&(7 if legacy else 15))+1
    state=(p>>(19 if legacy else 20))&(1 if legacy else 7)
    step=.005 if meta['layout']=='old_sweep' else .001
    t=(p & 65535)*step;sel=(t>=float(meta['analysis_start_s']))&(t<float(meta['analysis_end_s']))
    results=[]
    for run in sorted(set(number[sel])):
        pick=(number==run)&sel;tt=t[pick];conditions=np.unique(state[pick]);assert len(conditions)==1
        condition=('C0','C2-H','C3')[conditions[0]]
        current=f.actual[pick].to_numpy();echo=f.offset[pick].to_numpy();pos=f.position[pick].to_numpy();wit=f.witness[pick].to_numpy()
        if meta['method']=='sweep':cycles=.25*tt+.5*((1/.65-.25)/300)*tt**2
        else:cycles=tt/float(meta['period_s'])
        target=10+5*np.sin(2*np.pi*cycles)
        reconstructed=current-5.4*echo;rmse=np.sqrt(np.mean((target-pos)**2))
        official=reported[meta['stable_id'],int(run)]
        assert condition==official['condition'] and len(tt)==int(official['n_samples'])
        results.append(dict(file_id=meta['stable_id'],run=int(run),condition=condition,rows=len(tt),offset_nonzero_rows=int(np.count_nonzero(echo)),measured_current_min_mA=float(current.min()),measured_current_max_mA=float(current.max()),offset_min_count=int(echo.min()),offset_max_count=int(echo.max()),offset_steps=int(np.count_nonzero(np.diff(echo))),current_sd_mA=round(float(current.std()),8),reconstructed_residual_sd_mA=round(float(reconstructed.std()),8),internal_witness_min_native=float(wit.min()),internal_witness_max_native=float(wit.max()),internal_witness_unique=int(np.unique(wit).size),tracking_rmse_deg=round(float(rmse),10),abs_rmse_difference_published_deg=round(abs(rmse-float(official['rmse_deg'])),12),abs_current_sd_difference_published_mA=round(abs(current.std()-float(official['measured_total_current_sd_ma'])),10)))
    return results
def analyze(output,cache):
    output.mkdir(parents=True,exist_ok=True)
    record=json.load(urlopen(BASE,timeout=40));keys={f['key']:f for f in record['files']}
    with ZipFile(io.BytesIO(readfile(keys['06_code_metadata_figures.zip'],cache))) as z:
        manifest={r['relative_path']:r for r in table(z.read('metadata/raw_files.csv'))}
        cam={r['relative_path']:r for r in table(z.read('metadata/electronic_cam_manifest.csv'))}
    with ZipFile(io.BytesIO(readfile(keys['05_derived_results.zip'],cache))) as z:
        reported={(r['stable_id'],int(r['run'])):r for r in table(z.read('data/derived/electronic_cam/run_metrics.csv'))}
    out=[];measurements=[];seen=set()
    for key in sorted(k for k in keys if k.endswith('_raw.zip')):
        print('Reading',key,flush=True)
        with ZipFile(io.BytesIO(readfile(keys[key],cache))) as z:
            for name in z.namelist():
                if name.endswith('/'):continue
                # Filenames use the release's fully qualified relative paths.
                r=manifest[name];h=hashlib.sha256();size=0;lines=0;tail=b''
                with z.open(name) as f:
                    for block in iter(lambda:f.read(1<<20),b''):
                        h.update(block);size+=len(block);lines+=block.count(b'\n');tail=block[-1:]
                lines+=int(tail not in (b'\n',b''))
                assert size==int(r['bytes']) and h.hexdigest()==r['sha256'] and name not in seen
                seen.add(name)
                out.append(dict(file_id=r['stable_id'],group=r['experiment_group'],release_archive=key,source_sha256=h.hexdigest(),bytes=size,rows_by_newline=lines,manifest_rows=int(r['rows_including_possible_bom_header']),same_row_count=int(lines==int(r['rows_including_possible_bom_header']))))
                if name in cam:measurements.extend(runs(z,name,cam[name],reported))
    assert seen==manifest.keys() and len(measurements)==len(reported)
    write(output,'harmonic-raw-verification.csv',out);write(output,'harmonic-cam-windows.csv',measurements)
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path);p.add_argument('--cache',type=Path);a=p.parse_args();analyze(a.output,a.cache)
