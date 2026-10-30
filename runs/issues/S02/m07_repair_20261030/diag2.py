import csv, collections, json, os
BASE=r"C:/Users/zhangjianmei/Documents/ChatGPT/机器人企业行业拐点研究/robotics-inflection-research/runs/issues/S02/remediation_20261029/collect_q3_2026"
s=list(csv.DictReader(open(os.path.join(BASE,'s00_v7.csv'),encoding='utf-8-sig')))
det=json.load(open('m07_detail.json',encoding='utf-8'))
by=collections.defaultdict(lambda: collections.defaultdict(set))
for r in s:
    by[r['stock_code']][r['period_key']].add(r['field_id'])
rows=[]
for d in det:
    per=d['period']; q1='20260331' if per=='20260630' else '20260630'
    rows.append((d['code'],d['name'],per,q1,
                 'Q1有记录' if by[d['code']][q1] else 'Q1无任何记录',
                 len(by[d['code']][q1]),
                 'NPDEDT.YTD' in by[d['code']][q1],
                 'REV.YTD' in by[d['code']][q1],
                 'NPDEDT.YTD' in by[d['code']][per]))
c=collections.Counter((r[4],r[6]) for r in rows)
for k,v in c.items(): print(k,v)
print('--- Q1 无任何记录的公司:')
for r in rows:
    if r[4]=='Q1无任何记录': print(r)
