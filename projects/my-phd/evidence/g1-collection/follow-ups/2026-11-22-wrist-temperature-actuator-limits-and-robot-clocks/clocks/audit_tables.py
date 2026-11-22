"""Derive aggregate contrasts from 5G-SMART D2.3 and Nguyen & Chosa, Table 2.

Usage: python audit_tables.py smart.pdf publisher.html OUTPUT_DIR
Requires Python 3.11+ and pdftotext (Poppler).
"""
import argparse
import csv
import hashlib
import re
import subprocess
from decimal import Decimal
from html.parser import HTMLParser
from pathlib import Path


class TableCells(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_cell = False
        self.parts = []
        self.cells = []

    def handle_starttag(self, tag, attrs):
        if tag in ('td','th'):
            self.in_cell = True
            self.parts = []

    def handle_endtag(self, tag):
        if tag in ('td','th') and self.in_cell:
            self.cells.append(' '.join(''.join(self.parts).split()))
            self.in_cell = False

    def handle_data(self, data):
        if self.in_cell:
            self.parts.append(data)


def save(file,rows):
    with file.open('w',newline='') as f:
        w=csv.DictWriter(f,list(rows[0]),lineterminator='\n')
        w.writeheader(); w.writerows(rows)


def analyse(pdf, html, out):
    assert hashlib.sha256(pdf.read_bytes()).hexdigest()=='226d5113344795d47539d8de5b951885fccc6f6033e265ac84f4bb9658c07db8'
    text=subprocess.check_output(['pdftotext','-layout',str(pdf),'-']).decode()
    contrasts=[]
    configs=[('3 Completion time values for mobile robot navigation','navigation','s',['0.5','1.0'],[0,3]),
             ('4 Stopping margin values','stopping margin','m',['0.5','1.0'],[0,3]),
             ('6 Completion time values for mobile robot docking','docking','s',['0.2','0.8'],[0,3]),
             ('8 Completion time values for robot manipulation','pick and place','s',[''],[1])]
    for caption,task,unit,speeds,cols in configs:
        end=text.index('Table '+caption)
        need=4 if len(cols)==1 else 6
        triples=[]
        for line in text[max(end-2500,0):end].splitlines():
            vals=re.findall(r'(?<![\w.])\d+\.\d+(?![\w.])',line)
            if len(vals)==need:
                triples.append([Decimal(v) for v in vals])
        ref,actual,extra=triples[-3:]
        for speed,idx in zip(speeds,cols):
            contrasts.append(dict(locator='Table '+caption.split()[0],endpoint=task,unit=unit,
                target_or_max_speed_m_s=speed,wired_reference_mean=ref[idx],
                actual_5g_minus_reference_mean=actual[idx]-ref[idx],added_traffic_minus_actual_mean=extra[idx]-actual[idx],
                added_traffic_minus_reference_mean=extra[idx]-ref[idx]))
    save(out/'kista-trial-contrasts.csv',contrasts)
    parsed=TableCells()
    parsed.feed(html.read_text())
    cells=[c.replace(',','') for c in parsed.cells]
    patterns=[('Image acquisition: external high-speed camera','173','1157','1335','948'),
              ('Image acquisition: host timestamps','2619','1177','1363','1096'),
              ('Image processing: high-speed camera','180','11','14.38','7.37'),
              ('Control transmission: host timestamps','2380','113','120.63','58.26'),
              ('Control and crawler actuation: high-speed camera','107','149','156.8','71.83')]
    results=[]
    for endpoint,*values in patterns:
        assert any(cells[i:i+4]==values for i in range(len(cells)-3)),endpoint
        n,median,mean,sd=map(Decimal,values)
        results.append(dict(endpoint=endpoint,n=n,mean_minus_median_ms=mean-median,
                            sd_to_mean_percent=round(100*sd/mean,3)))
    save(out/'crawler-observer-contrasts.csv',results)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('pdf',type=Path);p.add_argument('html',type=Path);p.add_argument('out',type=Path)
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True);analyse(a.pdf,a.html,a.out)
