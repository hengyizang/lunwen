"""Audit the public Results/ tree at sntubix/e2e_latency commit abdde3817cfdcff8818a64b58f437827ec19a599.
Run python derive_vehicle.py PATH_TO_REPO OUTPUT_DIR. All epoch arithmetic uses integer nanoseconds.
"""
import argparse
import csv
import hashlib
import statistics
import struct
from pathlib import Path

HEAD = ["VEHICLE_GY_ON","VEHICLE_GY_OFF","LED_ON","STATION_GY_ON","STATION_GY_OFF","PHOTOTRANSISTOR"]
SCALE = 1_000_000


def write(out, name, rows):
    with (out / name).open("w", newline="") as fp:
        w = csv.DictWriter(fp, fieldnames=rows[0].keys(),lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def quantile(x, p):
    """Linear interpolation between adjacent ordered samples (type 7)."""
    x = sorted(x)
    pos = (len(x) - 1) * p
    lo = int(pos)
    return x[lo] + (x[min(lo+1,len(x)-1)] - x[lo]) * (pos-lo)


def pcap(path):
    with path.open("rb") as f:
        head = f.read(24)
        assert head[:4] == bytes.fromhex("d4c3b2a1")
        version_major,version_minor,_,_,snaplen,link=struct.unpack("<HHIIII",head[4:])
        assert (version_major,version_minor,link)==(2,4,101)
        count=short=reverse=0
        first=last=None
        while h:=f.read(16):
            if len(h)!=16: raise ValueError("partial pcap header")
            sec, micro, cap, wire=struct.unpack("<IIII",h)
            assert micro<1_000_000 and cap<=snaplen and cap<=wire
            if len(f.read(cap))!=cap: raise ValueError("partial pcap frame")
            t=sec*1_000_000+micro
            if first is None:first=t
            if last is not None and t<last:reverse+=1
            last=t
            short+=cap<wire
            count+=1
    return dict(file=path.name,format="pcap 2.4 little-endian microsecond timestamps; raw IP",frames=count,
                truncated_frames=short,decreasing_capture_time=reverse,span_seconds=f"{(last-first)/1e6:.6f}")


def run(repo,out):
    out.mkdir(parents=True,exist_ok=True)
    inv,summary,quality,pcaps=[],[],[],[]
    for path in sorted((repo/"Results").rglob("*")):
        if not path.is_file():continue
        rel=path.relative_to(repo).as_posix()
        digest=hashlib.sha256(path.read_bytes()).hexdigest()
        if path.suffix!=".csv":
            entry=pcap(path);pcaps.append(entry); n=entry["frames"]
        elif path.name.startswith("Camera_"):
            with path.open() as fp:
                r=csv.reader(fp);assert next(r)==["LATENCY (ms)"]
                data=[float(row[0]) for row in r]
            n=len(data)
            for k,v in [("camera_and_monitor_file_ms",data)]:
                summary.append(dict(file=rel,metric=k,unit="ms",rows=n,negative_rows=sum(i<0 for i in v),minimum=f"{min(v):.6f}",p25=f"{quantile(v,.25):.6f}",median=f"{quantile(v,.5):.6f}",p75=f"{quantile(v,.75):.6f}",maximum=f"{max(v):.6f}",mean=f"{statistics.mean(v):.6f}"))
        else:
            with path.open() as fp:
                r=csv.reader(fp);assert next(r)==HEAD
                data=[tuple(map(int,row)) for row in r]
            assert all(len(v)==6 for v in data)
            n=len(data);m2m=[v[0]-v[3] for v in data];g2g=[v[5]-v[2] for v in data]
            led=[v[2]-v[0] for v in data]
            # Station clock end-to-end, subtract the vehicle-clock LED trigger interval.
            e2e=[(v[5]-v[3])-(v[2]-v[0]) for v in data]
            assert all(a+b==c for a,b,c in zip(m2m,g2g,e2e))
            for k,vs in [("steering_onset_vehicle_minus_station_signed",m2m),("steering_onset_absolute_in_source_script",list(map(abs,m2m))),("screen_light_minus_vehicle_LED_signed",g2g),("corrected_station_loop",e2e),("vehicle_LED_minus_vehicle_onset",led)]:
                conv=lambda y:f"{y/SCALE:.6f}"
                summary.append(dict(file=rel,metric=k,unit="ms",rows=n,negative_rows=sum(i<0 for i in vs),minimum=conv(min(vs)),p25=conv(quantile(vs,.25)),median=conv(quantile(vs,.5)),p75=conv(quantile(vs,.75)),maximum=conv(max(vs)),mean=conv(statistics.mean(vs))))
            quality.append(dict(file=rel,rows=n,unique_six_event_rows=len(set(data)),
                station_onset_non_increasing=sum(x[3]>=y[3] for x,y in zip(data,data[1:])),
                vehicle_end_before_start=sum(x[1]<x[0] for x in data),station_end_before_start=sum(x[4]<x[3] for x in data),
                abs_two_component_sum_differs_from_signed_e2e=sum(abs(a)+abs(b)!=c for a,b,c in zip(m2m,g2g,e2e))))
        inv.append(dict(file=rel,bytes=path.stat().st_size,sha256=digest,records_or_frames=n))
    write(out,"vehicle-file-inventory.csv",inv)
    write(out,"vehicle-timing.csv",summary)
    write(out,"vehicle-quality.csv",quality)
    write(out,"vehicle-capture-coverage.csv",pcaps)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo",type=Path);parser.add_argument("output",type=Path)
    args=parser.parse_args()
    run(args.repo,args.output)
