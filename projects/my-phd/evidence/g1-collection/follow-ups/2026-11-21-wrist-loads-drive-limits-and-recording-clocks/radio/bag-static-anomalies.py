"""Extract static interval inconsistencies from the original decimal tokens.
Usage: python bag-static-anomalies.py FIGSHARE_V2_ZIP OUTPUT_DIRECTORY
"""
import csv
from collections import Counter
from decimal import Decimal, InvalidOperation
import hashlib
import io
from pathlib import Path
import sys
from zipfile import ZipFile

CLOCKS = ['rtd_init', 'rtd_resp', 'resp_rx_ts', 'poll_tx_ts', 'resp_tx_ts', 'poll_rx_ts']
MODULUS = 1 << 32


def exact(token):
    number = Decimal(token)
    if not number.is_finite() or number != number.to_integral_value():
        raise ValueError('Not a finite integer')
    return int(number)


def scan(archive):
    result, counts = [], Counter()
    for name in sorted(archive.namelist()):
        if '/Static_measurements/' not in name or not name.endswith('.csv'):
            continue
        counts['csv_files'] += 1
        with archive.open(name) as raw:
            reader = csv.reader(io.TextIOWrapper(raw, encoding='utf-8-sig'))
            header = next(reader)
            rows = [dict(zip(header, cells)) if len(cells) == len(header) else {} for cells in reader]
        for i, r in enumerate(rows):
            try:
                interval1, interval2, rx1, tx1, tx2, rx2 = (exact(r[k]) for k in CLOCKS)
            except (KeyError, ValueError, InvalidOperation):
                continue
            counts['integer_clock_rows'] += 1
            residuals = [(rx1-tx1) % MODULUS - interval1, (tx2-rx2) % MODULUS - interval2]
            try:
                following = rows[i+1]
                step = [exact(following[k])-exact(r[k]) for k in ('Transmission #', 'Reception #')]
            except (IndexError, KeyError, ValueError, InvalidOperation):
                step = ['', '']
            counts['validclock_rows_with_next_both_counters_jump'] += bool(step[0] != '' and min(step) > 1)
            counts['validclock_rows_with_next_both_step_15'] += step == [15, 15]
            if residuals == [0, 0]:
                continue
            counts['any_mismatch'] += 1
            counts['init_mismatch'] += residuals[0] != 0
            counts['resp_mismatch'] += residuals[1] != 0
            counts['both_mismatch'] += all(residuals)
            counts['mismatch_before_next_both_counters_jump'] += bool(step[0] != '' and min(step) > 1)
            counts['mismatch_with_timestamp_outside_u32_and_i32'] += any(
                v < -(1 << 31) or v >= 1 << 32 for v in (rx1, tx1, tx2, rx2))
            result.append({'member': name.split('/', 1)[1], 'csv_line_1_based': i+2,
                           'transmission': r['Transmission #'], 'reception': r['Reception #'],
                           **{k: r[k] for k in CLOCKS}, 'init_residual_ticks': residuals[0],
                           'resp_residual_ticks': residuals[1], 'next_transmission_step':step[0],
                           'next_reception_step':step[1]})
    return result, counts


if __name__ == '__main__':
    archive, dest = map(Path, sys.argv[1:])
    if hashlib.md5(archive.read_bytes()).hexdigest() != '2a3808e0d781704b96f2e436a7623f74':
        raise ValueError('Expected Figshare v2')
    with ZipFile(archive) as z:
        rows, counts = scan(z)
    dest.mkdir(parents=True, exist_ok=True)
    with (dest/'bag-static-interval-anomalies.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, rows[0], lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)
    print(dict(sorted(counts.items())))
