"""独立复算 84 格补入的扣非：扣非 = 归母净利润 − 非经常性损益合计（另一张表）。

归母优先取 PDF 摘要表；摘要表没给时取 s00_v7 已入池的三表归母。
"""
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(r"C:/Users/zhangjianmei/Documents/ChatGPT/机器人企业行业拐点研究/robotics-inflection-research")
HERE = Path(__file__).parent
sys.path.insert(0, str(ROOT / 'tools'))
import a03_financial_field_extractor as A          # noqa: E402
import pymupdf as fitz                             # noqa: E402

NUM = re.compile(r'-?\d[\d,]*\.?\d*')
SLOT_PERIOD = {'q1_2026': '20260331', 'h1_2026': '20260630', 'q3_2026': '20260930'}

v7npp = {}
for r in csv.DictReader(open(ROOT / 'runs/issues/S02/remediation_20261029/collect_q3_2026/s00_v7.csv',
                            encoding='utf-8-sig')):
    if r['field_id'] == 'FIN.NPP.YTD':
        v7npp[(r['stock_code'], r['period_key'])] = r['value_cny']

index = {}
for r in csv.DictReader(open(ROOT / 'runs/collection/collection_index.csv', encoding='utf-8-sig')):
    index[(r['security_id'], r['slot_id'])] = r


def find_total(doc):
    started = False
    for pi in range(min(12, len(doc))):
        lines = A.page_lines(doc[pi].get_text())
        for i, ln in enumerate(lines):
            flat = re.sub(r'\s+', '', ln)
            if '非经常性损益项目' in flat or ('非经常性损益' in flat and '金额' in flat):
                started = True
            if not started:
                continue
            if flat.startswith('合计'):
                vals = []
                for c in NUM.findall(' '.join(lines[i:i + 3])):
                    v = float(c.replace(',', ''))
                    if abs(v) >= 1000 or ',' in c:
                        vals.append(v)
                if vals:
                    return vals          # 三季报有「本报告期/年初至报告期末」两列，全部返回
    return None


overrides = json.loads((HERE / 'npdedt_override_rows.json').read_text(encoding='utf-8'))
out = []
for key, row in overrides.items():
    sec, slot = key.split('|')
    period = SLOT_PERIOD[slot]
    rec = index[(sec, slot)]
    doc = fitz.open(ROOT / rec['local_file'])
    total = find_total(doc)
    npdedt = float(row['value_cny'])
    npp = v7npp.get((row['stock_code'], period))
    if npp in ('', None):
        kf = A.extract_key_financials([doc[i].get_text() for i in range(min(60, len(doc)))],
                                      anchor_rev=None)[0]
        npp = kf.get('FIN.NPP.YTD')
    if not total or npp in ('', None):
        out.append(dict(stock_code=row['stock_code'], slot=slot, npdedt=npdedt,
                        npp=npp, total=total, verdict='NO_CROSSCHECK'))
        continue
    npp = float(str(npp).replace(',', ''))
    best = None
    for t in total:
        calc = npp - t
        diff = npdedt - calc
        tol = max(2000.0, abs(calc) * 0.002)
        if abs(diff) <= tol:
            best = (t, calc, diff)
            break
    if best:
        out.append(dict(stock_code=row['stock_code'], stock_name=row.get('stock_name',''), slot=slot,
                        npdedt=npdedt, npp=npp, total=best[0], calc=round(best[1], 2),
                        diff=round(best[2], 2), verdict='PASS'))
    else:
        t0 = total[0]
        calc = npp - t0
        out.append(dict(stock_code=row['stock_code'], stock_name=row.get('stock_name',''), slot=slot,
                        npdedt=npdedt, npp=npp, total=total, calc=round(calc, 2),
                        diff=round(npdedt - calc, 2), verdict='FAIL'))

(HERE / 'verify_overrides.json').write_text(json.dumps(out, ensure_ascii=False, indent=1),
                                            encoding='utf-8')
print(dict(Counter(o['verdict'] for o in out)))
for o in out:
    if o['verdict'] != 'PASS':
        print(o['verdict'], o['stock_code'], o.get('stock_name'), o['slot'],
              o.get('npdedt'), o.get('npp'), o.get('total'), o.get('diff'))
