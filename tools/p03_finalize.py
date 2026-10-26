"""Build P03 technical acceptance from actual probe and smoke outputs."""
import hashlib,json
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'runs/issues/P03'
def get(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
records=get(OUT/'probe_records.json');by_id={r['probe_id']:r for r in records};smoke=get(OUT/'adapter_smoke.json')
assert len(smoke)==3 and all(r['status']=='PASS' for r in smoke)
registry=__import__('csv').DictReader((ROOT/'data/document_registry.csv').open(encoding='utf-8-sig',newline=''))
hashes={r['stock_code']:r['sha256'] for r in registry if r['stock_code'] in ['688218','002031','920207'] and r['period_covered']=='2025年度'}
pdfs=[]
for ex,code in [('SH','688218'),('SZ','002031'),('BJ','920207')]:
    p=by_id['official_pdf_'+ex];assert p['status']=='PDF_BINARY_OBTAINED' and p['sha256']==hashes[code]
    pdfs.append({'exchange':ex,'stock_code':code,'status':p['status'],'sha256':p['sha256'],'matches_registered_binary':True})
tests=(OUT/'circuit_tests.txt').read_text(encoding='utf-8-sig');assert '\nOK' in tests and 'Ran 6 tests' in tests
now=datetime.now(timezone.utc).isoformat()
health={'plan_version':'20261026_collection_first_v2','issue_key':'P03','checked_at':now,'status':'MINIMAL_PROBES_PASS_NOT_FULL_COVERAGE',
 'local_workbench':{'page_http_status':by_id['toolbox_session_recovery']['http_status'],'catalog_http_status':by_id['toolbox_session_catalog']['http_status'],'SH_finance_http_status':by_id['toolbox_SH_finance']['http_status'],'SZ_finance_http_status':by_id['toolbox_SZ_finance']['http_status'],'BJ_finance_http_status':by_id['toolbox_BJ_actual_validation']['http_status'],'BJ_route':'EXPLICIT_SOURCE_ADAPTER_REQUIRED','lifecycle':'CURRENT_EXECUTION_SESSION_NOT_GUARANTEED_AUTOSTART'},
 'direct_adapter_samples':smoke,'official_pdf_samples':pdfs,
 'failures_preserved':[{'probe_id':r['probe_id'],'status':r['status'],'http_status':r.get('http_status'),'error_class':r.get('error_class')} for r in records if r['status'] in ('TRANSPORT_FAILURE','HTTP_FAILURE') or r.get('total_announcements')==0],
 'drive_readback':{'checked_in':'P02','registered_pdfs_readable':90,'hash_baseline_matches':87,'new_hashes':3,'scope':'CODEX_CONNECTOR_ONLY_NOT_WORKBUDDY'},
 'circuit_tests':{'count':6,'result':'PASS','global_incident_not_company_manual_request':True},
 'collection_gate':{'full_universe_allowed':False,'reason':'P04,P05,P06,P07 not yet accepted','manual_requests_created':0,'company_collection_started':False},
 'limitations':['3 known samples, one financial report period only','Sina is non-official; no field/unit/business acceptance','Old workbench remains SH/SZ-only; BJ uses adapter','SSE/SZSE exchange-site fallback not directly probed; CNINFO official dissemination URLs were probed','No account, proxy, sharing or existing AKShare source modifications']}
put(OUT/'source_health.json',health)
review={'template_only':False,'plan_version':'20261026_collection_first_v2','issue_number':14,'issue_key':'P03','executor':'Codex','reviewer':'Codex','review_method':'SELF_CHECK_LIVE_SAMPLE_PROBES_AND_FAULT_TESTS','reviewed_at':now,'decision':'SELF_CHECK_PASS',
 'dependency_review':{'key':'P00','review_file':'runs/issues/P00/review.json','decision':get(ROOT/'runs/issues/P00/review.json')['decision']},
 'checks':[{'criterion':'沪深北探针与失败路径实测，北交所独立路由','result':'PASS','evidence':['source_health.json','probe_records.json','adapter_smoke.json']},{'criterion':'全局故障只生成源事故，不生成1054条人工补件','result':'PASS','evidence':['source_circuit_policy.json','circuit_tests.txt','tools/test_source_access.py']}],
 'coverage':{'known_companies':3,'financial_report_periods_per_company':1,'official_pdf_files':3,'full_universe_processed':0},
 'allows_next_stage':True,'allows_next_stage_scope':'Only P03 technical dependency for P05/P07; all their other dependencies must separately pass. No full-universe or business adoption release.',
 'next_recommended_issue':{'number':15,'key':'P04'},'limitations':health['limitations']+['SELF_CHECK, not independent business audit']}
put(OUT/'review.json',review)
paths=[p for p in OUT.iterdir() if p.is_file() and p.name not in ('manifest.json','toolbox_pid.txt','toolbox_stdout.log','toolbox_stderr.log')]+[ROOT/'tools'/name for name in ['source_access.py','test_source_access.py','p03_probe.py','p03_adapter_smoke.py','p03_local_service.py','p03_finalize.py']]
put(OUT/'manifest.json',{'issue_key':'P03','plan_version':'20261026_collection_first_v2','generated_at':now,'executor':'Codex','files':[{'path':p.relative_to(ROOT).as_posix(),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in paths]})
print(json.dumps({'decision':'SELF_CHECK_PASS','sample_companies':3,'fault_tests':6,'whole_universe_allowed':False},ensure_ascii=False))
