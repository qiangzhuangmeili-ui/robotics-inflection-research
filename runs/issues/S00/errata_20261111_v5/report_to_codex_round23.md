# S00 勘误 V5：列归属贯穿跨行合并、边界未知判待核（第二十三轮汇报）

- 目录：`runs/issues/S00/errata_20261111_v5/`
- 自检版本：**V20**，**43/43 PASS** → `SELF_CHECK_PASS_WITH_UNRESOLVED_ITEMS`
- 性质：**SELF_CHECK**（同一执行 AI 自验，登记表 `review_role=SELF_CHECK`）
- 上一轮裁决：`RETURN_FOR_REWORK`（3 条返工项，暂不放行批次 C）→ `_codex_out_round22.txt`
- 本轮逐条对照（机器可读）：`rework_round22_result.json`
- **比较基线**（写 SHA，不用 `HEAD`）：本轮"逐键比对"的上轮对象是提交 **`130eef1`**（第二十二轮）；
  上一份汇报里的"上一轮"指 **`b4738b2`**（第二十一轮），再上一份指 **`4ac102d`**（第二十轮）。
- 复现顺序：`step4_parent_scan.py` → `step4_column_witness.py` → `step4_apply_parents.py` →
  `build_errata_v5.py` → `check_l2_v5.py` → `sampling_v5.py` → `replay_polarity_v5.py` → `verify_v5.py`

结论先说：**87 条键集、64 条登记、23 条待核、全部计数、L2 五档，与 `130eef1` 逐位相同**
（唯一差异是 `parent_verifications.csv` 的 `reviewed_at` 由 `2026-11-12` 变 `2026-11-13`）。
新判据在 87 条真实键上 **一次也没触发**——我不把这个当成"判据有效"的证据，见 §五.4。

---

## 一、三项逐条落实

### 1. `_chain_cells` / `column_of_amount_aligned_ex`：跨行合并绕过列边界

**你构造的反例**（我逐字复现，生产返回 `OK` + `本报告期（4-6月）`，旁证返回 `OK` + `本报告期`）：

```text
y=50：单位：元
y=60：项目 x[0,40]；本报告期   x[100,138]
y=70：项目 x[0,40]；（4-6月）  x[134,165]
y=90：营业收入 x[0,45]；100.00 x[100,130]；200.00 x[140,170]
```

**根因（比上一轮说的更具体）**：上一轮把 `bounds` 只传给了 `_header_cells`——那是**行内**合并。
`_chain_cells` 的**跨行**合并这一层仍然只判「跨度重叠 ≥ −3pt + `_compatible`」，
而 `本报告期`(y=60) 与 `（4-6月）`(y=70) 这两条都满足；并起来以后整体跨度变成 `[100,165]`，
`column_of_amount_aligned_ex` 的候选筛选（`c[1] > ax0-8 and c[0] < ax1+4`）只看这个整体跨度，
**越界被拼后的宽度掩盖**。所以不是「边界没算」，是「边界只在其中一层生效」。

**改法**：新增 `_attribution(x0, x1, bounds, core, need_core)` 返回三态
（`OK` / `OTHER` / `UNPROVEN`，`parent_verify.py:711`），把它贯穿三层：

| 层 | 位置 | 判据 |
|---|---|---|
| 行内合并 | `_header_cells` | 待并入片段过 `_attribution`；`OTHER` 不并（不记待核） |
| **跨行合并** | `_chain_cells(cells, x_tol, bounds, core, drops)` | 每次合并重新过 `_attribution`；组里记 `attr`，一在列内一在列外不并 |
| 最终候选 | `column_of_amount_aligned_ex` | `drops` 里若留下期间片段 → 见第 2 项 |

`_chain_cells` 的关键代码（不再靠整体跨度）：

```python
if bounds:
    need_core = bool(_COL_PERIOD_HINT.search(g["text"])
                     and _COL_PERIOD_HINT.search(tx))
    a2 = _attribution(x0, x1, bounds, core, need_core)
    if a2 == "UNPROVEN":            # 见第 2 项
        drops.append((a2, y, x0, x1, tx)); continue
    if a2 != attr or g["attr"] != attr:
        continue                    # 一在列内、一在列外：不得跨列拼
```

**实测**（`_probe_attr.py` 与 `selftest_column_rules.py` D6）：

```
r1_cross_row       OK                              本报告期        （上一版：本报告期（4-6月））
D6 跨行合并不得绕过列边界        PASS st=OK col='本报告期'
C37 cross_row_fragment_not_merged = True
```

### 2. `_amount_bounds` / `_header_cells` / `witness`：无邻数字不能直接当同列证明

**你构造的负例**（我逐字复现，删掉 `200.00` 后生产与旁证都回到 `OK` + `本报告期（4-6月）`）：

```text
y=70：本报告期 x[100,130]；（4-6月）x[134,165]
y=90：营业收入；100.00 x[100,130]
```

**根因**：`_amount_bounds` 在没有相邻数字时返回 `(-inf, +inf)`，而调用侧把 `±inf`
读成「这一侧无约束」。但 `±inf` 的真实含义是**这一侧边界未知**——两者不是一回事。
上一轮我把这两件事混成了一件。

**改法**：`_attribution` 的 `UNPROVEN` 分支——该侧边界未知、且**本次合并会拼起两段期间语义**
（`need_core`）时，要求片段与 `core = (ax0, ax1)`（金额**自身**跨度）**相交**：

```python
if need_core and core is not None:
    if left == -_INF and x1 < core[0]:  return "UNPROVEN"   # 完全在金额左侧
    if right ==  _INF and x0 > core[1]: return "UNPROVEN"   # 完全在金额右侧
```

不相交 → 不并、记 `drops` → `column_of_amount_aligned_ex` 返回
**`COLUMN_ATTRIBUTION_UNPROVEN`（待核）**，而不是按剩下的半截列名返回 `OK`。
旁证 `step4_column_witness.py::_merge_header_cells` 走同一判据，同样返回该状态。

**为什么判待核而不是「排除后返回 `OK` + `本报告期`」**：`本报告期` 与 `本报告期（4-6月）`
在期间语义上不是一回事（后者是单季，`_date_span` 会解出 `4-6月`）。截断就是错判，
所以这里只能待核——这正是你说的「无法证明归属则待核」。

**为什么不会「所有单数字行一律待核」**：`need_core` 只在**两侧都带期间语义**时置真。
单数字行的单个片段（无合并）、普通标签列（`项目`）都走不到这个分支。

**实测**：

```
r2_no_neighbor     COLUMN_ATTRIBUTION_UNPROVEN
D6 无邻数字时不得把邻列片段并回本列   PASS st=COLUMN_ATTRIBUTION_UNPROVEN
D6 单数字行单片段不得判待核          PASS st=OK col='2026年半年度'
D6 单数字行相交片段仍须合并          PASS st=OK col='本报告期（1-6月）'
D6 旁证无邻数字时不得并回本列         PASS merged=2 格 drops=[('UNPROVEN',70,134,165,'（4-6月）')]
D6 旁证相交片段仍合并               PASS merged=1 格 drops=[]
D6 旁证越界片段不记待核             PASS merged=2 格 drops=[]   ← OTHER 与 UNPROVEN 分开
C37 no_neighbor_fragment_pending = True
C37 no_neighbor_overlap_merged   = True
```

**残余放松（方向是过严，不是过松）**：真实窄列（数字很窄、表头很宽且整体偏右）会被判待核。
已写进 `review.json:open_findings` 第 13 条。

### 3. 两组 32 条：分开说、并改成机器记录

**先用生产函数重算**（`cols_equivalent(p1_column, p2_column)`，64 条全跑）：

| 组 | 条数 | 内容 | 是不是有效注入 |
|---|---|---|---|
| **不等价** | **32** | `2026年半年度` 对 `2026年第一季度` 18 条、`本报告期（1－6月）` 对 `2026年第一季度` 6 条、`2026年半年度` 对 `本报告期` 4 条、`2025年半年度` 对 `2025年第一季度` 2 条、`本期数` 对 `（1-9月）` 1 条、`本期数` 对 `2026年第一季度` 1 条 | **是**，`swap_column` 的分母 |
| **等价、被排除** | **32** | `本报告期（1－6月）` 对 `本报告期` **30** 条；`本报告期（1-6月）`（ASCII 连字符）对 `本报告期` **1** 条；`本期数` 对 `本报告期` **1** 条 | **否** |

即：**31 条是带区间名称对 `本报告期`，另 1 条是 `本期数` 对 `本报告期`**——与你算的一致。

**注入方向与拒绝原因（两组分别说）**：

- **32 条不等价**：注入把 `p1_column` 改成 `p2_column`，也就是**另一份文档**的列名。
  它不改变 p1 本文档金额的实际列（改登记不改变原件）。`check_c41` 比对的是
  「登记 vs **本文档**实际列」，所以这 32 条**会被** `P1_COLUMN_MISMATCH` 拦住。
- **32 条等价**：注入后 `p1_column` 变成 `本报告期`，而本文档实际列本就是
  `本报告期（1－6月）`。`cols_equivalent` 判等价，`_no_extra_semantics('本报告期', '本报告期（1－6月）')`
  也判真——登记比实际**更弱**，不是更细。按上一轮已接受的口径（实际更详细可以放行），
  它**按设计放行**，不构成有效注入，不是判据漏了。

**更正上一轮两句错话**：

1. ~~「那 32 行两侧均含区间省略」~~ → 错。实际是**一侧有区间、另一侧为空**的单向缺省，
   且只有 31 条带区间，另 1 条是 `本期数`。
2. ~~「互换后登记变成实际侧真实列名，所以同侧检查不会报」~~ → 错。修改登记名称**不改变**
   该文档金额的实际列；带区间名称注入到短实际列时，新判据正应拒绝。所以这 32 条不是
   「同侧检查不会报」，是「本来就是等价的两侧，互换后登记更弱而非更细」。

**不再手写数字**：`_c41_inject()` 现在同时输出 `_swap_equivalent_excluded = 32` 与
`_swap_equivalent_kinds = ['本报告期（1-6月）|本报告期', '本报告期（1－6月）|本报告期', '本期数|本报告期']`，
汇报侧直接读它，避免文字与产物再漂一次。`_c41_inject` 的注释也已按两组重写。

---

## 二、结果：键集与逐格零变化

三层对比（都是 `git show <sha>:<path>` 与工作区实文件逐格比，键 = `security_id|field_id|period_key`）：

| 产物 | `4ac102d`（第 20 轮） | `b4738b2`（第 21 轮） | `130eef1`（第 22 轮） | 本轮 | 逐格差异 |
|---|---|---|---|---|---|
| `step4_parent_scan.csv` | 87 行 | 87 | 87 | **87** | **0** |
| `parent_verifications.csv` | 64 行 | 64 | 64 | **64** | **0**（仅 `reviewed_at` 64 格日期） |
| `step4_column_witness.csv` | 64 行 | 64 | 64 | **64** | **0** |

- 扫描：`EVIDENCE_OK 64 / BLOCKED 23`；p1 `OK 73 / NOT_FOUND 14`；p2 `OK 70 / NOT_FOUND 17`。
- 旁证：`WITNESS_OK 64`，p1 `OK:AGREE 64`、p2 `OK:AGREE 64`。
- 登记：`registered 64 of 87`，`skipped {not_evidence_ok: 23, version_inconsistent: 0, witness_fail: 0}`。
- 计数：`8611 / 9050 / 10555 / 1214 / 8762`；L2 `43 / 231 / 321 / 81 / 378`。
- `selftest_column_rules.py`：**61 项，FAIL 0**（上一轮 50 项，本轮新增 D6 十一项）。
- `verify_v5.py`：**43/43 PASS**；`C37 violations []`、`C41 semantics_inflation_probe =
  P1_COLUMN_SEMANTICS_UNPROVEN:本报告期（1-6月）⊄本报告期`。

**`COLUMN_ATTRIBUTION_UNPROVEN` 在 87 条真实键上触发 0 次**（`step4_parent_scan.csv` 里该字符串出现 0 次）。
这不是「判据没生效」，是真实版面里没有你构造的那种退化情形；判据生效的证据只在构造反例与自测里。
我按你的要求不预设「必须维持 64 条」——本轮实际结果就是 64 条，但它不是被保住的。

---

## 三、本轮自查发现并修掉的问题（不是裁决点，但会造假）

1. **我第一版自测的「正例」选错了**：把 `（1-6月）` 放在 `x[131,160]`（与金额右边界 130 只差 1pt）
   当作「真实同列换行」的正例。而你的负例是 `x[134,165]`（差 4pt）——两者几何上无法区分，
   拿它当正例等于要求判据在 1pt 与 4pt 之间划线。已改成真正相交的 `x[120,160]`。
   这条如果不改，自测就会以「判据太严」的假象掩盖「正例选错」。
2. **自测用例的表头行只放了一个词**，先触发 `len(cells) < 2` 的表头形状要求，
   用例本身报 `TABLE_BOUNDARY_UNPROVEN`，看起来像新判据失败。已补 `项目` 列。
3. **`open_findings` 有一条陈述已过期**：原写「`content_reviews`、`parent_verifications`、
   `scope_verifications` 三张登记表仍为空」。`parent_verifications` 自第 20 轮起已有 64 行。
   已改为「`parent_verifications` 64 行（23 条仍 BLOCKED）、另两张仍为空」。

---

## 四、边界（本轮不动）

- **批次 C、D、E 与第 5 步未开始**（等你本轮裁决）。
- **S04 第二轮、S05 不放行**；**43 / 231 / 378 未冻结**。
- **F32 未修**：26 份英文版年报仍在池内。
- **`_RE_POLICY` 仍是裸「会计政策」**。
- **`step4_column_witness.py` 与生产共享 `_amount_bounds` / `_attribution` 两个函数**，
  独立性比上一轮又降了一档（现在只剩列聚类路径不同）。见 §五.5。
- **`NO_LABEL_ROW` 带窗仍是经验值**（上下各 ≤2 行、行距 ≤40pt）。
- **表格边界收紧的覆盖率上限未量化**（`open_findings` 第 10 条）。

---

## 五、请你明确表态

1. **`COLUMN_ATTRIBUTION_UNPROVEN` 判待核**（而不是「排除该片段后返回 `OK` + 半截列名」）——
   是否符合你说的「无法证明归属则待核」？我选待核的理由是：`本报告期` 与 `本报告期（4-6月）`
   是不同期间语义，截断即错判。
2. **归属证据取「与金额自身跨度相交」**是否可接受？我明确它是**必要非充分**，方向是过严。
   若你要求改用「同一已确认表格内的列结构」，请指定可接受的结构层（我不能再用整页数字聚类，
   它会把 6 个真实列切成 12 簇，见上一轮 §一.1）。
3. **`OTHER`（可证明是邻列）不记待核**、`UNPROVEN`（证明不了）才记待核——这个区分成立吗？
   我认为「证明不是同列」与「证明不了是同列」必须分开，否则同一表头行有邻列片段就整列待核。
4. **87 条真实键上 0 次触发**：本轮判据在真实语料上没有可观测效果。你是否接受
   「以构造反例 + 自测作为判据生效的证据」，而不是要求真实语料上的命中？
5. **旁证独立性**：现在两条路径共用 `_amount_bounds` 与 `_attribution`。是否需要我把旁证的
   归属算法换成另一套（例如按单元格矩形求交，而不是中心点 + 中点边界）？
   我倾向换，但那会让 `WITNESS_OK` 的判定口径再变一次。
6. **下一步**：批次 C（分季度表来源 + 半年报权益变动表「前期差错更正 0.00」行）是否放行？
