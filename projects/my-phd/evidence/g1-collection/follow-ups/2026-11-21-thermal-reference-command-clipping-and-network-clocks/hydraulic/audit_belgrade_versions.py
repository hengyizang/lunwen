"""Rebuild the Zenodo concept 4556923 version and file comparison from public records.

Usage: python audit_belgrade_versions.py OUTPUT.csv [--cache DOWNLOAD_DIRECTORY]
The four record DOIs are fixed to the lineage observed on 2026-11-21. Requires NumPy.
"""
import argparse
import csv
import hashlib
import io
import json
from collections import defaultdict
from pathlib import Path
from urllib.request import urlopen

import numpy as np

VERSIONS = (4556924, 5514279, 5514310, 5514351)
CONCEPT = "10.5281/zenodo.4556923"
METRICS = (
    "samples", "min_native", "max_native", "distinct_native", "adjacent_equal",
    "native_equal_point_two", "native_equal_one", "native_above_one",
)


def download(url, cache, label):
    target = cache / label if cache else None
    if target and target.is_file():
        return target.read_bytes()
    with urlopen(url, timeout=90) as response:
        data = response.read()
    if target:
        target.write_bytes(data)
    return data


def signal_metrics(payload, received):
    values = np.loadtxt(io.BytesIO(payload))
    if values.ndim != 1 or not np.isfinite(values).all():
        raise ValueError("Expected a finite single-column signal")
    result = {
        "samples": len(values), "min_native": values.min(), "max_native": values.max(),
        "distinct_native": len(np.unique(values)),
        "adjacent_equal": np.count_nonzero(values[1:] == values[:-1]),
    }
    if received:
        result.update(
            native_equal_point_two=np.count_nonzero(values == 0.2),
            native_equal_one=np.count_nonzero(values == 1.0),
            native_above_one=np.count_nonzero(values > 1.0),
        )
    return result


def main(output, cache):
    if cache:
        cache.mkdir(parents=True, exist_ok=True)
    rows = []
    versions_by_digest = defaultdict(list)
    for index, record in enumerate(VERSIONS):
        endpoint = f"https://zenodo.org/api/records/{record}"
        metadata = json.loads(download(endpoint, cache, f"{record}.json"))
        desc = metadata["metadata"]
        relation = desc["relations"]["version"][0]
        if metadata["conceptdoi"] != CONCEPT or relation["index"] != index:
            raise ValueError(f"Unexpected version relationship in {endpoint}")
        base = {
            "concept_doi": CONCEPT, "version_doi": metadata["doi"],
            "version": desc["version"], "publication_date": desc["publication_date"],
            "access": desc["access_right"], "license": (desc.get("license") or {}).get("id", ""),
            "record_url": endpoint,
        }
        files = metadata["files"]
        if not files:
            rows.append({**base, "kind": "restricted_record_no_files_publicly_listed"})
        for member in sorted(files, key=lambda item: item["key"]):
            name = member["key"]
            url = member["links"]["self"]
            payload = download(url, cache, f"{record}-{name}")
            if len(payload) != member["size"] or "md5:" + hashlib.md5(payload).hexdigest() != member["checksum"]:
                raise ValueError(f"Length or file checksum mismatch for {url}")
            digest = hashlib.sha256(payload).hexdigest()
            versions_by_digest[digest].append(desc["version"])
            received = name.endswith("_v2.txt")
            kind = "LC1_received" if received else "regulator_voltage" if name.endswith(".txt") else "published_table"
            row = {
                **base, "file": name, "kind": kind, "file_url": url, "bytes": len(payload),
                "source_md5": member["checksum"].removeprefix("md5:"), "observed_sha256": digest,
            }
            if name.endswith(".txt"):
                row.update(signal_metrics(payload, received))
            rows.append(row)
    for row in rows:
        if "observed_sha256" in row:
            row["versions_with_identical_bytes"] = " | ".join(versions_by_digest[row["observed_sha256"]])
    columns = (
        "concept_doi", "version_doi", "version", "publication_date", "access", "license",
        "record_url", "file", "kind", "file_url", "bytes", "source_md5", "observed_sha256",
        "versions_with_identical_bytes", *METRICS,
    )
    with output.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--cache", type=Path)
    args = parser.parse_args()
    main(args.output, args.cache)
