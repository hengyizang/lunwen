"""Summarize selected tabs of Liu et al.'s Source Data workbook. Usage: python derive_thermal_grid.py SourceData.xlsx output"""
import argparse
import csv
import hashlib
import re
from collections import defaultdict
from pathlib import Path
from statistics import fmean
from xml.etree import ElementTree as ET
from zipfile import ZipFile

NS='{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
RID='{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id'

def write(p,rows):
    with p.open('w',newline='',encoding='utf8') as f:
        w=csv.DictWriter(f,list(rows[0]),lineterminator='\n')
        w.writeheader()
        w.writerows(rows)

def analyze(path,out):
    assert hashlib.sha256(path.read_bytes()).hexdigest()=='3f4ae8f3f272c43a3acde90531a5852dcd8f36bd25aff5aa9e61460e51557a40'
    with ZipFile(path) as archive:
        strings=[''.join(s.itertext()) for s in ET.fromstring(archive.read('xl/sharedStrings.xml'))]
        rel={r.get('Id'):r.get('Target') for r in ET.fromstring(archive.read('xl/_rels/workbook.xml.rels'))}
        sheets={s.get('name'):'xl/'+rel[s.get(RID)] for s in ET.fromstring(archive.read('xl/workbook.xml')).findall('.//'+NS+'sheet')}
        def values(name,min_row):
            records=[]
            for r in ET.fromstring(archive.read(sheets[name])).findall('.//'+NS+'row'):
                if int(r.get('r'))<min_row:
                    continue
                cells={}
                for c in r.findall(NS+'c'):
                    val=c.findtext(NS+'v')
                    if val:
                        cells[re.sub(r'\d','',c.get('r'))]=strings[int(val)] if c.get('t')=='s' else float(val)
                if cells:
                    records.append(cells)
            return records
        measurements=values('Figure 5b',5)
        matrix=values('Figure 5c',5)
        long_grid=values('Figure 5d',5)
        coefs=values('Figure 5e',5)
        grid={}
        for start in range(ord('B'),ord('W')+1,3):
            temp=matrix[0][chr(start)]
            for r in matrix:
                grid[(temp,r[chr(start+1)])]=r[chr(start+2)]
        assert len(grid)==len(long_grid)==80
        assert all(grid[(r['B'],r['C'])]==r['D'] for r in long_grid)
        outrows=[]
        for mean,coef in zip(measurements,coefs):
            temp=mean['C']
            assert temp==mean['G']==coef['B']==coef['D']
            curve={p:v for (t,p),v in grid.items() if t==temp}
            err=[v-(coef['C']*p+coef['E']) for p,v in curve.items()]
            outrows.append(dict(temperature_C=temp,pressure_levels=len(curve),
                figure_5c_and_5d_exact_matches=len(curve),
                grid_voltage_rise_from_10_to_100kPa_V=round(curve[100]-curve[10],5),
                grid_minus_fixed_pressure_mean_at_100kPa_V=round(curve[100]-mean['D'],5),
                max_abs_grid_minus_fig5e_linear_reconstruction_V=round(max(map(abs,err)),6)))
        write(out/'liu-thermal-pressure-grid.csv',outrows)
        traces=values('Figure 4d',5); result=[]
        for start in range(ord('B'),ord('N')+1,3):
            ps=[r[chr(start)] for r in traces if chr(start) in r]
            assert len(set(ps))==1
            time=[r[chr(start+1)] for r in traces]
            volts=[r[chr(start+2)] for r in traces]
            result.append(dict(pressure_label_kPa=ps[0],time_voltage_pairs=len(time),window_start_s=time[0],window_end_s=time[-1],
                increasing_time_steps=sum(t2>t1 for t1,t2 in zip(time,time[1:])),
                peak_to_peak_voltage_V=round(max(volts)-min(volts),5),mean_voltage_V=round(fmean(volts),5)))
        write(out/'liu-pressure-trace-windows.csv',result)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('workbook',type=Path)
    parser.add_argument('output',type=Path)
    args=parser.parse_args()
    args.output.mkdir(exist_ok=True,parents=True)
    analyze(args.workbook,args.output)
