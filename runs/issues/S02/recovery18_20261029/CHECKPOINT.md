# S02 剩余18家公司定向修复

2026-10-30继续2026-10-29中断的工作；仍为S02的辅助修复，不领取S03。
在线active_issue复核仍为WorkBuddy占用S02、修复v2等待外部复核。控制文件未改。

- 冻结v1/v2和原始PDF保留。新成果全部在本目录。
- xcheck11负责11家三表/摘要差异；scope5负责4家通用表名+比亚迪；ocr2负责中国中铁和孚日。
- ocr2已生成8份corrected_results，118条选数证据；金额、当期列及单位已逐项对原页图核对，8份三表与摘要核心值一致。孚日2026Q3明确新增合并范围，原数恢复仍须比较待核。
- comparability_holds.json是明确原文支持的待核输入门禁；不改变S01公式或阈值。
- integration正在准备完整v2覆盖+18家新修正的v3重算；源未齐不正式执行。
- scope5当前输出仍在修订，通用摘要fallback不得绕过P04正式报表字段契约。只用有证据的原报表单元格；未确认范围不假标集团合并。
- 只有独立新结果自检，不是外部验收。S03锁定。
- 不推送远端main，不写GitHub评论/控制文件；先前remote push自动审查拒绝仍适用，不能用其他工具绕过。

## 2026-10-30追加断点

- 三组源结果均已定稿：xcheck11=28份/11家公司、scope5=20份/5家公司、ocr2=8份/2家公司，共56份。
- xcheck11有40条更正台账、439条基础字段/派生源追溯记录、43份实际指标引用PDF；仅长安两份Q1正式营业收入按P04仍缺。
- scope5保留3家具体范围缺口：华阳变速、微创光电、蓝箭电子。国机通用两期已用吸收合并并注销原子公司及后续无子公司证据批准等效全报告主体。比亚迪只用正式三表原行，取消summary fallback。
- 蓝箭交易进展原件已由父代理下载并核图：additional_sources/，2026-037公告仅称“近日”完成，不能确认6月30日截止时范围；仍HOLD。
- 全量runner尚未进入S00计算/创建输出：已修旧v2 IMAGE_ONLY合法空fields，以及旧计划D盘路径映射。最新剩余前置兼容点是comparability_adapter.verify_hold_source_files须对同一经索引/字节核验的D盘junction原件使用一致路径规则；integration_review正在收尾并做只读preflight。
- 来源修复JSON已锁定，不再改三组源文件。后续运行统一重算、source_adoption实际入表检查、metrics独立replay，再打包Drive交付；不得把当前未执行状态说成全量通过。

下一步：integration前置检查通过后执行rebuild_v3.py --execute；完整成功前不放行S03、不改正式输入与控制文件。

## 最终有效断点（上面的运行前断点已经解决）

- canonical为integration/v3_output_run2/：全量S00/S02执行成功，229216行标准表、12648个指标格，183个指标全字段行变化、18家公司变化。
- 非目标1036家公司全部标准化行、12432个指标行、公司汇总和290条QC记录完全不变。
- source_adoption_check.json：511条有值记录和110条范围暂扣字段核对，零错误。
- integration/s02_replay_v3_run2/replay_manifest.json：第二个全新目录独立执行计算，指标和公司汇总逐字段、逐字节相同。此前空目录/失败尝试不是canonical。
- 根review.json、handoff.md、remaining_cases_v3.json为本次对外结论：13家主要缺陷排除、2家部分解决、3家仍有范围缺口。另3家原件/期间待核在18家范围之外保留。
- 本候选S02 JSON的历史模板WorkBuddy署名已更正为Codex，PASS/WARN计数拆开；修改前后指纹在metadata_corrections.json，未改财务行。所有结果仍是SELF_CHECK。
- S03未启动，正式输入/控制文件未接管，远端main未推送。交接包归档和回读校验完成后方可报告交付。
