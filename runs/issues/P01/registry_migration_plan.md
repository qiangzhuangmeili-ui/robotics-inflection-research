# P01 登记表迁移方案

> 目标表：`data/document_registry.csv`（现有 100 行 × 23 列）
> 目标结构：`runs/issues/P01/document_registry_schema.json`
> 身份规则：`runs/issues/P01/document_identity_rules.json`
> 本文件是**方案**，不是执行记录。执行由后续卡按本文步骤落地。

## 一、边界

- 只加列、只加旁表。**不删列、不改名、不覆盖既有值。**
- 6 个字段语义冻结、原文不动：`document_id`、`source_type`、`period_covered`、`file_status`、`storage_provider`、`access_check_status`。
- 100 行一条不少，`document_id` 一个不改（含 36 条非标准命名）。
- 迁移前必须备份；迁移后必须能逐行证明原始 23 列一字未变。

## 二、前置条件

1. `data/document_registry.csv` 当前 SHA-256 = `a2c31e7be0fd151c8f29ad9a65ed3f589677ae5e112f754463676d5bb6fcc4ed`。若执行时哈希不符，先停下核对，不得在变动过的表上迁移。
2. 备份到 `data/backup/document_registry_<YYYYMMDD_HHMM>.csv`，并记哈希。
3. 确认 `data/company_master.csv` 仍是 P00 冻结版本（1054 行）。

## 三、十步流程

| 步 | 动作 | 产出 | 是否可逆 |
|---:|---|---|---|
| 1 | 备份原表并记录哈希 | `backup/*.csv` | 是 |
| 2 | 追加 19 个新列，全部留空 | 新表头 | 是（删列即可） |
| 3 | 回填 `id_scheme`（按 ID 形态判定） | 100 行有值 | 是 |
| 4 | 回填 `document_type` + `document_type_source` | 100 行有值 | 是 |
| 5 | 回填 `acquisition_channel` | 100 行有值 | 是 |
| 6 | 归一 `period_covered` → `period_key` | 100 行有值 | 是 |
| 7 | 拆 `file_status` → `link_status` / `binary_status` / `access_identity_status` / `evidence_status` | 四轴有值 | 是 |
| 8 | 归一 `archive_status`，原文存 `archive_status_legacy`；旧 `access_check_status` 存 `access_check_status_legacy` | 两列留痕 | 是 |
| 9 | 写 `unknown_reasons`、`next_action`、`migration_flags` | 100 行有值 | 是 |
| 10 | 建 `data/document_sources.csv`，把 `primary_url` / `drive_file_id` / `local_file` 拆成来源行 | 旁表 | 是 |

第 10 步的拆分规则：

- `primary_url` 非 UNKNOWN → 一条 `source_kind` 按域名判定（巨潮/上交所/深交所/北交所/股转/公司站/其他）的来源行，`is_primary=true`
- `drive_file_id` 非空 → 一条 `source_kind=DRIVE_FILE` 的来源行，`is_primary=false`
- `local_file` 非空 → 一条 `source_kind=LOCAL_FILE` 的来源行，`is_primary=false`，`note=临时缓存`
- `source_id` = `SRC-` + sha256(document_id + "|" + source_kind + "|" + locator) 前 16 位大写

## 四、字段映射（dry-run 实测）

| 新字段 | 取值分布（100 行） |
|---|---|
| `id_scheme` | SHA16 64 / LEGACY_SEMANTIC_ADHOC 13 / LEGACY_SEMANTIC_C00 12 / LEGACY_SEMANTIC_AR 8 / LEGACY_SEMANTIC_H1 3 |
| `document_type` | ANNUAL_REPORT 74 / INVESTOR_RELATIONS_ARTICLE 7 / OFFICIAL_WEBSITE_ARTICLE 4 / ANNUAL_REPORT_SUMMARY 3 / SEMI_ANNUAL_REPORT 3 / LISTING_DISCLOSURE 2 / PROSPECTUS 2 / CONTRACT_ANNOUNCEMENT 2 / SUSTAINABILITY_REPORT 1 / SHAREHOLDER_MEETING_MATERIAL 1 / TENDER_NOTICE 1 |
| `document_type_source` | TITLE_PATTERN 77 / SOURCE_TYPE 23 |
| `period_key` | FY2025 69 / 2026H1 12 / NOT_APPLICABLE_EVENT_BASED 7 / PERIOD_UNRESOLVED 7 / PRE_LISTING_MATERIALS 2 / LISTING_YEAR_2026 1 / AGM_2026 1 / MULTI_PERIOD_FY2023_FY2025 1 |
| `link_status` | FOUND_OFFICIAL 83 / NOT_RECORDED 11 / FOUND_SECONDARY 6 |
| `binary_status` | OBTAINED 90 / NOT_ATTEMPTED 8 / FAILED 2 |
| `archive_status`（归一后） | UPLOADED_UNVERIFIED 76 / VERIFIED 14 / NOT_UPLOADED 8 / NOT_REQUIRED_REFERENCE_ONLY 2 |
| `access_identity_status` | NOT_CHECKED 72 / AI_READ_CONFIRMED 24 / AI_TEXT_EXTRACTED_UNVERIFIED 3 / IDENTITY_MISMATCH 1 |
| `evidence_status` | NOT_USED 84 / SELF_CHECK_ONLY 16 |

**关键提醒**：`document_type` 有 77 行是**从标题推断**的（`document_type_source=TITLE_PATTERN`），不是官方元数据确认。这些值在归档核验时必须升级为 `OFFICIAL_METADATA` 或改判，不得直接当已确认事实用于统计。

## 五、三张归一表

### 5.1 报告期（11 个自由文本 → 受控值）

| 原值 | period_key | 说明 |
|---|---|---|
| 2025年度 | FY2025 | |
| 2026H1 | 2026H1 | |
| 2026半年度 | 2026H1 | 同一期间的另一种写法 |
| 2025年度报告摘要 | FY2025 | 期间相同，类型由 document_type 区分 |
| 2023-2025审计财务数据 | MULTI_PERIOD_FY2023_FY2025 | 跨期数据包 |
| 2026年度 | PERIOD_UNRESOLVED | 年度未结束，无法判定是年度还是泛指 2026 年 |
| 2026年度_投资者关系 | NOT_APPLICABLE_EVENT_BASED | 事件类，真实时点看 event_period |
| 2025年度_投资者关系 | NOT_APPLICABLE_EVENT_BASED | 同上 |
| 2026年度_上市前材料 | PRE_LISTING_MATERIALS | |
| 2026年上市披露 | LISTING_YEAR_2026 | |
| 2026年年度股东会材料 | AGM_2026 | |

### 5.2 归档状态（2 个规则外自造值归一）

| 原值 | 归一为 | 原因 |
|---|---|---|
| L1_SOURCE_INDEX_ONLY | NOT_UPLOADED | 规则里没有「只做索引」这个归档状态；索引不等于归档 |
| UPLOADED_AND_TEXT_READ | UPLOADED_UNVERIFIED | 上传且读到文本，但未核身份与物理页，属未核验 |

原文一律写入 `archive_status_legacy`。

### 5.3 读取状态（4 个规则外自造值归一）

| 原值 | 归一为 | 原因 |
|---|---|---|
| DRIVE_TEXT_EXTRACTION_OK | AI_TEXT_EXTRACTED_UNVERIFIED | 提取到文本，但未核物理页，不能等同 AI_READ_CONFIRMED |
| WEB_PAGE_READ_NOT_DRIVE_ARCHIVED | NOT_CHECKED | 读的是网页，不是归档原件；「读过网页」这件事记在 link_status |
| OFFICIAL_PAGE_WEB_VERIFIED | NOT_CHECKED | 同上 |
| WEB_TEXT_READ_IDENTITY_CORRECTED | IDENTITY_MISMATCH | 该行本身记录的就是身份被纠正 |

原文一律写入 `access_check_status_legacy`。这不是降级——是把「读过网页」和「读过归档原件」两件事分开记。

## 六、4 行冲突，必须人工判定后才能迁移

迁移脚本遇到这几行**保留旧值 + 打 `CONFLICT` 标记**，不自动取舍：

| document_id | 冲突点 | 旧值 | file_status 暗示 | 建议 |
|---|---|---|---|---|
| `DOC-2025AR-920346` | 归档 | UPLOADED_UNVERIFIED | VERIFIED | 核 Drive 是否已做身份核验，是则升 VERIFIED |
| `DOC-C00-2025-920211` | 归档 | UPLOADED_UNVERIFIED | VERIFIED | 同上 |
| `DOC-AWARD-920207-20260429` | 归档 | NOT_REQUIRED_REFERENCE_ONLY | NOT_UPLOADED | 确认它是否仅作参考；若是则保留参考态 |
| `DOC-C00-2026-IPO-920211` | 读取 | AI_READ_CONFIRMED | NOT_CHECKED | 已读网页全文但下载失败，`AI_READ_CONFIRMED` 成立；补记「读的是网页版」 |

最后一行恰好说明五轴必须独立：官方链接有、二进制下载失败、Drive 无原件、但 AI 确实读完了网页全文。合成一个字段就会丢掉这个事实。

## 七、验证清单（迁移后必跑）

| 编号 | 检查 | 通过标准 |
|---|---|---|
| V01 | 行数 | = 100，不得减少 |
| V02 | `document_id` | 100 行原值逐一相等 |
| V03 | 原始 23 列 | 逐行逐列与备份完全一致 |
| V04 | 枚举合法性 | 所有枚举列取值在表内，0 个越界 |
| V05 | `archive_status` | 全部落在规则定义的 5 值内 |
| V06 | `evidence_status` | 不出现 `VERIFIED_INDEPENDENT` |
| V07 | `*_legacy` 留痕 | 6 行归档归一、10 行读取归一均有原文 |
| V08 | 旁表条数 | `document_sources` 行数 = 有定位符的行数之和，无孤儿 `document_id` |
| V09 | 冲突标记 | 4 行 CONFLICT 全部可见，未被静默处理 |
| V10 | 未知原因 | 每个 UNKNOWN 都有 `unknown_reasons` 代码 |

## 八、回滚

1. 删掉新增 19 列与 `data/document_sources.csv`，即回到原表——因为原始列一字未改。
2. 若第 8 步已归一 `archive_status`，用 `archive_status_legacy` 反写即可。
3. 极端情况直接还原备份文件并核对哈希。

## 九、不做的事

- 不重新编号 `document_id`
- 不合并任何两行
- 不删除任何「重复」记录（现有表实测无重复 `sha256`、无重复 `drive_file_id`）
- 不用标题推断 `issuer_scope`
- 不访问 Drive、不下载任何文件
- 不修改 `data/document_registry.csv`（本卡只出方案）

## 十、执行建议

- 建议放在 **P02（盘点 Drive / 本机 / 旧库）开始时**一并做：P02 本来就要遍历登记表，顺手落列成本最低。
- 第 4 步的 77 行标题推断值，建议在 P02 盘点时用 Drive 文件首页核对一遍，转为 `OFFICIAL_METADATA`。
- 第 10 步旁表建好后，去重查重顺序的第 4 步（公告编号）仍缺列，需在 P02/P03 从 CNINFO URL 反解后回填 `official_announcement_id`。
