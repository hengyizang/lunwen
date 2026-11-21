"""Audit NNFM identification channels and compute tracking RMS using named fields.

SOURCE is the root of the fixed Git release or its three data directories arranged as in Git.
"""
import argparse
import csv
import hashlib
from pathlib import Path
import numpy as np
import pandas as pd


def f(v):
    return f"{v:.9f}"


def rms(x):
    return float(np.sqrt(np.mean(np.square(x))))


def write(path, rows):
    with path.open("w", newline="", encoding="utf-8") as out:
        writer = csv.DictWriter(out, fieldnames=rows[0], lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def file_and_frame(source, path):
    with path.open(encoding="utf-8-sig", newline="") as fh:
        names = next(csv.reader(fh))
    header_present = names[0] == "time"
    if header_present:
        frame = pd.read_csv(path, float_precision="round_trip")
    else:
        # Two fixed Franka files start immediately with 29 numerical values.
        if len(names) != 29 or not all(np.isfinite(float(n)) for n in names):
            raise ValueError(f"Unexpected header in {path}")
        names = ["time"] + [f"{k}{i}" for k in ("q","dq","ddq") for i in range(1,8)]
        names.extend(f"q{i}_tau_J_compensate" for i in range(1,8))
        frame = pd.read_csv(path, header=None, names=names, float_precision="round_trip")
    if not np.isfinite(frame.to_numpy()).all():
        raise ValueError(f"Nonfinite data in {path}")
    delta = frame.time.diff().dropna()
    row = dict(file=path.relative_to(source).as_posix(), sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
               original_header_present=int(header_present), rows=len(frame), first_time_native=f(frame.time.iloc[0]), last_time_native=f(frame.time.iloc[-1]),
               nonincreasing_time_steps=int((delta <= 0).sum()), median_time_step=f(delta.median()),
               maximum_time_step=f(delta.max()), zero_joint7_four_fields=int(
                   (frame[["q7", "dq7", "ddq7", "q7_tau_J_compensate"]] == 0).all(axis=1).sum()))
    return row, frame


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    files, recording_axes = [], []
    for path in sorted(args.source.glob("* Robot Dataset/*.csv")):
        row, data = file_and_frame(args.source, path)
        files.append(row)
        # FAIRINO holdings are a six-joint data product padded to seven channels.
        axes = range(1, 7 if path.parent.name.startswith("FAIRINO") else 8)
        for joint in axes:
            dq = data[f"dq{joint}"].to_numpy()
            residual = data[f"q{joint}_tau_J_compensate"].to_numpy()
            recording_axes.append(dict(file=row["file"], joint=joint, rows=len(data),
                                       negative_velocity=int((dq < 0).sum()), zero_velocity=int((dq == 0).sum()),
                                       positive_velocity=int((dq > 0).sum()),
                                       stored_torque_channel_min=f(residual.min()),
                                       stored_torque_channel_median=f(np.median(residual)),
                                       stored_torque_channel_max=f(residual.max())))
    controller = args.source / "Joint Compensation Experimental Data"
    runs = []
    for name in ["test_data_jointmotion.csv", "test_data_jointmotion_nnfm1.csv"]:
        row, data = file_and_frame(args.source, controller/name)
        files.append(row)
        ticks = np.rint(data.time * 1000).astype("int64")
        if not np.allclose(data.time * 1000, ticks, rtol=0., atol=1e-7) or ticks.duplicated().any():
            raise ValueError(f"Cannot match elapsed-millisecond indices in {name}")
        runs.append(data.set_index(ticks))
    base, model = runs
    shared = base.index.intersection(model.index, sort=True)
    if set(model.use_nnfm) != {1} or len(base) == len(model):
        raise ValueError("Compensation release or layout differs")
    trajectory = []
    for joint in range(1, 8):
        e, q, ref = f"tracking_error{joint}", f"q{joint}", f"q_d{joint}"
        base_same, model_same = base.loc[shared], model.loc[shared]
        nominal_difference = (base_same[ref] - model_same[ref]).abs()
        trajectory.append(dict(joint=joint, baseline_rows=len(base), compensation_rows=len(model),
                               common_elapsed_ms=len(shared), all_compensation_flags_one=int((model.use_nnfm == 1).sum()),
                               baseline_full_rms_tracking_rad=f(rms(base[e])),
                               compensation_full_rms_tracking_rad=f(rms(model[e])),
                               baseline_common_rms_tracking_rad=f(rms(base_same[e])),
                               compensation_common_rms_tracking_rad=f(rms(model_same[e])),
                               max_abs_reference_difference_common_rad=f(nominal_difference.max()),
                               max_abs_baseline_error_minus_qref_minus_q_rad=f((base[e] - (base[ref]-base[q])).abs().max()),
                               max_abs_compensation_error_minus_qref_minus_q_rad=f((model[e] - (model[ref]-model[q])).abs().max()),
                               model_predicted_torque_max_abs_Nm=f(model[f"tau_nnfm{joint}"].abs().max())))
    if len(files) != 25 or len(recording_axes) != 149:
        raise ValueError("Unexpected source coverage")
    args.output.mkdir(exist_ok=True, parents=True)
    write(args.output/"nnfm-traces.csv", files)
    write(args.output/"nnfm-joint-channels.csv", recording_axes)
    write(args.output/"nnfm-tracking-comparison.csv", trajectory)


if __name__ == "__main__":
    main()
