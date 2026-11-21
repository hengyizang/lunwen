"""python derive_fingertip.py INPUT_DIR OUTPUT_DIR (NumPy, SciPy, openpyxl)."""
import argparse
import csv
import hashlib
import io
from pathlib import Path
import re
from zipfile import ZipFile

import numpy as np
import openpyxl
from scipy.io import loadmat

AXES = ("Fx", "Fy", "Fz", "Mx", "My", "Mz")
SIGN = np.array([1, 1, -1, 1, 1, 1])
TOLERANCE = 0.00000501  # Five decimal places, in each native display unit.


def write(path, rows):
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=rows[0], lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def frozen_network(source, voltages):
    # Parse literal matrices only. Do not execute the downloaded MATLAB program.
    pattern = r"^(\w+(?:\.\w+)?) = \[([^\]]+)\];"
    w = {name: np.array([[float(t) for t in row.split()] for row in expr.split(";")])
         for name, expr in re.findall(pattern, source, flags=re.MULTILINE)}
    inputs = (voltages.T - w["x1_step1.xoffset"]) * w["x1_step1.gain"] - 1
    hidden1 = np.tanh(w["IW1_1"] @ inputs + w["b1"])
    hidden2 = np.tanh(w["LW2_1"] @ hidden1 + w["b2"])
    output = w["LW3_2"] @ hidden2 + w["b3"]
    return ((output + 1) / w["y1_step1.gain"] + w["y1_step1.xoffset"]).T


def summary(tag, targets, result):
    delta = result - targets
    rows = []
    for axis, (target, residual) in enumerate(zip(targets.T, delta.T)):
        rows.append(dict(group=tag, axis=AXES[axis], unit="N" if axis < 3 else "mN m",
                         samples=len(target), reference_min=round(float(target.min()), 9),
                         reference_max=round(float(target.max()), 9),
                         mean_output_minus_reference=round(float(residual.mean()), 9),
                         rmse=round(float(np.sqrt(np.mean(residual**2))), 9),
                         max_abs_error=round(float(np.max(np.abs(residual))), 9)))
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("inputs", "output"):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    archive = args.inputs / "fingertip.zip"
    if hashlib.md5(archive.read_bytes()).hexdigest() != "5a1f55365e34690f7ef63f9c8c56c2a3":
        raise ValueError("Zenodo archive differs from verified release")
    with ZipFile(archive) as z:
        data = loadmat(io.BytesIO(z.read(next(x for x in z.namelist() if x.endswith("/data.mat")))))["data"]
        model = z.read(next(x for x in z.namelist() if x.endswith("/six_force.m"))).decode()
    targets = data[:, 8:]
    predictions = frozen_network(model, data[:, :8])
    book = openpyxl.load_workbook(args.inputs / "figures.xlsx", read_only=True, data_only=True)
    series = [list(book[f"Figure 3{suffix}"].values) for suffix in "bcdefg"]
    if any(AXES[i] not in rows[0][0] for i, rows in enumerate(series)):
        raise ValueError("Unexpected worksheet header")
    fig = np.array([rows[1:] for rows in series], dtype=float).transpose(1, 0, 2)
    if data.shape != (418, 14) or fig.shape != (208, 6, 3):
        raise ValueError("Unexpected published matrix dimensions")
    if not np.allclose(fig[:, :, 1]-fig[:, :, 0], fig[:, :, 2], atol=1.01e-5, rtol=0):
        raise ValueError("Source Data errors inconsistent with plotted values")
    zero = (targets == 0).all(axis=1)
    raw_fig = targets * SIGN
    candidates = (np.abs(raw_fig[:, None, :] - fig[None, :, :, 0]) <= TOLERANCE).all(axis=2)
    unique = candidates.sum(axis=0) == 1
    raw_idx = np.argmax(candidates[:, unique], axis=0)
    if len(raw_idx) != len(set(raw_idx)):
        raise ValueError("Non-unique use of raw rows in distinct-target comparison")
    axes = summary("deposited model on full matrix, native sign", targets, predictions)
    axes += summary("deposited model on zero-target rows of full matrix", targets[zero], predictions[zero])
    axes += summary("article Fig. 3 displayed pairs, plot sign", fig[:, :, 0], fig[:, :, 1])
    axes += summary("model vs plotted output, uniquely matched targets only", fig[unique, :, 1], predictions[raw_idx] * SIGN)
    matches = []
    for j in range(len(fig)):
        ids = np.flatnonzero(candidates[:, j])
        matches.append(dict(worksheet_row=j+2, candidate_mat_rows=len(ids),
                            unique_mat_row_1_based=int(ids[0]+1) if len(ids)==1 else "",
                            all_six_plotted_targets_zero=int(np.all(fig[j, :, 0] == 0))))
    args.output.mkdir(parents=True, exist_ok=True)
    write(args.output/"fingertip-comparisons.csv", axes)
    write(args.output/"fingertip-target-matches.csv", matches)


if __name__ == "__main__":
    main()
