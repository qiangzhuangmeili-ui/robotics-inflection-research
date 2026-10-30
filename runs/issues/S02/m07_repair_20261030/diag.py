import csv, collections, json, os
BASE=r"C:/Users/zhangjianmei/Documents/ChatGPT/机器人企业行业拐点研究/robotics-inflection-research/runs/issues/S02/remediation_20261029/collect_q3_2026"
m=list(csv.DictReader(open(os.path.join(BASE,'s02_v7_guarded','all_pool_metrics.csv'),encoding='utf-8-sig')))
m7=[r for r in m if r['metric_id']=='M07' and r['metric_status']=='MISSING']
codes={r['stock_code']:r for r in m7}
s=list(csv.DictReader(open(os.path.join(BASE,'s00_v7.csv'),encoding='utf-8-sig')))
idx=collections.defaultdict(list)
for r in s:
    idx[(r['stock_code'],r['field_id'],r['period_key'])].append(r)

stat=collections.Counter()
detail=[]
for code,row in codes.items():
    per=row['period_key']
    q1 = '20260331' if per=='20260630' else '20260630'
    ytd_t = idx.get((code,'FIN.NPDEDT.YTD',per))
    ytd_q1 = idx.get((code,'FIN.NPDEDT.YTD',q1))
    sq_t = idx.get((code,'FIN.NPDEDT.SQ',per))
    sq_b = idx.get((code,'FIN.NPDEDT.SQ',row['base_period_key']))
    key=(bool(ytd_t),bool(ytd_q1),bool(sq_t),bool(sq_b))
    stat[key]+=1
    detail.append(dict(code=code,name=row['stock_name'],period=per,
        ytd_t=(ytd_t[0]['value_cny'],ytd_t[0]['status']) if ytd_t else None,
        ytd_q1=(ytd_q1[0]['value_cny'],ytd_q1[0]['status']) if ytd_q1 else None,
        sq_t=(sq_t[0]['value_cny'],sq_t[0]['status']) if sq_t else None,
        sq_b=(sq_b[0]['value_cny'],sq_b[0]['status']) if sq_b else None))
print('total', len(codes))
for k,v in sorted(stat.items(), key=lambda x:-x[1]):
    print('YTD_t=%s YTD_q1=%s SQ_t=%s SQ_base=%s -> %d'%(*k,v))
json.dump(detail,open('m07_detail.json','w',encoding='utf-8'),ensure_ascii=False,indent=1)
