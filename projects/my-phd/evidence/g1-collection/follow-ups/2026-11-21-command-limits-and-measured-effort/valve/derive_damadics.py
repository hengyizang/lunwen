"""Derive daily valve statistics and published intervention windows from the four plant ZIPs.

Run with Python, NumPy and pandas: python derive_damadics.py INPUT_ZIP_DIR OUTPUT_DIR
Raw caption, tag definitions and intervention labels follow the official data description
(02 March 2002, tables 1, 3-5). No simulator outputs are used.
"""
import argparse
from datetime import datetime
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import pandas as pd


# Item order follows Tables 3–5. One interval has only a documented start.
windows = [
    (1,1,'f18','2001-10-30',58800,59800),(2,1,'f16','2001-11-09',57275,57550),
    (3,1,'f18','2001-11-09',58830,58930),(4,1,'f18','2001-11-09',58520,58625),
    (5,1,'f18','2001-11-17',54600,54700),(6,1,'f16','2001-11-17',56670,56770),
    (7,1,'f17','2001-11-20',37780,38400),(8,2,'f17','2001-11-17',53780,53794),
    (9,2,'f17','2001-11-17',54193,54215),(10,2,'f19','2001-11-17',55482,55517),
    (11,2,'f19','2001-11-17',55977,56015),(12,2,'f19','2001-11-17',57030,57072),
    (13,2,'f17','2001-11-20',44400,None),(14,3,'f18','2001-10-30',57340,57890),
    (15,3,'f16','2001-11-09',60650,60700),(16,3,'f16','2001-11-09',60870,60960),
    (17,3,'f16','2001-11-17',57475,57530),(18,3,'f16','2001-11-17',57675,57800),
    (19,3,'f19','2001-11-17',58150,58325)
]


def measures(frame):
    # Channel-wise means use finite values of that channel, paired measures use both.
    cv, x, flow = frame['command'], frame['rod'], frame['flow']
    valid = cv.notna() & x.notna()
    delta = (cv - x).abs()
    return dict(sample_rows=len(frame), finite_command_rows=cv.count(), finite_rod_rows=x.count(),
                finite_flow_rows=flow.count(), paired_rows=valid.sum(),
                command_at_or_below_0=(cv<=0).sum(), command_at_or_above_100=(cv>=100).sum(),
                mean_abs_command_rod_gap_pct_points=delta.mean(), peak_abs_command_rod_gap_pct_points=delta.max(),
                min_command_pct_closing=cv.min(), max_command_pct_closing=cv.max(),
                min_rod_pct_closing=x.min(), max_rod_pct_closing=x.max(),
                mean_recorded_flow=flow.mean(), mean_valve_pressure_drop_kpa=(frame['inlet']-frame['outlet']).mean())


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('input',type=Path)
    p.add_argument('out',type=Path)
    args=p.parse_args()
    args.out.mkdir(parents=True,exist_ok=True)
    days,events=[],[]
    for part in range(1,5):
        with ZipFile(args.input/f'Lublin_all_data_part{part}.zip') as archive:
            for member in sorted(n for n in archive.namelist() if n.endswith('.txt')):
                date=datetime.strptime(Path(member).stem,'%d%m%Y').date().isoformat()
                with archive.open(member) as f:
                    data=pd.read_csv(f,header=None,sep='\t')
                assert data.shape==(86400,33) and np.array_equal(data[0],np.arange(86400))
                # Zero-based column indices from Table 1.
                for valve,cols in enumerate([[1,2,4,5,6],[17,18,20,21,22],[23,24,26,27,28]],1):
                    vals=data[cols].copy()
                    vals.columns=['inlet','outlet','flow','command','rod']
                    info=dict(date=date,valve=valve,flow_unit='t/h' if valve==3 else 'm3/h')
                    days.append(dict(**info,zip_part=part,**measures(vals)))
                    for item,actuator,fault,day,lo,hi in windows:
                        if valve!=actuator or date!=day:
                            continue
                        tags=dict(item=item,fault=fault,**info,published_start_s=lo,published_end_s=hi)
                        if hi is None:
                            events.append(dict(**tags,window='start_only'))
                            continue
                        length=hi-lo+1
                        for label,start,stop in [('preceding',lo-length,lo-1),('annotated',lo,hi)]:
                            events.append(dict(**tags,window=label,first_included_s=start,last_included_s=stop,
                                               **measures(vals.iloc[start:stop+1])))
    assert len(days)==75 and len(events)==37
    for name,rows,sort in [('damadics-valve-days',days,['date','valve']),('damadics-fault-windows',events,['item','window'])]:
        pd.DataFrame(rows).sort_values(sort).to_csv(args.out/(name+'.csv'),index=False,lineterminator='\n',float_format='%.9g')


if __name__=='__main__':
    main()
