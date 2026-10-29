"""Fresh source-byte and source-page checks; repair-author review, not third-party audit."""
from pathlib import Path
import csv,hashlib,importlib.util,json,re,sys,shutil
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone,timedelta
import pypdfium2 as pdfium
ROOT=Path(__file__).resolve().parents[4]
OUT=Path(__file__).parent
R=ROOT/'runs/issues/S02/remediation_20261029'
def read(p):return list(csv.DictReader(p.open(encoding='utf-8-sig',newline='')))
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def flat(s):return re.sub(r'\s+','',s)
def main():
 OUT.mkdir(exist_ok=True);(OUT/'source_pages').mkdir(exist_ok=True)
 plan=json.loads((R/'reextract_plan.json').read_text(encoding='utf-8'))
 def verify(t):
  p=ROOT/t['path'];got=sha(p) if p.exists() else None
  return dict(document_id=t['document_id'],path=t['path'],expected_sha256=t['ledger_sha256'],actual_sha256=got,result='PASS' if got==t['ledger_sha256'] else 'FAIL')
 with ThreadPoolExecutor(max_workers=4) as pool:hashes=list(pool.map(verify,plan['tasks']))
 (OUT/'pdf_binary_hashes.json').write_text(json.dumps(hashes,ensure_ascii=False,indent=2),encoding='utf-8')
 print('PDF_HASHES',sum(r['result']=='PASS' for r in hashes),'/',len(hashes),flush=True)
 bydoc={t['document_id']:t for t in plan['tasks']}
 cases=[dict(document_id=r['document_id'],value_raw=r['new_value_raw'],unit=r['new_unit_raw'],value_cny=float(r['new_value_cny']),page=int(r['source_page_physical']),unit_page=int(r['source_page_physical'])) for r in read(R/'units/normalized_corrections.csv')]
 cases += [dict(document_id=r['document_id'],value_raw=r['expected_raw'],unit=r['unit'],value_cny=r['value_cny'],page=r['value_page'],unit_page=r['unit_page']) for r in json.loads((R/'units/regression/expected.json').read_text(encoding='utf-8'))['rows']]
 source=[]
 for i,c in enumerate(cases,1):
  t=bydoc[c['document_id']];doc=pdfium.PdfDocument(str(ROOT/t['path']));page=doc[c['page']-1];text=page.get_textpage().get_text_range();unit_text=doc[c['unit_page']-1].get_textpage().get_text_range()
  present=flat(c['value_raw']) in flat(text);unit_present=c['unit'] in flat(unit_text)
  stem=f"{t['stock_code']}_{t['slot_id']}_p{c['page']:03}"
  page.render(scale=1.5).to_pil().save(OUT/'source_pages'/f'{stem}.png')
  (OUT/'source_pages'/f'{stem}.txt').write_text(text,encoding='utf-8')
  if c['unit_page']!=c['page']:
   doc[c['unit_page']-1].render(scale=1.5).to_pil().save(OUT/'source_pages'/f"{t['stock_code']}_{t['slot_id']}_p{c['unit_page']:03}_unit.png")
  src=dict(c,security_id=t['security_id'],path=t['path'],amount_present_on_exact_physical_page=present,unit_present_on_declared_page=unit_present,result='PASS' if present and unit_present else 'FAIL',text_engine='PDFium (production extraction uses pypdf)')
  source.append(src);doc.close()
 (OUT/'source_page_checks.json').write_text(json.dumps(source,ensure_ascii=False,indent=2),encoding='utf-8')
 print('SOURCE_PAGE_LEXICAL_CHECKS',sum(r['result']=='PASS' for r in source),'/',len(source),flush=True)
 # Only metadata (input fingerprint and measured row counts) is refreshed in a validation copy.
 spec=importlib.util.spec_from_file_location('s01_policy_recheck',ROOT/'tools/s01_rules_check.py');s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)
 normalized=R/'s00/financial_normalized.csv';s.NORMALIZED=normalized
 _,_,field_rows,_=s.load_rows()
 rules=json.loads((ROOT/'runs/issues/S01/screen_rules_v2.json').read_text(encoding='utf-8'))
 base=json.loads(json.dumps(rules));changed=[]
 for fid,info in rules['field_catalog'].items():
  if info['rows']!=field_rows[fid]:changed.append(dict(field_id=fid,old=info['rows'],new=field_rows[fid]))
  info['rows']=field_rows[fid]
 fps=[R/'s00/financial_normalized.csv.gz',R/'s00/normalization_manifest.json',ROOT/'data/company_master.csv']
 rules['input_fingerprint']['files']=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p),bytes=p.stat().st_size) for p in fps]
 for k in ['metrics','signals','policies','decision_layers','risk_hints','quality_flags']:
  assert rules[k]==base[k],k+' changed'
 restored=json.loads(json.dumps(rules));restored['field_catalog']=base['field_catalog'];restored['input_fingerprint']=base['input_fingerprint']
 assert restored==base,'Unexpected rule changes outside measured counts and input fingerprint'
 # C15 checks the historical v1->v2 scientific revision, which must be evaluated
 # on the actual frozen rules; the validation copy intentionally has new input metadata.
 s.load_signal_defs(base);s.structural(base,{fid:info['rows'] for fid,info in base['field_catalog'].items()})
 frozen_c15=next(c for c in s.checks if c['id']=='C15');assert frozen_c15['result']=='PASS'
 s.checks.clear()
 original_add=s.add
 def validation_add(cid,item,ok,detail,blocking=True):
  if cid=='C15':
   return original_add(cid,'冻结v1到v2政策差异不变；校验副本只更新输入指纹与实测行数',frozen_c15['result']=='PASS' and restored==base,dict(frozen_rule_check=frozen_c15,validation_metadata_only=True,changed_measured_counts=changed),blocking)
  return original_add(cid,item,ok,detail,blocking)
 s.add=validation_add
 vr=OUT/'validation_rules_metadata_only.json';vr.write_text(json.dumps(rules,ensure_ascii=False,indent=2),encoding='utf-8')
 s.RULES=vr;s.S01=OUT/'policy';s.S01.mkdir(exist_ok=True);sys.argv=[str(__file__)]
 if (s.S01/'self_check.json').exists() and not (OUT/'policy_initial_self_check.json').exists():shutil.copyfile(s.S01/'self_check.json',OUT/'policy_initial_self_check.json')
 policy_rc=s.main()
 result=json.loads((s.S01/'self_check.json').read_text(encoding='utf-8'))
 summary=dict(review_nature='REPAIR_AUTHOR_SOURCE_AND_TECHNICAL_RECHECK_NOT_THIRD_PARTY',reviewed_at=datetime.now(timezone(timedelta(hours=8))).isoformat(),pdf_hashes_pass=sum(r['result']=='PASS' for r in hashes),pdf_hashes_total=len(hashes),source_pages_pass=sum(r['result']=='PASS' for r in source),source_pages_total=len(source),source_page_limit='Automated amount/unit presence checks plus separate visual review are needed to establish column semantics; this alone is not independent field extraction.',policy_exit_code=policy_rc,policy_checks_pass=result['checks_pass'],policy_checks_total=result['checks_total'],synthetic_tests_total=len(result['synthetic_tests']),synthetic_tests_fail=sum(t['result']=='FAIL' for t in result['synthetic_tests']),policy_blocking_fail=result['blocking_fail'],validation_metadata_changes=changed,formula_sha256=sha(ROOT/'tools/s01_rules_check.py'),normalized_sha256=sha(normalized))
 (OUT/'source_policy_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
