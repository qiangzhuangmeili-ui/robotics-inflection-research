# S01 指标公式登记 v1

- 规则版本：`S01_SCREEN_RULES_V1`（机器可读版：`screen_rules_v1.json`）
- 输入：`runs/issues/S00/financial_normalized.csv`（228,155 行，1,054 家，19 个字段）
- 冻结时间：2026-10-29 10:30 (+08)；知识截止 2026-10-25
- 本文件只定义「怎么算」，不定义「谁入选」；阈值与理由见 `threshold_rationale.md`
- **先冻结、后运行**：本文件与 JSON 的哈希在 `manifest.json` 中登记，S02 运行时必须核对未变

---

## 〇、通用约定

| 约定 | 规则 |
|---|---|
| 金额 | 一律用 `value_cny`（元）。`value_raw`/`unit_raw` 只作证据，不参与计算 |
| 比率字段 | `FIN.GROSSMARGIN.PCT`、`FIN.NPMARGIN.PCT` 是百分数数值（23.28 表示 23.28%），变动用 **pp** |
| 同比 | 只允许 **同 period_type** 对 **同 period_type**（FY↔FY、H1↔H1、9M↔9M、Q3↔Q3）；`period_key - 10000` 取上年同期 |
| 单季 | 只用 `period_basis=SINGLE_QUARTER` 的 `*.SQ` 字段；不得用累计相减临时造单季（S00 已固定口径） |
| 最新期 | 逐公司取「有可用 `FIN.REV.YTD` 的最大 period_key」。2026Q3 只有 188 家已披露，其余自然回落到 2026H1，**不补、不推** |
| 天数 | `days_in_period = period_end - period_start + 1`，从数据行取，不硬编码 365 |
| 缺失 | 行不存在 = MISSING；**不填 0、不插补、不用同业值** |
| HOLD | 状态属于 `EXTRACTED_XCHECK_MISMATCH` / `DERIVED_HOLD_UPSTREAM` / `DERIVED_Q1_HOLD_UPSTREAM` 的输入，只能产出 HOLD |
| 合并范围 | 只对 `consolidation_scope=CONSOLIDATED` 计算主口径；其他单列 |

### 状态 → 可用性映射

| 类别 | 状态 |
|---|---|
| 可直接用 | `EXTRACTED`、`EXTRACTED_KEY_TABLE`、`EXTRACTED_QUARTERLY_TABLE`、`DERIVED`、`DERIVED_CUMULATIVE_DIFF`、`DERIVED_Q1_EQUALS_YTD`、`DERIVED_QUARTERLY_SUM_OVERRIDE` |
| 可用但降级 | `LEGACY_SNAPSHOT`（旧快照 2021/2022，单一来源，标 `SINGLE_SOURCE`） |
| HOLD | `EXTRACTED_XCHECK_MISMATCH`、`DERIVED_HOLD_UPSTREAM`、`DERIVED_Q1_HOLD_UPSTREAM` |
| 缺失 | 行不存在（S00 只写有值行） |

**指标状态枚举（计算结果的状态，不是输入状态）**：`OK`、`PROVISIONAL`（值可算但含 Q06 重述，可进 L1、不进 L2）、
`HOLD`、`MISSING`、`NOT_COMPARABLE`、`UNDEFINED_BASE`、`NOT_APPLICABLE`、`EXCLUDED_SCOPE`、`VERSION_MISMATCH`。
逐条映射见 `implementation_notes.md`。

### 质量标记（每条指标都要判）

| 标记 | 触发 | 后果 |
|---|---|---|
| `Q01 HOLD_UPSTREAM` | 任一必需输入 HOLD | 指标 HOLD，不参与任何改善判断 |
| `Q02 MISSING_INPUT` | 必需输入行缺失 | 指标 MISSING，不填 0 |
| `Q03 NEGATIVE_BASE` | 分母或基期 < 0 | 比率不算，改绝对额 |
| `Q04 ZERO_BASE` | 分母/基期绝对值 < 100 万元 | 比率不算 |
| `Q05 LOW_BASE` | `low_base_flag` ∈ {`LOW_BASE_REV`,`LOW_BASE_PROFIT`,`NEGATIVE_BASE_PROFIT`} 或基期营收 < 5,000 万 或 \|基期扣非\| < 1,000 万 | 信号标 PROVISIONAL |
| `Q06 RESTATEMENT_UNRESOLVED` | 任一侧 `restatement_flag=是` 或 `=RESTATEMENT_INDICATED_NEEDS_REVIEW`，或 `comparability_note` 含 `RESTATED_PRIOR_YEARS_UNRECALCULATED` | 指标降为 PROVISIONAL，不进 L2 |
| `Q07 LEGACY_SINGLE_SOURCE` | 任一侧 `LEGACY_SNAPSHOT` | 标 SINGLE_SOURCE，L2 只作辅助 |
| `Q08 PRE_LISTING_OR_NO_HISTORY` | `is_pre_listing=YES` 或上年同期缺失 | NOT_COMPARABLE |
| `Q09 ONE_OFF_DOMINATED` | \|归母−扣非\|/max(\|归母\|,1) > 50% | 盈利信号改用扣非 |
| `Q10 PROJECT_MODE` | 合同资产/资产 > 5% 或 合同资产/营收 > 10% | 存货天数不作判断 |
| `Q11 STALE_PERIOD` | 最新期落后全池最新期 ≥ 1 个季度 | 横截面分层 |
| `Q12 NON_CONSOLIDATED` | `consolidation_scope=UNKNOWN` 且非 `LEGACY_SNAPSHOT`，或明确为母公司口径 | 不进主筛选（旧快照只计 Q07） |

---

## 一、指标清单（12 条）

### M01 营业收入同比（累计）

```
REV_YOY_YTD = FIN.REV.YTD(t) / FIN.REV.YTD(t-1y) - 1
```
- 输入：`FIN.REV.YTD` @ t、t-1y，同为 `YTD_CUMULATIVE`
- 单位：倍（0.12 = +12%）；方向：越高越好；有效区间 [-1, 20]
- 缺失/HOLD：MISSING / HOLD，值留空
- 基期为负或为零：不算比率，输出绝对额差 `REV.YTD(t) − REV.YTD(t−1y)`

### M02 营业收入同比（单季）

```
REV_YOY_SQ = FIN.REV.SQ(t) / FIN.REV.SQ(t-4q) - 1
```
- t-4q = 同一季度序号的上一年（Q3 2026 ↔ Q3 2025）
- 不得用「今年 9M − 今年 H1」临时造单季来替代

### M03 单季营收同比加速度

```
REV_ACCEL_SQ = REV_YOY_SQ(t) - REV_YOY_SQ(t-1q)         单位 pp
```
- 需要 t、t−1q 两个连续单季各自的上年同期，共 4 个值
- 任一缺 → MISSING（**不用相邻季度顶替**）

### M04 毛利率同比变动

```
GM(t) = FIN.GROSSMARGIN.PCT(t)                                   # 优先
GM(t) = (FIN.REV.YTD - FIN.COST.YTD) / FIN.REV.YTD * 100          # 仅当 PCT 缺失且 REV、COST 同期同版本
GM_PP = GM(t) - GM(t-1y)                                          单位 pp
```
- 回算时必须 REV、COST 同一 document_id / 同一 `version_used`，禁止跨版本拼
- PCT 为 `DERIVED_HOLD_UPSTREAM` 时整条指标 HOLD（不因为能回算就绕过）

### M05 扣非归母净利润同比（累计）

```
NPDEDT_YOY_YTD = FIN.NPDEDT.YTD(t) / FIN.NPDEDT.YTD(t-1y) - 1     # 仅基期 > 0
```
- 基期 ≤ 0：不算同比，改判 `TURN_POSITIVE`（基期<0 且当期>0 且当期 ≥ 1,000 万）或绝对额改善
- 扣非缺失时**不得**用归母净利润替代

### M06 扣非归母净利率变动

```
NPDEDT_MARGIN(t) = FIN.NPDEDT.YTD(t) / FIN.REV.YTD(t) * 100
NPDEDT_MARGIN_PP = NPDEDT_MARGIN(t) - NPDEDT_MARGIN(t-1y)         单位 pp
```
- 扣非为负是有效值（负利润率），只有**营收**非正才不计算

### M07 扣非归母净利润同比（单季）

```
NPDEDT_YOY_SQ = FIN.NPDEDT.SQ(t) / FIN.NPDEDT.SQ(t-4q) - 1        # 仅基期 > 0
```

### M08 经营现金流 / 归母净利润

```
OCF_TO_NP = FIN.OCF.YTD(t) / FIN.NPP.YTD(t)                       # 仅归母 > 0
```
- 归母 ≤ 0 时本指标不适用，改看 M09 绝对额与转正
- OCF 缺失时不得用净利润、营业利润或「经营现金流估算」替代

### M09 经营现金流同比变动额

```
OCF_CHG_YTD = FIN.OCF.YTD(t) - FIN.OCF.YTD(t-1y)                  单位 元
```

### M10 应收账款周转天数变动

```
AR_DAYS(t)     = FIN.AR.INSTANT(t) / FIN.REV.YTD(t) * days_in_period(t)      # 期末余额法
AR_DAYS_CHG    = AR_DAYS(t) - AR_DAYS(t-1y)                                  单位 天
```
- 用**期末余额**而非平均余额：平均法需要 t−2y 期末数，会与 2021/2022 旧快照单一来源叠加，造成系统性缺值；同比差分已部分抵消季节性
- 应收 = `FIN.AR.INSTANT`（应收账款）；应收票据 `FIN.NR.INSTANT` 单列，不并入主口径
- 应收缺失不假设为 0

### M11 存货周转天数变动

```
INV_DAYS(t)  = FIN.INV.INSTANT(t) / FIN.COST.YTD(t) * days_in_period(t)      # 期末余额法
INV_DAYS_CHG = INV_DAYS(t) - INV_DAYS(t-1y)                                  单位 天
```
- 项目制公司（Q10）不判本指标；无存货科目记 `NOT_IN_STATEMENT`，不填 0

### M12 合同资产占营收比重变动

```
CA_RATIO(t)     = FIN.CONTRACTASSET.INSTANT(t) / FIN.REV.YTD(t) * 100
CA_RATIO_CHG    = CA_RATIO(t) - CA_RATIO(t-1y)                    单位 pp
```
- 方向中性：既是项目制识别依据，也是回款节奏风险提示（RH03）

---

## 二、信号（改善）与风险提示

| 信号 | 定义 | 维度 |
|---|---|---|
| SG01 | M01 ≥ 10% | GROWTH |
| SG02 | M03 ≥ 5pp | GROWTH |
| SG03 | M04 ≥ +1.0pp | MARGIN |
| SG04 | M05 ≥ 20%（基期>0） | PROFIT |
| SG05 | M06 ≥ +1.0pp | PROFIT |
| SG06 | 扣非转正：基期<0、当期>0、当期 ≥ 1,000 万 | PROFIT |
| SG07 | M08 ≥ 0.8 **且** M09 > 0 | CASH |
| SG08 | 现金流转正：OCF(t)>0 且 OCF(t−1y)≤0 | CASH |
| SG09 | M07 ≥ 30%（单季，基期>0） | PROFIT |

| 风险提示 | 定义 |
|---|---|
| RH01 | M10 ≥ +30 天 |
| RH02 | M11 ≥ +30 天（项目制不适用） |
| RH03 | M12 ≥ +5pp |
| RH04 | M08 < 0.5（归母>0 时） |
| RH05 | M04 ≤ −2.0pp |
| RH06 | Q09 一次性损益主导 |

风险提示**不是**改善信号，不参与 L1 的「任一改善」判定，只做标注与 L2 解释要求。

---

## 三、分层判定

| 层 | 规则 | 输出 |
|---|---|---|
| L0 可评估性 | 至少 1 条指标 OK | `EVALUABLE`；否则 `W1_NO_DATA` / `W2_ALL_HOLD` / `W4_EARLY` |
| L1 宽筛 | 任一 SG 为真 | `OBSERVE_QUEUE`；仅 RH → `RISK_WATCH`；都没有 → `NO_SIGNAL` |
| L2 收紧 | GROWTH/MARGIN/PROFIT/CASH 四维中 ≥2 维各有 1 条 SG 为真，且所用指标全 OK、无 Q01/Q05未确认/Q06 | `SHORTLIST_CANDIDATE`；否则 `HOLD_FOR_DATA` / `NOT_SHORTLISTED` |
| L3 质量闸门 | 所用指标均有 document_id + source_page + 非 HOLD | `QUALITY_PASS` / `QUALITY_HOLD` |

**HOLD 语义**：HOLD 既不算改善也不算恶化，只减少可用证据数；因 HOLD 而缺维度时输出 `HOLD_FOR_DATA`，不得写成「未通过」。

---

## 四、观察名单与重进

| 名单 | 含义 | 重进条件 |
|---|---|---|
| W1_NO_DATA | 全部指标缺失（62 个整槽无值为主） | 补采中文版 / OCR 完成后按同规则重算 |
| W2_ALL_HOLD | 全部指标 HOLD | xcheck 复核或重抽解除后重算 |
| W3_LOW_BASE_ONLY | 只有低基数信号 | 出现非低基数信号，或绝对额确认 |
| W4_EARLY | 上市前 / 无上年同期 | 上市满 4 个季度自动重进 |
| W5_PROVISIONAL | 只有 PROVISIONAL 信号 | 重述落定 / 旧快照被官方 PDF 替代 |

---

## 五、执行约束

1. 本文件的任何修改都产生 `screen_rules_v2.json`，并对全池重算；不覆盖 v1、不手工加回公司。
2. 计算脚本必须逐格输出 `metric_status` 与触发的 `quality_flag`，不得只输出最终名单。
3. 任何指标不得使用「行业均值」「同业中位数」做插补；横截面分布只用于事后描述。
4. 公式实现与本文不一致时，以本文 + JSON 为准，实现需改而不是改文档。
