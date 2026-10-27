# M00_11 交接：基础资料自动采集（固定 54 家，不做业务精读）

- **issue**：#29 / M00_11，plan_version `20261026_collection_first_v2`
- **执行者/自检者**：WorkBuddy AI（执行与自检同一主体，`review_nature=SELF_CHECK`，不冒充独立审计）
- **起止**：2026-10-27T03:53:31Z → 2026-10-27T04:04:38Z（耗时 667.3 秒）
- **参数源**：`runs/issues/P07/collection_config_v1.json`（P07 派生配置，未改 P05 冻结参数）
- **名单**：`intake_batches/M00_11/assignment.csv`，sha256 `65354e337dfc641650358e787793d4d5e84cb14ae73bcacd69f368ed2dfe67ad`
- **本卡不做**：财务字段精读、客户/订单归因、行业判断、估值、改名单、改原始输入

## 一、一句话结论

54 家 × 7 槽 = **378 个槽位全部有状态**：339 个 `COLLECTED_IDENTITY_VERIFIED`、0 个 `COLLECTED_PENDING_IDENTITY`、39 个 `NOT_TRIED`、0 个 `NOT_DISCLOSED_BY_ISSUER`、0 个源失败/访问受限；合计取得 **339** 槽，累计 717.8 MB 落本机 D 盘。

## 二、名单构成

| 维度 | 分布 |
|---|---|
| 交易所 | SH 0 / SZ 0 / BJ 54 |
| 板块 | 北交所 54 |
| 计划槽位 | annual_2023、annual_2024、annual_2025、h1_2024、h1_2025、h1_2026、q1_2026 |

## 三、逐槽覆盖率

| 槽位 | 已取得 | 槽数 | 覆盖率 |
|---|---:|---:|---:|
| annual_2023 | 47 | 54 | 87.0% |
| annual_2024 | 47 | 54 | 87.0% |
| annual_2025 | 49 | 54 | 90.7% |
| h1_2024 | 47 | 54 | 87.0% |
| h1_2025 | 47 | 54 | 87.0% |
| h1_2026 | 53 | 54 | 98.1% |
| q1_2026 | 49 | 54 | 90.7% |

## 四、状态对账

| 状态 | 槽数 |
|---|---:|
| `COLLECTED_IDENTITY_VERIFIED` | 339 |
| `NOT_TRIED` | 39 |
| **合计** | **378** |

### 对账（验收第 3 条）

| 口径 | 槽数 |
|---|---:|
| obtained_verified | 339 |
| obtained_pending_identity | 0 |
| not_disclosed_by_issuer | 0 |
| not_applicable_pre_listing | 0 |
| not_yet_disclosed | 0 |
| failed_source | 0 |
| not_tried | 39 |
| duplicate_or_other | 0 |
| **分桶合计** | **378**（总槽数 378） |
| 其中发出过下载请求 | 334 |
| 其中零 HTTP 复用 | 12 |

## 五、未取得项与自动队列

`automatic_failures.csv` 共 39 行，状态分布：`NOT_TRIED` 39。本批只入自动队列，不向用户逐家追件。

### NOT_TRIED 的缺口形态（7 家）

`listing_date` 仍全 UNKNOWN，按 P00 只能记 NOT_TRIED；下表只是**缺口形态**，供 A00/A01 回填上市日期时对照，不构成“上市前不适用”的断言。

| 证券 | 简称 | 未尝试槽位 | 已取得槽位 |
|---|---|---|---|
| 920096 | 嘉晨智能 | annual_2023、annual_2024、annual_2025、h1_2024、h1_2025、q1_2026 | h1_2026 |
| 920100 | 三协电机 | annual_2023、annual_2024、h1_2024、h1_2025 | annual_2025、h1_2026、q1_2026 |
| 920124 | 南特科技 | annual_2023、annual_2024、h1_2024、h1_2025 | annual_2025、h1_2026、q1_2026 |
| 920211 | 新睿电子 | annual_2023、annual_2024、annual_2025、h1_2024、h1_2025、q1_2026 | h1_2026 |
| 920220 | 朗信电气 | annual_2023、annual_2024、annual_2025、h1_2024、h1_2025、q1_2026 | h1_2026 |
| 920238 | 长鹰硬科 | annual_2023、annual_2024、annual_2025、h1_2024、h1_2025、q1_2026 | h1_2026 |
| 920289 | 华汇智能 | annual_2023、annual_2024、annual_2025、h1_2024、h1_2025、h1_2026、q1_2026 | 无 |


## 六、存储与归档

- 原件根：`sources/collection/originals`（目录联接 → `D:\StockResearchLab\IndustryInflectionLab\robotics_data\collection\originals`）。
- 台账：`runs/collection/checkpoint/*.json` + `runs/collection/collection_index.csv`（COLLECTION_LEDGER_V1，M00 后续批次共用）。
- **Drive 未使用**：本会话无 Google Drive 连接器，`archive_status` 一律不写 VERIFIED；`document_receipts.csv` 只声明本地原件与校验结果。

## 七、已知限制

1. `listing_date` 仍 1054/1054 UNKNOWN：空目录只能记 `NOT_TRIED`，不得判上市前不适用或未披露。
2. 本卡不抽财务字段：`field_coverage.csv` 只区分“旧快照已有 / 原件已取得待 S00 抽取 / 无来源”，不是财务结论。
3. 自检由执行者本人完成，不等于独立审计；业务采用仍需独立复核。
4. P05 故障用例 T07 期望“主体错配不留原件”，与 P07 冻结的 F2/F4 行为（低文本记 PENDING、错配保留 `.pdf.rejected`）不一致，属既有用例过期，本卡未改测试。
5. `tools/validate_plan.py` 仍 106 通过 / 5 失败，全部是 P00 期包索引漂移（68 vs 67、59 vs 58、1056 vs 1054、`D00_B00_ADVANCE_01` 缺 ZIP），与本批采集无关；输出见 `plan_validation.txt`。

## 八、下一步

- 下一张：`M00_02`（issue #20），沿用同一台账与配置，名单另取 `intake_batches/M00_02/assignment.csv`。
- 开跑前不必重复本卡工作：登记表级幂等已进 `tools/p05_collector.py`（`lookup_order[2]`）。
