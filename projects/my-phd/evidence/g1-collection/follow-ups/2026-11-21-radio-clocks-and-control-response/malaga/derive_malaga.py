"""Summarize each author-labelled Málaga RTT experiment. Usage: python derive_malaga.py ZIP OUTDIR"""
import argparse
import csv
import hashlib
from pathlib import Path
import zipfile

import numpy as np


def derive(bundle, output):
    if hashlib.sha256(bundle.read_bytes()).hexdigest() != EXPECTED_SHA256:
        raise ValueError("Unexpected source archive")
    rows = []
    with zipfile.ZipFile(bundle) as archive:
        for member in sorted(n for n in archive.namelist() if n.endswith(".csv")):
            metadata_name = member.replace(".csv", "_metadata.txt")
            metadata = dict(line.split(": ", 1) for line in archive.read(metadata_name).decode().splitlines() if line)
            data = archive.read(member)
            obs = np.fromstring(data.decode("ascii"), sep="\n")
            if len(obs) != len(data.splitlines()) or not np.isfinite(obs).all():
                raise ValueError(f"Incomplete numeric parse in {member}")
            if metadata["Time units"] != "ms" or not member.endswith(metadata["Experiment ID"] + ".csv"):
                raise ValueError(f"Unexpected unit or experiment ID in {member}")
            valid = obs[obs >= 0]
            quantiles = np.quantile(valid, [0, .5, .95, .99, 1], method="linear")
            row = {
                "experiment_id": metadata["Experiment ID"], "source_member": member,
                "csv_sha256": hashlib.sha256(data).hexdigest(),
                "metadata_sha256": hashlib.sha256(archive.read(metadata_name)).hexdigest(),
                "source_name": metadata["Name"], "source_class": metadata["Class"],
                "source_density_bytes": metadata["Density (bytes)"], "source_network": metadata["Network"],
                "source_geoloc": metadata["Geoloc"], "source_software": metadata["Software"],
                "observations": len(obs), "negative": int(np.count_nonzero(obs < 0)),
                "zero": int(np.count_nonzero(obs == 0)), "nonnegative_used": len(valid),
            }
            for label, value in zip(("min_ms", "p50_ms", "p95_ms", "p99_ms", "max_ms"), quantiles):
                row[label] = f"{value:.6f}"
            rows.append(row)
    if len(rows) != 36:
        raise ValueError("Expected 36 paired experiment files")
    output.mkdir(parents=True, exist_ok=True)
    with (output / "malaga-rtt-by-experiment.csv").open("w", newline="") as sink:
        writer = csv.DictWriter(sink, rows[0].keys(), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


EXPECTED_SHA256 = "c95b18a646d1726ea1918e3eef6b3b83809420c7e1495c7e25e7df76b0e43f1a"
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    derive(args.bundle, args.output)
