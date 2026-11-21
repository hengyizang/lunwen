"""Summarize the pinned NCSbench platform-a-wireless trace. Usage: python derive_ncsbench.py MEASUREMENT_DIR OUTDIR"""
import argparse
import csv
from decimal import Decimal
import hashlib
from pathlib import Path
import struct

import numpy as np


def write_csv(path, rows):
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, rows[0].keys(), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def read_trace(path):
    """Read only fixed application layouts from the authors' little-endian Ethernet capture."""
    data = path.read_bytes()
    if data[:4] != bytes.fromhex("d4c3b2a1") or struct.unpack_from("<I", data, 20)[0] != 1:
        raise ValueError("Expected a classic little-endian microsecond Ethernet capture")
    offset = 24
    truncated_other_records = 0
    sensor, control = {}, {}
    while offset < len(data):
        sec, usec, size, _ = struct.unpack_from("<IIII", data, offset)
        frame = data[offset + 16:offset + 16 + size]
        offset += 16 + size
        if len(frame) != size:
            # The final UDP datagram in the archived capture ends partway through an unrelated payload.
            if len(frame) < 38 or frame[12:14] != b"\x08\x00" or frame[23] != 17:
                raise ValueError("Cannot classify truncated capture record")
            udp = 14 + (frame[14] & 15) * 4
            if struct.unpack_from("!HH", frame, udp) in {(34543, 34543), (34543, 34544)}:
                raise ValueError("Incomplete experiment datagram")
            truncated_other_records += 1
            continue
        if len(frame) < 34 or frame[12:14] != b"\x08\x00" or frame[23] != 17:
            continue
        udp = 14 + (frame[14] & 15) * 4
        src, dst, length, _ = struct.unpack_from("!HHHH", frame, udp)
        payload = frame[udp + 8:udp + length]
        key = src, dst, len(payload)
        if key == (34543, 34543, 88):
            target, layout = sensor, "<11q"
        elif key == (34543, 34544, 192):
            target, layout = control, "<24q"
        else:
            continue
        values = struct.unpack(layout, payload)
        if values[0] in target:
            raise ValueError("Duplicate sequence ID")
        target[values[0]] = (values, sec * 1_000_000 + usec)
    return sensor, control, truncated_other_records


TIMING = ("tsr_k", "tsstx_k", "tasrx_k", "taw_k", "tssrx_k", "tastx_k")
TELEMETRY = ("gyro_rate", "motor_position_left", "motor_position_right", "gyro_offset",
             "motor_voltage_applied_left", "motor_voltage_applied_right")


def file_log(folder, field):
    path, = folder.glob(f"*_{field}_logger.csv")
    with path.open() as stream:
        return [(Decimal(r["timestamp"]), Decimal(r["value"])) for r in csv.DictReader(stream, delimiter=";", quotechar="'")]


def derive(folder, outdir):
    outdir.mkdir(parents=True, exist_ok=True)
    capture = folder / "record.pcap"
    robot, commands, truncated_other = read_trace(capture)
    timing = {field: file_log(folder, field) for field in TIMING}
    telemetry = {field: file_log(folder, field) for field in TELEMETRY}
    if len({len(series) for series in timing.values()}) != 1:
        raise ValueError("Mismatched timing logger lengths")
    received_at = [stamp for stamp, val in telemetry["gyro_rate"]]
    for payload_index, field in enumerate(TELEMETRY, 5):
        series = telemetry[field]
        if [stamp for stamp, val in series] != received_at:
            raise ValueError(f"Telemetry rows do not align for {field}")
        if any(round(val * 1_000_000) != robot[k][0][payload_index] for k, (_, val) in enumerate(series, 1)):
            raise ValueError(f"Telemetry/capture mismatch in {field}")

    # Stamps describe cycle k and are carried by robot report k+1.
    # Restrict join to reports accepted by the controller log. Capture extends past shutdown.
    ticks_per_second = 10_000_000
    reports = {robot[k][0][1]: k for k in range(1, len(received_at)+1)}
    groups = {"all_aligned_cycles": {}, "reported_pair_within_1_microvolt": {}}
    sequences, exceptions = [], []
    exact_pair = 0
    for logged in zip(*(timing[name] for name in TIMING)):
        r_read, r_send, r_recv, r_write, host_recv, host_send = [value for _, value in logged]
        report_id = reports[round(r_read*ticks_per_second)]
        k = report_id - 1
        sequences.append(k)
        reported = robot[report_id][0]
        sent, capture_control_us = commands[k]
        if [round(v*ticks_per_second) for v in (r_read,r_send,r_recv,r_write)] != list(reported[1:5]):
            raise ValueError("Robot timestamp join failed")
        if abs(host_send*ticks_per_second - sent[1]) > 1 or host_recv != received_at[k-1]:
            raise ValueError("Controller timestamp join failed")
        error = max(abs(target-observed) for target, observed in zip(sent[2:4], reported[9:11]))
        exact_pair += error == 0
        intervals = {
            "robot_read_to_pre_send": (r_send-r_read)*1000,
            "robot_pre_send_to_receive_marker": (r_recv-r_send)*1000,
            "robot_receive_marker_to_post_write": (r_write-r_recv)*1000,
            "robot_read_to_post_write": (r_write-r_read)*1000,
            "controller_receive_to_pre_send": (host_send-host_recv)*1000,
            "capture_sensor_to_command": (capture_control_us-robot[k][1])/1000,
        }
        for group, measures in groups.items():
            if group == "reported_pair_within_1_microvolt" and error > 1:
                continue
            for measure, value in intervals.items():
                measures.setdefault(measure, []).append(float(value))
        if error > 1:
            exceptions.append({"cycle_id": k, "max_abs_pair_difference_microvolt": error})
    if sequences != list(range(295,1684)):
        raise ValueError("Unexpected cycle range")
    metrics = []
    for group, measures in groups.items():
        for measure, values in measures.items():
            row = {"subset":group, "interval":measure, "cycles":len(values)}
            for label, val in zip(("min_ms","p50_ms","p95_ms","p99_ms","max_ms"),np.quantile(values,[0,.5,.95,.99,1])):
                row[label] = f"{val:.6f}"
            metrics.append(row)
    write_csv(outdir/"ncsbench-timing.csv", metrics)
    write_csv(outdir/"ncsbench-command-mismatches.csv", exceptions)
    counter_path, = folder.glob("*_counters.csv")
    with counter_path.open() as stream:
        last_counter=list(csv.DictReader(stream, delimiter=";", quotechar="'"))[-1]
    coverage = {
        "truncated_nonexperiment_datagrams": truncated_other, "sensor_packets": len(robot), "sensor_first_seq":min(robot), "sensor_last_seq":max(robot),
        "control_packets":len(commands), "control_first_seq":min(commands), "control_last_seq":max(commands),
        "telemetry_rows_per_stream": len(received_at), "timing_rows_per_stream":len(sequences),
        "aligned_cycle_first":sequences[0], "aligned_cycle_last":sequences[-1],
        "aligned_pairs_exact":exact_pair, "aligned_pairs_within_1_microvolt":len(sequences)-len(exceptions),
        "aligned_pairs_over_1_microvolt":len(exceptions), "precomputed_controller_rows":len(file_log(folder,"controller_processing_delay")),
        "precomputed_robot_rtt_rows":len(file_log(folder,"robot_roundtrip_network_delay")),
        **{f"final_{k}":v for k,v in last_counter.items() if k != "timestamp"},
    }
    write_csv(outdir/"ncsbench-coverage.csv", [coverage])
    write_csv(outdir/"ncsbench-source-files.csv", [
        {"source_member":f.name,"bytes":f.stat().st_size,"sha256":hashlib.sha256(f.read_bytes()).hexdigest()}
        for f in sorted(folder.iterdir()) if f.is_file()])


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("measurement_dir",type=Path)
    parser.add_argument("output",type=Path)
    args=parser.parse_args()
    derive(args.measurement_dir,args.output)
