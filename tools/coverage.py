"""Coverage check over every text source the game can show; exit 1 until all player-visible text is Hebrew.

    python tools/coverage.py                  per-source report; exit 1 if anything is missing or broken
    python tools/coverage.py --todo 12000     also write what's missing as translator batches:
                                              work/todo/<source>-NNN.json (about that many characters each)

Sources (tools/inventory.py classifies them; run it after a game update):
  tables     Unity Localization string tables (work/en)             -> translation/he/<table>.json
  glossary   in-game glossary articles (code literals)             -> translation/he/_literals.json
  literals   other player-visible code literals                    -> _literals.json (via literal) or
                                                                      _labels.json (via label: display swap)
  scenes     TextMeshPro default texts in scenes/prefabs           -> translation/he/_scenes.json
  options    dropdown option texts                                  -> translation/he/_labels.json
  dialogs    the manager's chat dialogs (Resources/dialogs/en)     -> translation/he/_dialogs.json
  emdb       player bios, tournament descriptions (default.emdb)   -> translation/he/_emdb.json (team and
                                                                      sponsor descriptions come from the
                                                                      Descriptions table, FaceIt bios from
                                                                      a template in sources.py)
  seen       English lines from the proxy's text log (translation/seen_in_game.txt: hashes; --add-seen)
Names and brands that stay in Latin are listed in translation/keep.json ("keep": {reason: [H(text)]}).
Every tracked file is keyed by H(English) (common.H: SHA-256, 16 hex digits) or by table entry id; the English
comes from work/ (extract.py, glossary.py, il2cpp_xrefs.py, inventory.py), never from the repo.
null in _literals.json / _scenes.json = looked at, not shown to the player (counted as decided); a scene text set
to null stays English in the build (HomeWindow_rd2 finds its section titles by their English scene text and sets
them through the display labels).
Markup that must survive: {placeholders} (same names; gender choices {м:..|ж:..} may change their text),
<tags>, [[glossary links]]; the number of line breaks is not checked except in glossary articles.
"""
import argparse, collections, json, os, re, sys
from common import H, ROOT, WORK, ByHash, english, hebrew, keep_hashes, load_he, load_json, save_json

PH = re.compile(r'\{([A-Za-z_][\w.]*|\d+)(?::[^{}]*)?\}')
CHOICE = re.compile(r'\{[мж]:[^{}]*\}')
TAG = re.compile(r'</?[A-Za-z][^<>]*>')
# smart-string plural, {0:plural:one|other}; its options are words to translate and may hold placeholders
# ("{0:plural:אימייל אחד|{0} אימיילים}")
PLURAL = re.compile(r'\{(\w+):(?:plural|p)(?:\([^)]*\))?:((?:[^{}]|\{[^{}]*\})*)\}')
HEB = re.compile(r'[֐-׿]')
INV = os.path.join(WORK, 'inventory')
SOURCES = ['tables', 'glossary', 'literals', 'scenes', 'options', 'dialogs', 'emdb', 'seen']
SEEN = os.path.join(ROOT, 'translation', 'seen_in_game.txt')   # tracked: H(line)<TAB>H(plain(line))
SEEN_EN = os.path.join(WORK, 'seen_in_game.txt')               # local: the English lines (text log copies)


def ph_names(s):
    """Placeholder names, a plural format counted as its own name plus the placeholders in its options."""
    inner = []
    def one(m):
        inner.extend(PH.findall(m.group(2)))
        return '{%s}' % m.group(1)
    return PH.findall(PLURAL.sub(one, s)) + inner


def markup_ok(en, he):
    # with a plural the number may move into the options: then the same names, not the same count
    same = ((lambda a, b: set(a) == set(b)) if PLURAL.search(en) or PLURAL.search(he)
            else (lambda a, b: collections.Counter(a) == collections.Counter(b)))
    return (same(ph_names(en), ph_names(he))
            and len(CHOICE.findall(en)) <= len(CHOICE.findall(he)) + len(CHOICE.findall(en))
            and collections.Counter(TAG.findall(en)) == collections.Counter(TAG.findall(he)))


def plain(s):
    """A glossary text without links, tags and bold, spaces collapsed, lower case (a text-log line of a rendered
    glossary article is compared in this form)."""
    return re.sub(r'\s+', ' ', re.sub(r'<[^<>]*>|\*\*', '', re.sub(r'\[\[[\w.]+\|([^\]]*)\]\]', r'\1', s))).strip().lower()


def unescape_line(line):
    return line.replace('\\n', '\n').replace('\\t', '\t').replace('\\\\', '\\')


def escape_line(line):
    return line.replace('\\', '\\\\').replace('\n', '\\n').replace('\t', '\\t')


def seen_lines():
    """[(H(line), H(plain(line)), English line or None)] of the text-log lines without Hebrew: the tracked hashes,
    with the English where work/seen_in_game.txt has it."""
    en = {}
    if os.path.exists(SEEN_EN):
        for line in open(SEEN_EN, encoding='utf-8').read().split('\n'):
            line = unescape_line(line)
            if line and not HEB.search(line):
                en[H(line)] = line
    out = []
    if os.path.exists(SEEN):
        for row in open(SEEN, encoding='utf-8').read().split('\n'):
            f = row.split('\t')
            if len(f) == 2:
                out.append((f[0], f[1], en.get(f[0])))
    return out


def add_seen(path):
    """Fold English text-log lines (the proxy's textlog.txt) into translation/seen_in_game.txt (hashes) and keep
    the English in work/seen_in_game.txt."""
    have = {h for h, _, _ in seen_lines()}
    lines = [unescape_line(l) for l in open(path, encoding='utf-8').read().split('\n')]
    new = list(dict.fromkeys(l for l in lines if l and not HEB.search(l) and H(l) not in have))
    with open(SEEN, 'a', encoding='utf-8', newline='\n') as f:
        f.writelines(f'{H(l)}\t{H(plain(l))}\n' for l in new)
    with open(SEEN_EN, 'a', encoding='utf-8', newline='\n') as f:
        f.writelines(escape_line(l) + '\n' for l in new)
    print(len(new), 'new seen lines')


def check():
    """String tables: (total, done, missing [(table, row)], broken [(table, row, he, why)])."""
    keep = set(load_json(os.path.join(ROOT, 'translation', 'keep.json')).get('ids', []))
    en, he = english(), hebrew()
    total = done = 0
    missing, broken = [], []
    for t, rows in en.items():
        for r in rows:
            total += 1
            plain = TAG.sub('', CHOICE.sub('', PH.sub('', PLURAL.sub(lambda m: f' {m.group(2)} ', r['en']))))
            if not re.search(r'[A-Za-z]{2}', plain) or f"{t}|{r['id']}" in keep:
                done += 1
                continue
            h = he[t].get(r['id'])
            if not h:
                missing.append((t, r))
            elif not markup_ok(r['en'], h):
                broken.append((t, r, h, 'markup'))
            elif not HEB.search(h):
                broken.append((t, r, h, 'no Hebrew'))
            else:
                done += 1
    return total, done, missing, broken


def md_shape(s):
    """What must survive translation in a glossary article: link ids, =see/=attrs lines, line structure."""
    return (sorted(re.findall(r'\[\[([\w.]+)', s)), re.findall(r'(?m)^=(?:see|attrs) .*$', s.replace('\r', '')),
            s.count('**'), s.count('\n'), re.findall(r'(?m)^(# |!tip |!trap |=table |- )', s.replace('\r', '')))


class Row:
    def __init__(self, name):
        self.name, self.total, self.visible, self.translated, self.kept, self.null = name, 0, 0, 0, 0, 0
        self.missing, self.broken = [], []


def table_translations():
    """{English: Hebrew} from the translated string tables (reused for the same text elsewhere)."""
    en, he = english(), hebrew()
    out = {}
    for t, rows in en.items():
        for r in rows:
            h = he[t].get(r['id'])
            if h and HEB.search(h):
                out.setdefault(r['en'], h)
    return out


def evaluate():
    """Per-source Row objects with counts, missing items (dicts with context) and broken ones."""
    keep = keep_hashes()
    lits, labels, scenes_he = load_he('_literals'), load_he('_labels'), load_he('_scenes')
    dialogs_he, emdb_he = load_he('_dialogs'), load_he('_emdb')
    rows = {}

    t = rows['tables'] = Row('tables')
    total, done, missing, broken = check()
    t.total = t.visible = total
    t.translated = done
    t.missing = [{'text': r['en'], 'table': tb, 'id': r['id'], 'key': r['key']} for tb, r in missing]
    t.broken = [f'{why} {tb} {r["id"]}: {r["en"][:60]!r} -> {h[:60]!r}' for tb, r, h, why in broken]

    g = rows['glossary'] = Row('glossary')
    arts = [s for _, s in load_json(os.path.join(WORK, 'glossary_en.json')) or []]
    g.total = g.visible = len(arts)
    for s in arts:
        h = lits.get(s)
        if not h:
            g.missing.append({'text': s})
        elif not HEB.search(h) or md_shape(s) != md_shape(h):
            g.broken.append(f'glossary markup: {s[:60]!r}')
        else:
            g.translated += 1
    art_set = set(arts)

    def judge(row, text, he, ctx, check_markup=True):
        """Count one visible text: translated / kept / null-decided / missing / broken."""
        row.visible += 1
        null = ctx.pop('_null', False)
        if H(text) in keep:
            row.kept += 1
        elif not he and null:
            row.null += 1
        elif not he:
            row.missing.append(dict(ctx, text=text))
        elif check_markup and not markup_ok(text, he) or not HEB.search(he):
            row.broken.append(f'{row.name}: {text[:60]!r} -> {he[:60]!r}')
        else:
            row.translated += 1

    tables_he = table_translations()
    L = rows['literals'] = Row('literals')
    inv = load_json(os.path.join(INV, 'literals.json')) or []
    L.total = len(inv)
    L.kinds = collections.Counter(e['kind'] for e in inv)
    for e in inv:
        s = e['text']
        if e['kind'] != 'ui' or s in art_set:
            continue
        he = lits.get(s) or labels.get(s) or tables_he.get(s)
        judge(L, s, he, {'via': e['via'], 'ctx': e.get('ctx', []), 'i': e['i'], '_null': s in lits})

    S = rows['scenes'] = Row('scenes')
    inv = load_json(os.path.join(INV, 'scenes.json')) or []
    S.total = len(inv)
    for e in inv:
        s = e['text']
        if e['kind'] != 'ui':
            continue
        he = scenes_he.get(s) or lits.get(s) or labels.get(s) or tables_he.get(s)
        judge(S, s, he, {'where': e['where'], '_null': s in scenes_he})

    O = rows['options'] = Row('options')
    inv = load_json(os.path.join(INV, 'options.json')) or []
    O.total = len(inv)
    for e in inv:
        if e['kind'] == 'ui':
            s = e['text']
            judge(O, s, labels.get(s) or tables_he.get(s), {'where': e['where']})

    D = rows['dialogs'] = Row('dialogs')
    inv = load_json(os.path.join(INV, 'dialogs.json')) or []
    D.total = len(inv)
    for e in inv:
        judge(D, e['text'], dialogs_he.get(e['text']), {k: e[k] for k in ('dialog', 'speaker', 'after') if k in e})

    import sources
    E = rows['emdb'] = Row('emdb')
    inv = load_json(os.path.join(INV, 'emdb.json')) or []
    E.total = len(inv)
    for e in inv:
        s = e['text']
        he = emdb_he.get(s) or tables_he.get(s) or sources.faceit_he(s)
        judge(E, s, he, {k: e[k] for k in ('field', 'row', 'gender') if k in e})

    V = rows['seen'] = Row('seen')
    # a line counts as translated when it is a translated text of any source, or the plain form of a translated
    # glossary article or of one of its lines (the glossary window shows an article paragraph by paragraph)
    para = set()
    for s in arts:
        if lits.get(s):
            para.add(H(plain(s)))
            for line in s.replace('\r', '').split('\n'):
                para.add(H(plain(re.sub(r'^(# |!tip |!trap |- )', '', line))))
    anyhe = ({H(k) for k in tables_he} | set(labels.raw)
             | {k for d in (lits, scenes_he, dialogs_he, emdb_he) for k, v in d.raw.items() if v})
    for h, hp, line in seen_lines():
        V.total += 1
        V.visible += 1
        if h in keep:
            V.kept += 1
        elif h in anyhe or hp in para:
            V.translated += 1
        else:
            V.missing.append({'text': line or f'(text-log line {h}: English not in work/seen_in_game.txt)'})
    return rows


def translations():
    """What build.py applies, resolved the same way evaluate() counts it:
    {'literals': {English: Hebrew} (global-metadata rewrite), 'labels': ByHash (display swap),
     'scenes', 'emdb': {English: Hebrew}, 'dialogs': ByHash, 'keep': H() of the texts kept in Latin (+ database
     names)}."""
    import sources
    lits_all, labels, scenes_he = load_he('_literals'), load_he('_labels'), load_he('_scenes')
    lits = ByHash({k: v for k, v in lits_all.raw.items() if v})
    tables_he = table_translations()
    inv_lits = load_json(os.path.join(INV, 'literals.json')) or []
    out_lit = {e['text']: lits.get(e['text']) for e in inv_lits if e['text'] in lits}
    for e in inv_lits:
        s = e['text']
        if e['kind'] == 'ui' and s not in lits and s not in labels and tables_he.get(s):
            if e['via'] == 'literal':
                out_lit[s] = tables_he[s]
            else:
                labels[s] = tables_he[s]
    for e in load_json(os.path.join(INV, 'options.json')) or []:
        s = e['text']
        if e['kind'] == 'ui' and s not in labels and tables_he.get(s):
            labels[s] = tables_he[s]
    scenes = {}
    for e in load_json(os.path.join(INV, 'scenes.json')) or []:
        s = e['text']
        if s in scenes_he and scenes_he[s] is None:
            continue  # null: the scene keeps its English text (e.g. a key the code looks up by text)
        he = scenes_he.get(s) or lits.get(s) or labels.get(s) or tables_he.get(s)
        if e['kind'] == 'ui' and he:
            scenes[s] = he
    emdb_he = load_he('_emdb')
    emdb = {}
    for e in load_json(os.path.join(INV, 'emdb.json')) or []:
        s = e['text']
        he = emdb_he.get(s) or tables_he.get(s) or sources.faceit_he(s)
        if he:
            emdb[s] = he
    keep = keep_hashes() | {H(n) for n in load_json(os.path.join(INV, 'names.json')) or []}
    return {'literals': out_lit, 'labels': labels, 'scenes': scenes, 'dialogs': load_he('_dialogs'), 'emdb': emdb,
            'keep': keep}


def english_pool():
    """{H(text): text} of every English text of the regenerated sources (work/) and of its upper-case form: to
    find the English of a hashed display label (the proxy also matches upper-cased labels)."""
    texts = {r['en'] for rows in english().values() for r in rows}
    for name in ('literals', 'scenes', 'options', 'dialogs', 'emdb'):
        texts.update(e['text'] for e in load_json(os.path.join(INV, name + '.json')) or [])
    texts.update(s for _, s in load_json(os.path.join(WORK, 'glossary_en.json')) or [])
    texts.update(line for _, _, line in seen_lines() if line)
    out = {H(t): t for t in texts}
    for t in texts:
        out.setdefault(H(t.upper()), t.upper())
    return out


def write_todo(rows, size):
    """Missing visible text as translator batches with context: work/todo/<source>-NNN.json."""
    todo = os.path.join(WORK, 'todo')
    os.makedirs(todo, exist_ok=True)
    for f in os.listdir(todo):
        if f.endswith('.json'):
            os.remove(os.path.join(todo, f))
    refs = None
    n = 0
    for name in ['literals', 'scenes', 'options', 'dialogs', 'emdb', 'tables', 'glossary', 'seen']:
        items = rows[name].missing
        if name == 'literals':
            # neighbouring strings: other English UI literals used by the same methods
            inv = load_json(os.path.join(INV, 'literals.json'))
            by_m = collections.defaultdict(list)
            for e in inv:
                if e['kind'] == 'ui':
                    for m in e.get('ctx', []):
                        by_m[m].append(e['text'])
            for it in items:
                nb = []
                for m in it['ctx'][:2]:
                    nb += [s for s in by_m[m] if s != it['text']][:6]
                it['neighbours'] = nb[:8]
            items.sort(key=lambda it: (it['ctx'][:1], it['text']))
        if name == 'dialogs':
            items.sort(key=lambda it: it['dialog'])
        batch, chars, k = [], 0, 0
        for it in items + [None]:
            if it is None or (batch and (chars + len(it['text']) > size or len(batch) >= 250)):
                if batch:
                    save_json(os.path.join(todo, f'{name}-{k:03d}.json'), {'source': name, 'items': batch})
                    k += 1
                    n += 1
                batch, chars = [], 0
            if it is not None:
                batch.append(it)
                chars += len(it['text']) + 40
    print(f'{n} batches in work/todo')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--todo', type=int, metavar='CHARS')
    ap.add_argument('-v', action='store_true', help='list every missing text')
    ap.add_argument('--add-seen', metavar='TEXTLOG', help="add the proxy's textlog.txt lines to the seen source")
    a = ap.parse_args()
    if a.add_seen:
        add_seen(a.add_seen)
    if not os.path.exists(os.path.join(INV, 'literals.json')):
        print('run tools/il2cpp_xrefs.py and tools/inventory.py first')
        sys.exit(1)
    rows = evaluate()
    print(f'{"source":10} {"total":>7} {"visible":>8} {"Hebrew":>7} {"kept":>5} {"null":>5} {"missing":>8} {"broken":>7}')
    bad = 0
    for name in SOURCES:
        r = rows[name]
        print(f'{name:10} {r.total:7} {r.visible:8} {r.translated:7} {r.kept:5} {r.null:5} {len(r.missing):8} {len(r.broken):7}')
        bad += len(r.missing) + len(r.broken)
    k = rows['literals'].kinds
    print('literal kinds:', ', '.join(f'{x} {k[x]}' for x in sorted(k, key=lambda x: -k[x])))
    for name in SOURCES:
        for b in rows[name].broken:
            print('BROKEN', b)
        if a.v:
            for m in rows[name].missing:
                print('MISSING', name, repr(m['text'][:100]))
    vis = sum(r.visible for r in rows.values())
    done = sum(r.translated + r.kept + r.null for r in rows.values())
    print(f'all sources: {done}/{vis} visible texts done ({100 * done / max(vis, 1):.2f}%), {bad} missing or broken')
    if a.todo:
        write_todo(rows, a.todo)
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
