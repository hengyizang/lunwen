"""Summarize six commanded cycles and three separate no-load torque sweeps."""
import argparse
import csv
import hashlib
import io
import math
from pathlib import Path
from zipfile import ZipFile

SOURCE_MD5 = "04bf59f344a04b76a7c3907ee032ab9f"
ROOT = "PM_synchronous_motor/Measurement_results"


def read_pairs(z, name, header):
    data = z.read(name).decode("utf-8-sig")
    rows = list(csv.reader(io.StringIO(data)))
    if rows[0] == header:
        rows = rows[1:]
    pairs = [tuple(map(float, row)) for row in rows]
    if not all(len(r) == 2 and all(map(math.isfinite, r)) for r in pairs):
        raise ValueError(f"Malformed data: {name}")
    return list(zip(*pairs))


def cycles(z):
    results = []
    for profile in ("Mid_sized_vehicle", "Small_sized_vehicle"):
        for cycle in ("Artemis", "Bcdc", "Wltp"):
            drive = f"{ROOT}/Drive_cycle_torque_speed_data/{profile}/{cycle}"
            power = f"{ROOT}/Drive_cycle_measurement_results/{profile}/{cycle}"
            t, torque = read_pairs(z, f"{drive}_torque_nm.csv", ["Time", "Torque"])
            ts, speed = read_pairs(z, f"{drive}_speed_rpm.csv", ["Time", "Speed"])
            ti, pin = read_pairs(z, f"{power}_input_power.csv", ["Time", "Power"])
            to, pout = read_pairs(z, f"{power}_output_power.csv", ["Time", "Power"])
            if not (t == ts == ti == to and all(y-x == 0.5 for x, y in zip(t, t[1:]))):
                raise ValueError(f"Unaligned or irregular cycle: {profile}/{cycle}")
            # Rated torque is 0.10 Nm; maximum torque and speed are 0.15 Nm / 7050 rpm (Table 6).
            results.append(dict(profile=profile, cycle=cycle, aligned_samples=len(t), span_s=t[-1]-t[0],
                                step_s=0.5, min_torque_input_Nm=min(torque), max_torque_input_Nm=max(torque),
                                max_abs_torque_input_Nm=max(map(abs,torque)),
                                torque_input_at_or_above_max_count=sum(abs(x)>=0.15 for x in torque),
                                peak_speed_input_rpm=max(speed), speed_input_at_max_count=speed.count(7050.0),
                                measured_input_power_min_W=min(pin), measured_input_power_max_W=max(pin),
                                measured_output_power_min_W=min(pout), measured_output_power_max_W=max(pout)))
    return results


def no_load(z):
    out = []
    for day, rotor, warmup in [("20231005", "outside stator", "90"),
                               ("20231017", "outside stator", "120"),
                               ("20231018", "inside stator", "120")]:
        name = f"{ROOT}/No_load_tests/M{day}.csv"
        speed, torque = read_pairs(z, name, ["Speed","Torque"])
        if len(set(speed)) != len(speed) or any(y>=x for x,y in zip(speed,speed[1:])):
            raise ValueError(f"Unexpected sweep order: {name}")
        out.append(dict(source_member=name, rotor_location=rotor, stated_warmup_minutes=warmup,
                        speed_settings=len(speed), min_speed_rpm=min(speed), max_speed_rpm=max(speed),
                        measured_min_torque_Nm=min(torque), measured_max_torque_Nm=max(torque),
                        measured_torque_at_min_speed_Nm=torque[-1], measured_torque_at_max_speed_Nm=torque[0]))
    return out


def write_csv(path, rows):
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0], lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    with args.archive.open("rb") as source:
        if hashlib.file_digest(source, "md5").hexdigest() != SOURCE_MD5:
            raise ValueError("Archive differs from 10.3217/sns1d-77m43")
    with ZipFile(args.archive) as z:
        write_csv(args.output_dir / "creator-drive-cycles.csv", cycles(z))
        write_csv(args.output_dir / "creator-no-load.csv", no_load(z))
