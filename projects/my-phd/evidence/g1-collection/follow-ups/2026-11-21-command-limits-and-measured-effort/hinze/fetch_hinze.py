"""Fetch fixed, public DaRUS releases, preserving and verifying each original byte stream."""
import concurrent.futures
import hashlib
import json
import time
from pathlib import Path
from urllib.request import urlopen
import argparse


def fetch(root,number):
    root.mkdir(parents=True,exist_ok=True)
    url=f'https://darus.uni-stuttgart.de/api/datasets/:persistentId/versions/1.0?persistentId=doi:10.18419/darus-{number}'
    with urlopen(url,timeout=45) as source:
        raw=source.read()
    meta=json.loads(raw)['data']
    assert (meta['versionNumber'],meta['versionMinorNumber'])==(1,0)
    (root/f'meta{number}.json').write_bytes(raw)
    dest=root/str(number);dest.mkdir(exist_ok=True)
    def one(entry):
        f=entry['dataFile']; path=dest/str(f['id'])
        url=f"https://darus.uni-stuttgart.de/api/access/datafile/{f['id']}"
        if 'originalFileName' in f:url+='?format=original'
        if path.exists() and hashlib.md5(path.read_bytes()).hexdigest()==f['md5']:return
        for i in range(3):
            try:
                with urlopen(url,timeout=60) as stream: content=stream.read()
                assert len(content)==f.get('originalFileSize',f['filesize']) and hashlib.md5(content).hexdigest()==f['md5']
                path.write_bytes(content);return
            except Exception:
                if i==2:raise
                time.sleep(i+1)
    with concurrent.futures.ThreadPoolExecutor(6) as pool:
        list(pool.map(one,meta['files']))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('root',type=Path);p.add_argument('number',type=int,choices=(3003,3152))
    a=p.parse_args();fetch(a.root,a.number)
