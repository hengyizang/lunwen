"""Derive paired contrasts from two published IMEKO tables, using Python 3 and Poppler.

Usage: python derive_printed_calibrations.py 2017-022.pdf 2010-042.pdf output_directory
The original PDFs are linked and SHA-256-pinned in literature.csv.
"""
import argparse
import csv
import hashlib
import re
import subprocess
from decimal import Decimal
from pathlib import Path

TORQUE_SHA = '0cc2130206343b7d8f61a045dcba706cfe5b0737d62f986efbf50772b96e1cfa'
FORCE_SHA = '61a1535c85b37134727c601822c8d91e55028d07ccd0e42374af5a9d86098037'


def extract(path, checksum, layout):
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != checksum:
        raise ValueError(f"Unexpected source SHA-256 for {path}: {digest}")
    return subprocess.check_output(['pdftotext', layout, str(path), '-'], encoding='utf-8')


def torque_contrasts(source):
    cases = [
        ('Table 1: Effect of temperature on the creep', '4. EFFECT OF RELATIVE HUMIDITY',
         'temperature_C', '22,40,22', '50% RH', 'Table 1'),
        ('Table 2: Effect of humidity on the creep', '5. CONCLUSIONS',
         'relative_humidity_percent', '50,70,50', '22 deg C', 'Table 2'),
    ]
    rows = []
    for start, end, variable, levels, fixed_condition, locator in cases:
        content = source.split(start, 1)[1].split(end, 1)[0]
        instrument = phase = None
        for line in content.splitlines():
            line = line.strip()
            instrument_match = re.fullmatch(r'\((TT1#[\d-]+|T34-R40#[\d-]+)\)', line)
            if instrument_match:
                instrument = instrument_match.group(1)
            elif line == 'Creep':
                phase = 'loaded_creep'
            elif line == 'recovery':
                phase = 'unloaded_recovery'
            else:
                result = re.fullmatch(r'(3|30) min ([-.\d]+) ([-.\d]+) ([-.\d]+)', line)
                if result:
                    if not (instrument and phase):
                        raise ValueError('Missing torque table labels')
                    duration, first, excursion, final = result.groups()
                    rows.append(dict(source_id='IMEKO-TC3-2017-022', locator=locator,
                                     instrument=instrument, phase=phase, minutes=duration,
                                     variable=variable, cycle_levels=levels, fixed_condition=fixed_condition,
                                     excursion_minus_initial_mV_per_V=f'{Decimal(excursion) - Decimal(first):.6f}',
                                     returned_minus_initial_mV_per_V=f'{Decimal(final) - Decimal(first):.6f}'))
    keys = {(r['locator'], r['instrument'], r['phase'], r['minutes']) for r in rows}
    if len(rows) != 16 or len(keys) != 16:
        raise ValueError(f'Expected 16 unique torque contrasts. Got {len(rows)} / {len(keys)}')
    return rows


def force_contrasts(source):
    content = source.split('Table 1: Creep measurements', 1)[1].split('For the majority', 1)[0]
    rows = []
    for line in content.splitlines():
        result = re.match(r'^\s*([ABC])-\s*(\d+)\s*(kN|N)\s+([.\d]+)\s+([.\d]+)\s+([.\d]+)\b', line)
        if result:
            letter, capacity, unit, direct, partial, full = result.groups()
            d, p, f = map(Decimal, (direct, partial, full))
            rows.append(dict(source_id='IMEKO-TC3-2010-042', locator='Table 1',
                             instrument_group=letter, capacity=capacity, capacity_unit=unit,
                             creep_interval_s='30-300', direct_minus_some_steps_mV_per_V=f'{d-p:.6f}',
                             direct_minus_full_steps_mV_per_V=f'{d-f:.6f}',
                             direct_strictly_largest=str(d > p and d > f).lower()))
    keys = {(r['instrument_group'], r['capacity'], r['capacity_unit']) for r in rows}
    if len(rows) != 7 or len(keys) != 7:
        raise ValueError(f'Expected 7 unique force contrasts. Got {len(rows)} / {len(keys)}')
    return rows


def save_csv(path, rows):
    with path.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, rows[0].keys(), lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('torque_pdf', type=Path)
    parser.add_argument('force_pdf', type=Path)
    parser.add_argument('output_directory', type=Path)
    args = parser.parse_args()
    torque = torque_contrasts(extract(args.torque_pdf, TORQUE_SHA, '-raw'))
    force = force_contrasts(extract(args.force_pdf, FORCE_SHA, '-layout'))
    args.output_directory.mkdir(parents=True, exist_ok=True)
    save_csv(args.output_directory / 'environment-contrasts.csv', torque)
    save_csv(args.output_directory / 'loading-sequence-contrasts.csv', force)
