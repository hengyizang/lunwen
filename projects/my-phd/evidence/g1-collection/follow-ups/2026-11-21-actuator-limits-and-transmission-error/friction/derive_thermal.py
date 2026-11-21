"""Summarize the DaRUS-5015 original CSV files in their published directory layout."""
import argparse
import csv
import hashlib
from pathlib import Path
import numpy as np
import pandas as pd


def write(path, rows):
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def load(path):
    data = pd.read_csv(path, float_precision="round_trip")
    if list(data) != ["t", "T_L", "T_H", "T_E", "theta_dot", "tau_f"]:
        raise ValueError(f"Unexpected columns in {path}")
    if not np.isfinite(data).all().all() or (data.t.diff().dropna() <= 0).any():
        raise ValueError(f"Invalid measurements in {path}")
    return data


def f(value):
    return f"{value:.8f}"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    files, contrasts, overlaps = [], [], []
    for file in sorted(args.source.rglob("*.csv")):
        frame = load(file)
        rel = file.relative_to(args.source).as_posix()
        gap = frame.T_L - frame.T_H
        files.append(dict(source=rel, sha256=hashlib.sha256(file.read_bytes()).hexdigest(),
                          rows=len(frame), duration_s=f(frame.t.iloc[-1] - frame.t.iloc[0]),
                          median_dt_s=f(frame.t.diff().median()),
                          median_velocity_rad_s=f(frame.theta_dot.median()),
                          positive_velocity_rows=int((frame.theta_dot > 0).sum()),
                          negative_velocity_rows=int((frame.theta_dot < 0).sum()),
                          lubricant_min_C=f(frame.T_L.min()), lubricant_max_C=f(frame.T_L.max()),
                          housing_min_C=f(frame.T_H.min()), housing_max_C=f(frame.T_H.max()),
                          lubricant_minus_housing_min_K=f(gap.min()),
                          lubricant_minus_housing_max_K=f(gap.max())))
        if rel.startswith("identification/"):
            # File labels give unsigned speed; the 0.9425 rad/s identification run rotates backwards.
            nominal = float(file.stem.split("=")[1].replace("p", "."))
            direction = int(np.sign(frame.theta_dot.median()))
            stable = (frame.theta_dot * direction - nominal).abs() <= nominal * .02
            bands = []
            for lower in (22, 44):
                subset = frame.loc[stable & frame.T_L.ge(lower) & frame.T_L.lt(lower + 2)]
                if subset.empty:
                    raise ValueError(f"No matched observations in {file}")
                bands.append((len(subset), subset.theta_dot.median(), subset.tau_f.abs().median()))
            cold, hot = bands
            contrasts.append(dict(source=rel, nominal_speed_magnitude_rad_s=f(nominal),
                                  direction=direction, lower_band_rows=cold[0], upper_band_rows=hot[0],
                                  lower_band_median_velocity_rad_s=f(cold[1]),
                                  upper_band_median_velocity_rad_s=f(hot[1]),
                                  lower_band_median_abs_tau_f_Nm=f(cold[2]),
                                  upper_band_median_abs_tau_f_Nm=f(hot[2]),
                                  upper_minus_lower_median_abs_tau_f_Nm=f(hot[2] - cold[2])))
        elif rel.startswith("validation/long-term/"):
            first_speed = file.stem.split("_1=")[1].split("_theta")[0]
            short = args.source / "validation" / "heat-up" / f"theta_dot={first_speed}.csv"
            heat = load(short)
            prefix = frame.iloc[:len(heat)]
            identical = (prefix.to_numpy() == heat.to_numpy())
            overlaps.append(dict(long_file=rel, heat_file=short.relative_to(args.source).as_posix(),
                                 short_rows=len(heat), matched_prefix_all_six_columns=int(identical.all(axis=1).sum()),
                                 time_start_s=f(heat.t.iloc[0]), time_end_s=f(heat.t.iloc[-1]),
                                 all_values_identical=int(identical.all())))
    if (len(files), len(contrasts), len(overlaps)) != (13, 5, 2):
        raise ValueError("Unexpected release coverage")
    args.output.mkdir(exist_ok=True, parents=True)
    write(args.output / "thermal-traces.csv", files)
    write(args.output / "thermal-temperature-bands.csv", contrasts)
    write(args.output / "thermal-validation-overlap.csv", overlaps)


if __name__ == "__main__":
    main()
