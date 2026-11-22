"""Audit four independent contributor releases linked from Rhoban/bam. Stdlib only."""
import argparse
import hashlib
import io
import json
import math
import urllib.request
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

from replay import emit

SOURCES = {
    "MD300": ("https://github.com/mangdangroboticsclub/bam/releases/download/md300-data-v1/md300_logs.zip",
              "d0ad06eb792c02e94801a91a8fd85c342af4a6f2f82b99c413e2f5c1ebbdf1f6"),
    "J288": ("https://github.com/lachlanhurst/bam/releases/download/unitree-j288-v1.0.0/unitree_j288_raw.zip",
             "4e617b21c61f2f7667e574dc09555164734333c5b8d98089d17eb9bd7cc007d3"),
    "HLS2915": ("https://raw.githubusercontent.com/Seamus-Z/bam/9b4342661ce56e7ddb9c5331d2a1091434c35fcd/feetech_hls2915_raw.zip",
                "fe99b40a854512b91dd8c416b63c9d759e2129bc5acc4693cd4142f7149b1458"),
    "STS3215-12V": ("https://github.com/T-K-233/bam/releases/download/sts3215-12v-bam-data-v1/feetech_sts3215_12V_raw.zip",
                    "435ddbcbb91d98009b7cc06f41b0f87f5fef2b9aa2fffb853d2cd660744876a3"),
}


def add_range(stats, values):
    if not values:
        return
    low, high = min(values), max(values)
    if not math.isfinite(low) or not math.isfinite(high):
        raise ValueError("Nonfinite value in selected field")
    if stats:
        stats[0] = min(stats[0], low)
        stats[1] = max(stats[1], high)
        stats[2] += len(values)
    else:
        stats.extend([low, high, len(values)])


def main(args):
    receipts, summaries, ranges, current_only, boundaries = [], [], [], [], []
    for motor, (url, digest) in SOURCES.items():
        name = url.rsplit("/", 1)[-1]
        if args.cache:
            data = (args.cache / name).read_bytes()
        else:
            with urllib.request.urlopen(url, timeout=150) as r:
                data = r.read()
        if hashlib.sha256(data).hexdigest() != digest:
            raise ValueError(f"Changed input {name}")
        receipts.append(dict(motor=motor, file=name, url=url, bytes=len(data), sha256=digest))
        counts, stats, modes = defaultdict(Counter), defaultdict(list), set()
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            for path in sorted(archive.namelist()):
                if not path.endswith(".json") or path.startswith("params/") or "/processed/" in path:
                    continue
                run = json.loads(archive.read(path))
                if "entries" not in run:
                    continue
                rows = run["entries"]
                on = [r for r in rows if r["torque_enable"] is True]
                group = path.split("/")[1] if motor in {"MD300", "J288"} else run["trajectory"]
                counts[group].update(logs=1, rows=len(rows), enabled=len(on))
                if motor == "MD300":
                    fields = [("load", "supply-side current readback", "mA"), ("duty_cycle", "recorder reconstruction", "fraction")]
                    for key,unit in [("at32_max_pwm_duty_cycle", "fraction"), ("cur_cap_ma", "mA"), ("at32_live_max_current_mA", "mA")]:
                        if key in run and run[key] is not None:
                            add_range(stats[group,key,"per-run configuration",unit], [run[key]])
                    cap = run["at32_live_max_current_mA"]
                    exceeding = [r for r in on if abs(r["load"]) > cap]
                    if exceeding:
                        boundaries.append(dict(motor=motor, member=path, group=group, field="load",
                            condition=f"abs(supply current readback) > {cap:g} mA configured limit",
                            enabled_condition_samples=len(exceeding), enabled_rows=len(on),
                            first_match_s=f"{exceeding[0]['timestamp']:.6f}",
                            signed_first_value=exceeding[0]["load"],
                            first_abs_tracking_error_rad=f"{abs(exceeding[0]['goal_position']-exceeding[0]['position']):.6f}",
                            first_onboard_current_A=exceeding[0]["load"]/1000))
                    counts[group]["live_pwm_field_samples"] += sum("pwm_duty" in r or "live_pwm_duty" in r for r in on)
                elif motor == "J288":
                    fields = [("goal_torque", "feedforward command", "Nm"), ("torque", "current-derived reply", "Nm")]
                    # Zero per-sample feedback gains isolate the feedforward command.
                    selected = [r for r in on if r["kp"] == 0 and r["kd"] == 0 and r["goal_torque"] != 0]
                    if selected:
                        diffs = [abs(r["goal_torque"] - r["torque"]) for r in selected]
                        current_only.append(dict(member=path, split=group, profile=run["profile"],
                            nonzero_feedforward_zero_feedback_samples=len(diffs),
                            mean_abs_request_vs_reply_Nm=f"{math.fsum(diffs)/len(diffs):.6f}",
                            min_request_Nm=min(r["goal_torque"] for r in selected),
                            max_request_Nm=max(r["goal_torque"] for r in selected)))
                elif motor == "HLS2915":
                    modes.add(run["control_mode"])
                    rails = [r for r in on if abs(r["load"]) == 100.0]
                    if rails:
                        boundaries.append(dict(motor=motor, member=path, group=group, field="load",
                            condition="abs(reported PWM percent) == 100",
                            enabled_condition_samples=len(rails), enabled_rows=len(on),
                            first_match_s=f"{rails[0]['timestamp']:.6f}", signed_first_value=rails[0]["load"],
                            first_abs_tracking_error_rad=f"{abs(rails[0]['goal_position']-rails[0]['position']):.6f}",
                            first_onboard_current_A=rails[0]["measured_current"]))
                    fields = [("measured_current", "onboard current readback", "A"), ("control", "calculated signed voltage", "V")]
                    residual = [abs(r["control"] + r["input_volts"] * r["load"] / 100) for r in on]
                    add_range(stats[group,"control_reconstruction_abs_diff","abs(control + input_volts * load / 100)","V"], residual)
                else:
                    fields = [("load", "recorded load field", "raw")]
                for field, meaning, unit in fields:
                    add_range(stats[group,field,meaning,unit], [r[field] for r in on])
        if motor == "HLS2915":
            assert modes == {"position_voltage"}
        for group,d in sorted(counts.items()):
            summaries.append(dict(motor=motor, group=group, logs=d["logs"], samples=d["rows"], enabled=d["enabled"],
                enabled_with_live_pwm_field=d["live_pwm_field_samples"] if motor=="MD300" else ""))
        for (group,field,meaning,unit),(lo,hi,n) in sorted(stats.items()):
            ranges.append(dict(motor=motor, group=group, field=field, interpretation=meaning, unit=unit,
                               n=n, minimum=f"{lo:.8g}", maximum=f"{hi:.8g}"))
    args.out.mkdir(parents=True, exist_ok=True)
    emit(args.out / "neighbor-receipts.csv", receipts)
    emit(args.out / "neighbor-log-counts.csv", summaries)
    emit(args.out / "neighbor-field-ranges.csv", ranges)
    emit(args.out / "j288-feedforward.csv", current_only)
    emit(args.out / "neighbor-boundary-observations.csv", boundaries)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cache", type=Path, help="Directory holding the four source ZIPs; otherwise download")
    p.add_argument("--out", type=Path, default=Path(__file__).resolve().parent)
    main(p.parse_args())
