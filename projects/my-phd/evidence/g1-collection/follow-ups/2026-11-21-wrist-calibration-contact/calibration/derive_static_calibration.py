"""Recompute static wrist gravity fits and inter-deposit checks from two Zenodo CSVs."""
import argparse
import csv
import hashlib
from pathlib import Path
import numpy as np


def load(path, digest):
    if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise ValueError(f"Unexpected source: {path}")
    with path.open(newline="") as stream:
        data = list(csv.DictReader(stream))
    fields = "fx fy fz tx ty tz gx gy gz r11 r12 r13 r21 r22 r23 r31 r32 r33".split()
    matrix = np.array([[float(row[key]) for key in fields] for row in data])
    if matrix.shape != (24, 18) or not np.isfinite(matrix).all():
        raise ValueError("Expected 24 finite pose records")
    return matrix


def block(g):
    x, y, z = g
    # h cross g where h = mass * centre of mass in the sensor frame.
    return np.array([[0, z, -y], [-z, 0, x], [y, -x, 0]])


def designs(rows):
    count = len(rows)
    gravity = rows[:, 6:9]
    identity = np.tile(np.eye(3), (count, 1))
    return (np.column_stack((gravity.ravel(), identity)),
            np.column_stack((np.vstack([block(g) for g in gravity]), identity)))


def fit_summary(train, test, name):
    f, t = designs(train)
    force, _, frank, _ = np.linalg.lstsq(f, train[:, :3].ravel(), rcond=None)
    torque, _, trank, _ = np.linalg.lstsq(t, train[:, 3:6].ravel(), rcond=None)
    if (frank, trank) != (4, 6):
        raise ValueError("Insufficient excitation rank")
    fv, tv = designs(test)
    fe = (fv @ force).reshape(-1, 3) - test[:, :3]
    te = (tv @ torque).reshape(-1, 3) - test[:, 3:6]
    numeric = dict(zip(("mass_kg", "force_offset_x_N", "force_offset_y_N", "force_offset_z_N"), force))
    numeric.update(zip(("com_x_m", "com_y_m", "com_z_m"), torque[:3] / force[0]))
    numeric.update(zip(("torque_offset_x_Nm", "torque_offset_y_Nm", "torque_offset_z_Nm"), torque[3:]))
    numeric["force_vector_RMSE_N"] = np.sqrt(np.mean(np.sum(fe**2, axis=1)))
    numeric["torque_vector_RMSE_Nm"] = np.sqrt(np.mean(np.sum(te**2, axis=1)))
    return {"evaluation": name, "train_poses": len(train), "evaluated_poses": len(test),
            "force_design_rank": frank, "torque_design_rank": trank,
            **{k: format(v, ".8f") for k, v in numeric.items()}}


def write(path, rows):
    with path.open("w", newline="") as stream:
        output = csv.DictWriter(stream, fieldnames=rows[0], lineterminator="\n")
        output.writeheader()
        output.writerows(rows)


def directions(x):
    gravity = x[:, 6:9]
    idx = np.argmax(abs(gravity), axis=1)
    return np.array([("-" if value[i] < 0 else "+") + "xyz"[i] for i, value in zip(idx, gravity)])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    a = load(args.input_dir / "fts_measurements.csv", "742411fc66461bff69e472de020febd11456b1338130607da5f114583b593aef")
    b = load(args.input_dir / "0-calibration_fts-accel.csv", "ae7966b36fd1338de666665eeff2d5ec7c32c6d7dfeee30a0948c3ae172c5edd")
    labels = directions(a)
    if not np.array_equal(labels, directions(b)) or len(set(labels)) != 6:
        raise ValueError("Unexpected gravity pose correspondence")
    results = [fit_summary(a, a, "all_poses_in_sample")]
    for direction in sorted(set(labels)):
        held_out = labels == direction
        if held_out.sum() != 4:
            raise ValueError("Expected four distinct orientations per gravity direction")
        results.append(fit_summary(a[~held_out], a[held_out], "held_out_gravity_" + direction))
    compare = []
    for col, key in enumerate(("Fx_N", "Fy_N", "Fz_N", "Tx_Nm", "Ty_Nm", "Tz_Nm")):
        delta = abs(a[:, col] - b[:, col])
        compare.append({"component": key, "rows_compared_in_order": len(a),
                        "same_value_rows": int((delta == 0).sum()),
                        "min_abs_difference": format(min(delta), ".8g"),
                        "median_abs_difference": format(np.median(delta), ".8g"),
                        "max_abs_difference": format(max(delta), ".8g")})
    if set(map(tuple, a[:, :6])).intersection(map(tuple, b[:, :6])):
        raise ValueError("Unexpected exact wrench overlap across deposits")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write(args.output_dir / "static-wrist-fits.csv", results)
    write(args.output_dir / "static-wrist-deposit-comparison.csv", compare)


if __name__ == "__main__":
    main()
