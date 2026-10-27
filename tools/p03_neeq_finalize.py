"""Build reproducible P03 technical handoff from cached official evidence only."""
import json,hashlib,csv,sys
from pathlib import Path
from datetime import datetime,timezone
sys.path.insert(0,str(Path(__file__).resolve().parent))
from p03_neeq_inventory import ROOT,OUT,RAW,parse_response,slot_of,is_current_report,params

def save(name,obj):
    (OUT/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding="utf-8")

indexes=json.loads((OUT/'neeq_indexes.json').read_text(encoding='utf-8'))
slots=json.loads((OUT/'slot_lookup.json').read_text(encoding='utf-8'))
bycode={'BJ:'+x['stock_code']:x for x in indexes}
for slot in slots:
    rows=bycode[slot['security_id']]['rows']
    hits=[x for x in rows if is_current_report(x) and slot_of(x['disclosureTitle'])==slot['slot_id']]
    slot.update(candidates=[{**x,'official_pdf_url':'https://www.neeq.com.cn'+x['destFilePath']} for x in hits],candidate_count=len(hits),
        lookup_result='OFFICIAL_FULL_REPORT_LINK_FOUND' if hits else 'NO_FULL_REPORT_IN_COMPLETE_INDEX')
    slot['excluded_cancelled_versions']=[x for x in rows if slot_of(x['disclosureTitle'])==slot['slot_id'] and not is_current_report(x)]
save('slot_lookup.json',slots)

# External primary-source search extracts supplement local PDF evidence. Search
# excerpts are explicitly distinguished from locally downloaded original PDFs.
listing={
 '920011':('2024-09-09','LOCAL_PDF_PAGE_6',None),
 '920055':('2024-09-19','LOCAL_PDF_PAGE_5',None),
 '920124':('2024-11-08','OFFICIAL_SEARCH_EXTRACT','https://www.bse.cn/disclosure/2025/2025-11-05/1762329134_281505.pdf'),
 '920211':('2024-09-25','OFFICIAL_SEARCH_EXTRACT','https://www.bse.cn/disclosure/2026/2026-05-21/1779357371_723533.pdf'),
 '920238':('2025-03-10','OFFICIAL_SEARCH_EXTRACT','https://www.bse.cn/disclosure/2026/2026-07-08/1783503134_547223.pdf'),
 '920289':('2024-06-24','OFFICIAL_SEARCH_EXTRACT','https://www.bse.cn/disclosure/2026/2026-04-14/1776157330_293258.pdf')}
samples=json.loads((OUT/'sample_pdf_checks.json').read_text(encoding='utf-8'))
app=[]
for s in slots:
    if s['candidate_count']:continue
    code=s['security_id'].split(':')[1]
    r={k:s[k] for k in ['security_id','stock_name','old_neeq_code','slot_id']}
    r.update(shared_status='NOT_TRIED',shared_status_changed=False)
    if s['slot_id'].startswith('q1_'):
        r.update(technical_classification='VOLUNTARY_QUARTER_NOT_FOUND_IN_VALIDATED_REGULAR_INDEX',
           rule_url='https://www.neeq.com.cn/class_c0/200025689.html',rule_articles=[11,13],
           next_action='Check issuer-specific special obligation and BSE transition date before adopting a not-required status; failed quarter-only controls are not absence evidence.')
    else:
        date,kind,url=listing[code]
        if url is None:url=next(x['official_pdf_url'] for x in samples if x['security_id']==s['security_id'])
        r.update(technical_classification='PERIOD_PRECEDES_CURRENT_NEEQ_LISTING_REVIEW_REQUIRED',
            current_neeq_listing_date=date,evidence_kind=kind,evidence_url=url,
            next_action='Review filing deadlines, any prior listing interval and IPO documents; pre-listing financial statements may exist inside a prospectus and do not equal a separately disclosed periodic report.')
        if code=='920124':r['multiple_listing_warning']='Earlier listing under 838401 ended before the current 874643 listing. Do not use the earliest lifetime listing date for 2023/2024 applicability.'
    app.append(r)
save('applicability_review.json',app)

checks=[]
def check(label,value):
    checks.append({'check':label,'pass':bool(value)})
    assert value,label
check('15 issuer mappings unique',len(indexes)==15 and len(bycode)==15)
check('all official name/code identities and totals reconciled',all(x['reconciled'] and x['mapping_verdict']=='OFFICIAL_INDEX_NAME_AND_CODE_MATCH' and len(x['rows'])==x['total'] for x in indexes))
check('65 scoped slots partition into 50 candidate and 15 applicability checks',len(slots)==65 and sum(bool(s['candidate_count']) for s in slots)==50 and len(app)==15)
check('no shared collection status promotion',all(s['collection_status_changed'] is False for s in slots))
check('cancelled versions excluded',all(is_current_report(x) for s in slots for x in s['candidates']))
check('cancelled-version regression',not is_current_report({'disclosureTitle':'晨光电机:2024年年度报告','disclosurePostTitle':'已取消'}))
check('corrected full report retained',is_current_report({'disclosureTitle':'晨光电机:2024年年度报告（更正后）','disclosurePostTitle':''}))
check('summary is not full report',slot_of('晨光电机:2024年年度报告摘要') is None)
for bad in ['{}','null([])','null([{"listInfo":null}])']:
    try:parse_response(bad)
    except (ValueError,TypeError,AttributeError):checks.append({'check':'reject malformed response '+bad,'pass':True})
    else:raise AssertionError('bad schema accepted')
cache=RAW/'neeq_874468_p0.txt'
check('cached positive control yields seven rows',parse_response(cache.read_text(encoding='utf-8'))['totalElements']==7)
check('request uses critical array names','disclosureType[]' in params('874468') and 'xxfcbj[]' in params('874468'))
check('five PDF identity samples verified',sum(bool(x.get('name_in_text') and x.get('old_code_in_text')) for x in samples)==5)
for x in samples:
    if 'sha256' in x:check('PDF hash '+x['security_id'],hashlib.sha256((ROOT/x['local_file']).read_bytes()).hexdigest()==x['sha256'])
save('self_check.json',checks)

save('adapter_config.json',{'scope':'15 issuers / 65 slots only','method':'POST','url':'https://www.neeq.com.cn/disclosureInfoController/companyAnnouncement.do',
  'encoding':'application/x-www-form-urlencoded; urllib.parse.urlencode(params,doseq=True)',
  'sample_params':params('874468'),'sample_expected_total':7,'noticeType_is_required':False,
  'throttle_seconds':1.2,'max_pages':10,'timeout_seconds':25,'verify_tls':True,
  'source_failure_threshold':3,'failure_scope':'Distinguish index lookup, PDF transport and issuer applicability.',
  'unvalidated_routes':['quarter subcategory query','keyword quarter query'],
  'version_policy':'Exclude disclosurePostTitle containing 取消 from candidates; preserve original index records.',
  'collection_policy':'Candidate URL is not a collected/identity-verified/archived document.'})

review={'issue':'P03','scope':'NEEQ_RECHECK_20261027','decision':'SELF_CHECK_PASS_WITH_OPEN_ITEM',
 'completed_at':datetime.now(timezone.utc).isoformat(),'official_index_route':'AVAILABLE_POSITIVE_CONTROL_VERIFIED',
 'issuer_mappings':15,'target_slots':65,'slots_with_current_official_links':50,
 'unresolved_applicability':15,'pre_current_listing_periods':11,'quarterly_slots':4,
 'sample_pdf_identity_verified':5,'sample_pdf_download_errors':10,'shared_ledger_modified':False,
 'a02_ready':False,'next_action':'A01 automatic recovery using validated old codes and parameter encoding; applicability checks and file transport diagnostics first. Do not dispatch 65 manual requests.',
 'limits':['50 is candidate-link coverage, not 50 downloaded PDFs.','5 PDF samples are issuer identity checks, not 5 newly recovered target slots.',
 '11 pre-listing periods are review candidates, not final NA decisions.','Quarter-specific positive controls failed; their zeros cannot prove absence.',
 'No Drive upload, financial adoption or independent acceptance in this follow-up.']}
save('review.json',review)

handoff='''# P03 股转接口技术复核（2026-10-27）

结论：`SELF_CHECK_PASS_WITH_OPEN_ITEM`。股转公告查询可用，“65 槽因平台整体故障无法取得”的判断不成立。A02 仍不接收这 65 槽人工补件清单。

## 四问的答复

1. **接口参数**：官网仍使用 `companyAnnouncement.do`。按 `adapter_config.json` 发送表单，数组名 `disclosureType[]`、`xxfcbj[]` 必须保留方括号，分类使用 `9503`。晨光旧代码 874468 正向对照返回 7 条；单独把前两者任一个改成无括号字段均为 0。`noticeType[]` 可省略（省略后仍为 7），此前将其视为必填的猜测已撤回。未要求账号令牌；官方公开 C3VK 页面会话与 Referer 随探针使用，不声称所有请求条件均已单独证明必要。初始化接口忽略筛选，不能替代按公司检索。

2. **旧码映射**：15/15 已用官方返回的公司简称与旧码交叉匹配，见 `historical_code_mapping.json`。奥美森为 873044、南特为 874643，不能把 orgId 中的历史数字当作当前挂牌代码。完整列表及分页总数对账见 `neeq_indexes.json`。

3. **65 槽实际情况**：50 槽定位到未取消的官方全文链接（`slot_lookup.json`）；另 11 槽报告期早于本轮股转挂牌时间，4 槽为 2026 一季报。现行规则第 11、13 条要求年报/中报、允许季报；还需核实特殊义务和北交所上市切换时点。11 槽也需结合披露期限及历史挂牌区间审核，不直接改 NA。详见 `applicability_review.json`。季度子分类/关键词探针未通过已知有数据的正向对照，其 0 值不可作缺失证据。

4. **熔断**：公告索引已有正向证据，不登记全局源故障。PDF 传输另行记录：15 个主体样本中 5 个已下载且前 12 页命中简称与旧码，10 个在两个官方域名出现 302 跳转循环。该轮探针没有及时在第三次连续文件失败后停下，是本轮验证的执行缺陷；脚本现已加入三次连续失败熔断，未重跑失败队列。原失败记录保留，不包装成熔断已实测通过。

## 接手执行

- 先按最新在线控制文件领取 A01 的自动恢复工作；沿用 P07 配置、共享 checkpoint 和登记表，不另开台账。50 个链接先查幂等/本地/登记表，再下载，逐份身份和报告期确认成功后才能写采集完成。
- PDF 原件继续经 `sources/collection` 联接落 D 盘；本目录只放技术证据、索引、配置和自检，不上传整份报告、页面会话 cookie 或正文缓存到 GitHub。
- 取消版本只留版本历史；使用更正后的全文。50 槽链接不是下载数；5 份主体抽样也不是 5 个新补齐目标槽。
- 11 个挂牌前时期保留为待规则采信；南特存在早期挂牌/摘牌，不能一律用最早挂牌日。4 个一季报待特定义务核实；可选披露不等于文件必不存在。
- A02 继续等待自动恢复及适用性复核；不能把剩余项直接发人工。既有 7173 已采集与 140 既有 NA 不受本补充影响，本轮共享 65 NOT_TRIED 未改。

## 证据与限制

`serialization_isolation.json` 为单字段对照；`quarter_and_parameter_controls.json` 与 `serialization_and_quarter_fallback.json` 留存失败季度探针；`sample_pdf_checks.json` 含 5 份 PDF 哈希、物理页码和挂牌时间摘录、10 条失败；`self_check.json` 是本地自检，不是独立验收。

现行规则：https://www.neeq.com.cn/class_c0/200025689.html 。外部官方检索摘录已标 `OFFICIAL_SEARCH_EXTRACT`，对应 PDF 未成功下载，不能冒充本地原件已读。源码、配置与缓存复算脚本在 tools/p03_neeq_*；缓存复算运行 `p03_neeq_finalize.py`，不发网络请求。
'''
(OUT/'handoff.md').write_text(handoff,encoding='utf-8')
manifest=[]
for f in sorted(OUT.iterdir()):
    if f.is_file() and f.name!='manifest.json':manifest.append({'path':f.relative_to(ROOT).as_posix(),'bytes':f.stat().st_size,'sha256':hashlib.sha256(f.read_bytes()).hexdigest()})
save('manifest.json',manifest)
print(json.dumps({'review':review,'checks_passed':len(checks)},ensure_ascii=False))
