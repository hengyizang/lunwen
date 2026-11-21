"""Verify 802.11ad archive; run python check_porto.py v2i-80211ad-dataset.zip OUTPUT."""
from array import array
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import io
from itertools import islice
from pathlib import Path
from statistics import median
import struct
from zipfile import ZipFile


def save(out, filename, rows):
    with (out / filename).open('w', newline='') as f:
        w = csv.DictWriter(f, rows[0], lineterminator='\n')
        w.writeheader()
        w.writerows(rows)


def read_capture(z, path):
    """Retain numeric headers (no packet contents). Each frame number is 1-based."""
    data = z.read(path)
    if data[:4] != bytes.fromhex('d4c3b2a1') or struct.unpack_from('<I', data, 20)[0] != 127:
        raise ValueError(f'Unexpected pcap clock or link type: {path}')
    times, sizes = array('q'), array('I')
    at = 24
    while at + 16 <= len(data):
        sec, usec, stored, wire = struct.unpack_from('<IIII', data, at)
        if at + 16 + stored > len(data):
            break
        times.append(sec * 1000000 + usec)
        sizes.append(wire)
        at += 16 + stored
    return times, sizes, len(data)-at


def check_frames(z, root, year):
    caps = {int(p.split('/trace-')[1].split('/')[0]):p for p in z.namelist()
            if p.startswith(root) and '/pcap/trace-' in p and p.endswith('.pcap')}
    stats, finished = {}, set()
    key = None
    with io.TextIOWrapper(z.open(root+'wifi.csv'),newline='',encoding='utf-8') as f:
        reader=csv.reader(f)
        columns=next(reader)
        assert columns[:3] == ['frame.time_epoch','frame.number','frame.len'] and columns[-1] == 'trace_nr'
        for cells in islice(reader, 1000):
            if len(cells)!=len(columns):raise ValueError('malformed CSV record')
            r = int(cells[-1])
            if r != key:
                if key is not None:finished.add(key)
                assert r not in finished, 'trace recurs non-contiguously'
                key = r
                times, sizes, tail = read_capture(z, caps[r])
                d = stats[r] = dict(year=year,trace=r,pcap_frames=len(times),incomplete_tail_bytes=tail,sampled_export_rows=0,
                    nonincreasing_frame_number=0,timestamp_mismatches=0,timestamp_more_than_half_us=0,max_abs_export_minus_pcap_ns=0,wire_size_mismatches=0,
                    first_pcap_us=times[0],last_pcap_us=times[-1],last_sampled_csv_frame=0)
            s,idx,size_code=cells[:3]
            s1,s2 = s.split('.')
            assert len(s2)<=9 or not s2[9:].strip('0')
            stamp=int(s1)*1000000000+int((s2+'000000000')[:9])
            n=int(idx)
            assert 1<=n<=len(times)
            d['nonincreasing_frame_number']+=n<=d['last_sampled_csv_frame']
            d['last_sampled_csv_frame']=n
            d['sampled_export_rows']+=1
            residual=abs(stamp-1000*times[n-1])
            d['timestamp_mismatches']+=residual!=0
            d['timestamp_more_than_half_us']+=residual>500
            d['max_abs_export_minus_pcap_ns']=max(d['max_abs_export_minus_pcap_ns'],residual)
            d['wire_size_mismatches']+=int(size_code)!=sizes[n-1]
    for r,path in caps.items():
        if r not in stats:
            times,sizes,tail=read_capture(z,path)
            stats[r]=dict(year=year,trace=r,pcap_frames=len(times),incomplete_tail_bytes=tail,sampled_export_rows=0,
                nonincreasing_frame_number=0,timestamp_mismatches=0,timestamp_more_than_half_us=0,max_abs_export_minus_pcap_ns=0,wire_size_mismatches=0,
                first_pcap_us=times[0],last_pcap_us=times[-1],last_sampled_csv_frame=0)
    return [stats[r] for r in sorted(stats)]


def run(archive,out):
    out.mkdir(parents=True, exist_ok=True)
    with archive.open('rb') as f:
        assert hashlib.file_digest(f,'md5').hexdigest()=='a37836cce4f3d37f8ef374850069fc9e'
    gps, delivery, frames = [], [], []
    with ZipFile(archive) as z:
        for year,name in [(2020,'trghpt'),(2021,'thrghpt')]:
            root=f'v2i-80211ad-dataset/{year}/'
            records=defaultdict(list)
            for row in csv.DictReader(io.TextIOWrapper(z.open(root+'gps.csv'))):
                records[row['identifier']].append(row)
            for tag,rows in sorted(records.items()):
                dif=[int(x['timestamp'])-int(x['gpstime']) for x in rows]
                gps.append(dict(year=year,NMEA_type=tag,rows=len(rows),
                    valid_latlon=sum(float(x['lat'])!=-1 and float(x['lon'])!=-1 for x in rows),
                    distinct_recorder_seconds=len({x['timestamp'] for x in rows}),
                    distinct_device_seconds=len({x['gpstime'] for x in rows}),
                    recorder_minus_gpstime_s_min=min(dif),median_s=median(dif),max_s=max(dif),
                    zero_s=dif.count(0),exactly_3601_s=dif.count(3601)))
            rmc=records['GPRMC']
            host={int(x['timestamp']) for x in rmc if float(x['lat'])!=-1 and float(x['lon'])!=-1}
            device={int(x['gpstime']) for x in rmc if float(x['lat'])!=-1 and float(x['lon'])!=-1}
            bins=defaultdict(list)
            for row in csv.DictReader(io.TextIOWrapper(z.open(root+name+'.csv'))):
                bins[int(row['trace_nr'])].append(row)
            for trace,rows in sorted(bins.items()):
                positive=[r for r in rows if float(r['pckt_cntr'])>0]
                diff=[float(r['diff_local_avg']) for r in positive]
                ts=[int(r['timestamp']) for r in rows]
                delivery.append(dict(year=year,trace=trace,bins=len(rows),distinct_seconds=len(set(ts)),
                    first_second=min(ts),last_second=max(ts),positive_packet_bins=len(positive),
                    received_packets=sum(int(float(r['pckt_cntr'])) for r in positive),
                    zero_packets_nonzero_local_difference=sum(float(r['pckt_cntr'])==0 and float(r['diff_local_avg'])!=0 for r in rows),
                    negative_local_difference_positive_bins=sum(x<0 for x in diff),
                    min_positive_bin_diff_us=min(diff) if diff else '',median_positive_bin_diff_us=median(diff) if diff else '',
                    max_positive_bin_diff_us=max(diff) if diff else '',exact_second_match_GPRMC_logger=sum(x in host for x in ts),
                    exact_second_match_GPRMC_device=sum(x in device for x in ts)))
            frames.extend(check_frames(z,root,year))
    save(out,'porto-gps-clocks.csv',gps)
    save(out,'porto-receiver-bins.csv',delivery)
    save(out,'porto-pcap-replay.csv',frames)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('archive',type=Path);p.add_argument('output',type=Path)
    args=p.parse_args();run(args.archive,args.output)
