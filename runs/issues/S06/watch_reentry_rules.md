# S06 观察名单准入、去重、辅助观察口径与重进规则（返修轮 R2）

- 任务编号：S06（GitHub #41）
- 计划版本：`20261026_collection_first_v2`
- 知识截止日：`2026-10-25`（冻结不变）
- 放行依据：`runs/issues/S06/release_20261122.json`、`runs/issues/S06/handoff_from_s05_20261122.md`
- 返修依据：`runs/issues/S06/codex_review_s06_20261122.md`、`runs/issues/S06/codex_review_s06_r1_20261123.md`（本地复核溯源引用，非运行必需输入）
- 需求先行指标方法依据：`METHOD_20261107_LEADING_INDICATORS`（`docs/需求先行指标分工_20261107.md`、`data/methodology_decision_20261107.json`）
- 辅助观察版本：`S06_AUX_LEAD_V1`
- 生成时间：`2026-11-23T00:22:20+08:00`

---

## 一、主线去重与全池主键守恒规则

1. **权威主键基线**：`data/company_master.csv` 共 1,054 家唯一 `security_id`，与 S05 验收分区完全互斥且覆盖：
   - S05 主线通过对照（`runs/issues/S05/quality_pass.csv`）：**277 家**
   - S05 主线观察对照（`runs/issues/S05/quality_observe.csv`）：**1 家**（`SZ:000856` 冀东装备）
   - 上游保留观察入口（`runs/issues/S05/observe_pool_preserved_776.csv`）：**776 家**
   - 合计：`277 + 1 + 776 = 1,054` 家，主键 0 重复、0 遗漏。
2. **严格去重原则**：
   - `early_stage_watch.csv`（共 **54 家**）**全部来自 776 非主线池**，与 S05 278 主线（277 通过 + 1 观察）**0 重叠**。已有历史证据但已进入 S05 主线的 **20 家**公司不重复计入早期观察，仅在 `handoff.md` 列明对照。
   - `missing_data_watch.csv`（共 **379 家**）由 **378 家**非主线 776 缺数据/守卫公司（`NON_MAINLINE_776`）与 **1 家** S05 主线观察结转（`SZ:000856` 冀东装备，`MAINLINE_S05_OBSERVE_CARRYOVER_DO_NOT_DOUBLE_COUNT`）构成，与 S05 277 `quality_pass.csv` **0 重叠**。
   - 两张观察表之间的交集为 **33 家**（已在 `missing_data_watch.csv` 的 `in_early_stage_watch=YES` 显式标出，非主线观察去重并集共 **399 家**）。

---

## 二、早期储备观察（`early_stage_watch.csv`）准入、主体绑定与多产品线规则

1. **硬证据门槛（杜绝概念污染与误采用）**：
   - 仅复用已有可追溯证据（`archive/` 53 家旧分类附限制采用、10 家早期样本局部断言、`packages/B00_SOURCE_01/02`、`packages/C00_PILOT_01`），**不扩大全池采集或新增企业深研**。
   - 凡源登记标为 `DO_NOT_ADOPT`（如 `BJ:920124` 南特科技旧镜像 `R1A02-E001`）的记录**严禁列入采用 `evidence_ids`**，仅降格记录在 `non_adopted_historical_locators`。
   - `runs/issues/A04R/keyword_originals.jsonl` 仅作原文定位器（locator），不单独构成业务事实准入依据。
   - 已有核查但为无机器人产品/仅意向/仅计划/仅 RPA/证据不足的 **6 家**非主线公司与主表外 1 家（`BJ:920007`）**明确不纳入**；其余未深研非主线公司保持 `UNKNOWN`，不凭概念纳入，也不反推精确的“无业务公司数”。
2. **主体绑定与多产品线保留规则（R1 修订重点）**：
   - **主体严格分离**：非并表参股公司产品线（`ASSOCIATE_NOT_CONSOLIDATED`）不得决定上市主体主桶；例如 `SH:603219` 富佳股份按上市母公司扫地机器人 ODM（`stage=UNKNOWN`）归入 `EVIDENCED_PRODUCT_STAGE_UNKNOWN`，参股公司芯禾机器人（`S1`/`S3`）仅作为间接观察保留在 `all_recorded_product_lines` 与 `other_verified_stages`。
   - **多产品线全量保留**：公司按 `security_id` 去重为一行；当并表/上市主体同时存在早期线（`S0`–`S2`）与较高阶段线（`S3`/`S4`）时，主桶优先服务早期观察（`bucket_selection_rule=PRIMARY_BUCKET_EARLY_S0_S2_FIRST_WITH_OTHER_STAGES_PRESERVED`），同时在 `all_recorded_product_lines` 与 `other_verified_stages` 中完整保留全部已核产品线、阶段、主体与证据 ID（涵盖华勤技术 `R1B02-PL041` S4、捷昌驱动 `R1A02-PL013` S4、埃夫特 `R1B1-PL001` S4、新时达 `R1B1-PL006/007` S3），确保 S07 分层抽样同步取到全部阶段证据。
3. **四类观察分桶（R1 重算结果，共 54 家）**：
   - `EARLY_RD_PROTOTYPE_SAMPLING`（**15 家**）：并表/上市主体已记录研发（`S0`）、样机（`S1`）、送样（`S2`）或供货规模待核的早期线索（含宁波韵升 2026H1 物理第 11 页长期协议/样品交付与供货，规模与收入未知）。
   - `EARLY_PILOT_SMALL_BATCH`（**6 家**）：并表/上市主体已记录付费试点/小批量交付（`S3`）；德昌股份因未证外部交付已移出本桶。
   - `COMMERCIAL_NON_MAINLINE_RESERVE`（**11 家**）：已记录 `S4` 批量交付或 C00 确认商业化主业，但因财务指标、`HOLD_FOR_DATA` 或截止日后隔离未进 S05 主线。
   - `EVIDENCED_PRODUCT_STAGE_UNKNOWN`（**22 家**）：已核实存在机器人产品/业务或量产推进，但交付/商业阶段为 `UNKNOWN`（含富佳股份上市母公司口径、德昌股份物理第 12 页量产推进未证外部交付）。
4. **非推荐边界**：观察名单不是买入推荐、投资候选或已商业化认定，不跳过 S07/S08 进入估值。

---

## 三、缺数据观察（`missing_data_watch.csv`）与截止日诊断约束

1. **纳入范围**（共 **379 家** = **378 家非主线** + **1 家 S05 主线观察**）：
   - `S05_QUALITY_HOLD_CONSOLIDATION_SCOPE_UNKNOWN`（**1 家**）：`SZ:000856` 冀东装备。
   - `AFTER_CUTOFF_ISOLATED`（**4 家**）：`SH:603448` 天博智能、`SH:688836` 宇树科技、`SZ:301348` 蓝箭电子、`SZ:301699` 洛轴股份。**这 4 家的 `s02_gap_diagnostic_scope` 明确标注为 `AFTER_CUTOFF_ISOLATED_DIAGNOSTIC_ONLY_NOT_ADMISSIBLE_BEFORE_R05`**，其 S02 裸状态计数仅作隔离期诊断，S07 抽样须继续严格执行 `2026-10-25` 截止日隔离。
   - `PENDING_ANCHOR_RESELECTION`（**1 家**）：`SZ:002083` 孚日股份。
   - `S04_HOLD_FOR_DATA_AND_QUALITY_SOURCE_UNKNOWN`（**9 家**）与 `QUALITY_SOURCE_UNKNOWN_NON_MAINLINE`（**6 家**）：合计严格等于 **15 家**质量来源未知（`PENDING_CE_SOURCE`）。
   - `S04_HOLD_FOR_DATA`（**319 家**）：与上面 9 家合计严格等于 **328 家** `HOLD_FOR_DATA`。
   - `S02_METRIC_HOLD_OR_MISSING_NON_MAINLINE`（**39 家**）。
2. **未决守卫结转**：4 家截止日后隔离、1 家锚点待重选、15 家质量来源未知、8 项未采用父链提议（`#53` 开放）、S05 专门待核均原样保留；缺数据不填零。

---

## 四、需求先行辅助观察口径登记（`S06_AUX_LEAD_V1`）

依据 `METHOD_20261107_LEADING_INDICATORS`（`data/methodology_decision_20261107.json`），预先登记 `S06_AUX_LEAD_V1`：

| 登记项 | 合同负债（`AUX.CONTRACT_LIAB`） | 可信在手订单（`AUX.VERIFIED_BACKLOG`） |
|---|---|---|
| **辅助观察版本** | `S06_AUX_LEAD_V1`（独立辅助观察标签，不改 S01/S04/S05 冻结硬门槛） | `S06_AUX_LEAD_V1`（独立辅助观察标签，不改 S01/S04/S05 冻结硬门槛） |
| **字段定义** | 合并资产负债表“合同负债”期末余额（人民币元），须与合同资产（`FIN.CONTRACTASSET.INSTANT`）严格分列 | 正式公告/定期报告明确披露的已生效且可量化在手合同/订单金额，须区分生效订单、长期框架协议、已履行部分及取消/变更风险 |
| **来源与期间** | 合并资产负债表原页（锚定期与上年同期同口径配对）；当前不在 P04/S00 冻结标准化字段内 | 交易所正式定期报告、重大合同签约公告原页（含物理页码与主体范围）；`A04R` 仅作定位器 |
| **适用业务模式** | 项目型系统集成（`PROJECT`）、定制设备/预收款模式优先参考；结合付款条款解释 | 项目型与大额配套/运维服务合同；框架协议或长期协议（如 `SH:600366` 宁波韵升 2026H1 第 11 页长期协议、主线对照 `BJ:920207` 众诚科技按实际下单结算合同）不推定为确定在手订单金额 |
| **当前取值与缺失语义** | 非主线观察名单统一记 `UNKNOWN`（`NOT_IN_FROZEN_S00_SCHEMA`），不填 0、不淘汰 | 非主线观察名单统一记 `UNKNOWN`，不填 0、不淘汰 |
| **既有主线参考（不重复计入非主线）** | `packages/D00_B00_ADVANCE_01/results/evidence.csv` 记录主线 `BJ:920578` 巨能股份 2026H1 合同负债较期初下降 34.59% | `packages/D00_B00_ADVANCE_01/results/evidence.csv` 记录主线 `BJ:920207` 众诚科技数采中心合同（83,123,260 元/年、按实际下单结算，实际履约待核） |
| **重进/升级条件** | 对特定观察对象定向回读已归档报告合并资产负债表原页并登记同口径对比后解除 `UNKNOWN` | 取得正式原文核实主体、统计时点、生效状态与可量化金额口径后方可转为已核辅助观察；订单转化与在建工程留 R00/R01 核验 |

---

## 五、可验证的重进条件（主线准入与业务核证分离）

每家公司均在 `reentry_trigger_conditions` 中分列两部分：
1. **【主线重进】**：严格按冻结 S01/S04/S05/R05 规则执行（截止日隔离→R05 增量重算；`HOLD_FOR_DATA`→闭合财务/来源/重述缺口后重算 L2；未入围→后续定期报告出现至少 2 个干净维度改善信号并通过 S05），禁止手工加回。
2. **【业务核证目标】**：按各自 `fact_tier` 与主体范围写明具体可验证节点（`S0`→`S1`/`S2`、`S1`→`S2`/`S3`、`S2`→`S3`、`S3`→`S4`、宁波韵升→核供货规模与收入归属、德昌股份→核外部交付、富佳股份→母公司与参股分核），不强行套用“必须单列独立分部毛利”的一刀切模板。
