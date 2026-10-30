"""独立复算：扣非 = 归母净利润 − 非经常性损益合计（另一张表，不同来源）。
只做机器比对，不改任何数据。"""
import csv, json, re, sys
from pathlib import Path
ROOT = Path(r"C:/Users/zhangjianmei/Documents/ChatGPT/机器人企业行业拐点研究/robotics-inflection-research")
sys.path.insert(0, str(ROOT/'tools'))
import a03_financial_field_extractor as A
import pymupdf as fitz

NUM = re.compile(r'-?\d[\d,]*\.?\d*')
rows = json.load(open('dump83.json', encoding='utf-8'))
survey = {x['code']: x for x in json.load(open('survey.json', encoding='utf-8'))}

# 关键表没给归母时，用 v7 已入池的归母（来自三表）作对照，保证 83 家都能验算
V7 = {}
for r in csv.DictReader(open(r"C:/Users/zhangjianmei/Documents/ChatGPT/机器人企业行业拐点研究/robotics-inflection-research/runs/issues/S02/remediation_20261029/collect_q3_2026/s00_v7.csv", encoding='utf-8-sig')):
    if r['field_id'] == 'FIN.NPP.YTD':
        V7[(r['stock_code'], r['period_key'])] = r['value_cny']

def find_total(doc):
    """在「非经常性损益」小节里找『合计』行，返回第一个金额。"""
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
                cand = NUM.findall(' '.join(lines[i:i+3]))
                for c in cand:
                    v = float(c.replace(',', ''))
                    if abs(v) >= 1000 or ',' in c:
                        return v, pi+1
    return None, None

out=[]
for r in rows:
    if not r['npdedt']:
        out.append(dict(code=r['code'], name=r['name'], verdict='NO_VALUE')); continue
    x = survey[r['code']]
    doc = fitz.open(ROOT/x['file'])
    total, page = find_total(doc)
    npdedt = float(r['npdedt'].replace(',', ''))
    npp_raw = r['npp'] or V7.get((r['code'], survey[r['code']]['mid']))
    npp = float(str(npp_raw).replace(',', '')) if npp_raw else None
    if total is None or npp is None:
        out.append(dict(code=r['code'], name=r['name'], npdedt=npdedt, npp=npp, total=total,
                        verdict='NO_CROSSCHECK')); continue
    calc = npp - total
    diff = npdedt - calc
    tol = max(2000.0, abs(calc) * 0.002)
    out.append(dict(code=r['code'], name=r['name'], npdedt=npdedt, npp=npp, total=total,
                    calc=calc, diff=diff, page=page,
                    verdict='PASS' if abs(diff) <= tol else 'FAIL'))
json.dump(out, open('verify_arith.json','w',encoding='utf-8'), ensure_ascii=False, indent=1)
import collections
print(collections.Counter(o['verdict'] for o in out))
for o in out:
    if o['verdict'] in ('FAIL','NO_CROSSCHECK','NO_VALUE'):
        print(o['verdict'], o['code'], o['name'], o.get('npdedt'), o.get('npp'), o.get('total'), o.get('diff'))
