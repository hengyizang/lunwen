"""Fetch complete ZIP directories and boundary CSVs from the pinned commaSteeringControl release.

python fetch_steering.py ROOT [--workers 6] [--full-smallest 6]
ROOT/steer may contain whole platform ZIP files, e.g. the six smallest.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
import json
from pathlib import Path
import time
import shutil
from urllib.parse import quote
from urllib.request import Request,urlopen
from zipfile import ZipFile

REV='647fe063d1a955ed0acb3601c2e71e108fdce18b'
BASE='https://huggingface.co/datasets/commaai/commaSteeringControl/resolve/'+REV+'/'
TREE='https://huggingface.co/api/datasets/commaai/commaSteeringControl/tree/'+REV+'/data?limit=200&expand=false'


class Ranges(io.RawIOBase):
    def __init__(self,url,size):
        self.url,self.size,self.pos=url,size,0
        self.cache=[]
    def seek(self,offset,whence=0):
        self.pos=offset+(self.pos if whence==1 else self.size if whence==2 else 0)
        if self.pos<0:raise OSError('Negative file offset')
        return self.pos
    def tell(self):return self.pos
    def seekable(self):return True
    def read(self,n=-1):
        start=self.pos
        end=self.size if n<0 else min(self.pos+n,self.size)
        if start>=end:return b''
        for a,b in self.cache:
            if a<=start and end<=a+len(b):
                self.pos=end
                return b[start-a:end-a]
        a=max(0,start-131072) if end==self.size else start
        b=min(self.size,max(end,a+131072))
        for attempt in range(4):
            try:
                req=Request(self.url+f'?download=true&span={a}-{b-1}',headers={'Range':f'bytes={a}-{b-1}'})
                with urlopen(req,timeout=45) as res:
                    if res.status!=206 or res.headers.get('Content-Range')!=f'bytes {a}-{b-1}/{self.size}':raise OSError('Incorrect server range')
                    data=res.read()
                if len(data)!=b-a:raise OSError('Incomplete range')
                break
            except OSError:
                if attempt==3:raise
                time.sleep(1+attempt)
        self.cache.append((a,data))
        self.pos=end
        return data[start-a:end-a]


def handle(root,item):
    name=Path(item['path']).stem
    out=root/'steer-index'/name
    out.mkdir(parents=True,exist_ok=True)
    record=out/'index.json'
    whole=root/'steer'/(name+'.zip')
    if record.exists():
        old=json.loads(record.read_text())
        if (old['complete_sha_checked']==whole.is_file() and
            all((out/Path(e['name']).name).is_file() for e in old['selected'])):
            return
    verified=False
    if whole.is_file():
        with whole.open('rb') as f:assert hashlib.file_digest(f,'sha256').hexdigest()==item['lfs']['oid']
        verified=True
    inp=whole if verified else Ranges(BASE+quote(item['path']),item['size'])
    with ZipFile(inp) as z:
        files=sorted((m for m in z.infolist() if m.filename.endswith('.csv')),key=lambda m:m.filename)
        keys=[m.filename for m in files]
        assert files and len(keys)==len(set(keys))
        selected=[]
        for m in [files[0],files[-1]]:
            b=z.read(m)
            dest=out/Path(m.filename).name
            dest.write_bytes(b)
            selected.append(dict(name=m.filename,bytes=len(b),crc32=f'{m.CRC:08x}',sha256=hashlib.sha256(b).hexdigest()))
        directory=[(m.filename,m.file_size,m.compress_size,m.CRC) for m in files]
        record.write_text(json.dumps(dict(platform=name,zip_bytes=item['size'],lfs_sha256=item['lfs']['oid'],
              complete_sha_checked=verified,all_entries=len(z.infolist()),csv_members=len(files),uncompressed_csv_bytes=sum(m.file_size for m in files),
              distinct_crc_size=len({(m.CRC,m.file_size) for m in files}),
              directory_inventory_sha256=hashlib.sha256(json.dumps(directory,separators=(',',':')).encode()).hexdigest(),selected=selected))+'\n')


def fetch_full(root,item):
    folder=root/'steer'
    folder.mkdir(parents=True,exist_ok=True)
    target=folder/Path(item['path']).name
    if target.is_file():return
    temp=target.with_suffix('.partial')
    with urlopen(BASE+quote(item['path'])+'?download=true',timeout=90) as response,temp.open('wb') as out:
        shutil.copyfileobj(response,out)
    with temp.open('rb') as stream:assert hashlib.file_digest(stream,'sha256').hexdigest()==item['lfs']['oid']
    temp.replace(target)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('root',type=Path);p.add_argument('--workers',type=int,default=6);p.add_argument('--full-smallest',type=int,default=6);a=p.parse_args()
    a.root.mkdir(exist_ok=True,parents=True)
    tree=a.root/'commaSteeringControl-tree.json'
    if not tree.is_file():tree.write_bytes(urlopen(TREE,timeout=30).read())
    items=json.loads(tree.read_text())
    smallest=sorted(items,key=lambda e:(e['size'],e['path']))[:a.full_smallest]
    with ThreadPoolExecutor(a.workers) as ex:
        list(ex.map(lambda i:fetch_full(a.root,i),smallest))
        list(ex.map(lambda i:handle(a.root,i),items))


if __name__=='__main__':main()
