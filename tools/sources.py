"""Readers (and writers) for the text sources outside the string tables and code literals.

- TextMeshPro default texts (`m_text`) of the scene and prefab components in level*, sharedassets*.assets
  and resources.assets. These files have no type trees, so the MonoBehaviour data is read raw: base fields
  (GameObject PPtr, enabled, script PPtr, name), Graphic fields (material, color, raycast target and padding,
  maskable, OnCullStateChanged calls), then `m_text`. A text replaced by `set_raw` keeps every later field.
- Dropdown option texts (TMP_Dropdown / StyledDropdown `m_Options`): shown through `TMP_Text.text`, so they
  are translated as display labels (the code may read the option text as a value).
- Dialogs: `Resources/dialogs/en/*` TextAssets in resources.assets, JSON {subject, blocks: [{type, text}]}
  (type 0 = staff member speaking, 1/2/3 = the manager's answers).
- default.emdb (StreamingAssets): "EMDB" + version 0x03 + AES-256-GCM (12-byte nonce, tag at the end; the key
  is a hex code literal) around a zip of `;`-separated CSV files (Players, Teams, Sponsors, Tournaments, Staff).
"""
import csv, io, json, os, re, struct, zipfile
from common import DEFAULT_GAME

DATA = 'EsportsManager_Data'
EMDB = os.path.join(DATA, 'StreamingAssets', 'default.emdb')
EMDB_KEY = 'E47A2C9F01D85B33A6F27EC4980D4B613EB5792ADF148C506FC3279105E6BA48'
TMP_SCRIPTS = ('TMPro.TextMeshProUGUI', 'TMPro.TextMeshPro')
DROPDOWN_SCRIPTS = ('StyledDropdown', 'TMPro.TMP_Dropdown')
LSE = 'UnityEngine.Localization.Components.LocalizeStringEvent'
# emdb columns a player reads (the rest are names, numbers, ids, urls)
EMDB_TEXT = {'Players.csv': ['Bio'], 'Teams.csv': ['Description'], 'Sponsors.csv': ['Description'],
             'Tournaments.csv': ['Description']}


def scene_files(game=DEFAULT_GAME):
    d = os.path.join(game, DATA)
    return sorted((f for f in os.listdir(d) if re.fullmatch(r'level\d+|sharedassets\d+\.assets|resources\.assets', f)),
                  key=lambda f: (not f.startswith('level'), int(re.sub(r'\D', '', f) or 0), f))


_SCRIPTS = {}


def scripts(game=DEFAULT_GAME):
    """{(file name lower, path id): 'Namespace.Class'} of the MonoScripts (globalgamemanagers.assets)."""
    if not _SCRIPTS:
        import UnityPy
        env = UnityPy.load(os.path.join(game, DATA, 'globalgamemanagers.assets'))
        for o in env.objects:
            if o.type.name == 'MonoScript':
                s = o.read()
                _SCRIPTS[('globalgamemanagers.assets', o.path_id)] = (s.m_Namespace + '.' if s.m_Namespace else '') + s.m_ClassName
    return _SCRIPTS


def script_of(o, raw):
    fid, pid = struct.unpack_from('<iq', raw, 16)
    sf = o.assets_file
    try:
        fn = sf.name if fid == 0 else os.path.basename(sf.externals[fid - 1].path)
    except IndexError:
        return '?'
    return _SCRIPTS.get((fn.lower(), pid), '?')


def read_str(raw, off):
    n = struct.unpack_from('<i', raw, off)[0]
    if not 0 <= n <= len(raw) - off - 4:
        return None, off
    try:
        return raw[off + 4:off + 4 + n].decode('utf-8'), off + 4 + n + (-n) % 4
    except UnicodeDecodeError:
        return None, off


def tmp_text_offset(raw):
    """Offset of m_text in a TextMeshPro(UGUI) MonoBehaviour, or None."""
    name, off = read_str(raw, 28)
    if name is None or off + 60 > len(raw):
        return None
    if struct.unpack_from('<i', raw, off + 52)[0] != 0:  # OnCullStateChanged has persistent calls: unusual
        return None
    t, _ = read_str(raw, off + 56)
    return off + 56 if t is not None else None


def set_str(raw, off, text):
    """raw with the length-prefixed string at off replaced (4-byte aligned like Unity writes it)."""
    n = struct.unpack_from('<i', raw, off)[0]
    end = off + 4 + n + (-n) % 4
    b = text.encode('utf-8')
    return raw[:off] + struct.pack('<i', len(b)) + b + b'\0' * ((-len(b)) % 4) + raw[end:]


def all_strings(raw, start):
    """(offset, text) of every plausible aligned length-prefixed string from start (heuristic)."""
    out, i, n = [], start, len(raw)
    while i + 4 <= n:
        L = struct.unpack_from('<i', raw, i)[0]
        if 1 <= L <= 100000 and i + 4 + L <= n and raw[i + 4 + L:i + 4 + L + (-L) % 4] == b'\0' * ((-L) % 4):
            try:
                s = raw[i + 4:i + 4 + L].decode('utf-8')
            except UnicodeDecodeError:
                s = None
            if s and all(c.isprintable() or c in '\r\n\t' for c in s):
                out.append((i, s))
                i += 4 + L + (-L) % 4
                continue
        i += 4
    return out


def scan_ui(game=DEFAULT_GAME, files=None):
    """Yield dicts for TMP default texts ('tmp') and dropdown options ('option') in the scene/asset files."""
    import UnityPy
    scripts(game)
    for f in files or scene_files(game):
        env = UnityPy.load(os.path.join(game, DATA, f))
        mbs, lse_gos, gos = [], set(), {}
        for o in env.objects:
            if o.type.name == 'GameObject':
                try:
                    gos[o.path_id] = o.read().m_Name
                except Exception:
                    pass
            elif o.type.name == 'MonoBehaviour':
                raw = o.get_raw_data()
                if len(raw) < 32:
                    continue
                scr = script_of(o, raw)
                go = struct.unpack_from('<q', raw, 4)[0]
                if scr == LSE:
                    lse_gos.add(go)
                elif scr in TMP_SCRIPTS or scr in DROPDOWN_SCRIPTS:
                    mbs.append((o.path_id, scr, go, raw))
        for pid, scr, go, raw in mbs:
            if scr in TMP_SCRIPTS:
                off = tmp_text_offset(raw)
                if off is None:
                    continue
                t, _ = read_str(raw, off)
                if t:
                    yield {'kind': 'tmp', 'file': f, 'id': pid, 'off': off, 'text': t, 'go': gos.get(go, ''),
                           'localized': go in lse_gos}
            else:
                ss = all_strings(raw, 28)
                k = next((i for i, (_, s) in enumerate(ss) if s == 'Disabled'), None)
                if k is None:
                    continue
                for _, s in ss[k + 1:]:
                    if re.fullmatch(r'[\w.+`\[\]]+, [\w.\-]+', s):
                        break
                    yield {'kind': 'option', 'file': f, 'id': pid, 'text': s, 'go': gos.get(go, '')}


def dialogs(game=DEFAULT_GAME):
    """{resource path: (path id, json text)} of the English dialogs (Resources/dialogs/en/*)."""
    import UnityPy
    env = UnityPy.load(os.path.join(game, DATA, 'globalgamemanagers'))
    cont = {}
    for o in env.objects:
        if o.type.name == 'ResourceManager':
            t = o.read_typetree()
            for path, ptr in t['m_Container']:
                fid = ptr['m_FileID']
                fn = os.path.basename(o.assets_file.externals[fid - 1].path) if fid else o.assets_file.name
                if fn.lower() == 'resources.assets' and path.startswith('dialogs/en/'):
                    cont[ptr['m_PathID']] = path
    env = UnityPy.load(os.path.join(game, DATA, 'resources.assets'))
    out = {}
    for o in env.objects:
        if o.type.name == 'TextAsset' and o.path_id in cont:
            s = o.read().m_Script
            out[cont[o.path_id]] = (o.path_id, s if isinstance(s, str) else bytes(s).decode('utf-8'))
    return out


def dialog_texts(js):
    return [b['text'] for b in json.loads(js)['blocks'] if b.get('text')]


def emdb_open(path):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    d = open(path, 'rb').read()
    assert d[:4] == b'EMDB' and d[4] == 3, 'unknown emdb format'
    z = AESGCM(bytes.fromhex(EMDB_KEY)).decrypt(d[5:17], d[17:], None)
    zf = zipfile.ZipFile(io.BytesIO(z))
    return {i.filename: zf.read(i) for i in zf.infolist()}, [i.filename for i in zf.infolist()]


def emdb_save(files, order, path):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for n in order:
            zf.writestr(n, files[n])
    nonce = os.urandom(12)
    open(path, 'wb').write(b'EMDB\x03' + nonce + AESGCM(bytes.fromhex(EMDB_KEY)).encrypt(nonce, buf.getvalue(), None))


def csv_rows(b):
    """(header, rows, line break) of a `;` CSV in the emdb: no quoting, one record per line (the game splits)."""
    t = b.decode('utf-8')
    nl = '\r\n' if '\r\n' in t else '\n'
    lines = t.split(nl)
    return lines[0].split(';'), [l.split(';') for l in lines[1:]], nl


def csv_bytes(header, rows, nl):
    for r in rows:
        for v in r:
            assert ';' not in v and '\n' not in v, v
    return nl.join([';'.join(header)] + [';'.join(r) for r in rows]).encode('utf-8')


def emdb_texts(game=DEFAULT_GAME):
    """[(csv file, column, row key, English text)] of the player-visible emdb text."""
    files, _ = emdb_open(os.path.join(game, EMDB))
    out = []
    for f, cols in EMDB_TEXT.items():
        h, rows, _ = csv_rows(files[f])
        for r in rows:
            for c in cols:
                v = r[h.index(c)] if len(r) == len(h) else ''
                if v.strip():
                    out.append((f, c, r[0], v))
    return out


# FaceIt-style player bios (4,239 of default.emdb) are one sentence with numbers, translated by a template. The
# template is known here only by the hash of its skeleton (see skeleton()): the repo carries no game English.
# The four skeletons are "a"/"an" before the win percentage x "rate"/"raet" (today's default.emdb misspells it,
# older databases do not). Holes in text order: ELO value, the word ELO, FaceIt level, since (date), region,
# matches, win %, K/D, best streak.
FACEIT_SKELETONS = {'290c5cda8bb9e3ef', '38455c882591a31f', '8a750456253d4323', '2b98bc289391cfab'}
FACEIT_HE = ('{0} ELO (רמה {2} ב-FaceIt), משחק ב-FaceIt מאז {3} באזור {4}. '
             'שיחק {5} משחקים עם {6}% ניצחונות ו-K/D ממוצע של {7}, רצף הניצחונות הטוב ביותר: {8}.')


def _alnum(c):
    return c.isascii() and c.isalnum()


def skeleton(t):
    """(text with each hole replaced by `{}`, [holes]): the bio-template normalisation, the same as the proxy's
    (tools/proxy/src/tmp.rs `skeleton`). A hole starts after a non-alphanumeric character (or at the start) and is
    either a number-like token (an ASCII digit, then ASCII letters/digits, `.` between two of them, a space
    before another digit: "17.02.2019", "1.47", "2 308", "248u") or a word of 2-4 ASCII capitals ("EU", "ELO")."""
    out, holes, i, n = [], [], 0, len(t)
    while i < n:
        c = t[i]
        start = i == 0 or not _alnum(t[i - 1])
        if start and '0' <= c <= '9':
            j = i
            while True:
                while j < n and _alnum(t[j]):
                    j += 1
                if j + 1 < n and t[j] == '.' and _alnum(t[j + 1]):
                    j += 1
                elif j + 1 < n and t[j] == ' ' and '0' <= t[j + 1] <= '9':
                    j += 1
                else:
                    break
            holes.append(t[i:j])
            out.append('{}')
            i = j
            continue
        if start and 'A' <= c <= 'Z':
            j = i
            while j < n and 'A' <= t[j] <= 'Z':
                j += 1
            if 2 <= j - i <= 4 and not (j < n and _alnum(t[j])):
                holes.append(t[i:j])
                out.append('{}')
                i = j
                continue
        out.append(c)
        i += 1
    return ''.join(out), holes


def faceit_he(s):
    from common import H
    sk, holes = skeleton(s.strip())
    return FACEIT_HE.format(*holes) if len(holes) == 9 and H(sk) in FACEIT_SKELETONS else None


def faceit_templates():
    """[(H(skeleton), Hebrew with `{0}`..`{8}`)] of the FaceIt bio for the proxy's bios file. Careers keep the bio
    text they were created with (DataPlayer.Biography in the save), so the numbers and the spelling differ per
    career; the proxy hashes the skeleton of a displayed text and fills the holes into the Hebrew."""
    return [(h, FACEIT_HE) for h in sorted(FACEIT_SKELETONS)]
