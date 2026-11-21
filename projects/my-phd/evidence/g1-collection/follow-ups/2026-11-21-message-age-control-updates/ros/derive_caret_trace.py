"""Decode the pinned CARET single-process example using Babeltrace 2 and Python 3."""
import argparse
import csv
import hashlib
import json
import re
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median

TOPICS = ("/topic1", "/topic2", "/topic3", "/topic4", "/drive")


def verified_events(root, binary):
    src = json.loads(Path(__file__).with_name("caret-source.json").read_text())
    trace_dir = root / src["trace_path"]
    for entry in src["ctf_files"]:
        file = root / entry["path"]
        if hashlib.sha256(file.read_bytes()).hexdigest() != entry["sha256"]:
            raise ValueError(f"Unexpected CTF file: {file}")
    command = [binary, "--clock-seconds", "--names", "all", "--no-delta", "--color=never", str(trace_dir)]
    lines = subprocess.run(command, capture_output=True, text=True, check=True).stdout.splitlines()
    hosts = set()
    processes = set()
    events = []
    for line in lines:
        m = re.search(r"^timestamp = (\d+)\.(\d{9}), trace:hostname = ([^,]+), name = ([^,]+)", line)
        if not m:
            raise ValueError("Unexpected Babeltrace 2 event format")
        seconds, nanos, host, name = m.groups()
        hosts.add(host)
        pid = int(re.search(r"\bvpid = (\d+)", line)[1])
        processes.add(pid)
        tid = int(re.search(r"\bvtid = (\d+)", line)[1])
        # Only the simple integer, handle, and topic fields are used; symbol strings are immaterial.
        fields = {k: v.strip('"') for k, v in re.findall(r'(\w+) = ("[^"]*"|0x[0-9a-fA-F]+|\d+)', line.partition("event.fields = ")[2])}
        events.append((int(seconds)*10**9 + int(nanos), name.split(":")[-1], tid, fields))
    if len(events) != 2880 or len(hosts) != 1 or len(processes) != 1:
        raise ValueError("Unexpected trace event coverage or host/process scope")
    return events


def collect(events):
    pubs, subs, sub_objects, callback_topics = {}, {}, {}, {}
    requests = defaultdict(list)
    deliveries = defaultdict(list)
    pending_pub, pending_dispatch, active = {}, {}, {}
    linked = {}
    for t, n, tid, f in events:
        if n == "rcl_publisher_init":
            pubs[f["publisher_handle"]] = f["topic_name"]
        elif n == "rcl_subscription_init":
            subs[f["subscription_handle"]] = f["topic_name"]
        elif n == "rclcpp_subscription_init":
            sub_objects[f["subscription"]] = subs[f["subscription_handle"]]
        elif n == "rclcpp_subscription_callback_added":
            callback_topics[f["callback"]] = sub_objects[f["subscription"]]
        elif n == "rclcpp_publish" and pubs.get(f["publisher_handle"]) in TOPICS:
            topic = pubs[f["publisher_handle"]]
            pub = (topic, t, f["message_timestamp"])
            requests[topic].append(pub)
            key = tid, f["message"]
            if key in pending_pub:
                raise ValueError("Ambiguous pending publication")
            pending_pub[key] = pub
        elif n == "dds_bind_addr_to_stamp":
            pub = pending_pub.pop((tid, f["addr"]), None)
            if pub:
                key = pub[0], f["source_stamp"]
                if key in linked:
                    raise ValueError("Repeated DDS identifier in a topic")
                linked[key] = pub
        elif n == "dispatch_subscription_callback" and callback_topics.get(f["callback"]) in TOPICS:
            topic = callback_topics[f["callback"]]
            pub = linked[(topic, f["source_stamp"])]
            if pub[2] != f["message_timestamp"]:
                raise ValueError("Message header changed within a DDS delivery")
            key = tid, f["callback"]
            if key in pending_dispatch:
                raise ValueError("Unmatched prior dispatch")
            pending_dispatch[key] = (pub, t)
        elif n == "callback_start" and (tid, f["callback"]) in pending_dispatch:
            key = tid, f["callback"]
            if key in active:
                raise ValueError("Unmatched prior callback start")
            active[key] = (*pending_dispatch.pop(key), t)
        elif n == "callback_end" and (tid, f["callback"]) in active:
            pub, dispatch, start = active.pop((tid, f["callback"]))
            if not pub[1] <= dispatch <= start <= t:
                raise ValueError("Noncausal timestamp order")
            deliveries[pub[0]].append((pub, dispatch, start, t))
    if pending_dispatch or active:
        raise ValueError("Incomplete callback boundary")
    bound = Counter(topic for topic, stamp in linked)
    return requests, deliveries, bound


def tables(requests, deliveries, bound):
    hops = []
    for topic in TOPICS:
        recv = deliveries[topic]
        full = [start-pub[1] for pub, _, start, _ in recv]
        hops.append({"topic": topic, "rclcpp_publish": len(requests[topic]), "dds_stamp_bound_publications": bound[topic], "matched_callbacks": len(recv),
                     "distinct_published_headers": len({p[2] for p in requests[topic]}),
                     "distinct_received_headers": len({p[2] for p, _, _, _ in recv}),
                     "publish_to_start_min_ns": min(full), "publish_to_start_median_ns": median(full),
                     "publish_to_start_max_ns": max(full), "median_callback_duration_ns": median(end-start for _, _, start, end in recv)})
    stamps = {p[2]: (i, p[1]) for i,p in enumerate(requests["/topic1"], 1)}
    if "0" in stamps or len(stamps) != len(requests["/topic1"]):
        raise ValueError("Origin is not unique in this trace")
    origin = min(t for _, t in stamps.values())
    final = []
    freshest = -1
    for index, (pub, dispatch, start, end) in enumerate(sorted(deliveries["/topic4"], key=lambda x:x[2]), 1):
        seq, source = stamps[pub[2]]
        final.append({"sink_callback": index, "origin_publication_ordinal": seq,
                      "origin_publish_rel_ns":source-origin, "final_publish_rel_ns":pub[1]-origin,
                      "sink_dispatch_rel_ns":dispatch-origin, "sink_start_rel_ns":start-origin, "sink_end_rel_ns":end-origin,
                      "origin_publish_to_sink_start_ns": start-source, "newest_origin_advances": int(source>freshest)})
        freshest = max(freshest, source)
    # Integrate age from the first callback start to the last; repeating a source
    # stamp does not refresh the origin. No extrapolation through the capture edges.
    freshest_rel = -1
    area2 = 0
    peak_ns = 0
    for current, next_row in zip(final, final[1:]):
        freshest_rel = max(freshest_rel, current["origin_publish_rel_ns"])
        start = current["sink_start_rel_ns"]
        following = next_row["sink_start_rel_ns"]
        gap = following - start
        age = start - freshest_rel
        area2 += 2 * age * gap + gap * gap
        peak_ns = max(peak_ns, age + gap)
    window = final[-1]["sink_start_rel_ns"] - final[0]["sink_start_rel_ns"]
    latencies = [r["origin_publish_to_sink_start_ns"] for r in final]
    summary = [{"origin_publications":len(stamps), "sink_callbacks":len(final),
                "distinct_delivered_origins":len({r["origin_publication_ordinal"] for r in final}),
                "advancing_updates":sum(r["newest_origin_advances"] for r in final),
                "publish_to_sink_start_min_ns":min(latencies), "publish_to_sink_start_median_ns":median(latencies),
                "publish_to_sink_start_max_ns":max(latencies), "age_window_ns":window,
                "twice_integrated_age_ns2":area2, "time_average_age_ms":round(area2/(2*window*1_000_000), 6),
                "peak_age_before_next_callback_ns":peak_ns}]
    return hops, final, summary


def write(path, rows):
    with path.open("w", encoding="utf-8", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=rows[0], lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkout", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--babeltrace2", default="babeltrace2")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    hops, final, summary = tables(*collect(verified_events(args.checkout, args.babeltrace2)))
    write(args.output_dir/"caret-topic-timing.csv", hops)
    write(args.output_dir/"caret-sink-updates.csv", final)
    write(args.output_dir/"caret-software-age.csv", summary)
