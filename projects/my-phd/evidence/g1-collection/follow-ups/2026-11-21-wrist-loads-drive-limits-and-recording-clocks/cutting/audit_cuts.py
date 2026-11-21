"""Audit all 180 published cutting trials. Python 3.9+, standard library.

Usage: python audit_cuts.py PATH_TO_PRIOR_DERIVE_CUTTING_PY OUTPUT [--cache CACHE]
Use the immutable earlier reader identified in source.json. The optional cache
stores downloaded source files by Git blob ID. Its contents are verified on read.
"""
import argparse
import csv
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import statistics
import struct


def wrench_headers(data):
    """Extract WrenchStamped header and bag record timestamps as integer ns."""
    if not data.startswith(b"#ROSBAG V2.0\n"):
        raise ValueError("Unexpected bag version")
    connections = {}
    messages = []
    def u32(pos):
        return struct.unpack_from("<I", data, pos)[0]
    def records(pos, stop):
        while pos < stop:
            cursor = pos + 4
            end = cursor + u32(pos)
            header = {}
            while cursor < end:
                size = u32(cursor)
                key, value = data[cursor+4:cursor+4+size].split(b"=", 1)
                header[key] = value
                cursor += size + 4
            start = end + 4
            pos = start + u32(end)
            if cursor != end or pos > stop:
                raise ValueError("Invalid ROS bag boundaries")
            op = header[b"op"][0]
            if op == 5:
                if header[b"compression"] != b"none":
                    raise ValueError("Unexpected compressed chunk")
                records(start, pos)
            elif op == 7:
                connections[int.from_bytes(header[b"conn"], "little")] = header[b"topic"].decode()
            elif op == 2:
                sec, ns = struct.unpack("<II", header[b"time"])
                messages.append((int.from_bytes(header[b"conn"], "little"), sec*10**9+ns, start, pos))
    records(13, len(data))
    result = []
    for cid, bag_time, pos, end in messages:
        if connections[cid].split("/")[-1] != "tool_wrench":
            continue
        seq, sec, ns, length = struct.unpack_from("<IIII", data, pos)
        if end-pos != 16+length+48 or ns >= 10**9:
            raise ValueError("Unexpected WrenchStamped layout")
        frame = data[pos+16:pos+16+length].decode()
        result.append((seq, sec*10**9+ns, bag_time, frame))
    return result


def writer(path, header):
    stream = path.open("w", newline="")
    table = csv.writer(stream, lineterminator="\n")
    table.writerow(header.split())
    return table, stream


def run(reader, out, cache):
    out.mkdir(parents=True, exist_ok=True)
    if cache:
        cache.mkdir(parents=True, exist_ok=True)
    url = f"https://api.github.com/repos/{reader.REPO}/git/trees/{reader.REV}?recursive=1"
    tree_object = json.loads(reader.download(url))
    if tree_object["truncated"]:
        raise ValueError("Incomplete source tree")
    tree = {r["path"]: r for r in tree_object["tree"] if r["type"] == "blob"}
    pairs, file1 = writer(out/"trial-pairs.csv",
        "specimen repetition bag_git_blob fixture_git_blob joint1_git_blob velocity_messages "
        "joint_torque_messages compensated_torque_messages tool_wrench_messages robot_span_s "
        "header_span_s wrench_distinct_header_times wrench_header_sequence_jumps "
        "wrench_header_nonincreasing_times wrench_frames_json min_bag_minus_header_ms "
        "median_bag_minus_header_ms max_bag_minus_header_ms peak_robot_force_norm peak_robot_moment_norm "
        "fixture_rows fixture_span_at_nominal_200Hz_s fixture_over_robot_span peak_fixture_force_norm "
        "peak_fixture_moment_norm nonfinite_fixture_col7 decreasing_fixture_col7 distinct_fixture_col8 "
        "processed_joint1_rows positive_cutting_flag_rows")
    try:
        for specimen in range(1,13):
            for rep in range(1,16):
                stem = f"cut_{specimen}/cut_{specimen}_{rep}"
                bag_path, fixture_path, joint_path = f"robot_data/{stem}.bag", f"ft_sensor_data/{stem}.csv", f"data/{stem}/joint_1.csv"
                bag_bytes = reader.source(bag_path,tree,cache)
                bag = reader.bag_streams(bag_bytes)
                fixture = reader.fixture(reader.csv_values(reader.source(fixture_path,tree,cache)))
                joint = reader.csv_values(reader.source(joint_path,tree,cache))
                hdr = wrench_headers(bag_bytes)
                wrench = bag["tool_wrench"]
                if len(wrench) != len(hdr) or len(wrench) < 2:
                    raise ValueError("Unmatched wrench timestamps")
                sec = (hdr[-1][2]-hdr[0][2])/1e9
                span = (fixture[0]-1)/200
                offsets = [(row[2]-row[1])/1e6 for row in hdr]
                pairs.writerow([specimen,rep,*(tree[p]["sha"] for p in (bag_path,fixture_path,joint_path)),
                    len(bag["cartesian_velocity"]),len(bag["actual_joint_torques"]),len(bag["compensated_joint_torques"]),
                    len(wrench),f"{sec:.9f}",f"{(hdr[-1][1]-hdr[0][1])/1e9:.9f}",len({h[1] for h in hdr}),
                    sum((b[0]-a[0])%(2**32)!=1 for a,b in zip(hdr,hdr[1:])),sum(b[1]<=a[1] for a,b in zip(hdr,hdr[1:])),
                    json.dumps(sorted({r[3] for r in hdr})),*(f"{val:.6f}" for val in (min(offsets),statistics.median(offsets),max(offsets))),
                    f"{max(math.hypot(*v[:3]) for _,v in wrench):.6f}",f"{max(math.hypot(*v[3:]) for _,v in wrench):.6f}",
                    fixture[0],f"{span:.6f}",f"{span/sec:.6f}",*fixture[1:],len(joint),sum(r[4]!=0 for r in joint)])
    finally:
        file1.close()
    source_readme = reader.source("README.md", tree, cache).decode()
    claimed = {}
    for line in source_readme.splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) == 4 and cells[0].isdigit() and cells[3].isdigit():
            claimed[int(cells[0])] = int(cells[3])
    if set(claimed) != set(range(1,13)):
        raise ValueError("Expected twelve specimen rows in source README")
    with (out/"trial-pairs.csv").open() as inp:
        pairs = list(csv.DictReader(inp))
    counts, counts_file = writer(out/"processed-counts.csv", "specimen readme_datapoints observed_joint1_rows difference")
    try:
        for specimen, value in sorted(claimed.items()):
            observed = sum(int(r["processed_joint1_rows"]) for r in pairs if int(r["specimen"]) == specimen)
            counts.writerow([specimen, value, observed, observed-value])
    finally:
        counts_file.close()
    flagtab, flag_file = writer(out/"cutting-labels.csv",
        "specimen repetition joint1_to_joint6_git_blobs rows published_positive recomputed_positive "
        "recomputed_disagreements joint_streams_with_time_or_label_disagreement")
    try:
        for specimen in range(1,13):
            for rep in range(1,16):
                stem = f"data/cut_{specimen}/cut_{specimen}_{rep}"
                paths = [f"{stem}/joint_{j}.csv" for j in range(1,7)]
                joints = [reader.csv_values(reader.source(p,tree,cache)) for p in paths]
                base = joints[0]
                if len(base) < 9 or any(len(rows) != len(base) for rows in joints):
                    raise ValueError("Unpaired processed joint channels")
                if any(len(row)!=7 or not all(map(math.isfinite,row)) or row[4] not in [0,1] for rows in joints for row in rows):
                    raise ValueError("Unexpected processed joint sample")
                issues = sum(any(a[3:5] != b[3:5] for a,b in zip(base,rows)) for rows in joints)
                if issues:
                    raise ValueError("Joint time or labels do not agree")
                inferred = [True]*len(base)
                # RobotDataHelper.add_labels uses the rolling sample SD (pandas ddof=1),
                # sets leading positions 0:4 from positions 5:9, then intersects four joints.
                for j in (0,2,3,4):
                    tau = [row[2] for row in joints[j]]
                    roll = [0.0]*4 + [statistics.stdev(tau[i-4:i+1]) for i in range(4,len(tau))]
                    roll[:4] = roll[5:9]
                    mean = statistics.fmean(roll)
                    inferred = [prior and (value > mean) for prior,value in zip(inferred,roll)]
                inferred[0] = False
                labels = [bool(row[4]) for row in base]
                flagtab.writerow([specimen,rep,"|".join(tree[p]["sha"] for p in paths),len(base),
                                  sum(labels),sum(inferred),sum(a!=b for a,b in zip(labels,inferred)),issues])
    finally:
        flag_file.close()




if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reader", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--cache", type=Path)
    args = parser.parse_args()
    reader_bytes = args.reader.read_bytes()
    digest = hashlib.sha1(f"blob {len(reader_bytes)}\0".encode()+reader_bytes).hexdigest()
    if digest != "906ed39a3218028648dfd335f20ee727e9774fbb":
        raise ValueError("Reader differs from the pinned earlier file")
    spec = importlib.util.spec_from_file_location("cut_reader", args.reader)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    run(module,args.output,args.cache)
