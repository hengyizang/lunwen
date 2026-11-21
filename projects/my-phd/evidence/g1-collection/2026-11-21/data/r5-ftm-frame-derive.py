"""Rebuild the frame-level RoboLoc-G derivative with Python's standard library."""
import argparse
import csv
import gzip
import hashlib
import io
import zlib
from pathlib import Path

# trajectory: (data row count, uncompressed size, ZIP CRC32, uncompressed SHA256)
MEMBERS = {
    'circle': (1106, 151040, '25e236b2', '5f2f47bec91e0fc5e70aac7c450db2c448bcc12acdf9dca517bb6fc5766fb5b1'),
    'random1': (2167, 298488, '4d4b7ba3', 'de2b37d4c8eeddea46d8a86120668f27b5fde632462843aca8e83feb162f32f5'),
    'random2': (2510, 346278, '4ba6b150', '1e2bfed14fd9617c1374f31396e488d60a826eb0688265e26b6630a1e6d579d2'),
    'still': (2704, 374930, 'ce4e561c', 'be4474c8ec09a81f25f448dd4eeb75d3f483e6484808b59cb7ec67f37211b9ef'),
    'zigzag1': (1195, 165672, '5b600234', '76dbc9575310e827b38f72bf645e7c4d6a50441d3c9a1bfad55fd72217e9329a'),
    'zigzag2': (2223, 311029, '15b2c77c', 'c617ab88193f1d07d939287e6c7fdadc6ca2b3fb8c9acd98a13825cb197e88c5'),
    'zigzag3': (864, 121180, 'cdfe8376', 'dcc1ff1617c535df5cf51a0afc7cc49ddf923d8e599ef7f9e36acec410be1dc2'),
    'zigzag4': (2383, 326430, 'dfa8f395', 'a5505c4c452e9d7a02e997767405fc8d801dee7a2162a1be87418400b3d389c5'),
}
FIELDS = (
    'trajectory','source_row','anchor_local_id','session_local_id',
    't4_minus_t1_ps','t3_minus_t2_ps','double_difference_ps','reported_frame_rtt_raw',
    'reported_minus_derived_numeric','comparison_status',
)

def number(value):
    return int(value) if value.strip() else None

def derive(source, destination):
    csv_text = io.StringIO(newline='')
    writer = csv.writer(csv_text, lineterminator='\n')
    writer.writerow(FIELDS)
    for trajectory, (count, size, crc, sha) in MEMBERS.items():
        path = source / (trajectory + '.csv')
        if not path.is_file():
            path = source / 'SENSORS_MEASUREMENTS_CSV' / 'UWB_FTM_IMU' / trajectory / 'gtec-ftm.csv'
        raw = path.read_bytes()
        if (len(raw),f'{zlib.crc32(raw):08x}',hashlib.sha256(raw).hexdigest()) != (size,crc,sha):
            raise ValueError(f'Source member verification failed for {trajectory}')
        anchors, sessions = {}, {}
        n = 0
        for n, row in enumerate(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'),newline='')),1):
            anchor = row['anchor_id']
            stamp = row['timestamp']
            anchor_id = anchors.setdefault(anchor,len(anchors)+1) if anchor else None
            session_id = sessions.setdefault((stamp,anchor),len(sessions)+1) if stamp and anchor else None
            t1,t2,t3,t4 = (number(row['frames.t'+str(i)]) for i in range(1,5))
            reported = number(row['frames.rtt'])
            first_interval = None if None in (t1,t4) else t4-t1
            second_interval = None if None in (t2,t3) else t3-t2
            difference = None if None in (first_interval,second_interval) else first_interval-second_interval
            residual = None if None in (reported,difference) else reported-difference
            if difference is None or reported is None:
                status = 'missing_both' if difference is None and reported is None else ('missing_timestamp' if difference is None else 'missing_reported_rtt')
            elif residual == 0:
                status = 'equal'
            else:
                status = 'reported_zero_negative_difference' if reported==0 and difference<0 else 'different'
            writer.writerow((trajectory,n,anchor_id,session_id,first_interval,second_interval,difference,reported,residual,status))
        if n!=count:
            raise ValueError(f'Row count mismatch in {trajectory}: {n}')
    payload = csv_text.getvalue().encode('utf-8')
    with destination.open('wb') as target:
        with gzip.GzipFile(filename='',mode='wb',fileobj=target,mtime=0,compresslevel=9) as archive:
            archive.write(payload)
    print(f'CSV SHA-256 {hashlib.sha256(payload).hexdigest()}')
    print(f'gzip SHA-256 {hashlib.sha256(destination.read_bytes()).hexdigest()}')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path,help='Flat directory with <trajectory>.csv files or root of extracted sensor ZIP')
    parser.add_argument('destination',type=Path,help='Output .csv.gz file')
    args=parser.parse_args()
    derive(args.source,args.destination)
