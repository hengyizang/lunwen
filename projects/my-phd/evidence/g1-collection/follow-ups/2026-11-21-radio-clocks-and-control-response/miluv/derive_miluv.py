"""Audit the MILUV three-robot CSV subset. Python 3, pandas, NumPy, SciPy, PyYAML.

Usage: python derive_miluv.py INPUT OUTPUT
INPUT contains experiments.csv, tags.yaml, anchors.yaml and the extracted experiment directories.
The directory EXP/EXP/ifo001 and the single-level EXP/ifo001 layout are both supported.
"""
import argparse
import ast
import csv
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from scipy.spatial.transform import Rotation

RADIO = ["tx1", "rx1", "tx2", "rx2", "tx3", "rx3"]
IDS = ["from_id", "to_id"]
ACTIVE_KEY = IDS + [v + "_raw" for v in RADIO]
C = 299702547 / 1e9    # m/ns in the authors' pyuwbcalib code
PERIOD = (2**32) * (1e9 / 499.2e6 / 128)
ROBOTS = ["ifo001", "ifo002", "ifo003"]


def load_csv(file, fields):
    return pd.read_csv(file, usecols=fields, float_precision="round_trip")


def combined(root, name, fields, identity):
    files = [root / robot / name for robot in ROBOTS]
    frame = pd.concat([load_csv(f, fields) for f in files], ignore_index=True)
    total = len(frame)
    # Only collapse identical retained fields. A radio identity collision with
    # different values is not silently resolved by taking the first row.
    unique = frame.drop_duplicates().reset_index(drop=True)
    if unique.duplicated(identity).any():
        raise ValueError(f"Ambiguous radio identity in {root.name}/{name}")
    return unique, total


def diff_ns(later, earlier):
    return np.remainder(later - earlier, PERIOD)


def active_range(df):
    a = diff_ns(df.rx2, df.tx1)
    b = diff_ns(df.tx2, df.rx1)
    c = diff_ns(df.rx3, df.rx2)
    d = diff_ns(df.tx3, df.tx2)
    if np.any(d == 0):
        raise ValueError("Zero interval in active ranging transaction")
    return 0.5 * C * (a - c/d*b)


def geom(tag_ids, times, root, anchors, tag_cfg, poses):
    """Reconstruct tag locations from independent motion-capture CSVs at source ROS time."""
    xyz = np.full((len(times), 3), np.nan)
    for tag in np.unique(tag_ids):
        mask = tag_ids == tag
        if tag in anchors:
            xyz[mask] = anchors[tag]
            continue
        robot, offset = tag_cfg[tag]
        if robot not in poses:
            pose = pd.read_csv(root/robot/"mocap.csv", float_precision="round_trip")
            t = pose.timestamp.to_numpy()
            if np.any(np.diff(t) <= 0):
                raise ValueError("Nonincreasing motion-capture clock")
            poses[robot] = t, pose.iloc[:,1:].to_numpy()
        t, values = poses[robot]
        sel = mask & (times >= t[0]) & (times <= t[-1])
        if not sel.any():
            continue
        v = np.column_stack([np.interp(times[sel], t, col) for col in values.T])
        valid = np.isfinite(v).all(axis=1) & (np.linalg.norm(v[:,3:], axis=1) > 0)
        xyz[np.flatnonzero(sel)[valid]] = v[valid,:3] + Rotation.from_quat(v[valid,3:]).apply(offset)
    return xyz


def rms(x):
    x = np.asarray(x, dtype=float)
    return float(np.sqrt(np.mean(x*x))) if x.size else np.nan


def row_stats(experiment, a, p_all, metadata):
    counts = p_all["idx"].value_counts()
    observed = a["idx"].map(counts).fillna(0)
    geometry = a["geom_range"] - a["gt_range"]
    return dict(experiment=experiment, trajectory=metadata["trajectory"], constellation=metadata["anchor_constellation"],
                cir_recorded=metadata["cir_bool"], obstacles=metadata["obstacles_bool"],
                active_rx_transactions=len(a), gt_raw_error_rmse_m=rms(a.range_raw-a.gt_range),
                gt_calibrated_error_rmse_m=rms(a["range"]-a.gt_range),
                recalculated_radio_to_stored_range_rmse_m=rms(a.reconstructed-a["range"]),
                mocap_comparable=int(geometry.notna().sum()), mocap_vs_stored_gt_rmse_m=rms(geometry.dropna()),
                matched_listener_rows=int(observed.sum()), active_with_one_or_more_listener=int((observed>0).sum()),
                active_without_archived_listener=int((observed==0).sum()))


def process(base, record, tag_cfg, constellations):
    name = record["experiment"]
    root = base/name
    if (root/name).is_dir():
        root = root/name
    anchors = constellations[record["anchor_constellation"]]
    fields = list(dict.fromkeys(ACTIVE_KEY + RADIO + ["timestamp","range","range_raw","gt_range"]))
    active, raw_active = combined(root, "uwb_range.csv", fields, ACTIVE_KEY)
    active["idx"] = np.arange(len(active))
    active["reconstructed"] = active_range(active)
    poses = {}
    for role in ("from", "to"):
        xyz = geom(active[role+"_id"].to_numpy(), active.timestamp.to_numpy(), root, anchors, tag_cfg, poses)
        for j, v in enumerate("xyz"):
            active[role+"_"+v] = xyz[:,j]
    coords_from, coords_to = ([role+"_"+v for v in "xyz"] for role in ("from","to"))
    active["geom_range"] = np.linalg.norm(active[coords_from].to_numpy()-active[coords_to].to_numpy(), axis=1)

    identity = IDS + ["my_id"] + [v+"_raw_n" for v in RADIO] + ["rx1_raw","rx2_raw","rx3_raw"]
    fields = identity + ["rx1","rx2","rx3","timestamp","timestamp_n","range_n","gt_range_n"]
    passive, raw_passive = combined(root, "uwb_passive.csv", fields, identity)
    passive.rename(columns={c:c+"_listener" for c in ("rx1_raw","rx2_raw","rx3_raw")}, inplace=True)
    passive.rename(columns={v+"_raw_n":v+"_raw" for v in RADIO}, inplace=True)
    passive.rename(columns={n:n+"_listener" for n in ["rx1","rx2","rx3","timestamp"]}, inplace=True)
    # Require both endpoint IDs and all six original radio stamps to select the active transaction.
    matched = passive.merge(active,on=ACTIVE_KEY,how="inner",validate="many_to_one")
    p = matched
    p["header_gap_ms"] = 1e3 * (p.timestamp_listener - p.timestamp)
    if len(p):
        if (p["range"]-p["range_n"]).abs().max()>1e-7 or (p.gt_range-p.gt_range_n).abs().max()>1e-7:
            raise ValueError("Reference columns disagree with a six-stamp join")
        if len(p[["idx","my_id"]].drop_duplicates()) != len(p):
            raise ValueError("Multiple decoded observations per listener and transaction")
    init = p.from_id.map(lambda i: tag_cfg[i][0] if i in tag_cfg else "anchor")
    target = p.to_id.map(lambda i: tag_cfg[i][0] if i in tag_cfg else "anchor")
    listener = p.my_id.map(lambda i: tag_cfg[i][0] if i in tag_cfg else "anchor")
    p["listener_role"] = np.select([listener=="anchor", listener==init, listener==target],
                                   ["anchor", "on_initiator_robot","on_responder_robot"], default="other_robot")

    # Passive differential range to responder minus range to initiator, with
    # local oscillator-scale estimate from messages 2 and 3 sent by responder.
    sender_span = diff_ns(p.tx3,p.tx2)
    listener_span = diff_ns(p.rx3_listener,p.rx2_listener)
    listener_first = diff_ns(p.rx2_listener,p.rx1_listener)
    responder_wait = diff_ns(p.tx2,p.rx1)
    acceptable = (sender_span>0) & (listener_span>0)
    p["pdiff"] = (C*(listener_first * sender_span/listener_span - responder_wait) - p["range"]).where(acceptable)
    obs_xyz = geom(p.my_id.to_numpy(),p.timestamp.to_numpy(),root,anchors,tag_cfg,poses)
    p["geom_diff"] = (np.linalg.norm(obs_xyz-p[coords_to].to_numpy(),axis=1)
                      - np.linalg.norm(obs_xyz-p[coords_from].to_numpy(),axis=1))
    stats = row_stats(name, active, p, record)
    stats.update(active_rows_across_robot_exports=raw_active,passive_rows_across_robot_exports=raw_passive,
                 distinct_archived_listener_observations=len(passive),unmatched_listener_observations=len(passive)-len(p),
                 max_abs_copied_active_header_difference_us=float((p.timestamp-p.timestamp_n).abs().max()*1e6))
    links=[]
    for (a,b),subset in active.groupby(IDS,sort=True):
        links.append(dict(from_id=int(a),to_id=int(b),
                          **row_stats(name,subset,p[p.from_id.eq(a)&p.to_id.eq(b)],record)))
    listeners=[]
    for role,sub in p.groupby("listener_role",sort=True):
        gap=sub.header_gap_ms
        delta=(sub.pdiff-sub.geom_diff).dropna()
        listeners.append(dict(experiment=name,listener_role=role,observations=len(sub),
                              strictly_negative_ros_header_gap=int((gap<0).sum()),
                              median_ros_header_gap_ms=float(gap.median()),p05_ros_header_gap_ms=float(gap.quantile(.05)),
                              p95_ros_header_gap_ms=float(gap.quantile(.95)),geometric_comparable=len(delta),
                              differential_range_signed_median_error_m=float(delta.median()),
                              differential_range_median_absolute_error_m=float(delta.abs().median()),
                              differential_range_p95_absolute_error_m=float(delta.abs().quantile(.95)),
                              triangle_excess_over_1m=int((sub.loc[delta.index,"pdiff"].abs() >
                                                          sub.loc[delta.index,"geom_range"]+1.0).sum()),
                              differential_range_untrimmed_rmse_m=rms(delta)))
    return stats, links, listeners


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root",type=Path)
    parser.add_argument("output",type=Path)
    args=parser.parse_args()
    records=[r for r in csv.DictReader((args.root/"experiments.csv").open()) if r["num_robots"]=="3"]
    if len(records)!=16:
        raise ValueError("Expected all 16 published three-robot configurations")
    anchors={str(key):{int(tag):ast.literal_eval(x) for tag,x in v.items()}
             for key,v in yaml.safe_load((args.root/"anchors.yaml").read_text()).items()}
    tags={int(tag):(robot,ast.literal_eval(x)) for robot,v in yaml.safe_load((args.root/"tags.yaml").read_text()).items()
          for tag,x in v.items()}
    exps,links,listeners=[],[],[]
    for r in records:
        ex,ln,ls=process(args.root,r,tags,anchors)
        exps.append(ex)
        links.extend(ln)
        listeners.extend(ls)
    args.output.mkdir(parents=True,exist_ok=True)
    for file,rows in [("experiments",exps),("directed-links",links),("passive-timing",listeners)]:
        pd.DataFrame(rows).to_csv(args.output/f"miluv-{file}.csv",index=False,float_format="%.9f",lineterminator="\n")


if __name__=="__main__":
    main()
