## 第二十一轮：取列判据收紧与表格边界（V18，待 Codex 第 21 轮复核）

提交 `b4738b2`（已推送 `4ac102d..b4738b2 → main`）。上一轮 Codex 裁决 `RETURN_FOR_REWORK`（6 条返工项，不放行批次 C）。

**本轮仍然只改判定方法，不改「哪些键应当闭合」。** 结论：**87 条键集、64 条登记、23 条待核、全部计数、L2 五档，与上一轮逐位相同。**

| 裁决项 | 落地 |
|---|---|
| 1 表头合并的期间冲突 | `_canon_parts` 三维拆分 + `_compatible`（任一分量两侧都写且不同即冲突）；`_header_cells` 并格改用它；`_chain_cells` **合并前**过 `_compatible`，冲突则不并 → 两个候选 → `AMBIGUOUS`（不是链合并后数候选） |
| 2 等价判定保留完整语义 | `cols_equivalent` 删「两侧都有区间就 return」的短路，逐维度比对；`_RE_SPAN_YEAR` 使 `2025年度`/`2026年度` → `R-y-1-12`；C37 补四项完整链反例（含 `rel_year_rejected_by_gap` / `annual_year_rejected_by_gap`） |
| 3 金额与引文边界 | `_same_amount` 直接比 Decimal（`1.0==1.00` 真、`100.004==100.00` 假）；`_has_subcent` → 取列入口即 `AMOUNT_PRECISION_INVALID`；`_num_in_quote` 删「任意数字位切分」，只留 exact 双核对 / 严格 token 全等 |
| 4 逐侧依据 + 逐行注入 | `_basis_clauses` + `_version_basis_ok` 逐侧绑定（该侧标记 + 该侧版本词 + 该侧文档号或期间）；`_scope_basis_ok` 须两期都出现；注入新增 `version_basis_p1_only` / `scope_basis_one_period`，拦截按**唯一记录键数**计 |
| 5 表格边界 | `_TITLE_ROW` 扩到报表标题；向上找表头**遇标题行即停**，扫不过去记 `TABLE_BOUNDARY_UNPROVEN`；旁证同规则 + 表头片段两两 `_compatible` |
| 6 固定重验基线 | 新增 `step4_parent_targets.csv`（87 键 + `frozen_at`）；`targets()` 读「基线 ∪ 当前登记键」，缺键记 `MISSING_FROM_SCOPE` 并打印 |

**结果**

- 目标 87 / `EVIDENCE_OK` 64 / `BLOCKED` 23；登记 **64 行 / 27 列**；旁证 **64/64 `WITNESS_OK`**，两侧 `OK:AGREE`。
- 逐键比对上一轮扫描表：**双向差集为空、verdict 变化 0、侧状态变化恰好 1 条**
  （`SH:688800 FIN.OCF.SQ@20251231` 的 p2 `OK`→`NOT_FOUND`，原因 `AMBIGUOUS`；该行本就 `BLOCKED`）。
- 登记表逐格比对：**唯一变化的字段是 `version_basis`（64/64 行）**，其余 26 列逐字相同。
- 计数 `8611 / 9050 / 10555 / 1214 / 8762` 与 L2 `43/231/321/81/378` **全部不变**。
- 自检 **V18，43/43 PASS**；`selftest_column_rules.py` **38 项 `FAIL 0`**；C41 十三类注入 12×64/64 + `swap_column` 32/32。

**判据收紧的代价（已写进 `review.json:open_findings`）**

1. `_compatible` 的「空 = 不约束」让 **43/64** 行靠「一侧有分量、另一侧空」通过，是一条放松。
2. `TABLE_BOUNDARY_UNPROVEN` 对 **12 个侧实例**生效，全部同时已有 `NO_LABEL_ROW`/`NO_AMOUNT`（零新增待核）；但表头与数据之间夹 `单位：元` / `续` 的真实页面会退化为待核，覆盖率上限未量化。
3. `step4_column_witness.py` 仍与生产**共享「表头行 / 指标带」假设**，不能称完全独立。

**边界**：批次 C–E 与第 5 步未开始；S04 第二轮、S05 不放行；43/231/378 未冻结；F32 与裸 `_RE_POLICY` 未修。

材料：`report_to_codex_round21.md`（逐条汇报）、`rework_round20_result.json`（机器可读对照）、`_codex_prompt_round21.txt`、`_run_*_r21*.log`。
