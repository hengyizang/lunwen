"""Check six 15-receiver TelosB reception matrices against their published plot scripts.
Input: the Grid Topology (Cleaned Raw data).zip file in Mendeley release v2.
"""
import argparse
import csv
import hashlib
import io
import itertools
import re
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

NS = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
IDS = frozenset(range(1, 3001))
MOTES = tuple(range(1, 16))


def bits(workbook):
    with ZipFile(io.BytesIO(workbook)) as book:
        strings = [''.join(s.itertext()) for s in ET.fromstring(book.read('xl/sharedStrings.xml'))]
        rows = ET.fromstring(book.read('xl/worksheets/sheet1.xml')).findall('.//'+NS+'row')
    def value(cell):
        text = cell.findtext(NS+'v')
        return strings[int(text)] if cell.get('t')=='s' else text
    if [value(c) for c in rows[0][1:]] != [f'P{i}' for i in range(1,3001)]:
        raise ValueError('Unexpected packet index in workbook')
    result = {}
    for row in rows[1:]:
        label = value(row[0])
        m = re.fullmatch(r'Mote\s*(\d+)', label or '', flags=re.I)
        if m:
            mote = int(m[1])
            cells = [value(c) for c in row[1:]]
            if mote in result or len(cells)!=3000 or set(cells)-{'0','1'}:
                raise ValueError('Invalid or repeated mote row')
            result[mote] = {i for i,b in enumerate(cells,1) if b=='1'}
    if sorted(result)!=list(MOTES):
        raise ValueError('Incomplete mote coverage')
    return result


def plot_ids(source):
    vectors = {}
    for label, body in re.findall(rb'(?m)^x(\d+)\s*=\s*\[([^\]]*)\]', source):
        values = [int(s) for s in body.split()]
        mote = int(label)
        if mote in vectors or len(set(values))!=len(values) or not set(values)<=IDS:
            raise ValueError('Invalid plotting vector')
        vectors[mote] = set(values)
    if sorted(vectors)!=list(MOTES):
        raise ValueError('Missing plotting vectors')
    return vectors


def consecutive_missing(ids):
    return max((sum(1 for _ in block) for missed,block in itertools.groupby(
        (i not in ids for i in range(1,3001))) if missed), default=0)


def write(path, rows):
    with path.open('w',newline='',encoding='utf-8') as file:
        w=csv.DictWriter(file,fieldnames=rows[0],lineterminator='\n')
        w.writeheader()
        w.writerows(rows)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive',type=Path)
    parser.add_argument('output',type=Path)
    args=parser.parse_args()
    if hashlib.sha256(args.archive.read_bytes()).hexdigest()!='e0fa6b398284fb8cf75ccf86f7aaf28aa7a79273ef99f6b5c39223e8fb3a7a1f':
        raise ValueError('Unexpected v2 input archive')
    links,sessions=[],[]
    def normalized(name):
        return re.sub(r'[- ]','',Path(name).stem).lower()
    with ZipFile(args.archive) as z:
        scripts={normalized(n):n for n in z.namelist() if n.endswith('.m')}
        for name in sorted(n for n in z.namelist() if n.endswith('.xlsx')):
            script=scripts[normalized(name)]
            a,b=bits(z.read(name)),plot_ids(z.read(script))
            common=dict(experiment=Path(name).stem,grid_setting=Path(name).parent.name)
            for m in MOTES:
                lower=a[m]&b[m]
                upper=a[m]|b[m]
                links.append(dict(**common,mote=m,transmitted=3000,received_workbook=len(a[m]),
                                  received_plot=len(b[m]),agreed_receptions=len(lower),
                                  agreed_losses=3000-len(upper),unresolved=len(upper-lower),
                                  longest_agreed_loss_streak_packets=consecutive_missing(upper),
                                  longest_possible_loss_streak_packets=consecutive_missing(lower)))
            all_min = set.intersection(*(a[m]&b[m] for m in MOTES))
            all_max = set.intersection(*(a[m]|b[m] for m in MOTES))
            any_min = set.union(*(a[m]&b[m] for m in MOTES))
            any_max = set.union(*(a[m]|b[m] for m in MOTES))
            sessions.append(dict(**common,workbook=name,plot_script=script,
                                 workbook_sha256=hashlib.sha256(z.read(name)).hexdigest(),
                                 plot_sha256=hashlib.sha256(z.read(script)).hexdigest(),
                                 broadcast_packet_ids=3000,receiver_opportunities=45000,
                                 receiver_cells_disagree=sum(len(a[m]^b[m]) for m in MOTES),
                                 received_by_all15_min=len(all_min),received_by_all15_max=len(all_max),
                                 received_by_no_mote_min=3000-len(any_max),
                                 received_by_no_mote_max=3000-len(any_min)))
    args.output.mkdir(parents=True,exist_ok=True)
    write(args.output/'multicast-receivers.csv',links)
    write(args.output/'multicast-broadcasts.csv',sessions)


if __name__=='__main__':
    main()
