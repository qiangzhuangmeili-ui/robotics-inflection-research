# R03（#47）公司与行业拐点研究交接说明（#63 Batch 01 + #64 Batch 02 共 6 家）

- 计划版本：`20261026_collection_first_v2`；知识截止日：`2026-10-25`；固定重跑时间：`2026-11-28T00:02:00+08:00`
- 复核性质：`SELF_CHECK`（待 Codex 干净树独立复核）；`R04_released=false`、`#53 OPEN` 未触碰。

## 1. 复现命令
```powershell
$env:R03_FIXED_NOW='2026-11-28T00:02:00+08:00'; py runs/issues/R03/step_r03_build.py; py runs/issues/R03/step_r03_verify.py
```

## 2. 6 家核心公司拐点研判与 R04 准入分层（仅研究排包，非投资建议）

| 批次 | 代码 | 名称 | 锚定期 | 拐点判定 | R04 情景估值准入建议 |
|---|---|---|---|---|---|
| `R03_BATCH_01` | `SZ:300607` | 拓斯达 | `20260630` | `PARTIAL_INFLECTION_MIXED_SCOPE` | `READY_FOR_SCENARIO_VALUATION_WITH_LIMITS` |
| `R03_BATCH_01` | `SZ:002747` | 埃斯顿 | `20260630` | `CONDITIONAL_INFLECTION_QUALITY_WATCH` | `HOLD_UNTIL_QUALITY_OR_SCOPE_CLARIFIED` |
| `R03_BATCH_01` | `SZ:002472` | 双环传动 | `20260630` | `PARTIAL_INFLECTION_MIXED_SCOPE` | `READY_FOR_SCENARIO_VALUATION_WITH_LIMITS` |
| `R03_BATCH_02` | `SZ:002979` | 雷赛智能 | `20260930` | `CONDITIONAL_INFLECTION_QUALITY_WATCH` | `READY_FOR_SCENARIO_VALUATION_WITH_LIMITS` |
| `R03_BATCH_02` | `SH:688003` | 天准科技 | `20260930` | `CONDITIONAL_INFLECTION_QUALITY_WATCH` | `HOLD_UNTIL_QUALITY_OR_SCOPE_CLARIFIED` |
| `R03_BATCH_02` | `BJ:920593` | 鼎智科技 | `20260630` | `PARTIAL_INFLECTION_MIXED_SCOPE` | `READY_FOR_SCENARIO_VALUATION_WITH_LIMITS` |

- **可带限制进入 R04 情景估值（4 家）**：SZ:300607 拓斯达, SZ:002472 双环传动, SZ:002979 雷赛智能, BJ:920593 鼎智科技
- **暂留质量/口径观察（2 家，需先验证现金流/扣非/存货或按高不确定性处理）**：SZ:002747 埃斯顿, SH:688003 天准科技

## 3. 结转至 R04 的铁律
- 6 家公司在各自锚定期纯机器人本体收入均为 `UNKNOWN`，R04 严禁编造单一纯本体营收基数，必须按分部混合口径做情景与敏感性区间，且不输出买卖建议或目标价预测。
