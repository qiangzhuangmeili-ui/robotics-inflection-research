# S00 交接：标准化全池财务，保留原值、单位和版本（返工版 v2）

- **issue**：#35 / S00，plan_version `20261026_collection_first_v2`
- **执行者/自检者**：WorkBuddy AI（`review_nature=SELF_CHECK`，不冒充独立审计）
- **首版**：2026-10-28T22:4x(+08)，提交 `6c35701`
- **返工**：2026-10-29T09:50–10:3x(+08)，按 Codex 复核 `RETURN_FOR_REWORK` 修四项阻断
- **依赖**：#34 A04，`runs/issues/A04/rework/review.json` = `ACCEPTED_WITH_LIMITS`
- **本卡不做**：不筛公司、不定阈值、不算拐点、不估值、不改原件、不改台账状态、不重跑全池采集

## 〇、返工改了什么（对 Codex 四项阻断的处置）

| 阻断项 | 根因 | 修法 | 复验证据 |
|---|---|---|---|
| **1 派生指标未随基础值更新** | 派生在 V1 仲裁之前算，64 个年度值被改写后没重算；同方股份 FY2023 毛利率输出 −490.61% | 派生抽成 `derive_ratios()`，在 V1 仲裁后**整体重算**；同时重算依赖 FY 的 Q4 单季；仲裁格保留 `value_before_adoption`/`adoption_reason`/`quarterly_inputs` | `V1-1~V1-5`：全表 4 条公式 0 违规；同方股份 FY2023 毛利率 **17.759629%**、毛利额 **5,120,716,308.64**，与「最终收入−成本」一致 |
| **2 重述标记整批丢失** | `load_extract` 以 `(field_id, note)` 建键，重述行 note 是 `method=...`，代码只查空 note | 改为「空键取不到就按 field_id 回退」；`restate` 改存 flag/status/page/evidence/document_id | `V2-1~V2-3`：normalized 中 是 **1,155** / 否 **9,490** / 待核 **6,373** / NOT_APPLICABLE 903 / NOT_FOUND 15；issues 中重述待核逐条有记录 |
| **3 HOLD 未向派生值传播** | 派生只标 `DERIVED`，不看输入是否 `EXTRACTED_XCHECK_MISMATCH` | 派生与单季差分都检查上游 HOLD，输出 `DERIVED_HOLD_UPSTREAM` / `DERIVED_Q1_HOLD_UPSTREAM`，并写 `upstream_hold_fields` 父键 | `V3-1~V3-3`：HOLD 派生格 **2,037**（毛利/比率 1,627 + 单季差分 364 + Q1 45），泄漏 0，父键齐全 |
| **4 更正版未接入采用** | 直接用台账 `document_id` 抽取，未接 A04 版本链 | `tools/s00_rework_corrected.py` 重抽 6 份更正全文，逐字段比对后采用更正版 `document_id`，原版留在 `original_document_id` | `V4-1~V4-2`：6 槽全部 `version_used=CORRECTED_FULLTEXT`；**132 个字段对逐字段比对 0 处不同**，数值不变但溯源改正 |

返工自检 19 项全部 PASS，明细见 `runs/issues/S00/self_check_rework.json`。

## 一、一句话结论

把 **11,468 份已核定期报告 + 旧快照 2021/2022** 整理成 **228,155 行逐格可复算**的标准化财务表：
1054 家公司、12,648 个槽位一个不少，缺失一律不填 0，扣非和经营现金流缺失时**没有**用净利润顶替；
每一条派生值都能沿 `upstream_hold_fields` / `value_before_adoption` 追回父键和采用理由。

要交接出去的仍是 **62 个槽（0.54%）整槽抽不出值**——其中 **26 份是采到英文版年报**（格力、立讯这类有 B/H 股的公司），
14 份无文本层，20 份中文正常但抽取器版式覆盖不到，2 份中英混排。这是文件形态问题，不是"公司没披露"。

## 二、交付

| 文件 | 内容 | 规模 |
|---|---|---|
| `financial_normalized.csv` | 全池标准化长表，一行一格 | **228,155 行**，87.4 MB（本机） |
| `financial_normalized.csv.gz` | 同上 gzip（提交 Git 用） | 5.9 MB |
| `normalization_issues.csv` | 缺失/不适用/未披露/校验失败/重述待核/版本采用逐条登记 | **16,513 行** |
| `normalization_manifest.json` | 口径、覆盖、校验汇总、可比性矩阵、无值槽定性、版本采用对账 | — |
| `legacy_snapshot_conflicts.json` | 旧快照 vs 官方 PDF 逐条冲突（V3） | 442 条 |
| `self_check_rework.json` | 返工 19 项自检逐条结果 | 19 项 |
| `rework/corrected_vs_original_diff.csv` | 6 份更正版 vs 原版逐字段比对 | 132 行（0 处不同） |
| `manifest.json` | 交付清单与逐文件 sha256 | — |
| `extract/*_fields.csv` | 逐格抽取证据（12 槽） | 213,446 行，33.6 MB（本机） |
| `extract/*_diag.csv` | 每份 PDF 的解析诊断 | 11,468 行 |

生成器：`tools/s00_extract.py`（分批+断点续跑）、`tools/s00_normalize.py`（标准化）、
`tools/s00_rework_corrected.py`（更正版重抽）、`tools/s00_verify.py`（返工自检）、`tools/s00_finalize.py`（压缩与指纹）。

## 三、怎么做的（返工后的顺序）

1. **抽取**：12 槽全量重抽 11,468 份，213,446 字段行。与 A03 年报逐格比对：annual_2024 4,116 格全同、
   annual_2025 4,180 格全同、annual_2023 4,019 格全同 + 9 格由 NOT_IN_STATEMENT 改善为抽到值。
2. **版本采用**：A04 版本链对账出 6 个「有更正全文却用原版」的槽，重抽更正版，132 字段对 0 处不同后采用更正版。
3. **期间**：累计（FY/H1/9M/Q1）与单季（Q1–Q4）分开；单季优先级 **官方分季表 40,264 格 ＞ Q1 累计即单季 5,327 ＞ 同年同版本累计相减 8,239**；
   跨来源相减拦截 27 次。
4. **V1 校验与仲裁**：四季之和 vs 全年累计。10,629 一致 + 116 舍入一致；不一致 114，按「第三方快照 1% 内」仲裁：
   **采用四季和 64 / 保留全年 24 / 双方都远离快照 3 / 无第三方 23**。后两类在格上标 `PERIOD_INCONSISTENT_*`，不只写在 issues 里。
5. **下游重算**（返工新增）：仲裁后重算依赖 FY 的 Q4 单季（1,267 次重算、0 次值变，因为被仲裁的都是有官方分季表的公司），
   再整体重算派生比率 44,499 格。
6. **派生与 HOLD 传播**：毛利额、毛利率、归母净利率、现金含量（仅归母>0）；上游任一输入 HOLD 时派生值同步 HOLD 并记父键。
7. **标记**：`is_pre_listing`（逐行比对 A04 的 274 条不适用依据）、`restatement_flag`（是/否/待核/不适用/未找到 + 页码证据）、
   `low_base_flag`（1,921 格）、`comparability_note`（重述未重算/重述未决/期间不一致/低基数/HOLD 父键）。

## 四、抽取器缺陷（F28–F32）

| 编号 | 缺陷 | 状态 |
|---|---|---|
| **F28** | 季报三表定位 `start_page` 固定 15，10–20 页季报整份漏抽 | 已修：页数<40 从第 2 页扫 |
| **F29** | 三季报利润表标题「合并年初到报告期末利润表/现金流量表」未识别 | 已修：标题变体正则 + `$` 锚定 |
| **F30** | 北交所季报「变动情况」页小标题冒充报表标题，BS 错位、OCF 漏抽 | 已修：加「2 页内命中 2 个科目特征词」检验 |
| **F31** | 三季报摘要表累计列位置三种版式（深市第 2 列 / 北交所第 1 列 / 沪市第 4 列） | 已修：用三表营收累计值反查列下标 |
| **F32** | 采集器不校验文档语言，26 份英文版年报被当中文版采入 | **未修**，交资料轮补采中文版 |

## 五、覆盖与质量

- **主键集合**：1054 家全在（`companies_missing=[]`）；12,648 槽全覆盖（`slots_uncovered=0`）：
  已核 11,468、上市前不适用 274、发行人未披露 42、未到期 864；有值槽 11,406（99.46%）。
- **字段覆盖（格数）**：扣非累计 18,018、单季营收 13,914、单季归母 13,773、单季扣非 13,364、
  归母累计 13,312、营收累计 13,308、经营现金流 11,174、营业成本 11,178、应收 11,174、存货 11,170、
  合同资产 5,651（大量公司无此科目，记 NOT_IN_STATEMENT 不填 0）。
- **状态分布**：EXTRACTED 103,818、DERIVED 42,871、EXTRACTED_QUARTERLY_TABLE 40,264、
  LEGACY_SNAPSHOT 13,652、EXTRACTED_KEY_TABLE 10,557、DERIVED_CUMULATIVE_DIFF 8,239、
  DERIVED_Q1_EQUALS_YTD 5,327、**DERIVED_HOLD_UPSTREAM 1,992**、**DERIVED_Q1_HOLD_UPSTREAM 45**、
  EXTRACTED_XCHECK_MISMATCH 1,326、DERIVED_QUARTERLY_SUM_OVERRIDE 64。
- **校验**：V3 PDF vs 快照 16,921/17,363 一致；V4 毛利率 一致 3,334、差≤2pp 381、差>2pp 59；
  三表 vs 摘要表 一致 10,542、部分 242、无摘要表 231、**不一致 453**。

## 六、62 个整槽无值

| 成因 | 槽数 | 建议动作 |
|---|---:|---|
| `DOCUMENT_IS_ENGLISH_OR_NON_ZH` | 26 | 回资料轮补采中文版；采集器加语言校验（F32） |
| `DOCUMENT_NO_TEXT_LAYER` | 14 | OCR 或补采文本版 |
| `EXTRACTION_BLIND_SPOT` | 20 | 抽取器版式覆盖 |
| `DOCUMENT_MIXED_LANGUAGE` | 2 | 同上 |

## 七、验收对照

| 验收标准 | 结果 | 证据 |
|---|---|---|
| 1054 家公司全留在主键集合 | **PASS** | `companies_in_normalized=1054`、`slots_uncovered=0` |
| 缺失不填 0 | **PASS** | `V0-3` 无空 value_cny，缺失全走 issues 带状态码 |
| 季度与年度可比性明确 | **PASS** | `period_basis` 三值 + `comparability_matrix`；`V5-1` 最终表四季和=全年，50 个无法仲裁的已在格上标 `PERIOD_INCONSISTENT_*` |
| 现金流缺失不用净利润替代 | **PASS** | `V6-1` OCF 状态白名单校验通过，无同页同源等值代理 |
| 扣非缺失不用净利润替代 | **PASS** | 同上；扣非只来自摘要表/分季度表，缺失记 NOT_IN_STATEMENT |
| 保留原值/单位/倍数/来源/版本 | **PASS** | `value_raw`/`unit_raw`/`unit_scale`/`value_cny`/`document_id`/`source_page`/`evidence_label`/`source_kind`/`restatement_flag`/`version_used` |
| 检查合计关系与来源 | **PASS** | V1 仲裁、V3 双源、V4 反算、三表 vs 摘要表；返工后 `V1-1~V1-5` 全表公式 0 违规 |

## 八、限制与未做

1. 旧快照 2021/2022 只有单一来源（新浪），无官方 PDF 交叉校验。
2. 未用最新年报「上年同期」列重算历史期；重述公司历史值仍是当年报告口径（`RESTATED_PRIOR_YEARS_UNRECALCULATED`）。
3. 453 份文档三表与摘要表不一致，相关 REV/NPP/OCF 标 `EXTRACTED_XCHECK_MISMATCH`（1,326 格），S02 用前须核或排除。
4. 营业总收入 vs 营业收入口径差（同方股份这类）统一取「营业收入」，与旧快照（多取营业总收入）不可比，已在 V3/V4 冲突登记。
5. 季报能力上限不同：深市部分一季/三季报只有摘要表，COST/AR/INV 在该期 NOT_IN_STATEMENT。
6. 62 个整槽无值中 26 份英文版是采集层缺陷，本轮未补采、未 OCR。
7. 2026Q3 只有 190 家已披露（其余 864 家未到披露期）。
8. `collected_at` 用台账 `updated_at` 代理（台账无独立取件时间戳）。
9. 本次自检仍是 SELF_CHECK，不冒充独立审计；返工只针对复核指出的四项，未扩大改动范围。

## 九、给 S01 #36 的输入

- **规则输入**：`financial_normalized.csv`；`period_basis` 决定什么能比，`status` 决定什么能用。
- **必须尊重的三件事**：累计与单季不可混算；跨来源不可相减；扣非与归母不可互相替代。
- **机器可识别的脏区**：`status=DERIVED_HOLD_UPSTREAM`（2,037 格）与 `upstream_hold_fields` 直接指向不可信上游；
  `comparability_note` 含 `PERIOD_INCONSISTENT_*` / `RESTATEMENT_*` / `HOLD_UPSTREAM:*`。
- **S01 可覆盖**：低基数阈值（本轮临时收入 1,000 万 / 归母 500 万）；HOLD 公司是排除还是降权；重述待核的处理。
