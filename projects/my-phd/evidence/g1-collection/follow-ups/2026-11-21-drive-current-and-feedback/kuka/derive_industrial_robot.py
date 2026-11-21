"""Summarize the two extracted archives for DOI 10.26204/data/5.

Usage: python derive_industrial_robot.py WITH_RAW_DIR WITHOUT_RAW_DIR OUTPUT_DIR
Dependencies: NumPy and SciPy. Extract the two RAR archives into separate directories.
"""
import argparse
import csv
import hashlib
from pathlib import Path

import numpy as np
from scipy.io import loadmat


def sha256(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def write_table(path, rows):
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, rows[0].keys(), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def rms(values):
    return round(float(np.sqrt(np.mean(np.square(values)))), 9)


def summarize_recording(path, role):
    data = loadmat(path, squeeze_me=True)
    time = data["time"]
    n = len(time)
    step = np.diff(time)
    if not (data["recording_ok"] == 1 and np.allclose(step, 0.004, atol=1e-9, rtol=0)):
        raise ValueError(f"Invalid recording time base or status: {path}")
    fields = ("q_ref", "q_se_meas", "q_mot_meas", "tau_ref_ff", "tau_fb_meas", "tau_meas")
    if any(data[k].shape != (6, n) or not np.isfinite(data[k]).all() for k in fields):
        raise ValueError(f"Invalid axis channels: {path}")
    record = dict(file=path.name, sha256=sha256(path), split=role, samples=n,
                  first_s=float(time[0]), last_s=float(time[-1]), nominal_ms=4)
    axes = []
    for i in range(6):
        main_axis = i < 3
        secondary = data["q_se_meas"][i]
        resolver = data["q_mot_meas"][i]
        feedback = data["tau_fb_meas"][i]
        feedforward = data["tau_ref_ff"][i]
        measured = data["tau_meas"][i]
        pos = secondary if main_axis else resolver
        difference = measured - (feedforward + feedback)
        axes.append(dict(file=path.name, joint=i+1, samples=n, position_channel="secondary encoder" if main_axis else "motor resolver",
                         secondary_all_zero=int(np.all(secondary == 0)),
                         position_reference_rms_error_deg=rms(data["q_ref"][i] - pos),
                         resolver_minus_secondary_rms_deg=rms(resolver - secondary) if main_axis else "",
                         feedforward_rms_Nm=rms(feedforward), feedback_rms_Nm=rms(feedback),
                         current_derived_motor_torque_rms_Nm=rms(measured),
                         measured_minus_FF_plus_FB_rms_Nm=rms(difference),
                         abs_same_row_difference_over_0p01_Nm=int(np.count_nonzero(np.abs(difference) > 0.01))))
    return record, axes


def summarize_prepared(raw, prepared, recordings):
    datasets = {}
    for task in ("forward", "inverse"):
        name = f"{task}_identification_without_raw_data.mat"
        if sha256(raw / name) != sha256(prepared / name):
            raise ValueError(f"Prepared file differs between releases: {name}")
        datasets[task] = loadmat(prepared / name, squeeze_me=True)
    forward, inverse = datasets["forward"], datasets["inverse"]
    result = []
    for split in ("train", "test"):
        time = forward[f"time_{split}"]
        torque = forward[f"u_{split}"]
        if not (np.array_equal(time, inverse[f"time_{split}"])
                and np.array_equal(torque, inverse[f"y_{split}"])):
            raise ValueError("Prepared forward and inverse files do not share the same time/torque array")
        selected = [r for r in recordings if r["split"] == split]
        raw_n = sum(r["samples"] for r in selected)
        if len(time) != len(range(0, raw_n, 25)):
            raise ValueError("Subsampling differs from the publisher processing script")
        result.append(dict(split=split, raw_recording_files=len(selected), raw_samples=raw_n,
                           prepared_samples=len(time), forward_inputs=torque.shape[0],
                           inverse_inputs=inverse[f"u_{split}"].shape[0],
                           forward_input_equals_inverse_target=int(np.array_equal(torque, inverse[f"y_{split}"])),
                           first_time_s=float(time[0]), last_time_s=float(time[-1]),
                           nominal_ms=100, archived_mean_step_ms=round(1000*np.diff(time).mean(), 9)))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("with_raw_dir", "without_raw_dir", "output_dir"):
        parser.add_argument(arg, type=Path)
    args = parser.parse_args()
    files = sorted((args.with_raw_dir / "raw_data").glob("*.mat"))
    if len(files) != 12:
        raise ValueError("Expected twelve original acquisition files")
    recordings, axes = [], []
    for path in files:
        recording, summaries = summarize_recording(path, "test" if path == files[-1] else "train")
        recordings.append(recording)
        axes.extend(summaries)
    prepared = summarize_prepared(args.with_raw_dir, args.without_raw_dir, recordings)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, rows in (("recordings", recordings), ("joint-channels", axes), ("prepared-splits", prepared)):
        write_table(args.output_dir / f"kuka-{name}.csv", rows)


if __name__ == "__main__":
    main()
