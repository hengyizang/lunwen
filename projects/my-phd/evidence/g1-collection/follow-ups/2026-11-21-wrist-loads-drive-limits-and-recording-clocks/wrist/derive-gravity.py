"""Recompute ATI drift, cross-pose residuals and provenance. Requires numpy and scipy."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen

import numpy as np
from scipy.spatial.transform import Rotation

REPO = "leledeyuan00/Gravity-Compensation-F-T-sensor"
REV = "139efe1841f97391002655ef370911d0417feaed"
RAW = f"https://raw.githubusercontent.com/{REPO}/{REV}/"
AXES = ["Fx_N", "Fy_N", "Fz_N", "Mx_Nm", "My_Nm", "Mz_Nm"]


def write_csv(path, rows):
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def design(pose):
    r = Rotation.from_quat(pose[:, 3:7]).as_matrix()
    up = np.zeros((len(r), 3)); up[:, 2] = 1
    force = np.concatenate((up[:, :, None], r), axis=2)
    moment = np.concatenate((np.cross(r[:, :, 2], up)[:, :, None], r), axis=2)
    return force, moment


def fit(pose, wrench):
    f, m = design(pose)
    p = np.linalg.lstsq(f.reshape(-1, 4), wrench[:, :3].ravel(), rcond=None)[0]
    # Fit the product (gravity force * axial CoM distance) in the first moment term.
    q = np.linalg.lstsq(m.reshape(-1, 4), wrench[:, 3:].ravel(), rcond=None)[0]
    return p, q


def persist_results(output, arrays):
    static = arrays["static_pose_recording.txt"]
    t = static[:, 0]
    assert len(t) == 130511 and np.all(np.diff(t) > 0) and static.shape[1] == 7
    elapsed = t - t[0]
    masks = [("all", np.ones(len(t), bool)), ("first_600_samples", np.arange(len(t)) < 600),
             ("last_600_samples", np.arange(len(t)) >= len(t) - 600)]
    for h in range(1 + int(elapsed[-1] // 3600)):
        masks.append((f"elapsed_hour_{h:02d}", (elapsed >= h * 3600) & (elapsed < (h + 1) * 3600)))
    drift = []
    for label, keep in masks:
        d = dict(window=label, n=int(keep.sum()), elapsed_start_s=round(elapsed[keep][0], 6),
                 elapsed_end_s=round(elapsed[keep][-1], 6))
        for ix, axis in enumerate(AXES, 1):
            col = static[keep, ix]
            for stat, value in [("mean", col.mean()), ("sd_population", col.std()), ("min", col.min()), ("max", col.max())]:
                d[f"{axis}_{stat}"] = round(float(value), 9)
        drift.append(d)
    write_csv(output / "gravity-static-windows.csv", drift)
    pose_sets = {}
    for n, suff in [(7, ""), (100, "_100")]:
        pose_sets[n] = (arrays[f"recorded_messages_pose{suff}.txt"], arrays[f"recorded_messages_wrench{suff}.txt"])
    tests = []
    for n, (pose, wrench) in pose_sets.items():
        for target, (p_test, w_test) in pose_sets.items():
            p, q = fit(pose, wrench)
            f, m = design(p_test)
            ef = np.linalg.norm(f @ p - w_test[:, :3], axis=1)
            em = np.linalg.norm(m @ q - w_test[:, 3:], axis=1)
            rec = dict(fit_file_poses=n, evaluated_file_poses=target, evaluation="same file" if n == target else "other file")
            for i, col in enumerate(["gravity_z_N", "sensor_bias_fx_N", "sensor_bias_fy_N", "sensor_bias_fz_N"]):
                rec[col] = round(float(p[i]), 9)
            rec["axial_com_m"] = round(float(q[0] / p[0]), 9)
            for i, name in enumerate(["mx", "my", "mz"], 1):
                rec[f"sensor_bias_{name}_Nm"] = round(float(q[i]), 9)
            for error, units in [(ef, "N"), (em, "Nm")]:
                rec[f"rms_residual_norm_{units}"] = round(float(np.sqrt(np.mean(error ** 2))), 9)
                rec[f"peak_residual_norm_{units}"] = round(float(error.max()), 9)
            tests.append(rec)
    write_csv(output / "gravity-pose-transfer.csv", tests)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("output", type=Path)
    ap.add_argument("cache", type=Path)
    args = ap.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    args.cache.mkdir(parents=True, exist_ok=True)
    with urlopen(f"https://api.github.com/repos/{REPO}/git/trees/{REV}?recursive=1") as response:
        tree = json.load(response)["tree"]
    inventory, arrays = [], {}
    for item in tree:
        key = item["path"]
        if not key.startswith("datas/") or item["type"] != "blob":
            continue
        file = args.cache / Path(key).name
        if not file.exists():
            with urlopen(RAW + key, timeout=120) as response:
                file.write_bytes(response.read())
        data = file.read_bytes()
        digest = hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()
        assert digest == item["sha"] and item["size"] == len(data)
        a = np.loadtxt(file, delimiter=",")
        assert np.isfinite(a).all()
        arrays[file.name] = a
        inventory.append(dict(path=key, git_blob_sha1=digest, bytes=len(data), rows=a.shape[0], columns=a.shape[1]))
    write_csv(args.output / "gravity-inventory.csv", inventory)
    persist_results(args.output, arrays)


if __name__ == "__main__":
    main()
