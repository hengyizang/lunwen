"""Audit source target files against all split-ZIP entries and verify selected image/depth payloads.

python derive_feel.py ROOT OUT [--fetch]
ROOT has the three label CSVs, Hugging Face tree.json and the ZIP64 central.bin.
--fetch obtains one complete matching image/depth pair per observed split-membership pattern.
"""
import argparse
from collections import Counter,defaultdict
import csv
import hashlib
import io
from itertools import combinations
import json
from pathlib import Path
import struct
import numpy as np
from feel_zip import PARTS,fetch_range,load_member,read_directory


def write(out,name,rows):
    with (out/name).open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=rows[0],lineterminator='\n')
        w.writeheader()
        w.writerows(rows)


def central(raw,sizes):
    tail_file=raw/'tail.bin'
    if not tail_file.exists():
        tail_file.write_bytes(fetch_range(3,sizes[3]-256,sizes[3]-1,sizes))
    tail=tail_file.read_bytes()
    zip64=struct.unpack_from('<4sQ2H2I4Q',tail,tail.rindex(b'PK\x06\x06'))
    if zip64[4:6]!=(3,3):raise ValueError('Central directory starts on unexpected part')
    number,nbytes,begin=zip64[-3:]
    cd=raw/'central.bin'
    if not cd.exists():cd.write_bytes(fetch_range(3,begin,begin+nbytes-1,sizes))
    if cd.stat().st_size!=nbytes:raise ValueError('Partial directory')
    archive={}
    count=0
    for name,entry in read_directory(cd.read_bytes()):
        if name in archive:raise ValueError('Duplicate archive name: '+name)
        archive[name]=entry
        count+=1
    if count!=number:raise ValueError('Entry count differs from ZIP64 footer')
    return archive


def analyze(raw,out,allow_fetch):
    tree={row['path']:row for row in json.loads((raw/'tree.json').read_text())}
    sizes=[tree[n]['size'] for n in PARTS]
    archive=central(raw,sizes)
    labels=defaultdict(dict)
    paths={}
    split_rows=[]
    for split in ('train','val','test'):
        filename=f'TacForce_{split}_set.csv'
        data=(raw/filename).read_bytes()
        with io.StringIO(data.decode('utf-8-sig')) as f:rows=list(csv.DictReader(f))
        entries=[]
        sixes=[]
        for row in rows:
            tactile,depth=row['tactile'],row['depth']
            target=tuple(float(t) for t in row['FT'].split())
            if len(target)!=6 or not np.isfinite(target).all():raise ValueError('Invalid six-component label')
            if 'dataset/'+tactile not in archive or 'dataset/'+depth not in archive:raise ValueError('Path absent from archive')
            if tactile in paths and paths[tactile]!=depth:raise ValueError('Inconsistent depth path')
            paths[tactile]=depth
            old=labels[tactile].setdefault(split,target)
            if old!=target:raise ValueError('Conflicting repeated target inside split')
            entries.append(tactile)
            sixes.append(target)
        split_rows.append(dict(split=split,source_csv=filename,sha256=hashlib.sha256(data).hexdigest(),
                               rows=len(rows),unique_tactile_paths=len(set(entries)),extra_occurrences=len(entries)-len(set(entries)),
                               unique_depth_paths=len({paths[k] for k in entries}),
                               image_path_hits=len(entries),depth_path_hits=len(entries),
                               median_abs_fz_n=round(float(np.median(np.abs(np.asarray(sixes)[:,2]))),7)))
    patterns=defaultdict(list)
    for path,d in labels.items():patterns['+'.join(sorted(d))].append(path)
    pair_rows=[]
    for left,right in combinations(('train','val','test'),2):
        common=[v for v in labels.values() if left in v and right in v]
        pair_rows.append(dict(first_split=left,second_split=right,shared_unique_tactile_depth_pairs=len(common),
                              identical_six_number_labels=sum(v[left]==v[right] for v in common),
                              differing_six_number_labels=sum(v[left]!=v[right] for v in common)))
    examples=[]
    for pattern,keys in sorted(patterns.items()):
        path=min(keys)
        for modality,p in [('tactile',path),('depth',paths[path])]:
            name='dataset/'+p
            local=raw/'examples'/p
            info=archive[name]
            if allow_fetch and not local.is_file():
                local.parent.mkdir(parents=True,exist_ok=True)
                local.write_bytes(load_member(name,info,sizes))
            data=local.read_bytes()
            import zlib
            if len(data)!=info[3] or zlib.crc32(data)!=info[4]:raise ValueError('Sample fails CRC')
            if modality=='depth':
                value=np.load(io.BytesIO(data),allow_pickle=False)
                shape='x'.join(map(str,value.shape))
                dtype=str(value.dtype)
            else:
                if data[:8]!=b'\x89PNG\r\n\x1a\n' or data[12:16]!=b'IHDR':raise ValueError('Not PNG')
                width,height=struct.unpack('>II',data[16:24])
                shape=f'{height}x{width}'
                dtype='PNG'
            examples.append(dict(membership=pattern,unique_paths_with_membership=len(keys),modality=modality,
                                 sampled_archive_member=name,starting_part=PARTS[info[0]],raw_bytes=len(data),
                                 crc32=f'{info[4]:08x}',sha256=hashlib.sha256(data).hexdigest(),shape=shape,format_or_dtype=dtype))
    write(out,'feel-splits.csv',split_rows)
    write(out,'feel-split-intersections.csv',pair_rows)
    write(out,'feel-payload-checks.csv',examples)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('raw',type=Path)
    p.add_argument('output',type=Path)
    p.add_argument('--fetch',action='store_true')
    a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=True)
    analyze(a.raw,a.output,a.fetch)
