"""ROS1 recorded-time audit of independently instrumented CALPAK fixture collisions.

python derive_collision.py ZENODO_DATA.zip OUT
Needs Python, NumPy and rosbags (0.11.10 tested). Read only, no ROS master needed.
"""
import argparse
from collections import defaultdict
import csv
import hashlib
import io
import struct
from pathlib import Path,PurePosixPath
import tempfile
from xml.etree import ElementTree
from zipfile import ZipFile

import numpy as np
from rosbags.rosbag1 import Reader

EXTERNAL='/external_ft_sensor'
ROBOT='/coll_det_ee/force'
FLAGS=('/coll_det_ee/coll_detected','/coll_det_jts/coll_detected')


def write(path,records):
    with path.open('w',newline='',encoding='utf-8') as stream:
        w=csv.DictWriter(stream,fieldnames=records[0],lineterminator='\n')
        w.writeheader()
        w.writerows(records)


def logsheet(z,folder):
    name=next(n for n in z.namelist() if n.startswith(folder+'/README') and n.endswith('.docx'))
    with ZipFile(io.BytesIO(z.read(name))) as doc:
        ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
        x=ElementTree.fromstring(doc.read('word/document.xml'))
        rows=[[''.join((p.text or '') for p in c.findall('.//w:t',ns)).strip() for c in tr.findall('w:tc',ns)] for tr in x.findall('.//w:tbl/w:tr',ns)]
    return {r[0]:dict(zip(rows[0],r)) for r in rows[1:]}


def wrench(blob):
    # ROS1 JointState: Header, string[] name, 3 float64 arrays (position,velocity,effort).
    seq,sec,nano,frame_len=struct.unpack_from('<4I',blob)
    off=16+frame_len
    names=struct.unpack_from('<I',blob,off)[0]
    off+=4
    for _ in range(names):off+=4+struct.unpack_from('<I',blob,off)[0]
    for _ in range(2):off+=4+8*struct.unpack_from('<I',blob,off)[0]
    n=struct.unpack_from('<I',blob,off)[0]
    if off+4+8*n!=len(blob) or n<6:raise ValueError('Unexpected wrench field layout')
    return (sec*10**9+nano,seq,n,*struct.unpack_from('<6d',blob,off+4))


def measure(path,trial):
    indexed=bool(trial)
    documents={}
    histories=defaultdict(list)
    with Reader(path) as reader:
        for topic in [EXTERNAL,ROBOT,*FLAGS]:
            messages=[c for c in reader.connections if c.topic==topic]
            documents[topic]=sum(c.msgcount for c in messages)
        selected=[c for c in reader.connections if c.topic in documents]
        if indexed:
            for connection,t,b in reader.messages(connections=selected):
                topic=connection.topic
                if topic in FLAGS:
                    if connection.msgtype!='std_msgs/msg/Bool' or len(b)!=1:raise ValueError('Unsupported flag')
                    histories[topic].append((t,bool(b[0])))
                else:
                    if connection.msgtype!='sensor_msgs/msg/JointState':raise ValueError('Unexpected message type')
                    histories[topic].append((t,*wrench(b)))
            if any(len(histories[t])!=count for t,count in documents.items()):raise ValueError('Incomplete topic read')
        info={'bag_entries':reader.message_count,'duration_s':round(reader.duration/1e9,5),
              'external_msgs':documents[EXTERNAL],'robot_ee_msgs':documents[ROBOT],
              'ee_flags':documents[FLAGS[0]],'joint_flags':documents[FLAGS[1]]}
    return info,histories


def stats(rows):
    record=np.array([r[0] for r in rows],dtype='int64')
    header=np.array([r[1] for r in rows],dtype='int64')
    values=np.array([r[4:] for r in rows])
    if not np.isfinite(values).all():raise ValueError('Non-finite wrench')
    # No subtraction between different device header domains.
    baseline=np.median(values[record<=record[0]+500_000_000],axis=0)
    residual=values-baseline
    amplitude=np.linalg.norm(residual[:,:3],axis=1)
    ordinal=np.flatnonzero((amplitude[:-2]>20)&(amplitude[1:-1]>20)&(amplitude[2:]>20))
    crossing=int(record[ordinal[0]]) if len(ordinal) else None
    hx=(header-record)/1e9
    result=dict(first_record_ns=int(record[0]),header_minus_recorder_s_median=round(np.median(hx),6),
                header_backsteps=int((np.diff(header)<0).sum()),header_equal_adjacent=int((np.diff(header)==0).sum()),
                typical_recorder_interval_ms=round(np.median(np.diff(record))/1e6,5),
                initial_baseline_rows=int((record<=record[0]+500_000_000).sum()),
                peak_triplet_norm_raw=round(np.linalg.norm(values[:,:3],axis=1).max(),4),
                peak_baseline_subtracted_triplet_norm=round(amplitude.max(),4),
                peak_baseline_subtracted_second_triplet_norm=round(np.linalg.norm(residual[:,3:6],axis=1).max(),4),
                first_sustained_20_record_ns='' if crossing is None else crossing)
    for n,value in enumerate(baseline,1):
        result[f'initial_median_effort_{n}']=round(value,6)
    return result,crossing


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('archive',type=Path);p.add_argument('out',type=Path)
    args=p.parse_args();args.out.mkdir(exist_ok=True,parents=True)
    inventory=[];signals=[];comparisons=[]
    with ZipFile(args.archive) as z,tempfile.TemporaryDirectory() as tmp:
        tables={folder:logsheet(z,folder) for folder in ('data/2022_08_03_calpak','data/2022_08_04_calpak')}
        for name in sorted(n for n in z.namelist() if n.endswith('.bag')):
            topic=PurePosixPath(name)
            trial=tables.get(str(topic.parent),{}).get(topic.stem)
            pth=Path(tmp)/'trial.bag';digest=hashlib.sha256()
            with z.open(name) as source,pth.open('wb') as out:
                for block in iter(lambda:source.read(2**21),b''):
                    digest.update(block);out.write(block)
            info,hist=measure(pth,trial)
            inventory.append(dict(member=name,sha256=digest.hexdigest(),bytes=pth.stat().st_size,
                                  documented_august_fixture_trial=int(bool(trial)),**info))
            if not trial:continue
            stats_by={}
            for topic in (EXTERNAL,ROBOT):
                if hist[topic]:
                    vals,crossing=stats(hist[topic]);stats_by[topic]=(vals,crossing)
                    signals.append(dict(member=name,topic=topic,messages=len(hist[topic]),**vals))
            ext,te=stats_by.get(EXTERNAL,({},None))
            ee,tr=stats_by.get(ROBOT,({},None))
            row=dict(member=name,speed_override=trial['Speed overide'],pad=trial.get('pads',trial.get('Sensor pads for stiffness measurement')),
                     orientation=trial['orientation'],extension=trial.get('extention',trial.get('robot extension')),panel=trial.get('panel',trial.get('Panel')),
                     selected_detector=trial.get('jt/ee',''),notes=trial.get('note',''),
                     source_peak=trial.get('peak force',''),
                     external_raw_triplet_norm_max=ext.get('peak_triplet_norm_raw',''),
                     external_residual_triplet_norm_max=ext.get('peak_baseline_subtracted_triplet_norm',''),
                     ee_residual_triplet_norm_max=ee.get('peak_baseline_subtracted_triplet_norm',''),
                     relative_header_offsets_s=round(ext['header_minus_recorder_s_median']-ee['header_minus_recorder_s_median'],6) if ext and ee else '',
                     robot_minus_external_threshold_ms=round((tr-te)/1e6,4) if tr is not None and te is not None else '')
            for label,flag in zip(('ee','joint'),FLAGS):
                flags=hist[flag]
                edges=[b[0] for a,b in zip(flags,flags[1:]) if not a[1] and b[1]]
                row[label+'_recorded_rising_edges']=len(edges)
                row[label+'_initial_flag']=int(flags[0][1]) if flags else ''
                row[label+'_first_rise_minus_external_threshold_ms']=round((edges[0]-te)/1e6,4) if edges and te is not None else ''
            comparisons.append(row)
    write(args.out/'collision-bags.csv',inventory)
    write(args.out/'collision-wrench-topics.csv',signals)
    write(args.out/'collision-fixture-conditions.csv',comparisons)


if __name__=='__main__':main()
