# S07 / #42 执行交接（SELF_CHECK）

完成时间：2026-11-26T13:55:00+08:00（北京时间）。计划版本 `20261026_collection_first_v2`。执行方 CodeBuddy，统筹方 Antigravity，独立复核指派 Codex。
返修轮次：`R2`；返修依据：`runs/issues/S07/codex_review_s07_r1_20261126.md`。

## 完成内容

- 冻结确定性分层抽样 **62 家**（50–65 家区间内），覆盖 6 个分层、38 个子槽；无随机数，排序键固定。
- 从 `s00_v10.csv.gz` 独立重算 12 项指标 **744 格**，状态一致 744、数值一致 744，最大绝对差 4.977e-11。
- S03 L1 重放：57 家规则重推一致、5 家冻结覆盖（逐家说明）、0 家不一致。
- S04 边界：62 家内部一致；绝对额通道 11 条、低基数确认 6 条逐条从 `s00_v10` 复算，全部通过。
- S05：RH 阈值 21 家一致；20 格越界值确认越界且未改路由；RH06 待核 7 家保持。
- S06：缺失观察 7 类 379 家、早期储备 4 桶 54 家；五项计数逐家一致，缺失未填 0。
- 反向漏筛：抽样 5 家逐家独立重推，计算漏筛 0 家；全池 36 家仅做路由分布汇总，未逐一重推。
- 定级：`systemic_blocker=False`、`requires_s00_s01_rollback=False`，由 10 项异常清单动态推导（计数全部为 0）。

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

**推荐方式：指定提交的干净 Git checkout / worktree。** 例如：

```
git worktree add --detach /tmp/s07_replay <commit_sha>
cd /tmp/s07_replay
S07_FIXED_NOW=2026-11-26T13:55:00+08:00 py runs/issues/S07/step_s07_build.py
S07_FIXED_NOW=2026-11-26T13:55:00+08:00 py runs/issues/S07/step_s07_verify.py
```

此时 C13 在存在 `.git` 的情况下强制执行 `git ls-files --error-unmatch`，验证 29 份输入 100% 位于 Git 跟踪树内。

**备选方式：`git archive` 纯归档目录（无 `.git`）。** 归档须包含本提交的 `manifest.json`。此时 C13 检测到无 `.git`，改为核对全部输入文件存在、且与 `manifest.json` / `release_20261126.json` 冻结输入清单及 SHA-256 逐一匹配，并标注 `git_index_check=SKIPPED_NO_GIT_DIR_VERIFIED_BY_MANIFEST`，不会因缺少 Git 索引而崩溃。该模式下 22 项自检同样全部 PASS；除 C13 的模式标注（及其导致的 `review.json` 与清单根摘要差异）外，其余 6 份交付逐字节一致。

**逐字节一致性**：推荐模式下连续两次 `build + verify` 的 8 份文件（`screen_audit_sample.csv`、`screen_audit_findings.md`、`screen_audit_review.json`、`handoff.md`、`review.json`、`manifest.json`、`step_s07_build.py`、`step_s07_verify.py`）SHA-256 完全一致。

构建脚本输出全部 CSV/MD/JSON；自检脚本校验输入哈希、主键守恒、分层覆盖、复算一致、绝对额/低基数逐条证据、反向漏筛重推、交付哈希与清单根摘要，并写 `manifest.json` 与 `review.json`。

## 未做 / 限制

- 未重研全池、未逐家深读公告、未调整任何阈值、未手工加回公司。
- S04 复核版 `tight_pass`（278）不在 Git 跟踪树内，445→278 的逐家映射无法在干净树内完全重放；该可追溯性缺口登记为 F10，结转 S08。
- 20 格越界值的处置动作在冻结规则中未定义（F11），只登记不改路由。
- 本卡为 `SELF_CHECK`，不释放 S08；须 Codex 独立复核后再登记验收。

## 断点与下一步

1. Codex 按 `screen_audit_review.json` 的 F01–F13 做独立复核，重点核 F10（S04→S05 池口径）与 F11（越界处置）。
2. 复核通过后登记 S07 验收；S08 放行仍须单独授权。
3. 建议 S08 开工前补齐 S04 复核版 `tight_pass`/`tight_decision_log` 的 Git 跟踪，或在 S08 输入合同中显式冻结 278 的逐家映射。

