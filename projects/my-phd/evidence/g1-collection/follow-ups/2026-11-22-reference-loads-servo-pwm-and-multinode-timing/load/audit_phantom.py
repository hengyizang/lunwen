"""Inspect two Neo-Hookean fit candidates at each of four phantom sites.

Run python audit_phantom.py --out results_dir (NumPy, SciPy, Python 3).
Only the central directory and eight small MAT members are retrieved via
HTTP byte ranges. The selected bytes are checked against each member's CRC.
"""
import argparse
import csv
import hashlib
import io
import pathlib
import struct
import urllib.request
import zipfile
import zlib

import numpy as np
from scipy.io import loadmat

URL = "https://ndownloader.figshare.com/files/57562576"
ZIP_SIZE = 781116035
CD_OFFSET = 780299703
CD_SHA256 = "88f33999c21ad36a5bc4897ea89815de6fe2a3be6dbff7d8c0c3fbae007de492"
CURVES = (("indent", "displ_exp", "force_exp"), ("twist", "rot_exp", "torque_exp"))


def http_range(start, end):
    request = urllib.request.Request(URL + f"?g1_range={start}",
                                     headers={"Range": f"bytes={start}-{end}"})
    with urllib.request.urlopen(request, timeout=45) as response:
        expected = f"bytes {start}-{end}/{ZIP_SIZE}"
        if response.status != 206 or response.headers.get("Content-Range") != expected:
            raise ValueError("Expected a partial response matching the pinned ZIP")
        data = response.read()
        if len(data) != end - start + 1:
            raise ValueError("Incomplete range")
        return data


def member_bytes(info):
    # ZipFile opened on the central directory alone adjusts local offsets as if
    # archive bytes preceding that directory did not exist.
    pos = CD_OFFSET + info.header_offset
    header = http_range(pos, pos + 29)
    fields = struct.unpack("<4s5H3I2H", header)
    if fields[0] != b"PK\x03\x04":
        raise ValueError("Invalid local header")
    data_start = pos + 30 + fields[-2] + fields[-1]
    compressed = http_range(data_start, data_start + info.compress_size - 1)
    if info.compress_type != zipfile.ZIP_DEFLATED:
        raise ValueError("Unexpected compression")
    raw = zlib.decompress(compressed, -15)
    if len(raw) != info.file_size or zlib.crc32(raw) != info.CRC:
        raise ValueError("Invalid ZIP member size or CRC")
    return raw


def write(path, rows):
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def inspect(out):
    central = http_range(CD_OFFSET, ZIP_SIZE - 1)
    assert hashlib.sha256(central).hexdigest() == CD_SHA256
    curves, checks = [], []
    with zipfile.ZipFile(io.BytesIO(central)) as archive:
        assert len(archive.infolist()) == 5970
        for site in range(1, 5):
            first = {}
            for fit in (1, 2):
                name = f"datashare-figshare/Neo hookean model/phantom_{site}/output_mats/FEBioData_{fit}.mat"
                info = archive.getinfo(name)
                mat = loadmat(io.BytesIO(member_bytes(info)), squeeze_me=True)
                for phase, xkey, ykey in CURVES:
                    x, y = mat[xkey], mat[ykey]
                    assert x.ndim == 1 and x.shape == y.shape
                    valid = np.isfinite(x) & np.isfinite(y)
                    assert valid.any()
                    if fit == 1:
                        first[phase] = (x, y)
                        for i, (a, b) in enumerate(zip(x, y)):
                            if not valid[i]:
                                continue
                            curves.append(dict(site=site, phase=phase, index=i,
                                               coordinate_variable=xkey, coordinate_unit="mm" if phase == "indent" else "degree",
                                               coordinate_value=f"{a:.12g}",
                                               response_variable=ykey, response_unit="N" if phase == "indent" else "N mm",
                                               response_value=f"{b:.12g}"))
                    checks.append(dict(
                        site=site, fit_candidate=fit, phase=phase, paired_points=len(x), finite_xy=int(valid.sum()),
                        equal_to_first_xy=bool(np.array_equal(x, first[phase][0], equal_nan=True) and
                                               np.array_equal(y, first[phase][1], equal_nan=True)),
                        response_min=f"{y[valid].min():.10g}", response_max=f"{y[valid].max():.10g}",
                        member_crc32=f"{info.CRC:08x}", member=name,
                    ))
    out.mkdir(parents=True, exist_ok=True)
    write(out / "phantom_curves.csv", curves)
    write(out / "phantom_checks.csv", checks)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=pathlib.Path, default=pathlib.Path("."))
    inspect(parser.parse_args().out)
