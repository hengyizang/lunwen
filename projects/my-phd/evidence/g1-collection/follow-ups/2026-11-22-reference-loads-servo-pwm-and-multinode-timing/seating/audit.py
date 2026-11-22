"""Rebuild four sets of summary tables from fixed public data. Requires numpy, h5py and openpyxl."""

import argparse
import io
from pathlib import Path
import time
from urllib.request import Request, urlopen
from zipfile import ZipFile

import h5py

from measurements import (
    digest,
    save,
    summarise_demo,
    summarise_patch,
    summarise_press,
    summarise_tests,
)


# ZIP's central directory and each selected member can be read independently.
# Validate HTTP ranges on every request. ZipFile checks each extracted member's CRC.
class RemoteZipFile:
    def __init__(self, url, length):
        self.url = url
        self.length = length
        self.position = 0
        self.start = 0
        self.cache = b""

    def seekable(self):
        return True

    def tell(self):
        return self.position

    def seek(self, offset, whence=0):
        self.position = (offset, self.position + offset, self.length + offset)[whence]
        return self.position

    def fetch(self, first, last):
        for attempt in range(4):
            try:
                bounds = f"{first}-{last}"
                request = Request(
                    f"{self.url}?range={bounds}", headers={"Range": f"bytes={bounds}"}
                )
                with urlopen(request, timeout=120) as response:
                    content_range = f"bytes {bounds}/{self.length}"
                    if (
                        response.status != 206
                        or response.headers.get("Content-Range") != content_range
                    ):
                        raise ValueError(
                            "Server did not honor the requested byte range"
                        )
                    data = response.read()
                if len(data) != last - first + 1:
                    raise ValueError("Incomplete byte range")
                return data
            except (OSError, ValueError):
                if attempt == 3:
                    raise
                time.sleep(3 * (attempt + 1))

    def read(self, size=-1):
        first = self.position
        end = self.length if size < 0 else min(self.length, first + size)
        if end <= first:
            return b""
        self.position = end
        if not (self.start <= first and self.start + len(self.cache) >= end):
            self.start = max(0, first - 131072) if end == self.length else first
            stop = min(self.length, max(end, self.start + 8192))
            # Split large independent requests so a slow transfer can be resumed locally.
            block = 24 * 1024 * 1024
            self.cache = b"".join(
                self.fetch(start, min(stop, start + block) - 1)
                for start in range(self.start, stop, block)
            )
        return self.cache[first - self.start : end - self.start]


def zenodo_url(record, filename):
    return f"https://zenodo.org/api/records/{record}/files/{filename}/content"


DEMOS = (
    "tofas_part1/step_execution/trial1/step3_19-06-2024_12-35-55/demo.hdf5",
    "pcl_part2/step_execution/trial2/step1_19-06-2024_15-20-32/demo.hdf5",
    "tofas_part2/complete_execution/tofas_part2_assembly_19-06-2024_12-58-40/demo.hdf5",
    "pcl_part2/complete_execution/complete_19-06-2024_15-14-12/demo.hdf5",
)


def robot(out):
    url = zenodo_url("12513790", "assembly_dataset_V1.1.zip")
    rows = []
    with ZipFile(RemoteZipFile(url, 19_040_656_534)) as archive:
        for path in DEMOS:
            raw = archive.read(path)
            with h5py.File(io.BytesIO(raw), "r") as data:
                rows.extend(summarise_demo(path, data, digest(raw)))
        members = []
        names = archive.namelist()
        checked = {r["member"]: r["sha256"] for r in rows}
        for info in sorted(archive.infolist(), key=lambda item: item.filename):
            if not info.filename.endswith("/demo.hdf5"):
                continue
            directory = info.filename.rsplit("/", 1)[0] + "/"
            siblings = [n for n in names if n.startswith(directory)]
            members.append(
                dict(
                    hdf5_member=info.filename,
                    hdf5_uncompressed_bytes=info.file_size,
                    compressed_bytes=info.compress_size,
                    zip_crc32=f"{info.CRC:08x}",
                    local_header_offset=info.header_offset,
                    db3_same_demo=sum(n.endswith(".db3") for n in siblings),
                    yaml_same_demo=sum(n.endswith("/metadata.yaml") for n in siblings),
                    sha256_if_read=checked.get(info.filename, ""),
                )
            )
    save(out, "hartu-members.csv", members)
    save(out, "demo-channels.csv", rows)


def patch(out):
    url = zenodo_url("11387093", "fiberOpticForceSensorExperiments_v1.zip")
    rows = []
    with ZipFile(RemoteZipFile(url, 575_024_126)) as archive:
        for test in (3, 6, 9):
            directory = (
                f"fiberOpticForceSensorExperiments_v1/tactileFingers/test{test}/"
            )
            wrench = archive.read(f"{directory}wrenches{test}.txt")
            optical = archive.read(f"{directory}test{test}.h5")
            rows.append(summarise_patch(test, wrench, optical))
    save(out, "patch-tests.csv", rows)


def press(out):
    with urlopen(
        "https://darus.uni-stuttgart.de/api/access/datafile/657027", timeout=150
    ) as response:
        raw = response.read()
    if (
        digest(raw)
        != "126505afc1eddc6fda35ecf353af2cbb671b1129ec276a3f93652ff6aac58fec"
    ):
        raise ValueError("Changed DaRUS archive")
    path = "experimental_data_robotic_adhesive_application/pressing/pressing_data_0_60s.csv"
    with ZipFile(io.BytesIO(raw)) as archive:
        save(out, "pressing.csv", [summarise_press(archive.read(path))])


def rivets(out):
    rows = []
    for name in ("LAP", "PEEL"):
        filename = f"Tensile_Tests_{name}.xlsx"
        with urlopen(zenodo_url("12741922", filename), timeout=120) as response:
            raw = response.read()
        rows.extend(summarise_tests(filename, raw))
    save(out, "rivet-tests.csv", rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("."))
    parser.add_argument(
        "--dataset", choices=("all", "robot", "patch", "press", "rivets"), default="all"
    )
    args = parser.parse_args()
    args.out.mkdir(exist_ok=True, parents=True)
    for name, calculate in (
        ("robot", robot),
        ("patch", patch),
        ("press", press),
        ("rivets", rivets),
    ):
        if args.dataset in ("all", name):
            calculate(args.out)
