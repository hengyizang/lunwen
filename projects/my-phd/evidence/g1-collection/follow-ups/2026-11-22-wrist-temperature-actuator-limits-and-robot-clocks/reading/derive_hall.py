"""Replay the six Results/ CSV files in the earlier Hall-effect latency release.
python derive_hall.py PATH_TO_REPO OUTPUT_DIR
"""
import argparse
import csv
import hashlib
import statistics
from decimal import Decimal
from pathlib import Path


def write(out,name,rows):
    with (out/name).open("w",newline="") as fp:
        writer=csv.DictWriter(fp,rows[0].keys(),lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def run(repo,out):
    out.mkdir(parents=True,exist_ok=True)
    inv,cal,motion=[],[],[]
    for p in sorted((repo/"Results").rglob("*.csv")):
        with p.open() as fp:
            reader=csv.reader(fp);header=next(reader);r=list(reader)
        assert all(len(row)==6 and not row[header.index('')] for row in r)
        inv.append(dict(file=p.relative_to(repo).as_posix(),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),rows=len(r)))
        if p.parent.name=="Synchronization":
            assert header==['trigger_time_s','sync_offset_ns','Jitter_ns','','sync_offset_ms','Jitter_ms']
            off=[int(x[1]) for x in r];jit=[int(x[2]) for x in r]
            mismatch=sum(abs(Decimal(x[4])*1_000_000)!=abs(o) for x,o in zip(r,off))
            diffs=sum((b-a)!=c for a,b,c in zip(off,off[1:],jit[1:]))
            cal.append(dict(condition=p.stem,rows=len(off),negative_offsets=sum(n<0 for n in off),
                min_signed_ns=min(off),max_signed_ns=max(off),median_signed_ns=statistics.median(off),
                min_abs_ns=min(map(abs,off)),max_abs_ns=max(map(abs,off)),mean_abs_ns=f"{statistics.mean(map(abs,off)):.3f}",
                reported_abs_ms_mismatch=mismatch,successive_signed_difference_mismatches_excluding_first=diffs,
                first_signed_jitter_ns=jit[0],first_exported_jitter_ms=r[0][5]))
        else:
            assert header==['remote_station_s','remote_station_ns','vehicle_s','vehicle_ns','','m2m_latency_ms']
            def stamp(s,ns):return int(s)*1_000_000_000+int(ns)
            delta=[stamp(x[2],x[3])-stamp(x[0],x[1]) for x in r]
            err=[abs(Decimal(x[5])*1_000_000-v) for x,v in zip(r,delta)]
            motion.append(dict(condition=p.stem,rows=len(r),unique_instrument_pairs=len({tuple(x[:4]) for x in r}),negative_differences=sum(v<0 for v in delta),
                min_ms=f"{min(delta)/1e6:.6f}",median_ms=f"{statistics.median(delta)/1e6:.6f}",max_ms=f"{max(delta)/1e6:.6f}",
                mean_ms=f"{statistics.mean(delta)/1e6:.6f}",published_column_exact_as_ns=sum(x==0 for x in err),max_absolute_column_rounding_ns=str(max(err))))
    write(out,"hall-file-inventory.csv",inv)
    write(out,"hall-clock-calibration.csv",cal)
    write(out,"hall-motion-timing.csv",motion)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("repo",type=Path);p.add_argument("output",type=Path)
    a=p.parse_args();run(a.repo,a.output)
