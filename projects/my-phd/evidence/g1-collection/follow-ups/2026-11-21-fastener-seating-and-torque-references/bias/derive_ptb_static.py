"""Cross-check PTB torque workbook against the two independent file representations.

python derive_ptb_static.py FOLDER_CONTAINING_XLSX_AND_TWO_CERTIFICATES OUTPUT_DIRECTORY
Requires openpyxl, numpy and Poppler pdftotext.
"""
import argparse
import csv
from pathlib import Path
import re
import subprocess
import numpy as np
from openpyxl import load_workbook


def write_csv(path, records):
    with path.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=records[0],lineterminator='\n')
        w.writeheader()
        w.writerows(records)


def certificate_rows(pdf):
    page=subprocess.check_output(['pdftotext','-layout','-f','5','-l','5',str(pdf),'-']).decode()
    table=[]
    for line in page.splitlines():
        parts=line.split()
        if len(parts)==7 and re.fullmatch(r'-?\d+',parts[0]) and all(
                x=='-' or re.fullmatch(r'-?\d+,\d+',x) for x in parts[1:]):
            table.append([int(parts[0]),*[None if x=='-' else float(x.replace(',','.')) for x in parts[1:]]])
    assert len(table)==36
    return table


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('folder',type=Path)
    p.add_argument('out',type=Path)
    a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=True)
    book=load_workbook(a.folder/'T40FH_calibration.xlsx',data_only=True,read_only=True)
    cases,validation=[],[]
    for name,pdf in [('kHz','12140_22-12.pdf'),('VDC','12141_22-12.pdf')]:
        sheet=list(book[name].values)
        observed=certificate_rows(a.folder/pdf)
        for k,record in enumerate(observed):
            # PDF splits each direction into two tables of 6 columns. Excel arranges all 12 in one row.
            offset=(k//9)%2*6+1
            native=sheet[k//18*9+k%9+2]
            assert native[0]==record[0]
            assert all((v is None and original=='-') or v==original for v,original in zip(record[1:],native[offset:offset+6]))
        for row_start,direction in [(2,'CW'),(11,'CCW')]:
            data=np.array([[float(row[j]) for j in [0,4,5,6,8,9,11,12]] for row in sheet[row_start:row_start+9]])
            # Fit increasing-load readings separately per mounting position, and hold one mounting out.
            loads=data[:,0]
            inc=data[:,[1,4,6]]
            dec=data[:,[2,5,7]]
            for j,orientation in enumerate([0,120,240]):
                nonzero=loads!=0
                deflection=dec[:,j]-inc[:,j]
                held=inc[:,j]
                train=inc[:,[h for h in range(3) if h!=j]].mean(axis=1)
                gain=np.dot(train,loads)/np.dot(loads,loads)
                residual_nm=(held/gain-loads)*1000
                cases.append(dict(output=name,direction=direction,mount_deg=orientation,
                                  nonzero_steps=int(nonzero.sum()),increasing_zero=inc[0,j],released_zero=dec[0,j],
                                  unloading_minus_loading_largest_absolute=round(max(abs(deflection[1:])),7),
                                  endpoint_difference=round(deflection[-1],7),
                                  max_deviation_2nd_increase=round(max(abs(data[:,3]-inc[:,j])),7) if j==0 else ''))
                validation.append(dict(output=name,direction=direction,heldout_mount_deg=orientation,
                                       training_mounts=2,heldout_nonzero_steps=int(nonzero.sum()),
                                       zero_intercept_fit_gain_output_per_kNm=round(gain,10),
                                       heldout_rms_torque_error_Nm=round(np.sqrt(np.mean(residual_nm[nonzero]**2)),6),
                                       heldout_max_abs_torque_error_Nm=round(max(abs(residual_nm[nonzero])),6)))
    write_csv(a.out/'ptb-torque-mounts.csv',cases)
    write_csv(a.out/'ptb-torque-holdouts.csv',validation)


if __name__=='__main__':
    main()
