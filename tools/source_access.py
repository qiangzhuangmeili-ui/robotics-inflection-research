"""Small P03 transport adapter for P05 reuse, not a batch collector.

Exchange is supplied explicitly as SH/SZ/BJ. This never guesses exchange by prefix.
Circuit state is per provider route, not per issuer. Empty data is never zero revenue.
"""
import json
import time
from dataclasses import dataclass, asdict
from pathlib import Path
import requests

ROOT=Path(__file__).resolve().parents[1]
POLICY=ROOT/'runs/issues/P03/source_circuit_policy.json'

class CircuitOpen(RuntimeError):pass
class SourceFailure(RuntimeError):pass
class DocumentUnavailable(RuntimeError):pass

@dataclass
class Circuit:
    failures:int=0
    opened_at:float|None=None
    last_error:str|None=None
    def allow(self,now,cooldown,known_good_probe=False):
        if self.opened_at is None:return True
        return known_good_probe and now-self.opened_at>=cooldown
    def success(self):self.failures=0;self.opened_at=None;self.last_error=None
    def failure(self,code,now,threshold):
        self.failures+=1;self.last_error=code
        if self.failures>=threshold:self.opened_at=now

class SourceAccess:
    def __init__(self,state_path=None,transport=None,sleeper=time.sleep,clock=time.time):
        self.policy=json.loads(POLICY.read_text(encoding='utf-8'))
        self.state_path=Path(state_path) if state_path else ROOT/'runs/issues/P03/source_circuit_state.json'
        self.session=requests.Session();self.session.headers.update({'User-Agent':'Mozilla/5.0','Referer':'https://www.cninfo.com.cn/'})
        self.transport=transport or self.session.request;self.sleeper=sleeper;self.clock=clock
        self.states={k:Circuit(**v) for k,v in json.loads(self.state_path.read_text(encoding='utf-8')).items()} if self.state_path.exists() else {}
    def save(self):
        self.state_path.parent.mkdir(parents=True,exist_ok=True)
        self.state_path.write_text(json.dumps({k:asdict(v) for k,v in self.states.items()},indent=2)+'\n',encoding='utf-8')
    def quarantine(self,route,reason):
        state=self.states.setdefault(route,Circuit());state.failure(reason,self.clock(),1);self.save()
        raise SourceFailure(reason)
    def request(self,route,method,url,*,kind='json',known_good_probe=False,**kwargs):
        state=self.states.setdefault(route,Circuit());p=self.policy
        if not state.allow(self.clock(),p['cooldown_seconds'],known_good_probe):raise CircuitOpen(route)
        for attempt in range(p['max_attempts_per_call']):
            try:
                response=self.transport(method,url,timeout=(p['connect_timeout_seconds'],p['pdf_read_timeout_seconds'] if kind=='pdf' else p['read_timeout_seconds']),**kwargs)
                if response.status_code==404:raise DocumentUnavailable('HTTP_404_DOCUMENT_ONLY')
                if response.status_code in (401,403,429):
                    state.failure('HTTP_'+str(response.status_code),self.clock(),1);self.save();raise SourceFailure(state.last_error)
                if response.status_code!=200:raise SourceFailure('HTTP_'+str(response.status_code))
                if kind=='pdf':
                    if not response.content.startswith(b'%PDF-'):raise SourceFailure('NON_PDF_RESPONSE')
                    result=response.content
                else:
                    try:result=response.json()
                    except ValueError:raise SourceFailure('INVALID_JSON') from None
                    if not isinstance(result,(dict,list)):raise SourceFailure('INVALID_SCHEMA')
                state.success();self.save();return result
            except DocumentUnavailable:raise
            except (requests.RequestException,SourceFailure) as exc:
                if state.opened_at is not None:raise
                code=type(exc).__name__ if isinstance(exc,requests.RequestException) else str(exc)
                threshold=p['transport_failure_threshold'] if isinstance(exc,requests.RequestException) else p['source_failure_threshold']
                state.failure(code,self.clock(),threshold);self.save()
                if state.opened_at is not None or attempt+1>=p['max_attempts_per_call']:raise SourceFailure(code) from None
                self.sleeper(p['retry_delay_seconds'])
        raise SourceFailure('EXHAUSTED')
    @staticmethod
    def validate_security(security_id):
        exchange,code=security_id.split(':',1)
        if exchange not in ('SH','SZ','BJ') or len(code)!=6 or not code.isdigit():raise ValueError('Explicit SH/SZ/BJ:6-digit-code required')
        return exchange,code
    def finance_probe(self,security_id):
        exchange,code=self.validate_security(security_id)
        value=self.request('sina_finance','GET','https://quotes.sina.cn/cn/api/openapi.php/CompanyFinanceService.getFinanceReport2022',params={'paperCode':exchange.lower()+code,'source':'lrb','type':'0','page':'1','num':'1'})
        result=value.get('result',{});data=result.get('data') or {};periods=list((data.get('report_list') or {}).keys())
        if (result.get('status') or {}).get('code')!=0 or not periods:self.quarantine('sina_finance','PROVIDER_SCHEMA_OR_EMPTY_REQUIRES_KNOWN_GOOD_CHECK')
        return {'security_id':security_id,'source':'SINA_NON_OFFICIAL_FINANCIAL_DATA','periods':periods,'data':data,'research_accepted':False}
    def annual_index_probe(self,security_id,org_id):
        exchange,code=self.validate_security(security_id)
        column={'SH':'sse','SZ':'szse','BJ':'szse'}[exchange]
        value=self.request('cninfo_annual_index','POST','https://www.cninfo.com.cn/new/hisAnnouncement/query',data={'pageNum':'1','pageSize':'3','column':column,'tabName':'fulltext','stock':code+','+org_id,'searchkey':'','category':'category_ndbg_szsh','seDate':'2026-01-01~2026-10-25','isHLtitle':'true'})
        rows=value.get('announcements')
        if not isinstance(rows,list) or not rows:self.quarantine('cninfo_annual_index','EMPTY_INDEX_REQUIRES_KNOWN_GOOD_CHECK_NOT_MISSING_REPORT')
        if any(str(r.get('secCode'))!=code for r in rows):self.quarantine('cninfo_annual_index','ISSUER_MISMATCH')
        return {'security_id':security_id,'column':column,'total':value.get('totalAnnouncement'),'rows':rows,'research_accepted':False}

if __name__=='__main__':
    import sys
    access=SourceAccess()
    action,security=sys.argv[1:3]
    if action=='finance':r=access.finance_probe(security);print(json.dumps({k:v for k,v in r.items() if k!='data'},ensure_ascii=False))
    elif action=='annual-index':
        r=access.annual_index_probe(security,sys.argv[3]);print(json.dumps({k:v for k,v in r.items() if k!='rows'},ensure_ascii=False))
    else:raise ValueError('finance or annual-index')
