"""Prepare the reviewable technical handoff; do not mutate remote/local controllers."""
from pathlib import Path
import csv,hashlib,json,re,subprocess,zipfile
from datetime import datetime,timezone,timedelta
ROOT=Path(__file__).resolve().parents[4];OUT=Path(__file__).parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf-8')
def main():
 log=(OUT/'reasonix/output_round2.log').read_text(encoding='utf-8-sig')
 objs=re.findall(r'```json\s*(\{.*?\})\s*```',log,re.S);decision=json.loads(objs[-1])
 assert decision['verdict']=='PASS_TECHNICAL_WITH_LIMITS' and decision['remaining_blockers']==[]
 dump(OUT/'reasonix/decision_round2.json',dict(recorded_by='Codex; exact final JSON extracted from Reasonix stdout',source_log_sha256=sha(OUT/'reasonix/output_round2.log'),decision=decision))
 start=log.index('## 复审结论');end=log.find('\n  · ',start)
 (OUT/'reasonix/review_round2.md').write_text('# Reasonix 独立会话技术审阅：复审\n\n记录者：Codex，从stdout原样提取；Reasonix因6轮工具上限未自行写review.md。\n\n'+log[start:end if end>=0 else None],encoding='utf-8')
 canonical=ROOT/'runs/issues/S02/remediation_20261029/s02'
 for mode in ['recalc_copy','recalc_gzip']:
  p=OUT/'reasonix/round2'/mode
  for name in ['all_pool_metrics.csv','company_metric_summary.csv']:assert sha(p/name)==sha(canonical/name)
 repro=json.loads((OUT/'reproduction_manifest.json').read_text(encoding='utf-8'))
 for p,h in repro['source_sha256'].items():assert sha(ROOT/p)==h
 integration=json.loads((OUT/'integration/test_results.json').read_text(encoding='utf-8'))
 gates=json.loads((OUT/'gates/gate_tests.json').read_text(encoding='utf-8'))
 source=json.loads((OUT/'source_policy_summary.json').read_text(encoding='utf-8'))
 assert integration['test_count']==11 and all(t['status']=='PASS' for t in integration['tests'].values())
 assert gates['passed']==17 and gates['failed']==0 and source['policy_blocking_fail']==0
 review=dict(issue_key='S02',issue_number=37,plan_version='20261026_collection_first_v2',reviewed_at=datetime.now(timezone(timedelta(hours=8))).isoformat(),review_nature='AUTHOR_RECHECK_PLUS_INDEPENDENT_SESSION_AI_TECHNICAL_REVIEW',author_rechecker='Codex (repair author; not an independent financial-source auditor)',independent_reviewer='Reasonix independent session, existing default configuration; underlying model not inspected',decision='TECHNICAL_ACCEPTANCE_RECOMMENDED_WITH_LIMITS',source_commit=repro['source_commit'],data_version='S00_TARGETED_REEXTRACTION_20261029',metric_formula_version='S01_SCREEN_RULES_V2',formulas_changed=False,thresholds_changed=False,canonical_data_changed=False,metric_cells=12648,canonical_csv_byte_reproduction=True,source_pdf_hashes='360/360',source_page_amount_and_unit_presence='19/19; lexical/page-position checks, not full independent financial extraction',policy_checks='28/28',synthetic_tests='23/23',integration_tests='11/11',guard_tests='17/17',gate_contract_checks='15/15',independent_session_verdict=decision,remaining_coverage_companies=21,protected21_l0=dict(EVALUABLE=10,W5_PROVISIONAL_ONLY=8,W9_MIXED_NON_EVALUABLE=3),release_S03_applied=False,remote_controller_updated=False,proposed_next_scope='S03 first integrates and verifies load_gate_inputs/protect_existing_route; only after that may it run frozen L1 technical triage. No business/final-candidate adoption.',s03_actual_consumer_verified=False,independent_financial_source_audit=False,limits=['21家开放覆盖队列不能仅因NO_SIGNAL终结淘汰；W5/W9必须保留。','PROVISIONAL/HOLD不能充作干净维度；低基数确认和SG06绝对额路径继续由冻结S01执行器处理。','Reasonix独立复算了同内容CSV副本与gzip入口；P06两条负面路径主要由作者测试及代码审阅支持；Q05 helper在复审中未由Reasonix独立实跑。','本次不是全池原始PDF、财务字段或业务证据的第三方完整审计。','远端main推送被自动审批拒绝；控制文件仍维持S02待复核/S03锁定，状态更新只作提案。'])
 dump(OUT/'acceptance_recommendation.json',review)
 controls=['data/active_issue.json','PROJECT_STATE.json','data/issue_execution_plan.csv','data/issue_execution_plan.json']
 proposal=dict(status='PREPARED_NOT_APPLIED',base_remote_commit='e41f61d',expected_control_sha256={p:sha(ROOT/p) for p in controls},review_file=(OUT/'acceptance_recommendation.json').relative_to(ROOT).as_posix(),review_file_sha256=sha(OUT/'acceptance_recommendation.json'),proposed_changes={'S02_status':'ACCEPTED_WITH_LIMITS','S02_review_nature':review['review_nature'],'S03_status':'READY (guard integration and verification must precede any L1 triage; no actual consumer proof yet)','S03_required_input':'S00_TARGETED_REEXTRACTION_20261029','S03_required_gate':'tools/s03_input_gate.py plus pinned gate_contract.json and protected_21.csv','S03_pre_execution_rule':'必须实际调用守卫并保存消费验证记录后，才能计算冻结L1观察信号；不要求所有未知清零。','next_recommended_issue':'S03 #38','unchanged':'原始PDF、冻结S00/S01/S02数据、阈值与业务采用状态'},requires_explicit_authorization_for_remote_main=True,applied=False)
 dump(OUT/'proposed_control_updates.json',proposal)
 handoff='''# S02 接入复核与守卫交接（2026-10-29）

本轮接续 WorkBuddy 的 `e41f61d` 修复版接手状态。数据仍是已交付的 v2；本轮只修接入、复现和观察保护。正式数据与控制文件没有被覆盖，S03 未实际执行。

## 完成结果

- 计算器绑定真正载入的CSV/payload，并校验其已登记内容哈希；可读取已知同内容副本和`.csv.gz`，压缩件只在明确输出目录中解压缓存。
- v2每次重跑均自动应用已锁SHA的L0补丁，不会再遗留3家MIXED。v1明确显示补丁不适用；v2未应用补丁即失败关闭。
- 新计算清单登记calculator、formula、L0、上游A03及重抽计划哈希。生产代码已存本地提交 `d72d4d5`；`reproduction_manifest.json` 将它与canonical两张CSV的精确字节重现关联。历史canonical manifest保留不追改。
- 360份PDF的实际二进制SHA复验通过；19条原页金额/单位存在性与物理页位置检查通过（不冒称全量独立财务字段抽取）。新输入的28项政策结构检查和23项合成测试通过；11组接入测试、17项守卫测试、15项契约校验通过。
- Reasonix独立会话首轮退回3项，补修后复审结论 `PASS_TECHNICAL_WITH_LIMITS`；它在自己目录分别用CSV副本和gzip重跑，12,648格指标与1054家公司汇总均与canonical逐字节相同。完整意见及其未独立验证边界保留在reasonix目录。
- Q05 readiness支持显式绝对额确认；它不替代S01.signals_of/confirm_low_base/layers，也不能用于否决SG06等冻结允许的绝对额路径。

## 21家待核与下一步

10家EVALUABLE、8家W5、3家W9逐家写入protected_21.csv。开放覆盖问题未解决时，10家EVALUABLE原始NO_SIGNAL转待复核；W5无触发仍观察；W9保留数据/范围复核。PROVISIONAL/HOLD不得混入干净维度。不为筛选数量调阈值。

S03第一步必须实际调用tools/s03_input_gate.py的load_gate_inputs，并对已有L0/L1路由调用protect_existing_route；保存实际消费验证记录后才可做冻结L1技术宽筛。当前consumer_verified仍false，本轮没有生成S03名单。

## 复现

正式输入/指标仍在 runs/issues/S02/remediation_20261029/。执行`reproduce_committed.py`会自行从归档gzip产生隔离CSV副本，然后分别重算；不再依赖Reasonix临时输入目录。原公式文件存在已核实的Git LF/工作副本CRLF差异，来源清单同时记录两种哈希与纯换行等价性，未改写旧文件。

复跑接入测试：`python runs/issues/S02/recheck_20261029/integration/test_s02_integration.py`。
复跑守卫测试：`python -m unittest discover -s runs/issues/S02/recheck_20261029/gates -p test_s03_input_gate.py -v`。

## 发布断点

自动审批拒绝了直接推送GitHub main，理由为未获明确共享默认分支写入授权。因此远端控制仍是S02待复核、S03锁定。本包中的acceptance_recommendation.json是技术验收建议，proposed_control_updates.json是可审查但未应用的状态更新。不得把本地提交或Drive交付当作远端已更新，也不通过其他代理绕过该审批。获得明确授权后还须重读在线控制版本，冲突则先重读，不覆盖其他执行者。

代码覆盖包以现有修复版/e41f61d为基线；如本机代码已有其他修改，先比较哈希与差异，不盲目覆盖。包不包含原PDF、密钥、账号配置或大表测试副本。
'''
 (OUT/'handoff.md').write_text(handoff,encoding='utf-8')
 # A bounded package: code, tests, audit summaries and original-page evidence.
 files=[ROOT/'tools/s02_calculate.py',ROOT/'tools/s03_input_gate.py']
 for name in ['source_and_policy.py','source_policy_summary.json','pdf_binary_hashes.json','source_page_checks.json','reproduce_committed.py','reproduction_manifest.json','acceptance_recommendation.json','proposed_control_updates.json','handoff.md','prepare_completion.py']:files.append(OUT/name)
 files += [p for p in (OUT/'gates').iterdir() if p.is_file() and p.suffix in ('.py','.json','.md','.csv')]
 files += [OUT/'integration'/n for n in ['test_s02_integration.py','test_results.json','integration_review.md']]
 files += [OUT/'reasonix'/n for n in ['review_round1.md','review_round2.md','decision_round2.json']]
 files += [OUT/'reasonix/round2'/n for n in ['recalc_round2.json','recalc_round2.py','round2b.json','round2b.py']]
 files += list((OUT/'source_pages').glob('*.png'))+list((OUT/'source_pages').glob('*.txt'))
 # Preserve new execution manifests without including the large input caches.
 for mode in ['csv_copy','gzip']:files.append(OUT/'reproduction'/mode/'calculation_manifest.json')
 mf=dict(schema='S02_TECHNICAL_RECHECK_HANDOFF_V1',source_commit=repro['source_commit'],remote_main_updated=False,controller_updated=False,files=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p),bytes=p.stat().st_size) for p in sorted(set(files))])
 mp=OUT/'delivery_manifest.json';dump(mp,mf);files.append(mp)
 zp=ROOT.parent/'S02_接入复核与输入守卫_20261029.zip'
 with zipfile.ZipFile(zp,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
  for p in sorted(set(files)):z.write(p,p.relative_to(ROOT).as_posix())
 with zipfile.ZipFile(zp) as z:
  assert z.testzip() is None
  for f in mf['files']:assert hashlib.sha256(z.read(f['path'])).hexdigest()==f['sha256']
 receipt=dict(path=str(zp),sha256=sha(zp),bytes=zp.stat().st_size,files_verified=len(mf['files']),independent_verdict=decision['verdict'],remote_main_updated=False)
 dump(OUT/'package_receipt.json',receipt);print(json.dumps(receipt,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
