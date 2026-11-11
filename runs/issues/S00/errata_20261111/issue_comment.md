## S00 勘误台账完成（2026-11-11）

**性质：SELF_CHECK，不是独立验收。**

### 起因

发现 S00 存在两份并存的标准化文件，且「S00 验收针对 A、S02-S04 实际消费 B」，中间无一致性检查。Codex 顾问裁决要求：保留 B 作为当前计算链唯一输入，但补做一次有明确范围的 S00 勘误验收。

### 版本谱系

```
A  runs/issues/S00/financial_normalized.csv          228,155 行
   ↓ remediation_20261029
v7 runs/issues/S02/remediation_20261029/.../s00_v7.csv   229,393 行
   ↓ m07_repair_20261030
v9 runs/issues/S02/m07_repair_20261030/s00_v9.csv.gz     229,666 行
   ↓ hangcha_restated_20261101
B  runs/issues/S02/hangcha_restated_20261101/s00_v10/...  229,667 行
```

B 的 `built_from` 是 v9，不是直接改自 A。替代关系登记：`runs/issues/S00/supersession.json`。

### 差异与处置

| 类别 | 总数 | 有依据 | 未解决 |
|---|---:|---:|---:|
| 值差异 | 240 格 | 212 | 28 |
| 键差异 | 2,056 | 1,682 | 374 |
| 元数据 | 17,728 行 | 12,430 | 5,298 |
| 合计 | 20,024 | 14,324 | **5,700** |

未解决项一律标 `UNRESOLVED_NO_EVIDENCE`，未按「B 更合理」选边。

### 一项重要澄清

17,009 行重述标记变化**不是**无记录的批量重置。依据是 `remediation_20261029/restatement_verify/results.csv`：1,007 份文档逐份原文核验（`否` 1,004、`是` 3），每行带 document_id、页码、方法、原文摘录；`apply_summary.json` 记录 `not_applied: 待核/未找到判据 保持 NEEDS_REVIEW，不猜`。

其中 11,461 行为强依据、475 行为弱依据（`ASSUMED_NO_PENDING_REVIEW`，假设非实证）、5,073 行不在核验范围。

### 下游影响

445 家 S04 名单中：

- **443 家** L2 结论不受未解决差异影响（剔除争议数据后仍成立）
- **2 家** 须待勘误闭合：

| 公司 | 争议 |
|---|---|
| 禾川科技 SH:688320 | A 的 `EXTRACTED_XCHECK_MISMATCH`、`DERIVED_HOLD_UPSTREAM` 在 B 中变为正常，无依据 |
| 联赢激光 SH:688518 | 同上；另有经营现金流符号翻转 A `+1.20 亿` vs B `-4,363 万` |

### 须独立复核的重点

1. 475 行弱依据是否真的「无待复核事项」
2. 5,073 行未覆盖重述为何不在 1,007 份清单内
3. 禾川科技、联赢激光的告警解除依据
4. 符号翻转格的原文读数
5. 规则 v3 `universe.source` 仍指向 A，须以元数据勘误修正

### 交付

`runs/issues/S00/errata_20261111/`：`cell_diff.csv`（240）、`key_diff.csv`（2,056）、`meta_diff.csv`（17,728）、`l2_dependency_check.csv`（445 家判定）、`REPORT.md`、`handoff.md`、`review.json`（12/12 PASS）、`manifest.json`。

复算：`build_errata.py` → `check_l2_dependency.py` → `verify.py`，两次运行输出哈希一致。

未回读 PDF、未修改任何数据文件。S05 仍不放行。
