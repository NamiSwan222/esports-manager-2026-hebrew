"""Make CS terms consistent across translation batches (tables and code literals). Re-runnable.

    python tools/unify.py
"""
import os, re
from common import H as text_key, HE_DIR, WORK, english, hebrew, load_he, load_json, save_he, save_json

H = r'[א-ת]'
# whole-word replacements (a Hebrew prefix letter like ב/ל/ה/ו before the word is kept)
WORDS = [
    ('סייט', 'אתר'), ('סטאק', 'ריכוז'), ('ספליט', 'פיצול'), ('קונטקט', 'מגע'), ('ריטייק', 'כיבוש מחדש'),
    ('פוש', 'דחיפה'), ('פלנט', 'הטמנה'), ('שתילה', 'הטמנה'), ('הדשוט', 'ירייה לראש'),
]
PHRASES = [('חצי-קנייה', 'קנייה חלקית'), ('חצי קנייה', 'קנייה חלקית'), ('ירייה בראש', 'ירייה לראש'),
           ('שתילה ופירוק', 'הטמנה ונטרול')]
PREFIX = '(?:ו?[בלהמש]?)'


def fix(he, en):
    for a, b in PHRASES:
        he = he.replace(a, b)
    for a, b in WORDS:
        he = re.sub(rf'(?<!{H})({PREFIX}){a}(?!{H})', lambda m: m.group(1) + b, he)
    if re.search(r'\bRush', en or ''):
        he = re.sub(rf'(?<!{H})({PREFIX})ראש(?!{H})', lambda m: m.group(1) + 'הסתערות', he)
    if re.search(r'\bFake\b', en or ''):
        he = re.sub(rf'(?<!{H})({PREFIX})פייק(?!{H})', lambda m: m.group(1) + 'הטעיה', he)
    return he


def main():
    n = 0
    en, he = english(), hebrew()
    for t, rows in en.items():
        src = {r['id']: r['en'] for r in rows}
        for k, v in list(he[t].items()):
            new = fix(v, src.get(k))
            if new != v:
                he[t][k] = new
                n += 1
        save_json(os.path.join(HE_DIR, t + '.json'), dict(sorted(he[t].items())))
    lit = load_he('_literals')
    # the English of each entry (for the Rush/Fake rules) from the regenerated literal list (tools/inventory.py)
    en_of = {}
    for e in load_json(os.path.join(WORK, 'inventory', 'literals.json')) or []:
        if e['text'] in lit:
            en_of.setdefault(text_key(e["text"]), e["text"])
    for h, v in list(lit.raw.items()):
        if v:
            new = fix(v, en_of.get(h))
            if new != v:
                lit.raw[h] = new
                n += 1
    save_he('_literals', lit)
    print('changed', n)


if __name__ == '__main__':
    main()
