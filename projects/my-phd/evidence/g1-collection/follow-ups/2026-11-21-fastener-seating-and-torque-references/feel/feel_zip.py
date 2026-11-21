"""Read a split ZIP64 central directory and extract ordinary deflated members by verified ranges."""
from pathlib import Path
import struct
from urllib.request import Request,urlopen
import zlib

PARTS=['dataset.z01','dataset.z02','dataset.z03','dataset.zip']
REVISION='b757dc72ba7ad9a0b501d92fa097d5a91474fbc9'
BASE=f'https://huggingface.co/datasets/amirsh1376/FeelAnyForce/resolve/{REVISION}/'
CENTRAL=struct.Struct('<4s6H3I5H2I')


def read_directory(blob):
    pos=0
    while pos<len(blob):
        h=CENTRAL.unpack_from(blob,pos)
        if h[0]!=b'PK\x01\x02':raise ValueError('Invalid central header')
        cs,us=h[8:10]
        fn,ex,comment,disc=h[10:14]
        offset=h[16]
        pos+=CENTRAL.size
        name=blob[pos:pos+fn].decode('utf-8')
        extra=blob[pos+fn:pos+fn+ex]
        z=0
        while z+4<=len(extra):
            kind,length=struct.unpack_from('<HH',extra,z)
            val=extra[z+4:z+4+length]
            if kind==1:
                j=0
                if us==0xffffffff:us,=struct.unpack_from('<Q',val,j);j+=8
                if cs==0xffffffff:cs,=struct.unpack_from('<Q',val,j);j+=8
                if offset==0xffffffff:offset,=struct.unpack_from('<Q',val,j);j+=8
                if disc==0xffff:disc,=struct.unpack_from('<I',val,j)
            z+=4+length
        yield name,(disc,offset,cs,us,h[7],h[4])
        pos+=fn+ex+comment


def fetch_range(part,begin,end,sizes):
    span=f'{begin}-{end}'
    req=Request(BASE+PARTS[part]+'?download=true&g1='+span,headers={'Range':'bytes='+span})
    with urlopen(req,timeout=60) as res:
        if res.status!=206 or res.headers.get('Content-Range')!=f'bytes {span}/{sizes[part]}':
            raise ValueError('Unexpected HTTP content range')
        blob=res.read()
    if len(blob)!=end-begin+1:raise ValueError('Missing range bytes')
    return blob


def disk_bytes(part,offset,n,sizes):
    data=bytearray()
    while len(data)<n:
        width=min(n-len(data),sizes[part]-offset)
        if width>0:data.extend(fetch_range(part,offset,offset+width-1,sizes))
        part+=1
        offset=0
    return data


def load_member(name,info,sizes):
    part,off,cs,us,crc,method=info
    prefix=disk_bytes(part,off,30,sizes)
    if prefix[:4]!=b'PK\x03\x04':raise ValueError('Missing local file header')
    fn,ex=struct.unpack_from('<HH',prefix,26)
    data=disk_bytes(part,off,30+fn+ex+cs,sizes)
    if data[30:30+fn].decode()!=name:raise ValueError('Local name differs')
    packed=data[30+fn+ex:]
    raw=zlib.decompress(packed,-15) if method==8 else bytes(packed) if method==0 else None
    if raw is None or len(raw)!=us or zlib.crc32(raw)!=crc:raise ValueError('File or CRC mismatch')
    return raw
