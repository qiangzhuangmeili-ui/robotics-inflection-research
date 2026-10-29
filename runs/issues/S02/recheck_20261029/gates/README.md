# S02 → S03 门槛契约

## Canonical 输入

契约绑定正式修复版 S02：`runs/issues/S02/remediation_20261029/s02/all_pool_metrics.csv`、`company_metric_summary.csv`、`calculation_manifest.json`，以及 `l0/repaired/l0_reclassification.csv` 和其自检记录。清单登记的输入版本为 `S00_TARGETED_REEXTRACTION_20261029`。输入、指标、汇总、L0、冻结 S01 规则和 21 家保护队列的 SHA-256 均写入契约，由 `tools/s03_input_gate.py` 逐项校验。契约不把其他独立重算目录作为权威输入。

## 技术结论与限制

可按冻结 S01 L1 做带状态标签的技术宽筛和观察路由。门槛模块只校验输入并保护路由，不计算指标或信号，也不生成 S03 名单。S03 仍须在第一步实际调用守卫；本次没有证明 S03 已调用，`current_implementation_gate_verified` 仍是 false。

## 21 家保护队列

`protected_21.csv` 从覆盖待处理清单、正式 S02 汇总和 L0 repaired 路由合并生成。10 家 EVALUABLE 保留冻结 L1；原始 L1 为 NO_SIGNAL 时转 `REVIEW_PENDING_UPSTREAM_COVERAGE`。8 家 W5 无触发仍留观察名单。3 家 W9 等待数据或范围复核。每家公司 12 格状态向量必须完整。开放队列在有明确解决或复核接受记录前不得终结淘汰；不要求全池未知清零。

## 状态保护

PROVISIONAL 4,303 格可按冻结 S01 带标记进入 L1，但不得混入普通 OK 或计入 L2 干净维度。HOLD 267 格不作改善、恶化或无信号证据。缺失、不可比、基数无意义等状态保持原值语义，不替换为零。

守卫的 `metric_evidence_is_clean` 仅检查单格 readiness。Q05 只有在调用方明确传入 S01 `confirm_low_base` 产生的 `low_base_confirmed=True` 后才可通过；此函数不推导确认结果。它不取代 `signals_of`、`confirm_low_base` 或 `layers`，也不得用于否决 SG06 等 S01 允许的绝对额备选路径。本守卫不判断 L2 候选。

## SELF_CHECK 边界

父代理参与了上游修复。本产物与门槛模块测试属于技术 SELF_CHECK，不是独立第三方原始 PDF 或源数据审计。最终业务采用仍须遵循独立复核要求。

## 输入守卫测试

运行 `python -m unittest discover -s runs/issues/S02/recheck_20261029/gates -p test_s03_input_gate.py -v` 可复跑纯函数门槛测试。只对冻结的 S01 规则 JSON 与 acceptance JSON 接受已核实的全 LF/全 CRLF 等价字节形式；混合换行、内容改动及其他文件的哈希变化均失败关闭。当前测试不证明 S03 已调用守卫。
