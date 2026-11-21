"""Recompute the selected REASSEMBLE v1.0.0 wrist-and-segment summaries.

Usage: python derive_reassemble.py DATA_DIRECTORY SPLITS_ZIP OUTPUT_DIRECTORY
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

import h5py
import numpy as np


CHANNELS = ("measured_force", "measured_torque", "compensated_base_force", "compensated_base_torque")


def checksum(path, algorithm):
    with path.open("rb") as source:
        return hashlib.file_digest(source, algorithm).hexdigest()


def write_csv(path, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys(), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def segment_row(file, index, skill, group, parent, origin, data):
    start, end = float(group["start"][()]), float(group["end"][()])
    if end < start:
        raise ValueError(f"Negative duration: {file} segment {index}/{skill}")
    row = dict(file=file, high_index=index, skill_index=skill,
               level="action" if skill == "" else "skill", parent_action=parent,
               text=group["text"][()].decode(), success=int(group["success"][()]),
               start_wrt_first_wrist_s=round(start-origin, 6),
               end_wrt_first_wrist_s=round(end-origin, 6), duration_s=round(end-start, 6))
    for channel in CHANNELS:
        t, norms = data[channel]
        values = norms[(t >= start) & (t < end)]
        row[channel + "_samples"] = len(values)
        for label, q in (("median", 0.5), ("p95", 0.95)):
            row[channel + "_norm_" + label] = round(float(np.quantile(values, q)), 6) if len(values) else ""
    return row


def read_recording(path, role):
    all_rows = []
    recording = {"file": path.name, "split": role}
    with h5py.File(path, "r") as file:
        data = {}
        for c in CHANNELS:
            t = np.asarray(file["timestamps"][c], dtype=np.float64)
            x = np.asarray(file["robot_state"][c], dtype=np.float64)
            if x.shape != (len(t), 3) or not np.isfinite(t).all() or not np.isfinite(x).all():
                raise ValueError(f"Unexpected shape/nonfinite entries: {path.name}, {c}")
            steps = np.diff(t)
            recording[c + "_samples"] = len(t)
            recording[c + "_nonpositive_steps"] = int((steps <= 0).sum())
            recording[c + "_median_step_ms"] = round(float(np.median(steps)*1000), 6)
            data[c] = t, np.linalg.norm(x, axis=1)
        for label, a, b in (("measured", CHANNELS[0], CHANNELS[1]),
                            ("compensated", CHANNELS[2], CHANNELS[3])):
            recording[label + "_force_torque_timestamps_equal"] = int(np.array_equal(data[a][0], data[b][0]))
        origin = data["measured_force"][0][0]
        segments = file["segments_info"]
        for index in sorted(segments, key=int):
            group = segments[index]
            high = segment_row(path.name, index, "", group, "", origin, data)
            all_rows.append(high)
            if "low_level" in group:
                skills = group["low_level"]
                for skill in sorted(skills, key=int):
                    all_rows.append(segment_row(path.name, index, skill, skills[skill], high["text"], origin, data))
    recording["high_level_segments"] = sum(r["level"] == "action" for r in all_rows)
    recording["nested_skills"] = len(all_rows) - recording["high_level_segments"]
    return recording, all_rows


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for arg in ("data_directory", "splits_zip", "output_directory"):
        p.add_argument(arg, type=Path)
    args = p.parse_args()
    source = json.loads(Path(__file__).with_name("reassemble-source.json").read_text())
    if checksum(args.splits_zip, "md5") != "641882928ef3a8b2c3db41ac7c60b994":
        raise ValueError("splits.zip does not match the deposit")
    with ZipFile(args.splits_zip) as z:
        split = {kind:set(z.read(kind + "_split1.txt").decode().splitlines()) for kind in ("train", "test")}
    if split["train"] & split["test"]:
        raise ValueError("Overlapping official splits")
    inventory, recordings, segments = [], [], []
    for member in sorted(source["archive_members"], key=lambda r:r["file"]):
        name = Path(member["file"])
        role = next((s for s in split if name.stem in split[s]), "unlisted")
        selected = member["cs"] <= 100_000_000
        inventory.append(dict(file=name.name, compressed_bytes=member["cs"], uncompressed_bytes=member["size"],
                              crc32=member["crc32"], split=role, selected=int(selected)))
        if selected:
            path = args.data_directory / name.name
            if path.stat().st_size != member["size"] or checksum(path, "sha256") != member["selected_sha256"]:
                raise ValueError(f"Archive member mismatch: {path}")
            recording, rows = read_recording(path, role)
            recordings.append(recording)
            segments.extend(rows)
    if (split["train"] | split["test"]) - {Path(x["file"]).stem for x in inventory}:
        raise ValueError("Split lists a non-existing recording")
    args.output_directory.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_directory / "reassemble-archive-splits.csv", inventory)
    write_csv(args.output_directory / "reassemble-recordings.csv", recordings)
    write_csv(args.output_directory / "reassemble-segments.csv", segments)


if __name__ == "__main__":
    main()
