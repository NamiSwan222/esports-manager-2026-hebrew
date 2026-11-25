"""Write a small uncompressed Unreal .pak (format version 3, read by UE 4.x and 5.x).

    py -I tools/pak.py <folder> <out.pak>

Every file under <folder> goes in at its relative path (e.g. Ala/Content/...), mount point ../../../.
Only our own files go in: no game data.
"""
import hashlib, os, struct, sys

VERSION = 3
MAGIC = 0x5A6F12E1


def fstring(s):
    b = s.encode('ascii') + b'\0'
    return struct.pack('<i', len(b)) + b


def entry(offset, size, sha1):
    # Offset, Size, UncompressedSize, CompressionMethod(None), Hash, Flags, CompressionBlockSize
    return struct.pack('<qqqi', offset, size, size, 0) + sha1 + struct.pack('<BI', 0, 0)


def build(src, out):
    files = []
    for root, _, names in os.walk(src):
        for n in names:
            full = os.path.join(root, n)
            files.append((os.path.relpath(full, src).replace('\\', '/'), full))
    files.sort()
    body, index = bytearray(), bytearray()
    index += fstring('../../../') + struct.pack('<i', len(files))
    for rel, full in files:
        data = open(full, 'rb').read()
        sha = hashlib.sha1(data).digest()
        off = len(body)
        body += entry(0, len(data), sha) + data
        index += fstring(rel) + entry(off, len(data), sha)
    footer = struct.pack('<B', 0) + struct.pack('<IiqQ', MAGIC, VERSION, len(body), len(index)) + hashlib.sha1(index).digest()
    with open(out, 'wb') as f:
        f.write(body + index + footer)
    return [r for r, _ in files]


if __name__ == '__main__':
    for r in build(sys.argv[1], sys.argv[2]):
        print(r)
