"""Recompute complete DS-TWR exchanges in the Linz rotary-table release (NumPy).
Run python linz_clocks.py --output destination. Only one source blob is held at a time.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import pickletools
import time
from urllib.request import Request, urlopen

import numpy as np

REPO = "ppeterseil/UWB-weak-NLOS-structured-dataset"
REV = "fc165c5a68c95a0cfc80729905081654737842ad"
CLOCKS = ["TS_TTX1", "TS_ARX1", "TS_ATX1", "TS_TRX1", "TS_TTX2", "TS_ARX2"]
INTERVALS = {"Ra": (3, 0), "Rb": (5, 2), "Da": (4, 3), "Db": (2, 1)}


def get(url):
    for attempt in range(3):
        try:
            with urlopen(Request(url, headers={"User-Agent": "G1-academic-research"}), timeout=90) as response:
                return response.read()
        except OSError:
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)


def numeric_blocks(blob):
    # Parse the primitive arrays in this pinned data layout without executing the pickle.
    operations = [(op.name, arg) for op, arg, _ in pickletools.genops(blob)]
    strings = [arg for op, arg in operations if op == "SHORT_BINUNICODE"]
    columns = strings[strings.index("firstPathPower"):strings.index("TS_ARX2") + 1]
    buffers = [arg for op, arg in operations if op == "BINBYTES"]
    rows = len(buffers[-1])
    matrix = np.frombuffer(buffers[0], "<f8").reshape(-1, rows)
    positions = list(np.frombuffer(buffers[1], "<i8"))
    assert len(columns) == 128 and len(positions) == len(matrix) == 127
    codes_start = operations.index(("SHORT_BINUNICODE", "codes"))
    codes = [arg for op, arg in operations[codes_start:] if op == "BINBYTES"]
    assert len(codes) == 7 and len(codes[0]) == len(codes[2]) == rows and len(codes[1]) == 2 * rows
    # The first three MultiIndex levels are anchor, sample and packet step.
    def level_values(key):
        stop = operations.index(("SHORT_BINUNICODE", key))
        buf = next(arg for op, arg in reversed(operations[:stop]) if op in ("BINBYTES", "SHORT_BINBYTES"))
        return np.frombuffer(buf, "<i8")
    anchor_values, step_values = level_values("anchor"), level_values("step")
    assert set(anchor_values.tolist()) <= {21, 22, 23} and step_values.tolist() == [0, 1, 2]
    anchors = anchor_values[np.frombuffer(codes[0], "i1")]
    samples = np.frombuffer(codes[1], "<i2")
    steps = step_values[np.frombuffer(codes[2], "i1")]
    vectors = {key: matrix[positions.index(columns.index(key))] for key in CLOCKS + list(INTERVALS) + ["trueDistance", "distance"]}
    return anchors, samples, steps, vectors


def summarize(blob, path, sha256):
    anchors, samples, steps, v = numeric_blocks(blob)
    outputs = []
    mod = 2**40
    for anchor in np.unique(anchors):
        selected = np.flatnonzero(anchors == anchor)
        sequence = np.lexsort((steps[selected], samples[selected]))
        rows = selected[sequence]
        _, enter, counts = np.unique(samples[rows], return_index=True, return_counts=True)
        threes = enter[counts == 3]
        triples = rows[threes[:, None] + np.arange(3)]
        has_steps = np.all(steps[triples] == [0, 1, 2], axis=1)
        repeated = np.ones(len(triples), dtype=bool)
        for name in CLOCKS:
            vals = v[name][triples]
            repeated &= np.isfinite(vals).all(axis=1) & (vals == vals[:, :1]).all(axis=1)
        valid = triples[has_steps & repeated, 0]
        stamps = [v[name][valid] for name in CLOCKS]
        assert valid.size and all(np.all((x >= 0) & (x < 2**53) & (x == x.astype(np.int64))) for x in stamps)
        fits = np.ones(len(valid), dtype=bool)
        wrapped = np.zeros(len(valid), dtype=bool)
        for name, (stop, start) in INTERVALS.items():
            diff = stamps[stop] - stamps[start]
            fits &= diff % mod == v[name][valid]
            wrapped |= diff < 0
        tag_total = (stamps[4] - stamps[0]) % mod
        anchor_total = (stamps[5] - stamps[1]) % mod
        ppm = (tag_total / anchor_total - 1) * 1e6
        med = lambda arr: round(float(np.median(arr)), 6)
        outputs.append(dict(file=path, sha256=sha256, anchor=int(anchor), packet_rows=len(rows),
                            sequence_keys=len(counts), valid_three_packet_exchanges=len(valid),
                            four_local_intervals_match=int(fits.sum()), negative_local_difference_exchanges=int(wrapped.sum()),
                            any_stored_tick_ge_2pow40=int(np.any(np.asarray(stamps) >= mod, axis=0).sum()),
                            relative_interval_ratio_ppm_p05=round(float(np.quantile(ppm, .05)), 6),
                            relative_interval_ratio_ppm_p50=med(ppm),
                            relative_interval_ratio_ppm_p95=round(float(np.quantile(ppm, .95)), 6),
                            published_true_distance_median_m=med(v["trueDistance"][valid]),
                            published_range_minus_true_median_m=med(v["distance"][valid] - v["trueDistance"][valid])))
    return outputs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("."))
    parser.add_argument("--cache", type=Path, help="Optional existing cache with the upstream relative paths")
    args = parser.parse_args()
    tree = json.loads(get(f"https://api.github.com/repos/{REPO}/git/trees/{REV}?recursive=1"))["tree"]
    files = sorted((entry for entry in tree if entry["path"].endswith(".pkl")), key=lambda x:x["path"])
    assert len(files) == 36
    rows = []
    for entry in files:
        name = entry["path"]
        cached = args.cache / name if args.cache else None
        blob = cached.read_bytes() if cached and cached.exists() else get(f"https://raw.githubusercontent.com/{REPO}/{REV}/{name}")
        assert len(blob) == entry["size"]
        assert hashlib.sha1(f"blob {len(blob)}\0".encode() + blob).hexdigest() == entry["sha"]
        rows.extend(summarize(blob, name, hashlib.sha256(blob).hexdigest()))
        print(name, flush=True)
    args.output.mkdir(parents=True, exist_ok=True)
    with (args.output / "linz-clock-summary.csv").open("w", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
