"""Compare two device velocity traces in Aiple's one-DOF teleoperator archive.

Pass the directory of extracted MAT files and a destination directory. Use all six
identification files and both DL/FF files from numeric subject IDs 1 through 4.
Requires NumPy and SciPy. Positive lag means unit 2 follows unit 1.
"""
import argparse
import csv
import hashlib
import re
from pathlib import Path

import numpy as np
from scipy.io import loadmat
from scipy.signal import correlate


def write_table(path, rows):
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0], lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def shifted_match(first, second, margin=100):
    # Every candidate lag compares the same central unit-1 samples. Center
    # and normalize the unit-2 samples for each shift to obtain Pearson r.
    reference = first[margin:-margin]
    centered = reference - reference.mean()
    width = len(reference)
    sums = np.r_[0, second.cumsum()]
    squares = np.r_[0, np.square(second).cumsum()]
    norm2 = squares[width:] - squares[:-width] - (sums[width:] - sums[:-width])**2 / width
    if reference.std() < 0.1 or np.sqrt(np.maximum(norm2, 0) / width).min() < 0.1:
        return None
    coefficients = correlate(second, centered, mode="valid", method="fft") / np.sqrt(norm2 * (centered @ centered))
    best = int(np.argmax(coefficients))
    return best - margin, float(coefficients[best]), float(coefficients[margin])


def summarize(files):
    records, windows = [], []
    for path in files:
        data = loadmat(path, squeeze_me=True, variable_names=[
            "time", "onedof_ntp_time", "onedof_ntp_sync", "unit1_velout",
            "unit2_velout", "delay_on", "force_on", "slave_on", "endstop_visibility",
            "hammer_visibility",
        ])
        time = data["time"]
        dt = np.diff(time)
        if not np.allclose(dt, 0.001, rtol=0, atol=1e-8):
            raise ValueError(f"Unexpected nominal acquisition grid: {path.name}")
        if any(not np.isfinite(arr).all() for name, arr in data.items() if not name.startswith("_")):
            raise ValueError(f"Nonfinite signal: {path.name}")
        device_time = np.diff(data["onedof_ntp_time"])
        eligible = []
        for start in range(0, len(time)-4999, 5000):
            section = slice(start, start+5000)
            result = shifted_match(data["unit1_velout"][section], data["unit2_velout"][section])
            if result:
                lag, peak, at_zero = result
                eligible.append((lag, peak))
            windows.append(dict(member=path.name, start_index=start, window_ms=5000,
                                eligible=int(result is not None),
                                best_lag_ms="" if result is None else lag,
                                peak_r="" if result is None else round(peak, 7),
                                zero_lag_r="" if result is None else round(at_zero, 7)))
        high = [lag for lag, peak in eligible if peak >= 0.8]
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream,"sha256").hexdigest()
        records.append(dict(member=path.name,source_sha256=digest,rows=len(time),
                            nominal_dt_ms=1,ntp_dt_p01_ms=round(np.quantile(device_time,.01)*1000,7),
                            ntp_dt_p99_ms=round(np.quantile(device_time,.99)*1000,7),
                            ntp_sync_nonzero=int(np.count_nonzero(data["onedof_ntp_sync"])),
                            delay_on_rows=int(np.count_nonzero(data["delay_on"])),
                            force_on_rows=int(np.count_nonzero(data["force_on"])),
                            slave_on_nonzero_rows=int(np.count_nonzero(data["slave_on"])),
                            both_optical_markers_visible_rows=int(np.count_nonzero(
                                (data["endstop_visibility"]==1) & (data["hammer_visibility"]==1))),
                            disjoint_complete_windows=len(time)//5000, eligible_windows=len(eligible),
                            eligible_r_ge_0p8=len(high),selected_at_search_edge=sum(abs(k)==100 for k in high),
                            median_lag_ms_r_ge_0p8="" if not high else float(np.median(high))))
    return records, windows


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source",type=Path)
    parser.add_argument("output",type=Path)
    args=parser.parse_args()
    files=sorted(p for p in args.source.glob("*.mat") if "-Identification-" in p.name or
                 re.fullmatch(r"OneDofHashtrudi-subject[1-4]-group[A-D]-(DL|FF)\.mat",p.name))
    if len(files)!=14:
        raise ValueError("Expected six identification and eight task files")
    args.output.mkdir(exist_ok=True,parents=True)
    records,windows=summarize(files)
    write_table(args.output/"bilateral-recordings.csv",records)
    write_table(args.output/"bilateral-motion-windows.csv",windows)


if __name__ == "__main__":
    main()
