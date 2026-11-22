"""Compare condition-level RMS and audit exact signal reuse after check_transmission.py."""
import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

def write(path,rows):
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
def main(folder):
    grouped=defaultdict(dict);digests=defaultdict(list)
    with (folder/'transmission-conditions.csv').open() as source:
        for row in csv.DictReader(source):
            if row['common_channel_hash']:digests[row['common_channel_hash']].append(row)
            file=row['file'];kind=row['series']
            if not file.startswith(('Fig_9_','Fig_11_')):continue
            speed=int(re.search(r'(100|50|75)mm',file).group(1))
            force=int(re.search(r'F_(?:ext|LDD)=(-?\d+)',row['condition']).group(1))
            if kind=='3759':on=file.endswith('_active.tab')
            else:on=row['condition'].endswith('Compensation=1')
            key=(kind,speed,force)
            assert on not in grouped[key]
            grouped[key][on]=row
    comparisons=[]
    for (kind,speed,force),pair in sorted(grouped.items()):
        off,on=pair[False],pair[True];off_rms=float(off['rms_position_error_native'])*1e6
        on_rms=float(on['rms_position_error_native'])*1e6
        comparisons.append(dict(series=kind,nominal_speed_mm_s=speed,external_force_label_N=force,
            off_rows=off['rows'],on_rows=on['rows'],off_rms_um=off_rms,on_rms_um=on_rms,
            reduction_percent=100*(1-on_rms/off_rms)))
    overlaps=[]
    for digest,group in sorted(digests.items()):
        if len(group)<2:continue
        for r in group:
            overlaps.append(dict(common_bytes_sha256=digest,series=r['series'],file=r['file'],
                                 condition=r['condition'],rows=r['rows']))
    write(folder/'compensation-on-off.csv',comparisons)
    write(folder/'reused-signals.csv',overlaps)
if __name__=='__main__':main(Path(sys.argv[1]))
