"""Summarize measured braking torque vs specified torque and independent tangential contact force.
Use a downloaded release .7z or its pinned file URL. Requires libarchive and NumPy.
"""
import argparse
import csv
import ctypes as ct
import hashlib
import io
import re
from pathlib import Path
from urllib.request import urlopen

import numpy as np

URL='https://data.4tu.nl/file/8e5df55a-42f4-45a3-9336-501c38bc4b85/202cb5cc-3b8c-4450-af91-8713e8c01332'
SHA='437c938f44d9725d519eb48f5e34a36ccf26bb499ee87329ca574d48f55cdaef'

def measurements(data):
    lib=ct.CDLL('libarchive.so.13')
    ptr=ct.c_void_p
    def api(name,ret,args):
        f=getattr(lib,name);f.restype=ret;f.argtypes=args
        return f
    a=api('archive_read_new',ptr,[])()
    support=api('archive_read_support_format_7zip',ct.c_int,[ptr])
    openmem=api('archive_read_open_memory',ct.c_int,[ptr,ptr,ct.c_size_t])
    header=api('archive_read_next_header',ct.c_int,[ptr,ct.POINTER(ptr)])
    path=api('archive_entry_pathname',ct.c_char_p,[ptr]);size=api('archive_entry_size',ct.c_longlong,[ptr])
    read=api('archive_read_data',ct.c_ssize_t,[ptr,ptr,ct.c_size_t])
    free=api('archive_read_free',ct.c_int,[ptr])
    try:
        assert support(a)==0 and openmem(a,data,len(data))==0
        entry=ptr()
        while True:
            status=header(a,ct.byref(entry))
            if status==1:break
            if status!=0:raise RuntimeError('Invalid archive entry')
            name=path(entry).decode().rsplit('/',1)[-1]
            match=re.fullmatch(r'(\d+)_(\d+)Nm_(\d+)RPM_(\d+)N(_repeat)?\.txt',name)
            is_decay=name.startswith('Traction_Decay_7_5Nm_') and name.endswith('.txt')
            if not (match or is_decay):continue
            n=size(entry); buf=ct.create_string_buffer(n);offset=0
            while offset<n:
                got=read(a,ct.byref(buf,offset),n-offset)
                if got<=0:raise IOError(name)
                offset+=got
            values=np.loadtxt(io.BytesIO(buf.raw))
            expected=float(match[1]+'.'+match[2]) if match else 7.5
            group=('torque-mode repeats' if match[5] else 'torque-mode primary') if match else 'traction-decay'
            assert values.ndim==2 and values.shape[1]==6 and np.isfinite(values).all(),name
            time,load,force,mu,rpm,torque=values.T
            yield group,dict(rows=len(values),backward=int(sum(np.diff(time)<0)),stationary=int(sum(np.diff(time)==0)),source_rate_median_s=float(np.median(np.diff(time))),brake_file_mean_error=float(np.mean(-torque-expected)),brake_file_mean_abs_error=float(np.mean(abs(-torque-expected))),traction_torque_minus_brake_mean=float(np.mean(0.027*force+torque)),time_span_s=float(time[-1]-time[0]))
    finally:
        free(a)

def audit(source,out):
    if str(source)=='remote':
        with urlopen(URL,timeout=180) as f:data=f.read()
    else:data=Path(source).read_bytes()
    assert len(data)==119605044 and hashlib.sha256(data).hexdigest()==SHA
    by={}
    for k,v in measurements(data):by.setdefault(k,[]).append(v)
    summary=[]
    for k,items in by.items():
        field=lambda n:np.array([r[n] for r in items])
        summary.append(dict(group=k,files=len(items),rows=int(sum(field('rows'))),min_rows=int(min(field('rows'))),max_rows=int(max(field('rows'))),nonincreasing_time_samples=int(sum(field('backward')+field('stationary'))),min_of_file_median_step_s=round(min(field('source_rate_median_s')),6),max_of_file_median_step_s=round(max(field('source_rate_median_s')),6),median_of_file_mean_resisting_brake_minus_named_setting_Nm=round(float(np.median(field('brake_file_mean_error'))),6),median_of_file_mean_abs_resisting_brake_minus_named_setting_Nm=round(float(np.median(field('brake_file_mean_abs_error'))),6),median_of_file_mean_contact_traction_torque_plus_signed_brake_Nm=round(float(np.median(field('traction_torque_minus_brake_mean'))),6)))
    assert len(summary)==3
    with out.open('w',newline='',encoding='utf8') as f:
        w=csv.DictWriter(f,list(summary[0]),lineterminator='\n');w.writeheader();w.writerows(summary)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('archive',help="File path or 'remote'");p.add_argument('csv',type=Path)
    args=p.parse_args();audit(args.archive,args.csv)
