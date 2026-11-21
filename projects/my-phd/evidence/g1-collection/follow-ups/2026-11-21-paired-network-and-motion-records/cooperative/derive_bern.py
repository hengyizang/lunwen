"""Audit the fixed TWR-CLOUD-Bern v6 role tables. Python 3.11+, pandas 2.2, NumPy."""
import argparse
import hashlib
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

DIGESTS = {
    'Rangings at Pollers (Stats).pkl': 'fa848403f34d5f594e0677e2492230942b5674873c5eb96948954a7da04bfd99',
    'Rangings at Pollers.pkl': '55189d1ae900bbb836806715d15c1425b0a19c0c3c3ceff9238387388af3228e',
    'Rangings at Responders (Stats).pkl': 'faa9e67f06584811e12bc50fd328fbac1b7e95e756f59bae681a842a035c49bd',
    'Rangings at Responders.pkl': '65c077bb1aa9b8793d9b206a406ecfd574047ad345fbafdbf93cfcdfad26fa21',
}
SPEED_OF_LIGHT_AIR = 299702547  # m/s used by the published release builder


class PinnedFrameReader(pickle.Unpickler):
    allowed = {
        'pandas.core.frame': {'DataFrame'},
        'pandas.core.internals.managers': {'BlockManager'},
        'pandas._libs.internals': {'_unpickle_block'},
        'numpy._core.numeric': {'_frombuffer'},
        'numpy': {'dtype', 'ndarray'},
        'builtins': {'slice'},
        'numpy._core.multiarray': {'_reconstruct'},
        'pandas.core.indexes.base': {'_new_Index', 'Index'},
        'pandas.core.indexes.range': {'RangeIndex'},
    }

    def find_class(self, module, name):
        if name not in self.allowed.get(module, set()):
            raise ValueError(f'Unexpected pickle global {module}.{name}')
        return super().find_class(module, name)


def load(root, name):
    with (root / name).open('rb') as f:
        if hashlib.file_digest(f, 'sha256').hexdigest() != DIGESTS[name]:
            raise ValueError(f'Expected the pinned v6 release of {name}')
        f.seek(0)
        return PinnedFrameReader(f).load()


def rounded(v):
    return round(float(v), 8)


def signatures(frame):
    # At most 12 scans, 7 listening periods, 40 nodes and a finite set of range estimates.
    # An exact float is used as reported by both roles; the width of the time window is varied separately.
    result = np.rec.fromarrays(
        [frame[c].to_numpy() for c in ('Listening_Period', 'Poller_ID', 'Responder_ID', 'ToF', 'Timestamp')],
        names=['listen', 'poll', 'resp', 'tof', 'ts'])
    return np.sort(result)


def candidate_bounds(query, other, window_ns):
    lo = query.copy()
    hi = query.copy()
    lo.ts -= window_ns
    hi.ts += window_ns
    return np.searchsorted(other, lo), np.searchsorted(other, hi, side='right')


def pairing(scan, poll, resp):
    p = signatures(poll)
    r = signatures(resp)
    timestamp_fields = ['Listening_Period', 'Poller_ID', 'Responder_ID', 'Timestamp']
    same_role = pd.MultiIndex.from_frame(resp[timestamp_fields])
    swapped = resp.rename(columns={'Poller_ID':'Responder_ID', 'Responder_ID':'Poller_ID'})
    reverse_role = pd.MultiIndex.from_frame(swapped[timestamp_fields])
    poll_keys = pd.MultiIndex.from_frame(poll[timestamp_fields])
    same_stamp_links = int(poll_keys.isin(same_role).sum())
    reversed_stamp_links = int(poll_keys.isin(reverse_role).sum())
    out = []
    for ms in (0, 1, 10, 100):
        lo, hi = candidate_bounds(p, r, ms * 1_000_000)
        rlo, rhi = candidate_bounds(r, p, ms * 1_000_000)
        counts = hi - lo
        unique = np.flatnonzero(counts == 1)
        keep = unique[(rhi - rlo)[lo[unique]] == 1]
        lag = (p.ts[keep] - r.ts[lo[keep]]) / 1e6
        out.append(dict(scan=scan, window_ms=ms, poller_rows=len(p), responder_rows=len(r),
                        exact_stamp_same_link_ignoring_tof=same_stamp_links,
                        exact_stamp_reversed_link_ignoring_tof=reversed_stamp_links,
                        pollers_with_zero_candidates=int((counts == 0).sum()),
                        pollers_with_one_candidate=len(unique),
                        pollers_with_multiple_candidates=int((counts > 1).sum()),
                        mutually_unique_candidates=len(keep),
                        poller_log_before_responder_log=int((lag < 0).sum()),
                        median_poller_minus_responder_ms=rounded(np.median(lag)) if len(lag) else None))
    return out


def main(root, out):
    out.mkdir(parents=True, exist_ok=True)
    results, statistics = {}, []
    for role in ('Poller', 'Responder'):
        frame = load(root, f'Rangings at {role}s.pkl')
        counts = load(root, f'Rangings at {role}s (Stats).pkl')
        att, ok, first, final = {
            'Poller': ('Polling Attempts', 'Successful Polls', 'No Valid TX2', 'No Valid TX4'),
            'Responder': ('Responding Attempts', 'Successful Responds', 'No Valid TX1', 'No Valid TX3')
        }[role]
        results[role] = frame
        by = counts.groupby(['Scan_ID', 'Listening_Period'])
        for (scan, listen), m in frame.groupby(['Scan_ID', 'Listening_Period']):
            c = by.get_group((scan, listen))
            err = m['ToF'] * (SPEED_OF_LIGHT_AIR / 1e7) - m['Node_Distance_3D']
            # Check labelled geometric range directly against endpoint coordinates.
            dist_sq = sum((m['Poller_' + k] - m['Responder_' + k]) ** 2 for k in 'XYZ')
            reference_difference = abs(np.sqrt(dist_sq) * 100 - m['Node_Distance_3D'])
            imbalance = c[att] - (c[ok] + c[first] + c[final])
            statistics.append(dict(scan=int(scan), split=m['Class'].unique().item(), listen_ms=int(listen),
                                   role=role, records=len(m), stats_rows=len(c),
                                   distinct_directed_links=len(m[['Poller_ID', 'Responder_ID']].drop_duplicates()),
                                   successful_counter=int(c[ok].sum()), attempts_counter=int(c[att].sum()),
                                   first_rx_invalid_counter=int(c[first].sum()), later_rx_invalid_counter=int(c[final].sum()),
                                   rows_attempts_differ_success_plus_two_failure_counters=int((imbalance != 0).sum()),
                                   rows_first_rx_invalid_exceeds_attempts=int((c[first] > c[att]).sum()),
                                   successful_counter_minus_records=int(c[ok].sum() - len(m)),
                                   negative_tof_ns=int((m['ToF'] < 0).sum()),
                                   ranges_abs_error_mean_cm=rounded(np.abs(err).mean()),
                                   ranges_abs_error_median_cm=rounded(np.median(np.abs(err))),
                                   ranges_abs_error_p95_cm=rounded(np.quantile(np.abs(err), .95)),
                                   surveyed_coordinate_distance_check_max_diff_cm=rounded(reference_difference.max())))
    scans = sorted(results['Poller']['Scan_ID'].unique())
    matches = []
    for scan in scans:
        subsets = [table.loc[table['Scan_ID'] == scan] for table in results.values()]
        matches.extend(pairing(int(scan), *subsets))
    pd.DataFrame(statistics).to_csv(out/'bern-role-condition.csv', index=False)
    pd.DataFrame(matches).to_csv(out/'bern-time-association.csv', index=False)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('data', type=Path)
    p.add_argument('out', type=Path)
    args = p.parse_args()
    main(args.data, args.out)
