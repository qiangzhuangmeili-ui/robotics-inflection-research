# S00 勘误 V5 交接说明（自检 V7，第七轮返工后）

> 版本：`ERRATA_V5`，自检 `V7`，39/39 PASS。
> 性质：**SELF_CHECK**。自检通过 ≠ 独立验收通过。
> 上一版 V4 保留在 `runs/issues/S00/errata_20261111_v4/`，未删除。

## 1. 这一版是什么

V5 换掉了「期间相等即闭合」这个错判据，改成「证据覆盖范围 ⊇ 该行断言必需范围」。
第六轮返工把期间参数改成显式三态、极性改成三分；第七轮返工进一步修掉三处实现缺陷：

- **必需范围改为并集**：期间要求 ∪ 取值来源要求。V6 在非自身期间分支直接返回，把
  `QUARTERLY_TABLE_PROVENANCE` / `PARENT_COMPATIBILITY` 覆盖掉了。
- **极性重写**：识别勾选符号的实际取值、否定只绑定最近的原因、肯定与否定冲突单列、
  「事件已确认」与「影响仅限特定项目」分开记录、纯标签行不判极性。
- **父输入兼容性重做**：撤销「同 version_used 即兼容」「任一父键在采用审计即兼容」
  「空值相等即一致」三条捷径；Q1 按单个累计父输入处理，不套两期相减。

核心待处置 **8,294**（重述差异）/ 全表核心未闭合 **9,098**、含补充列 **10,603**。

## 2. 数字（均与台账一致，可复算）

| 项 | 值 |
|---|---|
| 重述差异总数 | 17,009 |
| 自身期间 / 非自身期间 | 15,769 / 1,240 |
| 非自身期间处置 | **1,239 待核 + 1 条裁决解除**（大豪科技） |
| 已解除（`RESOLVED_SCOPE_COVERED`） | 8,714 |
| 待核 `PENDING_SCOPE_LIMITED_METHOD` | 6,373 |
| 待核 `PENDING_PARENT_COMPATIBILITY` | **1,277**（跨文档累计差分重开） |
| 待核 `PENDING_WEAK_ASSUMPTION` | 515 |
| 待核 `PENDING_SOURCE_PROVENANCE` | 47 |
| 待核 `PENDING_CAUSE_UNCOVERED` | 43 |
| 未核文档 `UNRESOLVED_DOC_NEVER_VERIFIED` | 26 |
| 事件已确认、来源未核 | 8 |
| 证据与 B 相反 `UNRESOLVED_EVIDENCE_MISMATCH` | 4 |
| 确认无据 `PENDING_CONFIRMED_UNSUPPORTED` | 1 |
| 裁决解除 | 1 |
| 父输入兼容性 | YES **4** / NO **3,675** / NA 13,330 |

全池（1,054 家）：`HOLD_PENDING_ERRATA` **44**、`R2_MAY_CHANGE` **231**、`R1_NO_LINK` **378**、
`NOT_AFFECTED` **320**、`STILL_PASSES_WITHOUT` **81**。
受限表 **407 行 / 401 个唯一差异 ID**；重述差异按「方法 × 覆盖签名 × 极性 × 来源 × 自身期间」分 **87 组**。

**43 / 207 / 445 均未冻结**，本版不锁定任何名单数字。

## 3. 文件

| 文件 | 说明 |
|---|---|
| `evidence_scope.py` | 判据唯一实现（`analyse` / `period_scope` / `source_scope` / `required_scope` / `judge`） |
| `meta_classes.py` | 元数据字段影响分类唯一来源（自检与生产共用，防止台账自报分类绕过） |
| `l2_core.py` | 依赖引擎（按 B 实际 `status` 分支展开父键） |
| `build_errata_v5.py` | 台账构建，含 `parent_compatible()` |
| `check_l2_v5.py` | 全池影响判定，含稳定 `dispute_id` 与逐表哈希 |
| `sampling_v5.py` | 分层抽验（37 条 / 20 类，原件物理页回读） |
| `verify_v5.py` | 39 项自检 |
| `meta_diff.csv` | 17,728 行；重述差异含 `is_own_period` / `parent_compatible` / `polarity` / `scope_*` |
| `extra_meta_diff.csv` | 1,505 格补充元数据（19 列），含 `content_review` / `content_review_ref` |
| `dispute_ledger.csv` | 10,603 条唯一差异 ID（含逐条源表哈希） |
| `restricted_claims.csv` | 407 行受限声明，逐表差异 ID + 逐表哈希 |
| `l2_dependency_check.csv` | 1,054 家全池判定 |
| `sampling_v5.csv` / `.json` | 抽验明细与汇总（含 `locate_status`、两父输入核证结论） |
| `summary.json` / `review.json` / `manifest.json` | 汇总、自检结论、文件清单 |
| `rulings_resolved.json` | 裁决解除清单（含裁决文件路径 + sha256 + 冲突解释） |
| `report_to_codex_round8.md` | 本轮汇报（含 6 个待裁定问题） |

## 4. 能复现的故障注入

| 对象 | 结果 |
|---|---|
| V1 台账 | C13 **6** / C14 **11,936** / C17 **12,076**（必须 FAIL） |
| V4 台账（旧标签映射后） | C26 **7,714** / C14 **6,602** / 受限方法自身期间 **5,270** |
| V5 自身 | C13 / C14 / C17 / C26 均 **0** |

5,270 与 Codex 复算一致。

## 5. 边界与未做

- **未回读全部 PDF**：抽验 37 条，覆盖 1,007 份核验文档中的 20 份。
- **9,927 条 `NOTE_TRACE_NA` 已解决项未做方法适用性复审**（涉及 630 份文档，第 4 步处理）。
- **`NOTE_RETAINED_ERRATA_ZERO` 642 条**（自身 563 / 非自身 79，涉及 42 份文档）未逐条回读原注。
- **1,505 格补充元数据**仅登记字段级核验要求，未逐项核完。
- **未覆盖**锚定期回退与上游准入的间接依赖。
- **第 4 步批量核证、第 5 步重算分层未做**。
- **不给出最终未闭合数**；本文件不构成验收结论。

## 6. 表述纪律（第七轮已撤回的三句）

1. ~~「第六轮裁决第 1–3 步已完成」~~ → 第 1 步（修方法）在本轮按第七轮裁决继续返工；第 2 步抽验已补三类样本；第 3 步自检已加牙但仍有同源局限。
2. ~~「原件中不存在该证据」~~ → 改为「**未定位到**」：全文检索未命中不等于原件中没有。
3. ~~「改台账不改代码必被抓住」~~ → 改为「C26/C29 的重算独立于台账自报字段，但与生产共用同一套判据函数，属同源重算，不能替代独立方法验证」。
