# Reasonix 独立会话技术审阅：复审

记录者：Codex，从stdout原样提取；Reasonix因6轮工具上限未自行写review.md。

## 复审结论（限范围 6 轮，已用尽工具步数）

### P-01 生产脚本入库 + 来源哈希 —— 已修复（我独立复算）
- `git log` 最新提交 `d72d4d5` 存在；`git status` 中已无 `M tools/s02_calculate.py` / `?? tools/s03_input_gate.py`，两脚本均已入库。
- 我用 `git cat-file blob d72d4d5:<path>` 取提交字节独立算 SHA256 并与工作区比对：
  - `tools/s02_calculate.py` = `13a6eb75…a8cd4` **字节完全相同**
  - `tools/s03_input_gate.py` = `a135fddd…2df12` **完全相同**
  - `tools/l0_classify.py` = `b500b3a1…37d3` **完全相同**
  - `tools/a03_financial_field_extractor.py` = `11137167…45d7` **完全相同**
  - `tools/s01_rules_check.py` 工作区 `134d0fee…4470f` vs blob `88a2333c…a0e9f`，**仅 `\r\n`↔`\n` 替换后完全一致**（`exact_bytes=false, lf_only_equivalent=true`），与作者声明一致；原运行 SHA 仍是 `134d0fee…`，未被追改。
- 历史 canonical manifest（`remediation_20261029/s02/calculation_manifest.json`）我读出键表**不含 `execution_sources`**（其 `formula_source` 仍只记 `s01_rules_check.py`）→ canonical 未被追溯修改；来源链改由新 execution manifest 承载，`calculator / formula_engine / l0_classifier / l0_rules / upstream_a03` 五项齐备。

### P-02 重算不可复现 —— 已修复（我本轮同命令实跑）
在 `reasonix/round2/` 内、未触碰 canonical：
- **CSV 副本模式**（我自己从 `s00/financial_normalized.csv.gz` 解出的 `round2/recalc_input/financial_normalized.csv`）：rc=0，`PASS P05 实际加载的标准输入 CSV 内容 SHA 与来源匹配`（上轮此处 FAIL），输出 `all_pool_metrics.csv`=`69f82db2…258425`、`company_metric_summary.csv`=`1dcd4093…3bf95`，**与 canonical 逐字节相等**；23/23 检查、blocking_fail=0；格数 12648、12 指标、1054 家、OK 6211 / PROVISIONAL 4303 / HOLD 267 均与 canonical 一致。
- **直接 `.csv.gz` 入口**（`--normalized ...s00/financial_normalized.csv.gz --out-dir round2/recalc_gzip`）：rc=0，两个 CSV **同样逐字节相等**，上轮 `UnicodeDecodeError` 不再出现。
- 两种模式的 manifest 均记录：源压缩件 `b18c8079…0824`、`normalization_manifest.json`、`company_master.csv`，`l0_distribution` = 664/387/3，`execution_sources.l0_rules.applied=true`。

### P-03 P06/L0 —— 代码层已改为 fail-closed，我实跑确认 applied=true（负面路径未由我本轮实跑）
- 只读源码 `tools/s02_calculate.py:445/462-466`：`l0_required = input_identity["ok"] and l0_addendum_required(...)`；`p06_status = "NOT_APPLICABLE" if not l0_required else ("PASS" if p06_applied else "FAIL")`，断言 `not l0_required or p06_applied` → **v2 必需但未应用即 FAIL（阻断）**，v1 才 NOT_APPLICABLE。上轮“applied=False 也 PASS”的弱点在代码上已消除。
- 我的两次实跑 P06 均为 `PASS`，manifest `l0_rules.applied=true`、`l0_classifier.executed=true`。
- **未执行**：v1 输入走 NOT_APPLICABLE、以及“v2 标记但 L0 applied=false”的故障注入复现（脚本已采集候选 rules 文件，但输出被截断，我未见其结果，故不声称已验证；作者 `integration/test_results.json` 的 11 组含 loader applied=false 属作者 SELF_CHECK）。

### Q05 辅助判断 —— 本轮未独立验证（不构成阻断）
`tools/*.py` 中 `low_base_confirmed` 的命中清单已由脚本采集，但输出被截断，我**未读到** helper 签名与 False/True/未知类型的实际行为。故 Q05 仅保留上轮结论（Q05 不进入 clean 维度这条由 gate 的 `CLEAN_BLOCKING_FLAGS` 覆盖），**本轮不作独立确认**。

### 执行边界
- 只读生产代码；写盘仅限 `runs/issues/S02/recheck_20261029/reasonix/round2/`（`recalc_round2.py`、`round2b.py`、`recalc_round2.json`、`round2b.json`、`recalc_input/`、`recalc_copy/`、`recalc_gzip/`、`neg_tamper/`）。未覆盖 canonical，未改规则/输入/历史交付/控制文件/密钥，未建子代理、未发外部消息。
- **`round2/review.md` 未写**（步数用尽）；上述两份 JSON 已是可追溯的原始复算记录。
- 未做原始 PDF/财务字段独立审计；19 条来源页与 `source_page_checks.json` 的物理页对应未逐条复核；S03 实际消费仍为 false。
- 远端 main 未推送（推送被审批拒绝，本轮不要求绕过）；`recheck_20261029/` 下多份新证据文件仍是未跟踪状态（`reproduction_manifest.json` 等 `??`），只有 `d72d4d5` 内的代码为已提交内容。
- 一处需要作者说明的小瑕疵：`reproduction_manifest.json` 的 `csv_copy` run 把输入指向**我上轮的目录** `reasonix/recalc_input/financial_normalized.csv`，而 `gzip` run 才从归档压缩件重派生。payload SHA 已登记且 P05 PASS，故不阻断；但更干净的写法应让两种模式都从 `s00/financial_normalized.csv.gz` 自行解出。

**判定**：P-01/P-02 已可独立复现，P-03 在代码与运行记录层已 fail-closed；本地技术修复可交付，限制见上。

```json
{"verdict":"PASS_TECHNICAL_WITH_LIMITS","p01":"PASS：tools/s02_calculate.py=13a6eb75…a8cd4、s03_input_gate.py=a135fddd…2df12、l0_classify.py=b500b3a1…37d3、a03=11137167…45d7 工作区与 d72d4d5 blob 逐字节相同；s01_rules_check.py 工作区134d0fee…4470f vs blob88a2333c…a0e9f 仅CRLF/LF差异(纯换行等价)，原运行SHA未追改；新execution manifest 记录 calculator/formula_engine/L0/upstream_a03 哈希，canonical manifest 无 execution_sources 未被追溯修改","p02":"PASS：本轮自行从 s00/financial_normalized.csv.gz 解出 CSV 副本并以 --out-dir round2/recalc_copy 实跑 rc=0、P05 PASS、all_pool_metrics.csv=69f82db2…258425 与 company_metric_summary.csv=1dcd4093…3bf95 均与canonical逐字节相等；直接 .csv.gz 入口 --out-dir round2/recalc_gzip 同样 rc=0 且两CSV逐字节相等；23/23检查、blocking_fail=0、12648格/1054家/6211-4303-267一致；未写canonical","p03":"PASS_WITH_LIMIT：源码 s02_calculate.py:445/462-466 已改为 l0_required 时 applied 必须为真否则FAIL、v1才NOT_APPLICABLE；我两次实跑 P06=PASS 且 manifest l0_rules.applied=true、l0_classifier.executed=true；但 v1→NOT_APPLICABLE 与 v2未应用→阻断 两条负面路径本轮未由我实跑复现（仅代码阅读+作者 test_results.json SELF_CHECK）","q05":"UNVERIFIED_THIS_ROUND：low_base_confirmed helper 所在文件已定位但输出被截断，未读到签名与 False/True/未知类型的实际行为，不作独立确认；不构成阻断，闸门侧 Q05 仍由 CLEAN_BLOCKING_FLAGS 覆盖","s03_actual_consumer_verified":false,"independent_financial_source_audit":false,"remaining_blockers":[]}
```