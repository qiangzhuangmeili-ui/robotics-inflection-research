# S06 观察名单准入、去重、辅助观察口径与重进规则

- 任务编号：S06（GitHub #41）
- 计划版本：`20261026_collection_first_v2`
- 知识截止日：`2026-10-25`（冻结不变）
- 放行依据：`runs/issues/S06/release_20261122.json`、`runs/issues/S06/handoff_from_s05_20261122.md`
- 需求先行指标方法依据：`METHOD_20261107_LEADING_INDICATORS`（`docs/需求先行指标分工_20261107.md`、`data/methodology_decision_20261107.json`）
- 辅助观察版本：`S06_AUX_LEAD_V1`
- 生成时间：`2026-11-22T23:45:00+08:00`

---

## 一、主线去重与全池主键守恒规则

1. **权威主键基线**：`data/company_master.csv` 共 1,054 家唯一 `security_id`，与 S05 验收分区完全互斥且覆盖：
   - S05 主线通过对照（`runs/issues/S05/quality_pass.csv`）：**277 家**
   - S05 主线观察对照（`runs/issues/S05/quality_observe.csv`）：**1 家**（`SZ:000856` 冀东装备）
   - 上游保留观察入口（`runs/issues/S05/observe_pool_preserved_776.csv`）：**776 家**
   - 合计：`277 + 1 + 776 = 1,054` 家，主键 0 重复、0 遗漏。
2. **严格去重原则**：
   - `early_stage_watch.csv`（共 **54 家**）**全部来自 776 非主线池**，与 S05 278 主线（277 通过 + 1 观察）**0 重叠**。已有历史证据但已进入 S05 主线的 **20 家**公司不重复计入早期观察，仅在 `handoff.md` 与 `review.json` 中按主键列明对照。
   - `missing_data_watch.csv`（共 **379 家**）由 **378 家**非主线 776 缺数据/守卫公司（`NON_MAINLINE_776`）与 **1 家** S05 主线观察结转（`SZ:000856` 冀东装备，`MAINLINE_S05_OBSERVE_CARRYOVER_DO_NOT_DOUBLE_COUNT`）构成，与 S05 277 `quality_pass.csv` **0 重叠**。
   - 两张观察表之间的交集为 **33 家**（已在 `missing_data_watch.csv` 的 `in_early_stage_watch=YES` 显式标出，统计总覆盖时按 `security_id` 去重，非主线观察并集共 **399 家**）。
   - S05 `quality_pass.csv`（277 家）内部已登记的专门待核项（RH02 待核 129、RH03 待核 19、RH06 待核 7、既有待核隔离 4 家在 pass + 1 家在 observe、越界观察 20 格）继续由 S05 原表承接，不在此重复造表。

---

## 二、早期储备观察（`early_stage_watch.csv`）准入与事实分层

1. **硬证据门槛（杜绝概念污染）**：
   - 仅复用已有可追溯证据（`archive/` 53 家旧分类附限制采用、10 家早期样本局部断言、`packages/B00_SOURCE_01/02`、`packages/C00_PILOT_01`、`packages/D00_B00_ADVANCE_01`），**不扩大全池采集或新增企业深研**。
   - `runs/issues/A04R/keyword_originals.jsonl` 与 `announcement_index.jsonl` **仅作原文定位器（locator）**，不单独构成业务事实准入依据。
   - 已有核查但结论为无机器人产品/仅合作意向/仅经营计划/仅 RPA 软件/证据不足的 **6 家**非主线公司（`BJ:920198` 微创光电、`BJ:920263` 中航泰达、`BJ:920002` 万达轴承、`SH:600699` 均胜电子、`SH:603466` 风语筑、`SH:688327` 云从科技）**明确不纳入**。
   - 其余未做业务精读的非主线公司一律保留业务证据 `UNKNOWN`，**不凭概念标签纳入**，也**不从来源覆盖反推精确的“无业务公司数”**。
   - 不在冻结 1,054 主表内的历史记录（如 `BJ:920007` 酉立智能）明确剔除。
2. **四类观察分桶（`watch_bucket`）与事实层级（`fact_tier`）**：
   - `EARLY_RD_PROTOTYPE_SAMPLING`（**16 家**）：已记录研发（`S0`）、样机（`S1`）或客户送样测试（`S2`）事实，不强制要求盈利。
   - `EARLY_PILOT_SMALL_BATCH`（**7 家**）：已记录付费试点/小批量交付或新品量产推进（`S3`）但未进 S05 主线。
   - `COMMERCIAL_NON_MAINLINE_RESERVE`（**11 家**）：已记录批量交付/直接机器人主业（`S4` 或 C00 确认主业），因未盈利、`HOLD_FOR_DATA`、`L2_NOT_IN_SCOPE` 或 `WATCH_AFTER_CUTOFF` 未进 S05 主线。
   - `EVIDENCED_PRODUCT_STAGE_UNKNOWN`（**20 家**）：已核实存在直接/间接机器人产品或业务，但原复核记录中产品线商业阶段为 `UNKNOWN`。
3. **非推荐边界**：观察名单**不是**买入推荐、投资候选或已商业化认定，不得跳过 S07/S08 直接进入估值。

---

## 三、缺数据观察（`missing_data_watch.csv`）准入与守卫结转

1. **纳入范围**（共 **379 家** = **378 家非主线** + **1 家 S05 主线观察**）：
   - `S05_QUALITY_HOLD_CONSOLIDATION_SCOPE_UNKNOWN`（**1 家**）：`SZ:000856` 冀东装备（S05 主线观察结转）。
   - `AFTER_CUTOFF_ISOLATED`（**4 家**）：`SH:603448` 天博智能、`SH:688836` 宇树科技、`SZ:301348` 蓝箭电子、`SZ:301699` 洛轴股份（沿用 S02 截止日后强制隔离）。
   - `PENDING_ANCHOR_RESELECTION`（**1 家**）：`SZ:002083` 孚日股份（锚定期待重选）。
   - `S04_HOLD_FOR_DATA_AND_QUALITY_SOURCE_UNKNOWN`（**9 家**）：同时处于 `HOLD_FOR_DATA` 与 15 家质量来源未知（`PENDING_CE_SOURCE`）交集。
   - `QUALITY_SOURCE_UNKNOWN_NON_MAINLINE`（**6 家**）：位于 `L2_NOT_IN_SCOPE` 但带 `PENDING_CE_SOURCE`（与上一类合计严格等于 **15 家**质量来源未知）。
   - `S04_HOLD_FOR_DATA`（**319 家**）：其余 S04 `HOLD_FOR_DATA`（与上面 9 家合计严格等于 **328 家**）。
   - `S02_METRIC_HOLD_OR_MISSING_NON_MAINLINE`（**39 家**）：虽未判 `HOLD_FOR_DATA`，但 S02 冻结指标表存在至少 1 个 `HOLD` 或 `MISSING` 单元格的非主线公司。
2. **未决守卫原样结转**：
   - 4 家截止日后隔离、1 家锚点待重选、15 家质量来源未知、8 项未采用父链提议（`#53` 开放）、S05 已登记专门待核全部原样保留，不擅自闭合 `#53`，不把 `44/231/378` 历史未冻结统计当作当前派工名单。
   - **缺数据不填零**：`HOLD`、`MISSING`、`PROVISIONAL`、`NOT_COMPARABLE`、`UNDEFINED_BASE` 严格分列，均不视作 0 或无业务。

---

## 四、需求先行辅助观察口径登记（`S06_AUX_LEAD_V1`）

依据 `METHOD_20261107_LEADING_INDICATORS`（`data/methodology_decision_20261107.json`），在首次采用合同负债与可信在手订单作为 S06 辅助观察前，预先登记版本 `S06_AUX_LEAD_V1` 如下：

| 登记项 | 合同负债（`AUX.CONTRACT_LIAB`） | 可信在手订单（`AUX.VERIFIED_BACKLOG`） |
|---|---|---|
| **辅助观察版本** | `S06_AUX_LEAD_V1`（独立辅助观察标签，不改 S01/S04/S05 冻结硬门槛） | `S06_AUX_LEAD_V1`（独立辅助观察标签，不改 S01/S04/S05 冻结硬门槛） |
| **字段定义** | 合并资产负债表“合同负债”期末余额（人民币元），须与合同资产（`FIN.CONTRACTASSET.INSTANT`）严格分列，禁止混用 | 正式公告/定期报告明确披露的已生效在手合同/订单金额，须区分生效合同、框架/意向协议、已履行部分及取消/变更风险 |
| **权威来源与期间** | 合并资产负债表原页（与公司锚定期及上年同期同口径配对）；**当前状态：不在 P04/S00 冻结标准化字段内** | 交易所正式定期报告、重大合同签约公告原页（含物理页码与主体范围）；`A04R` 公告目录仅作定位器 |
| **适用业务模式** | 项目型系统集成（`PROJECT`）、定制设备/预收款模式优先参考；消费零售/标准品短账期模式须结合付款条款解释，增减不自动判好坏 | 项目型（`PROJECT`）与大额配套/运维服务合同；框架协议或按实际发生额结算合同（如主线对照 `BJ:920207` 众诚科技数采中心合同）不得当作确定收入 |
| **当前版本取值与缺失语义** | 非主线观察名单统一记 `UNKNOWN`（原因：`NOT_IN_FROZEN_S00_SCHEMA`），**不填 0、不据此淘汰**；不作全池补抽 | 非主线观察名单统一记 `UNKNOWN`（原因：`NO_VERIFIED_STRUCTURED_BACKLOG_IN_EXISTING_RECORDS`），**不填 0、不据此淘汰** |
| **既有可定位线索对照（不重复计入非主线）** | `packages/D00_B00_ADVANCE_01` 已记录主线公司 `BJ:920578` 巨能股份 2026H1 合同负债较期初下降 34.59%（主线参考，留 R00/R01 核验） | `packages/D00_B00_ADVANCE_01` 已记录主线公司 `BJ:920207` 众诚科技 2026-07-15 签约数采中心合同（83,123,260 元/年、36 个月、按实际下单与发生额结算，实际订单/验收待核） |
| **重进/升级条件** | 在后续定向核验或增量版中对具体观察对象回读已归档报告合并资产负债表原页，登记同期与上期合同负债、付款条款及交付节奏后再解除 `UNKNOWN` | 取得正式公告/定期报告原页并核实合同主体、签署/统计时点、生效状态、金额口径与履约进展后，方可转为已核辅助观察线索；订单转化与在建工程产能归属留 R00/R01 核验 |

---

## 五、可验证的重进条件（Re-entry Rules）总则

每家观察公司均在 CSV 的 `reentry_trigger_conditions` 列写明具体触发条件，汇总遵循四条统一硬原则：

1. **时间隔离重进（4 家 `WATCH_AFTER_CUTOFF`）**：严禁在 `2026-10-25` 冻结口径下放行；仅在增量版本（R05）上调截止日后，纳入新披露正式财报重算 S02–S05。
2. **数据缺口重进（`HOLD_FOR_DATA` / `PENDING_ANCHOR_RESELECTION` / `PENDING_CE_SOURCE` / `S05_QUALITY_HOLD` / S02 `HOLD`/`MISSING`）**：必须由正式定期报告原页核验闭合对应缺失或争议单元格（含合并范围、重述版本、父键口径），并按冻结 S01/S04/S05 规则全量重算通过，禁止手工加回。
3. **早期业务重进（`S0`→`S1`→`S2`→`S3`→`S4`）**：按“研发→样机→送样→小批量/付费试点→批量交付/独立收入”逐级提供可核验的正式披露原文（含主体、产品线、物理页码、期间与金额/数量口径），不得将概念、意向或库存入库视作外部交付收入。
4. **盈利与主线重进**：未盈利早期企业可保留在 S06 早期观察并随后续定期报告跟踪；若要进入主线候选用池，仍须经 S07 抽查与 S08 名单验收，并按冻结规则满足相应信号与质量要求。
