"""Match unmodified SQLite/CDR sensor measurements to released 100-Hz samples.

python derive_shaft_native.py data.tar.gz DIRECTORY_WITH_EXTRACTED_DB3 OUTPUT_DIRECTORY
Run on Free and Teleop_compressed original data folders. Requires NumPy, pandas.
"""
import argparse
import csv
import hashlib
import io
from pathlib import Path
import sqlite3
import struct
import tarfile
import numpy as np
import pandas as pd


def read_wrenches(db, name):
    row = db.execute('SELECT id, type FROM topics WHERE name = ?', (name,)).fetchone()
    if row is None:
        return np.array([], dtype=np.int64), np.empty((0, 6)), set()
    assert row[1] == 'geometry_msgs/msg/WrenchStamped'
    stamps, vectors, frames = [], [], set()
    for stamp, payload in db.execute(
        'SELECT timestamp, data FROM messages WHERE topic_id = ? ORDER BY timestamp, id', (row[0],)
    ):
        # CDR little endian, Header timestamp and nul-terminated string followed by six doubles.
        assert payload[:4] == b'\x00\x01\x00\x00'
        size = struct.unpack_from('<I', payload, 12)[0]
        assert size > 0 and payload[15 + size] == 0
        offset = 4 + (12 + size + 7) // 8 * 8
        assert len(payload) == offset + 48
        frames.add(payload[16:15 + size].decode())
        stamps.append(stamp)
        vectors.append(struct.unpack_from('<6d', payload, offset))
    return np.asarray(stamps, dtype=np.int64), np.asarray(vectors, dtype=float), frames


def audit(file, frame):
    with file.open('rb') as src:
        digest = hashlib.file_digest(src, 'sha256').hexdigest()
    with sqlite3.connect(file.as_uri() + '?mode=ro', uri=True) as db:
        htime, hexvec, hframe = read_wrenches(db, '/HEX10/wrench')
        atime, ativec, aframe = read_wrenches(db, '/ati_data')
    columns = ['fx', 'fy', 'fz', 'tx', 'ty', 'tz']
    published = frame[columns].to_numpy(dtype=np.float32)
    native = hexvec.astype(np.float32)
    lookup = {}
    for i, row in enumerate(native):
        key = row.tobytes()
        lookup[key] = i if key not in lookup else -1
    # Each unique exact wrench anchors a lower/upper bound on the common grid origin.
    # A value repeats on the grid if no new physical measurement has arrived.
    ids = np.asarray([lookup.get(row.tobytes(), -1) for row in published], dtype=int)
    rows = np.where((ids >= 0) & (ids < len(native) - 1))[0]
    assert len(rows) > 0
    step = 10_000_000
    lo = np.max(htime[ids[rows]] - rows * step)
    hi = np.min(htime[ids[rows] + 1] - rows * step)
    out = dict(bag=file.parent.name, db3_sha256=digest, db3_bytes=file.stat().st_size,
               native_hex_messages=len(native), native_ati_messages=len(atime),
               hex_frame_ids=repr(sorted(hframe)), ati_frame_ids=repr(sorted(aframe)), released_rows=len(frame),
               unambiguous_hex_anchors=len(rows), grid_origin_latest_lower_ns=int(lo),
               grid_origin_earliest_exclusive_upper_ns=int(hi), feasible_origin_width_ns=int(hi - lo),
               six_hex_fields_matching_rows='', ati_force_norm_abs_diff_p99_N='',
               ati_force_norm_abs_diff_max_N='', native_ati_torque_allzero_rows='',
               native_ati_torque_norm_p50_native='', native_ati_torque_norm_p95_native='',
               native_ati_torque_norm_max_native='')
    if len(atime):
        norms = np.linalg.norm(ativec[:, 3:], axis=1)
        out.update(native_ati_torque_allzero_rows=int(np.sum((ativec[:, 3:] == 0).all(axis=1))),
                   native_ati_torque_norm_p50_native=round(float(np.median(norms)), 8),
                   native_ati_torque_norm_p95_native=round(float(np.percentile(norms, 95)), 8),
                   native_ati_torque_norm_max_native=round(float(max(norms)), 8))
    if hi <= lo:
        return out
    # A midpoint of the feasible interval is one admissible alignment, not hardware timing truth.
    grid = lo + (hi - lo - 1) // 2 + np.arange(len(frame), dtype=np.int64) * step
    hist = np.searchsorted(htime, grid, side='right') - 1
    assert min(hist) >= 0
    out['six_hex_fields_matching_rows'] = int((published == native[hist]).all(axis=1).sum())
    if len(atime):
        prev = np.searchsorted(atime, grid, side='right') - 1
        ok = prev >= 0
        reference_force = np.linalg.norm(ativec[prev[ok], :3], axis=1)
        prepared_force = np.linalg.norm(frame[['ati_fx', 'ati_fy', 'ati_fz']].to_numpy()[ok], axis=1)
        delta = np.abs(reference_force - prepared_force)
        out.update(ati_force_norm_abs_diff_p99_N=round(float(np.percentile(delta, 99)), 9),
                   ati_force_norm_abs_diff_max_N=round(float(max(delta)), 9))
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('prepared', type=Path)
    parser.add_argument('native_dir', type=Path)
    parser.add_argument('out', type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    records = []
    with tarfile.open(args.prepared, 'r:*') as z:
        files = {Path(obj.name).parent.name: obj for obj in z if obj.name.endswith('.csv')}
        for db in sorted(args.native_dir.resolve().rglob('*.db3')):
            data = pd.read_csv(io.BytesIO(z.extractfile(files[db.parent.name]).read()),
                               usecols=['fx','fy','fz','tx','ty','tz','ati_fx','ati_fy','ati_fz'])
            records.append(audit(db, data))
    with (args.out/'shaft-native-replay.csv').open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=records[0], lineterminator='\n')
        writer.writeheader()
        writer.writerows(records)


if __name__ == '__main__':
    main()
