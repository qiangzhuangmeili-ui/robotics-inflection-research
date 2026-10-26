# P04 交接：冻结财务字段、单位、报表与时间口径

- **issue**：#15 / P04，plan_version `20261026_collection_first_v2`
- **执行者/自检者**：WorkBuddy AI（执行与自检同一主体，`review_nature=SELF_CHECK`，不冒充独立审计）
- **起止**：2026-10-26T15:18(+08) 领取 → 2026-10-26T15:4x(+08) 完成
- **输入基线 commit**：`c5ce8b3`（Codex 完成 P03 后的 main）
- **依赖**：P00（#11），`runs/issues/P00/review.json` = `SELF_CHECK_PASS`，放行范围含 P04
- **本卡不做**：不按财务结果筛公司、不采全池、不判断拐点、不估值、不改任何原件

## 一、一句话结论

把"钱怎么算"这件事钉死了：**33 个规范字段、52 条来源映射、1 套期间换算规则、63 条旧快照缺口**，全部带可复算证据。
最重要的一条不是"能取到什么"，而是**取不到什么**——扣非归母净利润在结构化接口里根本不存在，只能回官方 PDF。

## 二、交付

| 文件 | 内容 | 规模 |
|---|---|---|
| `runs/issues/P04/financial_field_dictionary.csv` | 规范字段字典（含单位量纲、期间基础、合并范围、空值语义、阻断条件） | 33 字段 × 20 列 |
| `runs/issues/P04/provider_field_mapping.csv` | 来源字段映射（新浪／官方 PDF／旧快照／派生） | 52 行 × 16 列 |
| `runs/issues/P04/period_conversion_rules.json` | 期间换算、PIT、重述、增速、空值、校验与阻断规则 | 20 个规则块 |
| `runs/issues/P04/legacy_snapshot_gap_register.csv` | 旧快照逐列覆盖 + 缺字段 + 分段缺口 | 63 行 |
| `runs/issues/P04/self_check.json` | 12 项自检，逐项 PASS | 12/12 |
| `runs/issues/P04/evidence_index.json` | 证据文件哈希索引 | 14 个文件 |

证据文件（同目录）：`provider_field_inventory.csv`（新浪 281 个真实字段）、`provider_probe_records.json`（9 次探针）、
`pdf_lineitem_evidence.json`（4 份年报 PDF 的 80 条行项目/页码）、`crosscheck_provider_vs_pdf.json`、
`crosscheck_period_conversion.json`。
生成器：`tools/p04_probe_provider_fields.py`、`tools/p04_extract_pdf_lineitems.py`、`tools/p04_crosscheck_units.py`、
`tools/p04_crosscheck_periods.py`、`tools/p04_freeze_financial_contract.py`、`tools/p04_self_check.py`。

## 三、九条实测发现（每条都能回到文件）

### 1. 结构化接口没有扣非，必须回原文
新浪利润表 77 个字段全量扫过（`provider_field_inventory.csv`），**不存在**"扣除非经常性损益"任何变体。
`provider_field_mapping.csv` 用 `CONFIRMED_ABSENT` 显式登记，避免下游以为能取到。
扣非只能从官方 PDF 的「非经常性损益项目及金额」表或「主要会计数据」表取（688218 p9/p7 已定位）。

### 2. `type` 参数不是"累计/单季"开关
实测 `type=0/1/2/3/4` 分别返回 全部/一季报/半年报/三季报/年报 的**报告期**，**返回的都是年初至今累计**。
`type=1` 看起来像单季度，只是因为一季度累计恰好等于一季度单季——这是个容易踩的坑。
结论：**接口不提供单季度序列**。

### 3. 单季度优先取官方"分季度主要财务数据"表，而不是相减
年报正文已直接披露 Q1–Q4 的营业收入、归母净利、扣非、经营现金流（688218 p9、002354 p8）。
相减只在没有官方分季表时才用，且必须与官方分季表勾稽。

### 4. 旧快照的 22 列扣非是**累计**，不是单季（P02 表述有误）
- 688218：Q1 −19,728,084.54 + Q2 −5,735,225.19 = −25,463,309.73 = 快照 `20250630` 值
- 再加 Q3 −10,888,975.44 = −36,352,285.17 = 快照 `20250930` 值
- 再加 Q4 −47,527,254.08 = −83,879,539.25 ≈ 快照 `20251231` 值

P02 交接里写的"22 期单季扣非"必须按本表更正；S00 标准化时按累计读入，需要单季再换算。

### 5. 旧快照对北交所覆盖率 = 0/62
全池 1054 家中 BJ 62 家，**全部** `FINANCIAL_DATA_MISSING`，且全池金额列零值单元格为 0（说明缺失是用 NULL 表示的，做法正确）。
P03 已实测旧工作台北交所接口返回 400 —— 两条证据互相印证：北交所必须走显式三市场适配器。

### 6. 62 家缺失的原因现在还判不了
`prelisting_flag` 交叉表：62 家缺失行的 flag 全是 `NONE`，反而 61 家 `PRE_LISTING_PROSPECTUS_DATA` 有数据。
加上 `listing_date` 1054/1054 全 `UNKNOWN`，**不能**判 `NOT_APPLICABLE_PRE_LISTING`，只能记 `MISSING_CAUSE_UNKNOWN`。
这条直接约束 P05：先把上市日期回填了，再谈"上市前不适用"。

### 7. 2025H1 基数是当前最硬的缺口
旧快照有 `2026H1` 也有 `2021–2025` 年度，**唯独没有 2025H1**。
后果：2026H1 的营收／归母／毛利率／现金流／扣非同比，**五项全部算不出来**。
这不是"少一个字段"，而是让当期最重要的一张表失去可比性。

### 8. 毛利率是百分数，不是小数
快照 `gross_margin_pct_2025`（688218）= 23.282460，与官方 (510,041,067.79−391,290,961.13)/510,041,067.79 一致。
字段字典把 `unit_kind=RATIO_PCT` 的 `unit` 固定为 `%`、`scale` 写明"百分数数值，非小数"；比率变动另立 `DELTA_PP`（百分点）。
年报原文"减少13.85个百分点"不得写成 −13.85%。

### 9. 单位与合并范围不是推断出来的
- 4/4 样本 PDF 表头为"单位：元 币种：人民币"，`pdf_lineitem_evidence.json` 逐份记录。
- 同一公司同一报告期，接口与官方 PDF **14/14 字段逐分钱一致**（`crosscheck_provider_vs_pdf.json`）。
- 同一份 PDF 里合并报表与母公司报表并存（688218：合并 BS p122-124，母公司 BS p125-126），抽取必须先锁"合并"标题。

## 四、期间换算规则要点

```
Q1单季 = 一季报累计
Q2单季 = H1累计 − Q1累计
Q3单季 = 9M累计 − H1累计
Q4单季 = FY累计 − 9M累计
```
禁止：跨年度相减、跨版本（重述前后）相减、合并范围变化前后相减、单季×4 反推全年。
校验：四季之和=全年（≤0.01 元）、累计差=官方单季、接口 vs PDF（≤1 元）、毛利率反算（≤0.05pp）、合并范围精确匹配。
实测：48/48 项校验 MATCH_EXACT（含 2 家公司 × 3 字段 × 4 季度的累计比对与相减验证）。

PIT 四时间轴严格分开：`report_period` / `published_on` / `collected_at` / `as_of`（2026-10-25）。
`published_on` 未知时记 `PIT_UNKNOWN`，不得用报告期结束日代替，也不得用取件日冒充披露日。

## 五、验收对照（issue #15 原文）

| 验收标准 | 结果 | 证据 |
|---|---|---|
| 收入/扣非/净利、金额/比例/百分点均不混；NULL 和真实 0 可区分 | PASS | 自检 A1/A2/A3；字段字典 33 行；快照 41 个金额列零值=0、62 家全 NULL |
| 旧快照缺 2025H1 营收、经营现金流等具体缺口已列；来源字段映射有证据 | PASS | 自检 B1/B2/B3/B4；缺口登记 63 行含 5 项 2025H1 基数；映射 52 行全部有 evidence_ref |

12 项自检全 PASS，明细见 `self_check.json`。**这是 SELF_CHECK，不是独立审计。**

## 六、限制与未做

1. 只实测 3 家公司（SH/SZ/BJ 各 1）+ 4 份 PDF，**不等于全池口径验收**；P07 校准仍需覆盖更多公司。
2. 新浪为非官方结构化数据，本次只证明"数值与单位对得上"，不证明业务口径正确。
3. PDF 数值来自文本抽取，可能存在折行/列错位；`raw_line` 已逐条保留供复核。3 份 PDF 的"基本每股收益"标签未被识别（格式差异），已如实记为 `LABEL_NOT_FOUND_IN_RANGE`，未用近似值填补。
4. 旧工作台 `/api/finance/report` 未纳入映射：它是 AKShare 的本地包装，字段词汇未实测，P03 已决定北交所走独立适配器。**未验证就不写进映射表。**
5. 本卡没有改动 `document_registry.csv`（P01 迁移方案仍未执行），也没有新增任何业务验收。
6. `tools/validate_plan.py` 重跑结果存 `plan_validation.json`：**106 项通过 / 5 项失败**，5 项全部是既有包索引漂移
   （`package_index` 68 vs 67、primary 59 vs 58、`D00_B00_ADVANCE_01` 造成 BJ:920207/920578 重复指派、该包缺 ZIP），
   与 P04 无关，本卡未改动这些文件，也未通过改断言"修复"。

## 七、给 P05 的直接输入

- 字段口径：`financial_field_dictionary.csv`（33 字段，含 `p00_required` 标记）
- 取数字段名：`provider_field_mapping.csv`（可直接当代码里的常量表）
- 换算与校验：`period_conversion_rules.json`（`validation_rules` 五条建议直接实现为断言）
- 必须补的：北交所 62 家、7 个 P00 契约字段、2025H1 五项基数、扣非（只能解析 PDF）
- 实现建议：先做 `V1–V5` 校验器，再跑批量；失败项按 P00 状态码落 `FIN.STATUS`，不要落到"人工补件"队列
