"""Aggregate the Oslo physical manipulation experiment without re-exporting participant rows."""
import argparse
from collections import Counter, defaultdict
import csv
from itertools import product
from pathlib import Path
import numpy as np


def save(path, rows):
    with path.open("w",newline="") as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]),lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_tsv",type=Path)
    parser.add_argument("output",type=Path)
    args=parser.parse_args()
    with args.source_tsv.open(newline="",encoding="utf-8-sig") as stream:
        rows=list(csv.DictReader(stream,delimiter="\t"))
    groups,changes=[],[]
    for scope,excluded in [("all_recorded",set()),("paper_exclusions",{2,7,10,32})]:
        pool=[r for r in rows if int(r["participant"]) not in excluded]
        for task,delay in product(["JTHFT","BBT"],[0,50,100,150,200]):
            subset=[r for r in pool if r["task"]==task and int(r["latency_ms"])==delay]
            nrepeat=sum(int(r["repeat_count"]) for r in subset)
            reasons=Counter(reason.strip() for r in subset for reason in r["repeat_reasons"].split(",") if reason.strip())
            metric=[float(r["performance_metric"]) for r in subset]
            groups.append(dict(scope=scope,task=task,metric_unit="s" if task=="JTHFT" else "blocks_in_60_s",
                               injected_delay_ms=delay,complete_rows=len(subset),
                               distinct_participants=len({r["participant"] for r in subset}),
                               median_successful_metric=round(np.median(metric),5),
                               repeat_events=nrepeat,completed_trials_with_repeats=sum(int(r["repeat_count"])>0 for r in subset),
                               hardware_reason_tokens=reasons["hardware"],participant_reason_tokens=reasons["participant"],
                               other_reason_tokens=reasons["other"],unresolved_repeat_count_minus_reason_tokens=nrepeat-reasons.total()))
            if delay==0:
                continue
            pairs=defaultdict(lambda: defaultdict(list))
            for r in pool:
                if r["task"]==task and int(r["latency_ms"]) in [0,delay]:
                    pairs[r["participant"]][int(r["latency_ms"])].append(float(r["performance_metric"]))
            delta=np.array([v[delay][0]-v[0][0] for v in pairs.values() if len(v[0])==1 and len(v[delay])==1])
            changes.append(dict(scope=scope,task=task,injected_delay_ms=delay,
                                unique_baseline_condition_pairs=len(delta),
                                median_paired_change_native_units=round(np.median(delta),5),
                                worse_than_baseline=int(np.sum(delta>0 if task=="JTHFT" else delta<0)),
                                equal_to_baseline=int(np.sum(delta==0)),
                                better_than_baseline=int(np.sum(delta<0 if task=="JTHFT" else delta>0))))
    args.output.mkdir(parents=True,exist_ok=True)
    save(args.output/"oslo-condition-outcomes.csv",groups)
    save(args.output/"oslo-paired-outcomes.csv",changes)


if __name__=="__main__":
    main()
