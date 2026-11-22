"""Summarize three moving model-railway measurements and their surveyed path (Python stdlib)."""
import argparse
import collections
import csv
import hashlib
import io
from pathlib import Path
from urllib.request import urlopen

BASE = "https://raw.githubusercontent.com/ppeterseil/UWB-AEC-trust-dataset/12f631086eaf1f6510e5feb98627a6aefa8b1feb/"
INPUTS = {
    "datasets/dyn_nlos.csv": "6ea74ad9f18b76d4638fde26c448bd805cda795d86c2fbb76f6e2986e4cbb28f",
    "datasets/dyn_nlos2.csv": "43dd90dc3a0e3f9e3bcde4362d08c78776f5c36674a1d663430377f868853d90",
    "datasets/dyn_person.csv": "089c018d91c6f0a59945be25f949520e605936168ed06156d937280aaa2d24f4",
    "reference/trajectory.csv": "c0034383eb7b5643d880dcb472dfc535576255abedab34bd39f1adc95082ad1c"
}


def rows(path, digest):
    with urlopen(BASE + path, timeout=90) as source:
        data = source.read()
    assert hashlib.sha256(data).hexdigest() == digest
    return io.StringIO(data.decode())


def summarize(name):
    by_anchor = collections.defaultdict(list)
    for row in csv.reader(rows(name, INPUTS[name])):
        if not row or row[0].startswith("#"):
            continue
        if row[1] == "result":
            header = row
            continue
        r = dict(zip(header, row))
        assert r["topic"] == "jku/ranging"
        by_anchor[r["nodeid"]].append(r)
    for anchor, data in sorted(by_anchor.items()):
        keys, invalid_order = set(), 0
        wraps = 0
        for r in data:
            # DW1000 uses a 40-bit timestamp counter. Assess ordering inside one exchange
            # separately on the tag and anchor. Wall clocks across devices are not subtracted.
            tag = [int(r[k]) for k in ("ttx1", "trx1", "ttx2")]
            peer = [int(r[k]) for k in ("arx1", "atx1", "arx2")]
            keys.add((r["seqcode"], r["seqno"]))
            wraps += any(b < a for local in (tag, peer) for a, b in zip(local, local[1:]))
            for local in (tag, peer):
                first, middle, last = local
                left, right = (middle - first) % 2**40, (last - middle) % 2**40
                if not (0 < left and 0 < right and left + right == (last - first) % 2**40):
                    invalid_order += 1
                    break
        yield dict(file=name, sha256=INPUTS[name], anchor=anchor, exchanges=len(data),
                   unique_sequencecode_number_pairs=len(keys), valid_both_local_orders=len(data) - invalid_order,
                   negative_difference_before_modulo=wraps, logger_time_min=min(r["_time"] for r in data),
                   logger_time_max=max(r["_time"] for r in data))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("."))
    dest = parser.parse_args().output
    dest.mkdir(parents=True, exist_ok=True)
    stats = [r for path in INPUTS if path.startswith("datasets/") for r in summarize(path)]
    with (dest / "linz-rail-exchanges.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=stats[0])
        w.writeheader()
        w.writerows(stats)
    path = "reference/trajectory.csv"
    coords = list(csv.DictReader(rows(path, INPUTS[path])))
    assert list(coords[0]) == ["", "x", "y"] and all(float(r["x"]) == float(r["x"]) and float(r["y"]) == float(r["y"]) for r in coords)
    print(f"{len(coords)} indexed path points, with x and y coordinates.")


if __name__ == "__main__":
    main()
