"""Audit the public real peg-teleoperation release with revision-pinned HTTP ranges.
Usage: python derive_tactile_timing.py OUTPUT_DIR ; dependencies numpy and pyarrow.
"""
import csv
import hashlib
import json
import tempfile
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import numpy as np
import pyarrow.parquet as pq

REPO = 'qingzhu-robotics/TacRich-Manip-LeRobot-teleoperation-insert-peg-cylinder'
REV = 'b788b5977287c5dea139d47b444f3e17dfd44077'
KEYS = ['observation.tactile','observation.timestamp','observation.source_timestamp_tactile','observation.source_timestamp_proprio','observation.source_timestamp_vision','index','episode_index','frame_index']

def fetch(url, first, last, size):
    request = urllib.request.Request(url+'?range='+str(first)+'-'+str(last),headers={'Range':f'bytes={first}-{last}'})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request,timeout=80) as response:
                data=response.read()
                if response.headers.get('Content-Range')!=f'bytes {first}-{last}/{size}' or len(data)!=last-first+1:
                    raise IOError('Incomplete byte range')
                return data
        except OSError:
            if attempt==2: raise
            time.sleep(2**attempt)

def shard(entry):
    path=entry['path'];size=entry['size']
    url='https://huggingface.co/datasets/'+REPO+'/resolve/'+REV+'/'+urllib.parse.quote(path)
    footer_start=size-65536
    tail=fetch(url,footer_start,size-1,size)
    assert tail[-4:]==b'PAR1' and int.from_bytes(tail[-8:-4],'little')<=65528
    with tempfile.TemporaryDirectory() as temp:
        file=Path(temp)/'partial.parquet'
        with file.open('wb') as f:
            f.write(b'PAR1');f.seek(footer_start);f.write(tail)
        q=pq.ParquetFile(file);spans=[]
        for g in range(q.metadata.num_row_groups):
            rg=q.metadata.row_group(g)
            for k in range(rg.num_columns):
                col=rg.column(k);name=col.path_in_schema.split('.list.')[0]
                if name not in KEYS:continue
                start=col.dictionary_page_offset if col.dictionary_page_offset is not None else col.data_page_offset
                spans.append((start,start+col.total_compressed_size))
        assert spans
        # Cover the selected column chunks and any intervening state data in one short range.
        lo=min(i[0] for i in spans);hi=max(i[1] for i in spans)-1
        payload=fetch(url,lo,hi,size)
        with file.open('r+b') as f:
            f.seek(lo);f.write(payload)
        table=q.read(columns=KEYS,use_threads=False)
        assert table.num_columns==len(KEYS)
        tex=table['observation.tactile'].combine_chunks()
        for _ in range(3):
            tex=tex.flatten()
        tactile=tex.to_numpy(zero_copy_only=False).reshape(table.num_rows,2,32*58)
        assert np.isfinite(tactile).all()
        result={k:table[k].to_numpy() for k in KEYS if k!='observation.tactile'}
        result['left_max']=np.max(np.abs(tactile[:,0,:]),axis=1)
        result['right_max']=np.max(np.abs(tactile[:,1,:]),axis=1)
        result['left_nonzero']=(tactile[:,0,:]!=0).sum(axis=1)
        result['right_nonzero']=(tactile[:,1,:]!=0).sum(axis=1)
        # A digest of each decoded full two-pad image allows consecutive identical maps to be counted across shards.
        result['map_hash']=np.array([hashlib.md5(np.ascontiguousarray(v).tobytes()).hexdigest() for v in tactile])
    receipt={'path':path,'source_bytes':size,'publisher_lfs_sha256':entry['lfs']['oid'],'rows':table.num_rows,'footer_start':footer_start,'footer_sha256':hashlib.sha256(tail).hexdigest(),'range_start':lo,'range_end_inclusive':hi,'range_sha256':hashlib.sha256(payload).hexdigest()}
    return result,receipt

def csvout(p,r):
    with p.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=r[0],lineterminator='\n');w.writeheader();w.writerows(r)

def main(out):
    api='https://huggingface.co/api/datasets/'+REPO+'/tree/'+REV+'/data?recursive=true&expand=false'
    files=[i for i in json.load(urllib.request.urlopen(api)) if i['type']=='file' and i['path'].endswith('.parquet')]
    assert len(files)==44
    with ThreadPoolExecutor(3) as pool:
        results=list(pool.map(shard,files))
    raw={k:np.concatenate([r[k] for r,_ in results]) for k in results[0][0]}
    order=raw['index'].argsort()
    t={k:v[order] for k,v in raw.items()};n=len(order)
    assert np.array_equal(t['index'],np.arange(n)) and n==109073
    outputs=[]
    for episode in np.unique(t['episode_index']):
        use=t['episode_index']==episode;g={k:v[use] for k,v in t.items()};count=int(use.sum())
        assert np.array_equal(g['frame_index'],np.arange(count))
        time0=g['observation.timestamp']; tt=g['observation.source_timestamp_tactile']; tp=g['observation.source_timestamp_proprio']; tv=g['observation.source_timestamp_vision']
        assert all(np.isfinite(x).all() for x in (time0,tt,tp,tv))
        delta=(tt-tv)*1000
        o=dict(episode=int(episode),frames=count,span_s=round(float(time0[-1]-time0[0]),6),tactile_minus_vision_median_ms=round(float(np.median(delta)),5),abs_tactile_minus_vision_p95_ms=round(float(np.quantile(np.abs(delta),.95)),5),abs_tactile_minus_vision_max_ms=round(float(np.abs(delta).max()),5),abs_tactile_minus_vision_gt_25ms=int((np.abs(delta)>25).sum()),tactile_timestamp_equals_aligned=int((tt==time0).sum()),proprio_timestamp_equals_aligned=int((tp==time0).sum()),vision_timestamp_equals_aligned=int((tv==time0).sum()),adjacent_tactile_timestamp_equal=int((np.diff(tt)==0).sum()),adjacent_vision_timestamp_equal=int((np.diff(tv)==0).sum()),adjacent_decoded_map_identical=int((g['map_hash'][1:]==g['map_hash'][:-1]).sum()))
        for side in ('left','right'):
            o[side+'_all_zero_frames']=int((g[side+'_nonzero']==0).sum())
            o[side+'_median_nonzero_taxels']=float(np.median(g[side+'_nonzero']))
            o[side+'_peak_abs_response_native']=round(float(g[side+'_max'].max()),6)
        outputs.append(o)
    assert len(outputs)==79
    csvout(out/'tacrich-episodes.csv',outputs);csvout(out/'tacrich-shards.csv',[v for _,v in results])

if __name__=='__main__':
    import sys
    main(Path(sys.argv[1]))
