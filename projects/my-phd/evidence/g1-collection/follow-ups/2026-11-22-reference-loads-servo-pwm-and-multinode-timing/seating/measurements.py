import csv
import hashlib
import io
from pathlib import Path
import numpy as np
import h5py


def digest(data):
    return hashlib.sha256(data).hexdigest()


def save(out, name, rows):
    with (Path(out) / name).open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def summarise_demo(path, data, file_hash):
    result = []
    for side, key in [("left", "l"), ("right", "r")]:
        root = "topic_recordings/" + side + "_ft_sensor/wrench/"
        ts = np.asarray(data[root + "stamp"])
        force = np.asarray(data[root + "force"])
        torque = np.asarray(data[root + "torque"])
        chain = "robot_chains/kuka_lbr_" + key + "_hand_tcp/"
        pos = np.asarray(data[chain + "cart_pos"])
        joint_stamp = np.asarray(data["topic_recordings/joint_states/stamp"])
        # The same number of poses and joint stamps permits a timing audit, without asserting a pose clock.
        axis_span = np.ptp(pos[:, :3], axis=0)
        dt = np.diff(ts)
        result.append(
            dict(
                member=path,
                sha256=file_hash,
                arm=side,
                raw_wrench_n=len(ts),
                raw_wrench_elapsed_s=round(ts[-1] - ts[0], 6),
                median_raw_wrench_dt_s=round(np.median(dt), 6),
                max_raw_wrench_gap_s=round(dt.max(), 6),
                nonpositive_raw_wrench_steps=int((dt <= 0).sum()),
                force_norm_min_N=round(np.linalg.norm(force, axis=1).min(), 5),
                force_norm_max_N=round(np.linalg.norm(force, axis=1).max(), 5),
                torque_norm_max_Nm=round(np.linalg.norm(torque, axis=1).max(), 5),
                joint_stamps_n=len(joint_stamp),
                cart_pos_n=len(pos),
                chain_wrench_n=data[chain + "cart_wrench"].shape[0],
                chain_timestamp_n=data[chain + "timestamp"].shape[0],
                x_span_m=round(axis_span[0], 6),
                y_span_m=round(axis_span[1], 6),
                z_span_m=round(axis_span[2], 6),
            )
        )
    return result


def summarise_patch(test, wb, hb):
    wrench = np.loadtxt(io.BytesIO(wb))
    assert wrench.shape[1] == 7
    with h5py.File(io.BytesIO(hb), "r") as h:
        has = "Sensores" in h and "Tiempo" in h
        if has:
            signals = h["Sensores"][:]
            time = h["Tiempo"][:]
            assert signals.shape[0] == len(time)
            delta = np.diff(time)
        return dict(
            test=test,
            wrench_sha256=digest(wb),
            optical_sha256=digest(hb),
            wrench_n=len(wrench),
            index_first=int(wrench[0, 0]),
            index_last=int(wrench[-1, 0]),
            nonunit_index_steps=int((np.diff(wrench[:, 0]) != 1).sum()),
            min_fz_N=round(wrench[:, 3].min(), 6),
            max_fz_N=round(wrench[:, 3].max(), 6),
            max_force_norm_N=round(np.linalg.norm(wrench[:, 1:4], axis=1).max(), 6),
            max_torque_norm_Nm=round(np.linalg.norm(wrench[:, 4:7], axis=1).max(), 6),
            h5_groups="|".join(h.keys()),
            optical_n=len(time) if has else 0,
            optical_cols=signals.shape[1] if has else 0,
            nonfinite_optical_values=int((~np.isfinite(signals)).sum()) if has else "",
            optical_median_dt_native=round(np.median(delta), 8) if has else "",
            optical_nonpositive_deltas=int((delta <= 0).sum()) if has else "",
        )


def summarise_press(b):
    arr = np.loadtxt(io.BytesIO(b), delimiter=";", skiprows=1)
    assert arr.shape[1] == 6
    t, pct, nm, rpm, speed, pos = arr.T
    stationary = np.where(np.logical_and.accumulate((rpm == 0)[::-1])[::-1])[0]
    return dict(
        member="pressing/pressing_data_0_60s.csv",
        sha256=digest(b),
        n=len(t),
        start_s=t[0],
        end_s=t[-1],
        median_dt_s=round(np.median(np.diff(t)), 6),
        min_current_percent=pct.min(),
        max_current_percent=pct.max(),
        max_reported_Nm=nm.max(),
        max_abs_difference_Nm_from_pct_times_0_32=round(
            np.max(np.abs(nm - 0.32 * pct)), 8
        ),
        first_final_zero_rpm_s=t[stationary[0]],
        final_zero_rpm_samples=len(stationary),
        final_position_mm=pos[-1],
    )


def summarise_tests(path, b):
    from openpyxl import load_workbook

    f = load_workbook(io.BytesIO(b), read_only=True, data_only=True)
    rows = []
    for sh in f:
        entries = sh.values
        names = next(entries)
        units = next(entries)
        idxs = [i for i, v in enumerate(names) if v]
        channels = {i: [] for i in idxs}
        for i in idxs:
            assert units[i : i + 3] == ("Time (s)", "Displacement (mm)", "Force (N)")
        for row in entries:
            for i in idxs:
                triplet = row[i : i + 3]
                if len(triplet) == 3 and all(
                    isinstance(v, (float, int)) for v in triplet
                ):
                    channels[i].append(triplet)
        for i in idxs:
            a = np.asarray(channels[i])
            imax = np.argmax(a[:, 2])
            rows.append(
                dict(
                    workbook=path,
                    file_sha256=digest(b),
                    sheet=sh.title,
                    trace_label=names[i],
                    complete_numeric_rows=len(a),
                    nonpositive_time_steps=int((np.diff(a[:, 0]) <= 0).sum()),
                    duration_s=round(a[-1, 0] - a[0, 0], 6),
                    peak_force_N=a[imax, 2],
                    displacement_at_peak_mm=a[imax, 1],
                    time_at_peak_s=a[imax, 0],
                )
            )
    return rows
