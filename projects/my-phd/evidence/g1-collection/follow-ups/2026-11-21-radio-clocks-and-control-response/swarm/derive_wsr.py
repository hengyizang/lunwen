"""Summarize reciprocal WiFi CSI captures from Harvard-REACT/WSR-Toolbox-Dataset.
Run with the pinned dataset checkout (or its matching raw-data tree) and an output directory.
"""
import argparse
import csv
import hashlib
import json
import statistics
import struct
from collections import Counter, defaultdict
from pathlib import Path


def write(path, rows):
    with path.open('w', encoding='utf-8', newline='') as out:
        writer = csv.DictWriter(out, rows[0].keys(), lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def parse(path, labels):
    data = path.read_bytes()
    offset = 0
    peers = defaultdict(dict)
    while offset + 3 <= len(data):
        length, code = struct.unpack_from('>HB', data, offset)
        if length < 1:
            raise ValueError(f'Invalid record length in {path}')
        end = offset + 2 + length
        if end > len(data):
            break
        start = offset + 3
        if code != 187 or length < 39:
            raise ValueError(f'Unexpected CSI record type or size in {path}')
        beam_size = struct.unpack_from('<H', data, start + 16)[0]
        if length != 1 + 38 + beam_size:
            raise ValueError(f'Incomplete CSI header or payload in {path}')
        sec, usec = struct.unpack_from('<II', data, start + 20)
        if usec >= 1_000_000:
            raise ValueError(f'Invalid microseconds in {path}')
        key = data[start + 28:start + 34].hex()
        number = struct.unpack_from('<I', data, start + 34)[0]
        stream = peers[labels[key]]
        if number in stream:
            raise ValueError(f'Within-file frame counter collision in {path}')
        stream[number] = sec * 1_000_000 + usec
        offset = end
    return peers, len(data) - offset, hashlib.sha256(data).hexdigest()


def channel_stats(stream):
    if not stream:
        return dict(count=None, first=None, last=None, skipped_counter_values=None,
                    interarrival_median_us=None, interarrival_max_us=None)
    counters = list(stream)
    times = list(stream.values())
    spacings = [b-a for a,b in zip(times,times[1:])]
    if any(b<=a for a,b in zip(counters,counters[1:])) or any(d<=0 for d in spacings):
        raise ValueError('Counter or receive time is not increasing within a local stream')
    return dict(count=len(counters),first=counters[0],last=counters[-1],
                skipped_counter_values=counters[-1]-counters[0]+1-len(counters),
                interarrival_median_us=statistics.median(spacings) if spacings else None,
                interarrival_max_us=max(spacings, default=None))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root',type=Path)
    parser.add_argument('output',type=Path)
    args=parser.parse_args()
    config=json.loads((args.root/'config_files/dataset.json').read_text())
    peers=config['input_TX_channel_csi_fn']['value']
    labels={peers[node]['mac_id'].replace(':','').lower():node for node in ('tx2','tx3','tx4')}
    labels[config['input_RX_channel_csi_fn']['value']['mac_id'].replace(':','').lower()]='rx'
    root=args.root/'Dataset/2D-Displacement_raw_data'
    groups=defaultdict(dict)
    files=[]
    for path in sorted(root.glob('*/*/*.dat')):
        _,node,run = path.stem.split('_',2)
        streams,tail,sha=parse(path,labels)
        group=groups[(path.parent.parent.name, path.parent.name, run)]
        if node in group or not streams:
            raise ValueError(f'Missing frames or repeated capture: {path}')
        group[node]=streams
        files.append(dict(file=path.relative_to(root).as_posix(),logger=node,bytes=path.stat().st_size,
                          sha256=sha,complete_records=sum(map(len,streams.values())),trailing_bytes=tail,
                          senders_seen=' '.join(sorted(streams))))
    if len(files)!=882 or len(groups)!=245:
        raise ValueError('Incomplete release')
    links=[]
    for (scenario,station,run), nodes in sorted(groups.items()):
        central=nodes['rx']
        for peer in sorted(set(central) | (set(nodes) - {'rx'})):
            reverse=central.get(peer,{})  # received at central from peer
            if peer in nodes and set(nodes[peer])!={'rx'}:
                raise ValueError(f'Unexpected source identities at peer {peer}')
            forward=nodes.get(peer,{}).get('rx',{})  # central -> peer, received at peer
            row=dict(scenario=scenario,station=station,run=run,peer=peer,
                     peer_capture_present=int(peer in nodes))
            for name,stream in (('central_to_peer',forward),('peer_to_central',reverse)):
                row.update({name+'_'+k:v for k,v in channel_stats(stream).items()})
            metrics=dict(paired_counters=None,only_received_at_central=None,only_received_at_peer=None,
                         common_counter_range_unseen_both=None,
                         paired_peer_clock_minus_central_clock_median_us=None)
            if forward and reverse:
                common=forward.keys() & reverse.keys()
                lo=max(min(forward),min(reverse))
                hi=min(max(forward),max(reverse))
                observed=forward.keys() | reverse.keys()
                metrics.update(paired_counters=len(common),only_received_at_central=len(reverse.keys()-common),
                               only_received_at_peer=len(forward.keys()-common),
                               common_counter_range_unseen_both=max(0,hi-lo+1)-sum(lo<=k<=hi for k in observed),
                               paired_peer_clock_minus_central_clock_median_us=statistics.median(forward[k]-reverse[k] for k in common) if common else None)
            row.update(metrics)
            links.append(row)
    args.output.mkdir(exist_ok=True,parents=True)
    write(args.output/'wsr-captures.csv',files)
    write(args.output/'wsr-directional-exchanges.csv',links)


if __name__=='__main__':
    main()
