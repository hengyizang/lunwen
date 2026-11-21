"""Summarize the complete physical reaction-wheel balance export. Python 3 standard library."""
import argparse
import csv
import hashlib
from decimal import Decimal
from itertools import groupby
from pathlib import Path


def write(path, data):
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer=csv.DictWriter(stream, fieldnames=data[0], lineterminator='\n')
        writer.writeheader()
        writer.writerows(data)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('record',type=Path)
    parser.add_argument('out',type=Path)
    args=parser.parse_args()
    raw=args.record.read_bytes()
    lines=raw.decode().splitlines()
    if lines[-1]!='# end':
        raise ValueError('Missing firmware end-of-export marker')
    records=list(csv.DictReader(lines[:-1]))
    if len(records)!=1000 or [int(row['t_ms']) for row in records]!=list(range(0,2000,2)):
        raise ValueError('Unexpected ring-buffer slots')
    command=[int(Decimal(row['u_V'])*1000) for row in records]
    change=[b-a for a,b in zip(command,command[1:])]
    runs=[]
    rail=lambda mv: (1 if mv==6000 else -1 if mv==-6000 else 0)
    for endpoint, group in groupby(range(len(records)),key=lambda i:rail(command[i])):
        if endpoint:
            indices=list(group)
            rows=[records[i] for i in indices]
            runs.append(dict(command_endpoint_V=6*endpoint,first_export_slot=indices[0],last_export_slot=indices[-1],
                             sample_rows=len(indices),first_nominal_ms=indices[0]*2,last_nominal_ms=indices[-1]*2,
                             first_to_last_nominal_span_ms=(indices[-1]-indices[0])*2,
                             includes_last_record=int(indices[-1]==len(records)-1),
                             min_wheel_rad_s=min(Decimal(x['wheel_rad_s']) for x in rows),
                             max_wheel_rad_s=max(Decimal(x['wheel_rad_s']) for x in rows),
                             min_bus_V=min(Decimal(x['vbus_V']) for x in rows),
                             max_bus_V=max(Decimal(x['vbus_V']) for x in rows)))
    summary=dict(sha256=hashlib.sha256(raw).hexdigest(),rows=len(records),
                 min_command_mV=min(command),max_command_mV=max(command),command_plus_6V_rows=command.count(6000),
                 command_minus_6V_rows=command.count(-6000),endpoint_segments=len(runs),
                 adjacent_steps=len(change),positive_600mV_changes=change.count(600),
                 negative_600mV_changes=change.count(-600),
                 abs_changes_above_600mV=sum(abs(v)>600 for v in change),
                 bus_min_V=min(Decimal(x['vbus_V']) for x in records),
                 bus_max_V=max(Decimal(x['vbus_V']) for x in records))
    args.out.mkdir(parents=True,exist_ok=True)
    write(args.out/'reaction-wheel-settings.csv',[summary])
    write(args.out/'reaction-wheel-endpoints.csv',runs)


if __name__=='__main__':
    main()
