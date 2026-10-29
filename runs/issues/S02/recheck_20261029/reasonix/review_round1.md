# Reasonix 独立会话技术审阅：第一轮

记录者：Codex，从Reasonix stdout原样提取最终报告；未改写退回结论。原日志SHA256：74af7aac213520fc78d12d521cf109e7b63097d4e509f4166d9b870f8e1d9630。本轮达到12步工具上限，Reasonix未自行写review.md。

## 1 判定：**RETURN_FOR_REWORK**（仅需 3 项可追溯性修复；数据面未发现需重算的迹象）

- `tools/s03_input_gate.py` 我独立验证**行为正确、fail-closed**，可作为 S03 第一步守卫的候选模块。
- 但 S02 #37 交付的**生产链不可复现**（脚本未提交、manifest 未记录脚本哈希、重算命令失败），3 项具体问题见第 3 节。这三项修好后即可转为 `PASS_TECHNICAL_WITH_LIMITS`。

## 2 我实际读取/执行的证据

**哈希独立复算（全部与声明一致）**
- `tools/s01_rules_check.py` = `134d0fee…4470f` ✓（要求值；`calculation_manifest.json.formula_source.sha256` 同值）
- 13 个 canonical artifact 全部等于 `gate_contract.json` 声明（`all_pool_metrics.csv`=69f82db2…、`company_metric_summary.csv`=1dcd4093…、`financial_normalized.csv.gz`=b18c8079…、`l0_reclassification.csv`=6bc02248…、`coverage_resolution.csv`=bd91619c…、`protected_21.csv`=74753e9a…、`screen_rules_v2.json`=ada501e8… 等）
- `gate_contract.json` = `dfe00fc2…418a` = `s03_input_gate.py::EXPECTED_CONTRACT_SHA256` ✓
- `validation.json.output_sha256` 四项复算全对：`s03_input_gate.py`=4d612466…、`test_s03_input_gate.py`=9e586990…、`gate_tests.json`=0c524451…、`README.md`=4cdc8f06…

**代码通读**
- `tools/s03_input_gate.py`（443 行全文）：契约 ID/版本/状态钉死；13 个 artifact 逐字节校验；`_expected_l0()` 从 12 格状态向量**独立复算 L0** 并要求与 `l0_reclassification.csv` 一致；`coverage_resolution.csv` 开放行必须恰好 join 到 21 家；逐家状态向量与 canonical summary 相等；`terminal_exclusion_allowed_while_open != "NO"` 即报错；W9→`HOLD_FOR_DATA_OR_SCOPE_REVIEW`、W5 无触发→`W5_PROVISIONAL_WATCHLIST`、protected EVALUABLE 且 `NO_SIGNAL/None`→`REVIEW_PENDING_UPSTREAM_COVERAGE`；未知 status/flag/company 抛 `GateError`；CRLF/LF 容忍**仅**限两个冻结 JSON 的两种纯字节形式（混合换行仍拒）。
- `runs/issues/S01/screen_rules_v2.json` 的 `decision_layers` 与 `quality_flags`：L2 明列阻断面为 `status=OK`、无 Q01、无 Q06、无 Q05 未确认；gate 的 `CLEAN_BLOCKING_FLAGS={Q01,Q05,Q06,Q07,Q12}` 额外含 Q07（规则写“L2 仅作辅助证据”）与 Q12（“不进入主筛选”）——**比冻结文本更严，不是放宽**。
- `tools/a03_financial_field_extractor.py`（`git diff 547508d`，178 行）：注3 在物理行边界剥离（避免 `31,144,165,735`）；`summary_cells()` 用 `不适用|[—－–]|--` 保留空位不再压缩列；百分比列纳入列位并以 `is_percent` 区分，取消按量级过滤（>1000% 不再当金额）；`_ytd_column_index` 累计列改第 3 列；`carried_unit`/`row_unit` 防“后页万元回灌前页元”；括号负数与附注号剥离；合并/母公司并列时**表头列序不明即跳过**（保持未知）；成本括号列示转正并保留 raw 符号。
- `tools/s02_calculate.py`（工作区版）：`science_rules_match()` 只接受冻结 S01 v2 的科学内容、仅允许 4 个元数据键；`load_l0_addendum()` 路径钉死、校验版本/base 哈希/**与 repair manifest 冻结 SHA 对照**；`l0_classify.py` 状态向量与 metric 数校验；写盘全部走 `S02 = args.out_dir`。
- `source_pages/` 抽查：`600196_h1_2026_p008.txt` 有“单位：元 币种：人民币”与四列表头；`601238_h1_2026_p009.txt` 表头含“本报告期比上年同期增减(%)”（对应百分比列假设）。

**实跑（只读/仅写入 `reasonix/`，未触碰任何交付文件）**
- 内联调用 `load_gate_inputs` + `protect_existing_route`：`contract_sha=dfe00fc2…`、`companies=1054`、`protected=21`、`l0_global={664,387,3}`；21 家按 `NO_SIGNAL` 路由 → **10→REVIEW_PENDING_UPSTREAM_COVERAGE**、**8→W5_PROVISIONAL_WATCHLIST**、**3→HOLD_FOR_DATA_OR_SCOPE_REVIEW**，全部 `terminal_exclusion_allowed_by_this_gate=False`；非 protected：654 家 EVALUABLE 保持 `NO_SIGNAL`（未淘汰）、379 家 W5 保持 watchlist；`metric_evidence_is_clean`：OK=True、PROVISIONAL/HOLD/Q05=False、未知状态抛错；改写 `final_business_adoption` 的契约副本被拒（*tamper rejected*）；未知 company id 被拒；临时目录已清理。
- **重算 canonical 12,648 格：失败（见第 3 节 P-01/P-02）**。

## 3 具体阻断问题与复现方法

**P-01 生产脚本未入库 + manifest 不记录脚本字节哈希**
- 位置：`git status` → `M tools/s02_calculate.py`（相对 HEAD `e41f61d` 为 **321 增 / 66 删**）、`?? tools/s03_input_gate.py`；`runs/issues/S02/remediation_20261029/s02/calculation_manifest.json` 的 `formula_source` **只记录 `tools/s01_rules_check.py`**，不含 `s02_calculate.py`、`a03_financial_field_extractor.py`、`l0_classify.py` 的字节哈希。
- 影响：`all_pool_metrics.csv`(69f82db2…) 无法从任何提交历史确认由哪个脚本版本产出；S03 消费的冻结产物“来源脚本”不可追溯。
- 复现：`git -C <repo> status --short; git diff --stat HEAD -- tools/s02_calculate.py`

**P-02 重算路径不可复现（P05 失败）**
- 位置：`tools/s02_calculate.py:343`（`--normalized` 直接被 `s01.NORMALIZED` 使用，`.csv.gz` 不解压）→ `s01_rules_check.py:107 load_rows()` 抛 `UnicodeDecodeError: 'utf-8' codec can't decode byte 0x8b`；解压后传入 `:365 verify_normalized_input()` 返回 `ok=False` → `:374` `P05 blocking FAIL` → `:391 return 1`，产物未生成。
- 实测：解压得到的 payload SHA256 = `e08a2731cd6c5c3e31dee0da566fedf132f3f750a7ce4eb3a116edb880b869ab`，不被 `rules_recalculation_inputs.json` 的 `input_fingerprint` 接受。
- 复现（我执行的命令，写入仅限 reasonix）：
  ```
  py -c "import gzip,shutil;shutil.copyfileobj(gzip.open(r'runs/issues/S02/remediation_20261029/s00/financial_normalized.csv.gz','rb'),open(r'runs/issues/S02/recheck_20261029/reasonix/recalc_input/financial_normalized.csv','wb'))"
  py tools/s02_calculate.py --normalized runs/issues/S02/recheck_20261029/reasonix/recalc_input/financial_normalized.csv --rules runs/issues/S02/remediation_20261029/rules_recalculation_inputs.json --out-dir runs/issues/S02/recheck_20261029/reasonix/recalc
  # 观察：P05 FAIL，无 all_pool_metrics.csv
  ```
  （直接传 `.csv.gz` 则在 `load_rows` 处 `UnicodeDecodeError`。）

**P-03 `P06` 的 PASS 不区分 L0 addendum 是否真的应用**
- 位置：`tools/s02_calculate.py:384-389` — `add("P06", …, l0_error is None, {"applied": …})`，而 `load_l0_addendum()` 在输入非 v2 时**正常返回 `applied=False` + note “historical/base input”**（`:213-215`）。即 `applied=False` 也会显示 PASS。
- 影响：S02 自检断言偏弱（对 S03 的直接风险由 gate 侧 `l0_reclassification.csv` 哈希 + L0 独立复算兜住，故非数据污染）。
- 复现：以 S00 基线输入运行时看 P06 明细中 `applied=false` 仍 PASS。

**未发现的问题（明确写无）**：21 家保护路由、10 家 EVALUABLE 不因 `NO_SIGNAL` 终结、387 家 W5 无触发仍观察、3 家 W9 待核、PROVISIONAL/HOLD 不进干净维度、禁止为家数调阈值（664/387/3、6211/4303/267 全部由 canonical 产物实算复现）——**门禁逻辑无阻断缺陷**。

## 4 必须保持的限制

1. 本次为**技术审阅**：不含业务结论、盈利归因、投资建议、候选名单或最终名单验收。
2. 未做原始 PDF 财务字段的逐份独立核验：360 份 PDF 哈希是作者复验，`source_pages/` 我只抽读了 4 个文本页，**不得表述为逐份审计**；19 条来源页与 `source_page_checks.json` 的物理页对应关系未逐条复核。
3. `contract`/`validation` 均为作者 **SELF_CHECK**（`review_nature=SELF_CHECK`，`current_implementation_gate_verified=false`，`consumer_verified=false`）；我这次是独立会话审阅，但**不是第三方审计身份**，也未运行作者的 `test_s03_input_gate.py`（其 `tempfile.TemporaryDirectory(dir=self.root)` 会在仓库内建临时目录，为守“只读”约束我改用等价的内联验证）。
4. gate 的 `CLEAN_BLOCKING_FLAGS` 比冻结 L2 文本更严（多 Q07/Q12），必须**在文档中注明为收紧方向**，S04/S05 若要按冻结文本口径使用需重新声明，不得反向放宽。
5. `a03` 的三表取值 `spans=(1,2,3,4,5)` 已不再受 `use_merge` 约束（原非合并表只取同行），靠 `BLANK_IN_STATEMENT` 与 `_ytd_column_index` 硬编码 +1 列兜底；列版式不同时倾向**退化为缺失而非错值**——这是可接受但仍需在受限范围内观察的精度风险，不能宣称字段已全池确认。
6. `KNOWN_JSON_EOL_EQUIVALENTS` 的存在说明换行符会影响字节哈希；后续任何 CRLF 转换都可能让 gate 拒绝合法文件（fail-closed，但会阻塞 S03）。
7. 本轮我在允许目录内新增了 `runs/issues/S02/recheck_20261029/reasonix/recalc_input/financial_normalized.csv`（重算输入副本）；`recalc/` 未生成。`review.md` **未写入**（步骤用尽），需下一轮补写或由你决定是否放弃该文件。

## 5 边界声明

这**不等于**原始 PDF 财务字段或业务证据的第三方完整审计；`RETURN_FOR_REWORK` 的修复范围仅限 P-01/P-02/P-03 的可追溯性与复现链，修复后仍须保持上述全部限制。**S03 实际执行时必须调用 `tools/s03_input_gate.py::load_gate_inputs` 并在接受任何 L0/L1 路由前校验契约与全部 canonical 哈希**——本次仅证明“守卫存在且我独立跑通其保护行为”，未证明 S03 已实际消费它。

**需要你决定**：是否 (a) 让作者完成 P-01/P-02/P-03 后再进 S03（我的建议），还是 (b) 接受“gate fail-closed + 哈希钉死已覆盖”的论证，带限制进入 S03 并在 S03 卡内登记复现缺口。