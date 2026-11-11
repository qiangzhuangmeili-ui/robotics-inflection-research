# 第十三轮汇报：S00 勘误 V5 自检 V12（回应第十二轮 `RETURN_FOR_REWORK`）

- 目录：`runs/issues/S00/errata_20261111_v5/`
- 自检版本：**V12**，**41/41 PASS** → `SELF_CHECK_PASS_WITH_UNRESOLVED_ITEMS`
- 上一轮裁决：`_codex_out_round12.txt`（274 行）**`RETURN_FOR_REWORK`**，G 通过，A/B/C/D/E/F/H 不通过
- 本轮改动范围：**只改判据与校验，不改数据**。全链重跑后 `meta_diff.csv`、`summary.json` 的 md5 与改前逐字节相同（`c9063515…` / `027e063d…`）
- 复现：`build_errata_v5.py` → `check_l2_v5.py` → `sampling_v5.py` → `replay_polarity_v5.py` → `verify_v5.py`

---

## 0. 一句话

上一轮七项不通过里有六项，问题不在「判据不够严」，而在**判据判错了方向**：
词尾判主语、取第一个重复金额、页码当金额、清单自身不受检、窗口不设跨度、退出原因不归因。
本轮把六处判据换成**结构性判据**（中心语 / 目标行绑定 / 期间语义类 / 清单自证 / 跨度上限 / 四类归因），
第七项（H）把「两处维护同一份摘要」改成**单一写者 + 结构检查**。

---

## 1. A 项：极性「新主语」改按中心语判

### 1.1 你给的四条反例

| 输入 | 上一轮判定 | 应为 | 原因 |
|---|---|---|---|
| `…其中营业总收入金额为100.00元` | 续写 | 新主语 | 词尾「为」被当功能词 |
| `…其中营业总收入确认的金额100.00元` | 续写 | 新主语 | 词尾「金额」被当计量单位 |
| `…其中营业总收入合计100.00元` | 续写 | 新主语 | 词尾「合计」被当汇总词 |
| `…影响0.00元，影响增加100.00元` | 新主语 | 续写 | 词尾「增加」被当动词 |

### 1.2 改法：不再看词尾，取中心语

`evidence_scope._head_noun()`：用闭集功能词/动词/量词表 `_TAIL_STRIP` 从右往左反复剥离
（`的/后/元/及/和/对/按/以/为/是/达/合计/金额/影响/增加/减少/…` 加标点与数字），
剩下的名词片段即中心语。`_new_subject()` 判据：

```
中心语为空                                  → 续写
中心语含受影响权益项目（_RE_SCOPED_ITEM）    → 续写
中心语含原因短语（_CAUSE_ANY）              → 续写
中心语含治理/程序词（_RE_PROCEDURE）         → 续写
否则                                        → 新主语（且长度 ≥ 2）
```

四条反例记为 ⑯⑰⑱⑲，另加 ⑳ 守护「同分句原因就近命中时不按 `new_subj` 否定」。
`polarity_cases.py` 33 → **38 条**，C34 全过。

### 1.3 `tgt` 分支：上一轮汇报与代码不符，本轮说清

上一轮汇报写「已给 `tgt` 分支也加了 `new_subj`」，代码里没有。**本轮确认不加，且这是有意的**：

- `tgt` = 本分句内原因词就近命中。此时金额无论挂在哪个项目上，都能证明该事件确实发生，
  加 `new_subj` 会丢掉真肯定；
- `new_subj` 只约束 `single` / `prev_causes` 两条**跨分句继承**分支，作用是防止把别的
  主语的金额算到上一分句的原因头上。

docstring 第 6 条写明了这个区别。汇报从此与代码一致。

### 1.4 「从未触发」这句话撤回，改为给数字

上一轮写「新判据在真实证据上从未触发」，你的插桩显示调用 88 次、判真 44 次——那句话无据。
本轮把计数器直接打进 `replay_polarity_v5.json`：

```
documents 1007 / clause_changed 0 / polarity_changed 0
new_subject_calls 88 / new_subject_true 0 / new_subject_true_nonzero 0
head_nouns {"附注：由于重大会计差错更正影响期初未分配利润": 44, "同一控制合并范围变更": 44}
```

两点如实交代：

1. 中心语在 1,007 份存量证据里**只出现两种**，且都是原因短语。补词表前那 44 次「判真」
   全部来自 `同一控制合并范围变更`——它是原因短语，只是没写成「同一控制下企业合并」，
   被旧词表漏掉，于是被误判成新主语。该条不影响结论（同分句原因词就近命中，走 `tgt` 分支）。
   本轮把 `同一控制下?[^，。；]{0,4}合并`、`合并范围变更` 补进 `_CAUSE_ANY`，判真降为 0。
2. **正确说法是「对存量证据的极性结果无影响」，不是「判据从未触发」。**
   判据是否承重由 38 条反例证明，不由回放证明——回放只能证明「没改坏存量」。

---

## 2. B 项：父输入栏目

### 2.1 你给的三条

1. 同页两个相同金额时取第一个，可能取到别的行；
2. 登记「本期发生额」与原件「本期数」被判为不同列，属误拒；
3. 扫描页（无文本层）应记「待回读」，不是「不可解」。

### 2.2 改法

`parent_verify.column_of_amount_ex()` 返回 `(列头, 金额, 状态)`，状态五态：

| 状态 | 含义 | 调用方处理 |
|---|---|---|
| `OK` | 目标行 + 列头都定位到 | 比对列头 |
| `NO_WORDS` | 该页无文本层（扫描页） | `PARENT_COLUMN_NEEDS_REREAD`（待回读） |
| `NO_AMOUNT` | 目标行里找不到该金额 | `PARENT_COLUMN_UNRESOLVED` |
| `AMBIGUOUS` | 同页/同行有多个相同金额，无法绑定 | `PARENT_COLUMN_AMBIGUOUS` |
| `NO_COLUMN` | 金额上方无期间列头 | `PARENT_COLUMN_UNRESOLVED` |

- `label` 参数把金额**绑定到目标行**（`rows_of_words()` 先按 y 坐标分行，再取标签所在行），
  同页重复金额记 `AMBIGUOUS`，不再「取第一个」；
- `cols_equivalent()` 先按**期间语义类**比对，再退回子串：

```
PRIOR_YEAR_SAME  上年同期/上期/上期数/上期发生额/上期金额/同期数/比较期
YEAR_OPEN        年初/期初/上年年末/上年度末/年初数
PERIOD_END       期末/期末数/年末/年末数
CURRENT          本期/本期数/本期发生额/本期金额/本报告期/报告期/本年累计/本期累计/本年数
```

「本期发生额 vs 本期数」同属 `CURRENT`，不再误拒。

### 2.3 验证

C37 注入链 29 → **35 环**，新增 6 环正是这三条：
`real_column_needs_reread`、`real_column_ambiguous`、`duplicate_amount_ambiguous`、
`duplicate_amount_row_bound`、`column_synonym_ok`、`column_antonym_rejected`。
逐环断言拒绝原因，`violations = []`。

---

## 3. C 项：C24 文本字段与页码

### 3.1 你给的三条

1. 「见第12页附表说明」里的 12 冒充金额；
2. `SELF_PAGE` 取「该金额最早出现的页」，页眉重复金额会把第 1 页当成答案；
3. `currency='CNY'` 遇「记账本位币：人民币」被拒，属误拒。

### 3.2 改法

**数量而非数字**：`evidence_label` 须「标签 + 20 字内**数量**」，数量定义为
带单位（`元/万元/千元/亿元/%/％`）或带小数（`\d+\.\d{1,2}`）；命中页码/表号正则
`_RE_PAGE_REF`（`第N页/表/行/节/项/条`、`见第N页/表`、`附表N`）一律记
`REVIEW_LITERAL_NUMBER_IS_PAGE_REF`。

**目标行定位**：`SELF_PAGE` 不再比两个自报页码，也不取「最早出现页」，而是：
词坐标 → 指标名同行 → 该金额 → 列头，四者同时成立才认这一页；
无词坐标时退回「同页同时出现指标名与该金额」。`NO_AMOUNT / AMBIGUOUS / NO_COLUMN`
各有独立拒绝原因。

**币种受控映射**：`CURRENCY_ALIASES = {CNY: {CNY, RMB, 人民币, 人民币元, 元}, HKD: {...}, USD: {...}}`，
只在组内互认，不做模糊匹配。

### 3.3 直测（写进 C38 的 `literal_path_ok`）

```
「2025年上半年营业总收入见第12页附表说明文字为索引」 → 拒（页码冒充金额）
「2025年上半年营业总收入100.00元，较上年同期增长」   → 收（带单位数量）
currency=CNY /「金额单位：人民币元；记账本位币：人民币」→ 收（受控映射）
```

`literal_path_ok = True`、`unit_path_ok = True`。

---

## 4. D 项：裁决清单自身受检

### 4.1 你给的两条

1. 把 `ruling_scope.csv` 里的 `ruling_file_sha256` 改成 64 个 0，裁决照样生效；
2. 清单只有一个 section，「改成另一个已登记 section」无法构造。

### 4.2 改法

新增 `scope_row_ok(section, ent)`，四道关：

| 返回 | 触发条件 |
|---|---|
| `RULING_SCOPE_FILE_UNBOUND` | 清单行没写 `ruling_file` 或 `ruling_file_sha256` |
| `RULING_SCOPE_FILE_MISSING` | 清单里写的裁决文件不存在 |
| `RULING_SCOPE_FILE_HASH_MISMATCH` | 文件实算 sha256 ≠ 清单写的值（**这条挡住「改哈希」**） |
| `RULING_SCOPE_FILE_DISAGREES` | 登记条目自报的裁决文件/哈希 ≠ 清单行 |

`ruling_gap()` 在「键在允许范围内」之后立刻调 `scope_row_ok(section, ent)`。

### 4.3 关于「换另一个已登记 section」：说清为什么构造不出来，并给了等价测法

真实清单只有 1 行（`Q2 大豪科技改判 → SH:603025|FIN.REV.SQ|20250331`）。
把 section 换成另一个，裁决行文本就对不上，会**先**被 `RULING_SECTION_MISMATCH` 拦下，
测不到白名单本身。所以这条攻击在真实数据上不可构造。

本轮改为**直接改清单内容**：把该 section 的 `allowed_key` 换成同公司另一个已登记字段
（`FIN.NPDEDT.SQ`），再单独调 `ruling_gap`，必须返回 `RULING_KEY_NOT_IN_SCOPE`。
效果上等价于「允许范围被换成了别的条目」，且不依赖任何自报字段。

C14 注入 10 → **13 种**：新增 `scope_file_sha_disagrees`、`scope_row_hash_tampered`、
`scope_allowed_key_narrowed`。`reason_mismatch = {}`、`not_caught = []`、正例对照仍通过。

---

## 5. E 项：窗口规则下沉

### 5.1 你给的两条

1. 维度载体词放在 501 字之外，仍算同窗口；
2. 页脚写「分季度见附表」，也算 `QUARTERLY_TABLE_PROVENANCE` 覆盖。

### 5.2 改法

上一轮的窗口规则只活在 `verify_v5._dim_window` 里，`scope_dims()` 用的是另一套三词检查——
又是「同一规则两处实现」。本轮**下沉到 `parent_verify.dim_window_ok(q, key, dim)`**，
`scope_dims()` 与自检共用同一份：

- 三词（指标名 + 该行具体期间 + 维度载体）跨度 ≤ `_MAX_DIM_SPAN = 160`；
- 载体词所在句不得是注释/页脚：`注：/附注/脚注/见附表/附表见/页脚/见附录/详见`；
- `scope_dims()` 内原三词检查替换为 `if not dim_window_ok(q, key, dim): continue`。

C38 注入 12 → **14 种**：新增 `rejected_quote_marker_too_far`、`rejected_quote_footnote_marker`，
全部拦住。

---

## 6. F 项：抽样键集变更的退出归因

### 6.1 你给的两条

1. `SH:600060|FIN.NPDEDT.SQ|20260630` 仍满足 `_r6_pred`，退出原因是**排序/名额截取**，
   不是「不再命中判据」；
2. 汇报说「新增 600143 两父数均定位」，而 `parent_orig_verified` 实为 920289 ONE /
   600143 ONE / 600008 NONE。

### 6.2 改法一：判据单点定义

入选判据原来是抽样循环里的匿名 lambda，diff 无法复用，只能笼统写一句。
现在提为**具名谓词**：`_pred_r1` … `_pred_r10`、`_pred_r5a/_r5b/_r5c_conflict/_r5c_event`、`_r6_pred`；
抽样用它，退出归因也用它——**同一个谓词**。

### 6.3 改法二：`REMOVED` 必须归到四类之一

| `exit_code` | 含义 |
|---|---|
| `LEDGER_KEY_GONE` | 台账里已没有这个键（键集本身变化） |
| `PREDICATE_FALSE` | 键还在台账，但按当前定位器重算不再命中该风险类型的入选判据 |
| `RANK_CUT` | 判据仍成立，被「同公司去重 / 候选池上限 14 / 评分取前 3」截掉 |
| `UNKNOWN` | 判据未登记，须人工判定（**不得默认成前两类**） |

并且**自证**：`RANK_CUT` 必须谓词为真、`PREDICATE_FALSE` 必须谓词为假、
`LEDGER_KEY_GONE` 必须台账无该键。结果写进 `sampling_v5.json:keys_diff.exit_code_selfcheck`，
由 **C31** 纳入 PASS 条件（`checked` 必须等于 REMOVED 行数，`bad` 必须为空）。

当前值：

```
rows 28 / KEPT 26 / ADDED 1 / REMOVED 1
removed_exit_code {"SH:600060|FIN.NPDEDT.SQ|20260630": "RANK_CUT"}
exit_code_selfcheck {"checked": 1, "bad": [], "ok": true}
reason: 判据仍成立（R6_CROSS_DOC_PARENT 谓词为真），但被名额规则截掉：
        同公司去重 → 候选池上限 14 家 → 按定位结论 BOTH/ONE/NONE 排序取前 3
```

### 6.4 改法三：R6 说明按字段逐字对应

`_LOCATED_TXT` 表：`BOTH` → 「两个实际累计父数均已按金额在原件定位」；
`ONE` → 「仅一个实际累计父数在原件定位，另一个未定位（**不得记作两父均已定位**）」；
`NONE` → 「两个均未在原件定位」。600143 现在写作 `ONE`。

**关于 920289 / 600008 的定位结论**：本版如实照抄字段值，不另行描述。
`parent_orig_verified` 的三个值（920289 ONE / 600143 ONE / 600008 NONE）与本轮汇报一致；
`covered_requirements` 里「两父输入原件均已定位」一项因没有 `BOTH` 而为 `false`——
这是事实，不是缺陷，写在这里以免下一轮又被当成「已完成」。

---

## 7. H 项：状态文件单一写者

### 7.1 你给的两条

1. `active_issue.json` 的 `s00_errata.checks` 仍是「V10：C34 30 条反例；C37 27 环；C14 9 项」；
2. `sampling.unique_keys_note` 仍称「600060 新增、无删除」。

### 7.2 改法：不是「再改一次」，是把写者收敛成一个

根因是**同一份摘要有两个写者**（`verify_v5.py` 写 `review.json`，另一个人工/临时脚本写
`active_issue.json`）。本轮：

- 派生字段（`status` / `self_check_version` / `self_check` / `checks` / `sampling` /
  `round` / `decision` / `report_to_codex`）改由 `verify_v5.write_status()` **唯一写出**；
- 写出内容只含**指针与版本号**，不复述条数、环数、注入种数、键数、增删结论：

```json
"checks":   {"canonical": ".../review.json#checks", "count": 41, "note": "…不在状态文件复述…"}
"self_check": {"version": "V12", "checks": 41, "pass": 41, "canonical": ".../review.json#checks"}
"sampling": {"canonical": ".../sampling_v5.json", "rows": ".../sampling_v5.csv",
             "keys_diff": ".../sampling_keys_diff.csv", "locator_version": "V12"}
```

- 新增 **C39**：旧计数口径必须消失（`条反例|环 =|种伪造|种绕过|PASS（V` 一律不许出现）、
  版本必须等于本次、`locator_version` 必须与 `sampling_v5.json` 一致、
  状态必须含 `AWAITING_RECHECK_13`。

### 7.3 幂等性

连跑两次 `verify_v5.py`：

```
active_issue.json md5 = 0e24ec3e5f31a854c82566491bad68b8（两次相同）
review.json      md5 = 341c9723100867604532bf0b6ac767c6（两次相同）
```

即：`reviewed_at` 与 `generated_at` 都改成固定值，重跑不再产生「只差时间戳」的 diff。

---

## 8. G 项：保持通过，本轮未改

G（C24 注入键集合与预期原因集合严格相等、`_leak_with` 显式决定登记表、`not_exercised` 判失败、
枚举注入纳入 PASS 条件）本轮未动。当前状态：
`injections` 13 键 + 枚举 1，`injection_keys_equal_expect = True`，`not_exercised = {}`。

---

## 9. 自检与数字（V11 → V12）

| 项 | V11 | V12 |
|---|---|---|
| 自检 | 40/40 | **41/41**（新增 C39） |
| C34 极性反例 | 33 条 | **38 条**（⑯–⑳） |
| C37 注入链 | 29 环 | **35 环** |
| C14 注入 | 10 种 | **13 种** |
| C38 注入 | 12 种 | **14 种** |
| C24 注入 | 13 键 + 枚举 1 | 13 键 + 枚举 1（未变） |
| 抽样定位器 | V11 | **V12** |
| 抽样键集 | 27 键 | 27 键（KEPT 26 / ADDED 1 / REMOVED 1） |
| `meta_diff.csv` md5 | `c9063515…` | `c9063515…`（未变） |
| `summary.json` md5 | `027e063d…` | `027e063d…`（未变） |

数据结论也未变：核心未闭合 9,113 / 含补充 10,618；待处置 8,309；44 / 231 / 378 **仍未冻结**。

---

## 10. 与上一轮汇报口径不一致、本轮已改的地方

| 上一轮说法 | 本轮更正 |
|---|---|
| 「`tgt` 分支也加了 `new_subj`」 | 代码没加，**有意不加**，已写进 docstring 第 6 条 |
| 「新判据在真实证据上从未触发」 | 撤回。调用 88 次、判真（补词表后）0 次，中心语只有两种且都是原因短语 |
| 「新增 600143 两父数均定位」 | 实为 `ONE`，已按 `BOTH/ONE/NONE` 逐字对应 |
| 「600060 不再命中判据」 | 仍命中 `_r6_pred`，退出原因是 `RANK_CUT` |
| 「C37 29 环 / C14 10 种 / C38 12 种」 | 本轮 35 环 / 13 种 / 14 种 |

---

## 11. 复现

```
cd runs/issues/S00/errata_20261111_v5
python -B build_errata_v5.py     # meta_diff.csv / summary.json 逐字节不变
python -B check_l2_v5.py
python -B sampling_v5.py         # 生成 sampling_v5.csv/.json + sampling_keys_diff.csv
python -B replay_polarity_v5.py  # 生成 replay_polarity_v5.json（含 88/0/0 计数）
python -B verify_v5.py           # 41/41 PASS，同时写 review.json 与 data/active_issue.json
```

顺序不能换：`sampling` 依赖 `build` 的产物，`replay` 的 JSON 被 C34 读取，`verify` 依赖全部。

---

## 12. 本轮没做的事（照旧，不因自检通过而改变）

- 第 4 步批量核证（文档级事件确认 / 字段级影响确认 / 采用链确认）**未开始**；
- 第 5 步重算分层与受限表**未开始**；44 / 231 / 378 未锁定；
- 1,505 格补充元数据：登记表 `content_reviews.csv` 为空 → 0 条放行；
- `parent_verifications.csv`、`scope_verifications.csv` 仍为空 →
  父输入兼容性 YES = 0、来源维度 47 条全部停在 `PENDING_SOURCE_PROVENANCE`；
- 未回读全部 PDF：抽验 37 行 / 20 类 / 27 键；
- 锚定期回退与上游准入的间接依赖未覆盖。

---

## 13. 仍待你裁定的四个问题（与上一轮相同，未擅自决定）

1. 上游 `results.csv` 对 `DOC-E2BDEAB4F6274B6E` 的 `verdict=否` 与原文相反，
   修正动作归 S02 还是 S00 勘误？
2. 累计差分「正常同口径相减」的充分依据，除两父原文核证外是否还接受别的证据形式？
3. `PENDING_EVENT_CONFIRMED_SCOPE_LIMITED` 这个中间态是否必要？
4. 是否放行 S04 第二轮与 S05？

第 4 问按你上一轮「本次不放行后续步骤」执行——本轮不放行。
