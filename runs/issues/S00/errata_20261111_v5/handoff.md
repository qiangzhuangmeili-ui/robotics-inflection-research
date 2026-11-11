# S00 勘误 V5 交接说明（自检 V12，第十二轮返工后）

> 版本：`ERRATA_V5`，自检 `V12`，41/41 PASS。
> 性质：**SELF_CHECK**。自检通过 ≠ 独立验收通过。
> 上一版 V4 保留在 `runs/issues/S00/errata_20261111_v4/`，未删除。
> 复现：`build_errata_v5.py` → `check_l2_v5.py` → `sampling_v5.py` → `replay_polarity_v5.py` → `verify_v5.py`（顺序不能换）。

## 0. 第十二轮改了什么（先看这段）

第十二轮裁决 **G 通过、A/B/C/D/E/F/H 七项不通过**。与上一轮不同：这七项里有六项不是
「判据不够严」，而是**判据判错了方向**——Codex 每一处都给的是真实语料上的反例。

| 项 | 绕过（裁决实测） | 改法 |
|---|---|---|
| A 极性 | `…其中营业总收入金额为100.00元` / `确认的金额` / `合计` 仍被当续写；`影响增加` 反被误判新主语；`tgt` 分支是否加 `new_subj` 与汇报不符；「从未触发」与插桩 88/44 不符 | 改为**取中心语**（闭集功能词表从右往左剥离），中心语属权益项目/原因短语/治理参与方/空 → 续写，否则新主语；`tgt` 分支**有意不加**并写入 docstring；回放把调用/判真次数打进 JSON。反例 33 → **38 条** |
| B 父输入栏目 | 同页重复金额取第一个；「本期发生额 vs 本期数」误拒；扫描页记「不可解」 | `column_of_amount_ex()` 返回 `(列头, 金额, 状态)`，`label` 绑定目标行；`cols_equivalent()` 先比**期间语义类**；`NO_WORDS` 记 `PARENT_COLUMN_NEEDS_REREAD`。C37 29 → **35 环** |
| C C24 文本字段 | 「见第12页附表说明」的 12 冒充金额；`SELF_PAGE` 取最早页被页眉抢走；`CNY` 遇「人民币」误拒 | 要求「标签 + 20 字内**数量**」且排除页码/表号；`SELF_PAGE` 改**目标行定位**；新增 `CURRENCY_ALIASES` 受控映射 |
| D C14 适用范围 | 清单里的 `ruling_file_sha256` 改成 64 个 0 仍生效；「换另一个已登记 section」不可构造 | `scope_row_ok()` 校验清单自身文件+哈希并须与登记条目一致；真实数据只有 1 个 section，改为「把 allowed_key 换成同公司另一字段」直测。C14 10 → **13 种** |
| E C38 维度证据 | 501 字远距离拼接仍算同窗口；页脚「分季度见附表」算覆盖 | 窗口规则从 `verify_v5._dim_window` **下沉到 `parent_verify.dim_window_ok()`**，跨度 ≤160 且载体句非页脚。C38 12 → **14 种** |
| F 抽样键集归因 | 600060 退出原因写成「不再命中判据」，实际是**排序截取**；汇报说「600143 两父均定位」，字段实为 `ONE` | 判据提为**具名谓词**，抽样与 diff 共用；`REMOVED` 四类归因（`LEDGER_KEY_GONE`/`PREDICATE_FALSE`/`RANK_CUT`/`UNKNOWN`）并**自证**（C31 纳入 PASS 条件）；R6 说明按 `BOTH/ONE/NONE` 逐字对应 |
| H 维护 | `active_issue.json` 仍留着 V10 的「30 条/27 环/9 种」与「新增该键、无删除」 | 派生字段改由 `verify_v5.write_status()` **唯一写出**，只写指针与版本号；新增 **C39** 检查旧计数必须消失、版本与定位器版本一致 |

`meta_diff.csv` / `summary.json` 全链重跑后**逐字节未变**（md5 前后一致）。

### 0.1 回放的口径更正（上一轮写错的一句）

上一轮写「新判据在真实证据上从未触发」。Codex 插桩显示 `_new_subject` 被调用 88 次、
判真 44 次。本轮把计数打进 `replay_polarity_v5.json`：

```
documents 1007 / clause_changed 0 / polarity_changed 0
new_subject_calls 88 / new_subject_true 0 / new_subject_true_nonzero 0
head_nouns {"附注：由于重大会计差错更正影响期初未分配利润": 44, "同一控制合并范围变更": 44}
```

中心语在存量证据里只有两种，**都是原因短语**；补词表（`同一控制下?[^，。；]{0,4}合并`、
`合并范围变更`）后判真 0 次。正确说法是「对存量证据的极性结果无影响」，
**不能**说「从未触发」；判据是否承重由 38 条反例证明，不由回放证明。

### 0.2 键集变更（`sampling_keys_diff.csv`，`locator_version = V12`）

KEPT 26 / ADDED 1（`SH:600143|FIN.NPP.SQ|20260630`）/ REMOVED 1
（`SH:600060|FIN.NPDEDT.SQ|20260630`，`exit_code = RANK_CUT`：判据仍成立，
被「同公司去重 → 候选池上限 14 → 评分取前 3」截掉）。基线冻结在 `sampling_keys_baseline.csv`。

## 1. 这一版是什么

V5 换掉了「期间相等即闭合」这个错判据，改成「证据覆盖范围 ⊇ 该行断言必需范围」。
第六轮把期间参数改成显式三态、极性改成三分；第七轮把必需范围改成并集、极性重写、
父输入兼容性重做；第八轮修「判据实现与判据主张不一致」；第九轮修「极性判据在换行切分下不稳、
且核证入口仍可被伪造」；第十轮修「新增边界测试不通过 + 五处入口仍可接受形式化依据 +
自检存在前置失败导致空过 + 文本未同步」；第十一轮修「七处判据本身可被一句话绕过」；
**第十二轮修「判据判错了方向」**（中心语、目标行绑定、期间语义类、清单自身受检、
窗口下沉、退出归因、状态单一写者，见第 0 节）。历史各轮见 `REPORT.md` 第二至第五节。

以下为**第十轮十条**（历史，与 `review.json:round10_fixes` 逐条对应）：

- **极性五条新绕过全修**：①`√` 独占一行时，组内出现「纯符号碎片」即把整组拼回；
  ②原因标签带符号（`前期差错更正□`）仍作主语行，不被当成下一组；③同组「勾了适用」
  又「排除了某原因」判 `conflict` 交回原页；④金额绑定不得跨主题（出现其他报表项目词即断开，
  `未发生前期差错更正，营业收入100.00元` 不再误判肯定）；⑤单原因分句的金额直绑，
  不再受 24 字半径限制。反例集 22 → **30 条**；回放 1,007 份证据**分句变化 0 / 极性变化 0**，
  `meta_diff.csv`、`summary.json` 逐字节未变。
- **父输入单位折算键名修正**：`gap()` 原读 `expect[side]["unit"]`，`_expect()` 给的是
  `unit_scale`，折算恒为 1 倍，真实原件 `187,875.40 万元 = 1,878,754,000 元` 会被正确引文**拒绝**。
  现统一读 `unit_scale`，并限定金额字段只接受 `1 / 1000 / 10000` 三档。
- **父输入栏目与版本改为可核**：`p1_column` 须为**期间列头**且出现在引文里；
  `adjust_version` 须等于该父**实际 `version_used` 的归类**（ORIGINAL / RESTATED），
  且引文须有对应标记（重述版含「调整后/重述后/更正后」，原版不得含）。`SAME_VERSION` 免证标签已删。
- **父输入引文源改为回读原件登记页**（`_pdf_page`），不再用 `results.csv.evidence` 上游摘录；
  引文须落在登记页，且同时含**目标指标名 + 期间列头 + 父数**。
- **C24 数值解析修正**：先去千分位逗号再比较（`float("5,667,075,612.52")` 抛错落入文本分支的漏洞）；
  同页上年数冒充本期终值不再过关（`REVIEW_PRINTED_VALUE_NOT_SUPPORT_VALUE`）；
  新增 `REVIEW_KEY_MISMATCH`（登记记录必须属于该键，不再靠「缺文档」偶然拦截）。
- **C24 枚举字段不再由自述举证**：`judgement_basis` 降为描述，判定改走字段规则表
  `FIELD_RULES`（NUM / UNIT / DATE / LITERAL / SELF_PAGE）；11 个无可核验映射的字段
  一律 `REVIEW_FIELD_RULE_UNDEFINED` 留待核。
- **C24 故障注入改为「完整正例为基线、每次只改一个条件」**，并断言具体拒绝原因
  （13 种 + 枚举 1 种，`reason_mismatch` 为空才算 PASS）。
- **C14 绑定正式裁决表条目**：引文所在行必须是裁决表行（`| Qn 标题 | 结论 |`），
  裁决项标题必须点名该键，结论须来自该行结论单元格 → 「三项都填大豪科技 + 引第 88 行
  文档登记说明」返回 `RULING_LINE_NOT_A_RULING_ROW`；第 235 行 Q1 通用条目同样被拒。
  大豪科技原裁决仍成立（正例对照通过）。第十一轮复核中断前又暴露两处：`ruled_key` 未绑定（同公司换字段仍能过）、结论只查子串（「不代表全公司验收」能过）——现分别返回 `RULING_KEY_MISMATCH` 与 `RULING_VERDICT_NEGATED`，C14 注入 9 种〔第十一轮增至 10 种，**第十二轮增至 13 种**，见第 0 节〕。
- **C38 来源维度核对 `source_page` 并绑定维度证据载体**：引文须落在登记页（正整数页码、
  该页可定位），且须含该维度自己的载体词（分季度 / 季度主要财务数据 / 第 N 季度；
  比较 / 上年同期 / 期初 / 调整前）。封面片段 `Ltd.年度报告——2025——` 不再同时取得两个维度。
- **R6 改为按词坐标确认目标行与目标列**：金额所在行左侧标签须含目标指标（支持换行标签回退），
  列头取金额 x 区间正上方最近的期间列头，单位绑定该表表头并做固定映射对照，
  调整前后取列头附近 ±20 行内的原件标记。定位结论按 `parent_amount_located` 逐字对应：
  `BOTH` 才可写「两父均已定位」，`ONE` 须写「仅一个定位、另一个未定位」。第十二轮复核
  指出上一轮把 600143（实为 `ONE`）写成「两父均定位」，已改；`SH:600060@20260630`
  本轮已不在样本内（退出归因 `RANK_CUT`）。

核心待处置 **8,309**（重述差异）/ 全表核心未闭合 **9,113**、含补充列 **10,618**。

## 2. 数字（均与台账一致，可复算）

### 2.1 重述差异（17,728 条元数据差异中的 17,009 条 `restatement_flag`）

| 处置 | 条数 |
|---|---:|
| `RESOLVED_SCOPE_COVERED` | 8,699 |
| `PENDING_SCOPE_LIMITED_METHOD` | 6,373 |
| `PENDING_PARENT_COMPATIBILITY` | **1,277**（全部待核，无自动放行） |
| `PENDING_WEAK_ASSUMPTION` | 515 |
| `PENDING_SOURCE_PROVENANCE` | 47 |
| `PENDING_CAUSE_UNCOVERED` | 43 |
| `UNRESOLVED_DOC_NEVER_VERIFIED` | 26 |
| **`UNRESOLVED_EVIDENCE_CONTRADICTS`** | **15**（三协电机） |
| `PENDING_CONFIRMED_EVENT_FIELD_OPEN` | 8 |
| `UNRESOLVED_EVIDENCE_MISMATCH` | 4 |
| `PENDING_CONFIRMED_UNSUPPORTED` | 1 |
| `RESOLVED_BY_RULING` | 1 |
| **合计** | **17,009** |

自身期间 / 非自身期间 = **15,769 / 1,240**；非自身期间处置 = **1,239 待核 + 1 条裁决解除**（大豪科技）。
待处置（`PENDING_*` + `UNRESOLVED_*`）合计 **8,309**（= 17,009 − 8,699 − 1）。
父输入兼容性：重述差异 17,009 → YES **0** / NO **3,679** / NA 13,330。

### 2.1b 其余四列（`status` 555 / `document_id` 83 / `pit_status` 48 / `consolidation_scope` 33）

`RESOLVED_NORMALIZED_DELTA` 354 / `UNRESOLVED_NO_EVIDENCE` 225 /
`UNRESOLVED_FIELD_NOT_IN_RECORD` 116 / `UNRESOLVED_EVIDENCE_MISMATCH` 16 /
`UNRESOLVED_RECORD_IS_REMOVE` 8，合计 **719**，未闭合 **365**。

两表相加 = 17,728 行 / 未闭合 **8,674** 行，与 `summary.json:meta_diff.open` 一致。

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

`HOLD_PENDING_ERRATA` **44**、`R2_MAY_CHANGE` **231**、`R1_NO_LINK` **378**、
`NOT_AFFECTED` **320**、`STILL_PASSES_WITHOUT` **81**。
受限表 **407 行 / 401 个唯一差异 ID**；重述差异按「方法 × 覆盖签名 × 极性 × 来源 × 自身期间」分 **89 组**。
全量 17,728 的父输入兼容性：YES **0** / NO **3,768** / NA 13,960。

**44 / 231 / 378 均未冻结**，本版不锁定任何名单数字。

## 3. 文件

| 文件 | 说明 |
|---|---|
| `evidence_scope.py` | 判据唯一实现（`analyse` / `option_group` / `required_scope` / `judge(scope_ok=…)`） |
| `meta_classes.py` | 元数据字段影响分类唯一来源（防止台账自报分类绕过） |
| `l2_core.py` | 依赖引擎（按 B 实际 `status` 分支展开父键） |
| `parent_verify.py` | 父输入兼容性与来源维度核证的判据（生产与自检共用，27 列登记表） |
| `polarity_cases.py` | **38 条**极性反例的唯一来源（C34 与独立脚本共用） |
| `build_errata_v5.py` | 台账构建，含 `parent_compatible()` / `parent_gap()` / `_pdf_page()` |
| `check_l2_v5.py` | 全池影响判定，含稳定 `dispute_id` 与逐表哈希 |
| `sampling_v5.py` | 分层抽验（**37 行 / 20 类 / 27 键**，原件物理页回读 + 父数按词坐标定位） |
| `verify_v5.py` | **41 项**自检（V12）；派生状态字段的唯一写者 |
| `replay_polarity_v5.py` / `.json` | 极性 A/B 回放（旧判据 vs 新判据，1,007 份证据），C34 的 PASS 条件之一 |
| `meta_diff.csv` | 17,728 行；含 `is_own_period` / `parent_compatible` / `parent_basis` / `polarity` / `scope_*` |
| `extra_meta_diff.csv` | 1,505 格补充元数据（19 列），含 `content_review` / `content_review_ref` |
| **`evidence_conflicts.csv`** | 15 行：上游 `verdict` 与原文极性冲突，含传播范围与修正动作 |
| **`content_reviews.csv`** | 补充元数据放行所需的审查登记表（当前为空 → 0 条放行） |
| **`parent_verifications.csv`** | 父输入兼容性核证登记表（**27 列**，当前为空 → YES = 0） |
| **`scope_verifications.csv`** | 比较范围 / 季度表来源核证登记表（当前为空） |
| `dispute_ledger.csv` | **10,618 行 / 10,618 个唯一差异 ID**（含逐条源表哈希） |
| `restricted_claims.csv` | 407 行受限声明，逐表差异 ID + 逐表哈希 |
| `sampling_v5.csv` / `.json` | 抽验明细与汇总（含 `locate_status`、`parent_p1_row`/`parent_p2_row`、两父输入核证、`locator_version`、`keys_diff`） |
| **`sampling_keys_baseline.csv`** | 抽样键集基线（V10 冻结，含 `source_sha256`），供 diff 对照 |
| **`sampling_keys_diff.csv`** | 键集变更留痕：KEPT 26 / ADDED 1 / REMOVED 1，逐键带样本 ID、原因、定位器版本、前后哈希 |
| **`ruling_scope.csv`** | 裁决适用范围清单（`ruling_section → allowed_key`），独立维护，防止 `key`+`ruled_key` 一起改写借用原裁决 |
| `rulings_resolved.json` | 裁决解除清单（路径 + sha256 + 原文片段 + 行号） |
| `report_to_codex_round11.md` | 第十一轮汇报（含与裁决数字不一致之处的交代与待裁定问题） |
| `report_to_codex_round12.md` | 第十二轮汇报（A–G 逐条落实 + H 维护意见） |
| `report_to_codex_round13.md` | 第十三轮汇报（A–H 逐条落实，含「判据判错方向」的更正） |

## 4. 能复现的故障注入

| 对象 | 结果 |
|---|---|
| V1 台账 | C13 **6** / C14 **11,936** / C17 **12,076** / C26 **17,009**（必须 FAIL） |
| V4 台账（旧标签映射后） | C26 **7,729** / C14 **6,617** / 受限方法自身期间 **5,270** |
| V5 自身 | C13 / C14 / C17 / C26 均 **0** |
| C37 撤去父兼容依据 | **35 环（1 正例 + 34 反例）**逐项按预期拒绝，并逐环断言拒绝原因；另有真实原件阳性对照被接受 |
| C37 单位三档 / 错误栏目 / 同数异义 | 分别 `PARENT_QUOTE_WITHOUT_PARENT_VALUE` / `PARENT_COLUMN_MISMATCH`（词坐标核实）/ 被拒 |
| C38 撤去来源核证 | 退回 `PENDING_SOURCE_PROVENANCE`；错页 `SOURCE_PAGE_NOT_LOCATED`、只有标题 `DIM_MARKER_MISSING` |
| C24 **13 键 + 枚举 1 种**伪造 | 全部拦住（无记录 / 未绑定台账 / 换期间 / 缺文档 / 占位审查人+空日期 / 角色未标 / 结论非法 / 片段错页 / 片段为样板 / 终值未声明 / 依据占位 / 同页异数）；注入键集合与预期原因集合**严格相等**，`not_exercised` 为空；正例对照被接受 |
| C14 **13 种**伪造 | 全部拦住（依据写 `x` / 行号偏移 / 无关引文+正确行号 / 识别信息指向他公司 / 裁决条目名不在该行 / 引第 88 行登记说明 / 引第 235 行 Q1 通用条目 `RULING_SCOPE_NOT_LISTED` / 同公司异字段 `RULING_KEY_MISMATCH` / **key 与 ruled_key 同时改写 `RULING_KEY_NOT_IN_SCOPE`** / 否定表述截断 `RULING_VERDICT_NEGATED` / **清单行哈希被改 `RULING_SCOPE_FILE_HASH_MISMATCH`** / **登记条目与清单裁决文件不一致 `RULING_SCOPE_FILE_DISAGREES`** / **allowed_key 被换成同公司另一字段 `RULING_KEY_NOT_IN_SCOPE`**） |

## 5. 边界与未做

- **未回读全部 PDF**：抽验 **37 行 / 20 类 / 27 个键**（键数取自 `sampling_v5.json:unique_keys`），
  覆盖 1,007 份核验文档中的 20 份。回读分布：`MATCH` 18 / `PARTIAL` 5 / `LOCATED` 2 /
  `WEAK_LOCATE` 1 / `NO_PAGE_RECORDED` 5 / 补充字段不适用 6。
- **`NOTE_TRACE_NA` 总量 9,954 条 / 631 份文档，其中已解除 8,655 条 / 630 份，剩余 1,299 条 / 1 份待核**；
  总量与解除量分列，均未做方法适用性复审；已解除部分同样须复审（第 4 步处理）。
- **`NOTE_RETAINED_ERRATA_ZERO` 642 条**（自身 563 / 非自身 79，涉及 42 份文档）未逐条回读原注。
- **1,505 格补充元数据**仅登记字段级核验要求，登记表为空，0 条放行。
- **上游 `results.csv` 对 `DOC-E2BDEAB4F6274B6E` 的 `verdict=否` 与原文相反**，本版只登记为证据冲突，未改上游。
- **未覆盖**锚定期回退与上游准入的间接依赖。
- **第 4 步批量核证、第 5 步重算分层未做**；44 / 231 / 378 未锁定。
- **不给出最终未闭合数**；本文件不构成验收结论。

## 6. 表述纪律（历轮已撤回的四句）

1. ~~「第六轮裁决第 1–3 步已完成」~~ → 第 1 步（修方法）在第八轮仍在返工；第 3 步自检已加牙但仍有同源局限。
2. ~~「原件中不存在该证据」~~ → 改为「**未定位到**」：全文检索未命中不等于原件中没有。
3. ~~「改台账不改代码必被抓住」~~ → 改为「C26/C29 的重算独立于台账自报字段，但与生产共用同一套判据函数，属同源重算，不能替代独立方法验证」。
4. ~~「原文逐字一致（VERBATIM_ORIGINAL）」~~ → 改为「**原文片段已定位**」：20 字连续片段命中只证明该片段出自原件，不等于整段证据逐字无误。
