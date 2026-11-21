"""Read the public Figure 3b raster and a calibration point cloud. Requires numpy and Pillow."""
import argparse
import csv
import hashlib
import io
import tarfile
from pathlib import Path
from urllib.request import urlopen

import numpy as np
from PIL import Image

REV = "d03259df66df97bba0e00e54c121a59dfc7d5881"
ARCHIVE = "https://arxiv.org/src/2309.16057v1"
PCD = f"https://raw.githubusercontent.com/unmannedlab/UWB_Dataset/{REV}/lidar2camera/manual_calib/data/0001.pcd"
FIGURE_SHA = "6938ba442e239544f302a03512f05e90860aa8c52dabff73f2b98520234769f8"


def read_or_fetch(file, url):
    if not file.exists():
        with urlopen(url, timeout=120) as response:
            file.write_bytes(response.read())
    return file.read_bytes()


def write(path, rows):
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, rows[0].keys(), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("output", type=Path)
    ap.add_argument("cache", type=Path)
    args = ap.parse_args()
    args.cache.mkdir(exist_ok=True, parents=True)
    args.output.mkdir(exist_ok=True, parents=True)
    read_or_fetch(args.cache / "source.tar", ARCHIVE)
    with tarfile.open(args.cache / "source.tar") as t:
        fig = t.extractfile("Images/lidar_uwb.png").read()
    assert hashlib.sha256(fig).hexdigest() == FIGURE_SHA
    img = np.array(Image.open(io.BytesIO(fig)).convert("RGB"))
    assert img.shape == (379, 613, 3)
    # Calibrate against the six x gridlines (0…10 s) and five y gridlines (0.2…1).
    to_t = np.polyfit([96, 183, 270, 358, 445, 533], [0, 2, 4, 6, 8, 10], 1)
    to_r = np.polyfit([293, 235, 176, 118, 59], [.2, .4, .6, .8, 1], 1)
    rows = []
    for instrument, rgb in [("UWB", (255, 165, 0)), ("LiDAR", (0, 191, 255))]:
        keep = (img == rgb).all(axis=2)
        keep[:110, :245] = False  # exclude legend samples
        yy, xx = np.nonzero(keep)
        for second in range(1, 10):
            # Nearest pure-colored column to each integer second; allow instruments to differ.
            x = int(xx[np.argmin(np.abs(np.polyval(to_t, xx) - second))])
            y = float(np.median(yy[xx == x]))
            rows.append(dict(series=instrument, target_time_s=second, readout_column_px=x,
                             median_row_px=y, approximate_trace_time_s=round(float(np.polyval(to_t, x)), 3),
                             approximate_normalized_distance=round(float(np.polyval(to_r, y)), 3)))
    write(args.output / "figure3b-readouts.csv", rows)
    pcd = read_or_fetch(args.cache / "sample.pcd", PCD)
    # Compare with the pinned tree object for the original acquisition example.
    digest = hashlib.sha1(f"blob {len(pcd)}\0".encode() + pcd).hexdigest()
    assert digest == "c1beddf0044a1af205a70b957dea63fd2d135300"
    header, raw = pcd.split(b"DATA ascii\n", 1)
    assert b"FIELDS x y z\n" in header
    points = np.loadtxt(io.BytesIO(raw))
    assert points.shape == (49965, 3) and np.isfinite(points).all()
    norm = np.linalg.norm(points, axis=1)
    print("xyz points, median and maximum norm in native coordinates:", len(norm), np.median(norm), norm.max())


if __name__ == "__main__":
    main()
