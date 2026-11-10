# S04（#39）L2 第二道收紧 — 返工报告

- 执行：WorkBuddy AI｜时间：2026-11-10
- 状态：`SELF_CHECK_PASS_WITH_LIMITS`（自检，**不等同独立复核**）
- 规则：`S01_SCREEN_RULES_V3`（sha `6c474d1f…`），取代 v2
- 覆盖：1054 家｜通过 **445** 家（v1 为 443）
- 自检 9/9 PASS｜回归测试 16/16 PASS｜两次运行输出哈希一致

## 一、为什么返工

2026-11-08 交付的 v1 被独立复核判为 `RETURN_FOR_REWORK`。逐条核实后，两项 P1 成立：

| 编号 | 问题 | 证据 |
|---|---|---|
| P1-01 | 低基数信号未执行绝对额确认，直接不计入维度 | v1 `tight_screen.py` L188-189；只在 `reentry_condition` 写「取得确认后可计入」 |
| P1-02 | 指标资格未落地：算了 `ok_dims` 却用 `clean_dims` 决策 | v1 L195 / L225-232 / L248 |

另有三条属实：C05/C07 硬编码 443、`review.json` 与 `active_issue.json` 状态不一致、最新提交未改脚本。

**复核意见有一处证据错误**：和林微纳（688661）不是漏筛。复核用的是 `runs/issues/S00/financial_normalized.csv`，而 S02 实际消费的是 `s00_v10`。按权威版本其单季扣非增量仅 **+232.91 万元**（361.79 万 → 594.70 万），远低于 1,000 万门槛，本就应排除。复核给出的 4,188.98 万来自被取代的旧 S00。

## 二、规则变更 v2 → v3

返工前先向 Codex 咨询并取得书面裁决（`codex_ruling.md`）：**选 B、锁定 s00_v10、先冻结 v3 再复算**。

1. **L2 改为双通道资格**：比率通道所用指标须 `metric_status=OK`；SG06/SG08 绝对额通道须实际输入行 `status` 属 usable 且跨期可比，单独登记 `ABS_CHANNEL`，不沿用上游 CLEAN 标签，也不把 M05 的 `UNDEFINED_BASE` 改写成 OK。
   - 理由：SG06 只在基期<0 时触发，此时 M05 必为 `UNDEFINED_BASE`；严格按「均 OK」会让 SG06 在 L2 永久失效，与 `policies.loss` 冲突。
2. **新增 `low_base_confirmation` 同口径映射**：SG01→累计营收、SG04/SG06→累计扣非、SG09→单季扣非、SG08→累计经营现金流；增量 ≥1,000 万元且两侧输入可用、无未决重述。
3. **SG02/SG03/SG05/SG07 记 `NO_CONFIRM_RULE`**：无冻结的确认映射，本版不计入，保留观察；不得临时拿任意金额替代。
4. **输入指纹改指向 s00_v10**，旧 S00 列入 `superseded`。

**九条信号阈值一字未改**（C07 逐条比对 v2）。未新增或删除任何信号。

## 三、结果

| 决策 | 家数 |
|---|---:|
| `L2_SHORTLIST_CANDIDATE` | **445** |
| `L2_HOLD_FOR_DATA` | 10 |
| `L2_NOT_SHORTLISTED` | 322 |
| `L2_NOT_IN_SCOPE` | 273 |
| `WATCH_AFTER_CUTOFF` | 4 |

相对 v1 只变了 2 家，均为低基数确认后补足第二维：

| 公司 | 变化 | 依据 |
|---|---|---|
| 公元股份（SZ:002641） | 未入选 → 入选 | SG03 毛利 + SG04 累计扣非 +2,253.57 万 |
| 同兴达（SZ:002845） | 未入选 → 入选 | SG03 毛利 + SG09 单季扣非 +3,977.51 万 |

证据通道分布：纯 A 级（比率通道全 OK）328 家；A+C 33 家；A+B 83 家；A+B+C 1 家。
**绝对额通道关键依赖 16 家**（剔除 SG06/SG08 后不足 2 维），含南天信息（SZ:000948），已单列供 S05 优先复核。

低基数信号判定：确认 45 条、增量不足 47 条、无确认映射 25 条。仅 3 家因 `NO_CONFIRM_RULE`（全部为 SG02 单季营收加速度）未能补维。

## 四、自检与测试

自检不再锁定通过家数，改为充要条件与集合不变量：

- C00 输入哈希闸门（config / rules v3 / metrics / s00_v10 / contract）
- C01–C02 覆盖 1054、三分区互斥 777/149/128
- **C03 逐行充要条件**：入选 ⟺ 合格维度≥2，独立重算与主路径零差异
- C05 集合不变量：入选 ⊆ wide_pass、四类决策互斥且合计 1054
- C06 四家截止日后公司隔离、零信号
- C07 九条阈值与 v2 完全一致
- C08 100 家定向核验对象齐全
- C09 证据降级不得增加通过集合

回归测试 16 项（`test_tight_screen.py`）：门槛边界（999.99 万 / 1,000 万）、单季口径不得借用累计、SG06 非正基期与当期金额门槛、SG08 转正、Q06 阻断、HOLD 阻断、比率型 `NO_CONFIRM_RULE`、四家边界公司端到端、隔离零泄漏。

## 五、遗留与限制

1. **自检不等同独立复核**，S05 仍 `WAITING_DEPENDENCIES`，须第二轮外部复核。
2. **两份 S00 并存**是系统性问题：旧交付件与 `s00_v10` 有 240 格数值不同、1,784 键仅新版有。本版已锁 `s00_v10` 并在 v3 指纹中登记，但旧文件仍在仓库中，需在 S00 侧正式标注取代关系。
3. SG02/SG03/SG05/SG07 的低基数确认映射缺失，本版按 `NO_CONFIRM_RULE` 不计入，属保守处理；如需启用须另立 v4 预登记。
4. 未回读 PDF、未新增业务采用；445 家不等于投资候选。
5. 100 家定向核验只核数据依赖链，未新增原件深读。

## 六、交付清单

```
runs/issues/S04/
  tight_screen_v2.py          执行脚本（v1 已归档）
  test_tight_screen.py        16 项回归测试
  tight_pass.csv              445
  tight_observe.csv           609
  tight_decision_log.csv      1054
  review_100_qc.csv           100
  v1_v3_diff.csv              2 家变化
  tight_summary.json          汇总与自检结果
  manifest.json               输入/输出/脚本哈希
  review.json                 自检记录（状态已与 active_issue 统一）
  codex_ruling.md             顾问裁决原文
  superseded_v1/              v1 交付、脚本、报告（只读留档）
runs/issues/S01/screen_rules_v3.json   规则 v3（含 change_log）
```
