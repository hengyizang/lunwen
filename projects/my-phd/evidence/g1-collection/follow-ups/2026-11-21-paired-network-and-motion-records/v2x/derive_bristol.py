"""Summarize all publisher MATLAB tables and pair both passenger cars' CAM records.
Usage: python derive_bristol.py importedData macAddresses.mat OUT
Requires NumPy and SciPy. The MATLAB table subsystem is verified by field names and dimensions.
"""
import argparse
import csv
import hashlib
import io
from pathlib import Path
import re
import numpy as np
from scipy.io import loadmat
from scipy.io.matlab._mio5 import MatFile5Reader


def write_csv(path, rows):
    with path.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0], lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def read_table(path):
    source = loadmat(path)
    stream = io.BytesIO(source['__function_workspace__'].tobytes())
    if stream.read(8) != bytes.fromhex('0001494d00000000'):
        raise ValueError('Unexpected MATLAB subsystem header')
    reader = MatFile5Reader(stream, byte_order='<', struct_as_record=False)
    reader.initialize_read()
    header, _ = reader.read_var_header()
    cells = reader.read_var_array(header, True).item().MCOS.item()[3].ravel()
    names = [str(x.item()) for x in cells[-3].ravel()]
    vectors = cells[-8].ravel()
    data = dict(zip(names, (v.ravel() for v in vectors), strict=True))
    count = int(cells[-6].item())
    if 'RxMAC' in data:
        categories = np.asarray([str(x.item()) for x in cells[2].ravel()])
        codes = cells[3].ravel().astype(int)
        # MATLAB categorical index 0 denotes an undefined value.
        data['RxMAC'] = np.r_[np.array(['']), categories][codes]
    elif 'srcAddress' in data:
        words = cells[2].ravel()
        if tuple(words[:4]) != (1, 2, count, 1):
            raise ValueError('Unsupported MATLAB string array header')
        lengths = words[4:4+count]
        payload = words[4+count:].astype('<u8', copy=False).tobytes()
        if len(payload) < 2*int(lengths.sum()):
            raise ValueError('Truncated string array')
        if np.all(lengths == 17):
            data['srcAddress'] = np.frombuffer(payload[:34*count], dtype='S34').view('<u2').reshape(count,17)[:,::1].astype('u1').view('S17').reshape(-1).astype('U17')
        else:
            text = payload[:2*int(lengths.sum())].decode('utf-16-le')
            offsets = np.r_[0, np.cumsum(lengths)].astype(int)
            data['srcAddress'] = np.array([text[a:b] for a,b in zip(offsets,offsets[1:])])
    if any(len(x) != count for x in data.values()):
        raise ValueError(f'Table row counts disagree in {path.name}')
    return data


def match(sender_seq, observed_seq):
    seq, indices, counts = np.unique(sender_seq, return_index=True, return_counts=True)
    order = np.searchsorted(seq, observed_seq)
    within = order < len(seq)
    rx = np.flatnonzero(within)
    rx = rx[(seq[order[rx]] == observed_seq[rx]) & (counts[order[rx]] == 1)]
    return indices[order[rx]], rx


def quantile(values, p):
    values = np.asarray(values)
    values = values[np.isfinite(values)]
    return round(float(np.quantile(values,p)), 6) if len(values) else ''


def audit_pair(tx, rx, sniff, source_mac, receiver_tx, metadata):
    rx_idx = np.flatnonzero(rx['RxMAC'] == source_mac)
    cap_idx = np.flatnonzero(np.char.lower(sniff['srcAddress']) == source_mac)
    app, keep_app = match(tx['SeqNum'], rx['SeqNum'][rx_idx])
    cap, keep_cap = match(tx['SeqNum'], sniff['seqNum'][cap_idx])
    r = rx_idx[keep_app]
    c = cap_idx[keep_cap]
    app_u = np.unique(app)
    cap_u = np.unique(cap)
    both = np.intersect1d(app_u, cap_u)
    sender_time = tx['Timestamp']
    # Receiver's own transmitted series approximates its logging interval.
    valid_receiver_ticks = receiver_tx['Timestamp'][np.isfinite(receiver_tx['Timestamp'])]
    active = (sender_time >= valid_receiver_ticks.min()) & (sender_time <= valid_receiver_ticks.max())
    capture_dt_ms = 1000.0 * sniff['timeStamp'][c] - sender_time[cap]
    app_dt_ms = rx['Timestamp'][r] - sender_time[app]
    coords = (np.rint(sniff['lon'][c]*1e7) == np.rint(tx['CamLon'][cap]*1e7)) & (np.rint(sniff['lat'][c]*1e7) == np.rint(tx['CamLat'][cap]*1e7))
    dl = np.abs(sniff['lon'][c]-tx['CamLon'][cap])*1e7
    da = np.abs(sniff['lat'][c]-tx['CamLat'][cap])*1e7
    close = (dl <= 1.00001) & (da <= 1.00001)
    return dict(**metadata, tx_rows=len(sender_time), sender_unique_finite_sequences=len(np.unique(tx['SeqNum'][np.isfinite(tx['SeqNum'])])),
                tx_rows_missing_timestamp=int(np.count_nonzero(~np.isfinite(sender_time))),
                receiver_application_rows_from_sender=len(rx_idx), receiver_capture_rows_from_sender=len(cap_idx),
                app_rows_joined=len(app), capture_rows_joined=len(cap), distinct_sent_seen_at_application=len(app_u),
                distinct_sent_seen_at_capture=len(cap_u), distinct_seen_at_both=len(both), distinct_app_only=len(np.setdiff1d(app_u,cap_u)),
                distinct_capture_only=len(np.setdiff1d(cap_u,app_u)), distinct_seen_at_neither=len(sender_time)-len(np.union1d(app_u,cap_u)),
                tx_rows_in_receiver_own_tx_time_span=int(active.sum()), app_matched_in_time_span=int(active[app_u].sum()),
                capture_matched_in_time_span=int(active[cap_u].sum()), equal_app_and_sender_timestamp_rows=int(np.count_nonzero(app_dt_ms==0)),
                application_minus_sender_timestamp_ms_p50=quantile(app_dt_ms,.5),
                packet_capture_same_encapsulated_coordinates_rows=int(coords.sum()),
                packet_capture_within_one_coordinate_unit_rows=int(close.sum()),
                usable_capture_clock_differences=int(np.isfinite(capture_dt_ms).sum()),usable_app_clock_differences=int(np.isfinite(app_dt_ms).sum()),
                capture_clock_minus_sender_ms_negative=int(np.count_nonzero(capture_dt_ms<0)),
                capture_clock_minus_sender_ms_p05=quantile(capture_dt_ms,.05),capture_clock_minus_sender_ms_p50=quantile(capture_dt_ms,.5),
                capture_clock_minus_sender_ms_p95=quantile(capture_dt_ms,.95))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('data','address_map','out'):
        parser.add_argument(key,type=Path)
    args = parser.parse_args()
    mac = loadmat(args.address_map, simplify_cells=True)['mac']['obu']
    inventory, links = [], []
    for day in sorted(p for p in args.data.iterdir() if p.is_dir()):
        by_group = {}
        for path in sorted(day.glob('*.mat')):
            name = re.fullmatch(r'(rsu|vehNo)_([^_]+)_(TxCAM|RxCAM|tcpDump)_(LP|HP)(?:_(mr|af))?\.mat',path.name)
            if name is None:
                raise ValueError(path.name)
            kind, node, mode, band, session = name.groups()
            t = read_table(path)
            n = len(next(iter(t.values())))
            inventory.append(dict(day=day.name, file=path.name,node_type=kind,node=node,transceiver=band,session=session or 'day',
                                  table=mode,rows=n,columns='|'.join(t),bytes=path.stat().st_size,
                                  sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
            if kind == 'vehNo':
                by_group.setdefault((band,session),{}).setdefault(node,{})[mode]=t
        for (band,session), nodes in sorted(by_group.items()):
            if set(nodes) != {'00','01'}:
                continue
            for sender,receiver in [('00','01'),('01','00')]:
                origin, target = nodes[sender], nodes[receiver]
                if set(target) != {'RxCAM','TxCAM','tcpDump'}:
                    raise ValueError('Incomplete receiver data')
                links.append(audit_pair(origin['TxCAM'],target['RxCAM'],target['tcpDump'],mac['veh'+sender][band],target['TxCAM'],
                                        dict(day=day.name,transceiver=band,session=session,sender=sender,receiver=receiver)))
    args.out.mkdir(parents=True,exist_ok=True)
    write_csv(args.out/'bristol-files.csv',inventory)
    write_csv(args.out/'bristol-v2v-links.csv',links)


if __name__ == '__main__':
    main()
