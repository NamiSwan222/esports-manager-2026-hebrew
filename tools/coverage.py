"""Coverage check: every used English string needs Hebrew with the same markup.

    python tools/coverage.py                 report; exit 1 if anything is missing or broken
    python tools/coverage.py --batch 300     also write what's missing to work/todo/batch-NNN.json

Markup that must survive: {placeholders} (same names; gender choices {м:..|ж:..} may change their text),
<tags>, and the number of line breaks is not checked (Hebrew may wrap differently).
"""
import argparse, collections, os, re, sys
from common import ROOT, WORK, english, hebrew, load_json, save_json

PH = re.compile(r'\{([A-Za-z_][\w.]*|\d+)(?::[^{}]*)?\}')
CHOICE = re.compile(r'\{[мж]:[^{}]*\}')
TAG = re.compile(r'</?[A-Za-z][^<>]*>')
HEB = re.compile(r'[֐-׿]')


def markup_ok(en, he):
    return (collections.Counter(PH.findall(en)) == collections.Counter(PH.findall(he))
            and len(CHOICE.findall(en)) <= len(CHOICE.findall(he)) + len(CHOICE.findall(en))
            and collections.Counter(TAG.findall(en)) == collections.Counter(TAG.findall(he)))


def check():
    keep = set(load_json(os.path.join(ROOT, 'translation', 'keep.json')).get('ids', []))
    en, he = english(), hebrew()
    total = done = 0
    missing, broken = [], []
    for t, rows in en.items():
        for r in rows:
            total += 1
            plain = TAG.sub('', CHOICE.sub('', PH.sub('', r['en'])))
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


def glossary_check():
    """The in-game glossary (markdown literals): every English article translated with its markup intact."""
    import json
    path = os.path.join(WORK, 'glossary_en.json')
    if not os.path.exists(path):
        print('glossary: run tools/glossary.py first')
        return 1
    decided = load_json(os.path.join(ROOT, 'translation', 'he', '_literals.json'))
    arts = [s for _, s in json.load(open(path, encoding='utf-8'))]
    bad = [s for s in arts if not decided.get(s) or not HEB.search(decided[s]) or md_shape(s) != md_shape(decided[s])]
    for s in bad:
        print('GLOSSARY', 'missing' if not decided.get(s) else 'markup', repr(s[:80]))
    print(f'glossary articles: {len(arts) - len(bad)}/{len(arts)} translated')
    return len(bad)


def seen_check():
    """English text actually seen on screen (proxy -tirgumim_textlog, saved to translation/seen_in_game.txt):
    each line must be a translated display label (_labels.json), a name kept in Latin (keep.json "seen"),
    or a paragraph of a translated glossary article."""
    import json
    path = os.path.join(ROOT, 'translation', 'seen_in_game.txt')
    if not os.path.exists(path):
        return 0
    labels = load_json(os.path.join(ROOT, 'translation', 'he', '_labels.json'))
    keep = set(load_json(os.path.join(ROOT, 'translation', 'keep.json')).get('seen', []))
    decided = load_json(os.path.join(ROOT, 'translation', 'he', '_literals.json'))
    gpath = os.path.join(WORK, 'glossary_en.json')
    plain = lambda s: re.sub(r'\s+', ' ', re.sub(r'<[^<>]*>|\*\*', '', re.sub(r'\[\[[\w.]+\|([^\]]*)\]\]', r'\1', s))).strip().lower()
    arts = [plain(s) for _, s in json.load(open(gpath, encoding='utf-8')) if decided.get(s)] if os.path.exists(gpath) else []
    bad = []
    for line in open(path, encoding='utf-8').read().split('\n'):
        line = line.replace('\\n', '\n').replace('\\t', '\t').replace('\\\\', '\\')
        if not line or HEB.search(line) or line in labels or line in keep:
            continue
        p = plain(line)
        if any(p in a for a in arts):
            continue
        bad.append(line)
    for s in bad:
        print('SEEN untranslated', repr(s[:100]))
    print(f'seen in game: {len(bad)} untranslated')
    return len(bad)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--batch', type=int)
    a = ap.parse_args()
    total, done, missing, broken = check()
    for t, r, h, why in broken:
        print(f'BROKEN ({why}) {t} {r["id"]} {r["key"]}\n  en: {r["en"]!r}\n  he: {h!r}')
    print(f'coverage: {done}/{total} = {100 * done / total:.2f}%  missing {len(missing)}  broken {len(broken)}')
    # hard-coded code literals: every candidate must be decided (Hebrew, or null = not player-facing)
    cand_path = os.path.join(WORK, 'literal_candidates.json')
    lit_missing = 0
    if os.path.exists(cand_path):
        import json
        decided = load_json(os.path.join(ROOT, 'translation', 'he', '_literals.json'))
        cands = json.load(open(cand_path, encoding='utf-8'))
        lit_bad = [s for _, s in cands if decided.get(s) and not markup_ok(s, decided[s])]
        lit_missing = sum(1 for _, s in cands if s not in decided) + len(lit_bad)
        for s in lit_bad:
            print('BROKEN literal', repr(s), '->', repr(decided[s]))
        print(f'code literals: {len(cands) - lit_missing}/{len(cands)} decided '
              f'({sum(1 for v in decided.values() if v)} translated)')
    lit_missing += glossary_check() + seen_check()
    if a.batch:
        todo = os.path.join(WORK, 'todo')
        os.makedirs(todo, exist_ok=True)
        for f in os.listdir(todo):
            os.remove(os.path.join(todo, f))
        items = missing + [(t, r) for t, r, _, _ in broken]
        for i in range(0, len(items), a.batch):
            b = {}
            for t, r in items[i:i + a.batch]:
                b.setdefault(t, []).append({'id': r['id'], 'key': r['key'], 'en': r['en']})
            save_json(os.path.join(todo, f'batch-{i // a.batch:03d}.json'), b)
        print(f'{(len(items) + a.batch - 1) // a.batch} batches in work/todo')
    sys.exit(0 if not missing and not broken and not lit_missing else 1)


if __name__ == '__main__':
    main()
