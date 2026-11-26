# S07 / #42 抽查阈值边界、漏筛和缺数据偏差｜审计报告

生成时间：2026-11-26T13:30:00+08:00（北京时间）。计划版本 `20261026_collection_first_v2`，知识截止日 `2026-10-25`。
执行方：CodeBuddy；统筹方：Antigravity；独立复核指派：Codex。本报告为 `SELF_CHECK`，不释放 S08。

## 1. 审计范围与方法

本卡只做**小样本规则与计算审计**：不重研全池、不逐家深读公告、不调整任何冻结阈值、不把任何公司手工加回主线。

### 1.1 确定性分层抽样

抽样不使用随机数：每个分层先定义候选池与配额，再以固定排序键（`security_id` 升序，或到阈值的绝对距离、再 `security_id`）取前 N 家。跨层去重，单家公司可带多个标签。

样本总量 **62 家**（要求 50–65 家）。各主分层数量：

| 分层 | 数量 |
|---|---:|
| BOUNDARY_PASS_FAIL | 22 |
| BJ_MARKET | 7 |
| LOSS_AND_LOW_BASE | 8 |
| MISSING_DATA_WATCH | 14 |
| EARLY_STAGE_WATCH | 6 |
| REVERSE_OMISSION | 5 |

| 子槽 | 分层 | 配额 | 实取 | 入选规则 |
|---|---|---:|---:|---|
| B01_S03_MIN_2DIM | BOUNDARY_PASS_FAIL | 1 | 1 | S03 wide_pass with exactly 2 clean dimensions (minimum pass); security_id asc |
| B02_S03_MIN_1DIM | BOUNDARY_PASS_FAIL | 1 | 1 | S03 wide_pass with exactly 1 clean dimension (boundary pass); security_id asc |
| B03_S03_DEFER_RISK | BOUNDARY_PASS_FAIL | 1 | 1 | S03 wide_defer RISK_WATCH (RH-only, no SG); security_id asc |
| B04_S04_MIN2_PASS | BOUNDARY_PASS_FAIL | 2 | 2 | S04 L2 candidate with exactly 2 reachable = 2 qualified dimensions (minimum pass); security_id asc |
| B05_S04_ONE_DIM_FAIL | BOUNDARY_PASS_FAIL | 2 | 1 | S04 L2 candidate with 3 reachable / 2 qualified (only one dimension short); security_id asc |
| B06_S04_ABS_SG06 | BOUNDARY_PASS_FAIL | 2 | 2 | S04 L2 candidate depending on SG06 absolute-amount channel; security_id asc |
| B07_S04_LOWBASE_CONFIRMED | BOUNDARY_PASS_FAIL | 2 | 2 | S04 L2 candidate carrying C_LOW_BASE_CONFIRMED signal; security_id asc |
| B08_RH01_NEAR | BOUNDARY_PASS_FAIL | 1 | 1 | S05 RH01 nearest-not-triggered below/at threshold (distance, security_id asc) |
| B08_RH02_NEAR | BOUNDARY_PASS_FAIL | 1 | 1 | S05 RH02 nearest-not-triggered below/at threshold (distance, security_id asc) |
| B08_RH03_NEAR | BOUNDARY_PASS_FAIL | 1 | 1 | S05 RH03 nearest-not-triggered below/at threshold (distance, security_id asc) |
| B08_RH04_NEAR | BOUNDARY_PASS_FAIL | 1 | 1 | S05 RH04 nearest-not-triggered below/at threshold (distance, security_id asc) |
| B08_RH05_NEAR | BOUNDARY_PASS_FAIL | 1 | 1 | S05 RH05 nearest-not-triggered below/at threshold (distance, security_id asc) |
| B09_RH06_TRIGGER | BOUNDARY_PASS_FAIL | 1 | 1 | S05 QUALITY_PASS with RH06 (one-off) triggered; security_id asc |
| B08_RH_TRIGGERED_NEAR | BOUNDARY_PASS_FAIL | 2 | 2 | S05 RH04/RH05 nearest-triggered above/below threshold (distance, rh, security_id asc) |
| B10_OUT_OF_VALID_RANGE | BOUNDARY_PASS_FAIL | 4 | 4 | S05 out-of-valid-range representatives: M08-H1, M08-9M, M12, M10; first distinct company by file order |
| J01_BJ_PASS_H1 | BJ_MARKET | 2 | 2 | BJ S05 QUALITY_PASS anchored 2026H1; security_id asc |
| J02_BJ_PASS_9M | BJ_MARKET | 2 | 2 | BJ S05 QUALITY_PASS anchored 2026Q3; security_id asc |
| J03_BJ_S04_CAND_NOT_PASS | BJ_MARKET | 2 | 1 | BJ S04 L2 candidate outside frozen S05 278; security_id asc |
| J04_BJ_RISK_OR_NO_SIGNAL | BJ_MARKET | 1 | 1 | BJ S03 RISK_WATCH / NO_SIGNAL; security_id asc |
| J05_BJ_MISSING_WATCH | BJ_MARKET | 1 | 1 | BJ on S06 missing-data watch; security_id asc |
| L01_LOSS_M05_UNDEFINED | LOSS_AND_LOW_BASE | 3 | 3 | M05 UNDEFINED_BASE (loss / negative base); security_id asc |
| L02_M07_UNDEFINED_BASE | LOSS_AND_LOW_BASE | 2 | 2 | M07 UNDEFINED_BASE (single-quarter negative base); security_id asc |
| L03_LOWBASE_PROVISIONAL | LOSS_AND_LOW_BASE | 2 | 2 | S03 OQ_LOW_BASE_PROVISIONAL; security_id asc |
| L04_LOWBASE_CONFIRMED_EXTRA | LOSS_AND_LOW_BASE | 1 | 1 | S04 C_LOW_BASE_CONFIRMED not already sampled; security_id asc |
| M01_AFTER_CUTOFF | MISSING_DATA_WATCH | 4 | 4 | All 4 after-cutoff isolated companies (guard preserved); security_id asc |
| M02_ANCHOR_PENDING | MISSING_DATA_WATCH | 1 | 1 | Anchor reselection pending company; security_id asc |
| M03_QUALITY_HOLD_JIDONG | MISSING_DATA_WATCH | 1 | 1 | S05 QUALITY_HOLD consolidation-scope unknown (Jidong); security_id asc |
| M04_QUALITY_SOURCE_UNKNOWN | MISSING_DATA_WATCH | 1 | 1 | Non-mainline quality source unknown; security_id asc |
| M05_HOLD_AND_QUALITY_UNKNOWN | MISSING_DATA_WATCH | 1 | 1 | S04 HOLD_FOR_DATA + quality source unknown; security_id asc |
| M06_S04_HOLD_FOR_DATA | MISSING_DATA_WATCH | 3 | 3 | S04 HOLD_FOR_DATA prioritised by S02 HOLD > UNDEFINED_BASE > MISSING, then security_id |
| M07_S02_HOLD_OR_MISSING | MISSING_DATA_WATCH | 3 | 3 | S02 metric HOLD/MISSING non-mainline prioritised by HOLD > MISSING, then security_id |
| E01_EARLY_RD | EARLY_STAGE_WATCH | 2 | 2 | S06 early-stage bucket EARLY_RD_PROTOTYPE_SAMPLING; security_id asc |
| E02_EARLY_PILOT | EARLY_STAGE_WATCH | 1 | 1 | S06 early-stage bucket EARLY_PILOT_SMALL_BATCH; security_id asc |
| E03_EVIDENCED_UNKNOWN | EARLY_STAGE_WATCH | 2 | 2 | S06 early-stage bucket EVIDENCED_PRODUCT_STAGE_UNKNOWN; security_id asc |
| E04_COMMERCIAL_RESERVE | EARLY_STAGE_WATCH | 1 | 1 | S06 early-stage bucket COMMERCIAL_NON_MAINLINE_RESERVE; security_id asc |
| R01_NOT_IN_SCOPE | REVERSE_OMISSION | 2 | 2 | Strong robot exposure, S04 L2_NOT_IN_SCOPE, not in S05 277; security_id asc |
| R02_HOLD_FOR_DATA | REVERSE_OMISSION | 2 | 2 | Strong robot exposure, reviewed HOLD_FOR_DATA, not in S05 277; prefer baseline candidate then security_id |
| R03_NOT_SHORTLISTED | REVERSE_OMISSION | 1 | 1 | Strong robot exposure, reviewed NOT_SHORTLISTED, not in S05 277; security_id asc |

### 1.2 独立复算口径

以 `s00_v10.csv.gz` 原始标准化数值为唯一算术底座，独立重算 M01–M12（营收/扣非同比、毛利率变动、现金含量、应收/存货天数、合同资产占比等），不读取 S02 的中间结果反推。锚定期间由锚定字段（`FIN.REV.YTD` / `FIN.REV.SQ` / `FIN.NPDEDT.YTD`）在 usable 状态下的最新 `period_key` 独立推导，再与 `all_pool_metrics.csv` 的 `period_key` 比对。

逐格比对结果：**744 格**（62 家 × 12 指标），状态一致 **744**，数值一致 **744**；最大绝对差 `4.977e-11`（浮点容差 `5.0e-10`，即 S02 固定 10 位小数的舍入量级）。锚定期间独立推导不一致 **0** 家。

全部样本均达到 `EXACT`：状态与数值逐格一致，无需按口径/重述/合并范围/锚定期做差异归因。

## 2. 路由复算与边界核对

- S03 L1：由复算指标重新触发 SG01–SG09、重算四维与 bucket/subtag，**57 家 CONSISTENT**，5 家为底稿/截止日 `FROZEN_OVERRIDE`，不一致 **0** 家。
- S04 L2：维度计数与 `qualified_dims` 内部一致 **62 家**，不一致 **0** 家；对 `B_ABS_CHANNEL` 与 `C_LOW_BASE_CONFIRMED` 另做输入级复核（见 2.1、2.2）。
- S05 质量闸门：样本中进入 S05 278 的 **21 家**，RH01–RH05 阈值判定与 `quality_flags.csv` 一致 **21 家**，不一致 **0** 家；RH06 的 `one_off` 标记与 Q09 复算一致。
- S06 观察名单：样本中进入缺失观察的 **30 家**，`s02_hold/missing/undefined_base/provisional/not_comparable` 五项计数与 S02 状态逐家一致 **30 家**，不一致 **0** 家。

### 2.1 绝对额通道 `B_ABS_CHANNEL`

全池 S04 中共 **104 家**登记绝对额通道。对样本内每家逐一回查 `s00_v10`：SG06 的 `FIN.NPDEDT.YTD`、SG08 的 `FIN.OCF.YTD` 在 t 与 t−1y 两侧均为 usable 状态、有金额、同期间可比。样本内未发现“比率通道 UNDEFINED_BASE 导致绝对额通道失效”的情况，也未发现沿用上游 CLEAN 标签直接放行。

### 2.2 低基数确认 `C_LOW_BASE_CONFIRMED`

全池 S04 中共 **40 家**登记低基数确认。按冻结映射（SG01/SG04/SG06/SG08 用 YTD、SG09 用 SQ）回查同口径绝对额增量，样本内全部满足 **增量 ≥ 1,000 万元且方向为正**；未发现用任意金额替代、跨期相减或把未确认低基数信号计入维度。S03 中仅低基数信号的 `OQ_LOW_BASE_PROVISIONAL` 共 **11 家**，带低基数命中标记的公司 **94 家**。

## 3. 偏差诊断

### 3.1 缺失数据偏差

S06 `missing_data_watch.csv` 共 **379 家**，7 个细分类型全部覆盖：

| 类型 | 数量 |
|---|---:|
| AFTER_CUTOFF_ISOLATED | 4 |
| PENDING_ANCHOR_RESELECTION | 1 |
| QUALITY_SOURCE_UNKNOWN_NON_MAINLINE | 6 |
| S02_METRIC_HOLD_OR_MISSING_NON_MAINLINE | 39 |
| S04_HOLD_FOR_DATA | 319 |
| S04_HOLD_FOR_DATA_AND_QUALITY_SOURCE_UNKNOWN | 9 |
| S05_QUALITY_HOLD_CONSOLIDATION_SCOPE_UNKNOWN | 1 |

观察名单内按公司计：HOLD 集中于 M01=32，M04=32，M09=32，M10=32；MISSING 集中于 M04=26，M08=13，M03=8；UNDEFINED_BASE 集中于 M05=76，M07=76。

**结论**：HOLD/MISSING 覆盖 M01（营收同比）、M04（毛利率）、M09（经营现金流变动）、M10（应收天数）与 M08（现金含量），UNDEFINED_BASE 集中于 M05/M07（扣非同比）。因此缺失数据的影响不只在 CASH：它会同时压低 GROWTH / MARGIN / PROFIT / CASH 四个维度的可评估证据。冻结规则要求 HOLD 既不计改善也不计恶化，所以偏差方向是**双向保守**——既可能漏掉真实改善，也不会把缺失误判成恶化。缺失一律保持 `MISSING/HOLD/UNKNOWN`，未填 0、未插补、未因缺失淘汰；S06 五项计数与 S02 状态逐家一致，说明观察名单没有把“缺数据”写成“无业务”。该偏差属于已知受限，不是系统性阻断。

### 3.2 混合报告期偏差（H1 vs 9M）

S05 冻结 278 家 = **H1 锚点 200 家 + 9M 锚点 78 家**。同比在同一 `period_type` 内配对，因此期间长度不直接污染同比；但横截面触发率不能直接相加比较。

| RH | H1 可判/触发/触发率 | 9M 可判/触发/触发率 |
|---|---|---|
| RH01 | 200/11/5.5% | 77/2/2.6% |
| RH02 | 80/13/16.2% | 38/8/21.1% |
| RH03 | 95/7/7.4% | 38/0/0.0% |
| RH04 | 168/77/45.8% | 72/32/44.4% |
| RH05 | 200/36/18.0% | 74/8/10.8% |

`out_of_valid_range` 20 格按锚点分布：{'20260630': 15, '20260930': 5}；按指标：{'M08': 15, 'M10': 4, 'M12': 1}。H1 与 9M 的越界比例接近，未见某一锚点系统性越界。

**结论**：混合锚点影响的是**横截面可比性与解释口径**，不影响同比计算本身；S05 已把锚点分列并保留 Q11 冻结标记。结转 S08 时须继续按锚点分层陈述，不得把 278 家当作同一报告期。

### 3.3 低基数 / 亏损 / 无定义基数偏差

全池 M05 `UNDEFINED_BASE` **242 格**、M07 **252 格**（基期为负或近零）。冻结规则对这些格不计算比率，改判绝对额改善或转正；SG06 还要求当期扣非 ≥ 1,000 万元，防止微利转正。复算未发现对负基数强行计算同比、或用归母替代扣非。

低基数信号在 L1 单列为 `OQ_LOW_BASE_PROVISIONAL`，L2 必须有同口径绝对额确认才计入维度。样本复核显示确认门槛被严格执行；无确认规则的 SG02/SG03/SG05/SG07 保持 `NO_CONFIRM_RULE`，未折算成维度。**偏差方向**：低基数公司更容易在增长率上“看起来很好”，当前规则用绝对额确认抑制了该放大效应；仍可能有少量真实改善因确认门槛被推迟，属于保守侧偏差。

### 3.4 项目模式 RH02 豁免

S05 RH02 状态：{'PENDING_APPLICABILITY': 127, 'TRIGGERED': 21, 'NOT_APPLICABLE': 31, 'NOT_TRIGGERED': 97, 'PENDING_HOLD': 2}。项目制公司按 Q10 规则不判存货天数，故 RH02 记 `NOT_APPLICABLE`，但这不影响应收天数（RH01）与合同资产占比（RH03）。**影响**：项目制公司的存货风险信号被规则性关闭，不能解读为“无存货风险”；S05 已把该豁免逐家登记，S08 应继续以应收/合同资产为主观察。

### 3.5 北交所披露差异

全池 BJ **62 家**（H1 锚点 57、9M 锚点 5），S05 通过 **25 家（40.3%）**；非 BJ 通过 252/992（25.4%）。BJ 进入缺失观察 **11 家**，非 BJ **368 家**。BJ 的 M12 无合同资产科目 **35 家**。

**结论**：BJ 通过率高于非 BJ，但样本内 BJ 的低基数确认占比也更高（3/25），且 BJ 全部为 EVALUABLE、缺失观察占比更低。现有证据不足以把差异归因于“披露更宽松”或“计算偏差”；更可能是行业结构与基数效应。该差异**不构成系统性阻断**，但 S08 不应把 BJ 与非 BJ 的通过率直接对比。

### 3.6 反向漏筛检验

以 `robot_exposure ∈ DIRECT_DISCLOSED / DIRECT_UNDISCLOSED / INDIRECT_VERIFIED` 定义“已有较强机器人业务线索”，全池 **45 家**，其中 **9 家**进入 S05 277 主线，**36 家**未进入。未进入者的 S04 基线判定：{'L2_NOT_IN_SCOPE': 12, 'L2_NOT_SHORTLISTED': 11, 'L2_SHORTLIST_CANDIDATE': 12, 'WATCH_AFTER_CUTOFF': 1}；S06 冻结复核判定：{'L2_NOT_IN_SCOPE': 12, 'HOLD_FOR_DATA': 19, 'NOT_SHORTLISTED': 4, 'WATCH_AFTER_CUTOFF': 1}。

抽样 5 家的判定分布：{'RULE_CONSISTENT_SCOPE': 2, 'RULE_CONSISTENT_HOLD_FOR_DATA': 2, 'RULE_CONSISTENT_DIMS_LT2': 1}；计算/口径漏筛 **0** 家。

**结论**：未进入主线的强线索公司均为规则性结果——`L2_NOT_IN_SCOPE`（L1 未进观察队列）、`HOLD_FOR_DATA`（S05 适用性复核后有效维度不足 2，保留重进）、`NOT_SHORTLISTED`（有效维度不足 2）或 `WATCH_AFTER_CUTOFF`（截止日隔离）。复算未发现“指标算错导致被排除”的案例，也未手工加回任何公司。

### 3.7 S04 基线与 S05 冻结池的口径差

`runs/issues/S04/tight_decision_log.csv`（Git 跟踪的基线）登记 `L2_SHORTLIST_CANDIDATE` **445 家**，S05 冻结质量池为 **278 家**，差 **167 家**；S05 池是 S04 候选的子集：**是**。

S05 的 `decision_reason` 对这部分的解释是“剩余有效维度不足 2；命中精确待核输入/上游 HOLD/暂定维度可能补足，暂不降为不通过”，S06 `early_stage_watch.csv` 的 `s04_l2_decision` 也把相关公司记为 `HOLD_FOR_DATA`。因此这是 **S04 基线日志 → S05 适用性复核** 的版本口径差，不是算术漏筛；但 Git 树内缺少 S04 复核版 `tight_pass`（`reviewed_view` 未跟踪），导致 445→278 的逐家映射不可在干净树内完全重放。该可追溯性缺口应结转 S08/资料治理，不阻断 S07 结论。

### 3.8 有效区间与 RH06 待核

`s05_out_of_valid_range.csv` 的 20 格状态均为 `OK` 但数值越出冻结 `valid_range`。冻结规则没有给越界处置动作，S05 只登记、不阻断、不改值。样本复核确认这些值确实越界，且未被用于改写路由。**定级**：规则版本缺口（S01 v4 未定义 `valid_range` 处置），结转 S08；不是计算错误。

RH06 采用台账：{'QUALIFIED_NOT_TRIGGERED': 234, 'QUALIFIED_TRIGGERED': 37, 'PENDING_INPUT_GAP': 6, 'PENDING_EXISTING_HINT': 1}，未采用 **7 家**（缺 NPP 或开放争议）。未发现把未解决争议当作已采用输入。

## 4. 定级与放行判定

| 编号 | 发现 | 归因层 | 定级 | 处置 |
|---|---|---|---|---|
| F01 | 样本 12 项指标逐格复算与 S02 完全一致（状态+数值） | S02 计算 | INFO | 无需处置 |
| F02 | S03 L1 信号/维度/bucket 可由复算指标完整重放 | S03 规则 | INFO | 无需处置 |
| F03 | S04 维度计数、绝对额通道、低基数确认边界成立 | S04 规则 | INFO | 无需处置 |
| F04 | 缺失保持未知、未填 0；S06 五项计数与 S02 一致 | S02/S06 | INFO | 继续按未知处理 |
| F05 | H1/9M 混合锚点影响横截面解释，不影响同比 | S02/S05 | LOW | S08 按锚点分层 |
| F06 | 项目模式 RH02 豁免使存货风险信号规则性关闭 | S05 规则 | LOW | S08 以应收/合同资产为主 |
| F07 | 低基数确认抑制增长率放大，可能保守推迟真实改善 | S01/S04 | LOW | 保持冻结阈值，不回调 |
| F08 | BJ 通过率高于非 BJ，但证据不足以归因披露差异 | 数据/结构 | LOW | 不做跨市场通过率对比 |
| F09 | 强线索未进主线均为规则性排除/待核，无计算漏筛 | S04/S05/S06 | INFO | 保留观察与重进 |
| F10 | S04 基线 445 候选 vs S05 冻结 278，复核版映射不可在干净树重放 | S04/S05 版本 | MEDIUM | 结转 S08 资料治理 |
| F11 | 20 格越界值状态 OK，冻结规则无处置动作 | S01 规则 | LOW | 结转 S08 定义处置 |
| F12 | RH06 7 家待核（缺 NPP / 开放争议），未强行采用 | S05 规则 | LOW | 保持待核 |
| F13 | 4 家截止日隔离、1 家锚点待重选、冀东 QUALITY_HOLD、#53 开放均保留 | 守卫 | INFO | 原样结转 |

**系统性阻断判定：不存在 `SYSTEMIC_BLOCKER`。** 样本内 12 项指标的状态与数值、S03 信号与维度、S04 边界属性、S05 RH 阈值、S06 计数均可由 `s00_v10` 与冻结规则独立重放；没有发现需要回退 S00/S01 重算的系统性口径错误。

**可结转 S08 的已知受限**：F05 混合锚点、F06 RH02 项目模式豁免、F07 低基数保守偏差、F08 BJ 结构差异、F10 S04→S05 版本映射缺口、F11 越界处置未定义、F12 RH06 待核。上述限制均已在 S05/S06 冻结件中登记，S08 不得把它们当作已解决。

## 5. 守卫与边界

- 截止日后隔离 **4 家**、锚点待重选 **1 家**、质量来源未知 **15 家** 均保留；冀东装备 `SZ:000856` `QUALITY_HOLD` 保留 = **是**；`#53` 状态 **OPEN**。
- 未修改任何冻结阈值、未修改 `runs/issues/S07/` 以外文件、未执行 git commit/push、未释放 S08、未改 `#53`。
- 本报告为执行方自检（SELF_CHECK），不等同独立验收；须由 Codex 独立复核后再登记 S07 验收。

