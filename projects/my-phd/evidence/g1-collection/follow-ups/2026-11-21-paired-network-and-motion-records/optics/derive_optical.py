"""Compare physical-controller onset and mid-movement display lag in Warburton et al.
Python >=3.11, numpy, pandas and rdata. Arguments: OSF root containing
latency_script/{input_data,output_data}/*.Rds and the output directory.
"""
from argparse import ArgumentParser
from concurrent.futures import ProcessPoolExecutor
import csv
import hashlib
from pathlib import Path
import warnings

import numpy as np
import pandas as pd
import rdata


def read_rds(path):
    # R's readr/vctrs classes carry extra metadata. The reader retains the data.frames.
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="Missing constructor for R class.*")
        return rdata.read_rds(path)


def frame_delta(table, first):
    observed = pd.to_numeric(table["frame_difference"]).to_numpy(dtype=float, na_value=np.nan)
    delta = (table["row_num.y"] - table[first]).to_numpy(dtype=float, na_value=np.nan)
    valid = np.isfinite(observed)
    if not np.array_equal(observed[valid], delta[valid]):
        raise ValueError("Released lag and endpoint indices disagree")
    return observed


def ms(values, stat=np.median):
    return round(float(stat(values)) * 1000 / 240, 6) if len(values) else ""


def summarize(path):
    start = read_rds(path)
    endpath = path.parent.parent / "output_data" / path.name
    end = read_rds(endpath)
    name = path.stem
    if len(start["camera"]) != len(start["unity"]):
        raise ValueError("Unequal number of camera and application runs")
    coverage = []
    for cam, app in zip(start["camera"], start["unity"]):
        key, = cam["video"].unique()
        appkey, = app["video"].unique()
        assert key == appkey and cam["frame"].is_unique
        coverage.append(dict(condition=name, video=int(key), camera_rows=len(cam),
                             camera_frame_index_min=int(cam["frame"].min()), camera_frame_index_max=int(cam["frame"].max()),
                             missing_physical_x=int(cam["controller_position_x"].isna().sum()),
                             ambiguous_either_eye_frames=int(((cam["hmd_left"] == "ambiguous") | (cam["hmd_right"] == "ambiguous")).sum()),
                             unity_rows=len(app), missing_unity_x=int(app["pos_x"].isna().sum())))

    events = {}
    definitions = []
    for kind, field in [("sudden", "frame"), ("continuous", "row_num.x")]:
        table = end[kind].copy()
        table["lag_frames"] = frame_delta(table, field)
        if table.duplicated(["video", "observation"]).any():
            raise ValueError("Ambiguous event ID within a video")
        events[kind] = table
        valid = table["lag_frames"].dropna().to_numpy()
        keep = np.abs(valid - valid.mean()) < 3 * valid.std(ddof=1)
        definitions.append(dict(condition=name, endpoint=kind, motion_ids=len(table), finite_lags=len(valid),
                                excluded_three_sd=int((~keep).sum()), retained_three_sd=int(keep.sum()),
                                zero_or_negative_before_filter=int((valid <= 0).sum()),
                                negative_before_filter=int((valid < 0).sum()),
                                mean_raw_ms=ms(valid, np.mean), median_raw_ms=ms(valid),
                                p95_raw_ms=ms(valid, lambda a: np.quantile(a, .95)),
                                mean_after_three_sd_ms=ms(valid[keep], np.mean),
                                input_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                                output_sha256=hashlib.sha256(endpath.read_bytes()).hexdigest()))
    paired = []
    # The authors number onset and midpoint detections separately. Pair by the
    # enclosing physical movement interval; exclude intervals with multiple crossings.
    for key, stream in end["overall"].groupby("video"):
        onsets = stream.loc[stream["real_movement_start"].fillna(False), "row_num"].to_numpy(dtype=float)
        if len(onsets) < 2 or (np.diff(onsets) <= 0).any():
            raise ValueError("Invalid ordering of physical movement starts")
        onset = events["sudden"].loc[lambda t: t.video == key].set_index("frame")
        middle = events["continuous"].loc[lambda t: t.video == key].copy()
        idx = np.searchsorted(onsets, middle["row_num.x"], side="right") - 1
        # Row indices in 'overall' bound the final movement through the end of the video.
        valid = (idx >= 0) & (middle["row_num.x"] <= stream["row_num"].max())
        middle = middle.loc[valid].copy()
        middle["onset_frame"] = onsets[idx[valid]]
        repeated = middle["onset_frame"].duplicated(keep=False)
        have = middle.loc[~repeated].set_index("onset_frame")
        joined = onset[["observation", "lag_frames"]].join(have[["observation", "lag_frames"]],
                                                           how="inner", lsuffix="_onset", rsuffix="_middle")
        both = joined.dropna(subset=["lag_frames_onset", "lag_frames_middle"])
        delta = (both["lag_frames_onset"] - both["lag_frames_middle"]).to_numpy()
        paired.append(dict(condition=name, video=int(key), registered_onsets=len(onset),
                           registered_midpoint_crossings=len(events["continuous"].loc[lambda t: t.video == key]),
                           ambiguous_midpoint_crossings=int(repeated.sum()), paired_finite_lags=len(both),
                           differing_published_ordinals=int((both["observation_onset"] != both["observation_middle"]).sum()),
                           onset_lag_greater_count=int((delta > 0).sum()), same_lag_count=int((delta == 0).sum()),
                           onset_lag_smaller_count=int((delta < 0).sum()),
                           median_within_motion_onset_minus_midpoint_ms=ms(delta)))
    return coverage, definitions, paired


def main():
    ap = ArgumentParser(description=__doc__)
    ap.add_argument("osf_root", type=Path)
    ap.add_argument("output", type=Path)
    ap.add_argument("--workers", type=int, default=1)
    args = ap.parse_args()
    inputs = sorted((args.osf_root / "latency_script" / "input_data").glob("*.Rds"))
    if len(inputs) != 7:
        raise ValueError("Expected seven registered settings")
    args.output.mkdir(parents=True, exist_ok=True)
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        res = list(pool.map(summarize, inputs))
    for i, name in enumerate(["optical-video-coverage", "optical-endpoint-lags", "optical-paired-events"]):
        rows = [row for group in res for row in group[i]]
        with (args.output / (name + ".csv")).open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=rows[0], lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)


if __name__ == "__main__":
    main()
