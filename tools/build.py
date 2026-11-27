"""Build the Hebrew files from translation/he/*.json into work/build (+ work/pack/files).

    python tools/build.py [--allow-missing] [--game "<install>"]

What each source becomes (tools/coverage.py `translations()` resolves the Hebrew):
- string tables: the English string-table bundle with every used string replaced, plus catalog.bin with that
  bundle's CRC set to 0 and its new size (Addressables would reject the changed bundle).
- code literals: global-metadata.dat with the literal table rewritten (glossary articles, sentences, labels
  used only by display code).
- display labels: labels.txt, exact English UI texts (short code literals the code may also use as keys,
  dropdown options) that the proxy shows in Hebrew (translation/he/_labels.json and reused table text).
- scenes: TextMeshPro default texts in level0-3, resources.assets and sharedassets0-3.assets (raw
  MonoBehaviour rewrite, tools/sources.py).
- dialogs: the Resources/dialogs/en TextAssets in resources.assets.
- default.emdb: bios and descriptions replaced, re-encrypted with the game's key.
- fonts: LiberationSans (TextMeshPro's default fallback) and the other OS fonts in resources.assets /
  sharedassets1-3 replaced by Noto Sans + Noto Sans Hebrew (OFL): all Hebrew glyphs come from that fallback.
- bios.txt: player bios for careers created before the pack (or with another database): a career keeps the bio
  text it copied from the database (DataPlayer.Biography in the save), and the profile sets it whole on a
  TextMeshPro text, so the proxy swaps it at display time: exact text -> Hebrew lines, and `*` template lines
  for the FaceIt bio (numbers differ per career). The save is never changed.
- keep.txt: texts that stay in Latin on purpose (names); the proxy's text log skips them.
The pack carries no English: labels.txt, bios.txt and keep.txt are keyed by H(English) (common.H, 16 hex digits of
SHA-256 over the UTF-8 text; README "Lookup files"). work/plain/ gets the same files with the English keys
(never shipped) for the proxy's tests (cargo test compares the hashed lookup with the plain one).
- dates.txt: English dates the game builds at run time ("<b>Thursday</b>,<br>01 Jan 2026", "Thursday, January 1,
  2026") -> Hebrew names and order; a copy of translation/he/dates.txt (shapes and names, format described there).
TextMeshPro has no bidi: the proxy makes Hebrew texts right-to-left at runtime (tools/proxy, `rtl=tmp`).
All are modified copies in work/build; make-pack turns them into bsdiff patches with `output` into
tirgumim\\he\\, and the proxy (version.dll) redirects the game to them only when started with -tirgumim_he.
The text log is off by default: build never ships textlog.on (README: how to turn it on).
"""
import argparse, json, os, shutil, struct, subprocess, sys
import UnityPy
from common import AA, DEFAULT_GAME, EN_BUNDLE, HE_DIR, ROOT, WORK, H, english, hebrew, load_json
import coverage, metadata, sources
os.environ.setdefault("TIRGUMIM_PLAIN_FONTS", "1")  # merged GPOS tables misplace Hebrew letters in TMP
import build_fonts

DATA = 'EsportsManager_Data'
FONT_FILES = ['resources.assets', 'sharedassets1.assets', 'sharedassets2.assets', 'sharedassets3.assets']
SKIP_FONTS = ('NotoSansTC', 'NotoSansSC', 'NotoSansKR')
PACK_CFG = os.path.join(ROOT, 'pack', 'pack.config.json')
REDIRECT = os.path.join(ROOT, 'pack', 'redirect.cfg')


def weight(name):
    n = name.lower()
    for k, v in [('black', 900), ('extrabold', 800), ('semibold', 600), ('bold', 700), ('medium', 500), ('light', 300)]:
        if k in n:
            return v
    return 400


def esc(t):
    return t.replace('\\', '\\\\').replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')


def build_tables(game, out):
    en, he = english(), hebrew()
    ids = {t: {r['id'] for r in rows} for t, rows in en.items()}
    env = UnityPy.load(os.path.join(game, AA, EN_BUNDLE))
    for o in env.objects:
        if o.type.name != 'MonoBehaviour':
            continue
        t = o.read_typetree()
        if 'm_TableData' not in t:
            continue
        name = t['m_Name'][:-3]
        for e in t['m_TableData']:
            h = he.get(name, {}).get(str(e['m_Id']))
            if h and str(e['m_Id']) in ids.get(name, ()):
                e['m_Localized'] = h
        o.save_typetree(t)
    new_bundle = env.file.save(packer='lz4')
    open(os.path.join(out, EN_BUNDLE), 'wb').write(new_bundle)
    # Addressables checks each bundle's CRC from catalog.bin. In our copy of the catalog the record of the
    # replaced bundle gets CRC 0 (= don't check) and its new size: (u32 crc, u32 size) are adjacent.
    cat = bytearray(open(os.path.join(game, AA, '..', 'catalog.bin'), 'rb').read())
    old_size = os.path.getsize(os.path.join(game, AA, EN_BUNDLE))
    i = cat.find(struct.pack('<I', old_size))
    if i < 4 or cat.find(struct.pack('<I', old_size), i + 1) != -1:
        sys.exit('catalog.bin: bundle record not found (or not unique)')
    struct.pack_into('<II', cat, i - 4, 0, len(new_bundle))
    open(os.path.join(out, 'catalog.bin'), 'wb').write(cat)


def build_assets(game, out, tr, fonts=True):
    """Fonts, TMP default texts and dialogs in the serialized files. Returns the files written."""
    scenes, dialogs_he = tr['scenes'], tr['dialogs']
    dlg = sources.dialogs(game)
    dlg_ids = {pid: js for pid, js in dlg.values()}
    sources.scripts(game)
    work = os.path.join(out, '_fonts')
    os.makedirs(work, exist_ok=True)
    written = []
    for f in sorted(set(sources.scene_files(game)) | set(FONT_FILES)):
        env = UnityPy.load(os.path.join(game, DATA, f))
        n_font = n_tmp = n_dlg = 0
        for o in env.objects:
            tn = o.type.name
            if tn == 'Font' and fonts and f in FONT_FILES:
                t = o.read_typetree()
                if t['m_Name'].startswith(SKIP_FONTS) or not t.get('m_FontData'):
                    continue
                wd = 75 if 'condensed' in t['m_Name'].lower() or t['m_Name'] in ('Oswald-Bold', 'Anton') else 100
                ttf = build_fonts.build(os.path.join(ROOT, 'fonts', 'src'), work, weight(t['m_Name']), wd)
                t['m_FontData'] = list(open(ttf, 'rb').read())
                o.save_typetree(t)
                n_font += 1
            elif tn == 'MonoBehaviour' and scenes:
                raw = o.get_raw_data()
                if len(raw) < 32 or sources.script_of(o, raw) not in sources.TMP_SCRIPTS:
                    continue
                off = sources.tmp_text_offset(raw)
                if off is None:
                    continue
                t, _ = sources.read_str(raw, off)
                if t in scenes:
                    o.set_raw_data(sources.set_str(raw, off, scenes[t]))
                    n_tmp += 1
            elif tn == 'TextAsset' and f == 'resources.assets' and o.path_id in dlg_ids:
                js = json.loads(dlg_ids[o.path_id])
                changed = False
                for b in js['blocks']:
                    h = dialogs_he.get(b.get('text'))
                    if h:
                        b['text'] = h
                        changed = True
                if changed:
                    d = o.read()
                    d.m_Script = json.dumps(js, ensure_ascii=False, indent=4)
                    d.save()
                    n_dlg += 1
        if n_font or n_tmp or n_dlg:
            open(os.path.join(out, f), 'wb').write(env.file.save())
            written.append(f)
            print(f'{f}: {n_font} fonts, {n_tmp} texts, {n_dlg} dialogs')
    shutil.rmtree(work)
    return written


def build_emdb(game, out, emdb_he):
    files, order = sources.emdb_open(os.path.join(game, sources.EMDB))
    n = 0
    for f, cols in sources.EMDB_TEXT.items():
        h, rows, nl = sources.csv_rows(files[f])
        for r in rows:
            if len(r) != len(h):
                continue
            for c in cols:
                v = r[h.index(c)]
                he = emdb_he.get(v)
                if he:
                    r[h.index(c)] = he.replace(';', ',').replace('\r', ' ').replace('\n', ' ')
                    n += 1
        files[f] = sources.csv_bytes(h, rows, nl)
    sources.emdb_save(files, order, os.path.join(out, 'default.emdb'))
    print(f'default.emdb: {n} texts')


def bios(game, emdb_he):
    """{English: Hebrew} of each translated default.emdb text that is not a FaceIt bio (those are covered by the
    templates)."""
    # every translated default.emdb text (player bios, team/sponsor/tournament descriptions): default.emdb itself
    # is NOT patched, because a career copies these texts into its save and a later Steam launch must stay English
    return {v: emdb_he[v] for f, c, _, v in sources.emdb_texts(game) if emdb_he.get(v) and not sources.faceit_he(v)}


def upper(s):
    return s.upper()  # the proxy: Rust str::to_uppercase (both full Unicode case mapping)


def write_lookups(he_dir, plain_dir, tr, bio_texts):
    """labels.txt, bios.txt, keep.txt for the proxy, keyed by H(English):
      labels.txt  `H<TAB>Hebrew` (exact text), `^H<TAB>Hebrew` (H of the upper-cased English, for a text the game
                  upper-cases before showing it; first label in English order wins, as the proxy did)
      bios.txt    `H<TAB>Hebrew` (exact text), `*<TAB>H(skeleton)<TAB>Hebrew with {0}..` (sources.skeleton)
      keep.txt    `H` per line
    and the same with the English keys (the old format) into plain_dir, for tests only."""
    import coverage
    pool = coverage.english_pool()
    labels = {h: v for h, v in tr['labels'].raw.items() if v}
    en_labels = {pool[h]: v for h, v in labels.items() if h in pool}
    unresolved = len(labels) - len(en_labels)
    up = {}
    for en, v in sorted(en_labels.items()):
        up.setdefault(H(upper(en)), v)
    up = {h: v for h, v in up.items() if h not in labels}  # the proxy tries the exact key first
    with open(os.path.join(he_dir, 'labels.txt'), 'w', encoding='utf-8', newline='\n') as f:
        f.writelines(f'{h}\t{esc(v)}\n' for h, v in sorted(labels.items()))
        f.writelines(f'^{h}\t{esc(v)}\n' for h, v in sorted(up.items()))
    exact = {H(k): v for k, v in bio_texts.items()}
    with open(os.path.join(he_dir, 'bios.txt'), 'w', encoding='utf-8', newline='\n') as f:
        f.writelines(f'{h}\t{esc(v)}\n' for h, v in sorted(exact.items()))
        f.writelines(f'*\t{h}\t{esc(v)}\n' for h, v in sources.faceit_templates())
    with open(os.path.join(he_dir, 'keep.txt'), 'w', encoding='utf-8', newline='\n') as f:
        f.writelines(f'{h}\n' for h in sorted(tr['keep']))
    # plain (English) copies for the proxy's tests: never shipped
    os.makedirs(plain_dir, exist_ok=True)
    with open(os.path.join(plain_dir, 'labels.txt'), 'w', encoding='utf-8', newline='\n') as f:
        f.writelines(f'{esc(k)}\t{esc(v)}\n' for k, v in sorted(en_labels.items()))
    with open(os.path.join(plain_dir, 'bios.txt'), 'w', encoding='utf-8', newline='\n') as f:
        f.writelines(f'{esc(k)}\t{esc(v)}\n' for k, v in sorted(bio_texts.items()))
    with open(os.path.join(plain_dir, 'faceit.txt'), 'w', encoding='utf-8', newline='\n') as f:
        f.writelines(f'{esc(v)}\t{esc(sources.faceit_he(v))}\n' for v in sorted({v for _, _, _, v in sources.emdb_texts()
                                                                               if sources.faceit_he(v)}))
    names = set(load_json(os.path.join(WORK, 'inventory', 'names.json')) or [])
    kept = sorted(t for t in set(pool.values()) | names if H(t) in tr['keep'])
    with open(os.path.join(plain_dir, 'keep.txt'), 'w', encoding='utf-8', newline='\n') as f:
        f.writelines(f'{esc(k)}\n' for k in kept)
    return len(labels), len(up), unresolved, len(exact)


def sync_pack(files):
    """pack.config.json patches and redirect.cfg map lines for every built file."""
    rel = {'catalog.bin': f'{DATA}/StreamingAssets/aa/catalog.bin',
           EN_BUNDLE: f'{DATA}/StreamingAssets/aa/StandaloneWindows64/{EN_BUNDLE}',
           'global-metadata.dat': f'{DATA}/il2cpp_data/Metadata/global-metadata.dat',
           'default.emdb': f'{DATA}/StreamingAssets/default.emdb'}
    cfg = json.load(open(PACK_CFG, encoding='utf-8'))
    patches = []
    for f in files:
        p = rel.get(f, f'{DATA}/{f}')
        patches.append({'path': p, 'patched': f'../work/build/{f}', 'output': f'tirgumim/he/{f}'})
    if cfg['patches'] != patches:
        cfg['patches'] = patches
        # the file's own layout: one line per key, one line per patch
        lines = [f'  {json.dumps(k)}: {json.dumps(v, ensure_ascii=False)}' for k, v in cfg.items() if k != 'patches']
        lines.append('  "patches": [\n' + ',\n'.join('    ' + json.dumps(p).replace('{"', '{ "').replace('"}', '" }')
                                                    .replace('", "', '", "') for p in patches) + '\n  ]')
        with open(PACK_CFG, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write('{\n' + ',\n'.join(lines) + '\n}\n')
        print('pack.config.json: patches updated')
    head = [l for l in open(REDIRECT, encoding='utf-8').read().splitlines() if l and not l.startswith(('map=', 'labels=', 'bios=', 'dates=', 'keep='))]
    maps = [f"map={rel.get(f, f'{DATA}/{f}').replace('/', chr(92))}={f}" for f in files]
    text = '\n'.join(head + maps + ['labels=labels.txt', 'bios=bios.txt', 'dates=dates.txt', 'keep=keep.txt']) + '\n'
    if open(REDIRECT, encoding='utf-8').read() != text:
        open(REDIRECT, 'w', encoding='utf-8', newline='\n').write(text)
        print('redirect.cfg: map lines updated')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--allow-missing', action='store_true')
    ap.add_argument('--game', default=DEFAULT_GAME)
    ap.add_argument('--no-fonts', action='store_true', help='test: no font replacement')
    a = ap.parse_args()
    if not a.allow_missing and subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'coverage.py')]).returncode:
        sys.exit('coverage is not 100%: not building (use --allow-missing for a test build)')
    out = os.path.join(WORK, 'build')
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(out)
    tr = coverage.translations()
    build_tables(a.game, out)
    assets = build_assets(a.game, out, tr, fonts=not a.no_fonts)
    # Text hard-coded in the game's code: IL2CPP string literals in global-metadata.dat.
    md = open(os.path.join(a.game, DATA, 'il2cpp_data', 'Metadata', 'global-metadata.dat'), 'rb').read()
    lits = metadata.literals(md)
    rep = {i: tr['literals'][s] for i, s in enumerate(lits) if tr['literals'].get(s)}
    open(os.path.join(out, 'global-metadata.dat'), 'wb').write(metadata.rewrite(md, rep))
    print(len(rep), 'code literals replaced')
    # default.emdb is not patched: its texts are copied into a career's save, which must stay English for a Steam
    # launch. Bios and descriptions are shown in Hebrew at display time through bios.txt (see bios()).
    built = [EN_BUNDLE, 'catalog.bin', 'global-metadata.dat'] + assets
    sync_pack(built)
    # launcher-only activation: proxy version.dll + its config (data files come from the patches above)
    files = os.path.join(WORK, 'pack', 'files')
    shutil.rmtree(files, ignore_errors=True)
    he_dir = os.path.join(files, 'tirgumim', 'he')
    os.makedirs(he_dir)
    dll = os.path.join(WORK, 'proxy-target', 'release', 'tirgumim_proxy.dll')
    if not os.path.exists(dll):
        sys.exit(r'build the proxy first: tools\proxy\build.cmd version <repo>\work\proxy-target')
    shutil.copy(dll, os.path.join(files, 'version.dll'))
    shutil.copy(REDIRECT, os.path.join(he_dir, 'redirect.cfg'))
    n_lab, n_up, unresolved, n_bio = write_lookups(he_dir, os.path.join(WORK, 'plain'), tr, bios(a.game, tr['emdb']))
    if unresolved:
        print(f'WARNING: {unresolved} display labels without English in work/ (no upper-case form)')
    shutil.copy(os.path.join(HE_DIR, 'dates.txt'), os.path.join(he_dir, 'dates.txt'))
    assert not os.path.exists(os.path.join(he_dir, 'textlog.on'))
    print(n_lab, 'display labels (+', n_up, 'upper-case),', n_bio, 'bios +', len(sources.faceit_templates()),
          'templates,', len(tr['keep']), 'kept names')
    print('built', sorted(os.listdir(out)))


if __name__ == '__main__':
    main()
