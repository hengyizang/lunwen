"""Summarize two OpenMCT releases and verify the published v2 current calibration."""
import argparse
import csv
import hashlib
import io
from pathlib import Path
from zipfile import ZipFile

import numpy as np

LOG_MANIFESTS = {
    1: "c8e8886951ea7143a0712ffc9ab1c9fc9bcffcf01ecc5a0e047099c53f387364",
    2: "ade527389ced9a974505a19f86838e28f4313bc970a59b00c1402398064da021",
}
COLUMNS = ("REF", "MEAS", "DT_ms", "CURRENT_RAW", "CURRENT_AVG", "PWM",
           "DMM_CURRENT_A", "DMM_TIME_s", "DMM_AGE_ms", "DMM_SAMPLE_ID")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write(directory, filename, rows):
    with (directory / filename).open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0], lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: format(v, ".10g") if isinstance(v, (float, np.floating)) else v
                             for k, v in row.items()})


def parse(data):
    lines = data.decode("utf-8-sig").splitlines()
    if not lines[0].startswith("Mode: ") or not lines[1].startswith("Date: "):
        raise ValueError("Missing mode or recording date")
    if tuple(lines[2].split(",")) != COLUMNS:
        raise ValueError("Unknown measurement schema")
    a = np.loadtxt(lines[3:], delimiter=",", ndmin=2)
    if not np.isfinite(a[:, :6]).all() or not np.isfinite(a[:, 9]).all():
        raise ValueError("Missing signal outside optional DMM fields")
    return dict(zip(COLUMNS, a.T)), lines[0][6:], lines[1][6:]


def get_valid(d):
    return ((d["DMM_SAMPLE_ID"] >= 0) & np.isfinite(d["DMM_CURRENT_A"]) &
            np.isfinite(d["DMM_TIME_s"]) & np.isfinite(d["DMM_AGE_ms"]))


def meter_summary(d):
    valid = get_valid(d)
    ids = d["DMM_SAMPLE_ID"][valid]
    amp = d["DMM_CURRENT_A"][valid]
    time = d["DMM_TIME_s"][valid]
    age = d["DMM_AGE_ms"][valid]
    if (np.diff(ids) < 0).any() or (age < 0).any():
        raise ValueError("Unexpected DMM clock or identifier ordering")
    unique, counts = np.unique(ids, return_counts=True)
    same = np.diff(ids) == 0
    return {
        "complete_dmm_rows": len(ids), "unique_dmm_ids": len(unique),
        "repeated_references_beyond_first": len(ids)-len(unique),
        "distinct_ids_referenced_more_than_once": np.sum(counts > 1), "max_rows_per_dmm_id": np.max(counts),
        "same_id_adjacent_changes_in_current_or_timestamp": np.sum(same & ((np.diff(amp) != 0) | (np.diff(time) != 0))),
        "age_min_ms": np.min(age), "age_median_ms": np.median(age), "age_p95_ms": np.quantile(age, .95),
        "age_max_ms": np.max(age), "rows_age_le_10ms": np.sum(age <= 10),
        "distinct_ids_age_le_10ms": len(np.unique(ids[age <= 10])),
    }


def pwm_summary(d):
    pwm = d["PWM"]
    ref = d["REF"]
    if (pwm < 0).any() or (pwm > 255).any() or (pwm != np.floor(pwm)).any():
        raise ValueError("Unexpected PWM range or quantization")
    high = pwm == 255
    low = pwm == 0
    edges = np.diff(np.r_[False, high, False].astype(int))
    return {
        "rows": len(pwm), "pwm_min": np.min(pwm), "pwm_max": np.max(pwm),
        "pwm_zero_and_reference_zero": np.sum(low & (ref == 0)),
        "pwm_zero_and_reference_nonzero": np.sum(low & (ref != 0)),
        "pwm_255_rows": np.sum(high), "pwm_255_runs": np.sum(edges == 1),
        "pwm_255_zero_based_row_indices": ",".join(map(str, np.flatnonzero(high))),
        "pwm_255_reference_as_stored": ",".join(format(x, "g") for x in ref[high]),
        "pwm_255_measured_speed_as_stored": ",".join(format(x, "g") for x in d["MEAS"][high]),
    }


def calibration(d, benchmarks):
    valid = get_valid(d)
    results = []
    for published in benchmarks:
        max_age = float(published["MaxDmmAge_ms"])
        candidates = np.flatnonzero(valid & (d["DMM_AGE_ms"] <= max_age))
        # Retain minimum age per ID, with first row winning ties as in the release.
        best = {}
        for i in candidates:
            ident = int(d["DMM_SAMPLE_ID"][i])
            if ident not in best or d["DMM_AGE_ms"][i] < d["DMM_AGE_ms"][best[ident]]:
                best[ident] = i
        indices = np.array(list(best.values()))
        x = d["CURRENT_RAW"][indices]
        y = 1000*np.abs(d["DMM_CURRENT_A"][indices])
        residual = y - np.polyval(np.polyfit(x, y, 1), x)
        centered = residual - np.median(residual)
        keep = np.abs(centered) <= 4 * 1.4826 * np.median(np.abs(centered))
        slope, offset = np.polyfit(x[keep], y[keep], 1)
        final_residual = y[keep] - (slope*x[keep] + offset)
        rmse = np.sqrt(np.mean(final_residual**2))
        observed = [len(x), keep.sum(), len(x)-keep.sum(), slope, offset, rmse]
        expected = [float(published[k]) for k in ("CandidatePairCount", "RetainedPairCount", "RejectedPairCount",
                    "SlopeAfterRejection_mA_per_count", "InterceptAfterRejection_mA", "RMSEAfterRejection_mA")]
        if not np.allclose(observed, expected, rtol=1e-9, atol=1e-9):
            raise ValueError(f"Published calibration disagreement at {max_age} ms")
        results.append({
            "version": 2, "maximum_age_ms": max_age, "eligible_firmware_rows": len(candidates),
            "unique_dmm_pairs": len(x), "retained_pairs": np.sum(keep), "rejected_pairs": np.sum(~keep),
            "slope_mA_per_adc_count": slope, "intercept_mA": offset, "calibration_fit_rmse_mA": rmse,
        })
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("v1_zip", type=Path)
    parser.add_argument("v2_zip", type=Path)
    parser.add_argument("outdir", type=Path)
    args = parser.parse_args()
    args.outdir.mkdir(parents=True, exist_ok=True)
    runs, controls, calibrations = [], [], []
    previous_hashes = set()
    for version, filename in enumerate((args.v1_zip, args.v2_zip), 1):
        with ZipFile(filename) as archive:
            files = {name.split("/", 1)[1]: name for name in archive.namelist()}
            names = sorted(k for k in files if k.endswith(".txt") and Path(k).name.startswith("raw_"))
            hashes = {name: digest(archive.read(files[name])) for name in names}
            manifest = "".join(f"{k}\t{v}\n" for k, v in hashes.items())
            if digest(manifest.encode()) != LOG_MANIFESTS[version]:
                raise ValueError(f"Raw log hashes differ from release v{version}")
            if version == 2:
                manifest_lines = archive.read(files["SHA256SUMS.txt"]).decode().splitlines()
                release_hashes = dict((line[66:], line[:64]) for line in manifest_lines if line.strip())
                if any(hashes[k] != release_hashes[k] for k in names):
                    raise ValueError("Raw logs differ from the author's v2 manifest")
            for name in names:
                d, role, date = parse(archive.read(files[name]))
                fixed = {"version": version, "member": name}
                runs.append({
                    **fixed, "sha256": hashes[name], "mode_as_logged": role, "date_as_logged": date,
                    "exact_v1_duplicate": int(version == 2 and hashes[name] in previous_hashes),
                    "rows": len(d["PWM"]), "distinct_DT_ms": len(np.unique(d["DT_ms"])),
                    "median_DT_ms": np.median(d["DT_ms"]), **meter_summary(d),
                })
                if role == "Speed Control" or name.startswith("optional_characterization/"):
                    controls.append({**fixed, "mode_as_logged": role, **pwm_summary(d)})
                if version == 2 and name == "01_current_calibration/raw_data.txt":
                    refname = "01_current_calibration/current_calibration_age_sensitivity.csv"
                    text = archive.read(files[refname]).decode("utf-8-sig")
                    calibrations = calibration(d, csv.DictReader(io.StringIO(text)))
            if version == 1:
                previous_hashes = set(hashes.values())
    write(args.outdir, "openmct-dmm-by-log.csv", runs)
    write(args.outdir, "openmct-output-endpoints.csv", controls)
    write(args.outdir, "openmct-calibration-age.csv", calibrations)


if __name__ == "__main__":
    main()
