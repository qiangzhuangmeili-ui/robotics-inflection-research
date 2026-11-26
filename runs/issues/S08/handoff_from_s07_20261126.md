# S08 / #43 正式放行与交接

核对日期为 2026-11-26（北京时间）。计划版本为 `20261026_collection_first_v2`。
用户已确认放行（2026-11-26T14:09:26+08:00），并明确授权独立复核方 Codex 在本次任务中使用 `--sandbox danger-full-access` 执行真实 `py` 干净树重放与复核。统筹方为 Antigravity，执行方为 CodeBuddy，独立复核方为 Codex（默认 `gpt-6.2-sol low`，遇复杂争议再升档 `high`）。详见 [放行记录](release_20261126.json)。

## 放行范围与目标

S08 只做**指标轮总验收与后期业务核验名单冻结**，**不启动任何公司业务深研或估值**，**不提前放行 R00/R02**。

核心任务四项：
1. **全池 1,054 家全链条对账**：完整对账 S03 宽筛（777+149+128）、S04 收紧（基线 445）、S05 质量（277 pass + 1 hold + 776 observe）、S06 观察（54 早期储备 + 379 缺数据观察，交集 33，非主线并集 399）及 S07 审计限制，确保每家公司都有明确且可复现的进入/观察/未过理由。
2. **闭环 S07 F10：固化 `445→278` 逐家映射表（`s04_to_s05_bridge_445_to_278.csv`）**：100% 基于 Git 跟踪的冻结文件（`S04/tight_decision_log.csv` + `S05/quality_pass.csv` + `S05/quality_observe.csv` + `S05/observe_pool_preserved_776.csv` + `S06/missing_data_watch.csv` + `S06/early_stage_watch.csv`），固化 445 家 S04 基线候选中 278 家进入 S05 质量池、167 家落入 `HOLD_FOR_DATA` 观察池的逐家去向、版本与理由，并关联已核验的 Drive 归档 ID `1VrpWyQct6xI5PpRdGNs6KFZmubbspYEA`。
3. **冻结后期业务核验名单与优先级分层（`business_verification_candidates.csv`）**：
   - 覆盖全部 1,054 家主键（每家明确标注 `final_queue`：`R00_MAINLINE_VERIFY` [277 家]、`OBSERVE_QUALITY_HOLD` [1 家冀东装备]、`OBSERVE_EARLY_STAGE_ONLY` / `OBSERVE_EARLY_AND_MISSING` / `OBSERVE_MISSING_DATA_ONLY`、`NOT_SELECTED_FOR_R00`），**绝不为凑固定数量修改门槛，绝不手工加回公司**。
   - 为 `R00_MAINLINE_VERIFY` 的 277 家按**规则与证据缺口**分配清晰的核验预算优先级分层（如 P1：已有历史可追溯机器人证据且无/少质量风险触发；P2：无质量风险触发的 111 家其余公司；P3：有质量风险触发或 RH06/RH02/RH03 待核项的其余主线公司），并显式标注锚定期分层（H1 vs 9M）、BJ 市场标识、质量触发标签与 F05–F12 结转提示，供后续 R00 按 5 家小包派工。
4. **历史成果复用映射（`candidate_reuse_map.csv`）**：精确关联旧 53 家采用、旧 45 家细筛候选、10 家早期局部样本及 B00/C00/D00 已有成果，**只复用、不自动提升状态**（例如未过 S05 277 主线的旧 45 家候选仍保留在对应观察或未选分区，绝不自动进入 R00 主线）。

## 继承守卫与 S07 结转限制

- 必须全部显式写入 `screen_acceptance.json`：F05（H1 200 vs 9M 78 锚点分层）、F06（RH02 项目制豁免 31 家）、F07（低基数保守偏差）、F08（BJ 差异仅描述）、F09（反向重推限 5 家）、F10（已通过 `s04_to_s05_bridge_445_to_278.csv` 固化 Git 可重放映射，原未跟踪复核版以 Drive 归档 ID 留溯源）、F11（20 格越界值保留原值/OK 状态与冻结路由）、F12（RH06 7 家继续待核）。
- 继承守卫：4 家截止日隔离、1 家锚点待重选、15 家质量来源未知、8 项未采用父链、冀东装备 `SZ:000856` `QUALITY_HOLD`，`#53` 保持 OPEN。
- 全部运行输入 100% 位于 Git 跟踪树内；全部文本交付纯 LF 换行；支持 `S08_FIXED_NOW` 逐字节复现；不修改 `runs/issues/S08/` 以外任何文件；不释放 R00/R02。
