# S00 勘误台账 V5 报告（第十二轮返工后）

- 目录：`runs/issues/S00/errata_20261111_v5/`
- 性质：**SELF_CHECK**，不是独立验收
- 自检版本：**V12**，41/41 PASS → `SELF_CHECK_PASS_WITH_UNRESOLVED_ITEMS`
- 本轮触发：Codex 第十二轮复核 `RETURN_FOR_REWORK`（G 项通过，A、B、C、D、E、F、H 七项不通过；不放行 S04 第二轮、不放行 S05）
- 复现顺序：`python build_errata_v5.py` → `python check_l2_v5.py` → `python sampling_v5.py` → `python replay_polarity_v5.py` → `python verify_v5.py`

---

## 一、第十二轮裁决的逐条落实

第十二轮裁决的结论是：**G 项通过**，A、B、C、D、E、F、H 七项不通过。
与上一轮不同的是，本轮七项里有六项**不是「判据不够严」而是「判据判错了方向」**——
Codex 每一处都给了真实语料上的反例，不是合成语料。

### 1.1 A 项：极性「新主语」改按中心语判，并承认判据确实会触发

上一轮用「金额左侧 10 字以名词收尾」判新主语，Codex 用三句话打穿：

| 输入 | 上一轮判定 | 应为 | 原因 |
|---|---|---|---|
| `…其中营业总收入金额为100.00元` | 续写 | 新主语 | 词尾是「为」，被当成功能词 |
| `…其中营业总收入确认的金额100.00元` | 续写 | 新主语 | 词尾是「金额」，被当成计量单位 |
| `…其中营业总收入合计100.00元` | 续写 | 新主语 | 词尾是「合计」，被当成汇总词 |
| `…影响0.00元，影响增加100.00元` | 新主语 | 续写 | 词尾是「增加」，被当成动词 |

改为**取中心语**：用闭集功能词/动词/量词表（`_TAIL_STRIP`）从右往左反复剥离，
剩下的名词片段即中心语；中心语属权益项目（`_RE_SCOPED_ITEM`）/原因短语（`_CAUSE_ANY`）/
治理参与方（`_RE_PROCEDURE`）/空 → 判续写，否则判新主语。四条反例分别记为 ⑯–⑲，
另加 ⑳ 守护「同分句原因就近命中时不按 new_subj 否定」。

**关于 `tgt` 分支**：上一轮汇报说「已给 `tgt` 分支也加了 `new_subj`」，实际代码没加。
本轮明确：**这是有意的，不加**——`tgt` 表示本分句内原因词就近命中，此时金额无论挂在
哪个项目上都能证明该事件发生；`new_subj` 只约束 `single` / `prev_causes` 两条跨分句继承分支。
docstring 第 6 条写明了这个区别，汇报也改成与代码一致。

**关于「从未触发」**：上一轮汇报写「新判据在真实证据上从未触发」，Codex 插桩显示
`_new_subject` 被调用 88 次、判真 44 次，该说法无据。本轮把计数器直接打进
`replay_polarity_v5.json`，当前值：

```
documents 1007 / clause_changed 0 / polarity_changed 0
new_subject_calls 88 / new_subject_true 0 / new_subject_true_nonzero 0
head_nouns {"附注：由于重大会计差错更正影响期初未分配利润": 44, "同一控制合并范围变更": 44}
```

即：判据在 1,007 份存量证据上被调用 88 次，中心语只出现两种，**都是原因短语**。
补词表前那 44 次「判真」全部来自 `同一控制合并范围变更`——它是原因短语，只是没写成
`同一控制下企业合并`，被旧词表漏掉，于是被误判成新主语（该条不影响结论，因为同分句
原因词就近命中，走 `tgt` 分支）。补词表后判真 0 次。**结论只能说「对存量证据的极性结果
无影响」，不能说「判据从未触发」；判据是否承重由 38 条反例证明，不由回放证明。**

### 1.2 B 项：父输入栏目改「带状态返回 + 目标行绑定 + 期间语义类」

Codex 三条实测：

1. 同页有两个相同金额时，`column_of_amount` 取第一个，可能取到别的行；
2. 登记列头「本期发生额」与原件列头「本期数」被判为不同列，误拒；
3. 扫描页（无文本层）应记「待回读」，不是「不可解」。

改法：`column_of_amount_ex()` 返回 `(列头, 金额, 状态)`，状态五态
`OK / NO_WORDS / NO_AMOUNT / AMBIGUOUS / NO_COLUMN`；`label` 参数把金额**绑定到目标行**
（词坐标 + 指标名同行），同页重复金额记 `AMBIGUOUS` 而不是取第一个；
`cols_equivalent()` 先按**期间语义类**比对（`PRIOR_YEAR_SAME / YEAR_OPEN / PERIOD_END / CURRENT`），
再退回子串，「本期发生额 vs 本期数」归同一类；`NO_WORDS` 记
`PARENT_COLUMN_NEEDS_REREAD`（待回读），不再与「不可解」混为一谈。
C37 注入链由 29 环扩到 **35 环**，新增 6 环正是上述三条：`real_column_needs_reread`、
`real_column_ambiguous`、`duplicate_amount_ambiguous`、`duplicate_amount_row_bound`、
`column_synonym_ok`、`column_antonym_rejected`。

### 1.3 C 项：证据标签要「数量」、SELF_PAGE 要「目标行」、币种要「受控映射」

- `evidence_label` 原先只要 20 字内有数字就放行，于是「见第12页附表说明」里的 12 冒充金额。
  现在要求「标签 + 20 字内**数量**」（带单位或带小数），且该片段不得命中页码/表号
  正则（`_RE_PAGE_REF`），否则记 `REVIEW_LITERAL_NUMBER_IS_PAGE_REF`。
- `SELF_PAGE` 原先取「该金额在原件里最早出现的页」，页眉重复金额会让第 1 页抢走第 2 页
  的真实表格行。现在改为**目标行定位**：词坐标 → 指标名同行 → 该金额 → 列头；
  无词坐标时退回「同页同时出现指标名与该金额」。`NO_AMOUNT / AMBIGUOUS / NO_COLUMN`
  各自有拒绝原因。
- `currency='CNY'` 遇「记账本位币：人民币」被拒属误拒。新增 `CURRENCY_ALIASES`
  受控映射（CNY/HKD/USD 各自一组同义写法），只在组内互认，不做模糊匹配。

### 1.4 D 项：裁决清单自身也受检

上一轮新增 `ruling_scope.csv` 挡住「把 key 和 ruled_key 一起改写」，但 Codex 指出：
**清单里的 `ruling_file_sha256` 改成 64 个 0 照样生效**——清单本身可被改写，等于授权范围可被改写。

新增 `scope_row_ok(section, ent)`：清单行的 `ruling_file` 必须存在、`ruling_file_sha256`
必须与文件实算一致（`RULING_SCOPE_FILE_UNBOUND / _MISSING / _HASH_MISMATCH`），
且须与登记条目自报的裁决文件/哈希一致（`RULING_SCOPE_FILE_DISAGREES`）。
C14 注入由 10 种增至 **13 种**：新增 `scope_file_sha_disagrees`（登记条目与清单不一致）、
`scope_row_hash_tampered`（清单行哈希被改）、`scope_allowed_key_narrowed`（见下）。

**关于「换成另一个已登记 section」**：真实清单只有 1 个 section，这个攻击在真实数据上
构造不出来——换了 section，裁决行文本就对不上，会先被 `RULING_SECTION_MISMATCH` 拦下，
测不到白名单本身。本轮改为直接改清单内容：把该 section 的 `allowed_key` 换成**同公司
另一个已登记字段**，再单独调 `ruling_gap`，必须返回 `RULING_KEY_NOT_IN_SCOPE`。
这在效果上等价于「允许范围被换成了别的条目」，且不依赖自报字段。

### 1.5 E 项：窗口规则下沉，远距离拼接与页脚载体都不算覆盖

Codex 两条实测：把维度载体词放在 501 字之外仍算同窗口；页脚写「分季度见附表」也算覆盖。
上一轮的窗口规则只活在 `verify_v5._dim_window` 里，`scope_dims()` 用的是另一套三词检查。

本轮把规则**下沉到 `parent_verify.dim_window_ok()`**，`scope_dims()` 与自检共用同一份：
三词（指标名 + 该行具体期间 + 维度载体）跨度 ≤ `_MAX_DIM_SPAN = 160`，
且载体词所在句不得是注释/页脚（`注：/附注/脚注/见附表/附表见/页脚/见附录/详见`）。
C38 注入由 12 种增至 **14 种**，新增 `rejected_quote_marker_too_far`、
`rejected_quote_footnote_marker`。

### 1.6 F 项：抽样键集变更的退出归因

Codex 实测：`sampling_keys_diff.csv` 把 `SH:600060|FIN.NPDEDT.SQ|20260630` 的退出原因
写成「不再命中判据」，但该键**仍满足** `_r6_pred`，实际退出原因是排序/名额截取。
另外汇报写「新增 600143 两父数均定位」，而字段 `parent_amount_located` 实为 `ONE`。

改法：

- 入选判据从抽样循环里的匿名 lambda 提为**具名谓词**（`_pred_r1` … `_pred_r10`、`_r6_pred`），
  抽样与 diff 共用同一份——上一轮的教训「阈值只能写在一处」在这里同样适用。
- `REMOVED` 必须归到四类之一：`LEDGER_KEY_GONE`（台账无该键）/ `PREDICATE_FALSE`
  （键在台账但判据不再成立）/ `RANK_CUT`（判据成立但被同公司去重、候选池上限 14、
  评分取前 3 截掉）/ `UNKNOWN`（判据未登记，须人工看，不得默认成前两类）。
- 归因**自证**：`RANK_CUT` 必须谓词为真、`PREDICATE_FALSE` 必须谓词为假、
  `LEDGER_KEY_GONE` 必须台账无该键，结果写进 `sampling_v5.json:keys_diff.exit_code_selfcheck`，
  并由 C31 纳入 PASS 条件。
- R6 样本说明按 `parent_amount_located` 的 `BOTH / ONE / NONE` **逐字对应**：
  `BOTH` → 两个父数均已定位，`ONE` → 仅一个定位、另一个未定位（不得记作两父均已定位），
  `NONE` → 均未定位。600143 现在写作 `ONE`。

当前 diff：28 行 = KEPT 26 / ADDED 1（`SH:600143|FIN.NPP.SQ|20260630`）/
REMOVED 1（`SH:600060|FIN.NPDEDT.SQ|20260630`，`exit_code = RANK_CUT`）。

### 1.7 H 项：状态文件改成单一写者，且不再复述任何计数

Codex 连续两轮都抓到 `data/active_issue.json` 里留着上一版的数字：
`s00_errata.checks` 仍写着「V10：C34 30 条反例；C37 27 环；C14 9 种」，
`sampling.unique_keys_note` 仍写着「新增该键、无删除」。

根因不是「忘改」，是**同一份摘要有两个写者**。本轮：

- 派生字段（`status` / `self_check_version` / `self_check` / `checks` / `sampling` /
  `round` / `decision` / `report_to_codex`）改由 `verify_v5.write_status()` **唯一写出**；
- 写出的内容只含**指针与版本号**，不再复述条数、环数、注入种数、键数与增删结论；
- 新增 **C39**：旧计数口径必须消失（`条反例|环 =|种伪造|种绕过|PASS（V` 一律不许出现）、
  版本必须等于本次、`locator_version` 必须与 `sampling_v5.json` 一致、状态必须含
  `AWAITING_RECHECK_13`。

连跑两次 `verify_v5.py`，`data/active_issue.json` 与 `review.json` 的 md5 完全相同（幂等）。

### 1.8 数字变化（与裁决口径的差异）

| 项 | 第十一轮（V11） | 第十二轮（V12） |
|---|---|---|
| 自检 | 40/40 | **41/41**（新增 C39） |
| C34 反例 | 33 条 | **38 条**（⑯–⑳） |
| C37 注入链 | 29 环 | **35 环** |
| C14 注入 | 10 种 | **13 种** |
| C38 注入 | 12 种 | **14 种** |
| C24 注入 | 13 键 + 1 枚举 | 13 键 + 1 枚举（未变） |
| 抽样定位器 | V11 | **V12** |
| 抽样键集 | 27 键 | 27 键（KEPT 26 / ADDED 1 / REMOVED 1） |

`meta_diff.csv` 与 `summary.json` 在本轮全链重跑后**逐字节不变**（md5 前后一致），
说明本轮改的都是判据与校验，没有动数据。

---

## 二、第十一轮裁决的逐条落实

第十一轮裁决的结论是：**H 项（文本与状态同步）通过**，A–G 七项不通过——每一处都能被
一句合成语料或一条真实原件绕过。本轮七项全部改的是**判据本身**，不是补一条反例。

### 1.1 A 项：极性「结构性新主语」

裁决给的绕过：

```
前期差错更正对期初未分配利润影响0.00元，其中营业总收入100.00元
```

修前把 `100.00` 承接成「ERRATA 肯定」——因为同一分句里出现原因词，后续金额默认继承主语。
修前两轮的做法是**扩充报表项目词表**（`_RE_OTHER_ITEM`），这是无底洞：换个词表外的项目就又漏。

本轮改判据：**金额左侧紧跟片段以名词收尾即为新主语**。

- 取金额起始位置左侧 10 字窗口；
- 命中受影响权益项目词（`未分配利润`/`所有者权益合计` 等）→ 不是新主语，继续承接；
- 以动词/量词/标点/数字收尾（`为`/`计`/`影响`/`元`/`，`/`\d`）→ 不是新主语；
- 剥掉「其中/该/上述/本期/元/数字」等填充后**仍余 ≥2 字** → 判为新主语，不承接前一分句。

反例集 30 → **33 条**，新增：

| 反例 | 修前 | 修后 |
|---|---|---|
| ⑭ 词表**外**项目切换（`其中营业总收入100.00元`） | `affirmed=ERRATA` | `set()`（不承接） |
| ⑭ 词表**内**项目切换（`其中营业收入100.00元`） | `set()` | `set()`（守护，防止改判过头） |
| ⑮ 权益项目续写（`对所有者权益合计影响100.00元`） | — | 仍 `scoped=ERRATA`（守护，权益项目不算新主语） |

`_RE_OTHER_ITEM` 里原含「所有者权益合计」，会让 ⑮ 丢失 scoped，已剔除——权益项目是
**受影响对象**，不是「另一个项目」。

**A/B 回放（新增，`replay_polarity_v5.py`）**：把 `_new_subject` 换成恒 `False`（＝第十轮行为）
作对照，对 1,007 份核验证据各跑一遍 `analyse`，逐条比对分句与四个极性集合：

```
{"documents": 1007, "clause_changed": 0, "polarity_changed": 0}
```

即：**新判据在真实证据上从未触发**。这不是「修好了」，而是「修的是一个只存在于合成语料里的绕过」——
必须如实写明，不能拿零变化当成绩。回放结果已纳入 C34 的 PASS 条件（`REPLAY_MISSING` /
`REPLAY_CHANGED_EXISTING_EVIDENCE` 均判 FAIL），`meta_diff.csv` 与 `summary.json` 也仍逐字节未变。

### 1.2 B 项：父输入栏目改按词坐标核实

裁决给的绕过：真实阳性 `BJ:920289` 的 `p1_column` 登记为「上年同期」，而金额实际落在
「本期」列——`p1_column` 只被当成「必须出现在引文里的字符串」，没人核对它是不是该金额所在的列。

本轮新增 `parent_verify.page_words()` + `column_of_amount()`：

1. 从原件该页取出带坐标的词；
2. 找到与登记金额数值相等的词，取它的 x 中心；
3. 向上找**同 x 区间**、非数值、最近一行的词 → 该金额的**实际列头**；
4. 归一化（去空格/`*`/`_`）后与登记的 `p1_column`/`p2_column` 比对。

拒绝原因新增两个：`PARENT_COLUMN_MISMATCH`（列头对不上）、`PARENT_COLUMN_UNRESOLVED`
（取不到列头——宁可判不可解，也不放过）。C37 注入链 27 → **29 环**（新增两条**真实原件**负例：
错列、列头不可解）。

### 1.3 C 项：C24 文本字段按标签绑定、SELF_PAGE 独立定位

裁决给的三条绕过：

| 绕过 | 修前 | 修后 |
|---|---|---|
| `unit_raw` 填 `元`，片段里只要有 `2025` 就过 | `evidence_label` 与金额无关也能过 | `unit_raw` 须命中 `单位\s*[:：]?\s*(?:人民币)?元`；`currency` 须命中 `(币种\|货币\|记账本位币)\s*[:：]?\s*CNY` |
| `evidence_label` 随便写 | 只要片段含数字即过 | 须「标签 + 紧随其后 20 字内出现数字」 |
| `SELF_PAGE` 只比两个**自报**页码 | `original_page == source_page` 即过 | 独立定位：该行金额在原件里**最早出现**的页，必须等于登记页（`REVIEW_SOURCE_PAGE_NOT_FIRST_OCCURRENCE`） |

没有标签的文本字段不再走「自述举证」分支，一律 `REVIEW_FIELD_RULE_UNDEFINED` 留待核。

### 1.4 D 项：裁决适用范围独立维护

裁决给的绕过：同时改写 `key` 与 `ruled_key`，两者相等，于是「借用」原裁决。

修前 `ruled_key == key` 是**自报对自报**，必然自洽。本轮新增独立文件
`ruling_scope.csv`（`ruling_section → allowed_key`），裁决必须同时满足：

- `ruled_key` 精确等于待判键（`RULING_KEY_MISMATCH`）；
- 该键在 `ruling_scope.csv` 登记范围内（`RULING_KEY_NOT_IN_SCOPE`）；
- section 在清单里有登记（`RULING_SCOPE_NOT_LISTED`）。

C14 注入 9 → **10 种**，新增「`key` + `ruled_key` 同时改写」→ `RULING_KEY_NOT_IN_SCOPE`。
注入表改为一张 `_C14_MUTS` 管住「注入名 → 改法 → 预期原因」，键集合与预期原因集合同源。

### 1.5 E 项：C38 维度证据要求「指标名 + 具体期间 + 载体」

裁决给的绕过：`_find_dim` 找到的 COMPARATIVE_SCOPE 阳性是

> 经营计划2025年，公司成功登陆北京证券交易所……报告期初比较

一段经营叙述，既没点出目标指标，也没点出该行的具体期间。

本轮 `_dim_window()` 要求同页同窗口同时出现：目标指标名、该行**具体期间表述**
（`_period_tokens`：`20250630 → 半年度/上半年/6月30日/1-6月/…`）、维度载体词，
且窗口含该行年份。窗口下界扩到包含「离指标名最近的期间表述」，否则下游 `scope_dims`
会因引文不含期间而判「未覆盖」（本轮修 C38 时实际踩到，已一并修正）。

### 1.6 F 项：R6 词坐标（断行与别列）

| 问题 | 修法 |
|---|---|
| S21 的「调整前」来自页内**别列** | 版本标记只取与金额 x 区间重叠的词（`x1 > ax0-2 and x0 < ax1+2`） |
| 600053 是**断行**误判（标签被折成两行） | 向上最多回看 3 行逐行拼接，直到出现目标指标名；金额行只有部分标签时把上一行补进来再判 |

### 1.7 G 项：C24 注入断言改严

裁决原文：注入键集合与预期原因键集合存在缺口；`no_review` / `unbound_digest` 把原因字符串
**直接写进结果元组**（断言的是「我以为拦在哪」）；`fragment_wrong_page` 没进 `EXPECT_REASON`；
`if k in EXPECT_REASON` 让未登记或拼错的键**静默跳过**；枚举用例只要求拒绝布尔值。

本轮：

1. `no_review` / `unbound_digest` 改为走 `extra_leaks` 全链，**捕获实际拒绝原因**
   （`_leak_with()` 显式决定登记表里有没有这条记录）；
2. `fragment_wrong_page` 纳入预期原因表；
3. `set(inj) == set(EXPECT_REASON)` **严格相等**，`key_gap` / `key_extra` 任一非空即 FAIL；
4. 条件型注入（样板片段、同页异数）构造不出对照物时记 `caught=None` 并进 `not_exercised`，
   判失败——不再用 `(True, "NO_BOILERPLATE_FOUND")` 蒙混成通过；
5. 枚举注入把 `REVIEW_FIELD_RULE_UNDEFINED` 纳入 PASS 条件（`injection_enum_ok`）。

结果：`injection_keys_equal_expect = True`、`expect_reason_keys = 13`、
`key_gap = []`、`key_extra = []`、`reason_mismatch = {}`、`not_exercised = {}`。

顺带修了一处**归因错误**：`generic_ruling_item` 实际拦在 `RULING_SCOPE_NOT_LISTED`
（`Q1 document_id 匹配` 不在 `ruling_scope.csv`），而不是 `RULING_ITEM_DOES_NOT_NAME_KEY`；
后者由 `key_pattern_other_company` 单独覆盖（那一项的 section 是已登记条目）。

### 1.8 H 项（维护意见）与 `sampling_keys_diff.csv`

- `active_issue.json` 顶层 `self_check` 已降为**指针**（`canonical: s00_errata.self_check`），
  不再维护两份明细——同一份摘要写两处必然漂移（本轮已因此出现 V8/V9/V10 三处版本冲突）。
- 新增 **`sampling_keys_diff.csv`**：抽样键集相对上一交付版（V10）的 `ADDED` / `REMOVED` /
  `KEPT` 逐键留痕，字段为 `status, key, security_id, field_id, period_key, baseline_version,
  baseline_sample_id, baseline_risk_type, current_sample_id, current_risk_type, reason,
  locator_version, baseline_sha256, current_sha256`。基线冻结在 `sampling_keys_baseline.csv`。
  本轮结果：**KEPT 26 / ADDED 1 / REMOVED 1**（`SH:600143|FIN.NPP.SQ|20260630` 进、
  `SH:600060|FIN.NPDEDT.SQ|20260630` 出，原因逐行写在 `reason` 列）。

### 1.9 数字变化（与裁决口径的差异）

| 项 | 裁决时 | 本轮 | 说明 |
|---|---|---|---|
| C37 注入链 | 27 环 | **29 环** | 新增两条真实原件负例（错列 / 列头不可解） |
| C14 注入 | 9 种 | **10 种** | 新增 `key`+`ruled_key` 同时改写 |
| C24 注入 | 13 种 + 枚举 1 | **13 键（严格对齐）+ 枚举 1** | 键集合与预期原因集合相等 |
| 极性反例 | 30 条 | **33 条** | 新增 ⑭×2、⑮ |
| 抽验 | 37 行 / 20 类 / 27 键 | **同** | `sampling_keys_diff.csv` 里 1 进 1 出，键数不变 |
| 自检 | V10 40/40 | **V11 40/40** | `meta_diff.csv` / `summary.json` 逐字节未变 |

---

## 三、第十轮裁决的逐条落实（历史段落，对应自检 V10）

第十轮裁决的结论是：A 项上一轮指定整改通过（22 条反例全过、1,007 份证据零变化），
但**新增边界测试不通过**；B/C/D/E/F 五处入口仍可接受伪造或形式化依据；G 项自检存在
「前置失败导致空过」；H 项文本未彻底同步。

### 1.1 A 项：极性五条新反例

| 反例 | 修前 | 修后 | 修法 |
|---|---|---|---|
| `前期差错更正\n√\n不适用` | ERRATA 同时肯定、排除（假冲突） | `excluded=ERRATA` | `_clauses` 追加「组内有纯符号碎片即合并」 |
| `前期差错更正\n√\n适用` | 同上 | `affirmed=ERRATA` | 同上 |
| `前期差错更正□\n√适用□不适用` | 排除 ERRATA → `RESOLVED_SCOPE_COVERED` | `conflict=ERRATA`（待核） | `_is_cause_label` 允许「原因词 + 符号」仍作主语行；`option_group` 追加「勾了适用又排除某原因」判歧义 |
| `未发生前期差错更正，营业收入100.00元` | ERRATA 假冲突 | `excluded=ERRATA` | `_bind_amount` 识别报表项目切换，不再把无关金额承接为主语肯定 |
| `前期差错更正对期初未分配利润影响经重新核算并经董事会和监事会审核后确认为100.00元` | 无 affirmed 也无 scoped | `affirmed=ERRATA` + `scoped=ERRATA` | 单原因分句金额直绑，不再受 24 字半径限制 |

`_AMOUNT_RADIUS` 不再单独承担语义绑定；`prev_causes` 也不再让后续所有金额持续继承原因
（须以续写词/权益项目/金额起句为前提，且本分句不得出现其他报表项目词）。
无法唯一解释的选项组一律保留 `conflict` 交回原页。

反例集由 22 条增至 **30 条**（新增五条独立反例 + 三条守护用例）〔第十一轮增至 33 条，见第一节 1.1〕。
对 1,007 份证据回放：**分句变化 0、极性变化 0**，`meta_diff.csv` 与 `summary.json`
逐字节未变——本轮极性修复对存量零影响。

### 1.2 B 项：父输入核证

1. **单位折算键名**（`parent_verify.py:233`）：原读 `expect[side].get("unit")`，而
   `_expect()` 提供的是 `unit_scale`，折算恒回退 1 倍。真实原件
   `187,875.40 万元 = 1,878,754,000 元` 会被正确引文**拒绝**。现统一改读 `unit_scale`，
   并限定金额字段只接受 `1 / 1000 / 10000` 三档（`SCOPE_UNIT_NOT_AMOUNT`）。
2. **栏目与版本**：`p1_column` 须是**期间列头**（含年份或本期/上期/期末…），且必须
   出现在引文里（`PARENT_COLUMN_NOT_PERIOD` / `PARENT_COLUMN_NOT_IN_QUOTE`）；
   `adjust_version` 须等于该父**实际 `version_used` 的归类**（ORIGINAL / RESTATED），
   引文还须有对应标记（重述版须含「调整后/重述后/更正后」，原版不得含）。
   `SAME_VERSION` 这个免证标签已删除。
3. **引文源**：`build_errata_v5.py` 与 `verify_v5.py` 均改为按登记页回读原件
   （`_pdf_page`），不再用 `results.csv.evidence` 上游摘录；引文必须落在登记页上，
   且须同时含**目标指标名 + 期间列头 + 父数**。

C37 注入链 **27 环（1 正例 + 26 反例）**〔第十一轮已扩到 29 环，见第一节 1.2〕，逐环断言具体拒绝原因；另有真实原件阳性对照（生产路径判 YES）、
单位三档直测、错误栏目、页码非法、同数异义负例。自动 YES 仍为 **0**，
`PENDING_PARENT_COMPATIBILITY` 仍为 **1,277**。

### 1.3 C 项：C24 内容审查

- `float("5,667,075,612.52")` 抛错落入文本分支的漏洞已修：先去千分位逗号再比较；
  同一页的上年数冒充本期终值不再过关（`REVIEW_PRINTED_VALUE_NOT_SUPPORT_VALUE`）。
- `judgement_basis` **不再作为证据**：改为字段规则表
  `FIELD_RULES`（NUM / UNIT / DATE / LITERAL / SELF_PAGE）。
- 11 个没有可核验映射规则的字段（`period_source`、`slot_id`、`source_kind`、
  `status_reason`、`upstream_hold_fields`、`low_base_flag`、`quarterly_inputs`、
  `comparability_note`、`version_used`、`adoption_reason`、`original_document_id`）
  一律 `REVIEW_FIELD_RULE_UNDEFINED`，**留在待核**——它们的值都是内部枚举/派生状态，
  PDF 里没有对应字面，也没有可回放的采用日志；让自述举证等于没有举证。
- 新增 `REVIEW_KEY_MISMATCH`：登记记录必须属于该键，不再靠「缺文档」偶然拦截。

### 1.4 D 项：C14 裁决绑定

引文所在行必须是**正式裁决表行**（`| Qn 标题 | 结论 |`），且：

1. `ruling_section` 必须等于该行的「Qn + 标题」；
2. `ruling_verdict` 必须出现在该行结论单元格；
3. `ruling_key_pattern` 必须出现在**裁决项标题**里（通用条目如「Q1 document_id 匹配」
   不得用于解除单键）；
4. 识别信息仍须真是本键（代码/简称/本键文档 ID）。

Codex 第十轮的实测绕过（三项都填「大豪科技」+ 引第 88 行文档登记说明）现在返回
`RULING_LINE_NOT_A_RULING_ROW`。大豪科技原裁决继续成立（正例对照通过）。

第十一轮复核中断前，日志又暴露两处，已一并修掉：

5. **裁决粒度**：`ruling_gap()` 追加 `ruled_key` 必须与待判键三元组**完全相等**
   （`RULING_RULED_KEY_MISSING` / `RULING_KEY_MISMATCH`）。此前只在 `check_c14` 里比对，
   单独调判据时把键换成同一公司的其他字段（`FIN.REV.SQ` → `FIN.NPDEDT.SQ`）仍返回 `None`。
   判据必须自带绑定，不能靠调用方代劳。
6. **结论语义**：`ruling_verdict` 须与结论单元格去掉强调符后**前缀匹配**
   （`RULING_VERDICT_NOT_IN_ROW`），且不得含否定词（`RULING_VERDICT_NEGATED`）。
   此前只查子串，从同一格末尾截出「不代表全公司验收」即可通过。

C14 注入由 7 种增至 **9 种**〔第十一轮增至 10 种，见第一节 1.4〕，逐项断言原因，`reason_mismatch = {}`。

### 1.5 E 项：C38 来源维度

`scope_dims` 追加两条：`source_page` 必须是正整数且引文能在**该物理页**定位；
引文必须点出该维度自己的证据载体（分季度表来源须含「分季度/季度主要财务数据/第 N 季度」，
比较范围须含「比较/上年同期/期初/调整前」）。封面片段 `Ltd.年度报告——2025——`
不再同时取得 `COMPARATIVE_SCOPE` 与 `QUARTERLY_TABLE_PROVENANCE`。

### 1.6 F 项：R6 目标行列确认

`locate_amount_in_doc` 改为按 pymupdf **词坐标**判定：

- 行：金额所在行左侧词 → `row_label`，须含目标指标名；指标名换行时回退上下相邻行的左侧词；
- 列：金额 x 区间正上方最近的期间列头 → `column_label`；
- 单位：金额行及其上方最近的「单位：X」→ 与 `unit_scale` 做固定映射对照；
- 调整前后：列头附近 ±20 行内的「调整前/调整后/重述前/重述后」。

三条 R6 样本（S19 `BJ:920289`、S20 `SH:600008`、S21 `SH:600060`）的两个父数
现在都是 `LOCATED_OK`，并交付目标行、期间列头、单位对照与调整版本标记。
`_period_column` / `_adjust_version` 不再由文档期间与元数据单独推导，取不到原件依据时
显式标注「原件未见…」。

### 1.7 G 项：自检前置失败

C24 的 13 种注入 + 1 种枚举注入全部改为「以完整正例为基线、每次只改一个条件」，
并逐项断言拒绝原因（`reason_mismatch` 为空才算 PASS）。C14 的 7 种注入同样断言原因。

### 1.8 H 项：文本同步

- 抽验计数改为「37 行 / 20 类 / 27 键」，并写入 `sampling_v5.json` 的 `unique_keys`
  字段（不再手写）。上版为 26 键：R6 抽样谓词改用新定位器后第三条样本由
  `SH:600053` 变为 `SH:600060`，键集合 +1。
- `data/active_issue.json` 的嵌套 `self_check` 已改为 V10，`fault_injection_v4_mapped`
  改为 7,729 / 6,617。
- `NOTE_TRACE_NA` 改为**总量与解除量分列**：总量 9,954 条 / 631 份，已解除 8,655 条 /
  630 份，剩余 1,299 条 / 1 份待核；已解除部分同样须复审。
- 本报告第二节起为第八轮及更早的历史段落，保留原编号与原文，仅在其标题上标注历史身份。

---

## 四、第九轮裁决的逐条落实（历史段落，对应自检 V9）

第九轮裁决的结论是：三协电机整改通过，但**极性仍有误放行反例**，父输入 / 来源维度 /
C24 / C14 的新入口仍可接受伪造依据，R6 尚未交付两个实际累计父数的完整核证。

### 1.1 A 项：三协电机 —— 本次指定整改通过

复算 `DOC-E2BDEAB4F6274B6E`：四选项行判 `excluded=POLICY_CHANGE` / `affirmed=ERRATA`；
B 中直接供给 15 行，15 条重述差异全部 `UNRESOLVED_EVIDENCE_CONTRADICTS`；
`cell_diff` / `key_diff` / `extra_meta_diff` / `restricted_claims` 对该文档的直接引用均为 0。
本轮未再改动该路径，C34 的对应反例仍通过。

**措辞修正**：所谓「传播到此为止」只覆盖**本次核对的直接引用与已实现依赖范围**，
不覆盖锚定期回退、上游准入等尚未检查的间接路径。上游错误判定仍须修正，
重开不等于来源已改正。

### 1.2 B 项：极性三条独立反例 —— 本轮修复

| 独立测试 | 修复前 | 修复后 |
|---|---|---|
| 四选项行中每个 `□` 后插换行（两种变体） | `excluded=ERRATA` / `affirmed=POLICY_CHANGE` → 误放行 | `affirmed=ERRATA` / `excluded=POLICY_CHANGE`，与单行一致 |
| `前期差错更正对期初未分配利润影响0.00元及对净资产影响100.00元` | 只有 `scoped`，丢失事件肯定 | `affirmed=ERRATA` + `scoped=ERRATA` |
| `前期差错更正` 换行 `□适用√不适用，对期初未分配利润影响0.00元，对净资产影响100.00元` | 排除 ERRATA、无冲突 → 误放行 | `conflict=ERRATA` → `UNRESOLVED_POLARITY_CONFLICT` |

三处根因与改法：

1. **选项组被换行切碎**（`evidence_scope.py` 的 `_clauses`）。原先换行先被 `_CLAUSE_SPLIT`
   切成分句，`□` / `会计政策变更 √` / `会计差错更正 □` 各自还能解出一套自洽但**反向**的
   取值。现先把「含 ≥2 个符号」的连续碎片拼回一个选项组再解析；**纯原因标签**
   （`前期差错更正` 等）必须留在组外——否则符号左侧也能解出一套自洽取值，与右侧解
   冲突而假判歧义（这一条是本轮回归时实测出来的）。
2. **零值压掉非零值**（`_bind_amount`）。原 `nonzero = 有金额 and not 零值` 把整句归一，
   同句只要出现一个 `0.00元` 就把 `100.00元` 一起判成零值。现改为**逐个金额**判定：
   每个金额各自就近绑定原因，零值只记 `scoped`，非零值另记 `affirmed`。
3. **已有 excluded 压掉后续肯定**（`_bind_amount`）。原 `t not in excluded` 让勾选
   「√不适用」静默盖掉后面的非零金额。现撤销该条件：勾选否定与金额肯定并存时
   保留 `conflict`，由 `judge()` 判 `UNRESOLVED_POLARITY_CONFLICT` 退回原页。

`polarity_cases.py` 由 17 条扩到 **22 条**（新增第九轮三条独立反例 + 两条正向对照），
生产与自检共用同一批期望值。

**传播范围重算**：把修复后的分句器回放到 1,007 份核验文档的全部 `evidence` 上，
**分句结果发生变化的文档 0 份**，极性结论变化的 0 份；`meta_diff.csv` 与 `summary.json`
逐字节未变。也就是说这三条是**内存反例**，存量台账未因此改变——修复的意义是
堵住未来的误放行，不能据此宣称「此前已有一批被误放行」。

### 1.3 C 项：父输入登记须绑定实际父输入 —— 本轮修复

原 `parent_verify.gap()` 只比对两个父终值、口径非空、引文能定位。裁决实测：
把两父文档都改成无关的 `DOC-01140151955D939E`、期间与口径写错、`reviewer=x`、日期留空，
仍返回 `True / VERIFIED`。现在登记记录必须逐项对上**实际父输入**：

| 校验 | 不通过时的原因码 |
|---|---|
| `p1_doc` / `p2_doc` 等于实际父键的 `document_id` | `PARENT_DOC_MISMATCH` |
| `p1_period` / `p2_period` 等于实际父期间 | `PARENT_PERIOD_MISMATCH` |
| `p1_value` / `p2_value` 等于实际父终值 | `PARENT_VALUE_MISMATCH` |
| 登记取值栏目（本期累计列 / 上期累计列） | `PARENT_COLUMN_EMPTY` |
| 登记调整前后版本，且两父版本一致 | `PARENT_ADJUST_VERSION_INVALID` / `_INCONSISTENT` |
| 口径三元组等于实际父输入，且有 `scope_basis` ≥20 字 | `SCOPE_MISMATCH_WITH_PARENT` / `SCOPE_BASIS_MISSING` |
| `reviewer` 非占位、`reviewed_at` 为真实日期、`review_role` 已标注 | `VERIFICATION_WITHOUT_REVIEWER` / `_DATE` / `_ROLE` |
| 引文 ≥12 字、可在原文定位，**且含该父数**（按 `unit_scale` 折算） | `PARENT_QUOTE_WITHOUT_PARENT_VALUE` |

C37 的注入链由 8 环扩到 **20 环**：除原有「撤去记录 / 结论不符 / 终值不符 / 引文不可定位 /
口径空 / 无审查人 / 引文缺失」外，新增文档不符（两父各一）、期间不符、栏目空、
调整版本非法、两父版本不一致、口径与实际不符、口径依据缺失、审查人占位、日期空、
角色未标、**引文真实存在但不含父数**（即裁决用的「无关内容」路径）。

登记表仍为空，所以兼容 **YES = 0**；重述差异 NO 3,679 / NA 13,330，
全量 17,728 条核心元数据差异 NO 3,768 / NA 13,960。`PENDING_PARENT_COMPATIBILITY` 仍为 1,277。

### 1.4 D 项：C24 —— 本轮修复（不再宣称「不可伪造」）

原 `review_gap()` 只查键、终值、结论、审查人非空、引文在 `results.csv.evidence` 中可定位。
裁决实测：复制现有摘录前 20 字、`reviewer=x`、`reviewed_at` 留空，返回 `None`。
现在补五道：

1. `reviewed_at` 必须是真实日期（`YYYY-MM-DD` 且可解析）；
2. `review_role` 必须显式标注（`SELF_CHECK` / `INDEPENDENT_REVIEW`）——**自检也要标**；
3. `original_page` + `original_fragment` 必须在**原件该页**逐字命中；
   定位源不再是 `results.csv.evidence`，而是回读 PDF 物理页文本；
4. `original_value_text` 必须是该字段在原文里**印出来的字面值**，且出现在片段中；
   内部枚举名（如 `LEGACY_SNAPSHOT`）不会出现在 PDF，此时必须由 `judgement_basis`
   同时写出印刷值与内部终值，把映射讲清楚；
5. `judgement_basis` ≥40 字，且点名该元数据字段与终值——即针对该字段的判断依据。

C24 注入扩到 **11 种**，包含裁决用过的「占位审查人 + 空日期 + 照抄摘录前缀」。
同时给出**正例对照**：对 `SH:600100|FIN.REV.YTD|20250630|value_raw` 按上述口径构造一条
真实可核的记录，`review_gap()` 返回 `None`——证明门槛可满足，不是不可通过的死门。

**结论措辞**：这些只是堵住了当前已知的绕过路径，**不等于入口已不可伪造**。

### 1.5 E 项：C14 —— 本轮修复

原 `ruling_content_ok()` 核对「引文逐字存在 + 行号指向该行」，于是把引文换成裁决文件
第 3 行 `建议存档名：codex_ruling_round4.md`（确实存在、行号也对）即可通过。
现在要求**引文所在那一行同时命中三样东西**：

- `ruling_section`：裁决条目名（`Q2 大豪科技改判`）；
- `ruling_key_pattern`：该键的识别信息，且必须真是本键（证券代码 / 简称 / 该键 DOC ID）；
- `ruling_verdict`：裁决结论用语（`接受该具体争议解除`）。

C14 注入由 2 种扩到 **5 种**：依据写 `x`、行号偏移、**无关引文 + 其正确行号**、
识别信息指向他公司、裁决条目名不在该行。大豪科技既有裁决继续保留，不重开。

### 1.6 F 项：C38 —— 本轮修复

两条实测绕过：① 用无关文档的通用引文登记季度表来源即可解除；② `scope_dims()` 接受
`PARENT_COMPATIBILITY`，`judge(scope_ok=…)` 接受全部 `SOURCE_DIMS`，因此
`parent_ok=False` 时仍可通过来源登记解除。现在：

- `scope_dims()` 只接受 `COMPARATIVE_SCOPE` / `QUARTERLY_TABLE_PROVENANCE`；
- 必须登记 `target_field` / `target_period` 且等于目标键；
- `document_id` 必须等于该行实际供给文档；
- 引文必须能在**原件**定位，且含该行期间年份；
- `judge()` 的 `scope_ok` 同步只认这两类（`SCOPE_REGISTRABLE`），父输入兼容不得被顶替。

C38 注入 **9 种**：结论不符、引文不可定位、无审查人、角色未标、日期空、无关文档、
父输入维度顶替、目标期间不符、引文不含期间年份。候选行
`BJ:920022|FIN.NPDEDT.SQ|20250630`：无登记 `PENDING_SOURCE_PROVENANCE`，
登记后来源维度补齐（仍因原因维度未覆盖停在 `PENDING_CAUSE_UNCOVERED`），
仅提供 `PARENT_COMPATIBILITY` 时仍为 `PENDING_SOURCE_PROVENANCE`。

### 1.7 G 项：抽验 —— R6 本轮重做

裁决指出 V8 的父 1 片段是「追溯重述法□适用√不适用……」模板，**没有定位实际累计父数**；
父 2 也没交付期间列、单位、调整前后版本。现在 `parent_detail()` 改为：

- **两个父数都按金额本身定位**（`locate_amount_in_doc`），片段取该金额左右窗口；
- 逐父交付：取值、取值状态、所在期间列、表头单位字面、调整前后版本；
- 额外交付：两父是否同一 `version_used`、是否同一采用文档、兼容缺口；
- `parent_compat_conclusion` 明确写「定位本身不构成兼容已证」。

三条样本（S19 `BJ:920289`、S20 `SH:600008`、S21 `SH:600053`）实测：

| 样本 | 父1 定位 | 父2 定位 | 父1 片段（含实际父数） | 兼容 |
|---|---|---|---|---|
| S19 | `LOCATED_AMOUNT(p.10)` | `LOCATED_AMOUNT(p.3)` | …扣除非经常性损益后的净利润 57,296,869.60 … | NO / `NO_VERIFICATION_RECORD` |
| S20 | `LOCATED_AMOUNT(p.6)` | `LOCATED_AMOUNT(p.1)` | …扣除非经常性损益的净利润 818,989,707.54 … | NO / `NO_VERIFICATION_RECORD` |
| S21 | `LOCATED_AMOUNT(p.6)` | `LOCATED_AMOUNT(p.1)` | …扣除非经常性损益的净利润 -86,542,044.51 … | NO / `NO_VERIFICATION_RECORD` |

三条均交付：期间列（本期累计列）、表头单位字面（`单位：元`）、调整版本
（`ORIGINAL|文档期间=…|未登记采用`）、同 `version_used` = YES、同采用文档 = `NO_RECORD`。
**三条 `parent_amount_located=BOTH` 只说明两个父数在原件定位到，不构成两父核证完成**——
兼容仍为 NO。

同时把抽验脚本的 `_pc()` 与生产统一为核证登记表唯一来源，撤销「同文档 / 上游双否 /
采用同文档」三条捷径（此前抽验表比生产更宽）。

### 1.8 H 项：文本同步

- V4 故障注入数字改为 **C26 7,729 / C14 6,617**（原写 7,714 / 6,602，各少 15）。
- `NO=3,768` 属**全量 17,728 条核心元数据差异**，`NA=13,330` 属**重述差异 17,009**，
  两者不再混用；重述差异的 NO 为 3,679。
- `dispute_ledger.csv` 为 **10,618 行 / 10,618 个唯一差异 ID**（原写 17,728）。
- 「9,954 条已解决项」改为「**合计 9,954 条 / 631 份文档，其中已解除 8,655 条 / 630 份**」。
- 撤回「C24/C14 不再可伪造」「R6 两父核证完成」等结论。

---

## 五、第八轮裁决的落实（历史段落，对应自检 V8；有更新的已就地标注）

### 1.1 A 项：必需范围取并集 —— 已通过（第八轮确认）

第七轮把 `period_scope(期间)` 与 `source_scope(status, 行期间)` 取并集，非自身期间的
分季度表行 / 累计差分行不再丢掉来源维度。第八轮复核确认通过，本轮未改动。
覆盖它的自检项是 **C36**。

### 1.2 B 项：极性 —— 本轮重做

第八轮点名了一处**真实误放行**，以及五条内存反例。

**真实误放行。** 三协电机 `BJ:920100`、文档 `DOC-E2BDEAB4F6274B6E`、原 PDF 第 135 页：

> `□会计政策变更 √会计差错更正 □其他原因 □不适用`

V7 的 `option_group()` 对**每个符号**同时看左右两侧标签。因为符号写在标签**前面**，
每个符号的左侧恰好是**上一个选项**的标签，于是「左 ≠ 右」被当成歧义，整行判成
`conflict=ERRATA,POLICY_CHANGE`；`analyse()` 随后按歧义处理，同时写入
`excluded` 与 `affirmed`，而 `judge()` 只在「本行必需维度冲突」时阻断——
POLICY_CHANGE 不是必需维度，于是这行以 `excluded=ERRATA` 一路放行。
该文档供给的 **15 条重述差异全部为 `RESOLVED_SCOPE_COVERED`**。

**修法：版面整体求解。** 不再逐符号混判，而是把整组按两种版面各解一遍：

| 版面 | 取标签的一侧 | 例 |
|---|---|---|
| `after`（符号在前） | 符号右侧 | `√会计差错更正 □其他原因` |
| `before`（符号在后） | 符号左侧 | `适用√ 不适用□` |

每种解法都要求「每个符号都能解出标签」且「标签互不重复」（同一选项被两个符号认领即不成立）。
两种版面都能自洽且结论不同，才判真歧义。

结果：

```
□会计政策变更 √会计差错更正 □其他原因 □不适用
  → excluded=POLICY_CHANGE | affirmed=ERRATA | conflict=-
```

**处置结果。** 该文档 15 条不再解除，全部转 `UNRESOLVED_EVIDENCE_CONTRADICTS`，
并新增 `evidence_conflicts.csv` 逐行登记上游 `verdict` 与原文极性的冲突及其传播范围
（该文档在 B 中供给 15 个元数据槽，全部转冲突；`cell_diff` / `key_diff` /
`extra_meta_diff` / `restricted_claims` 均未引用该文档，传播到此为止）。

**五条反例。** 全部纳入 `polarity_cases.py`，生产与自检共用同一份期望值：

| # | 输入 | 期望 |
|---|---|---|
| ① | `本期未发生前期差错更正，但本期发生前期差错更正100.00元` | 同句肯定否定 → `conflict=ERRATA` |
| ② | `本期发生前期差错更正，无重大影响` | `affirmed=ERRATA`，无冲突（「无重大影响」是重要性表述） |
| ③ | `前期差错更正□适用√不适用，本期发生差错更正100.00元` | 勾选与叙述冲突 → `conflict=ERRATA` |
| ④ | `前期差错更正适用√不适用□` | 后置符号：√ 打在「适用」上 → `affirmed=ERRATA` |
| ⑤ | `前期差错更正对期初未分配利润影响0.00元，对净资产影响100.00元` | 保留非零事件 → `affirmed=ERRATA` + `scoped=ERRATA` |

**返工过程中另外查出的两个缺陷（不在裁决清单里，但会污染结论）：**

1. **半角逗号无条件切分。** `-160,517.06元` 被切成 `-160` 与 `517.06元` 两段，
   金额句丢失非零证据，导致 `*ST九鼎` 与 `派斯林` 各 4 条、共 **8 条**事件确认
   从 `PENDING_CONFIRMED_EVENT_FIELD_OPEN` 掉到 `PENDING_CONFIRMED_UNSUPPORTED`。
   改为「全角逗号一律切，半角逗号仅在不是千分位时切」。
2. **勾选组跨标题误绑。** `（四）审批程序及其他说明` 后面紧跟 `√适用□不适用`，
   该勾选组讲的是「审批程序」，与差错更正无关，但 V7 会绑到上一节的差错更正主语上。
   改为「标题行换题即断开主语承接」，只有标题本身含原因词时才继承。

覆盖这三处的自检项是 **C34**（17 条反例）。

### 1.3 C 项：父输入兼容性 —— 本轮重做

第八轮否掉两条自动判据：

- **同文档不能自动证明兼容**：同一报告可能含调整前后列或混合来源；
- **上游「双否」不能直接证明兼容**：三协电机已证明 `verdict` 可能与原文相反，
  它只能作待核线索。

因此 V8 把 `parent_compatible()` 收窄为两道门：

1. 口径三元组（`consolidation_scope` / `unit_scale` / `currency`）**非空且一致** —— 必要条件；
2. `parent_verifications.csv` 给出两个实际累计父数、原文引文、审查结论 —— 充分条件。

**登记表为空，所以 YES = 0。** 这不是回退，是把「没有依据的放行」清零：

| 项 | 第七轮 | 第八轮 |
|---|---:|---:|
| 兼容 YES | 4 | **0** |
| 兼容 NO（17,009 条重述差异） | 3,675 | **3,679** |
| 兼容 NA（17,009 条重述差异） | 13,330 | 13,330 |
| 兼容 NO（全部 17,728 条核心元数据差异） | — | **3,768** |
| 兼容 NA（全部 17,728 条核心元数据差异） | — | 13,960 |
| `PENDING_PARENT_COMPATIBILITY` | 1,277 | **1,277** |

那 4 条 YES 属于 `SH:688328@20251231` 的直接分季度表记录（走「双否」分支），
本来就因缺季度表来源而未解除，所以清零不改变待核数——但也不再向任何人暗示
「累计差分已核证通过」。每行都新增 `parent_basis` 列写明判定依据
（`NO_VERIFICATION_RECORD` / `SCOPE_UNIT_CURRENCY_MISMATCH` / `PARENT_MISSING` / `VERIFIED`）。

同时澄清一条纪律：**正常同口径累计数相减，不要求两期调整额相等**；只有主张
「调整影响相互抵消」时才必须证明调整额相等。本版不采用「抵消」论证。

覆盖它的自检项是 **C37**，按第八轮指定的方式检验：**撤去真实兼容依据后是否仍通过**。
做法是挑一条口径一致的真实累计差分键，造一条满足条件的登记记录，确认判 YES；
再逐项撤去依据（换结论 / 改终值 / 引文不可定位 / 单位字段清空 / 无审查人 / 第二父引文缺失），
确认逐项变 NO。

### 1.4 D 项：事件确认不再用方法名兜底 —— 已通过（第八轮确认）

第八轮核读两份原 PDF 后确认通过，本轮未改动。

### 1.5 E 项：两条自检绕过路径 —— 本轮修复

**C24：审查记录可伪造。** 原判据是
`content_review == "CONFIRMED"` 且 `content_review_ref == sha1(键|字段|终值)[:12]`。
摘要由公开公式算出，不做审查也能填对；且摘要**遗漏 `period_key`**，同一证券同一字段
跨期间会互相顶替。

V8 改为外部登记表 `content_reviews.csv`，逐条核对：

- 完整键（`security_id` + `field_id` + `period_key` + `meta_field`）；
- 台账的 `content_review_ref` 必须指向该登记键（台账须自证依据的是哪条审查）；
- 终值 `value_B` 必须与登记记录一致；
- `conclusion` 必须是 `CONFIRMED_EXPLAINED` / `CONFIRMED_NOT_SUBSTANTIVE`；
- 必须有审查人与审查日期；
- 登记记录引用的 `document_id` 必须等于 B 该行的取值来源文档；
- `evidence_quote` 长度 ≥12 字，且必须**在该文档的上游原文里逐字定位**。

当前登记表为空，1,505 格补充元数据全部停在 `PENDING_FIELD_LEVEL_CHECK`（0 条放行）。
六种注入绕过全部被拦住：无记录 / 改标展示字段 / 仅填可算摘要 / 换 `period_key` /
引文不可定位 / 终值不符。

**C14：占位解释仍通过。** 原判据只要求 `basis` 与 `conflict_explanation` 非空，
把两者都写成 `"x"` 也能过。V8 要求每条裁决额外登记：

- `ruling_quote`：≥20 字的裁决原文片段，必须**逐字出现在裁决文件中**；
- `ruling_line`：该片段所在行号，且该行确实包含该片段（行号不能编）；
- `basis` 与 `conflict_explanation` 各自 ≥40 字，且至少包含一个识别信息
  （证券代码 / 文档 ID / 公司简称）。

大豪科技既有裁决**未重开**：`SH:603025|FIN.REV.SQ|20250331` 仍为
`RESOLVED_BY_RULING`，登记文件 `errata_20261111_v3/codex_ruling_round4.md`
（sha256 `5e6b1d6e…`）第 236 行原文：

> `| Q2 大豪科技改判 | **接受该具体争议解除。** 当前范围内可标 NOT_AFFECTED，不代表全公司验收 |`

两种注入（把依据改成 `"x"`、把行号改成 235）都被拦住。

### 1.6 F 项：抽验补齐 —— 本轮修复

**R6 两父输入原文核证。** 原 `parent_detail()` 只给「两份文档 ID + 文档判定 + 兼容性」，
没有定位实际累计父数。V8 逐个父输入交付：取值 `value_cny`、取值状态、来源文档、
原件定位结论、命中片段。当父输入文档不在 1,007 份核验清单内（无 `evidence` 文本）时，
退到**按金额在原件中定位**（千分位格式化后整串匹配，避免子串误命中）。

抽样池也改了：优先取「两父输入都能在原件中定位」的样本。3 条 R6 样本现在全部
`parent_orig_verified = BOTH`。

**R7 措辞。** 原结论写 `VERBATIM_ORIGINAL`，把「20 字连续片段命中」说成整段逐字一致。
V8 改为 `ORIGINAL_FRAGMENT_LOCATED：<n> 字连续片段已在 p.<n> 逐字命中；仅证明该片段
出自原件，不等于整段证据逐字无误`，并新增 `located_page` 与 `located_fragment` 两列
保存命中片段本身。

**verify 的捷径判据。** 原 C37 把所有「跨文档 + 同版本 + 兼容」都判成捷径，
将来会误拦合法核证。V8 删除该判据，换成 1.3 节的注入链。

### 1.7 G/H 项：故障注入与文本

故障注入数字复算一致（第八轮确认）：

| 版本 | C13 | C14 | C17 |
|---|---:|---:|---:|
| V1 原始 | 6 | 11,936 | 12,076 |
| V4 旧标签映射后 | — | **6,617** | — |
| V5 自身 | 0 | 0 | 0 |

文本旧数已同步：去重键 27 个（第七轮表为 25，因 R6 池改为「两父均可定位」而换样）、
`NOTE_TRACE_NA` **9,954 条 / 631 份文档**（已解除 8,655 条 / 630 份）、
分层数字统一引 **44 / 231 / 378**、自检版本 V6→V8、
`active_issue.json` 的「撤销四条捷径」表述已改为「只认核证登记表」。

### 1.8 新增 C38：来源维度的结构化核证入口

第八轮指出 `judge()` 尚不能消费结构化的「比较范围」「季度表来源」核证记录。
V8 新增 `scope_verifications.csv` 与 `judge(scope_ok=…)`：这两个维度**只能**由
登记表覆盖（要求结论 `CONFIRMED`、有审查人、引文 ≥12 字且能在所引文档原文定位），
不接受「文档里提到过」。撤去登记记录后该行必须退回 `PENDING_SOURCE_PROVENANCE`。

---

## 六、数字

### 2.1 重述差异（17,728 条元数据差异中的 17,009 条 `restatement_flag`）

| 处置 | 条数 |
|---|---:|
| `RESOLVED_SCOPE_COVERED` | 8,699 |
| `PENDING_SCOPE_LIMITED_METHOD` | 6,373 |
| `PENDING_PARENT_COMPATIBILITY` | 1,277 |
| `PENDING_WEAK_ASSUMPTION` | 515 |
| `PENDING_SOURCE_PROVENANCE` | 47 |
| `PENDING_CAUSE_UNCOVERED` | 43 |
| `UNRESOLVED_DOC_NEVER_VERIFIED` | 26 |
| **`UNRESOLVED_EVIDENCE_CONTRADICTS`** | **15**（三协电机，新增） |
| `PENDING_CONFIRMED_EVENT_FIELD_OPEN` | 8 |
| `UNRESOLVED_EVIDENCE_MISMATCH` | 4 |
| `PENDING_CONFIRMED_UNSUPPORTED` | 1 |
| `RESOLVED_BY_RULING` | 1 |
| **合计** | **17,009** |

待处置（`PENDING_*` + `UNRESOLVED_*`）合计 **8,309**（= 17,009 − 8,699 − 1）。

### 2.1b 其余四列（`status` 555 / `document_id` 83 / `pit_status` 48 / `consolidation_scope` 33）

| 处置 | 条数 |
|---|---:|
| `RESOLVED_NORMALIZED_DELTA` | 354 |
| `UNRESOLVED_NO_EVIDENCE` | 225 |
| `UNRESOLVED_FIELD_NOT_IN_RECORD` | 116 |
| `UNRESOLVED_EVIDENCE_MISMATCH` | 16 |
| `UNRESOLVED_RECORD_IS_REMOVE` | 8 |
| **合计** | **719** |

未闭合 **365**（= 719 − 354）。两张表相加 = 17,728 行 / 未闭合 8,674 行，与 2.2 节
「元数据（核心 5 列）17,728 / 8,674」一致。上一版把两表混排在一张「17,009」标题下
（表内合计实为 17,728），本轮拆开。

与第七轮的差异只有两处，且都指向同一件事：
`RESOLVED_SCOPE_COVERED` 8,714 → 8,699（−15），
`UNRESOLVED_EVIDENCE_CONTRADICTS` 0 → 15（+15）。
其余分布逐项不变——说明这轮改动是定点修复，没有顺带改变别处结论。

### 2.2 全表

| 层 | 总数 | 未闭合 |
|---|---:|---:|
| 值差异 | 240 | 34 |
| 键差异 | 2,056 | 405 |
| 元数据（核心 5 列） | 17,728 | 8,674 |
| 元数据（补充 19 列） | 1,505 | 1,505 |
| **核心合计** | — | **9,113** |
| **含补充合计** | — | **10,618** |

### 2.3 全池影响（1,054 家）

| 判定 | 家数 |
|---|---:|
| `NOT_AFFECTED` | 320 |
| `STILL_PASSES_WITHOUT` | 81 |
| `HOLD_PENDING_ERRATA` | **44** |
| `R2_MAY_CHANGE` | **231** |
| `R1_NO_LINK` | **378** |

受限表 407 行 / 401 个唯一差异 ID；重述同质分组 89 组。

---

## 七、自检 41 项

V12 相对 V11 的变动：**新增 C39**（状态文件单一写者：旧计数必须消失、版本与定位器版本
必须本次一致）；C31 增加「键集变更的退出归因须机器自证」；C34 38 条、C37 35 环、
C14 13 种、C38 14 种（见第一节 1.8 的数字表）。

V8 相对 V7 的变动：

- **C34** 由 9 条反例扩到 **17 条**，直接消费 `polarity_cases.py`（与独立脚本同源）；
- **C37** 从「有没有捷径」改为「撤去真实依据后是否变 NO」的注入链；
- **C24** 从「可算摘要」改为「外部登记表 + 引文可定位」，注入 6 种绕过；
- **C14** 增加裁决原文片段与行号的回读核对，注入 2 种绕过；
- **新增 C38** 来源维度结构化核证入口。

`python verify_v5.py` 输出 `41/41 PASS → SELF_CHECK_PASS_WITH_UNRESOLVED_ITEMS`。

---

## 八、故障注入

| 注入对象 | 结果 |
|---|---|
| V1 原始台账代入同一套检查 | C13 = 6、C14 = 11,936、C17 = 12,076 全部 FAIL（实质原因，非版本号差异） |
| V4 旧标签映射后 | C26 = **7,729**、C14 = **6,617**、受限方法自身期间 5,270 仍 FAIL |
| V5 自身 | 全 0 |
| C37 撤去兼容依据 | **29 环**（1 正例 + 28 反例，含 2 条真实原件负例）逐项按预期拒绝 |
| C38 撤去来源核证 | 退回 `PENDING_SOURCE_PROVENANCE` |
| C24 **13 键 + 枚举 1 种**伪造 | 全部拦住并断言原因（含「同页上年数冒充本期终值」「枚举字段靠自述映射」「千分位粘连」三条实测绕过）；注入键集合与预期原因集合严格相等；正例对照被接受 |
| C14 **10 种**伪造 | 全部拦住并断言原因（含「无关引文＋其正确行号」「引第 88 行登记说明」「引第 235 行 Q1 通用条目」「同公司异字段」「否定表述截断」「key 与 ruled_key 同时改写」六条实测绕过） |

---

## 九、抽验（37 行 / 20 类 / 27 个键；键数取自 `sampling_v5.json:unique_keys`）

- 原件物理页回读：`MATCH` 18、`PARTIAL` 5、`LOCATED` 2、`WEAK_LOCATE` 1、
  `NO_PAGE_RECORDED` 5、补充字段不适用 6（合计 37，逐项取自 `sampling_v5.json:page_reread`）；
- R6 三条样本两父输入**均**在原件定位（`parent_orig_verified = BOTH`）；
- R7 三条：2 条 `VERIFIED`（命中片段已保存）、1 条 `WEAK`（汇总注非原文，不算已定位）；
- 键集变更留痕：`sampling_keys_diff.csv`（基线 `sampling_keys_baseline.csv` = V10，
  `baseline_sha256 = 0d0940cc…`）逐键记录 **KEPT 26 / ADDED 1 / REMOVED 1**，
  带样本 ID、原因、`locator_version = V11` 与前后来源哈希。

发现：`SH:600936 FIN.REV.SQ@20250630` 的核验证据在原件全文无法定位，
属上游核验记录异常，**未放行**。

---

## 十、仍未闭合的已知问题

1. **`NOTE_TRACE_NA` 合计 9,954 条 / 631 份文档，其中已解除 8,655 条 / 630 份**，均未做方法适用性复审；已解除部分同样须纳入复审。
2. `NOTE_RETAINED_ERRATA_ZERO` 642 条（自身 563 / 非自身 79，42 份文档）未逐条回读原注。
3. 1,505 格补充元数据仅登记字段级核验要求，登记表为空，**0 条放行**。
4. **上游 `results.csv` 对 `DOC-E2BDEAB4F6274B6E` 的 `verdict=否` 与原文相反**，
   本版只登记为证据冲突，未修改上游判定——修正动作归 S02 还是 S00 勘误，请裁决。
5. 锚定期回退与上游准入的间接依赖未覆盖。
6. 第 4 步批量核证、第 5 步重算分层**未开始**；44 / 231 / 378 均未锁定。
7. C26 / C29 与生产共用判据函数，属**同源重算**，不能替代独立方法验证。

---

## 十一、本轮不做的事

- 不启动 S04 第二轮正式验收；S05 保持 `WAITING_DEPENDENCIES`。
- 不锁定 44 / 231 / 378 或任何名单数字。
- 不宣称「第 1–3 步已完成」：第 1 步在本轮继续返工，第 3 步自检仍有同源局限。
- 不宣称「原件中不存在某证据」：只写「未定位到」。
- 不修改 S02 的上游 `results.csv`。
