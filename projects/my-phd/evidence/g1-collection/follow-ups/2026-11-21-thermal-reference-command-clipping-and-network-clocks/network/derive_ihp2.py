"""Recompute IHP2 mobility-message pairs, response handshakes and follower observations.

Usage: python derive_ihp2.py cavihp.zip OUT
Dependencies: lz4, openpyxl. Input is the original Socrata 2qjp-7bah archive.
"""
import argparse
import bisect
import csv
import hashlib
import io
import itertools
import math
import re
import struct
from collections import Counter, defaultdict
from pathlib import Path
from zipfile import ZipFile

from lz4.frame import decompress
from openpyxl import load_workbook

TOPICS = [f'/message/{direction}_mobility_{typ}' for direction in ('incoming', 'outgoing')
          for typ in ('operation', 'request', 'response')]
STATE = '/guidance/platooning_info'
STRATEGIC = '/guidance/platoon_info'
CTRL = '/guidance/ctrl_cmd'
SPEED = '/hardware_interface/vehicle/twist'
HW = '/hardware_interface/arbitrated_speed_commands'
PEDALS = ('/hardware_interface/throttle_feedback','/hardware_interface/brake_feedback')
TOPICS += [STATE, STRATEGIC, CTRL, SPEED, HW, *PEDALS, '/carma_system_version']


def u32(data, off=0):
    return struct.unpack_from('<I', data, off)[0]


def txt(data, off):
    length = u32(data, off)
    end = off+4+length
    return data[off+4:end].decode(), end


def fields(data):
    result = {}
    off = 0
    while off < len(data):
        length = u32(data, off)
        k,v = data[off+4:off+4+length].split(b'=',1)
        result[k] = v
        off += 4+length
    assert off == len(data)
    return result


def record(data, off):
    end = off+4+u32(data,off)
    header = fields(data[off+4:end])
    size = u32(data,end)
    return header,end+4,size


def records(data, off):
    while off < len(data):
        h,start,size = record(data,off)
        yield h,start,size
        off = start+size
    assert off == len(data)


def nano(data):
    sec,nsec = struct.unpack('<II',data)
    return sec*10**9+nsec


def decode(topic, data):
    if topic.startswith('/message/'):
        header=[]; pos=0
        for _ in range(4):
            word,pos=txt(data,pos)
            header.append(word)
        header.append(struct.unpack_from('<Q',data,pos)[0])
        pos += 8
        if topic.endswith('operation'):
            strategy,pos=txt(data,pos)
            params,pos=txt(data,pos)
            assert pos == len(data)
            return (*header,strategy,params)
        if topic.endswith('request'):
            strategy,pos=txt(data,pos)
            # Plan type and urgency begin the application body. The remaining bytes
            # can change in wire codecs, so the handshake uses plan identity.
            return (*header,strategy,data[pos],hashlib.sha256(data[pos:]).digest())
        urgency,accepted,ptype,reason,repeat=struct.unpack_from('<HBBBB',data,pos)
        assert pos+6 == len(data)
        return (*header,accepted,ptype,urgency,reason,repeat)
    if topic in (STATE, STRATEGIC):
        leader_group,pos=txt(data,1)
        leader,pos=txt(data,pos+2)
        leader_track,leader_cmd,slot=struct.unpack_from('<ffB',data,pos)
        host_cmd,desired,actual,pred_head,pred_speed,pred_pos=struct.unpack_from('<ffffff',data,pos+9)
        assert len(data)==pos+38
        # The 4.2.0 platoon control callback copies the state, writes host_cmd_speed,
        # and subtracts 5 m if the strategic actual_gap exceeds 5 m.
        signature = bytearray(data)
        struct.pack_into('<f',signature,pos+9,0.0)
        if topic==STRATEGIC and actual>5.0:
            struct.pack_into('<f',signature,pos+17,actual-5.0)
        return data[0],leader,leader_cmd,slot,host_cmd,hashlib.sha256(signature).digest()
    if topic == '/carma_system_version':
        return txt(data,0)[0].strip()
    _,pos=txt(data,12)  # std_msgs/Header seq/time/frame_id
    if topic==HW:
        return struct.unpack_from('<Hfff',data,pos)
    if topic in PEDALS:
        return struct.unpack_from('<f',data,pos)[0]
    return struct.unpack_from('<d',data,pos)[0] # ctrl_cmd.linear_velocity, twist.linear.x


def extract(data):
    assert data.startswith(b'#ROSBAG V2.0\n')
    meta,_,_=record(data,13)
    connections={}; indexed=Counter(); chunks=[]
    for h,off,size in records(data,struct.unpack('<Q',meta[b'index_pos'])[0]):
        op=h[b'op'][0]
        if op==7:
            info=fields(data[off:off+size])
            connections[u32(h[b'conn'])]=(h[b'topic'].decode(),info.get(b'callerid',b'').decode())
        elif op==6:
            chunks.append(struct.unpack('<Q',h[b'chunk_pos'])[0])
            assert size==8*u32(h[b'count'])
            for conn,count in struct.iter_unpack('<II',data[off:off+size]):
                indexed[conn]+=count
    observed=Counter();streams=defaultdict(list)
    for start in chunks:
        h,off,size=record(data,start)
        assert h[b'op'][0]==5 and h[b'compression']==b'lz4'
        raw=decompress(data[off:off+size])
        assert len(raw)==u32(h[b'size'])
        for h,pos,n in records(raw,0):
            if h[b'op'][0]!=2:
                continue
            conn=u32(h[b'conn']);observed[conn]+=1
            topic,caller=connections[conn]
            if topic in TOPICS:
                streams[topic].append((nano(h[b'time']),decode(topic,raw[pos:pos+n])))
    assert observed==indexed
    for sequence in streams.values():
        sequence.sort(key=lambda x:x[0])
    return streams,len(chunks),sum(observed.values()),sorted({c for t,c in connections.values() if t==STATE})


def quant(values,p):
    if not values:
        return ''
    arr=sorted(values); ix=(len(arr)-1)*p; floor=math.floor(ix);ceil=math.ceil(ix)
    return round(arr[floor]+(arr[ceil]-arr[floor])*(ix-floor),6)


def next_row(seq,t,max_ns=200_000_000):
    idx=bisect.bisect_left(seq,t,key=lambda r:r[0])
    if idx<len(seq) and 0<=seq[idx][0]-t<=max_ns:
        return seq[idx]


def fingerprint(m):
    # Encoded broadcast recipient and unset dynamic ID have explicit placeholder
    # forms on inbound ROS messages. Preserve all other decoded fields.
    return (m[0],m[1] if m[1] else 'UNSET',m[2] if m[2] else '00000000',*m[3:])


def index_rows(rows):
    d=defaultdict(list)
    for stamp,msg in rows:
        d[fingerprint(msg)].append((stamp,msg))
    return d


def typ(streams,direction,kind):
    return streams.get('/message/'+direction+'_mobility_'+kind,[])


def speed_from_status(m):
    if m[5]!='Carma/Platooning' or not m[6].startswith('STATUS|'):
        return None
    for field in m[6].split('|',1)[1].split(','):
        if field.startswith('CMDSPEED:'):
            # The receiver stores float32. Require exact equality at that precision.
            return struct.unpack('<f',struct.pack('<f',float(field.split(':',1)[1])))[0]


def follow(pairs,rx,receiver,fig,src,dst):
    states=receiver.get(STATE,[])
    input_hashes=defaultdict(list)
    output_counts=Counter(row[5] for t,row in states)
    for t,state in receiver.get(STRATEGIC,[]):
        input_hashes[state[5]].append(t)
    event_by_sender=defaultdict(list)
    for time,m in rx:
        if speed_from_status(m) is not None:
            event_by_sender[m[0]].append(time)
    out=[]; candidates=bracket=0
    for tx_time,rx_time,mt,m in pairs:
        wire=speed_from_status(m)
        if wire is None:continue
        i=bisect.bisect_left(states,rx_time,key=lambda row:row[0])
        if i==0 or i==len(states):continue
        ta,before=states[i-1];tb,after=states[i]
        if before[0]!=5 or after[0]!=5 or before[1]!=m[0] or after[1]!=m[0]:continue
        bracket+=1
        targeted=event_by_sender[m[0]]
        if bisect.bisect_right(targeted,tb)-bisect.bisect_right(targeted,ta)!=1:continue
        candidates+=1
        if before[2]==after[2] or wire!=after[2]:continue
        base=dict(figure=fig,sender=src,receiver=dst,ordinal=len(out)+1,
                  tx_to_rx_logger_ms=round((rx_time-tx_time)/1e6,6),
                  receiver_state_bracket_ms=round((tb-ta)/1e6,6),
                  rx_to_new_state_ms=round((tb-rx_time)/1e6,6),
                  prior_leader_cmd_m_s=round(before[2],6),incoming_leader_cmd_m_s=round(wire,6),
                  host_state_cmd_m_s=round(after[4],6))
        inputs=input_hashes[after[5]]
        if len(inputs)==1 and output_counts[after[5]]==1:
            input_time=inputs[0]
            base.update(unique_strategic_to_control_copy=1,
                        rx_to_strategic_ms=round((input_time-rx_time)/1e6,6),
                        strategic_to_control_ms=round((tb-input_time)/1e6,6))
        else:
            base.update(unique_strategic_to_control_copy=0,rx_to_strategic_ms='',strategic_to_control_ms='')
        for label,topic in [('ctrl',CTRL),('measured_speed',SPEED),('hw_cmd',HW),
                            ('throttle_feedback',PEDALS[0]),('brake_feedback',PEDALS[1])]:
            sequence=receiver.get(topic,[])
            obs=next_row(sequence,tb)
            previous_idx=bisect.bisect_left(sequence,tb,key=lambda row:row[0])-1
            previous=sequence[previous_idx] if previous_idx>=0 else None
            if previous and tb-previous[0]>200_000_000:
                previous=None
            if previous and obs:
                old=previous[1][1] if topic==HW else previous[1]
                new=obs[1][1] if topic==HW else obs[1]
                base[label+'_prior_to_state_ms']=round((tb-previous[0])/1e6,6)
                base[label+'_prior_value']=round(old,6)
                base[label+'_first_after_changed']=int(new!=old)
            else:
                for suffix in ('_prior_to_state_ms','_prior_value','_first_after_changed'):
                    base[label+suffix]=''
            base[label+'_after_state_ms']=round((obs[0]-tb)/1e6,6) if obs else ''
            base[label+'_value']=(round(obs[1][1] if topic==HW else obs[1],6) if obs else '')
        out.append(base)
    return out,bracket,candidates


def four_point(a,b,aa,bb,fig):
    def group(st,direction,kind,start,end):
        r=defaultdict(list)
        for t,m in typ(st,direction,kind):
            if (m[0],m[1])==(start,end) and m[3]:
                r[m[3]].append((t,m))
        return r
    reqout=group(a,'outgoing','request',aa,bb); reqin=group(b,'incoming','request',aa,bb)
    ansout=group(b,'outgoing','response',bb,aa); ansin=group(a,'incoming','response',bb,aa)
    keys=sorted(reqout.keys() & reqin.keys() & ansout.keys() & ansin.keys())
    results=[]; ambiguous=0
    for key in keys:
        buckets=[t[key] for t in (reqout,reqin,ansout,ansin)]
        if any(len(bucket)!=1 for bucket in buckets):
            ambiguous+=1;continue
        (t1,r1),(t2,r2),(t3,r3),(t4,r4)=[bucket[0] for bucket in buckets]
        if r1[4:7]!=r2[4:7] or r3[4:]!=r4[4:]:
            continue
        results.append(dict(figure=fig,ordinal=len(results)+1,plan_type=r1[6],response_plan_type=r3[6],
                            accepted=r3[5],same_request_tail=r1[7]==r2[7],
                            requester_roundtrip_ms=round((t4-t1)/1e6,6),
                            responder_processing_ms=round((t3-t2)/1e6,6),
                            outbound_cross_logger_ms=round((t2-t1)/1e6,6),
                            return_cross_logger_ms=round((t4-t3)/1e6,6)))
    return results,len(reqout),len(keys),ambiguous


def dump(path,data):
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=data[0].keys(),lineterminator='\n')
        w.writeheader();w.writerows(data)


def run(src,out):
    out.mkdir(parents=True,exist_ok=True)
    inv=[]; directions=[]; updates=[];handshakes=[];handcounts=[]
    with open(src, "rb") as handle:
        digest = hashlib.file_digest(handle, "sha256").hexdigest()
    if digest != "455e7b3b7859b44324dd9220bc128e3d0fd34e9d170e3d18cc837a36d5864bf8":
        raise ValueError("Archive version differs from the inspected dataset.")
    with ZipFile(src) as archive:
        members={Path(m).name:m for m in archive.namelist()}
        workbook=load_workbook(io.BytesIO(archive.read(members['Filename_ReportImage_Mapping.xlsx'])),
                               read_only=True,data_only=True)
        done=set()
        for row in list(workbook.active.values)[1:]:
            fig=row[0];fleet={};ids={}
            for role,name in zip(row[7::2],row[8::2]):
                if not name:continue
                assert name not in done;done.add(name)
                raw=archive.read(members[name]);st,nchunks,nmsgs,callers=extract(raw);fleet[role]=st
                local={m[0] for t,m in typ(st,'outgoing','operation')}
                assert len(local)==1;ids[role]=local.pop()
                x=dict(figure=fig,test=row[2],run=row[3],vehicle=role,bag=name,
                       bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),chunks=nchunks,all_messages=nmsgs,
                       state_caller=' | '.join(callers),
                       platform_version=' | '.join(sorted({v for t,v in st.get('/carma_system_version',[])})))
                for t in TOPICS[:-1]:x[t]=len(st.get(t,[]))
                inv.append(x)
            for a,b in itertools.permutations(fleet,2):
                tx=typ(fleet[a],'outgoing','operation');rx=typ(fleet[b],'incoming','operation')
                tx=[r for r in tx if r[1][1] in ('','UNSET',ids[b])]
                rx=[r for r in rx if r[1][0]==ids[a] and r[1][1] in ('','UNSET',ids[b])]
                sx,sy=index_rows(tx),index_rows(rx)
                both=sx.keys()&sy.keys();pairs=[]
                for k in both:
                    if len(sx[k])==len(sy[k])==1:
                        (ts,ms),(tr,mr)=sx[k][0],sy[k][0];pairs.append((ts,tr,ms,mr))
                pairs.sort(key=lambda r:r[1])
                dt=[(tr-ts)/1e6 for ts,tr,ms,mr in pairs]
                u,bracket,unique=follow(pairs,rx,fleet[b],fig,a,b);updates.extend(u)
                directions.append(dict(figure=fig,sender=a,receiver=b,tx_eligible_rows=len(tx),rx_eligible_rows=len(rx),
                    common_keys=len(both),common_nonunique_keys=len(both)-len(pairs),unique_pairs=len(pairs),
                    all_seven_decoded_fields_identical=sum(ms==mr for ts,tr,ms,mr in pairs),
                    negative_cross_logger_intervals=sum(v<0 for v in dt),min_delta_ms=min(dt) if dt else '',
                    median_delta_ms=quant(dt,.5),p95_delta_ms=quant(dt,.95),max_delta_ms=max(dt) if dt else '',
                    status_bracketed_by_follower_states=bracket,single_sender_status_in_bracket=unique,
                    changed_leader_speed_exact_f32=len(u)))
                h,first,allfour,multi=four_point(fleet[a],fleet[b],ids[a],ids[b],fig)
                for v in h:v.update(requester=a,responder=b)
                handshakes.extend(h)
                handcounts.append(dict(figure=fig,requester=a,responder=b,unique_plan_ids_requested=first,
                    distinct_plan_ids_in_all_four_logs=allfour,nonunique_in_any_of_four=multi,
                    agreement_on_type_time_and_response_payload=len(h)))
        assert len(done)==len([m for m in members if m.endswith('.bag')])
    for fn,d in [('bag-coverage',inv),('operation-matches',directions),('follower-updates',updates),
                 ('handshake-coverage',handcounts),('four-event-handshakes',handshakes)]:
        if d:dump(out/('ihp2-'+fn+'.csv'),d)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive',type=Path);parser.add_argument('output',type=Path)
    args=parser.parse_args();run(args.archive,args.output)
