## 最终结论

**`RETURN_FOR_REWORK`**。#47 及子卡 #63、#64 的交付通过了干净树重放和单字节篡改测试。实质审计发现，六家公司共用的 R02 引用混淆了改善率与样本覆盖率，个别公司把上游推断或未披露事项写成确定事实，雷赛智能的 R04 准入建议也缺少对现金流警报的明确约束。R04 保持未放行。

## 复核对象与重放证据

| 检查 | 独立复核结果 |
|---|---|
| 提交与环境 | `21a47d63adbcffc541343642bdc7b292bd596ec5`，在 detached 临时 worktree 中执行。创建时以 `core.autocrlf=false` 保留提交中的原始行尾。 |
| 基线验证 | `py runs/issues/R03/step_r03_verify.py` 退出码 `0`，`8/8 PASS, anomalies=0`。 |
| 固定时间重建 | `R03_FIXED_NOW=2026-11-28T00:02:00+08:00`，构建退出码 `0`，`git status --short` 无输出，脏文件 `0`。 |
| 实测负例 | 将拓斯达首个 `F1：` 改为 `X1：`，只改动一个字节。校验退出码 `1`，V03、V06、V08 均失败。恢复后重新校验为 `8/8 PASS, anomalies=0`，工作树干净。 |
| 清单完整性 | 独立复算 8 项输入及 6 项交付的字节数、SHA-256 和根摘要，全部一致。14 项均受 Git 跟踪，原始字节为 LF、无 BOM。`manifest.json` 无 `review_provenance_refs` 字段，`review.json` 中该字段为空数组，无失效引用。 |
| 清理 | `git worktree remove --force` 已注销临时 worktree。Windows 首次删除时留下空目录，退出该目录后已移除。复查目录不存在，`git worktree list` 仅列主工作树。 |

指定提交中没有 `runs/issues/R01/revenue_scope_bridge.csv` 和 `runs/issues/R01/quality_and_balance_check.csv`。本次按 R01 验收记录及 R03 清单实际引用的 `robot_revenue_scope.csv`、`attribution_review.json` 执行收入与质量对账，并核对 R02 的 `industry_signals.csv`、`industry_limits.md`。复核范围为已验收底稿与 R03 交付之间的一致性，未重新逐页核读公司公告。

## 六家公司与 R04 分流

#63 为拓斯达、埃斯顿、双环传动，#64 为雷赛智能、天准科技、鼎智科技。两批各 3 家、无重复，并集严格等于 R01 的 `R03_PRIORITY_A`，没有 `R03_OBSERVE_OR_DEFER` 混入。共 4 家 H1、2 家 9M，与派单一致。六家均填写了产品线、财务事实、替代解释、可推翻信号及缺证条件，具体口径问题见下表。 [#63 固定名单](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/63) · [#64 固定名单](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/64)

| 公司与锚定期 | 实质审计 | 交付中的 R04 建议 |
|---|---|---|
| 拓斯达 · H1 · T02 | 工业机器人及自动化应用系统 7.07 亿元、同比 +121.62%，板块毛利率同比降 10.46 个百分点。集成放量与低毛利能源业务收缩支持“部分拐点”，后续以本体拆分、板块毛利率和回款检验。小拓、星仔的收入状态写得过强，全年与半年金额的叙述也需修正。 | 带限制候选 |
| 埃斯顿 · H1 · T02 | 机器人及智能制造系统毛利率同比升 4.69 个百分点，集团扣非从上年同期亏损转正。一次性公允价值收益和弱现金转化仍是主要反证。酷卓 9 月并表已与 H1 分开。后续观察回款、扣非和并表后损益。 | HOLD，与质量警报一致 |
| 双环传动 · H1 · T01 | “减速器及其他”FY25 同比 +21.18%，H1 同比 +26.18%。4.40 亿元及 47.47% 自算毛利率均为混合大类口径。增长、毛利回落及环动科技单体披露可检验部分拐点，纯 RV 盈利仍缺证。 | 带限制候选 |
| 雷赛智能 · 9M · T01 | 集团收入同比 +46.77%，经营现金流约 −5,153 万元，Q3 单季约 −9,489 万元。通用工控周期和营运资金占用均是实质反证。10.08 亿元伺服系统收入不能量化机器人部件贡献，部件归入伺服系统仍属推断。后续以现金回补、存货和票据变化检验。 | 带限制候选，准入依据需补 |
| 天准科技 · 9M · T01 | 9M 集团收入同比 +52.07%，存货较年初 +75.01%，扣非约占归母利润 32.31%。H1 具身大脑方案收入 1.58 亿元，3.15 亿元为混合新签订单，两项均已标明 H1。具身业务判断限于 H1，后续观察存货、星智现金流和域控拆分。 | HOLD，与口径和质量缺证一致 |
| 鼎智科技 · H1 · T01 | 直流电机及组件 FY25 同比 +118.39%、H1 同比 +202.29%，纯机器人金额未知。赛仑特并表与毛利结构下行是实质反证。半年报综合毛利率同比 −6.31 个百分点，与冻结 M04 的 +15.22 个百分点仍待核。后续观察并表满周年后的内生增长和周转。 | 带限制候选 |

R02 的工业机器人产量与各主题同锚定期的改善率、营收中位数可以回溯到相应行。财务锚定期没有发现 H1 与 9M 的金额合并。两份 R03 研究交付均未发现买卖建议、目标价或估值结论。`review.json` 保持 `SELF_CHECK_PASS_WITH_LIMITS`，复核性质为 `SELF_CHECK`，`R04_released` 为 JSON 布尔值 `false`。该提交只改动 R03 的 8 个文件，未改 S00 勘误，GitHub #53 仍为 Open。本次未修改仓库控制文件或 GitHub issue。 [#53 S00 勘误](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/53)

## 必改项

以下路径均相对于提交 `21a47d6` 的仓库根目录。修复应落在生成脚本，并同步重建交付和清单。

1. **修正六家公司的行业改善率分母。** `runs/issues/R03/step_r03_build.py:142,151` 把 `valid_paired_count / denominator_count` 放在改善率后，生成到 `inflection_cases.csv:2–7` 的 `r02_industry_signal_ref`。按 R02 定义，改善率分母是有效配对数。营收改善应写为 T02 H1 **43/48**、T01 H1 **59/70**、T01 9M **20/22**。扣非改善应写为 **32/39、32/41、14/15**。如保留 `48/61` 等数字，明确标注为有效配对覆盖。依据为 `runs/issues/R02/industry_signals.csv:83–88,123–127` 及 `industry_limits.md` 第 11 条。
2. **恢复未知状态，并标注分项归属的证据等级。** `inflection_cases.csv:2,3,4,7` 的 `product_line_separation`，以及 `counter_evidence.md:16,24,32,56`，应逐项核对早期产品的“无收入”表述。小拓、星仔及鼎汇等没有确认零收入的证据时，改为“未披露独立收入”或 `UNKNOWN`。双环和鼎智的研发项目亦按相同规则处理。`inflection_cases.csv:5` 同字段及 `counter_evidence.md:40` 应把雷赛“伺服系统包含无框力矩电机等机器人部件”标为推断，继承 `runs/issues/R01/attribution_review.json:527` 的限制。
3. **明确列出同期基准，分开财务事实与解释。** `inflection_cases.csv:2,5,6` 的 `two_period_comparable_facts` 及 `counter_evidence.md:17,41,49`，应把拓斯达的 H1 同比证据写成 2025H1 对 2026H1，将 FY25 全年金额列为背景，并给能源业务 `9.15亿→0.70亿` 补齐期间和依据。雷赛、天准应明确列出 2025 年同期与 2026 年同期的同口径值，标注直接披露或复算。雷赛的 Q3 单季与 9M 累计分别比较各自上年同期，伺服分部对 R02 集团营收中位数只作背景参照。天准 H1 分部及订单另列，且 `falsifiers` 中的“毛利率继续下滑”改为可观察的阈值条件，保留 H1 毛利率未知。
4. **为雷赛的 R04 分流补上明确条件。** `inflection_cases.csv:5` 的 `r04_valuation_readiness`、`counter_evidence.md:39` 和 `handoff.md:22` 应同步说明，在 RH04 已触发、9M 及 Q3 单季现金流为负的情况下，哪些集团或混合分部情景可用，哪些机器人收入或现金转化假设必须等待新证据。若无法给出这些边界，改为 `HOLD_UNTIL_QUALITY_OR_SCOPE_CLARIFIED`，同步更新分流计数，并保留 `R04_released: false`。
