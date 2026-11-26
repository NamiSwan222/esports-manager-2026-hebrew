"""The in-game term glossary (main menu -> Glossary): markdown articles hard-coded as IL2CPP literals.

    python tools/glossary.py            -> work/glossary_en.json  [[index, text], ...]

Each article exists in ~21 languages, every one a separate string literal. Markup (keep it exactly):
**bold**, [[entry.id|link label]] / [[entry.id]], "# Section heading" lines, "!tip " / "!trap " callouts,
"=see id, id" lines (ids only, never translated), \r\n line breaks. The article titles, categories and
short UI labels of the glossary are not here: they are exact strings shown as-is, translated for display
in translation/he/_labels.json (the proxy swaps them when TextMeshPro shows them).
"""
import json, os, re
from common import DEFAULT_GAME, WORK
import metadata

MD = re.compile(r'\[\[[\w.]+(\|[^\]]*)?\]\]|\r?\n=see |^!(tip|trap) |\r?\n!(tip|trap) |\r?\n# ')
EN = set('the a an and of to in is are be your you that it not on for with as by from this its at or'.split())


def english(s):
    if re.search(r'[^\x00-\x7f\u2014\u2013\u2018\u2019\u201c\u201d\u2026\u00d7\u20ac\u00b7\u2192\u2265\u2264\u00a0]', s):
        return False
    words = re.findall(r'[A-Za-z]+', re.sub(r'\[\[[^\]]*\]\]|=see .*', '', s))
    return len(words) > 0 and sum(w.lower() in EN for w in words) / len(words) > 0.12


def articles(lits):
    return [[i, s] for i, s in enumerate(lits) if MD.search(s) and english(s)]


def main():
    d = open(os.path.join(DEFAULT_GAME, r'EsportsManager_Data\il2cpp_data\Metadata\global-metadata.dat'), 'rb').read()
    a = articles(metadata.literals(d))
    json.dump(a, open(os.path.join(WORK, 'glossary_en.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
    print(len(a), 'English glossary articles,', sum(len(s.split()) for _, s in a), 'words')


if __name__ == '__main__':
    main()
