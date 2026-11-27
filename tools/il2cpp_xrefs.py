"""Which game methods use each IL2CPP string literal (offline, from GameAssembly.dll + global-metadata.dat).

    python tools/il2cpp_xrefs.py [--game "<install>"]     -> work/inventory/literal_refs.json

The literals in global-metadata.dat are sorted alphabetically, so they carry no context. The code does:
every literal has a slot in GameAssembly's .data that starts out as the encoded metadata usage
`(5 << 29) | (index << 1) | 1` (5 = string literal) and is read with a RIP-relative instruction in each
method that uses it. We find those slots, every disp32 in the code sections that points at one, the
function containing it (.pdata), and its name: each IL2CPP code-gen module (`<Assembly>.dll` string +
method count + method pointer table) lists the methods of one assembly by metadata token; the metadata
gives the method's name and declaring type (version 107 layouts: method 32 bytes = name u32, declaring
type u16, ..., token u32 at +20; type 72 bytes = name u32, namespace u32, ...; image 36 bytes = name u32,
assembly u32, typeStart u16 + typeCount u16, ...).

Output: [[ "Assembly.dll|Class::Method", ... ] per literal index]. A code chunk that is not a method start
(split-off cold code) gets the method before it with a "~" prefix; nothing near: "?|0x<rva>".
"""
import argparse, bisect, json, os, re, struct
import numpy as np
import pefile
from common import DEFAULT_GAME, WORK
import metadata

DATA = 'EsportsManager_Data'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--game', default=DEFAULT_GAME)
    a = ap.parse_args()
    md = open(os.path.join(a.game, DATA, 'il2cpp_data', 'Metadata', 'global-metadata.dat'), 'rb').read()
    S = metadata.sections(md)
    so = S[2][0]

    def ident(i):
        return md[so + i:md.index(b'\0', so + i)].decode('utf-8', 'replace')

    images = []
    for r in range(S[21][2]):
        v = struct.unpack_from('<9I', md, S[21][0] + r * 36)
        images.append((v[2] & 0xffff, v[2] >> 16, ident(v[0])))
    images.sort()
    starts = [x[0] for x in images]
    types = []
    for r in range(S[19][2]):
        n, ns = struct.unpack_from('<2I', md, S[19][0] + r * 72)
        types.append((ident(ns) + '.' if ident(ns) else '') + ident(n))

    ga_path = os.path.join(a.game, 'GameAssembly.dll')
    pe = pefile.PE(ga_path, fast_load=True)
    ga = open(ga_path, 'rb').read()
    ib = pe.OPTIONAL_HEADER.ImageBase
    secs = {s.Name.rstrip(b'\0'): s for s in pe.sections}

    def rva2off(r):
        for s in pe.sections:
            if s.VirtualAddress <= r < s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData):
                return s.PointerToRawData + r - s.VirtualAddress

    def raw(s):
        return ga[s.PointerToRawData:s.PointerToRawData + s.SizeOfRawData]

    # code-gen modules: {"X.dll": (method count, method pointer table VA)}
    rd = secs[b'.rdata']
    dll_names = {ib + rd.VirtualAddress + m.start(1): m.group(1).decode()
                 for m in re.finditer(rb'(?<=\x00)([A-Za-z0-9_.\-]+\.dll)\x00', raw(rd))}
    keys = np.array(sorted(dll_names), dtype=np.uint64)
    mods = {}
    for s in pe.sections:
        if not s.Name.startswith((b'.data', b'.rdata')):
            continue
        b = raw(s)
        arr = np.frombuffer(b[:len(b) // 8 * 8], dtype='<u8')
        k = np.clip(np.searchsorted(keys, arr), 0, len(keys) - 1)
        for pos in np.nonzero(keys[k] == arr)[0]:
            o = s.PointerToRawData + int(pos) * 8
            cnt, ptr = struct.unpack_from('<I', ga, o + 8)[0], struct.unpack_from('<Q', ga, o + 16)[0]
            if 0 < cnt < 500000 and ib < ptr < ib + pe.OPTIONAL_HEADER.SizeOfImage:
                mods.setdefault(dll_names[int(arr[pos])], (cnt, ptr))
    names = {}
    for r in range(S[5][2]):
        o = S[5][0] + r * 32
        nm, dt, tok = struct.unpack_from('<I', md, o)[0], struct.unpack_from('<H', md, o + 4)[0], struct.unpack_from('<I', md, o + 20)[0]
        img = images[bisect.bisect_right(starts, dt) - 1][2]
        if img not in mods:
            continue
        cnt, ptr = mods[img]
        rid = tok & 0xffffff
        if 1 <= rid <= cnt:
            f = struct.unpack_from('<Q', ga, rva2off(ptr - ib) + (rid - 1) * 8)[0]
            if f:
                names.setdefault(f - ib, f'{img}|{types[dt]}::{ident(nm)}')

    # string literal slots in .data
    ds = secs[b'.data']
    b = raw(ds)
    arr = np.frombuffer(b[:len(b) // 8 * 8], dtype='<u8')
    pos = np.nonzero((arr >> 32 == 0) & (arr & 1 == 1) & (((arr >> 29) & 7) == 5))[0]
    slot_rva = (ds.VirtualAddress + pos * 8).astype(np.int64)
    slot_idx = ((arr[pos] & 0x1FFFFFFE) >> 1).astype(np.int64)
    o = np.argsort(slot_rva)
    slot_rva, slot_idx = slot_rva[o], slot_idx[o]
    pd = secs[b'.pdata']
    rf = np.frombuffer(ga[pd.PointerToRawData:pd.PointerToRawData + pd.Misc_VirtualSize // 12 * 12], dtype='<u4').reshape(-1, 3)
    o = np.argsort(rf[:, 0])
    fb, fe = rf[o, 0].astype(np.int64), rf[o, 1].astype(np.int64)
    nstart = np.array(sorted(names), dtype=np.int64)

    def name_of(fn, site):
        if fn in names:
            return names[fn]
        k = int(np.searchsorted(nstart, site, side='right')) - 1  # a split-off chunk: the method before it
        if k >= 0 and site - nstart[k] < 0x10000:
            return '~' + names[int(nstart[k])]
        return f'?|{site:#x}'

    nlit = S[0][2] - 1
    refs = [set() for _ in range(nlit)]
    for name in (b'.text', b'il2cpp'):
        s = secs.get(name)
        if s is None:
            continue
        code = np.frombuffer(ga[s.PointerToRawData:s.PointerToRawData + s.Misc_VirtualSize], dtype=np.uint8)
        n, step = len(code), 1 << 24
        for st in range(0, n - 4, step):
            en = min(n - 4, st + step)
            seg = code[st:en + 4].astype(np.int64)
            d = seg[:-4] | (seg[1:-3] << 8) | (seg[2:-2] << 16) | (seg[3:-1] << 24)
            d = np.where(d >= 1 << 31, d - (1 << 32), d)
            site = s.VirtualAddress + np.arange(st, en, dtype=np.int64)
            tgt = site + 4 + d
            k = np.clip(np.searchsorted(slot_rva, tgt), 0, len(slot_rva) - 1)
            hit = slot_rva[k] == tgt
            hs, hl = site[hit], slot_idx[k[hit]]
            fi = np.searchsorted(fb, hs, side='right') - 1
            for sv, li, f in zip(hs.tolist(), hl.tolist(), fi.tolist()):
                fn = int(fb[f]) if f >= 0 and sv < fe[f] else None
                if li < nlit:
                    refs[li].add(name_of(fn, sv))
    os.makedirs(os.path.join(WORK, 'inventory'), exist_ok=True)
    out = [sorted(r) for r in refs]
    json.dump(out, open(os.path.join(WORK, 'inventory', 'literal_refs.json'), 'w', encoding='utf-8'), ensure_ascii=False)
    print(f'{len(names)} named methods, {sum(1 for r in out if r)}/{nlit} literals with a code reference')


if __name__ == '__main__':
    main()
