"""Audit both original F1/10 ROS2 SQLite bags. Usage: python derive_platoon.py EXTRACTED_DATASET OUT.
Uses NumPy and the Python standard library. Timing statistics use the ROS recorder domain unless marked header.
"""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import math
from pathlib import Path
import sqlite3
import struct
import numpy as np


def save(path, rows):
    with path.open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=rows[0], lineterminator='\n')
        w.writeheader()
        w.writerows(rows)


def align(offset, width):
    return (offset + width - 1) // width * width


def cdrstring(b, pos):
    pos=align(pos,4)
    size,=struct.unpack_from('<I',b,pos)
    raw=b[pos+4:pos+4+size]
    if size<1 or raw[-1]!=0:
        raise ValueError('Invalid CDR string terminator')
    return raw[:-1].decode(),pos+4+size


def body_header(b):
    if b[:4]!=b'\x00\x01\x00\x00':
        raise ValueError('Expected little-endian ROS2 CDR')
    body=b[4:]
    sec, ns=struct.unpack_from('<iI',body)
    if ns>=10**9:raise ValueError('Invalid ROS time')
    frame,pos=cdrstring(body,8)
    return body,sec*10**9+ns,frame,pos


def cam_payload(b):
    body,stamp,reason,pos=body_header(b)
    robot,pos=cdrstring(body,pos)
    pos=align(pos,8)
    xyz=struct.unpack_from('<5d',body,pos)
    drive=body[pos+40]
    tail=align(pos+41,8)
    v,vd,curve,length,width=struct.unpack_from('<5d',body,tail)
    if tail+40!=len(body):raise ValueError('CAM schema mismatch')
    if not all(math.isfinite(x) for x in (*xyz,v,vd,curve,length,width)):
        raise ValueError('Non-finite CAM measurement')
    return (robot,stamp,reason,*xyz,drive,v,vd,curve,length,width)


def quant(a, p):
    return round(float(np.quantile(a,p)),6) if len(a) else ''


def deltas(times):
    return np.diff(np.sort(np.asarray(times,dtype=np.int64)))/1e6


def earliest_span(times, active):
    """First true run sustained over 0.15 seconds, with recording gaps >0.1 seconds excluded."""
    begin=None; previous=None
    for t,yes in zip(times,active):
        if not yes:
            begin=None
        elif begin is None or (previous is not None and t-previous>100_000_000):
            begin=t
        elif t-begin>=150_000_000:
            return int(begin)
        previous=t
    return None


def analyze(db):
    run=db.parent.name
    with sqlite3.connect(f'file:{db}?mode=ro',uri=True) as conn:
        meta=conn.execute('SELECT id,name,type,serialization_format FROM topics ORDER BY id').fetchall()
        ids={name:i for i,name,_,_ in meta}
        selected={i:name for i,name,_,_ in meta if name=='/cam' or name.endswith(('/cam_filtered','/cacc/cam_debug','/sensors/core','/vicon/pose','/commands/motor/speed','/ackermann_cmd'))}
        global_messages=defaultdict(list)
        filtered=defaultdict(list)
        debug=defaultdict(list)
        motion=defaultdict(list)
        counts=Counter()
        time_limits={}
        # A single table scan also counts empty topics listed by the archive but never recorded.
        query='SELECT topic_id,timestamp,CASE WHEN topic_id IN ('+','.join('?' for _ in selected)+') THEN data END FROM messages ORDER BY id'
        for i,t,b in conn.execute(query,tuple(selected)):
            counts[i]+=1
            if i not in time_limits:time_limits[i]=[t,t]
            else:
                time_limits[i][0]=min(t,time_limits[i][0])
                time_limits[i][1]=max(t,time_limits[i][1])
            if i not in selected:continue
            name=selected[i]
            if name=='/cam':
                key=cam_payload(b);global_messages[key].append((t,hashlib.sha256(b).digest()))
                continue
            node=name.split('/')[1]
            if name.endswith('/cam_filtered'):
                filtered[node].append((cam_payload(b),t,hashlib.sha256(b).digest()))
            elif name.endswith('/cacc/cam_debug'):
                key=cam_payload(b);debug[node].append((t,key[1],(key[3],key[4],key[9])))
            elif name.endswith('/ackermann_cmd'):
                body,_,_,pos=body_header(b)
                _,_,speed,_,_=struct.unpack_from('<5f',body,align(pos,4))
                motion[node,'ack'].append((t,speed))
            elif name.endswith('/commands/motor/speed'):
                if len(b)!=12:raise ValueError('Unexpected Float64 size')
                speed,=struct.unpack_from('<d',b,4)
                motion[node,'cmd'].append((t,speed))
            elif name.endswith('/sensors/core'):
                body,_,_,pos=body_header(b)
                electrical_speed,=struct.unpack_from('<d',body,align(pos,8)+7*8)
                motion[node,'feedback'].append((t,electrical_speed))
            elif name.endswith('/vicon/pose'):
                body,_,_,pos=body_header(b)
                child,pos=cdrstring(body,pos)
                if child!=node:raise ValueError('Unexpected tracked rigid body')
                x,y=struct.unpack_from('<2d',body,align(pos,8))
                motion[node,'pose'].append((t,x,y))
    inventory=[dict(run=run,topic=name,type=typ,storage=fmt,rows=counts[i],first_recorder_ns=time_limits.get(i,['',''])[0],
                    last_recorder_ns=time_limits.get(i,['',''])[1]) for i,name,typ,fmt in meta]
    sources=[]
    for robot,reason in sorted({(k[0],k[2]) for k in global_messages}):
        keys=[k for k in global_messages if k[0]==robot and k[2]==reason]
        msg_times=[k[1] for k in keys for _ in global_messages[k]]
        sources.append(dict(run=run,broadcast_robot=robot,frame_id=reason,global_rows=len(msg_times),distinct_payloads=len(keys),distinct_header_stamps=len(set(msg_times))))
    channels=[];uses=[];physical=[];conversions=[]
    for node in sorted({name.split('/')[1] for name in ids if name.startswith('/F110_')}):
        rows=filtered[node]
        sender_counts=Counter(x[0][0] for x in rows)
        if len(sender_counts)>1:raise ValueError('Multiple predecessors require separate analysis')
        matched=[];literal=0
        for key,t,raw_hash in rows:
            candidates=global_messages.get(key,[])
            if len(candidates)==1:
                source,gh=candidates[0]
                matched.append((t-source)/1e6)
                literal+=raw_hash==gh
        arr=np.asarray(matched)
        sender=next(iter(sender_counts),'')
        relevant=sum(len(v) for k,v in global_messages.items() if k[0]==sender)
        projections=defaultdict(list)
        for key,t,_ in rows:
            projections[key[3],key[4],key[9]].append((t,key[1]))
        held=defaultdict(list);ambig=0;unmatched=0
        for t,stamp,project in debug[node]:
            candidates=projections.get(project,[])
            if not candidates:unmatched+=1
            elif len(candidates)>1:ambig+=1
            else:
                candidate=candidates[0]
                held[candidate].append((t,stamp))
        first_rec=[];first_hdr=[];repeats=[]
        for (ft,origin),hits in held.items():
            first_stamp=min(hits)
            first_rec.append((first_stamp[0]-ft)/1e6)
            first_hdr.append((first_stamp[1]-origin)/1e6)
            repeats.append(len(hits))
        channels.append(dict(run=run,receiver=node,source_name=sender,filtered_topic_registered=int('/'+node+'/cam_filtered' in ids),global_rows_from_source=relevant,filtered_rows=len(rows),
            distinct_filtered_payloads=len({x[0] for x in rows}),filtered_with_one_identical_decoded_global=arr.size,identical_serialized_bytes=literal,
            filtered_earlier_in_recorder_time=int(np.sum(arr<0)),global_to_filtered_recorder_ms_p50=quant(arr,.5),global_to_filtered_recorder_ms_p95=quant(arr,.95),
            global_to_filtered_recorder_ms_min=quant(arr,0),global_to_filtered_recorder_ms_max=quant(arr,1)))
        uses.append(dict(run=run,receiver=node,source_name=sender,debug_rows=len(debug[node]),unique_filtered_frames_represented=len(held),
            debug_rows_exact_unique_x_y_v=sum(repeats),debug_rows_ambiguous_x_y_v=ambig,debug_rows_no_same_x_y_v=unmatched,
            uses_per_identified_frame_median=quant(repeats,.5),uses_per_identified_frame_max=quant(repeats,1),
            first_debug_before_filtered_at_recorder=int(np.sum(np.asarray(first_rec)<0)),
            first_debug_minus_filtered_recorder_ms_p50=quant(first_rec,.5),
            first_debug_minus_filtered_recorder_ms_p95=quant(first_rec,.95),
            first_debug_minus_origin_header_ms_p50=quant(first_hdr,.5)))
        ack=sorted(motion[node,'ack'])
        motor=sorted(motion[node,'cmd'])
        if ack and motor:
            # Distinct transitions in both streams suppress matches between repeated setpoints.
            def changes(points,scale):
                return [(points[j][0],points[j-1][1]*scale,points[j][1]*scale) for j in range(1,len(points)) if abs(points[j][1]-points[j-1][1])*scale>0.001]
            ack_changes=changes(ack,4614.0)
            motor_changes=changes(motor,1.0)
            motor_time=np.asarray([x[0] for x in motor_changes],dtype=np.int64)
            candidates=defaultdict(list)
            ambiguous=0
            for t,prev,nxt in ack_changes:
                left=np.searchsorted(motor_time,t-100_000_000)
                right=np.searchsorted(motor_time,t+100_000_000,side='right')
                match=[i for i in range(left,right) if abs(prev-motor_changes[i][1])<=0.001 and abs(nxt-motor_changes[i][2])<=0.001]
                if len(match)==1:candidates[match[0]].append(t)
                elif len(match)>1:ambiguous+=1
            pairs=np.asarray([(motor_changes[i][0]-ts[0])/1e6 for i,ts in candidates.items() if len(ts)==1])
            conversions.append(dict(run=run,node=node,ackermann_rows=len(ack),motor_command_rows=len(motor),source_transitions=len(ack_changes),
                motor_transitions=len(motor_changes),unique_transition_pairs=len(pairs),source_changes_with_multiple_compatible_targets=ambiguous,
                target_candidates_with_multiple_sources=sum(len(ts)>1 for ts in candidates.values()),paired_motor_earlier_in_recorder_time=int(np.sum(pairs<0)),
                paired_recorder_difference_ms_p50=quant(pairs,.5),paired_recorder_difference_ms_p95=quant(pairs,.95)))
        series={k:sorted(motion[node,k]) for k in ('cmd','feedback','pose')}
        # Do each clock computation in int64 and keep the pose threshold on a shared recorder window.
        starts=[s[0][0] for s in series.values() if s]
        if len(starts)!=3:continue
        begin=max(starts);end=min(s[-1][0] for s in series.values())
        orig={}
        for k,ss in series.items():
            vals=[x for x in ss if begin<=x[0]<=end]
            if not vals:raise ValueError('No common interval')
            times=np.asarray([x[0] for x in vals],dtype=np.int64)
            values=np.asarray([x[1:] for x in vals])
            if k=='pose':
                base=np.median(values[times<begin+250_000_000],axis=0)
                magnitudes=np.linalg.norm(values-base,axis=1)
                thresh=.02
            else:magnitudes=np.abs(values[:,0]);thresh=200
            orig[k]=earliest_span(times,magnitudes>thresh)
            physical.append(dict(run=run,node=node,series=k,rows=len(ss),common_rows=len(times),common_duration_s=round((end-begin)/1e9,6),
                 median_recorder_step_ms=quant(deltas(times),.5),threshold=thresh,units='m displacement from first 250 ms median' if k=='pose' else 'electrical rpm magnitude',
                 first_250ms_median_magnitude=quant(magnitudes[times<begin+250_000_000],.5),max_magnitude=quant(magnitudes,1),
                 first_sustained_threshold_after_common_start_ms='' if orig[k] is None else round((orig[k]-begin)/1e6,6)))
    return inventory,channels,uses,physical,sources,conversions


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('data',type=Path);p.add_argument('out',type=Path);a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=True)
    result=[[] for _ in range(6)]
    for db in sorted(a.data.glob('*/*.db3')):
        for arr,rows in zip(result,analyze(db),strict=True):arr.extend(rows)
    if not result[0]:raise ValueError('No bags')
    for label,rows in zip(('topics','forwarding','control-uses','motion','broadcasts','motor-conversions'),result,strict=True):
        save(a.out/f'platoon-{label}.csv',rows)


if __name__=='__main__':main()
