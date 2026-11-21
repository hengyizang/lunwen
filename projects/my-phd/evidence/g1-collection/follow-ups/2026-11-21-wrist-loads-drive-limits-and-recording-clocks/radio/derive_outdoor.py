"""Recompute static radio intervals and dynamic ROS timestamps from Figshare v2.
Usage: python derive_outdoor.py UWB-dataset.zip OUTPUT_DIRECTORY
"""
import argparse
import csv
import hashlib
import io
import math
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path
from statistics import median
from zipfile import ZipFile

ARCHIVE_MD5 = '2a3808e0d781704b96f2e436a7623f74'
TICKS = 1 << 32


def table(out, name, entries):
    with (out/name).open('w', newline='') as f:
        writer = csv.DictWriter(f, entries[0], lineterminator='\n')
        writer.writeheader()
        writer.writerows(entries)


def integer(row, key):
    try:
        value = Decimal(row[key])
    except InvalidOperation as error:
        raise ValueError(key) from error
    if not value.is_finite() or value != value.to_integral_value():
        raise ValueError(key)
    return int(value)


def read_static(z, member):
    path = Path(member)
    reader = csv.reader(io.TextIOWrapper(z.open(member), encoding='utf-8-sig'))
    header = next(reader)
    totals = Counter()
    distances, counters = [], []
    footer = {}
    for cells in reader:
        if len(cells) == 2 and cells[0] in ('Distance Mean', 'Distance Std', 'RSSI(dBm) Mean',
            'RSSI(dBm) Std', 'RSSI_fp(dBm) Mean', 'RSSI_fp(dBm) Std'):
            footer[cells[0]] = cells[1]
            continue
        row = dict(zip(header, cells))
        if len(cells) != len(header):
            totals['other'] += 1
            continue
        totals['width'] += 1
        try:
            init, resp, rx1, tx1, tx2, rx2 = [integer(row,k) for k in
                ('rtd_init','rtd_resp','resp_rx_ts','poll_tx_ts','resp_tx_ts','poll_rx_ts')]
        except (ValueError, OverflowError):
            totals['bad_clock'] += 1
        else:
            totals['init_difference'] += (rx1-tx1) % TICKS != init
            totals['resp_difference'] += (tx2-rx2) % TICKS != resp
            totals['init_wrap'] += (rx1-tx1) < 0
            totals['resp_wrap'] += (tx2-rx2) < 0
        try:
            tx, rx = integer(row,'Transmission #'), integer(row,'Reception #')
        except (ValueError, OverflowError):
            counters.append(None)
        else:
            counters.append((tx,rx))
        try:
            dist = float(row['Distance'])
        except ValueError:
            continue
        if math.isfinite(dist):
            distances.append(dist)
    for a,b in zip(counters,counters[1:]):
        if a and b:
            totals['counter_pairs'] += 1
            dt, dr = b[0]-a[0], b[1]-a[1]
            totals['tx_gap'] += dt > 1
            totals['rx_gap'] += dr > 1
            totals['both_gap'] += dt > 1 and dr > 1
            totals['nonincreasing'] += min(dt,dr) <= 0
    err = ''
    if distances and 'Distance Mean' in footer:
        try:
            value = float(footer['Distance Mean'])
        except ValueError:
            value = math.nan
        if math.isfinite(value):
            err = round(sum(distances)/len(distances) - value, 10)
    return dict(file=str(path.relative_to(path.parts[0])), crc32=f'{z.getinfo(member).CRC:08x}',
        data_width_rows=totals['width'], summary_fields=len(footer), other_rows=totals['other'],
        usable_clock_rows=totals['width']-totals['bad_clock'],
        init_mod32_mismatches=totals['init_difference'],resp_mod32_mismatches=totals['resp_difference'],
        negative_direct_init_differences=totals['init_wrap'],negative_direct_resp_differences=totals['resp_wrap'],
        consecutive_valid_counter_pairs=totals['counter_pairs'],tx_gaps_gt1=totals['tx_gap'],
        rx_gaps_gt1=totals['rx_gap'],both_gaps_gt1=totals['both_gap'],nonincreasing_either=totals['nonincreasing'],
        finite_distance_rows=len(distances),computed_minus_footer_mean_m=err)


def read_dynamic(z, member):
    name = Path(member)
    rows = list(csv.DictReader(io.TextIOWrapper(z.open(member))))
    key = 'field.stamp' if 'field.stamp' in rows[0] else 'field.header.stamp'
    report = [int(r['%time']) for r in rows]
    stamp = [int(r[key]) for r in rows]
    delta = [a-b for a,b in zip(report,stamp)]
    return dict(file=str(name.relative_to(name.parts[0])),crc32=f'{z.getinfo(member).CRC:08x}',
        signal_stamp_column=key,samples=len(stamp),distinct_signal_stamps=len(set(stamp)),
        signal_stamp_nonincreasing=sum(b<=a for a,b in zip(stamp,stamp[1:])),
        negative_stamp_gaps=sum(v<0 for v in delta),first_stamp_ns=stamp[0],
        last_stamp_ns=stamp[-1],min_export_minus_signal_ns=min(delta),
        median_export_minus_signal_ns=median(delta),max_export_minus_signal_ns=max(delta)), set(stamp)


def run(archive,out):
    if hashlib.md5(archive.read_bytes()).hexdigest() != ARCHIVE_MD5:
        raise ValueError('Archive does not match the Figshare v2 checksum')
    out.mkdir(parents=True,exist_ok=True)
    static, streams, cases = [], [], {}
    with ZipFile(archive) as z:
        if z.testzip() is not None:
            raise ValueError('Invalid archive member CRC32')
        for item in sorted(z.namelist()):
            if '/Static_measurements/' in item and item.endswith('.csv'):
                static.append(read_static(z,item))
            if '/Dynamic_measurements/' not in item or Path(item).name not in (
                    'A3.csv','A5.csv','A9.csv','A12.csv','gnss.csv','imu.csv'):
                continue
            report, stamps = read_dynamic(z,item)
            streams.append(report)
            if Path(item).name.startswith('A'):
                cases.setdefault(Path(report['file']).parent,{})[Path(item).stem] = stamps
    table(out,'static-clock-and-counter-check.csv',static)
    table(out,'dynamic-stream-clocks.csv',streams)
    table(out,'dynamic-anchor-stamp-overlap.csv',[
        dict(case=str(case),anchor_streams=len(anchors),unique_stamps_any=len(set.union(*anchors.values())),
             common_stamps_all_four=len(set.intersection(*anchors.values())),
             exactly_one_anchor=sum(n==1 for n in Counter(s for ticks in anchors.values() for s in ticks).values()))
        for case, anchors in sorted(cases.items()) if len(anchors)==4])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive',type=Path)
    parser.add_argument('output',type=Path)
    args=parser.parse_args()
    run(args.archive,args.output)
