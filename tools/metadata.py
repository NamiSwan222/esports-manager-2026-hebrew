"""Read and rewrite string literals in an IL2CPP global-metadata.dat (version 107, Unity 6000.5).

Header: magic 0xFAB11BAF, version, then 32 sections as (offset, size, count) triples.
  section 0: string literal table, u32 start offset of each literal in section 1 (+ one end sentinel)
  section 1: string literal data (UTF-8, back to back)
Every other section is addressed only through the header, so after growing section 1 we move the later
sections and add the size difference to their offsets (keeping each section's 4-byte alignment).
"""
import struct

MAGIC = 0xFAB11BAF


def sections(d):
    out, o = [], 8
    for _ in range(32):
        out.append(list(struct.unpack_from('<III', d, o)))
        o += 12
    return out


def literals(d):
    s = sections(d)
    (to, tsz, tc), (do, dsz, dc) = s[0][:3], s[1][:3]
    offs = [struct.unpack_from('<I', d, to + 4 * i)[0] for i in range(tc)]
    return [d[do + offs[i]:do + (offs[i + 1] if i + 1 < tc else dsz)].decode('utf-8', 'surrogatepass')
            for i in range(tc - 1)]


def rewrite(d, replace):
    """replace: {literal index: new text}. Returns the new metadata bytes."""
    assert struct.unpack_from('<I', d, 0)[0] == MAGIC
    s = sections(d)
    lits = literals(d)
    for i, t in replace.items():
        lits[i] = t
    data, offs = bytearray(), []
    for t in lits:
        offs.append(len(data))
        data += t.encode('utf-8', 'surrogatepass')
    offs.append(len(data))
    tc = s[0][2]
    assert len(offs) == tc
    table = b''.join(struct.pack('<I', o) for o in offs)
    assert len(table) == s[0][1]
    old_end = s[1][0] + s[1][1]
    new_end = s[1][0] + len(data)
    head = bytearray(d[:s[1][0]])
    head[s[0][0]:s[0][0] + len(table)] = table
    pad_old = s[2][0] - old_end                       # padding the original had before section 2
    pad_new = (-(new_end) % 4) if pad_old else 0
    rest = d[s[2][0]:]
    delta = (new_end + pad_new) - s[2][0]
    out = head + data + b'\0' * pad_new + rest
    struct.pack_into('<III', out, 8 + 12 * 1, s[1][0], len(data), s[1][2])
    for k in range(2, 32):
        off, sz, cnt = s[k]
        struct.pack_into('<III', out, 8 + 12 * k, off + delta, sz, cnt)
    return bytes(out)
