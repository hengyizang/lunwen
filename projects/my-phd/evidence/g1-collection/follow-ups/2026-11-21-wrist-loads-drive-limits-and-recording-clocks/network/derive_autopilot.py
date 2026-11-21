"""Reproduce from CC BY 4.0 Zenodo releases. Python >=3.11, standard library."""
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

LIVORNO = 3630479
BRAINPORT = (3603301, 3606473, 3606616)


def verified_archives(record, cache):
    url = f"https://zenodo.org/api/records/{record}"
    with urllib.request.urlopen(url, timeout=45) as stream:
        files = json.load(stream)["files"]
    for item in sorted(files, key=lambda f: f["key"]):
        path = cache / item["key"]
        if not path.exists():
            with urllib.request.urlopen(item["links"]["self"], timeout=180) as src, path.open("wb") as dst:
                shutil.copyfileobj(src, dst)
        with path.open("rb") as src:
            actual = hashlib.file_digest(src, "md5").hexdigest()
        if path.stat().st_size != item["size"] or item["checksum"] != "md5:" + actual:
            raise ValueError(f"Source mismatch: {path}")
        yield path


def read_csvs(archive, prefix):
    for path in archive.namelist():
        if Path(path).name.startswith(prefix + "_") and path.endswith(".csv"):
            with archive.open(path) as src:
                yield from csv.DictReader(io.TextIOWrapper(src, encoding="utf-8-sig"))


def json_csv(archive, prefix):
    for path in archive.namelist():
        if Path(path).name.startswith(prefix + "_") and path.endswith(".csv"):
            with archive.open(path) as src:
                lines = io.TextIOWrapper(src, encoding="utf-8-sig")
                header = next(lines).strip().split(",")
                for line in lines:
                    row = dict(zip(header, line.rstrip().split(",", len(header)-1), strict=True))
                    # JSON payload is an unescaped final column. 2019 exports add single quotes.
                    row["data"] = json.loads(row["data"].strip("'"))
                    yield row


def quantile95(values):
    return statistics.quantiles(values, n=100, method="inclusive")[94] if len(values) > 1 else values[0]


def match(tx, rx):
    def index(records):
        result = defaultdict(list)
        for key, time in records:
            result[key].append(time)
        return result
    sent, received = index(tx), index(rx)
    common = sent.keys() & received.keys()
    differences = [received[k][0]-sent[k][0] for k in common if len(received[k]) == len(sent[k]) == 1]
    return dict(tx_rows=len(tx), rx_rows=len(rx), tx_keys=len(sent), rx_keys=len(received),
                keys_on_both_ends=len(common), tx_only_keys=len(sent.keys()-received.keys()),
                rx_only_keys=len(received.keys()-sent.keys()),
                common_ambiguous_keys=len(common)-len(differences), unique_pairs=len(differences),
                rx_before_tx_pairs=sum(d < 0 for d in differences),
                min_log_delta_ms=min(differences, default=None),
                median_log_delta_ms=statistics.median(differences) if differences else None,
                p95_log_delta_ms=round(quantile95(differences), 3) if differences else None,
                max_log_delta_ms=max(differences, default=None))


def livorno(archive, trial, pairs, motion):
    cams = list(read_csvs(archive, "CAM"))
    fields = [k for k in cams[0] if not k.startswith("log_")]
    assert len(fields) == 17
    warnings = list(read_csvs(archive, "DENM"))
    speeds = list(read_csvs(archive, "Vehicle"))
    brakes = list(read_csvs(archive, "DriverVehicleInteraction"))
    for source, destination in [("3903", "3905"), ("3905", "3903")]:
        def messages(logger, action):
            return [(tuple(r[k] for k in fields), int(r["log_timestamp"])) for r in cams
                    if r["stationid"] == source and r["log_stationid"] == logger and
                    r["log_action"] == action and r["log_communicationprofile"] == "ITS_G5"]
        pairs.append(dict(trial=trial, source=source, destination=destination, **match(messages(source,"SENT"),messages(destination,"RECEIVED"))))
        events = [r for r in warnings if r["log_action"] == "RECEIVED" and r["log_stationid"] == source]
        if not events:
            continue
        assert all(r["eventcausecode"] == "12" for r in events)
        t0 = min(int(r["log_timestamp"]) for r in events)
        speed = sorted((int(r["log_timestamp"]), float(r["speed"])) for r in speeds if r["log_stationid"] == source and r["speed"])
        brake = sorted((int(r["log_timestamp"]), float(r["brakestatus"])) for r in brakes if r["log_stationid"] == source and r["brakestatus"])
        row = dict(trial=trial, receiving_station=source, recorded_denm=len(events), first_denm_log_ms=t0,
                   first_denm_detection_minus_log_ms=min(int(r["detectiontimeutc"])-t0 for r in events if int(r["log_timestamp"])==t0),
                   unique_denm_event_ids=len({(r["originatingstationid"],r["sequencenumber"]) for r in events}),
                   speed_samples=len(speed), brake_samples=len(brake))
        for delta in (0,2000,5000,10000):
            nearest = min(speed,key=lambda a:abs(a[0]-t0-delta)) if speed else None
            ok = nearest and abs(nearest[0]-t0-delta) <= 150
            row[f"native_speed_at_{delta}ms"] = nearest[1] if ok else None
            row[f"sample_offset_{delta}ms"] = nearest[0]-t0-delta if ok else None
        row.update(first_logged_speed_zero_ms_after_warning=next((t-t0 for t,v in speed if t>=t0 and v==0),None),
                   first_logged_positive_brake_ms_after_warning=next((t-t0 for t,v in brake if t>=t0 and v>0),None))
        motion.append(row)


def brainport(archive, record, trial, pairs, states, hops):
    messages = list(json_csv(archive, "IotVehicleMessage"))
    formation = list(json_csv(archive, "PlatoonFormation"))
    status = list(json_csv(archive, "PlatoonStatus"))
    positions = list(read_csvs(archive, "PositioningSystemResampled"))
    def timed(rows):
        return [(json.dumps(r["data"], separators=(",",":"), sort_keys=True), int(r["log_timestamp"])) for r in rows]
    for s,d in [("3101","3103"),("3103","3101")]:
        src = [r for r in messages if r["log_stationid"]==s and r["log_action"]=="SENT" and r["stationid"]==s and r["log_communicationprofile"]=="CELLULAR"]
        for receiver,profile in [(d,"CELLULAR"),("3199","WIRE")]:
            dst = [r for r in messages if r["log_stationid"]==receiver and r["log_action"]=="RECEIVED" and r["stationid"]==s and r["log_communicationprofile"]==profile]
            if src or dst:
                pairs.append(dict(record=record,trial=trial,topic="IotVehicleMessage",source=s,destination=receiver,destination_profile=profile,
                                  **match(timed(src),timed(dst))))
        a = [r for r in formation if r["log_stationid"]=="3199" and r["log_action"]=="SENT" and r["stationid"] in (s, "112233") and r["log_communicationprofile"]=="WIRE"]
        b = [r for r in formation if r["log_stationid"]==s and r["log_action"]=="RECEIVED" and r["log_communicationprofile"]=="CELLULAR"]
        if a or b:
            # Trial 193 labels the source's payload as a service-originated message, with no separate target field.
            # Each destination is tested against the full sender candidate set in that trial.
            mid = [r for r in formation if r["log_stationid"]=="630892900" and r["log_action"]=="RECEIVED" and r["log_communicationprofile"]=="WIRE"]
            endpoint = []
            for rows in (a, mid, b):
                by_payload = defaultdict(list)
                for key, time in timed(rows):
                    by_payload[key].append(time)
                endpoint.append(by_payload)
            triples = [(tx[0], endpoint[1][k][0], endpoint[2][k][0]) for k,tx in endpoint[0].items()
                       if len(tx)==len(endpoint[1].get(k,[]))==len(endpoint[2].get(k,[]))==1]
            if mid:
                hops.append(dict(record=record,trial=trial,destination=s,source_log="3199",intermediate_log="630892900",
                                 source_candidates=len(a),intermediate_candidates=len(mid),destination_rows=len(b),unique_payload_triplets=len(triples),
                                 middle_before_source=sum(m<t for t,m,r in triples),destination_before_middle=sum(r<m for t,m,r in triples),
                                 median_tx_to_middle_ms=statistics.median([m-t for t,m,r in triples]) if triples else None,
                                 median_middle_to_rx_ms=statistics.median([r-m for t,m,r in triples]) if triples else None,
                                 median_end_to_end_ms=statistics.median([r-t for t,m,r in triples]) if triples else None))
            pairs.append(dict(record=record,trial=trial,topic="PlatoonFormation",source="3199",destination=s,destination_profile="CELLULAR",**match(timed(a),timed(b))))
        state = [r["data"] for r in status if r["log_stationid"]==s and r["log_action"]=="SENT" and r["stationid"]==s and r["log_communicationprofile"]=="CELLULAR"]
        loc = [r for r in positions if r["log_stationid"]==s]
        v=[float(r["speed"]) for r in loc if r["speed"]]
        states.append(dict(record=record,trial=trial,station=s,platoon_status_self_sent=len(state),
                           reported_vehicle_modes="|".join(map(str,sorted({r["vehicleMode"] for r in state}))),
                           reported_platoon_states="|".join(map(str,sorted({r["platoonState"] for r in state}))),
                           resampled_position_rows=len(loc),nonempty_speed_rows=len(v),native_speed_min=min(v,default=None),
                           native_speed_max=max(v,default=None)))


def write(path,rows):
    with path.open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=rows[0].keys(),lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("cache",type=Path)
    p.add_argument("output",type=Path)
    args=p.parse_args()
    args.cache.mkdir(parents=True,exist_ok=True)
    args.output.mkdir(parents=True,exist_ok=True)
    lp, lm, bp, bs, bh = [], [], [], [], []
    for record in (LIVORNO, *BRAINPORT):
        for file in verified_archives(record,args.cache):
            trial = int(file.name.split("-")[0])
            with zipfile.ZipFile(file) as archive:
                if record==LIVORNO:
                    livorno(archive,trial,lp,lm)
                else:
                    brainport(archive,record,trial,bp,bs,bh)
    for name,rows in [("livorno-cam-pairs",lp),("livorno-warning-and-speed",lm),("brainport-message-pairs",bp),("brainport-vehicle-status",bs),("brainport-three-logger-matches",bh)]:
        write(args.output/(name+".csv"),rows)


if __name__=="__main__":
    main()
