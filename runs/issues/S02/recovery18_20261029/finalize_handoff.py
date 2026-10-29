"""Finalize factual review metadata and the bounded, non-screening handoff."""
import csv,hashlib,json
from collections import Counter
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
OUT=HERE/'integration/v3_output_run2'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load(p):return json.loads(p.read_text(encoding='utf-8'))
def save(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf-8')
def csvread(p):return list(csv.DictReader(p.open(encoding='utf-8-sig')))
def main():
 recovery=load(OUT/'recovery18_manifest.json');replay=load(HERE/'integration/s02_replay_v3_run2/replay_manifest.json')
 adoption=load(OUT/'source_adoption_check.json')
 assert recovery['decision'].startswith('SELF_CHECK_PASS') and replay['decision'].startswith('SELF_CHECK_PASS') and adoption['decision']=='PASS'
 # The accepted calculator carries a historical WorkBuddy template label.
 # Correct only this newly produced candidate's authorship and disjoint QC counts.
 corrections=[]
 for filename in ('calculation_manifest.json','review.json'):
  p=OUT/'s02'/filename;m=load(p);old_hash=sha(p);old={k:m[k] for k in ('executor','reviewer','checks_pass','checks_warn') if k in m}
  m['engine_template_attribution']=old;m['executor']='Codex'
  if filename=='review.json':
   m['reviewer']='Codex';counts=Counter(x['result'] for x in m['checks'])
   m['checks_pass']=counts['PASS'];m['checks_warn']=counts['WARN'];m['checks_fail']=counts['FAIL']
   m['checks_count_semantics']='Disjoint result counts; WARN can satisfy the nonblocking gate but is not counted again as PASS.'
  m['review_nature']='SELF_CHECK';save(p,m)
  corrections.append(dict(path=str(p.relative_to(ROOT)).replace('\\','/'),before_sha256=old_hash,after_sha256=sha(p),old_template_fields=old,actual_executor='Codex',financial_rows_changed=False))
 receipt=dict(review_nature='SELF_CHECK',reason='Correct inherited calculator template authorship; distinguish PASS and WARN counts without changing any check decision or financial output.',changes=corrections)
 save(OUT/'metadata_corrections.json',receipt)
 scope={x['security_id']:x for x in csvread(OUT/'coverage_resolution_v2_v3.csv') if x['in_recovery18_scope']=='YES'}
 scope_unknown={'BJ:920146':'华阳变速','BJ:920198':'微创光电','SZ:301348':'蓝箭电子'}
 followups=[]
 for sec,name in scope_unknown.items():
  r=scope[sec];followups.append(dict(security_id=sec,stock_name=name,case='REPORTING_SCOPE_UNRESOLVED',latest_usable_period=r['v3_latest_period_key'],reason='完整原报表及相关披露仍不足以确认本期全部报告主体范围' if sec!='SZ:301348' else '收购进展未披露明确完成日，不能确认2026-06-30截止时是否已纳入新子公司',s03_requirement='必须保留口径待核；旧期结果不得冒充2026H1结论；不因旧期指标触发而自动解除此缺口'))
 followups.extend([
  dict(security_id='SZ:002083',stock_name='孚日股份',case='REPORTED_AMOUNTS_RESTORED_SCOPE_CHANGE_HOLD',latest_usable_period='20260930',reason='已恢复原数；8月新增合并范围，11个比较指标HOLD，另1项不适用',s03_requirement='保留观察，必须使用comparability_adapter，核实可比范围后才释放'),
  dict(security_id='SZ:000625',stock_name='长安汽车',case='CURRENT_YTD_RESTORED_Q1_REVENUE_GAP',latest_usable_period='20260630',reason='H1正式合并营业收入已恢复；2025/2026Q1仅有营业总收入，按P04不替代正式FIN.REV，M02/M03仍缺',s03_requirement='按冻结规则处理部分可评估指标，同时保留单季营收缺口，不手工补零'),
 ])
 for sec,name in [('SH:603448','天博智能'),('SH:688836','宇树科技'),('SZ:301699','洛轴股份')]:
  followups.append(dict(security_id=sec,stock_name=name,case='OUTSIDE_RECOVERY18_NO_CURRENT_PDF_IN_LEDGER',latest_usable_period='',reason='本次18家之外；当前台账没有可用本期原报告，招股材料及期间适用性仍待核',s03_requirement='未知保持未知，不能当作没有改善；不得仅凭取件状态宣称原文不存在'))
 save(HERE/'remaining_cases_v3.json',dict(review_nature='SELF_CHECK',source_followups=followups,not_a_candidate_or_signal_list=True,s03_release=False))
 final=load(OUT/'s02/calculation_manifest.json')
 review=dict(issue_key='S02',version='RECOVERY18_V3_20261030',executor='Codex',reviewer='Codex',review_nature='SELF_CHECK',decision='SELF_CHECK_PASS_WITH_SOURCE_LIMITS_EXTERNAL_REVIEW_REQUIRED',target_companies=18,corrected_documents=56,main_source_defect_resolved_companies=13,partially_resolved_companies=2,scope_unresolved_companies=3,normalized_rows=229216,comparison=recovery['comparison'],metric_counts=final['counts'],source_adoption=dict(value_checks=511,scope_held_checks=110,errors=0),metrics_replay=dict(path=str((HERE/'integration/s02_replay_v3_run2/replay_manifest.json').relative_to(ROOT)).replace('\\','/'),sha256=sha(HERE/'integration/s02_replay_v3_run2/replay_manifest.json'),all_pool_metrics_bytes_equal=True,company_summary_bytes_equal=True),metadata_corrections_sha256=sha(OUT/'metadata_corrections.json'),source_followups_path=str((HERE/'remaining_cases_v3.json').relative_to(ROOT)).replace('\\','/'),source_pdf_audit_is_independent=False,formal_input_adopted=False,controls_changed=False,s03_release=False)
 save(HERE/'review.json',review)
 report='''# S02 18家公司定向修复交接（2026-10-30）

18家全部完成有边界的原件核查并生成新版本：13家主要抽取/单位/报表定位缺陷已排除，2家部分解决，3家仍有明确的报告范围缺口。这里的“解决”是排除本次主要数据缺陷，不表示所有指标均为干净OK，也不是企业改善结论。

新版本恢复了56份报表的修正/待核记录。1054家公司×12项指标共12,648格已统一重算，另一个全新输出目录的复算与指标表、公司汇总表逐字段且逐字节一致。18家以外的1036家公司，其标准化行、12,432个指标格、公司汇总和相关QC记录均未变。原PDF、v1/v2、冻结公式和信号阈值保留。

## 仍保留的限制

- 华阳变速、微创光电：查阅了完整年报和相关半年报/季报，仍未取得足够证据确认全部报告主体范围。本期原值另存待核，不放入正常合并值。最新可用期因此退回2025年报，不能把旧期结果当作2026H1结论。
- 蓝箭电子：股东会在6月29日通过收购，8月进展公告只说“近日”完成登记，未给明确完成日。6月30日的合并范围仍待核；当前可用期回退至2026Q1，不能当作半年报无改善。
- 孚日股份：扫描报表原数已经恢复，但8月新增并表子公司。比较口径未核清，11个指标继续HOLD；不把并购带来的增长当作已经确认的改善。
- 长安汽车：H1正式合并营业收入已恢复，两份Q1正式营业收入仍缺；不拿“营业总收入”或摘要替代，相关单季指标仍缺。
- 原21家中的另外3家（天博智能、宇树科技、洛轴股份）不在本次有原件的18家范围；本期台账缺件/期间适用性仍须核，不解释成没有改善。

国机通用采用了明确的原文证据链：原子公司已吸收合并并注销、全部业务和债权债务由公司承继，年报和随后半年报均无子公司。其通用表名按“零子公司、全报告主体”作等效范围映射，保留原始表名和本次SELF_CHECK判断，未伪造合并标题。

## 验证与交付位置

- canonical：integration/v3_output_run2/，完整新标准表为s00/financial_normalized.csv.gz；12,648格结果为s02/all_pool_metrics.csv。
- 来源更正实际入表检查：511条有值记录、110条范围暂扣字段，零错误；记录在source_adoption_check.json。
- 独立执行的计算复算：integration/s02_replay_v3_run2/replay_manifest.json。这里只独立重新计算，不是原始PDF的外部独立审计。
- xcheck11保存11家40条更正台账及439条基础字段/派生源追溯；scope5保存20份范围判定结果；ocr2保存8份OCR核对结果及118条选数记录。
- remaining_cases_v3.json是上游资料/口径待核清单，不是S03候选名单。

新输入有3项非阻断提示：与历史S01计数不同、最新可用期分布变化、仍有覆盖缺口。全部阻断检查通过。review.json的PASS/WARN为互斥计数；生产计算器旧模板中的WorkBuddy署名已在本候选的元数据里纠正为实际执行者Codex，修改前后哈希见metadata_corrections.json，不影响任何财务行。

## 计算复现

本候选使用P04比较范围门禁。单独运行生产s02_calculate.py不能重现孚日的范围HOLD；必须使用同一comparability_adapter和已登记的comparability_holds.json。准备好的复算命令（从仓库根运行，输出目录须不存在）：

```powershell
& '<Python可执行文件>' -B runs/issues/S02/recovery18_20261029/integration/replay_metrics_v3.py --execute --v3-manifest runs/issues/S02/recovery18_20261029/integration/v3_output_run2/recovery18_manifest.json --out-dir runs/issues/S02/recovery18_20261029/integration/external_replay
```

## 状态

SELF_CHECK_PASS_WITH_SOURCE_LIMITS，等待外部来源/口径复核。没有接管正式v2输入，没有改active_issue、PROJECT_STATE或issue计划，没有启动S03。旧v2的S03输入守卫也不能直接接受新v3哈希。后续必须复核来源限制、将新输入与范围门禁正确接入实际S03消费者并验证后，才可更新正式放行记录；不得仅凭本包自检或覆盖率提高解除剩余待核。
'''
 (HERE/'handoff.md').write_text(report,encoding='utf-8')
 print(json.dumps({k:review[k] for k in ['decision','target_companies','corrected_documents','main_source_defect_resolved_companies','partially_resolved_companies','scope_unresolved_companies','s03_release']},ensure_ascii=False))
if __name__=='__main__':main()
