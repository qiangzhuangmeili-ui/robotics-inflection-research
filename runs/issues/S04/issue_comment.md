S04 执行完成，自检通过，PR #52 已提交待复核。

**结论**：SELF_CHECK_PASS_WITH_LIMITS。1,054 家全部保留，未删除、未改阈值、未新增硬门槛。

| 交付 | 家数 | 说明 |
|---|---:|---|
| `runs/issues/S04/tight_pass.csv` | 443 | 干净维度 ≥2；等于 S03 `AUTO_PASS_L2_READY`，逐家一致 |
| `runs/issues/S04/tight_observe.csv` | 611 | 未通过/不在范围，全部保留并带重进条件 |
| `runs/issues/S04/tight_decision_log.csv` | 1,054 | 逐家触发/未触发原因、维度明细、阻断缺口 |
| `runs/issues/S04/review_100_qc.csv` | 100 | 只核数据依赖，未新增 PDF 深读 |

决策分布：`L2_SHORTLIST_CANDIDATE` 443、`L2_HOLD_FOR_DATA` 10、`L2_NOT_SHORTLISTED` 324、`L2_NOT_IN_SCOPE` 273、`WATCH_AFTER_CUTOFF` 4。

**口径**：L2 规则原文照抄 S01 v2；阈值全部从 `runs/issues/S01/screen_rules_v2.json`（`ada501e8…`）读取，脚本内不写筛选数值。干净维度与 S03 `clean_ok_dims_count`、`hold_dims_count` 逐家对账，差异 0。PROVISIONAL / 低基数未确认 / 上游 HOLD 不计入维度——因此 100 家高优先对象里 65 家本就不在收紧范围，25 家单维不足，只有 10 家真正挂起等数据。四家截止日后公司保持隔离，零信号零维度。合同负债 / 在手订单 / 在建工程未进门槛（METHOD_20261107_LEADING_INDICATORS）。

**证据等级**：A 级 422 家（干净信号指标全部 OK）、B 级 21 家（含 SG06/SG08 绝对额通道，指标按设计为 UNDEFINED_BASE）。其中仅南天信息（SZ:000948）的通过完全依赖该通道，建议 S05 优先复核。

**自检 10/10**：输入哈希闸门、主键覆盖、分区互斥、两项维度对账、443 家一致性、四家隔离、交付守恒、阈值未改、核验对象齐全；两次运行输出哈希一致。

**限制**：自检不等同独立复核，S05 不放行；未回读 PDF、未新增业务采用；443 家不等于投资候选；42 份重述宽容假设与 973 格 PROVISIONAL 继续有效。

PR：https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/pull/52
报告：`runs/issues/S04/REPORT.md`　交接：`runs/issues/S04/handoff.md`
