"""Pick the hard-coded English UI text among the game's IL2CPP string literals.

    python tools/literals.py [--game "<install>"]     -> work/literal_candidates.json [[index, text]]

The game shows a lot of text straight from its code (tactic names, sponsor/news sentences, tooltips).
They live in global-metadata.dat next to every other literal (.NET/Unity messages, names, keys, and the
game's own built-in translations into other languages). We only take sentence-like English text: at least
3 words with a space, ASCII, common English words in it, and nothing that looks technical. Short labels
(1-2 words) are left out on purpose, because code often uses them as keys; the ones that are really shown
are added one by one in translation/literal_labels.json after checking them in game.
"""
import argparse, json, os, re
from common import DEFAULT_GAME, WORK, ROOT, load_json
import metadata

STOP = set('the a an and or of to in for with on at is are be your you this that it from by as not was will '
           'can has have more than his her their our we they he she its'.split())
TECH = re.compile(r'(?i)exception|invalid|argument|parameter|null|assembly|serializ|xml|regex|stream|socket|'
                  r'thread|unity|shader|mesh|render|graphics|texture|compil|buffer|pointer|marshal|delegate|'
                  r'enumerat|instance|generic|attribute|property|method|constructor|interface|struct|utf|'
                  r'encoding|culture|locale|byte|array|index|capacity|overflow|handle|native|platform|http|'
                  r'json|uri|cert|cipher|crypto|async|task|mutex|semaphore|debug|assert|profil|vulkan|d3d|gpu|'
                  r'asset|bundle|addressable|prefab|gameobject|component|collider|rigidbody|canvas|tmp|glyph|'
                  r'atlas|vertex|matrix|quaternion|vector|mono|il2cpp|reflection|namespace|schema|dtd|entity|sql')
BAD = re.compile(r'[_\\]|::|=>|\(\)|^\s|\w\.\w+\(')
NON_ASCII = re.compile(r'[^\x00-\x7f‘’“”—–…•]')


def ui_sentence(s):
    if len(s) < 8 or NON_ASCII.search(s) or BAD.search(s) or TECH.search(s):
        return False
    words = re.findall(r"[A-Za-z']+", s)
    if len(words) < 3 or ' ' not in s:
        return False
    if len(words) > 4 and not any(w.lower() in STOP for w in words):
        return False  # long text without English function words: another language
    return True


def candidates(lits):
    import glossary
    labels = set(load_json(os.path.join(ROOT, 'translation', 'literal_labels.json')).get('labels', []))
    articles = {i for i, _ in glossary.articles(lits)}  # markdown with [[entry.id|..]] fails ui_sentence
    return [[i, s] for i, s in enumerate(lits) if ui_sentence(s) or s in labels or i in articles]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--game', default=DEFAULT_GAME)
    a = ap.parse_args()
    d = open(os.path.join(a.game, r'EsportsManager_Data\il2cpp_data\Metadata\global-metadata.dat'), 'rb').read()
    c = candidates(metadata.literals(d))
    os.makedirs(WORK, exist_ok=True)
    json.dump(c, open(os.path.join(WORK, 'literal_candidates.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
    print(len(c), 'candidates,', sum(len(s.split()) for _, s in c), 'words')


if __name__ == '__main__':
    main()
