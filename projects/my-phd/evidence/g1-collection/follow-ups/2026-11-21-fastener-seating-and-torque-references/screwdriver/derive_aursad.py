"""Recompute actuator-state summaries from AURSAD's fixed HDF5; requires h5py and NumPy.

python derive_aursad.py AURSAD.h5 OUTPUT_DIR
"""
import argparse
import csv
from pathlib import Path
import h5py
import numpy as np

LABELS={0:'normal',1:'damaged screw',2:'extra assembly component',3:'missing screw',
        4:'damaged thread',5:'loosening / screw picking'}


def write(path, rows):
    with path.open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=rows[0],lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def fmt(value):
    return round(float(value),8)


def analyze(matrix, flags, col, bits, sample, label, start, stop):
    def analog(key):
        return matrix[:,col[key]]
    def flag(i):
        return flags[:,bits[f'output_bit_register_{i}']].astype(bool)
    t=analog('timestamp')
    twist=np.column_stack([analog(f'actual_TCP_force_{i}') for i in range(3,6)])
    current=analog('output_double_register_25')
    achieved=analog('output_double_register_24')
    target=analog('output_double_register_26')
    tighten=flag(67)
    busy=flag(70)
    pulse_and_busy=tighten & busy
    active=busy & (label in (0, 1, 2, 3, 4))
    ok,failed=flag(72),flag(71)
    dt=np.diff(t)
    assert np.isfinite(matrix[:,[col[f'output_double_register_{i}'] for i in (24,25,26)]]).all()
    assert np.isfinite(twist).all() and np.isfinite(t).all()
    row=dict(sample_nr=sample,stored_label=label,label_name=LABELS[label],first_index=start,
             end_exclusive=stop,rows=stop-start,t_first_s=fmt(t[0]),t_last_s=fmt(t[-1]),
             backwards_clock_steps=int(sum(dt<0)),equal_clock_steps=int(sum(dt==0)),
             positive_steps_longer_15ms=int(sum(dt>.015)),tightening_flag_rows=int(tighten.sum()),
             busy_flag_rows=int(busy.sum()),both_tightening_and_busy_rows=int(pulse_and_busy.sum()),
             active_busy_rows_in_tightening_event=int(active.sum()),
             process_ok_flag_rows=int(ok.sum()),process_not_ok_flag_rows=int(failed.sum()),
             coincident_ok_not_ok_rows=int((ok&failed).sum()),
             current_torque_abs_peak_Nm=fmt(np.abs(current).max()),
             achieved_torque_abs_peak_Nm=fmt(np.abs(achieved).max()),
             tcp_moment_norm_peak_Nm=fmt(np.linalg.norm(twist,axis=1).max()),
             target_positive_active_rows=int(np.sum(active & (target>0))),
             current_abs_at_least_positive_target_active_rows=int(np.sum(active & (target>0) & (np.abs(current)>=target))))
    for series,name in [(np.abs(current),'current_torque'),(np.abs(achieved),'achieved_torque'),
                        (np.linalg.norm(twist,axis=1),'tcp_moment_norm')]:
        sel=series[active]
        row[f'active_{name}_max_Nm']=fmt(sel.max()) if sel.size else ''
    return row


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path)
    parser.add_argument('out',type=Path)
    a=parser.parse_args()
    segments=[]
    with h5py.File(a.source) as h:
        g=h['complete_data']
        names=lambda k:[n.decode() for n in g[f'block{k}_items'][:]]
        indices=lambda k:{n:j for j,n in enumerate(names(k))}
        col,bits=indices(1),indices(0)
        ids=g['block3_values'][:,names(3).index('sample_nr')]
        labels=g['block2_values'][:,names(2).index('label')]
        edges=np.r_[0,np.flatnonzero((np.diff(ids)!=0)|(np.diff(labels)!=0))+1,len(ids)]
        for left,right in zip(edges[:-1],edges[1:]):
            segments.append(analyze(g['block1_values'][left:right],g['block0_values'][left:right],col,bits,
                                    int(ids[left]),int(labels[left]),int(left),int(right)))
        assert sum(s['rows'] for s in segments)==len(g['axis1'])
    groups=[]
    for lbl in sorted({s['stored_label'] for s in segments}):
        subset=[s for s in segments if s['stored_label']==lbl]
        active=[s for s in subset if s['active_busy_rows_in_tightening_event']]
        row=dict(stored_label=lbl,label_name=LABELS[lbl],segments=len(subset),
                 distinct_sample_ids=len({s['sample_nr'] for s in subset}),rows=sum(s['rows'] for s in subset),
                 with_active_tightening=len(active),
                 active_segments_current_at_least_target=sum(s['current_abs_at_least_positive_target_active_rows']>0 for s in active),
                 segments_with_any_ok_flag=sum(s['process_ok_flag_rows']>0 for s in subset),
                 segments_with_any_not_ok_flag=sum(s['process_not_ok_flag_rows']>0 for s in subset))
        for name in ('current_torque','achieved_torque','tcp_moment_norm'):
            vals=[s[f'active_{name}_max_Nm'] for s in active]
            for key,q in [('min',0),('median',50),('max',100)]:
                row[f'active_{name}_per_segment_peak_{key}_Nm']=fmt(np.percentile(vals,q)) if vals else ''
        groups.append(row)
    a.out.mkdir(parents=True,exist_ok=True)
    write(a.out/'screwdriver-segments.csv',segments)
    write(a.out/'screwdriver-events-by-label.csv',groups)


if __name__=='__main__':
    main()
