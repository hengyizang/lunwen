"""Audit four hardware timestamps and the reference notebook's timestamp conversion.

Run python check_slate.py SLATE-PTP.zip OUTPUT_DIRECTORY.
"""
from argparse import ArgumentParser
from collections import Counter
import csv
import hashlib
import io
import json
import math
from pathlib import Path
from statistics import median
from zipfile import ZipFile


def write(out, name, rows):
    with (out/name).open('w',newline='') as f:
        w=csv.DictWriter(f,rows[0],lineterminator='\n')
        w.writeheader()
        w.writerows(rows)


def q95(values):
    a=sorted(values); return a[math.ceil(0.95*len(a))-1]


def inspect(z, path):
    counter=Counter()
    forward,reverse,exact,supplied,changes,age=[],[],[],[],[],[]
    prev_seq=prev_capture=last_forward=delay=None
    for r in csv.DictReader(io.TextIOWrapper(z.open(path))):
        seq,capture=int(r['seq_id']),int(r['capture_ts'])
        if prev_seq is not None:
            counter['seq_nonunit']+=seq!=prev_seq+1
            counter['ts_back']+=capture<prev_capture
        prev_seq,prev_capture=seq,capture
        fields=[i for i in ('t1','t2','t3','t4') if r[i]!='']
        kind=r['msg_type']; assert (kind,fields) in [('sync',['t1','t2']),('delay_req',['t3','t4'])]
        a,b=map(int,(r[f] for f in fields)); af,bf=int(float(a)),int(float(b))
        counter['timestamp_rounded']+= int(af!=a)+int(bf!=b)
        counter['rounded_pairdiff']+=(bf-af)!=(b-a)
        counter['max_epoch_error']=max(counter['max_epoch_error'],abs(af-a),abs(bf-b))
        if kind=='sync':
            forward.append(b-a)
            last_forward=(b-a,bf-af)
            if delay is not None:
                e=(b-a)-delay[0]; other=(bf-af)-delay[1]
                exact.append(e); supplied.append(other); changes.append(other-e);age.append(capture-delay[2])
        else:
            reverse.append(b-a)
            if last_forward is not None:
                delay=((last_forward[0]+b-a)//2,(last_forward[1]+bf-af)//2,capture)
    rmse=lambda v:round(math.sqrt(sum(x*x for x in v)/len(v)),6)
    tag=Path(path).name
    return (
       dict(file=tag,crc32=f'{z.getinfo(path).CRC:08x}',rows=len(forward)+len(reverse),
        sync_samples=len(forward),delay_req_samples=len(reverse),full_quartet_rows=0,
        seq_nonunit_steps=counter['seq_nonunit'],capture_time_backsteps=counter['ts_back'],
        min_forward_ns=min(forward),median_forward_ns=median(forward),p95_forward_ns=q95(forward),max_forward_ns=max(forward),
        min_reverse_ns=min(reverse),median_reverse_ns=median(reverse),p95_reverse_ns=q95(reverse),max_reverse_ns=max(reverse),
        half_difference_of_directional_medians_ns=(median(forward)-median(reverse))/2),
       dict(file=tag,eligible_sync_offset_estimates=len(exact),nonempty_t1_to_t4_values=2*(len(forward)+len(reverse)),
        epoch_values_altered_by_float=counter['timestamp_rounded'],max_abs_epoch_rounding_ns=counter['max_epoch_error'],
        one_direction_subtractions_altered=counter['rounded_pairdiff'],offset_estimates_altered=sum(x!=0 for x in changes),
        altered_by_more_than_20ns=sum(abs(x)>20 for x in changes),max_abs_offset_change_ns=max(map(abs,changes)),
        median_abs_offset_change_ns=median(map(abs,changes)),p95_abs_offset_change_ns=q95(list(map(abs,changes))),
        rms_estimated_offset_integer_ns=rmse(exact),rms_estimated_offset_notebook_float_ns=rmse(supplied),
        last_delay_update_to_sync_median_ms=round(median(age)/1e6,6),last_delay_update_to_sync_max_ms=round(max(age)/1e6,6)))


def main(archive,out):
    with archive.open('rb') as f:
        assert hashlib.file_digest(f,'md5').hexdigest()=='40109ef71fd232f2679346bacbba1f5f'
    with ZipFile(archive) as z:
        assert z.testzip() is None
        cells=json.loads(z.read('ptp_pipeline.ipynb'))['cells']
        code='\n'.join(''.join(c['source']) for c in cells if c['cell_type']=='code')
        assert 'return int(float(value))' in code
        a=[];b=[]
        for name in sorted(n for n in z.namelist() if n.startswith('data/') and n.endswith('.csv')):
            x,y=inspect(z,name);a.append(x);b.append(y)
    out.mkdir(parents=True,exist_ok=True)
    write(out,'slate-directional-delays.csv',a)
    write(out,'slate-clock-precision.csv',b)


if __name__=='__main__':
    parser=ArgumentParser(description=__doc__)
    parser.add_argument('archive',type=Path)
    parser.add_argument('output',type=Path)
    args=parser.parse_args()
    main(args.archive,args.output)
