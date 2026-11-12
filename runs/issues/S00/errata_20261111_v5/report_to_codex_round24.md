# S00 勘误 V5：归属检查覆盖首片段、既有组与最终候选（第二十四轮汇报）

- 目录：`runs/issues/S00/errata_20261111_v5/`
- 自检版本：**V21**，**43/43 PASS** → `SELF_CHECK_PASS_WITH_UNRESOLVED_ITEMS`
- 性质：**SELF_CHECK**（同一执行 AI 自验，登记表 `review_role=SELF_CHECK`）
- 上一轮裁决：`RETURN_FOR_REWORK`（3 条返工项，暂不放行批次 C）→ `_codex_out_round23.txt`
- 本轮逐条对照（机器可读）：`rework_round23_result.json`
- **比较基线**（写 SHA，不用 `HEAD`）：本轮"逐键比对"的上轮对象是提交 **`87eecdd`**（第二十三轮）；
  更早分别是 `130eef1`（22 轮）、`b4738b2`（21 轮）、`4ac102d`（20 轮）。
- 复现顺序：`step4_parent_scan.py` → `step4_column_witness.py` → `step4_apply_parents.py` →
  `build_errata_v5.py` → `check_l2_v5.py` → `sampling_v5.py` → `replay_polarity_v5.py` → `verify_v5.py`

结论先说：**87 条键集、64 条登记、23 条待核、全部计数、L2 五档，与 `87eecdd` 逐位相同**。
你三条指出的都是**同一个模式**：归属检查的**调用点漏了**。本轮把四个调用点补齐，
并把这一点作为结构性风险写进 `open_findings`（见 §四）。

---

## 一、三项逐条落实

### 1. 行内合并的首片段漏检

**你构造的反例**（我逐字复现，上一版生产与旁证都返回 `OK` + `（4-6月）本报告期`）：

```text
y=50：单位：元
y=70：（4-6月）x[65,96]；本报告期 x[100,138]
y=90：营业收入 x[0,45]；200.00 x[60,90]；100.00 x[100,130]
```

**根因**（与你判断一致）：`_header_cells` 只在「要并第二段」时才调 `_attribution`；
首片段走的是 `cur = [x0, x1, tx]` 分支，`attr` 变量此时还是初值 `"OK"`，
于是 `cur_attr = "OK"`——**越界的首片段从未被判过**。之后那段合法的 `本报告期`
通过检查，就被并进同一个格子。

**改法**（`parent_verify.py:744`）：每个片段（**含首片段**）建格时先单独判一次
`base = _attribution(x0, x1, bounds, None, False)`，合并要求 `attr`、`base`、
`cur_attr` 三者一致：

```python
base = _attribution(x0, x1, bounds, None, False) if bounds else "OK"
...
elif attr != base or cur_attr != base:
    joinable = False          # 一在列内、一在列外（含首片段在列外）
```

**实测**：`OK` + `本报告期`（左边界 95，`（4-6月）` 中心 80.5 判 `OTHER`）。
自测 `D7 首片段越界不得被后一段带进本列`；C37 `first_fragment_out_of_bounds = True`。
旁证同改（`step4_column_witness.py:103`），`D7 旁证首片段越界不得并` →
`merged=[(65,96,['（4-6月）'],'OTHER'), (100,138,['本报告期'],'OK')]`。

### 2. 边界未知时对既有组漏检

**你构造的反例**（上一版返回 `OK` + `本报告期（4-6月）`）：

```text
y=60：项目 x[0,40]；本报告期  x[132,165]
y=70：项目 x[0,40]；（4-6月） x[100,130]
y=90：营业收入 x[0,45]；100.00 x[100,130]
```

**根因**：`_chain_cells` 建组时用 `need_core=False` 判归属 → 首片段记为 `OK`；
合并时**只重判新片段**，旧组没有重新验证。于是「首片段完全不与金额跨度相交」
这件事从来没被 `need_core` 那一条判过。

**改法**（`parent_verify.py:811`）：两段期间语义合并（`need_core=True`）时，
对**双方原始片段**逐段重新应用 `need_core=True`；任一段 `UNPROVEN` 即不并、记 `drops`：

```python
if need_core:
    bad = None
    for py, px0, px1, ptx in g["parts"] + [(y, x0, x1, tx)]:
        if _attribution(px0, px1, bounds, core, True) == "UNPROVEN":
            bad = (py, px0, px1, ptx); break
    if bad is not None:
        drops.append(("UNPROVEN", bad[0], bad[1], bad[2], bad[3])); continue
```

为此 `g["parts"]` 由 `(y, x0, tx)` 改为 `(y, x0, x1, tx)`（**保留片段右边界**，
否则无法对片段重判）。

**状态顺序也改了**：`COLUMN_ATTRIBUTION_UNPROVEN` 现在**先于**「多候选 `AMBIGUOUS`」判
（`parent_verify.py:1061`）。理由：被挡下的那段期间片段往往自己也在候选带内，
两个状态都成立时报**原因**比报歧义更能定位；两者都不放行。

**实测**：`COLUMN_ATTRIBUTION_UNPROVEN`。自测 `D7 既有组首片段也要按 need_core 重判`；
C37 `existing_group_need_core = True`。
**左右倒序也补了**：无左邻数字、首片段 `[65,98]`（与下方 `[100,130]` 跨行重叠 2pt，
真的会触发合并判定）→ 同样 `COLUMN_ATTRIBUTION_UNPROVEN`（自测 `D7 左右倒序同样不得拼`）。

### 3. 最终候选筛选仍未应用列归属约束

**你构造的反例**（上一版返回 `OK` + `2026年半年度`）：

```text
y=70：项目 x[0,40]；2026年半年度 x[65,110]
y=90：营业收入 x[0,45]；200.00 x[60,90]；100.00 x[100,130]
```

**根因**：`hit` 仍只判「整体跨度重叠」（`c[1] > lo and c[0] < hi`），链的归属没有带出来。
所以我上一轮汇报里写的「最终候选也使用同一套 `bounds + core`」**不成立**——你说得对。

**改法**：`_chain_cells` 改为返回**四元组** `(x0, x1, text, attr)`，最终筛选加一条：

```python
hit = [c for c in chains
       if c[1] > lo and c[0] < hi and (len(c) < 4 or c[3] == "OK")]
```

（`len(c) < 4` 只为兼容旧的三元组调用，生产路径上恒为四元组。）
旁证同步：`_merge_header_cells` 返回四元组，`witness` 选列时 `cell[3] != "OK"` 即跳过
（`step4_column_witness.py:299`）。

**实测**：`NO_COLUMN`。自测 `D7 最终候选须过滤越界链`；
C37 `final_candidate_filters_other = True`。

---

## 二、结果：键集与逐格零变化

| 产物 | `130eef1`（22 轮） | `87eecdd`（23 轮） | 本轮 | 逐格差异 |
|---|---|---|---|---|
| `step4_parent_scan.csv` | 87 行 | 87 | **87** | **0** |
| `step4_column_witness.csv` | 64 行 | 64 | **64** | **0** |
| `parent_verifications.csv` | 64×27 | 64×27 | **64×27** | **0**（仅 `reviewed_at` 64 格日期） |

- 扫描：`EVIDENCE_OK 64 / BLOCKED 23`；p1 `OK 73 / NOT_FOUND 14`；p2 `OK 70 / NOT_FOUND 17`。
- 旁证：`WITNESS_OK 64`，p1 / p2 全 `OK:AGREE`。
- 登记：`registered 64 of 87`，`skipped {not_evidence_ok: 23, 其余 0}`。
- 计数：`8611 / 9050 / 10555 / 1214 / 8762`；L2 `43 / 231 / 321 / 81 / 378`。
- `selftest_column_rules.py`：**67 项，FAIL 0**（上一轮 61 项 + 新增 D7 六项）。
- `verify_v5.py`：**43/43 PASS**；`C37 violations []`；六个归属探针全 `True`。

`COLUMN_ATTRIBUTION_UNPROVEN` 在 87 条真实键上**仍触发 0 次**。三条新反例也全部是构造的，
真实版面里没有出现。我按你的要求不预设维持 64 条——实际结果就是 64 条，但不是被保住的。

---

## 三、本轮自己修掉的两处（不是裁决点，但会造假）

1. **`drops` 元组少一个元素**：既有组重判分支我最初写 `("UNPROVEN",) + bad[1:]`，
   只 4 个元素，`column_of_amount_aligned_ex` 取 `d[4]` 时 `IndexError`。
   已改为显式五元组。这类错误自测能抓住，但如果只跑真实数据会**静默跳过**（因为该分支
   在 87 条上从不触发）。
2. **自测用例的边界方向写反**：`D7 旁证首片段越界` 首版把 95 写成**右**边界 `(-inf, 95)`，
   于是 `（4-6月）` 中心 80.5 落在边界内、判 `OK`，用例「通过」了但测的是错的东西。
   你原话是「左边界 **95**」，已改为 `(95, +inf)`。

---

## 四、结构性风险（我认为这是本轮最该说的一条）

三轮裁决命中的是**同一个模式**：

| 轮次 | 漏掉的调用点 |
|---|---|
| 22 轮 | 跨行合并整层没判归属 |
| 23 轮 | 首片段（行内）、既有组（跨行）、最终候选筛选 |
| 24 轮（本轮） | 上面三处都补了，但**仍是四个分散调用点** |

归属现在是**判据**，不是**数据结构属性**。只要还有第五个消费 `chains` 的地方没调
`_attribution`，同类缺陷会第三次出现。彻底修法是把归属做成候选的属性
（`_chain_cells` 已返回四元组），在**唯一出口**统一过滤，而不是继续在每个调用点补一行。
本轮只做到「现有四个调用点都覆盖」，**未做结构收敛**——已写进 `open_findings` 第 14 条。
如果你认为这一步必须现在做，我按此改。

---

## 五、边界（本轮不动）

- **批次 C、D、E 与第 5 步未开始**（等你本轮裁决）。
- **S04 第二轮、S05 不放行**；**43 / 231 / 378 未冻结**。
- **F32 未修**：26 份英文版年报仍在池内。
- **`_RE_POLICY` 仍是裸「会计政策」**。
- **旁证与生产共用 `_amount_bounds` / `_attribution`**（现在两处都调，独立性进一步下降）。
- **`NO_LABEL_ROW` 带窗仍是经验值**；**表格边界收紧的覆盖率上限未量化**。

---

## 六、请你明确表态

1. 归属检查目前是**四个分散调用点**（行内合并、跨行新片段、跨行既有组、最终候选）。
   你是否要求现在就做**结构收敛**（归属作为候选属性 + 唯一出口过滤），
   还是接受「现有四点全覆盖 + 持续披露」？
2. 我把 `COLUMN_ATTRIBUTION_UNPROVEN` 提到 `AMBIGUOUS` **之前**判——两者都不放行，
   但前者能定位到具体片段。这个顺序可以吗？
3. 你对「金额跨度相交可作当前保守过滤条件、不能单独证明同列」的定性我接受，
   所以我不再声称残余风险只有过严。**但我也无法量化过松的部分**——
   在 87 条真实键上它一次都没触发，等于没有可观测证据。这一点你是否接受作为
   `ACCEPTED_WITH_LIMITS` 的边界，还是要求我另找真实版面构造？
4. **下一步**：批次 C（分季度表来源 + 半年报权益变动表「前期差错更正 0.00」行）是否放行？
