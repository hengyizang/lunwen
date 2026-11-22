"""Summarize the public BAM servo recordings with Python 3.10+ (stdlib only)."""
import argparse
import csv
import hashlib
import io
import json
import math
import statistics
import tarfile
import urllib.request
import zipfile
from collections import defaultdict
from pathlib import Path

HF = "https://huggingface.co/buckets/Gregwar/bam_data/resolve/"
WAVE = "https://github.com/i1Cps/duck_mini_pro_headless/releases/download/st3025-bam-data-v1/"
INPUTS = [
    ("mx64_raw.tgz", "MX64", "44a75abd970e66516b0c65b21554eab904775f3afc1136ec62f6edff1a077ef4"),
    ("mx106_raw.tgz", "MX106", "04249451a338d0cd83017448a8701166baf3af66a52b8b8d7d2501315ae1cef5"),
    ("xl320_raw.tgz", "XL320", "bd100ec940761fead99c6383d049a8357e39241e46c6f8990427bfb42c704e53"),
    ("xl330_raw.zip", "XL330", "d308d126585235264cd4045b4702e35992fe36a9bb6b4a280987ba6ae5f09546"),
    ("feetech_sts3215_raw.zip", "STS3215", "1410a376d2b9bf3ce708e412c1816efbf269a5b1c01695c00c005bb4a0937bde"),
    ("waveshare_st3025_raw.zip", "ST3025", "ae103fe4f05d825005944a860c5de0a0505cd629698b3b54f1f8ff0404120017"),
]


def records(data, suffix):
    if suffix == ".zip":
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            for entry in sorted(archive.namelist()):
                if entry.endswith(".json") and "__MACOSX" not in entry and not Path(entry).name.startswith("._"):
                    yield entry, json.loads(archive.read(entry))
    else:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r|gz") as archive:
            for entry in archive:
                if entry.isfile() and entry.name.endswith(".json"):
                    yield entry.name, json.load(archive.extractfile(entry))


def emit(path, rows):
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0], lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def summarize(args):
    receipts, groups, episodes = [], [], []
    for name, motor, expected in INPUTS:
        url = WAVE + name if motor == "ST3025" else HF + name + "?download=true"
        if args.cache:
            data = (args.cache / name).read_bytes()
        else:
            with urllib.request.urlopen(url, timeout=120) as response:
                data = response.read()
        actual = hashlib.sha256(data).hexdigest()
        if actual != expected:
            raise ValueError(f"Input changed: {name} ({actual})")
        receipts.append(dict(motor=motor, archive=name, url=url, bytes=len(data), sha256=actual))
        by_task = defaultdict(list)
        for member, log in records(data, Path(name).suffix):
            if not isinstance(log, dict) or "entries" not in log:
                continue
            rows = log["entries"]
            if not rows:
                raise ValueError(f"Empty log: {member}")
            active = [row for row in rows if row["torque_enable"] is True]
            errors = [abs(row["goal_position"] - row["position"]) for row in active]
            readouts = [row["load"] for row in active]
            assert all(math.isfinite(v) for v in errors + readouts)
            # XL330 record.py reads Present PWM and normalizes by 885 counts.
            # For other models "load" has a different meaning.
            positive = sum(v == 1.0 for v in readouts) if motor == "XL330" else 0
            negative = sum(v == -1.0 for v in readouts) if motor == "XL330" else 0
            by_task[log["trajectory"]].append({
                "n": len(rows), "on": len(active), "sum_error": math.fsum(errors),
                "lo": min(readouts, default=None), "hi": max(readouts, default=None),
                "positive": positive, "negative": negative,
            })
            if positive + negative:
                # Run boundaries follow source row order. Disabled samples, sub-boundary
                # samples and sign changes all start a new run.
                runs = []
                for i, row in enumerate(rows):
                    if row["torque_enable"] is True and abs(row["load"]) == 1.0:
                        if i and runs and runs[-1][-1] == i - 1 and rows[i - 1]["load"] == row["load"]:
                            runs[-1].append(i)
                        else:
                            runs.append([i])
                for idx in runs:
                    part = [rows[i] for i in idx]
                    med = statistics.median(abs(r["goal_position"] - r["position"]) for r in part)
                    episodes.append(dict(archive=name, member=member, trajectory=log["trajectory"],
                        mass_kg=log["mass"], length_m=log["length"], kp=log["kp"],
                        first_entry_index0=idx[0], last_entry_index0=idx[-1], samples=len(idx),
                        first_s=f"{part[0]['timestamp']:.6f}", last_s=f"{part[-1]['timestamp']:.6f}",
                        reported_duty=part[0]["load"], median_abs_tracking_error_rad=f"{med:.6f}",
                        min_input_V=min(r["input_volts"] for r in part),
                        max_input_V=max(r["input_volts"] for r in part)))
        for task, logs in sorted(by_task.items()):
            n = sum(log["n"] for log in logs)
            on = sum(log["on"] for log in logs)
            lo = [log["lo"] for log in logs if log["lo"] is not None]
            hi = [log["hi"] for log in logs if log["hi"] is not None]
            pos = sum(log["positive"] for log in logs)
            neg = sum(log["negative"] for log in logs)
            groups.append(dict(motor=motor, trajectory=task, logs=len(logs), samples=n, enabled=on,
                enabled_mae_rad=f"{math.fsum(log['sum_error'] for log in logs) / on:.6f}" if on else "",
                enabled_load_field_min=min(lo, default=""), enabled_load_field_max=max(hi, default=""),
                enabled_at_plus_one_pwm=pos if motor == "XL330" else "",
                enabled_at_minus_one_pwm=neg if motor == "XL330" else "",
                logs_at_pwm_boundary=sum(log["positive"]+log["negative"] > 0 for log in logs) if motor == "XL330" else ""))
    args.out.mkdir(parents=True, exist_ok=True)
    emit(args.out / "archive-receipts.csv", receipts)
    emit(args.out / "servo-waveform-summary.csv", groups)
    emit(args.out / "xl330-pwm-boundary-runs.csv", sorted(episodes, key=lambda r:(r["member"], r["first_entry_index0"])))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, help="Directory with the six exact archives. Omit to fetch them.")
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parent)
    summarize(parser.parse_args())
