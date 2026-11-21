"""Rebuild aggregate statistics from the pinned public episode files. Requires numpy and pyarrow."""
import argparse
import csv
import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.request import urlopen

import numpy as np
import pyarrow.parquet as pq

REPO = "PeiYuan001/forceldm-dataset"
REV = "ee424c789ee8e43c95d34d08ba88c9f6b39870f6"
WEB = f"https://huggingface.co/datasets/{REPO}/resolve/{REV}/"
API = f"https://huggingface.co/api/datasets/{REPO}/tree/{REV}/data/chunk-000?limit=1000"


def fetch(url):
    for attempt in range(5):
        try:
            with urlopen(url, timeout=45) as response:
                return response.read()
        except OSError:
            if attempt == 4:
                raise
            time.sleep(2 ** attempt)


def write_csv(path, rows):
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def summarize(entry, cache):
    name = Path(entry["path"]).name
    path = cache / name
    data = path.read_bytes() if path.exists() else fetch(WEB + entry["path"])
    sha256 = hashlib.sha256(data).hexdigest()
    if sha256 != entry["lfs"]["oid"] or len(data) != entry["size"]:
        raise ValueError(f"Unexpected bytes for {name}")
    if not path.exists():
        path.write_bytes(data)
    a = pq.read_table(path, columns=["episode_index", "frame_index", "task_index", "observation.is_contact",
                                     "observation.state", "observation.effort"])
    col = lambda k: np.asarray(a[k].to_pylist())
    n = len(a)
    ep = int(name.removeprefix("episode_").removesuffix(".parquet"))
    assert np.all(col("episode_index") == ep) and np.array_equal(col("frame_index"), np.arange(n))
    tasks = np.unique(col("task_index"))
    assert len(tasks) == 1
    label = col("observation.is_contact").reshape(n)
    assert np.isin(label, [0, 1]).all()
    is_contact = label.astype(bool)
    wrench = col("observation.effort")
    assert wrench.shape == (n, 6) and np.isfinite(wrench).all()
    mismatches = int(np.any(wrench != col("observation.state")[:, 7:13], axis=1).sum())
    f, m = np.linalg.norm(wrench[:, :3], axis=1), np.linalg.norm(wrench[:, 3:], axis=1)
    stats = dict(episode_index=ep, task_index=int(tasks[0]), parquet_sha256=sha256, frames=n,
                 contact_label_1=int(is_contact.sum()), label_transitions=int(np.count_nonzero(np.diff(label))),
                 frames_with_state_effort_mismatch=mismatches, peak_force_N=round(float(f.max()), 6),
                 peak_moment_Nm=round(float(m.max()), 6))
    return stats, f, m, is_contact


def auc(f, pos):
    # Mann-Whitney U with half credit for identical scores.
    neg = np.sort(f[~pos])
    p = f[pos]
    return (np.searchsorted(neg, p, side="left") + np.searchsorted(neg, p, side="right")).sum() / (2 * len(p) * len(neg))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("output", type=Path)
    ap.add_argument("cache", type=Path)
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()
    args.cache.mkdir(exist_ok=True, parents=True)
    args.output.mkdir(exist_ok=True, parents=True)
    entries = json.loads(fetch(API))
    assert len(entries) == 474
    tasks = {int(r["task_index"]): r["task"] for r in map(json.loads, fetch(WEB + "meta/tasks.jsonl").splitlines())}
    with ThreadPoolExecutor(args.workers) as pool:
        episodes = list(pool.map(lambda x: summarize(x, args.cache), entries))
    write_csv(args.output / "forceldm-episodes.csv", [k[0] for k in episodes])
    by_task = []
    for task_id, task in sorted(tasks.items()):
        group = [k for k in episodes if k[0]["task_index"] == task_id]
        f, m, pos = (np.concatenate([item[i] for item in group]) for i in (1, 2, 3))
        row = dict(task_index=task_id, task=task, episodes=len(group), frames=len(f),
                   frames_with_state_effort_mismatch=sum(k[0]["frames_with_state_effort_mismatch"] for k in group))
        for label, mask in [("contact0", ~pos), ("contact1", pos)]:
            row[label + "_frames"] = int(mask.sum())
            for name, arr in [("force_N", f), ("moment_Nm", m)]:
                for q, value in zip(["min", "median", "p95", "max"], np.quantile(arr[mask], [0, .5, .95, 1])):
                    row[f"{label}_{name}_{q}"] = round(float(value), 6)
            row[label + "_force_gt_25N_frames"] = int((f[mask] > 25).sum())
        row["force_norm_vs_contact_label_framewise_AUC"] = round(float(auc(f, pos)), 6)
        by_task.append(row)
    write_csv(args.output / "forceldm-tasks.csv", by_task)


if __name__ == "__main__":
    main()
