"""Derive EMPS summaries using the public ZIP and the authors' release conventions."""

import argparse
import csv
import hashlib
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import numpy as np
from scipy.io import loadmat
from scipy.signal import butter, decimate, sosfiltfilt

ZIP_SHA256 = "f0e575c2aba2cb1e236516eefb17674b7e1e4a28de6bfcdc5b5ad68193ef9f59"
FILES = {"estimation": "DATA_EMPS.mat", "pulse_validation": "DATA_EMPS_PULSES.mat"}
DT = 0.001


def rms(values):
    return np.sqrt(np.mean(values**2))


def write_table(directory, name, rows):
    with (directory / name).open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0], lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: format(v, ".10g") if isinstance(v, (float, np.floating)) else v
                             for k, v in row.items()})


def from_archive(archive, member):
    raw = archive.read(member)
    fields = {k: np.asarray(v, dtype=float).ravel() for k, v in loadmat(BytesIO(raw)).items()
              if not k.startswith("_")}
    n = len(fields["t"])
    for key, values in fields.items():
        expected = 1 if key in ("kv", "kp", "gtau") else n
        if len(values) != expected or not np.isfinite(values).all():
            raise ValueError(f"Unexpected shape or nonfinite sample: {member} {key}")
    if not np.all(np.diff(fields["t"]) > 0):
        raise ValueError(f"Nonmonotonic clock: {member}")
    return fields, hashlib.sha256(raw).hexdigest()


def pulse_windows(d, member):
    pulse = d["pulses_N"]
    if set(pulse) != {0, 5}:
        raise ValueError("Unexpected pulse levels in release")
    edges = np.diff(np.r_[False, pulse != 0, False].astype(int))
    windows = []
    for i, (start, stop) in enumerate(zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)), 1):
        windows.append({
            "member": member, "window": i, "first_zero_based_row": start, "last_zero_based_row": stop-1,
            "first_recorded_s": d["t"][start], "last_recorded_s": d["t"][stop-1],
            "rows": stop-start, "pulse_as_stored": pulse[start],
            "falling_edge_observed": int(stop < len(pulse)),
            "vir_min_as_stored": np.min(d["vir"][start:stop]), "vir_max_as_stored": np.max(d["vir"][start:stop]),
        })
    return windows


def control_residuals(d, member):
    # The average of two consecutive positions is differenced in the reported PD law.
    q = d["qm"]
    velocity = (q[2:] - q[:-2]) / (2 * DT)
    pd_output = d["kv"].item() * (d["kp"].item() * (d["qg"][2:] - q[2:]) - velocity)
    residual = d["vir"][2:] - pd_output
    if "pulses_N" in d:
        groups = [(str(int(p)), d["pulses_N"][2:] == p) for p in np.unique(d["pulses_N"])]
    else:
        groups = [("channel_absent", np.ones(len(residual), dtype=bool))]
    return [{
        "member": member, "pulse_as_stored": label, "comparable_rows": np.sum(mask),
        "median_vir_minus_PD": np.median(residual[mask]), "rmse_vir_minus_PD": rms(residual[mask]),
        "rmse_tracking_error_mm": 1000*rms((d["qg"][2:] - q[2:])[mask]),
    } for label, mask in groups]


def inverse_data(d, law):
    # Offline inverse-dynamics regressors follow the report's 100 Hz position filter
    # and numerical differentiation. Decimator endpoints can differ across libraries.
    sos = butter(4, 100, fs=1000, output="sos")
    q = sosfiltfilt(sos, d["qm"])
    v = np.gradient(q, DT)
    acc = np.gradient(v, DT)
    direction = np.sign(v)
    if law == "symmetric_with_offset":
        x = np.column_stack((acc, v, direction, np.ones_like(v)))
    else:
        pos = (1+direction)/2
        neg = (1-direction)/2
        x = np.column_stack((acc, v*pos, direction*pos, v*neg, direction*neg))
    force_proxy = d["gtau"].item()*d["vir"]
    # MATLAB n_border:N with n_border=50 starts at Python row 49.
    return decimate(x[49:], 10, axis=0), decimate(force_proxy[49:], 10)


def evaluate(datasets):
    results = []
    for law in ("symmetric_with_offset", "directional_no_offset"):
        train_x, train_y = inverse_data(datasets["estimation"], law)
        beta, _, rank, _ = np.linalg.lstsq(train_x, train_y, rcond=None)
        if rank != len(beta):
            raise ValueError(f"Rank-deficient estimation matrix: {law}")
        for role, d in datasets.items():
            x, y = inverse_data(d, law)
            error = y - x @ beta
            symmetric = law == "symmetric_with_offset"
            results.append({
                "fit_member": FILES["estimation"], "evaluated_member": FILES[role], "model": law,
                "decimated_rows": len(y), "fit_rank": rank, "condition_number_unscaled_X_eval": np.linalg.cond(x),
                "mass_kg": beta[0], "viscous_positive_Ns_per_m": beta[1], "coulomb_positive_N": beta[2],
                "viscous_negative_Ns_per_m": beta[1] if symmetric else beta[3],
                "coulomb_negative_N": beta[2] if symmetric else beta[4],
                "offset_N": beta[3] if symmetric else "",
                "drive_gain_force_proxy_rmse_N": rms(error),
                "relative_l2_force_proxy_error_pct": 100*np.linalg.norm(error)/np.linalg.norm(y),
            })
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("zip_file", type=Path)
    parser.add_argument("outdir", type=Path)
    args = parser.parse_args()
    if hashlib.sha256(args.zip_file.read_bytes()).hexdigest() != ZIP_SHA256:
        raise ValueError("Archive SHA-256 differs from verified release")
    args.outdir.mkdir(parents=True, exist_ok=True)
    summary, conditions, windows = [], [], []
    datasets = {}
    with ZipFile(args.zip_file) as archive:
        for role, member in FILES.items():
            d, digest = from_archive(archive, member)
            datasets[role] = d
            t, u, q = d["t"], d["vir"], d["qm"]
            clock_us = 1e6*np.diff(t)
            summary.append({
                "role": role, "member": member, "sha256": digest, "rows": len(t),
                "elapsed_s": t[-1]-t[0], "min_step_us": np.min(clock_us), "max_step_us": np.max(clock_us),
                "min_vir_as_stored": np.min(u), "max_vir_as_stored": np.max(u),
                "abs_vir_ge_10_as_stored": np.sum(np.abs(u) >= 10),
                "drive_gain_N_per_V": d["gtau"].item(),
                "min_gtau_times_vir_N_proxy": d["gtau"].item()*np.min(u),
                "max_gtau_times_vir_N_proxy": d["gtau"].item()*np.max(u),
                "overall_position_tracking_rmse_mm": 1000*rms(q - d["qg"]),
                "max_abs_ref_difference_vs_estimation_m": np.max(np.abs(d["qg"]-datasets["estimation"]["qg"])),
            })
            conditions.extend(control_residuals(d, member))
            if "pulses_N" in d:
                windows.extend(pulse_windows(d, member))
    write_table(args.outdir, "emps-experiments.csv", summary)
    write_table(args.outdir, "emps-pd-residuals.csv", conditions)
    write_table(args.outdir, "emps-pulse-windows.csv", windows)
    write_table(args.outdir, "emps-inverse-models.csv", evaluate(datasets))


if __name__ == "__main__":
    main()
