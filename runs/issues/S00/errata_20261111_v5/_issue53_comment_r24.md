## 第二十四轮：归属检查覆盖首片段 / 既有组 / 最终候选（V21，待 Codex 第 24 轮复核）

上一轮 Codex 裁决 `RETURN_FOR_REWORK`（3 条返工项，暂不放行批次 C）→ `_codex_out_round23.txt`。
**仍然只改判定方法。结论：87 条目标、64 条登记、23 条待核、全部计数、L2 五档与 `87eecdd` 逐格零变化。**

你三条指出的都是**同一个模式**：归属检查的某个调用点漏了。本轮补齐四个调用点：

| 裁决项 | 落地 |
|---|---|
| 1 行内合并首片段漏检 | `_header_cells` 每个片段（**含首片段**）建格即算 `base=_attribution(...,None,False)`；合并要求 `attr`/`base`/`cur_attr` 三者一致。反例：`（4-6月）` 中心 80.5 < 左边界 95，上一版拼成 `（4-6月）本报告期`，本轮 `OK` + `本报告期` |
| 2 既有组漏检 | `_chain_cells` 在 `need_core` 时对 `g["parts"] + 新片段` **逐段重判**；`g["parts"]` 由 `(y,x0,tx)` 改 `(y,x0,x1,tx)`（保留片段右边界）；`COLUMN_ATTRIBUTION_UNPROVEN` 提到 `AMBIGUOUS` **之前**判。反例：上一版 `OK` + `本报告期（4-6月）`，本轮 `COLUMN_ATTRIBUTION_UNPROVEN`；**左右倒序也补了** |
| 3 最终候选未过滤 | `_chain_cells` 返回**四元组** `(x0,x1,text,attr)`；`hit` 过滤加 `c[3]=="OK"`；旁证选列 `cell[3]!="OK"` 即跳过。反例：表头中心 87.5 < 左边界 95，上一版 `OK` + `2026年半年度`，本轮 `NO_COLUMN` |

**结果**

- `step4_parent_scan.csv`（87 行）、`step4_column_witness.csv`（64 行）、`parent_verifications.csv`（64×27）
  与 `87eecdd` **逐格差异 0**（唯一差异：`reviewed_at` 64 格日期）。
- 计数 `8611 / 9050 / 10555 / 1214 / 8762`、L2 `43/231/321/81/378` 全部不变。
- 自检 **V21，43/43 PASS**；`selftest_column_rules.py` **67 项 `FAIL 0`**（新增 D7 六项）；
  C37 六个归属探针全 `True`、`violations []`；C41 十二类 64/64 + `swap_column` 32/32。
- `COLUMN_ATTRIBUTION_UNPROVEN` 在 87 条真实键上**仍触发 0 次**；三条新反例全是构造的。

**结构性风险（我认为最该说的一条）**：三轮裁决命中同一模式——归属检查的某个调用点漏了
（22 轮跨行整层、23 轮首片段/既有组/最终候选）。归属目前是**判据**而不是**数据结构属性**；
只要还有第五个消费 `chains` 的地方没调 `_attribution`，同类缺陷会再出现。彻底修法是
候选属性 + **唯一出口**过滤。**本轮未做结构收敛**，已写进 `open_findings` 第 14 条。

**本轮自己修掉的两处（必须记）**

1. `drops` 元组最初少一个元素（`('UNPROVEN',)+bad[1:]`）→ `IndexError`。该分支在 87 条真实键上
   从不触发，**只跑真实数据会静默跳过**。
2. `D7 旁证首片段越界` 首版把 95 写成**右**边界 `(-inf,95)`，片段中心落在边界内判 `OK`，
   用例「通过」但测的是错的东西。裁决原话是「左边界 95」。

**边界**：批次 C–E 与第 5 步未开始；S04 第二轮、S05 不放行；43/231/378 未冻结；
F32 与裸 `_RE_POLICY` 未修；旁证与生产共用 `_amount_bounds` 与 `_attribution`。

材料：`report_to_codex_round24.md`、`rework_round23_result.json`、`_codex_prompt_round24.txt`。
