"""Summarize timed application events from the pinned Aalborg GRAB repository.
python derive_aalborg.py PATH_TO_REPO OUTPUT_DIR
The repository's MQTT/saved_data/ tree is the input. Standard library only.
"""
import argparse
import csv
import hashlib
import math
from decimal import Decimal
from pathlib import Path

HEAD = ["Controller sends target", "Arm receives target", "Arm sends current", "Controller receives current"]
PAPER = {"5.5h_5g", "5.5h_ethernet"}
MILLION = 1_000_000
NS = 1_000_000_000


def ns(s):
    scaled = Decimal(s) * NS
    if scaled != scaled.to_integral_value():
        raise ValueError("input cannot be exactly represented in nanoseconds")
    return int(scaled)


def quantile(values, p):
    x = sorted(values)
    return x[max(0, math.ceil(p * len(x)) - 1)]


def ms(value):
    return f"{value / MILLION:.6f}"


def us(value):
    return f"{value / 1000:.3f}"


def write(out, name, rows):
    with (out / name).open("w", newline="") as fp:
        w = csv.DictWriter(fp, rows[0].keys(), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def run(repo, out):
    src = repo / "MQTT" / "saved_data"
    out.mkdir(parents=True, exist_ok=True)
    inv, arm_rows, pair_rows, clock_rows, case = [], [], [], [], {}
    seen_arm_records = set()
    for path in sorted(src.rglob("*.csv")):
        rel = path.relative_to(repo).as_posix()
        campaign = "5h_unspecified_link" if path.parent == src else path.parent.name
        arm = path.stem[-1] if "data_arm_" in path.stem else ""
        with path.open(newline="") as fp:
            reader = csv.reader(fp)
            hdr = next(reader)
            data = [[ns(v) for v in r] for r in reader]
        fields = len(hdr)
        if not data or any(len(r) != fields for r in data):
            raise ValueError(path)
        inv.append(dict(file=rel, bytes=path.stat().st_size, sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                        campaign=campaign, paper_designated=int(campaign in PAPER), fields=fields, data_rows=len(data)))
        if arm:
            assert hdr == HEAD
            case.setdefault(campaign, {})[arm] = data
            down = [r[1]-r[0] for r in data]
            up = [r[3]-r[2] for r in data]
            end = [r[3]-r[0] for r in data]
            records = {tuple(r) for r in data}
            overlaps = len(records & seen_arm_records)
            seen_arm_records.update(records)
            arm_rows.append(dict(campaign=campaign, paper_designated=int(campaign in PAPER), arm=arm,
                rounds=len(data), unique_four_stamp_rows=len(records), overlap_with_earlier_files=overlaps,
                descending_or_equal_dispatches=sum(a[0]>=b[0] for a,b in zip(data,data[1:])),
                within_arm_receive_after_feedback=sum(r[1]>r[2] for r in data),
                cross_host_down_negative=sum(d<0 for d in down), cross_host_up_negative=sum(u<0 for u in up),
                down_min_ms=ms(min(down)), down_p50_ms=ms(quantile(down,.5)), down_p999_ms=ms(quantile(down,.999)),down_max_ms=ms(max(down)),
                up_min_ms=ms(min(up)), up_p50_ms=ms(quantile(up,.5)), up_p999_ms=ms(quantile(up,.999)), up_max_ms=ms(max(up)),
                controller_dispatch_to_return_p50_ms=ms(quantile(end,.5)), controller_dispatch_to_return_max_ms=ms(max(end))))
        else:
            assert hdr==["NTP offset"]
            vals=[r[0] for r in data]
            clock_rows.append(dict(campaign=campaign,paper_designated=int(campaign in PAPER), host=path.stem.split("_ntp")[0], rows=len(vals),
                distinct_values=len(set(vals)),adjacent_equal=sum(a==b for a,b in zip(vals,vals[1:])),
                min_us=us(min(vals)),p50_us=us(quantile(vals,.5)),p999_abs_us=us(quantile(list(map(abs,vals)),.999)),max_us=us(max(vals))))
    for c,k in sorted(case.items()):
        a,b=k["1"],k["2"]
        assert len(a)==len(b)
        dispatch=[y[0]-x[0] for x,y in zip(a,b)]
        receive=[y[1]-x[1] for x,y in zip(a,b)]
        # The controller creates one target before publishing arm 1 then arm 2.
        # Its dispatch plus 20 ms is the reported target in the two paper traces.
        target=20*MILLION
        if c in PAPER:
            late1=sum(x[1]-x[0]>target for x in a)
            late2=sum(y[1]-x[0]>target for x,y in zip(a,b))
            both=sum(x[1]-x[0]>target and y[1]-x[0]>target for x,y in zip(a,b))
            either=late1+late2-both
        else:
            late1=late2=both=either=""
        pair_rows.append(dict(campaign=c,paper_designated=int(c in PAPER),paired_by_move_row=len(a),
                same_controller_arm2_publish_precedes_arm1=sum(v<0 for v in dispatch),
                dispatch_skew_p50_ms=ms(quantile(dispatch,.5)), dispatch_skew_max_ms=ms(max(dispatch)),
                arm_receipt_signed_arm2_minus_arm1_min_ms=ms(min(receive)), receipt_signed_max_ms=ms(max(receive)),
                receipt_abs_p50_ms=ms(quantile(list(map(abs,receive)),.5)),
                receipt_abs_p999_ms=ms(quantile(list(map(abs,receive)),.999)), receipt_abs_max_ms=ms(max(map(abs,receive))),
                arm1_recorded_arrivals_after_common_20ms=late1, arm2_recorded_arrivals_after_common_20ms=late2,
                either_after_common_20ms=either,both_after_common_20ms=both))
    write(out,"aalborg-file-inventory.csv",inv)
    write(out,"aalborg-arm-timing.csv",arm_rows)
    write(out,"aalborg-paired-arrivals.csv",pair_rows)
    write(out,"aalborg-clock-offsets.csv",clock_rows)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo",type=Path)
    parser.add_argument("output",type=Path)
    args=parser.parse_args()
    run(args.repo,args.output)
