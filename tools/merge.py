"""Merge translated batches into translation/he/<target>.json.

    python tools/merge.py work/done/batch-000.json [...]
Each file: {"<target>": {"<ns>|<key>": "Hebrew", ...}, ...}
"""
import os, sys
from common import HE_DIR, load_json, save_json

for path in sys.argv[1:]:
    for target, items in load_json(path).items():
        out = os.path.join(HE_DIR, target + '.json')
        cur = load_json(out)
        cur.update({k: v for k, v in items.items() if v})
        save_json(out, dict(sorted(cur.items())))
    print('merged', path)
