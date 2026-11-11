# S00 勘误 V5 第十一轮返工汇报（报第十二轮复核）

## 0. 一句话

A–G 七项全部改的是**判据本身**，不是再补一条反例；H 项按你的维护意见把「同一份摘要维护两处」拆掉了。
自检 **V11，40/40 PASS**，`meta_diff.csv` / `summary.json` 与上一版**逐字节一致**。
一个必须主动说清楚的结果：A 项新判据在 1,007 份真实证据上**从未触发**（回放零变化）——
它修的是一个只存在于合成语料里的绕过，不能拿零变化当成绩（见第 1 节）。

---

## 1. A 项：极性「结构性新主语」——已修，反例 30 → 33

### 1.1 你给的绕过与修法

```
前期差错更正对期初未分配利润影响0.00元，其中营业总收入100.00元
```

修前：`100.00` 被判成「ERRATA 肯定」。根因是同一分句出现原因词后，后续金额默认继承主语。

前两轮的做法是**扩充报表项目词表**（`_RE_OTHER_ITEM`），这是无底洞——你换一个词表外的项目就再漏一次。
本轮改判据：**金额左侧紧跟片段以名词收尾即为新主语**。

```python
def _new_subject(clause, st, window=10):
    tail = clause[max(0, st - window):st]
    if not tail:                       return False
    if _RE_SCOPED_ITEM.search(tail):   return False   # 受影响权益项目 → 不是新主语
    if _RE_VERB_TAIL.search(tail):     return False   # 动词/量词/标点/数字收尾
    return len(_RE_TAIL_FILLER.sub("", tail)) >= 2    # 剥掉「其中/该/元/数字」后仍有 ≥2 字
```

`_bind_amount` 的三个承接分支（`tgt` 唯一命中 / 单一原因 / 承接上一分句）全部加 `not new_subj`。

### 1.2 新增反例（33 条，全过）

| 反例 | 期望 | 结果 |
|---|---|---|
| ⑭ `…影响0.00元，其中营业总收入100.00元`（**词表外**项目） | `set()` | `set()` |
| ⑭ `…影响0.00元，其中营业收入100.00元`（**词表内**项目，守护） | `set()` | `set()` |
| ⑮ `对所有者权益合计影响100.00元`（权益项目续写，守护） | `scoped=ERRATA` | `scoped=ERRATA` |

⑮ 这条逼出一个错：`_RE_OTHER_ITEM` 里原含「所有者权益合计」，会让它丢失 scoped。
权益项目是**受影响对象**，不是「另一个项目」，已从词表剔除。

### 1.3 A/B 回放：新判据在真实证据上从未触发

新增 `replay_polarity_v5.py`：把 `_new_subject` 临时换成恒 `False`（＝第十轮行为）作对照，
对 1,007 份核验证据各跑一遍 `analyse`，逐条比对 `_clauses()` 输出与
`excluded / affirmed / scoped / mentioned / conflict`：

```json
{"documents": 1007, "clause_changed": 0, "polarity_changed": 0, "changed_samples": []}
```

**这说明什么、不说明什么**：说明本轮修复对存量零影响（所以 `meta_diff.csv` 逐字节未变）；
**不说明**判据变强了——真实年报不会在差错更正影响句后面接「其中营业总收入100.00元」，
所以这条规则一次都没被真实数据触发过。它是一条防合成绕过的护栏，我按实际情况记，
不把它写成「修复生效」。回放结果已纳入 C34 的 PASS 条件（缺文件判 `REPLAY_MISSING`）。

---

## 2. B 项：父输入栏目改按词坐标核实——已修，C37 27 → 29 环

### 2.1 你给的真实绕过

`BJ:920289` 的 `p1_column` 登记为「上年同期」，而金额实际落在「本期」列，仍判 True。
根因：`p1_column` 只被当成「必须出现在引文里的字符串」，**没人核对它是不是该金额所在的列**。

### 2.2 修法

`parent_verify.py` 新增：

```python
def page_words(pdf_path, page):  # 返回 [(x0,y0,x1,y1,text)]，不可用返回 []
def column_of_amount(words, value, x_tol=3.0, y_tol=4.0):
    # 金额词 → x 中心 → 向上找同 x 区间、非数值、最近一行的词 = 该金额的实际列头
```

`gap()` 在栏目判据之后追加：

```python
actual_col = col_of(ent["%s_doc" % side], ent["%s_page" % side], exp.get("value"))
if not actual_col:                                  return "PARENT_COLUMN_UNRESOLVED"
if _col_norm(col) not in _col_norm(actual_col):     return "PARENT_COLUMN_MISMATCH"
```

`_col_norm` 去掉空格 / `*` / `_`，避免「本期 数」这类排版空格造成假阴性。
**取不到列头一律判不可解**，不退回「引文里有就算」。

### 2.3 C37 注入链 29 环

`verification_chain` 29 项（1 正例 + 28 反例），逐项断言具体拒绝原因（25 种不同原因码）。新增两环：

| 新环 | 做法 | 拒绝原因 |
|---|---|---|
| 真实原件·错列 | 真实阳性 `SH:600008\|FIN.OCF.SQ\|20260630` 的登记列头改成另一列（实际列头：`本期数` / `本报告期`） | `PARENT_COLUMN_MISMATCH` |
| 真实原件·列头不可解 | 把该金额挪到一个上方无列头的位置 | `PARENT_COLUMN_UNRESOLVED` |

自动 YES 仍为 **0**，`PENDING_PARENT_COMPATIBILITY` 仍为 **1,277**，`parent_verifications.csv` 仍为空表。

---

## 3. C 项：C24 文本字段按标签绑定 + SELF_PAGE 独立定位——已修

### 3.1 你给的三条绕过

| 绕过 | 修前 | 修后 |
|---|---|---|
| `unit_raw` 填 `元`，`evidence_label` 与金额无关，只要片段里有 `2025` 就过 | 文本分支只要「片段含数字」 | `unit_raw` 须命中 `单位\s*[:：]?\s*(?:人民币)?元` |
| `currency` 同上 | 同上 | 须命中 `(币种\|货币\|记账本位币)\s*[:：]?\s*CNY` |
| `evidence_label` 随便写 | 同上 | 须「标签 + 紧随其后 20 字内出现数字」 |
| `SELF_PAGE` 只比两个**自报**页码 | `original_page == source_page` 即过 | 独立定位：该行金额在原件里**最早出现**的页，必须等于登记页（`REVIEW_SOURCE_PAGE_NOT_FIRST_OCCURRENCE`） |

实现要点：`_LITERAL_LABEL` 表把每个 LITERAL 字段映射到自己的标签正则；没有标签的文本字段
不再走「自述举证」分支，一律 `REVIEW_FIELD_RULE_UNDEFINED` 留待核（当前 11 个字段）。

### 3.2 一个仍要你知道的口径

`SELF_PAGE` 的「最早出现」在扫描件/多栏页上可能被页眉重复数字干扰。当前正例
（`SH:600100|FIN.REV.YTD|20250630|value_raw`）能通过，但这是**单点验证**，不是全类验证。
1,505 格补充元数据登记表仍为空，**0 条放行**。

---

## 4. D 项：裁决适用范围独立维护——已修，C14 9 → 10 种

### 4.1 你给的绕过

同时改写 `key` 与 `ruled_key`，两者相等，于是「借用」原裁决。
根因：`ruled_key == key` 是**自报对自报**，必然自洽。

### 4.2 修法

新增独立文件 **`ruling_scope.csv`**（与台账、与裁决登记条目都分开维护）：

```
ruling_section,allowed_key,ruling_file,ruling_file_sha256,note
Q2 大豪科技改判,SH:603025|FIN.REV.SQ|20250331,runs\issues\S00\errata_20261111_v5\codex_ruling_round4.md,5e6b1d6e…,裁决只解除该键；不得扩用到同公司其他字段或期间
```

`ruling_gap()` 现在要求四者同时成立：

1. `ruled_key` 精确等于待判键（`RULING_KEY_MISMATCH`）；
2. 该 section 在清单里有登记（`RULING_SCOPE_NOT_LISTED`）；
3. 该键在登记范围内（`RULING_KEY_NOT_IN_SCOPE`）；
4. 结论单元格以裁决结论**开头**且不含否定词（`RULING_VERDICT_NOT_IN_ROW` / `RULING_VERDICT_NEGATED`）。

### 4.3 注入表改成一张表管住「改法 → 预期原因」

原来 10 个独立变量、10 个独立布尔，漏一个也没人发现。现在：

```python
_C14_MUTS = [("placeholder_basis", _ph, "RULING_BASIS_TOO_SHORT"), …,
             ("both_key_and_ruled_rewritten", _both_rewritten, "RULING_KEY_NOT_IN_SCOPE"),
             ("negative_verdict_substring", _neg_verdict, "RULING_VERDICT_NEGATED")]
```

10 种逐项比对原因，`reason_mismatch = {}`、`not_caught = []`。

**顺带修了一处我自己的归因错误**：`generic_ruling_item`（引第 235 行 Q1 通用条目）实际拦在
`RULING_SCOPE_NOT_LISTED`——因为 `Q1 document_id 匹配` 不在 `ruling_scope.csv` 里。
上一版把它写成 `RULING_ITEM_DOES_NOT_NAME_KEY` 是错的。后者由 `key_pattern_other_company`
单独覆盖（那一项的 section 是已登记条目）。预期原因已按实际改正，注释也写明了拦截顺序。

---

## 5. E 项：C38 维度证据要求「指标名 + 具体期间 + 载体」——已修

### 5.1 你给的绕过

`_find_dim` 找到的 COMPARATIVE_SCOPE 阳性是：

> 经营计划2025年，公司成功登陆北京证券交易所……报告期初比较

一段经营叙述，既没点出目标指标，也没点出该行的具体期间。

### 5.2 修法

`_dim_window(pages, k, dim)` 要求同页同窗口同时出现：

- 目标指标名（`pv.METRIC_ALIASES`，单季键回落同名 YTD 别名）；
- 该行**具体期间表述**（`_period_tokens`：`20250630 → 半年度 / 上半年 / 6月30日 / 1-6月 / 1月至6月 / 第二季度`）；
- 维度载体词（`DIM_MARKERS`）；
- 窗口内出现该行年份，长度 ≥20 字。

窗口下界取三者位置的**最小值**，保证期间表述被包进引文。

### 5.3 修 C38 时踩到的一个坑（值得记一笔）

第一版只要求「该**页**出现期间表述」，窗口却只包住指标名和载体词。结果下游
`pv.scope_dims()` 因为「引文不含期间」判 `VALID_RECORD_NOT_ACCEPTED`，C38 直接 FAIL。
改法是让窗口把期间表述一起包进来——**同一件事在两层各判一次，两层的口径必须一致**，
否则一处放一处收，看起来像 bug，其实是判据不闭合。

修后 C38 PASS，12 种伪造全拦，正例键 `BJ:920100|FIN.REV.SQ|20250630`，
维度证据页 `COMPARATIVE_SCOPE p.149` / `QUARTERLY_TABLE_PROVENANCE p.10`，
`dims_from_record == dims_required == {两个维度}`，`PENDING_SOURCE_PROVENANCE` 仍 47 条未动。

---

## 6. F 项：R6 词坐标（断行与别列）——已修

| 你指出的问题 | 修法 |
|---|---|
| S21 的「调整前」来自页内**别列** | 版本标记只取与金额 x 区间**重叠**的词：`x1 > ax0 - 2 and x0 < ax1 + 2` |
| 600053 是**断行**误判 | 向上最多回看 3 行逐行拼接（`_acc = _seg + _acc`），直到出现目标指标名；金额行只有部分标签时把上一行补进来再判 |

`sampling_v5.py` 里 R7 三条的定位状态因此变化：`SH:600053` / `SH:600215` 由
`LOCAL_MISMATCH`/未定位改为 `LOCATED(p.168)` / `LOCATED(p.159)`，`SH:603298` 仍是
`WEAK_LOCATE(p.168)`（汇总注非原文，不算已定位）。

---

## 7. G 项：C24 注入断言改严——已修（这是本轮唯一「纯自检」的修）

### 7.1 你列的四条

| 你的原话 | 修法 |
|---|---|
| `no_review` / `unbound_digest` 把原因字符串**直接写进结果元组** | 改走 `extra_leaks` 全链，从返回里取**实际**原因（`_leak_with()` 显式决定登记表里有没有这条记录） |
| `fragment_wrong_page` 没进 `EXPECT_REASON` | 已登记 `REVIEW_FRAGMENT_NOT_IN_ORIGINAL_PAGE` |
| `if k in EXPECT_REASON` 让未登记或拼错的键**静默跳过** | 改为 `set(inj) == set(EXPECT_REASON)` 严格相等，`key_gap` / `key_extra` 任一非空即 FAIL |
| 枚举用例只要求拒绝布尔值 | 把 `REVIEW_FIELD_RULE_UNDEFINED` 纳入 PASS 条件（`injection_enum_ok`） |

### 7.2 顺带堵掉一个同型漏洞

条件型注入（样板片段、同页异数）在构造不出对照物时，原来返回 `(True, "NO_BOILERPLATE_FOUND")`——
**布尔为真、原因是个占位串**，于是「没测到」被算成「测过了」。现在记 `caught=None` 并进
`not_exercised`，`not_exercised` 非空即 FAIL。

当前结果：

```json
{"injections": 13, "injection_keys_equal_expect": true, "expect_reason_keys": 13,
 "key_gap": [], "key_extra": [], "reason_mismatch": {}, "not_exercised": {},
 "injection_enum_rule_undefined": "REVIEW_FIELD_RULE_UNDEFINED", "injection_enum_ok": true}
```

---

## 8. H 项（维护意见）与 `sampling_keys_diff.csv`

### 8.1 同一份摘要不再维护两处

`data/active_issue.json` 顶层 `self_check` 已降为**指针**：

```json
{"version": "V11", "checks": 40, "pass": 40,
 "canonical": "s00_errata.self_check",
 "detail": "runs/issues/S00/errata_20261111_v5/review.json",
 "note": "为避免同一份注入明细维护两处而漂移，顶层只保留版本与计数，明细见 canonical 指向的对象。"}
```

你说得对，本轮之前确实出现过三处版本冲突（`V8` / `V9` / `V10` 各写一处）。现在的做法是
「明细只有一个写者」，顶层只留计数，且由脚本从 `review.json` 回填，不手改。

### 8.2 `sampling_keys_diff.csv` 已固定

列：`status, key, security_id, field_id, period_key, baseline_version, baseline_sample_id,
baseline_risk_type, current_sample_id, current_risk_type, reason, locator_version,
baseline_sha256, current_sha256`

基线冻结在 `sampling_keys_baseline.csv`（V10 的样本键集 + `source_sha256 = 0d0940cc…`）。
本轮结果：

| status | 数量 | 键 | 原因 |
|---|---:|---|---|
| KEPT | 26 | — | 键集未变 |
| ADDED | 1 | `SH:600143\|FIN.NPP.SQ\|20260630` | 单季由两期累计相减，两父输入来自不同文档；两个累计父数已按金额在原件定位 |
| REMOVED | 1 | `SH:600060\|FIN.NPDEDT.SQ\|20260630` | 键仍在台账，但 V11 定位器下不再命中 `R6_CROSS_DOC_PARENT` 的入选判据 |

键数仍 27，但**不是同一批 27 个键**——这正是你要求留痕的原因。

---

## 9. 与裁决数字不一致之处（主动交代）

| 项 | 你裁定时 | 本轮 | 原因 |
|---|---:|---:|---|
| C37 注入链 | 27 环 | **29 环** | 新增两条真实原件负例（错列 / 列头不可解） |
| C14 注入 | 9 种 | **10 种** | 新增 `key`+`ruled_key` 同时改写 |
| C24 注入 | 13 种 + 枚举 1 | **13 键（严格对齐）+ 枚举 1** | 键集合与预期原因集合相等，不再靠「多一个少一个没人管」 |
| 极性反例 | 30 条 | **33 条** | 新增 ⑭×2、⑮ |
| 抽验 | 37 行 / 20 类 / 27 键 | 同 | 键集 1 进 1 出，见第 8.2 节 |
| C38 正例键 | `BJ:920022` | **`BJ:920100`** | E 项收紧后 920022 不再满足「指标名+期间+载体」同窗口，改用 920100（p.149 / p.10） |
| C37 真实阳性键 | `BJ:920289` | **`SH:600008\|FIN.OCF.SQ\|20260630`** | 同上，920289 的列头不可解（`PARENT_COLUMN_UNRESOLVED`），按你上一轮意见「须先换」 |

---

## 10. 复现

```bash
cd runs/issues/S00/errata_20261111_v5
python -B build_errata_v5.py      # 36s，写 5 张差异表
python -B check_l2_v5.py          # 2s
python -B sampling_v5.py          # 13s，写 sampling_v5.csv/.json + sampling_keys_diff.csv
python -B replay_polarity_v5.py   # 3s，写 replay_polarity_v5.json
python -B verify_v5.py            # 36s，写 review.json
```

顺序不能换：`verify_v5.py` 读前四步的产物。`git status` 应显示
`meta_diff.csv` / `summary.json` / `cell_diff.csv` / `key_diff.csv` / `extra_meta_diff.csv` /
`l2_dependency_check.csv` **均未修改**——这是「判据改严但对存量零影响」的机器证据。

---

## 11. 仍未做 / 不宣称

- 不宣称 A 项「修复生效」：回放零变化说明新判据在真实数据上从未触发（第 1.3 节）。
- 不宣称 C 项 `SELF_PAGE` 已全类验证：只有 1 个正例，1,505 格补充元数据仍 0 条放行。
- 不宣称父输入已核：`parent_verifications.csv` 仍为空表，自动 YES 仍 0，1,277 条待核。
- 不宣称第 4 步（文档级事件确认 / 字段级影响确认 / 采用链确认）已开始。
- 不宣称第 5 步重算分层已做；44 / 231 / 378 仍未冻结。
- 不宣称「原件中不存在某证据」：只写「未定位到」。

---

## 12. 待裁定问题

1. **A 项这种「只在合成语料里成立的绕过」要不要继续修？** 本轮修了，但回放证明真实数据一次都不触发。
   如果你认为这类护栏的边际价值低于维护成本，我可以改为「记录为已知边界、不加判据」。
2. **C38 / C37 的正例键一换再换**（920022 → 920100、920289 → 600008），每次都因为判据收紧后
   原键不再满足。是否需要固定一份「正例键白名单」，改判据时只允许在白名单内换？
3. **`ruling_scope.csv` 由谁维护？** 目前是执行方手写一行。若后续裁决增多，
   是否要求「裁决文件 + 适用范围清单」必须同一次提交、且清单里的 `ruling_file_sha256` 由脚本校验？
4. **`sampling_keys_diff.csv` 的 REMOVED 原因目前是机器推导的**（「键仍在台账但不再命中判据」）。
   要不要强制人工填一句具体原因？本轮 600060 这一条我只能机器推导到「不再命中 R6 判据」，
   没有把握说是哪一处改动导致的（F 项动了断行回看，也可能只是抽样顺序变化）——
   与其编一句看起来具体的话，不如先承认推导边界。
