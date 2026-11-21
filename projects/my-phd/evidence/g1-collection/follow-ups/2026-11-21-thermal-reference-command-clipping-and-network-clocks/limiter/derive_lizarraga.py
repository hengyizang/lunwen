"""Recount recorded controller rails and audit signed-duty reconstruction on the pinned ESP32 bench.
Usage: python derive_lizarraga.py EXTRACTED_SOURCE GIT_TREE_JSON OUTPUT (SciPy + NumPy).
"""
import argparse
import csv
import hashlib
import itertools
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from scipy.io import loadmat

REV = '8c74893a15c2c110e880d41eabd0d648bd2dcc93'
F = np.float32


def sha1blob(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def round_half_away(value):
    return int(math.copysign(math.floor(abs(float(value))+0.5), value))


def reconstruct(sample, actual):
    dpp = F(360)/F(actual['CPR'])
    dt = F(actual['Ts_ms'])/F(1000)
    kp,ki,kd = [F(actual[k]) for k in ('Kp','Ki','Kd')]
    lo,hi = [F(actual[k]) for k in ('u_min','u_max')]
    ref = F(actual['A_applied'])
    db = F(actual['e_deadband'])
    ref = F(round_half_away(ref/dpp))*dpp
    integ = old = F(0)
    replay, unclipped = [0], [0.]
    for t,y in zip(sample['t_ms'][1:], sample['y'][1:]):
        position = F(round_half_away(F(y)/dpp))*dpp
        r = ref if t >= actual['t_step_ms'] else F(0)
        e = F(r-position)
        d = F(kd*F(e-old)/dt)
        p = F(kp*e)
        candidate = F(integ+F(ki*dt)*e)
        raw = F(F(p+candidate)+d)
        if lo <= raw <= hi or (raw>hi and e<0) or (raw<lo and e>0):
            integ = candidate
        unbounded = F(F(p+integ)+d)
        replay.append(round_half_away(min(hi,max(lo,unbounded))))
        unclipped.append(float(unbounded))
        if abs(e) < db:
            integ = old = F(0)
        else:
            old = e
    return np.asarray(replay), np.asarray(unclipped)


def evaluate(file):
    e = loadmat(file,simplify_cells=True)['E']
    s, a = e['data'],e['applied']
    r,y,u,t = [np.atleast_1d(s[k]).astype(float) for k in ('r','y','u','t_ms')]
    if not len(t) or len({len(r),len(y),len(u),len(t)})!=1 or not all(np.isfinite(c).all() for c in (r,y,u,t)):
        raise ValueError(file)
    low, high = a['u_min'],a['u_max']
    rail=(u==low)|(u==high)
    dead = np.abs(r-y)<a['e_deadband']
    gated=dead & (u!=0)
    expected, pre = reconstruct(s,a)
    strict=(pre<low)|(pre>high)
    longest=max((sum(1 for _ in group) for key,group in itertools.groupby(rail) if key),default=0)
    return dict(trials=1,rows=len(t),rail_low=int((u==low).sum()),rail_high=int((u==high).sum()),
                outside_ack_bounds=int(((u<low)|(u>high)).sum()),trials_with_rail=int(rail.any()),
                rows_deadband=int(dead.sum()),nonzero_logged_in_deadband=int(gated.sum()),
                rail_in_deadband=int((rail&dead).sum()),replay_mismatch=int((expected!=u).sum()),
                trials_with_replay_mismatch=int((expected!=u).any()),strict_clip_replay=int(strict.sum()),
                logged_rail_without_strict_clip_replay=int((rail&~strict).sum()),strict_clip_without_logged_rail=int((strict&~rail).sum()),
                largest_rail_streak_samples=longest,zero_dt=int((np.diff(t)==0).sum()),
                irregular_steps=int((np.diff(t)!=a['Ts_ms']).sum()),
                rows_first_off_schedule=int(t[0]!=0),rows_last_off_schedule=int(t[-1]!=a['Tf_ms']))


def summarize(source, tree, out):
    official = json.loads(tree.read_text())
    assert official['sha']==REV and not official['truncated']
    sources={x['path']:x for x in official['tree'] if x['type']=='blob'}
    files = sorted(source.glob('data/**/experiment_*.mat'))
    assert len(files)==2942
    groups=defaultdict(Counter)
    per_campaign=defaultdict(Counter)
    sha_list = []
    for file in files:
        path=file.relative_to(source).as_posix()
        data=file.read_bytes()
        sha=sha1blob(data)
        if sha!=sources[path]['sha']:
            raise ValueError(path)
        sha_list.append(sha)
        stats=evaluate(file)
        key=tuple(file.relative_to(source).parts[1:3])
        for item in (groups[key],per_campaign[key[0]]):
            prev=item['largest_rail_streak_samples']
            item.update(stats)
            item['largest_rail_streak_samples']=max(prev,stats['largest_rail_streak_samples'])
    assert len(set(sha_list))==len(files)
    out.mkdir(parents=True,exist_ok=True)
    for filename,rows in [
        ('liz-campaigns.csv',[dict(campaign=k,**v) for k,v in sorted(per_campaign.items())]),
        ('liz-generations-and-amplitudes.csv',[dict(campaign=k[0],group=k[1],**v) for k,v in sorted(groups.items())])]:
        with (out/filename).open('w',newline='') as f:
            w=csv.DictWriter(f,rows[0],lineterminator='\n');w.writeheader();w.writerows(rows)
    print(len(files),hashlib.sha256(('\n'.join(sha_list)+'\n').encode()).hexdigest())


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for arg in ('source','tree','out'):p.add_argument(arg,type=Path)
    a=p.parse_args();summarize(a.source,a.tree,a.out)
