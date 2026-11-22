"""Derive same-distance scope comparisons from Tables 2 and 4 of the public article.
python derive_xbee.py FULLTEXT_XML OUTPUT_DIRECTORY
Source: https://www.ebi.ac.uk/europepmc/webservices/rest/PMC8587709/fullTextXML
"""
import argparse
import csv
from decimal import Decimal
from pathlib import Path
from xml.etree import ElementTree as ET


def run(article,out):
    root=ET.parse(article)
    tables={}
    for wrap in root.findall(".//table-wrap"):
        tables[wrap.findtext("label")]=[["".join(x.itertext()).strip() for x in tr.findall("td")] for tr in wrap.findall(".//tbody/tr")]
    receive=dict(tables['Table 4'])
    rows=[]
    for distance,minimum,maximum,jitter in tables['Table 2']:
        span=Decimal(maximum)-Decimal(minimum)
        assert span==Decimal(jitter)
        receiver=Decimal(receive[distance])
        rows.append([distance,str(span),str(receiver),str(span-receiver)])
    out.mkdir(parents=True,exist_ok=True)
    with (out/'xbee-scope-contrasts.csv').open('w',newline='') as f:
        w=csv.writer(f,lineterminator='\n')
        w.writerow(['distance_m','controller_serial_to_node_delay_span_ms','three_node_reception_jitter_ms','difference_of_two_descriptive_spreads_ms'])
        w.writerows(rows)


if __name__=='__main__':
    a=argparse.ArgumentParser(description=__doc__);a.add_argument('article',type=Path);a.add_argument('out',type=Path)
    args=a.parse_args();run(args.article,args.out)
