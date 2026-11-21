"""Inspect SmartMesh-labelled measurements, ROS 2 payload timestamps and MCAP log times.
Python 3.11+, NumPy, pandas and mcap. Input is the two fixed Zenodo experiment ZIPs.
"""
import argparse
from collections import Counter
import hashlib
import itertools
from pathlib import Path
import re
import struct
import wave
import zipfile

from mcap.records import Channel, Message, Footer
from mcap.exceptions import EndOfFile
from mcap.stream_reader import StreamReader
import numpy as np
import pandas as pd

ARCHIVES = {
    '2026_03_04_datasets.zip': '3697b7df7415fc7de9843ebfcb5c89281c71a464e9842783914c32249087bda4',
    '2026_04_20_datasets.zip': '440f8d7173d0841c234e3c4ff93d024dcb30b16e4abab61196f6dac9f96d6a6e'
}


class CDR:
    """Little-endian CDR1 payload cursor; alignment is relative to the encapsulated payload."""
    def __init__(self, data):
        if data[:2] != b'\x00\x01':
            raise ValueError('Unexpected CDR encoding')
        self.buf = memoryview(data)[4:]
        self.pos = 0

    def align(self, size):
        self.pos += -self.pos % size

    def unpack(self, fmt):
        width = struct.calcsize('<'+fmt)
        self.align(width)
        v, = struct.unpack_from('<'+fmt, self.buf, self.pos)
        self.pos += width
        return v

    def string(self):
        n = self.unpack('I')
        out = self.buf[self.pos:self.pos+n].tobytes()
        if len(out) != n or out[-1:] != b'\0':
            raise ValueError('Invalid CDR string')
        self.pos += n
        return out[:-1].decode()

    def header(self):
        seconds = self.unpack('i')
        ns = self.unpack('I')
        self.string()
        return seconds * 1_000_000_000 + ns

    def array(self):
        for _ in range(self.unpack('I')):
            self.string()
            self.unpack('I')
            self.unpack('I')
        self.unpack('I')  # layout.data_offset
        n = self.unpack('I')
        if n:
            self.align(8)
            self.pos += 8 * n
        if self.pos > len(self.buf):
            raise ValueError('Truncated Float64 sequence')
        return n


def optional_int(s):
    return int(s) if s.isdigit() else None


def median_ms(values):
    return round(float(np.median(values))/1e6, 6) if len(values) else None


def read_bag(z, member):
    if z.getinfo(member).file_size == 0:
        return [], [], 'empty_member'
    channels = {}
    gps, rms = [], []
    ending = 'no_footer'
    with z.open(member) as f:
        try:
            out = StreamReader(f, validate_crcs=True).records
            while True:
                try:
                    rec = next(out)
                except StopIteration:
                    break
                except (EndOfFile, struct.error) as exc:
                    ending = 'partial_' + type(exc).__name__
                    break
                if isinstance(rec, Footer):
                    ending = 'footer'
                if isinstance(rec, Channel):
                    channels[rec.id] = rec.topic
                if not isinstance(rec, Message):
                    continue
                cur = CDR(rec.data)
                topic = channels[rec.channel_id]
                base = {'logged':rec.log_time, 'published':rec.publish_time}
                if topic == '/mavros/gpsstatus/gps1/raw':
                    gps.append(dict(**base, header=cur.header(), fix=cur.unpack('B')))
                elif topic == '/rms_stream/data':
                    stamp = int(cur.string())
                    nav = cur.header()
                    status = cur.unpack('b')
                    cur.unpack('H')
                    cur.align(8)
                    cur.pos += 12*8  # 3 position fields and 9 covariances
                    cur.unpack('B')
                    cur.array()
                    node, utc = cur.string(), cur.string()
                    n = cur.array()
                    # A CDR payload can be padded to a 4-byte boundary.
                    if not 0 <= len(cur.buf)-cur.pos <= 3:
                        raise ValueError('Unexpected trailing CDR contents')
                    rms.append(dict(**base, stamp=stamp, nav=nav, status=status, node=node,
                                    tick=optional_int(utc), audio_values=n))
                else:
                    raise ValueError(f'Unexpected topic {topic}')
        except EndOfFile:
            # A recorder may terminate during a chunk; only fully parsed records are counted.
            ending = 'partial_EndOfFile'
    return rms, gps, ending


def read_csv(z, member):
    rows, padding = [], 0
    with z.open(member) as stream:
        header = stream.readline().rstrip().split(b',')
        if header[:7] != [b'node_id', b'timestamp', b'utc_time', b'nav_status', b'nav_service', b'lat', b'lon']:
            raise ValueError('Unexpected CSV header')
        for line in stream:
            if b',' not in line and not line.strip(b'\0\n\r'):
                padding += len(line)
                continue
            if line.count(b',') + 1 != len(header):
                raise ValueError('Malformed row')
            node, stamp, tick, status, _, lat, lon, _ = line.split(b',',7)
            rows.append(dict(node=node.decode(), stamp=int(stamp), tick=optional_int(tick),
                             status=int(status), zero_location=(float(lat)==0 and float(lon)==0)))
    return rows, len(header)-7, padding


def station(z, trial, ident, members):
    all_rows, gps, rms, files = [], [], [], []
    bag_count, bag_bytes, endings = 0, 0, []
    for member in members:
        if member.endswith('.csv'):
            rows, width, padding = read_csv(z, member)
            all_rows.extend(rows)
            with z.open(member.removesuffix('.csv')+'.wav') as f, wave.open(f) as wav:
                files.append(dict(trial=trial, vehicle=ident, csv=member, csv_rows=len(rows),
                                  audio_columns=width, null_padding_bytes=padding,
                                  tick_present=sum(r['tick'] is not None for r in rows),
                                  embedded_node_values='|'.join(sorted({r['node'] for r in rows})),
                                  wav_channels=wav.getnchannels(), wav_rate_hz=wav.getframerate(),
                                  wav_header_frames=wav.getnframes()))
        elif member.endswith('.mcap'):
            stream, fixes, ending = read_bag(z, member)
            bag_count += 1
            bag_bytes += z.getinfo(member).file_size
            endings.append(ending)
            rms.extend(stream)
            gps.extend(fixes)
    def key(r):
        return (r['stamp'], r['node'], r['tick'], r['status'])
    csv_keys, mcap_keys = Counter(map(key,all_rows)), Counter(map(key,rms))
    tick_count = Counter(r['tick'] for r in all_rows if r['tick'] is not None)
    unique = {r['tick']:r for r in all_rows if r['tick'] is not None and tick_count[r['tick']] == 1}
    stats = dict(trial=trial, vehicle=ident, mcap_files=bag_count, mcap_bytes=bag_bytes, mcap_complete_footer=endings.count('footer'), mcap_ending='|'.join(endings), csv_rows=len(all_rows), mcap_rms_messages=len(rms),
                 gps_messages=len(gps), exact_payload_matches=sum((csv_keys & mcap_keys).values()),
                 csv_without_sync_tick=sum(r['tick'] is None for r in all_rows),
                 mcap_rms_without_sync_tick=sum(r['tick'] is None for r in rms),
                 gps_fix_type_6=sum(r['fix']==6 for r in gps),
                 csv_zero_coordinates=sum(r['zero_location'] for r in all_rows),
                 unique_sync_ticks=len(unique),
                 csv_records_with_repeated_tick=sum(n for n in tick_count.values() if n>1),
                 mcap_rms_unique_nav_headers=len({r['nav'] for r in rms}),
                 median_mcap_log_minus_payload_ms=median_ms([r['logged']-r['stamp'] for r in rms]),
                 median_mcap_publish_minus_payload_ms=median_ms([r['published']-r['stamp'] for r in rms]),
                 median_mcap_log_minus_publish_ms=median_ms([r['logged']-r['published'] for r in rms]))
    return stats,files,unique


def main(root,out):
    out.mkdir(parents=True,exist_ok=True)
    stations,files,pairs=[],[],[]
    for filename,sha in ARCHIVES.items():
        path=root/filename
        with path.open('rb') as fp:
            if hashlib.file_digest(fp,'sha256').hexdigest()!=sha:
                raise ValueError('Expected pinned experiment ZIP '+filename)
        trial=filename[:10]
        by={}
        with zipfile.ZipFile(path) as z:
            for ident in ('usv1','usv2','usv3','usv4'):
                members=[n for n in z.namelist() if re.search(r'/'+ident+r'[/_]',n)]
                stats,sources,by[ident]=station(z,trial,ident,members)
                stations.append(stats)
                files.extend(sources)
        for a,b in itertools.combinations(sorted(by),2):
            common=sorted(by[a].keys() & by[b].keys())
            dt=np.array([by[b][u]['stamp']-by[a][u]['stamp'] for u in common],dtype=np.int64)
            pairs.append(dict(trial=trial, vehicle_a=a, vehicle_b=b, exactly_shared_unique_sync_ticks=len(common),
                              same_embedded_node_id=sum(by[a][u]['node']==by[b][u]['node'] for u in common),
                              equal_local_timestamps=int(np.count_nonzero(dt==0)),
                              median_local_b_minus_a_ms=median_ms(dt),
                              p95_abs_local_difference_ms=round(float(np.quantile(abs(dt),.95))/1e6,6) if len(dt) else None))
    for filename,rows in [('openswarm-stations.csv',stations),('openswarm-recordings.csv',files),
                          ('openswarm-cross-station.csv',pairs)]:
        pd.DataFrame(rows).to_csv(out/filename,index=False)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('data',type=Path)
    parser.add_argument('out',type=Path)
    args=parser.parse_args()
    main(args.data,args.out)
