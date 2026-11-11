# S00 勘误 V5 第十轮返工汇报（报第十一轮复核）

## 0. 一句话

你第十轮 A–H 八项全部落地：极性五条新反例、父输入单位/栏目/版本/引文源、C24 数值与枚举、
C14 裁决表绑定、C38 页码与维度载体、R6 目标行列确认、自检前置失败、文本同步。
自检升到 **V10，40/40 PASS**。**仍然不宣称任何入口「不可伪造」**——只宣称你实测过的那几条路径已被堵住，
且注入用例现在断言的是**拦在哪一道**，不是「有没有拦住」。

先交代三处**与裁决数字不一致**的地方，见第 9 节。其中两处是我上一版写错、本轮实测纠正；
一处是键数从 26 变 27，原因可逐键复算。

## 1. A 项：极性五条新反例 —— 已修，反例集 22 → 30

### 1.1 五条实测（改前与你一致，改后如下）

| 输入 | 改前 | 改后 |
|---|---|---|
| `前期差错更正\n√\n不适用` | ERRATA 同时肯定、排除（假 conflict） | `excluded=ERRATA` |
| `前期差错更正\n√\n适用` | 同上 | `affirmed=ERRATA` |
| `前期差错更正□\n√适用□不适用` | 排除 ERRATA → `RESOLVED_SCOPE_COVERED` | `conflict=ERRATA`（退回原页） |
| `未发生前期差错更正，营业收入100.00元` | ERRATA 假 conflict | `excluded=ERRATA` |
| `前期差错更正对期初未分配利润影响经重新核算并经董事会和监事会审核后确认为100.00元` | 无 affirmed 也无 scoped | `affirmed=ERRATA` + `scoped=ERRATA` |

### 1.2 五条修法

1. **单符号跨行**：`_clauses.flush()` 追加判据——组内符号数 ≥2，**或**组内存在「纯符号碎片」
   （去掉符号与空白后为空，即 `√` 独占一行）即整组拼回。你给的两个变体都属第二种。
2. **含符号的原因标签**：`_is_cause_label()` 改用整串正则 `_RE_CAUSE_ONLY` 判定，
   `前期差错更正□` 仍作**主语行**留在组外，不被并进选项。
   （实现细节：原先用 `_cause_spans` 判「只有一个 span」，但 `前期差错更正` 会被
   `前期差错`(0–4) 与 `差错更正`(2–6) 重叠命中，`len(spans)==1` 恒不成立，标签认不出。）
3. **勾了适用又排除某原因**：`option_group()` 末尾追加——`YES ∈ checked` 且
   `unchecked ∩ CAUSES ≠ ∅` → 直接返回歧义（`conflict`），不再按「勾选优先」静默定值。
4. **金额不得跨主题**：`_bind_amount()` 引入 `_RE_OTHER_ITEM`（营业收入/营业成本/净利润/总资产…），
   分句出现其他报表项目词即断开与主语原因的绑定；`prev_causes` 也不再无条件下传。
5. **单原因直绑**：`causes` 只有唯一原因时，本分句金额直接绑给它，**不受 `_AMOUNT_RADIUS=24` 限制**。

`_AMOUNT_RADIUS` 不再单独承担语义绑定（你的原话），这条已在代码注释里固定。

### 1.3 存量影响：零

- `polarity_cases.py` 22 → **30 条**（五条独立反例 + 三条守护用例：不得因放宽而误合并、
  不得把无关金额绑成肯定、不得把纯标签并进组）。
- 回放 **1,007 份核验文档**全部 `evidence`：**分句变化 0 / 极性变化 0**。
- `git status` 佐证：`meta_diff.csv`、`summary.json`、`key_diff.csv`、`extra_meta_diff.csv`、
  `restricted_claims.csv` **均未被修改**（与 HEAD 逐字节一致）。这轮极性修复对存量零影响。

## 2. B 项：父输入 —— 三处实现错误已修，自动 YES 仍为 0

### 2.1 单位折算键名（你点的那处）

`gap()` 原读 `expect[side].get("unit")`，而 `_expect()` 提供的是 `unit_scale`，折算恒回退 1 倍。
现统一读 `unit_scale`，并限定金额字段只接受 `1 / 1000 / 10000`（其余返回
`SCOPE_UNIT_NOT_AMOUNT`）。`unit_paths_ok = True` 为三档直测，且**生产路径**（`build_errata_v5.py`
→ `parent_compatible()`）与自检共用同一 `gap()`，不再是「helper 有效、生产无效」。

### 2.2 栏目与版本

- `p1_column` / `p2_column`：非空且长度 ≥2（`PARENT_COLUMN_EMPTY` / `PARENT_COLUMN_TOO_SHORT`）
  → 必须是**期间列头**，正则 `_PERIOD_COL` 命中（`PARENT_COLUMN_NOT_PERIOD`）
  → 必须**出现在引文中**（`PARENT_COLUMN_NOT_IN_QUOTE`）。
- `adjust_version`：枚举只留 `ORIGINAL` / `RESTATED`（`SAME_VERSION` 免证标签已删）
  → 必须等于该父**实际 `version_used` 的归类**（`PARENT_ADJUST_VERSION_MISMATCH`）
  → 引文还须有对应标记：重述版须含「调整后/重述后/更正后」，原版**不得**含
  （`PARENT_QUOTE_WITHOUT_VERSION_MARK` / `PARENT_QUOTE_VERSION_CONFLICT`）。

### 2.3 引文源改回读原件

`build_errata_v5.py` 删除 `_pdf_text` / `_PDF_TXT`，改为 `_PDF_PAGES` + `_pdf_page(sec, doc, page)`
按**登记页物理回读**（去空白后比对）；`verify_v5.py` 同步。不再用 `results.csv.evidence` 上游摘录。
引文须同时含**目标指标名 + 期间列头 + 父数（按 `unit_scale` 折算后比对）**
（`PARENT_QUOTE_WITHOUT_TARGET_METRIC` / `PARENT_COLUMN_NOT_IN_QUOTE` / `PARENT_QUOTE_WITHOUT_PARENT_VALUE`）。

### 2.4 C37 注入链：27 环，逐环断言原因

`verification_chain` 共 **27 环（1 正例 + 26 反例）**，全部通过，且每环都有 `reject_reasons` 断言：

| 环 | 期望原因 |
|---|---|
| `with_record`（正例） | 生产路径返回 YES |
| `no_record` | 无登记记录，直接判不兼容（不进入 `gap()`，故无原因码） |
| `doc_mismatch` / `p2_doc_mismatch` | `PARENT_DOC_MISMATCH` |
| `period_mismatch` | `PARENT_PERIOD_MISMATCH` |
| `column_empty` | `PARENT_COLUMN_EMPTY` |
| `column_not_period` | `PARENT_COLUMN_NOT_PERIOD` |
| `column_not_in_quote` | `PARENT_COLUMN_NOT_IN_QUOTE` |
| `page_invalid` | `PARENT_PAGE_INVALID` |
| `quote_on_wrong_page` | `PARENT_SOURCE_UNAVAILABLE` |
| `adjust_version_invalid` | `PARENT_ADJUST_VERSION_INVALID` |
| `adjust_version_mismatch` / `adjust_version_other_side` | `PARENT_ADJUST_VERSION_MISMATCH` |
| `quote_without_parent_value` | `PARENT_QUOTE_WITHOUT_TARGET_METRIC` |
| `original_quote_with_restated_mark` | `PARENT_QUOTE_NOT_LOCATED` |
| `quote_other_metric` | `PARENT_QUOTE_WITHOUT_TARGET_METRIC` |
| `value_mismatch` | `PARENT_VALUE_MISMATCH` |
| `quote_not_located` | `PARENT_QUOTE_NOT_LOCATED` |
| `empty_scope` | `SCOPE_FIELD_EMPTY` |
| `scope_mismatch` | `SCOPE_MISMATCH_WITH_PARENT` |
| `scope_basis_missing` | `SCOPE_BASIS_MISSING` |
| `no_reviewer` / `reviewer_placeholder` | `VERIFICATION_WITHOUT_REVIEWER` |
| `no_date` | `VERIFICATION_WITHOUT_DATE` |
| `role_unmarked` | `VERIFICATION_WITHOUT_ROLE` |
| `wrong_conclusion` | `VERIFICATION_NOT_COMPATIBLE` |
| `p2_quote_missing` | `PARENT_QUOTE_TOO_SHORT` |

另有：**真实原件阳性**（`BJ:920289|FIN.NPDEDT.SQ|20260630`，两个父数均在生产路径判 YES，
不是合成源）、单位三档直测、错误栏目、页码非法、同数异义负例。

一处如实交代：`adjust_version_inconsistent`（声明两父版本不一致）这条**不可达**——
先被 per-side 的 `PARENT_ADJUST_VERSION_MISMATCH` 拦下。已改名 `adjust_version_other_side`
并改期望值，代码里注明「声明一致性检查被逐侧检查遮蔽」。

`PENDING_PARENT_COMPATIBILITY` 仍 **1,277**，自动 YES 仍 **0**。

## 3. C 项：C24 —— 你给的两个键已作为固定注入用例

### 3.1 数值：千分位终值不再落入文本分支

`_as_num()` 先去 `,` 与空白再 `float()`。你实测的绕过（保留真实页码与片段，把
`original_value_text` 换成同页上年数 **6,303,196,235.21**，在 `judgement_basis` 自述其映射到本期终值）
现在是固定用例 `same_page_other_amount`，返回 **`REVIEW_PRINTED_VALUE_NOT_SUPPORT_VALUE`**。

实现上还修了一个自己造的坑：`_genuine_review()` 的纯数值扫描会把相邻单元格粘连成
`5,667,075,612.526`（假精度），导致「同页异数」候选其实是同一个数。现改为
①NUM 分支优先取与 `value_B` 完全一致的字面串；②异数候选须同时不等于 `original_value_text`
与 `value_B` 的数值。

### 3.2 枚举：`judgement_basis` 不再承担举证

`judgement_basis` 降为描述字段，判定改走 `FIELD_RULES`：

| 类型 | 字段 | 判定 |
|---|---|---|
| `NUM` | `value_raw` / `value_before_adoption` | 印刷值折算后须等于终值 |
| `UNIT` | `unit_scale` | 只认 1/1000/10000/1000000/100000000 |
| `DATE` | `published_on` | 须可解析为日期 |
| `LITERAL` | `unit_raw` / `currency` / `evidence_label` | 须逐字出现在片段中 |
| `SELF_PAGE` | `source_page` | 页码须为该记录自身页 |

11 个**没有可核验映射**的字段一律 `REVIEW_FIELD_RULE_UNDEFINED` 留待核：
`period_source`、`slot_id`、`source_kind`、`status_reason`、`upstream_hold_fields`、
`low_base_flag`、`quarterly_inputs`、`comparability_note`、`version_used`、
`adoption_reason`、`original_document_id`。
你举的 `SH:600444|FIN.COST.YTD|20251231|period_source` 就是这套枚举注入的固定用例，
现在返回 `REVIEW_FIELD_RULE_UNDEFINED`。理由：这些值都是内部枚举/派生状态，PDF 里没有对应字面，
让自述举证等于没有举证——**宁可留待核**。

### 3.3 新增 `REVIEW_KEY_MISMATCH`

登记记录必须属于该键，不再靠「缺文档」偶然拦截。

### 3.4 13 种 + 1 种注入，全部断言原因

正例基线 `SH:600100|FIN.REV.YTD|20250630|value_raw` 被接受（`control_accepted`），
13 种注入 + 1 种枚举注入逐项断言：`RELEASE_WITHOUT_CONTENT_REVIEW` / `LEDGER_NOT_LINKED_TO_REVIEW` /
`REVIEW_KEY_MISMATCH` / `REVIEW_DOCUMENT_MISMATCH` / `REVIEW_WITHOUT_REVIEWER` / `REVIEW_WITHOUT_DATE` /
`REVIEW_ROLE_UNMARKED` / `REVIEW_WITHOUT_CONCLUSION` / `REVIEW_FRAGMENT_NOT_IN_ORIGINAL_PAGE` /
`REVIEW_PRINTED_VALUE_NOT_IN_FRAGMENT` / `REVIEW_VALUE_NOT_DECLARED` / `REVIEW_BASIS_TOO_SHORT` /
`REVIEW_PRINTED_VALUE_NOT_SUPPORT_VALUE` / `REVIEW_FIELD_RULE_UNDEFINED`，`reason_mismatch = {}`。

## 4. D 项：C14 —— 绑定正式裁决表行

引文所在行必须匹配 `^\|\s*(Q\d+)\s+([^|]+?)\s*\|(.*)\|\s*$`，且：

1. `ruling_section` = 该行「Qn 标题」（`RULING_SECTION_MISMATCH`）；
2. `ruling_verdict` 出现在该行结论单元格（`RULING_VERDICT_NOT_IN_ROW`）；
3. `ruling_key_pattern` 出现在**裁决项标题**（`RULING_ITEM_DOES_NOT_NAME_KEY`）；
4. 识别信息仍须真是本键（`RULING_KEY_MISMATCH`）。

你实测的三处绕过现在是固定用例：三项都填「大豪科技」+ 引**第 88 行**文档登记说明 →
`RULING_LINE_NOT_A_RULING_ROW`；引**第 235 行** Q1 通用条目 → `RULING_ITEM_DOES_NOT_NAME_KEY`。
9 种注入全部断言原因，`reason_mismatch = {}`；**大豪科技原裁决继续成立**（`control_accepted = True`）。

### 4.1 第十一轮复核中断前又暴露两处，已一并修掉

第一次发起第十一轮复核时，Codex 在收尾前因上下文超限中断（`Bad Request`，108,316 tokens），
**没有给出裁决**。但它中断前的探针日志留下了两条实测：

```
OTHER_KEY      None    # 把键从 FIN.REV.SQ 换成同公司的 FIN.NPDEDT.SQ，判据仍返回 None
NEGATIVE_STRING '不代表全公司验收' None   # 从结论单元格末尾截出的否定句也通过
```

两条都是真缺陷，已在同一版内修掉：

1. **裁决粒度**：`ruling_gap()` 追加 `ruled_key` 必须与待判键三元组**完全相等**
   （`RULING_RULED_KEY_MISSING` / `RULING_KEY_MISMATCH`）。
   此前只在 `check_c14` 里比对 `ruled_key`，单独调判据时同公司其他字段也能过——
   **判据必须自带绑定，不能靠调用方代劳**（这条与「查不到就跳过」是同一类错误）。
2. **结论语义**：`ruling_verdict` 须与结论单元格去掉强调符后**前缀匹配**
   （`RULING_VERDICT_NOT_IN_ROW`），且不得含否定词（`RULING_VERDICT_NEGATED`）。
   此前只查子串，于是「不代表全公司验收」这种反向表述也能当裁决结论。

改后单测：

```
CONTROL        None                    # 大豪科技原裁决仍通过
OTHER_FIELD    RULING_KEY_MISMATCH
NEG_VERDICT    RULING_VERDICT_NEGATED
NO_RULED_KEY   RULING_RULED_KEY_MISSING
```

C14 注入由 7 种增至 **9 种**，自检仍 40/40。

## 5. E 项：C38 —— 页码与维度载体双检

`scope_dims()` 追加：

- `source_page` 须匹配 `^[1-9]\d{0,3}$`（`PARENT_PAGE_INVALID`），且等于登记页
  （`SOURCE_PAGE_NE_REGISTERED_PAGE`），引文须能在该物理页定位；
- 引文须含该维度**自己的载体词** `DIM_MARKERS`：`QUARTERLY_TABLE_PROVENANCE` 要
  「分季度 / 季度主要财务数据 / 第 N 季度」，`COMPARATIVE_SCOPE` 要
  「比较 / 上年同期 / 上年年末 / 上期 / 期初 / 调整前 / 重述前」（`DIM_MARKERS` 未命中即拒）。

你实测的 `BJ:920022|FIN.NPDEDT.SQ|20250630`（供给文档 `DOC-EFCBFB68E83B84D0`）
封面片段 `Ltd.年度报告——2025——` 现在**取不到任何维度**（`rejected_quote_without_dim_marker = True`）。
12 种绕过全部被拒：错结论 / 引文不可定位 / 无审查人 / 角色未标 / 无日期 / 他文档 /
父输入维度顶替 / 目标键错 / 引文无年份 / 引文错页 / 无维度载体 / 页码非法。

如实交代两点：
- 该键合法登记时结论是 **`PENDING_CAUSE_UNCOVERED`**，不是「已覆盖」——两个来源维度被登记覆盖后，
  原因维度仍未覆盖。这比上一版「with_record = covered」更严。
- 覆盖页分别是 p.13（比较）与 p.9（季度表），已写进 `evidence_pages`。

## 6. F 项：R6 —— 目标行列、单位、版本都取自原件

`locate_amount_in_doc()` 改为按 pymupdf **词坐标**：

| 项 | 判据 |
|---|---|
| 目标行 | 金额所在行左侧词 → `row_label`，须含目标指标名；换行标签回退上下相邻行（`LOCATED_ROW_MISMATCH`） |
| 目标列 | 金额 x 区间**正上方最近**的期间列头 → `column_label`（`LOCATED_NO_COLUMN`） |
| 单位 | 金额行及上方最近的「单位：X」→ 与 `unit_scale` 做固定映射对照（AGREE / MISMATCH / NO_ORIGINAL_UNIT） |
| 调整前后 | 列头附近 ±20 行内的「调整前/调整后/重述前/重述后」 |

三条样本（S19 `BJ:920289`、S20 `SH:600008`、S21 `SH:600060`）p1/p2 **均 `LOCATED_OK`**，
并交付 `parent_p1_row` / `parent_p2_row` / `parent_p1_unit` / `parent_p2_unit` /
`parent_p1_version` / `parent_p2_version`。`_period_column()` / `_adjust_version()` 不再由文档期间与
元数据单独推导，取不到原件依据时显式写「原件未见…」。

**这条判据确实有牙**：`SH:600053|FIN.NPDEDT.SQ|20260630` 的 p1 现在判
`LOCATED_ROW_MISMATCH`（行标签未含「扣除非经常性损益」），因此它掉出 R6 池前三，
S21 顺延为 `SH:600060`——这也是抽验键数 26 → 27 的原因（见第 9 节）。

措辞纪律：「两父已定位」≠「两父核证完成」。三条样本的 `parent_compatible` 仍为
`PENDING_PARENT_COMPATIBILITY`，不据此认定兼容。

## 7. G 项：自检前置失败 —— 已改为「正例基线 + 单变量 + 断言原因」

你指出的问题是 `_with_review()` 默认造出「缺文档/缺原件」的不完整记录，错页、样板片段、
终值未声明等用例先被 `REVIEW_DOCUMENT_MISMATCH` 拦下，PASS 没验到目标门槛。

现改为：`_genuine_review()` 先构造一条**完整合规**记录（正例被接受，`control_accepted` 为断言项），
每个注入只改**一个**字段，并断言**具体拒绝原因**（`EXPECT_REASON` + `reason_mismatch`）。
C14 同理。`reason_mismatch` 为空是 PASS 的必要条件，不是「布尔通过即可」。

## 8. H 项：文本同步

- **抽验口径**：37 行 / 20 类 / **27 键**，键数写进 `sampling_v5.json:unique_keys`，报告不再手写。
- **`data/active_issue.json`**：此前有三处互相冲突（`s00_errata.self_check.version = V8`、
  `s00_errata.self_check_version = V9`、顶层 `self_check_version = V9`，另有顶层 `self_check = V10`）。
  现改为**单一维护点**：完整注入明细只放 `s00_errata.self_check`（V10），顶层 `self_check`
  只留 `{version, checks, pass, canonical}` 指针 + 说明。所有 `self_check_version` 一律 V10，
  `fault_injection_v4_mapped` 一律 7,729 / 6,617。**同一份明细维护两处必然漂移，这条已写进 note。**
- **`NOTE_TRACE_NA`**：`review.json`、`verify_v5.py`、`REPORT.md`、`handoff.md`、
  `active_issue.json` 全部改为**总量与解除量分列**：总量 9,954 条 / 631 份，已解除 8,655 条 / 630 份，
  剩余 1,299 条 / 1 份待核；并写明已解除部分同样须复审。
- **`REPORT.md`**：新增第一节「第十轮裁决的逐条落实」，原第八/九轮两节标题标注
  「历史段落（对应自检 V8/V9）」，编号整体后移；当前控制对象指向第十轮，
  `report_to_codex_round9.md` 保留历史身份但不再被引用为当前统计来源。
- **`parent_verifications.csv`**：`COLS` 新增 `version_basis`（26 → 27 列），表头已同步
  （表为空，无数据行变化）。

## 9. 与裁决数字不一致之处（主动交代）

### 9.1 抽验键数：你说的 26，本轮实测 27

逐键差集可复算：

```
旧（HEAD）26 键 → 新 27 键
新增：('SH:600060', 'FIN.NPDEDT.SQ', '20260630')
删除：无
```

原因：R6 抽样池按 `parent_orig_verified`（BOTH → ONE → NONE）排序取前三。
新词坐标定位器下 `SH:600053|FIN.NPDEDT.SQ|20260630` 判为 `ONE`
（p1 `LOCATED_ROW_MISMATCH`），掉出前三，S21 由 `SH:600060` 顶上（`BOTH`）。
样本数仍 37、风险类仍 20，只有键集合 +1。

我上一版把这条写成「R6 谓词变化导致 +1」但没给差集，本轮补上。
`review.json:not_independent` 与 `sampling_v5.json:unique_keys` 均为 27，`active_issue.json` 同。

### 9.2 C37 环数：我上一版写 25，实际 27

`review.json` 的 `verification_chain` 有 **27** 个键（1 正例 + 26 反例）。
上一版 `REPORT.md:50`、`handoff.md`、`claim_note` 写的 25 是我数漏，本轮已全部改为 27 并注明拆分。

### 9.3 `REPORT.md` 抽验回读分布：上一版 MATCH 19 / NO_PAGE 4，实测 18 / 5

按 `sampling_v5.json:page_reread` 与 `sampling_v5.csv` 逐行复算：
`MATCH 18 / PARTIAL 5 / LOCATED 2 / WEAK_LOCATE 1 / NO_PAGE_RECORDED 5 / 不适用 6 = 37`。
上一版是链路重跑前的旧值，已改。

### 9.4 `REPORT.md` 2.1 表：上一版标题写 17,009，表内合计实为 17,728

已拆成两张表：`restatement_flag` 17,009（12 行，合计 17,009，待处置 8,309）
+ 其余四列 719（5 行，未闭合 365）。两表相加 = 17,728 / 未闭合 8,674，
与 `summary.json:meta_diff.open` 一致。

### 9.5 自检版本仍是 V10，但内容在第十一轮中断后追加过两处

第一次发起第十一轮复核时 Codex 因上下文超限中断，未出裁决。中断前的探针日志暴露 C14 两处缺陷
（见 4.1），我在**同一版 V10 内**修掉并补了注入用例，没有另起 V11。
理由：V10 从未被任何一方出过裁决，不存在「已被接受的 V10」被改动的问题；
但为了避免看起来像「事后偷偷改过」，这里显式登记：
`review.json:interrupt_fixes_round11` 记录了这两条，`review.json:round10_fixes` 仍是原十条不变。

## 10. 复现

```
python build_errata_v5.py   # 台账（parent_compatible / parent_gap 走 _pdf_page）
python check_l2_v5.py       # 全池影响判定
python sampling_v5.py       # 37 行 / 20 类 / 27 键
python verify_v5.py         # 40/40 PASS → SELF_CHECK_PASS_WITH_UNRESOLVED_ITEMS
```

本轮 `verify_v5.py` 实跑输出末行：

```
40/40 PASS → SELF_CHECK_PASS_WITH_UNRESOLVED_ITEMS
```

核心数字未变：重述差异待处置 **8,309**；全表核心未闭合 **9,113**、含补充 **10,618**；
自动 YES **0**、`PENDING_PARENT_COMPATIBILITY` **1,277**；全池 44 HOLD / 231 待核证 / 378 无关联；
受限表 **407 行 / 401 个唯一差异 ID**；补充元数据 1,505 格 **0 条放行**。

## 11. 仍未做 / 不宣称

- **第 4 步批量核证、第 5 步重算分层未开始**；44 / 231 / 378 均未冻结。
- **未回读全部 PDF**：抽验 37 行覆盖 1,007 份核验文档中的 20 份。
- **不宣称入口不可伪造**：C24 / C14 / C37 / C38 都只是「当前已知绕过被堵住」，
  且与生产共用同一套判据函数，属**同源重算**，不能替代独立方法验证。
- **不改上游**：`DOC-E2BDEAB4F6274B6E` 的 `results.csv:verdict=否` 与原文相反，
  本版只登记为证据冲突。
- S04 第二轮正式验收与 S05 继续等待。

## 12. 待裁定问题

1. **11 个内部枚举字段的放行路径**。我目前一律 `REVIEW_FIELD_RULE_UNDEFINED` 留待核，
   因为 PDF 里没有对应字面。你第 165 行说「可提供原文事实 + 实际采用记录或处理日志 + 明确字段映射规则」。
   请确认这套三件套是否可作为放行依据；若是，日志的**最小字段集**是什么
   （我倾向：源文件名 + 物理页 + 表格标题/表号 + 期间列头 + 取值 + 采用时点 + 采用人）？
   没有这个最小集，我无法判断「采用日志」要写到什么程度才算证据。
2. **C37 真实原件阳性的覆盖要求**。目前只在一处（`BJ:920289|FIN.NPDEDT.SQ|20260630`）
   取得生产路径 YES。是否要求「跨文档 + 调整前后版本 + 万元折算」三者**同时**成立的样本，
   还是分项样本即可？前者在这批原件里我暂时只找到一处候选，需要额外找件。
3. **`LOCATED_ROW_MISMATCH` 的处置归属**。`SH:600053@20260630` 的 p1 行标签不含目标指标名。
   这应视为「定位失败、须回读原页」，还是「原件行标签与目标指标确实不同、须改判父数归属」？
   两种处置会给出不同的 `parent_orig_verified`，也影响抽验口径，请你定。
4. **抽验键数变化的登记方式**。26 → 27 我已按「差集 + 原因」登记。是否需要把每次抽样键集合
   的差集固定成一份可 diff 的文件（如 `sampling_keys_diff.csv`），以便跨轮比对？
   若需要，我下一轮加上。
