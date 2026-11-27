"""Inventory of every text source the game can show, classified, with context for translators.

    python tools/il2cpp_xrefs.py      # first: which methods use each code literal
    python tools/inventory.py         -> work/inventory/{literals,scenes,options,dialogs,emdb}.json

Sources (see README "Where the text is"):
- literals: all IL2CPP string literals. kind = ui (English a player reads), id (keys, ids, paths), symbol (no
  words), debug (log/developer text), other_language (the game's built-in translations), name (team,
  player, place names), engine (used only by Unity/.NET/library code). Classification uses the methods that
  reference a literal: EmailsDataBaseEN / GlossaryContentEn are the game's English UI text, EmailsDataBaseXX /
  GlossaryContentXx (XX != EN) its other languages, CountiesAndNames / NameDatabase / PhotoOrigins... name pools.
  `via` says how a ui literal reaches the game: "literal" (global-metadata.dat rewrite: only for literals
  used solely by display code, sentences, or text with placeholders/tags) or "label" (exact TextMeshPro text
  swapped at display time: short strings the code may also use as keys).
- scenes: TextMeshPro default texts in scenes/prefabs (asset patch) that no LocalizeStringEvent replaces.
- options: dropdown option texts (display labels).
- dialogs: the manager's chat dialogs (Resources/dialogs/en TextAssets).
- emdb: player bios and team/sponsor/tournament descriptions in StreamingAssets/default.emdb.
The string tables and glossary articles are inventoried by coverage.py from work/en and work/glossary_en.json.
"""
import argparse, collections, glob, itertools, json, os, re
from common import DEFAULT_GAME, EN_DIR, ROOT, WORK, H, keep_hashes, load_he, load_json
import metadata, sources

INV = os.path.join(WORK, 'inventory')
GAME_MODULES = {'EsportsManager.dll', 'SimMod.dll', 'Assembly-CSharp.dll'}
LANG_CLASS = re.compile(r'^(EmailsDataBase|GlossaryContent)([A-Z][A-Za-z])$')
EN_CLASSES = {'EmailsDataBaseEN', 'GlossaryContentEn'}
# classes whose literals are display text only (safe to rewrite in global-metadata.dat)
DISPLAY_CLASSES = EN_CLASSES | {'EmailsDatabase', 'LawsuitTemplates'}
NAME_CLASSES = {'CountiesAndNames', 'NameDatabase', 'PhotoOrigins', 'LanguageCohesion', 'LanguageRegionMap',
                'NationalityBarrier', 'EmailAuthorFactory', 'WorkshopKitSetAuthoring', 'CarsCatalog', 'VenueProvider'}
DEBUG = re.compile(r'^\s*(<color=\w+>)?\[[^\]]+\]|Exception|NullReference|^[A-Z][a-z]+[A-Z]\w*(\.\w+)*: |'
                   r'(?i:\b(could not|couldn\'t|failed to|is missing|not found|is null|must be|cannot be)\b)')
DEBUG_METHODS = re.compile(r'::(DEV_|Debug|Log|Test|tmp_|Migrate)')
FOREIGN = re.compile(r'[^\x00-\x7f‘’“”—–…•€×·→←≥≤°\u00a0\u200b]')
WORD = re.compile(r"[A-Za-z][a-z]+|[A-Z]+")


def strip(s):
    return re.sub(r'<[^<>]*>|\{[^{}]*\}|\[\[[\w.]+\|?|\]\]', ' ', s)


class Vocab:
    def __init__(self):
        self.c = collections.Counter()

    def add(self, s):
        self.c.update(w.lower() for w in WORD.findall(s))

    def english(self, s):
        ws = [w.lower() for w in re.findall(r'[A-Za-z]{2,}', strip(s))]
        return bool(ws) and sum(w in self.c for w in ws) / len(ws) >= 0.8


def cls(ref):
    m, c = ref.lstrip('~').split('|', 1)
    return m, c.split('::')[0], ref


class Names:
    """Proper names: the database's (English, from the install) and the texts kept in Latin (translation/keep.json,
    known only by H())."""

    def __init__(self, names, kept):
        self.names, self.kept = set(names), kept

    def __contains__(self, s):
        return s in self.names or H(s) in self.kept


def emdb_names(game):
    """Proper names in the database: nicks, names, teams, sponsors, tournaments, cities (kept in Latin)."""
    files, _ = sources.emdb_open(os.path.join(game, sources.EMDB))
    out = set()
    cols = {'Players.csv': ['Nick', 'Name', 'Surname', 'Team'], 'Teams.csv': ['Nick', 'Name', 'Academy', 'StartIGL'],
            'Sponsors.csv': ['CompanyName'], 'Tournaments.csv': ['id', 'Name', 'CupId', 'City'],
            'Staff.csv': ['Nick', 'Name', 'Surname', 'Team']}
    for f, cs in cols.items():
        h, rows, _ = sources.csv_rows(files[f])
        for r in rows:
            if len(r) == len(h):
                out.update(r[h.index(c)] for c in cs if r[h.index(c)])
    return out


def classify_literals(lits, refs, vocab, names):
    out = []
    for i, s in enumerate(lits):
        rs = [cls(r) for r in refs[i]]
        game = [(c, r) for m, c, r in rs if m in GAME_MODULES]
        cs = {c for c, _ in game}
        plain = strip(s)
        if not cs:
            k = 'engine'
        elif not re.search(r'[A-Za-z]{2}', plain):
            k = 'symbol'
        elif all(LANG_CLASS.match(c) and c not in EN_CLASSES for c in cs) or FOREIGN.search(s):
            k = 'other_language'
        elif ' ' not in s.strip() and (re.search(r'[_./:\\#@=|]', s) or re.search(r'[a-z][A-Z]|[A-Z]{2}[a-z]', s)
                                       or (not cs & EN_CLASSES and re.fullmatch(r'[a-z0-9]+', s))
                                       or re.fullmatch(r'[0-9A-Fa-f]{6,8}|[a-z]{2,3}-[A-Z]{2}|[A-Za-z]+\d+|\d+[A-Za-z]+|COM\d|-\w+', s)):
            k = 'id'
        elif re.search(r'\w=\s*$|^\W*\w+=|; \w+=|\) to=', s):
            k = 'debug'
        elif not cs & DISPLAY_CLASSES and (DEBUG.search(s) or all(DEBUG_METHODS.search(r) for _, r in game)):
            k = 'debug'
        elif not cs & DISPLAY_CLASSES and (cs <= NAME_CLASSES | {c for c in cs if LANG_CLASS.match(c)} or s in names):
            k = 'name'
        elif vocab.english(s):
            k = 'ui'
        else:
            k = 'other_language'
        e = {'i': i, 'text': s, 'kind': k}
        if k == 'ui':
            words = len(re.findall(r'[A-Za-z]+', plain))
            safe = all(c in DISPLAY_CLASSES or (LANG_CLASS.match(c) and c not in EN_CLASSES) for c in cs)
            e['via'] = 'literal' if (safe or words >= 3 or re.search(r'\{\d+[^}]*\}|<[^<>]+>', s)
                                     or s != s.strip()) else 'label'
            e['ctx'] = sorted({r.split('|', 1)[1] for _, r in game})[:6]
        out.append(e)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--game', default=DEFAULT_GAME)
    a = ap.parse_args()
    os.makedirs(INV, exist_ok=True)
    md = open(os.path.join(a.game, 'EsportsManager_Data', 'il2cpp_data', 'Metadata', 'global-metadata.dat'), 'rb').read()
    lits = metadata.literals(md)
    refs = json.load(open(os.path.join(INV, 'literal_refs.json'), encoding='utf-8'))
    assert len(refs) == len(lits), 'run tools/il2cpp_xrefs.py for this game version'

    print('reading dialogs, emdb, scenes...')
    dlg = sources.dialogs(a.game)
    emdb = sources.emdb_texts(a.game)
    ui = list(sources.scan_ui(a.game))
    kept = keep_hashes()
    names = emdb_names(a.game)

    vocab = Vocab()
    for f in glob.glob(os.path.join(EN_DIR, '*.json')):
        for r in load_json(f):
            vocab.add(r['en'])
    for _, s in load_json(os.path.join(WORK, 'glossary_en.json')) or []:
        vocab.add(s)
    for _, js in dlg.values():
        for t in sources.dialog_texts(js):
            vocab.add(t)
    for _, _, _, t in emdb:
        if not t.startswith('Has '):
            vocab.add(re.sub(r'^\S+ \S+ \S+', '', t))  # bios start with a (made-up) full name
    decided = load_he('_literals')
    for s in dict.fromkeys(lits):
        if decided.get(s):
            vocab.add(s)
    for i, r in enumerate(refs):
        if any(cls(x)[1] in EN_CLASSES for x in r):
            vocab.add(lits[i])
    common_words = {r['en'] for f in glob.glob(os.path.join(EN_DIR, '*.json')) for r in load_json(f)}
    common_words |= {lits[i] for i, r in enumerate(refs) if any(cls(x)[1] in EN_CLASSES for x in r)}
    names -= {w for w in common_words if H(w) not in kept}  # "Nick", "Support"...: UI words that are also a name
    for n in names:  # names are not English words
        if ' ' not in n:
            vocab.c.pop(n.lower(), None)
    # nor are the kept ones, known only by hash: try each spelling of the word found in the game's texts
    spellings = collections.defaultdict(set)
    for s in itertools.chain(common_words, lits, (r['text'] for r in ui), (t for _, _, _, t in emdb),
                             (t for _, js in dlg.values() for t in sources.dialog_texts(js)),
                             (s for _, s in load_json(os.path.join(WORK, 'glossary_en.json')) or [])):
        for t in re.findall(r'[A-Za-z]+', s):
            spellings[t.lower()].add(t)
    for w in list(vocab.c):
        if any(H(v) in kept for v in spellings[w] | {w, w.capitalize(), w.upper()}):
            vocab.c.pop(w, None)
    names = Names(names, kept)
    for w in 'the a an and or of to in on at for with by from is are be you your it this that not no all'.split():
        vocab.c[w] += 1

    lit = classify_literals(lits, refs, vocab, names)
    json.dump(lit, open(os.path.join(INV, 'literals.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=0)

    scenes = collections.OrderedDict()
    for r in ui:
        if r['kind'] != 'tmp' or r['localized']:
            continue
        e = scenes.setdefault(r['text'], {'text': r['text'], 'kind': None, 'where': []})
        if len(e['where']) < 4:
            e['where'].append(f"{r['file']}:{r['go']}")
    for e in scenes.values():
        s = e['text']
        e['kind'] = ('ui' if vocab.english(s) and s not in names and not re.search(r'(?i)lorem ipsum', s) else
                     'name' if s in names else 'other')
    json.dump(list(scenes.values()), open(os.path.join(INV, 'scenes.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=0)

    opts = collections.OrderedDict()
    for r in ui:
        if r['kind'] == 'option':
            e = opts.setdefault(r['text'], {'text': r['text'], 'kind': None, 'where': f"{r['file']}:{r['go']}"})
            e['kind'] = 'ui' if vocab.english(r['text']) and r['text'] not in names else 'name'
    json.dump(list(opts.values()), open(os.path.join(INV, 'options.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=0)

    dl = collections.OrderedDict()
    for path, (_, js) in sorted(dlg.items()):
        blocks = json.loads(js)['blocks']
        prev = ''
        for b in blocks:
            if b.get('text'):
                e = dl.setdefault(b['text'], {'text': b['text'], 'kind': 'ui', 'dialog': path.split('/')[-1],
                                              'speaker': 'member' if b.get('type') == 0 else 'manager',
                                              'after': prev[:160]})
                prev = b['text']
    json.dump(list(dl.values()), open(os.path.join(INV, 'dialogs.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=0)

    em = collections.OrderedDict()
    files, _ = sources.emdb_open(os.path.join(a.game, sources.EMDB))
    h, rows, _ = sources.csv_rows(files['Players.csv'])
    genders = {r[0]: r[h.index('Gender')] for r in rows if len(r) == len(h)}
    for f, col, key, t in emdb:
        e = em.setdefault(t, {'text': t, 'kind': 'ui', 'field': f'{f}:{col}', 'row': key})
        if f == 'Players.csv':
            e['gender'] = genders.get(key, 'MALE')
    json.dump(list(em.values()), open(os.path.join(INV, 'emdb.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
    json.dump(sorted(names.names), open(os.path.join(INV, 'names.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=0)

    print('literals', collections.Counter(e['kind'] for e in lit),
          collections.Counter(e.get('via') for e in lit if e['kind'] == 'ui'))
    print('scenes', len(scenes), collections.Counter(e['kind'] for e in scenes.values()))
    print('options', len(opts), collections.Counter(e['kind'] for e in opts.values()))
    print('dialogs', len(dl), 'emdb', len(em), 'names', len(names.names), '+', len(kept), 'kept')


if __name__ == '__main__':
    main()
