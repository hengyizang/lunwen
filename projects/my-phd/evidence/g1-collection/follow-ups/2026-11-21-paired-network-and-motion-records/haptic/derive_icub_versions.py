"""Match complete numeric trajectories between two fixed iCub Zenodo deposits."""
import argparse
from collections import defaultdict
import csv
import hashlib
import io
from pathlib import Path, PurePosixPath
import re
import zipfile
import numpy as np


def digest(array):
    return hashlib.sha256(np.ascontiguousarray(array,dtype="<f8").tobytes()).digest()


def fingerprint(archive,item):
    text=archive.read(item)
    array=np.loadtxt(io.BytesIO(text),delimiter=",",ndmin=2)
    if not np.isfinite(array).all():
        raise ValueError(f"Nonfinite values: {item.filename}")
    return hashlib.sha256(text).digest(),array.shape,digest(array)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("older",type=Path,help="Zenodo 5596856 ZIP")
    parser.add_argument("newer",type=Path,help="Zenodo 5913573 ZIP")
    parser.add_argument("output",type=Path)
    parser.add_argument("--first",type=Path,help="Zenodo 4906336 ZIP or a sparse file with its full central directory at the original offset")
    args=parser.parse_args()
    bundles=defaultdict(dict)
    raw_matches=defaultdict(list)
    numeric_matches=defaultdict(list)
    with zipfile.ZipFile(args.older) as archive:
        for item in archive.infolist():
            path=PurePosixPath(item.filename)
            if path.suffix!=".csv" or path.parts[1] not in ("training","validation"):
                continue
            prefix,trial=re.fullmatch(r"(pr|p|r|c|)([0-9]+)",path.stem).groups()
            raw,shape,values=fingerprint(archive,item)
            bundles[(path.parts[1],path.parts[2],int(trial))][prefix or "q"]=raw.hex()
            if prefix not in ("pr","r","c"):
                continue
            raw_matches[raw].append(item.filename)
            numeric_matches[(shape,values)].append(item.filename)
    rows=[]
    with zipfile.ZipFile(args.newer) as archive:
        for item in sorted(archive.infolist(),key=lambda x:x.filename):
            path=PurePosixPath(item.filename)
            if path.suffix!=".csv":
                continue
            raw,shape,values=fingerprint(archive,item)
            hits=numeric_matches[(shape,values)]
            rows.append(dict(newer_member=item.filename,rows=shape[0],cols=shape[1],
                             raw_sha256=raw.hex(),older_byte_identical_files=len(raw_matches[raw]),
                             older_numeric_identical_files=len(hits),
                             matching_older_numeric_files="|".join(sorted(hits))))
    args.output.mkdir(exist_ok=True,parents=True)
    with (args.output/"icub-version-matches.csv").open("w",newline="") as stream:
        writer=csv.DictWriter(stream,fieldnames=rows[0],lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    bundle_groups=defaultdict(list)
    for experiment,signals in sorted(bundles.items()):
        if set(signals)!={"q","p","pr","r","c"}:
            raise ValueError(f"Incomplete trial bundle {experiment}")
        key=tuple(signals[k] for k in ("q","p","pr","r","c"))
        bundle_groups[key].append(experiment)
    bundle_rows=[]
    for digests,members in bundle_groups.items():
        n_train=sum(m[0]=="training" for m in members)
        n_valid=sum(m[0]=="validation" for m in members)
        for split,task,trial in members:
            bundle_rows.append(dict(split=split,task=task,trial=trial,
                                    sha256_of_five_concatenated_binary_sha256=hashlib.sha256(
                                        bytes.fromhex("".join(digests))).hexdigest(),
                                    identical_training_bundles=n_train,identical_validation_bundles=n_valid))
    with (args.output/"icub-earlier-split-bundles.csv").open("w",newline="") as stream:
        writer=csv.DictWriter(stream,fieldnames=bundle_rows[0],lineterminator="\n")
        writer.writeheader()
        writer.writerows(sorted(bundle_rows,key=lambda r:(r["split"],r["task"],r["trial"])))

    if args.first:
        archives=[]
        for filename in (args.first,args.older):
            with zipfile.ZipFile(filename) as z:
                archive_index={}
                for item in z.infolist():
                    parts=PurePosixPath(item.filename).parts
                    if item.filename.endswith(".csv"):
                        name="/".join(parts[1:])
                        if name in archive_index:
                            raise ValueError(f"Duplicate file path in archive: {name}")
                        archive_index[name]=(item.file_size,item.CRC)
                archives.append(archive_index)
        first,second=archives
        stages=sorted({n.split("/")[0] for n in first.keys()|second.keys()})
        directory_rows=[]
        for stage in stages:
            names={n for n in first.keys()|second.keys() if n.split("/")[0]==stage}
            common=names & first.keys() & second.keys()
            directory_rows.append(dict(folder=stage,first_release_csv=len(names & first.keys()),
                                       middle_release_csv=len(names & second.keys()),same_relative_path=len(common),
                                       same_path_length_crc32=sum(first[n]==second[n] for n in common),
                                       different_length_or_crc32=sum(first[n]!=second[n] for n in common)))
        with (args.output/"icub-first-two-indexes.csv").open("w",newline="") as stream:
            writer=csv.DictWriter(stream,fieldnames=directory_rows[0],lineterminator="\n")
            writer.writeheader()
            writer.writerows(directory_rows)


if __name__=="__main__":
    main()
