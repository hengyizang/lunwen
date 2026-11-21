"""Read PTB optical and electrical traces from the original dynamic-sensor experiment.

python derive_ptb_dynamic.py PTB_ZIP OUTPUT_DIRECTORY
Dependencies: numpy.
"""
import argparse
import csv
import hashlib
import io
from pathlib import Path
import re
from zipfile import ZipFile
import numpy as np


def write_csv(path, rows):
    with path.open('w', newline='', encoding='utf-8') as f:
        wr=csv.DictWriter(f, fieldnames=rows[0], lineterminator='\n')
        wr.writeheader()
        wr.writerows(rows)


def parse_traces(data):
    lines = data.decode('ascii').splitlines()
    markers = [i for i,line in enumerate(lines) if line.strip()=='58']
    traces=[]
    for i in markers:
        channel = lines[i+2].strip()
        meta = lines[i+7].split()
        n=int(meta[1])
        period=float(meta[4])
        end=i+12
        while lines[end].strip()!='-1':
            end+=1
        vector=np.fromstring(' '.join(lines[i+12:end]),sep=' ')
        assert vector.size==n and np.isfinite(vector).all()
        traces.append((channel,period,vector))
    return traces


def rigid(data):
    mat=np.loadtxt(io.BytesIO(data))
    keep=(mat[:,2:5]==3).all(axis=1)
    x=mat[keep,5:8]
    y=mat[keep,8:11]
    # Fit a proper rotation, allowing translation. Units stay as instrument-export coordinates.
    xc=x-x.mean(0)
    yc=y-y.mean(0)
    u,_,vt=np.linalg.svd(xc.T@yc)
    sign=np.linalg.det(u@vt)
    rotation=(u*np.array([1,1,sign]))@vt
    residual=xc@rotation-yc
    angle=np.degrees(np.arccos(np.clip((np.trace(rotation)-1)/2,-1,1)))
    return len(mat),len(x),round(float(angle),8),round(float(np.sqrt(np.mean(np.sum(residual**2,axis=1)))),9)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('zip',type=Path)
    parser.add_argument('out',type=Path)
    a=parser.parse_args()
    a.out.mkdir(parents=True,exist_ok=True)
    files,peaks,facets=[],[],[]
    with ZipFile(a.zip) as z:
        for p in z.namelist():
            if p.endswith('/'):
                continue
            data=z.read(p)
            digest=hashlib.sha256(data).hexdigest()
            if p.endswith('.asc'):
                traces=parse_traces(data)
                points=len(traces)//3
                labels=[traces[j*points][0] for j in range(3)]
                files.append(dict(member=p,sha256=digest,scan_points=points,series=len(traces),
                                  samples_per_channel=len(traces[0][2]),sample_interval_s=traces[0][1],
                                  laser_label=labels[0],ref1_label=labels[1],ref2_label=labels[2]))
                if p.endswith('/z_Scan_time.asc'):
                    mass=Path(p).parent.name
                    for j in range(points):
                        _,period,laser=traces[j]
                        ref_label,_,base=traces[j+points]
                        assert 'Beschleunigung' in ref_label
                        freq=np.fft.rfftfreq(len(laser),period)
                        numerator=abs(np.fft.rfft(laser-laser.mean()))
                        denominator=abs(np.fft.rfft(base-base.mean()))
                        band=(freq>=500)&(freq<=2200)
                        for floor in (0.0,0.001,0.01,0.1):
                            valid=band & (denominator>floor*denominator[band].max())
                            k=np.flatnonzero(valid)[np.argmax(numerator[valid]/denominator[valid])]
                            peaks.append(dict(mass_group=mass,scan_point_1based=j+1,
                                              base_spectral_amplitude_floor_as_band_fraction=floor,
                                              considered_frequency_bins=int(valid.sum()),
                                              spectral_peak_hz=round(freq[k],7),
                                              laser_to_base_amplitude_ratio=round(numerator[k]/denominator[k],8)))
            elif re.search(r'/result_[AB]\d+\.txt$',p):
                num,valid,angle,error=rigid(data)
                obj,frame=re.search(r'result_([AB])(\d+)',p).groups()
                facets.append(dict(member=p,sha256=digest,body=obj,frame=int(frame),facets=num,
                                   valid_facets=valid,rotation_from_initial_deg=angle,
                                   rigid_residual_rms_export_coordinate_units=error))
    write_csv(a.out/'ptb-dynamic-acquisitions.csv',files)
    write_csv(a.out/'ptb-axial-transfer.csv',peaks)
    write_csv(a.out/'ptb-rigid-motion.csv',sorted(facets,key=lambda v:(v['body'],v['frame'])))


if __name__=='__main__':
    main()
