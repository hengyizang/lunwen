"""Read numeric inputs against the versioned DaRUS manifest using the original bytes."""
import csv
import hashlib
import json
from pathlib import Path


def verified(root, number):
    metadata = json.loads((root / f'meta{number}.json').read_text())
    for item in metadata['data']['latestVersion']['files']:
        m = item['dataFile']
        path = root / str(number) / str(m['id'])
        with path.open('rb') as stream:
            actual = hashlib.file_digest(stream,'md5').hexdigest()
        if actual != m['md5'] or path.stat().st_size != m.get('originalFileSize', m['filesize']):
            raise ValueError(f"Unexpected original bytes for {m['id']}")
        yield m.get('originalFileName',m['filename']),item.get('directoryLabel',''),path


def write_table(path, rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w',newline='',encoding='utf-8') as stream:
        writer=csv.DictWriter(stream,fieldnames=rows[0],lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)
