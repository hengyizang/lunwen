"""Analyze the fixed Zenodo A1 release. Usage: python derive_axis.py data.zip output_dir."""
import csv
import hashlib
import io
import sys
from pathlib import Path
from zipfile import ZipFile

import numpy as np


def write(path, rows):
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rows[0], lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def main(archive, output):
    output.mkdir(parents=True, exist_ok=True)
    runs = {}
    receipts = []
    with ZipFile(archive) as z:
        for name in sorted(n for n in z.namelist() if n.endswith(".csv")):
            blob = z.read(name)
            h = hashlib.sha256(blob).hexdigest()
            a = np.genfromtxt(io.BytesIO(blob), delimiter=",", names=True)
            t = a["Time"]
            r, m = a["Reference_Current"], a["Actual_Current"]
            assert np.isfinite(t).all() and (np.diff(t) > 0).all()
            assert np.isfinite(r).all() and np.isfinite(m).all()
            dual = "Arm_Actual_Position" in a.dtype.names
            pos = a["Arm_Actual_Position" if dual else "Actual_Position"]
            rel_gap = ((a["Motor_Actual_Position"] - a["Motor_Actual_Position"][0])
                       - (pos - pos[0])) if dual else None
            slope, offset = np.polyfit(r, m, 1)
            receipts.append(dict(member=name, sha256=h, rows=len(t),
                duplicate_of=runs[h][0] if h in runs else "", duration_s=t[-1]-t[0],
                dt_min_s=np.diff(t).min(),dt_max_s=np.diff(t).max(),
                velocity_nonfinite=int((~np.isfinite(a["Velocity"])).sum()),
                reference_current_min=r.min(),reference_current_max=r.max(),
                actual_current_min=m.min(),actual_current_max=m.max(),
                ols_slope=slope,ols_intercept=offset,pearson_r=np.corrcoef(r,m)[0,1],
                reference_pos_range=np.ptp(a["Reference_Position"]),
                actual_pos_range=np.ptp(pos),
                dual_encoder_max_abs_displacement_difference_deg=
                  np.abs(rel_gap).max() if dual else ""))
            runs.setdefault(h, (name,r,m))
    write(output/"axis-trials.csv",receipts)
    results=[]
    for held,(name, r, m) in runs.items():
        others=[v for h,v in runs.items() if h!=held]
        train_r=np.concatenate([v[1] for v in others])
        train_m=np.concatenate([v[2] for v in others])
        slope,offset=np.polyfit(train_r,train_m,1)
        residual=m-(slope*r+offset)
        results.append(dict(test_member=name, train_members=len(others),train_rows=len(train_r),
            test_rows=len(r),train_slope=slope,train_offset=offset,
            identity_rmse=np.sqrt(np.mean((m-r)**2)),affine_rmse=np.sqrt(np.mean(residual**2)),
            affine_mae=np.mean(np.abs(residual)),affine_peak_abs=np.abs(residual).max(),
            test_ref_outside_train_range=int(((r<train_r.min()) | (r>train_r.max())).sum())))
    write(output/"axis-heldout.csv",results)


if __name__ == "__main__":
    main(Path(sys.argv[1]),Path(sys.argv[2]))
