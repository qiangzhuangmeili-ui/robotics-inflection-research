# S01 实现细则（R3，2026-10-29 第三轮）

本文件记录「冻结规则 → 可执行代码」的映射，供复核方逐条对照。
规则版本：**`screen_rules_v2.json`**（v1 原文件保留不改，sha256 `c76d0461…`；v1→v2 只改 SG02 单位，见 `erratum_sg02_unit_20261029.md`）。

**R3 相对 R2 的三处修正**（对应 Codex 复验 `522e1cd`）：

1. **信号质量并集**：每个信号声明全部依赖指标（`SIGNAL_DEPS`），`SG07 = M08 ∪ M09`、`SG08 = M09`、`SG06 = M05`；
   信号的 `flags` 由依赖指标重新合并，**L2 判定也从原始指标重取标记**，不读信号自报的 flags。
   新增不变量核验：`signal_flags_missing_dep` 必须为 0。
2. **M08 传播低基数**：`m08` 读原始 OCF / 归母输入的 `low_base_flag` 并加 Q05；M08 无绝对额口径，低基数一律 `NO_CONFIRM_INPUT`。
3. **UNKNOWN 口径**：非旧快照必须明确 `CONSOLIDATED`，`UNKNOWN` 只在 `LEGACY_SNAPSHOT` 行放行（记 Q07）。
4. **SG02 单位**：阈值改为 5.0 pp（v2），代码不再写死阈值，改为**从规则文件读取**，避免再出现单位漂移。

---

## 一、状态枚举与优先级

| 状态 | 含义 | 是否可参与 L1 | 是否可贡献 L2 |
|---|---|---|---|
| `OK` | 可计算且无未决质量问题 | 是 | 是 |
| `PROVISIONAL` | 值可算，但输入含已确认/未决重述（Q06） | 是 | **否** |
| `HOLD` | 输入含 xcheck 不一致等 HOLD | 否（也不算恶化） | 否 |
| `MISSING` | 必需输入行不存在 | 否 | 否 |
| `NOT_COMPARABLE` | 上市前 / 无上年同期（Q08） | 否 | 否 |
| `UNDEFINED_BASE` | 分母或基期非正（Q03/Q04） | 否 | 否 |
| `NOT_APPLICABLE` | 口径上不适用（归母≤0 的现金含量、项目制的存货天数、无合同资产） | 否 | 否 |
| `EXCLUDED_SCOPE` | 非合并口径（Q12） | 否 | 否 |
| `VERSION_MISMATCH` | 回算时 REV/COST 不同文档或不同版本 | 否 | 否 |

判定优先级：`MISSING > HOLD > MISSING(未知状态) > EXCLUDED_SCOPE > NOT_COMPARABLE > OK`。
Q06 在数值算完之后把 `OK` 降为 `PROVISIONAL`——值保留、可观察，但不得当正常样本。

---

## 二、四个阻断的落地

### B1 Q06 不得进 L2

- **触发口径**（比原先更严）：`restatement_flag = 是`、`= RESTATEMENT_INDICATED_NEEDS_REVIEW`，
  或 `comparability_note` 含 `RESTATED_PRIOR_YEARS_UNRECALCULATED`。
  「是」也计入，因为 S00 已声明历史期未按最新年报上年同期重算，跨期比较是混合口径。
- **L1**：`PROVISIONAL` 信号照常进观察队列。
- **L2**：`eligible = fired 且无 Q06 且已确认`；维度只从 eligible 取。
- **SG06（扣非转正）/SG08（现金流转正）**：单独分支，同样把输入的重述标记并入 `flags`，
  不再绕过质量判定。
- **事后核验**（非重言式）：对每个判为 `SHORTLIST_CANDIDATE` 的公司，重新检查「支撑它的干净维度是否 ≥2」，
  不足即记 `l2_without_two_clean_dims`，要求为 0。

### B2 低基数按绝对额确认

| 指标 | 能否提供绝对额确认 | 依据 |
|---|---|---|
| M01 营收同比（累计） | 能 | `REV.YTD(t) − REV.YTD(t−1y) ≥ 1,000 万` |
| M02 营收同比（单季） | 能 | 同上（单季口径） |
| M05 扣非同比（累计） | 能 | `NPDEDT.YTD(t) − NPDEDT.YTD(t−1y) ≥ 1,000 万` |
| M07 扣非同比（单季） | 能 | 同上（单季口径） |
| M09 现金流变动额 | 能 | 该指标本身就是绝对额，`≥ 1,000 万` |
| M03 单季加速 | **不能** | 百分点差的绝对额含义不唯一 → `NO_CONFIRM_INPUT` |
| M04 毛利率 pp | **不能** | 同上 |
| M06 扣非净利率 pp | **不能** | 同上 |
| M08 现金含量 | **不能** | 无量纲比率 |

- 低基数且能确认 → 记 `CONFIRMED_ABS`，可贡献 L2 维度；
- 低基数且增量不足 → `ABS_BELOW_THRESHOLD`，只进 L1；
- 低基数但指标无绝对额口径 → `NO_CONFIRM_INPUT`，只进 L1。
- 三类分别计数（`q05_confirmed` / `q05_unconfirmed` / `q05_no_confirm_input`），不再用「一律排除」代替政策。

### B3 质量与可比性边界

| 规则 | 实现位置 | 行为 |
|---|---|---|
| Q06 已确认重述 | `_restate()` + `evaluate()` 末段 | 状态降为 `PROVISIONAL` |
| Q08 上市前 | `_inputs()` | `is_pre_listing=YES` → `NOT_COMPARABLE` |
| Q12 非合并口径 | `_inputs()` | `scope ∈ {PARENT_ONLY, NON_CONSOLIDATED}` → `EXCLUDED_SCOPE`；`LEGACY_SNAPSHOT` 的 UNKNOWN 只计 Q07 |
| Q10 项目制 | `project_mode()` | 合同资产/资产 >5% 或 /营收 >10% → M11 置 `NOT_APPLICABLE` |
| Q11 陈旧期 | 主循环 | 最新期 < 全池最新期前一个季度 → 全指标加 Q11 |
| M04 回算同版本 | `m04()` | 回算前比对 REV 与 COST 的 `document_id` 与 `version_used`，不一致 → `VERSION_MISMATCH` |
| 期间元数据 | `load_rows()` | 改为**逐字段**存 `period_start/period_end`，天数取流量字段自己的期间（修掉 2025H1 共享到 Q2 元数据的隐患） |

### B4 毛利率百分点差分

- `M04 = PCT(t) − PCT(t−1y)`，**不以基期毛利率作分母**，基期 0% 与负毛利率都合法；
- 只有「PCT 缺失 → 用 REV/COST 回算」这一条路径才检查营收分母与版本一致性。

---

## 三、合成测试（21 项，全部 PASS）

| 用例 | 断言 |
|---|---|
| T1 | 毛利率 0%→1% = +1.0pp / OK |
| T2 | 毛利率 −5%→−2% = +3.0pp / OK |
| T3 | 营收基期 0 → UNDEFINED_BASE + Q04 |
| T4 | 扣非基期 −1,000 万 → UNDEFINED_BASE + Q03 |
| T5 | 低基数 + 增量 4,224 万 → SG01 确认（CONFIRMED_ABS） |
| T6 | 低基数 + 增量 900 万 → 不确认（ABS_BELOW_THRESHOLD） |
| T7 | Q06 信号进 L1、不进 L2 |
| T8 | 现金含量 1.0 但现金流同比为负 → SG07 不触发 |
| T9 | 已确认重述（是）→ 标 Q06，状态降级 |
| T10 | 上市前 → NOT_COMPARABLE + Q08 |
| T11 | 母公司口径 → EXCLUDED_SCOPE + Q12 |
| T12 | 合同资产占比 >5% → 项目制，M11 不判（Q10） |
| T13 | 最新期落后 → 全指标 Q11 |
| T14 | 回算毛利率 REV/COST 不同文档 → VERSION_MISMATCH |
| T15 | 扣非由负转正且 ≥1,000 万 → SG06 触发 |
| T16 | Q06 增长 + 干净毛利 → 只剩 1 维，不得进 L2（flip=1） |
| T17 | 非旧快照 `scope=UNKNOWN` → EXCLUDED_SCOPE + Q12 |
| T17b | 旧快照 `scope=UNKNOWN` → OK + Q07（单列例外） |
| T18 | M08 干净但 M09 带 Q06 → SG07 继承 Q06、不进 L2 |
| T19 | M08 原始输入带低基数 → Q05 + NO_CONFIRM_INPUT |
| T20 | SG02 阈值 5pp：1pp 不触发、6pp 触发 |

## 三之二、干跑对比（v1 → v2，匿名计数）

---

## 四、干跑变化（匿名计数，非名单）

| 项 | 首版 v1 | R2 | **R3（v2）** | 说明 |
|---|---|---|---|---|
| L2 收紧 | 496 | 290 | **281** | Q06 排除 −209；Q05 绝对额确认 +43 信号部分抵消；SG02 单位修正 −9 |
| L1 观察队列 | 867 | 867 | **841** | SG02 由 0.05pp 改 5pp 后减少 26 家 |
| SG02 命中 | 522 | 522 | **415** | 107 条低于 5pp 的误触发被剔除 |
| 指标 OK（M01） | 951 | 565 OK + 386 PROVISIONAL | 同 R2 | 把「可算但不可比」单独拆出 |

R3 违例计数：`ok_with_q06` **0**、`ok_with_q12` **0**、`l2_without_two_clean_dims` **0**、
`signal_flags_missing_dep` **0**、`q06_dimension_flip` 202、`q06_signal_fired` 836。

复核方按旧实现算出的 170 家（Q06 翻转）与本次 202 家的差异，来自 Q06 口径扩到「已确认重述」与 Q05 确认两项，
不是阈值；SG02 的 −107 是单位修正的算术后果，不是按命中率调门槛。
