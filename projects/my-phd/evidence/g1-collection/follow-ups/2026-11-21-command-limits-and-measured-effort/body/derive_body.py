"""Compute per-segment command/feedback aggregates for the pinned commabody release.
Usage: python derive_body.py RAW_ROOT OUTPUT [--workers 3]
fetch_body.py prepares RAW_ROOT. This script downloads the verified recorded schemas on demand.
"""
import argparse
import bz2
from concurrent.futures import ProcessPoolExecutor
import csv
import hashlib
import json
from pathlib import Path
import struct
import subprocess
from urllib.error import URLError
from urllib.request import Request, urlopen
import numpy as np
import capnp


DATA_REV = "16123f8d2cf28e39cf52e0e1bfb5c0e6975287d0"
CODE = "bc6c6421a99da5a5d7b5ece0da17174646b6a78d"
CEREAL = "b1a1afebb8533a96ff0e8efbba7c10eb47df2af0"
SCHEMA_HASHES = {
    'car.capnp': '1697ed57c29e7959231ccd6713a25ca953093585423fd354e09a6f0e7aa0648a',
    'custom.capnp': '07aef2024e92fd13f2bb38c89e8b27885fedc28c8f7dd9ec7e5cbbd6f29a72d9',
    'include/c++.capnp': 'fb306076cd38c27af1aed20fac6395e9a46fbe5b5df6a248b5f1b6845a079c44',
    'legacy.capnp': '4ab15bad593a3433dab2d3c8f9951fa4fbadea2074ca0ebb082139ed38f25131',
    'log.capnp': '9553c2878593297827d18d5c7d9cc68501b555ca376c3189bcfbd434bdd0edf2',
    'maptile.capnp': 'f979c4d96901f210d1f5b2b1a68073e525ae736e3937897b5c803d054806fabd',
}
ALT_CODE = "469c225442455b1a90048337ac1ffa2bab5f36c4"
ALT_CEREAL = "a44f6c5499753f4c0a2e35dd63947f4937b4b8dc"
ALT_LOG_HASH = "b9242672116f9750abd4cf2c5b6d21d5ea30d2e6611108ee0b665c1149e075c3"
WINDOW_NS = 10_000_000
EVENT = None


def schema(root, alternate=False):
    dest = (root / "body-alternate" if alternate else root) / "recorded-schema"
    hashes = dict(SCHEMA_HASHES)
    revision = ALT_CEREAL if alternate else CEREAL
    if alternate:
        hashes["log.capnp"] = ALT_LOG_HASH
    for file, expected in hashes.items():
        p = dest / file
        if not p.exists():
            p.parent.mkdir(parents=True, exist_ok=True)
            url="https://raw.githubusercontent.com/commaai/cereal/" + revision + "/" + file
            try:
                with urlopen(url,timeout=30) as response:
                    blob=response.read()
            except URLError:
                api="https://api.github.com/repos/commaai/cereal/contents/" + file + "?ref=" + revision
                try:
                    with urlopen(Request(api,headers={"Accept":"application/vnd.github.raw+json"}),timeout=30) as response:
                        blob=response.read()
                except URLError:
                    endpoint="repos/commaai/cereal/contents/" + file + "?ref=" + revision
                    blob=subprocess.check_output(["gh","api","-H","Accept: application/vnd.github.raw+json",endpoint])
            if hashlib.sha256(blob).hexdigest()!=expected:
                raise ValueError("Downloaded schema checksum mismatch: " + file)
            p.write_bytes(blob)
        if hashlib.sha256(p.read_bytes()).hexdigest() != expected:
            raise ValueError("Schema checksum mismatch: " + file)
    return dest


def init_worker(dest):
    global EVENT
    EVENT = capnp.load(str(dest / "log.capnp"), imports=[str(dest)]).Event


def ordered(rows, width):
    a = np.asarray(rows, dtype=np.int64).reshape(-1, width)
    # CAN frames in a packet share an event timestamp: preserve their source order.
    return a[np.argsort(a[:, 0], kind="stable")]


def nearest(query, stream):
    """First closest host-event stamp; prefer predecessor at an equal distance."""
    assert len(stream)
    at = np.searchsorted(stream[:, 0], query)
    previous = np.maximum(at-1, 0)
    following = np.minimum(at, len(stream)-1)
    return np.where(np.abs(stream[previous,0]-query) <= np.abs(stream[following,0]-query), previous, following)


def compare(query, stream, tag, with_counter):
    key = {"kind":tag, "query_events":len(query), "candidate_events":len(stream), "window_ms":10}
    for name in ["nearest_in_window","nearest_identical_wheel_pair","nearest_identical_full_payload",
                 "any_same_key_in_window","unique_same_key_in_window","multiple_same_key_in_window",
                 "unique_same_key_used_by_one_query","nearest_identical_pair_median_candidate_minus_query_ms",
                 "future_window_ms","future_any_same_key","future_unique_same_key","future_multiple_same_key",
                 "future_unique_used_by_one_query","future_unique_median_candidate_minus_query_ms","future_unique_p95_candidate_minus_query_ms"]:
        key[name] = None
    if not len(stream) or not len(query):
        return key
    indexes = nearest(query[:,0],stream)
    linked = stream[indexes]
    dt = linked[:,0]-query[:,0]
    close = np.abs(dt) <= WINDOW_NS
    exact = close & np.all(query[:,1:3] == linked[:,1:3], axis=1)
    key.update(nearest_in_window=int(close.sum()),nearest_identical_wheel_pair=int(exact.sum()))
    if exact.any():
        key["nearest_identical_pair_median_candidate_minus_query_ms"] = np.median(dt[exact])/1e6
    if with_counter:
        key["nearest_identical_full_payload"]=int((exact & (linked[:,3]==query[:,3])).sum())
    # Group candidates by full payload (CAN echo) or wheel-pair only (published report).
    from collections import defaultdict
    groups=defaultdict(list)
    ncols=4 if with_counter else 3
    for i, row in enumerate(stream):
        groups[tuple(row[1:ncols])].append((row[0],i))
    groups={k:np.asarray(v,np.int64) for k,v in groups.items()}
    from bisect import bisect_left, bisect_right
    multiplicity=np.zeros(len(query),dtype=int)
    use=np.zeros(len(stream),dtype=int)
    future_latency=[]
    future_multiple=0
    future_use=np.zeros(len(stream),dtype=int)
    for i,row in enumerate(query):
        g=groups.get(tuple(row[1:ncols]))
        if g is None:continue
        lo=bisect_left(g[:,0],row[0]-WINDOW_NS)
        hi=bisect_right(g[:,0],row[0]+WINDOW_NS)
        multiplicity[i]=hi-lo
        if hi-lo==1:use[g[lo,1]]+=1
        left=bisect_left(g[:,0],row[0])
        right=bisect_right(g[:,0],row[0]+2*WINDOW_NS)
        if right-left==1:
            future_latency.append(g[left,0]-row[0])
            future_use[g[left,1]]+=1
        elif right-left>1:
            future_multiple+=1
    key.update(future_window_ms=20,future_any_same_key=len(future_latency)+future_multiple,
               future_unique_same_key=len(future_latency),future_multiple_same_key=future_multiple,
               future_unique_used_by_one_query=int((future_use==1).sum()))
    if future_latency:
        key.update(future_unique_median_candidate_minus_query_ms=np.median(future_latency)/1e6,
                   future_unique_p95_candidate_minus_query_ms=np.quantile(future_latency,.95)/1e6)
    key.update(any_same_key_in_window=int((multiplicity>0).sum()),unique_same_key_in_window=int((multiplicity==1).sum()),
               multiple_same_key_in_window=int((multiplicity>1).sum()),unique_same_key_used_by_one_query=int((use==1).sum()))
    return key


def pair_feedback(candidates, stream, side, signal, regime):
    row=dict(side=("left","right")[side],command_regime=regime,
             channel=signal,commands=len(candidates),nearest_within_10ms=0,distinct_used_sensor_frames=0,
             nonzero_sensor_samples=0,matched_signed_sum=0,matched_abs_sum=0,matched_sq_sum=0,
             matched_signed_min=None,matched_signed_max=None,abs_host_dt_median_ms=None)
    if not len(candidates) or not len(stream):return row
    idx=nearest(candidates[:,0],stream)
    delay=np.abs(stream[idx,0]-candidates[:,0])
    keep=delay<=WINDOW_NS
    idx=idx[keep]
    if not len(idx):return row
    field=1+side if signal=="wheel_speed" else 1+2*side+(signal=="phase_BC")
    v=stream[idx,field]
    row.update(nearest_within_10ms=len(v),distinct_used_sensor_frames=len(np.unique(idx)),
               nonzero_sensor_samples=int(np.count_nonzero(v)),matched_signed_sum=int(v.sum()),
               matched_abs_sum=int(abs(v).sum()),matched_sq_sum=int((v*v).sum()),
               matched_signed_min=int(v.min()),matched_signed_max=int(v.max()),
               abs_host_dt_median_ms=np.median(delay[keep])/1e6)
    return row


def derive(args):
    path, expected, label = args
    compressed=path.read_bytes()
    digest=hashlib.sha256(compressed).hexdigest()
    assert digest==expected
    raw=bz2.decompress(compressed)
    sent,echo,wheel,current,report=[],[],[],[],[]
    init_count=commit_count=wheeled_count=platform_count=0
    recorded_commit=None
    platform_checks=0
    state_counts=np.zeros(7,dtype=np.int64)
    for e in EVENT.read_multiple_bytes(raw,traversal_limit_in_words=2**25):
        kind=e.which()
        if kind=="initData":
            d=e.initData
            init_count+=1
            recorded_commit=str(d.gitCommit)
            expected=ALT_CODE if label.startswith("S06-") and int(label[4:])>=5 else CODE
            assert recorded_commit==expected
            commit_count+=recorded_commit==expected
            wheeled_count+=any(x.key=="WheeledBody" and bytes(x.value)==b"1" for x in d.params.entries)
        elif kind=="carParams":
            platform_checks+=1
            platform_count+=e.carParams.carFingerprint=="COMMA BODY"
        elif kind=="carState":
            st=e.carState
            w=st.wheelSpeeds
            state_counts+=(1,w.fl!=0,w.fr!=0,w.rl!=0,w.rr!=0,st.steeringTorque!=0,st.steeringTorqueEps!=0)
        elif kind=="carControl":
            v=e.carControl
            out=v.actuatorsOutput
            left,right=out.accel,out.steer
            assert left==int(left) and right==int(right)
            report.append((int(e.logMonoTime),int(left),int(right),int(v.enabled),
                           int(len(v.orientationNED)>1 and len(v.angularVelocity)>1),
                           int(out.steerOutputCan==right)))
        elif kind in ("can","sendcan"):
            t=int(e.logMonoTime)
            for m in getattr(e,kind):
                address=m.address
                if address not in (513,516,592):continue
                src=m.src
                if address==592 and ((kind=="sendcan" and src==0) or (kind=="can" and src==128)):
                    val=bytes(m.dat)
                    assert len(val)==6
                    left,right,tail=struct.unpack(">hhH",val)
                    (sent if kind=="sendcan" else echo).append((t,left,right,tail))
                elif kind=="can" and src==0 and address in (513,516):
                    val=bytes(m.dat)
                    assert len(val)==8
                    target,row=(wheel,struct.unpack(">hh",val[:4])) if address==513 else (current,struct.unpack(">hhhh",val))
                    target.append((t,*row))
    cfg=dict(segment=label,recorded_openpilot_commit=recorded_commit,rlog_sha256=digest,compressed_bytes=len(compressed),init_records=init_count,
             init_expected_revision=commit_count,init_wheeled_body_1=wheeled_count,carparams_records=platform_checks,
             carparams_comma_body=platform_count)
    sent,echo,wheel,current,report=(ordered(v,c) for v,c in [(sent,4),(echo,4),(wheel,3),(current,5),(report,6)])
    cfg.update(sent_592=len(sent),echo_592=len(echo),wheel_513=len(wheel),current_516=len(current),
               published_carcontrol=len(report),enabled_reports=int(report[:,3].sum()),
               enabled_pose_valid_reports=int((report[:,3]*report[:,4]).sum()),
               right_steerOutputCan_equal=int(report[:,5].sum()),
               outside_bound_wheel_slots=int((np.abs(sent[:,1:3])>500).sum()),
               both_wheels_zero_send=int(np.all(sent[:,1:3]==0,axis=1).sum()),
               either_wheel_at_rail_send=int(np.any(abs(sent[:,1:3])==500,axis=1).sum()),
               consecutive_equal_wheel_pair=int(np.all(np.diff(sent[:,1:3],axis=0)==0,axis=1).sum()))
    for i,n in enumerate(["left_AB","left_BC","right_AB","right_BC"]):
        cfg["nonzero_raw_current_"+n]=int(np.count_nonzero(current[:,1+i]))
    for side,n in enumerate(["left","right"]):
        u=sent[:,1+side]
        cfg[n+"_abs_command_max"]=int(abs(u).max()) if len(u) else None
        cfg[n+"_abs_step_50"]=int((abs(np.diff(u))==50).sum())
        cfg[n+"_abs_step_over_50"]=int((abs(np.diff(u))>50).sum())
        cfg[n+"_negative_rail"]=int((u==-500).sum())
        cfg[n+"_positive_rail"]=int((u==500).sum())
    cfg["disabled_nonzero_report"]=int(((report[:,3]==0) & np.any(report[:,1:3]!=0,axis=1)).sum())
    cfg.update(zip(["carstate_count","nonzero_state_forward_left","nonzero_state_forward_right",
                    "nonzero_state_rear_left","nonzero_state_rear_right","nonzero_state_steering_torque",
                    "nonzero_state_steering_torque_eps"], map(int,state_counts)))
    match=[compare(sent,report[:,:3],"sent_to_published_report",False),
           compare(sent,echo,"sent_to_bus_echo",True)]
    feedback, steps=[],[]
    for side in (0,1):
        absolute=abs(sent[:,1+side])
        change=abs(np.diff(sent[:,1+side]))
        gap=np.diff(sent[:,0])
        regular=(gap>=5_000_000)&(gap<=15_000_000)
        for name,stream in [("wheel_speed",wheel),("phase_AB",current),("phase_BC",current)]:
            for regime,mask in [("inside_abs_500",absolute<500),("at_abs_500",absolute==500)]:
                feedback.append(pair_feedback(sent[mask],stream,side,name,regime))
            for regime,mask in [("abs_step_0",change==0),("abs_step_1_to_49",(change>0)&(change<50)),
                                ("abs_step_50",change==50),("abs_step_above_50",change>50)]:
                steps.append(pair_feedback(sent[1:][regular&mask],stream,side,name,regime))
    return (cfg, *[[dict(segment=label,**v) for v in table] for table in (match,feedback,steps)])



def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root",type=Path)
    parser.add_argument("output",type=Path)
    parser.add_argument("--workers",type=int,default=3)
    a=parser.parse_args()
    tasks=[]
    for i,count in enumerate([12,12,12,11,11,11]):
        folder=a.root/"body"/f"data-{i:05d}"
        receipt=json.loads((folder/"complete.json").read_text())
        assert len(receipt["logs"])==count
        for j,log in enumerate(receipt["logs"]):
            tasks.append((folder/log["member"],log["sha256"],f"S{i+1:02d}-{j+1:02d}"))
    assert len(tasks)==69 and len(set(t[1] for t in tasks))==69
    a.output.mkdir(parents=True,exist_ok=True)
    # Separate workers isolate the two Cap'n Proto schemas sharing schema IDs.
    # The seven final archive members identify the second recording revision in initData.
    results=[]
    for alternate,group in [(False,tasks[:-7]),(True,tasks[-7:])]:
        dest=schema(a.root,alternate)
        with ProcessPoolExecutor(a.workers,initializer=init_worker,initargs=(dest,)) as pool:
            results.extend(pool.map(derive,group))
    for name, rows in [("body-segments",[x[0] for x in results]),
                       ("body-message-match",[r for x in results for r in x[1]]),
                       ("body-feedback",[r for x in results for r in x[2]]),
                       ("body-command-steps",[r for x in results for r in x[3]])]:
        with (a.output/(name+".csv")).open("w",newline="") as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator="\n")
            w.writeheader()
            w.writerows(rows)


if __name__=="__main__":
    main()
