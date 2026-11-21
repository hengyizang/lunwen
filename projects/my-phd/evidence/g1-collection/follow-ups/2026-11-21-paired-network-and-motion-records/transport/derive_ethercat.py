"""Inspect per-cycle drive feedback and downstream acquisition accounting.

Usage: python derive_ethercat.py LUM_TII_raw_jitter_data.zip LUM_TII_reproducibility.zip OUT
"""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import re
from zipfile import ZipFile

import numpy as np

# 64-byte CycleLogRecord documented by analyze_phase3.py in the fixed release.
RECORD = np.dtype([
    ('cycle', '<u8'), ('qpc', '<i8'), ('target', '<i4'), ('actual', '<i4'),
    ('velocity', '<i4'), ('command_velocity', '<i4'), ('acceleration', '<i4'), ('step', '<i4'),
    ('compare', '<u4'), ('status', '<u2'), ('wkc', '<i2'), ('drop_delta', '<u2'),
    ('mode', 'i1'), ('phase', 'u1'), ('flags', 'u1'), ('reserved', 'V11')
])


def write(path, rows):
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0], lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def cycle_summary(archive, member):
    blob = archive.read(member)
    data = np.frombuffer(blob, dtype=RECORD)
    meta = json.loads(archive.read(member.replace('.bin', '.json')))
    assert len(data) == meta['nCyclesWritten'] and RECORD.itemsize == 64
    dc = np.diff(data['cycle'].astype(np.int64))
    dt = np.diff(data['qpc'])
    # The host QPC runs nominally at 10 MHz. Evaluate only consecutive, positive-time pairs.
    eligible = (dc == 1) & (data['qpc'][:-1] > 0) & (dt > 0)
    long = eligible & (dt > 50_000)
    bad = data['wkc'] != 12
    same_position = data['actual'][1:] == data['actual'][:-1]
    valid_dt = dt[eligible]
    return dict(
        run=member.split('/')[0], bin_sha256=hashlib.sha256(blob).hexdigest(),
        records=len(data), cycles_reported_dropped=meta['nCyclesDropped'],
        missing_or_duplicate_index_pairs=int((dc != 1).sum()),
        nonpositive_qpc=int((data['qpc'] <= 0).sum()), consecutive_positive_pairs=int(eligible.sum()),
        median_host_interval_us=round(float(np.median(valid_dt)) / 10, 2),
        p99_host_interval_us=round(float(np.quantile(valid_dt, .99)) / 10, 2),
        max_host_interval_us=round(float(valid_dt.max()) / 10, 2),
        host_interval_over_5ms=int(long.sum()), wkc_other_than_12=int(bad.sum()),
        over_5ms_ending_with_wkc_other_than_12=int((long & bad[1:]).sum()),
        over_5ms_starting_with_wkc_other_than_12=int((long & bad[:-1]).sum()),
        consecutive_pairs_ending_bad_wkc=int((eligible & bad[1:]).sum()),
        consecutive_pairs_ending_bad_wkc_encoder_unchanged=int((eligible & bad[1:] & same_position).sum()),
        bad_wkc_and_nonzero_drop_delta=int((bad & (data['drop_delta'] != 0)).sum()),
        sum_drop_delta=int(data['drop_delta'].sum()), nonzero_compare_fire=int(np.count_nonzero(data['compare'])),
        nonzero_act_vel=int(np.count_nonzero(data['velocity'])),
        encoder_displacement_pairs=int((eligible & ~same_position).sum()),
    )


def metric_rows(z, member):
    return list(csv.DictReader(io.StringIO(z.read(member).decode('utf-8-sig'))))


def accounting(z, member):
    summary = {row['metric']: row['value'] for row in metric_rows(z, member)}
    log = z.read(member.replace('summary.csv', 'log.txt')).decode('utf-8', 'replace')
    excess = list(map(int, re.findall(r'RowAssembler[^\n]*?excess=(\d+) segments discarded', log)))
    return dict(run=member.split('/')[1], total_segments=int(summary['total_segments']),
                total_rows=int(summary['total_rows']), ring_drops=int(summary['drops']),
                row_assembler_discard_messages=len(excess), row_assembler_discarded_segments=sum(excess),
                discarded_share=round(sum(excess) / int(summary['total_segments']), 8))


def pipeline(z):
    prefix = 'data_latency/measure_Scan029_PipelineLatency/'
    out = []
    for name in ('pipeline_latency.csv', 'gl_latency.csv'):
        content = z.read(prefix + name).decode('utf-8-sig').splitlines()
        # pipeline_latency appends a separate summary block following an empty line.
        if '' in content:
            content = content[:content.index('')]
        data = list(csv.DictReader(content))
        for channel in data[0]:
            observations = np.array([float(row[channel]) for row in data])
            assert np.isfinite(observations).all()
            out.append(dict(run='Scan029', stage=channel, measured_rows=len(data),
                            median_us=round(float(np.median(observations)), 3),
                            p99_us=round(float(np.quantile(observations, .99)), 3),
                            max_us=round(float(np.max(observations)), 3)))
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('jitter', type=Path)
    parser.add_argument('analysis', type=Path)
    parser.add_argument('out', type=Path)
    args = parser.parse_args()
    args.out.mkdir(exist_ok=True, parents=True)
    with ZipFile(args.jitter) as z:
        members = sorted(x for x in z.namelist() if x.endswith('/run_0001.bin'))
        write(args.out / 'ethercat-drive-cycles.csv', [cycle_summary(z, x) for x in members])
    with ZipFile(args.analysis) as z:
        members = sorted(x for x in z.namelist() if x.startswith('data_throughput/') and x.endswith('/summary.csv'))
        write(args.out / 'ethercat-acquisition-loss.csv', [accounting(z, x) for x in members])
        write(args.out / 'ethercat-pipeline-stages.csv', pipeline(z))


if __name__ == '__main__':
    main()
