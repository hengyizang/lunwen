"""Summarize the four distinct triangular command cycles in Zenodo 15584329."""
from bisect import bisect_left
import argparse
import csv
import hashlib
import math
from pathlib import Path

SOURCE_MD5 = "654c05be81fa60391e4b481787c320d3"


def at(x, y, value):
    index = bisect_left(x, value)
    if x[index] == value:
        return y[index]
    weight = (value-x[index-1])/(x[index]-x[index-1])
    return y[index-1] + weight*(y[index]-y[index-1])


def integrate(x, y):
    return math.fsum((x2-x1)*(y2+y1)/2 for x1,x2,y1,y2 in zip(x,x[1:],y,y[1:]))


def summarize(input_csv):
    if hashlib.md5(input_csv.read_bytes()).hexdigest() != SOURCE_MD5:
        raise ValueError("Expected the fixed Zenodo data.csv")
    with input_csv.open(newline='') as src:
        rows = list(csv.DictReader(src))
    t,x,y = ([float(r[key]) for r in rows] for key in ('Time','Input','Output'))
    assert all(math.isfinite(v) for col in (t,x,y) for v in col)
    assert all(b>a for a,b in zip(t,t[1:]))
    min_x = min(x)
    minima = [i for i,value in enumerate(x) if value==min_x]
    max_x = max(x)
    maxima = [i for i,value in enumerate(x) if value==max_x]
    if len(minima)!=5 or len(maxima)!=4:
        raise ValueError("Incomplete command cycles")
    result=[]
    for cycle,(a,b,c) in enumerate(zip(minima,maxima,minima[1:]),1):
        xu,yu=x[a:b+1],y[a:b+1]
        xd,yd=x[b:c+1][::-1],y[b:c+1][::-1]
        assert all(u<v for xx in (xu,xd) for u,v in zip(xx,xx[1:]))
        row=dict(cycle=cycle,first_row_1based=a+1,peak_row_1based=b+1,last_row_1based=c+1,
                 samples_including_shared_minima=c-a+1,rising_steps=b-a,falling_steps=c-b,
                 source_start_time=t[a],source_peak_time=t[b],source_end_time=t[c],
                 output_at_start=y[a],output_at_peak_command=y[b],output_at_end=y[c],
                 output_range_min=min(y[a:c+1]),output_range_max=max(y[a:c+1]),
                 area_falling_minus_rising_input_output_units=integrate(xd,yd)-integrate(xu,yu))
        for q in (.25,.5,.75):
            rise,fall=at(xu,yu,q),at(xd,yd,q)
            row[f'output_rising_input_{q}']=rise
            row[f'output_falling_input_{q}']=fall
            row[f'fall_minus_rise_input_{q}']=fall-rise
        result.append(row)
    return result


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('data_csv',type=Path)
    parser.add_argument('output',type=Path)
    args=parser.parse_args()
    data=summarize(args.data_csv)
    args.output.mkdir(parents=True,exist_ok=True)
    with (args.output/'pneumatic-hysteresis-cycles.csv').open('w',newline='') as dst:
        writer=csv.DictWriter(dst,fieldnames=data[0],lineterminator='\n')
        writer.writeheader()
        writer.writerows(data)
