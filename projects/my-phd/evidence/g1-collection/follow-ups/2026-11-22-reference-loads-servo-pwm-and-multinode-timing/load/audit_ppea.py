"""Summarize the eight De Smedt et al. raw CSV traces. Requires NumPy.

Run: python audit_ppea.py path/to/raw.zip --out results_dir
The optional ZIP path avoids a second 60.65 MB download.
"""
import argparse
import csv
import hashlib
import pathlib
import tempfile
import urllib.request
import zipfile

import numpy as np

URL = "https://zenodo.org/api/records/23769731/files/1%20Raw%20data.zip/content"
SOURCE_MD5 = "f6c9fb2819271854101c1c58088a4107"
CHANNELS = (
    (2, "input_torque_sensor", 10 / 16384, "Nm"),
    (3, "output_torque_sensor", -10 / 16384, "Nm"),
    (4, "spring_torque_sensor", 1, "native_units"),
    (5, "input_motor_torque", 2.8033 / 1000, "Nm"),
    (6, "output_motor_torque", -2.8033 / 1000, "Nm"),
    (9, "undocumented_col10", 1, "native_units"),
    (10, "undocumented_col11", 1, "native_units"),
)


def write_table(path, rows):
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def inspect(archive, out):
    with archive.open("rb") as f:
        if hashlib.file_digest(f, "md5").hexdigest() != SOURCE_MD5:
            raise ValueError("Zenodo raw ZIP MD5 mismatch")
    summary, channels = [], []
    with zipfile.ZipFile(archive) as z:
        members = sorted(i for i in z.namelist() if i.endswith(".csv"))
        assert len(members) == 8
        for member in members:
            with z.open(member) as f:
                header = f.readline().decode("ascii").strip().split(",")
                assert header == [f"Var1_{n}" for n in range(1, 12)]
                values = np.loadtxt(f, delimiter=",", ndmin=2)
            assert values.shape[1] == 11
            complete = np.isfinite(values).all(axis=1)
            time = values[:, 0]
            dt = np.diff(time)
            assert np.isfinite(time).all() and (dt > 0).all()
            trace = pathlib.PurePosixPath(member).stem
            summary.append(dict(
                trace=trace, rows=len(time), complete_rows_all_11=int(complete.sum()),
                start_s=f"{time[0]:.6f}", end_s=f"{time[-1]:.6f}",
                min_dt_s=f"{dt.min():.8f}", median_dt_s=f"{np.median(dt):.8f}",
                max_dt_s=f"{dt.max():.8f}", archive_member=member,
                crc32=f"{z.getinfo(member).CRC:08x}",
            ))
            for col, name, scale, unit in CHANNELS:
                v = values[:, col]
                finite = v[np.isfinite(v)]
                p05, p95 = np.quantile(finite * scale, [.05, .95])
                channels.append(dict(
                    trace=trace, csv_column=header[col], channel=name,
                    finite=len(finite), raw_min=f"{finite.min():.9g}",
                    raw_max=f"{finite.max():.9g}", span_unit=unit,
                    p95_minus_p05_span=f"{p95-p05:.9g}",
                ))
    out.mkdir(parents=True, exist_ok=True)
    write_table(out / "ppea_traces.csv", summary)
    write_table(out / "ppea_channels.csv", channels)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("zip_path", type=pathlib.Path, nargs="?")
    parser.add_argument("--out", type=pathlib.Path, default=pathlib.Path("."))
    args = parser.parse_args()
    if args.zip_path:
        inspect(args.zip_path, args.out)
    else:
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "raw.zip"
            urllib.request.urlretrieve(URL, path)
            inspect(path, args.out)
