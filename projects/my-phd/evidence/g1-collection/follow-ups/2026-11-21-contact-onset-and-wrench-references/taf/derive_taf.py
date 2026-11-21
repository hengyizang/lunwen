"""Summarize TaF numeric records and eight canonical tactile videos (NumPy, PyArrow, ffprobe).

Input is a local snapshot of jiamig/taf-dataset at 239c8ee8156bf11eb6d6c11c004f9a8721528d9d.
Include all numerical partitions, all meta/info.json and all published meta/episodes parquet.
Include each *_obj1 canonical video and both canonical and sidecar videos in the two
sequences whose numerical tables extend beyond their declared ranges.
Expected SHA-256 identifiers are given in the result tables and HTTP record in taf-source.json.
"""
import argparse
import csv
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess

import numpy as np
import pyarrow.parquet as pq


def digest(path):
    with path.open("rb") as source:
        return sha256(source.read()).hexdigest()


def write(path, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0], lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def sequence_summary(path, base):
    table = pq.read_table(path)
    expected = {"observation.pressure_matrix", "observation.force_torque",
                "timestamp", "frame_index", "episode_index", "index", "task_index"}
    if set(table.column_names) != expected:
        raise ValueError(f"Unexpected fields: {path}")
    if any(table[c].null_count for c in table.column_names):
        raise ValueError(f"Null top-level entries: {path}")
    wrench = table["observation.force_torque"].combine_chunks().values.to_numpy().reshape(-1, 6)
    pressure = table["observation.pressure_matrix"].combine_chunks()
    if not (np.all(np.diff(pressure.offsets.to_numpy()) == 12) and
            np.all(np.diff(pressure.flatten().offsets.to_numpy()) == 12)):
        raise ValueError(f"Map dimensions changed: {path}")
    matrix = pressure.flatten().flatten().to_numpy().reshape(-1, 144)
    n = len(table)
    ep = table["episode_index"].to_numpy()
    frame = table["frame_index"].to_numpy()
    idx = table["index"].to_numpy()
    times = table["timestamp"].to_numpy()
    start = np.r_[0, np.flatnonzero(ep[1:] != ep[:-1]) + 1]
    end = np.r_[start[1:], n]
    length = end - start
    if not (np.array_equal(idx, np.arange(n)) and np.all(frame[start] == 0)
            and np.array_equal(frame, idx - np.repeat(start, length))
            and np.array_equal(ep[start], np.arange(len(start)))):
        raise ValueError(f"Unexpected row/episode index: {path}")
    if not np.isfinite(times).all():
        raise ValueError(f"Missing packaged timestamp: {path}")
    valid = np.all(np.isfinite(wrench), axis=1) & np.all(np.isfinite(matrix), axis=1)
    w = wrench[valid]
    m = matrix[valid]
    pressure_sum = np.sum(m, axis=1, dtype=np.float64)
    any_pressure = np.any(m > 0, axis=1)
    zero_wrench = np.all(w == 0, axis=1)
    correlation = ""
    if len(w) >= 2 and np.ptp(w[:, 2]) > 0 and np.ptp(pressure_sum) > 0:
        correlation = round(np.corrcoef(-w[:, 2], pressure_sum)[0, 1], 7)
    name = path.relative_to(base).parts[2]
    config, local_id = re.fullmatch(r"(.+)_obj(\d+)", name).groups()
    seq = path.parents[2]
    info_path = seq / "meta/info.json"
    info = json.loads(info_path.read_text())
    declared_rows, declared_episodes = info["total_frames"], info["total_episodes"]
    if info["fps"] != 30 or not (0 < declared_episodes <= len(start)) or end[declared_episodes-1] != declared_rows:
        raise ValueError(f"Declared prefix does not follow numerical episode boundaries: {seq}")
    meta_paths = list(seq.glob("meta/episodes/*/*.parquet"))
    meta_hash = ""
    if meta_paths:
        meta_path, = meta_paths
        meta = pq.read_table(meta_path, columns=["length", "dataset_from_index", "dataset_to_index"])
        if not (np.array_equal(meta["length"].to_numpy(), length[:declared_episodes]) and
                np.array_equal(meta["dataset_from_index"].to_numpy(), start[:declared_episodes]) and
                np.array_equal(meta["dataset_to_index"].to_numpy(), end[:declared_episodes])):
            raise ValueError(f"Published episode index differs from declared prefix: {seq}")
        meta_hash = digest(meta_path)
    return dict(sequence=name, config_as_archived=config, local_object_id=int(local_id),
                info_sha256=digest(info_path), episode_metadata_sha256=meta_hash,
                declared_frames=declared_rows, declared_episodes=declared_episodes,
                additional_numerical_rows=n-declared_rows,
                positive_map_rows_in_declared_prefix=int(np.sum(np.any(matrix[:declared_rows] > 0, axis=1) & valid[:declared_rows])),
                parquet_path=path.relative_to(base).as_posix(), sha256=digest(path),
                rows=n, packaged_episodes=len(start), episodes_3000_rows=int(np.sum(length == 3000)),
                paired_finite_rows=int(valid.sum()), all_zero_wrench_rows=int(zero_wrench.sum()),
                all_zero_matrix_rows=int(np.sum(np.all(m == 0, axis=1))),
                positive_taxel_rows=int(any_pressure.sum()),
                positive_map_and_zero_wrench_rows=int(np.sum(any_pressure & zero_wrench)),
                map_sum_min=float(pressure_sum.min()), map_sum_max=float(pressure_sum.max()),
                fz_min_as_stored=float(w[:, 2].min()), fz_max_as_stored=float(w[:, 2].max()),
                correlation_minus_fz_map_sum=correlation,
                max_frame_index_over_30_time_error_us=round(float(np.abs(times-frame/30).max()*1e6), 5))


def video_check(base, row):
    seq = (base / row["parquet_path"]).parents[2]
    info_path = seq / "meta/info.json"
    info = json.loads(info_path.read_text())
    meta_path, = seq.glob("meta/episodes/*/*.parquet")
    meta = pq.read_table(meta_path, columns=["length", "dataset_from_index", "dataset_to_index",
                                             "videos/observation.image/from_timestamp",
                                             "videos/observation.image/to_timestamp"])
    video_path, = seq.glob("videos/observation.image/*/*.mp4")
    def read_video(file):
        stream, = json.loads(subprocess.check_output([
        "ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets", "-show_entries",
        "stream=width,height,r_frame_rate,nb_read_packets,nb_frames,duration,codec_name",
        "-of", "json", str(file)]))["streams"]
        return stream
    stream = read_video(video_path)
    starts = meta["dataset_from_index"].to_numpy()
    ends = meta["dataset_to_index"].to_numpy()
    if (not np.array_equal(ends-starts, meta["length"].to_numpy()) or
        starts[0] != 0 or not np.array_equal(ends[:-1], starts[1:]) or
        ends[-1] != row["declared_frames"] or info["total_episodes"] != len(meta) or
        info["total_frames"] != row["declared_frames"] or len(meta) != row["declared_episodes"]):
        raise ValueError(f"Metadata coverage mismatch: {seq}")
    t0 = meta["videos/observation.image/from_timestamp"].to_numpy()
    t1 = meta["videos/observation.image/to_timestamp"].to_numpy()
    if int(stream["nb_read_packets"]) != row["declared_frames"] or int(stream["nb_frames"]) != row["declared_frames"]:
        raise ValueError(f"Canonical video does not cover the declared range: {seq}")
    sidecars = list(seq.glob("tmp*/*.mp4"))
    side_name, side_hash, side_packets = "", "", ""
    if row["additional_numerical_rows"]:
        side, = sidecars
        side_name = side.relative_to(seq).as_posix()
        side_hash = digest(side)
        side_packets = int(read_video(side)["nb_read_packets"])
    return dict(sequence=row["sequence"], rows=row["rows"], metadata_episodes=len(meta),
                declared_frames=row["declared_frames"], additional_numeric_rows=row["additional_numerical_rows"],
                sidecar_path=side_name, sidecar_sha256=side_hash, sidecar_video_packets=side_packets,
                info_sha256=digest(info_path), episode_meta_sha256=digest(meta_path),
                mp4_sha256=digest(video_path), video_codec=stream["codec_name"],
                video_width=stream["width"], video_height=stream["height"], nominal_rate=stream["r_frame_rate"],
                video_frames_in_header=int(stream["nb_frames"]), demuxed_video_packets=int(stream["nb_read_packets"]),
                max_segment_time_vs_index_over_30_ms=round(1000*max(np.abs(t0-starts/30).max(),
                                                                     np.abs(t1-ends/30).max()), 8))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    files = sorted(args.snapshot.glob("taf_dataset/*/*/data/*/*.parquet"))
    if len(files) != 408:
        raise ValueError("Expected all 408 published numerical partitions")
    rows = [sequence_summary(path, args.snapshot) for path in files]
    if len({row["sha256"] for row in rows}) != 408:
        raise ValueError("Duplicate numerical file")
    videos = [video_check(args.snapshot, row) for row in rows if row["local_object_id"] == 1 or row["additional_numerical_rows"]]
    assert len(videos) == 8
    args.output.mkdir(parents=True, exist_ok=True)
    write(args.output / "taf-sequences.csv", rows)
    write(args.output / "taf-video-checks.csv", videos)


if __name__ == "__main__":
    main()
