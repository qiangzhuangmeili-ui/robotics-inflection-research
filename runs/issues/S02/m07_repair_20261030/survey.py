"""诊断 86 家 M07 缺失：中间期原件是否存在、扣非是否可抽。"""
import csv, json, os, sys, collections
from pathlib import Path
ROOT = Path(r"C:/Users/zhangjianmei/Documents/ChatGPT/机器人企业行业拐点研究/robotics-inflection-research")
sys.path.insert(0, str(ROOT/'tools'))
import a03_financial_field_extractor as A

det = json.load(open('m07_detail.json', encoding='utf-8'))
idx = {}
for r in csv.DictReader(open(ROOT/'runs/collection/collection_index.csv', encoding='utf-8-sig')):
    idx[(r['security_id'], r['slot_id'])] = r
SLOT = {'20260331': 'q1_2026', '20260630': 'h1_2026', '20260930': 'q3_2026'}

out = []
for d in det:
    per = d['period']
    mid = '20260331' if per == '20260630' else '20260630'
    sid = None
    for (s, sl) in idx:
        if s.endswith(':'+d['code']):
            sid = s
    rec = idx.get((sid, SLOT[mid]))
    item = dict(code=d['code'], name=d['name'], period=per, mid=mid, slot=SLOT[mid],
                ytd_t=bool(d['ytd_t']), ytd_mid=bool(d['ytd_q1']))
    if not rec:
        item['state'] = 'NO_SLOT_RECORD'
    else:
        item['doc'] = rec['document_id']; item['status'] = rec['status']
        p = ROOT/rec['local_file']
        item['file'] = rec['local_file']; item['exists'] = p.exists()
        if p.exists():
            r = A.extract_one(dict(document_id=rec['document_id'], security_id=sid,
                                   stock_code=d['code'], slot_id=SLOT[mid],
                                   period_label=mid, path=str(p)))
            got = {f['field_id']: (f.get('value_raw'), f.get('status'), f.get('note',''))
                   for f in r['fields']}
            item['npdedt_now'] = got.get('FIN.NPDEDT.YTD')
            item['rev_now'] = got.get('FIN.REV.YTD')
            item['kf_page'] = r.get('key_financials_page')
            item['parse_error'] = r.get('parse_error')
    out.append(item)
json.dump(out, open('survey.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
c = collections.Counter((x.get('exists'), bool(x.get('npdedt_now') and x['npdedt_now'][0])) for x in out)
print('exists/抽取到扣非:', dict(c))
for x in out:
    if not x.get('exists') or not (x.get('npdedt_now') and x['npdedt_now'][0]):
        print(x['code'], x['name'], x['slot'], x.get('state') or x.get('status'), '|', x.get('npdedt_now'), '|', x.get('file'))
