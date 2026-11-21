"""Audit two force-sensor calibration outputs at pinned source versions.

Usage: python derive_calibrations.py OUTPUT. Python 3.9+ standard library.
"""
import argparse
import bisect
import csv
import hashlib
import io
import json
import math
from pathlib import Path
from urllib.request import urlopen


DIGIT = ("gemixin/digit-force-calibration", "59ef5ef32f28cdfbeec47ae707a8075460e008fb")
OPENFT = ("dimensionalOS/openFT-sensor", "876b60efbf6483fe401966c4d9fde0a9755bbc94")
SAMPLES = ["d3c18b2b5bbbce5313d4f1385072dd100afafebc", "71b0423692291df936366accceeb712ddaa8bea2"]
CURVES = ["4557dc0cef14e56ebc7780814b8b4a0ade1b1d90", "613b58bfb96a217fdd1391985cbf012323db2a7f"]


def source(repo, path, blob):
    owner_repo, revision = repo
    with urlopen(f"https://raw.githubusercontent.com/{owner_repo}/{revision}/{path}", timeout=60) as response:
        data = response.read()
    if hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest() != blob:
        raise ValueError(f"Git blob mismatch in {path}")
    return data.decode("utf-8")


def inverse(voltage, curve):
    position = bisect.bisect_left([r[1] for r in curve], voltage)
    if position == 0:
        return curve[0][0]
    if position == len(curve):
        return curve[-1][0]
    left, right = curve[position - 1:position + 1]
    return left[0] + (voltage - left[1]) * (right[0] - left[0]) / (right[1] - left[1])


def fsr_rows():
    curves = []
    for i, blob in enumerate(CURVES, 1):
        records = csv.DictReader(io.StringIO(source(DIGIT, f"curves/calibration_curve_fsr{i}.csv", blob)))
        curves.append([(float(row["force_n"]), float(row["voltage"])) for row in records])
    yield ["sensor", "target_g", "sample_rows", "trials", "adc_min", "adc_max", "adc_full_scale",
           "voltage_above_last_own_knot", "voltage_below_first_positive_own_knot", "target_has_positive_own_knot",
           "own_clamped_map_rmse_N", "other_clamped_map_rmse_N"]
    for i, blob in enumerate(SAMPLES):
        records = csv.DictReader(io.StringIO(source(DIGIT, f"data/force_calibration_fsr{i+1}.csv", blob)))
        rows = [(int(r["trial"]), int(r["target_g"]), int(r["raw"]), float(r["voltage"])) for r in records]
        own, other = curves[i], curves[1-i]
        for mass in [None, *sorted({r[1] for r in rows})]:
            group = [r for r in rows if mass is None or r[1] == mass]
            raw = [r[2] for r in group]
            volts = [r[3] for r in group]
            errors = []
            for curve in [own, other]:
                squared = [(inverse(voltage, curve) - target * 0.00981)**2 for _, target, _, voltage in group]
                errors.append(f"{math.sqrt(sum(squared)/len(squared)):.8f}")
            has_knot = mass is not None and any(abs(row[0] - mass * 0.00981) < 1e-8 for row in own)
            yield [i + 1, "all" if mass is None else mass, len(group), len({r[0] for r in group}),
                   min(raw), max(raw), raw.count(65535), sum(v > own[-1][1] for v in volts),
                   sum(v < own[1][1] for v in volts), int(has_knot), *errors]


def openft_rows():
    metadata = json.loads(source(OPENFT, "software/calibration/ft_calibration.json",
                                 "dd149a28799d9b500332865345c3269e90ba58cc"))
    yield ["output", "bias_intercept", "coefficient_L1", "nominal_box_min", "nominal_box_max", "nominal_box_span"]
    for name, bias, row in zip(["Fx","Fy","Fz","Mx","My","Mz"], metadata["bias_vector"],
                               metadata["calibration_matrix"]):
        low, high = bias, bias
        for coef in row:
            low += min(coef * 9000, coef * 21000)
            high += max(coef * 9000, coef * 21000)
        l1 = sum(abs(coef) for coef in row)
        yield [name, *(format(v, ".8e") for v in (bias, l1, low, high, 12000*l1))]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    out = parser.parse_args().output
    out.mkdir(exist_ok=True, parents=True)
    for filename, data in [("digit-fsr-knots.csv", fsr_rows()), ("openft-output-span.csv", openft_rows())]:
        with (out / filename).open("w", encoding="utf-8", newline="") as stream:
            csv.writer(stream, lineterminator="\n").writerows(data)
