"""Check that files hold none of the game's English text (repo rule: the repo and the pack carry Hebrew only).

    python tools/no_english.py                     every tracked file of the working tree
    python tools/no_english.py --rev <commit>      every file of a commit's tree
    python tools/no_english.py --zip <pack.zip>    every text file of a pack
    python tools/no_english.py --sample 10         also: N random bios, dialog lines and long literals,
                                                   each searched as a whole string

The game's English comes from the install, regenerated into work/ (tools/extract.py, glossary.py,
inventory.py): string tables, glossary articles, visible code literals, scene texts, dropdown options, dialogs,
default.emdb texts. A hit is a run of 6 words of a game text (case and markup ignored, at least two of them common English words
such as "the", "is": Latin name lists do not count) found in a file. Short
UI words and names are allowed, so shorter texts are not searched. Exit 1 on any hit.
"""
import argparse, glob, io, os, random, re, subprocess, sys, zipfile
from common import EN_DIR, ROOT, WORK, load_json

N = 6
WORDS = re.compile(r"[^\W\d_]+")  # letter runs (a Hebrew word breaks an English run)
INV = os.path.join(WORK, 'inventory')


def game_texts():
    """{source: [English text]} of everything the game shows (from work/)."""
    out = {'tables': [r['en'] for f in glob.glob(os.path.join(EN_DIR, '*.json')) for r in load_json(f)],
           'glossary': [s for _, s in load_json(os.path.join(WORK, 'glossary_en.json')) or []]}
    for name in ('literals', 'scenes', 'options', 'dialogs', 'emdb'):
        out[name] = [e['text'] for e in load_json(os.path.join(INV, name + '.json')) or [] if e['kind'] == 'ui']
    if not all(out.values()):
        sys.exit('regenerate the English first: tools/extract.py, glossary.py, il2cpp_xrefs.py, inventory.py')
    return out


def words(s):
    return [w.lower() for w in WORDS.findall(re.sub(r'<[^<>]*>|\[\[[\w.]+\|?|\]\]|\\[nrt]', ' ', s))]


# a run counts only with at least two of these: a list of Latin names or titles is not a sentence
STOP = set('the a an of in is was are and to for with on at by his her he she it its from as that has have be '
           'this their they you your will not or'.split())


def shingles(ws):
    out = set()
    for i in range(len(ws) - N + 1):
        run = ws[i:i + N]
        if sum(w in STOP for w in run) >= 2:
            out.add(' '.join(run))
    return out


def tracked(rev=None):
    if rev:
        names = subprocess.run(['git', 'ls-tree', '-r', '--name-only', rev], cwd=ROOT, capture_output=True,
                               text=True, check=True).stdout.splitlines()
        for n in names:
            yield n, subprocess.run(['git', 'show', f'{rev}:{n}'], cwd=ROOT, capture_output=True, check=True).stdout
    else:
        names = subprocess.run(['git', 'ls-files'], cwd=ROOT, capture_output=True, text=True, check=True).stdout.splitlines()
        for n in names:
            p = os.path.join(ROOT, n)
            if os.path.isfile(p):
                yield n, open(p, 'rb').read()


def zipped(path):
    with zipfile.ZipFile(path) as z:
        for i in z.infolist():
            yield i.filename, z.read(i)


def as_text(b):
    if b[:4] in (b'PK\x03\x04',) or b'\0' in b[:4096]:
        return None  # binary (fonts, dll, nested archives)
    try:
        return b.decode('utf-8')
    except UnicodeDecodeError:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--rev')
    ap.add_argument('--zip')
    ap.add_argument('--sample', type=int, default=0)
    a = ap.parse_args()
    texts = game_texts()
    index = {}
    for src, ss in texts.items():
        for s in ss:
            for sh in shingles(words(s)):
                index.setdefault(sh, s)
    files = list(zipped(a.zip) if a.zip else tracked(a.rev))
    hits = scanned = 0
    corpus = []
    for name, b in files:
        t = as_text(b)
        if t is None:
            continue
        scanned += 1
        corpus.append(t)
        found = sorted({index[sh] for sh in shingles(words(t)) if sh in index})
        for s in found[:5]:
            print(f'HIT {name}: {s[:110]!r}')
        if len(found) > 5:
            print(f'HIT {name}: ... {len(found)} game texts in all')
        hits += len(found)
    print(f'{scanned} text files scanned ({len(files)} files), {len(index)} 6-word runs of game text, {hits} hits')
    if a.sample:
        rnd = random.Random(2026)
        whole = '\n'.join(corpus)
        bios = [s for s in texts['emdb'] if len(s) > 80]
        lits = [s for s in texts['literals'] if len(words(s)) >= 8]
        for src, pool in (('bio', bios), ('dialog', texts['dialogs']), ('literal', lits)):
            for s in rnd.sample(pool, min(a.sample, len(pool))):
                n = whole.count(s)
                print(f'sample {src}: {n} hits  {s[:90]!r}')
                hits += n
    sys.exit(1 if hits else 0)


if __name__ == '__main__':
    main()
