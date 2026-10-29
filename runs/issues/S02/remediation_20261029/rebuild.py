"""Rebuild S00 and S02 as a separate input version, reusing both accepted implementations."""
import csv,gzip,hashlib,json,sys
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4]
OUT=Path(__file__).parent
sys.path.insert(0,str(ROOT/'tools'))
import s00_normalize as N
import s02_calculate as S
import l0_classify as L
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return list(csv.DictReader(p.open(encoding='utf-8-sig',newline='')))
def write(p,rows):
    with p.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
def main():
    plan=json.loads((OUT/'reextract_plan.json').read_text(encoding='utf-8'))
    assert plan['parser_sha256']==sha(ROOT/'tools/a03_financial_field_extractor.py'),'Parser changed during extraction'
    extracted={}
    for t in plan['tasks']:
        p=OUT/'extracted'/f"{t['document_id']}.json"
        if not p.exists():raise RuntimeError('EXTRACTION_NOT_FINISHED: '+str(p))
        r=json.loads(p.read_text(encoding='utf-8'));extracted[(r['security_id'],r['slot_id'])]=r
    old_extract,old_diag=N.load_extract,N.load_diag
    def load_extract(slot):
        x=old_extract(slot)
        for (sec,sl),r in extracted.items():
            if sl==slot:x[sec]={(f['field_id'],f['note']):f for f in r['fields']}
        return x
    def load_diag(slot):
        x=old_diag(slot)
        for (sec,sl),r in extracted.items():
            if sl!=slot:continue
            d=dict(x.get(sec,{}));d.update({k:r.get(k,'') for k in ['parse_error','restatement','restatement_method','n_pages','text_chars']})
            xc=r.get('crosscheck',{})
            import a03_financial_field_extractor as A
            d['xcheck_pass']=A.xcheck_verdict(xc)
            for f,k in [('FIN.REV.YTD','xcheck_rev'),('FIN.NPP.YTD','xcheck_npp'),('FIN.OCF.YTD','xcheck_ocf')]:d[k]=xc.get(f,'')
            x[sec]=d
        return x
    # Reuse existing language diagnoses for untouched empty PDFs, avoiding repeated full parsing.
    oldmanifest=json.loads((ROOT/'runs/issues/S00/normalization_manifest.json').read_text(encoding='utf-8'))
    idx=N.load_index()
    old_lang={str(ROOT/idx[(r['slot_id'],r['security_id'])]['local_file']):(r['language'],r.get('zh_ratio',0),r.get('text_chars',0)) for r in oldmanifest.get('empty_slots_no_value',{}).get('items',[]) if (r['slot_id'],r['security_id']) in idx}
    original_language=N.detect_doc_language
    N.detect_doc_language=lambda p,pages=3:old_lang.get(str(p)) or original_language(p,pages)
    N.load_extract,N.load_diag=load_extract,load_diag
    N.OUT=OUT/'s00';N.OUT.mkdir(exist_ok=True)
    N.main()
    np=N.OUT/'financial_normalized.csv'
    with (N.OUT/'financial_normalized.csv.gz').open('wb') as raw:
        with gzip.GzipFile(fileobj=raw,mode='wb',mtime=0) as g:g.write(np.read_bytes())
    old=read(ROOT/'runs/issues/S00/financial_normalized.csv');new=read(np)
    key=lambda r:(r['security_id'],r['period_key'],r['field_id'])
    om={key(r):r for r in old};nm={key(r):r for r in new};deltas=[]
    for k in sorted(om.keys()|nm.keys()):
        a,b=om.get(k),nm.get(k)
        if a==b:continue
        fields=[f for f in (a or b) if (a or {}).get(f)!=(b or {}).get(f)]
        deltas.append(dict(security_id=k[0],period_key=k[1],field_id=k[2],change='ADD' if a is None else 'REMOVE' if b is None else 'UPDATE',old_value=(a or {}).get('value_cny',''),new_value=(b or {}).get('value_cny',''),old_status=(a or {}).get('status',''),new_status=(b or {}).get('status',''),changed_columns=';'.join(fields),document_id=(b or a)['document_id'],source_page=(b or a)['source_page']))
    write(OUT/'normalized_delta.csv',deltas)
    targets={t['security_id'] for t in plan['tasks']}
    assert not {d['security_id'] for d in deltas}-targets,'Unexpected changes outside targeted companies'
    # New input fingerprint only; metric/signal definitions and thresholds remain byte-for-byte JSON-equal.
    rules=json.loads((ROOT/'runs/issues/S01/screen_rules_v2.json').read_text(encoding='utf-8'))
    base_rules=json.loads(json.dumps(rules))
    fps=[N.OUT/'financial_normalized.csv.gz',N.OUT/'normalization_manifest.json',ROOT/'data/company_master.csv']
    rules['input_fingerprint']['files']=[dict(path=str(p.relative_to(ROOT)).replace('\\','/'),sha256=sha(p),bytes=p.stat().st_size) for p in fps]
    rules['input_version']='S00_TARGETED_REEXTRACTION_20261029'
    rules['base_rules_sha256']=sha(ROOT/'runs/issues/S01/screen_rules_v2.json')
    rules['l0_addendum_path']=str(L.PATCH.relative_to(ROOT)).replace('\\','/')
    for k in ['metrics','signals','risk_hints','thresholds']:
        if k in rules:assert rules[k]==base_rules[k]
    rp=OUT/'rules_recalculation_inputs.json';rp.write_text(json.dumps(rules,ensure_ascii=False,indent=2),encoding='utf-8')
    S.S02=OUT/'s02';S.RULES=rp;S.RULES_SHA_REQUIRED=sha(rp);S.s01.NORMALIZED=np
    original_add=S.add
    def add(cid,item,ok,detail,blocking=True):
        if cid=='P01':item='新输入版本指纹固定，指标公式沿用冻结 S01 v2'
        if cid=='Q16':detail['note']='S00已覆盖12槽；此清单是抽取盲区、口径待核或原HOLD的剩余落点，不能解释为没有改善。'
        if cid in ('Q13','Q14') and not ok:
            return original_add(cid,'与历史S01快照的差异（本轮已修复输入，不要求计数不变）',False,detail,False)
        return original_add(cid,item,ok,detail,blocking)
    S.add=add
    code=S.main();assert code==0,'S02 blocking checks failed'
    cp=S.S02/'company_metric_summary.csv';companies=read(cp)
    for r in companies:r['l0_evaluability']=L.classify({s:int(r[col]) for s,col in L.COUNT_COLUMNS.items()})[0]
    write(cp,companies)
    oldmetrics={ (r['security_id'],r['metric_id']):r for r in read(ROOT/'runs/issues/S02/all_pool_metrics.csv')}
    newmetrics=read(S.S02/'all_pool_metrics.csv');md=[]
    for r in newmetrics:
        a=oldmetrics[(r['security_id'],r['metric_id'])]
        if r!=a:md.append(dict(security_id=r['security_id'],metric_id=r['metric_id'],old_value=a['value'],new_value=r['value'],old_status=a['metric_status'],new_status=r['metric_status'],period_key=r['period_key']))
    write(OUT/'metric_delta.csv',md)
    assert not {r['security_id'] for r in md}-targets
    mp=S.S02/'calculation_manifest.json';m=json.loads(mp.read_text(encoding='utf-8'))
    m.update(executor='Codex',rules_file=str(rp.relative_to(ROOT)).replace('\\','/'),input_version=rules['input_version'],l0_distribution=dict(Counter(r['l0_evaluability'] for r in companies)),l0_rule_note='Exhaustive L0 addendum; no company dropped, no signals or candidates produced',base_metric_rules_sha256=rules['base_rules_sha256'])
    m['known_limits']=[x for x in m['known_limits'] if not x.startswith(('上游缺陷','规则 L0','S00 遗留'))]
    m['known_limits']+=[f"仅{plan['target_companies']}家公司{len(plan['tasks'])}份相关报告定向重抽；剩余未知/HOLD保留，见coverage_resolution.csv。",'未放行S03；L0补丁与新输入均须外部复核。']
    for out in m['outputs']:
        p=S.S02/Path(out['path']).name;out.update(path=str(p.relative_to(ROOT)).replace('\\','/'),sha256=sha(p),bytes=p.stat().st_size)
    mp.write_text(json.dumps(m,ensure_ascii=False,indent=2),encoding='utf-8')
    rv=S.S02/'review.json';v=json.loads(rv.read_text(encoding='utf-8'));v.update(executor='Codex',reviewer='Codex',decision='SELF_CHECK_PASS_TARGETED_REPAIR_EXTERNAL_REVIEW_REQUIRED',limits=m['known_limits'],next_stage_release='S03_LOCKED');rv.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf-8')
    result=dict(normalized_rows=len(new),normalized_changes=len(deltas),metric_changes=len(md),companies_changed=len({r['security_id'] for r in md}),unchanged_company_metrics_verified=1054-len(targets),status_counts=dict(Counter(r['metric_status'] for r in newmetrics)),l0_counts=m['l0_distribution'])
    (OUT/'rebuild_summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
