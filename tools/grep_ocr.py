"""在已有 OCR 结果中按关键词检索（孚日 2026H1 / 2026Q3）。"""
import glob
import json
import re
import sys

BASE = (r"C:/Users/zhangjianmei/Documents/ChatGPT/机器人企业行业拐点研究/robotics-inflection-research/"
        r"runs/issues/S02/recovery18_20261029/ocr2")
doc = sys.argv[1]
kws = sys.argv[2].split('|')
span = int(sys.argv[3]) if len(sys.argv) > 3 else 800
limit = int(sys.argv[4]) if len(sys.argv) > 4 else 5
hits = 0
for f in sorted(glob.glob(f'{BASE}/{doc}/p*.json')):
    d = json.load(open(f, encoding='utf-8'))
    flat = re.sub(r'\s+', '', d.get('text', ''))
    for kw in kws:
        if kw in flat:
            i = flat.find(kw)
            print('---', f.replace('\\', '/').split('/')[-1], '命中', kw)
            print(flat[max(0, i - 200):i + span])
            hits += 1
            break
    if hits >= limit:
        break
if not hits:
    print('NO HIT')
