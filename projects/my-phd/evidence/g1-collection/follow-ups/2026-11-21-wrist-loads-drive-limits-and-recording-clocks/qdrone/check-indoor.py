"""Verify the two indoor release archives and tabulate sensor/ground-truth timing."""
import argparse
import csv
import hashlib
import io
import math
import re
import statistics
import urllib.parse
import urllib.request
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

ROOT = 'https://huggingface.co/datasets/QDrone/UWB_IMU_GT_QDrone_Benchmark_Dataset/resolve/cd3774c9db03899afde886a52f06687bbe4a1ed1/'
FILES = {
    'All Datasets/indoor.zip': '0bd32415be7d81250d95eb9f4acae044c797ffe49ac1decd247c4f5b47538ce9',
    'Dataset with Ground Truth/indoor-gt.zip': '110dddc745f291fe9693fd42f6540d9116691f922421a22d5511c3e7378c2899',
}


def archive(path, cache):
    target = cache / path.split('/')[-1]
    if not target.exists():
        urllib.request.urlretrieve(ROOT + urllib.parse.quote(path), target)
    if hashlib.sha256(target.read_bytes()).hexdigest() != FILES[path]:
        raise ValueError(f'Checksum mismatch: {path}')
    return zipfile.ZipFile(target)


def decode(zf, filename, has_gt):
    result = []
    with zf.open(filename) as source:
        reader = csv.reader(io.TextIOWrapper(source, encoding='ascii', newline=''))
        if has_gt:
            assert next(reader) == list('abcdefghijk')
        for marker in reader:
            assert len(marker)==11 and all(int(x or 0)==0 for x in marker[1:])
            tag = int(marker[0])
            width = {0:4, 2:11, 3:1}[tag]
            row = next(reader)
            assert len(row)==11 and all(float(x or 0)==0 for x in row[width:])
            payload = tuple(map(float,row[:width]))
            assert all(math.isfinite(x) for x in payload)
            xyz = None
            if has_gt:
                g = next(reader)
                assert len(g)==11 and all(x=='' for x in g[3:])
                xyz = tuple(map(float,g[:3]))
                assert all(math.isfinite(x) for x in xyz)
            result.append((tag,payload,xyz))
    return result


def table(path,keys,records):
    with path.open('w',newline='') as f:
        writer=csv.writer(f,lineterminator='\n')
        writer.writerow(keys)
        writer.writerows(records)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('output',type=Path)
    parser.add_argument('cache',type=Path)
    args=parser.parse_args()
    args.cache.mkdir(exist_ok=True,parents=True)
    args.output.mkdir(exist_ok=True,parents=True)
    inventory, event_rows, anchor_rows=[],[],[]
    augmented={}
    for path in reversed(FILES):
        has_gt='Ground Truth' in path
        with archive(path,args.cache) as zf:
            for name in sorted(n for n in zf.namelist() if n.endswith('.csv')):
                trial=re.search(r'_exp(\d+)',name)[1]
                events=decode(zf,name,has_gt)
                kinds=Counter(tag for tag,_,_ in events)
                timed=[(tag,v[0]) for tag,v,_ in events if tag in (0,2)]
                stamp=[t for _,t in timed]
                reversals=[(a,b,round((ta-tb)*1e6)) for (a,ta),(b,tb) in zip(timed,timed[1:]) if tb<ta]
                inventory.append([path,trial,name,zf.getinfo(name).file_size,format(zf.getinfo(name).CRC,'08x'),len(events),kinds[0],kinds[2],kinds[3],int(has_gt),min(stamp),max(stamp),len(reversals),sum(a==b for a,b,_ in reversals),max((dt for _,_,dt in reversals), default=0)])
                if has_gt:
                    augmented[trial]=events
                    continue
                if trial in augmented:
                    enriched=augmented[trial]
                    assert [r[0] for r in enriched]==[r[0] for r in events]
                    differences=[max(abs(i-j) for i,j in zip(a[1],b[1])) for a,b in zip(events,enriched)]
                    xyz=[row[2] for row in enriched]
                    uwb_xyz=[row[2] for row in enriched if row[0]==0]
                    times_ok=sum(a[1][0]==b[1][0] for a,b in zip(events,enriched) if a[0] in (0,2))
                    event_rows.append([trial,len(events),sum(x==0 for x in differences),format(max(differences),'.10g'),times_ok,kinds[0]+kinds[2],len(xyz),len(set(xyz)),sum(a==b for a,b in zip(xyz,xyz[1:])),len(uwb_xyz),len(set(uwb_xyz)),sum(a==b for a,b in zip(uwb_xyz,uwb_xyz[1:]))])
                grouped=defaultdict(list)
                for tag,v,_ in events:
                    if tag==0:
                        assert v[1].is_integer()
                        grouped[int(v[1])].append(v)
                for anchor,vals in sorted(grouped.items()):
                    gaps=[round((b[0]-a[0])*1000000) for a,b in zip(vals,vals[1:])]
                    anchor_rows.append([trial,anchor,len(vals),min(v[2] for v in vals),max(v[2] for v in vals),min(gaps),statistics.median(gaps),sorted(gaps)[math.ceil(.95*len(gaps))-1],max(gaps),sum(d<=0 for d in gaps)])
    table(args.output/'indoor-inventory.csv',['archive','trial','member','uncompressed_bytes','zip_crc32','sensor_events','uwb','imu','height','has_appended_xyz','min_sensor_timestamp_s','max_sensor_timestamp_s','adjacent_backward_timestamp_timed_sensor_rows','adjacent_reversals_same_sensor_type','largest_reversal_us'],inventory)
    table(args.output/'ground-truth-overlap.csv',['trial','sensor_events_compared','identical_sensor_payloads_numeric','max_abs_tag_payload_difference_mixed_units','identical_uwb_or_imu_timestamps','timed_uwb_or_imu_events','finite_xyz_rows','distinct_xyz','adjacent_equal_xyz_all','uwb_with_xyz','distinct_xyz_at_uwb','adjacent_equal_xyz_uwb'],event_rows)
    table(args.output/'uwb-anchor-intervals.csv',['trial','module_id','uwb_records','min_range_m','max_range_m','min_gap_us','median_gap_us','p95_nearest_rank_gap_us','max_gap_us','nonpositive_gaps'],anchor_rows)


if __name__=='__main__':
    main()
