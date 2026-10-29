"""Check actual v3 adoption against the bounded source correction JSONs."""
import argparse,csv,json,hashlib
from decimal import Decimal
from pathlib import Path
HERE=Path(__file__).resolve().parent
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def period(slot,note=''):
 parts=slot.split('_');year=parts[-1]
 if note in ('Q1','Q2','Q3','Q4'):return year+{'Q1':'0331','Q2':'0630','Q3':'0930','Q4':'1231'}[note]
 return year+{'annual':'1231','h1':'0630','q1':'0331','q3':'0930'}[parts[0]]
def main():
 ap=argparse.ArgumentParser();ap.add_argument('output_directory');args=ap.parse_args();out=Path(args.output_directory)
 rows=list(csv.DictReader((out/'s00/financial_normalized.csv').open(encoding='utf-8-sig')))
 matrix={(r['security_id'],r['period_key'],r['field_id']):r for r in rows}
 checks=[];errors=[];held=[]
 for group in ('xcheck11','scope5','ocr2'):
  for path in sorted((HERE/group/'corrected_results').glob('*.json')):
   r=read(path)
   for f in r['fields']:
    if f['field_id']=='FIN.RESTATEMENT':continue
    if f['extract_status']=='STMT_SCOPE_HOLD':
     n=matrix.get((r['security_id'],period(r['slot_id']),f['field_id']))
     if n and n['document_id']==r['document_id'] and n['value_cny']:
      errors.append(dict(kind='HELD_SOURCE_LEAKED',source=str(path),field=f['field_id'],normalized=n))
     held.append([r['document_id'],f['field_id']]);continue
    if f['extract_status']!='EXTRACTED' or f['value_cny'] in ('',None):continue
    pk=period(r['slot_id'],f.get('note',''));key=(r['security_id'],pk,f['field_id']);n=matrix.get(key)
    item=dict(security_id=r['security_id'],period_key=pk,field_id=f['field_id'],source_document=r['document_id'],source_file=str(path.relative_to(HERE)),source_value=str(f['value_cny']))
    if n is None:
     item.update(result='FAIL',reason='EXTRACTED_SOURCE_NOT_ADOPTED');errors.append(item);checks.append(item);continue
    same_doc=n['document_id']==r['document_id'] or r['document_id'] in n['document_id'].split('|')
    value_match=bool(n['value_cny']) and abs(Decimal(n['value_cny'])-Decimal(str(f['value_cny'])))<=Decimal('.01')
    original_match=bool(n.get('value_before_adoption')) and abs(Decimal(n['value_before_adoption'])-Decimal(str(f['value_cny'])))<=Decimal('.01')
    # Another directly disclosed official quarterly table may legitimately win.
    alternate_official=f['field_id'].endswith('.SQ') and n['source_kind']=='PDF_QUARTERLY_TABLE' and value_match
    ok=(same_doc and (value_match or original_match)) or alternate_official
    item.update(result='PASS' if ok else 'FAIL',normalized_document=n['document_id'],normalized_value=n['value_cny'],normalized_status=n['status'],reason='DIRECT' if same_doc and value_match else 'ARBITRATION_PRESERVES_ORIGINAL' if same_doc and original_match else 'SAME_OFFICIAL_QUARTER_VALUE' if alternate_official else 'SOURCE_ADOPTION_DIFF')
    checks.append(item)
    if not ok:errors.append(item)
 report=dict(review_nature='SELF_CHECK',decision='PASS' if not errors else 'FAIL',source_value_checks=len(checks),scope_held_field_checks=len(held),errors=errors,checks=checks,s03_release=False)
 (out/'source_adoption_check.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({k:v for k,v in report.items() if k!='checks'},ensure_ascii=False,indent=2));return bool(errors)
if __name__=='__main__':raise SystemExit(main())
