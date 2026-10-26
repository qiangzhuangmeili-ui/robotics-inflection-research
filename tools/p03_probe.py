"""Bounded public source probes; no credentials or full-universe collection."""
import csv, hashlib, json, sys, time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
import requests

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'runs/issues/P03'
OUT.mkdir(parents=True,exist_ok=True)
SESSION=requests.Session()
SESSION.headers.update({'User-Agent':'Mozilla/5.0','Referer':'https://www.cninfo.com.cn/'})

def probe(key,url,params=None,method='GET',data=None):
    start=time.monotonic();r={'probe_id':key,'url':url,'method':method,'checked_at':datetime.now(timezone.utc).isoformat()}
    if params:r['parameters']=params
    if data:r['form_parameters']=data
    try:
        resp=SESSION.request(method,url,params=params,data=data,timeout=(8,20))
        r.update(http_status=resp.status_code,elapsed_seconds=round(time.monotonic()-start,3),content_type=resp.headers.get('Content-Type',''),size_bytes=len(resp.content),final_host=urlparse(resp.url).hostname)
        if resp.status_code!=200:r['status']='HTTP_FAILURE'
        elif resp.content.startswith(b'%PDF-'):
            r.update(status='PDF_BINARY_OBTAINED',sha256=hashlib.sha256(resp.content).hexdigest())
            cache=ROOT/'sources/p03_probes';cache.mkdir(parents=True,exist_ok=True)
            (cache/(key+'.pdf')).write_bytes(resp.content)
        else:
            try:
                value=resp.json();r['status']='JSON_OBTAINED'
                if isinstance(value,dict):
                    r['top_level_keys']=list(value)[:20]
                    if 'stockList' in value:
                        r['stock_count']=len(value['stockList']);r['sample_org_ids']={x['code']:x['orgId'] for x in value['stockList'] if x.get('code') in ['688218','002031','920207']}
                    if 'announcements' in value:
                        r['total_announcements']=value.get('totalAnnouncement');r['sample_announcements']=[{k:x.get(k) for k in ['secCode','secName','announcementTitle','adjunctUrl','announcementTime']} for x in (value.get('announcements') or [])[:2]]
                    result=value.get('result',{})
                    if isinstance(result,dict):
                        d=result.get('data');r['provider_status']=result.get('status')
                        if isinstance(d,dict):r['report_date_count']=len(d.get('report_date') or []);r['report_periods']=list((d.get('report_list') or {}).keys())[:6]
                r['response_sha256']=hashlib.sha256(resp.content).hexdigest()
            except ValueError:r['status']='HTML_OR_NON_JSON'
    except requests.RequestException as exc:r.update(status='TRANSPORT_FAILURE',error_class=type(exc).__name__,elapsed_seconds=round(time.monotonic()-start,3))
    p=OUT/'probe_records.json';records=json.loads(p.read_text(encoding='utf-8')) if p.exists() else []
    records.append(r);p.write_text(json.dumps(records,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(r,ensure_ascii=False),flush=True)
    return r

if __name__=='__main__':
    mode=sys.argv[1]
    if mode=='local':probe('toolbox_before_recovery','http://127.0.0.1:8774/toolbox')
    elif mode=='indexes':
        for exchange,code,org in [('SH','688218','gfbj0836084'),('SZ','002031','gssz0002031'),('BJ','920207','gfbj0835207')]:
            probe('cninfo_replay_'+exchange,'https://www.cninfo.com.cn/new/hisAnnouncement/query',method='POST',data={'pageNum':'1','pageSize':'3','column':'sse' if exchange=='SH' else 'szse','tabName':'fulltext','stock':code+','+org,'searchkey':'','category':'category_ndbg_szsh','seDate':'2026-01-01~2026-10-25','isHLtitle':'true'})
    elif mode=='workbench':
        probe('toolbox_replay_page','http://127.0.0.1:8774/toolbox')
        probe('toolbox_replay_catalog','http://127.0.0.1:8774/api/toolbox/catalog')
        for exchange,code in [('SH','688218'),('SZ','002031'),('BJ','920207')]:
            probe('toolbox_replay_finance_'+exchange,'http://127.0.0.1:8774/api/finance/report',params={'symbol':code,'kind':'profit','period':'20260630'})
    elif mode=='public':
        probe('cninfo_legacy_http_dictionary','http://www.cninfo.com.cn/new/data/szse_stock.json')
        probe('cninfo_https_dictionary','https://www.cninfo.com.cn/new/data/szse_stock.json')
        for exchange,code in [('SH','688218'),('SZ','002031'),('BJ','920207')]:
            probe('sina_'+exchange,'https://quotes.sina.cn/cn/api/openapi.php/CompanyFinanceService.getFinanceReport2022',params={'paperCode':exchange.lower()+code,'source':'lrb','type':'0','page':'1','num':'1'})
        with (ROOT/'data/document_registry.csv').open(encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
        for exchange,code in [('SH','688218'),('SZ','002031'),('BJ','920207')]:
            row=next(x for x in rows if x['stock_code']==code and x['period_covered']=='2025年度')
            probe('official_pdf_'+exchange,row['primary_url'])
