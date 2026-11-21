"""Reconcile UNICO v1 original traffic captures with published inter-packet summaries.

Arrange the ten *_capture.csv and ten *_analysis.csv files by their original names
in INPUT (gzip optional). Run python derive_unico.py INPUT OUT. Requires NumPy and pandas.
"""
import argparse
import csv
from pathlib import Path

import numpy as np
import pandas as pd


def table(root, stem, columns, **kwargs):
    p = root / (stem + '.csv')
    if not p.is_file():
        p = root / (stem + '.csv.gz')
    return pd.read_csv(p, usecols=columns, **kwargs)


def save(path, rows):
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0], lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def summarize(root, stream):
    cap = table(root, stream + '_capture', ['No.', 'Time', 'Protocol', 'Length'])
    supplied = table(root, stream + '_analysis', ['Inter-packet Time', 'Length'])
    stamp_us = np.rint(cap['Time'].to_numpy() * 1e6).astype('int64')
    intervals = np.diff(stamp_us)
    seq = cap['No.'].to_numpy()
    assert np.isfinite(cap['Time']).all() and np.isfinite(supplied['Inter-packet Time']).all()
    assert np.all(np.diff(seq) > 0)
    aligned = len(supplied) == len(intervals)
    return dict(stream=stream, captured=len(cap), local_capture_number_first=seq[0],
                local_capture_number_last=seq[-1], number_jumps_gt_one=int((np.diff(seq) > 1).sum()),
                protocol_counts='|'.join(f'{k}={v}' for k, v in sorted(cap['Protocol'].value_counts().items())),
                bytes_min=cap['Length'].min(), bytes_max=cap['Length'].max(),
                first_capture_us=stamp_us[0], last_capture_us=stamp_us[-1], intervals=len(intervals),
                min_interval_us=intervals.min(), median_interval_us=round(float(np.median(intervals)), 2),
                p99_interval_us=round(float(np.quantile(intervals, .99)), 2), max_interval_us=intervals.max(),
                interval_gt_15ms=int((intervals > 15000).sum()), same_microsecond=int((intervals == 0).sum()),
                negative_intervals=int((intervals < 0).sum()),
                published_intervals=len(supplied), published_max_interval_ms=round(supplied['Inter-packet Time'].max(), 6),
                aligned_intervals_within_half_us=(
                    int((abs(intervals - supplied['Inter-packet Time'].to_numpy() * 1000) <= .51).sum())
                    if aligned else ''
                ),
                aligned_packet_lengths_equal=(
                    int((cap['Length'].to_numpy()[1:] == supplied['Length'].to_numpy()).sum())
                    if aligned else ''
                ))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    args.output.mkdir(exist_ok=True, parents=True)
    streams = ['easybot1', 'easybot2152', 'D435camera', 'laserHokuyo']
    streams.extend(f'Scenario{i}_{role}' for i in [1, 2, 3] for role in ['generator', 'collector'])
    rows = [summarize(args.input, stream) for stream in streams]
    save(args.output / 'unico-capture-intervals.csv', rows)
    pairs = []
    for gen, rx, (low, high) in zip(rows[4::2], rows[5::2], [(8.99, 11.00), (9.96, 10.09), (9.98, 10.03)]):
        pairs.append(dict(scenario=gen['stream'].split('_')[0], generator_packets=gen['captured'],
                          collector_packets=rx['captured'], captured_count_shortfall=gen['captured'] - rx['captured'],
                          generator_first_time_us=gen['first_capture_us'], collector_first_time_us=rx['first_capture_us'],
                          collector_min_ms=rx['min_interval_us']/1000, collector_max_ms=rx['max_interval_us']/1000,
                          description_table1_min_ms=low, description_table1_max_ms=high,
                          collector_gaps_gt_15ms=rx['interval_gt_15ms']))
    save(args.output / 'unico-wifi-scenarios.csv', pairs)


if __name__ == '__main__':
    main()
