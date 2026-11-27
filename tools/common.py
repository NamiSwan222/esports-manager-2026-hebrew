"""Shared paths and helpers for the Esports Manager 2026 tools."""
import hashlib, io, json, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = os.path.join(ROOT, 'work')
EN_DIR = os.path.join(WORK, 'en')
HE_DIR = os.environ.get('TIRGUMIM_HE_DIR') or os.path.join(ROOT, 'translation', 'he')
DEFAULT_GAME = r'D:\SteamLibrary\steamapps\common\Esports Manager 2026'
AA = r'EsportsManager_Data\StreamingAssets\aa\StandaloneWindows64'
EN_BUNDLE = 'localization-string-tables-en_assets_all.bundle'


def load_json(path):
    if not os.path.exists(path):
        return {}
    with io.open(path, encoding='utf-8') as f:
        return json.load(f)


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with io.open(path, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
        f.write('\n')


def tables():
    return sorted(f[:-5] for f in os.listdir(EN_DIR) if f.endswith('.json'))


def english():
    """{table: [{id, key, en}]}: only entries the game uses (present in the shared key table)."""
    return {t: load_json(os.path.join(EN_DIR, t + '.json')) for t in tables()}


def hebrew():
    return {t: load_json(os.path.join(HE_DIR, t + '.json')) for t in tables()}


# The repo holds no English game text: translation/he/_*.json and translation/keep.json are keyed by H(English),
# the English itself is regenerated from the install into work/ (extract.py, glossary.py, inventory.py).
def H(s):
    """Key of an English text: the first 16 hex digits of SHA-256 over its UTF-8 bytes (no normalisation:
    the exact text; the proxy hashes what TextMeshPro is given the same way, tools/proxy/src/sha.rs)."""
    return hashlib.sha256(s.encode('utf-8')).hexdigest()[:16]


class ByHash:
    """A tracked {H(English): Hebrew | null} file, looked up by English text."""

    def __init__(self, raw=None):
        self.raw = dict(raw or {})

    def get(self, en, default=None):
        return self.raw.get(H(en), default) if isinstance(en, str) else default

    def __contains__(self, en):
        return isinstance(en, str) and H(en) in self.raw

    def __getitem__(self, en):
        return self.raw[H(en)]

    def __setitem__(self, en, v):
        self.raw[H(en)] = v

    def __len__(self):
        return len(self.raw)

    def resolve(self, texts):
        """{English: value} for the given English texts that have an entry."""
        return {t: self.raw[H(t)] for t in texts if H(t) in self.raw}


def load_he(name):
    return ByHash(load_json(os.path.join(HE_DIR, name + '.json')))


def save_he(name, by_hash):
    save_json(os.path.join(HE_DIR, name + '.json'), dict(sorted(by_hash.raw.items())))


KEEP = os.path.join(ROOT, 'translation', 'keep.json')


def keep_hashes():
    """H() of every text kept in Latin on purpose (translation/keep.json "seen" + "keep": {reason: [H]})."""
    k = load_json(KEEP)
    out = set(k.get('seen', []))
    for v in k.get('keep', {}).values():
        out.update(v)
    return out
