"""Recompute descriptive tables from three pinned public archives using Python 3.

Usage: python derive.py INPUT_DIR OUTPUT_DIR
INPUT_DIR contains g1-uci-138.zip, g1-nanodrone.zip and a zenodo/
directory of the 12 CSVs in Zenodo record 11096791. Source URLs and hashes
are in sources.json. Original archives are not redistributed here.
"""
import csv
import hashlib
import io
import json
import math
import statistics
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
CHANNELS = ("fx", "fy", "fz", "tx", "ty", "tz")


def write_csv(path, records):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(records[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)


def verify(path, expected):
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise ValueError(f"Source hash mismatch for {path.name}")


def uci_records(path):
    records = []
    with zipfile.ZipFile(path) as archive:
        for i in range(1, 6):
            lines = [line.strip() for line in archive.read(f"lp{i}.data").decode("ascii").splitlines() if line.strip()]
            if len(lines) % 16:
                raise ValueError("Incomplete UCI episode")
            for offset in range(0, len(lines), 16):
                label = lines[offset]
                samples = [[int(v) for v in line.split()] for line in lines[offset+1:offset+16]]
                if not label[0].isalpha() or any(len(row) != 6 for row in samples):
                    raise ValueError("Invalid UCI episode label or width")
                result = {"task": f"LP{i}", "episode_in_source": 1+offset//16, "class_as_released": label, "samples": len(samples)}
                for index, channel in enumerate(CHANNELS):
                    values = [sample[index] for sample in samples]
                    result[channel + "_median_native"] = statistics.median(values)
                    result[channel + "_peak_to_peak_native"] = max(values) - min(values)
                records.append(result)
    if len(records) != 463:
        raise ValueError("Unexpected UCI episode count")
    return records


def get_numeric_table(payload):
    reader = csv.DictReader(io.StringIO(payload.decode("utf-8-sig")))
    rows = [{column: float(value) for column, value in row.items()} for row in reader]
    if not rows or any(not math.isfinite(v) for row in rows for v in row.values()):
        raise ValueError("Found an empty or non-finite table")
    return rows


def zenodo_records(directory, entries):
    records = []
    for entry in entries:
        path = directory / entry["file"]
        verify(path, entry["sha256"])
        rows = get_numeric_table(path.read_bytes())
        for column in rows[0]:
            if column == "t":
                continue
            values = [row[column] for row in rows]
            times = [row["t"] for row in rows if "t" in row]
            result = {"source_file": path.name, "channel": column, "samples": len(rows),
                      "minimum_native": min(values), "median_native": statistics.median(values),
                      "maximum_native": max(values), "timestamp_span_native": "",
                      "timestamp_nonincreasing_intervals": ""}
            if times:
                result.update(timestamp_span_native=int(times[-1] - times[0]),
                              timestamp_nonincreasing_intervals=sum(b <= a for a, b in zip(times, times[1:])))
            records.append(result)
    return records


def flight_records(path):
    records = []
    with zipfile.ZipFile(path) as archive:
        for name in sorted(n for n in archive.namelist() if n.endswith(".csv")):
            rows = get_numeric_table(archive.read(name))
            times = [r["t"] for r in rows]
            intervals = [b-a for a, b in zip(times, times[1:])]
            inputs = [f"m{i}_rads" for i in range(1, 5)]
            outputs = ["x","y","z","vx","vy","vz","qx","qy","qz","qw","wx","wy","wz"]
            if not set(inputs + outputs) <= rows[0].keys():
                raise ValueError("Unexpected flight schema")
            records.append({"source_file": name, "official_split": name.split("/")[0],
                            "samples": len(rows), "span_s": round(times[-1]-times[0], 6),
                            "median_interval_s": round(statistics.median(intervals), 8),
                            "nonincreasing_intervals": sum(dt <= 0 for dt in intervals),
                            "observed_motor_speed_channels": len(inputs), "state_output_channels": len(outputs)})
    return records


def main():
    inputs, output = map(Path, sys.argv[1:])
    output.mkdir(exist_ok=True, parents=True)
    sources = json.loads((HERE / "sources.json").read_text())
    for item in (sources["uci"], sources["nano_drone"]):
        verify(inputs / item["local_name"], item["sha256"])
    write_csv(output / "uci-failure-episodes.csv", uci_records(inputs / sources["uci"]["local_name"]))
    write_csv(output / "wrist-conditions-channels.csv", zenodo_records(inputs / "zenodo", sources["zenodo"]["files"]))
    write_csv(output / "nano-drone-runs.csv", flight_records(inputs / sources["nano_drone"]["local_name"]))


if __name__ == "__main__":
    main()
