"""Read-only S00 output checks. Does not run producer or alter existing results."""
import csv,json,gzip,hashlib
from pathlib import Path
from collections import Counter,defaultdict
from decimal import Decimal,InvalidOperation
ROOT=Path(__file__).resolve().parents[3]
OUT=Path(__file__).resolve().parent
def rows(p):
    with (ROOT/p).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
r=rows('runs/issues/S00/financial_normalized.csv')
issues=rows('runs/issues/S00/normalization_issues.csv')
master={x['security_id'] for x in rows('data/company_master.csv')}
keys=Counter((x['security_id'],x['period_key'],x['period_basis'],x['field_id']) for x in r)
cells={(x['security_id'],x['period_key'],x['period_basis'],x['field_id']):x for x in r}
conv=[]
for x in r:
    if x['value_raw'] and x['unit_scale'] and x['unit_scale'] not in ('pct','times'):
        try:
            a=Decimal(x['value_raw'].replace(',','').replace('，',''))*Decimal(x['unit_scale']);b=Decimal(x['value_cny'])
            if abs(a-b)>Decimal('0.02'):conv.append({k:x[k] for k in ['security_id','period_key','field_id','status','value_raw','unit_raw','unit_scale','value_cny']})
        except InvalidOperation:pass
formula_specs=[('FIN.GROSSPROFIT.YTD',['FIN.REV.YTD','FIN.COST.YTD'],lambda v:v[0]-v[1],.02),('FIN.GROSSMARGIN.PCT',['FIN.REV.YTD','FIN.COST.YTD'],lambda v:(v[0]-v[1])/v[0]*100,.000002),('FIN.NPMARGIN.PCT',['FIN.NPP.YTD','FIN.REV.YTD'],lambda v:v[0]/v[1]*100,.000002),('FIN.OCF_TO_NP.RATIO',['FIN.OCF.YTD','FIN.NPP.YTD'],lambda v:v[0]/v[1],.000002)]
formula_bad=[]; formula_count=Counter()
for x in r:
    for target,deps,fn,tol in formula_specs:
        if x['field_id']!=target or x['status']!='DERIVED':continue
        src=[cells.get((x['security_id'],x['period_key'],'YTD_CUMULATIVE',fid)) for fid in deps]
        if not all(src):continue
        try:expected=fn([float(v['value_cny']) for v in src])
        except ZeroDivisionError:continue
        if abs(float(x['value_cny'])-expected)>tol:
            formula_count[target]+=1
            formula_bad.append({'security_id':x['security_id'],'period_key':x['period_key'],'field_id':target,'actual':x['value_cny'],'expected':expected,'input_statuses':[v['status'] for v in src]})
manifest=json.loads((OUT/'manifest.json').read_text(encoding='utf-8'))
manifest_bad=[]
for f in manifest['deliverables']:
    p=OUT/f['file']
    if not p.is_file() or sha(p)!=f['sha256']:manifest_bad.append(f['file'])
norm_manifest=json.loads((OUT/'normalization_manifest.json').read_text(encoding='utf-8'))
extract_bad=[f['file'] for f in norm_manifest.get('extract_artifacts',[]) if sha(OUT/f['file'])!=f['sha256']]
gz_sha=hashlib.sha256(gzip.decompress((OUT/'financial_normalized.csv.gz').read_bytes())).hexdigest()
restate=Counter()
for p in (OUT/'extract').glob('*_fields.csv'):
    with p.open(encoding='utf-8-sig',newline='') as f:
        for x in csv.DictReader(f):
            if x['field_id']=='FIN.RESTATEMENT':restate[x['extract_status']+':'+x['value_raw']]+=1
dirty_ratios=0
for x in r:
    for target,deps,_,_ in formula_specs:
        if x['field_id']==target and x['status']=='DERIVED':
            if any(cells.get((x['security_id'],x['period_key'],'YTD_CUMULATIVE',fid),{}).get('status')=='EXTRACTED_XCHECK_MISMATCH' for fid in deps):dirty_ratios+=1
result={'rows':len(r),'issues':len(issues),'companies':len({x['security_id'] for x in r}),'missing_companies':sorted(master-{x['security_id'] for x in r}),'extra_companies':sorted({x['security_id'] for x in r}-master),'duplicate_cell_keys':sum(v>1 for v in keys.values()),'status_counts':dict(Counter(x['status'] for x in r)),'conversion_mismatch_count':len(conv),'conversion_mismatch_samples':conv[:8],'formula_mismatch_counts':dict(formula_count),'formula_mismatch_samples':formula_bad[:12],'manifest_mismatches':manifest_bad,'extract_hash_mismatches':extract_bad,'gzip_matches_plain':gz_sha==sha(OUT/'financial_normalized.csv'),'blank_values':sum(not x['value_cny'] for x in r),'blocking_issues':sum(x['blocking_for_indicator']=='YES' for x in issues),'extract_restatement_counts':dict(restate),'normalized_restatement_counts':dict(Counter(x['restatement_flag'] for x in r)),'restatement_issue_rows':sum('RESTATEMENT' in x['issue_type'] for x in issues),'derived_ratios_or_gp_from_mismatch_parent':dirty_ratios}
print(json.dumps(result,ensure_ascii=False,indent=2))
