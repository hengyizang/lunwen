"""Audit the Mendeley v1 archive and summarize the DSP observation channels."""
import argparse
import csv
import hashlib
import io
import math
import struct
from collections import defaultdict
from pathlib import Path
from zipfile import ZipFile

import numpy as np

ARCHIVE_SHA256 = "1e9e05f44aa4dc3603710ff25ecc8af98c99ba426057245da706ea66875c4ce8"


def decode(raw):
    signature, size, count = struct.unpack_from("<4sII", raw)
    if signature != b"AG10" or size != len(raw):
        raise ValueError("Invalid AG10 signature or length")
    pos = 12
    channels = {}
    for _ in range(count):
        header_size, _, buffers, points = struct.unpack_from("<IIII", raw, pos)
        dt, origin = struct.unpack_from("<dd", raw, pos + 32)
        label = raw[pos+112:pos+128].split(b"\0")[0].decode("ascii")
        pos += header_size
        data_header, _, width, length = struct.unpack_from("<IHHI", raw, pos)
        if buffers != 1 or width != 4 or points * width != length or label in channels:
            raise ValueError("Unexpected channel layout")
        signal = np.frombuffer(raw, dtype="<f4", count=points, offset=pos + data_header)
        if not np.all(np.isfinite(signal)) or dt <= 0 or not math.isfinite(origin):
            raise ValueError("Invalid voltage or channel clock")
        channels[label] = (dt, origin, signal)
        pos += data_header + length
    if pos != len(raw):
        raise ValueError("Incomplete decode")
    return channels


def csv_members(z, member):
    return list(csv.DictReader(io.StringIO(z.read(member).decode("utf-8-sig"))))


def summarize(archive):
    with archive.open("rb") as f:
        if hashlib.file_digest(f, "sha256").hexdigest() != ARCHIVE_SHA256:
            raise ValueError("Archive differs from Mendeley v1")
    out = []
    with ZipFile(archive) as z:
        manifest = csv_members(z, "manifest.csv")
        headers = {(r["path"], r["recorded_channel_label"]): r
                   for r in csv_members(z, "waveform_metadata.csv")}
        groups = defaultdict(set)
        for item in manifest:
            groups[item["sha256"]].add(item["group"])
        for item in sorted(manifest, key=lambda r: r["path"]):
            name = item["path"]
            raw = z.read(name)
            sha = hashlib.sha256(raw).hexdigest()
            if sha != item["sha256"] or len(raw) != int(item["bytes"]):
                raise ValueError(f"Bad manifest entry: {name}")
            if not name.endswith(".bin"):
                continue
            chan = decode(raw)
            if set(chan) != {"1", "2", "3", "4"}:
                raise ValueError(f"Unexpected channel set: {name}")
            for k, (dt, t0, values) in chan.items():
                ref = headers[name, k]
                if not (len(values) == int(ref["points"]) and
                        math.isclose(dt, float(ref["sample_interval_s"]), rel_tol=1e-12) and
                        math.isclose(t0, float(ref["record_origin_s"]), abs_tol=1e-12)):
                    raise ValueError(f"Mismatch with published headers: {name}:{k}")
            dts = {d[0] for d in chan.values()}
            counts = {len(d[2]) for d in chan.values()}
            if len(dts) != 1 or len(counts) != 1:
                raise ValueError("Incommensurable channel sampling")
            dt = dts.pop()
            skew = max(d[1] for d in chan.values()) - min(d[1] for d in chan.values())
            if skew >= dt / 2:
                raise ValueError("Channel origins differ by >= half a scope sample")
            group = item["group"]
            ambiguous = len(groups[sha]) > 1
            condition = next(s for s in name.split("/") if s.startswith(("5N_", "10N_")) or s == "empty")
            row = dict(source_member=name, sha256=sha, controller=item["manuscript_algorithm"],
                       nominal_speed_rpm=item["nominal_speed_rpm"], acquisition_group=group,
                       condition_path_label=condition, parameter_setting=item["parameter_setting"],
                       channel_mapping="cross-group identical bytes" if ambiguous else "as documented",
                       samples_per_channel=counts.pop(), scope_dt_us=round(dt*1e6, 8),
                       max_origin_skew_ns=round(skew*1e9, 5), mean_reference_iq_A="",
                       mean_observed_iq_A="", iq_tracking_rmse_A="", rms_phase_a_A="", rms_phase_b_A="")
            if not ambiguous:
                # Both groups use channels 3/4 for a quantity calibrated in amperes.
                current3 = 4.0 * (chan["3"][2].astype("float64") - 2.5)
                current4 = 4.0 * (chan["4"][2].astype("float64") - 2.5)
                if group == "group1":
                    row.update(mean_reference_iq_A=round(float(current3.mean()), 7),
                               mean_observed_iq_A=round(float(current4.mean()), 7),
                               iq_tracking_rmse_A=round(float(np.sqrt(np.mean((current3-current4)**2))), 7))
                else:
                    row.update(rms_phase_a_A=round(float(np.sqrt(np.mean(current3**2))), 7),
                               rms_phase_b_A=round(float(np.sqrt(np.mean(current4**2))), 7))
            out.append(row)
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("output_csv", type=Path)
    args = parser.parse_args()
    rows = summarize(args.archive)
    with args.output_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0], lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
