"""Audit within-row measured currents vs the published 240-A dq operating envelope.
Usage: python derive_switch_currents.py SOURCE_FILE.zip OUTPUT_DIRECTORY
Requires pandas and numpy. The source does not guarantee chronological row order.
"""
from pathlib import Path
from zipfile import ZipFile
import argparse
import numpy as np
import pandas as pd


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('archive',type=Path)
    p.add_argument('out',type=Path)
    a=p.parse_args()
    a.out.mkdir(exist_ok=True,parents=True)
    counts=np.zeros((49,12),dtype=np.float64)
    minmax=np.column_stack((np.full(49,np.inf),np.full(49,-np.inf),
                            np.full(49,np.inf),np.full(49,-np.inf)))
    rows=0
    adjacent_current_match=0
    adjacent_current_and_vector_match=0
    adjacent_vector_match=0
    previous=None
    with ZipFile(a.archive) as z,z.open('Dataset_Electric_Motor.csv') as f:
        for d in pd.read_csv(f,chunksize=400_000):
            cols=['id_k','iq_k','epsilon_k','n_k','n_1k','id_k1','iq_k1']
            if list(d)!=cols or not np.isfinite(d.to_numpy()).all():
                raise ValueError('Unexpected columns or nonfinite values')
            if not np.isin(d[['n_1k','n_k']],[1,2,3,4,5,6,7]).all():
                raise ValueError('Unexpected switching state code')
            di,qi,_,v,old,df,qf=(d[c].to_numpy() for c in cols)
            group=(old-1)*7+v-1
            start=np.hypot(di,qi)
            end=np.hypot(df,qf)
            delta=np.hypot(df-di,qf-qi)
            stats=(None,start>240,end>240,(start<=240)&(end>240),
                   (start>240)&(end<=240),(start>240)&(end>240),
                   df-di,qf-qi,delta**2,start==240,end==240,delta==0)
            for i,weights in enumerate(stats):
                counts[:,i]+=np.bincount(group,weights=weights,minlength=49)
            for i,vec in [(0,start),(2,end)]:
                np.minimum.at(minmax[:,i],group,vec)
                np.maximum.at(minmax[:,i+1],group,vec)
            prev_df=np.r_[np.nan if previous is None else previous[0],df[:-1]]
            prev_qf=np.r_[np.nan if previous is None else previous[1],qf[:-1]]
            prev_v=np.r_[-1 if previous is None else previous[2],v[:-1]]
            matched=(prev_df==di)&(prev_qf==qi)
            adjacent_current_match+=int(matched.sum())
            adjacent_current_and_vector_match+=int((matched&(prev_v==old)).sum())
            adjacent_vector_match+=int((prev_v==old).sum())
            previous=df[-1],qf[-1],v[-1]
            rows+=len(d)
    result=[]
    for g,x in enumerate(counts):
        n=int(x[0])
        if n==0:
            continue
        result.append(dict(previous_vector=g//7+1,applied_vector=g%7+1,samples=n,
            start_over_240_a=int(x[1]),end_over_240_a=int(x[2]),inside_to_over=int(x[3]),
            over_to_inside=int(x[4]),over_to_over=int(x[5]),
            mean_d_change_a=x[6]/n,mean_q_change_a=x[7]/n,rms_dq_change_a=np.sqrt(x[8]/n),
            start_exact_240_a=int(x[9]),end_exact_240_a=int(x[10]),unchanged_currents=int(x[11]),
            min_start_a=minmax[g,0],max_start_a=minmax[g,1],min_end_a=minmax[g,2],max_end_a=minmax[g,3]))
    pd.DataFrame(result).to_csv(a.out/'switch-current-transitions.csv',index=False,float_format='%.9f',lineterminator='\n')
    sequence=dict(source_rows=rows,adjacent_stored_rows=rows-1,
            previous_outcome_equals_next_start_both_currents=adjacent_current_match,
            previous_applied_equals_next_previous_vector=adjacent_vector_match,
            both_currents_and_vector_match=adjacent_current_and_vector_match)
    pd.DataFrame([sequence]).to_csv(a.out/'switch-current-row-order.csv',index=False,lineterminator='\n')


if __name__=='__main__':
    main()
