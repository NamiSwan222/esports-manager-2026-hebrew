"""Make CS terms consistent across translation batches (tables and code literals). Re-runnable.

    python tools/unify.py
"""
import os, re
from common import HE_DIR, english, hebrew, load_json, save_json

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
    p = os.path.join(HE_DIR, '_literals.json')
    lit = load_json(p)
    for e, v in list(lit.items()):
        if v:
            new = fix(v, e)
            if new != v:
                lit[e] = new
                n += 1
    save_json(p, dict(sorted(lit.items())))
    print('changed', n)


if __name__ == '__main__':
    main()
