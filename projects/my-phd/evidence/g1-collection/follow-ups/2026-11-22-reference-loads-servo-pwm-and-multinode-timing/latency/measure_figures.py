"""Verify published figures and an annotated same-camera video; see README.md.
Python 3.10+, PyMuPDF, Pillow, NumPy, ffmpeg, ffprobe. Outputs are summaries of public graphics.
"""
import argparse
import csv
import io
import json
import subprocess
import tempfile
from fractions import Fraction
from pathlib import Path

import numpy as np
import pymupdf
from PIL import Image

from measure import HERE, read_input, save


def alignment(a, b, lo, hi, max_lag):
    # Same input interval for every lag. Pair positive lags with a later output.
    frame = np.arange(lo + max_lag, hi - max_lag)
    scores = []
    for lag in range(-max_lag, max_lag + 1):
        x, y = a[frame], b[frame + lag]
        mask = np.isfinite(x) & np.isfinite(y)
        scores.append((np.corrcoef(x[mask], y[mask])[0, 1], lag, int(mask.sum())))
    return max(scores)


def duarte(data):
    doc = pymupdf.open(stream=data, filetype="pdf")
    ref = doc[5].get_images()[0][0]
    image = np.asarray(Image.open(io.BytesIO(doc.extract_image(ref)["image"])).convert("RGB")).astype(int)
    assert image.shape[:2] == (625, 790)
    # Calibration from labelled 75 s and 80 s ticks at x=87,766. Crop the legend.
    for threshold in (16, 40, 75):
        series = []
        for color in ([0, 114, 189], [217, 83, 25]):
            dist = np.max(np.abs(image - color), axis=2)
            trace = []
            for x in range(91, 764):
                top = 106 if x < 255 else 65
                ys = np.flatnonzero(dist[top:533, x] <= threshold) + top
                trace.append(np.median(ys) if len(ys) else np.nan)
            series.append(np.array(trace))
        for lo, hi in [(0, 673), (100, 560), (200, 600)]:
            r, lag, pairs = alignment(*series, lo, hi, 32)
            yield ["Duarte_Fig4", "published pixel columns", threshold, lo + 91, hi + 91,
                   lag, round(5000 * lag / 679, 3), round(float(r), 5), pairs]


def kroep(data):
    doc = pymupdf.open(stream=data, filetype="pdf")
    # Page index can change if the repository cover changes.
    page = next(p for p in doc if "Glass-to-Glass Latency" in p.get_text() and "CDFs of latency" in p.get_text())
    curves = [d for d in page.get_drawings() if len(d["items"]) == 99 and d["color"] and max(d["color"]) - min(d["color"]) > 0.2]
    assert len(curves) == 3
    # Grey vertical gridlines run from 0 to 14 ms in 2-ms increments.
    grid = sorted({d["rect"].x0 for d in page.get_drawings()
                   if d["color"] and 0.68 < d["color"][0] < 0.71
                   and d["rect"].width < 0.001 and d["rect"].height > 70})
    assert len(grid) == 8
    for drawing in curves:
        c = np.array(drawing["color"])
        label = ["robot_object_interaction", "predictive_force_feedback", "model_update_feedback"][int(c.argmax())]
        seg = drawing["items"]
        points = [seg[0][1]] + [piece[2] for piece in seg]
        v = np.array([(p.x - grid[0]) * 14 / (grid[-1] - grid[0]) for p in points])
        assert np.all(np.diff(v) > -0.001) and len(v) == 100
        yield [label, len(v), *[round(float(v[i]), 3) for i in [0, 49, 89, 94, 98, 99]], round(float(v.mean()), 3)]


def wave(data):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "wave.mp4"
        path.write_bytes(data)
        probe = subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=r_frame_rate,avg_frame_rate,nb_frames", "-of", "json", str(path)])
        stream = json.loads(probe)["streams"][0]
        assert stream["avg_frame_rate"] == stream["r_frame_rate"] == "30000/1001" and int(stream["nb_frames"]) == 359
        hz = float(Fraction(stream["r_frame_rate"]))
        cmd = ["ffmpeg", "-loglevel", "error", "-threads", "1", "-i", str(path), "-vf",
               r"select=between(n\,100\,245),scale=760:428", "-fps_mode", "passthrough",
               "-an", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"]
        samples = {i: [] for i in range(3)}
        size = 760 * 428 * 3
        with subprocess.Popen(cmd, stdout=subprocess.PIPE) as proc:
            while True:
                raw = proc.stdout.read(size)
                if not raw:
                    break
                assert len(raw) == size
                frame = np.frombuffer(raw, dtype=np.uint8).reshape(428, 760, 3)
                for i, pairs in samples.items():
                    points = []
                    for role, (x, y, w, h) in enumerate([(55, 62, 146, 168), (276, 125, 104, 146)]):
                        r, g, b = frame[y:y+h, x:x+w].astype(int).transpose(2, 0, 1)
                        if role == 0:
                            mask = (b - g > 20 + i * 5) & (b - r > 6) & (r - g > 3)
                        else:
                            mask = (r - b > 32 + i * 10) & (r - g > 10) & (g - b > 6)
                        ys = np.flatnonzero(mask) // w
                        points.append(np.median(ys) if len(ys) >= 40 else np.nan)
                    pairs.append(points)
            if proc.wait():
                raise RuntimeError("ffmpeg decode failed")
        for threshold, pairs in samples.items():
            a, b = np.array(pairs).T
            assert len(a) == 146
            r, lag, count = alignment(a, b, 0, len(a), 10)
            # Embedded caption 0.5x: each presentation second corresponds to 0.5 physical second.
            yield ["ExtremControl_overlay", "decoded presentation frames; 0.5x", threshold, 100, 246,
                   lag, round(500 * lag / hz, 3), round(float(r), 5), count]


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument("--cache", type=Path)
    p.add_argument("--output", type=Path, default=HERE)
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    with (HERE / "file-manifest.csv").open() as f:
        files = {r["group"]: r for r in csv.DictReader(f)}
    lags = list(duarte(read_input(files["duarte"], args.cache)))
    lags.extend(wave(read_input(files["wave"], args.cache)))
    save(args.output / "graph-video-lags.csv", ["source", "sample_unit", "color_threshold_or_profile", "region_start_inclusive", "region_end_exclusive", "peak_lag_units", "approx_physical_lag_ms", "peak_pearson_r", "valid_pairs_at_peak"], lags)
    save(args.output / "haptic-loop-cdf.csv", ["figure6_curve", "plotted_cdf_vertices", "p1_ms", "p50_ms", "p90_ms", "p95_ms", "p99_ms", "p100_ms", "mean_plotted_vertices_ms"], kroep(read_input(files["kroep"], args.cache)))


if __name__ == "__main__":
    main()
