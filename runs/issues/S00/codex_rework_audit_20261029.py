"""Independent read-only checks of S00 rework, including HOLD rows."""
import csv,json,gzip,hashlib
from pathlib import Path
from collections import Counter
ROOT=Path(__file__).resolve().parents[3]
OUT=Path(__file__).resolve().parent
def read(p):
    with p.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def hs(p):return hashlib.sha256(p.read_bytes()).hexdigest()
rs=read(OUT/'financial_normalized.csv');issues=read(OUT/'normalization_issues.csv')
cells={(r['security_id'],r['period_key'],r['period_basis'],r['field_id']):r for r in rs}
specs={'FIN.GROSSPROFIT.YTD':(['FIN.REV.YTD','FIN.COST.YTD'],lambda a:a[0]-a[1],.025),'FIN.GROSSMARGIN.PCT':(['FIN.REV.YTD','FIN.COST.YTD'],lambda a:(a[0]-a[1])/a[0]*100,.000002),'FIN.NPMARGIN.PCT':(['FIN.NPP.YTD','FIN.REV.YTD'],lambda a:a[0]/a[1]*100,.000002),'FIN.OCF_TO_NP.RATIO':(['FIN.OCF.YTD','FIN.NPP.YTD'],lambda a:a[0]/a[1],.000002)}
formula_bad=[];hold_bad=[];adopt_bad=[];formula_count=Counter();hold_count=Counter()
hold=lambda r:r and r['status']=='EXTRACTED_XCHECK_MISMATCH'
holdout={'DERIVED_HOLD_UPSTREAM','DERIVED_Q1_HOLD_UPSTREAM'}
for r in rs:
    if r['field_id'] in specs:
        deps,fn,tol=specs[r['field_id']]
        src=[cells.get((r['security_id'],r['period_key'],'YTD_CUMULATIVE',f)) for f in deps]
        if all(src):
            try:expected=fn([float(s['value_cny']) for s in src])
            except ZeroDivisionError:continue
            formula_count[r['field_id']]+=1
            if abs(float(r['value_cny'])-expected)>tol:formula_bad.append((r['security_id'],r['period_key'],r['field_id']))
            if any(hold(s) for s in src):
                hold_count['ratio_or_gp']+=1
                if r['status'] not in holdout or not r['upstream_hold_fields']:hold_bad.append((r['security_id'],r['period_key'],r['field_id']))
    if r['source_kind']=='DERIVED_DIFF' or r['status'] in ('DERIVED_Q1_EQUALS_YTD','DERIVED_Q1_HOLD_UPSTREAM'):
        fid=r['field_id'].replace('.SQ','.YTD');hi=cells.get((r['security_id'],r['period_key'],'YTD_CUMULATIVE',fid))
        suffix=r['period_key'][4:];lo_s={'0630':'0331','0930':'0630','1231':'0930'}.get(suffix)
        lo=cells.get((r['security_id'],r['period_key'][:4]+lo_s,'YTD_CUMULATIVE',fid)) if lo_s and r['source_kind']=='DERIVED_DIFF' else None
        if hi and (r['source_kind']!='DERIVED_DIFF' or lo):
            if any(hold(s) for s in (hi,lo)):
                hold_count['sq']+=1
                if r['status'] not in holdout or not r['upstream_hold_fields']:hold_bad.append((r['security_id'],r['period_key'],r['field_id']))
            exp=float(hi['value_cny'])-(float(lo['value_cny']) if lo else 0)
            if abs(float(r['value_cny'])-exp)>.03:formula_bad.append((r['security_id'],r['period_key'],r['field_id'],'SQ'))
    if r['source_kind']=='DERIVED_QUARTERLY_SUM':
        if not all(r[k] for k in ['value_before_adoption','adoption_reason','quarterly_inputs']):adopt_bad.append((r['security_id'],r['period_key'],r['field_id']))
manifest_bad=[]
for f in json.loads((OUT/'manifest.json').read_text(encoding='utf-8'))['deliverables']:
    if not (OUT/f['file']).is_file() or hs(OUT/f['file'])!=f['sha256']:manifest_bad.append(f['file'])
chain=json.loads((ROOT/'runs/issues/A04R/correction_chains.json').read_text(encoding='utf-8'))
expected={(r['security_id'],r['slot_id']):(r['original'],r['corrected']) for r in chain['rows'] if r['corrected']}
ledger={(r['security_id'],r['slot_id']):r for r in read(ROOT/'runs/collection/collection_index.csv')}
targets={k:v for k,v in expected.items() if ledger[k]['document_id']!=v[1]}
version_bad=[];version_checked=0
for r in rs:
    # source doc maps to an affected slot even when output slot_id is shared by a mixed-source period group
    affected=[(k,ids) for k,ids in targets.items() if k[0]==r['security_id'] and r['document_id'] in ids]
    for k,ids in affected:
        version_checked+=1
        if r['document_id']!=ids[1] or r['version_used']!='CORRECTED_FULLTEXT' or r['original_document_id']!=ids[0]:version_bad.append((k,r['field_id']))
master={r['security_id'] for r in read(ROOT/'data/company_master.csv')}
result={'rows':len(rs),'issues':len(issues),'companies':len({r['security_id'] for r in rs}),'company_set_exact':master=={r['security_id'] for r in rs},'duplicate_keys':len(rs)-len(cells),'formula_checked':dict(formula_count),'formula_bad':formula_bad,'hold_dependencies_checked':dict(hold_count),'hold_bad':hold_bad,'adoption_cells':sum(r['source_kind']=='DERIVED_QUARTERLY_SUM' for r in rs),'adoption_trace_bad':adopt_bad,'restatement_flags':dict(Counter(r['restatement_flag'] for r in rs)),'restatement_issue_rows':sum('RESTATEMENT' in r['issue_type'] for r in issues),'version_target_slots':len(targets),'version_rows_checked':version_checked,'version_bad':version_bad,'manifest_bad':manifest_bad,'gzip_matches_plain':hashlib.sha256(gzip.decompress((OUT/'financial_normalized.csv.gz').read_bytes())).hexdigest()==hs(OUT/'financial_normalized.csv')}
print(json.dumps(result,ensure_ascii=False,indent=2))
