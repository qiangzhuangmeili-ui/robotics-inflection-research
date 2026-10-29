S01 已按 `ACCEPTED_WITH_LIMITS` 验收（提交 `c2bfc0d`），本卡置 `READY`。

## 开工前置

- 规则版本：**`S01_SCREEN_RULES_V2`**，`sha256 = ada501e8bcd276ce670a4799c730a81cdf2f9dc70c244f9255485b00168c6a85`。不得回退 v1（v1 的 SG02 = 0.05pp 是单位错误，实际门槛比文字定义小 100 倍）。
- 输入指纹（三份，须在 `calculation_manifest.json` 复核登记）：
  - `runs/issues/S00/financial_normalized.csv.gz` — `9d124e64…`，5,922,025 B
  - `runs/issues/S00/normalization_manifest.json` — `4293a95c…`，31,093 B
  - `data/company_master.csv` — `9d9e83ea…`，707,054 B
- 验收记录与限制：`runs/issues/S01/acceptance_20261029.json`

## 必须输出

1. `all_pool_metrics.csv`：**逐格**给出 `metric_status`（OK / PROVISIONAL / HOLD / MISSING / NOT_COMPARABLE / UNDEFINED_BASE / EXCLUDED_SCOPE）、`quality_flags`（Q01–Q12）、计算期间、分子/分母、来源 `document_id` 与 `version_used`。只给汇总不算交付。
2. `metric_qc.csv`：单位、前导零、NA、极端值、跨期与版本核对结果。
3. `calculation_manifest.json`：规则版本与哈希、三份输入指纹、**最新可用期定义**、公式版本。

## 三条硬约束

- **PROVISIONAL 不得混入普通 OK**。S01 里 386 家最新期样本因已确认重述落 PROVISIONAL，S02 必须单列。
- **最新可用期锚定沿用 S01 定义**（营收 `REV.YTD`/`REV.SQ` 或扣非 `NPDEDT.YTD` 有可用值）。复算时若改成「该字段自身有值的最新期」，SG09 会从 203 变 215（+12 家回退到更早期间），计数即漂移。
- **不得复制 `SIGNAL_DEPS` 表**。该表目前硬编码在 `tools/s01_rules_check.py`，规则文件未登记 `dependencies`；S02 若需要依赖关系，从规则文件读或先迁表升版，不要在第二个地方再写一份。

## 范围

本次放行**仅限指标计算与口径检查**。不得进入 S03 名单筛选、业务深研或估值；不得以本轮计算声称具备 PIT 历史回测或机器人分部盈利归因。数据/公式有误回 S00/S01，不手工抹异常值。

S00 遗留限制原样有效：62 个整槽无值、453 份三表≠摘要表（1,326 格 XCHECK_MISMATCH）、2,157 个重述键 NEEDS_REVIEW、旧快照 2021/2022 单一来源、2026Q3 截面不完整。
