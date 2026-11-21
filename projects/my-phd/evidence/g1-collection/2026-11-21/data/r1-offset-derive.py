"""Derive timestamp-relative wrench magnitudes from Zenodo record 17376427."""

import argparse
import csv
import gzip
import hashlib
import io
import json
import math
import statistics
import zipfile
from pathlib import Path

SOURCE_SHA256 = "e5f1087a1de5ed261af79b25bdc7548bbbf4e1386510c731e1675b8280c3eae4"
AUTHOR_CODE = (
    "https://github.com/alimousavimohammadi/offset_gravity_estimation/blob/"
    "781aa7cbd370ada97ea98e66a79aee32a1207550/src/python/scripts/"
)
TRIALS = {
    "human_demonstration/report_2025_02_22_10_47_44_light_object.dat": ("light_object", 9394),
    "human_demonstration/report_2025_03_04_17_55_42_heavy_object.dat": ("heavy_object", 19550),
    "robot_execution/report_of_2025_02_22_11_58_21_normal_speed.dat": ("normal_speed", 6553),
    "robot_execution/report_of_2025_02_22_12_03_48_slow_speed.dat": ("slow_speed", 41022),
}
COLUMNS = {
    "condition": "Condition from the public source filename. One recording per condition.",
    "setup": "human_demonstration or robot_execution as labeled in the source archive.",
    "wrench_channel": "JR3 wrench_filter_0 for demonstrations; netft_sensor.sensed_wrench for robot runs.",
    "sample_index": "One-based index within this recording; source acquisition order.",
    "relative_time_s": "Seconds since the first recorded sample in this condition.",
    "delta_time_s": "Difference in seconds from the previous sample in this recording. Empty for its first row.",
    "time_step_flag": "first_sample; regular (positive and at most twice this recording's median positive interval); long_interval (strictly above twice that median). Long intervals do not establish packet loss.",
    "force_norm_N": "Euclidean norm of the three recorded force components, in newtons, before additional offset or gravity correction.",
    "torque_norm_Nm": "Euclidean norm of the three recorded torque components, in newton-metres, before additional offset or gravity correction.",
}


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def read_trial(archive, name):
    setup = name.split("/")[0]
    if setup == "human_demonstration":
        channel = "JR3 wrench_filter_0"
        names = [
            f"jr3.sensor_0.wrench_filter_0.{quantity}.{axis}"
            for quantity in ("force", "torque") for axis in "xyz"
        ]
    else:
        channel = "netft_sensor.sensed_wrench"
        names = [f"{channel}.{i}" for i in range(6)]

    payload = archive.read(name)
    input_file = io.BytesIO(payload)
    header = input_file.readline().decode("ascii").split()
    indices = [header.index(key) for key in ["TimeStamp", *names]]
    measurements = []
    for line in input_file:
        if not line.strip():
            continue
        fields = line.split()
        if len(fields) != len(header):
            raise ValueError(f"Unexpected field count in {name}")
        stamp, fx, fy, fz, mx, my, mz = (float(fields[i]) for i in indices)
        measure = (stamp, math.hypot(fx, fy, fz), math.hypot(mx, my, mz))
        if not all(math.isfinite(value) for value in measure):
            raise ValueError(f"Nonfinite time or wrench in {name}")
        measurements.append(measure)
    return setup, channel, measurements, sha256(payload)


def write_trial(writer, archive, name, condition, expected):
    setup, channel, observations, member_hash = read_trial(archive, name)
    if len(observations) != expected:
        raise ValueError(f"Unexpected sample count in {name}")
    times, forces, torques = zip(*observations)
    intervals = [now - previous for now, previous in zip(times[1:], times)]
    if any(interval <= 0 for interval in intervals):
        raise ValueError(f"Non-increasing timestamps in {name}")
    median_interval = statistics.median(intervals)
    long_count = 0
    for index, (stamp, force, torque) in enumerate(observations):
        dt = intervals[index - 1] if index else None
        flag = "first_sample"
        if dt is not None:
            flag = "long_interval" if dt > 2 * median_interval else "regular"
            long_count += flag == "long_interval"
        writer.writerow([
            condition, setup, channel, index + 1, format(stamp - times[0], ".14g"),
            "" if dt is None else format(dt, ".14g"), flag,
            format(force, ".14g"), format(torque, ".14g"),
        ])
    return {
        "condition": condition, "setup": setup, "wrench_channel": channel,
        "member": name, "member_sha256": member_hash, "rows": expected,
        "time_span_source_units": times[-1] - times[0],
        "median_positive_time_step_source_units": median_interval,
        "long_intervals": long_count,
        "force_norm_min_N": min(forces), "force_norm_median_N": statistics.median(forces),
        "force_norm_max_N": max(forces), "torque_norm_min_Nm": min(torques),
        "torque_norm_median_Nm": statistics.median(torques), "torque_norm_max_Nm": max(torques),
    }


def check_summary(summaries, path):
    with path.open(encoding="utf-8-sig", newline="") as file:
        prior = {row["condition"]: row for row in csv.DictReader(file)}
    if set(prior) != {s["condition"] for s in summaries}:
        raise ValueError("Summary conditions do not match")
    for result in summaries:
        row = prior[result["condition"]]
        if result["rows"] != int(row["finite_wrench_time_rows"]):
            raise ValueError("Summary sample counts do not match")
        for key in result:
            if key.startswith(("force_norm_", "torque_norm_", "time_span_", "median_positive_")):
                if not math.isclose(result[key], float(row[key]), rel_tol=1e-9, abs_tol=1e-12):
                    raise ValueError(f"Summary mismatch: {result['condition']} {key}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, help="Unmodified data.zip from Zenodo record 17376427")
    parser.add_argument("--outdir", type=Path, default=Path.cwd())
    parser.add_argument("--summary", type=Path, help="Optional four-condition summary for cross-checking")
    args = parser.parse_args()
    payload = args.archive.read_bytes()
    if len(payload) != 2581147 or sha256(payload) != SOURCE_SHA256:
        raise ValueError("Source archive size or SHA-256 does not match Zenodo record 17376427")

    buffer = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(payload)) as source:
        if {item.filename for item in source.infolist() if not item.is_dir()} != set(TRIALS):
            raise ValueError("Unexpected archive members")
        with gzip.GzipFile(filename="", mode="wb", fileobj=buffer, mtime=0) as gz:
            with io.TextIOWrapper(gz, encoding="utf-8", newline="") as text:
                writer = csv.writer(text, lineterminator="\n")
                writer.writerow(COLUMNS)
                summaries = [
                    write_trial(writer, source, name, condition, count)
                    for name, (condition, count) in TRIALS.items()
                ]
    if args.summary:
        check_summary(summaries, args.summary)

    compressed = buffer.getvalue()
    name = "r1-offset-timeseries.csv.gz"
    code_name = "r1-offset-derive.py"
    provenance = {
        "dataset_title": 'Dataset for "Estimating Force/Torque Sensor Offsets and Gravity Parameters Using Only Wrench Measurements to Facilitate Human Demonstration of Robot Manipulation Tasks in Contact"',
        "source_creator": "Ali Mousavi Mohammadi, Katholieke Universiteit Leuven",
        "publication_date": "2025-09-23",
        "source_record": "https://zenodo.org/records/17376427",
        "source_doi": "10.5281/zenodo.17376427",
        "file_url": "https://zenodo.org/api/records/17376427/files/data.zip/content",
        "archive_bytes": len(payload), "archive_sha256": SOURCE_SHA256,
        "publisher_md5": "8064a4e55b5c51d00fe59cc32faf8e21",
        "related_paper": "https://doi.org/10.1109/CASE58245.2025.11163796",
        "license": "CC BY 4.0", "license_url": "https://creativecommons.org/licenses/by/4.0/",
        "attribution_and_changes": "Derived from the CC BY 4.0 dataset by Ali Mousavi Mohammadi (2025). This derivative tabulates two vector magnitudes, elapsed times and sample-interval flags. Cite and credit the original dataset and identify this transformation when reusing the derivative.",
        "channel_mapping_and_unit_sources": [
            AUTHOR_CODE + "human_demonstration.py", AUTHOR_CODE + "robot_execution.py",
            AUTHOR_CODE + "functions/plotting.py",
        ],
        "units_evidence": "Author analysis selects TimeStamp, and plots with t [s], force [N], and moment [Nm].",
        "derivation": "Read the four fixed .dat members in source acquisition order. Retain all nonempty data rows including startup, require finite timestamp and wrench and strictly increasing time; omit global timestamps, pose and source axis values. For each sample take sqrt(Fx^2+Fy^2+Fz^2) and sqrt(Mx^2+My^2+Mz^2). Subtract the first timestamp per file, and difference consecutive timestamps. No smoothing, gravity compensation, sensor-zero fitting, interpolation or resampling. Numeric text has 14 significant digits. Columns are UTF-8, comma-separated with LF and deterministic gzip header time zero.",
        "columns": COLUMNS, "recordings": summaries, "total_rows": sum(s["rows"] for s in summaries),
        "missing_finite_wrench_or_time": 0, "missing_first_time_step_rows": len(TRIALS),
        "nonpositive_successive_intervals": 0,
        "limitations": [
            "Two demonstration and two robot conditions arose from different sensor channels and data acquisition setups; pool them only with an explicit model for those differences.",
            "Magnitude removes direction and sign. Norms include load, gravity, and other contributions. True sensor bias, drift and contact forces are not identifiable from these norms alone.",
            "Rows within recordings are serially dependent. No sample is an independent trial of assembly efficacy, and no long interval has an independently verified cause.",
        ],
        "output": {"name": name, "compressed_bytes": len(compressed), "gzip_sha256": sha256(compressed),
                   "uncompressed_csv_sha256": sha256(gzip.decompress(compressed))},
        "reproduce": f"python3 {code_name} data.zip --outdir OUTPUT [--summary r1-offset-sample.csv]",
        "derivation_script_sha256": sha256(Path(__file__).read_bytes()),
    }
    if args.summary:
        provenance["four_condition_crosscheck"] = {
            "sha256": sha256(args.summary.read_bytes()), "passed": True,
            "fields": "4 counts; 8 per-condition continuous statistics (time span, median interval, force norm and torque norm min/median/max)",
            "relative_tolerance": 1e-9, "absolute_tolerance": 1e-12,
        }
    args.outdir.mkdir(parents=True, exist_ok=True)
    (args.outdir / name).write_bytes(compressed)
    (args.outdir / "r1-offset-timeseries.json").write_text(
        json.dumps(provenance, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
