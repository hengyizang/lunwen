"""Fetch just the ROS1 file header and publisher-stored connection/chunk index of each RBO bag.

python fetch_rbo_indexes.py zenodo-1036660.json interactions_index.csv OUT
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import csv
from email.utils import parsedate_to_datetime
import json
from pathlib import Path
import struct
import threading
import time
from urllib.request import Request,urlopen
from urllib.error import HTTPError


class RangeReader:
    def __init__(self):
        self.lock=threading.Lock()
        self.next_request=0.0

    def interval(self,url,size,begin,end):
        for attempt in range(6):
            with self.lock:
                time.sleep(max(0,self.next_request-time.monotonic()))
                self.next_request=time.monotonic()+0.74
            query=f'{begin}-{end}'
            req=Request(url+'?r='+query,headers={'Range':'bytes='+query})
            try:
                with urlopen(req, timeout=45) as response:
                    if response.status!=206 or response.headers.get('Content-Range')!=f'bytes {query}/{size}':
                        raise ValueError('Server did not supply the indicated interval')
                    b=response.read()
                if len(b)!=end-begin+1:raise OSError('Short range')
                return b
            except HTTPError as e:
                if e.code!=429 and e.code<500:raise
                wait=e.headers.get('Retry-After')
                try: pause=float(wait) if wait else 2**attempt
                except ValueError: pause=max(1,parsedate_to_datetime(wait).timestamp()-time.time())
                with self.lock:self.next_request=max(self.next_request,time.monotonic()+pause)
                if attempt==5:raise
            except OSError:
                if attempt==5:raise
                time.sleep(2**attempt)


def field_map(data):
    fields={}
    pos=0
    while pos<len(data):
        n=struct.unpack_from('<I',data,pos)[0]
        field=data[pos+4:pos+4+n]
        if len(field)!=n:raise ValueError('Truncated field')
        key,value=field.split(b'=',1)
        fields[key]=value
        pos+=4+n
    return fields


def bag_header(data):
    magic=b'#ROSBAG V2.0\n'
    if not data.startswith(magic):raise ValueError('Expected ROS bag v2')
    n=struct.unpack_from('<I',data,len(magic))[0]
    return field_map(data[len(magic)+4:len(magic)+4+n])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('registry',type=Path)
    p.add_argument('interactions',type=Path)
    p.add_argument('out',type=Path)
    a=p.parse_args()
    with a.interactions.open(newline='') as f:rows=list(csv.DictReader(f))
    files={x['key']:x for x in json.loads(a.registry.read_text())['files']}
    a.out.mkdir(parents=True,exist_ok=True)
    reader=RangeReader()
    def fetch(row):
        name=row['Name'];f=files[name+'_o.bag'];size=f['size'];url=f['links']['self']
        hp=a.out/(name+'.head');ip=a.out/(name+'.idx')
        if not hp.exists():hp.write_bytes(reader.interval(url,size,0,159))
        off=int.from_bytes(bag_header(hp.read_bytes())[b'index_pos'],'little')
        if not 160<off<size:raise ValueError(name+' invalid index offset')
        if not ip.exists() or ip.stat().st_size!=size-off:
            ip.write_bytes(reader.interval(url,size,off,size-1))
    # Fetch labeled wrench runs first. Each request is rate-limited independently of worker count.
    rows.sort(key=lambda row:(row['force/torque sensor used']!='1',row['Name']))
    with ThreadPoolExecutor(5) as ex:list(ex.map(fetch,rows))


if __name__=='__main__':
    main()
