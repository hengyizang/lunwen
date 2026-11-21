"""Read deterministic complete-record windows from all five stored (uncompressed) ZIP members.
python derive_ethercat_motion.py LUM_TII_reproducibility.zip CACHE OUT --fetch
Later runs can use the same cache offline.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import csv
import hashlib
import json
from pathlib import Path
import struct
from urllib.request import Request, urlopen
from zipfile import ZipFile

import numpy as np

URL = 'https://zenodo.org/api/records/23652951/files/LUM_TII_motion_logs.zip/content'
SIZE = 3476308532
WIDTH = 4096


def acquire(root, start, size, fetch):
    path = root / f'{start}_{size}.bin'
    if not path.is_file() and fetch:
        end = start + size - 1
        span = f'{start}-{end}'
        req = Request(URL + '?range=' + span, headers={'Range':'bytes=' + span})
        with urlopen(req, timeout=50) as response:
            if response.status != 206 or response.getheader('Content-Range') != f'bytes {span}/{SIZE}':
                raise ValueError('Range unsupported')
            path.write_bytes(response.read())
    blob = path.read_bytes()
    if len(blob) != size:
        raise ValueError('Incomplete range')
    return blob


def windows(root, code, fetch):
    tail = acquire(root, SIZE-128, 128, fetch)
    end = struct.unpack_from('<4s4H2IH',tail,tail.rindex(b'PK\x05\x06'))
    central = acquire(root, end[-2], end[-3], fetch)
    offset = 0
    tasks = []
    while offset < len(central):
        h = struct.unpack_from('<4s6H3I5H2I',central,offset)
        if h[0] != b'PK\x01\x02' or h[4] != 0:
            raise ValueError('Expected a stored ZIP member')
        nlen, extra, comment = h[10:13]
        name = central[offset+46:offset+46+nlen].decode()
        size = h[9]
        if size == 0xffffffff:
            fields = central[offset+46+nlen:offset+46+nlen+extra]
            pos = 0
            while pos < len(fields):
                marker, length = struct.unpack_from('<HH',fields,pos)
                if marker == 1:
                    size, = struct.unpack_from('<Q',fields,pos+4)
                    break
                pos += 4 + length
        local = acquire(root, h[-1], 30+nlen, fetch)
        fn, ex = struct.unpack_from('<HH',local,26)
        if local[:4]!=b'PK\x03\x04' or local[30:30+fn].decode()!=name:
            raise ValueError('Local ZIP header mismatch')
        data_start = h[-1] + 30 + fn + ex
        meta = json.loads(code.read(name.replace('run_0001.bin','run_summary_0001.json')))
        records = size//64
        if records*64 != size or meta['nCyclesWritten'] != records:
            raise ValueError('Run count differs from published sidecar')
        for window in range(9):
            idx = (records-WIDTH)*window//8
            tasks.append((name,records,idx,window,data_start+64*idx,meta['v_mm_s']))
        offset += 46+nlen+extra+comment
    if len(tasks) != 9*end[4]:
        raise ValueError('Invalid member count')
    return tasks


def summarize(task, root, fetch):
    name, total, idx, window, pos, speed = task
    blob = acquire(root, pos, WIDTH*64, fetch)
    words = np.frombuffer(blob, dtype='<i4').reshape(-1,16)
    longs = np.frombuffer(blob,dtype='<i8').reshape(-1,8)
    ids, clock = longs[:,0], longs[:,1]
    target, actual = words[:,4].astype(np.int64), words[:,5].astype(np.int64)
    # Use the pre-specified 26-cycle shift in RECORD_FORMAT.md. Require 26 consecutive
    # transitions, positive DC intervals, and nonconstant target motion in the window.
    clean = (np.diff(ids)==1) & (np.diff(clock)>0)
    eligible = np.lib.stride_tricks.sliding_window_view(clean,26).all(axis=1)
    moving = eligible & (target[26:]!=target[:-26])
    current_error = np.abs(target[26:]-actual[26:])[moving]
    lagged_error = np.abs(target[:-26]-actual[26:])[moving]
    return dict(member=name, nominal_speed_mm_s=speed,total_archived_records=total, window=window,
                first_offset_record=idx, sample_records=WIDTH,byte_begin=pos,bytes=len(blob),
                sha256=hashlib.sha256(blob).hexdigest(),first_cycle=ids[0],last_cycle=ids[-1],
                nonconsecutive_index_transitions=int((np.diff(ids)!=1).sum()),
                positive_contiguous_26_cycle_windows=int(eligible.sum()),
                with_net_target_motion=int(moving.sum()),
                median_abs_unshifted_error_counts=round(float(np.median(current_error)),2) if moving.any() else '',
                median_abs_lag26_error_counts=round(float(np.median(lagged_error)),2) if moving.any() else '',
                strictly_smaller_error_after_lag26=int((lagged_error<current_error).sum()),
                equal_error_after_lag26=int((lagged_error==current_error).sum()))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('code',type=Path)
    p.add_argument('cache',type=Path)
    p.add_argument('output',type=Path)
    p.add_argument('--fetch',action='store_true')
    args=p.parse_args()
    args.cache.mkdir(parents=True,exist_ok=True)
    args.output.mkdir(parents=True,exist_ok=True)
    with ZipFile(args.code) as z:
        tasks=windows(args.cache,z,args.fetch)
    with ThreadPoolExecutor(4) as pool:
        rows=list(pool.map(lambda t:summarize(t,args.cache,args.fetch),tasks))
    with (args.output/'ethercat-motion-windows.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=rows[0],lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


if __name__=='__main__':
    main()
