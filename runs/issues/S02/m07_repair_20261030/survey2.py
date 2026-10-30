"""86 家 M07 缺失：当期与中间期两份原件的扣非可得性（现行解析器基线）。"""
import csv, json, sys
from pathlib import Path
ROOT = Path(r"C:/Users/zhangjianmei/Documents/ChatGPT/机器人企业行业拐点研究/robotics-inflection-research")
sys.path.insert(0, str(ROOT/'tools'))
import a03_financial_field_extractor as A

det = json.load(open('m07_detail.json', encoding='utf-8'))
idx = {}
for r in csv.DictReader(open(ROOT/'runs/collection/collection_index.csv', encoding='utf-8-sig')):
    idx[(r['security_id'], r['slot_id'])] = r
SLOT = {'20260331': 'q1_2026', '20260630': 'h1_2026', '20260930': 'q3_2026'}
sec = {}
for r in csv.DictReader(open(ROOT/'data/company_master.csv', encoding='utf-8-sig')):
    sec[r.get('stock_code')] = r.get('security_id')

def probe(code, slot):
    sid = sec.get(code) or next((s for (s, sl) in idx if s.endswith(':'+code)), None)
    rec = idx.get((sid, slot))
    if not rec: return dict(state='NO_RECORD')
    p = ROOT/rec['local_file']
    if not p.exists(): return dict(state='NO_FILE', file=rec['local_file'])
    r = A.extract_one(dict(document_id=rec['document_id'], security_id=sid, stock_code=code,
                           slot_id=slot, period_label=slot, path=str(p)))
    got = {f['field_id']: f for f in r['fields']}
    n = got.get('FIN.NPDEDT.YTD', {})
    return dict(state='OK', doc=rec['document_id'], file=rec['local_file'],
                npdedt=n.get('value_raw') or '', status=n.get('extract_status'),
                kf=r.get('key_financials_page'), chars=r.get('text_chars'),
                rev=(got.get('FIN.REV.YTD') or {}).get('value_raw') or '')

out=[]
for d in det:
    per=d['period']; mid='20260331' if per=='20260630' else '20260630'
    out.append(dict(code=d['code'], name=d['name'], period=per,
                    cur=probe(d['code'], SLOT[per]), mid=probe(d['code'], SLOT[mid])))
json.dump(out, open('survey2.json','w',encoding='utf-8'), ensure_ascii=False, indent=1)
import collections
c=collections.Counter((bool(x['cur'].get('npdedt')), bool(x['mid'].get('npdedt'))) for x in out)
print('当期扣非/中间期扣非:', dict(c))
for x in out:
    if not x['cur'].get('npdedt'):
        print(' CUR-MISS', x['code'], x['name'], x['period'], x['cur'].get('state'), x['cur'].get('kf'), x['cur'].get('chars'))
