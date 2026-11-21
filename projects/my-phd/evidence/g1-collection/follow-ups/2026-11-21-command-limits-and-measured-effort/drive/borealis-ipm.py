"""Read the Borealis V1.0 original workbook and derive command/feedback statistics.
Usage: python borealis-ipm.py RAW_DIR OUTPUT_DIR (numpy and openpyxl).
"""
import csv
import hashlib
import sys
from pathlib import Path

import numpy as np
import openpyxl

raw, out = map(Path, sys.argv[1:])
out.mkdir(parents=True, exist_ok=True)
workbook = raw / 'IPM 2-in-1 Characterization.xlsx'
assert hashlib.sha256(workbook.read_bytes()).hexdigest() == 'aea6dad2c439514c282f1c5a4c526ba8c6d39b14379a573184ab7d6d75bcc308'
wb = openpyxl.load_workbook(workbook, read_only=True, data_only=True)
channels = ['D2_Motor_Speed', 'D2_Torque_Feedback', 'D3_Id_Command',
            'D4_Iq_Command', 'D3_Id', 'D4_Iq', 'tqDyno1Total']
sets = {}
for sheet, header_row in [('FluxMap Test', 120), ('Loss Test', 140)]:
    rows = iter(wb[sheet].values)
    for _ in range(header_row):
        header = next(rows)
    units = next(rows)
    ix = [header.index(c) for c in channels]
    sets[sheet] = np.array([[row[i] for i in ix] for row in rows
                            if isinstance(row[header.index('D2_Torque_Feedback')], (int, float))],
                           dtype=float)
    assert np.isfinite(sets[sheet]).all()
assert [len(a) for a in sets.values()] == [142, 136]

def features(data, interaction):
    iq, id_ = data[:, 5], data[:, 4]
    parts = [np.ones_like(iq), iq]
    if interaction:
        parts.append(iq * id_)
    return np.column_stack(parts)

def rmse(x):
    return np.sqrt(np.mean(np.square(x)))

fields = ['sheet', 'rpm_group', 'n', 'speed_min_rpm', 'speed_max_rpm',
          'feedback_torque_min_Nm', 'feedback_torque_max_Nm', 'signed_Id_err_mean_Apk',
          'signed_Iq_err_mean_Apk', 'dq_vector_err_rms_Apk', 'dq_vector_err_p95_Apk',
          'dq_vector_err_max_Apk', 'iq_model_feedback_rmse_Nm', 'iq_interaction_model_feedback_rmse_Nm',
          'iq_model_tqDyno1Total_rmse_Nm', 'iq_interaction_model_tqDyno1Total_rmse_Nm']
training = sets['FluxMap Test']
models = [(mult, output, np.linalg.lstsq(features(training, mult), training[:, output], rcond=None)[0])
          for output in (1, 6) for mult in (False, True)]
with (out / 'borealis-ipm-tracking.csv').open('w', newline='') as f:
    writer = csv.writer(f, lineterminator='\n')
    writer.writerow(fields)
    for sheet, records in sets.items():
        # Only the Loss Test mixes widely different speeds. Group by nearest 100 rpm.
        groups = [('all', records)]
        if sheet == 'Loss Test':
            rpm = 100 * np.rint(records[:, 0] / 100)
            groups.extend((str(int(speed)), records[rpm == speed]) for speed in np.unique(rpm))
        for key, a in groups:
            err = a[:, 4:6] - a[:, 2:4]
            norms = np.linalg.norm(err, axis=1)
            stats = [a[:, 0].min(), a[:, 0].max(), a[:, 1].min(), a[:, 1].max(),
                     *err.mean(axis=0), rmse(norms), np.percentile(norms, 95), norms.max(),
                     *(rmse(features(a, mult) @ coef - a[:, output])
                       for mult, output, coef in models)]
            writer.writerow([sheet, key, len(a), *[f'{v:.6f}' for v in stats]])
