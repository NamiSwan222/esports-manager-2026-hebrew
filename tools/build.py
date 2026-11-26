"""Build the Hebrew files from translation/he/*.json into work/pack/files (layout of the game folder).

    python tools/build.py [--allow-missing] [--game "<install>"]

- The English string-table bundle with every used string replaced by Hebrew, in logical order. TextMeshPro
  has no bidi: the proxy makes Hebrew texts right-to-left at runtime, when they are set on a text component
  (tools/proxy/src/tmp.rs, `rtl=tmp` in pack/redirect.cfg).
- catalog.bin with that bundle's CRC set to 0 (Addressables would reject the changed bundle).
- labels.txt: exact English UI labels (glossary titles, categories...) that the proxy shows in Hebrew; they
  stay English in the code, where short strings are often keys (translation/he/_labels.json).
- LiberationSans (TextMeshPro's default fallback, in resources.assets) replaced by Noto Sans + Noto Sans
  Hebrew (OFL): all Hebrew glyphs then come from that fallback (the game's own fonts have none).
These are written as modified copies to work/build; make-pack turns them into bsdiff patches with
`output` into tirgumim\\he\\, and the proxy (version.dll) redirects the game to them only when started
with -tirgumim_he.
"""
import argparse, os, shutil, struct, subprocess, sys
import UnityPy
from common import AA, DEFAULT_GAME, EN_BUNDLE, HE_DIR, ROOT, WORK, english, hebrew, load_json
import metadata
os.environ.setdefault("TIRGUMIM_PLAIN_FONTS", "1")  # merged GPOS tables misplace Hebrew letters in TMP
import build_fonts

DATA = 'EsportsManager_Data'
FONT_FILES = ['resources.assets', 'sharedassets1.assets', 'sharedassets2.assets', 'sharedassets3.assets']
SKIP_FONTS = ('NotoSansTC', 'NotoSansSC', 'NotoSansKR')


def weight(name):
    n = name.lower()
    for k, v in [('black', 900), ('extrabold', 800), ('semibold', 600), ('bold', 700), ('medium', 500), ('light', 300)]:
        if k in n:
            return v
    return 400


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--allow-missing', action='store_true')
    ap.add_argument('--game', default=DEFAULT_GAME)
    ap.add_argument('--no-fonts', action='store_true', help='test: string tables only')
    a = ap.parse_args()
    if not a.allow_missing and subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'coverage.py')]).returncode:
        sys.exit('coverage is not 100%: not building (use --allow-missing for a test build)')
    out = os.path.join(WORK, 'build')
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(out)
    en, he = english(), hebrew()
    ids = {t: {r['id'] for r in rows} for t, rows in en.items()}
    env = UnityPy.load(os.path.join(a.game, AA, EN_BUNDLE))
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
    cat = bytearray(open(os.path.join(a.game, AA, '..', 'catalog.bin'), 'rb').read())
    old_size = os.path.getsize(os.path.join(a.game, AA, EN_BUNDLE))
    i = cat.find(struct.pack('<I', old_size))
    if i < 4 or cat.find(struct.pack('<I', old_size), i + 1) != -1:
        sys.exit('catalog.bin: bundle record not found (or not unique)')
    struct.pack_into('<II', cat, i - 4, 0, len(new_bundle))
    open(os.path.join(out, 'catalog.bin'), 'wb').write(cat)
    work = os.path.join(out, '_fonts')
    os.makedirs(work)
    for f in ([] if a.no_fonts else FONT_FILES):
        env = UnityPy.load(os.path.join(a.game, DATA, f))
        changed = False
        for o in env.objects:
            if o.type.name != 'Font':
                continue
            t = o.read_typetree()
            if t['m_Name'].startswith(SKIP_FONTS) or not t.get('m_FontData'):
                continue
            wd = 75 if 'condensed' in t['m_Name'].lower() or t['m_Name'] in ('Oswald-Bold', 'Anton') else 100
            ttf = build_fonts.build(os.path.join(ROOT, 'fonts', 'src'), work, weight(t['m_Name']), wd)
            t['m_FontData'] = list(open(ttf, 'rb').read())
            o.save_typetree(t)
            changed = True
            print(f, t['m_Name'])
        if changed:
            open(os.path.join(out, f), 'wb').write(env.file.save())
    shutil.rmtree(work)
    # Text hard-coded in the game's code: IL2CPP string literals in global-metadata.dat.
    meta_path = os.path.join(a.game, DATA, 'il2cpp_data', 'Metadata', 'global-metadata.dat')
    md = open(meta_path, 'rb').read()
    lits = metadata.literals(md)
    tr = load_json(os.path.join(HE_DIR, '_literals.json'))
    rep = {i: s for i, s in ((i, tr.get(en)) for i, en in enumerate(lits)) if s}
    open(os.path.join(out, 'global-metadata.dat'), 'wb').write(metadata.rewrite(md, rep))
    print(len(rep), 'code literals replaced')
    # launcher-only activation: proxy version.dll + its config (data files come from the patches above)
    files = os.path.join(WORK, 'pack', 'files')
    shutil.rmtree(files, ignore_errors=True)
    os.makedirs(os.path.join(files, 'tirgumim', 'he'))
    dll = os.path.join(WORK, 'proxy-target', 'release', 'tirgumim_proxy.dll')
    if not os.path.exists(dll):
        sys.exit(r'build the proxy first: tools\proxy\build.cmd version <repo>\work\proxy-target')
    shutil.copy(dll, os.path.join(files, 'version.dll'))
    shutil.copy(os.path.join(ROOT, 'pack', 'redirect.cfg'), os.path.join(files, 'tirgumim', 'he', 'redirect.cfg'))
    # exact English UI labels the proxy swaps for Hebrew when TextMeshPro shows them (display only)
    esc = lambda t: t.replace('\\', '\\\\').replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')
    labels = load_json(os.path.join(HE_DIR, '_labels.json'))
    with open(os.path.join(files, 'tirgumim', 'he', 'labels.txt'), 'w', encoding='utf-8', newline='\n') as f:
        f.writelines(f'{esc(k)}\t{esc(v)}\n' for k, v in labels.items() if v)
    print(len(labels), 'display labels')
    print('built', os.listdir(out))


if __name__ == '__main__':
    main()
