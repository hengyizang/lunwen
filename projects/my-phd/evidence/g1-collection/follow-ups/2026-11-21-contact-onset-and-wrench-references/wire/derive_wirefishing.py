"""Check the four selected public WireFishing-M archive files.

Usage: python derive_wirefishing.py DOWNLOADS OUTPUT_DIR
Use the original filenames or local aliases listed below. Python 3.11+, numpy,
libarchive-c and a libarchive build with 7-Zip support are required.
"""
import argparse
import csv
import hashlib
import io
import re
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from zipfile import ZipFile

import libarchive
import numpy as np

SOURCES = [
    ("MUOJXI", 11718373, "Cable1-Random.7z", "20241129_113-113.7z", "cable1_random", "2185db43467fcf1ad23aa95018836317"),
    ("MUOJXI", 11578149, "Cable3-Human.7z", "20250328.7z", "cable3_human", "89c0515823858444d1cfc9689e058edf"),
    ("MUOJXI", 11580198, "Cable4-Random.zip", "20250407_30.zip", "cable4_random", "ed7f71ef961b15e6c549d70e6b75b969"),
    ("XOPUXY", 11770800, "Cable1-Random-part2.7z", "20241201_285-287.7z", "cable1_random", "51385913292c766f6c7288fec45ddd8c"),
]
VIEWS = ("globel_view", "inner_view", "local_view", "tactile_view")
INDEX = re.compile(r"_(\d+)\.(?:jpg|npy)$", re.IGNORECASE)


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=rows[0], lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def members(path):
    if path.suffix == ".zip":
        with ZipFile(path) as archive:
            for entry in archive.infolist():
                if not entry.is_dir():
                    yield entry.filename, lambda e=entry: archive.read(e)
    else:
        with libarchive.file_reader(str(path)) as archive:
            for entry in archive:
                if entry.isfile:
                    yield entry.pathname, lambda e=entry: b"".join(e.get_blocks())


def summarize_trial(dataset, file_id, group, trial, streams, data):
    ordered = sorted(data)
    states = np.stack([data[i] for i in ordered])
    if states.ndim != 2 or states.shape[1] < 20 or not np.isfinite(states).all():
        raise ValueError(f"Incomplete or nonnumeric robot state: {file_id}/{trial}")
    ids = set(ordered)
    modality_ids = [streams[v] for v in VIEWS]
    all_five = ids.intersection(*modality_ids)
    outcome = states[:,19]
    counts = np.unique(outcome, return_counts=True)
    force_norm = np.linalg.norm(states[:,0:3],axis=1)
    moment_norm = np.linalg.norm(states[:,3:6],axis=1)
    result = dict(dataset=dataset, file_id=file_id, condition=group, trial_in_archive=trial,
                  state_frames=len(ordered), vector_columns=states.shape[1], first_index=ordered[0],
                  last_index=ordered[-1], internal_index_gaps=ordered[-1]-ordered[0]+1-len(ordered),
                  five_stream_common_indices=len(all_five), inner_view_images=len(streams["inner_view"]),
                  inner_view_missing_for_state=len(ids-streams["inner_view"]),
                  inner_view_additional_indices=len(streams["inner_view"]-ids),
                  global_images=len(streams["globel_view"]), local_images=len(streams["local_view"]),
                  tactile_images=len(streams["tactile_view"]), outcome_column19_values="|".join(f"{v:g}:{n}" for v,n in zip(*counts)),
                  outcome_column19_changes=int(np.count_nonzero(np.diff(outcome))),
                  median_force_norm=round(float(np.median(force_norm)), 7), max_force_norm=round(float(force_norm.max()), 7),
                  median_moment_norm=round(float(np.median(moment_norm)), 7), max_moment_norm=round(float(moment_norm.max()), 7),
                  columns_after_index19=states.shape[1]-20, nonzero_tail_cells=int(np.count_nonzero(states[:,20:])))
    return result


def process(parameters):
    root, spec = parameters
    dataset, file_id, alias, filename, group, expected = spec
    path = root / alias if (root / alias).exists() else root / filename
    with path.open("rb") as f:
        if hashlib.file_digest(f, "md5").hexdigest() != expected:
            raise ValueError(f"Checksum mismatch: {file_id}")
    streams = defaultdict(lambda: defaultdict(set))
    state = defaultdict(dict)
    for name, read in members(path):
        parts = Path(name.replace("\\","/")).parts
        if len(parts)<2:
            continue
        view = parts[-2]
        if view not in (*VIEWS, "robot_data"):
            continue
        match = INDEX.search(parts[-1])
        if not match:
            raise ValueError(f"Unrecognized indexed member: {name}")
        idx = int(match[1])
        trial = "/".join(parts[:-2]) or "(archive root)"
        if idx in streams[trial][view]:
            raise ValueError(f"Duplicate modality/frame index: {name}")
        streams[trial][view].add(idx)
        if view == "robot_data":
            state[trial][idx] = np.load(io.BytesIO(read()), allow_pickle=False)
    return [summarize_trial(dataset, file_id, group, trial, streams[trial], state[trial]) for trial in sorted(state)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("downloads", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        result = list(pool.map(process, [(args.downloads, s) for s in SOURCES]))
    write_csv(args.output/"wire-trials.csv", [row for rows in result for row in rows])


if __name__ == "__main__":
    main()
