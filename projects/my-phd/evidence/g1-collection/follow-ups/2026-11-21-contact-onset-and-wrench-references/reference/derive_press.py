"""python derive_press.py INPUT_DIR OUTPUT_DIR (NumPy). Uses only bench recordings."""
import argparse
import csv
import hashlib
from io import StringIO
from pathlib import Path
from zipfile import ZipFile

import numpy as np


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write(path, rows):
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=rows[0], lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def process(archive):
    rows = []
    for session, count in ((1, 21), (2, 15), (3, 6)):
        for trial in range(count):
            prefix = "Calibration Data/"
            sensor = archive.read(f"{prefix}1D-TAS606/Session{session}/Calibration1D_{trial}.txt")
            standard = archive.read(f"{prefix}3D-FT Sensors/Session{session}/Calibration3D_{trial}.txt")
            low = np.loadtxt(StringIO(sensor.decode()), delimiter=",")
            reference = list(csv.reader(StringIO(standard.decode()), delimiter=";"))
            header, data = reference[0], np.asarray(reference[1:], dtype=float)
            if not (all("(kg)" in field for field in header[:3]) and "Frequency = 10" in header
                    and low.shape==(50, 2) and data.shape==(50, 6)):
                raise ValueError(f"Unexpected channels or sampling configuration: {session}/{trial}")
            moment_unit = "N-m" if session <= 2 else "kg-cm"
            if not all(moment_unit in field for field in header[3:6]):
                raise ValueError("Reference unit mismatch")
            # Archive designates kg and kg-cm. Interpret these as gravitational units.
            forces = data[:, :3] * 9.80665
            moments = data[:, 3:] * (1.0 if moment_unit == "N-m" else 0.0980665)
            mean_force = forces.mean(axis=0)
            mean_moment = moments.mean(axis=0)
            rows.append(dict(session=session, run_index=trial, sensor_sha256=digest(sensor),
                             reference_sha256=digest(standard), one_axis_rows=len(low),
                             six_axis_rows=len(data), reference_serial=header[8].split("=")[-1].strip(),
                             source_moment_unit=moment_unit, logger_counter_first=low[0, 0], logger_counter_last=low[-1, 0],
                             raw_one_axis_mean=round(float(low[:, 1].mean()), 9),
                             ref_mean_Fx_N=round(float(mean_force[0]), 9),
                             ref_mean_Fy_N=round(float(mean_force[1]), 9),
                             ref_mean_minus_Fz_N=round(float(-mean_force[2]), 9),
                             ref_mean_Mx_Nm=round(float(mean_moment[0]), 9),
                             ref_mean_My_Nm=round(float(mean_moment[1]), 9),
                             ref_mean_Mz_Nm=round(float(mean_moment[2]), 9)))
    # A scalar-ONLY baseline. Mounting geometry and the paper's lever model are not fitted.
    fit = rows[:21]
    matrix = np.array([[r["raw_one_axis_mean"], 1.] for r in fit])
    weights = np.linalg.lstsq(matrix, [r["ref_mean_minus_Fz_N"] for r in fit], rcond=None)[0]
    groups = []
    for session in (1, 2, 3):
        block = [r for r in rows if r["session"] == session]
        raw = np.array([r["raw_one_axis_mean"] for r in block])
        observed = np.array([r["ref_mean_minus_Fz_N"] for r in block])
        error = weights[0]*raw+weights[1]-observed
        for r, value in zip(block, error):
            r["baseline_predicted_minus_reference_N"] = round(float(value), 9)
        maximum = 500 if session < 3 else 495
        groups.append(dict(session=session, role="fit" if session==1 else "test",
                           device="ATI Nano25" if session<3 else "ATI Delta",
                           paired_files=len(block), source_longitudinal_maximum_N=maximum,
                           reference_mean_min_N=round(float(observed.min()), 9),
                           reference_mean_max_N=round(float(observed.max()), 9),
                           trial_means_above_source_max=int(np.count_nonzero(observed > maximum)),
                           slope_N_per_native_unit=round(float(weights[0]), 9),
                           intercept_N=round(float(weights[1]), 9),
                           file_mean_baseline_rmse_N=round(float(np.sqrt(np.mean(error**2))), 9)))
    return rows, groups


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("inputs", "output"):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    source = args.inputs/"load.zip"
    if hashlib.md5(source.read_bytes()).hexdigest() != "a565dae06f77d95a6e01bca27db97515":
        raise ValueError("Different version of the press archive")
    with ZipFile(source) as z:
        rows, groups = process(z)
    args.output.mkdir(parents=True, exist_ok=True)
    write(args.output/"press-paired-loads.csv", rows)
    write(args.output/"press-sessions.csv", groups)


if __name__=="__main__":
    main()
