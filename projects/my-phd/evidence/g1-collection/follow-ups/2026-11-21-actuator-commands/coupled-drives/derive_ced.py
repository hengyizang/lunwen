"""Recompute CED file-level summaries from the Uppsala University 2017 archive."""
import argparse
import csv
import hashlib
import io
from pathlib import Path
from zipfile import ZipFile

import numpy as np
from scipy.io import loadmat


ARCHIVE_SHA256 = "4379a002295891865ebbf9da15fd1ce253c4ba6586954db525ed6d63d8bb223e"


def read_recordings(archive, stem, pairs):
    mat = loadmat(io.BytesIO(archive.read(stem + ".MAT")))
    rows = csv.reader(io.StringIO(archive.read(stem + ".csv").decode("ascii")))
    names = next(rows)[:-1]  # CSV has an empty final field after its trailing comma.
    numeric_rows = [row for row in rows if row]
    if len(numeric_rows) != 500 or any(len(row) != len(names) + 1 or row[-1] for row in numeric_rows):
        raise ValueError(f"{stem} CSV schema or row count changed")
    csv_data = np.asarray([row[:-1] for row in numeric_rows], dtype=float)
    expected = {name for pair in pairs for name in pair}
    if set(names) != expected or len(names) != len(expected):
        raise ValueError(f"{stem} header differs from documented variables")
    data = {}
    for column, name in enumerate(names):
        if mat[name].shape != (500, 1):
            raise ValueError(f"Unexpected MAT shape for {name}")
        channel = mat[name][:, 0].astype(float)
        error = np.abs(csv_data[:, column] - channel)
        if not np.isfinite(error).all() or error.max() > 0.00005:
            raise ValueError(f"CSV/MAT values diverge for {name}")
        data[name] = (channel, error.max())
    return data


def summarize(archive):
    summaries = []
    inputs = {}
    for stem, pairs in (("DATAPRBS", (("u1", "z1"), ("u2", "z2"), ("u3", "z3"))),
                        ("DATAUNIF", (("u11", "z11"), ("u12", "z12")))):
        channels = read_recordings(archive, stem, pairs)
        for u_name, z_name in pairs:
            u, u_error = channels[u_name]
            z, z_error = channels[z_name]
            inputs[u_name] = u
            summaries.append({
                "archive_member_stem": stem, "input": u_name, "output": z_name,
                "samples": len(u), "sample_period_s": "0.02",
                "input_min_v": format(u.min(), ".12g"), "input_max_v": format(u.max(), ".12g"),
                "input_distinct_levels": len(np.unique(u)), "input_changes": int(np.count_nonzero(np.diff(u))),
                "samples_at_observed_input_min": int(np.sum(u == u.min())),
                "samples_at_observed_input_max": int(np.sum(u == u.max())),
                "output_min_native": format(z.min(), ".12g"), "output_max_native": format(z.max(), ".12g"),
                "negative_output_samples": int(np.sum(z < 0)),
                "max_abs_csv_mat_input_difference_v": format(u_error, ".9g"),
                "max_abs_csv_mat_output_difference_native": format(z_error, ".9g"),
            })
    for other in ("u2", "u3"):
        if not np.array_equal(np.sign(inputs["u1"]), np.sign(inputs[other])):
            raise ValueError("The three documented PRBS runs do not share a sign sequence")
    max_error = max(abs((inputs["u12"] - inputs["u11"]) - 0.5))
    if max_error >= 3e-16:
        raise ValueError(f"Uniform excitation offset differs: {max_error}")
    return summaries


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("output_csv", type=Path)
    args = parser.parse_args()
    if hashlib.sha256(args.archive.read_bytes()).hexdigest() != ARCHIVE_SHA256:
        raise ValueError("Archive differs from the reviewed release")
    with ZipFile(args.archive) as archive:
        if archive.testzip() is not None:
            raise ValueError("Archive member failed CRC")
        rows = summarize(archive)
    with args.output_csv.open("w", encoding="utf-8", newline="") as out:
        writer = csv.DictWriter(out, rows[0].keys(), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
