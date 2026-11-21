"""Audit three distinct 5G-MOBIX platooning deposits. Call with ROOT OUT.

ROOT contains RECORD.json from https://zenodo.org/api/records/RECORD plus a
RECORD directory holding its original ZIPs. Requires Python 3.11+ and openpyxl.
"""
from collections import Counter, defaultdict
import argparse
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import re
from statistics import median
import xml.etree.ElementTree as ET
from zipfile import ZipFile

import openpyxl


SITES={'7348877':'DE','7348882':'CN','7348870':'GR-TR'}
APP='timestamp senderstationid receiverstationid longitude latitude senderspeed receiverspeed flowdirection communicationprotocol ratmode messagetype datarate e2elatency packetstx packetsrx'.split()
ACCESS='timestamp senderstationid receiverstationid longitude latitude senderspeed receiverspeed flowdirection communicationprotocol ratmode cellularmnc cellularmcc ltepci ltersrp ltersrq nrarfcn nrpci nrssrsrp nrssrsrq'.split()
EVENT='timestamp senderstationid receiverstationid longitude latitude senderspeed receiverspeed flowdirection communicationprotocol ratmode messagetype handoversuccess handoverperiod'.split()


def write(path,rows):
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n')
        w.writeheader()
        w.writerows(rows)


def numeric(v):
    try:
        n=float(v)
        return n if math.isfinite(n) else None
    except (ValueError,TypeError):
        return None


def split_csv(data):
    return [[c.strip() for c in row] for row in csv.reader(io.StringIO(data.decode('utf-8-sig'))) if any(c.strip() for c in row)]


def german(data,filename):
    rows=split_csv(data)
    if not rows:return dict(kind='empty',header='empty',source_nonempty_lines_after_header=0,numeric_rows=0,quarantined_lines=0)
    if numeric(rows[0][0]) is None:
        header=[c.lower() for c in rows.pop(0)]
        source='published'
    else:
        templates={'app':APP,'acc':ACCESS,'han':EVENT}
        header=templates[filename.lower()[:3]]
        source='inferred from matching headed file'
    source_lines=len(rows)
    rows=[row for row in rows if len(row)==len(header) and numeric(row[0]) is not None]
    kind='handover' if 'handoversuccess' in header else 'application' if 'datarate' in header else 'network' if 'totalthroughput' in header else 'access'
    result=dict(kind=kind,header=source,source_nonempty_lines_after_header=source_lines,numeric_rows=len(rows),quarantined_lines=source_lines-len(rows))
    if 'packetstx' not in header:return result
    idx={v:i for i,v in enumerate(header)}
    key= 'timestamp senderstationid receiverstationid flowdirection communicationprotocol ratmode messagetype'.split()
    buckets=defaultdict(set)
    repeated=Counter(tuple(row) for row in rows)
    invalid=over=neg=0
    for row in rows:
        tx,rx,lat=[numeric(row[idx[k]]) for k in ('packetstx','packetsrx','e2elatency')]
        invalid+=int(tx is None or rx is None or tx<0 or rx<0)
        over+=int(tx is not None and rx is not None and rx>tx)
        neg+=int(lat is not None and lat<0)
        buckets[tuple(row[idx[k]] for k in key)].add((tx,rx,lat))
    result.update(unique_complete_rows=len(repeated),distinct_observation_keys=len(buckets),
                  keys_with_disagreeing_counts_or_latency=sum(len(v)>1 for v in buckets.values()),
                  missing_or_negative_counts=invalid,rx_greater_than_tx=over,negative_latency=neg)
    return result


def china(data):
    rows=split_csv(data)
    head=[s.lower() for s in rows.pop(0)]
    if not all(len(row)==len(head) for row in rows):raise ValueError('Invalid row length')
    tv=[float(row[head.index('transfer')]) for row in rows]
    bw=[float(row[head.index('bandwidth')]) for row in rows]
    ranges=[]
    if 'interval' in head:
        ranges=[tuple(map(float,row[head.index('interval')].split('-'))) for row in rows]
    sender_cols=[i for i,c in enumerate(head) if c=='senderstationid']
    return dict(rows=len(rows),sender_columns=len(sender_cols),sender_columns_disagree=sum(len({line[i] for i in sender_cols})>1 for line in rows),
                unique_pairs_of_transfer_bandwidth=len(set(zip(tv,bw))),transfer_median=median(tv),bandwidth_median=median(bw),
                explicit_intervals=len(ranges),first_interval_begin=ranges[0][0] if ranges else '',last_interval_end=ranges[-1][1] if ranges else '',
                consecutive_1_unit_intervals=int(all(b-a==1 for a,b in ranges) and all(p[1]==n[0] for p,n in zip(ranges,ranges[1:]))) if ranges else '',
                bandwidth_transfer_corr_check_within_1_of_8_192_x=sum(abs(b-8.192*t)<=1 for t,b in zip(tv,bw)))


def grtr(data):
    book=openpyxl.load_workbook(io.BytesIO(data),read_only=True,data_only=True)
    sheet,=book.worksheets
    it=sheet.values
    head=[str(s).strip().lower() for s in next(it)]
    left,right,t,flow,sender,receiver=[head.index(k) for k in ('messagestx','messagesrx','timestamp','flowdirection','senderstationid','receiverstationid')]
    rows=[x for x in it if any(c is not None for c in x)]
    path=[(x[t],numeric(x[left]),numeric(x[right])) for x in rows]
    usable=[(tx,rx) for _,tx,rx in path if tx is not None and rx is not None]
    flowset=lambda idx:'|'.join(sorted(set(str(x[idx]) for x in rows if x[idx] is not None)))
    return dict(rows=len(rows),both_counts=len(usable),rx_greater_than_tx=sum(rx>tx for tx,rx in usable),
                tx_zero_rx_positive=sum(tx==0 and rx>0 for tx,rx in usable),flow_labels=flowset(flow),senders=flowset(sender),receivers=flowset(receiver),
                distinct_timestamps=len({v for v,_,_ in path if v is not None})),path


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('root',type=Path);p.add_argument('out',type=Path)
    args=p.parse_args();args.out.mkdir(parents=True,exist_ok=True)
    archives=[];de=[];cn=[];gr=[];curves={};aliases=defaultdict(list)
    for record,site in SITES.items():
        registry=json.loads((args.root/(record+'.json')).read_text())
        for file in sorted(registry['files'],key=lambda f:f['key']):
            path=args.root/record/file['key']
            b=path.read_bytes()
            if len(b)!=file['size'] or 'md5:'+hashlib.md5(b).hexdigest()!=file['checksum']:raise ValueError(path.name)
            upload=int(path.name.split('-')[0])
            with ZipFile(io.BytesIO(b)) as archive:
                xml=ET.fromstring(archive.read('test_data_description.xml'))
                tag=lambda name:xml.findtext('.//'+name,default='').strip()
                fact=dict(site=site,upload=upload,archive=file['key'],bytes=len(b),verified_md5=file['checksum'],case=tag('Test_Case_Identifier'),
                          run=tag('Test_Run_Identifier'),scenario=tag('Evaluation_Scenario'),declared_qc=tag('DQCT_Status'),
                          declared_start=tag('Start_Timestamp'),declared_end=tag('End_Timestamp'))
                archives.append(fact)
                for filename in sorted(archive.namelist()):
                    if not filename.lower().endswith(('.csv','.xlsx')):continue
                    data=archive.read(filename);digest=hashlib.sha256(data).hexdigest()
                    base=dict(upload=upload,case=fact['case'],run=fact['run'],member=filename,sha256=digest)
                    if site=='DE':de.append(dict(**base,**german(data,filename)))
                    elif site=='CN':cn.append(dict(**base,**china(data)))
                    else:
                        value,curve=grtr(data)
                        gr.append(dict(**base,**value))
                        aliases[digest].append((upload,filename))
                        curves[digest]=curve
    for row in de:
        for k in ['unique_complete_rows','distinct_observation_keys','keys_with_disagreeing_counts_or_latency','missing_or_negative_counts','rx_greater_than_tx','negative_latency']:
            row.setdefault(k,'')
    pairs=defaultdict(dict)
    for digest,files in aliases.items():
        _,name=files[0]
        match=re.search(r'(DIRECT|PUBLIC).*?(DOWNLINK|UPLINK)\s*(\d+)',name.upper())
        if not match:raise ValueError(name)
        sides=pairs[match[1],int(match[3])]
        if match[2] in sides:raise ValueError('Ambiguous direction '+name)
        sides[match[2]]=digest
    contrasts=[]
    for (network,num),sides in sorted(pairs.items()):
        row=dict(connection=network,pair_id=num,uplink_sha256=sides.get('UPLINK',''),downlink_sha256=sides.get('DOWNLINK',''))
        for side in ('UPLINK','DOWNLINK'):
            digest=sides.get(side);row[side.lower()+'_archive_occurrences']=len(aliases[digest]) if digest else 0
        both=len(sides)==2
        up=curves[sides['UPLINK']] if both else []
        down=curves[sides['DOWNLINK']] if both else []
        # Source timestamps can repeat. The comparisons below always use published row order.
        common=list(zip(up,down));valid=[(a,b) for a,b in common if all(v is not None for v in [*a,*b])]
        row.update(both_files=int(both),shared_row_positions=len(common),complete_positions=len(valid),
                   same_stored_time=sum(a[0]==b[0] for a,b in valid),same_tx_and_rx=sum(a[1:]==b[1:] for a,b in valid),
                   same_time_tx_rx=sum(a==b for a,b in valid),unpaired_tail_rows=abs(len(up)-len(down)) if both else '')
        contrasts.append(row)
    for name,rows in [('mobix-archive-audit',archives),('mobix-de-files',de),('mobix-cn-windows',cn),('mobix-grtr-workbooks',gr),('mobix-grtr-endpoint-pairs',contrasts)]:
        write(args.out/(name+'.csv'),rows)


if __name__=='__main__':
    main()
