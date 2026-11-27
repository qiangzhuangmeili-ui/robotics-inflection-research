# R03 / #47 放行与交接（来自 R01 与 R02 独立验收）

- 计划版本：`20261026_collection_first_v2`
- 放行时间：`2026-11-27T23:55:00+08:00`
- 放行批准：用户正式批准放行 `#47 R03`（公司与行业拐点研究：每包最多 3 家公司），覆盖 `R01` 筛选出的 6 家 `R03_PRIORITY_A` 核心公司（拆分为 2 个固定 3 家子卡 `#63 R03_BATCH_01` 与 `#64 R03_BATCH_02`），并可对接 `F:\豆包\doubao-cli`（`deepseek` 模型）提供独立反方视角，最终由独立复核方 Codex（`--sandbox danger-full-access`）干净树复核。
- 前置验收：
  - `runs/issues/R01/acceptance_r01_20261126.json`（`ACCEPTED_WITH_LIMITS`）
  - `runs/issues/R02/acceptance_r02_20261126.json`（`ACCEPTED_WITH_LIMITS`）
  - `runs/issues/R00/tier1_completion/acceptance_r00_tier1_complete_20261127.json`（18/18 `TIER_1` 闭环）
- 知识截止日：`2026-10-25`

## 1. 固定名单（2 个 3 家小包，互斥零重复）

- **`R03_BATCH_01`（#63，3 家，整机龙头 + RV 减速器主线，全部 H1 锚定）**：`SZ:300607 拓斯达`、`SZ:002747 埃斯顿`、`SZ:002472 双环传动`
- **`R03_BATCH_02`（#64，3 家，驱动/域控 + 微特电机主线，2×9M + 1×H1 严格分期）**：`SZ:002979 雷赛智能`（9M）、`SH:688003 天准科技`（9M）、`BJ:920593 鼎智科技`（H1）

## 2. 拐点研究铁律

1. **产品线严格分开**：不取最高阶段或前沿研发（如人形样机/合作）代表整家公司，也不把行业产量增速直接归因于单家公司。
2. **至少两期可比事实 + 替代解释**：每家必须对比至少两期同口径可比事实，显式排查低基数、周期波动、并表（如赛仑特、酷卓期后交割）、一次性因素（如埃斯顿 9,950 万公允价值收益、天准 9M 非经常性占 67.7%）、现金流背离（雷赛 Q3 -9,489 万、埃斯顿 0.276）等替代解释。
3. **可推翻信号（Falsifiers）与缺证条件**：逐家列出未来可证伪“拐点”的具体可观测信号与当前缺证条件；无法独立归因者标为观察或受限拐点，绝不先写乐观结论再找证据。
4. **交付物与边界守卫**：输出 `inflection_batch_dispatch.csv`、`inflection_cases.csv`、`counter_evidence.md` 及标准 `manifest.json`、`handoff.md`、`review.json`、`step_r03_build.py`、`step_r03_verify.py`（支持 `R03_FIXED_NOW` 逐字节复现、纯 LF、动态结论、活体负例测试）。本次不放行 R04 估值、不新增买卖建议、不触碰 `#53`（保持 OPEN）。
