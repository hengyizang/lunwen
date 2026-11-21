"""Compare RoboLoc-G source timestamps, ROS2 MCAP records, and gantry/motion capture.

Usage: python derive_roboloc.py RAW OUTPUT   (Python 3.9+, NumPy and tzdata)
All source archive names, geometry and unit/identity assumptions are in the data receipt.
"""
from argparse import ArgumentParser
from collections import Counter, defaultdict
import csv
from datetime import datetime
import io
from pathlib import Path
import struct
from zipfile import ZipFile
from zoneinfo import ZoneInfo
import numpy as np

# Centimetres in gantry coordinates, source manual page 3. The FTM suffix recorded in AP mode
# is consistently +1 from each documented suffix. Treat this association as conditional.
FTM = {'87c7':(196.10,-32.52,-12.0),'b9dd':(-39.22,234.32,-12.0),
       'dbf1':(336.96,562.66,-12.0),'74e9':(555.14,351.84,-12.0)}
UWB = {'685a':(120.92,-72.95,-84.8),'6867':(308.24,-71.36,-213.3),
       '685b':(-38.97,330.65,-12.5),'687c':(40.95,563.00,-12.5),'686f':(555.20,203.36,-12.5)}
TOPICS = {'/gtec/ftm':'FTM','/gtec/uwb/ranging/pozyx':'UWB'}


def records(buffer):
    pos = 0
    while pos < len(buffer):
        op,size = struct.unpack_from('<BQ',buffer,pos)
        pos += 9
        data = buffer[pos:pos+size]
        if len(data)!=size: raise ValueError('Truncated MCAP record')
        pos += size
        yield op,data


def ros_messages(blob):
    if blob[:8]!=blob[-8:] or blob[:8]!=b'\x89MCAP0\r\n':
        raise ValueError('Invalid MCAP magic')
    channels={}
    result=defaultdict(dict)
    def walk(buffer):
        for op,data in records(buffer):
            if op==4:
                ch, _, size = struct.unpack_from('<HHI',data)
                channels[ch]=data[8:8+size].decode()
            elif op==6:
                size=struct.unpack_from('<Q',data,16)[0]
                encoding_len=struct.unpack_from('<I',data,28)[0]
                if encoding_len!=0 or size!=len(data)-40:raise ValueError('Expected uncompressed chunk')
                walk(data[40:])
            elif op==5:
                ch,seq,log,pub=struct.unpack_from('<HIQQ',data)
                tag=TOPICS.get(channels[ch])
                if tag is None:continue
                if log in result[tag] or data[22:26]!=b'\x00\x01\x00\x00':raise ValueError('Unexpected CDR message')
                body=data[26:]
                if tag=='UWB':
                    anchor,tag_id,ran,sequence=struct.unpack_from('<hhii',body)
                    record=(anchor,tag_id,ran,sequence)
                else:
                    n=struct.unpack_from('<I',body)[0]
                    anchor=body[4:4+n-1].decode()
                    p=(4+n+3)//4*4
                    est,raw,dist,num,frames=struct.unpack_from('<iifiI',body,p)
                    p+=20
                    vals=[]
                    for _ in range(frames):
                        rss,rtt=struct.unpack_from('<ii',body,p)
                        p=(p+8+7)//8*8
                        vals.append((rss,rtt,*struct.unpack_from('<qqqq',body,p)))
                        p+=32
                    if p!=len(body):raise ValueError('Extra FTM fields')
                    record=(anchor,est,raw,dist,num,vals)
                result[tag][log]=(pub,record)
    walk(blob[8:-8])
    return result


def values(arch,name):
    with arch.open(name) as raw,io.TextIOWrapper(raw) as f:return list(csv.DictReader(f))


def off_grid(ts,seconds,xyz):
    points = np.array([np.interp(ts,seconds,xyz[:,i]) for i in range(3)]).T
    points[(ts<seconds[0])|(ts>seconds[-1])] = np.nan
    return points


def rounded(v):
    return round(float(v),6) if np.isfinite(v) else ''


def rms(v):
    return np.sqrt(np.mean(np.square(v))) if len(v) else np.nan


def xyzrows(rows,name):
    return np.array([[float(row[name+'.'+col]) for col in 'XYZ'] for row in rows])


def optical(arch, name, trial, times, ideal):
    with arch.open(name) as f,io.TextIOWrapper(f) as txt:
        rows=csv.reader(txt)
        meta=next(rows)
        meta=dict(zip(meta[::2],meta[1::2]))
        # Motive writes local civil time. A Coruña was on summer time that day.
        # The capture field omits AM/PM. The adjacent take name supplies AM/PM.
        daypart=meta['Take Name'].split()[-1]
        start=datetime.strptime(meta['Capture Start Time'].strip()+' '+daypart,'%Y-%m-%d %I.%M.%S.%f %p')
        absolute=start.replace(tzinfo=ZoneInfo('Europe/Madrid')).timestamp()
        empty,types,names,ids,roles,axes=[next(rows) for _ in range(6)]
        cols=[i for i in range(len(axes)) if names[i]=='Grua' and types[i]=='Rigid Body' and roles[i]=='Position']
        assert [axes[i] for i in cols]==list('XYZ')
        measured=[]
        total=0
        for row in rows:
            total+=1
            if all(row[i] for i in cols):measured.append([float(row[1]),*(float(row[i]) for i in cols)])
        assert total==int(meta['Total Exported Frames'])
    arr=np.array(measured)
    out=[]
    # Same common time support across all shifts for a fair three-way comparison.
    base=absolute+arr[:,0]
    support=(base-.016>=times[0])&(base+.016<=times[-1])
    for shift in (-.016,0.,.016):
        support &= np.all(np.isfinite(off_grid(base+shift,times,ideal)),axis=1)
    for shift in (-.016,0.,.016):
        proj=off_grid(base[support]+shift,times,ideal)
        err=arr[support,1:]-proj
        out.append(dict(trajectory=trial,optical_time_shift_ms=int(shift*1000),optical_frames=total,
            valid_optical_xyz=len(arr),common_support_frames=int(support.sum()),
            euclidean_rmse_mm=rounded(rms(np.linalg.norm(err,axis=1))),
            median_euclidean_error_mm=rounded(np.median(np.linalg.norm(err,axis=1))) if err.size else ''))
    return out


def save(path,rows):
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=rows[0],lineterminator='\n');w.writeheader();w.writerows(rows)


def trial_tables(trial, archives):
    truth,gantry,opt,tab,bag=archives
    gt=values(truth,'GROUND_TRUTH/'+trial+'_ground_truth_gantry.csv')
    target=values(truth,'GROUND_TRUTH/'+trial+'_ground_truth_optitrack.csv')
    gr=values(gantry,'GANTRY_MEASUREMENTS/'+trial+'_gantry.csv')
    seconds=np.array([float(r['time']) for r in gt])
    if not (np.all(np.diff(seconds)>=0) and np.allclose(seconds,[float(r['time']) for r in gr],rtol=0,atol=3e-7) and
            np.allclose(xyzrows(gt,'Grua'),[[float(r[c]) for c in 'xyz'] for r in gr],rtol=0,atol=1e-9)): raise ValueError('Gantry and ground truth disagree')
    assert np.array_equal(seconds,[float(r['time']) for r in target])
    source_count=len(gt)
    retain=np.r_[True,np.diff(seconds)>0]
    conflict_times={seconds[j] for j in np.flatnonzero(~retain) if gt[j]!=gt[j-1] or target[j]!=target[j-1]}
    for j,t in enumerate(seconds):
        if t in conflict_times:
            for row in (gt[j],target[j]):
                for key in row:
                    if key!='time':row[key]='nan'
    seconds=seconds[retain]
    gt=[v for v,keep in zip(gt,retain) if keep]
    target=[v for v,keep in zip(target,retain) if keep]
    motion=optical(opt,'OPTITRACK_MEASUREMENTS_CSV/'+trial+'_optitrack.csv',trial,seconds,xyzrows(target,'Grua'))
    member,=[n for n in bag.namelist() if '/UWB_FTM_IMU/'+trial+'/' in n and n.endswith('.mcap')]
    messages=ros_messages(bag.read(member))
    clocks,geometry=[],[]
    for mode,suffix in [('FTM','gtec-ftm.csv'),('UWB','gtec-uwb-ranging-pozyx.csv')]:
        rows=values(tab,'SENSORS_MEASUREMENTS_CSV/UWB_FTM_IMU/'+trial+'/'+suffix)
        grouped=defaultdict(list)
        for r in rows:grouped[int(r['timestamp'])].append(r)
        raw=messages[mode]
        if set(grouped)!=set(raw):raise ValueError('CSV stamps and MCAP log stamps do not match')
        byanchor=defaultdict(list)
        frames=0
        for log,(pub,record) in raw.items():
            sub=grouped[log]
            first=sub[0]
            if mode=='UWB':
                assert len(sub)==1 and record==tuple(int(first[k]) for k in ('anchor_id','tag_id','range','seq'))
                key=format(record[0],'x')
                # Published CSV integer has table values around 1000–6000 despite manual saying metres.
                literal=float(first['range'])
                meter=literal/1000.
            else:
                aid,est,rttr,dist,num,values_=record
                assert aid==first['anchor_id'] and num==int(first['num_frames'])
                assert est==int(first['rtt_est']) and rttr==int(first['rtt_raw']) and abs(dist-float(first['dist_est']))<1e-8
                cols=['frames.rssi','frames.rtt','frames.t1','frames.t2','frames.t3','frames.t4']
                assert len(sub)==len(values_) and all(int(row['array_index'])==i and vals==tuple(int(row[k]) for k in cols) for i,(vals,row) in enumerate(zip(values_,sub)))
                frames+=len(values_)
                key=aid.replace(':','')[-4:].lower()
                literal=meter=dist
            byanchor[key].append((log,meter,literal))
        lags=np.array([(log-pub)/1e6 for log,(pub,_) in raw.items()])
        csv_keys=set(grouped)
        clocks.append(dict(trajectory=trial,radio=mode,csv_rows=len(rows),mcap_messages=len(raw),
            csv_distinct_time_match_log=len(csv_keys),csv_distinct_time_also_in_publish=len(csv_keys & {pub for pub,_ in raw.values()}),
            payload_checked_messages=len(raw),individual_ftm_frames=frames,negative_log_minus_publish=int((lags<0).sum()),
            log_minus_publish_median_ms=rounded(np.median(lags)),log_minus_publish_p95_ms=rounded(np.quantile(lags,.95)),
            log_minus_publish_max_ms=rounded(lags.max())))
        pos=xyzrows(gt,mode+'_tag')/1000
        anchors=FTM if mode=='FTM' else UWB
        for key,data in sorted(byanchor.items()):
            if key not in anchors: raise ValueError('Unknown anchor '+key)
            times=np.array([t/1e9 for t,_,_ in data])
            p=off_grid(times,seconds,pos)
            mask=np.all(np.isfinite(p),axis=1)
            rg=np.linalg.norm(p[mask]-np.array(anchors[key])/100,axis=1)
            sensor=np.array([v for t,v,l in data])[mask];literal=np.array([l for t,v,l in data])[mask]
            err=sensor-rg
            geometry.append(dict(trajectory=trial,radio=mode,recorded_anchor_suffix=key,gantry_samples=source_count,distinct_gantry_time=len(gt),conflicting_gantry_time=len(conflict_times),
                received_messages=len(data),bracketed_by_gantry=int(mask.sum()),
                median_reference_range_m=rounded(np.median(rg)) if len(rg) else '',
                median_sensor_range_as_csv_numeric=rounded(np.median(literal)) if len(literal) else '',
                direct_numeric_vs_reference_rmse=rounded(rms(literal-rg)),
                assumed_units='m' if mode=='FTM' else 'mm',metric_comparison_rmse_m=rounded(rms(err)),
                median_signed_error_m=rounded(np.median(err)) if len(err) else ''))
    return clocks,geometry,motion


def main():
    p=ArgumentParser(description=__doc__);p.add_argument('raw',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    inputs=['GROUND_TRUTH','GANTRY_MEASUREMENTS','OPTITRACK_MEASUREMENTS_CSV','SENSORS_MEASUREMENTS_CSV','SENSORS_MEASUREMENTS_ROS2BAGS']
    from contextlib import ExitStack
    with ExitStack() as stack:
        archives=[stack.enter_context(ZipFile(a.raw/(n+'.zip'))) for n in inputs]
        tables=[[],[],[]]
        for trial in ['circle','random1','random2','still','zigzag1','zigzag2','zigzag3','zigzag4']:
            for out,rows in zip(tables,trial_tables(trial,archives)):out.extend(rows)
    a.output.mkdir(parents=True,exist_ok=True)
    for name,data in zip(['roboloc-mcap-clocks','roboloc-gantry-ranging','roboloc-optical-time-shift'],tables):
        save(a.output/(name+'.csv'),data)


if __name__=='__main__':main()
