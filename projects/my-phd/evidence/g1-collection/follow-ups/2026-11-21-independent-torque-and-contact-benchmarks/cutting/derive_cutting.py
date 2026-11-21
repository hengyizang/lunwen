"""Inspect one paired trial per specimen and the 180-file fixture inventory.

Python 3.9+ standard library. Usage: python derive_cutting.py OUTPUT [--cache RAW]
Downloaded robot bags are read as uncompressed ROS bag v2 records.
"""
import argparse
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import struct
from urllib.request import Request, urlopen


REPO = "McGill-AML/aml_robot_cutting_dataset"
REV = "62fae2c2294c1f3d63ea860b3aa9c60810a307eb"
PAIR_HEADER = "specimen velocity_command_messages actual_torque_messages compensated_torque_messages robot_tool_wrench_messages robot_wrench_span_s robot_wrench_max_force_norm robot_wrench_max_moment_norm actual_torque_nonzero_seventh_slot fixture_rows fixture_duration_at_nominal_200Hz_s fixture_max_force_norm fixture_max_moment_norm fixture_aux7_nonfinite_rows fixture_aux7_finite_adjacent_decreases fixture_aux8_unique fixture_aux8_min fixture_aux8_max processed_joint1_rows processed_cutting_flag_rows".split()
ATI_HEADER = "specimen repetition git_blob bytes coverage fixture_rows maximum_norm_cols1to3 maximum_norm_cols4to6 nonfinite_col7 decreases_between_finite_adjacent_col7 distinct_col8".split()


def download(url):
    with urlopen(Request(url, headers={"User-Agent": "G1-public-file-audit"}), timeout=90) as response:
        return response.read()


def source(path, tree, cache):
    spec = tree[path]
    local = cache / spec["sha"] if cache else None
    data = local.read_bytes() if local and local.exists() else download(
        f"https://raw.githubusercontent.com/{REPO}/{REV}/{path}"
    )
    if hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest() != spec["sha"]:
        raise ValueError(f"Blob mismatch for {path}")
    if local and not local.exists():
        local.write_bytes(data)
    return data


def csv_values(data):
    return [list(map(float, row)) for row in csv.reader(io.StringIO(data.decode())) if row]


def fixture(rows):
    if not all(len(r) == 8 and all(map(math.isfinite, r[:6])) for r in rows):
        raise ValueError("Unexpected fixture sample")
    decreases = sum(math.isfinite(a[6]) and math.isfinite(b[6]) and b[6] < a[6]
                    for a, b in zip(rows, rows[1:]))
    return [len(rows), f"{max(math.hypot(*r[:3]) for r in rows):.6f}",
            f"{max(math.hypot(*r[3:6]) for r in rows):.6f}", sum(not math.isfinite(r[6]) for r in rows),
            decreases, "|".join(f"{v:g}" for v in sorted({r[7] for r in rows}))]


def bag_streams(data):
    if not data.startswith(b"#ROSBAG V2.0\n"):
        raise ValueError("Expected ROS Bag version 2")
    names, messages = {}, []
    def uint(at):
        return struct.unpack_from("<I", data, at)[0]
    def records(pos, stop):
        while pos < stop:
            end = pos + 4 + uint(pos)
            offset = pos + 4
            header = {}
            while offset < end:
                size = uint(offset)
                key, val = data[offset+4:offset+4+size].split(b"=", 1)
                header[key] = val
                offset += 4 + size
            start = end + 4
            pos = start + uint(end)
            if pos > stop or offset != end:
                raise ValueError("Bad ROS record boundary")
            op = header[b"op"][0]
            if op == 5:
                if header[b"compression"] != b"none":
                    raise ValueError("Compressed chunk")
                records(start, pos)
            if op == 7:
                names[int.from_bytes(header[b"conn"], "little")] = header[b"topic"].decode().split("/")[-1]
            if op == 2:
                sec, nsec = struct.unpack("<II", header[b"time"])
                messages.append((int.from_bytes(header[b"conn"], "little"), sec + nsec * 1e-9, start))
    records(13, len(data))
    streams = {}
    for cid, time, pos in messages:
        topic = names[cid]
        if topic == "tool_wrench":
            values = struct.unpack_from("<6d", data, pos + 16 + uint(pos + 12))
        elif topic == "actual_joint_torques":
            values = struct.unpack_from("<7f", data, pos)
        else:
            values = ()
        streams.setdefault(topic, []).append((time, values))
    return streams


def audit(out, cache, include_outstanding=False):
    tree_url = f"https://api.github.com/repos/{REPO}/git/trees/{REV}?recursive=1"
    tree_object = json.loads(download(tree_url))
    if tree_object["truncated"]:
        raise ValueError("Incomplete pinned tree")
    tree = {r["path"]: r for r in tree_object["tree"] if r["type"] == "blob"}
    out.mkdir(parents=True, exist_ok=True)
    if cache:
        cache.mkdir(exist_ok=True, parents=True)
    with (out/"fixture-files.csv").open("w", newline="") as a, (out/"paired-first-trials.csv").open("w", newline="") as p:
        aw, pw = (csv.writer(x, lineterminator="\n") for x in (a,p))
        aw.writerow(ATI_HEADER)
        pw.writerow(PAIR_HEADER)
        for specimen in range(1,13):
            for rep in range(1,16):
                stub = f"cut_{specimen}/cut_{specimen}_{rep}"
                path = f"ft_sensor_data/{stub}.csv"
                spec = tree[path]
                mark = [specimen, rep, spec["sha"], spec["size"]]
                if specimen == 1 and rep == 11 and not include_outstanding:
                    aw.writerow([*mark, "inventory_only_transport_limit", *([""]*6)])
                    continue
                rows = csv_values(source(path, tree, cache))
                stats = fixture(rows)
                aw.writerow([*mark, "numeric", *stats])
                if rep != 1:
                    continue
                bag = bag_streams(source(f"robot_data/{stub}.bag", tree, cache))
                joint = csv_values(source(f"data/{stub}/joint_1.csv", tree, cache))
                wrench = bag["tool_wrench"]
                duration = wrench[-1][0] - wrench[0][0]
                moments = [v for _,v in wrench]
                aux8 = {r[7] for r in rows}
                pw.writerow([specimen, len(bag["cartesian_velocity"]), len(bag["actual_joint_torques"]),
                             len(bag["compensated_joint_torques"]), len(wrench), f"{duration:.6f}",
                             f"{max(math.hypot(*v[:3]) for v in moments):.6f}",
                             f"{max(math.hypot(*v[3:]) for v in moments):.6f}",
                             sum(x[6] != 0 for _,x in bag["actual_joint_torques"]),
                             len(rows), f"{(len(rows)-1)/200:.6f}", *stats[1:5], len(aux8),
                             f"{min(aux8):g}", f"{max(aux8):g}", len(joint), sum(r[4] != 0 for r in joint)])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--cache", type=Path)
    parser.add_argument("--include-outstanding", action="store_true", help="Also audit the 13,710,042-byte fixture file omitted from the published aggregate")
    args = parser.parse_args()
    audit(args.output, args.cache, args.include_outstanding)
