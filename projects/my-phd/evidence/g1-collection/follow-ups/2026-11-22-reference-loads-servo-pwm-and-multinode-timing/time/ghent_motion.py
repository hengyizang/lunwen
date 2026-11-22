"""Summarize public Ghent radio and optical traces. Uses Python 3 and NumPy.

python ghent_motion.py --output results
An optional --cache supplies existing files named as in ghent-file-manifest.csv.
The source files are checked against the SHA-256 hashes of the inspected versions.
"""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import io
from pathlib import Path
from urllib.request import urlopen

import numpy as np

ROOT = "https://cloud.ilabt.imec.be/public.php/dav/files/"
RUNS = {
    "tdoa-random": ("XAmg5spW2As3toD", "db0fcf111a90c9bb7656540ca55e7fa569a1787c9c9496fd6ce281999e4c83f1", "f2a2a41af2ebe605a9f32907784605537fc96aec204af5e5c803025cf383ce7b"),
    "twr-one": ("iS3RkgeHAwitPTp", "687d097014bb9e40de1b3feaf8ff04ca675ac0b200b7badaa4da8f3368613138", "8112cc9df17d5f833cbdede0d72b37af0996d6acec0eef0c8c127906ab6705d4"),
    "twr-two": ("QtwFWDZG6PyrNXc", "8ad8935f594f9a4ba9154f6fe64fd27b787aeafe56fe3cadca93fa341671ad4a", "6948c6c00c771142df2c5723a971a1c3037f263b02af134d651d45540020a4f9"),
}


def read(run, token, member, digest, cache):
    source_url = ROOT + token + "/" + member
    name = run + "-" + member
    local = cache / name if cache else None
    if local and local.exists():
        raw = local.read_bytes()
    else:
        with urlopen(source_url, timeout=90) as f:
            raw = f.read()
    assert hashlib.sha256(raw).hexdigest() == digest, name
    return io.StringIO(raw.decode()), dict(run=run, cache_filename=name, source_url=source_url, bytes=len(raw), sha256=digest)


def export(folder, name, rows):
    with (folder / name).open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rows[0])
        w.writeheader()
        w.writerows(rows)


def utc(x):
    return datetime.fromtimestamp(x, timezone.utc).isoformat(timespec="milliseconds")


def rounded(q):
    return round(float(q), 6)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path)
    parser.add_argument("--output", type=Path, default=Path("."))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    manifests, stats, groups = [], [], []
    for run, (token, r_digest, g_digest) in RUNS.items():
        gf, gm = read(run, token, "gt.csv", g_digest, args.cache)
        g = np.array([[float(row[k]) for k in ("Logtime", "x", "y", "z")] for row in csv.DictReader(gf)])
        del gf
        gt = g[:, 0]
        assert np.isfinite(g).all() and np.all(np.diff(gt) > 0)
        rf, rm = read(run, token, "processed_full.csv", r_digest, args.cache)
        manifests.extend([rm, gm])
        buckets, keys, radio_time, anchors, observed_tags = {}, set(), [], set(), set()
        duplicates, complete, seqs = 0, 0, set()
        timestamps = ["UWB_time", "ts", "sync"] if run == "tdoa-random" else [f"T{i}" for i in range(1, 8)]
        for row in csv.DictReader(rf):
            t = float(row["Logtime"])
            anchor, tag, frame = row["anchor"], row["tag"], int(float(row["superframe"]))
            key = tag, frame, anchor
            duplicates += key in keys
            keys.add(key)
            anchors.add(anchor)
            observed_tags.add(tag)
            seqs.add(int(row["header.seq"]))
            radio_time.append(t)
            complete += all(row[k].strip() for k in timestamps)
            if run == "tdoa-random":
                assert row["mode"] == "TDOA"
                buckets.setdefault((tag, frame), []).append((anchor, t))
        del rf
        rt = np.array(radio_time)
        assert np.isfinite(rt).all()
        inside = rt[(rt >= gt[0]) & (rt <= gt[-1])]
        ix = np.searchsorted(gt, inside).clip(1, len(gt) - 1)
        distances = np.minimum(abs(inside - gt[ix - 1]), abs(inside - gt[ix])) * 1000
        stats.append(dict(run=run, radio_rows=len(rt), optical_rows=len(gt), distinct_observed_anchor_ids=len(anchors),
                          distinct_observed_tag_ids=len(observed_tags), distinct_logger_header_seq=len(seqs),
                          duplicate_tag_frame_anchor_rows=duplicates, complete_timing_fields_rows=complete,
                          checked_timing_fields=" ".join(timestamps), radio_min_utc=utc(rt.min()),
                          radio_max_utc=utc(rt.max()), optical_min_utc=utc(gt[0]), optical_max_utc=utc(gt[-1]),
                          radio_time_reversals_in_file=int(np.sum(np.diff(rt) < 0)),
                          radio_rows_inside_optical_interval=len(inside), optical_nearest_gap_median_ms=rounded(np.median(distances)),
                          optical_nearest_gap_p95_ms=rounded(np.quantile(distances, .95)),
                          inside_with_nearest_optical_over_50ms=int(np.sum(distances > 50)),
                          optical_largest_step_s=rounded(np.diff(gt).max()),
                          optical_x_span_m=rounded(np.ptp(g[:, 1])), optical_y_span_m=rounded(np.ptp(g[:, 2]))))
        if buckets:
            by_count = {}
            for observations in buckets.values():
                n = len({a for a, _ in observations})
                ts = [t for _, t in observations]
                by_count.setdefault(n, []).append(1000 * (max(ts) - min(ts)))
            for n, spans in sorted(by_count.items()):
                groups.append(dict(distinct_anchor_ids=n, tag_superframes=len(spans),
                                   logtime_span_median_ms=rounded(np.median(spans)),
                                   logtime_span_p95_ms=rounded(np.quantile(spans, .95)),
                                   logtime_span_max_ms=rounded(max(spans))))
    export(args.output, "ghent-file-manifest.csv", manifests)
    export(args.output, "ghent-motion-summary.csv", stats)
    export(args.output, "ghent-tdoa-superframes.csv", groups)


if __name__ == "__main__":
    main()
