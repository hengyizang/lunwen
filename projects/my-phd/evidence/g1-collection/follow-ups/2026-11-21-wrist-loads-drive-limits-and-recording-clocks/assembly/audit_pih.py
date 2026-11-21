"""Recompute three descriptive tables from Zenodo 7221443. Python 3, numpy, scipy.
Usage: python audit_pih.py pih-database.zip OUT
"""
import argparse
import csv
import hashlib
import io
from pathlib import Path, PurePosixPath
from zipfile import ZipFile
import numpy as np
from scipy.io import loadmat


def audit(path, out):
    digest = hashlib.md5(path.read_bytes()).hexdigest()
    if digest != "d9e3c338b8c44997dc75039249991612":
        raise ValueError("Not the pinned Zenodo archive")
    out.mkdir(parents=True, exist_ok=True)
    rows, thresholds = [], []
    grouped = {}
    fmt = lambda value: f"{value:.6f}"
    with ZipFile(path) as source:
        names = set(source.namelist())
        mats = sorted(n for n in names if "/panda_" in n and n.endswith(".mat"))
        for file_name in mats:
            member = PurePosixPath(file_name)
            stem = member.stem.removeprefix("panda_")
            aruco = str(member.with_name("aruco_"+stem+".mat"))
            outcome = str(member.with_name("rs_front_"+stem+".jpg"))
            if aruco not in names or outcome not in names:
                raise ValueError("Unpaired member in "+file_name)
            data = source.read(file_name)
            src = loadmat(io.BytesIO(data),simplify_cells=True)["states"]
            t = src["t"]; trun=src["trun"]
            plate, wrist, native = (src[k] for k in ("ATIFT_plate","ATIFT_wrist","FT"))
            if not (all(a.shape == (len(t),6) for a in (plate,wrist,native)) and
                    all(np.isfinite(a).all() for a in (plate,wrist,native,t,trun))):
                raise ValueError("Nonfinite field or inconsistent row pairing")
            fp,fw,fr,mp,mw,mr = (np.linalg.norm(a[:,sl],axis=1) for sl in (slice(0,3),slice(3,6)) for a in (plate,wrist,native))
            equal = (np.diff(t)==0)
            repeat_diff = [int((equal & (np.diff(a,axis=0)!=0).any(axis=1)).sum()) for a in (plate,wrist,native)]
            i_min=int(np.argmin(fp)); i_max=int(np.argmax(fp))
            cls=member.parts[1]
            group=(member.parts[0],cls)
            grouped.setdefault(group,[]).append(fp)
            rows.append([file_name,hashlib.sha256(data).hexdigest(),*group,len(t),len(np.unique(t)),
                         int(equal.sum()),int((np.diff(t)<0).sum()),int((np.diff(trun)<=0).sum()),
                         *repeat_diff,fmt(fp[0]),fmt(fw[0]),fmt(mw[0]),fmt(fr[0]),i_min,
                         fmt(fp[i_min]),fmt(fw[i_min]),fmt(mw[i_min]),fmt(fr[i_min]),i_max,fmt(fp[i_max]),
                         fmt(fw[i_max]),fmt(mw[i_max]),fmt(fr[i_max])])
            # 5 is an audit threshold, never a physical contact annotation.
            high=np.flatnonzero(fp>=5.0)
            for bound in (0.5,1.0,2.0):
                mask=(fp<=bound)
                if high.size: mask[high[0]:]=False
                else: mask[:]=False
                indx=np.flatnonzero(mask)
                thresholds.append([file_name,fmt(bound),len(indx),int(high[0]) if high.size else "",
                                   fmt(np.median(fp[mask])) if indx.size else "",fmt(np.median(fw[mask])) if indx.size else "",
                                   fmt(np.median(mw[mask])) if indx.size else "",fmt(np.median(fr[mask])) if indx.size else ""])
    def write(name,header,records):
        with (out/name).open("w",newline="") as stream:
            w=csv.writer(stream,lineterminator="\n");w.writerow(header.split());w.writerows(records)
    write("pih-trials.csv","member member_sha256 slot commanded_offset_group rows distinct_t adjacent_equal_t decreasing_t "
          "nonincreasing_trun equal_t_plate_changes equal_t_wrist_changes equal_t_FT_changes first_plate_Fnorm "
          "first_wrist_Fnorm first_wrist_Mnorm first_FT_Fnorm min_plate_row0 min_plate_Fnorm wrist_Fnorm_at_plate_min "
          "wrist_Mnorm_at_plate_min FT_Fnorm_at_plate_min max_plate_row0 max_plate_Fnorm wrist_Fnorm_at_plate_max "
          "wrist_Mnorm_at_plate_max FT_Fnorm_at_plate_max",rows)
    write("pih-baseline-sensitivity.csv","member plate_Fnorm_ceiling rows_before_first_ge5 first_ge5_row0 "
          "median_plate_Fnorm median_wrist_Fnorm median_wrist_Mnorm median_FT_Fnorm",thresholds)
    write("pih-conditions.csv","slot commanded_offset_group trials rows trials_reaching_plate_Fnorm_5",
          [(k[0],k[1],len(v),sum(map(len,v)),sum(np.max(a)>=5 for a in v)) for k,v in sorted(grouped.items())])


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive",type=Path);parser.add_argument("output",type=Path)
    args=parser.parse_args();audit(args.archive,args.output)
