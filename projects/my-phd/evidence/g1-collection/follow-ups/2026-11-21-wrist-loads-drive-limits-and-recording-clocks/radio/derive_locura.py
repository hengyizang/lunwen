"""Summarize original LocURa4IoT 20220611-uwb-twr JSON lines per mobile-to-anchor link."""
import argparse
import base64
import csv
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path
from statistics import median


def run(path, out):
    data = path.read_bytes()
    if len(data) != 7115180:
        raise ValueError('Unexpected source file size')
    source = Path(__file__).with_name('locura-source.json')
    if source.is_file() and json.loads(source.read_text())['sha256'] != hashlib.sha256(data).hexdigest():
        raise ValueError('Source digest differs')
    groups = defaultdict(list)
    for line in data.splitlines():
        q = json.loads(line)
        groups[(q['initiator'], q['target'])].append(q)
    result = []
    for (a,b),rows in sorted(groups.items()):
        errs, raw_errs, geom_errors, tof_diffs = [], [], [], []
        negatives = wraps = crc_lengths = decel = 0
        for q in rows:
            geom = q['localisation']
            d = math.dist([geom['initiator'][k] for k in 'xyz'],[geom['target'][k] for k in 'xyz'])
            geom_errors.append(abs(d-q['distance']))
            errs.append(q['rangeSkew']-q['distance'])
            raw_errs.append(q['rangeNoSkew']-q['distance'])
            negatives += q['rangeSkew'] < 0
            t1,t2,t3,t4 = [q[k] for k in ('t1','t2','t3','t4')]
            wraps += (t4<t1 or t3<t2)
            ticks = ((t4-t1) % (1<<40) - (t3-t2) % (1<<40))/2
            tof_diffs.append(ticks-q['tof'])
            signal = base64.b64decode(q['registerDump_CIR']['ACC_MEM'],validate=True)
            crc_lengths += int(len(signal)>0 and len(signal)%4==0)
        n=len(rows)
        rmse=lambda e: round(math.sqrt(sum(x*x for x in e)/n),9)
        result.append(dict(initiator=a,target=b,events=n,unique_seqnums=len({r['seqnum'] for r in rows}),
            distinct_geometry_distances=len({r['distance'] for r in rows}),
            min_geometry_distance_m=min(r['distance'] for r in rows),
            max_geometry_distance_m=max(r['distance'] for r in rows),
            max_xyz_vs_published_distance_m=round(max(geom_errors),9),
            reported_range_vs_corrected_mismatches=sum(q['range']!=q['rangeSkew'] for q in rows),
            corrected_negative_ranges=negatives,raw_rmse_m=rmse(raw_errs),corrected_rmse_m=rmse(errs),
            raw_median_bias_m=round(median(raw_errs),9),corrected_median_bias_m=round(median(errs),9),
            within_exchange_clock_rollovers=wraps,max_abs_unrounded_tof_minus_field_ticks=max(map(abs,tof_diffs)),
            valid_complex_int16_CIR_payloads=crc_lengths))
    with out.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=result[0],lineterminator='\n')
        w.writeheader()
        w.writerows(result)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('source',type=Path)
    p.add_argument('output',type=Path)
    args=p.parse_args()
    run(args.source,args.output)
