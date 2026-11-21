"""Compare the three contact-sensitive streams in the original slip bag files.
python derive_slip.py DIRECTORY_OF_EXTRACTED_BAGS OUTPUT_DIR
Requires rosbags and numpy. Original data stay in source repository.
"""
import argparse
import csv
import hashlib
from pathlib import Path
import struct
import numpy as np
from rosbags.rosbag1 import Reader


def output(path,rows):
    with path.open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=rows[0],lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def read_bag(path):
    topics=['/left/image','/right/image','/teensy/tactile']
    traces={name:[] for name in topics}
    nonzero_extra=0
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    with Reader(path) as bag:
        actual={c.topic for c in bag.connections}
        if not set(topics[:2])<=actual<=set(topics):
            raise ValueError(f'Unexpected connections: {path}')
        for c,t,raw in bag.messages():
            seq,sec,ns,frame_len=struct.unpack_from('<IIII',raw)
            offset=16+frame_len
            if c.topic=='/teensy/tactile':
                channels=np.frombuffer(raw,offset=offset,dtype='<u2').reshape(5,12)
                if np.max(channels[0])>1023:
                    raise ValueError('Distal count exceeds 1023')
                nonzero_extra+=int(np.any(channels[1:]))
                # Raw ADC approaches 1023 in the relaxed third probe; retain inverse counts.
                summed=12*1023-int(np.sum(channels[0]))
            else:
                h,w,n=struct.unpack_from('<III',raw,offset)
                encoding=raw[offset+12:offset+12+n]
                big,step,length=struct.unpack_from('<BII',raw,offset+12+n)
                if (h,w,encoding,big,step,length)!=(16,16,b'32FC1',0,64,1024):
                    raise ValueError(f'Unknown image schema: {path}')
                summed=np.sum(np.frombuffer(raw,dtype='<f4',count=256,offset=offset+21+n),dtype=np.float64)
            traces[c.topic].append((sec*10**9+ns,int(t),seq,summed))
    return digest,traces,nonzero_extra


def signal_summary(path,digest,topic,samples):
    # Integer nanoseconds must not be packed in a common floating-point matrix.
    stamp=np.array([v[0] for v in samples],dtype=np.int64)
    bag=np.array([v[1] for v in samples],dtype=np.int64)
    seq=np.array([v[2] for v in samples],dtype=np.int64)
    value=np.array([v[3] for v in samples],dtype=np.float64)
    if len(value)<4 or not np.isfinite(value).all():raise ValueError(f'Invalid stream in {path}')
    d=np.diff(stamp)
    differences=(bag-stamp)/1e6
    # Order by message-header time only for this sensitivity measurement.
    ix=np.argsort(stamp,kind='stable')
    ordered=stamp[ix]
    v=value[ix]
    start=v[ordered<=ordered[0]+250_000_000]
    end=v[ordered>=ordered[-1]-250_000_000]
    v0,v1=np.median(start),np.median(end)
    mad=np.median(np.abs(start-v0))
    change=v0-v1
    crossing=None
    if change>10*max(1,1.4826*mad):
        ixlow=np.flatnonzero((v[:-1]>(v0+v1)/2)&(v[1:]<=(v0+v1)/2))+1
        for i in ixlow:
            j=np.searchsorted(ordered,ordered[i]+10_000_000)
            if ordered[i]>=ordered[0]+250_000_000 and j<len(v) and np.all(v[i:j+1]<=(v0+v1)/2):
                crossing=int(ordered[i]);break
    row=dict(bag=path.name,bag_sha256=digest,topic=topic,frames=len(stamp),
             header_span_s=round((int(stamp.max())-int(stamp.min()))/1e9,7),
             header_median_step_ms=round(np.median(d)/1e6,6),
             header_nonpositive_steps=int((d<=0).sum()),sequence_discontinuities=int((np.diff(seq)!=1).sum()),
             median_bag_minus_header_ms=round(np.median(differences),6),
             p95_bag_minus_header_ms=round(np.percentile(differences,95),6),
             initial_sum_median=round(v0,5),final_sum_median=round(v1,5),
             initial_sum_mad=round(mad,5),resolved_half_drop=int(crossing is not None))
    return row,crossing


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('bags',type=Path)
    p.add_argument('output',type=Path)
    args=p.parse_args()
    coverage,comparisons=[],[]
    for path in sorted(args.bags.rglob('*.bag')):
        digest,streams,nonzero=read_bag(path)
        marks={topic:None for topic in streams}
        for topic,values in streams.items():
            if not values:
                continue
            row,marks[topic]=signal_summary(path,digest,topic,values)
            coverage.append(row)
        ref=marks['/teensy/tactile']
        def diff(topic):
            return round((marks[topic]-ref)/1e6,6) if marks[topic] is not None and ref is not None else ''
        comparisons.append(dict(bag=path.name,object_label=path.name.split('_')[0],
                                has_stable_filename=int('stable' in path.name),
                                third_probe_present=int(bool(streams['/teensy/tactile'])),extra_UBI_banks_nonzero_frames=nonzero,
                                third_probe_half_drop=int(ref is not None) if streams['/teensy/tactile'] else '',
                                left_minus_probe_half_drop_ms=diff('/left/image'),
                                right_minus_probe_half_drop_ms=diff('/right/image')))
    if not comparisons:raise ValueError('No bag files.')
    args.output.mkdir(parents=True,exist_ok=True)
    output(args.output/'slip-streams.csv',coverage)
    output(args.output/'slip-probe-comparisons.csv',comparisons)


if __name__=='__main__':
    main()
