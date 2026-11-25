"""Merge translated code-literal batches into translation/he/_literals.json ({English: Hebrew or null}).

    python tools/merge_literals.py work/lit_done/batch-00.json [...]

null = looked at and deliberately not translated (another language, developer text, a name).
Keys are the English text, so the file survives game updates that renumber literals.
"""
import json, os, sys
from common import HE_DIR, WORK, load_json, save_json

cand = {str(i): s for i, s in json.load(open(os.path.join(WORK, 'literal_candidates.json'), encoding='utf-8'))}
out = os.path.join(HE_DIR, '_literals.json')
cur = load_json(out)
for p in sys.argv[1:]:
    for idx, he in load_json(p).items():
        if idx in cand:
            cur[cand[idx]] = he
    print('merged', p)
save_json(out, dict(sorted(cur.items())))
print(len(cur), 'literals decided,', sum(1 for v in cur.values() if v), 'translated')
