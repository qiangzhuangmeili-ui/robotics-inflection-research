# S06 / #41 正式放行与交接

核对日期为 2026-11-22（北京时间）。计划版本为 20261026_collection_first_v2。
用户已确认放行。放行时间为 2026-11-22T23:29:38+08:00。Antigravity 尚待实际领取，主审为 Codex。[放行记录](release_20261122.json)

## 放行范围

S06 复用现有可追溯材料，整理早期储备、缺数据和重进条件。S01 和 S02 为正式依赖。S05 为对照与去重基线。S02 原验收仅授权 S03 复算，本次放行允许复用同一快照的状态、期间及缺口用于 S06 观察，保留所有原有限制。采用 2026-10-25 截止日和既定规则。主线资格及既有验收结论沿用冻结版本。

## 输入及主键

1. S01 验收为 runs/issues/S01/acceptance_20261029.json。规则沿用 S01 已冻结版本及后续登记的适用补充。需求辅助观察另做口径登记。
2. S02 采用 S02_FINAL_SNAPSHOT_20261102 及 runs/issues/S02/acceptance_20261106/s03_input_contract.json 的冻结时点限制。对应 runs/issues/S02/hangcha_restated_20261101/s02_v10/all_pool_metrics.csv 的 SHA-256 为 3091b0bb82a3e3114d7f338595c40d82c842ce47aa8802b141a6ce8ec2232953。用它作状态和缺口索引，区分 OK、PROVISIONAL、HOLD、MISSING、NOT_COMPARABLE、NOT_APPLICABLE 和 UNDEFINED_BASE。用已带时点隔离的下游记录约束裸 v10。
3. S05 基线按 runs/issues/S05/acceptance_s05_r1_20261121.json。quality_pass.csv 的 277 家为通过对照。quality_observe.csv 的冀东装备 1 家继续观察。observe_pool_preserved_776.csv 为上游保留观察入口。已复点 277＋1＋776＝1,054 家，互斥且等于 company_master 主键。278 家用于主线对照和去重，包含两种路由。776 家用于检查观察理由或缺数据。加入早期储备须有实际证据。与主线已有记录冲突时按主键关联并标原路径，避免重复计数。
4. 沿用 4 家截止日后隔离、1 家锚点待重选、15 家质量来源未知、8 项未采用父链及 S05 已登记的专门待核。#53 的未决事项维持开放。44/231/378 属历史未冻结统计，不作为派工名单，也不用于替换当前分区。

## 证据和辅助指标

- 从 data/resource_map.csv 定位证据，使用 archive/ 内有适用范围的验收记录及 B00/C00/D00 已核主张。53 家旧采用记录、10 家局部样本与报告取得记录各自保留原限制。A04R 关键词或公告目录只提供原文定位。保留公司、产品、披露日、原文 ID/URL、物理页、短引文、已核或待核状态。研发、样机、送样按已能支持的事实层级登记。证据不足标 UNKNOWN，不从来源覆盖推算精确的未知公司数。
- 合同负债缺于 P04 和冻结 S00 标准化字段。复用已有可定位合同负债证据，并可为已进入观察范围的个别对象定向回读现有归档原页。没有实际定向证据时保留 UNKNOWN，并记 NOT_IN_FROZEN_S00_SCHEMA 或实际缺口。合同资产与合同负债分列。无需全池补抽。
- 在手订单只沿用能定位到正式披露且可核主体、时点、状态、金额口径的材料。区分生效订单、框架意向、已履行部分与取消变更。只有索引或未披露时留 UNKNOWN。
- 首次采用两项辅助指标前，按 METHOD_20261107_LEADING_INDICATORS 登记定义、来源、期间、适用模式、缺失和重进条件及版本。保留独立辅助观察标签。已实现收入仍按收入证据确认。在建工程、订单转化与机器人产能核验安排在筛后既定阶段。

## 开工和验收

线上明确发布 release_S06=true、#41 进入 READY 后，由 Antigravity 读取最新调度及上述实际输入，在确认占用为空时按最新 SHA 领取一张卡。主仓库当前实际读取条件已由接手回执核对，git fetch 的本机代理故障作为环境备注记录。线上读状态沿用可用的 GitHub 接口。

交付目录为 runs/issues/S06/，产物为 early_stage_watch.csv、missing_data_watch.csv、watch_reentry_rules.md、manifest.json、handoff.md 和 review.json。复核公司主键、证据支持、时间隔离、未决项结转和每家重进条件。候选池大小由证据决定。执行方按 SELF_CHECK 记录，交 Codex 独立复核。

#41 等待 Antigravity 实际领取。S07/S08 仍按依赖执行。
