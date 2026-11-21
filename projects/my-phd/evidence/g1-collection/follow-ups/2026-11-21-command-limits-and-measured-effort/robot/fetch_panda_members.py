"""Fetch selected physical logs into a sparse ZIP with logical size 6.54 GB.

Usage: python fetch_panda_members.py MENDELEY_FILE_LIST_JSON OUTPUT_SPARSE_ZIP
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import struct
import time
from urllib.request import Request, urlopen
from zipfile import ZipFile

FREE_BASENAME = "speedratio0.1_mixmotion_5point_1.txt"
CONTACT = "normal contact tractory/Exp_data/"
CONFIG = "normal contact tractory/Exp_cfg/"


def selections(archive):
    names = set(archive.namelist())
    paired = {}
    chosen = set()
    for path in sorted(names):
        if path.startswith("Exp_data/") and path.endswith("/" + FREE_BASENAME):
            _, condition, basename = path.split("/")
            number, tool = condition.split()
            export = f"realpanda_dataset/{number}_{tool}_{basename}"
            config = f"Exp_cfg/exp{number}.json"
            if export not in names:
                raise ValueError(f"Missing paired export for {path}")
            chosen.update([export, path])
            paired[path] = export
            # Six suffixed condition IDs have no exactly named configuration JSON.
            if config in names:
                chosen.add(config)
        if path.startswith(CONTACT) and "/speedratio" in path and path.endswith(".txt"):
            chosen.add(path)
        if path.startswith(CONFIG) and path.endswith(".json"):
            chosen.add(path)
    return paired, chosen


def fetch_range(url, start, end, size):
    for attempt in range(5):
        try:
            req = Request(url, headers={"Range": f"bytes={start}-{end}", "User-Agent": "public data index audit"})
            with urlopen(req, timeout=45) as response:
                expected = f"bytes {start}-{end}/{size}"
                if response.status != 206 or response.headers.get("Content-Range") != expected:
                    raise ValueError("Server did not return the requested byte range")
                block = response.read()
            if len(block) != end - start + 1:
                raise ValueError("Incomplete byte range")
            return block
        except OSError:
            if attempt == 4:
                raise
            time.sleep(1 + attempt)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("registry", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    meta, = json.loads(args.registry.read_text())
    if meta["id"] != "dab3822f-af58-4a43-b413-8cd9875f15c2":
        raise ValueError("Expected the version-1 datas.zip file from Mendeley Data")
    size = meta["size"]
    url = meta["content_details"]["download_url"]
    tail = fetch_range(url, size-65536, size-1, size)
    footer = struct.unpack_from("<4sQ2H2I4Q", tail, tail.rindex(b"PK\x06\x06"))
    count, directory_size, directory_offset = footer[-3:]
    directory = fetch_range(url, directory_offset, directory_offset + directory_size - 1, size)
    with args.output.open("wb") as stream:
        stream.seek(directory_offset)
        stream.write(directory)
        stream.seek(size - len(tail))
        stream.write(tail)
    with ZipFile(args.output) as archive:
        if len(archive.infolist()) != count:
            raise ValueError("Incomplete central directory")
        _, selected = selections(archive)
        members = sorted(archive.infolist(), key=lambda entry: entry.header_offset)
        spans = []
        for i, member in enumerate(members):
            if member.filename not in selected:
                continue
            start = member.header_offset
            stop = members[i+1].header_offset if i+1 < len(members) else directory_offset
            if spans and start - spans[-1][1] <= 32768 and stop - spans[-1][0] <= 8*1024**2:
                spans[-1] = (spans[-1][0], stop)
            else:
                spans.append((start, stop))

    def load(span):
        start, stop = span
        return start, fetch_range(url, start, stop-1, size)

    with args.output.open("r+b") as stream, ThreadPoolExecutor(5) as pool:
        for start, block in pool.map(load, spans):
            stream.seek(start)
            stream.write(block)
    with ZipFile(args.output) as archive:
        for path in selected:
            archive.read(path)  # ZipFile validates the uncompressed member CRC32.
    print("Verified members:", len(selected), "bytes fetched:",
          sum(stop-start for start, stop in spans) + len(tail) + len(directory))


if __name__ == "__main__":
    main()
