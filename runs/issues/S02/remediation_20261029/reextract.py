"""S00 source repair experiment. Immutable PDFs and frozen outputs are never written."""
import argparse,csv,hashlib,json,sys,time
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor,as_completed
ROOT=Path(__file__).resolve().parents[4]
OUT=Path(__file__).parent
sys.path.insert(0,str(ROOT/'tools'))
import a03_financial_field_extractor as A
import s02_calculate as S
def read(p):return list(csv.DictReader(p.open(encoding='utf-8-sig',newline='')))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def slot(pk):return {'0331':'q1','0630':'h1','0930':'q3','1231':'annual'}[str(pk)[4:]]+'_'+str(pk)[:4]
def one(task):
    p=ROOT/task['path']
    if sha(p)!=task['ledger_sha256']:return dict(task,parse_error='BINARY_HASH_MISMATCH',fields=[])
    return A.extract_one(dict(task,path=str(p)))
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--workers',type=int,default=6);ap.add_argument('--refresh',action='store_true');args=ap.parse_args()
    (OUT/'extracted').mkdir(exist_ok=True)
    rows,_,_,_=S.s01.load_rows();latest=S.latest_periods(rows)
    targets={r['security_id'] for r in json.loads((OUT/'coverage_baseline.json').read_text(encoding='utf-8'))}
    targets.update('SZ:'+c for c in ['002420','002460','300420','300678','301041','000333','003032'])
    index={(r['security_id'],r['slot_id']):r for r in read(ROOT/'runs/collection/collection_index.csv')}
    tasks=[];unavailable=[]
    for sec in sorted(targets):
      pk=latest[sec];periods={pk,pk-10000,S.s01.prior_quarter(pk),S.s01.prior_quarter(pk)-10000}
      # 单季由累计相减的上游也必须重抽，而不能混用旧值。
      for p in list(periods):
       if str(p)[4:]!='0331':periods.add(S.s01.prior_quarter(p))
      slots={slot(p) for p in periods}
      # 同一公司的2025/2026各槽一并重抽，避免累计修复后用旧错误累计派生相邻单季。
      slots.update(sl for (s,sl) in index if s==sec and sl.endswith(('_2025','_2026')))
      for sl in sorted(slots):
       r=index.get((sec,sl),{})
       if r.get('status')!='COLLECTED_IDENTITY_VERIFIED' or not r.get('local_file'):
        unavailable.append(dict(security_id=sec,slot_id=sl,status=r.get('status','NO_LEDGER_ROW')));continue
       # 采用已核的更正全文（与 S00 版本映射一致），不回退到原版。
       period=int(sl.split('_')[1]+{'q1':'0331','h1':'0630','q3':'0930','annual':'1231'}[sl.split('_')[0]])
       norm=next((x for x in rows.get((sec,period),{}).values() if x['version_used']=='CORRECTED_FULLTEXT'),None)
       if norm and norm['document_id']!=r['document_id']:
        raise RuntimeError('CORRECTED_VERSION_REQUIRES_EXPLICIT_TASK: '+sec+' '+sl)
       tasks.append(dict(security_id=sec,stock_code=sec.split(':')[1],slot_id=sl,period_label=r['period_label'],document_id=r['document_id'],path=r['local_file'],ledger_sha256=r['sha256']))
    manifest=dict(target_companies=len(targets),coverage_companies=53,tasks=tasks,unavailable=unavailable,parser_sha256=sha(ROOT/'tools/a03_financial_field_extractor.py'))
    (OUT/'reextract_plan.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    pending=[t for t in tasks if args.refresh or not (OUT/'extracted'/f"{t['document_id']}.json").exists()]
    print(f'targets={len(targets)} tasks={len(tasks)} pending={len(pending)} unavailable={len(unavailable)}',flush=True)
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
      futs={pool.submit(one,t):t for t in pending}
      for i,f in enumerate(as_completed(futs),1):
       t=futs[f]
       try:r=f.result()
       except Exception as e:r=dict(t,parse_error=repr(e),fields=[])
       (OUT/'extracted'/f"{t['document_id']}.json").write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8')
       print(i,len(pending),t['security_id'],t['slot_id'],r.get('parse_error') or '',sum(x['extract_status']=='EXTRACTED' for x in r['fields']),flush=True)
if __name__=='__main__':main()
