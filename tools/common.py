"""Shared paths and helpers for the Esports Manager 2026 tools."""
import io, json, os

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
