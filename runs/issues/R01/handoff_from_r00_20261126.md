# R01 / #45 放行与交接（来自 R00 #44 独立验收）

- 计划版本：`20261026_collection_first_v2`
- 放行时间：`2026-11-26T22:48:00+08:00`
- 放行批准：用户明确批准执行方案 A，放行 `#45 R01`（覆盖 R00 已独立验收的 10 家核心 `TIER_1` 公司，拆分为 2 个固定 5 家执行子卡 `R01_BATCH_01` 与 `R01_BATCH_02`），并继续沿用独立复核方 Codex `--sandbox danger-full-access` 授权（默认 `gpt-6.2-sol low`，遇复杂归因争议升 `high`）。
- 统筹方：Antigravity；执行方：CodeBuddy；独立复核方：Codex
- 前置验收：
  - `runs/issues/R00/acceptance_r00_batch01_02_20261126.json`（`ACCEPTED_WITH_LIMITS`，commit `6ccd19f5e23be8342c4ac0d71c265b473d53d833`）
  - `runs/issues/S08/acceptance_s08_20261126.json`（`ACCEPTED_WITH_LIMITS`）
  - `runs/issues/R02/acceptance_r02_20261126.json`（`ACCEPTED_WITH_LIMITS`）
- 方法论补充：`docs/需求先行指标分工_20261107.md`（`METHOD_20261107_LEADING_INDICATORS`）
- 知识截止日：`2026-10-25`

## 1. 固定名单（2 批共 10 家，互斥零重复）

- **`R01_BATCH_01`（5 家，对应 R00 #57）**：`SZ:300607 拓斯达`（H1）、`SZ:002472 双环传动`（H1）、`SZ:002979 雷赛智能`（9M）、`SZ:002747 埃斯顿`（H1）、`BJ:920593 鼎智科技`（H1）。
- **`R01_BATCH_02`（5 家，对应 R00 #58）**：`BJ:920510 丰光精密`（H1）、`BJ:920491 奥迪威`（H1）、`SH:688003 天准科技`（9M）、`SZ:002698 博实股份`（H1）、`BJ:920578 巨能股份`（H1）。

## 2. 财务归因与收入范围核验红线

1. **收入范围分层**：逐家核对“纯机器人单项收入 / 混合含机器人大类收入 / 公司总收入”、分母、并表范围与报告期（严格分离 8 家 H1 与 2 家 9M）。不能把公司总收入或混合类别金额全归机器人；未单列的纯机器人收入保持 `UNKNOWN`，严禁由合作/产能/订单规模反推实绩。
2. **四维财务归因（收入、毛利、扣非净利、经营现金流）**：复用冻结 `s02_v10/all_pool_metrics.csv`、`S05/quality_flags.csv`、`S05/quality_decision_log.csv` 与 `R00` 核验底稿，核实业务改善是否真实传导至收入、毛利率、扣非净利润与回款（经营现金流/净利），对非经常性损益高占比（埃斯顿 56.5%、天准科技 67.7%）、现金流背离（雷赛 9M -0.172 / Q3 -9,489 万、埃斯顿 0.276、巨能 0.166）、毛利率下滑（拓斯达自动化系统 -10.46pp、奥迪威 -2.43pp、博实机器人+ 14.87%）给出清晰归因与限制。
3. **需求先行指标边界（`METHOD_20261107_LEADING_INDICATORS`）**：合同负债不等于全部订单或已实现收入；在手订单区分金额口径与台数口径且未披露不填 0；在建工程不直接当改善信号。
4. **交付与边界守卫**：输出 `financial_attribution_dispatch.csv`、`robot_revenue_scope.csv`、`attribution_review.json` 及标准 `manifest.json`、`handoff.md`、`review.json`、`step_r01_build.py`、`step_r01_verify.py`（支持 `R01_FIXED_NOW` 逐字节复现、纯 LF、动态推导结论、活体负例测试）。本次不放行 R03、不做估值、不触碰 `#53`（保持 OPEN）。
