"""Compare ROS1 bag messages with the matching published CSV. Python standard library.
Usage: python bag-verify.py FIGSHARE_V2_ZIP OUTPUT_DIRECTORY
"""
import csv
import hashlib
import io
import struct
import sys
import zipfile
from collections import Counter, defaultdict, deque
from pathlib import Path

BILLION = 10**9
TOPICS = {f'/dwm1001/anchor{i}': f'A{i}.csv' for i in (3, 5, 9, 12)}
TOPICS.update({'/imu/data': 'imu.csv', '/ublox_gps/fix': 'gnss.csv'})


def integer(data, start=0):
    return struct.unpack_from('<I', data, start)[0]


def fields(data):
    pos, result = 0, {}
    while pos < len(data):
        size = integer(data, pos)
        key, value = data[pos + 4:pos + 4 + size].split(b'=', 1)
        result[key.decode()] = value
        pos += size + 4
    return result


def records(data, start=0):
    while start < len(data):
        size = integer(data, start)
        header = fields(data[start + 4:start + 4 + size])
        start += size + 4
        size = integer(data, start)
        yield header, data[start + 4:start + 4 + size]
        start += size + 4


def nano(two_words):
    sec, nsec = struct.unpack('<II', two_words)
    if nsec >= BILLION:
        raise ValueError('Noncanonical ROS nanoseconds')
    return sec * BILLION + nsec


def ros_string(text):
    data = text.encode()
    return struct.pack('<I', len(data)) + data


def csv_payload(row, kind):
    # ROS1 scalar/array storage is unaligned, little-endian. Decimal floats in
    # the export are converted back to binary64 for bit-exact comparisons.
    stamp_key = 'field.stamp' if kind.endswith('/Anchor') else 'field.header.stamp'
    stamp = int(row[stamp_key])
    wire_time = struct.pack('<II', *divmod(stamp, BILLION))
    if kind.endswith('/Anchor'):
        data = wire_time + ros_string(row['field.id'])
        names = ('x', 'y', 'z', 'distanceFromTag', 'rssi', 'rssi_fp')
        return stamp, data + struct.pack('<6d', *(float(row['field.' + k]) for k in names))
    header = struct.pack('<I', int(row['field.header.seq'])) + wire_time + ros_string(row['field.header.frame_id'])
    if kind == 'sensor_msgs/Imu':
        nums = [float(v) for k, v in row.items() if k != '%time' and not k.startswith('field.header.')]
        return stamp, header + struct.pack('<37d', *nums)
    if kind == 'sensor_msgs/NavSatFix':
        status = struct.pack('<bH', int(row['field.status.status']), int(row['field.status.service']))
        names = ['latitude', 'longitude', 'altitude'] + ['position_covariance' + str(i) for i in range(9)]
        payload = struct.pack('<12dB', *(float(row['field.' + k]) for k in names), int(row['field.position_covariance_type']))
        return stamp, header + status + payload
    raise ValueError(f'Unknown message type {kind}')


def bag_streams(bag):
    magic = b'#ROSBAG V2.0\n'
    if not bag.startswith(magic):
        raise ValueError('Unsupported ROS format')
    # Connection definitions in end-of-file records map each connection ID to a topic.
    conns = {}
    for h, d in records(bag, len(magic)):
        if h['op'] == b'\x07' and h['topic'].decode() in TOPICS:
            details = fields(d)
            conns[integer(h['conn'])] = tuple(details[k].decode() for k in ('topic', 'type', 'callerid', 'md5sum'))
    streams = defaultdict(list)
    for h, d in records(bag, len(magic)):
        if h['op'] != b'\x05':
            continue
        if h['compression'] != b'none' or len(d) != integer(h['size']):
            raise ValueError('Unsupported or invalid chunk')
        for m, payload in records(d):
            if m['op'] != b'\x02':
                continue
            cid = integer(m['conn'])
            if cid in conns:
                off = 0 if conns[cid][1].endswith('/Anchor') else 4
                streams[cid].append((nano(m['time']), nano(payload[off:off + 8]), hashlib.sha256(payload).digest()))
    return conns, streams


def compare(archive, name):
    root = Path(name).parent
    bag = archive.read(name)
    bag_sha = hashlib.sha256(bag).hexdigest()
    conns, streams = bag_streams(bag)
    for cid, (topic, kind, caller, md5) in sorted(conns.items()):
        member = str(root / TOPICS[topic])
        b = streams[cid]
        c = []
        with archive.open(member) as source:
            for row in csv.DictReader(io.TextIOWrapper(source)):
                timestamp, payload = csv_payload(row, kind)
                c.append((int(row['%time']), timestamp, hashlib.sha256(payload).digest()))
        # Pair matching payload occurrences in archived order; count reordering and
        # missing rows independently of either timestamp.
        occurrences = defaultdict(deque)
        for ix, (_, _, payload) in enumerate(b):
            occurrences[payload].append(ix)
        mapped = [(i, occurrences[p].popleft()) for i, (_, _, p) in enumerate(c) if occurrences[p]]
        if not mapped:
            raise ValueError(f'No payload matches: {name} {topic}')
        deltas = [b[j][0] - c[i][0] for i, j in mapped]
        order = [j for _, j in mapped]
        yield dict(bag_member=name.split('/', 1)[1], bag_sha256=bag_sha, csv_member=member.split('/', 1)[1],
                   csv_crc32=f'{archive.getinfo(member).CRC:08x}', connection_id=cid, topic=topic, ros_type=kind,
                   ros_type_md5=md5, caller_id=caller, csv_rows=len(c), bag_messages=len(b),
                   same_index_stamp_matches=sum(x[1] == y[1] for x, y in zip(c, b)),
                   same_index_recorder_matches=sum(x[0] == y[0] for x, y in zip(c, b)),
                   same_index_payload_matches=sum(x[2] == y[2] for x, y in zip(c, b)),
                   stamp_multiset_shared=sum((Counter(x[1] for x in c) & Counter(y[1] for y in b)).values()),
                   payloads_matched=len(mapped), csv_only_payload_occurrences=len(c)-len(mapped),
                   bag_only_payload_occurrences=len(b)-len(mapped),
                   matched_bag_indices_nonincreasing=sum(x >= y for x, y in zip(order, order[1:])),
                   paired_stamp_equal=sum(c[i][1] == b[j][1] for i, j in mapped),
                   paired_csv_percent_time_equal_bag_time=deltas.count(0), bag_minus_csv_min_ns=min(deltas),
                   bag_minus_csv_max_ns=max(deltas), bag_first_time_ns=b[0][0], csv_first_percent_time_ns=c[0][0],
                   first_bag_payload_stamp_ns=b[0][1], first_csv_stamp_ns=c[0][1])


def main():
    p, dest = map(Path, sys.argv[1:])
    if hashlib.md5(p.read_bytes()).hexdigest() != '2a3808e0d781704b96f2e436a7623f74':
        raise ValueError('Expected the Figshare v2 archive')
    with zipfile.ZipFile(p) as z:
        entries = [row for name in sorted(z.namelist()) if name.endswith('/combined.bag') for row in compare(z, name)]
    if len(entries) != 48:
        raise ValueError('Expected 8 runs with the 6 selected sensors')
    dest.mkdir(parents=True, exist_ok=True)
    with (dest / 'bag-stream-verification.csv').open('w', newline='') as output:
        writer = csv.DictWriter(output, entries[0], lineterminator='\n')
        writer.writeheader()
        writer.writerows(entries)


if __name__ == '__main__':
    main()
