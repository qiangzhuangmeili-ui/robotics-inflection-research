import csv,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4];OUT=Path(__file__).parent/'ocr2'
sys.path.insert(0,str(ROOT/'tools'))
import a03_financial_field_extractor as A
def main():
 rows={r['document_id']:r for r in csv.DictReader((ROOT/'runs/collection/collection_index.csv').open(encoding='utf-8-sig'))}
 for dest in OUT.iterdir():
  if not dest.is_dir() or dest.name not in rows:continue
  r=rows[dest.name];task=dict(document_id=r['document_id'],security_id=r['security_id'],stock_code=r['security_id'].split(':')[1],slot_id=r['slot_id'],period_label=r['period_label'],path=str(ROOT/r['local_file']),ledger_sha256=r['sha256'])
  original=A.parse_pdf
  cache=OUT/(r['document_id']+'_text.json')
  if cache.exists():
   pages=json.loads(cache.read_text(encoding='utf-8'));parsed=dict(pages=pages,n_pages=len(pages),error=None)
  else:parsed=original(task['path'],max_scan=500)
  for p in dest.glob('p*.json'):
   o=json.loads(p.read_text(encoding='utf-8'));parsed['pages'][o['pdf_page']-1]=o['text']
  A.parse_pdf=lambda *a,**kw:parsed
  result=A.extract_one(task);A.parse_pdf=original
  result['recovery_method']='OCR_REPLAY_UNREVIEWED';(OUT/(dest.name+'_draft.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
  print(json.dumps(dict(doc=dest.name,slot=r['slot_id'],units=[result.get('unit_bs'),result.get('unit_is'),result.get('unit_cf')],restatement=result.get('restatement'),crosscheck=result.get('crosscheck'),fields=[(f['field_id'],f['value_raw'],f['page'],f['note']) for f in result['fields'] if f['extract_status']=='EXTRACTED']),ensure_ascii=False))
if __name__=='__main__':main()
