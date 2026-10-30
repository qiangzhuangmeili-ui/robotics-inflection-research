"""区分两种失败：页级门槛因换行断开「增减」而失败 vs 摘要表跨页续行被丢弃。"""
import json, re, sys, collections
from pathlib import Path
ROOT = Path(r"C:/Users/zhangjianmei/Documents/ChatGPT/机器人企业行业拐点研究/robotics-inflection-research")
sys.path.insert(0, str(ROOT/'tools'))
import a03_financial_field_extractor as A
import pymupdf as fitz

survey = json.load(open('survey.json', encoding='utf-8'))
targets = [x for x in survey if x.get('exists') and not (x.get('npdedt_now') and x['npdedt_now'][0])]
res=[]
for x in targets:
    doc = fitz.open(ROOT/x['file'])
    head_pages=[]; cont_pages=[]
    for pi in range(min(12, len(doc))):
        lines=[l.strip() for l in A.page_lines(doc[pi].get_text())]
        text='\n'.join(lines); flat=re.sub(r'\s+','',text)
        has_rev='营业收入' in text; has_np='归属于' in text
        gate_old = has_rev and has_np and ('增减' in text)
        gate_new = has_rev and has_np and ('增减' in flat)
        if gate_new: head_pages.append(pi+1)
        elif has_np and '扣除非经常性损益' in flat: cont_pages.append(pi+1)
    res.append(dict(code=x['code'],name=x['name'],slot=x['slot'],kf=x.get('kf_page'),
                    heads=head_pages, conts=cont_pages))
c=collections.Counter()
for r in res:
    c[('head_new' if r['heads'] else 'no_head', 'cont' if r['conts'] else 'no_cont')]+=1
print(dict(c))
for r in res:
    if not r['heads']: print(' NO_HEAD', r['code'], r['name'], r['slot'], 'kf',r['kf'], 'cont',r['conts'][:3])
