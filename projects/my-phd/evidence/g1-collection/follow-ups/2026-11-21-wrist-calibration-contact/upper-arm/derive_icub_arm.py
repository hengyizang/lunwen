"""Compute recorded joint/wrench coverage in the original iCubDyn MAT release."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.io import loadmat


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source_mat', type=Path)
    parser.add_argument('output_csv', type=Path)
    args = parser.parse_args()
    manifest_file = Path(__file__).with_name('temperature-and-arm-sources.json')
    manifest = json.loads(manifest_file.read_text(encoding='utf-8'))
    expected = manifest['arm_dataset']['files']['iCubDyn_2.0.mat']
    content = args.source_mat.read_bytes()
    if len(content) != expected['size'] or hashlib.sha256(content).hexdigest() != expected['sha256']:
        raise ValueError('Input size or SHA-256 differs from the inspected release')
    matrices = {k: v for k, v in loadmat(args.source_mat).items() if not k.startswith('__')}
    if set(matrices) != {'Xtr', 'Xte', 'Ytr', 'Yte'}:
        raise ValueError('Unexpected MAT variables')

    results = []
    for suffix, name in [('tr', 'train'), ('te', 'test')]:
        x = matrices['X' + suffix]
        y = matrices['Y' + suffix]
        if x.shape != (10000, 12) or y.shape != (10000, 6):
            raise ValueError('Unexpected matrix dimensions')
        if not np.isfinite(x).all() or not np.isfinite(y).all():
            raise ValueError('Non-finite measurements')
        repeats = np.all(x[1:] == x[:-1], axis=1)
        for column, axis in enumerate(['Fx', 'Fy', 'Fz', 'Mx', 'My', 'Mz']):
            values = y[:, column]
            results.append({
                'split': name, 'input_key': 'X' + suffix, 'measured_output_key': 'Y' + suffix,
                'output_channel': axis, 'unit': 'N' if column < 3 else 'N m',
                'paired_rows': x.shape[0], 'input_columns': x.shape[1],
                'adjacent_identical_full_input_pairs': int(repeats.sum()),
                'min': format(values.min(), '.10g'), 'median': format(np.median(values), '.10g'),
                'max': format(values.max(), '.10g')
            })
    with args.output_csv.open('w', encoding='utf-8', newline='') as stream:
        w = csv.DictWriter(stream, fieldnames=results[0], lineterminator='\n')
        w.writeheader()
        w.writerows(results)


if __name__ == '__main__':
    main()
