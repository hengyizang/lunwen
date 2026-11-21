"""Audit DETERMINISTIC6G COTS-side packet timing. Uses NumPy, PyArrow, OpenPyXL."""
import argparse
from collections import defaultdict
import csv
import hashlib
import io
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import openpyxl
import pyarrow.parquet as pq


def save(path, rows):
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0], lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def distribution(values):
    return {field: round(float(np.quantile(values, q)) / 1e6, 6)
            for field, q in [('median_ms', .5), ('p95_ms', .95), ('p99_ms', .99), ('max_ms', 1)]}


def single(z, name):
    blob = z.read(name)
    frame = pq.read_table(io.BytesIO(blob)).to_pandas().sort_index(kind='stable')
    seq = frame.index.to_numpy()
    assert len(seq) == len(np.unique(seq))
    starts = frame['timestamps.client.send.wall'].to_numpy()
    ends = frame['timestamps.server.receive.wall'].to_numpy()
    delay = frame['delay.send'].to_numpy()
    # Use integer arithmetic after conversion of the stored, rounded epoch value.
    valid = np.isfinite(ends) & np.isfinite(delay)
    recv = ends[valid].astype(np.int64)
    error = np.abs(recv - starts[valid].astype(np.int64) - delay[valid])
    physical = delay[valid]
    lost = frame['lost']
    assert np.all(np.isfinite(starts))
    # Count arrivals behind an already observed higher sequence, within each round.
    # Group tied receipt times so ties alone can never create an order inversion.
    order = np.argsort(recv, kind='stable')
    sorted_time = recv[order]
    ordered_seq = seq[valid][order]
    blocks = np.r_[0, np.flatnonzero(np.diff(sorted_time)) + 1]
    peak = np.maximum.reduceat(ordered_seq, blocks)
    preceding_peak = np.r_[-1, np.maximum.accumulate(peak)[:-1]]
    strict_old = ordered_seq < np.repeat(preceding_peak, np.diff(np.r_[blocks, len(ordered_seq)]))
    def singleton(k):
        arr = frame[k].drop_duplicates().tolist()
        return '|'.join(map(str, sorted(arr)))
    row = dict(member=name, sha256=hashlib.sha256(blob).hexdigest(), session=name.split('/')[1],
               direction=singleton('trip'), packet_length_field=singleton('packet_length'),
               packet_multiply_field=singleton('packet_multiply'), packet_interval_ns=singleton('packet_interval'),
               rows=len(seq), first_seq=seq[0], last_seq=seq[-1], holes_inside_seq_range=int(seq[-1]-seq[0]+1-len(seq)),
               backwards_send_clock=int((np.diff(starts)<0).sum()), valid_delay_and_endpoints=int(valid.sum()),
               missing_end_wall=int((~np.isfinite(ends)).sum()), missing_delay=int((~np.isfinite(delay)).sum()),
               lost_literal_true=int((lost == 'true').sum()), lost_literal_true_with_received_wall=int(((lost=='true') & np.isfinite(ends)).sum()),
               negative_valid_delay=int((physical<0).sum()),
               out_of_order_by_receive_wall=int(strict_old.sum()),
               tied_extra_receive_wall=int(len(sorted_time)-len(blocks)),
               max_abs_wall_minus_deposited_delay_ns=int(error.max()), delay_gt_10ms=int((physical>10e6).sum()),
               **distribution(physical))
    return row, physical


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('zip', type=Path)
    p.add_argument('out', type=Path)
    args = p.parse_args()
    args.out.mkdir(exist_ok=True,parents=True)
    with ZipFile(args.zip) as z:
        workbook = next(x for x in z.namelist() if x.endswith('.xlsx'))
        ws = openpyxl.load_workbook(io.BytesIO(z.read(workbook)), data_only=True,read_only=True)['EP5G industrial control']
        campaign = {str(r[0]):r for r in list(ws.values)[1:] if r[0]}
        members = defaultdict(list)
        for name in sorted(z.namelist()):
            if name.endswith('.parquet'):
                members[name.split('/')[1]].append(name)
        runs, sessions = [], []
        for condition, names in sorted(members.items()):
            records = [single(z,n) for n in names]
            rows = [row for row,_ in records]
            values = np.concatenate([d for _,d in records])
            runs.extend(rows)
            session, direction = condition.split('-')
            meta = campaign[condition] if condition in campaign else campaign[session]
            sessions.append(dict(session=condition, campaign_direction=meta[7], campaign_payload_B=meta[4],
                                 campaign_interval_ms=meta[2], rounds=len(rows), rows=sum(r['rows'] for r in rows),
                                 receive_and_delay_rows=len(values), delay_gt_10ms=int((values>10e6).sum()),
                                 late_after_fresher_sequence=sum(r['out_of_order_by_receive_wall'] for r in rows),
                                 **distribution(values)))
        coverage = []
        for key, row in campaign.items():
            condition = key if '-' in key else f'{key}-{row[7]}'
            coverage.append(dict(workbook_identifier=key, direction=row[7],
                                 campaign_status=row[9] or '', rounds_in_archive=len(members.get(condition, []))))
    save(args.out/'cellular-workbook-coverage.csv', coverage)
    save(args.out/'cellular-rounds.csv', runs)
    save(args.out/'cellular-sessions.csv', sessions)


if __name__ == '__main__':
    main()
