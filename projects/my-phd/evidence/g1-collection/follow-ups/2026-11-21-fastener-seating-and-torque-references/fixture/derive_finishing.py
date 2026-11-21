"""Extract independent fixture force profiles and authors' condition means from the archived vector plots.

python derive_finishing.py RELEASE.zip OUT
Requires numpy and PyMuPDF. The input is Zenodo 6457906 (v1.0.0).
"""
import argparse
import csv
import hashlib
import re
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

import numpy as np
import pymupdf


def save(path, rows):
    with path.open('w', newline='', encoding='utf-8') as stream:
        writer=csv.DictWriter(stream, fieldnames=rows[0], lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def number(s):
    return float(s.replace('−','-').replace(',',''))


def calibrate(page, drawings):
    """Pair each printed grid coordinate with its tick label by nearest center."""
    words=[w for w in page.get_text('words') if re.fullmatch(r'[−-]?[\d,]+(?:\.\d+)?',w[4])]
    xlines=np.array([i[1].x for i in drawings[0]['items']])
    ylines=np.array([i[1].y for i in drawings[1]['items']])
    xlabels=[w for w in words if w[1]>max(i[1].y for i in drawings[0]['items'])]
    ylabels=[w for w in words if w not in xlabels]
    slopes=[]
    for loc,labels,mid in [(xlines,xlabels,lambda w:(w[0]+w[2])/2),(ylines,ylabels,lambda w:(w[1]+w[3])/2)]:
        if len(loc)!=len(labels) or len(loc)<2:
            raise ValueError(('axis ticks',loc,labels))
        pairs=[min(labels,key=lambda w:abs(mid(w)-v)) for v in loc]
        if len(set(w[4] for w in pairs))!=len(loc):
            raise ValueError('Ambiguous grid calibration')
        vals=[number(w[4]) for w in pairs]
        coeff=np.polyfit(loc,vals,1)
        if np.max(abs(np.polyval(coeff,loc)-vals))>0.03:
            raise ValueError('Nonlinear figure axes')
        slopes.append(coeff)
    return slopes


def series(drawings,color,scales):
    matching=[d for d in drawings if d['color']==color and len(d['items'])>100]
    if len(matching)!=1:
        raise ValueError('Ambiguous or missing force path')
    lines=matching[0]['items']
    if not all(i[0]=='l' for i in lines):raise ValueError('Nonlinear path segment')
    points=[lines[0][1]]+[i[2] for i in lines]
    x,y=np.array([(p.x,p.y) for p in points]).T
    t=np.polyval(scales[0],x)
    if np.any(np.diff(t)<=0):raise ValueError('Non-monotonic plot trace')
    return t,np.polyval(scales[1],y)


def force_row(name,data):
    with pymupdf.open(stream=data,filetype='pdf') as doc:
        pg=doc[0]
        draws=pg.get_drawings()
        scales=calibrate(pg,draws)
        t,force=series(draws,(0.,0.,1.),scales)
        td,desired=series(draws,(1.,0.,0.),scales)
    if len(t)!=len(td) or np.max(abs(t-td))>0.0001:raise ValueError('Plotted time mismatch')
    scenario=next(s for s in name.split('/') if re.match('[123]_',s) and s.endswith(('profile','contact')))
    tc=6 if scenario.startswith('3') else 4
    mask=(t>=0)&(t<tc)
    baseline=(t>=-.5)&(t<=-.1)
    params=re.search(r'_F_([0-9]+)N',name),re.search(r'_v_([.0-9]+)_',name)
    settings=re.search(r'(?:scaling_|t_ramp_)([.\d]+)',name)[1]
    f=np.asarray(force[mask]);d=np.asarray(desired[mask]);span=np.quantile(force[baseline],[.05,.5,.95]) if any(baseline) else [np.nan]*3
    return dict(file=name,sha256=hashlib.sha256(data).hexdigest(),scenario=scenario,control=PurePosixPath(name).parent.name,
                target_N=int(params[0][1]),speed_m_s=float(params[1][1]),gain_or_ramp_s=float(settings),
                plotted_vertices=len(t),time_start_s=round(t[0],5),time_end_s=round(t[-1],5),row_interval_ms=round(1000*np.median(np.diff(t)),6),
                baseline_window_points=int(baseline.sum()),baseline_p05_N=round(span[0],3),baseline_median_N=round(span[1],3),baseline_p95_N=round(span[2],3),
                registered_contact_window_s=tc,window_vertices=len(f),fixture_max_N=round(float(f.max()),3),
                time_fixture_max_s=round(t[mask][np.argmax(f)],5),max_abs_error_N=round(max(abs(f-d)),3),
                mean_abs_error_N=round(float(np.mean(abs(f-d))),3),last_s_mean_force_N=round(float(np.mean(force[mask&(t>=tc-1)])),3))


def table_rows(name,data):
    with pymupdf.open(stream=data,filetype='pdf') as doc:
        pg=doc[0]; words=[w for w in pg.get_text('words') if w[1]>25]
    group=[w for w in words if w[2]<30]
    settings=[w for w in words if 38<=w[2]<=66 and re.fullmatch('[.0-9]+',w[4])]
    out=[]
    for setting in settings:
        line=[w for w in words if abs(w[1]-setting[1])<1 and w[0]>65]
        val=[w for w in line if re.fullmatch('[.0-9]+',w[4])]
        aborted=any('aborted' in w[4] for w in line)
        f=min(group,key=lambda w:abs(w[1]-setting[1]))
        row=dict(file=name,sha256=hashlib.sha256(data).hexdigest(),scenario=name.split('/Test_scenarios/')[1].split('/')[0],
            control=PurePosixPath(name).parent.name,speed_m_s=float(re.search('_v_([.0-9]+)_',name)[1]),
            target_N=int(f[4]),gain_or_ramp_s=float(setting[4]),aborted=int(aborted))
        # Numerical columns have aligned right edges and fixed order in the two formats.
        cols=[('settling_s',(76,114)),('max_contact_abs_error_N',(120,159)),
              ('mean_contact_abs_error_N',(180,218)),('sd_contact_abs_error_N',(232,270)),
              ('max_moving_abs_error_N',(282,317)),('mean_moving_abs_error_N',(337,379)),
              ('sd_moving_abs_error_N',(388,432))]
        seen=0
        for field,(low,high) in cols:
            cell=[w[4] for w in val if low<=w[2]<=high]
            if len(cell)>1:raise ValueError(('table column ambiguity',field,name))
            row[field]=cell[0] if cell else ''
            seen+=len(cell)
        if seen!=len(val) or (not aborted and not row['max_contact_abs_error_N']):raise ValueError(('table layout',name,setting,line))
        out.append(row)
    return out


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive',type=Path)
    parser.add_argument('out',type=Path)
    a=parser.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    force=[];tables=[]
    with ZipFile(a.archive) as z:
        for name in sorted(z.namelist()):
            if '/TcpUR_FzATI/' in name and name.endswith('_FzATI.pdf') and PurePosixPath(name).parent.name in ('UR','ACF'):
                force.append(force_row(name,z.read(name)))
            if '3_Evaluation' in name and name.endswith('_mean.pdf'):
                tables.extend(table_rows(name,z.read(name)))
    def setting(row):
        return (row['scenario'],row['control'],row['target_N'],row['speed_m_s'],row['gain_or_ramp_s'])
    individual={setting(row): row for row in force}
    if len(individual)!=len(force):raise ValueError('Nonunique condition plot')
    for row in tables:
        plot=individual.get(setting(row))
        if bool(plot)==bool(row['aborted']):raise ValueError('Missing plot for completed condition')
        row['single_plot_peak_error_minus_published_mean_of_peak_errors_N']=(round(plot['max_abs_error_N']-float(row['max_contact_abs_error_N']),3) if plot else '')
    save(a.out/'finishing-force-traces.csv',force)
    save(a.out/'finishing-published-conditions.csv',tables)


if __name__=='__main__':
    main()
