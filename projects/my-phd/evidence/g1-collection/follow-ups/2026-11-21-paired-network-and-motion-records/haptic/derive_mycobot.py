"""Measure missing RTTs and ordering sensitivity in the MyCobot 4G command log.

Input is Zenodo 23689905's data_pergerakan_robot.csv. Requires Python and NumPy.
Server timestamps record the arrival of a follow-up log request. Estimates of
the browser completion instant can differ by an extra, unknown one-way delay.
"""
from collections import defaultdict
import argparse
import csv
from datetime import datetime
from pathlib import Path
import numpy as np


def write_table(path, rows):
    with path.open("w",newline="") as stream:
        writer=csv.DictWriter(stream,fieldnames=rows[0],lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_csv",type=Path)
    parser.add_argument("output",type=Path)
    args=parser.parse_args()
    days=defaultdict(list)
    modes=defaultdict(list)
    with args.source_csv.open(newline="",encoding="utf-8-sig") as stream:
        for row in csv.DictReader(stream):
            clock=datetime.fromisoformat(row["Masa (Timestamp)"])
            midnight=clock.replace(hour=0,minute=0,second=0,microsecond=0)
            complete=round((clock-midnight).total_seconds()*1000)
            latency=int(row["Kelewatan Ping (ms)"])
            if latency<0:
                raise ValueError("Negative latency")
            days[clock.date().isoformat()].append((complete,latency))
            mode=row["Mod Kawalan"]
            modes[mode].append(latency)
    mode_rows=[]
    for mode,values in sorted(modes.items()):
        observed=[v for v in values if v>0]
        mode_rows.append(dict(mode=mode,records=len(values),zero_rtt=len(values)-len(observed),
                              positive_rtt=len(observed),
                              median_positive_rtt_ms="" if not observed else float(np.median(observed)),
                              p95_positive_rtt_ms="" if not observed else round(np.quantile(observed,.95),3)))
    pairs=[]
    for day,values in sorted(days.items()):
        complete,latency=np.array([(t,l) for t,l in values if l>0],dtype=int).T
        emit=complete-latency
        for bound in (0,10,25,50,100):
            inversions=0
            same_finish=0
            later_affected=set()
            for index,c in enumerate(complete):
                # The later estimated emission (index) has an earlier server
                # finish proxy than j. Count each oriented pair exactly once.
                where=(emit[index]-emit>bound) & (complete-c>bound)
                inversions+=int(where.sum())
                if where.any():
                    later_affected.add(index)
                same_finish+=int(np.count_nonzero(complete[index+1:]==c))
            pairs.append(dict(server_calendar_date=day,raw_rows=len(values),positive_rtt_rows=len(emit),
                              zero_rtt_rows=len(values)-len(emit),sensitivity_bound_ms=bound,
                              unordered_positive_pairs=len(emit)*(len(emit)-1)//2,
                              pairs_with_identical_server_finish=same_finish,
                              pairs_reversed_beyond_bound=inversions,
                              distinct_later_emitted_rows_in_reversed_pairs=len(later_affected)))
    args.output.mkdir(exist_ok=True,parents=True)
    write_table(args.output/"mycobot-rtt-modes.csv",mode_rows)
    write_table(args.output/"mycobot-order-sensitivity.csv",pairs)


if __name__=="__main__":
    main()
