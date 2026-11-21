"""Rebuild figure-level tables from the three publisher files in the manifest."""
import argparse
import csv
import io
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile

import fitz
import numpy as np
from PIL import Image


def write(path, fields, rows):
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.writer(output, lineterminator="\n")
        writer.writerow(fields)
        writer.writerows(rows)


def mao(workbook, target):
    ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(workbook) as book:
        sheets = ET.fromstring(book.read("xl/workbook.xml")).findall("s:sheets/s:sheet", ns)
        assert sheets[14].get("name") == "Figure 3j"
        sheet = ET.fromstring(book.read("xl/worksheets/sheet15.xml"))
        rows = []
        for record in sheet.findall("s:sheetData/s:row", ns)[1:]:
            values = [float(cell.findtext("s:v", namespaces=ns)) for cell in record]
            rows.append([int(values[0]), format(values[1], ".8g"), format(values[2], ".8g"), 5])
    assert len(rows) == 5
    write(target / "mao-figure-3j.csv", ["temperature_C", "Fz_mean_N", "Fz_SD_N", "repeats_one_sensor"], rows)


def paulsen(pdf, target):
    with fitz.open(pdf) as document:
        paths = [p for p in document[1].get_drawings() if len(p["items"]) > 100]
    assert len(paths) == 4
    rows = []
    # Fig S1 tick locations in points measured in the unmodified PDF.
    baseline_y, y_at_20 = 342.9335632324219, 141.80789184570312
    jun7_x, jun9_x = 159.75172424316406, 277.4326477050781
    for path in paths:
        red = round(path["color"][0], 2)
        name, unit = {0.15: ("LC3_blue", "g"), 0.07: ("LC2_green", "g"),
                      0.57: ("LC1_brown", "g"), 0.93: ("air_red", "degC")}[red]
        segments = path["items"]
        assert all(item[0] == "l" for item in segments)
        points = [segments[0][1]] + [item[2] for item in segments]
        values = [(baseline_y - p.y) * 20 / (baseline_y - y_at_20) for p in points]
        hours = (points[-1].x - points[0].x) * 48 / (jun9_x - jun7_x)
        rows.append([name, unit, len(points), round(hours, 1), round(min(values), 2), round(max(values), 2)])
    write(target / "paulsen-figure-s1.csv",
          ["plotted_trace_legend", "unit", "polyline_vertices", "visible_trace_span_h", "min_approx", "max_approx"], rows)


def gallo(pdf, target):
    with fitz.open(pdf) as document:
        images = document[13].get_images()
        xref, = [i[0] for i in images if (i[2], i[3]) == (1525, 992)]
        source = document.extract_image(xref)["image"]
    image = Image.open(io.BytesIO(source)).convert("RGB")
    image.thumbnail((900, 900), Image.Resampling.BICUBIC)
    assert image.size == (900, 585)
    pixels = np.asarray(image, dtype=np.int16)
    red, green, blue = pixels[:, :, 0], pixels[:, :, 1], pixels[:, :, 2]
    y, x = np.indices(red.shape)
    load_temperature = (green > red + 45) & (green > blue + 45) & (y > 110) & (y < 173)
    thrust_line = (pixels.max(axis=2) < 80) & (y > 277) & (y < 491)
    # Labels measured in the fixed raster. Crop frame; gray grid cannot enter either mask.
    t = (x - 136.5) * 10 / (878.5 - 136.5)
    temperature = 24 + (172.5 - y) * 2 / (172.5 - 60)
    thrust = 9.3 + (496.0 - y) * .2 / (496.0 - 273)
    rows = []
    for left in range(10):
        time_bin = (t >= left) & (t < left + 1) & (x > 138) & (x < 877)
        temp = temperature[time_bin & load_temperature]
        output = thrust[time_bin & thrust_line]
        assert len(temp) > 50 and len(output) > 50
        rows.append([left, left + 1, f"{np.median(temp):.2f}", f"{output.min():.2f}", f"{output.max():.2f}"])
    write(target / "gallo-figure-a2-bins.csv",
          ["plot_window_start_s", "plot_window_end_s", "loadcell_trace_median_C_approx",
           "thrust_trace_min_N_approx", "thrust_trace_max_N_approx"], rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("mao_workbook", "paulsen_supplement", "gallo_article", "output_dir"):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    args.output_dir.mkdir(exist_ok=True, parents=True)
    mao(args.mao_workbook, args.output_dir)
    paulsen(args.paulsen_supplement, args.output_dir)
    gallo(args.gallo_article, args.output_dir)
