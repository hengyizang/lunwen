"""Summarize four rounded model-selection statistics from Wu and Revzen, Table 1."""
import argparse
import csv
from pathlib import Path
import re
import subprocess


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('authors_pdf',type=Path)
    p.add_argument('output',type=Path)
    a=p.parse_args()
    text=subprocess.check_output(['pdftotext','-layout',str(a.authors_pdf),'-']).decode()
    part=text.split('Table 1 Summary of model selection statistics',1)[1].split('Abbreviations:',1)[0]
    names=['Full (six rotations','Six rotations','Six translations only','Single translation']
    rows=[]
    for name in names:
        line,=[l[l.index(name):] for l in part.splitlines() if name in l]
        cv,bic=map(int,re.search(r'\s+(\d+)\s+(\d+)\s*$',line).groups())
        rows.append((name,cv,bic))
    a.output.mkdir(parents=True,exist_ok=True)
    with (a.output/'hexapod-model-selection.csv').open('w',newline='') as f:
        w=csv.writer(f,lineterminator='\n')
        w.writerow(['model','stated_free_parameters','published_fivefold_cv_error','published_bic','cv_error_over_full_model','bic_difference_from_full'])
        for name,df,(_,cv,bic) in zip(['six rotations and six translations','six rotations and one translation','six translations only','one translation'],[36,21,18,3],rows):
            w.writerow([name,df,cv,bic,round(cv/rows[0][1],6),bic-rows[0][2]])


if __name__=='__main__':
    main()
