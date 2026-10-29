S01 规则预登记已完成（提交 `326ecac`），**本卡未产出任何名单**，自检 20/20 PASS，S02 仍保持 `WAITING_DEPENDENCIES`，等本卡外部复验后再启动。

## 交付

| 文件 | 内容 |
|---|---|
| `runs/issues/S01/screen_rules_v1.json` | 规则全集：12 指标 / 9 改善信号 / 6 风险提示 / 4 层判定 / 12 质量标记 / 10 类策略 / 输入指纹 / 变更程序 / 无配额声明 |
| `runs/issues/S01/metric_formulas.md` | 公式与边界，逐条列出 8 条缺失路径 |
| `runs/issues/S01/threshold_rationale.md` | 9 个阈值的取值理由、两层错误成本、亏损/缺失/低基数处理理由、附录 A 匿名干跑观察 |
| `runs/issues/S01/metric_coverage_dryrun.csv` | 匿名干跑覆盖（12 行，无公司标识） |
| `runs/issues/S01/self_check.json` | 20 项机器校验逐条结果 |
| `runs/issues/S01/manifest.json`、`handoff.md`、`review.json` | 收口三件套 |

工具：`tools/s01_rules_check.py`（结构+字段+指纹+干跑）、`tools/s01_finalize.py`。

## 冻结顺序

规则在 **2026-10-29T10:25:57+08:00** 冻结，三份研究输入（`financial_normalized.csv.gz`、`normalization_manifest.json`、`company_master.csv`）的 sha256 写入规则文件后才允许跑干跑；干跑只出聚合计数。

## 关键口径

- **HOLD 既不算改善也不算恶化**：只减少可用证据数；因 HOLD 缺维度时输出 `HOLD_FOR_DATA`，不写成「未通过」
- **负基数不算比率**：扣非基期 ≤0 改判「转正（≥1,000 万）」或绝对额改善；OCF 允许为负（M09 是绝对额差）
- **低基数需绝对额确认**：基期营收 <5,000 万或 |扣非| <1,000 万，L2 需增量 ≥1,000 万
- **周转天数用期末余额法**：平均法需 t−2y，会与 2021/2022 旧快照单一来源叠加造成系统性缺值
- **最新期逐公司回落**：`REV.YTD` → `REV.SQ` → `NPDEDT.YTD`（北交所 2 家只有单季字段）；2026Q3 只有 182 家可用
- **合同资产缺失记 NOT_IN_STATEMENT**，不填 0（560 家）

## 可执行性证据（20/20）

- 17 个 field_id 全部存在于 S00，行数逐一相等（如 `FIN.REV.YTD` 13,308、`FIN.CONTRACTASSET.INSTANT` 5,651）
- 1,054 家全部可定位最新期，0 家落 W1；12 条指标均有可计算样本（M12 465 家最少，M11 1,005 家最多）
- 配额键扫描：`target_count`/`quota`/`top_n`/`desired_count`/`must_select` 均未出现

## 已知局限（先说明，不事后改）

干跑显示 **SG01∪SG02 覆盖 718 家（68%）、L1 观察队列 867 家（82%）、L2 两维组合 496 家（47%）**，v1 阈值偏松；且 MARGIN 与 PROFIT 都来自利润率，算两维等于重复计数。

按「先登记、后运行」的原则，**本次没有回头调阈值**——看到分布再改就是用结果校准规则。修正留到 S04 收紧前另立 `screen_rules_v2.json`：加维度独立性要求（≥2 维中至少 1 维来自 GROWTH 或 CASH）、上调单季加速门槛，全池重算并出 v1/v2 差异报告。

干跑计数只证明规则能跑，**不得引用为「多少家改善」**。

## 下一步

S02 执行前须复核三份输入指纹未变；变化即视为新版本输入，规则随之升版。S02 必须逐格输出 `metric_status` 与 `quality_flag`，不得只出名单。
