"""Analyze the 24 MAT files of 4TU Dyrac, version 1 (10.4121/13625951).

Usage: python derive_dyrac.py SOURCE_DIRECTORY OUTPUT_DIRECTORY
See dyrac-source.json for source download addresses and MD5 checksums.
"""
import argparse
import csv
import hashlib
import json
import re
from pathlib import Path

import numpy as np
from scipy.io import loadmat


def num(x):
    return format(float(x), ".9g")


def emit(path, rows):
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0], lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main(source, output):
    receipt = json.loads(Path(__file__).with_name("dyrac-source.json").read_text())
    fixed, pulses, calibration = [], [], []
    for file in receipt["inputs"]:
        path = source / file["name"]
        with path.open("rb") as f:
            if hashlib.file_digest(f, "md5").hexdigest() != file["md5"]:
                raise ValueError(f"4TU MD5 differs for {path.name}")
        a = loadmat(path, simplify_cells=True)
        t = a["time"]
        n = len(t)
        if not all(len(x) == n and np.all(np.isfinite(x)) for k, x in a.items() if not k.startswith("_")):
            raise ValueError(f"Invalid channel in {path.name}")
        if not np.allclose(np.diff(t), 0.001, rtol=0, atol=1e-9):
            raise ValueError(f"Nonuniform or non-1-ms time in {path.name}")
        base = dict(file=path.name, rows=n, span_s=num(t[-1]-t[0]))
        if "T3calib" in path.name:
            calibration.append(dict(**base, T3set_min=num(a["T3set"].min()), T3set_max=num(a["T3set"].max()),
                                    Tz_min=num(a["Tz"].min()), Tz_max=num(a["Tz"].max())))
            continue
        if np.max(np.abs(a["etaactual"]-a["phiactual"]-a["alpha"])) > 1e-8:
            raise ValueError("Recorded angle convention does not hold for " + path.name)
        # Only rows with active motors and no flagged endstop qualify for comparisons.
        active = (a["MotorsActive"] == 1) & (a["EndstopActive"] == 0)
        rset = a["rset"] * 1000
        ract = a["ractual"] * 1000
        measured = a["ToSensor"]
        calibrated = np.abs(measured) <= 10
        base.update(setpoints_mm="|".join(num(v) for v in np.unique(rset)),
                    motor_on_endstop_off_rows=int(active.sum()),
                    over_10_Nm_all=int((~calibrated).sum()),
                    over_10_Nm_motor_on_endstop_off=int(np.sum(active & ~calibrated)))
        if "SpringIdentification" in path.name:
            nominal = int(re.search(r"-r(\d+)mm",path.name)[1])
            # Match actual and requested pivot to the indexed setting to avoid setup transients.
            valid = active & calibrated & np.isclose(rset, nominal, atol=1e-7, rtol=0) & (np.abs(ract-nominal) <= 0.5)
            x, y = a["alpha"][valid], measured[valid]
            slope, intercept = np.polyfit(x,y,1)
            fitted = slope*x + intercept
            fixed.append(dict(**base, nominal_filename_radius_mm=nominal, fit_rows=len(x),
                              alpha_min_rad=num(x.min()), alpha_max_rad=num(x.max()),
                              measured_min_Nm=num(y.min()), measured_max_Nm=num(y.max()),
                              median_actual_radius_mm=num(np.median(ract[valid])),
                              signed_slope_Nm_per_rad=num(slope), intercept_Nm=num(intercept),
                              fit_rmse_Nm=num(np.sqrt(np.mean((fitted-y)**2))),
                              r_squared=num(1-np.sum((fitted-y)**2)/np.sum((y-y.mean())**2))))
        else:
            # Changes are in the logged command, independently of the names on the files.
            starts = np.flatnonzero(np.abs(np.diff(rset))>1e-7) + 1
            if len(starts)==0:
                raise ValueError(f"No commanded radius reversal in {path.name}")
            for direction in (1,-1):
                count = continuous = near_previous = 0
                times = []
                for j, start in enumerate(starts):
                    end = starts[j+1] if j+1<len(starts) else n
                    old, new = rset[start-1],rset[start]
                    amplitude = abs(new-old)
                    if (new-old)*direction<=0:
                        continue
                    count += 1
                    if not active[start-1:end].all():
                        continue
                    continuous += 1
                    if abs(ract[start-1]-old)>0.10*amplitude:
                        continue
                    near_previous += 1
                    ix = np.flatnonzero(direction*(ract[start:end]-old) >= 0.90*amplitude)
                    if len(ix):
                        times.append(1000*(t[start+ix[0]]-t[start]))
                pulses.append(dict(**base,direction="increase" if direction==1 else "decrease",
                                  command_transitions=count, fully_active_holds=continuous,
                                  starts_within_10pct_previous=near_previous,
                                  reached_90pct_before_next_command=len(times),
                                  median_first_90pct_ms=num(np.median(times)) if times else "",
                                  min_first_90pct_ms=num(min(times)) if times else "",
                                  max_first_90pct_ms=num(max(times)) if times else ""))
    if (len(fixed),len(pulses),len(calibration))!=(19,8,1):
        raise ValueError("Unexpected release coverage")
    output.mkdir(exist_ok=True,parents=True)
    emit(output / "dyrac-spring-runs.csv",sorted(fixed, key=lambda r:r["nominal_filename_radius_mm"]))
    emit(output / "dyrac-radius-transitions.csv",pulses)
    emit(output / "dyrac-damper-calibration.csv",calibration)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_directory", type=Path)
    parser.add_argument("output_directory", type=Path)
    args = parser.parse_args()
    main(args.source_directory, args.output_directory)
