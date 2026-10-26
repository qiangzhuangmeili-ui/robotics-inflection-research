# P01 交接：统一文件身份、来源登记与去重规则

- **issue**：#12 / P01，plan_version `20261026_collection_first_v2`
- **执行者**：WorkBuddy AI（执行与自检同一主体，见 review.json 的 SELF_CHECK 标注）
- **起止**：2026-10-26T12:56 领取 → 2026-10-26T13:2x 完成
- **输入基线 commit**：`9c9ab7d`（P00 交付后）
- **依赖**：P00（#11），review.json 为 `SELF_CHECK_PASS`，放行范围含 P01

## 一、本卡做了什么、没做什么

**做了**：把「一份文件」拆成三层（逻辑文档 / 内容指纹 / 来源），定义 ID 生成、身份键、版本关系、来源别名、五个独立状态、查重顺序，给出目标表结构和 100 行迁移方案，并用 dry-run 实测跑通。

**没做**（按批准）：没有修改 `data/document_registry.csv`；没有创建 `document_sources.csv`；没有访问 Drive；没有下载任何文件；没有改任何公司研究结论。

## 二、交付文件

| 路径 | 作用 |
|---|---|
| `runs/issues/P01/document_identity_rules.json` | 身份规则 |
| `runs/issues/P01/document_registry_schema.json` | 目标表结构 |
| `runs/issues/P01/registry_migration_plan.md` | 迁移方案 |
| `runs/issues/P01/migration_dryrun.csv` | 100 行逐行 dry-run |
| `runs/issues/P01/migration_dryrun_summary.json` | 分布统计 + 6 项自动校验 |
| `tools/p01_registry_dryrun.py` | 只读生成器 |
| `tools/validate_plan.py` | 改动：截止日改为读 P00 冻结值 |

## 三、五个实测发现

1. **`document_id` 五套命名并存**：SHA16 64 条、`DOC-C00-*` 12 条、`DOC-<年>AR-*` 8 条、`DOC-<年>H1-*` 3 条、事件类临时命名 13 条。
2. **状态词表漂移**：规则定义 9 个合法值，实际用了 20 个，其中 6 个是自造值（`L1_SOURCE_INDEX_ONLY`、`UPLOADED_AND_TEXT_READ`、`WEB_PAGE_READ_NOT_DRIVE_ARCHIVED`、`DRIVE_TEXT_EXTRACTION_OK`、`OFFICIAL_PAGE_WEB_VERIFIED`、`WEB_TEXT_READ_IDENTITY_CORRECTED`）。
3. **`file_status` 一字段糊五件事**：14 种复合值，无法分轴统计。
4. **`source_type` 混装三种语义**：17 个取值里混了文档类型、取得方式、读取状态，没有一个是纯文档类型。
5. **三元组不能当唯一键**：存在 4 组「同公司 + 同 source_type + 同报告期」但内容不同的记录，已写入规则作为反例。

## 四、数量对账

| 口径 | 数量 |
|---|---:|
| 登记表行数 | 100（未改动） |
| 新增列 | 19 |
| 需归一报告期 | 92 |
| 保留历史 ID | 36 |
| 缺 SHA-256 | 13 |
| 文档类型由标题推断 | 77 |
| 报告期无法判定 | 7 |
| 归档状态规则外取值 | 6 |
| 读取状态规则外取值 | 10 |
| 未存二进制（仅网页/外链） | 5 |
| **状态轴冲突需人工判定** | **4** |
| 文档类型无法判定 | 0（补了 3 条标题规则后清零） |

## 五、dry-run 自动校验（6 项全过）

| 检查 | 结果 |
|---|---|
| 行数不变 = 100 | PASS |
| `document_id` 100 行原值不变 | PASS |
| 枚举无未映射值 | PASS |
| 归档状态归一后全部合法 | PASS |
| 证据状态未出现 `VERIFIED_INDEPENDENT` | PASS |
| 每行都有迁移标记 | PASS |

## 六、4 行冲突，留待人工判定（未自动处理）

| document_id | 冲突 | 处理 |
|---|---|---|
| `DOC-2025AR-920346` | 归档：旧值 UPLOADED_UNVERIFIED，file_status 暗示 VERIFIED | 保留旧值 + CONFLICT |
| `DOC-C00-2025-920211` | 同上 | 保留旧值 + CONFLICT |
| `DOC-AWARD-920207-20260429` | 归档：旧值 NOT_REQUIRED_REFERENCE_ONLY，暗示 NOT_UPLOADED | 保留旧值 + CONFLICT |
| `DOC-C00-2026-IPO-920211` | 读取：旧值 AI_READ_CONFIRMED，暗示 NOT_CHECKED | 保留旧值 + CONFLICT |

最后一行是最好的教材：官方链接有、PDF 下载失败、Drive 无原件，但 AI 确实读完了网页全文。五轴若合成一个字段，这个事实必然丢失。

## 七、校验器改动与遗留

**改了**：`tools/validate_plan.py` 原来硬编码 `2026-10-24`，与 P00 冻结的 `2026-10-25` 冲突。现改为读取 `runs/issues/P00/collection_scope.json` 的 `time_axis.knowledge_as_of`，回退到 `PROJECT_STATE.json`；同时把 `research_as_of` 的判定从「必须等于截止日」改为「不得晚于截止日」，符合 P00 定义的「行级时点 ≤ 研究截止日」。

**结果**：`research_cutoff_consistent` 由 FAIL 转 **PASS**（实际读到冻结值 2026-10-25，来源 `collection_scope.json`）。

**遗留 5 项既有失败，与本次改动无关，未处理**：
`package_index_count`、`primary_package_count`、`primary_packages_cover_master_once`、`master_primary_package_matches_assignment`、`all_local_package_zips_match_index`。

原因：`data/package_index.csv` 现在 68 行 / 59 个 primary，而校验器仍按 67 / 58 断言；新增的 `D00_B00_ADVANCE_01` 包（order 299）没有回写到 `company_master.primary_package_id`，也没有对应 ZIP。这是旧包体系的数据漂移，属历史遗留，不在 P01 范围。

**没有覆盖历史报告**：仓库原有的 `validation/independent_check.json` 是 2026-10-25 的绿报告（PASS，110 项全过，截止日 2026-10-24）。那是他人成果，已原样保留。本次运行结果另存 `runs/issues/P01/validate_plan_run.json`（106 通过 / 5 失败）。这也说明漂移发生在那次绿报告之后，不是 P01 引入的。

## 八、限制

1. **77 行文档类型来自标题推断**（`document_type_source=TITLE_PATTERN`），不是官方元数据确认。归档核验时必须升级或改判，不得直接当已确认事实统计。
2. **4 行状态冲突未裁决**，迁移时需人工看一眼。
3. **迁移方案未执行**。本卡只出方案，原表一字未动。
4. **去重第 4 步缺列**：`official_announcement_id` 现表没有，目前只能从 CNINFO URL 反解。
5. 本卡未访问 Drive，因此无法核对 73 条 `UPLOADED_UNVERIFIED` 是否真的在 Drive 里。

## 九、验收结论与放行

- 两条验收标准对照见 `review.json`，结论 **SELF_CHECK_PASS**。
- **放行**：P02（#13，盘点 Drive/本机/旧库——可直接按本卡结构与迁移方案落列）、P05（#16，采集器需要身份与去重规则）。
- **不放行**：任何业务结论采用、任何指标筛选。
- **声明**：本次自检由执行者本人完成，不是独立审计。

## 十、下一步建议

1. P02 开始时先执行迁移方案的十步，把 19 列和旁表落下——P02 本来就要遍历登记表，成本最低。
2. 迁移时同步裁决那 4 行冲突。
3. 建议另开一张小卡修掉校验器的 5 项包索引漂移（要么更新断言到 68/59，要么把 `D00_B00_ADVANCE_01` 回写进 master 并补 ZIP）。在修之前，`validate_plan.py` 的 `result` 会一直是 FAIL，看报告时要区分这 5 项与真实问题。
