"""Summarize CRIA insertion parquet and metadata. Usage: python derive_cria.py DATA_ROOT OUT_DIR.

Requires NumPy and PyArrow. DATA_ROOT is a subset of Hugging Face Joringell/CRIA at
af288f2a470189c3991db73873f9d64171620a43 containing insert/*/{meta,data}.
Video, model and training files are unnecessary.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq

TASKS = ("insert_ni", "insert_plug_2", "insert_plug_3", "insert_typec")
RAW = "observation.state.wrench_raw_chunk"
FILTERED = "observation.state.wrench_filtered_chunk"
VALID = "observation.state.wrench_chunk_valid_len"
COLUMNS = [RAW, FILTERED, VALID, "timestamp_us", "timestamp", "frame_index", "frame_label",
           "episode_index", "interaction_label", "episode_label", "source_id"]


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=rows[0], lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def chunk_values(table, key):
    blocks = table[key].combine_chunks()
    vectors = blocks.flatten()
    if not (np.all(np.diff(blocks.offsets) == 4) and np.all(np.diff(vectors.offsets) == 6)):
        raise ValueError("Unexpected 4x6 wrench layout")
    return vectors.flatten().to_numpy().reshape(-1, 4, 6)


def first(mask):
    indices = np.flatnonzero(mask)
    return int(indices[0]) if indices.size else None


def summarize(root, task, key, annotation, meta, threshold):
    path = root / "insert" / task / annotation["parquet_path"]
    table = pq.read_table(path, columns=COLUMNS)
    n = table.num_rows
    if n != annotation["num_frames"] or n != meta["length"] or not annotation["reviewed"]:
        raise ValueError(f"Unreviewed or mismatched episode: {path}")
    for field, value in (("frame_index", np.arange(n)), ("episode_index", int(key)),
                         ("episode_label", meta["episode_label"]), ("source_id", meta["source_id"])):
        if not np.all(table[field].to_numpy() == value):
            raise ValueError(f"Index/metadata mismatch: {field} {path}")
    label = int(meta["episode_label"])
    if label != annotation["episode_label"] or annotation["source"] != meta["source"]:
        raise ValueError("Different annotation and index outcomes/sources")
    valid = table[VALID].to_numpy()
    if np.any((valid < 0) | (valid > 4)):
        raise ValueError(f"Bad valid length: {path}")
    mask = np.arange(4)[None, :] < valid[:, None]
    raw = chunk_values(table, RAW)
    filtered = chunk_values(table, FILTERED)
    if not (np.isfinite(raw[mask]).all() and np.isfinite(filtered[mask]).all()):
        raise ValueError(f"Non-finite valid wrench: {path}")
    stored = annotation["interaction"]["auto"]
    auto = stored["onset_frame_index"]
    manual = annotation["interaction"]["manual"]["onset_frame_index"]
    frame = table["frame_label"].to_numpy()
    interaction = table["interaction_label"].to_numpy()
    manual_ranges = annotation["anomaly"]["manual"]["ranges"]
    anomaly_mask = np.zeros(n, dtype=bool)
    for start, end in manual_ranges:
        if not (0 <= start <= end < n):
            raise ValueError(f"Bad interval in {path}")
        anomaly_mask[start:end + 1] = True
    if not np.array_equal(frame == 0, anomaly_mask) or not np.isin(frame, [0, 1]).all():
        raise ValueError(f"Anomaly labels disagree with JSON: {path}")
    expected = np.arange(n) >= (n if manual is None else manual)
    if not np.array_equal(interaction, expected):
        raise ValueError(f"Interaction labels disagree with JSON: {path}")
    force = np.linalg.norm(filtered[:, :, :3], axis=2)
    first_slot = (valid > 0) & (force[:, 0] > threshold)
    full_window = np.any(mask & (force > threshold), axis=1)
    first_hit, any_hit = first(first_slot), first(full_window)
    first_peak = np.max(force[valid > 0, 0])
    first_peak_agrees = np.isclose(first_peak, stored["max_force_norm"], rtol=1e-5, atol=1e-5)
    stamps = table["timestamp_us"].to_numpy()
    dt = np.diff(stamps)
    signal_hash = hashlib.sha256(valid.astype("<i8").tobytes() + raw[mask].astype("<f8").tobytes()).hexdigest()
    baseline = None
    if manual is not None and manual >= 30:
        # Windows contain 15 control frames each and never overlap or cross the manual onset.
        slots_start = mask[:15]
        slots_late = mask[manual - 15:manual]
        if slots_start.any() and slots_late.any():
            early = np.median(raw[:15, :, 3:][slots_start], axis=0)
            late = np.median(raw[manual - 15:manual, :, 3:][slots_late], axis=0)
            baseline = dict(task=task, episode=int(key), source=meta["source"], success=label,
                            manual_proximity_frame=manual, start_window_torque_vectors=int(slots_start.sum()),
                            late_window_first_frame=manual-15, late_window_torque_vectors=int(slots_late.sum()),
                            start_tx=round(float(early[0]),8), start_ty=round(float(early[1]),8),
                            start_tz=round(float(early[2]),8), late_tx=round(float(late[0]),8),
                            late_ty=round(float(late[1]),8), late_tz=round(float(late[2]),8),
                            norm_late_minus_start=round(float(np.linalg.norm(late-early)),8))
    episode = dict(task=task, episode=int(key), source=meta["source"], data_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                valid_raw_signal_sha256=signal_hash, frames=n, valid_wrenches=int(valid.sum()),
                padded_slots=int(mask.size - mask.sum()), frames_with_less_than_4=int((valid < 4).sum()),
                min_step_us=int(dt.min()), max_step_us=int(dt.max()), nominal_grid_tolerance_1us=int(np.all(np.abs(dt - 1e6/30) <= 1)),
                success=label, anomalous_frames=int(anomaly_mask.sum()), manual_anomaly_ranges=len(manual_ranges),
                nominal_to_anomalous_runs=int(anomaly_mask[0]) + int((~anomaly_mask[:-1] & anomaly_mask[1:]).sum()),
                manual_proximity_frame=manual, deposited_auto_frame=auto, first_slot_threshold_frame=first_hit,
                any_valid_slot_threshold_frame=any_hit, first_slot_matches_auto=int(first_hit == auto),
                first_slot_peak_matches_auto=int(first_peak_agrees), any_slot_matches_auto=int(any_hit == auto),
                auto_minus_manual_frames=auto-manual if manual is not None and auto is not None else "",
                auto_minus_manual_ms=round((stamps[auto]-stamps[manual])/1000,3) if manual is not None and auto is not None else "",
                pre_proximity_any_slot_threshold_frames=int((full_window & ~expected).sum()) if manual is not None else "",
                filtered_force_first_slot_peak=round(float(first_peak),6), filtered_force_any_valid_slot_peak=round(float(force[mask].max()),6))
    return episode, baseline


def group(task, source, rows):
    diffs = [r["auto_minus_manual_frames"] for r in rows if r["auto_minus_manual_frames"] != ""]
    return dict(task=task, source=source, episodes=len(rows), successful=sum(r["success"] for r in rows),
                frames=sum(r["frames"] for r in rows), valid_wrenches=sum(r["valid_wrenches"] for r in rows),
                padded_slots=sum(r["padded_slots"] for r in rows), anomaly_episodes=sum(r["anomalous_frames"]>0 for r in rows),
                success_with_anomaly=sum(r["success"] and r["anomalous_frames"]>0 for r in rows),
                failed_without_anomaly=sum(not r["success"] and r["anomalous_frames"]==0 for r in rows),
                annotated_anomaly_ranges=sum(r["manual_anomaly_ranges"] for r in rows),
                anomalous_frames=sum(r["anomalous_frames"] for r in rows),
                manual_frame_available=sum(r["manual_proximity_frame"] is not None for r in rows),
                manual_only=sum(r["manual_proximity_frame"] is not None and r["deposited_auto_frame"] is None for r in rows),
                auto_only=sum(r["manual_proximity_frame"] is None and r["deposited_auto_frame"] is not None for r in rows),
                both_onsets=len(diffs), auto_earlier=sum(v<0 for v in diffs),
                auto_same=sum(v==0 for v in diffs), auto_later=sum(v>0 for v in diffs),
                median_auto_minus_manual_frames=float(np.median(diffs)) if diffs else "",
                first_slot_matches_auto=sum(r["first_slot_matches_auto"] for r in rows),
                first_slot_peak_matches_auto=sum(r["first_slot_peak_matches_auto"] for r in rows),
                any_slot_matches_auto=sum(r["any_slot_matches_auto"] for r in rows))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data_root", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    rows, groups, baselines = [], [], []
    for task in TASKS:
        base = args.data_root / "insert" / task
        annotations = json.loads((base / "meta/annotation.json").read_text())
        metadata = {r["episode_index"]:r for r in map(json.loads, (base / "meta/episodes.jsonl").read_text().splitlines())}
        keys = annotations["episodes"]
        if len(list(base.glob("data/chunk-*/*.parquet"))) != len(keys) or len(keys) != len(metadata):
            raise ValueError(f"Incomplete task files: {task}")
        result = [summarize(args.data_root, task, k, keys[k], metadata[int(k)], annotations["force_threshold"]) for k in sorted(keys)]
        taskrows = [ep for ep, _ in result]
        baselines.extend(b for _, b in result if b is not None)
        rows.extend(taskrows)
        for source in sorted({r["source"] for r in taskrows}):
            groups.append(group(task, source, [r for r in taskrows if r["source"] == source]))
    args.output.mkdir(exist_ok=True, parents=True)
    write_csv(args.output/"cria-episodes.csv", rows)
    write_csv(args.output/"cria-task-source.csv", groups)
    write_csv(args.output/"cria-pre-onset-wrist.csv", baselines)


if __name__ == "__main__":
    main()
