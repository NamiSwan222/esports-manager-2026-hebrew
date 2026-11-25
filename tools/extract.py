"""Extract the English string tables (Unity Localization) into work/en/<table>.json.

    python tools/extract.py [--game "<install folder>"]

Each row: {id, key, en}. Keys come from the shared table data (another bundle); rows whose id the
shared table doesn't list are leftovers the game never asks for and are skipped.
"""
import argparse, glob, os
import UnityPy
from common import AA, DEFAULT_GAME, EN_BUNDLE, EN_DIR, save_json


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--game', default=DEFAULT_GAME)
    a = ap.parse_args()
    aa = os.path.join(a.game, AA)
    keys = {}
    for f in glob.glob(os.path.join(aa, '*.bundle')):
        if 'string-tables' in f:
            continue
        for o in UnityPy.load(f).objects:
            if o.type.name != 'MonoBehaviour':
                continue
            try:
                t = o.read_typetree()
            except Exception:
                continue
            if 'm_Entries' in t and 'm_TableCollectionName' in t:
                keys[t['m_TableCollectionName']] = {e['m_Id']: e['m_Key'] for e in t['m_Entries']}
    for o in UnityPy.load(os.path.join(aa, EN_BUNDLE)).objects:
        if o.type.name != 'MonoBehaviour':
            continue
        t = o.read_typetree()
        if 'm_TableData' not in t:
            continue
        name = t['m_Name'][:-3]  # "Emails_en" -> "Emails"
        k = keys.get(name, {})
        rows = [{'id': str(e['m_Id']), 'key': k[e['m_Id']], 'en': e['m_Localized']}
                for e in t['m_TableData'] if e['m_Id'] in k]
        save_json(os.path.join(EN_DIR, name + '.json'), rows)
        print(name, len(rows), 'of', len(t['m_TableData']))


if __name__ == '__main__':
    main()
