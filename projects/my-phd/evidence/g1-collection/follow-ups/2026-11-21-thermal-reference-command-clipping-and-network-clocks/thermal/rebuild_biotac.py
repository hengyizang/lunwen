"""Rebuild both BioTac tables from the published uncompressed tar (Python 3, NumPy)."""
import argparse
import bz2
import csv
import io
from pathlib import Path
import struct
import tarfile

import numpy as np


def record_stream(stream):
    while size := stream.read(4):
        header = stream.read(struct.unpack("<I", size)[0])
        fields = {}
        offset = 0
        while offset < len(header):
            length = struct.unpack_from("<I", header, offset)[0]
            offset += 4
            key, value = header[offset:offset + length].split(b"=", 1)
            fields[key] = value
            offset += length
        payload_length = struct.unpack("<I", stream.read(4))[0]
        payload = stream.read(payload_length)
        if len(payload) != payload_length:
            raise ValueError("incomplete bag record")
        yield fields, payload


def read_bag(stream):
    assert stream.readline() == b"#ROSBAG V2.0\n"
    connections = {}
    for header, _ in record_stream(stream):
        if header[b"op"] == b"\x07":
            connections[header[b"conn"]] = header[b"topic"].strip(b"/")
    stream.seek(0)
    stream.readline()
    tactile, wrench_time, force = [], [], []
    for header, compressed in record_stream(stream):
        if header[b"op"] != b"\x05":
            continue
        compression = header[b"compression"]
        if compression not in (b"bz2", b"none"):
            raise ValueError(f"unexpected compression {compression!r}")
        data = bz2.decompress(compressed) if compression == b"bz2" else compressed
        for entry, payload in record_stream(io.BytesIO(data)):
            if entry[b"op"] != b"\x02":
                continue
            topic = connections[entry[b"conn"]]
            if topic not in (b"rh/tactile", b"wireless_ft/wrench_3"):
                continue
            _, sec, nsec, frame_len = struct.unpack_from("<IIII", payload)
            position = 16 + frame_len
            stamp = sec * 1_000_000_000 + nsec
            if topic == b"rh/tactile":
                # First element of sr_robot_msgs/Biotac[5], with 5 native int16 readings.
                _, _, pdc, _, tdc = struct.unpack_from("<5h", payload, position)
                tactile.append((stamp, pdc, tdc))
            else:
                wrench_time.append(stamp)
                force.append(struct.unpack_from("<6d", payload, position))
    return np.asarray(tactile, dtype=np.int64), np.asarray(wrench_time, dtype=np.int64), np.asarray(force)


def summarize(name, tactile, wrench_time, force):
    order = np.argsort(wrench_time, kind="stable")
    wrench_time, force = wrench_time[order], force[order]
    t, pdc, tdc = tactile.T
    right = np.clip(np.searchsorted(wrench_time, t), 1, len(wrench_time) - 1)
    left = right - 1
    nearest = np.where(t - wrench_time[left] <= wrench_time[right] - t, left, right)
    delta = wrench_time[nearest] - t
    good = (t >= wrench_time[0]) & (t <= wrench_time[-1]) & (np.abs(delta) <= 5_000_000)
    abs_time = np.abs(delta[good]) / 1_000_000
    f = np.linalg.norm(force[nearest, :3], axis=1)
    moments = np.linalg.norm(force[nearest, 3:], axis=1)
    summary = dict(bag=name, tactile_rows=len(t), wrench_rows=len(wrench_time),
                   tactile_span_s=round(np.ptp(t) / 1e9, 6), paired_rows=int(good.sum()),
                   unique_paired_wrench_rows=len(np.unique(nearest[good])),
                   abs_delta_median_ms=round(np.median(abs_time), 6),
                   abs_delta_p95_ms=round(np.quantile(abs_time, .95), 6),
                   abs_delta_max_ms=round(abs_time.max(), 6))
    bands = []
    for label, mask in (("all_paired", good), ("norm_at_most_0.1_N", good & (f <= .1)),
                        ("norm_over_1_N", good & (f > 1))):
        for period, time_mask in (("whole_recording", good),
                                  ("first_third", (t - t.min()) * 3 < np.ptp(t)),
                                  ("last_third", (t - t.min()) * 3 >= 2 * np.ptp(t))):
            keep = mask & time_mask
            assert np.any(keep)
            bands.append(dict(bag=name, force_band=label, time_window=period,
                              pairs=int(keep.sum()), force_norm_median_N=round(np.median(f[keep]), 6),
                              moment_norm_median_Nm=round(np.median(moments[keep]), 8),
                              moment_norm_p95_Nm=round(np.quantile(moments[keep], .95), 8),
                              tdc_adc_min=int(tdc[keep].min()), tdc_adc_median=np.median(tdc[keep]),
                              tdc_adc_max=int(tdc[keep].max()), pdc_adc_median=np.median(pdc[keep])))
    return summary, bands


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as dest:
        writer = csv.DictWriter(dest, fieldnames=rows[0], lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    summaries, bands = [], []
    with tarfile.open(args.archive) as dataset:
        for bag in dataset:
            if not bag.isfile() or not bag.name.endswith(".bag"):
                continue
            with dataset.extractfile(bag) as stream:
                summary, rows = summarize(Path(bag.name).name, *read_bag(stream))
            summaries.append(summary)
            bands.extend(rows)
    assert len(summaries) == 2
    args.output.mkdir(exist_ok=True, parents=True)
    write_csv(args.output / "biotac-match.csv", summaries)
    write_csv(args.output / "biotac-reference-bands.csv", bands)


if __name__ == "__main__":
    main()
