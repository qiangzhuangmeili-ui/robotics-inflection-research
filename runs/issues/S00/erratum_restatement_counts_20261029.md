# S00 勘误：重述标记计数口径（2026-10-29）

## 结论

`runs/issues/S00/review.json` 与 `issue_comment_rework.md` 里的 normalized 重述标记计数
（是 1,155 / 否 9,490 / 待核 6,373 / 不适用 903 / 未找到 15）**无法复现，应作废**。

行级（按财务格 / 行）计数才是唯一可复算口径，且合计等于全表行数：

| restatement_flag | 行数 |
|---|---|
| 是 | 18,660 |
| 否 | 102,512 |
| RESTATEMENT_INDICATED_NEEDS_REVIEW | 37,714 |
| NOT_APPLICABLE | 9,974 |
| NOT_FOUND | 33,543 |
| 空 | 25,752 |
| **合计** | **228,155** |

该组行级数字与 Codex 独立复验（`codex_rework_acceptance_20261029.md`）完全一致。

## 复现与排查

```bash
python - <<'PY'
import csv, collections
c = collections.Counter()
for r in csv.DictReader(open('runs/issues/S00/financial_normalized.csv', encoding='utf-8-sig', newline='')):
    c[r['restatement_flag'] or '空'] += 1
print(dict(c), sum(c.values()))
PY
```

已尝试的替代聚合，均**不能**得到 1,155 / 9,490 / 6,373：

| 聚合维度 | 是 | 否 | 待核 | 不适用 | 未找到 | 空 | 合计 |
|---|---|---|---|---|---|---|---|
| 行级（财务格） | 18,660 | 102,512 | 37,714 | 9,974 | 33,543 | 25,752 | 228,155 |
| 公司-期间级 | 1,086 | 5,687 | 2,155 | 577 | 1,933 | 10,313 | 21,751 |
| 公司-槽位-标记 | 1,183 | 5,811 | 2,272 | 580 | 2,640 | 8,449 | 20,935 |
| 公司-期间类型-标记 | 1,600 | 4,080 | 1,684 | 408 | 1,223 | 5,789 | 14,784 |

结论：原数字既不是行级也不是上述任一口径，来源未留痕，不能继续引用。

## 影响

- **不影响 S00 数据本身**：`restatement_flag` 逐行写死在 `financial_normalized.csv`，Q06 判定按行读，行为不受影响。
- **不影响 S01**：S01 只用逐行标记，不用汇总计数。
- **影响引用**：任何引用「重述待核 2,157 / 6,373」的地方都要改口径——2,157 是**抽取层按文档**的 NEEDS_REVIEW 数（Codex 逐键对账也是 2,157），6,373 已作废。

## 处置

1. 本勘误随 S00 验收记录一并存档，`acceptance_20261029.json` 的 `restatement_flag_row_counts.note` 已同步改写。
2. `review.json` 作为自检历史记录**不篡改**，引用时以本勘误为准。
3. 后续任何重述相关数字，一律写明「行级 / 文档级 / 公司-期间级」。
