# S04 → S05 交接

## 状态

- S04 返工完成，`SELF_CHECK_PASS_WITH_LIMITS`，**未放行 S05**。
- 规则版本 `S01_SCREEN_RULES_V3`（sha `6c474d1f…`），取代 v2。v2 与 v1 交付均保留只读留档。
- 通过 445 家（v1 为 443）。

## S05 可以直接用的东西

| 文件 | 用途 |
|---|---|
| `tight_pass.csv` | 445 家入选，含 `qualified_dims` / `evidence_channels` / `abs_critical` |
| `tight_decision_log.csv` | 1054 家逐家判定、阻断原因、重进条件 |
| `v1_v3_diff.csv` | 与 v1 的 2 家差异及原因 |
| `tight_summary.json` | 计数、证据通道分布、绝对额关键依赖名单 |

**必须使用 `runs/issues/S02/hangcha_restated_20261101/s00_v10/s00_v10.csv.gz`**，不得读 `runs/issues/S00/financial_normalized.csv`（已被取代，240 格数值不同）。

## S05 要做的事（不在 S04 范围）

1. 现金流/应收存货质量闸门（L3）：所用每个指标须有 `document_id` + `source_page` + 非 HOLD 状态。
2. **优先复核 16 家绝对额关键依赖**（剔除 SG06/SG08 后不足 2 维），名单见 `tight_summary.json.abs_channel_dependency`，含南天信息（SZ:000948）。
3. 低基数确认的 45 条信号须抽验原始金额（S04 只做数据链核对，未回读 PDF）。
4. `NO_CONFIRM_RULE` 的 25 条（SG02/SG03/SG05/SG07）如需启用，须先立 v4 预登记映射，不得临时补金额。

## 外部复核建议重点

1. **v3 规则变更是否合规**：`screen_rules_v3.json` 的 `change_log` 是否完整、阈值是否真的未改（C07）、绝对额通道资格是否被滥用。
2. **低基数确认口径**：SG04 用累计、SG09 用单季，是否与信号定义一致；45 条确认中是否有跨期口径错配。
3. **充要条件**：C03 的独立重算是否真的独立；`test_tight_screen.py` 的 iff 断言是否覆盖全部 1054 行。
4. **两份 S00**：本版是否确实全程只读 `s00_v10`（manifest 有哈希闸门），旧 S00 是否被任何下游误用。
5. **445 不是目标数**：C05 已移除数量锁，若复核认为口径应更严导致数字变化，属正常结果，不得回头凑数。

## 已知限制

- 自检不等同独立复核；本版所有结论均为自检性质。
- SG02/SG03/SG05/SG07 低基数无确认映射，保守不计入。
- 未回读 PDF、未做业务采用；445 家不等于投资候选。
- 旧 S00 交付件仍在仓库，尚未在 S00 侧正式标注取代关系（建议 S00 补一次勘误）。
