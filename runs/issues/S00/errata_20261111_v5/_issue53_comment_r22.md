## 第二十二轮：列边界归属 + 同侧语义单向包含（V19，待 Codex 第 22 轮复核）

提交 `130eef1`（已推送 `b4738b2..130eef1 → main`）。上一轮 Codex 裁决 `RETURN_FOR_REWORK`（4 条返工项，暂不放行批次 C）。

**仍然只改判定方法。结论：87 条目标、64 条登记、23 条待核、全部计数、L2 五档与 `b4738b2` 逐格零变化。**

| 裁决项 | 落地 |
|---|---|
| 1 互补语义≠同列 | 新增 `_amount_bounds()`：取「本列金额与**同一行**左右相邻数字的中点」作列边界（无相邻则 ±inf，**无拍定阈值**）；`_header_cells(bounds=)` 合并前比对两段中心是否同侧。上一版把 `本报告期` 与右邻列 `（4-6月）` 并成 `本报告期（4-6月）` |
| 2 同侧不得增加语义 | 新增 `_no_extra_semantics()`：同侧**单向包含**（登记 ⊆ 实际），反向放行；`gap()` → `PARENT_COLUMN_SEMANTICS_UNPROVEN`；`check_c41` → `<SIDE>_COLUMN_SEMANTICS_UNPROVEN`；新增合成引文探针 `_c41_semantics_probe()` |
| 3 旁证合并前检查冲突 | 抽出 `_merge_header_cells()`（合并前过 `_compatible` + 列边界，保留原始片段）+ `_hmerge_conflict()` 按片段复查 |
| 4 修正统计与解释 | 边界侧数改为 **21 侧（p1=9 / p2=12）**、全表 **72 侧**；撤回「零新增 BLOCKED ⇒ 边界规则未过度收紧」；写明基线 SHA `4ac102d` / `b4738b2`；Q2 改同侧对象重算 **0/64**；C37 改为「共同覆盖生产链，非每项各自跑完整链」 |

**结果**

- `step4_parent_scan.csv`（87 行）与 `parent_verifications.csv`（64×27）与 `b4738b2` **逐格差异 0**。
- 计数 `8611 / 9050 / 10555 / 1214 / 8762`、L2 `43/231/321/81/378` 全部不变。
- 自检 **V19，43/43 PASS**；`selftest_column_rules.py` **50 项 `FAIL 0`**；
  C41 十二类 64/64 + `swap_column` 32/32 + 语义探针命中。
- 旁证 **64/64 `WITNESS_OK`**，两侧全 `OK:AGREE`。

**自己造出来又回退的回归（必须记）**：先试「整页数字列格切区」，被脚注编号/页码切碎——
`SH:603273` 的 p2 页 6 个真实列被切成 12 个簇，`2026` 与 `年第一季度` 被判成两列，
`SH:600590 / 603082 / 603273 / 688067` 四条 p2 由 `OK:AGREE` 变 `OK:DISAGREE`。
回退为「只取金额那一行」后恢复。日志 `_run_wit_r22b.log`（失败）/ `_run_wit_r22c.log`（修复后）。

**边界**：批次 C–E 与第 5 步未开始；S04 第二轮、S05 不放行；43/231/378 未冻结；F32 与裸 `_RE_POLICY` 未修。

材料：`report_to_codex_round22.md`、`rework_round21_result.json`、`_codex_prompt_round22.txt`、`_run_*_r22*.log`。
