"""Stream the six commabody shards, validate LFS SHA-256, retain only compressed numeric event logs.

python fetch_body.py ROOT [--workers 3]
ROOT/commabody-tree.json is the Hugging Face fixed-revision tree response.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import shutil
import tarfile
from urllib.request import Request,urlopen

REV='16123f8d2cf28e39cf52e0e1bfb5c0e6975287d0'
BASE='https://huggingface.co/datasets/commaai/commabody/resolve/'+REV+'/'


class DigestReader:
    def __init__(self,source):
        self.source=source
        self.digest=hashlib.sha256()
        self.count=0
    def read(self,n):
        b=self.source.read(n)
        self.digest.update(b)
        self.count+=len(b)
        return b


def shard(root,entry):
    name=entry['path']
    folder=root/'body'/name.split('.')[0]
    folder.mkdir(exist_ok=True,parents=True)
    receipt=folder/'complete.json'
    if receipt.exists():return
    logs=[]
    with urlopen(Request(BASE+name+'?download=true&g1=complete',headers={'User-Agent':'G1 numeric source audit'}),timeout=100) as res:
        reader=DigestReader(res)
        with tarfile.open(fileobj=reader,mode='r|gz',bufsize=1024*256) as archive:
            for m in archive:
                if not m.isfile() or not m.name.endswith('.rlog.bz2'):continue
                path=folder/Path(m.name).name
                temp=path.with_suffix('.partial')
                with archive.extractfile(m) as inp,temp.open('wb') as out:shutil.copyfileobj(inp,out)
                assert temp.stat().st_size==m.size
                with temp.open('rb') as inp:digest=hashlib.file_digest(inp,'sha256').hexdigest()
                temp.replace(path)
                logs.append(dict(member=path.name,bytes=m.size,sha256=digest))
        while reader.read(1024*1024):pass
    assert reader.count==entry['size'] and reader.digest.hexdigest()==entry['lfs']['oid']
    receipt.write_text(json.dumps(dict(archive=name,verified_lfs_sha256=reader.digest.hexdigest(),size=reader.count,logs=logs))+'\n')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('root',type=Path);p.add_argument('--workers',type=int,default=3);a=p.parse_args()
    tree=a.root/'commabody-tree.json'
    if not tree.exists():
        tree.write_bytes(urlopen('https://huggingface.co/api/datasets/commaai/commabody/tree/'+REV+'?limit=200&expand=false',timeout=30).read())
    shards=[x for x in json.loads(tree.read_text()) if x['path'].endswith('.tar.gz')]
    with ThreadPoolExecutor(a.workers) as ex:list(ex.map(lambda s:shard(a.root,s),shards))


if __name__=='__main__':main()
