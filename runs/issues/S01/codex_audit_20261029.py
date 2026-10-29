"""Read-only checks and synthetic boundary probes. Never calls producer main()."""
import sys,json,hashlib
from pathlib import Path
from collections import Counter
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'tools'))
import s01_rules_check as s
OUT=Path(__file__).resolve().parent
def hs(p):return hashlib.sha256(p.read_bytes()).hexdigest()
rules=json.loads((OUT/'screen_rules_v1.json').read_text(encoding='utf-8'))
manifest=json.loads((OUT/'manifest.json').read_text(encoding='utf-8'))
rows,meta,field_counts,companies=s.load_rows()
latest={}
for (sec,pk),fields in rows.items():
    if any(fields.get(f) and s.classify(fields[f]) in ('OK','LEGACY') for f in ('FIN.REV.YTD','FIN.REV.SQ','FIN.NPDEDT.YTD')):latest[sec]=max(latest.get(sec,0),pk)
confirmed_restate_ok=0
for sec,pk in latest.items():
    base=s.prior_year(pk); a=rows.get((sec,pk),{}).get('FIN.REV.YTD');b=rows.get((sec,base),{}).get('FIN.REV.YTD')
    out=s.metric_ratio(rows,sec,pk,base,'FIN.REV.YTD',low_base_value=s.LOW_BASE_REV)
    if a and b and any(x['restate']=='是' for x in (a,b)) and out['status']=='OK':confirmed_restate_ok+=1
def rec(v,**kw):return dict({'value':v,'status':'EXTRACTED','low_base':'','restate':'否','scope':'CONSOLIDATED','pre_listing':'NO'},**kw)
gm={('X',20260630):{'FIN.GROSSMARGIN.PCT':rec(1)},('X',20250630):{'FIN.GROSSMARGIN.PCT':rec(0)}}
restate={('X',20260630):{'FIN.REV.YTD':rec(120000000,restate='是')},('X',20250630):{'FIN.REV.YTD':rec(100000000)}}
scope={('X',20260630):{'FIN.REV.YTD':rec(120000000,scope='PARENT_ONLY',pre_listing='YES')},('X',20250630):{'FIN.REV.YTD':rec(100000000)}}
ca={('X',20260630):{'FIN.CONTRACTASSET.INSTANT':rec(10000000,restate=s.RESTATE_PENDING),'FIN.REV.YTD':rec(100000000)},('X',20250630):{'FIN.CONTRACTASSET.INSTANT':rec(1000000),'FIN.REV.YTD':rec(100000000)}}
result={'input_hash_bad':[f['path'] for f in rules['input_fingerprint']['files'] if hs(ROOT/f['path'])!=f['sha256']],'manifest_bad':[f['path'] for f in manifest['outputs'] if hs(ROOT/f['path'])!=f['sha256']],'field_catalog_count_mismatches':[fid for fid,v in rules['field_catalog'].items() if field_counts[fid]!=v['rows']],'companies':len(companies),'latest_distribution':dict(Counter(latest.values())),'latest_M01_confirmed_restatement_returned_OK':confirmed_restate_ok,'zero_prior_gm_fixture':s.metric_gm(gm,'X',20260630,20250630),'confirmed_restatement_fixture':s.metric_ratio(restate,'X',20260630,20250630,'FIN.REV.YTD'),'prelisting_parent_scope_fixture':s.metric_ratio(scope,'X',20260630,20250630,'FIN.REV.YTD'),'M12_pending_restatement_fixture':s.metric_ca_ratio(ca,'X',20260630,20250630)}
print(json.dumps(result,ensure_ascii=False,indent=2))
