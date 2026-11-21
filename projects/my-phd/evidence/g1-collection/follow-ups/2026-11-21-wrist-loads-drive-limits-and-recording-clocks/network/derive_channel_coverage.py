"""Inspect which fields and endpoints actually exist. Python >=3.11, standard library."""
import argparse
import csv
import hashlib
import io
import json
import shutil
import statistics
import urllib.request
import zipfile
from collections import defaultdict
from pathlib import Path

from derive_autopilot import verified_archives, write


def historic_trials(cache):
    rows=[]
    for record in (3602546,3630478):
        for path in verified_archives(record,cache):
            with zipfile.ZipFile(path) as z:
                for prefix in ("Autopilot_V2X_CAM_", "Autopilot_V2X_DENM_", "Autopilot_vehicle_", "Autopilot_driver_vehicle_interaction_"):
                    files=[p for p in z.namelist() if Path(p).name.startswith(prefix) and "dynamics_" not in p]
                    if not files:
                        rows.append(dict(record=record,trial=path.name.split("-")[0],stream=prefix.rstrip("_"),present=0,rows=0,distinct_loggers="",action_field=0,sent=0,received=0,speed_nonempty=0,brake_nonempty=0,detection_utc_equals_detection_raw=0))
                    for f in files:
                        with z.open(f) as src:
                            reader=csv.DictReader(io.TextIOWrapper(src,encoding="utf-8-sig"))
                            keys={key.lower().replace("_",""):key for key in reader.fieldnames}
                            station=keys.get("logstationid",keys.get("logstationnid"))
                            action=keys.get("logaction","")
                            speeds=brakes=tx=rx=n=eq=0
                            stations=set()
                            for r in reader:
                                n+=1
                                if station:stations.add(r[station])
                                tx+=r.get(action)=="SENT"
                                rx+=r.get(action)=="RECEIVED"
                                speeds+=bool(r.get(keys.get("speed","")))
                                brakes+=bool(r.get(keys.get("brakestatus","")))
                                d=r.get(keys.get("detectiontimeutc",""))
                                eq+=bool(d) and d==r.get(keys.get("detectiontime",""))
                            rows.append(dict(record=record,trial=path.name.split("-")[0],stream=prefix.rstrip("_"),present=1,rows=n,distinct_loggers="|".join(sorted(stations)),action_field=int(bool(action)),sent=tx,received=rx,speed_nonempty=speeds,brake_nonempty=brakes,detection_utc_equals_detection_raw=eq))
    return rows


def checked_files(record, cache, names):
    with urllib.request.urlopen(f"https://zenodo.org/api/records/{record}",timeout=45) as stream:
        files=json.load(stream)["files"]
    for f in sorted(files,key=lambda item:item["key"]):
        if f["key"] not in names:
            continue
        path=cache/f["key"]
        if not path.exists():
            with urllib.request.urlopen(f["links"]["self"],timeout=150) as src, path.open("wb") as out:
                shutil.copyfileobj(src,out)
        with path.open("rb") as inp:
            if "md5:"+hashlib.file_digest(inp,"md5").hexdigest()!=f["checksum"]:
                raise ValueError(f"Digest mismatch: {path}")
        yield path


def v2i(cache):
    rows=[]
    for file in checked_files(6884095,cache,{"wifi-exp-log-summary.csv"}):
        groups=defaultdict(list)
        with file.open() as src:
            for r in csv.DictReader(src):
                groups[r["traceNr"],r["wifiType"]].append(r)
        for (trace,radio),g in sorted(groups.items()):
            times={r["systime"] for r in g}
            active=[r for r in g if r["isIperfOn"]=="1" and r["isInLap"]=="1"]
            def count(sub,field,fn):
                return sum(fn(float(r[field])) for r in sub if r[field] and r[field].lower()!="nan")
            rows.append(dict(trace=trace,radio=radio,rows=len(g),distinct_seconds=len(times),active_lap_rows=len(active),
                             active_lap_received_bytes_equal_zero=count(active,"nBytesReceived",lambda x:x==0),
                             active_lap_consumer_throughput_equal_zero=count(active,"tghptConsumer",lambda x:x==0),
                             active_lap_nonzero_bytes_zero_consumer=sum(float(r["nBytesReceived"])>0 and float(r["tghptConsumer"])==0 for r in active),
                             active_lap_zero_beacons=count(active,"nBeacons",lambda x:x==0),
                             active_lap_sentinel_beacon_rssi=count(active,"meanBeaconRssi",lambda x:x==-100),
                             active_lap_nonpositive_chan_util=count(active,"channelUtil",lambda x:x<=0)))
    return rows


def aveiro(cache):
    from decimal import Decimal
    result=[]
    for file in checked_files(21644263,cache,{s+".csv" for s in ("cam","vam","camera","lidar","radar","luxonis")}):
        with file.open() as src:
            reader=csv.DictReader(src)
            groups=defaultdict(list)
            for r in reader:
                groups[r.get("stationId",r.get("stationID","all_detections"))].append(r)
        for station,records in sorted(groups.items()):
            ts=[Decimal(r["edb_insert_timestamp"]) for r in records]
            dif=[b-a for a,b in zip(ts,ts[1:])]
            lag=[(t-Decimal(r["timestamp"]))*1000 for t,r in zip(ts,records) if r.get("timestamp")]
            speeds=[float(r["speedValue"]) for r in records if r.get("speedValue")]
            gen=[int(float(r["generationDeltaTime"])) for r in records if r.get("generationDeltaTime")]
            result.append(dict(stream=file.stem,station=station,rows=len(ts),distinct_insert_times=len(set(ts)),insert_time_backsteps=sum(d<0 for d in dif),
                               observation_timestamp_rows=len(lag),insert_before_observation=sum(d<0 for d in lag),
                               median_insert_minus_observation_ms=round(statistics.median(lag),3) if lag else None,
                               min_insert_minus_observation_ms=round(min(lag),3) if lag else None,
                               max_insert_minus_observation_ms=round(max(lag),3) if lag else None,
                               generation_delta_rollbacks=sum(b<a for a,b in zip(gen,gen[1:])),defined_speed_value_rows=len(speeds),
                               exact_zero_speed_value_rows=sum(v==0 for v in speeds)))
    return result


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cache",type=Path)
    parser.add_argument("output",type=Path)
    args=parser.parse_args()
    args.cache.mkdir(parents=True,exist_ok=True)
    args.output.mkdir(parents=True,exist_ok=True)
    for label,fn in [("livorno-related-channel-coverage",historic_trials),("porto-v2i-receiver",v2i),("aveiro-source-clocks",aveiro)]:
        write(args.output/(label+".csv"),fn(args.cache))
