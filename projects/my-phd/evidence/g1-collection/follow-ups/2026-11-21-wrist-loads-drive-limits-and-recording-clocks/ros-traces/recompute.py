"""Recompute with Python 3 and Babeltrace 2 CLI (2.0.4 was used)."""
import argparse
import csv
import hashlib
import io
import json
import math
import pickle
import pickletools
import re
import statistics
import subprocess
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path


PING_REPO = 'ros-tracing/tracetools_analysis'
PING_COMMIT = 'caa8c05158bb2f898e1632188e57eb58c5e88d05'
PING_PATH = 'tracetools_analysis/analysis/sample_data/converted_pingpong'
ROS_REPO = 'eclipse-tracecompass/tracecompass-test-traces'
ROS_COMMIT = '51217fafe19c7d614f83175fc359f770968aa347'
ROS_PREFIX = 'ctf/src/main/resources/ros2/'
ALLOWED_PICKLE = set('PROTO FRAME EMPTY_DICT MEMOIZE MARK SHORT_BINUNICODE LONG1 BININT BINGET BININT1 SETITEMS STOP BINUNICODE BININT2'.split())
TOPICS = ('/topic_a', '/topic_b')


def get_file(target, repo, revision, path, blob):
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        with urllib.request.urlopen(f'https://raw.githubusercontent.com/{repo}/{revision}/{path}') as response:
            target.write_bytes(response.read())
    data = target.read_bytes()
    if hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest() != blob:
        raise ValueError(f'Blob mismatch: {path}')
    return data


def summary(rows, source, edge, metric, values):
    if not values:
        return
    s = sorted(values)
    rows.append([source, edge, metric, len(s), s[0], statistics.median(s), s[math.ceil(.95*len(s))-1], s[-1]])


class PrimitiveReader(pickle.Unpickler):
    def find_class(self, module, name):
        raise ValueError('Unexpected pickle class')


def ping_measurements(data, metrics, counts):
    stream = io.BytesIO(data)
    while stream.tell() < len(data):
        for op, _, _ in pickletools.genops(stream):
            if op.name not in ALLOWED_PICKLE:
                raise ValueError(f'Unexpected opcode: {op.name}')
    stream.seek(0)
    reader = PrimitiveReader(stream)
    events = []
    while stream.tell() < len(data):
        events.append(reader.load())
    kinds = Counter(x['_name'] for x in events)
    counts.extend(['pingpong', k, v] for k, v in sorted(kinds.items()))
    subs, callbacks, topic_by_obj = {}, {}, {}
    for e in events:
        p, n = e['vpid'], e['_name']
        if n == 'ros2:rcl_subscription_init':
            subs[p, e['subscription_handle']] = e['topic_name']
        elif n == 'ros2:rclcpp_subscription_init':
            topic_by_obj[p, e['subscription']] = subs[p, e['subscription_handle']]
        elif n == 'ros2:rclcpp_subscription_callback_added':
            callbacks[p, e['callback']] = topic_by_obj[p, e['subscription']]
        elif n == 'ros2:rclcpp_timer_callback_added':
            callbacks[p, e['callback']] = 'timer'
    pending, ordered, durations = {}, [], defaultdict(list)
    for e in events:
        n = e['_name']
        if n not in ('ros2:callback_start', 'ros2:callback_end'):
            continue
        p, t, cb = e['vpid'], e['vtid'], e['callback']
        thread = (p,t)
        label = e['procname'] + ':' + callbacks[p, cb]
        if n == 'ros2:callback_start':
            assert thread not in pending
            pending[thread] = (cb, e['_timestamp'])
            ordered.append((label,e['_timestamp']))
        else:
            handle, start = pending.pop(thread)
            assert handle == cb
            durations[label].append(e['_timestamp'] - start)
    assert not pending
    for label, v in sorted(durations.items()):
        summary(metrics, 'pingpong', label, 'callback_duration', v)
    relevant = [(label,t) for label,t in ordered if 'parameter_events' not in label]
    groups = []
    for label, stamp in relevant:
        if label == 'test_ping:timer':
            groups.append([])
        assert groups
        groups[-1].append((label,stamp))
    patterns = Counter('|'.join(label for label,_ in g) for g in groups)
    counts.extend(['pingpong','observed callback order '+k,v] for k,v in sorted(patterns.items()))
    full = [g for g in groups if len(g)==3]
    assert all(g[1][0].startswith('test_pong:') and g[2][0].startswith('test_ping:') for g in full)
    for left, right in [(0,1),(1,2),(0,2)]:
        summary(metrics, 'pingpong', full[0][left][0]+' -> '+full[0][right][0], 'ordered_start_spacing_no_message_id', [g[right][1]-g[left][1] for g in full])
    summary(metrics, 'pingpong','test_ping:timer', 'inter_start', [b[0][1]-a[0][1] for a,b in zip(groups, groups[1:])])


def read_ctf(trace, binary):
    process = subprocess.Popen([binary,'--clock-cycles','-n','all','-f','all',str(trace)],text=True,stdout=subprocess.PIPE)
    for line in process.stdout:
        pre, fields = line.split('event.fields = ',1)
        stamp = int(re.match(r'timestamp = (\d+)',pre)[1])
        name = re.search(r', name = ([^,]+)',pre)[1]
        pid = int(re.search(r'vpid = (\d+)',pre)[1])
        tid = int(re.search(r'vtid = (\d+)',pre)[1])
        payload = dict(re.findall(r'\b(\w+) = ("[^"]*"|0x[\dA-Fa-f]+|-?\d+)',fields))
        yield (stamp,name,(pid,tid),{k:v.strip('"') for k,v in payload.items()})
    if process.wait():
        raise RuntimeError('Babeltrace failed')


def eclipse_measurements(events, metrics, counts):
    all_counts = Counter(name for _,name,_,_ in events)
    counts.extend(['example2',k,v] for k,v in sorted(all_counts.items()))
    publishers, writers, rmw_sub, rcl_sub, sub_object, callbacks = {}, {}, {}, {}, {}, {}
    for _,n,(p,_),f in events:
        if n=='dds:create_writer':
            writers[p,f['writer']] = f['topic_name'].removeprefix('rt')
        elif n=='ros2:rcl_publisher_init':
            publishers[p,f['publisher_handle']] = f['topic_name']
        elif n=='ros2:rcl_subscription_init':
            rmw_sub[p,f['rmw_subscription_handle']] = rcl_sub[p,f['subscription_handle']] = f['topic_name']
        elif n=='ros2:rclcpp_subscription_init':
            sub_object[p,f['subscription']] = rcl_sub[p,f['subscription_handle']]
        elif n=='ros2:rclcpp_subscription_callback_added':
            callbacks[p,f['callback']] = sub_object[p,f['subscription']]

    active, last_pub, prewrite, received = {}, {}, {}, {}
    writes, takes, complete = {k:{} for k in TOPICS},{k:{} for k in TOPICS},{k:{} for k in TOPICS}
    relay = {}
    for t,n,thread,f in events:
        p = thread[0]
        if n=='ros2:callback_start':
            assert thread not in active
            topic = callbacks.get((p,f['callback']))
            source_stamp = None
            if topic in TOPICS:
                take_topic,source_stamp = received.pop(thread)
                assert take_topic==topic
                assert source_stamp not in complete[topic]
                complete[topic][source_stamp] = [t]
            active[thread] = (f['callback'],topic,source_stamp)
        elif n=='ros2:callback_end':
            cb,topic,stamp = active.pop(thread)
            assert cb==f['callback']
            if topic in TOPICS:
                complete[topic][stamp].append(t)
        elif n=='ros2:rcl_publish':
            last_pub[thread] = (publishers.get((p,f['publisher_handle'])),f['message'],t)
        elif n=='dds:write_pre':
            prewrite[thread] = (f['writer'],f['data'])
        elif n=='dds:write':
            topic = writers.get((p,f['writer']))
            if topic not in TOPICS:
                continue
            stamp = int(f['timestamp'])
            wr,addr = prewrite.pop(thread)
            outgoing,msg,pubtime = last_pub.pop(thread)
            assert wr==f['writer'] and msg==addr and outgoing==topic and stamp not in writes[topic]
            writes[topic][stamp] = (pubtime,t)
            if topic=='/topic_b':
                _,incoming,origin = active[thread]
                assert incoming=='/topic_a' and origin not in relay
                relay[origin]=stamp
        elif n=='ros2:rmw_take' and f['taken']=='1':
            topic = rmw_sub.get((p,f['rmw_subscription_handle']))
            if topic not in TOPICS:
                continue
            s = int(f['source_timestamp'])
            assert s>0 and s not in takes[topic] and thread not in received
            takes[topic][s] = t
            received[thread] = (topic,s)

    assert not received and not active
    for topic in TOPICS:
        w,takes_t,c = writes[topic],takes[topic],complete[topic]
        assert set(c)==set(takes_t) and all(len(x)==2 for x in c.values())
        matched = set(w)&set(c)
        unused = set(w)-set(c)
        unpaired_takes = set(c)-set(w)
        counts.extend([['example2',topic+' unique writes',len(w)],['example2',topic+' observed successful takes and callbacks',len(c)],['example2',topic+' distinct write-take-callback matches',len(matched)],['example2',topic+' writes without matching take',len(unused)],['example2',topic+' takes without matching write',len(unpaired_takes)]])
        if matched:
            first_pub,last_pub = min(w[s][0] for s in matched),max(w[s][0] for s in matched)
            first_take,last_take = min(takes_t[s] for s in matched),max(takes_t[s] for s in matched)
            counts.extend([['example2',topic+' unmatched writes before first matched publication',sum(w[s][0]<first_pub for s in unused)],['example2',topic+' unmatched writes after last matched publication',sum(w[s][0]>last_pub for s in unused)],['example2',topic+' unmatched takes before first matched take',sum(takes_t[s]<first_take for s in unpaired_takes)],['example2',topic+' unmatched takes after last matched take',sum(takes_t[s]>last_take for s in unpaired_takes)]])
        for name,vals in [('rcl_publish_to_dds_write',[v[1]-v[0] for v in w.values()]),('dds_write_to_rmw_take',[takes_t[s]-w[s][1] for s in matched]),('rmw_take_to_callback_start',[c[s][0]-takes_t[s] for s in c]),('callback_duration',[b-a for a,b in c.values()]),('rcl_publish_to_callback_start',[c[s][0]-w[s][0] for s in matched])]:
            assert min(vals)>=0
            summary(metrics,'example2',topic,name,vals)
    origins = [a for a,b in relay.items() if b in complete['/topic_b']]
    assert set(relay)==set(complete['/topic_a'])
    counts.append(['example2','source publish to sink callback via matched in-callback relay',len(origins)])
    pairs = sorted(((a,relay[a]) for a in origins), key=lambda pair:writes['/topic_a'][pair[0]][0])
    latency = [complete['/topic_b'][b][0]-writes['/topic_a'][a][0] for a,b in pairs]
    for label, group in [('first 10 complete chains',latency[:10]),('subsequent complete chains',latency[10:])]:
        summary(metrics,'example2',label,'source_rcl_publish_to_sink_callback_start',group)
    counts.append(['example2','complete chains exceeding one 5 ms source timer period',sum(x>5000000 for x in latency)])
    counts.append(['example2','first 10 complete chains exceeding 5 ms',sum(x>5000000 for x in latency[:10])])
    stages = [('source_rcl_publish_to_sink_callback_start',[complete['/topic_b'][b][0]-writes['/topic_a'][a][0] for a,b in pairs]),('relay_callback_start_to_relay_rcl_publish',[writes['/topic_b'][b][0]-complete['/topic_a'][a][0] for a,b in pairs]),('source_rcl_publish_to_sink_callback_end',[complete['/topic_b'][b][1]-writes['/topic_a'][a][0] for a,b in pairs])]
    for name,vals in stages:
        assert min(vals)>=0
        summary(metrics,'example2','/topic_a -> /topic_b',name,vals)

    rows = []
    origin = min(t[0] for t in writes['/topic_a'].values())
    for i,(a,b) in enumerate(pairs,1):
        source_rcl, source_dds = writes['/topic_a'][a]
        relay_take = takes['/topic_a'][a]
        relay_start, relay_end = complete['/topic_a'][a]
        relay_rcl, relay_dds = writes['/topic_b'][b]
        sink_take = takes['/topic_b'][b]
        sink_start, sink_end = complete['/topic_b'][b]
        rows.append([i,source_rcl-origin,source_dds-source_rcl,relay_take-source_dds,relay_start-relay_take,relay_rcl-relay_start,relay_dds-relay_rcl,sink_take-relay_dds,sink_start-sink_take,sink_end-sink_start,relay_end-relay_start,sink_start-source_rcl])
    return rows


def write(path,header,rows):
    with path.open('w',newline='') as out:
        writer=csv.writer(out,lineterminator='\n')
        writer.writerow(header)
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('output',type=Path)
    parser.add_argument('cache',type=Path)
    parser.add_argument('--babeltrace',default='babeltrace2')
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    manifest=json.loads(Path(__file__).with_name('trace-blobs.json').read_text())
    ping=get_file(args.cache/'ping',PING_REPO,PING_COMMIT,PING_PATH,manifest['pingpong'])
    trace=args.cache/'ros2'
    for path,blob in manifest['example2'].items():
        get_file(trace/path,ROS_REPO,ROS_COMMIT,ROS_PREFIX+path,blob)
    metrics,counts=[],[]
    ping_measurements(ping,metrics,counts)
    rows = eclipse_measurements(list(read_ctf(trace,args.babeltrace)),metrics,counts)
    write(args.output/'matched-chains.csv',['matched_chain_index','source_rcl_ns_from_first_a_rcl','source_rcl_to_dds_ns','a_dds_to_relay_take_ns','relay_take_to_start_ns','relay_start_to_rcl_ns','relay_rcl_to_dds_ns','b_dds_to_sink_take_ns','sink_take_to_start_ns','sink_start_to_end_ns','relay_start_to_end_ns','source_rcl_to_sink_start_ns'],rows)
    write(args.output/'timings.csv',['source','topic_or_path','metric','observations','min_ns','median_ns','p95_nearest_rank_ns','max_ns'],metrics)
    write(args.output/'trace-counts.csv',['source','event_or_check','count'],counts)


if __name__=='__main__':
    main()
