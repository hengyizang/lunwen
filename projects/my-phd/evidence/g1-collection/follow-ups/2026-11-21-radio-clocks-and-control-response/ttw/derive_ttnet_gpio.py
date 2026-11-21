"""Audit four complete FlockLab trial members. Input directory contains TEST_ID.tar.gz."""
from collections import Counter,defaultdict
from decimal import Decimal
from pathlib import Path
import argparse,csv,hashlib,io,tarfile
from zipfile import ZipFile

TESTS = ("66873", "67353", "68673", "69155")


def summarize(root, test, serial):
    with tarfile.open(root/f"{test}.tar.gz") as tar:
        def member(name):
            return tar.extractfile(f"{test}/{name}.csv").read()
        def rows(data):
            return csv.DictReader(io.StringIO(data.decode("utf-8")))
        if member("serial") != serial:
            raise ValueError(f"Serial log mismatch, trial {test}")
        commands = list(rows(member("gpioactuation")))
        if {r["pin_name"] for r in commands} != {"RST"}:
            raise ValueError("Unexpected actuated channel")
        skew = [abs(Decimal(r["timestamp_executed"])-Decimal(r["# timestamp_planned"])) for r in commands]
        counts = Counter()
        nodes = defaultdict(set)
        previous = {}
        before = None
        backwards = 0
        same_node_before = 0
        traced = member("gpiotracing")
        for r in rows(traced):
            stamp = Decimal(r["# timestamp"])
            pin,node=r["pin_name"],r["node_id"]
            counts[pin]+=1
            nodes[pin].add(node)
            if before is not None and stamp<before:
                backwards+=1
            if node in previous and stamp<previous[node]:
                same_node_before+=1
            previous[node]=stamp
            before=stamp
        reset_nodes={r["node_id"] for r in commands}
        return dict(test_id=test, nested_archive_sha256=hashlib.sha256((root/f"{test}.tar.gz").read_bytes()).hexdigest(),
                    tracing_sha256=hashlib.sha256(traced).hexdigest(),
                    verified_same_serial_as_full_dataset=1, logged_actuation_pin="RST",
                    reset_rows=len(commands), reset_nodes=len(reset_nodes),
                    max_abs_planned_minus_executed_reset_us=str(max(skew)*1000000),
                    observed_edges=sum(counts.values()), cross_log_time_backsteps=backwards,
                    within_node_time_backsteps=same_node_before,
                    pin_edges="|".join(f"{k}={v}" for k,v in sorted(counts.items())),
                    pin_nodes="|".join(f"{k}={len(v)}" for k,v in sorted(nodes.items())))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for arg in ("root","serial_zip","out"):
        parser.add_argument(arg,type=Path)
    a=parser.parse_args()
    result=[]
    with ZipFile(a.serial_zip) as z:
        for test in TESTS:
            path,=[n for n in z.namelist() if f"/{test}_" in n and n.endswith("/serial.csv")]
            result.append(summarize(a.root,test,z.read(path)))
    a.out.mkdir(exist_ok=True,parents=True)
    with (a.out/"ttnet-gpio-sample.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=result[0],lineterminator="\n");w.writeheader();w.writerows(result)


if __name__=="__main__":
    main()
