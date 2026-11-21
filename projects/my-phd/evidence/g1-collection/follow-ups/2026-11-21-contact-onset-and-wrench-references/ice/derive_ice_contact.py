"""Summarize 8-channel tactile traces and the unheaded last column in ICECS v1."""
import argparse
import csv
import hashlib
from io import BytesIO
from pathlib import Path
import re
from zipfile import ZipFile

import numpy as np


def write_csv(path, rows):
    with path.open("w", encoding="utf8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=rows[0], lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def analyze(archive):
    records, phases = [], []
    with ZipFile(archive) as z:
        for path in sorted(z.namelist()):
            if path.endswith("/"):
                continue
            match = re.search(r"/(PVDF_roughtex|PVDF_softtex)/Voltage_TXH-Texture (\d+)-Hardness (\d+)-T9sec-t(\d+)$", path)
            if not match:
                raise ValueError(f"Unrecognized member: {path}")
            material, texture_id, hardness, trial = match.groups()
            raw = z.read(path)
            data = np.loadtxt(BytesIO(raw), delimiter="\t")
            if data.ndim != 2 or data.shape[1] != 9 or not np.isfinite(data).all():
                raise ValueError(f"Invalid trace: {path}")
            code = data[:, 8]
            if not np.all(code == np.floor(code)):
                raise ValueError(f"Nonintegral ninth channel: {path}")
            starts = np.r_[0, np.flatnonzero(np.diff(code)) + 1]
            ends = np.r_[starts[1:], len(data)]
            row = {"member":path, "sha256":hashlib.sha256(raw).hexdigest(), "folder":material,
                   "texture_id":int(texture_id), "hardness_id":int(hardness), "trial":int(trial),
                   "samples":len(data), "columns":data.shape[1],
                   "terminal_code":int(code[-1]), "code_blocks":len(starts),
                   "code_sequence":"-".join(str(int(v)) for v in code[starts])}
            for i in range(8):
                row[f"channel_{i+1}_peak_to_peak_as_stored"] = round(float(np.ptp(data[:, i])), 9)
            records.append(row)
            for block, (start,end) in enumerate(zip(starts,ends),1):
                phases.append({"folder":material, "trial":int(trial), "block":block,
                               "numeric_code":int(code[start]), "start_zero_based":int(start),
                               "end_exclusive":int(end), "samples":int(end-start)})
    return records, phases


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("archive",type=Path)
    p.add_argument("output_directory",type=Path)
    args=p.parse_args()
    with args.archive.open("rb") as stream:
        if hashlib.file_digest(stream, "md5").hexdigest() != "50479117586f4d61890cc8bb5505e4c8":
            raise ValueError("ZIP differs from fixed Zenodo v1")
    records, phases=analyze(args.archive)
    args.output_directory.mkdir(parents=True,exist_ok=True)
    write_csv(args.output_directory/"ice-tactile-files.csv",records)
    write_csv(args.output_directory/"ice-code-blocks.csv",phases)


if __name__=="__main__":
    main()
