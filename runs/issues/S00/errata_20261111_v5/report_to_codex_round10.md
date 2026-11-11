# S00 勘误 V5 第九轮返工汇报（报第十轮复核）

## 0. 一句话

你第九轮点出的三类问题全部改完：**极性三条独立反例**（换行切碎选项组 / 零值压非零 / 勾选否定压金额肯定）、
**父输入登记不绑定实际父输入**、**C24 / C14 / C38 三条伪造入口**，并重做 R6 的两个实际累计父数核证。
自检 **V9，40/40 PASS**。**但我不宣称这些入口「不可伪造」**——只宣称你实测的那几条路径已被堵住。

## 1. B 项：极性三条独立反例 —— 已修，22 条反例全过

### 1.1 复现（改前实测，与你给的结果一致）

```
换行插在每个□后(变体A)  → excluded=ERRATA|affirmed=POLICY_CHANGE
换行插在每个□后(变体B)  → excluded=POLICY_CHANGE|affirmed=ERRATA   （与 A 相反）
零值+非零值用「及」连    → 仅 scoped=ERRATA
勾选不适用+零值+非零     → excluded=ERRATA|affirmed=-|conflict=-
```

### 1.2 三个根因与改法

**① 选项组被换行切碎**（`evidence_scope.py` 的 `_clauses`）。
`□\n会计政策变更 √\n会计差错更正 □\n其他原因 □\n不适用` 被切成 5 个分句，
`会计政策变更 √` 这一片里 `√` 左侧是标签 → 解出 `affirmed=POLICY_CHANGE`；
`会计差错更正 □` 解出 `excluded=ERRATA`。每片都自洽，合起来正好反向。

改法：分句前先把「含 ≥2 个符号」的**连续选项碎片拼回一组**再解析。
关键细节：**纯原因标签必须留在组外**。第一版把 `前期差错更正\n√适用□不适用` 也拼进去，
结果 `√` 左侧也能认领「前期差错更正」，与右侧解冲突而假判歧义（22 条反例里 2 条当场 FAIL）。
现规则：组内已出现符号后又来一个纯原因标签 → 先断开，作为下一组主语。

**② 零值压掉非零值**（`_bind_amount`）。
原 `nonzero = bool(_RE_AMOUNT.search(c)) and not zero` 是**整句归一**，
同句出现一个 `0.00元` 就把 `100.00元` 一起判成零值。
改为 `_amounts(c)` 逐个金额判定：每个金额各自就近绑定原因，零值只记 `scoped`，非零值另记 `affirmed`。

**③ 已有 excluded 压掉后续肯定**（`_bind_amount`）。
原 `if nonzero and t not in neg_c and t not in excluded` 让勾选「√不适用」静默盖掉后面的非零金额。
撤销 `t not in excluded`：勾选否定与金额肯定并存时保留 `conflict`，
由 `judge()` 判 `UNRESOLVED_POLARITY_CONFLICT` 退回原页。

### 1.3 改后实测

```
原四选项行              excluded=POLICY_CHANGE|affirmed=ERRATA
换行变体A               excluded=POLICY_CHANGE|affirmed=ERRATA
换行变体B               excluded=POLICY_CHANGE|affirmed=ERRATA
零+非零 及              excluded=-|affirmed=ERRATA|scoped=ERRATA
勾选不适用+零+非零       excluded=ERRATA|affirmed=ERRATA|conflict=ERRATA
勾选适用+零+非零         excluded=-|affirmed=ERRATA|scoped=ERRATA
```

`polarity_cases.py` 17 → **22 条**（新增你三条 + 两条正向对照），生产与自检共用。

### 1.4 传播范围重算（你要求的那一步）

把修复后的分句器回放到 1,007 份核验文档的全部 `evidence`：

| 项 | 结果 |
|---|---|
| 分句结果发生变化的文档 | **0** |
| 极性结论发生变化的文档 | **0** |
| `meta_diff.csv` / `summary.json` | **逐字节未变** |

即：这三条是**内存反例**，存量台账未因此改变。我不据此宣称「此前已有一批被误放行」。

## 2. C 项：父输入登记现在绑定实际父输入

### 2.1 你实测的绕过

真实键 `SH:600008|FIN.NPDEDT.SQ|20260630`，两父文档都改成无关的 `DOC-01140151955D939E`、
期间口径写错、`reviewer=x`、日期留空、只保留正确父终值 → 仍 `True / VERIFIED`。
原因：`gap()` 只比 `p1_value`/`p2_value`、口径非空、引文能定位。

### 2.2 现在必须逐项对上实际父输入

| 校验 | 原因码 |
|---|---|
| `p1_doc` / `p2_doc` = 实际父键 `document_id` | `PARENT_DOC_MISMATCH` |
| `p1_period` / `p2_period` = 实际父期间 | `PARENT_PERIOD_MISMATCH` |
| `p1_value` / `p2_value` = 实际父终值 | `PARENT_VALUE_MISMATCH` |
| 取值栏目（本期累计列 / 上期累计列）非空 | `PARENT_COLUMN_EMPTY` |
| 调整前后版本合法，且两父版本一致 | `PARENT_ADJUST_VERSION_INVALID` / `_INCONSISTENT` |
| 口径三元组**等于实际父输入** + `scope_basis` ≥20 字 | `SCOPE_MISMATCH_WITH_PARENT` / `SCOPE_BASIS_MISSING` |
| `reviewer` 非占位 / `reviewed_at` 真实日期 / `review_role` 已标注 | `VERIFICATION_WITHOUT_REVIEWER` / `_DATE` / `_ROLE` |
| 引文 ≥12 字、可在原文定位、**且含该父数**（按 `unit_scale` 折算） | `PARENT_QUOTE_WITHOUT_PARENT_VALUE` |

最后一条正对你说的「引文真实存在，却来自错误文档、错误期间或无关内容」：
通用标题片段里没有那个数，`_num_in_quote()` 直接不通过。

### 2.3 C37 注入链 8 环 → 20 环

```
with_record=T, no_record=T, wrong_conclusion=T, value_mismatch=T, quote_not_located=T,
empty_scope=T, no_reviewer=T, p2_quote_missing=T,
doc_mismatch=T, p2_doc_mismatch=T, period_mismatch=T, column_empty=T,
adjust_version_invalid=T, adjust_version_inconsistent=T, scope_mismatch=T,
scope_basis_missing=T, reviewer_placeholder=T, no_date=T, role_unmarked=T,
quote_without_parent_value=T
```

### 2.4 数字

| 统计范围 | YES | NO | NA |
|---|---:|---:|---:|
| 17,009 条重述差异 | 0 | **3,679** | 13,330 |
| 全部 17,728 条核心元数据差异 | 0 | **3,768** | 13,960 |

`PENDING_PARENT_COMPATIBILITY` 仍 **1,277**。登记表为空，YES 仍为 0。

## 3. D 项：C24 —— 不再用 `results.csv.evidence` 自证

### 3.1 你实测的绕过

`SH:600444|FIN.COST.YTD|20251231|period_source`：复制现有摘录前 20 字、`reviewer=x`、
`reviewed_at` 留空、允许结论 → `review_gap()` 返回 `None`。

### 3.2 现在补五道

1. `reviewed_at` 必须是**真实日期**（`YYYY-MM-DD` 且可解析）；
2. `review_role` 必须**显式标注**（`SELF_CHECK` / `INDEPENDENT_REVIEW`）——自检也要标；
3. `original_page` + `original_fragment` 必须在**原件该页逐字命中**——定位源改为回读 PDF 物理页，
   不再用 `results.csv.evidence`；
4. `original_value_text` 必须是该字段在原文**印出来的字面值**且出现在片段中；
   内部枚举名（`LEGACY_SNAPSHOT` 之类）不会出现在 PDF，此时必须由 `judgement_basis`
   同时写出印刷值与内部终值，把映射讲清楚；
5. `judgement_basis` ≥40 字、点名该元数据字段与终值——即**针对该字段**的判断依据。

### 3.3 注入 11 种 + 一个正例对照

无记录 / 改标展示 / 仅填可算摘要 / 换期间 / **占位审查人+空日期+照抄摘录前缀（你实测的路径）** /
角色未标 / 片段错页 / 片段为通用样板 / 终值未声明 / 依据占位 —— 全部拦住。

正例对照：`SH:600100|FIN.REV.YTD|20250630|value_raw`，按上述口径从原件 p.7 取
`…营业收入5,667,075,612.52…` 作片段、印刷值 `5,667,075,612.52`、依据写明字段与终值
→ `review_gap()` 返回 `None`。**门槛可满足，不是死门。**

## 4. E 项：C14 —— 绑定「该段确实裁决该键」

### 4.1 你实测的绕过

保留既有长解释，仅把引文与行号换成裁决文件第 3 行 `建议存档名：codex_ruling_round4.md`
（确实逐字存在、行号也对）→ `ruling_content_ok()` 返回 `True`。

### 4.2 现在要求引文所在那一行同时命中三样

- `ruling_section`：裁决条目名 —— `Q2 大豪科技改判`；
- `ruling_key_pattern`：该键识别信息，且必须真是本键（证券代码 / 简称 / 该键 DOC ID）；
- `ruling_verdict`：裁决结论用语 —— `接受该具体争议解除`。

第 236 行 `| Q2 大豪科技改判 | **接受该具体争议解除。** … |` 三者齐备；
第 3 行 `建议存档名…` 三者皆无。注入 5 种全拦住（依据写 x / 行号偏移 /
**无关引文+正确行号** / 识别信息指向他公司 / 裁决条目名不在该行）。
大豪科技既有裁决继续保留，不重开。

## 5. F 项：C38 —— 来源维度限定 + 绑定目标

- `scope_dims()` 只接受 `COMPARATIVE_SCOPE` / `QUARTERLY_TABLE_PROVENANCE`；
- 必须登记 `target_field` / `target_period` 且等于目标键；
- `document_id` 必须等于**该行实际供给文档**；
- 引文必须能在**原件**定位，且**含该行期间年份**；
- `judge(scope_ok=…)` 同步只认这两类（`SCOPE_REGISTRABLE`），
  `PARENT_COMPATIBILITY` 只能走 `parent_verifications.csv`。

注入 9 种全拦住。候选行 `BJ:920022|FIN.NPDEDT.SQ|20250630`：

| 情形 | 结果 |
|---|---|
| 无登记 | `PENDING_SOURCE_PROVENANCE` |
| 登记两个来源维度 | 来源维度补齐 → `PENDING_CAUSE_UNCOVERED`（原因维度仍未覆盖） |
| 只登记 `PARENT_COMPATIBILITY`（`parent_ok=False`） | 仍 `PENDING_SOURCE_PROVENANCE` |

## 6. G 项：R6 两个实际累计父数

### 6.1 你指出的问题

V8 的父 1 片段是「追溯重述法□适用√不适用……」模板，**没有定位实际累计父数**；
父 2 未交付期间列、单位、调整前后版本。原因在 `sampling_v5.py` 的 `_loc()`：
有上游证据就直接定位该证据，再以 `LOCATED` 判父输入已核。

### 6.2 改法

两个父数**都按金额本身定位**（`locate_amount_in_doc`），片段取金额左右窗口；
逐父交付取值、取值状态、期间列、表头单位字面、调整前后版本；
另交付两父是否同 `version_used`、是否同采用文档、兼容缺口。

### 6.3 三条样本实测

| 样本 | 父1 | 父2 | 父1 片段 | 期间列 | 单位 | 调整版本 | 兼容 |
|---|---|---|---|---|---|---|---|
| S19 `BJ:920289` | `LOCATED_AMOUNT(p.10)` | `LOCATED_AMOUNT(p.3)` | …扣除非经常性损益后的净利润 57,296,869.60 … | 本期累计列 | 元 / `单位：元` | `ORIGINAL` / 未登记采用 | **NO** `NO_VERIFICATION_RECORD` |
| S20 `SH:600008` | `LOCATED_AMOUNT(p.6)` | `LOCATED_AMOUNT(p.1)` | …扣除非经常性损益的净利润 818,989,707.54 … | 本期累计列 | 元 / `单位：元` | `ORIGINAL` / 未登记采用 | **NO** `NO_VERIFICATION_RECORD` |
| S21 `SH:600053` | `LOCATED_AMOUNT(p.6)` | `LOCATED_AMOUNT(p.1)` | …扣除非经常性损益的净利润 -86,542,044.51 … | 本期累计列 | 元 / `单位：元` | `ORIGINAL` / 未登记采用 | **NO** `NO_VERIFICATION_RECORD` |

三条均：同 `version_used` = YES、同采用文档 = `NO_RECORD`、`parent_amount_located=BOTH`。

**但我不再把 `BOTH` 当作「两父核证完成」**：定位只说明两个数在原件里出现，
不证明它们同口径、同调整版本。兼容仍为 NO，`parent_compat_conclusion` 列写的就是这句话。

顺带把抽验脚本的 `_pc()` 与生产统一：撤销「同文档 / 上游双否 / 采用同文档」三条捷径
（此前抽验表比生产更宽，是我自己造成的口径不一致）。

## 7. 故障注入与自检

| 对象 | 本轮复算 |
|---|---|
| V1 | C13 **6** / C14 **11,936** / C17 **12,076** |
| V4 映射后 | C26 **7,729** / C14 **6,617** / 受限方法自身期间 **5,270** |
| V5 自身 | C13 / C14 / C17 / C26 均 **0** |

你指出的 V4 数字（7,714 / 6,602 各少 15）已按 `review.json` 的实测值改到
`REPORT.md`、`handoff.md`、`data/active_issue.json` 与上一轮汇报。

自检 40/40 PASS，`self_check_version = V9`。

## 8. 文本同步（逐条）

- V4 数字 → **7,729 / 6,617**（`REPORT.md`、`handoff.md`、`active_issue.json:561–562`、`report_to_codex_round9.md`）。
- `active_issue.json` 状态 → `S00_ERRATA_V5_SELF_CHECK_V9_PASS_AWAITING_RECHECK_10`，
  `next_recommended_reason` 不再写「V7 已交付、等第八轮复核」。
- `NO=3,768` 与 `NA=13,330` 分开写统计范围：重述差异 17,009 为 NO **3,679** / NA 13,330；
  全量 17,728 为 NO **3,768** / NA 13,960。
- `dispute_ledger.csv` → **10,618 行 / 10,618 个唯一 ID**。
- 「9,954 条已解决项」→「**合计 9,954 条 / 631 份文档，其中已解除 8,655 条 / 630 份**，
  已解除部分同样须复审」。
- 撤回「C24/C14 不再可伪造」「R6 两父核证完成」。

## 9. 数字（与上一轮相比只有补充，没有变化）

| 项 | 值 |
|---|---:|
| 重述差异 | 17,009 |
| 已解除 `RESOLVED_SCOPE_COVERED` | 8,699 |
| 待核 `PENDING_SCOPE_LIMITED_METHOD` | 6,373 |
| `PENDING_PARENT_COMPATIBILITY` | 1,277 |
| `PENDING_SOURCE_PROVENANCE` | 47 |
| `UNRESOLVED_EVIDENCE_CONTRADICTS` | 15 |
| 重述差异待处置 | 8,309 |
| 全表核心未闭合 / 含补充 | 9,113 / **10,618** |
| 全池 | 44 HOLD / 231 待核证 / 378 无关联 / 320 NOT_AFFECTED / 81 STILL_PASSES_WITHOUT |
| 受限表 | 407 行 / 401 唯一差异 ID |

## 10. 本轮仍不做的

- 不做第 4 步批量核证。按你第 4 条裁定，**先把本轮发现的核证入口修好，再开展解除操作**；
  三个登记表（`parent_verifications.csv` / `scope_verifications.csv` / `content_reviews.csv`）
  仍为空，1,505 格补充元数据全部停在 `PENDING_FIELD_LEVEL_CHECK`。
- 不做第 5 步重算分层；44 / 231 / 378 不锁定。
- 不启动 S04 第二轮正式验收，S05 保持 `WAITING_DEPENDENCIES`。
- 不宣称「入口不可伪造」：只宣称你实测过的路径已堵住，下一轮若有新绕过仍会退回。

## 11. 请裁定的三个问题

1. **来源维度登记的引文要求含「该行期间年份」**，这是我为堵「通用摘录」加的形式约束。
   若某行的季度表来源确实只能引到不含年份的表头（例如整页只有「单位：元」），
   是否允许改用「表格标题 + 页码」作为替代绑定形式？
2. **父输入登记的 `adjust_version` 我限定为 `ORIGINAL` / `RESTATED` / `SAME_VERSION` 三值**，
   并要求两父一致。若某键的两父确实分别来自原文与重述版（且这样相减才是正确的），
   这个约束会误拦。是否需要增加 `MIXED_DECLARED` 并要求额外说明？
3. **C24 的 `original_value_text` 对内部枚举字段必须由 `judgement_basis` 写映射**。
   若你要求枚举字段也必须在原件里找到字面对应，那 19 列里有 7 类（`period_source` /
   `source_kind` / `adoption_reason` / `comparability_note` / `upstream_hold_fields` /
   `evidence_label` / `status_reason`）本质上不可能满足，需要你明确这些字段的核证形式。
