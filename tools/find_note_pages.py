"""在指定 PDF 中按关键词定位页码并打印上下文，用于读附注。"""
import csv
import re
import sys
from pathlib import Path

ROOT = Path(r"C:/Users/zhangjianmei/Documents/ChatGPT/机器人企业行业拐点研究/robotics-inflection-research")
IDX = {}
for r in csv.DictReader(open(ROOT / 'runs/collection/collection_index.csv', encoding='utf-8-sig')):
    IDX[r['document_id']] = r


def pages_of(doc):
    from pypdf import PdfReader
    rec = IDX[doc]
    d = PdfReader(str(ROOT / rec['local_file']))
    return [(i + 1, d.pages[i].extract_text() or '') for i in range(len(d.pages))]


def main():
    doc = sys.argv[1]
    kws = sys.argv[2].split('|')
    ctx = int(sys.argv[3]) if len(sys.argv) > 3 else 400
    limit = int(sys.argv[4]) if len(sys.argv) > 4 else 3
    hits = 0
    for pno, text in pages_of(doc):
        flat = re.sub(r'\s+', '', text)
        for kw in kws:
            if kw in flat:
                print(f'===== p{pno} 命中「{kw}」')
                i = flat.find(kw)
                print(flat[max(0, i - ctx // 2):i + ctx])
                hits += 1
                break
        if hits >= limit:
            break
    if not hits:
        print('NO HIT')


if __name__ == '__main__':
    main()
