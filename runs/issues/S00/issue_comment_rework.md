已按复核意见完成返工，提交 `5489386`。四项阻断逐项关闭，19 项机器复算全部 PASS（`runs/issues/S00/self_check_rework.json`）。

## B1 派生指标未随基础值更新

根因如复核所述：派生在 V1 仲裁之前计算，64 个年度基础值被改写后没有重算下游。

修法：派生抽成 `derive_ratios()`，在仲裁后**整体重算**；同时重算依赖 FY 的 Q4 单季（1,267 次重算、0 次值变——被仲裁的 64 个都有官方分季表，Q4 本来就是官方值）。仲裁格新增 `value_before_adoption` / `adoption_reason` / `quarterly_inputs` 三列，原始抽错值不再被当成原值。

复核举的案例已核对：

| 同方股份 FY2023 | 修复前 | 修复后 |
|---|---|---|
| 毛利率 | −490.607250% | **17.759629%** |
| 毛利额 | −19,697,770,101.68 | **5,120,716,308.64** |
| 营业收入 | 4,014,977,373.82 | 28,833,463,784.14（采用四季之和，原值留档） |

全表公式复算：毛利额、毛利率、归母净利率、现金含量四条公式 **0 违规**（`V1-1~V1-4`）。

## B2 重述信息整批丢失

根因确认：`load_extract` 以 `(field_id, note)` 建键，抽取器重述行的 note 是 `method=...;evidence=...`，代码只查空 note，永远取不到。

修复后 normalized 的 `restatement_flag`：**是 1,155 / 否 9,490 / 待核 6,373 / 不适用 903 / 未找到 15**（抽取层按文档是 是1,089 / 否5,688 / 待核2,157 / 不适用577 / 未找到1,942；normalized 按格计数，同公司多期间共用同一标记）。`comparability_note` 同步重建：`RESTATED_PRIOR_YEARS_UNRECALCULATED` 1,137 格、`RESTATEMENT_UNRESOLVED` 6,280 格。问题清单里重述待核逐条有记录（`V2-1~V2-3`）。

## B3 HOLD 未向派生值传播

派生与单季差分都改为检查上游 `EXTRACTED_XCHECK_MISMATCH`，输出 `DERIVED_HOLD_UPSTREAM` / `DERIVED_Q1_HOLD_UPSTREAM`，并把父键写进 `upstream_hold_fields`、同时在 `comparability_note` 追加 `HOLD_UPSTREAM:<父键>`。

HOLD 派生格 **2,037** 个：比率 1,627 + 单季差分 364 + Q1 45 —— 与复核给出的 1,627 和 364 完全对上。泄漏 0，父键齐全（`V3-1~V3-3`）。校验时按字段依赖关系判（毛利率只依赖收入+成本，不因归母 HOLD 而 HOLD），没有一刀切。

## B4 已归档更正版未纳入采用

新增 `tools/s00_rework_corrected.py`，对 6 个「有更正全文却用原版」的槽重抽更正版并逐字段比对：**132 个字段对，0 处不同**。确认未变后采用更正版 `document_id`，原版保留在 `original_document_id` 列，`version_used=CORRECTED_FULLTEXT`。

| 槽 | 原版 | 采用 |
|---|---|---|
| SH:600775 annual_2024 | DOC-3B39555C8D1D9CA1 | DOC-F86D11DF081C2880 |
| SH:603072 q1_2025 | DOC-CC1BF80929B33DD3 | DOC-0D2AF2262165DE19 |
| SH:605100 annual_2024 | DOC-1A141FFCD9BD1164 | DOC-518ADB2CEFCE88F4 |
| SH:688661 q3_2024 | DOC-24049C9DCA0CAD61 | DOC-90BB6DE1873B4550 |
| SZ:001380 annual_2024 | DOC-837BDE9D222C9953 | DOC-682168F4BA8934CF |
| SZ:300887 q3_2024 | DOC-672D82E6A21171E5 | DOC-125CCC8742096B2D |

688661 的 `FIN.OCF.SQ` 两版确实相同（−27,391,385.82），本例证明的是版本采用与溯源已修正，不断言金额曾错。

## 另外补的一处

V1 有 50 个年度格「四季之和 ≠ 全年」且拿不到第三方仲裁（保留全年 24 + 双方都远离快照 3 + 无第三方 23）。这些原来只写在 issues 里，最终表看上去是「正常」的全年值。现在在格上标 `PERIOD_INCONSISTENT_YTD_KEPT` 等标记，`V5-1` 要求不一致必须显式标记，`mismatch_unflagged=0`。

## 边界

- 未重跑全池采集，未改原件，未改台账状态，未筛公司、未定阈值。
- 62 个空槽（英文版 26 / 无文本层 14 / 抽取盲区 20 / 混排 2）、旧快照 2021/2022 单来源等已声明限制保留。
- 交付规模变化：normalized 228,155 行（新增 6 列）、issues 16,513 行、gz 5.6 MB；gz 改用 `mtime=0` 压缩，同一内容重复压缩哈希稳定，便于复验。
- 这是 SELF_CHECK，不是独立审计。**#35 保持打开**，等复核方复验后再关闭；S01 不正式执行，可先备草案。
