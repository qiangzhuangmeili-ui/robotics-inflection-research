"""Independent source expectations, fail-closed parser fixtures, and artifact integrity."""
import csv,hashlib,json,sys,subprocess
from pathlib import Path
from collections import Counter
ROOT=Path(__file__).resolve().parents[4];OUT=Path(__file__).parent
sys.path.insert(0,str(ROOT/'tools'))
import a03_financial_field_extractor as A
import s02_calculate as S
import l0_classify as L
def read(p):return list(csv.DictReader(p.open(encoding='utf-8-sig',newline='')))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
checks=[]
def check(name,actual,expected):
    ok=actual==expected;checks.append(dict(check=name,result='PASS' if ok else 'FAIL',actual=actual,expected=expected));print('PASS' if ok else 'FAIL',name,flush=True)
def field(text,statement,fid,label,merge=True):
    return A.extract_statement_field([text],{statement:(0,0,'元')},statement,fid,[label],merge)
def fixtures():
    check('integer current amount retained',A.statement_amounts('应收票据 七、4 817 2,643',True)[0][1],817.0)
    check('small numbered note removed once',A.statement_amounts('附注 3 817 2,643',True)[0][1],817.0)
    check('spaced accounting negative',A.statement_amounts('营业收入 ( 1,000.00 ) (-900.00)')[0][1],-1000.0)
    check('double minus rejected by canonical sign',A.statement_amounts('营业收入 (-1,000.00) (900.00)')[0][1],-1000.0)
    check('blank NP does not borrow NPP',field('净利润\n归属于母公司股东的净利润 1,234.56 900.00','IS_CONS','FIN.NP.YTD','净利润')[0],None)
    check('dash current does not take prior amount',field('营业收入 注3 — 900.00','IS_CONS','FIN.REV.YTD','营业收入')[0],None)
    check('vertical balance row',field('应收账款\n1,000.00\n900.00\n存货 200.00 300.00','BS_CONS','FIN.AR.INSTANT','应收账款',False)[0],'1,000.00')
    check('vertical blank does not borrow inventory',field('合同资产\n存货 200.00 300.00','BS_CONS','FIN.CONTRACTASSET.INSTANT','合同资产',False)[0],None)
    check('loss explanation is not a blank column',field('净利润（净亏损以“-”号填列） 1,234.56 900.00','IS_CONS','FIN.NP.YTD','净利润')[0],'1,234.56')
    check('split numbering title',A.is_title('、合并资产负债表'),'BS_CONS')
    check('combined title',A.is_title('2026年半年度合并及公司利润表'),'IS_CONS')
    check('generic standalone remains outside scope',A.is_title('资产负债表'),None)
    check('NA retains column',A.summary_cells('6,430,820.01 不适用 59,617,005.56 57.41')[2][1],59617005.56)
    check('huge growth remains percent',A.summary_cells('787,643,773.92 2,803.44% 4,635,869,494.31 592.14%')[1][2],True)
    check('bare CNY header',A.detect_unit(['2026年6月30日 人民币元']),'元')
    # 摘要表前页的元不能被后页下一子表的万元覆盖。
    pages=['主要会计数据\n单位：元 币种：人民币', '营业收入 1,000.00 900.00 11.11\n归属于上市公司股东的净利润 100.00 90.00 11.11\n归属于上市公司股东的扣除非经常性损益的净利润 注3\n80.00 70.00 14.28\n经营活动产生的现金流量净额 120.00 110.00 9.09\n本期比上期增减\n单位：万元 币种：人民币']
    k,_,_,details=A.extract_key_financials(pages,anchor_rev='1,000.00',with_details=True)
    check('cross-page amount not annotated',k.get('FIN.NPDEDT.YTD'),'80.00')
    check('cross-page unit bound before row',details.get('FIN.NPDEDT.YTD',{}).get('unit'),'元')
    check('source physical page exact',details.get('FIN.NPDEDT.YTD',{}).get('page'),2)
    combined=['合并及公司资产负债表\n项目 母公司 母公司 合并 合并\n货币资金 100 200 300 400\n资产总计 100 200 300 400','合并及公司利润表\n项目 母公司 母公司 合并 合并\n营业收入 100 200 300 400\n营业成本 90 100 200 300\n净利润 10 100 100 100']
    check('combined parent-first fails closed',A.build_statement_map(combined,start_page=0),{})
def full():
    plan=json.loads((OUT/'reextract_plan.json').read_text(encoding='utf-8'))
    check('single final parser fingerprint',plan['parser_sha256'],sha(ROOT/'tools/a03_financial_field_extractor.py'))
    expected=read(OUT/'units/normalized_corrections.csv')
    reg=json.loads((OUT/'units/regression/expected.json').read_text(encoding='utf-8'))['rows']
    expected += [dict(document_id=r['document_id'],new_value_cny=r['value_cny'],new_unit_raw=r['unit'],source_page_physical=r['value_page']) for r in reg]
    source_checks=[];normalized=read(OUT/'s00/financial_normalized.csv')
    normalized_npd={r['document_id']:float(r['value_cny']) for r in normalized if r['field_id']=='FIN.NPDEDT.YTD' and r['value_cny']}
    for e in expected:
        ex=json.loads((OUT/'extracted'/f"{e['document_id']}.json").read_text(encoding='utf-8'))
        row=next(r for r in ex['fields'] if r['field_id']=='FIN.NPDEDT.YTD')
        ok=abs(float(row['value_cny'])-float(e['new_value_cny']))<.1 and row['unit_raw']==e['new_unit_raw'] and int(row['page'])==int(e['source_page_physical']) and abs(normalized_npd.get(e['document_id'],float('inf'))-float(e['new_value_cny']))<.1
        source_checks.append(ok)
    check('19 independently read source expectations',sum(source_checks),len(expected))
    fingerprints=[];arithmetic=[];errors=[]
    for t in plan['tasks']:
        ex=json.loads((OUT/'extracted'/f"{t['document_id']}.json").read_text(encoding='utf-8'))
        fingerprints.append(ex.get('ledger_sha256')==t['ledger_sha256'])
        if ex.get('parse_error'):errors.append(dict(document_id=t['document_id'],error=ex['parse_error']))
        for r in ex['fields']:
            if r['value_cny']=='' or r['unit_scale']=='':continue
            v=float(r['value_raw'].replace(',',''))*float(r['unit_scale'])
            if 'EXPENSE_PARENTHESIS_TO_POSITIVE_P04' in r['note']:v=abs(v)
            if abs(v-float(r['value_cny']))>1:arithmetic.append((t['document_id'],r['field_id']))
    check('all source binary hashes checked before extraction',sum(fingerprints),len(plan['tasks']))
    check('raw-value times unit arithmetic violations',len(arithmetic),0)
    check('unhandled parser/worker errors',len([r for r in errors if r['error'] not in ('IMAGE_ONLY_NO_TEXT_LAYER',)]),0)
    check('formula implementation unchanged',sha(ROOT/'tools/s01_rules_check.py'),'134d0feeb2aff67f1a6ab9df0a08a8d96c6a64a294df17382e06e5cd4964470f')
    for rel in ['runs/issues/S01/screen_rules_v2.json','runs/issues/S00/financial_normalized.csv.gz','runs/issues/S02/all_pool_metrics.csv','data/active_issue.json','PROJECT_STATE.json']:
        original=subprocess.check_output(['git','show','HEAD:'+rel],cwd=ROOT)
        actual=(ROOT/rel).read_bytes()
        # 旧提交仍有 LF/CRLF 差别；仅允许纯换行差异，不能把它当内容修改。
        same=actual==original or actual.replace(b'\r\n',b'\n')==original.replace(b'\r\n',b'\n')
        check('frozen file content unchanged '+rel,same,True)
        if rel.endswith('screen_rules_v2.json'):
            accepted='ada501e8bcd276ce670a4799c730a81cdf2f9dc70c244f9255485b00168c6a85'
            canonical_crlf=actual.replace(b'\r\n',b'\n').replace(b'\n',b'\r\n')
            equivalent=sha(ROOT/rel)==accepted or (sha(ROOT/rel)=='d9a6b3cc77fcd3afb498673668be2d5c86412b6b83ffe0193e6c78f4979ecabf' and hashlib.sha256(canonical_crlf).hexdigest()==accepted)
            check('accepted rules exact bytes or verified line-ending equivalent',equivalent,True)
    S.s01.NORMALIZED=OUT/'s00/financial_normalized.csv'
    rows,meta,_,_=S.s01.load_rows();latest=S.latest_periods(rows)
    new=read(OUT/'s02/all_pool_metrics.csv')
    check('metric primary keys',len({(r['security_id'],r['metric_id']) for r in new}),12648)
    check('no post-cutoff normalized disclosures',sum(r['published_on']>'2026-10-25' for r in read(OUT/'s00/financial_normalized.csv') if r['published_on']),0)
    baseline={r['security_id']:r for r in json.loads((OUT/'coverage_baseline.json').read_text(encoding='utf-8'))}
    coverage=[]
    fields=['FIN.REV.YTD','FIN.REV.SQ','FIN.NPDEDT.YTD','FIN.NPDEDT.SQ','FIN.COST.YTD','FIN.OCF.YTD','FIN.NPP.YTD','FIN.AR.INSTANT','FIN.INV.INSTANT','FIN.ASSET.INSTANT','FIN.CONTRACTASSET.INSTANT','FIN.GROSSMARGIN.PCT']
    for sec,b in baseline.items():
        pk=latest[sec];rr=rows.get((sec,pk),{});good=sum(f in rr and rr[f]['value'] is not None and rr[f]['status'] in S.s01.USABLE|S.s01.USABLE_FLAG for f in fields)
        hold=sum(f in rr and rr[f]['status'] in S.s01.HOLD for f in fields)
        sl={'0331':'q1','0630':'h1','0930':'q3','1231':'annual'}[str(pk)[4:]]+'_'+str(pk)[:4]
        task=next((t for t in plan['tasks'] if t['security_id']==sec and t['slot_id']==sl),{})
        doc=task.get('document_id',b['document_id']);p=OUT/'extracted'/f'{doc}.json';ex=json.loads(p.read_text(encoding='utf-8')) if p.exists() else {}
        if good>=8:resolution='RECOVERED_AT_LEAST_8_USABLE_FIELDS'
        elif good+hold>=8:resolution='HOLD_RECONCILIATION_REQUIRED'
        elif not b['document_id']:resolution='NO_CURRENT_PDF_LEGACY_ONLY'
        elif ex.get('parse_error'):resolution='PDF_TEXT_OR_OCR_REQUIRED'
        elif not ex.get('regions'):resolution='STATEMENT_LOCATION_OR_SCOPE_HOLD'
        else:resolution='PARTIAL_FIELDS_REMAIN_UNKNOWN'
        coverage.append(dict(security_id=sec,stock_name=b['stock_name'],period_key=pk,baseline_usable=b['fields_usable'],new_usable=good,new_hold=hold,resolution=resolution,document_id=doc,regions=json.dumps(ex.get('regions',{}),ensure_ascii=False),parse_error=ex.get('parse_error','')))
    with (OUT/'coverage_resolution.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(coverage[0]),lineterminator='\n');w.writeheader();w.writerows(coverage)
    check('53-company repair queue accounted for',len(coverage),53)
    enum=L.exhaustive_check()
    check('L0 legal status vectors',enum['legal_count_vectors'],125970)
    (OUT/'coverage_summary.json').write_text(json.dumps(dict(disposition_counts=dict(Counter(r['resolution'] for r in coverage)),remaining_below_8=sum(r['new_usable']<8 for r in coverage),initial_only_2=25,new_only_2=sum(r['new_usable']==2 for r in coverage),text_errors=errors),ensure_ascii=False,indent=2),encoding='utf-8')
if __name__=='__main__':
    fixtures()
    if '--fixtures-only' not in sys.argv:full()
    result=dict(review_nature='SELF_CHECK_WITH_SOURCE_EXPECTATIONS_AND_NEGATIVE_FIXTURES',checks=checks,pass_count=sum(r['result']=='PASS' for r in checks),fail_count=sum(r['result']=='FAIL' for r in checks),release_S03=False)
    (OUT/('fixture_check.json' if '--fixtures-only' in sys.argv else 'verification.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    sys.exit(bool(result['fail_count']))
