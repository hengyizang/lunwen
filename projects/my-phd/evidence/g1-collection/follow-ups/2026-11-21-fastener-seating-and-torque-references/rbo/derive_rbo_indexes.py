"""Summarize connection/chunk indexes in the RBO ROS1 bags, without decoding image payloads."""
import argparse
import csv
from collections import Counter
import hashlib
import json
from pathlib import Path
import struct

from fetch_rbo_indexes import bag_header, field_map


def integer(b):
    return int.from_bytes(b,'little')


def stamp(b):
    sec,nsec=struct.unpack('<II',b)
    return sec*10**9+nsec


def block(buf,idx):
    n=struct.unpack_from('<I',buf,idx)[0]
    end=idx+4+n
    if end>len(buf):raise ValueError('Truncated index record')
    return buf[idx+4:end],end


def inspect(file,directory,name,kind,labeled):
    hp=(directory/(name+'.head')).read_bytes()
    tail=(directory/(name+'.idx')).read_bytes()
    head=bag_header(hp)
    assert integer(head[b'index_pos'])+len(tail)==file['size']
    ptr=0
    names={}
    counts=Counter()
    chunks=0
    times=[]
    while ptr<len(tail):
        h,ptr=block(tail,ptr)
        body,ptr=block(tail,ptr)
        h=field_map(h)
        if h[b'op']==b'\x07':
            names[integer(h[b'conn'])]=(h[b'topic'].decode(),field_map(body)[b'type'].decode())
        elif h[b'op']==b'\x06':
            chunks+=1
            times.append((stamp(h[b'start_time']),stamp(h[b'end_time'])))
            if len(body)!=integer(h[b'count'])*8:raise ValueError('Unexpected chunk-index dimensions')
            for conn,count in struct.iter_unpack('<II',body):counts[conn]+=count
        else:raise ValueError('Unknown tail record')
    assert len(names)==integer(head[b'conn_count']) and chunks==integer(head[b'chunk_count'])
    assert set(counts).issubset(names)
    def topic_count(type_name):
        return sum(counts[i] for i,(_,t) in names.items() if t==type_name)
    ft=topic_count('geometry_msgs/WrenchStamped')
    js=topic_count('sensor_msgs/JointState')
    return dict(interaction=name,object=kind,index_ft_label=labeled,
                bag_bytes=file['size'],publisher_bag_md5=file['checksum'],head_bytes=len(hp),
                head_sha256=hashlib.sha256(hp).hexdigest(),tail_bytes=len(tail),tail_sha256=hashlib.sha256(tail).hexdigest(),
                connections=len(names),chunks=chunks,messages=sum(counts.values()),wrench_messages=ft,
                joint_state_messages=js,recorded_ft_presence_matches_label=int(bool(ft)==bool(int(labeled))),
                wrench_topics='|'.join(sorted({v[0] for v in names.values() if v[1]=='geometry_msgs/WrenchStamped'})),
                recorded_interval_s=round((max(t[1] for t in times)-min(t[0] for t in times))/1e9,6))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for arg in ('registry','interactions','indexes','output'):p.add_argument(arg,type=Path)
    a=p.parse_args()
    files={f['key']:f for f in json.loads(a.registry.read_text())['files']}
    with a.interactions.open(newline='') as f:rows=list(csv.DictReader(f))
    out=[inspect(files[r['Name']+'_o.bag'],a.indexes,r['Name'],r['Object'],r['force/torque sensor used']) for r in rows]
    a.output.mkdir(parents=True,exist_ok=True)
    with (a.output/'rbo-bag-indexes.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=out[0],lineterminator='\n')
        w.writeheader()
        w.writerows(out)


if __name__=='__main__':
    main()
