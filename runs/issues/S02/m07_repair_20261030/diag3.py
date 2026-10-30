import csv, collections, json, os
BASE=r"C:/Users/zhangjianmei/Documents/ChatGPT/机器人企业行业拐点研究/robotics-inflection-research/runs/issues/S02/remediation_20261029/collect_q3_2026"
s=list(csv.DictReader(open(os.path.join(BASE,'s00_v7.csv'),encoding='utf-8-sig')))
det=json.load(open('m07_detail.json',encoding='utf-8'))
by=collections.defaultdict(lambda: collections.defaultdict(list))
for r in s:
    by[r['stock_code']][r['period_key']].append(r)
fc=collections.Counter()
for d in det:
    per=d['period']; mid='20260331' if per=='20260630' else '20260630'
    for r in by[d['code']][mid]:
        fc[r['field_id']]+=1
print('中间期字段覆盖（n=86）:')
for k,v in fc.most_common(): print(f'  {k}: {v}')
# sample one company's intermediate rows
d=det[1]
print('\n样例', d['code'], d['name'])
for r in by[d['code']]['20260331']:
    print(' ', r['field_id'], r['value_cny'], r['status'], r['document_id'], r['source_page'], r['evidence_label'])
