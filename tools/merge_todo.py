"""Merge translated batches (work/done/<source>-NNN.json = {"<English>": "Hebrew" or null}) into translation/he.

    python tools/merge_todo.py work/done/literals-000.json [...]     (or: python tools/merge_todo.py --all)

The matching work/todo/<source>-NNN.json says where each text goes:
  literals  via "literal" -> _literals.json, via "label" -> _labels.json; null -> _literals.json null
            (looked at, not shown to the player)
  scenes    -> _scenes.json (null allowed: a placeholder the game always replaces)
  options / seen -> _labels.json (null -> keep.json "keep": {"kept-by-translator": [...]})
  dialogs   -> _dialogs.json        emdb -> _emdb.json        glossary -> _literals.json
  tables    -> <table>.json by entry id
Texts whose Hebrew breaks markup ({0}, <tags>) or has no Hebrew letter are not merged and are printed.
The tracked files get H(English) keys (common.H), never the English: the batches in work/ keep it.
"""
import glob, os, sys
from common import H, HE_DIR, KEEP, WORK, load_json, save_json
from coverage import HEB, markup_ok

FILES = {'literal': '_literals', 'label': '_labels', 'scenes': '_scenes', 'options': '_labels', 'seen': '_labels',
         'dialogs': '_dialogs', 'emdb': '_emdb', 'glossary': '_literals'}


def main():
    paths = sorted(glob.glob(os.path.join(WORK, 'done', '*.json'))) if sys.argv[1:] == ['--all'] else sys.argv[1:]
    cache = {}

    def tfile(name):
        if name not in cache:
            cache[name] = load_json(os.path.join(HE_DIR, name + '.json'))
        return cache[name]

    keep_path = KEEP
    keep = load_json(keep_path)
    kept = keep.setdefault('keep', {}).setdefault('kept-by-translator', [])
    bad = 0
    for p in paths:
        todo = load_json(os.path.join(WORK, 'todo', os.path.basename(p)))
        if not todo:
            print('no todo file for', p)
            continue
        done = load_json(p)
        src = todo['source']
        n = 0
        for it in todo['items']:
            en = it['text']
            if en not in done:
                continue
            he = done[en]
            if he is not None and (not HEB.search(he) or not markup_ok(en, he)):
                print('FIX', os.path.basename(p), repr(en[:70]), '->', repr(he[:70]))
                bad += 1
                continue
            if src == 'tables':
                if he:
                    tfile(it['table'])[it['id']] = he
            elif src == 'literals':
                if he is None:
                    tfile('_literals')[H(en)] = None
                else:
                    tfile('_literals' if it['via'] == 'literal' else '_labels')[H(en)] = he
            elif he is None:
                if src == 'scenes':
                    tfile('_scenes')[H(en)] = None
                elif src in ('options', 'seen') and H(en) not in kept:
                    kept.append(H(en))
            else:
                tfile(FILES[src])[H(en)] = he
            n += 1
        print('merged', os.path.basename(p), n, 'of', len(todo['items']))
    for name, data in cache.items():
        save_json(os.path.join(HE_DIR, name + '.json'), dict(sorted(data.items())))
    if kept:
        save_json(keep_path, keep)
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
