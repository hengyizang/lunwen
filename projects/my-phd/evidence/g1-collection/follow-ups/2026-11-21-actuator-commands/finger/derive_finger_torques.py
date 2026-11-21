"""Reproduce the G1 torque summaries from the three pinned Edmond v1.0 files."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np


SIGNALS = {"measured_angles", "measured_velocities", "measured_torques",
           "constrained_torques", "desired_torques"}
TOLERANCE = 1e-9  # N m
BOUND = 0.36  # magnitude seen in the archived constrained command, N m
PREFIX = 1000  # author extraction rule before public training/validation/test splits


def verify_source(path, entry):
    if path.stat().st_size != entry["bytes"]:
        raise ValueError(f"Unexpected byte count: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    if digest.hexdigest() != entry["sha256"]:
        raise ValueError(f"SHA-256 mismatch: {path}")


def write_table(path, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0], lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def summarize(file, mode, validation, rollout_rows, group_rows):
    expected_index = np.broadcast_to(np.arange(15000), (200, 15000))
    with np.load(file, allow_pickle=False) as source:
        if set(source.files) != SIGNALS | {"index"} or not np.array_equal(source["index"], expected_index):
            raise ValueError(f"Unexpected keys or index: {file.name}")
        signals = {}
        for key in sorted(SIGNALS):
            data = source[key]
            if data.shape != (200, 15000, 3) or not np.isfinite(data).all():
                raise ValueError(f"Invalid shape or nonfinite {key}: {file.name}")
            if mode == "Sines" and not np.array_equal(data[9:12, PREFIX:], validation[key]):
                raise ValueError(f"Validation split differs in {key}")
            if key.endswith("_torques"):
                signals[key] = data[:, PREFIX:]
    desired = signals["desired_torques"]
    command = signals["constrained_torques"]
    measured = signals["measured_torques"]
    changed = np.abs(desired - command) > TOLERANCE
    clipped = np.clip(desired, -BOUND, BOUND)
    scalar_match = changed & (np.abs(desired) > BOUND) & (np.abs(command - clipped) <= TOLERANCE)

    for group in range(4):
        rows = slice(group * 50, (group + 1) * 50)
        sub = changed[rows]
        group_rows.append({
            "controller": mode, "file_block_1based": group + 1, "rollouts": len(sub),
            "index_positions": int(sub.shape[0] * sub.shape[1]), "joint_samples": sub.size,
            "rollouts_with_any_change": int(np.any(sub, axis=(1, 2)).sum()),
            "positions_with_any_joint_changed": int(sub.any(axis=2).sum()),
            "joint_samples_changed": int(sub.sum()),
            "changed_matching_scalar_clip": int(scalar_match[rows].sum()),
            "other_changed_joint_samples": int(sub.sum() - scalar_match[rows].sum()),
        })
    for run in range(len(desired)):
        for joint in range(3):
            d, c, m = (x[run, :, joint] for x in (desired, command, measured))
            n_changed = int(changed[run, :, joint].sum())
            n_clip = int(scalar_match[run, :, joint].sum())
            rollout_rows.append({
                "controller": mode, "file_block_1based": run // 50 + 1,
                "file_rollout_1based": run + 1, "joint_1based": joint + 1, "index_positions": len(d),
                "command_changed": n_changed, "changed_matching_scalar_clip": n_clip,
                "other_changed": n_changed - n_clip,
                "desired_abs_max_Nm": f"{np.max(np.abs(d)):.9f}",
                "constrained_abs_max_Nm": f"{np.max(np.abs(c)):.9f}",
                "measured_abs_max_Nm": f"{np.max(np.abs(m)):.9f}",
                "mean_abs_desired_minus_constrained_Nm": f"{np.mean(np.abs(d - c)):.9f}",
                "mean_abs_constrained_minus_measured_same_index_Nm": f"{np.mean(np.abs(c - m)):.9f}",
            })


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sources", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    manifest = json.loads(Path(__file__).with_name("finger-torque-source.json").read_text(encoding="utf-8"))
    for entry in manifest["files"]:
        verify_source(args.sources / entry["file"], entry)
    rollout_rows, group_rows = [], []
    with np.load(args.sources / "Sines_validation.npz", allow_pickle=False) as validation:
        if set(validation.files) != SIGNALS:
            raise ValueError("Unexpected validation archive fields")
        for mode in ("Sines", "GPs"):
            summarize(args.sources / f"{mode}_full.npz", mode, validation, rollout_rows, group_rows)
    args.destination.mkdir(exist_ok=True, parents=True)
    write_table(args.destination / "finger-torque-rollouts.csv", rollout_rows)
    write_table(args.destination / "finger-torque-groups.csv", group_rows)


if __name__ == "__main__":
    main()
