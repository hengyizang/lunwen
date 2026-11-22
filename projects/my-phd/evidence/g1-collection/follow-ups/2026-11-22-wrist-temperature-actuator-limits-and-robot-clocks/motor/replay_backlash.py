"""python replay_backlash.py ResearchData_two-joint_backlash.zip OUT. Python 3 and NumPy."""
import argparse,csv,hashlib,io,json
from pathlib import Path
from zipfile import ZipFile
import numpy as np

def write(out,n,items):
    with (out/n).open('w',newline='') as f:
        w=csv.DictWriter(f,items[0],lineterminator='\n');w.writeheader();w.writerows(items)

def audit(file,out):
    out.mkdir(exist_ok=True,parents=True)
    windows=[];arms=[];probes=[];seen=set()
    with ZipFile(file) as z:
        assert z.testzip() is None
        for r in csv.DictReader(io.StringIO(z.read('MANIFEST.tsv').decode('utf-8-sig')),delimiter='\t'):
            b=z.read(r['file']);assert len(b)==int(r['size_bytes']) and hashlib.md5(b).hexdigest()==r['md5']
        read=lambda n:json.loads(z.read(next(s for s in z.namelist() if n in s and s.endswith('.json'))))
        trials=read('layer2_merged_analysis')['trial_details']
        for config,groups in sorted(trials.items()):
            for condition,rows in sorted(groups.items()):
                bytrial=[]
                for r in rows:
                    raw=r['raw'];vals=np.array([raw[k] for k in sorted(raw)],dtype='<f8')
                    assert vals.shape==(11,r['n_points'])
                    assert np.isfinite(vals).all()
                    digest=hashlib.sha256(vals.tobytes()).hexdigest();seenbefore=digest in seen;seen.add(digest)
                    t=np.array(raw['t_rel']);dt=np.diff(t);x=np.array(raw['dt_s1s0_deg']);y=np.array(raw['dt_s2s1_deg'])
                    row=dict(configuration=config,excitation=condition,trial=r['trial'],recorded_points=len(t),time_span_s=round(float(t[-1]-t[0]),6),time_dt_median_ms=round(float(np.median(dt))*1000,5),nonpositive_dt=int((dt<=0).sum()),gap_over_15ms=int((dt>.015).sum()),duplicate_trace_digest=int(seenbefore),unchanged_joint_pair_adjacent=int(((np.diff(x)==0)&(np.diff(y)==0)).sum()),joint1_peak_to_peak_deg=round(float(np.ptp(x)),7),joint2_peak_to_peak_deg=round(float(np.ptp(y)),7),source_modes=len(r['modes']))
                    windows.append(row);bytrial.append(row)
                rr=lambda k:[x[k] for x in bytrial]
                arms.append(dict(configuration=config,excitation=condition,trials=len(rows),sum_timepoints=sum(rr('recorded_points')),median_J1_range_deg=round(float(np.median(rr('joint1_peak_to_peak_deg'))),6),median_J2_range_deg=round(float(np.median(rr('joint2_peak_to_peak_deg'))),6),unchanged_joint_pair_adjacent=sum(rr('unchanged_joint_pair_adjacent'))))
        for setting,d in read('exp5_probes')['probes'].items():
            a=d['A'];b=d['B']
            probes.append(dict(q2_deg=a['q2_deg'],A_forward=a['r_fwd'],A_reverse=a['r_rev'],A_forward_minus_reverse=round(a['r_fwd']-a['r_rev'],7),B_output_gain=b['G_out'],B_motor_gain=b['G_motor'],B_supplied_normalized_gain=b['G_norm'] if b['G_norm'] is not None else '',B_output_phase_rad=b['phase_out_rad']))
    write(out,'backlash-trial-quality.csv',windows);write(out,'backlash-condition-comparison.csv',arms);write(out,'backlash-physical-probes.csv',probes)
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('zip',type=Path);p.add_argument('out',type=Path);a=p.parse_args();audit(a.zip,a.out)
