"""Verify the publisher's small Git LFS pointers. Run python verify-mcc-pointers.py OUT.
This checks remote pointer metadata and does not download the archive payloads.
"""
import csv
from pathlib import Path
import sys
from urllib.parse import quote
from urllib.request import urlopen

BASE = 'https://huggingface.co/datasets/Samlzy/MCC5-THU-Motor/raw/897bc5d2504980418249f98e733bfd7f61056186/'
EXPECTED = [
    ('MCC5-THU Motor_speed_circulation.zip', 6202740516, 'b82afc81667b4c08261b22b366020b49c3d312d92eb3256a7af08846020f4bc3'),
    ('MCC5-THU Motor_torque_circulation.zip', 6513549892, 'cf5007378e4a28e6d7cc100bf56f144166cadb6a2607fbf38614bbfd0b8af0fb')
]


def main(outdir):
    rows = []
    for name, expected_size, expected_sha in EXPECTED:
        with urlopen(BASE + quote(name), timeout=40) as response:
            pointer = response.read(4096).decode('ascii').splitlines()
        fields = dict(line.split(' ', 1) for line in pointer)
        size = int(fields['size'])
        algorithm, digest = fields['oid'].split(':', 1)
        if (fields['version'] != 'https://git-lfs.github.com/spec/v1' or
                (size, algorithm, digest) != (expected_size, 'sha256', expected_sha)):
            raise ValueError('Unexpected pointer: ' + name)
        rows.append((name, size, digest))
    outdir.mkdir(exist_ok=True, parents=True)
    with (outdir / 'mcc-motor-archive-pointers.csv').open('w', newline='') as stream:
        writer = csv.writer(stream, lineterminator='\n')
        writer.writerow(('archive', 'publisher_declared_bytes', 'publisher_declared_sha256'))
        writer.writerows(rows)


if __name__ == '__main__':
    main(Path(sys.argv[1]))
