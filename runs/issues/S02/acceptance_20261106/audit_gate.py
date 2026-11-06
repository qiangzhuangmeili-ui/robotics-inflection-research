"""Read-only audit of frozen S02 v10; writes only to this review directory."""
import csv, gzip, hashlib, json, re
from collections import Counter, defaultdict
from decimal import Decimal as D
from datetime import date
from pathlib import Path

ROOT=Path(__file__).resolve().parents[4]
OUT=Path(__file__).resolve().parent
BASE=ROOT/'runs/issues/S02/hangcha_restated_20261101'
snap=json.loads((ROOT/'runs/issues/S02/S02_final_snapshot.json').read_text(encoding='utf-8'))
def read(p):
    with open(p,encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def blob(p):
    b=p.read_bytes();return hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()
def write(name,rows):
    if not rows:return
    with (OUT/name).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
metrics=read(BASE/'s02_v10/all_pool_metrics.csv')
replay=read(OUT/'replay/all_pool_metrics.csv')
with gzip.open(BASE/'s00_v10/s00_v10.csv.gz','rt',encoding='utf-8-sig',newline='') as f: norm=list(csv.DictReader(f))
data={(r['security_id'],int(r['period_key']),r['field_id']):r for r in norm}
diff=[r for r,a in zip(metrics,replay) if r!=a]
dates=defaultdict(set)
for r in norm:
    for doc in re.findall(r'DOC-[A-Z0-9]+',r['document_id']):
        if r['published_on']: dates[doc].add(r['published_on'][:10])
arithmetic=Counter();errors=[];future=[];unknown=[];source_missing=[]
def val(sec,pk,f):return D(data[(sec,pk,f)]['value_cny'])
def quarter(pk):return int(str(pk)[:4]+{'0331':'1231','0630':'0331','0930':'0630','1231':'0930'}[str(pk)[4:]])-(10000 if str(pk)[4:]=='0331' else 0)
for r in metrics:
    s,p,m=r['security_id'],int(r['period_key']),r['metric_id'];b=p-10000
    docs=set(re.findall(r'DOC-[A-Z0-9]+',r['source_refs']))
    late=sorted(d for d in docs if any(x>'2026-10-25' for x in dates[d]))
    if late:future.append(dict(security_id=s,stock_name=r['stock_name'],metric_id=m,metric_status=r['metric_status'],documents=';'.join(late),published_on=';'.join(sorted({x for d in late for x in dates[d]}))))
    if docs and any(not dates[d] for d in docs):unknown.append((s,m))
    if r['metric_status'] in ('OK','PROVISIONAL') and not docs:source_missing.append((s,m))
    if not r['value']:continue
    try:
        v=lambda f,t=p:val(s,t,f)
        if m in ('M01','M02','M05','M07'):
            f={'M01':'FIN.REV.YTD','M02':'FIN.REV.SQ','M05':'FIN.NPDEDT.YTD','M07':'FIN.NPDEDT.SQ'}[m];expected=v(f)/v(f,b)-1
        elif m=='M03':
            q=quarter(p);f='FIN.REV.SQ';expected=((v(f)/v(f,b)-1)-(v(f,q)/v(f,q-10000)-1))*100
        elif m=='M04':
            if (s,p,'FIN.GROSSMARGIN.PCT') in data and (s,b,'FIN.GROSSMARGIN.PCT') in data:expected=v('FIN.GROSSMARGIN.PCT')-v('FIN.GROSSMARGIN.PCT',b)
            else:expected=((1-v('FIN.COST.YTD')/v('FIN.REV.YTD'))-(1-v('FIN.COST.YTD',b)/v('FIN.REV.YTD',b)))*100
        elif m=='M06':expected=(v('FIN.NPDEDT.YTD')/v('FIN.REV.YTD')-v('FIN.NPDEDT.YTD',b)/v('FIN.REV.YTD',b))*100
        elif m=='M08':expected=v('FIN.OCF.YTD')/v('FIN.NPP.YTD')
        elif m=='M09':expected=v('FIN.OCF.YTD')-v('FIN.OCF.YTD',b)
        elif m in ('M10','M11'):
            inst,flow=('FIN.AR.INSTANT','FIN.REV.YTD') if m=='M10' else ('FIN.INV.INSTANT','FIN.COST.YTD')
            def days(t):
                rec=data[(s,t,flow)];return D((date.fromisoformat(rec['period_end'])-date.fromisoformat(rec['period_start'])).days+1)
            expected=v(inst)/v(flow)*days(p)-v(inst,b)/v(flow,b)*days(b)
        else:expected=(v('FIN.CONTRACTASSET.INSTANT')/v('FIN.REV.YTD')-v('FIN.CONTRACTASSET.INSTANT',b)/v('FIN.REV.YTD',b))*100
        actual=D(r['value']);tol=max(D('0.000001'),abs(expected)*D('0.000000001'))
        arithmetic[m]+=1
        if abs(expected-actual)>tol:errors.append(dict(security_id=s,metric_id=m,expected=str(expected),actual=str(actual)))
    except Exception as e:errors.append(dict(security_id=s,metric_id=m,error=str(e)))
write('after_cutoff_cells.csv',future)
late_secs={r['security_id'] for r in future}
write('after_cutoff_company_guard.csv',[dict(security_id=s,stock_name=next(r['stock_name'] for r in metrics if r['security_id']==s),route='WATCH_AFTER_CUTOFF',allow_clean_signal='NO',reason='Source disclosed after frozen 2026-10-25 cutoff; retain for incremental version') for s in sorted(late_secs)])
summary=read(BASE/'s02_v10/company_metric_summary.csv')
summary_errors=[]
for r in summary:
    counts=Counter(m['metric_status'].lower() for m in metrics if m['security_id']==r['security_id'])
    if any(int(r[k])!=v for k,v in counts.items()):summary_errors.append(r['security_id'])
report=dict(snapshot_hashes={k:sha(ROOT/snap[k]['path'])==snap[k]['sha256'] for k in ('normalized_input','metrics','company_summary','review')},git_blob_sha={str(p.relative_to(ROOT)):blob(p) for p in (BASE/'s02_v10/all_pool_metrics.csv',BASE/'s00_v10/s00_v10.csv.gz')},companies=len({r['security_id'] for r in metrics}),cells=len(metrics),unique_keys=len({(r['security_id'],r['metric_id']) for r in metrics}),counts=dict(Counter(r['metric_status'] for r in metrics)),replay_differences=len(diff),arithmetic_checked=dict(arithmetic),arithmetic_errors=errors[:20],arithmetic_errors_count=len(errors),summary_errors=summary_errors,ok_with_q06=[(r['security_id'],r['metric_id']) for r in metrics if r['metric_status']=='OK' and 'Q06' in r['quality_flags']],source_missing=source_missing,after_cutoff_cells=len(future),after_cutoff_companies=len(late_secs),source_dates_missing_cells=len(unknown),normalized_rows=len(norm),normalized_duplicate_keys=len(norm)-len(data))
(OUT/'audit_results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=True,indent=2))
