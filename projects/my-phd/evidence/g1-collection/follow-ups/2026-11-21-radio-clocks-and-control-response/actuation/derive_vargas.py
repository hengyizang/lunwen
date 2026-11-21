"""Read the 22 printed latency labels in Vargas Cruz (2025), Fig. 5.7.

Usage: python derive_vargas.py THESIS_PDF OUTPUT_DIR
Requires Poppler pdfimages, tesseract, Pillow, NumPy. No trial video or bag is needed.
"""
import argparse
import csv
import hashlib
import itertools
from pathlib import Path
import re
import subprocess
import tempfile

import numpy as np
from PIL import Image, ImageOps


def read_graph(pdf):
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        subprocess.run(["pdfimages","-f","47","-l","47","-png",str(pdf),str(tmp/"fig")],check=True)
        with Image.open(tmp/"fig-002.png") as im:
            if im.size != (5367,1770) or im.mode != "RGB":
                raise ValueError("Expected the Fig. 5.7 panel of the fixed publication")
            pixels = np.asarray(im, dtype=np.int16)
        scan = pixels[60]
        selected = np.flatnonzero((scan[:,1]>scan[:,0]+15) & (scan[:,1]>scan[:,2]+15))
        bands = []
        for _, group in itertools.groupby(enumerate(selected), lambda i:i[0]-i[1]):
            ix = [int(p[1]) for p in group]
            if len(ix)>1:
                bands.append((ix[0]+ix[-1])//2)
        if len(bands)!=22:
            raise ValueError("Expected 22 annotated command onsets")
        canvas = Image.new("L",(260,90*len(bands)),255)
        for i,x in enumerate(bands):
            region = pixels[55:243,x-98:x+98]
            labels = np.where(np.max(region,axis=2)<100,0,255).astype("uint8")
            upright = Image.fromarray(labels).rotate(-45,expand=True,fillcolor=255)
            label = upright.crop(ImageOps.invert(upright).getbbox())
            label.thumbnail((225,73))
            canvas.paste(label,(12,90*i+10))
        canvas.save(tmp/"labels.png")
        ocr = subprocess.check_output(["tesseract",str(tmp/"labels.png"),"stdout","--psm","6"],
                                      stderr=subprocess.DEVNULL,text=True)
        values = [int(re.match(r"^\s*(\d+)",line)[1]) for line in ocr.splitlines() if line.strip()]
    # Visual readback from the publisher's annotated graph; never substitute text on a disagreement.
    checked = [30,32,57,36,47,88,62,62,49,58,50,74,72,50,26,56,62,37,59,70,79,28]
    if values!=checked:
        raise ValueError("OCR differed from independently inspected annotations")
    return values


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf",type=Path)
    parser.add_argument("output",type=Path)
    args=parser.parse_args()
    if hashlib.sha256(args.pdf.read_bytes()).hexdigest()!=PDF_SHA:
        raise ValueError("PDF differs from the reviewed thesis")
    values=read_graph(args.pdf)
    args.output.mkdir(exist_ok=True,parents=True)
    with (args.output/"vargas-ros-figure.csv").open("w",encoding="utf-8",newline="") as out:
        writer=csv.writer(out,lineterminator="\n")
        writer.writerow(["figure_order","published_cmd_vel_to_first_odom_change_ms"])
        writer.writerows(enumerate(values,start=1))


PDF_SHA = "17b1bc86fe753081550af78b8a8c95a4d08f6cba08e3146acefc8cce9907f6e0"
if __name__=="__main__":
    main()
