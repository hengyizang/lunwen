"""Inspect public wrist-servo time series. Supply a pinned repository checkout and an output directory."""
import argparse
import csv
import hashlib
import math
from pathlib import Path
import statistics

def read_rows(path):
    with path.open(encoding='utf-8-sig',newline='') as f:
        return list(csv.DictReader(f))

def write_table(path,rows):
    with path.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n')
        w.writeheader()
        w.writerows(rows)

def summarize(repo,out):
    out.mkdir(parents=True,exist_ok=True)
    # Hardware setting from the archived final-run command and paper Table of final parameters.
    k_delta=0.1336345470
    counts_per_unit=210
    headline=read_rows(repo/'data/best_results/raw/nuss_break_c12a_300.csv')
    replay=[]
    for row in headline:
        get=lambda key:float(row[key])
        upure=-(k_delta+get('kappa_delta'))*get('nussbaum_n')*get('psi')
        request=upure+get('tail_activation')*get('u_aux')+get('u_fric')
        limit=get('max_control_eff')
        command=max(-limit,min(limit,request))
        replay.append((request,limit,abs(command-get('u_cmd')),abs(counts_per_unit*get('u_cmd')-get('current_from_u_raw'))))
    assert max(x[2] for x in replay)<2e-10
    write_table(out/'wrist-headline-reconstruction.csv',[dict(rows=len(replay),k_delta=k_delta,counts_per_internal_unit=counts_per_unit,pre_clamp_min=min(x[0] for x in replay),pre_clamp_max=max(x[0] for x in replay),clip_abs_bound=min(x[1] for x in replay),above_positive_bound=sum(x[0]>x[1] for x in replay),below_negative_bound=sum(x[0]<-x[1] for x in replay),max_abs_pre_minus_logged_clamped=max(abs(x[0]-float(r['u_cmd'])) for x,r in zip(replay,headline)),max_abs_replayed_minus_logged_clamped=max(x[2] for x in replay),max_abs_mapped_current_discrepancy_counts=max(x[3] for x in replay))])
    files=sorted((repo/'data/best_results/raw').glob('*.csv'))+sorted((repo/'data/envelope_step_bandwidth').glob('*.csv'))
    counts=[];prev={};aliases=[]
    for path in files:
        rows=read_rows(path)
        if not rows or 'q_ref_rad' not in rows[0]:
            continue
        h=hashlib.sha256(path.read_bytes()).hexdigest()
        if h in prev:
            aliases.append((path.name,prev[h]));continue
        prev[h]=path.name
        val=lambda key:[float(r[key]) for r in rows]
        t=val('t');u=val('u_cmd');req=val('current_from_u_raw');goal=val('goal_current_raw');meas=val('present_current_raw')
        if not all(y>x for x,y in zip(t,t[1:])):raise ValueError(path.name+' wraps time')
        bound=val('max_control_eff') if 'max_control_eff' in rows[0] else None
        # The earlier schemas omit the per-row cap. Use observed maximum only under a distinct label.
        limits=bound or [max(map(abs,u))]*len(t)
        err=[math.degrees(abs(a-b)) for a,b in zip(val('q_ref_rad'),val('q_meas_rad'))]
        counts.append(dict(file=path.name,sha256=h,rows=len(t),span_s=f'{t[-1]-t[0]:.6f}',median_step_ms=round(1000*statistics.median(b-a for a,b in zip(t,t[1:])),5),bound_basis=('logged max_control_eff' if bound else 'empirical max absolute u_cmd'),min_bound=min(limits),max_bound=max(limits),absolute_u_equals_bound_within_1e_9=sum(abs(abs(a)-b)<=1e-9 for a,b in zip(u,limits)),absolute_u_at_least_99pct_bound=sum(abs(a)>=0.99*b for a,b in zip(u,limits)),max_abs_mapped_current_count=max(map(abs,req)),max_abs_goal_current_count=max(map(abs,goal)),max_abs_feedback_current_count=max(map(abs,meas)),goal_feedback_rmse_count=round(math.sqrt(statistics.mean((a-b)**2 for a,b in zip(goal,meas))),6),mae_deg=round(statistics.mean(err),7)))
    if not counts:raise FileNotFoundError('No wrist time-series files')
    write_table(out/'wrist-runs.csv',counts)
    trials=[]
    for folder in ('optuna_trials','envelope_step_bandwidth'):
        for path in sorted((repo/'data'/folder).glob('*trials.csv')):
            records=read_rows(path)
            scores=[float(r['score']) for r in records]
            trials.append(dict(source=path.name,campaign=folder,rows=len(records),distinct_trial_numbers=len({r['trial_number'] for r in records}),ok_flag_equal_one=sum(float(r['ok'])==1 for r in records),score_at_least_one_million=sum(s>=1e6 for s in scores),minimum_score=round(min(scores),6),maximum_score=round(max(scores),6)))
    write_table(out/'wrist-trial-campaigns.csv',trials)
    print('Distinct runs',len(counts),'source file name aliases',aliases,'rows',sum(r['rows'] for r in counts))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('repo',type=Path);p.add_argument('out',type=Path)
    a=p.parse_args();summarize(a.repo,a.out)
