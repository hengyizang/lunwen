"""Compare errors printed in Tables II and III of Kim et al., arXiv:2502.17528.
Run with the checked PDF as first argument and an output directory as second. Uses Poppler pdftotext.
"""
import csv
import hashlib
import re
import subprocess
import sys
from pathlib import Path

def derive(pdf,output):
    assert hashlib.sha256(pdf.read_bytes()).hexdigest()=='14ffd2735fe1b8d166743a21f4c09a84c9b936ab8d623df343de213f3a821bfd'
    text=subprocess.run(['pdftotext','-layout',str(pdf),'-'],check=True,capture_output=True).stdout.decode('utf8')
    rows=[]
    for table,direction in [('II','decreases'),('III','increases')]:
        begin=re.search(r'\bTABLE '+table+r'\b',text,re.M)
        assert begin
        chunk=text[begin.end():begin.end()+2200]
        data={}
        for method in ('No compensation','MLP','MLP(Sequence)','GRU'):
            pattern=re.escape(method)+r'\s+((?:[0-9.]+\s+){5}[0-9.]+)'
            found=re.search(pattern,chunk)
            assert found,(table,method)
            data[method]=list(map(float,found[1].split()))
        for i,axis in enumerate(['Fx','Fy','Fz','Mx','My','Mz']):
            zero=data['No compensation'][i]
            gru=data['GRU'][i]
            rows.append(dict(preprint_table=table,direction_as_captioned=direction,axis=axis,unit='N' if i<3 else 'N m',
                uncompensated_minus_GRU_RMSE=round(zero-gru,5),
                GRU_minus_sequence_MLP_RMSE=round(gru-data['MLP(Sequence)'][i],5),
                GRU_reduction_vs_uncompensated_percent=round(100*(zero-gru)/zero,3)))
    with (output/'kim-captioned-comparisons.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,list(rows[0]),lineterminator='\n')
        w.writeheader()
        w.writerows(rows)
if __name__=='__main__':
    derive(Path(sys.argv[1]),Path(sys.argv[2]))
