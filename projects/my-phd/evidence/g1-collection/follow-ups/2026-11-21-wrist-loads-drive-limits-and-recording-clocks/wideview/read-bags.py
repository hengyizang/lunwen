"""Validate published ROS1 index counts and replay the 10-second UWB extract. Python 3 standard library."""
import argparse
import csv
import hashlib
import struct
import time
from collections import Counter
from pathlib import Path
from urllib.request import Request, urlopen


def u32(raw):
    return struct.unpack_from("<I", raw)[0]


def clock_ns(raw):
    sec, nsec = struct.unpack_from("<II", raw)
    return sec * 1_000_000_000 + nsec


def header(raw, start=0):
    pos = start + 4
    end = pos + u32(raw[start:])
    fields = {}
    while pos < end:
        stop = pos + 4 + u32(raw[pos:])
        key, value = raw[pos + 4:stop].split(b"=", 1)
        fields[key.decode()] = value
        pos = stop
    return fields, end + 4, u32(raw[end:])


def byte_range(entry, start, end, cache):
    identity, size = entry["replacement_file_id"], int(entry["size_bytes"])
    path = cache / f"{identity}-{start}-{end}"
    if path.exists():
        return path.read_bytes()
    url = f"https://drive.usercontent.google.com/download?id={identity}&export=download&confirm=t&start={start}&end={end}"
    for attempt in range(3):
        try:
            with urlopen(Request(url, headers={"Range": f"bytes={start}-{end}"}), timeout=45) as response:
                assert response.status == 206 and response.headers["Content-Range"] == f"bytes {start}-{end}/{size}"
                data = response.read()
                assert len(data) == end - start + 1
            path.write_bytes(data)
            return data
        except OSError:
            if attempt == 2:
                raise
            time.sleep(attempt + 1)


def parse_bag(entry, cache):
    read = lambda a, b: byte_range(entry, a, b, cache)
    lead = read(0, 511)
    assert lead.startswith(b"#ROSBAG V2.0\n")
    h, _, _ = header(lead, 13)
    ix = struct.unpack("<Q", h["index_pos"])[0]
    data = read(ix, int(entry["size_bytes"]) - 1)
    assert hashlib.sha256(data).hexdigest() == entry["index_sha256"]
    pos, topics, counts, chunks = 0, {}, Counter(), []
    while pos < len(data):
        h, offset, length = header(data, pos)
        if h["op"] == b"\x07":
            topics[u32(h["conn"])] = h["topic"].decode()
        if h["op"] == b"\x06":
            by_topic = dict(struct.iter_unpack("<II", data[offset:offset+length]))
            counts.update(by_topic)
            chunks.append((struct.unpack("<Q", h["chunk_pos"])[0], clock_ns(h["start_time"]), by_topic))
        pos = offset + length
    assert len(chunks) == int(entry["chunks"])
    for key in entry:
        if key.endswith("_indexed"):
            assert int(entry[key]) == sum(n for c, n in counts.items() if topics[c] == key.removesuffix("_indexed"))
    return read, topics, chunks


def replay(read, topics, chunks):
    conn = next(k for k, v in topics.items() if v == "/Decawave")
    begin = min(c[1] for c in chunks)
    limit = begin + 10_000_000_000
    for i, (start, stamp, counts) in enumerate(chunks):
        if stamp >= limit or not counts.get(conn):
            continue
        h, offset, length = header(read(start, start + 127))
        assert h["compression"] == b"none"
        d = read(start + offset + length, chunks[i+1][0] - 1)
        j = 0
        while j < len(d):
            hd, k, n = header(d, j)
            j = k + n
            if hd["op"] != b"\x04" or u32(hd["conn"]) != conn:
                continue
            for sec, nsec, within in struct.iter_unpack("<III", d[k:j]):
                recorded = sec * 1_000_000_000 + nsec
                if recorded >= limit:
                    continue
                address = start + offset + within
                record = read(address, address + 180)
                mh, base, length = header(record)
                assert mh["op"] == b"\x02" and u32(mh["conn"]) == conn and clock_ns(mh["time"]) == recorded
                msg = record[base:base+length]
                assert len(msg) == length
                seq, sec, nsec, name_length = struct.unpack_from("<IIII", msg)
                tag, count = struct.unpack_from("<iI", msg, 16 + name_length)
                values = dict(struct.iter_unpack("<id", msg[24+name_length:]))
                assert len(values) == count
                yield (tag, seq, f"{(recorded-begin)*1e-9:.6f}", f"{(recorded-sec*10**9-nsec)*1e-6:.6f}", count,
                       min(values.values()), max(values.values()), values[0], address, hashlib.sha256(msg).hexdigest())


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cache", type=Path)
    ap.add_argument("--all-indexes", action="store_true", help="check all 21 footers, instead of the first only")
    opts = ap.parse_args()
    opts.cache.mkdir(exist_ok=True, parents=True)
    folder = Path(__file__).resolve().parent
    entries = list(csv.DictReader((folder / "bag-indexes.csv").open()))
    for entry in (entries if opts.all_indexes else entries[:1]):
        read, topics, chunks = parse_bag(entry, opts.cache)
        if entry["sequence"] == "1":
            result = [[str(k), *map(str, row)] for k, row in enumerate(replay(read, topics, chunks))]
            assert result == list(csv.reader((folder / "first-ten-seconds.csv").open()))[1:]
    print("Verified all requested indexes and the 36 retained UWB messages.")
