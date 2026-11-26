# R01（#45）财务归因与收入范围核验交接说明（#59 Batch 01 + #60 Batch 02 共 10 家）

- 计划版本：`20261026_collection_first_v2`；知识截止日：`2026-10-25`；固定重跑时间：`2026-11-26T22:50:00+08:00`
- 复核性质：`SELF_CHECK`（不冒充独立验收；待 Codex 干净树独立复核）
- 覆盖范围：10 家 R00 已独立验收的 `TIER_1` 公司，严格拆分为 8 家 H1（`20260630`）与 2 家 9M（`20260930`：雷赛智能、天准科技），严禁跨期合并。
- 方法论遵循：`METHOD_20261107_LEADING_INDICATORS`（合同负债/在手订单/在建工程独立留痕，未披露留 `UNKNOWN` 不填 0）。
- 放行守卫：`R03_released=false`、`R04_started=false`、`#53 OPEN` 未触碰。

## 1. 复现命令
```powershell
$env:R01_FIXED_NOW='2026-11-26T22:50:00+08:00'; py runs/issues/R01/step_r01_build.py; py runs/issues/R01/step_r01_verify.py
```

## 2. 10 家公司收入范围与归因分层一览

| 批次 | 代码 | 名称 | 锚定期 | 收入口径层级 | 锚定期纯本体收入 | S05 质量项 | 归因判定 | R03 排包建议 |
|---|---|---|---|---|---|---|---|---|
| `R01_BATCH_01` | `SZ:300607` | 拓斯达 | `20260630` | `MIXED_SEGMENT_DISCLOSED` | `UNKNOWN` | 触发:无 / 待核:无 | `CORE_ROBOT_DRIVER_WITH_MIXED_SCOPE` | `R03_PRIORITY_A` |
| `R01_BATCH_01` | `SZ:002472` | 双环传动 | `20260630` | `UNDISCLOSED_IN_BROADER_LINE` | `UNKNOWN` | 触发:无 / 待核:RH02 | `MIXED_OR_UNQUANTIFIED_DRIVER` | `R03_PRIORITY_A` |
| `R01_BATCH_01` | `SZ:002979` | 雷赛智能 | `20260930` | `UNDISCLOSED_IN_BROADER_LINE` | `UNKNOWN` | 触发:RH04 / 待核:RH02 | `CORE_ROBOT_DRIVER_WITH_MIXED_SCOPE` | `R03_PRIORITY_A` |
| `R01_BATCH_01` | `SZ:002747` | 埃斯顿 | `20260630` | `MIXED_SEGMENT_DISCLOSED` | `UNKNOWN` | 触发:RH04;RH06 / 待核:无 | `CORE_ROBOT_DRIVER_WITH_MIXED_SCOPE` | `R03_PRIORITY_A` |
| `R01_BATCH_01` | `BJ:920593` | 鼎智科技 | `20260630` | `UNDISCLOSED_IN_BROADER_LINE` | `UNKNOWN` | 触发:无 / 待核:RH02 | `MIXED_OR_UNQUANTIFIED_DRIVER` | `R03_PRIORITY_A` |
| `R01_BATCH_02` | `BJ:920510` | 丰光精密 | `20260630` | `UNDISCLOSED_IN_BROADER_LINE` | `UNKNOWN` | 触发:无 / 待核:RH02 | `NON_ROBOT_OR_QUALITY_CAVEAT` | `R03_OBSERVE_OR_DEFER` |
| `R01_BATCH_02` | `BJ:920491` | 奥迪威 | `20260630` | `MIXED_SEGMENT_DISCLOSED` | `UNKNOWN` | 触发:RH05 / 待核:RH02 | `NON_ROBOT_OR_QUALITY_CAVEAT` | `R03_OBSERVE_OR_DEFER` |
| `R01_BATCH_02` | `SH:688003` | 天准科技 | `20260930` | `MIXED_SEGMENT_DISCLOSED` | `UNKNOWN` | 触发:RH02;RH06 / 待核:无 | `CORE_ROBOT_DRIVER_WITH_MIXED_SCOPE` | `R03_PRIORITY_A` |
| `R01_BATCH_02` | `SZ:002698` | 博实股份 | `20260630` | `MIXED_SEGMENT_DISCLOSED` | `UNKNOWN` | 触发:RH05 / 待核:无 | `NON_ROBOT_OR_QUALITY_CAVEAT` | `R03_OBSERVE_OR_DEFER` |
| `R01_BATCH_02` | `BJ:920578` | 巨能股份 | `20260630` | `MIXED_SEGMENT_DISCLOSED` | `UNKNOWN` | 触发:RH04 / 待核:无 | `NON_ROBOT_OR_QUALITY_CAVEAT` | `R03_OBSERVE_OR_DEFER` |

## 3. R03 优先候选与观察/延后分层（仅研究排包，非投资建议）
- **`R03_PRIORITY_A`（6 家）**：SZ:300607 拓斯达, SZ:002472 双环传动, SZ:002979 雷赛智能, SZ:002747 埃斯顿, BJ:920593 鼎智科技, SH:688003 天准科技
- **`R03_OBSERVE_OR_DEFER`（4 家）**：BJ:920510 丰光精密, BJ:920491 奥迪威, SZ:002698 博实股份, BJ:920578 巨能股份

## 4. 关键结转限制条款
- 10 家公司在各自锚定期（2026H1 / 2026Q1-Q3）均未单列纯机器人本体收入（`anchor_pure_robot_rev_cny=UNKNOWN`）；FY2025 仅拓斯达单列机器人本体 300,432,856.32 元。
- 双环传动 2026H1 的 4.40 亿元归属“减速器及其他”混合科目；丰光精密 2025 年对意优机器人客户销售额 1,234.21 万元（5.89%）仅作客户销售额事实记录；博实股份灵博机器人属 2026-08 拟增资未交割事项（截至 H1 尚未出资、尚未参股，交割及会计处理待核）。
- 严禁由在手订单台数（如雷赛 100 万台）或产能规划（如 300 万台）反推实绩收入；未披露在建工程/在手订单一律保留 `UNKNOWN`。
