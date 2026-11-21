"""Download a fixed Stuttgart release into the input layout used by the derivations."""
import argparse
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen


def fetch(number, root):
    doi = f'10.18419/darus-{number}'
    origin = 'https://darus.uni-stuttgart.de/api'
    manifest = f'{origin}/datasets/:persistentId/versions/1.0?persistentId=doi:{doi}'
    with urlopen(manifest,timeout=60) as response:
        version=json.load(response)['data']
    assert (version['versionNumber'],version['versionMinorNumber'])==(1,0)
    folder = root / str(number)
    folder.mkdir(parents=True,exist_ok=True)
    (root/f'meta{number}.json').write_text(json.dumps({'data':{'latestVersion':version}}))
    for entry in version['files']:
        f=entry['dataFile']
        dest=folder/str(f['id'])
        if dest.exists() and hashlib.md5(dest.read_bytes()).hexdigest()==f['md5']:
            continue
        url=f"{origin}/access/datafile/{f['id']}"
        if 'originalFileName' in f:
            url+='?format=original'
        with urlopen(url,timeout=120) as response:
            content=response.read()
        if hashlib.md5(content).hexdigest()!=f['md5'] or len(content)!=f.get('originalFileSize',f['filesize']):
            raise ValueError(f"Manifest and bytes differ for {f['id']}")
        dest.write_bytes(content)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('release',type=int,choices=(2563,3109,6114,6333))
    parser.add_argument('input',type=Path)
    args=parser.parse_args(); fetch(args.release,args.input)
