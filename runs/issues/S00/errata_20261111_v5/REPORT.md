# S00 勘误台账 V5 报告（第九轮返工后）

- 目录：`runs/issues/S00/errata_20261111_v5/`
- 性质：**SELF_CHECK**，不是独立验收
- 自检版本：**V9**，40/40 PASS → `SELF_CHECK_PASS_WITH_UNRESOLVED_ITEMS`
- 本轮触发：Codex 第九轮复核 `RETURN_FOR_REWORK`（不放行 S04 第二轮、不放行 S05）
- 复现顺序：`python build_errata_v5.py` → `python check_l2_v5.py` → `python sampling_v5.py` → `python verify_v5.py`

---

## 一、第九轮裁决的逐条落实

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

## 二、第八轮裁决的落实（第八轮内容；本轮有更新的已就地标注）

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

## 三、数字

### 2.1 重述差异（17,728 条元数据差异中的 17,009 条 `restatement_flag`）

| 处置 | 条数 |
|---|---:|
| `RESOLVED_SCOPE_COVERED` | 8,699 |
| `PENDING_SCOPE_LIMITED_METHOD` | 6,373 |
| `PENDING_PARENT_COMPATIBILITY` | 1,277 |
| `PENDING_WEAK_ASSUMPTION` | 515 |
| `RESOLVED_NORMALIZED_DELTA` | 354 |
| `UNRESOLVED_NO_EVIDENCE` | 225 |
| `UNRESOLVED_FIELD_NOT_IN_RECORD` | 116 |
| `PENDING_SOURCE_PROVENANCE` | 47 |
| `PENDING_CAUSE_UNCOVERED` | 43 |
| `UNRESOLVED_DOC_NEVER_VERIFIED` | 26 |
| `UNRESOLVED_EVIDENCE_MISMATCH` | 20 |
| **`UNRESOLVED_EVIDENCE_CONTRADICTS`** | **15**（三协电机，新增） |
| `PENDING_CONFIRMED_EVENT_FIELD_OPEN` | 8 |
| `UNRESOLVED_RECORD_IS_REMOVE` | 8 |
| `PENDING_CONFIRMED_UNSUPPORTED` | 1 |
| `RESOLVED_BY_RULING` | 1 |

待处置（`PENDING_*` + `UNRESOLVED_*`）合计 **8,309**。

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

## 四、自检 40 项

V8 相对 V7 的变动：

- **C34** 由 9 条反例扩到 **17 条**，直接消费 `polarity_cases.py`（与独立脚本同源）；
- **C37** 从「有没有捷径」改为「撤去真实依据后是否变 NO」的注入链；
- **C24** 从「可算摘要」改为「外部登记表 + 引文可定位」，注入 6 种绕过；
- **C14** 增加裁决原文片段与行号的回读核对，注入 2 种绕过；
- **新增 C38** 来源维度结构化核证入口。

`python verify_v5.py` 输出 `40/40 PASS → SELF_CHECK_PASS_WITH_UNRESOLVED_ITEMS`。

---

## 五、故障注入

| 注入对象 | 结果 |
|---|---|
| V1 原始台账代入同一套检查 | C13 = 6、C14 = 11,936、C17 = 12,076 全部 FAIL（实质原因，非版本号差异） |
| V4 旧标签映射后 | C26 = **7,729**、C14 = **6,617**、受限方法自身期间 5,270 仍 FAIL |
| V5 自身 | 全 0 |
| C37 撤去兼容依据 | 20 环逐项变 NO |
| C38 撤去来源核证 | 退回 `PENDING_SOURCE_PROVENANCE` |
| C24 十一种伪造 | 全部拦住（含「reviewer=x + 日期留空 + 照抄摘录前缀」实测绕过）；正例对照被接受 |
| C14 五种伪造 | 全部拦住（含「无关引文＋其正确行号」实测绕过） |

---

## 六、抽验（37 行 / 20 类 / 27 个键）

- 原件物理页回读：`MATCH` 19、`PARTIAL` 5、`LOCATED` 2、`WEAK_LOCATE` 1、
  `NO_PAGE_RECORDED` 4、补充字段不适用 6；
- R6 三条样本两父输入**均**在原件定位（`parent_orig_verified = BOTH`）；
- R7 三条：2 条 `VERIFIED`（命中片段已保存）、1 条 `WEAK`（汇总注非原文，不算已定位）。

发现：`SH:600936 FIN.REV.SQ@20250630` 的核验证据在原件全文无法定位，
属上游核验记录异常，**未放行**。

---

## 七、仍未闭合的已知问题

1. **`NOTE_TRACE_NA` 合计 9,954 条 / 631 份文档，其中已解除 8,655 条 / 630 份**，均未做方法适用性复审；已解除部分同样须纳入复审。
2. `NOTE_RETAINED_ERRATA_ZERO` 642 条（自身 563 / 非自身 79，42 份文档）未逐条回读原注。
3. 1,505 格补充元数据仅登记字段级核验要求，登记表为空，**0 条放行**。
4. **上游 `results.csv` 对 `DOC-E2BDEAB4F6274B6E` 的 `verdict=否` 与原文相反**，
   本版只登记为证据冲突，未修改上游判定——修正动作归 S02 还是 S00 勘误，请裁决。
5. 锚定期回退与上游准入的间接依赖未覆盖。
6. 第 4 步批量核证、第 5 步重算分层**未开始**；44 / 231 / 378 均未锁定。
7. C26 / C29 与生产共用判据函数，属**同源重算**，不能替代独立方法验证。

---

## 八、本轮不做的事

- 不启动 S04 第二轮正式验收；S05 保持 `WAITING_DEPENDENCIES`。
- 不锁定 44 / 231 / 378 或任何名单数字。
- 不宣称「第 1–3 步已完成」：第 1 步在本轮继续返工，第 3 步自检仍有同源局限。
- 不宣称「原件中不存在某证据」：只写「未定位到」。
- 不修改 S02 的上游 `results.csv`。
