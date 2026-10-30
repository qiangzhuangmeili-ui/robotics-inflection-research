"""对 59 份未抽出扣非的中间期报告，扫描「扣非标签+金额」出现在哪一页、何种版式。"""
import json, re, sys, collections
from pathlib import Path
ROOT = Path(r"C:/Users/zhangjianmei/Documents/ChatGPT/机器人企业行业拐点研究/robotics-inflection-research")
sys.path.insert(0, str(ROOT/'tools'))
import a03_financial_field_extractor as A
import pymupdf as fitz

survey = json.load(open('survey.json', encoding='utf-8'))
targets = [x for x in survey if x.get('exists') and not (x.get('npdedt_now') and x['npdedt_now'][0])]
res = []
for x in targets:
    doc = fitz.open(ROOT/x['file'])
    hits = []
    for pi in range(len(doc)):
        lines = [re.sub(r'注\s*\d+(?=\s|$|[：:])', '', ln).strip() for ln in A.page_lines(doc[pi].get_text())]
        for i, ln in enumerate(lines):
            n = A.normalize(ln)
            if '扣除非经常性损益' not in n:
                continue
            if not (n.startswith('归属于') or n.startswith('扣除非经常性损益后')):
                continue
            # 拼接后 5 行看是否紧跟金额
            t = ' '.join(lines[i:i+4])
            vals = A.summary_cells(t)
            money = [v for v in vals if v[1] is not None]
            hits.append(dict(page=pi+1, line=i, text=t[:120], n_money=len(money),
                             first=(money[0][0] if money else None)))
    res.append(dict(code=x['code'], name=x['name'], doc=x['doc'], pages=len(doc), hits=hits))
json.dump(res, open('scan59.json','w',encoding='utf-8'), ensure_ascii=False, indent=1)

nohit = [r for r in res if not r['hits']]
print('总', len(res), '| 完全找不到扣非标签:', len(nohit))
for r in nohit: print('   NO-LABEL', r['code'], r['name'], r['pages'])
withmoney = [r for r in res if r['hits'] and max(h['n_money'] for h in r['hits']) >= 2]
print('标签+至少2个金额:', len(withmoney))
print('标签有但金额不足2:', len([r for r in res if r['hits'] and max(h['n_money'] for h in r['hits'])<2]))
for r in res[:3]:
    print(r['code'], r['name'], [(h['page'],h['n_money'],h['first']) for h in r['hits']])
