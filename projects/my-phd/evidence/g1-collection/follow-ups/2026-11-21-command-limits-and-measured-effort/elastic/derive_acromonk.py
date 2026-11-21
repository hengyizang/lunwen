"""Summarise physical AcroMonk logs. Usage: python derive_acromonk.py CHECKOUT OUT."""
import hashlib
from pathlib import Path
import sys
import numpy as np
import pandas as pd


def main(root, out):
    records, phases, comparison = [], [], []
    # Published Table IV, arXiv:2305.08373v1, page 7. One row per 5x BF controller.
    published = {"BF_pd_5x.csv": 3.506, "BF_tvlqr_5x.csv": 3.231, "BF_rl_5x.csv": 3.55}
    phase_names = {0:"kickback", 1:"swing", 2:"catch", 3:"recovery", 4:"go_to_zero"}
    for path in sorted((root / "results/real_system/csvs").glob("*.csv")):
        data = pd.read_csv(path)
        assert np.isfinite(data["elbow_meas_tau"]).all()
        records.append(dict(file=str(path.relative_to(root)), sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                            rows=len(data), named_columns=len(data.columns),
                            has_command_and_clipped="elbow_cmd_tau" in data,
                            has_phase="state_machine_flag" in data,
                            nonincreasing_meas_time_steps=int((data.meas_time.diff() <= 0).sum())))
        if path.name in published:
            peak = data["elbow_meas_tau"].abs().max()
            comparison.append(dict(file=path.name, csv_peak_abs_servo_readback_Nm=peak,
                                   table_IV_paper_peak_abs_Nm=published[path.name],
                                   csv_minus_paper_Nm=peak-published[path.name]))
        groups = data.groupby("state_machine_flag") if "state_machine_flag" in data else [(None,data)]
        for flag, frame in groups:
            measured = frame.elbow_meas_tau
            r = dict(file=path.name, phase=phase_names[flag] if flag is not None else "unlabelled",
                     rows=len(frame), readback_min_Nm=measured.min(), readback_max_Nm=measured.max())
            if "elbow_cmd_tau" in frame:
                command, clipped = frame.elbow_cmd_tau, frame.elbow_clipped_tau
                use = command.notna() & clipped.notna()
                command, clipped, measured = command[use], clipped[use], measured[use]
                delta = command.abs() - clipped.abs()
                r.update(paired_command_rows=len(delta), max_abs_cmd_Nm=command.abs().max(),
                         max_abs_clipped_Nm=clipped.abs().max(), magnitude_reduced_count=(delta > 1e-6).sum(),
                         max_magnitude_reduction_Nm=delta.max() if len(delta) else np.nan,
                         nonzero_opposite_sign_count=((command * clipped) < -1e-12).sum(),
                         zero_host_feedforward_count=((command == 0) & (clipped == 0)).sum(),
                         zero_host_but_abs_readback_above_0p1Nm=((command==0) & (clipped==0) & (measured.abs()>0.1)).sum())
            phases.append(r)
    for name, rows in [("acromonk-files",records),("acromonk-phases",phases),("acromonk-paper-check",comparison)]:
        pd.DataFrame(rows).to_csv(out/(name+".csv"),index=False,float_format="%.9g",lineterminator="\n")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
