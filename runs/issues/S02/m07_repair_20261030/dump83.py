import json, sys
from pathlib import Path
ROOT = Path(r"C:/Users/zhangjianmei/Documents/ChatGPT/机器人企业行业拐点研究/robotics-inflection-research")
sys.path.insert(0, str(ROOT/'tools'))
import a03_financial_field_extractor as A
survey = json.load(open('survey.json', encoding='utf-8'))
rows=[]
for x in survey:
    if not x.get('exists'): continue
    r = A.extract_one(dict(document_id=x['doc'], security_id='', stock_code=x['code'],
                           slot_id=x['slot'], period_label=x['mid'], path=str(ROOT/x['file'])))
    kf = r.get('key_financials_values') or {}; d = r.get('key_financials_details') or {}
    rows.append(dict(code=x['code'], name=x['name'], slot=x['slot'],
                     rev=kf.get('FIN.REV.YTD'), npp=kf.get('FIN.NPP.YTD'),
                     npdedt=kf.get('FIN.NPDEDT.YTD'), ocf=kf.get('FIN.OCF.YTD'),
                     page=(d.get('FIN.NPDEDT.YTD') or {}).get('page'),
                     col=(d.get('FIN.NPDEDT.YTD') or {}).get('column_index'),
                     raw=(d.get('FIN.NPDEDT.YTD') or {}).get('raw_row','')[:110]))
json.dump(rows, open('dump83.json','w',encoding='utf-8'), ensure_ascii=False, indent=1)
ok=[r for r in rows if r['npdedt']]
print('有扣非', len(ok), '/', len(rows))
for r in ok[:12]:
    print(f"{r['code']} {r['name'][:6]:<7} p{r['page']} c{r['col']} 扣非={r['npdedt']:>18} | {r['raw'][:80]}")
