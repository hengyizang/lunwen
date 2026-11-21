"""Match all sample paths to the ZIP central directory and test six complete image members.

Usage: python check_digitac_images.py samples.csv OUT [--archive images.zip]
Default reads selected public HTTP byte ranges from the fixed Zenodo record.
"""
import argparse
import io
from pathlib import Path
import struct
from urllib.request import Request, urlopen
from zipfile import ZipFile
import zlib

import pandas as pd


URL='https://zenodo.org/api/records/23209032/files/images.zip/content'
SIZE=6040203221


class RemoteZip(io.RawIOBase):
    """Seekable view of a public ZIP. Cache central directory and local file spans."""
    def __init__(self):
        self.pos=0
        self.cached_start=0
        self.cached=b''

    def tell(self):
        return self.pos

    def seek(self,offset,whence=0):
        self.pos=[offset,self.pos+offset,SIZE+offset][whence]
        return self.pos

    def read(self,n=-1):
        if n<0:
            n=SIZE-self.pos
        n=min(n,SIZE-self.pos)
        if not n:return b''
        relative=self.pos-self.cached_start
        if relative<0 or relative+n>len(self.cached):
            start=self.pos
            if self.pos>SIZE-1048576:
                start=SIZE-1048576
            stop=min(SIZE,max(self.pos+n,start+1048576))-1
            request=Request(URL,headers={'Range':f'bytes={start}-{stop}'})
            with urlopen(request,timeout=25) as response:
                if response.status!=206 or response.headers['Content-Range']!=f'bytes {start}-{stop}/{SIZE}':
                    raise IOError('Unexpected range response')
                self.cached=response.read()
            self.cached_start=start
            relative=self.pos-start
        self.pos+=n
        return self.cached[relative:relative+n]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('samples',type=Path)
    parser.add_argument('out',type=Path)
    parser.add_argument('--archive',type=Path)
    args=parser.parse_args()
    samples=pd.read_csv(args.samples).sort_values(['seed','pose_number'])
    chosen=samples.groupby(['batch','image_torn'],sort=True).head(1).sort_values(['batch','image_torn'])
    rows=[]
    with ZipFile(args.archive or RemoteZip()) as z:
        images=[x.filename for x in z.infolist() if x.filename.endswith('.png')]
        assert len(images)==10000 and set(images)==set(samples.image)
        for rec in chosen.itertuples():
            info=z.getinfo(rec.image)
            b=z.read(info)  # zipfile verifies whole-member CRC.
            assert b[:8]==b'\x89PNG\r\n\x1a\n' and b[12:16]==b'IHDR'
            w,h,depth,colour=struct.unpack('>IIBB',b[16:26])
            rows.append(dict(batch=rec.batch,seed=rec.seed,pose=rec.pose_number,source_torn_flag=rec.image_torn,
                             path=rec.image,uncompressed_bytes=len(b),crc32=f'{zlib.crc32(b):08x}',png_width=w,
                             png_height=h,bit_depth=depth,png_colour_type=colour))
    args.out.mkdir(parents=True,exist_ok=True)
    pd.DataFrame(rows).to_csv(args.out/'digitac-image-members.csv',index=False,lineterminator='\n')


if __name__=='__main__':
    main()
