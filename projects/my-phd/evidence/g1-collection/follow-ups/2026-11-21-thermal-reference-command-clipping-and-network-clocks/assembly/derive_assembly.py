"""Recreate small factual derivatives. Dependencies: lxml, numpy, PyMuPDF."""
import argparse
import csv
import hashlib
import statistics
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

import fitz
import numpy as np
from lxml import html


def verified(path, expected):
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != expected:
        raise ValueError(f'{path}: source checksum mismatch')


def emit(destination, name, headings, rows):
    with (destination / name).open('w', newline='', encoding='utf-8') as file:
        writer = csv.writer(file, lineterminator='\n')
        writer.writerow(headings)
        writer.writerows(rows)


def table_rows(path):
    doc = html.fromstring(path.read_text(encoding='utf-8'))
    return [[cell.text_content().strip() for cell in row.xpath('./th|./td')]
            for row in doc.xpath('//table//tr')]


def summarize_tolerances(source, rendered, output):
    verified(source, '02ceb901306b1ef7f993e6fa47a24be97a9bbc19b7463e1c40380e9cac37c7d5')
    rows = table_rows(source)
    if rendered and rows != table_rows(rendered):
        raise ValueError('Frozen author table and supplied rendered table differ')
    if len(rows) != 71 or any(len(row) != 8 for row in rows):
        raise ValueError('Unexpected author table shape')
    classes = defaultdict(list)
    parts = defaultdict(list)
    for expected, (index, _, cls, brand, part, pins, z, x) in enumerate(rows[1:], 1):
        assert int(index) == expected
        classes[cls].append((float(z), float(x)))
        parts[part].append((index, cls, brand, pins))
    def summarize(key, values):
        zs, xs = zip(*values)
        return [key,len(zs),min(zs),statistics.median(zs),max(zs),min(xs),
                statistics.median(xs),max(xs),round(max(abs(a-b) for a,b in values),3)]
    summary = [summarize('all',sum(classes.values(),[]))]
    summary.extend(summarize(k,v) for k,v in classes.items())
    emit(output,'yumbla-tolerance-summary.csv',
         ['author_class','source_rows','z_min_mm','z_median_mm','z_max_mm',
          'x_min_mm','x_median_mm','x_max_mm','max_abs_z_minus_x_mm'],summary)
    emit(output,'yumbla-repeated-part-codes.csv',
         ['verbatim_part_string','source_row_count','source_row_ids','classes','brands','pin_counts'],
         [[part,len(v),*('|'.join(g) for g in zip(*v))]
          for part,v in parts.items() if len(v)>1])


def calibrated_vertices(paths, path_index, grid_start, x_ticks, y_ticks):
    # Tick positions come from vector grid lines; labels are read from the paper.
    grids = [p['rect'] for p in paths[grid_start:path_index] if p['color']
             and all(.65 < c < .75 for c in p['color'])]
    xs = sorted(r.x0 for r in grids if r.width < .01 and r.height > 40)
    ys = sorted(r.y0 for r in grids if r.height < .01 and r.width > 100)
    assert len(xs) == len(x_ticks) and len(ys) == len(y_ticks)
    fx = np.polynomial.Polynomial.fit(xs,x_ticks,1)
    fy = np.polynomial.Polynomial.fit(ys,y_ticks,1)
    assert max(abs(fx(xs)-x_ticks)) < .003 and max(abs(fy(ys)-y_ticks)) < .003
    points = set()
    for kind,a,b in paths[path_index]['items']:
        assert kind == 'l'
        points.update(((a.x,a.y),(b.x,b.y)))
    xy = np.asarray(sorted(points))
    times, values = fx(xy[:,0]), fy(xy[:,1])
    assert -.001 < times.min() < .001 and 81 < times.max() < 82
    return np.maximum(times,0),values


def summarize_plots(source, output):
    verified(source,'e8d9dc6a7949eed9127bc858db0f23275137871fb13c7df3b6b0c3d1dc25c78e')
    with fitz.open(source) as doc:
        paths = doc[9].get_drawings()
    panels = [(14,29,3,range(0,81,10),[40,20,0,-20],'joint_18_plotted_actuator_torque','Nm'),
              (15,249,223,range(0,81,10),[40,20,0,-20],'joint_18_plotted_actuator_torque','Nm'),
              (16,409,379,range(10,81,10),range(120,-1,-20),'wrist_force_L2_norm','N')]
    seconds, windows = [], []
    for fig,idx,start,xt,yt,channel,unit in panels:
        ts,vs = calibrated_vertices(paths,idx,start,xt,yt)
        for dest, intervals in ((seconds,[(i,i+1) for i in range(82)]),
                                (windows,[(0,60),(60,82),(60,67),(67,75),(75,82)])):
            for lo,hi in intervals:
                mask = (ts >= lo) & (ts < hi)
                values,times = vs[mask],ts[mask]
                if not len(values):
                    dest.append([fig,channel,unit,lo,hi]+[""]*4)
                    continue
                imin,imax = int(values.argmin()),int(values.argmax())
                dest.append([fig,channel,unit,lo,hi,round(values[imin],2),round(values[imax],2),
                             round(times[imin],3),round(times[imax],3)])
    headings = ['figure','channel','unit','start_s_inclusive','end_s_exclusive',
                'min_plotted_vertex','max_plotted_vertex','time_at_min_s','time_at_max_s']
    emit(output,'bargsten-plotted-1s.csv',headings,seconds)
    emit(output,'bargsten-plotted-windows.csv',headings,windows)


def archive_inventory(source, output):
    verified(source,'4f1ecfa00cfc6de16d1ab093b6bfd6f859c9adc0faea4bf9ad33c23a953910a2')
    rows = []
    with zipfile.ZipFile(source) as archive:
        assert archive.testzip() is None
        for member in archive.infolist():
            if member.is_dir():
                continue
            name = member.filename
            ext = Path(name).suffix
            kind = {'.py':'implementation','.pth':'checkpoint','.pkl':'checkpoint',
                    '.rtf':'readme'}[ext]
            rows.append([name,kind,member.file_size,format(member.CRC,'08x')])
        pred = next(n for n in archive.namelist() if 'source_code_tactile/predict.py' in n)
        content = archive.read(pred).decode('utf-8')
        assert all(f'path_here_to_your_{act}_data.txt' in content for act in ('push','pull'))
    assert Counter(row[1] for row in rows) == {'implementation':9,'checkpoint':4,'readme':1}
    emit(output,'intelliman-archive-inventory.csv',['zip_member','kind','bytes','zip_crc32'],rows)


if __name__ == '__main__':
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument('--tolerances', required=True, type=Path)
    args.add_argument('--rendered-table', type=Path)
    args.add_argument('--paper', required=True, type=Path)
    args.add_argument('--intelliman', required=True, type=Path)
    args.add_argument('--output', required=True, type=Path)
    opt = args.parse_args()
    opt.output.mkdir(parents=True,exist_ok=True)
    summarize_tolerances(opt.tolerances,opt.rendered_table,opt.output)
    summarize_plots(opt.paper,opt.output)
    archive_inventory(opt.intelliman,opt.output)
