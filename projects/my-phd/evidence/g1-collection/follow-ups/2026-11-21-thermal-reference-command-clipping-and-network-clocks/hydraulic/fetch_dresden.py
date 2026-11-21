"""Fetch the test partitions and metadata from OPARA-151 into a sparse ZIP for analysis.
Usage: python fetch_dresden.py target.zip . Non-fetched training bytes are holes.
"""
import argparse
import hashlib
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.request import Request, urlopen
from zipfile import ZipFile

URL = 'https://opara.zih.tu-dresden.de/server/api/core/bitstreams/2ce1e46d-3017-4426-9487-f775c15b2e54/content'
SIZE = 554952233
CENTRAL = 554379274
CENTRAL_SHA256 = '6b0a20001ddb9596460e35cc9c87fbae13158d79969f47bbf095bf6cea0fedf5'

def fetch(start, stop):
    for attempt in range(3):
        req = Request(URL, headers={'Range': f'bytes={start}-{stop-1}'})
        try:
            with urlopen(req, timeout=80) as response:
                if response.headers.get('Content-Range') != f'bytes {start}-{stop-1}/{SIZE}':
                    raise ValueError('Server did not return the requested range')
                data = response.read()
                if len(data) != stop-start:
                    raise ValueError('Short range')
                return start, data
        except (OSError, ValueError):
            if attempt == 2:
                raise
            time.sleep(2**attempt)


def download(path):
    _, directory = fetch(CENTRAL, SIZE)
    if hashlib.sha256(directory).hexdigest() != CENTRAL_SHA256:
        raise ValueError('ZIP central directory and end record SHA-256 mismatch')
    with path.open('wb') as fh:
        fh.seek(CENTRAL)
        fh.write(directory)
    with ZipFile(path) as z:
        entries=sorted(z.infolist(),key=lambda e:e.header_offset)
    ranges=[]
    for i,e in enumerate(entries):
        if e.is_dir() or not ('/test_data/' in e.filename or e.filename.endswith(('.py','.txt'))):
            continue
        first=e.header_offset
        end=entries[i+1].header_offset if i+1<len(entries) else CENTRAL
        if ranges and first-ranges[-1][1] < 300 and end-ranges[-1][0] < 6*1024*1024:
            ranges[-1]=(ranges[-1][0],end)
        else:
            ranges.append((first,end))
    with path.open('r+b') as fh, ThreadPoolExecutor(5) as pool:
        for start,data in pool.map(lambda pair:fetch(*pair),ranges):
            fh.seek(start)
            fh.write(data)
    with ZipFile(path) as z:
        for e in entries:
            if not e.is_dir() and ('/test_data/' in e.filename or e.filename.endswith(('.py','.txt'))):
                z.read(e)
    print('Test partitions and source documentation verified by per-member CRC32')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path)
    download(parser.parse_args().output)
