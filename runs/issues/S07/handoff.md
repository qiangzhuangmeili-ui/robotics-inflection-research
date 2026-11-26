# S07 / #42 执行交接（SELF_CHECK）

完成时间：2026-11-26T13:30:00+08:00（北京时间）。计划版本 `20261026_collection_first_v2`。执行方 CodeBuddy，统筹方 Antigravity，独立复核指派 Codex。

## 完成内容

- 冻结确定性分层抽样 **62 家**（50–65 家区间内），覆盖 6 个分层、38 个子槽；无随机数，排序键固定。
- 从 `s00_v10.csv.gz` 独立重算 12 项指标 **744 格**，状态一致 744、数值一致 744，最大绝对差 4.977e-11。
- S03 L1 重放：57 家一致、5 家底稿/截止日覆盖、0 家不一致。
- S04 边界：62 家内部一致；绝对额通道与低基数确认逐家回查通过。
- S05：RH 阈值 21 家一致；20 格越界值确认越界且未改路由；RH06 待核 7 家保持。
- S06：缺失观察 7 类 379 家、早期储备 4 桶 54 家；五项计数逐家一致。
- 反向漏筛：强线索未进主线 36 家，样本判定均为规则性排除/待核，计算漏筛 0 家。

## 交付文件（runs/issues/S07/）

- `step_s07_build.py`
- `step_s07_verify.py`
- `screen_audit_sample.csv`
- `screen_audit_findings.md`
- `screen_audit_review.json`
- `manifest.json`
- `handoff.md`
- `review.json`

## 复现方式

在干净提交树内，以固定时间戳顺序运行：

```
S07_FIXED_NOW=2026-11-26T13:30:00+08:00 py runs/issues/S07/step_s07_build.py
S07_FIXED_NOW=2026-11-26T13:30:00+08:00 py runs/issues/S07/step_s07_verify.py
```

构建脚本输出全部 CSV/MD/JSON；自检脚本校验输入哈希、主键守恒、分层覆盖、复算一致、交付哈希与清单根摘要，并写 `manifest.json` 与 `review.json`。

## 未做 / 限制

- 未重研全池、未逐家深读公告、未调整任何阈值、未手工加回公司。
- S04 复核版 `tight_pass`（278）不在 Git 跟踪树内，445→278 的逐家映射无法在干净树内完全重放；该可追溯性缺口登记为 F10，结转 S08。
- 20 格越界值的处置动作在冻结规则中未定义（F11），只登记不改路由。
- 本卡为 `SELF_CHECK`，不释放 S08；须 Codex 独立复核后再登记验收。

## 断点与下一步

1. Codex 按 `screen_audit_review.json` 的 F01–F13 做独立复核，重点核 F10（S04→S05 池口径）与 F11（越界处置）。
2. 复核通过后登记 S07 验收；S08 放行仍须单独授权。
3. 建议 S08 开工前补齐 S04 复核版 `tight_pass`/`tight_decision_log` 的 Git 跟踪，或在 S08 输入合同中显式冻结 278 的逐家映射。

