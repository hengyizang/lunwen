"""Summarize DOI 10.3390/en17236096/s1. Usage: python derive-current-grid.py SUPPLEMENT_ZIP OUTPUT_DIRECTORY"""
import csv
import hashlib
import io
import math
import re
import statistics
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

NS = {'x': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
COLS = [chr(c) for c in range(ord('D'), ord('Z')+1)] + ['AA','AB','AC']
SOURCE = Path(sys.argv[1])
OUT = Path(sys.argv[2])
OUT.mkdir(parents=True, exist_ok=True)

def write(name, rows):
    with (OUT/name).open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=rows[0], lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)

def sheets(data):
    with zipfile.ZipFile(io.BytesIO(data)) as book:
        strings = [''.join(el.itertext()) for el in ET.fromstring(book.read('xl/sharedStrings.xml'))]
        rels = {r.get('Id'):r.get('Target') for r in ET.fromstring(book.read('xl/_rels/workbook.xml.rels'))}
        workbook = ET.fromstring(book.read('xl/workbook.xml'))
        for s in workbook.findall('x:sheets/x:sheet', NS):
            target = rels[s.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')]
            root = ET.fromstring(book.read('xl/'+target))
            cells = {}
            for c in root.findall('.//x:c', NS):
                v = c.findtext('x:v', None, NS)
                if v is not None:
                    cells[c.get('r')] = strings[int(v)] if c.get('t')=='s' else v
            yield s.get('name'), cells

def f(value):
    try:
        return float(value)
    except (ValueError, TypeError):
        return math.nan

def summary(values):
    return round(values, 7)

rows, exceptional = [], []
with zipfile.ZipFile(SOURCE) as src:
    for name in sorted(n for n in src.namelist() if n.endswith('.xlsx')):
        data = src.read(name)
        sheets_by_name = dict(sheets(data))
        grid, raw = sheets_by_name['DaneZbiorcze'], sheets_by_name['Arkusz1']
        assert [grid[f'B{4+30*x}'] for x in [0,1,9]] == ['id meas [A]','iq meas [A]','Trq meas [Nm]']
        quadrant = Path(name).stem[-2:]
        points, missing, unmatched = [], 0, 0
        for i in range(26):
            for j, col in enumerate(COLS):
                rd,rq = f(grid[col+'5']),f(grid[f'C{6+i}'])
                for block in [1,9]:
                    assert rd == f(grid[col+str(5+30*block)]) and rq == f(grid[f'C{6+i+30*block}'])
                md,mq,tq = [f(grid.get(col+str(6+i+30*k))) for k in [0,1,9]]
                finite = list(map(math.isfinite,[md,mq,tq]))
                if len(set(finite))>1:
                    unmatched += 1
                if not all(finite):
                    missing += 1
                    continue
                # Match the grid cells to the detailed worksheet by measured currents and signed torque.
                points.append((rd,rq,md,mq,tq))
                if math.hypot(rd,rq)>250+1e-8:
                    exceptional.append(dict(quadrant=quadrant,iq_row=i,id_column=j,id_req_A=rd,iq_req_A=rq,request_norm_A=summary(math.hypot(rd,rq)),measured_norm_A=summary(math.hypot(md,mq)),signed_torque_Nm=tq))
        grid_signatures={(md,mq,tq) for _,_,md,mq,tq in points}
        raw_values=[]
        for cell in raw:
            if re.fullmatch(r'B[0-9]+',cell):
                row=cell[1:]
                md,mq,calculated,direct,signed=[f(raw.get(c+row)) for c in 'BCNOP']
                if all(map(math.isfinite,[md,mq,calculated,direct,signed])):
                    raw_values.append((md,mq,calculated,direct,signed))
        assert len(raw_values)==len(points)
        # A few cells can store the same floating-point value with different decimal precision.
        mismatch=max(abs(a-b) for p,q in zip(sorted((md,mq,tq) for md,mq,_,_,tq in raw_values),sorted(grid_signatures)) for a,b in zip(p,q))
        assert mismatch<1e-7 and len(grid_signatures)==len(points)
        errs=[calculated-signed for _,_,calculated,_,signed in raw_values]
        rows.append(dict(quadrant=quadrant,workbook_sha256=hashlib.sha256(data).hexdigest(),grid_cells=26*26,finite_paired_cells=len(points),unavailable_cells=missing,mixed_availability_cells=unmatched,above_250A_requested_norm=sum(math.hypot(p[0],p[1])>250+1e-8 for p in points),above_250A_measured_norm=sum(math.hypot(p[2],p[3])>250 for p in points),max_requested_norm_A=summary(max(math.hypot(p[0],p[1]) for p in points)),max_measured_norm_A=summary(max(math.hypot(p[2],p[3]) for p in points)),max_abs_id_tracking_error_A=summary(max(abs(p[0]-p[2]) for p in points)),max_abs_iq_tracking_error_A=summary(max(abs(p[1]-p[3]) for p in points)),min_signed_torque_Nm=min(p[4] for p in points),max_signed_torque_Nm=max(p[4] for p in points),max_abs_torque_calc_minus_signed_Nm=summary(max(map(abs,errs))),torque_calc_minus_signed_RMSE_Nm=summary(math.sqrt(statistics.mean(x*x for x in errs))),max_abs_T_mes_plus_T_mes_K_Nm=summary(max(abs(d+s) for _,_,_,d,s in raw_values))))
write('current-grid-summary.csv',rows)
write('current-grid-boundary.csv',exceptional)
