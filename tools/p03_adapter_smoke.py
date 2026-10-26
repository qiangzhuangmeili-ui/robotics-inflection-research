"""Six bounded checks of the reusable P03 adapter; no raw financial table export."""
import json
from datetime import datetime,timezone
from pathlib import Path
from source_access import SourceAccess
ROOT=Path(__file__).resolve().parents[1]
access=SourceAccess();results=[]
for exchange,code,org in [('SH','688218','gfbj0836084'),('SZ','002031','gssz0002031'),('BJ','920207','gfbj0835207')]:
    security=exchange+':'+code
    finance=access.finance_probe(security);index=access.annual_index_probe(security,org)
    result={'security_id':security,'checked_at':datetime.now(timezone.utc).isoformat(),'financial_periods':finance['periods'],'annual_index_total':index['total'],'index_column':index['column'],'returned_security_codes':sorted(set(x['secCode'] for x in index['rows'])),'status':'PASS','research_accepted':False}
    results.append(result);print(json.dumps(result,ensure_ascii=False),flush=True)
(ROOT/'runs/issues/P03/adapter_smoke.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
