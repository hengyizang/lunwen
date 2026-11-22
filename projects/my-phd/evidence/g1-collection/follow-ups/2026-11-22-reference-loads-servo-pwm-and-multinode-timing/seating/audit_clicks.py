"""Summarize the checked-in-version Mendeley feature file. Python stdlib plus NumPy."""

import argparse
import collections
import csv
import hashlib
import io
from pathlib import Path
from urllib.request import Request, urlopen
from zipfile import ZipFile
import numpy as np

SOURCE = "https://data.mendeley.com/public-api/zip/2p4ng7zz3s/download/1"
SOURCE_HASH = "3fee0517e19f88099c46b4fc3f381e726b78cb0b4563b3322847c69a24163746"


def summarize(raw, output):
    if hashlib.sha256(raw).hexdigest() != SOURCE_HASH:
        raise ValueError("DataSet.csv differs from the version-1 source checksum")
    rows = csv.reader(
        io.TextIOWrapper(io.BytesIO(raw), encoding="utf-8-sig", newline="")
    )
    header = next(rows)
    assert header == [str(i) for i in range(1, 214)] + ["Class"]
    labels = collections.Counter()
    repeated = collections.defaultdict(collections.Counter)
    missing = collections.Counter()
    for row in rows:
        assert len(row) == len(header)
        label = row[-1]
        labels[label] += 1
        values = np.asarray(row[:-1], dtype="<f8")
        missing[label] += int((~np.isfinite(values)).sum())
        repeated[hashlib.sha256(values.tobytes()).digest()][label] += 1
    with Path(output).open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(
            [
                "source_sha256",
                "source_class",
                "rows",
                "feature_columns",
                "unique_feature_vectors_within_class",
                "feature_vectors_shared_with_other_classes",
                "nonfinite_feature_values",
            ]
        )
        for label, count in sorted(labels.items()):
            writer.writerow(
                [
                    SOURCE_HASH,
                    label,
                    count,
                    len(header) - 1,
                    sum(label in group for group in repeated.values()),
                    sum(
                        label in group and len(group) > 1 for group in repeated.values()
                    ),
                    missing[label],
                ]
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("click-features.csv"))
    args = parser.parse_args()
    request = Request(SOURCE, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(request, timeout=180) as response:
        archive = ZipFile(io.BytesIO(response.read()))
    with archive:
        (member,) = [
            name for name in archive.namelist() if name.endswith("DataSet.csv")
        ]
        summarize(archive.read(member), args.out)
