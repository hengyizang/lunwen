"""Audit all 43 V3 cable-cylinder records, including the depositor's separately retained runs.

Usage: python derive_cable.py CEP_ADRC_evidence_v3_2026-11-12.zip OUT
Requires Python, NumPy and pandas. 'Near rail' is the paper's absolute-voltage
threshold. The stored flag can encode a rate limit as well as an amplitude limit.
"""
import argparse
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import pandas as pd


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive',type=Path)
    parser.add_argument('out',type=Path)
    args=parser.parse_args()
    args.out.mkdir(parents=True,exist_ok=True)
    rows=[]
    with ZipFile(args.archive) as archive:
        index_path=next(n for n in archive.namelist() if n.endswith('/source_index_normalized.csv'))
        base=index_path.rsplit('/',1)[0]
        index=pd.read_csv(BytesIO(archive.read(index_path)))
        assert len(index)==43 and index.normalized_id.is_unique
        for rec in index.itertuples(index=False):
            b=archive.read(base+'/raw_csv/'+rec.source_relpath)
            assert sha256(b).hexdigest()==rec.sha256
            x=pd.read_csv(BytesIO(b))
            assert len(x)==rec.rows and x.shape[1]==14 and not x.isna().any().any()
            u=x.u_V.to_numpy()
            sat=x.sat.to_numpy()
            assert set(sat)<=set([0,1])
            flagged=sat!=0
            rail=np.abs(u)>=6.49
            joint=rail & flagged
            diff=np.diff(x.t_s)
            inc=np.diff(x.cycle)
            row=dict(record=rec.normalized_id,group=rec.normalized_group,controller=rec.controller,
                     experiment=rec.experiment_type,main_statistics=rec.main_statistics,
                     depositor_role=rec.evidence_role,raw_file=rec.source_relpath,source_sha256=rec.sha256,
                     sample_rows=len(x),median_logged_step_s=np.median(diff),nonincreasing_logged_time_rows=(diff<=0).sum(),
                     nonincreasing_cycle_rows=(inc<=0).sum(),jitter_flag_rows=(x.jitter!=0).sum(),fault_flag_rows=(x.fault!=0).sum(),
                     low_rail_rows=(u<=-6.49).sum(),high_rail_rows=(u>=6.49).sum(),both_flag_and_rail_rows=joint.sum(),
                     flagged_intermediate_voltage_rows=(flagged & ~rail).sum(),unflagged_near_rail_rows=(rail & ~flagged).sum(),
                     neither_flag_nor_rail_rows=(~rail & ~flagged).sum(),peak_abs_command_V=np.abs(u).max(),
                     min_measured_position_mm=x.pos_mm.min(),max_measured_position_mm=x.pos_mm.max(),
                     max_abs_target_minus_measured_mm=np.abs(x.target_mm-x.pos_mm).max(),
                     max_abs_shaped_ref_minus_measured_mm=np.abs(x.ref_mm-x.pos_mm).max())
            rows.append(row)
    data=pd.DataFrame(rows).sort_values('record')
    data.to_csv(args.out/'cable-voltage-flags-by-run.csv',index=False,lineterminator='\n',float_format='%.9g')
    totals=['sample_rows','low_rail_rows','high_rail_rows','both_flag_and_rail_rows','flagged_intermediate_voltage_rows',
            'unflagged_near_rail_rows','neither_flag_nor_rail_rows','jitter_flag_rows','fault_flag_rows']
    results=[]
    for role,group in data.groupby('depositor_role',sort=True):
        mismatches=group.flagged_intermediate_voltage_rows+group.unflagged_near_rail_rows
        results.append(dict(depositor_role=role,records=len(group),records_with_any_mismatch=(mismatches>0).sum(),
                            **group[totals].sum().to_dict()))
    pd.DataFrame(results).to_csv(args.out/'cable-screening-groups.csv',index=False,lineterminator='\n')


if __name__=='__main__':
    main()
