"""Recompute the descriptive calibration audit from the immutable source release.

Python 3.9+ with NumPy and SciPy. Run: python derive_fingertip.py OUTPUT
Files are fetched at a pinned commit and verified as Git blobs before reading.
"""
import argparse
import csv
import hashlib
import io
from pathlib import Path
import re
from urllib.request import urlopen

import numpy as np
from scipy.io import loadmat


REV = "0c688b315ceb58adc37b70ff3ee8800a02045c74"
REPO = "mq-0109/An-ultralight-tiny-flexible-six-axis-force-torque-sensor-enables-dexterous-fingertip-manipulations"
BLOBS = {
    "data.mat": "57de5f168601282dc5117f0b1852e6cd976187d9",
    "six_force.m": "690ff6d3b04a0cf605f75fc7696a1a16d7b784cf",
}
HEADER = ["subset", "axis", "units", "rows", "unique_axis_targets", "zero_axis_targets",
          "target_min", "target_max", "prediction_rmse", "prediction_mae",
          "mean_prediction_minus_target"]


def fetch(name):
    with urlopen(f"https://raw.githubusercontent.com/{REPO}/{REV}/{name}", timeout=60) as source:
        data = source.read()
    prefix = f"blob {len(data)}\0".encode()
    if hashlib.sha1(prefix + data).hexdigest() != BLOBS[name]:
        raise ValueError(f"Source hash mismatch for {name}")
    return data


def model(x, source):
    arrays = {}
    for key, value in re.findall(r"^([\w.]+) = \[([^\]]+)\];", source, re.MULTILINE):
        arrays[key] = np.array([[float(cell) for cell in row.split()] for row in value.split(";")])
    a = (x.T - arrays["x1_step1.xoffset"]) * arrays["x1_step1.gain"] - 1.0
    a = np.tanh(arrays["b1"] + arrays["IW1_1"] @ a)
    a = np.tanh(arrays["b2"] + arrays["LW2_1"] @ a)
    a = arrays["b3"] + arrays["LW3_2"] @ a
    return ((a + 1.0) / arrays["y1_step1.gain"] + arrays["y1_step1.xoffset"]).T


def main(out):
    data = loadmat(io.BytesIO(fetch("data.mat")))["data"]
    if data.shape != (418, 14) or not np.isfinite(data).all():
        raise ValueError("Unexpected sample matrix")
    y = data[:, 8:]
    prediction = model(data[:, :8], fetch("six_force.m").decode("utf-8"))
    zero = (y == 0).all(axis=1)
    groups = {"all": np.ones(len(y), dtype=bool), "all_six_targets_zero": zero,
              "any_nonzero_target": ~zero}
    out.mkdir(parents=True, exist_ok=True)
    with (out / "fingertip-axis-errors.csv").open("w", newline="", encoding="utf-8") as handle:
        write = csv.writer(handle, lineterminator="\n")
        write.writerow(HEADER)
        for group, mask in groups.items():
            for j, axis in enumerate(["Fx", "Fy", "Fz", "Mx", "My", "Mz"]):
                labels = y[mask, j]
                errors = prediction[mask, j] - labels
                stats = [labels.min(), labels.max(), np.sqrt(np.mean(errors**2)),
                         np.mean(np.abs(errors)), errors.mean()]
                write.writerow([group, axis, "N" if j < 3 else "mN m", len(labels),
                                len(np.unique(labels)), np.count_nonzero(labels == 0),
                                *(format(v, ".8f") for v in stats)])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    main(parser.parse_args().output)
