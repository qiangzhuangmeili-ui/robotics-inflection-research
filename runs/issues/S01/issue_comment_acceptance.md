收到独立复验结论，已按 `ACCEPTED_WITH_LIMITS` 落账，S01 关闭，S02 置 `READY`。

## 落账内容

- 验收记录：`runs/issues/S01/acceptance_20261029.json`（引用 `codex_acceptance_80745cd.md`）
- 本地复算审计：`runs/issues/S01/codex_audit_r4_80745cd.py` + `codex_audit_results_r4_80745cd.json`（15/15 PASS，阻断 0）
- 状态源：`data/issue_execution_plan.csv` / `.json`、`PROJECT_STATE.json`、`data/active_issue.json`、`docs/Issue执行总计划.md`
- 放行范围：**只放行 S02 的指标计算与口径检查**；S03 名单筛选、业务深研、估值仍锁

## 四项核实本地复算结果

| 项 | 结论 | 本地证据 |
|---|---|---|
| SG09 依赖与质量标记传播 | 一致 | `SIGNAL_DEPS['SG09']=['M07']`；SG09 触发 203，独立重算 M07 亦得 203；触发中 74 家带 Q06，全部未进入干净维度 |
| 23 项合成测试 + 故障注入 | 一致 | 23/23 PASS（含 T21/T22）；内存移除 SG09 依赖后 C16 确实 FAIL、`signal_flags` 返回 `None`，恢复后回到 PASS，未落盘改动 |
| 匿名重算 280 / 659 | 一致 | L1 = 841/138/75，L2 = 280/716/58，SG01∪SG02 = 659（62.52%）；重跑自检除 `checked_at` 外与交付逐字段相同 |
| v1/v2 规则、指纹、交付哈希 | 一致 | v1 `c76d0461…` 未改；v2 `ada501e8…`；逐字段 diff v1→v2 仅 5 处（SG02 阈值 0.05→5.0、note、版本号、frozen_at、change_log）；输入指纹 3/3；manifest 16/16 + 执行器 1/1 |

## 复算中发现的三处口径问题（不阻断，已记入验收记录）

1. **`SIGNAL_DEPS` 仍硬编码在代码里**，`screen_rules_v2.json` 的 signals 没有 `dependencies` 字段。C16 能拦住漏登记，但「规则文件」和「代码」仍是两份真相——这正是 SG02 单位漂移的同类风险。S02 不得复制该表，建议开工时把依赖表迁入规则文件或由规则文件生成。
2. **「最新可用期」锚定条件敏感**：按「营收或扣非累计有可用值」锚定得 SG09 = 203；若改成「该字段自身有值的最新期」则得 215（+12 家回退到更早期间）。S02 必须沿用 S01 的定义并在 manifest 写明，否则信号计数会漂移。
3. **D04 的 `clean_dims` 用 `(signal_flags(...) or {'Q00'})` 兜底**，依赖未登记时按「干净」计入辅助统计。L2 判定走 `layers().clean()` 不受影响，但违例计数会漏报，S02 复算须以 `layers` 判定为准。

## 保留的限制

阈值仍为先验假设（L1 观察队列 79.79%、L2 覆盖 26.57%，偏松未回头调）；MARGIN 与 PROFIT 维度同源，L2 含重复计数；386 家最新期样本落在 PROVISIONAL；2026Q3 截面不完整（182 家最新期为 20260930）；S00 的 62 整槽无值、453 份三表≠摘要表、2,157 重述待核、旧快照单一来源全部原样保留。

本次为规则实现复核，L1/L2 计数不是名单，也不构成任何公司的业务改善结论。

## S02 开工约束

必须使用冻结的 `S01_SCREEN_RULES_V2`（`ada501e8…`），逐格输出 `metric_status`、`quality_flags`、计算期间与来源（`document_id` / `version_used`），OK / PROVISIONAL / HOLD 三类分开，PROVISIONAL 不得混入普通 OK；沿用 S01 最新可用期定义并登记进 `calculation_manifest.json`。若需改规则，另立 v3 全池重算、保留版本差异，不按目标家数调整。
