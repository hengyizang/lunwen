"""Verify and summarize the JSI copper ring archives (NumPy, SciPy 1.5+)."""
import argparse
import csv
import hashlib
import json
from collections import defaultdict
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import numpy as np
from scipy.io import loadmat


MATRICES = {"ft": ("ATIFT", 6), "ft_tool": ("ATIFTS", 6),
            "x": ("x", 7), "x_ref": ("x_ref", 7)}


def image_index(archive):
    paths = [p for p in archive.namelist() if p.endswith(".jpg")]
    index = {Path(p).stem.removeprefix("rs_front_"): Path(p) for p in paths}
    if len(index) != len(paths):
        raise ValueError("Duplicate image key in one release")
    return index


def verify_matrix(values, csv_values):
    if values.shape != csv_values.shape or not np.isfinite(values).all() or not np.isfinite(csv_values).all():
        raise ValueError("Invalid shape or nonfinite values")
    # Half one unit in the fifth significant digit; MAT is higher precision.
    scale = np.maximum(np.abs(values), 1e-300)
    quantum = np.power(10.0, np.floor(np.log10(scale)) - 4)
    delta = np.abs(values - csv_values)
    if np.any(delta > 0.5000002 * quantum):
        raise ValueError("CSV differs beyond five-significant-digit rounding")


def summarize_attempt(early, late, key, source_image, target_image):
    source_dir, target_dir = source_image.parent, target_image.parent
    slot = source_dir.parent.name
    if slot != target_dir.parent.name:
        raise ValueError(f"Slot mismatch: {key}")
    image = early.read(str(source_image))
    if image != late.read(str(target_image)):
        raise ValueError(f"Outcome images differ: {key}")
    states = loadmat(BytesIO(late.read(str(target_dir / f"panda_{key}.mat"))),
                     simplify_cells=True)["states"]
    t = np.atleast_1d(states["t"])
    if t.ndim != 1 or len(t) < 2 or not np.isfinite(t).all():
        raise ValueError(f"Invalid timestamps: {key}")
    for csv_field, (mat_field, width) in MATRICES.items():
        values = states[mat_field]
        if values.shape != (len(t), width):
            raise ValueError(f"Unexpected shape: {key}/{mat_field}")
        raw = early.read(str(source_dir / f"{csv_field}_{key}.csv"))
        verify_matrix(values, np.loadtxt(BytesIO(raw), delimiter=",", ndmin=2))
    steps = np.diff(t)
    wrench = states["ATIFT"]
    return {
        "source_attempt_key": key, "slot": slot,
        "early_folder": source_dir.name, "late_folder": target_dir.name,
        "image_sha256_in_both_releases": hashlib.sha256(image).hexdigest(),
        "sample_rows": len(t), "time_span_s": format(t[-1] - t[0], ".9g"),
        "adjacent_equal_t": int(np.count_nonzero(steps == 0)),
        "adjacent_decreasing_t": int(np.count_nonzero(steps < 0)),
        "max_adjacent_t_step_s": format(np.max(steps), ".9g"),
        "peak_raw_force_norm_N": format(np.linalg.norm(wrench[:, :3], axis=1).max(), ".9g"),
        "peak_raw_torque_norm_Nm": format(np.linalg.norm(wrench[:, 3:], axis=1).max(), ".9g"),
    }


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0], lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive_folder", type=Path)
    parser.add_argument("output_folder", type=Path)
    args = parser.parse_args()
    manifest = json.loads(Path(__file__).with_name("rings-source.json").read_text())
    paths = []
    for entry in manifest["releases"]:
        path = args.archive_folder / entry["filename"]
        if path.stat().st_size != entry["bytes"] or hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
            raise ValueError(f"Source archive differs: {path}")
        paths.append(path)
    with ZipFile(paths[0]) as early, ZipFile(paths[1]) as late:
        if early.testzip() is not None or late.testzip() is not None:
            raise ValueError("Invalid ZIP CRC")
        a, b = image_index(early), image_index(late)
        if a.keys() != b.keys():
            raise ValueError("Source attempts do not match")
        rows = [summarize_attempt(early, late, key, a[key], b[key]) for key in sorted(a)]
    groups = defaultdict(list)
    for row in rows:
        groups[row["slot"], row["early_folder"], row["late_folder"]].append(row)
    grouped = [{"slot": slot, "early_folder": old, "late_folder": new,
                "matched_attempts": len(group), "sample_rows": sum(r["sample_rows"] for r in group)}
               for (slot, old, new), group in sorted(groups.items())]
    args.output_folder.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_folder / "ring-attempts.csv", rows)
    write_csv(args.output_folder / "ring-label-crosswalk.csv", grouped)


if __name__ == "__main__":
    main()
