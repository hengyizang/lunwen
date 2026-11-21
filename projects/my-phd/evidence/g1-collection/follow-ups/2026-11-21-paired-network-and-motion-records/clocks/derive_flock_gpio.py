"""Match physical observer INT1 strobe trains to receiver markers on the 36 actual March CC430 logs.

Usage: python derive_flock_gpio.py RAW OUT
The pulse-width and pairing windows are descriptive filters. All per-trial exclusions are explicit.
"""
from argparse import ArgumentParser
from bisect import bisect_left, bisect_right
from collections import defaultdict
import csv
import io
from pathlib import Path
import re
from zipfile import ZipFile


def stamp(t):
    sec,frac=t.split('.')
    return int(sec)*10_000_000+int(frac.ljust(7,'0'))


def slots(serial):
    reports={}
    active=set()
    for line in serial.decode('utf-8','replace').splitlines():
        cols=line.split(',',4)
        if len(cols)!=5:continue
        dest=cols[2];txt=cols[4]
        if txt=='Log:'+dest+':Strobing':active.add(int(dest))
        match=re.fullmatch(r'Log:(\d+):(\d+):([0-9.]+)',txt)
        if match:
            bits=''.join(f'{int(x):08b}' for x in match[3].rstrip('.').split('.'))[:100]
            if len(bits)==100 and int(match[2])==bits.count('1'):
                key=int(match[1]),int(dest)
                if key in reports and reports[key]!=bits:raise ValueError('Conflicting raw masks')
                reports[key]=bits
    return active,reports


def pulses(data):
    opened={}
    pulse=defaultdict(list)
    with io.TextIOWrapper(data) as f:
        for t,observer,node,pin,value in csv.reader(f):
            if pin!='INT1':continue
            i=int(node);v=stamp(t)
            if value=='1':
                opened[i]=v
            elif i in opened:
                start=opened.pop(i)
                if v<start:raise ValueError('Negative pin pulse width')
                pulse[i].append((start,v))
    tx={i:[t for t in seq if 3500<=t[1]-t[0]<=4100] for i,seq in pulse.items()}
    rx={i:[start for start,stop in seq if 0<stop-start<=600] for i,seq in pulse.items()}
    return tx,rx


def trial(archive,prefix):
    active,reports=slots(archive.read(prefix+'/serial.csv'))
    tx,rx=pulses(archive.open(prefix+'/gpiotracing.csv'))
    eligible={i:ts for i,ts in tx.items() if i in active and len(ts)==100 and
              all(5500<=b[0]-a[0]<=9000 for a,b in zip(ts,ts[1:]))}
    rows=[]
    for window in (100,150,250):
        total=paired=agreements=tp=fp=fn=tn=ambiguous=mixed=mixed_equal=0
        delays=[]
        for (a,b),bits in reports.items():
            if a not in eligible or b not in rx:continue
            total+=1;timed_mask=[]
            for idx,(_,end) in enumerate(eligible[a]):
                lo=bisect_left(rx[b],end-window*10);hi=bisect_right(rx[b],end+window*10)
                if hi-lo>1:
                    ambiguous+=1;timed_mask.append('?');continue
                found=hi-lo==1
                timed_mask.append('1' if found else '0')
                expected=bits[idx]=='1'
                if found and expected:
                    tp+=1;delays.append((rx[b][lo]-end)/10)
                elif found:fp+=1
                elif expected:fn+=1
                else:tn+=1
            informative='1' in bits and '0' in bits
            mixed+=informative
            if '?' not in timed_mask:
                paired+=1
                identical=''.join(timed_mask)==bits
                agreements+=identical
                mixed_equal+=informative and identical
        sorted_delays=sorted(delays)
        def percentile(q):
            if not sorted_delays:return ''
            k=(len(sorted_delays)-1)*q
            i=int(k);j=min(i+1,len(sorted_delays)-1)
            return round(sorted_delays[i]+(k-i)*(sorted_delays[j]-sorted_delays[i]),4)
        rows.append(dict(test=prefix.split('/')[-1],half_window_us=window,nodes_with_serial_strobing=len(active),
            nodes_with_identified_100_pulse_train=len(eligible),raw_consistent_reported_links=len(reports),
            eligible_directed_links=total,links_no_ambiguous_gpio_window=paired,
            links_exactly_matching_100bit_serial_mask=agreements,links_with_mixed_serial_bits=mixed,
            mixed_links_exactly_matching=mixed_equal,serial1_marker1=tp,serial0_marker1=fp,
            serial1_marker0=fn,serial0_marker0=tn,positions_with_multiple_candidate_edges=ambiguous,
            matched_rx_rise_minus_tx_fall_median_us=percentile(.5),
            matched_rx_rise_minus_tx_fall_p05_us=percentile(.05),matched_rx_rise_minus_tx_fall_p95_us=percentile(.95)))
    return rows


def main():
    p=ArgumentParser(description=__doc__);p.add_argument('raw',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    rows=[]
    with ZipFile(a.raw/'2020-03_raw_dpp-cc430.zip') as z:
        for path in sorted({n.rsplit('/',1)[0] for n in z.namelist() if n.endswith('/gpiotracing.csv')}):
            rows.extend(trial(z,path))
    a.output.mkdir(parents=True,exist_ok=True)
    with (a.output/'flocklab-strobe-gpio.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=rows[0],lineterminator='\n');w.writeheader();w.writerows(rows)


if __name__=='__main__':main()
