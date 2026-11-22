"""Audit the public ROA, HYMN and Aalto releases. Python 3.11+ standard library.

Input directory contains ptp.zip (16794348), hymn.zip (19566178) and the three
originally named Aalto SQLite files (4706065). Output contains aggregates only.
"""
import argparse
import ast
import csv
import hashlib
import io
import json
import math
import sqlite3
import statistics
import zipfile
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path


def table(path, rows):
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def digest(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def nearest_rank(xs, p):
    return sorted(xs)[math.ceil(len(xs)*p)-1] if xs else ""


def med(xs):
    return statistics.median(xs) if xs else ""


def readcsv(z, name):
    with z.open(name) as raw, io.TextIOWrapper(raw, encoding="utf-8-sig") as text:
        yield from csv.DictReader(text)


def audit_ptp(path, out):
    replay, inventory = [], []
    with zipfile.ZipFile(path) as z:
        assert z.testzip() is None
        for info in z.infolist():
            name = info.filename
            if info.is_dir() or not name.startswith("dataset/testbed/"):
                continue
            n = 0
            if '/clock/' in name:
                with z.open(info) as f:
                    n = sum(math.isfinite(float(line)) for line in f)
            elif name.endswith('.csv'):
                data = defaultdict(list)
                counts = Counter()
                back = 0
                last_t = None
                for r in readcsv(z, name):
                    t, var, val = int(r['timestamp']), r['variable'], int(r['value'])
                    n += 1
                    data[var].append((t, val))
                    counts[var] += 1
                    if last_t is not None and t < last_t:
                        back += 1
                    last_t = t
                # Same logger timestamp pairs t1/t2 or t3/t4 within one packet
                # event. Delays across directions do not have a shared packet ID.
                a, b, c, d = (data[k] for k in ('t1','t2','t3','t4'))
                def unique_pair(start,end):
                    left=defaultdict(list); right=defaultdict(list)
                    for t,val in start: left[t].append(val)
                    for t,val in end: right[t].append(val)
                    return [right[t][0]-left[t][0] for t in left.keys() & right.keys() if len(left[t])==len(right[t])==1]
                fwd,rev=unique_pair(a,b),unique_pair(c,d)
                all_stamps = [v for stream in (a,b,c,d) for _,v in stream]
                ofs = [v for _,v in data['offset']]
                replay.append(dict(file=name,partition='training' if '/train/' in name else 'testbed',
                      t1_rows=len(a),t2_rows=len(b),t3_rows=len(c),t4_rows=len(d),
                      paired_fwd_logger_times=len(fwd),paired_rev_logger_times=len(rev),external_offset_rows=len(ofs),
                      timestamp_fields=len(all_stamps),on_256ns_grid=sum(v%256==0 for v in all_stamps),
                      stamp_gcd_ns=math.gcd(*all_stamps),
                      fwd_median_ns=med(fwd),rev_median_ns=med(rev),
                      half_median_direction_difference_ns=(med(fwd)-med(rev))/2,
                      reference_offset_abs_p95_ns=nearest_rank(list(map(abs,ofs)),.95),
                      logger_backsteps=back))
            inventory.append(dict(file=name,uncompressed_bytes=info.file_size,archive_crc32=f'{info.CRC:08x}',numeric_rows=n))
    table(out/'roa-testbed.csv',replay)
    table(out/'roa-members.csv',inventory)


def audit_hymn(path, out):
    inventory, audits = [], []
    with zipfile.ZipFile(path) as z:
        assert z.testzip() is None
        root = z.infolist()[0].filename.split('/')[0]+'/'
        def read(name):
            return readcsv(z,root+name)
        points = {}
        for r in read('data/reference/csv/time_reference.csv'):
            def millis(k):
                return int(datetime.fromisoformat(r[k]).replace(tzinfo=timezone.utc).timestamp()*1000)
            points[r['point']] = (millis('start_time_UTC'),millis('end_time_UTC'))
        systems = ['ble','wifi','uwb','gnss','nr5g']
        paths, indexed, exported = {}, {}, {}
        for system in systems:
            source = 'data/processed/csv/'+system+'.csv'
            rows = [(r['point_id'],Decimal(r['ts']) if r['ts'] else None) for r in read(source)]
            by_point = defaultdict(list)
            for point, ts in rows:
                if ts is not None:
                    by_point[point].append(ts)
            for times in by_point.values():
                times.sort()
            paths[system],indexed[system],exported[system] = by_point,rows,set()
            valid=[(pt,ts) for pt,ts in rows if ts is not None]
            inventory.append(dict(system=system,rows=len(rows),missing_timestamp_rows=len(rows)-len(valid),point_ids=len(by_point),
                         reference_window_missing=sum(pt not in points for pt,_ in valid),
                         outside_inclusive_reference_window=sum(not points[pt][0]<=ts<=points[pt][1] for pt,ts in valid if pt in points),
                         duplicate_point_timestamp_rows=len(valid)-len(set(valid))))
        unions = Counter()
        for r in read('data/processed/csv/merged.csv'):
            pt, ts = r['point_id'], Decimal(r['ts'])
            present=[]
            for system in systems:
                token=r['idx_'+system]
                if not token:
                    continue
                ids=ast.literal_eval(token) if token.startswith('[') else [int(Decimal(token))]
                for ix in ids:
                    assert ix not in exported[system] and (pt,ts)==indexed[system][ix]
                    exported[system].add(ix)
                present.append(system)
            unions['+'.join(present)]+=1
        assert all(exported[s]=={i for i,(_,ts) in enumerate(indexed[s]) if ts is not None} for s in systems)
        table(out/'hymn-merged-coverage.csv',[dict(systems_at_exact_point_time=k,rows=v) for k,v in sorted(unions.items())])
        for system in ['ble','wifi','gnss','nr5g']:
            all_near, past = [], []
            future=tied=unsupported=0
            for point,t in indexed['uwb']:
                others=paths[system].get(point,[])
                if not others:
                    unsupported+=1
                    continue
                i=bisect_left(others,t)
                candidates=others[max(i-1,0):i+1]
                delta=min((v-t for v in candidates),key=lambda d:(abs(d),d))
                tied += len(candidates)==2 and candidates[0]!=candidates[1] and t-candidates[0]==candidates[1]-t
                if abs(delta)<=500:
                    all_near.append(abs(delta))
                    future+=delta>0
                j=bisect_right(others,t)-1
                if j>=0 and t-others[j]<=500:
                    past.append(t-others[j])
            audits.append(dict(stream=system,query_uwb_rows=len(indexed['uwb']),query_rows_without_stream_at_point=unsupported,
                    accepted_nearest_500ms=len(all_near),accepted_nearest_strictly_future=future,all_equidistant_ties=tied,
                    accepted_nearest_abs_p50_ms=med(all_near),accepted_nearest_abs_p95_ms=nearest_rank(all_near,.95),
                    accepted_causal_500ms=len(past),accepted_causal_age_p50_ms=med(past),accepted_causal_age_p95_ms=nearest_rank(past,.95)))
    table(out/'hymn-files.csv',inventory)
    table(out/'hymn-asof.csv',audits)


def audit_agv(inp,out):
    runs=[]
    for path in sorted(inp.glob('*.db')):
        with sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True) as db:
            assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            rows=list(db.execute('select Time,Latency,Throughput from record order by rowid'))
        t=[datetime.fromisoformat(r[0]) for r in rows]
        rtt=[r[1] for r in rows]
        rate=[r[2] for r in rows]
        dt=[(b-a).total_seconds() for a,b in zip(t,t[1:])]
        assert all(math.isfinite(x) for x in rtt+rate)
        runs.append(dict(file=path.name,sha256=digest(path),rows=len(rows),
              distinct_times=len(set(t)),first=str(t[0]),last=str(t[-1]),interval_min_s=min(dt),interval_median_s=med(dt),
              interval_max_s=max(dt),rtt_ms_min=min(rtt),rtt_ms_median=med(rtt),rtt_ms_p95=nearest_rank(rtt,.95),rtt_ms_max=max(rtt),
              throughput_median_kB_s=med(rate),throughput_min_kB_s=min(rate),throughput_max_kB_s=max(rate)))
    assert len(runs)==3
    table(out/'aalto-vpn.csv',runs)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('inputs',type=Path)
    p.add_argument('output',type=Path)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    audit_ptp(a.inputs/'ptp.zip',a.output)
    audit_hymn(a.inputs/'hymn.zip',a.output)
    audit_agv(a.inputs,a.output)
