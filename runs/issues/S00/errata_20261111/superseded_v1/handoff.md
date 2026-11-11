# S00 勘误交接（errata_20261111）

**性质：SELF_CHECK。执行方自检，不构成独立验收。**

## 一、一句话结论

A 与 B 的差异共 20,024 条（值 240 格、键 2,056、元数据 17,728 行），其中 14,324 条有可追溯依据、**5,700 条未解决**；445 家名单中 **443 家的 L2 结论不受未解决差异影响，2 家（禾川科技、联赢激光）须待勘误闭合**。

## 二、纠正了三个此前的错误认知

1. **B 不是从 A 直接改的。** 谱系是 A → v7（remediation）→ v9（M07 扣非补行）→ B（杭叉重述采用）。差异必须分步归因。
2. **17,009 行重述标记不是「无记录的批量重置」。** 依据是 1,007 份文档逐份原文核验（`restatement_verify/results.csv`，每行带 document_id、页码、方法、原文摘录），`apply_summary.json` 明确记录 `not_applied: 待核保持 NEEDS_REVIEW，不猜`。但仍有 5,073 行不在核验范围内。
3. **「131 家在名单内且有未解决差异」不等于「131 家结论有问题」。** 按 L2 依赖链逐家核对后，只有 2 家的未解决差异落在当期/上年同期的依赖字段上。

## 三、未解决项构成（5,700）

| 类别 | 数量 | 原因 |
|---|---:|---|
| 值差异 | 28 | A→v7 值变更，`normalized_delta.csv` 无 UPDATE 记录 |
| 键差异 | 374 | A→v7 增删无记录 |
| 重述标记 | 5,073 | 不在 1,007 份核验范围 |
| 其他元数据 | 225 | status / document_id / 合并范围 / PIT 无记录 |

另单列 475 行为 `RESOLVED_RESTATEMENT_VERIFY_WEAK`（方法为 `ASSUMED_NO_PENDING_REVIEW`，属假设非实证）。

## 四、须优先复核的 2 家

| 公司 | 争议 | 具体格 |
|---|---|---|
| 禾川科技 SH:688320 | A 的 `EXTRACTED_XCHECK_MISMATCH`、`DERIVED_HOLD_UPSTREAM` 在 B 中变为正常，无依据 | REV.YTD、REV.SQ、GROSSMARGIN.PCT @20260630 |
| 联赢激光 SH:688518 | 同上；另有经营现金流符号翻转 A `+1.20 亿` vs B `-4,363 万` | OCF.YTD、OCF.SQ、OCF_TO_NP @20260630 |

这两家的共同性质：**B 解除了 A 的告警状态**。若解除无依据，则其 L2 通过不成立。

## 五、独立复核建议重点

1. 抽验 475 行弱依据（`ASSUMED_NO_PENDING_REVIEW`）是否真的「无待复核事项」。
2. 抽验 5,073 行未覆盖重述：为什么这 5,056 行「待核→否」不在 1,007 份核验清单内——是遗漏，还是本就不该核。
3. 禾川科技、联赢激光的告警解除依据。
4. 28 格值差异中，符号翻转的那几格（如联赢激光 OCF、长安汽车毛利额）原件读数。
5. 规则 v3 `universe.source` 仍指向 A，须以元数据勘误方式修正并留记录。

## 六、本次未做

- 未回读 PDF、未改任何数据文件、未改 S01 规则或 S04 名单。
- 未处理「最新可用期选择」的间接依赖（锚定期由 B 决定，B 补行可能改变锚定）。
- 未对 5,700 条未解决项做原文核验——这是下一步独立补充验收的工作量。

## 七、文件清单

| 文件 | 内容 |
|---|---|
| `cell_diff.csv` | 240 格值差异，含 A/B 值、倍数、符号翻转、依据、处置 |
| `key_diff.csv` | 2,056 键增删，含方向、步骤、依据、处置 |
| `meta_diff.csv` | 17,728 行元数据差异（重述/状态/文档/范围/PIT） |
| `downstream_impact.csv` | 419 家受影响公司的粗粒度清单（有无差异） |
| `l2_dependency_check.csv` | 445 家精确判定（差异是否触及 L2 依赖） |
| `l2_dependency_summary.json` | 2 家 HOLD 的明细 |
| `summary.json` / `manifest.json` / `review.json` | 汇总、哈希、12 项自检 |
| `../supersession.json` | A/B 替代关系登记与消费规则 |

复算：`python runs/issues/S00/errata_20261111/build_errata.py` → `check_l2_dependency.py` → `verify.py`。
