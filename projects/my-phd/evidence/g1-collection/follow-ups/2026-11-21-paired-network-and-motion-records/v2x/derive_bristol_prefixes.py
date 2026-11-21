"""Check the first 256 KiB of each of the 30 vehicle text logs and 30 radio captures.
Usage: python derive_bristol_prefixes.py importedData PREFIX_CACHE OUT [--fetch]
"""
import argparse
from collections import Counter
import hashlib
from pathlib import Path
import re
import struct
from urllib.request import Request,urlopen
import numpy as np
from derive_bristol import read_table,write_csv

PREFIX=262144
URL='https://data.bris.ac.uk/datasets/eupowp7h3jl525yxhm3521f57/rawData/'


def text_records(blob):
    packets={'TxCAM':[],'RxCAM':[]}; stations=set(); skipped=0
    for line in blob[:blob.rfind(b'\n')+1].decode('ascii',errors='replace').splitlines():
        parts=line.split(';')
        if 'TX-REQ-CAM' in parts:
            kind='TxCAM';start=parts.index('TX-REQ-CAM')+1;mac=''
        elif 'RX-REQ-CAM' in parts:
            kind='RxCAM';start=parts.index('RX-REQ-CAM')+1;mac=parts[1].lower()
        else:
            skipped+=1
            continue
        data=dict(zip(parts[start::2],parts[start+1::2]))
        try:
            k=(int(data['SeqNum']),int(data['Timestamp']),round(float(data['CamLon'])*1e7),round(float(data['CamLat'])*1e7),mac)
            if kind=='TxCAM':stations.add(data['StationID'])
            packets[kind].append(k)
        except (ValueError,KeyError):
            skipped+=1
    return packets,len(stations),skipped


def in_table(records,table,kind):
    if not records:return 0
    tmin=min(k[1] for k in records);tmax=max(k[1] for k in records)
    idx=np.flatnonzero((table['Timestamp']>=tmin)&(table['Timestamp']<=tmax))
    keyset=set()
    for i in idx:
        if not all(np.isfinite(table[z][i]) for z in ('SeqNum','CamLon','CamLat')):continue
        keyset.add((int(table['SeqNum'][i]),int(table['Timestamp'][i]),round(table['CamLon'][i]*1e7),round(table['CamLat'][i]*1e7),
                    table['RxMAC'][i].lower() if kind=='RxCAM' else ''))
    return sum(k in keyset for k in records)


def pcap(blob):
    end={bytes.fromhex('a1b2c3d4'):'>',bytes.fromhex('d4c3b2a1'):'<'}[blob[:4]]
    link,=struct.unpack_from(end+'I',blob,20)
    if link!=127:raise ValueError('Expected radiotap link-layer type')
    p=24;frames=0;cam=[]
    while p+16<=len(blob):
        sec,us,n,_=struct.unpack_from(end+'4I',blob,p);p+=16
        if p+n>len(blob):break
        b=blob[p:p+n];p+=n;frames+=1
        if len(b)<8:continue
        rt,=struct.unpack_from('<H',b,2);wire=b[rt:]
        # Ordinary 802.11 data, neither ToDS nor FromDS, with ETSI GeoNetworking EtherType.
        if len(wire)<32:continue
        fc,=struct.unpack_from('<H',wire)
        if fc&0x000c!=8 or fc&0x0300:continue
        header=26 if fc&0x0080 else 24
        if wire[header:header+8]!=bytes.fromhex('aaaa030000008947'):continue
        cam.append((sec*10**6+us,wire[10:16].hex(':')))
    return frames,cam


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for a in ('data','cache','out'):p.add_argument(a,type=Path)
    p.add_argument('--fetch',action='store_true');a=p.parse_args();results=[]
    for txpath in sorted(a.data.glob('*/vehNo_*_TxCAM_*.mat')):
        day=txpath.parent.name;node,radio,slot=re.fullmatch(r'vehNo_(\d+)_TxCAM_(HP|LP)_(af|mr)',txpath.stem).groups()
        root=URL+day+'/OBU-'+node+'-'+day+'-'+{'mr':'Morning','af':'Afternoon'}[slot]+'/log_'+radio
        row=dict(day=day,node=node,radio=radio,session=slot)
        for mode,url in [('text',root+'.txt'),('capture',root+'_tcpd.pcap')]:
            path=a.cache/day/(txpath.stem+'-'+mode+'.bin')
            if not path.exists() and a.fetch:
                path.parent.mkdir(parents=True,exist_ok=True)
                req=Request(url+'?g1prefix=262144',headers={'Range':f'bytes=0-{PREFIX-1}'})
                with urlopen(req,timeout=60) as res:
                    if res.status!=206 or not res.headers['Content-Range'].startswith(f'bytes 0-{PREFIX-1}/'):raise ValueError('Wrong range')
                    path.write_bytes(res.read())
            blob=path.read_bytes()
            if len(blob)!=PREFIX:raise ValueError('Incomplete file prefix')
            row[mode+'_url']=url;row[mode+'_prefix_sha256']=hashlib.sha256(blob).hexdigest()
            if mode=='text':
                packets,distinct,other=text_records(blob)
                for kind,events in packets.items():
                    table=read_table(txpath.with_name(txpath.name.replace('TxCAM',kind)))
                    row[kind+'_raw_complete_rows']=len(events)
                    row[kind+'_same_seq_time_coords_and_source_in_mat']=in_table(events,table,kind)
                row['distinct_station_ids_in_raw_tx_prefix']=distinct
                row['other_or_incomplete_text_records']=other
            else:
                frames,packets=pcap(blob)
                table=read_table(txpath.with_name(txpath.name.replace('TxCAM','tcpDump')))
                us=np.rint(table['timeStamp']*1e6)
                captured=set()
                if packets:
                    lo,hi=min(k[0] for k in packets),max(k[0] for k in packets)
                    for i in np.flatnonzero((us>=lo)&(us<=hi)):captured.add((int(us[i]),table['srcAddress'][i].lower()))
                row['capture_complete_frames']=frames;row['capture_geo_data_frames']=len(packets)
                row['capture_same_device_and_microsecond_in_mat']=sum(k in captured for k in packets)
        results.append(row)
    a.out.mkdir(exist_ok=True,parents=True)
    write_csv(a.out/'bristol-raw-prefixes.csv',results)


if __name__=='__main__':main()
