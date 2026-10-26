# P00 交接：冻结资料范围、候选名单和研究截止日

- **issue**：#11 / P00，plan_version `20261026_collection_first_v2`
- **执行者**：WorkBuddy AI（执行与自检同一主体，见 review.json 的 SELF_CHECK 标注）
- **起止时间**：2026-10-26T12:31:29+08:00 领取；2026-10-26T12:3x 完成（本文件提交时间即完成时间）
- **输入基线 commit**：`faf56c53c3c3305c9cddfcec10dd4e805de59b36`

## 一、本卡范围与依赖

- **范围**：只制定本轮采集合同——名单、截止日、报告槽、字段清单、状态口径、容量规则。**未发起任何全池下载请求**，未筛公司，未做业务判断。
- **依赖**：无。P00 是新的第一张执行卡，无需前置 review.json。
- **输入**（全部只读，未修改）：`PROJECT_STATE.json`、`data/company_master.csv`、`data/intake_company_queue.csv`、`data/intake_batch_index.csv`、`data/document_registry.csv`。

## 二、实际交付文件

| 路径 | 作用 | SHA-256（前 16 位） |
|---|---|---|
| `runs/issues/P00/universe_fingerprint.json` | 候选池冻结指纹 | `8c60166c2105ea05` |
| `runs/issues/P00/collection_scope.json` | 采集范围合同 | `f5e31dc053b9d7a0` |
| `runs/issues/P00/coverage_acceptance_rules.json` | 覆盖与验收规则 | `7b8fadc770b09cae` |
| `runs/issues/P00/manifest.json` | 文件清单与输入版本 | — |
| `runs/issues/P00/review.json` | 自检记录 | — |
| `tools/p00_freeze_scope.py` | 可复算生成上述三份交付（只读、不联网） | `a68441ead50a5295` |

**冻结指纹**：`canonical_sha256 = e093c54dfaf60ef883f2b353667eb497a978d5d8cf00954457af674f95527f5e`
**仅证券ID集**：`07d4394ae21c8860a22708c017358800fa1f7fea1d5b524cf650fc632564132a`

复算方式：`python tools/p00_freeze_scope.py`。已用独立第二实现重算两个哈希，结果一致。

## 三、数量对账

**本卡是规则卡，不执行采集**，因此槽位级数量为设计如此，不是缺口：

| 口径 | 数量 | 说明 |
|---|---:|---|
| 候选证券 | 1054 | 与 `company_master.csv` 一致，security_id 与 stock_code 均唯一 |
| 已处理公司 | 0 | 本卡不做采集 |
| 已取得报告槽 | 0 | 本卡不做采集 |
| 未尝试槽位 | 1054 × 6 = 6324（上界） | 全部 `NOT_TRIED`，**不得计入完成** |
| 不适用 | 0 | 上市日期全部 UNKNOWN，无法判定，故不填不适用 |
| 未披露 | 0 | 同上，未做逐家披露检索 |
| 失败 | 0 | 未发起请求，无失败可记 |

**已有原文现状（只统计，不改动）**：登记 100 条 / 覆盖 72 家（覆盖率 6.83%）；`VERIFIED` 仅 14 条，`UPLOADED_UNVERIFIED` 73 条。已有原文**不构成资料轮完成**。

## 四、口径冲突与处理

| 冲突 | 处理 | 状态 |
|---|---|---|
| `PROJECT_STATE.knowledge_as_of=2026-10-25` vs `company_master.research_as_of=2026-10-24` | 冻结 `knowledge_as_of=2026-10-25` 为研究截止日；`research_as_of` 是行级研究时点标记，保留原值不回填 | RESOLVED_BY_DEFINITION |
| `tools/validate_plan.py` 与 `packages/*/TASK.md` 仍写死 `2026-10-24` | **未改动**（属旧体系遗留断言，改它等于动他人输入）；登记为后续待办 | LOGGED_NOT_CHANGED |

**新增规则（本卡确立）**：披露日晚于 `2026-10-25` 的文件记为 `AFTER_CUTOFF_DISCLOSED`，只作增量候选，不参与本轮筛选。这是为了满足"不因今天采集就混入截止日之后公告"。

## 五、限制与断点

1. **`listing_date` 1054/1054 全为 UNKNOWN**。这直接导致"上市前/不适用"判不了。本卡只冻结判定表（5 条规则 + 招股书替代规则），**未伪造任何上市日期**。槽位在取得可核上市日前一律保持 `NOT_TRIED`。解锁责任在 P02/P03（取交易所上市日期后回填）。
2. **容量未实测**。只定义估算公式（各槽尝试数 × 单位文件字节中位数），标 `UNMEASURED`；实测留给 P07 十家校准。未给出任何 GB 数字，避免把经验带宽当事实。
3. **本卡未验证任何数据源连通性**。那是 P03 的范围。
4. **北交所 62 家、61 家上市前公司**的实体映射与披露平台差异（股转 vs 北交所）只登记需求，映射表由 P01/P02 产出。

## 六、验收结论与放行

- 三条验收标准逐条对照见 `review.json`，结论 **SELF_CHECK_PASS**。
- **允许放行**：P01（#12）、P03（#14）、P04（#15）——三张均为技术/规格卡，依赖 P00 的冻结口径。
- **不放行**：任何业务结论采用、任何指标筛选（须等 A04）。
- **必须说明**：本次自检由执行者本人完成，**不是独立审计**。若需独立复核，另派复核卡，不改变本卡已产出的文件。

## 七、下一步建议

1. 按依赖顺序可并行开 P01（文件身份与去重）、P03（连接与熔断）、P04（财务字段口径）三张。
2. 若要先把 `listing_date` 缺口补上，可在 P03 内附一个交易所上市日期回填子步骤，避免 P07 校准时才发现不适用判不了。
3. `tools/validate_plan.py` 的硬编码截止日建议在 P01 一并改为读取 `runs/issues/P00/collection_scope.json` 的 `time_axis.knowledge_as_of`，否则它会一直报假失败。
