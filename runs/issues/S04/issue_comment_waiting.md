## S04 登记等待原因（2026-11-11）

按 Codex 裁决顺序「登记 S04 等待原因 → 领 S00 勘误卡 → 差异闭合 → 独立补充验收 → 验下游影响 → 完成 S04 第二轮复核」，本卡暂不申请第二轮复核，等待原因如下。

### 阻塞项

S00 勘误（#53）发现 S04 的 445 家名单中有 **2 家**的 L2 通过建立在无依据的数据变更上：

| 公司 | 争议 | 具体字段 |
|---|---|---|
| 禾川科技 SH:688320 | A 的 `EXTRACTED_XCHECK_MISMATCH`（三表勾稽不符）、`DERIVED_HOLD_UPSTREAM` 在 B 中被解除为正常态，无依据 | REV.YTD、REV.SQ、GROSSMARGIN.PCT @20260630 |
| 联赢激光 SH:688518 | 同上；另有经营现金流符号翻转 A `+1.20 亿` vs B `-4,363 万` | OCF.YTD、OCF.SQ、OCF_TO_NP @20260630 |

其余 443 家经 L2 依赖链逐家核对，即使剔除全部争议数据仍由已验收证据支持至少两个合格维度，结论不变。

### 本次未做的调整

- **未手工修改 445 家名单**（不因勘误结论逐家打补丁）
- 未改任何阈值
- 未回读 PDF

### 恢复条件

1. #53 的 5,700 条未解决项完成原文核验并取得独立补充验收
2. 上述 2 家的告警解除依据确认或推翻
3. 规则 v3 `universe.source` 的残留指向 A 已修正并留记录

三条闭合后申请 S04 第二轮外部复核。**S05 保持 `WAITING_DEPENDENCIES`，不放行。**

### 参考

- 勘误台账：`runs/issues/S00/errata_20261111/`
- 替代登记：`runs/issues/S00/supersession.json`
- Codex 裁决：`runs/issues/S04/codex_ruling_s00_split.md`
- 445 家判定：`runs/issues/S00/errata_20261111/l2_dependency_check.csv`
