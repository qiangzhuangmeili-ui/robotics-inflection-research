# S00 勘误 V5：批次 B 取列返工与独立旁证（第二十轮汇报）

- 目录：`runs/issues/S00/errata_20261111_v5/`
- 自检版本：**V17**，**43/43 PASS** → `SELF_CHECK_PASS_WITH_UNRESOLVED_ITEMS`
- 性质：**SELF_CHECK**（同一执行 AI 自验，登记表 `review_role=SELF_CHECK`）
- 上一轮裁决：`RETURN_FOR_REWORK`（D1–D5 + 6 条返工清单）→ `rework_round19.json`
- 本轮逐条对照（机器可读）：`rework_round19_result.json`
- 复现顺序：`step4_parent_scan.py` → `step4_column_witness.py` → `step4_apply_parents.py` →
  `build_errata_v5.py` → `check_l2_v5.py` → `sampling_v5.py` → `replay_polarity_v5.py` → `verify_v5.py`

**本轮不改「哪些键应当闭合」，只改判定方法，然后按新方法把 87 条全部重推一遍。**
裁决原文「本裁决不宣告这 70 条全部为假，但不接受据当前方法将批次 B 核证验收通过」是本轮的边界。

---

## 一、六条清单逐条落实

### 1. 多个期间列候选必须报歧义，禁止拼接后择一

**旧实现的错**（你复现的那个）：金额范围左扩 20pt、右扩 4pt，把范围内**所有**表头词拼起来，
再按最长匹配归一。左列 `2025年半年度` x[70,90]、本列 `2026年半年度` x[100,130]、
金额 x[100,110] → 拼成 `2025年半年度2026年半年度` → 归一成 `2025年半年度`。

**新实现**（`parent_verify.py:654-870`）：把列结构**先还原再取**，不拼字符串。

1. `_header_cells(rows, hdr_rows, gap=6.0)`：同一行相邻表头词按**间隙 ≤6pt** 并成**单元格**；
   加语义保护——**两侧各自都已是完整列名（`canon_column` 非空）就不并**。
   这条保护是必需的：测试夹具里两列只隔 5pt，纯按间隙会并。
2. `_chain_cells(cells, x_tol=3.0)`：单元格跨行按**横向重叠**并成**列链**；
   **同一行的两个单元格永不合并**（防止把两列横向并成一列）。
3. `_label_band(rows, ri, max_rows=2, max_dy=40.0)`：指标名换行时把紧邻的「无数字」行拼回来
   （上/下各至多 2 行）——否则「归属于上市公司股东的扣除非经常性 / 损益的净利润」会被判
   `NO_LABEL_ROW`。
4. 定列：`lo, hi = ax0 - 8.0, ax1 + 4.0`（`_BAND_PAD_LEFT` **20 → 8pt**，原值会把左邻表头拉进来），
   取与 `[lo,hi]` 有重叠的列链。**期间列候选 >1 → `AMBIGUOUS`**，不拼接、不取第一个。
5. 命中金额若落在**不同列**（`spans` 去重后 >1）也判 `AMBIGUOUS`
   （`一、营业总收入` 与 `其中：营业收入` 同值时会触发）。

C37 新增两条**生产路径**反例：`neighbor_header_not_taken`、`overlapping_columns_ambiguous`，
均 PASS。

### 2. 归一须保留年份、完整起止区间、本期/上年/上期及累计属性

`canon_column()` 重写为**结构化键** `相对年|区间|累计`（`parent_verify.py:873-931`）：

| 列名 | 旧归一 | 新归一 |
|---|---|---|
| `本期金额（2026年1-6月）` | `2026年` | `本期｜R-2026-1-6｜累计` |
| `本期金额（2026年4-6月）` | `2026年` | `本期｜R-2026-4-6｜累计` |
| `本报告期（1－6月）` | `本报告期` | `本期｜R0-1-6｜累计` |
| `本报告期（4－6月）` | `本报告期` | `本期｜R0-4-6｜累计` |
| `上年年初至报告期末` | `年初至报告期末` | `上年｜｜累计` |
| `上年同期（2025年1—6月）` | — | `上年｜R-2025-1-6｜累计` |
| `期末余额（2026年6月30日）` | — | `期末｜D-2026-6-30｜` |

配套三处修正：

- **`_COL_CLASSES` 顺序**：`PRIOR_YEAR_YTD` 提到 `CURRENT_YTD` 之前，否则
  `上年年初至报告期末` 先被 `CURRENT_YTD` 命中（`parent_verify.py:358-369`）。
- **区间正则连字符类**：`[—\-~～至]` → `[—–−－~～至\-]`，补上全角 `－`（U+FF0D）。
  `本报告期（1－6月）` 在真实半年报里用的正是全角。
- **`clean_column_text()` / `registrable_column()`**（`parent_verify.py:932-964`）：
  登记表里存**原文连续子串**（首个期间片段→末个期间片段的原样切片），
  并要求该候选在**正文中连续出现**、且 `canon_column` 与整段表头**完全相同**。

C37 的 `canon_keeps_semantics` 覆盖八组正例 + **十一组异义对**（必须判不等价）+ 四组同义对
（必须仍判等价）。你点名的三组（1-6月 vs 4-6月、本报告期两版、上年年初至报告期末）全在其中。

### 3. 金额精确十进制 + 完整数字边界；指标行未命中不得回退

**（a）十进制**：`_dec/_CENT/_same_amount/amount_pattern`（`parent_verify.py:472-535`），
比较为**分位逐位相等**（`quantize(0.01)`），删掉 `abs(diff)<0.01` 浮点容差。
`amount_pattern()` 由 Decimal 生成，不再用 `%.2f` 拼正则。

**（b）数字边界——这里有个坑必须交代**：
`_AMOUNT_TOKEN` 若右侧带 `(?!\d)`，在**去空白的正文**里几乎永远不命中：
PDF 文本层把 `684,956,197.48` 与 `585,346,923.80` 两列相邻数字去空白后**粘成**
`684,956,197.48585,346,923.80`。上一轮我一度把边界加到右侧，扫描从 70 条掉到 3 条。
所以：

- `_AMOUNT_TOKEN` 改为 `(?<![\d.,])-?\d[\d,]*(?:\.\d+)?`，**右侧不加** `(?!\d)`；
- 金额定位**回到词坐标**：`column_of_amount_aligned_ex()` 返回 `amount_word`（词元组），
  `step4_parent_scan._quote()` 按词偏移在原文中定位，不再用正则在拼接文本里捞；
- `_num_in_quote(exact=)` 三级判据：①按金额词原文严格命中 → ②Decimal 全等 →
  ③token 在某数字位切开，前半段等于父数、后半段是另一个数的开头（≥5 字符或自带小数点/千分位）。
  第 ③ 级专治「粘连」：`61249,206,238.56` 里 `61` 后面接的是另一个金额的开头。

**（c）指标行不得回退**：`_quote()` 里指标名必须命中；未命中即 `NO_LABEL_ROW`，
不再「页面只有一个候选金额就接受」。C37 反例 `label_row_required`
（目标营业收入、页面只有营业成本 `100.00`）与 `amount_exact_decimal`
（目标 `100.009`、页面只有 `100.00`）均 PASS。

**副作用（如实报）**：4 条粘连数字键（`603273/603380/688248/688400` 的
`FIN.REV.SQ@20260630`）由「判不出」变「可判」，已计入下面的计数变化。

### 4. C41 补齐父期间、两侧口径、版本依据与依据内容；纠正注入次数

`check_c41()` 新增（`verify_v5.py:3427-3553`）：

- **父期间绑定**：`p1_period` 必须等于本行 `period_key`、`p2_period` 必须等于本行前一期，
  否则 `P1_PERIOD_MISMATCH` / `P2_PERIOD_MISMATCH`；
- **两侧口径互检**：`SCOPE_NOT_SHARED_BETWEEN_PARENTS`（两侧 `consolidation_scope`/`unit_scale`/
  `currency` 必须一致），且两侧须**同时**与实际父输入相符；
- **版本依据可证**：`_version_basis_ok()` 要求**逐侧**写出版本归类
  （`ORIGINAL` / `RESTATED`）。旧版依据文字一律写「两段引文均不含调整后…即两期都取原版列」——
  在 `RESTATED` 时这是**假话**；
- **依据内容防填充**：`_filler_text()`（单字符 >40% 或不同字符 <6 判填充）、
  `_scope_basis_ok()`（须点到合并口径/单位/币种中文名与两期期间）。

**注入次数**：`_c41_inject()` 由「只改首行」改为**逐行**注入，并同时写出该类**实际注入行数**
`_rows_<name>`；判据改为「拦住数 == 该类注入行数」：

| 注入类 | 注入 | 拦住 |
|---|---:|---:|
| `fake_quote` / `wrong_column` / `wrong_value` / `wrong_page` | 64 | 64 |
| `version_flip` / `short_basis` / `wrong_period` | 64 | 64 |
| `empty_version_basis` / `repeat_version_basis` / `repeat_scope_basis` | 64 | 64 |
| `swap_column` | **32** | 32 |

`swap_column` 分母 32 而非 64：其中 32 行两侧登记列名在半年报里**本就等价**
（`本报告期（1－6月）` vs `本报告期`），互换后什么都没变。这类行若计入分母，
等于用「拦不住」冒充「拦住了」。分母取「两侧列不等价」子集，理由写在 `_c41_inject()` 注释里。

**V15/V16 汇报不一致**：上一轮 `review.json` 六项各记 1，我在报告里写「各 70」。
现在 `review.json` 直接记 `_rows_*` 分母，报告不再另写一份数字。

### 5. 全页取词失败不得缓存为空白证据

- `pdf_pages()`（`verify_v5.py:448`）：逐页异常记 **`None`**（与**真实空页 `""`** 区分），
  计 `failed`；**整本 `failed > 0` 一律不写 `_PDF_CACHE`**。
- `_pdf_ev()`（`verify_v5.py:491`）：技术失败返回 `None`、真空页返回 `""`；
  回退分支 `page_words` 为空也返回 `None`。
- C41：`src is None` → `<SIDE>_SOURCE_READ_FAILED`（技术失败，**不计入证据缺失**）；
  `not src` → `<SIDE>_SOURCE_UNAVAILABLE`。

### 6. 重验全部 70 条 + 独立列身份旁证 + 重算闭合数

`targets()` 现在**并入上一轮已登记的 70 个键**（不只取「HOLD 中仅缺 `PARENT_COMPATIBILITY`」的），
按键去重 → **87 条**全量重推。

**独立旁证 `step4_column_witness.py`（新增）**，走一条**与生产完全不同的路径**：

1. `_column_grid()`：把页面数字按**右边界聚类**成列，同时记该列**最左数字左边界**与词数；
2. `_column_span()`：列范围 `[该列最左数字左边界 − 12pt, 该列右边界 + 6pt]`。
   **不用相邻列右边界中点**——短数字与宽列会错位（首版 66 条全 `WITNESS_FAIL` 就是这原因）；
3. `_header_rows()`：取金额行**上方最近一行**「≥2 格且含期间词、非标题」的行。
   首版取「单元格最多的一行」，抓到的是「股本结构表」；
4. 表头词**先并单元格再按中心落列**。按**词**中心落列会把 `2026年第一季度` 削成 `年第一季度`；
5. `_band()`：指标名换行上下各并至多 2 行。

`step4_apply_parents.py` 的闸门：**`EVIDENCE_OK` 且 `WITNESS_OK` 才登记**。

---

## 二、结果：70 → 64

| 项 | 上一轮 | 本轮 |
|---|---|---|
| 目标 | 87 | **87** |
| `EVIDENCE_OK` | 70 | **64** |
| `BLOCKED`（保留待核） | 17 | **23** |
| 登记 `parent_verifications.csv` | 70 行 | **64 行 / 27 列**（全 `SELF_CHECK` / `WorkBuddy-Agent`） |
| 独立旁证 | 无 | **`WITNESS_OK` 64 / 64**，p1/p2 均 `OK:AGREE`，不一致 **0** |
| `skipped` | — | `{not_evidence_ok: 23, version_inconsistent: 0, witness_fail: 0}` |

两侧状态：`p1 OK 73 / NOT_FOUND 14`、`p2 OK 71 / NOT_FOUND 16`。

### 撤下 9 条（全部落回 `BLOCKED`，未强塞闭合）

| 键 | 受阻侧 | 原因 |
|---|---|---|
| `SH:600143 FIN.OCF.SQ@20260630` | p2 | `NO_LABEL_ROW` / `NO_AMOUNT` |
| `SH:600320 FIN.NPDEDT.SQ@20260630` | p2 | `NO_LABEL_ROW` / `NO_AMOUNT` |
| `SH:600862 FIN.NPDEDT.SQ@20260630` | p2 | `NO_LABEL_ROW` / `NO_AMOUNT` |
| `SH:688248 FIN.NPDEDT.SQ@20260630` | p2 | `NO_LABEL_ROW` / `NO_AMOUNT` |
| `SH:603350 FIN.NPDEDT.SQ@20260630` | p1+p2 | 两侧 `NO_LABEL_ROW` |
| `SH:600960 FIN.OCF.SQ@20250630` | p2 | `NO_HEADER_ROW` / `NO_LABEL_ROW` |
| `SH:605365 FIN.OCF.SQ@20260630` | p1+p2 | `NO_HEADER_ROW` |
| `SH:600590 FIN.NPP.SQ@20251231` | p1 | `NO_HEADER_ROW` |
| `SH:688800 FIN.OCF.SQ@20251231` | p1 | `COLUMN_NOT_CONTIGUOUS(2025年度)` |

**这 9 条不是被证伪**，是「按新方法取不到指标行 × 完整期间列 × 逐位相等金额的交点」。
按裁决第 6 条，一律保留待核。

### 新增 3 条（旧方法在邻列/歧义上把它们挡在门外）

`SH:600143 FIN.REV.SQ@20250630`、`SH:600143 FIN.REV.SQ@20251231`、`SH:688320 FIN.REV.SQ@20260630`。

---

## 三、计数变化

| 指标 | 上一轮 | 本轮 | 变化 |
|---|---|---|---|
| 元数据差异未闭合（`meta_diff` open） | 8,606 | **8,611** | +5 |
| 合计核心未闭合（`open_total_core` = 元数据 + 键 405 + 值 34） | 9,045 | **9,050** | +5 |
| 含补充列（`open_total_all`） | 10,550 | **10,555** | +5 |
| `PENDING_PARENT_COMPATIBILITY` | 1,209 | **1,214** | +5 |
| `RESOLVED_SCOPE_COVERED` | 8,767 | **8,762** | −5 |
| 重述差异父输入 `YES` | 0 | **64** | +64 |

净 +5 = 撤下 9 条（其覆盖的格回到待核）＋ 登记 3 条新键 ＋ 4 条粘连数字键转可判。

**口径必须写清，不要混用**：`meta_diff` open（8,611）≠ `open_total_core`（9,050）
≠ `open_total_all`（10,555，含补充列 1,505）。前几轮报告里的「核心未闭合 8,606」
实际指 `meta_diff` open，与 `summary.json` 同名字段不同义——这是我自己造的口径混乱，本轮改正。

---

## 四、必须单独说明：有一家公司脱离 HOLD

L2 分层 **44/231/320/81/378 → 43/231/321/81/378**。
`SH:600143 金发科技`：`HOLD_PENDING_ERRATA` → `NOT_AFFECTED`。

- 它在锚定期 20260630 只有 **1 个**争议维度 `GROWTH`，来源 `SG02=M03=FIN.REV.SQ@20250630`；
  `CASH` 维度本来就干净（`M08` 依赖 `FIN.OCF.YTD` / `FIN.NPP.YTD`，**不含** `FIN.OCF.SQ`，
  所以撤下的 `FIN.OCF.SQ@20260630` 不产生新争议）。
- 本轮**新登记** `FIN.REV.SQ@20250630`：p1 `2025年半年度` 31,636,077,814.20（DOC-1CCAD03FECD76E30 第 48 页）、
  p2 `2025年第一季度` 15,665,999,806.40（DOC-4D0DD05DDB863576 第 8 页），
  两期均 `ORIGINAL`、`CONSOLIDATED`、`unit_scale=1`、`CNY`。该键唯一缺口 `PARENT_COMPATIBILITY`
  补齐 → 争议闭合 → 唯一争议维度清空。
- 该行过完整 `gap()`、过 C41 逐行重推、独立旁证 `WITNESS_OK`（两侧 `OK:AGREE`）。

**这不是我主动放行，是判据自动结果**；但它是**名单级后果**，请你独立判定是否接受。
本报告**不把它计入批次 B 成果**。其余 21 家未脱离 HOLD（仍卡在
`PENDING_SCOPE_LIMITED_METHOD` 与 `UNRESOLVED_FIELD_NOT_IN_RECORD`）。

---

## 五、本轮修掉的自查缺陷（不是裁决点，但会造假）

1. **`facts()` 未传 `col_of`**：`gap()` 用新取列函数判 YES，重算侧仍用旧判据判 NO →
   C26/C29/C14/C22 **各报 4 条假违例**（`603273/603380/688248/688400` 的
   `FIN.REV.SQ@20260630`）。改为 `parent_compatible(k, col_of=_col_of(k[0]))`，
   生产侧与重算侧同一条判据。
2. **C37 阳性对照用旧函数**：`_loc()` 仍走 `column_of_amount`，报
   `REAL_ORIGINAL_POSITIVE_REJECTED:PARENT_COLUMN_UNRESOLVED`。改走生产路径
   （`column_of_amount_aligned_ex` + `registrable_column`）。
3. **`_nz()` 定义顺序**（上一轮遗留）：已前移。

---

## 六、边界（本轮不动）

- **S04 第二轮、S05 继续不放行**；批次 C–E 与第 5 步未开始。
- **43 / 231 / 378 未冻结**（且本轮因 §四 从 44/320 变成 43/321）。
- **F32 未修**：26 份英文版年报仍在池内，采集器不校验语言。
- **`_RE_POLICY` 仍是裸「会计政策」**：正文里的「公司会计政策」也会被认成 `POLICY_CHANGE`。
- **`step4_column_witness.py` 是同一作者的第二条路径，不是独立第三方**：
  它能证明「两种实现互不矛盾」，不能替代外部复核。
- **`NO_LABEL_ROW` 的带窗是经验值**（上下各 ≤2 行、行距 ≤40pt）：跨页断行或整行脚注会漏取，
  方向安全（漏取=待核），但覆盖率有上限。

---

## 七、请你明确表态

1. `_header_cells` 的「两侧各自已是完整列名就不并」这条语义保护，是否足以支撑「不再拼邻列」？
   还有哪种版面会让它失效？
2. `canon_column` 的 `相对年|区间|累计` 三元组是否够用？`累计` 维只有「有/无」两态，
   是否漏了「年初至报告期末 vs 本年累计」这类同义/异义的区分？
3. 金额三级判据（严格命中 / Decimal 全等 / token 切分）是否仍算「完整数字边界」？
   第 ③ 级是我为「去空白粘连」加的兜底，你如果认为它太松，我按你的口径去掉。
4. `swap_column` 分母取「两侧列不等价」子集，是否可接受？若你认为应全量 64 行都拦，
   我需要另造一个等价列的注入方式（例如改一侧为 `上年同期`），请指定。
5. **`SH:600143` 脱离 HOLD** 是否接受？若不接受，请指出应当在哪一层拦住。
6. 批次 C（分季度表来源 + 半年报权益变动表「前期差错更正 0.00」行）是否放行？
