# S00 勘误 V5：取列判据收紧与表格边界（第二十一轮汇报）

- 目录：`runs/issues/S00/errata_20261111_v5/`
- 自检版本：**V18**，**43/43 PASS** → `SELF_CHECK_PASS_WITH_UNRESOLVED_ITEMS`
- 性质：**SELF_CHECK**（同一执行 AI 自验，登记表 `review_role=SELF_CHECK`）
- 上一轮裁决：`RETURN_FOR_REWORK`（6 条返工项，不放行批次 C）→ `_codex_out_round20.txt`
- 本轮逐条对照（机器可读）：`rework_round20_result.json`
- 复现顺序：`step4_parent_scan.py` → `step4_column_witness.py` → `step4_apply_parents.py` →
  `build_errata_v5.py` → `check_l2_v5.py` → `sampling_v5.py` → `replay_polarity_v5.py` → `verify_v5.py`

**本轮同样不改「哪些键应当闭合」，只改判定方法，然后把 87 条全部重推一遍。**
结论先说：**87 条键集、64 条登记、23 条待核、全部计数、L2 五档，全部与上一轮逐位相同。**
唯一的状态变化是 `SH:688800 FIN.OCF.SQ@20251231` 的 p2 由 `OK` 变 `NOT_FOUND`（原因 `AMBIGUOUS`），
该行本就 `BLOCKED`，所以没有任何名单后果。**这不是「没改」，是改严之后恰好没改名单**——
下面每条都给出你点名的反例在本轮的实测输出。

---

## 一、六条逐条落实

### 1. `_header_cells` / `_chain_cells`：区分「互补片段」与「冲突期间」

**你指出的错**（复现无误）：上一版把「两侧 canon 都非空」当成「已是完整列名」，
这一个判据同时管了两件相反的事——对横排的 `本报告期` + `（1-6月）` 过严（拆成两格），
对跨行的 `2025年半年度` / `2026年半年度` 过松（几何合并直接拼成一个候选）。

**改法**（`parent_verify.py:933-971`）：新增三维拆分与兼容判定，替换「canon 非空」：

```python
def _canon_parts(text):      # -> (相对年, 区间, 累计) 三个可空分量
def _compatible(a, b):
    pa, pb = _canon_parts(a), _canon_parts(b)
    for x, y in zip(pa, pb):
        if x and y and x != y: return False   # 任一分量两侧都写了且不同 -> 冲突
    return True
```

- `_header_cells`（`:683`）：并单元格判据由 `not (canon_column(cur) and canon_column(tx))`
  改为 `_compatible(cur, tx)`。`本报告期` 的 `(本期, '', '')` 与 `（1-6月）` 的 `('', R0-1-6, 累计)`
  **互补不冲突** → 合并成一列；两段都写了不同区间 → 不并。
- `_chain_cells`（`:719`）：跨行几何合并**前**先过 `_compatible`。冲突则不并，
  得到**两个候选列链**，由调用方按「期间列候选 >1」判 `AMBIGUOUS`。
  **不是链合并后数候选**——冲突在合并那一刻就被拒绝。

**实测**（`selftest_column_rules.py`，与你的独立夹具同构）：

```
D4 横排互补片段成一列      PASS  st=OK         col='本报告期（1-6月）'
D4 列链冲突期间报歧义      PASS  st=AMBIGUOUS  col=None
```

夹具即你给的那组：`x[100,130]`、`y=70` 写 `2025年半年度`、`y=80` 写 `2026年半年度`，
金额在 `y=90`。上一版返回 `('2025年半年度2026年半年度', '100.00', 'OK', ...)`，本轮返回 `AMBIGUOUS`。

**真实数据上的副作用**（如实报）：`SH:688800 FIN.OCF.SQ@20251231` 的 p2 从 `OK` 变
`NOT_FOUND`，note 为 `11:AMBIGUOUS;1:NO_LABEL_ROW;2:NO_AMOUNT`——该页第 11 页表头区里
`本报告期` 与 `上年同期` 两组片段在同一列范围内冲突，按新判据不再择一。

### 2. `cols_equivalent`：删短路，逐维度比对；年度解析年份

**你指出的错**（复现无误）：生产函数 `cols_equivalent()` 在「两侧都有区间」时直接
`return sa == sb`，把相对年整个跳过：

```
cols_equivalent("上年同期（1-6月）", "本报告期（1-6月）")      # 旧: True
cols_equivalent("上期（2026年1-6月）", "本期（2026年1-6月）")  # 旧: True
canon_column("2025年度") == canon_column("2026年度") == "||累计"  # 旧: 绝对年份丢失
```

**改法**：

- `cols_equivalent`（`:433`）：删掉短路，**逐维度**比对——区间 → 相对年 → 累计，
  任一维度两侧都写了且不同即 `False`；两侧区间都写了且相等、其余维度不冲突才算等价。
- 新增 `_RE_SPAN_YEAR = re.compile(r"(\d{4})\s*年\s*(?:度|全年|报表)")`（`:369`），
  在 `_date_span` 里于「上半年」之后、季度之前返回 `("R", y, 1, 12)`。
  年度不再退化成 `||累计`。

**实测**（本轮现场跑，非引用旧日志）：

```
equiv 上年同期（1-6月） | 本报告期（1-6月）        -> False
equiv 上期（2026年1-6月） | 本期（2026年1-6月）    -> False
equiv 本期金额（2026年1-6月） | 本期金额（2026年4-6月） -> False
equiv 本期金额（2026年上半年） | 本期金额（2026Q2）  -> False
canon 2025年度 -> |R-2025-1-12|累计
canon 2026年度 -> |R-2026-1-12|累计
canon 2026年半年度 -> |R-2026-1-6|累计
```

**同义组仍判等价**（不能靠「一律判不等价」的退化实现通过）：`本期数 = 本报告期`、
`本年累计 = 年初至报告期末`、`2026年半年度 = 2026年1-6月`、`上年同期 = 上年同期金额`，
四项均 PASS。

**C37 补完整链**：新增四个键，全部走 `canon_column → cols_equivalent → gap()` 的真实生产链，
不是自造小函数：

| C37 键 | 断言 |
|---|---|
| `canon_keeps_semantics_via_equivalent` | 11 组异义对**必须连 `cols_equivalent` 一起拒**（旧版只测 canon） |
| `annual_year_kept` | `2025年度` 与 `2026年度` 的 canon 必须不同 |
| `rel_year_rejected_by_gap` | `上年同期（1-6月）` 当 `本报告期（1-6月）` 用，`gap()` 必须拒 |
| `annual_year_rejected_by_gap` | 跨年度换列，`gap()` 必须拒 |

`review.json.C37.detail.verification_chain` 里这四项均 `true`，`violations: []`。

### 3. 金额比较与引文边界

**你指出的三处**（全部复现无误）：

```
页面 100.00，目标 100.004 -> 生产取列 OK        （quantize(0.01) 把两者舍入成相等）
_num_in_quote("营业收入100999999", "100")            -> True
_num_in_quote("营业收入100.00", "999", exact="100.00") -> True
```

**改法**：

1. `_same_amount`（`:510`）由「各自 `quantize(0.01)` 再比」改为**直接比 Decimal**：
   `1.0 == 1.00` 为真（数值相等，不是字符串），`100.004 == 100.00` 为假。
2. 新增 `_has_subcent(d)`（`:495`）：分位以下存在非零尾数即真。
   `column_of_amount_aligned_ex` 入口处先判——命中即 `AMOUNT_PRECISION_INVALID`，
   **不参与任何匹配**（不是「取到再比」）。`gap()` 映射为 `PARENT_AMOUNT_PRECISION_INVALID`。
3. `_num_in_quote`（`:132`）重写为**两级**，删掉你说的「任意数字位切分」第三级：
   - 给了 `exact`：必须**同时**满足「该金额词的原文在引文里」**且**「该词数值 × `unit_scale` == 目标」；
   - 未给 `exact`：只做**严格 token 全等**，不做任何切分兜底。

**实测**：

```
_num_in_quote("营业收入100999999", "100")              -> False
_num_in_quote("营业收入100.00", "999", exact="100.00") -> False
_num_in_quote("营业收入100.00", "100", exact="100.00") -> True    （正确用例仍命中）
_same_amount(100.00, 100.004) -> False ;  _same_amount(1.0, 1.00) -> True
_has_subcent(100.004) -> True ;  _has_subcent(100.00) -> False
```

自测：`D3 100.009 不得匹配 100.00  PASS st=AMOUNT_PRECISION_INVALID`、
`D3 100.004 不得匹配 100.00  PASS`、`D3 引文数值逐位相等 PASS`、`D3 取消任意数字位切分 PASS`、
`D3 exact 须核对数值 PASS`。

**关于「去掉 `_AMOUNT_TOKEN` 右边界」这件事的收口**：右边界之所以不能加，是 PDF 文本层
去空白会把相邻两列数字粘连（`684,956,197.48` + `585,346,923.80` → `…923.80` 接 `585,346,923.80`）。
本轮不再用「切分」补边界，而是**把定位权交回词坐标**：`column_of_amount_aligned_ex` 返回
`amount_word`（词元组），`step4_parent_scan._quote()` 按词偏移在原文定位，
`_num_in_quote` 只做「这个词的原文 + 这个词的数值」双向核对。粘连不再靠猜，靠坐标。

### 4. C41：逐侧依据 + 逐行注入

**你指出的错**（复现无误）：`_version_basis_ok()` 用 `{v1, v2}` 集合去重，未绑定 p1/p2；
`_scope_basis_ok()` 只要求出现**任一**期间。用真实记录把依据改成「只解释 p1 原版 + 只写一个期间」，
C41 仍零违例。

**改法**：

- 新增 `_basis_clauses(t)`（`verify_v5.py:3457`）：按 `；;。\n` 切成子句。
- `_version_basis_ok(s, sides)`（`:3462`）：改为**逐侧绑定**——每一侧都要找到一个子句，
  该子句同时含该侧标记（`p1`/`p2`）、该侧版本词（`ORIGINAL`/`RESTATED`）、
  且含该侧文档号**或**该侧期间；缺任一侧即 `False`。
- `_scope_basis_ok(s, periods)`（`:3488`）：`any(...)` → `all(p in t for p in periods)`，**两期都须出现**。
- `step4_apply_parents._version_basis`：生成的依据文字在每侧子句末尾追加
  `（DOC-…，期间 …）`，使逐侧绑定在真实数据上**可满足**（否则改严后 64 条会全灭）。
- `_c41_inject`（`:3639`）：新增两类单侧注入 `version_basis_p1_only`、`scope_basis_one_period`；
  拦截数改为**按 `(security_id, field_id, period_key)` 去重后的唯一记录键数**计，
  不再用违例条数（一行可报多条，会虚高）。

**实测**（`review.json.C41.detail.injections`，分母 = 该类注入行数，拦截 = 唯一键数）：

| 注入类 | 注入 | 拦住 |
|---|---:|---:|
| `fake_quote` / `wrong_column` / `wrong_value` / `wrong_page` | 64 | 64 |
| `version_flip` / `short_basis` / `wrong_period` | 64 | 64 |
| `empty_version_basis` / `repeat_version_basis` / `repeat_scope_basis` | 64 | 64 |
| **`version_basis_p1_only`**（新增） | 64 | **64** |
| **`scope_basis_one_period`**（新增） | 64 | **64** |
| `swap_column` | 32 | 32 |

`swap_column` 分母 32 是你上轮认可的口径；本轮**先修好 `cols_equivalent` 再重算该子集**，
结果仍为 32（修复前后这个子集的成员没有变化，因为那 32 行两侧列名等价是**字符串层面**的
`本报告期（1－6月）` vs `本报告期`，与相对年/区间判据无关）。

**登记表实际变化**：64 行 / 27 列，**键集与上一轮完全相同**（双向差集为空）；
逐格比对 64 行 × 27 列，**唯一变化的字段是 `version_basis`，64/64 行**——
即每侧追加了 `（文档号，期间）`。其余 26 列逐字相同。这说明第 4 项改的是**依据的形态**，
不是**登记的结论**。

### 5. 表格边界：先限定同一表格区域

**你指出的错**（复现无误）：上方一张有期间表头的表 + 下方另一张无表头表，
两条路径都把旧表头套到下方金额，均返回 `OK`。

**改法**：

- `_TITLE_ROW`（`parent_verify.py:665`）由「股份有限公司/年度报告/单位：」扩到**报表标题**：
  `合并资产负债表`、`合并利润表`、`合并现金流量表`、`合并所有者权益变动表`、
  `母公司…`、`财务报表附注`。
- `column_of_amount_aligned_ex`（`:792`）：向上找表头时遇到标题行**立即停**（原为 `continue`，
  这是「跨表借表头」的根因）；表头必须落在「本表标题 → 金额行」之间；
  扫不过去记 `TABLE_BOUNDARY_UNPROVEN`，`gap()` 映射 `PARENT_TABLE_BOUNDARY_UNPROVEN`。
- `step4_column_witness._header_rows`（`:124`）：同一条边界规则，返回 `(rows, blocked)`；
  `witness()` 遇 `blocked` 返回 `TABLE_BOUNDARY_UNPROVEN`（`:188`）。
  另在列范围内对表头片段做**两两 `_compatible`** 检查，冲突即 `AMBIGUOUS`
  ——这正是处理你要求的「重叠与多个期间候选」。

**实测**：

```
D4 不得跨表借表头  PASS  st=TABLE_BOUNDARY_UNPROVEN  col=None
C37 table_boundary_rejected_by_gap = True
```

**代价（如实报，也是本轮唯一的覆盖率损失）**：23 条 `BLOCKED` 里，
有 **12 个侧实例**的 note 含 `TABLE_BOUNDARY_UNPROVEN`（p1 6 个、p2 6 个）。
它们**全部同时**已有 `NO_LABEL_ROW` 或 `NO_AMOUNT`，即边界收紧没有单独把任何一条
原本可判的记录打成待核。**但覆盖率上限仍未量化**：真实页面里若表头与数据之间夹了
`单位：元` 或 `续` 字样，会退化为待核。这是方向安全的漏取，不是误收。

### 6. `targets()`：固定重验基线

**你指出的错**（复现无误）：`targets()` 读的是**已缩到 64 行的当前登记表**，
用当前文件重算只得 **86** 条，漏 `SH:600143 FIN.OCF.SQ@20260630`。

**改法**：

- 新增 `step4_parent_targets.csv`（**新文件**）：**87 键固定 assignment**，
  含 `frozen_at` 与 `frozen_note`，一次性冻结，不再从登记表反推。
- `step4_parent_scan.py:155 load_target_baseline()` 读该文件；
  `targets()`（`:172`）的 keep 集合改为「**不可变基线 ∪ 当前登记键**」；
  基线里在 `meta_diff` 中找不到的键记入 `MISSING_FROM_SCOPE` 并在 `main()` 打印
  `BASELINE_KEYS_NOT_IN_SCOPE`——**不静默消失**。

**实测**：`targets 87`、`MISSING_FROM_SCOPE` 为空（未打印），
且基线 87 键 ⊇ 旧 70 键（`baseline_covers_prev70 = true`）。

**文档残留**：`REPORT.md:183` 与 `report_to_codex_round19.md` 的「六类注入各 70 条全部拦住」
已**就地**加标注「原汇报错误，实际各 1 条」，不是删除了事。本轮 `review.json` 直接记
`_rows_*` 分母，报告不另写一份数字。

---

## 二、结果：键集与名单零变化

| 项 | 上一轮 | 本轮 |
|---|---|---|
| 目标（固定基线） | 87 | **87**（读 `step4_parent_targets.csv`） |
| `EVIDENCE_OK` | 64 | **64** |
| `BLOCKED` | 23 | **23** |
| 登记 `parent_verifications.csv` | 64 行 / 27 列 | **64 行 / 27 列**（键集双向差集为空） |
| 独立旁证 | 64/64 `WITNESS_OK` | **64/64 `WITNESS_OK`**，p1/p2 均 `OK:AGREE`，不一致 **0** |
| `skipped` | — | `{not_evidence_ok: 23, version_inconsistent: 0, witness_fail: 0}` |

两侧状态：`p1 OK 73 / NOT_FOUND 14`、`p2 OK 70 / NOT_FOUND 17`（上轮 p2 为 71/16）。

**逐键比对上一轮扫描表**（`git show HEAD:…/step4_parent_scan.csv` vs 本轮）：

```
prev 87  now 87
only prev []          only now []
verdict changed 0
side status changed 1
  SH:688800 FIN.OCF.SQ@20251231  ('NOT_FOUND','OK') -> ('NOT_FOUND','NOT_FOUND')
```

**这就是全部变化。** 该行本就因 p1 `COLUMN_NOT_CONTIGUOUS(2025年度)` 而 `BLOCKED`，
p2 转 `AMBIGUOUS` 不改变 verdict，因此 64 / 23 / 计数 / L2 全部不动。

---

## 三、计数（与上一轮逐位相同）

| 指标 | 值 |
|---|---:|
| 元数据差异未闭合（`meta_diff` open） | **8,611** |
| 合计核心未闭合（`summary.open_total_core` = 元数据 + 键 405 + 值 34） | **9,050** |
| 含补充列（`summary.open_total_all` = 核心 + 1,505） | **10,555** |
| `PENDING_PARENT_COMPATIBILITY` | **1,214** |
| `RESOLVED_SCOPE_COVERED` | **8,762** |
| L2 五档 | **43 / 231 / 321 / 81 / 378** |

`8611 + 405 + 34 = 9050`，`9050 + 1505 = 10555`，与上轮一致。
`43/231/378` **未冻结**（裁决要求）。

---

## 四、本轮自查发现并修掉的缺陷（不是裁决点，但会造假）

1. **`_RE_SPAN_QUARTER` 行尾换行被误删**：插入 `_RE_SPAN_YEAR` 时把两条 assignment 接到同一行，
   `syntax error`。已拆回两条独立赋值。
2. **`_compatible` 首版只比区间**：`2025年度` 与 `2026年度` 都是 `1-12` 月，仍会判兼容。
   加 `_RE_SPAN_YEAR` 后才真正区分。
3. **自测夹具自身命中 `_TITLE_ROW`**：`D4 列链冲突期间报歧义` 首版返回
   `TABLE_BOUNDARY_UNPROVEN` 而非 `AMBIGUOUS`——夹具里 `单位：元` 把上方表头挡住了。
   改夹具为四列表头后通过。**这条值得你知道**：边界规则生效后，
   任何在表头与数据之间夹「单位：元」的真实页面都会退化为待核。
4. **`_version_basis` 未带文档号/期间**：第 4 项改严后 64 条会全灭（依据里只有 `p1`/`p2`
   标记，没有可绑定的文档或期间）。补写后 64/64 通过。这是**判据与数据形态必须同时改**的例子。
5. **注入计数按违例条数**：一行可报多条，虚高。改为按唯一 `(sec, fld, pk)` 计。

---

## 五、边界（本轮不动）

- **批次 C、D、E 与第 5 步未开始**（等本轮裁决）。
- **S04 第二轮、S05 不放行**；**43 / 231 / 378 未冻结**。
- **F32 未修**：26 份英文版年报仍在池内，采集器不校验语言。
- **`_RE_POLICY` 仍是裸「会计政策」**：正文「公司会计政策」也会被认成 `POLICY_CHANGE`。
- **`step4_column_witness.py` 仍与生产共享「表头行 / 指标带」的部分假设**：
  列聚类路径不同（右边界聚类 vs 词坐标三段还原），但表头行选取与语义比较是同一套思路，
  **不能称为完全独立**。你上轮的判断我接受，不辩解。
- **`NO_LABEL_ROW` 的带窗是经验值**（上下各 ≤2 行、行距 ≤40pt）：跨页断行会漏取，方向安全。
- **表格边界收紧的覆盖率上限未量化**：夹 `单位：元` / `续` 的页面会退化为待核。

---

## 六、请你明确表态

1. 第 1 项：`_compatible` 的判据是「任一分量两侧都写了且不同即冲突」，**互补即合并**。
   残留风险我点明：紧排表（列间距 3–5pt）里若真有**两列**分别写 `本报告期` 与 `（4-6月）`，
   它们互补、会被并成一列（canon `本期|R0-4-6|累计`），从版面无法与「同一列被拆成两段」区分。
   我认为这类版面在真实财报里不存在（两列必有各自的期间词或年份），但这是**推断不是证据**。
   要不要加一条「合并后的单元格宽度不得超过金额跨度 + N pt」的几何上界作为第二道闸？
   请你指定阈值或直接否掉。
2. 第 2 项：`_compatible` / `cols_equivalent` 现在把「一侧有值、另一侧为空」当作**不约束**。
   我实测了 64 条登记：**43 条**至少有一个分量属于这种「空 vs 非空」情形，典型是
   `本报告期（1－6月）`（区间 `R0-1-6`）对 `本报告期`（区间空），
   或 `2026年半年度`（相对年空）对 `本报告期`（相对年 `本期`）。
   当前判据下它们全部判等价。**这个「空 = 不约束」是否可接受？**
   若要改成「空也必须匹配」，这 43 条会全部灭——我不认为这是对的（两侧是不同文档的
   不同列名习惯，强求逐字相等等于禁止简称），但这是我的判断，请你定。
   需要提醒的风险：若实际表头只写 `本报告期`、而登记写 `本报告期（4-6月）`，
   当前判据也判等价（空侧不约束），这类「实际侧更短」的情形只能靠
   `registrable_column` 的「候选须在正文连续出现」兜住，兜不住就会放松。
3. 第 3 项：`AMOUNT_PRECISION_INVALID` 现在是**直接拒绝**（不取列），不是「取到再标待核」。
   你的口径是「拒绝或待核」，我选了拒绝（更严）。是否认可？
4. 第 4 项：`version_basis` 每侧追加 `（文档号，期间）` 是我为了让逐侧绑定可满足而改的
   **依据文字格式**。这算不算「为了过检而改证据」？我的理由是：文档号与期间本来就是
   该行已登记的字段，追加只是把隐含信息显式化。请你判定。
5. 第 5 项：`TABLE_BOUNDARY_UNPROVEN` 目前对 12 个侧实例生效，**全部是原本就 `BLOCKED` 的行**。
   这个「零新增待核」是巧合还是判据真的没过度收紧？请抽查。
6. 第 6 项：`step4_parent_targets.csv` 一次性冻结 87 键。若将来批次 C 需要新增目标键，
   我打算**追加**而不改旧行（append-only）。这个约定是否可接受？
7. **批次 C 是否放行？** 若不通过，请把要改的点写成可执行清单（文件 + 函数 + 判据方向）。
