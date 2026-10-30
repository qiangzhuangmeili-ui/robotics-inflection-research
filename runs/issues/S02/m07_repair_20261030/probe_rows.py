"""定位每份报告里「扣非」行实际出现在哪一页，以及该行有几个金额列。"""
import json, re, sys
from pathlib import Path
ROOT = Path(r"C:/Users/zhangjianmei/Documents/ChatGPT/机器人企业行业拐点研究/robotics-inflection-research")
sys.path.insert(0, str(ROOT/'tools'))
import a03_financial_field_extractor as A
import pymupdf as fitz

survey = json.load(open('survey.json', encoding='utf-8'))
targets = [x for x in survey if x.get('exists') and not (x.get('npdedt_now') and x['npdedt_now'][0])]

LABELS = ['归属于上市公司股东的扣除非经常性损益的净利润',
          '归属于上市公司股东的扣除非经常性损益后的净利润',
          '归属于挂牌公司股东的扣除非经常性损益后的净利润',
          '归属于挂牌公司股东的扣除非经常性损益的净利润',
          '归属于母公司股东的扣除非经常性损益的净利润',
          '扣除非经常性损益后归属于上市公司股东的净利润',
          '扣除非经常性损益后归属于公司普通股股东的净利润',
          '扣除非经常性损益后归属于母公司股东的净利润']

out=[]
for x in targets:
    doc = fitz.open(ROOT/x['file'])
    found=[]
    for pi in range(min(8, len(doc))):
        lines = [re.sub(r'注\s*\d+(?=\s|$|[：:])', '', ln).strip() for ln in A.page_lines(doc[pi].get_text())]
        n=len(lines)
        for i in range(n):
            for span in (1,2,3,4,5):
                if i+span>n: break
                t=' '.join(lines[i:i+span]); norm=A.normalize(t)
                if not any(norm.startswith(lb) for lb in LABELS): continue
                vals=A.summary_cells(t)
                money=[v for v in vals if v[1] is not None and not v[2]]
                found.append(dict(page=pi+1, span=span, money=len(money), first=(money[0][0] if money else None),
                                  raw=t[:90]))
                break
    out.append(dict(code=x['code'], name=x['name'], slot=x['slot'], kf=x.get('kf_page'), hits=found))
json.dump(out, open('probe_rows.json','w',encoding='utf-8'), ensure_ascii=False, indent=1)
import collections
c=collections.Counter()
for r in out:
    good=[h for h in r['hits'] if h['money']>=2]
    c['有≥2金额' if good else ('有但<2金额' if r['hits'] else '无命中')]+=1
print(dict(c))
for r in out:
    if not [h for h in r['hits'] if h['money']>=2]:
        print(' BAD', r['code'], r['name'], r['slot'], 'kf', r['kf'], r['hits'][:3])
