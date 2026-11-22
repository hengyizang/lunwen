"""Check all release files of DaRUS 4224 and 5687, and derive physical summaries.
python check_preload.py output [--cache input-directory]
Requires numpy and openpyxl. Input versions and MD5s are checked at the repository.
"""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
from urllib.request import urlopen
import numpy as np
from openpyxl import load_workbook

BASE='https://darus.uni-stuttgart.de/api/'
def save(path,rows):
    with path.open('w',newline='') as fo:
        w=csv.DictWriter(fo,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path);p.add_argument('--cache',type=Path)
    args=p.parse_args();args.output.mkdir(exist_ok=True,parents=True)
    manifest=[];summary=[];models=[];replays=[]
    for record in (4224,5687):
        version=json.load(urlopen(BASE+f'datasets/:persistentId/versions/1.0?persistentId=doi:10.18419/DARUS-{record}',timeout=40))['data']
        for file in version['files']:
            name=file['label'];df=file['dataFile'];url=BASE+'access/datafile/'+str(df['id'])
            path=args.cache/(('d4224-' if record==4224 else '')+name) if args.cache else None
            data=path.read_bytes() if path and path.exists() else urlopen(url,timeout=45).read()
            checksum=hashlib.md5(data).hexdigest()
            assert checksum==df['checksum']['value'] and len(data)==df['filesize']
            manifest.append(dict(version_doi=f'10.18419/darus-{record}',file=name,download=url,
                                 bytes=len(data),md5=checksum,sha256=hashlib.sha256(data).hexdigest()))
            if not name.endswith('.xlsx'):continue
            w=load_workbook(io.BytesIO(data),data_only=True,read_only=True)
            for sh in w.worksheets:
                rows=iter(sh.values);header=list(next(rows))
                a=np.array(list(rows),dtype=float);assert a.shape[1]==len(header) and np.isfinite(a).all()
                d=dict(zip(header,a.T));row=dict(record=record,file=name,sheet=sh.title,observations=len(a),
                    channels=' | '.join(header),span_axis=header[0],axis_min=a[:,0].min(),axis_max=a[:,0].max(),
                    median_increment_native=float(np.median(np.diff(a[:,0]))),
                    nonincreasing_steps=int(np.sum(np.diff(a[:,0])<=0)),preload_min_Nm='',preload_max_Nm='',
                    preload_mean_Nm='',force_min_N='',force_max_N='',tracking_mae_um='',tracking_rms_um='')
                if 'time' in d and 'T_pl' in d:
                    row.update(preload_min_Nm=d['T_pl'].min(),preload_max_Nm=d['T_pl'].max(),
                               preload_mean_Nm=d['T_pl'].mean())
                if 'F_LDD' in d or 'F_z' in d:
                    force=d.get('F_LDD',d.get('F_z'));row.update(force_min_N=force.min(),force_max_N=force.max())
                if 'x_d' in d and 'x_T' in d:err=d['x_d']-d['x_T']
                elif 'desired_pos' in d and 'table_pos' in d:err=d['desired_pos']-d['table_pos']
                else:err=None
                if err is not None:
                    row.update(tracking_mae_um=np.mean(abs(err))*1e6,tracking_rms_um=np.sqrt(np.mean(err**2))*1e6)
                summary.append(row)
                # Discrete approximation to Steinle et al. Eqs. (1)-(2), not a logged command.
                # Compare only full trailing windows of 100 backward differences in one clock segment.
                if record==4224 and err is not None and (sh.title=='Adaptive Preload' or name=='Fig_9_Acceleration_Comparison.xlsx'):
                    assert np.allclose(np.diff(d['time']),1/2000,rtol=0,atol=1e-10)
                    unlimited=np.convolve(900*np.abs(np.diff(err))*2000,np.ones(100)/100,mode='valid')
                    limited=np.clip(unlimited,0.52,10.0)
                    measured=d['T_pl'][100:] if 'T_pl' in d else None
                    replays.append(dict(file=name,sheet=sh.title,first_included_zero_based_index=100,
                        full_windows=len(unlimited),scale_Ns=900,lower_target_Nm=0.52,upper_target_Nm=10,
                        reconstructed_below_lower=int(np.sum(unlimited<0.52)),
                        reconstructed_above_upper=int(np.sum(unlimited>10)),
                        reconstructed_unlimited_min_Nm=unlimited.min(),reconstructed_unlimited_max_Nm=unlimited.max(),
                        measured_preload_below_lower=int(np.sum(measured<0.52)) if measured is not None else '',
                        measured_preload_above_upper=int(np.sum(measured>10)) if measured is not None else '',
                        measured_vs_limited_same_index_rmse_Nm=np.sqrt(np.mean((measured-limited)**2)) if measured is not None else ''))
                def report(key,ch,value,unit):
                    models.append(dict(record=record,file=name,metric=key,model_or_channel=ch,value=value,unit=unit))
                if record==5687:
                    if name=='data_Fig4.xlsx':
                        for u in ('dB','deg'):
                            low=d['G_meas_min_'+u];high=d['G_meas_max_'+u]
                            for m in ('meas_mean','pt1','pt2','pt4'):
                                vals=d['G_'+m+'_'+u]
                                report('bins_inside_inclusive_observed_envelope',m+'_'+u,
                                       int(np.sum((vals>=low)&(vals<=high))),'of 580 bins')
                    if name=='data_Fig5.xlsx':
                        for ch in header[1:]:
                            y=d[ch];x=d['frequency'];j=np.where(y<=-3)[0][0];assert j>0 and y[j-1]>-3
                            value=np.interp(-3,[y[j],y[j-1]],[x[j],x[j-1]])
                            report('first_crossing_minus3dB_linear_interpolation',ch,value,'Hz')
                    if name in ('data_Fig6.xlsx','data_Fig7.xlsx'):
                        for ch in header:
                            if ch.startswith('e_x_'):
                                report('whole_record_tracking_RMS',ch,np.sqrt(np.mean(d[ch]**2))*1e6,'um')
                                report('whole_record_absolute_peak_error',ch,np.max(abs(d[ch]))*1e6,'um')
                                if 'table_pos' in d:
                                    report('max_abs_desired_minus_single_measured_position_minus_error',ch,
                                           np.max(abs(d['desired_pos']-d['table_pos']-d[ch]))*1e6,'um')
    save(args.output/'preload-files.csv',manifest);save(args.output/'preload-sheets.csv',summary)
    save(args.output/'mpc-drive-comparisons.csv',models);save(args.output/'preload-law-replay.csv',replays)
if __name__=='__main__':main()
