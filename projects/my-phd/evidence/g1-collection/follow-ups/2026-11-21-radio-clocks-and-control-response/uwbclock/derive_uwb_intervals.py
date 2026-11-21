"""Compare intervals for the same two transmissions at Anchor 0 and at a receiver."""
import argparse
import csv
import hashlib
import io
from pathlib import Path
from zipfile import ZipFile

import numpy as np

MODULUS = 2**40
ARCHIVE_MD5 = "af8c217d6a69c5a4872660401cb6767c"
# Each tuple is (receiver, first and last sender timestamps, first and last
# matching receiver timestamps). See the sequence diagram on README.pdf p. 2.
PAIRS = [
    ("A1", "t1", "t5", "t2", "t6"),
    ("A2", "t5", "t10", "t7", "t11"),
    ("A3", "t10", "t15", "t12", "t16"),
    ("A4", "t15", "t20", "t17", "t21"),
    ("Tag", "t1", "t5", "tagPoll1", "tagPoll2"),
    ("Tag", "t5", "t10", "tagPoll2", "tagPoll3"),
    ("Tag", "t10", "t15", "tagPoll3", "tagPoll4"),
    ("Tag", "t15", "t20", "tagPoll4", "tagRange"),
    ("Tag", "t1", "t20", "tagPoll1", "tagRange"),
]


def write_csv(path, rows):
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def compare(name, fields):
    result = []
    for receiver, tx1, tx2, rx1, rx2 in PAIRS:
        tx = fields[tx2] - fields[tx1]
        rx = fields[rx2] - fields[rx1]
        if np.any(tx <= 0) or np.any(rx <= 0):
            raise ValueError(f"Nonpositive two-event interval in {name}")
        ppm = 1e6 * (rx - tx) / tx
        stats = dict(member=name, receiver=receiver, tx_start=tx1, tx_end=tx2,
                     rx_start=rx1, rx_end=rx2, intervals=len(tx),
                     tx_cross_2p40_rows=int(np.sum((fields[tx1] < MODULUS) & (fields[tx2] >= MODULUS))),
                     rx_cross_2p40_rows=int(np.sum((fields[rx1] < MODULUS) & (fields[rx2] >= MODULUS))),
                     tx_min_ticks=int(tx.min()), tx_max_ticks=int(tx.max()),
                     rx_min_ticks=int(rx.min()), rx_max_ticks=int(rx.max()))
        for label, value in zip(["min", "p05", "median", "p95", "max"],
                                np.quantile(ppm, [0, 0.05, 0.5, 0.95, 1])):
            stats[f"relative_interval_{label}_ppm"] = f"{value:.7f}"
        result.append(stats)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if hashlib.md5(args.archive.read_bytes()).hexdigest() != ARCHIVE_MD5:
        raise ValueError("Input does not match the pinned deposit")
    files, comparisons = [], []
    with ZipFile(args.archive) as archive:
        members = sorted(n for n in archive.namelist()
                         if n.endswith(".csv") and n.split("/")[0] in ("LOS", "NLOS1", "NLOS2"))
        if len(members) != 7:
            raise ValueError("Expected seven real CSV exports")
        for name in members:
            raw = archive.read(name)
            records = csv.reader(io.StringIO(raw.decode("ascii")), delimiter=";")
            header = next(records)
            values = np.asarray(list(records), dtype=np.int64)
            if len(header) != 30 or values.shape != (10000, 30):
                raise ValueError(f"Unexpected shape in {name}")
            if (values < 0).any():
                raise ValueError(f"Timestamp out of range in {name}")
            files.append(dict(member=name, csv_sha256=hashlib.sha256(raw).hexdigest(),
                              bytes=len(raw), exchanges=values.shape[0],
                              timestamp_fields=len(header), zero_ticks=int(np.sum(values == 0)),
                              ticks_ge_2p40=int(np.sum(values >= MODULUS)),
                              exchanges_ge_2p40=int(np.sum(np.any(values >= MODULUS, axis=1))),
                              duplicate_rows=len(values)-len(np.unique(values,axis=0))))
            comparisons.extend(compare(name, dict(zip(header, values.T))))
    args.output.mkdir(parents=True, exist_ok=True)
    write_csv(args.output / "uwb-clock-files.csv", files)
    write_csv(args.output / "uwb-common-event-intervals.csv", comparisons)


if __name__ == "__main__":
    main()
