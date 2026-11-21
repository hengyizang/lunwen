"""Summarize all 8 iRonCub-Mk3 arm calibration files at the pinned HF revision.

Usage: python derive_ironcub_temperature.py INPUT_REPO_DIRECTORY OUTPUT_DIRECTORY
Requires NumPy and SciPy. The input manifest is embedded in ironcub-source.json.
"""
import argparse
import csv
import hashlib
import json
import re
from pathlib import Path

import numpy as np
from scipy.io import loadmat
from scipy.spatial.distance import cdist


AXES = ("Fx", "Fy", "Fz", "Mx", "My", "Mz")
JOINTS = ("torso_pitch", "torso_roll", "torso_yaw")
ARM_JOINTS = ("shoulder_pitch", "shoulder_roll", "shoulder_yaw", "elbow")


def table(path, rows):
    with path.open("w", encoding="utf-8", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=rows[0], lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def rounded(value):
    return round(float(value), 7)


def load_sources(source, hashes):
    series = []
    for path in sorted(source.glob("*/*/dataset.mat")):
        key = path.relative_to(source).as_posix()
        with path.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != hashes[key]:
                raise ValueError(f"Unexpected file version: {key}")
        data = loadmat(path, squeeze_me=True, struct_as_record=False)["robot_logger_device"]
        positions = data.joints_state.positions
        masses = re.fullmatch(r"l(\d+)kg-r(\d+)kg", path.parent.name).groups()
        for side, mass in zip(("l", "r"), masses):
            name = f"{side}_arm_ft_sensor"
            wrench = getattr(data.FTs, name)
            temperature = getattr(data.temperatures, name)
            expected = getattr(data.expectedValues.FTs, name)
            time = wrench.timestamps - wrench.timestamps[0]
            if (not np.array_equal(wrench.timestamps, temperature.timestamps)
                    or not np.array_equal(time, expected.time)
                    or not np.array_equal(wrench.timestamps, positions.timestamps)
                    or not np.all(np.diff(time) > 0)):
                raise ValueError(f"Unaligned streams: {key} {side}")
            if (wrench.data.T.shape != expected.data.shape or expected.data.shape != (len(time), 6)
                    or not np.isfinite(wrench.data).all() or not np.isfinite(temperature.data).all()
                    or not np.isfinite(expected.data).all()):
                raise ValueError(f"Invalid values: {key} {side}")
            joints = (*JOINTS, *(f"{side}_{joint}" for joint in ARM_JOINTS))
            columns = [list(positions.elements_names).index(j) for j in joints]
            series.append(dict(source=key, split=path.parents[1].name, loads=path.parent.name,
                               arm=side, attached_mass_kg=int(mass), time=time, wrench=wrench.data.T,
                               temperature=temperature.data, expected=expected.data,
                               posture=positions.data[columns].T))
    if len(series) != 16:
        raise ValueError("Expected both upper arms in all eight measurements")
    return series


def assess_arms(series):
    sessions, validation = [], []
    for side in ("l", "r"):
        arm = [s for s in series if s["arm"] == side]
        training = [s for s in arm if s["split"] == "training"]
        ranges = [(s["temperature"].min(), s["temperature"].max()) for s in training]
        span_min = min(a for a, _ in ranges)
        span_max = max(b for _, b in ranges)
        for s in arm:
            t = s["temperature"]
            covered = np.logical_or.reduce([(a <= t) & (t <= b) for a, b in ranges])
            sessions.append(dict(file=s["source"], arm=side, mass_kg=s["attached_mass_kg"],
                                 rows=len(t), elapsed_s=rounded(s["time"][-1]),
                                 median_logger_step_ms=rounded(1000*np.median(np.diff(s["time"]))),
                                 temp_min_C=rounded(t.min()), temp_max_C=rounded(t.max()),
                                 temp_unique_values=len(np.unique(t)),
                                 logger_rows_outside_pooled_training_temperature_extent=int(((t < span_min) | (t > span_max)).sum()),
                                 logger_rows_outside_union_of_training_session_ranges=int((~covered).sum())))
        # Fit identical affine maps with and without the internal temperature regressor.
        x = np.vstack([s["wrench"] for s in training])
        y = np.vstack([s["expected"] for s in training])
        all_t = np.concatenate([s["temperature"] for s in training])
        train_mean_T = np.mean(all_t)
        for with_temperature in (False, True):
            X = np.column_stack((np.ones(len(x)), x))
            if with_temperature:
                X = np.column_stack((X, all_t - train_mean_T))
            coefficients, _, rank, _ = np.linalg.lstsq(X, y, rcond=None)
            if rank != X.shape[1]:
                raise ValueError("Rank-deficient regressor matrix")
            for s in arm:
                if s["split"] != "validation":
                    continue
                test = np.column_stack((np.ones(len(s["wrench"])), s["wrench"]))
                if with_temperature:
                    test = np.column_stack((test, s["temperature"] - train_mean_T))
                error = test @ coefficients - s["expected"]
                for j, axis in enumerate(AXES):
                    validation.append(dict(arm=side, file=s["source"], axis=axis,
                        unit="N" if j < 3 else "Nm", include_temperature=int(with_temperature),
                        training_rows=len(y), validation_rows=len(error), design_rank=int(rank),
                        fit_temp_center_C=rounded(train_mean_T) if with_temperature else "",
                        fitted_conditional_temp_coefficient_per_C=rounded(coefficients[-1,j]) if with_temperature else "",
                        heldout_mean_signed_error=rounded(error[:,j].mean()),
                        heldout_rmse=rounded(np.sqrt(np.mean(error[:,j]**2)))))
    return sessions, validation


def match_postures(series):
    rows = []
    for side in ("l", "r"):
        same_condition = [s for s in series if s["arm"] == side and s["loads"] == "l0kg-r7kg"]
        a, b = sorted(same_condition, key=lambda s:s["split"])
        # At most one recorded sample for each whole second of each file.
        ia, ib = [np.searchsorted(s["time"], np.arange(int(s["time"][-1]) + 1)) for s in (a, b)]
        pose_a = np.rad2deg(a["posture"][ia])
        pose_b = np.rad2deg(b["posture"][ib])
        # Ties occur when an arm holds still. Select the earliest equal-distance row.
        distances = cdist(pose_b, pose_a, metric="euclidean")
        nearest_a = distances.argmin(axis=1)
        nearest_b = distances.argmin(axis=0)
        distance = distances[np.arange(len(ib)), nearest_a]
        mutual = nearest_b[nearest_a] == np.arange(len(ib))
        for tolerance in (0.5, 1.0, 2.0):
            keep = mutual & (distance <= tolerance)
            if not keep.any():
                raise ValueError("No mutual-nearest pose pairs")
            i, j = ia[nearest_a[keep]], ib[keep]
            delta_t = b["temperature"][j] - a["temperature"][i]
            measured = b["wrench"][j] - a["wrench"][i]
            modeled = b["expected"][j] - a["expected"][i]
            for k, axis in enumerate(AXES):
                rows.append(dict(arm=side, axis=axis, unit="N" if k < 3 else "Nm",
                    train_file=a["source"], validation_file=b["source"], joint_distance_limit_deg=tolerance,
                    sampled_train_postures=len(ia), sampled_validation_postures=len(ib),
                    mutual_pairs=len(i), median_pose_distance_deg=rounded(np.median(distance[keep])),
                    median_temperature_difference_C=rounded(np.median(delta_t)),
                    median_measured_difference=rounded(np.median(measured[:,k])),
                    median_expected_difference=rounded(np.median(modeled[:,k])),
                    median_difference_after_expected_change=rounded(np.median(measured[:,k]-modeled[:,k]))))
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    manifest = json.loads(Path(__file__).with_name("ironcub-source.json").read_text())
    series = load_sources(args.source, manifest["raw_file_sha256"])
    sessions, validation = assess_arms(series)
    args.output.mkdir(parents=True, exist_ok=True)
    table(args.output/"ironcub-arm-sessions.csv", sessions)
    table(args.output/"ironcub-heldout-affine.csv", validation)
    table(args.output/"ironcub-matched-postures.csv", match_postures(series))


if __name__ == "__main__":
    main()
