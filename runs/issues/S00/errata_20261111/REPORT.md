# S00 勘误台账（errata_20261111）

**性质：SELF_CHECK，不是独立验收。**
**范围：只读比对，未修改任何数据文件，未回读原始 PDF。**

## 一、任务来源

2026-11-11 发现 S00 存在两份并存的标准化文件，且「S00 验收针对 A、S02-S04 实际消费 B」，中间无一致性检查。Codex 顾问裁决（`runs/issues/S04/codex_ruling_s00_split.md`）要求：

> 保留 B 作为当前计算链唯一输入，但补做一次有明确范围的 S00 勘误验收；保留现有计算成果，暂停把受争议输入支持的结论作为已验收结论放行。

本目录即该勘误的第一步：把 A 与 B 的全部差异逐条列出，给出依据来源与处置结论。

## 二、版本谱系（比原先认知更复杂）

```
A  runs/issues/S00/financial_normalized.csv          228,155 行  2026-10-29  S00 验收对象
   ↓ remediation_20261029（Q3 补采 + 1,007 份重述原文核验回填）
v7 runs/issues/S02/remediation_20261029/collect_q3_2026/s00_v7.csv   229,393 行
   ↓ m07_repair_20261030（扣非补行；v8 被 v9 取代）
v9 runs/issues/S02/m07_repair_20261030/s00_v9.csv.gz  229,666 行
   ↓ hangcha_restated_20261101（杭叉重述比较值采用）
B  runs/issues/S02/hangcha_restated_20261101/s00_v10/s00_v10.csv.gz  229,667 行
```

B 的 `built_from` 指向 v9，不是直接改自 A。因此差异必须分步归因，不能笼统说「B 改了 A」。

替代关系登记见 `runs/issues/S00/supersession.json`。

## 三、差异总览

| 类别 | 总数 | 有依据 | 未解决 |
|---|---:|---:|---:|
| 值差异 | 240 格 | 212 | **28** |
| 键差异（增删行） | 2,056 | 1,682 | **374** |
| 元数据差异 | 17,728 行 | 12,430 | **5,298** |
| 合计 | 20,024 | 14,324 | **5,700** |

值差异分步：A→v7 217 格、v9→v10 21 格、跨步 2 格。其中 **89 格正负号翻转**。
值差异性质（按绝对值倍数）：量级差异 154、中间倍数 33、小幅差异 53。
元数据构成：重述标记 17,009、状态 555、document_id 83、合并范围 33、PIT 状态 48。

涉及公司 419 家（39.8%），其中 175 家落在 S04 的 445 家通过名单内。

## 四、逐类处置

### 4.1 值差异 240 格

| 处置 | 格数 | 依据 |
|---|---:|---|
| `RESOLVED_NORMALIZED_DELTA` | 191 | `normalized_delta.csv` 的 UPDATE 记录，带 document_id 与页码 |
| `RESOLVED_RESTATED_ADOPTION` | 21 | 杭叉集团（SH:603298）`s00_v10_adoption_audit.csv`，逐格带前后文档与页码 |
| `UNRESOLVED_NO_EVIDENCE` | 28 | 无对应记录 |

28 格未解决里，26 格是 A→v7 的值变更但 `normalized_delta.csv` 无 UPDATE 记录，2 格（中京电子 SZ:002579 扣非 20260930）是跨步键变更导致无法归因。派生值若父输入有记录变更，已按 `RESOLVED_DERIVED_FROM_PARENT` 归因，不重复计入未解决。

### 4.2 键差异 2,056

| 处置 | 数量 | 依据 |
|---|---:|---|
| `RESOLVED_NORMALIZED_DELTA` | 1,412 | ADD/REMOVE 记录，带文档与页码 |
| `RESOLVED_M07_NPDEDT_OVERRIDE` | 228 | `npdedt_override_rows.json` 扣非补行 |
| `RESOLVED_M07_REPAIR` | 41 | `s00_v9_patch_summary.detail_added` 逐键记录 |
| `RESOLVED_RESTATED_ADOPTION` | 1 | v10 manifest `row_additions` |
| `UNRESOLVED_NO_EVIDENCE` | 374 | A→v7 增删无记录 |

方向分布：仅 B 有 1,784（补行）、仅 A 有 272（B 删除）。**补行不构成「两版冲突」**（A 本无该行），删除才需要解释；下游判定已按此区分。

### 4.3 元数据 17,728

**重述标记 17,009 行**是本项最大的一块，但**不是无依据的批量重置**：

- 依据 `remediation_20261029/restatement_verify/results.csv`：1,007 份文档逐份原文核验，`否` 1,004、`是` 3，每行带 document_id、页码、方法、原文摘录。
- `apply_summary.json` 记录：`NEEDS_REVIEW->否` 17,266 行、`NEEDS_REVIEW->是` 9 行、`only_restatement_flag_changed=true`、`not_applied: 待核/未找到判据 保持 NEEDS_REVIEW，不猜`。
- 覆盖情况：**11,461 行强依据**（NOTE_TRACE_NA / IMPORTANT_MATTER_NA / NOTE_RETAINED_ERRATA_ZERO 等实证方法）、**475 行弱依据**（`ASSUMED_NO_PENDING_REVIEW`，假设而非实证）、**5,073 行未覆盖**（不在 1,007 份核验范围内）。
- 另有 14 行 `NOT_FOUND -> 是` 与 3 行空值变更未覆盖。

状态差异 555 行中，494 行可追到 `normalized_delta` 的 `changed_columns`，225 行未解决；document_id 83、合并范围 33、PIT 48 行同法处置。

## 五、下游影响（关键结论）

两个口径必须分开看，否则会误读：

**口径一：该公司有无未解决差异** —— 见 `downstream_impact.csv`
419 家有差异，其中 131 家在 445 家名单内、165 家在观察区、123 家差异全部有依据。

**口径二：未解决差异是否真的触及该公司 L2 通过所依赖的字段** —— 见 `l2_dependency_check.csv`

按 L2 依赖链逐家判定（信号 → 指标 → S00 字段 → 当期与上年同期），结果：

| 判定 | 家数 |
|---|---:|
| `NOT_AFFECTED` | 443 |
| `HOLD_PENDING_ERRATA` | **2** |

**只有 2 家的 L2 通过建立在无依据的差异上：**

| 公司 | 争议维度 | 争议内容 |
|---|---|---|
| 禾川科技 SH:688320 | GROWTH / MARGIN / PROFIT | A 的 `EXTRACTED_XCHECK_MISMATCH`（三表勾稽不符）、`DERIVED_HOLD_UPSTREAM` 在 B 中被解除为正常态，无依据 |
| 联赢激光 SH:688518 | GROWTH / PROFIT | 同上；另有经营现金流符号翻转：A `+1.20 亿` vs B `-4,363 万` |

其余 129 家有未解决差异的名单内公司，其差异落在非依赖期间或非依赖字段（如 2025 年报、资产负债表科目），不改变当期 L2 结论。

**注意**：这不等于「443 家已验收」。它只说明「即使把争议数据全部剔除，这些公司的 L2 结论不变」。源值正确性仍未验收。

## 六、未解决项（5,700 条）

| 类别 | 数量 | 性质 |
|---|---:|---|
| 值差异 | 28 | A→v7 值变更无 UPDATE 记录 |
| 键差异 | 374 | A→v7 增删无记录 |
| 重述标记 | 5,073 | 不在 1,007 份核验范围 |
| 其他元数据 | 225 | status / document_id / 合并范围 / PIT 无记录 |

按 Codex 要求，这些一律标 `UNRESOLVED_NO_EVIDENCE`，**未按「B 更合理」选边**。

## 七、本次未做

- 未回读任何 PDF，未新增业务判断；未修改 A、v7、v9、B 任一文件。
- 未处理「最新可用期选择」等间接依赖（`anchor_period` 由 B 决定，若 B 补行导致锚定期变化，本判定无法捕捉）。
- 未对 5,700 条未解决项做原文核验——这需要独立补充验收。
- 未改动 S01 规则、S04 名单与任何验收记录状态。

## 八、下一步（按 Codex 裁决顺序）

1. 对 5,700 条未解决项做限定范围的原文核验（执行方），标 `SELF_CHECK`。
2. 独立补充验收（重点：2 家 HOLD、475 行弱依据、5,073 行未覆盖重述）。
3. 修正规则 v3 `universe.source` 的残留指向 A（须留元数据勘误记录）。
4. 落实「三个哈希相等」消费闸门。
5. 完成 S04 第二轮外部复核；S05 仍不放行。
