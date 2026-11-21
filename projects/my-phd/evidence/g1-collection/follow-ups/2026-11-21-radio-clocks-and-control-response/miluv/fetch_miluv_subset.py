"""Fetch only the pinned MILUV three-robot ranging/pose members; standard library.
Usage: python fetch_miluv_subset.py INPUT_DIRECTORY
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import time
from urllib.request import Request, urlopen
import zlib


def download(url, byte_range=None):
    if byte_range is None:
        request = Request(url)
    else:
        first, end, total = byte_range
        request = Request(f"{url}?miluv_range={first}-{end-1}", headers={"Range":f"bytes={first}-{end-1}"})
    for attempt in range(3):
        try:
            with urlopen(request, timeout=90) as response:
                if byte_range is not None:
                    if response.status!=206 or response.getheader("Content-Range")!=f"bytes {first}-{end-1}/{total}":
                        raise ValueError("Publisher did not return the requested byte range")
                data=response.read()
            if byte_range is not None and len(data)!=end-first:
                raise ValueError("Incomplete HTTP range")
            return data
        except OSError:
            if attempt==2:
                raise
            time.sleep(2**attempt)


def fetch_member(archive, member):
    size=archive["archive_bytes"]
    start=member["zip_header_offset"]
    url=archive["url"]
    header=download(url,(start,start+30,size))
    if header[:4]!=b"PK\x03\x04":
        raise ValueError("Invalid local ZIP header")
    name_bytes,extra_bytes=struct.unpack("<HH",header[26:30])
    data_start=start+30+name_bytes+extra_bytes
    compressed=download(url,(data_start,data_start+member["compressed_bytes"],size))
    if member["zip_method"]==8:
        data=zlib.decompress(compressed,-15)
    elif member["zip_method"]==0:
        data=compressed
    else:
        raise ValueError("Unsupported ZIP method")
    if len(data)!=member["bytes"] or f"{zlib.crc32(data)&0xffffffff:08x}"!=member["crc32"]:
        raise ValueError(f"Invalid member CRC32 or byte count: {member['path']}")
    return data


def save(path, digest, get_data):
    if path.exists():
        if hashlib.sha256(path.read_bytes()).hexdigest()==digest:
            return
        raise ValueError(f"Existing file differs from pinned release: {path}")
    data=get_data()
    if hashlib.sha256(data).hexdigest()!=digest:
        raise ValueError(f"SHA-256 mismatch: {path}")
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(data)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root",type=Path)
    args=parser.parse_args()
    receipt=json.loads(Path(__file__).with_name("miluv-source.json").read_text())
    for name, source in receipt["configuration_inputs"].items():
        save(args.root/name, source["sha256"], lambda:download(source["url"]))
    for archive in receipt["archives"].values():
        for member in archive["selected_members"]:
            path=Path(member["path"])
            if path.is_absolute() or ".." in path.parts:
                raise ValueError("Unexpected archive member path")
            save(args.root/path,member["sha256"],lambda:fetch_member(archive,member))


if __name__=="__main__":
    main()
