# A03 交接第 4 节计数更正（附加记录，不覆盖原 handoff）

- **记录方**：A04 返工复验（执行者与自检者为同一主体，`review_nature=SELF_CHECK`）
- **记录时间**：2026-10-27
- **被更正文件**：`runs/issues/A03/handoff.md` 第 4 节
- **原文主张**：`remaining_gaps.csv` 共 **226** 行
- **实际情况**：`runs/issues/A03/remaining_gaps.csv` 共 **1754** 行
- **处理方式**：原 handoff 与 `remaining_gaps.csv` 均**不修改、不覆盖**；本文件作为附加更正记录，A04 复验引用本记录。

## 逐层复算

| gap_layer | gap_type | 行数 |
|---|---|---:|
| DOCUMENT | NOT_APPLICABLE（上市前不适用） | 151 |
| DOCUMENT | NOT_DISCLOSED（公司未披露） | 4 |
| REGISTRY_DUPLICATE | SAME_FILE_TWO_IDS（同件双 ID） | 71 |
| FIELD | RESTATEMENT_NEEDS_REVIEW（重述待复核） | 960 |
| FIELD | FIELD_NOT_EXTRACTED（三表定位失败/未找到） | 568 |
| **合计** | | **1754** |

恒等式：155（文档层终态）+ 71（重复登记）+ 1528（字段项）= 1754。

## 226 是什么

226 = 155 + 71，只是**文档层与重复登记的子计数**，不含字段层 1528 条，不能当作缺口总数使用。

## 复算方法

```bash
python -c "import csv,collections; r=list(csv.DictReader(open('runs/issues/A03/remaining_gaps.csv',encoding='utf-8-sig'))); print(len(r), collections.Counter(x['gap_layer'] for x in r))"
```

## 限制

- 本条只更正计数口径，不重新判定任何缺口是否成立。
- 151 / 4 / 71 / 960 / 568 的分项含义仍以 A03 原始 `remaining_gaps.csv` 与 `review.json` 为准。
- 该更正不改变 A03 的 `SELF_CHECK_PASS` 结论，也不构成独立审计。
