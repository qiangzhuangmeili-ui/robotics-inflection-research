import csv, json, sys
from pathlib import Path
from collections import Counter
ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT/'tools'))
import s02_calculate as s02
OUT = Path(__file__).parent
def read(p):
    return list(csv.DictReader(p.open(encoding='utf-8-sig', newline='')))
def main():
    rows, meta, _, _ = s02.s01.load_rows()
    latest = s02.latest_periods(rows)
    index = {(r['security_id'],r['slot_id']):r for r in read(ROOT/'runs/collection/collection_index.csv')}
    master = {r['security_id']:r for r in read(ROOT/'data/company_master.csv')}
    out=[]
    for sec,pk in sorted(latest.items()):
        fs=['FIN.REV.YTD','FIN.REV.SQ','FIN.NPDEDT.YTD','FIN.NPDEDT.SQ','FIN.COST.YTD','FIN.OCF.YTD','FIN.NPP.YTD','FIN.AR.INSTANT','FIN.INV.INSTANT','FIN.ASSET.INSTANT','FIN.CONTRACTASSET.INSTANT','FIN.GROSSMARGIN.PCT']
        n=sum(1 for f,r in rows[(sec,pk)].items() if f in fs and r['value'] is not None and r['status'] in s02.s01.USABLE|s02.s01.USABLE_FLAG)
        if n>=8: continue
        slot={'0331':'q1','0630':'h1','0930':'q3','1231':'annual'}[str(pk)[4:]]+'_'+str(pk)[:4]
        ix=index[(sec,slot)]
        dg=next((r for r in read(ROOT/f'runs/issues/S00/extract/{slot}_diag.csv') if r['security_id']==sec),{})
        out.append(dict(security_id=sec,stock_name=master[sec]['stock_name'],period_key=pk,fields_usable=n,slot_id=slot,document_id=ix['document_id'],pages=ix['page_count'],path=ix['local_file'],parse_error=dg.get('parse_error'),bs_start=dg.get('bs_start'),is_start=dg.get('is_start'),cf_start=dg.get('cf_start'),unit_bs=dg.get('unit_bs'),unit_is=dg.get('unit_is'),text_chars=dg.get('text_chars')))
    (OUT/'coverage_baseline.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(out,ensure_ascii=False,indent=2))
if __name__=='__main__': main()
