"""Summarize the MIT MCube repeated-push validation grid without resampling its three clocks."""
import argparse
import csv
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median
from zipfile import ZipFile

ARCHIVE_SHA256 = "c68b7a1739cf433cc385fe09bdf60f4a4d85b440eb1131e11ecf3c64713005a7"
EXCLUSIONS_SHA256 = "b271a915b4e9ec0d43c4a07683ec8a70a67f77841b39f193190b50fc3149a0f8"
FILENAME = re.compile(
    r"motion_surface=plywood_shape=rect1_a=0_v=20_i=([0-3]\.000)_s=([01]\.\d{3})"
    r"_t=(-?\d\.\d{3})_rep=(\d{4})\.json"
)


def verify_file(path, expected):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    if digest.hexdigest() != expected:
        raise ValueError(f"Unrecognised source bytes: {path}")


def summarize(member, source):
    record = json.loads(source)
    if set(record) != {"object_pose", "tip_pose", "ft_wrench"}:
        raise ValueError(f"Unexpected source keys: {member}")
    spans = []
    stats = {}
    for name, field in (("wrench", "ft_wrench"), ("tip", "tip_pose"), ("object", "object_pose")):
        stream = record[field]
        if not stream or any(len(row) != 4 or not all(math.isfinite(x) for x in row) for row in stream):
            raise ValueError(f"Missing or invalid numeric values: {member} {field}")
        times = [row[0] for row in stream]
        stats[name + "_rows"] = len(stream)
        stats[name + "_backward_steps"] = sum(b < a for a, b in zip(times, times[1:]))
        stats[name + "_equal_time_steps"] = sum(b == a for a, b in zip(times, times[1:]))
        spans.append((min(times), max(times)))
    stats["shared_time_extent_s"] = max(0.0, min(b for a, b in spans) - max(a for a, b in spans))
    wrench = record["ft_wrench"]
    stats["max_planar_force_N"] = max(math.hypot(row[1], row[2]) for row in wrench)
    stats["max_abs_Mz_Nm"] = max(abs(row[3]) for row in wrench)
    for field, name in (("tip_pose", "tip"), ("object_pose", "object")):
        first = min(record[field], key=lambda row: row[0])
        last = max(record[field], key=lambda row: row[0])
        stats[name + "_net_xy_displacement_m"] = math.hypot(last[1] - first[1], last[2] - first[2])
    return stats


def save(path, records):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=records[0], lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)


def derive(archive, exclusions, output):
    verify_file(archive, ARCHIVE_SHA256)
    verify_file(exclusions, EXCLUSIONS_SHA256)
    excluded = set(exclusions.read_text(encoding="ascii").splitlines())
    groups = defaultdict(list)
    counts = Counter()
    seen = set()
    found_exclusions = set()
    candidates = {}
    with ZipFile(archive) as data:
        for member in data.infolist():
            if member.is_dir():
                continue
            name = Path(member.filename).name
            if name in seen:
                raise ValueError(f"Duplicate name: {name}")
            seen.add(name)
            match = FILENAME.fullmatch(name)
            if not match:
                raise ValueError(f"Unknown trial naming: {name}")
            side, point, angle, rep = match.groups()
            if side != "0.000":
                continue
            key = (int(round(float(point)*10)), int(round(float(angle)*10)))
            counts[key] += 1
            if name in excluded:
                found_exclusions.add(name)
                continue
            contents = data.read(member)
            metrics = summarize(name, contents)
            groups[key].append(metrics)
            if key not in candidates or int(rep) < candidates[key]["repeat_index"]:
                candidates[key] = dict(member=name, repeat_index=int(rep), sha256=hashlib.sha256(contents).hexdigest(), **metrics)
    if len(seen) != 35130 or len(counts) != 341 or set(counts.values()) != {100} or found_exclusions != excluded:
        raise ValueError("Archive or exclusion coverage changed")
    result, examples = [], []
    for key, records in sorted(groups.items()):
        condition = {"side": 0, "fraction_along_side": key[0] / 10, "push_angle_rad": key[1] / 10}
        summary = dict(condition, archive_trials=counts[key], publisher_excluded=counts[key]-len(records), kept_trials=len(records))
        for field in records[0]:
            values = [r[field] for r in records]
            if field.endswith(("_rows", "_steps")):
                summary[field] = sum(values)
            else:
                summary["median_of_trial_" + field] = median(values)
        result.append(summary)
        examples.append(dict(condition, **candidates[key]))
    output.mkdir(parents=True, exist_ok=True)
    save(output / "push-validation-conditions.csv", result)
    save(output / "push-validation-examples.csv", examples)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("unreliable_list", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    derive(args.archive, args.unreliable_list, args.output)
