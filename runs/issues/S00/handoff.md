# S00 交接：标准化全池财务，保留原值、单位和版本

- **issue**：#35 / S00，plan_version `20261026_collection_first_v2`
- **执行者/自检者**：WorkBuddy AI（执行与自检同一主体，`review_nature=SELF_CHECK`，不冒充独立审计）
- **领取**：2026-10-28T20:52(+08) → **完成**：2026-10-28T22:4x(+08)
- **依赖**：#34 A04，`runs/issues/A04/rework/review.json` = `ACCEPTED_WITH_LIMITS`，`release_S00=true`
- **本卡不做**：不筛公司、不定阈值、不算拐点、不估值、不改原件、不改台账状态、不下载新文件

## 一、一句话结论

把 **11,468 份已核定期报告 + 旧快照 2021/2022** 整理成 **228,154 行逐格可复算**的标准化财务表：
1054 家公司、12,648 个槽位一个不少地留在主键集合里，缺失一律不填 0，扣非和经营现金流缺失时**没有**用净利润顶替。

真正要交接出去的不是"抽到了多少"，而是 **62 个槽（0.54%）整槽抽不出任何值**——其中
**26 份是采到了英文版年报**（格力、美的、立讯这类有 B/H 股的公司），**14 份没有文本层**（图片版），
**20 份中文文本正常但抽取器版式覆盖不到**。这是资料层和抽取层的缺口，不是"公司没披露"。

## 二、交付

| 文件 | 内容 | 规模 |
|---|---|---|
| `financial_normalized.csv` | 全池标准化长表，一行一格，含原值/原单位/换算倍数/折算值/页码/来源文档/状态/口径标记 | **228,154 行**，76.7 MB（本机） |
| `financial_normalized.csv.gz` | 同上 gzip（提交 Git 用，sha256 见 manifest） | 5.5 MB |
| `normalization_issues.csv` | 缺失、不适用、未披露、校验失败、重述未决、单位未识别逐条登记 | **14,350 行**（ERROR 2,184 / WARN 8,915 / INFO 3,251；阻塞指标 1,307） |
| `normalization_manifest.json` | 口径、覆盖、校验汇总、可比性矩阵、无值槽定性、已知限制 | — |
| `legacy_snapshot_conflicts.json` | 旧快照 vs 官方 PDF 逐条冲突（V3） | 442 条 |
| `manifest.json` | 交付清单与逐文件 sha256 | — |
| `extract/*_fields.csv` | 逐格抽取证据（12 槽） | 213,446 行，33.6 MB（本机） |
| `extract/*_diag.csv` | 每份 PDF 的解析诊断（区域页码/单位/交叉校验） | 11,468 行 |

生成器：`tools/s00_extract.py`（按槽分批 + 断点续跑）、`tools/s00_normalize.py`（标准化）、
`tools/s00_finalize.py`（压缩与指纹）。抽取器复用并修正 `tools/a03_financial_field_extractor.py`。

## 三、怎么做的

### 1. 抽取层：12 槽全量重抽，不是复用 A03

A03 只跑过三个年报槽。本轮对 **12 个槽全量重抽**（11468 份，16 进程，约 78 分钟），保证同一套口径。
为让季报也能抽，改掉抽取器四处硬编码（见第四节 F28–F31）。与 A03 年报结果逐格比对：
**annual_2024 4,116 格全同、annual_2025 4,180 格全同、annual_2023 4,019 格全同 + 9 格由 NOT_IN_STATEMENT 转为抽到值**（改善，无回归）。

### 2. 期间层：YTD 与单季分开，单季优先官方分季表

- 累计（YTD）：FY/H1/9M/Q1 四个期间类型，`period_basis=YTD_CUMULATIVE`；
- 单季：`period_basis=SINGLE_QUARTER`，独立期间键（Q1–Q4）。
  优先级 **官方年报「分季度主要财务数据」表（40,264 格）＞ Q1 累计即单季（5,372 格）＞ 同年同版本累计相减（8,603 格）**；
- 禁止跨来源相减：27 次触发被拦截并登记（`CROSS_SOURCE_SUBTRACTION_BLOCKED`），例如 PDF 累计不能减旧快照累计；
- 时点科目（应收/存货/合同资产/资产总计）标 `INSTANT`，不与流量混算。

### 3. 派生层：只做四则运算能自证的

毛利额 = 收入 − 成本；毛利率、归母净利率、现金含量（仅归母净利 > 0 时算，否则记
`NOT_COMPUTABLE_NONPOSITIVE_NPP` 并只并列绝对额，2,315 条）。全部 `status=DERIVED`，带来源格。

### 4. 校验层：三条独立校验，冲突不藏

| 校验 | 口径 | 结果 |
|---|---|---|
| **V1 四季和 = 全年** | 官方分季表四季加总 vs 三表全年累计 | MATCH 10,629 + 舍入一致 116；不一致 114，其中第三方快照仲裁后 **采用四季和 64 / 保留全年 24 / 双方都远离快照 3 / 无第三方 23** |
| **V3 官方 PDF vs 旧快照** | 同公司同期间同字段，容差 1 元 | 17,363 组比对：一致 16,921、不一致 442（2.5%），**一律以官方 PDF 为准并逐条登记** |
| **V4 毛利率反算** | (收入−成本)/收入×100 vs 快照毛利率 | 一致 3,334、差 ≤2pp 381、**差 >2pp 59**（多为营业总收入 vs 营业收入口径差） |
| **三表 vs 摘要表** | 抽取器内建交叉校验 | 一致 10,542 份、部分一致 242、无摘要表 231；**不一致 453 份**，相关 REV/NPP/OCF 标 `EXTRACTED_XCHECK_MISMATCH`（1,326 格），阻塞跨期比较 |

V1 的 64 次「采用四季和」是有实证的修正，例如同方股份 2023 营业收入：三表抽出 40.15 亿（错位），
分季表四季和 288.33 亿、旧快照 288.33 亿，两者互证后采用后者。

### 5. 标记层：把"不能用"和"不能用来说什么"写清楚

`is_pre_listing`（逐行比对 A04 的 274 条不适用依据，日期必须真的晚于报告期末）、
`restatement_flag`（是/否/待核）、`low_base_flag`（上年同期收入 <1000 万或归母 <500 万记 LOW_BASE_*，
上年同期为负记 NEGATIVE_BASE_*，共 1,921 格）、`comparability_note`（重述未重算/重述未决/上市前/低基数）。

## 四、本轮新发现的四个抽取器缺陷（F28–F31，已修）

| 编号 | 缺陷 | 后果 | 修法 |
|---|---|---|---|
| **F28** | `build_statement_map` 的 `start_page` 固定 15 | 季报只有 10–20 页，报表在第 5–6 页，**整份漏抽**（深沪季报全中） | 页数 <40 时从第 2 页起扫 |
| **F29** | 三季报利润表标题写作「合并年初到报告期末利润表」 | 利润表/现金流量表定位失败 | 标题加变体正则，`$` 锚定整行避免误匹配「…项目」小标题 |
| **F30** | 北交所季报第 3–4 页「主要财务数据变动情况」里的小标题独占一行「合并资产负债表」「合并现金流量表」 | 变动说明页被当成报表区块，BS 区域错位、OCF 整段漏抽（920002/920060 复现） | 标题还要过「该页真像报表吗」检验：2 页内命中该报表 2 个以上科目特征词 |
| **F31** | 三季报摘要表列序三种版式完全不同 | 深市把 Q3 单季当累计写进 YTD（000026 扣非 41,360,520.65 应为 119,737,782.83） | 用三表已抽到的营业收入累计值**反查列下标**，再拿同一列取扣非 |

## 五、覆盖与质量

- **主键集合**：1054 家公司全部在 `financial_normalized.csv` 中（`companies_missing_from_normalized=[]`）；
  12,648 个槽位全覆盖（`slots_uncovered=0`），其中已核 11,468、上市前不适用 274、发行人未披露 42、未到期 864。
- **有值槽**：11,406 / 11,468（99.46%）。
- **字段覆盖（格数）**：扣非累计 18,018、单季营收 13,914、单季归母 13,773、单季扣非 13,364、
  归母累计 13,312、营收累计 13,308、经营现金流累计 11,174、营业成本 11,178、应收 11,174、
  存货 11,170、合同资产 5,651（大量公司无此科目，记 `NOT_IN_STATEMENT` 不填 0）。
- **抽取状态**：EXTRACTED 163,027 / 213,446（76.4%）；NOT_IN_STATEMENT 36,490（17.1%）；
  BLANK_IN_STATEMENT 7,711；STATEMENT_NOT_FOUND 1,410；NOT_FOUND 1,942；QUARTERLY_PARSE_FAILED 132。

## 六、62 个整槽无值：三种成因，都要交出去

| 成因 | 槽数 | 说明 | 建议动作 |
|---|---:|---|---|
| `DOCUMENT_IS_ENGLISH_OR_NON_ZH` | 26 | 采到的是英文版年报（格力 000651、立讯 002241 等有 B/H 股公司），中文关键词全部落空 | **回资料轮补采中文版**；采集器需加语言校验（F32） |
| `DOCUMENT_NO_TEXT_LAYER` | 14 | 图片版 PDF，无文本层（002083 全年 5 个槽全中） | 需 OCR 或补采文本版 |
| `EXTRACTION_BLIND_SPOT` | 20 | 中文文本正常（中文占比 0.33–0.72），三表标题定位失败 | 抽取器版式覆盖，交后续 |
| `DOCUMENT_MIXED_LANGUAGE` | 2 | 中英混排，标题被英文打断 | 同上 |

**这 62 个槽不是"公司没披露"**，文件在盘、身份已核，是文件形态问题。

## 七、验收对照（issue #35 原文）

| 验收标准 | 结果 | 证据 |
|---|---|---|
| 1054 家公司全留在主键集合 | **PASS** | `companies_in_normalized=1054`、`companies_missing=[]`、`slots_uncovered=0`；12648 槽全部有归属（有值或带原因码的 issue） |
| 缺失不填 0 | **PASS** | `financial_normalized.csv` 只输出有值格（`value_cny` 非空）；缺失一律走 `normalization_issues.csv` 并带状态码（NOT_IN_STATEMENT / BLANK_IN_STATEMENT / STATEMENT_NOT_FOUND / NOT_DISCLOSED / NOT_YET_DISCLOSED / PARSE_FAILED）；全表无 0 占位行 |
| 季度与年度可比性明确 | **PASS** | `period_basis` 三值（YTD_CUMULATIVE / SINGLE_QUARTER / INSTANT）+ `period_type` 八值 + manifest 的 `comparability_matrix`（含 prohibited 清单：FY vs H1、累计 vs 单季、跨年度相减、跨来源相减、跨版本相减） |
| 现金流缺失不得用净利润或其他代理值替代 | **PASS** | 代码中无任何 fillna/代理赋值；OCF 缺失格状态为 NOT_IN_STATEMENT / BLANK_IN_STATEMENT / STATEMENT_NOT_FOUND，`value_cny` 为空；V1 无法用快照仲裁的 OCF 差异 23 例保持原值并标 `UNRESOLVED_NO_PROVIDER` |
| 扣非缺失不得用净利润替代 | **PASS** | 扣非只来自「主要会计数据表」或「分季度表」，缺失记 NOT_IN_STATEMENT（876 条 FIELD_NOT_IN_STATEMENT 中含扣非）；`FIN.NPDEDT.YTD` 与 `FIN.NPP.YTD` 分列，无派生替代 |
| 保留原字段/单位/转换倍数/来源/版本 | **PASS** | 每行含 `value_raw`/`unit_raw`/`unit_scale`/`value_cny`/`document_id`/`source_page`/`evidence_label`/`source_kind`/`restatement_flag`；`period_source` 区分 COLLECTED_2026_SLOT 与 LEGACY_SNAPSHOT |
| 检查合计关系与来源 | **PASS** | V1 四季和（10,745 通过）、V3 PDF vs 快照（17,363 组）、V4 毛利率反算、三表 vs 摘要表（453 份不一致已标）；冲突全部逐条落 `normalization_issues.csv`，不静默取舍 |

## 八、限制与未做（给 S01/S02 的实话）

1. **旧快照 2021/2022 只有单一来源**（新浪），无官方 PDF 交叉校验；2023–2025 才有双源比对。用 2021/2022 做基期时要知道这一点。
2. **没有用最新年报的「上年同期」列重算历史期**。重述公司（`restatement_flag=是`）的历史值仍是当年报告口径，跨年比较已标 `RESTATED_PRIOR_YEARS_UNRECALCULATED`；待核的 2,157 份标 `RESTATEMENT_UNRESOLVED`（关键词判据，未逐份确认勾选项）。
3. **453 份文档三表与摘要表不一致**，相关 REV/NPP/OCF 已标 `EXTRACTED_XCHECK_MISMATCH`（1,326 格），S02 用到这些公司时应先核或排除。
4. **营业总收入 vs 营业收入口径差**：金融/多元业务公司（如同方股份）两个口径差一个数量级，本轮统一取「营业收入」，与旧快照（多取营业总收入）存在不可比，已在 V3/V4 冲突中登记。
5. **季报能力上限不同**：深市部分一季/三季报只披露「主要会计数据」摘要，没有完整三表，故 COST/AR/INV 在该期为 NOT_IN_STATEMENT；这不是漏抽。
6. **62 个整槽无值**（第五节）中 26 份英文版是采集层缺陷，需回资料轮；本轮未补采、未 OCR。
7. 2026Q3 只有 190 家已披露（其余 864 家未到披露期，记 `NOT_YET_DISCLOSED`），当期截面不完整。
8. `collected_at` 用台账 `updated_at` 代理（台账无独立取件时间戳），已在 manifest 注明。

## 九、给下一卡（S01 #36）的直接输入

- **规则输入**：`financial_normalized.csv` 的 `period_basis` 决定什么能比；`low_base_flag`/`restatement_flag`/`comparability_note` 决定什么要排除或单独处理。
- **必须尊重的三件事**：① 累计与单季不可混算；② 跨来源（PDF vs 快照）不可相减；③ 扣非与归母不可互相替代。
- **建议 S01 明确**：低基数阈值（本轮临时用收入 1000 万 / 归母 500 万，S01 可覆盖）、负基数下只报绝对额与利润率变化、`EXTRACTED_XCHECK_MISMATCH` 公司是排除还是降权。
- **S02 前置**：先把 453 份 xcheck 不一致、62 个无值槽、2,157 份重述待核当作已知脏区，别在筛选结果里当成"业绩突变"。
