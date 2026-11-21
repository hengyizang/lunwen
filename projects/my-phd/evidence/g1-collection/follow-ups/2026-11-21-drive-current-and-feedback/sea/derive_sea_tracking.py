"""Summarize the hardware trials from a fixed copy of Liken233/Transformer_RL.

Usage: python derive_sea_tracking.py REPOSITORY OUTPUT_DIR
Requires numpy and scipy. No raw rows, simulations or repeated representations are exported.
"""
import argparse
import csv
import hashlib
from pathlib import Path

import numpy as np
from scipy.io import loadmat


def records(path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def signals(rows):
    return {k: np.array([float(row[k]) for row in rows]) for k in rows[0]}


def fmt(number):
    return format(float(number), ".8f").rstrip("0").rstrip(".") or "0"


def main(root, output):
    experiment = root / "experiment_data"
    payload = next((experiment / "hardware_payload_experiment").glob("step30*/data"))
    published = {int(r["load_mass_g"]): r for r in records(payload / "summary_metrics.csv")}
    files = sorted(payload.glob("original/*_full.csv")) + sorted(experiment.glob("hardware*/*_clean.csv"))
    assert len(files) == 6
    summaries = []
    for path in files:
        data = signals(records(path))
        if not all(np.all(np.isfinite(v)) for v in data.values()):
            raise ValueError(f"Incomplete signal in {path.name}")
        n = len(data["wall_time_s"])
        terms = dict(completed="", passed="", command_passed="")
        mass = ""
        mat_hash = ""
        if path.name.endswith("_full.csv"):
            mass = int(path.name.split("_")[1][:-1])
            original = payload / "original" / f"step30_{mass}g.mat"
            mat_hash = hashlib.sha256(original.read_bytes()).hexdigest()
            mat = loadmat(original, simplify_cells=True)
            report, log = mat["report"], mat["log"]
            limit = report["command_limit_raw"]
            # Check the fields used for the summary against the original MAT export.
            mapping = {"controller_clock_s":"controller_clock", "external_target_rad":"target",
                       "q_link_rad":"q", "policy_output_numeric":"raw_action", "raw_candidate":"drive_candidate",
                       "safe_command_raw":"safe_command", "pre_integer_command_raw":"applied_command",
                       "pdo_command_int16_raw":"pdo_command", "actual_torque_raw":"actual_torque_raw"}
            for key, source in mapping.items():
                if not np.allclose(data[key], log[source], rtol=2e-12, atol=1e-10):
                    raise ValueError(f"{path.name}: MAT/CSV differ in {key}")
            first = np.flatnonzero(data["external_target_rad"] > np.deg2rad(15))[0]
            x = {k:v[first:] for k,v in data.items()}
            terms = {k:int(report[k]) for k in terms}
            trial = "30-degree payload step, post-onset"
            source = published[mass]
            # The Git blobs use LF. The publisher summary hashes the same CSV bytes with CRLF.
            crlf = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
            assert source["source_csv_sha256"].lower() == hashlib.sha256(crlf).hexdigest()
            assert len(x["wall_time_s"]) == int(source["post_step_sample_count"])
        else:
            # The accompanying experiment_description.txt specifies the 150-raw limit.
            limit = 150
            x = data
            trial = "sine tracking" if path.name.startswith("sine") else "multi-target steps"
        elapsed = x["controller_clock_s"] - x["controller_clock_s"][0]
        step = np.diff(elapsed)
        if np.any(step <= 0):
            raise ValueError(f"{path.name}: controller clock is not strictly increasing")
        err = np.rad2deg(x["external_target_rad"] - x["q_link_rad"])
        rmse = np.sqrt(np.mean(err**2))
        if mass != "" and abs(rmse - float(source["tracking_rmse_deg"])) > 1e-7:
            raise ValueError(f"{path.name}: source RMSE mismatch")
        safe = x["safe_command_raw"]
        summaries.append(dict(
            file=path.name, csv_sha256=hashlib.sha256(path.read_bytes()).hexdigest(), mat_sha256=mat_hash,
            condition=trial, added_mass_g=mass, all_csv_rows=n, retained_rows=len(err),
            span_controller_s=fmt(elapsed[-1]), median_logged_step_ms=fmt(1000*np.median(step)),
            max_logged_step_ms=fmt(1000*np.max(step)), nominal_command_limit_raw=fmt(limit),
            max_abs_policy_raw=fmt(np.max(np.abs(x["policy_output_numeric"]))),
            max_abs_candidate_raw=fmt(np.max(np.abs(x["raw_candidate"]))),
            max_abs_safe_raw=fmt(np.max(np.abs(safe))),
            max_abs_ethercat_command_raw=fmt(np.max(np.abs(x["pdo_command_int16_raw"]))),
            max_abs_drive_torque_feedback_raw=fmt(np.max(np.abs(x["actual_torque_raw"]))),
            samples_safe_at_or_beyond_limit=int(np.sum(np.abs(safe) >= limit)),
            peak_abs_motor_minus_link_deg=fmt(np.max(np.abs(np.rad2deg(x["theta_joint_rad"]-x["q_link_rad"])))),
            sample_weighted_tracking_rmse_deg=fmt(rmse),
            same_row_safe_vs_preinteger_different=int(np.sum(np.abs(safe-x["pre_integer_command_raw"])>1e-6)),
            atomic_safe_applied_nonzero=int(np.sum(np.abs(x["atomic_safe_applied_error_raw"])>1e-6)) if "atomic_safe_applied_error_raw" in x else "",
            nonzero_fault_code=int(np.count_nonzero(x["fault_code"])), **terms))
    output.mkdir(parents=True, exist_ok=True)
    with (output / "sea-tracking-runs.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=summaries[0], lineterminator="\n")
        w.writeheader()
        w.writerows(summaries)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repository", type=Path)
    parser.add_argument("output_directory", type=Path)
    args = parser.parse_args()
    main(args.repository, args.output_directory)
