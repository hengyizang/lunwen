"""Fetch original files listed in a versioned DaRUS JSON snapshot and verify Dataverse MD5."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import time
from urllib.request import urlopen


def fetch(row, out):
    f=row['dataFile']
    path=out/(str(f['id'])+Path(f.get('originalFileName',f['filename'])).suffix)
    size=f.get('originalFileSize',f['filesize'])
    def valid(data):
        return len(data)==size and hashlib.md5(data).hexdigest()==f['md5']
    if path.exists() and valid(path.read_bytes()):
        return
    url=f"https://darus.uni-stuttgart.de/api/access/datafile/{f['id']}?format=original"
    for retry in range(4):
        try:
            with urlopen(url,timeout=60) as res:
                data=res.read()
            if not valid(data):raise ValueError('size or digest mismatch '+url)
            path.write_bytes(data)
            return
        except (OSError,ValueError):
            if retry==3:raise
            time.sleep(1+retry)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('metadata',type=Path)
    p.add_argument('output',type=Path)
    p.add_argument('--workers',type=int,default=4)
    a=p.parse_args()
    obj=json.loads(a.metadata.read_text())['data']
    version=obj.get('latestVersion',obj)
    a.output.mkdir(parents=True,exist_ok=True)
    with ThreadPoolExecutor(a.workers) as pool:
        list(pool.map(lambda row:fetch(row,a.output),version['files']))


if __name__=='__main__':
    main()
