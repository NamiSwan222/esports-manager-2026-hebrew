"""Unify recurring role/bio terms to the wording the translated UI uses (glossary.md "Roles" rows).

    python tools/unify_terms.py        rewrites work/done/*.json answers and translation/he/_literals.json, _labels.json
                                       (BIO_RULES: work/done/emdb-*.json only)

Rule-based, exact phrase replacements only; prints counts. Safe to run again.
"""
import glob, json, os, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# UI reference: role labels רייפלר / לורקר / תומך / אנטרי / צלף and "IGL"; "In-game leader" label = מוביל במשחק
RULES = [
    (r'(?:מנהיגת|מובילת) המשחק \(IGL\)', 'מובילה במשחק (IGL)'),
    (r'(?:מנהיג|מוביל) המשחק \(IGL\)', 'מוביל במשחק (IGL)'),
    (r'(?:מנהיג|מוביל) המשחק(?= |$|[.,])', 'מוביל במשחק'),
    (r'מנהיג במשחק', 'מוביל במשחק'),
    (r'אנטרי פראגר', 'אנטרי'),
    (r'תפקיד מוביל במשחק', 'תפקיד המוביל במשחק'),
]

# Recurring bio/description patterns (work/done/emdb-*.json only): the three bio batches phrased them differently.
BIO_RULES = [
    # name history in brackets ("(formerly known as X)" left in English by some batches)
    (r'\((?:formerly|previously) known as ([^()]*?)\s*\)', r'(בעבר \1)'),
    (r'\((?:formerly|previously) stylized as ([^()]*?)\s*\)', r'(בעבר נכתב \1)'),
    (r'\(also known as ([^()]*?)\s*\)', r'(ידוע גם בשם \1)'),
    (r'\(also stylized as ([^()]*?)\s*\)', r'(נכתב גם \1)'),
    (r'\(stylized as ([^()]*?) (?:prior to|before) (\d{4})\s*\)', r'(עד \2 נכתב \1)'),
    (r'\(known as ([^()]*?) (?:prior to|before) (\d{4})\s*\)', r'(עד \2 נקרא \1)'),
    (r'\(ידוע גם כ-', '(ידוע גם בשם '),
    (r'\((?:הידוע עד (\d{4}) בשם|עד (\d{4}) ידוע בשם) ', r'(עד \1\2 נקרא '),
    (r'\((?:הידוע בקצרה כ-|ידוע לזמן קצר בשם )', '(לזמן קצר נקרא '),
    (r'\(לזמן קצר בכתיב ', '(לזמן קצר נכתב '),
    # bios: "of CS:GO and of CS" (one range wrote "של X ו-Counter-Strike")
    (r'(של Counter[- ]Strike(?:: Global Offensive| 2| Source)?) ו-(Counter-Strike)', r'\1 ושל \2'),
    # bios: nationality / gender forms
    (r'(?<![א-ת])קזחס?טא?ני(?![א-ת])', 'קזחי'),
    (r'(?<![א-ת])קזחס?טא?נית(?![א-ת])', 'קזחית'),
    (r'(?<![א-ת])אזרי(?=[ -])', "אזרבייג'אני"),
    (r'(שחקנית(?: [א-ת\'-]+)?) מקצוענית', r'\1 מקצועית'),
    # bios: "the Tier 2 circuit" = מעגל דרג 2, like the "Tier 1" = "דרג 1" label (glossary prose keeps "T1 (Tier 1)")
    (r'(?:(?<=מעגל )|(?<=מעגלי )|(?<=סצנת )|(?<=סצנות )|(?<=האונליין של ))Tier (\d(?:[–/-]\d)?)(?= [א-ת])', r'דרג \1'),
    # a generic Major = מייג'ור as in the UI; tournament names ("PGL Major Stockholm", "World Strike Major") stay Latin
    (r'(?<=שני )Majors?(?![A-Za-z])', "מייג'ורים"),
    (r'(?<![א-ת])([בהל])-Majors(?![A-Za-z])', r"\1מייג'ורים"),
    (r'(?<![א-ת])([בהל])-Major(?![A-Za-z]| [A-Z0-9])', r"\1מייג'ור"),
    (r'(?<=[א-ת] )Major(?![A-Za-z]| [A-Z0-9])', "מייג'ור"),
]


def fix(s, counts, rules=RULES):
    for a, b in rules:
        s2, n = re.subn(a, b, s)
        if n:
            counts[a] = counts.get(a, 0) + n
            s = s2
    return s


def walk(o, counts, rules=RULES):
    if isinstance(o, str):
        return fix(o, counts, rules)
    if isinstance(o, dict):
        return {k: walk(v, counts, rules) for k, v in o.items()}
    if isinstance(o, list):
        return [walk(v, counts, rules) for v in o]
    return o


def main():
    counts = {}
    files = glob.glob(os.path.join(ROOT, 'work', 'done', '*.json'))
    files += [os.path.join(ROOT, 'translation', 'he', n) for n in ('_literals.json', '_labels.json')]
    for p in files:
        if not os.path.exists(p):
            continue
        d = json.load(open(p, encoding='utf-8'))
        bio = os.path.basename(p).startswith('emdb-')
        n = walk(d, counts, RULES + BIO_RULES if bio else RULES)
        if n != d:
            json.dump(n, open(p, 'w', encoding='utf-8', newline='\n'), ensure_ascii=False, indent=1)
            print('updated', os.path.relpath(p, ROOT))
    for a, n in counts.items():
        print(f'{n:5}  {a}')


if __name__ == '__main__':
    main()
