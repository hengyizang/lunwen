"""Rebuild an independent alignment of PCD trial CSVs and BrainVision response codes."""
import argparse
import csv
import io
import re
import zipfile
from collections import defaultdict
from pathlib import Path

import numpy as np

from measure import HERE, read_input, save

# Sensor acquisition rates: button filename specifies 5000 Hz; 1000 Hz hypotheses for other
# two series were checked against six ~60-s CSV trials and the intervals between trial pulses.
SETUPS = [
    ("button", "Button5000HzDataset.zip", "Validation_button_5000hz.vmrk", "2023-11-30_06-02-53", 1, 4, 5000, "button1", -1),
    ("sound", "SoundDataset.zip", "Validation_sound_2.vmrk", "2023-11-30_04-21-31", 5, 4, 1000, "motor_1_vibrate_software", 1),
    ("motor", "MotorDataset.zip", "Validatoin_motor_2.vmrk", "2023-11-30_01-32-00", 5, 4, 1000, "motor_1_vibrate_software", 1),
]


def stats(kind, trial, starts, values):
    x = np.asarray(values)
    return [kind, trial, starts, len(x), int((x < 0).sum()),
            *[round(float(v), 3) for v in (x.mean(), np.median(x), np.percentile(x, 95), x.min(), x.max())]]


def analyze(setup, data):
    kind, _, marker, stamp, acode, mcode, hz, field, sign = setup
    markers = defaultdict(list)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for code, tick in re.findall(rb"^Mk\d+=Response,\s*R\s*(\d+),(\d+)", z.read(marker), re.M):
            markers[int(code)].append(int(tick))
        trials = {int(n.rsplit("=", 1)[1].split(".")[0]): n for n in z.namelist()
                  if not n.startswith("__") and stamp in n and n.endswith(".csv")}
        if len(trials) != len(markers[acode]):
            raise ValueError("Number of candidate trial anchors changed")
        total_starts, pooled = 0, []
        for trial, t0 in zip(sorted(trials), markers[acode]):
            with z.open(trials[trial]) as f:
                reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig"))
                t, state = [], []
                for row in reader:
                    t.append(float(row["timestamp"]))
                    state.append(float(row[field]))
            rises = np.array(t)[1:][np.diff(state) > 0]
            detected = (np.array(markers[mcode]) - t0) / hz
            used_detections = set()
            values = []
            for trigger in rises:
                k = int(np.argmin(np.abs(detected - trigger)))
                delay = 1000 * sign * (detected[k] - trigger)
                if k not in used_detections and abs(delay) < 100:
                    values.append(delay)
                    used_detections.add(k)
            total_starts += len(rises)
            pooled.extend(values)
            yield stats(kind, trial, len(rises), values)
        yield stats(kind, "pooled", total_starts, pooled)


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--cache", type=Path)
    parser.add_argument("--output", type=Path, default=HERE)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    with (HERE / "file-manifest.csv").open() as f:
        files = {row["file"]: row for row in csv.DictReader(f)}
    rows = []
    for setup in SETUPS:
        rows.extend(analyze(setup, read_input(files[setup[1]], args.cache)))
    save(args.output / "pcd-paired-delay.csv",
         ["channel", "trial", "software_rising_edges", "matched", "negative_delta", "mean_ms",
          "median_ms", "p95_ms", "min_ms", "max_ms"], rows)


if __name__ == "__main__":
    main()
