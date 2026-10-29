import csv,sys,json
from pathlib import Path
from pypdf import PdfReader
ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT/'tools'))
import a03_financial_field_extractor as A
idx=list(csv.DictReader((ROOT/'runs/collection/collection_index.csv').open(encoding='utf-8-sig')))
for code,slot in [('000333','h1_2026'),('601138','h1_2026'),('920146','h1_2026'),('600196','h1_2026'),('000601','q3_2026'),('688187','h1_2026')]:
 r=next(r for r in idx if r['security_id'].endswith(code) and r['slot_id']==slot)
 rd=PdfReader(ROOT/r['local_file']); chunks=[]
 for i,p in enumerate(rd.pages):
  t=p.extract_text() or ''
  if ('资产负债表' in t and ('货币资金' in t or '财务报表' in t)) or ('利润表' in t and '营业收入' in t) or ('现金流量表' in t and '经营活动' in t):
   chunks.append(f'=== PHYSICAL PAGE {i+1} ===\n'+t)
 out=Path(__file__).parent/f'probe_{code}.txt';out.write_text('\n'.join(chunks),encoding='utf-8')
 print(code, str(out), len(chunks),flush=True)
