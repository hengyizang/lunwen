"""Summarize PPS scope exports, PTPd reports and capture time boundaries (stdlib).
Usage: python derive_mobile_sync.py MOBILE_ZIP OUTPUT_DIRECTORY
"""
import argparse
import csv
import hashlib
import io
import math
import re
import statistics
import struct
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZipFile

TIME = re.compile(r'\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d{6},')
UTC = timezone.utc


def write(path, rows):
    with path.open("w", encoding="utf-8", newline="") as out:
        w = csv.DictWriter(out, fieldnames=rows[0].keys(), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def quantile(values, p):
    x = sorted(values)
    pos = (len(x)-1)*p
    k = math.floor(pos)
    return x[k] + (pos-k)*(x[min(k+1,len(x)-1)] - x[k])


def stats(values):
    absolute = [abs(v) for v in values]
    return dict(valid_values=len(values), signed_median_ms=round(statistics.median(values),9),
                abs_median_ms=round(statistics.median(absolute),9),
                abs_p95_ms=round(quantile(absolute,0.95),9),
                abs_max_ms=round(max(absolute),9), within_1_ms=sum(v<=1 for v in absolute))


def scope(name, buf):
    rows = list(csv.reader(io.StringIO(buf.decode('utf-8-sig'))))
    ids = [int(row[-2]) for row in rows]
    if ids != list(range(ids[0],ids[0]+len(ids))):
        raise ValueError("Unexpected sample-counter gap")
    dates = [row[0] for row in rows if len(row)==3]
    valid = [1000*float(row[-1]) for row in rows if row[-1]!='null']
    if not all(math.isfinite(v) for v in valid):
        raise ValueError("Non-finite PPS record")
    return dict(file=name,sha256=hashlib.sha256(buf).hexdigest(),scope_rows=len(rows),
                missing_values=len(rows)-len(valid),first_counter=ids[0],last_counter=ids[-1],
                first_reported_utc=dates[0] if dates else "",
                last_reported_utc=dates[-1] if dates else "",**stats(valid))


def ptpd(name, buf):
    states = Counter()
    times, values = [], []
    lines_with_joined = restored_boundaries = 0
    for line in buf.decode('utf-8-sig').splitlines():
        starts = [m.start() for m in TIME.finditer(line)]
        if not starts:
            if line.strip() and not line.lstrip().startswith('#'):
                raise ValueError("Nonempty line without a timestamp/header")
            continue
        if len(starts)>1:
            lines_with_joined += 1
            restored_boundaries += len(starts)-1
        for start, end in zip(starts, starts[1:]+[len(line)]):
            row = next(csv.reader([line[start:end]], skipinitialspace=True))
            states[row[1]] += 1
            if row[1]=='slv':
                if len(row)!=17 or not math.isfinite(float(row[4])):
                    raise ValueError("Invalid slave report")
                times.append(row[0])
                values.append(float(row[4])*1000)
    return dict(file=name,sha256=hashlib.sha256(buf).hexdigest(),timestamped_records=sum(states.values()),
                joined_lines=lines_with_joined,recovered_record_boundaries=restored_boundaries,
                state_counts='|'.join(f'{k}={v}' for k,v in sorted(states.items())),
                first_slave_local=times[0],last_slave_local=times[-1],**stats(values))


def capture(name, buf):
    cursor = 0
    timestamp_ticks = []
    ptp = Counter()
    interfaces = []
    while cursor < len(buf):
        kind, length = struct.unpack_from('<II', buf, cursor)
        if length<12 or cursor+length>len(buf) or struct.unpack_from('<I',buf,cursor+length-4)[0]!=length:
            raise ValueError("Invalid pcapng block")
        if kind==0x0a0d0d0a and buf[cursor+8:cursor+12]!=b'\x4d\x3c\x2b\x1a':
            raise ValueError("Expected little-endian capture section")
        if kind==1:
            linktype,_,_ = struct.unpack_from('<HHI',buf,cursor+8)
            opts = cursor+16
            tick = 1000
            while opts+4<=cursor+length-4:
                code,n = struct.unpack_from('<HH',buf,opts)
                if not code: break
                if code==9:
                    if n!=1 or buf[opts+4]!=9:raise ValueError("Unexpected timestamp resolution")
                    tick=1
                opts+=4+(n+3)//4*4
            if linktype!=12:raise ValueError("Expected raw IP capture")
            interfaces.append(tick)
        if kind==6:
            interface,high,low,plen,_ = struct.unpack_from('<IIIII',buf,cursor+8)
            timestamp_ticks.append(((high<<32)+low)*interfaces[interface])
            packet = buf[cursor+28:cursor+28+plen]
            if packet and packet[0]>>4==4 and len(packet)>=20 and packet[9]==17:
                k = (packet[0]&15)*4
                if len(packet)>=k+8+34:
                    dest=struct.unpack_from('>H',packet,k+2)[0]
                    if dest in (319,320) and packet[k+9]&15==2:
                        ptp[packet[k+8]&15] += 1
        cursor += length
    lo, hi = min(timestamp_ticks), max(timestamp_ticks)
    def iso(ns):
        return datetime.fromtimestamp(ns//1_000_000_000,UTC).strftime('%Y-%m-%dT%H:%M:%S')+f'.{ns%1_000_000_000:09d}Z'
    return dict(file=name,sha256=hashlib.sha256(buf).hexdigest(),packet_records=len(timestamp_ticks),
                earliest_capture_utc=iso(lo),latest_capture_utc=iso(hi),span_s=round((hi-lo)/1e9,9),
                ipv4_udp_ptp_v2_packets=sum(ptp.values()),sync=ptp[0],delay_req=ptp[1],
                follow_up=ptp[8],delay_resp=ptp[9],announce=ptp[11],signaling=ptp[12])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('archive',type=Path)
    p.add_argument('output',type=Path)
    a=p.parse_args()
    if hashlib.md5(a.archive.read_bytes()).hexdigest()!='945aefa3013bc926d748f7e820275069':
        raise ValueError("Unexpected release checksum")
    outputs = {'pps':[],'ptpd':[],'captures':[]}
    with ZipFile(a.archive) as z:
        for name in sorted(z.namelist()):
            if name.endswith('README.txt'):continue
            for ext,table,func in [('.txt','pps',scope),('.log','ptpd',ptpd),('.pcapng','captures',capture)]:
                if name.endswith(ext):
                    outputs[table].append(func(name,z.read(name)))
    if [len(r) for r in outputs.values()]!=[4,8,2]:raise ValueError("Incomplete release")
    a.output.mkdir(parents=True,exist_ok=True)
    for tag, rows in outputs.items():
        write(a.output/f'mobile-{tag}.csv',rows)

if __name__ == '__main__':
    main()
