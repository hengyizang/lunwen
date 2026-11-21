"""Audit free-run raw/export pairs and all normal-contact physical logs.

Usage: python derive_panda.py path_to_full_or_selected_sparse_zip output_directory
Raw array fields wrap across text lines and contain no comma separators.
"""
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import sys
from zipfile import ZipFile

import numpy as np

from fetch_panda_members import selections,CONTACT,CONFIG


def array_field(blob, field, cols, rows):
    fields=re.findall(rb"'"+field.encode()+rb"':\s*\[([^\]]+)\]",blob)
    if len(fields)!=rows:
        raise ValueError(f"Wrong {field} row count")
    matrix=np.fromstring(b" ".join(fields),sep=" ").reshape(rows,cols)
    if not np.isfinite(matrix).all():
        raise ValueError(f"Nonfinite field {field}")
    return matrix


def write(path, rows):
    with path.open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=rows[0],lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def main(archive, output):
    output.mkdir(parents=True,exist_ok=True)
    runs=[]; pairs=[]; manifests=[]
    with ZipFile(archive) as z:
        paired,chosen=selections(z)
        for name in sorted(chosen):
            f=z.getinfo(name)
            blob=z.read(f)
            digest=hashlib.sha256(blob).hexdigest()
            manifests.append(dict(member=name,uncompressed_bytes=f.file_size,compressed_bytes=f.compress_size,
                                  crc32=f"{f.CRC:08x}",uncompressed_sha256=digest))
            contact=name.startswith(CONTACT)
            if not (contact or name in paired):
                continue
            condition=name.split("/")[-2].split()[0]
            ref=(CONFIG if contact else "Exp_cfg/")+"exp"+condition+".json"
            mass=json.loads(z.read(ref))["total_mass"] if ref in chosen else ""
            t=np.array(re.findall(rb"'time':\s*([^,}]+)",blob),dtype=float)
            assert len(t)>1 and np.isfinite(t).all()
            actual=array_field(blob,"tau_J",7,len(t))
            desired=array_field(blob,"tau_J_d",7,len(t))
            t_ext=array_field(blob,"tau_ext_hat_filtered",7,len(t))
            wrench=array_field(blob,"O_F_ext_hat_K",6,len(t))
            dt=np.diff(t)
            measured_peak=np.abs(actual).max(axis=1)
            force=np.linalg.norm(wrench[:,:3],axis=1)
            runs.append(dict(member=name,collection="normal_contact_directory" if contact else "free_run_directory",
                condition_id=condition,matched_configuration=ref if ref in chosen else "",reported_total_mass=mass,
                rows=len(t),elapsed_s=t[-1]-t[0],nonpositive_dt=int((dt<=0).sum()),median_dt_s=np.median(dt),
                maximum_dt_s=dt.max(),requested_nonzero_rows=int(np.any(desired!=0,axis=1).sum()),
                measured_peak_abs_joint_Nm=measured_peak.max(),
                measured_above_1Nm_with_zero_request_rows=int(((measured_peak>1) & np.all(desired==0,axis=1)).sum()),
                filtered_external_joint_torque_peak_abs_Nm=np.abs(t_ext).max(),
                estimated_force_norm_median_N=np.median(force),estimated_force_norm_peak_N=force.max(),
                estimated_moment_norm_peak_Nm=np.linalg.norm(wrench[:,3:],axis=1).max()))
            if name in paired:
                raw=np.column_stack([t-t[0],array_field(blob,"q",7,len(t)),
                                array_field(blob,"dq",7,len(t)),actual])
                reduced=np.loadtxt(io.BytesIO(z.read(paired[name])),ndmin=2)
                assert reduced.shape[1]==22
                row=dict(raw=name,reduced=paired[name],raw_rows=len(raw),export_rows=len(reduced))
                for key,sl in (("relative_time_s",slice(0,1)),("q_rad",slice(1,8)),
                            ("dq_rad_per_s",slice(8,15)),("tau_J_Nm",slice(15,22))):
                    row["max_absolute_difference_"+key]=float(np.abs(raw[:,sl]-reduced[:,sl]).max()) if len(raw)==len(reduced) else ""
                pairs.append(row)
    write(output/"panda-member-hashes.csv",manifests)
    write(output/"panda-raw-runs.csv",runs)
    write(output/"panda-export-pairs.csv",pairs)


if __name__=="__main__":
    main(Path(sys.argv[1]),Path(sys.argv[2]))
