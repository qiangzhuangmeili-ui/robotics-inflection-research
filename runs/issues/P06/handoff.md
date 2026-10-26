# P06 交接：确定容量、目录、归档与交接规则

- **issue**：#17 / P06，plan_version `20261026_collection_first_v2`
- **执行者/自检者**：WorkBuddy AI（执行与自检同一主体，`review_nature=SELF_CHECK`，不冒充独立审计）
- **起止**：2026-10-26T16:52(+08) 领取 → 2026-10-26T17:02(+08) 完成
- **输入基线 commit**：`b753b49`（P05 完成后的 main）
- **依赖**：P00 #11、P02 #13，两者 `review.json` 均为 `SELF_CHECK_PASS`，且 P02 的放行范围明写含 P06
- **本卡不做**：不下载、不上传、不改 `document_registry.csv`、不改名单、不做业务判断、不估值

## 一、一句话结论

容量、目录、归档三件事都已经拆成**可机读、可复算、可拒收**的规则：
容量拆成"计划槽 / 实际发现 / 实际字节"三层，核心槽估算 **9.79—18.66 GiB（中位 13.43 GiB，不含季度）**，已超过本机允许的单轮缓存上限 **8 GiB**，因此**禁止"全池一次下完再归档"**，必须按批滚动缓存；
Drive 根目录与 01—05 分类目录按用户快照登记齐备，但本会话**无 Drive 权限（302/401/403）**，目录只能记 `RECORDED_NOT_REVERIFIED`、归档最高只能到 `UPLOADED_UNVERIFIED`；
回执 schema 用 10 条不变量把"目录 URL 当文件 ID""没回读就写 VERIFIED""归档成功当成已读全文"三种错**在校验层拒收**。

## 二、交付

| 文件 | 内容 | 规模 |
|---|---|---|
| `runs/issues/P06/storage_plan.json` | 容量三层口径、单位字节样本、估算区间、缓存策略与水位、Drive 布局与核实结论、登记顺序、去重与清理规则、历史状态归一化、6 条阻断、8 条不变量 | 40.9 KB |
| `runs/issues/P06/archive_routing.csv` | 13 条归档路由（年报/半年报/季报/摘要/招股书/更正/公告/财务导出/行业/交接包/仅索引/阻断），上传态与回读态**分两列** | 4.1 KB |
| `runs/issues/P06/transfer_receipt_schema.json` | 传输回执 JSON Schema（draft-07）+ 10 条不变量 + 4 条 `if/then` 条件必填 + 禁止模式 + 一份合格样例 | 19.1 KB |
| `runs/issues/P06/self_check.json` | 11 项可复算自检 | 4.3 KB |

代码：`tools/p06_storage_plan.py`（生成三份交付 + 自检 + 回执校验 CLI）。

## 三、容量：三层口径，不许混着说

| 层 | 口径 | 数字 | 说明 |
|---|---|---|---|
| 计划槽 | 数学上界 | 核心 **6324**（6 槽 × 1054）+ 季度适用 **5270**（5 槽 × 1054）= **11594** 次尝试 | `q3_2026` 法定披露期 2026-10-31 晚于截止日 2026-10-25，记 `NOT_YET_DISCLOSED`，**不计容量**。`listing_date` 1054/1054 UNKNOWN，无法扣除上市前不适用与未披露，**这是上界不是应有份数** |
| 实际发现 | 文件层计数 | 登记 **100** 份 / 唯一 ID **100** / 唯一内容哈希 **87** / 有 Drive ID **90** / 有本地路径 **64**（现存 64）/ `VERIFIED` **14** / `UPLOADED_UNVERIFIED` **73** / `AI_READ_CONFIRMED` **24** / **独立业务验收 0** | 四个数字分别列，不合并成"完成率" |
| 实际字节 | 已取得二进制的实测 | PDF 类资产 **83** 份共 **224,269,941 B（213.88 MiB）**；P05 实跑 **4** 份共 **13,988,588 B** | 未取得二进制的登记行**不计入**，也不按文件名推测大小 |

**单位字节（按内容哈希去重后的实测样本）**

| 类别 | n | 中位 | p25—p75 | 用途 |
|---|---:|---:|---|---|
| 年报全文 | 74 | 2,110,208 B | 1,493,006—2,885,355 | 3 个年报槽 × 1054 |
| 半年报全文 | 4 | 2,449,992 B | 1,830,444—3,451,576 | 3 个半年报槽 × 1054 |
| 年报摘要 | 2 | 186,696 B | — | 只作缺全文时的替代，不计核心槽 |
| 招股书 | 1 | 6,446,427 B | — | 上市前替代件 |
| **季度报告** | **0** | **UNMEASURED** | — | P05 季度开关未实跑；**按 P00 规则不给估计值** |

**核心槽估算（ESTIMATE_NOT_FACT，不是"需要 X GB"的事实）**

- 低（p25）：**9.79 GiB**　中位：**13.43 GiB**　高（p75）：**18.66 GiB**
- 季度 PDF 未计入（`UNMEASURED`），公告原件与财务导出另计

**本机约束（2026-10-26 16:56 实测）**

| 项 | 值 |
|---|---|
| 缓存盘 C: | 总 200 GiB，剩余 **24.29 GiB（已用 87.9%）** |
| 备用盘 D: | 剩余 **158.42 GiB** |
| 单轮滚动缓存上限 | **8 GiB** |
| 软水位 / 硬停 | 剩余 10 GiB 提前归档 / 剩余 6 GiB 停止新下载 |

估算中位 13.43 GiB > 单轮上限 8 GiB → **"全池一次下载完再归档"在本机不可行**。做法：按批（M00_xx）滚动缓存，批内完成"下载 → 归档回读 → 清理"，缓存只作滚动窗口，不作全池仓库。

## 四、Drive：目录登记齐备，但本会话核实不了

| 角色 | folder_id | 快照状态 | 本卡复核 |
|---|---|---|---|
| 根目录 | `1v8RYlfohKcrGrulwCFq3fZSnGdjFxUYQ` | CREATED_AND_READ_BACK | RECORDED_NOT_REVERIFIED |
| 01_原始资料 | `1uC1sk5q7PKMZMLPLt-xIxOj2nPk4z0Ne` | CREATED_AND_LISTED | RECORDED_NOT_REVERIFIED |
| 02_批次交接 | `1uep8rD84ZuK-RIDvwBXhnhhw3px_obr5` | CREATED_AND_LISTED | RECORDED_NOT_REVERIFIED |
| 03_历史版本 | `1i-HqmZKBxx_fMJMo1mA_nHW9JPe2ijqi` | CREATED_AND_LISTED | RECORDED_NOT_REVERIFIED |
| 04_财务与数据导出 | `1rbZSpFszk4i6nWbN4NwrxeqlEGtLX_St` | CREATED_AND_LISTED | RECORDED_NOT_REVERIFIED |
| 05_行业资料 | `1g3LMjH1SXHdosoqdQ8m-g3gfSq43Zll1` | CREATED_AND_LISTED | RECORDED_NOT_REVERIFIED |

真实探测（`storage_plan.drive_layout.verification`，可复跑）：

| 探测 | 结果 |
|---|---|
| 目录页 `GET /drive/folders/<root_id>` | **302** → `accounts.google.com/ServiceLogin` |
| 文件页 `GET /file/d/<file_id>/view` | **401** |
| `GET googleapis.com/drive/v3/files/<root_id>` | **403**（无凭据） |

结论 `DRIVE_API_NOT_CONNECTED`：列目录、读元数据、上传、下载二进制、读配额**全部不可用**。
因此本卡**没有**声称任何目录"已核实可用"，也**没有**给出 Drive 配额数字；五个目录只是"按用户快照登记"。
未尝试登录、未要求公开分享、未扩大任何权限。

## 五、三条最容易搞错的规则（每条都有机器校验）

### 1. 目录 URL 不是文件 ID，而且必须分字段
`drive_file_id` / `drive.file_id` 只放不透明 ID（`^[A-Za-z0-9_-]{20,}$`），禁止出现 `http`、`drive.google.com`、`/folders/`、`usp=drivesdk`；目录 ID 只能进 `drive.target_folder_id`；`drive.file_url` 只能是 `https://drive.google.com/file/d/<file_id>`。
现状核查：登记表 100 行里 **格式违规 0 行、URL 混入 0 行**（90 条 Drive ID 全部是裸 ID）。
自检 SC4 用四类错误回执实测：把目录 URL 填进 folder_id、没回读就写 VERIFIED、没有页码原句就写 AI_READ_CONFIRMED、把哈希写成 `NOT_COMPUTED` —— **4/4 全部被拒收**。

### 2. 归档成功 ≠ AI 已读全文
`archive_status` 与 `access_check_status` 是两个字段、两套证据：
- `VERIFIED` 必须同时有 `file_id` + `file_url` + `readback.listed=true` + `parents_contains_target_folder_id=true`（`INV-01`）；
- `AI_READ_CONFIRMED` 必须有 `evidence.page_quote.quote_located=true`（`INV-02`）；
- 路由表把"上传后（`UPLOADED_UNVERIFIED`）"与"回读后（`VERIFIED`）"**拆成两列**，不允许一个字段跨两态。
现有 100 行里 `VERIFIED` 14 行、`AI_READ_CONFIRMED` 24 行、独立业务验收 **0** 行 —— 归档数、读全文数、业务验收数三者不可互换。

### 3. 容量不足不是"截断"，是"断点 + 优先级"
优先级写死：**P0 annual_2025 → P1 h1_2026 → P2 annual_2024+h1_2025 → P3 annual_2023+h1_2024 → P4 关键词公告原件 → P5 季度 PDF（默认关）**。
触发硬水位（剩余 < 6 GiB）时的动作是固定的 5 条：停止新下载 → 写 checkpoint（已下载未归档清单、下一家/下一槽游标、已占字节）→ 记录被推迟的低优先级槽 → **保留本地原件** → 切换 cache_root 必须显式配置并留痕。
**任何情况下不删唯一副本**；清理本地缓存必须同时满足 6 个条件（含 `archive_status=VERIFIED`、回读父目录匹配、登记表已回填）。

## 六、验收对照

| 验收标准 | 结果 | 证据 |
|---|---|---|
| 不会在 GitHub 提交 PDF/ZIP/原始大表 | **PASS** | `git ls-files` 341 个跟踪文件，二进制 **0**；P06 交付最大 40.9 KB |
| 容量不足时有断点和优先级记录，不默默截断 | **PASS** | 6 条阻断（BLK-01—06）+ 5 条 breach 动作 + P0—P5 优先级 + 滚动缓存上限 8 GiB |
| Drive 目录 URL 不能填进文件 ID | **PASS** | schema `pattern` + `INV-03/04` + 自检 SC3（现状 0 违规）/SC4（反例被拒） |
| 归档成功不等于 AI 全文已核读 | **PASS** | 两字段分离 + `INV-01/02` + 路由表两列态 + SC11 |

自检 11/11 PASS（`self_check.json`）：入库无二进制、交付体量、登记表 ID 格式、回执 schema 四类反例、容量可复算、不把未实测写成事实、六目录齐备、路由覆盖 10 类文档、原始输入 diff 为空、优先级与断点齐备、路由状态值合法。

## 七、限制与未做

- **未做真实上传与回读**：无 Drive 权限，`VERIFIED` 这条路径本卡只在 schema 与校验器层面定义，未跑通一次真实闭环。P07 必须先做"列目录 → 上传 → 回读"三步探测。
- **季度报告字节数仍 UNMEASURED**：P05 季度开关未实跑；容量表里留空，没有用年报字节数顶替。
- **估算不是事实**：`capacity.status = PRE_CALIBRATION_ESTIMATE_NOT_FACT`，须 P07 用 10 家校准重算中位数后才改为 `CALIBRATED`。
- **`listing_date` 仍 1054/1054 UNKNOWN**：11594 是尝试上界，不是应有文件数；上市前不适用部分扣不掉。
- **历史状态未归一**：登记表存在 6 类非枚举值（`L1_SOURCE_INDEX_ONLY` 3、`UPLOADED_AND_TEXT_READ` 3、`WEB_PAGE_READ_NOT_DRIVE_ARCHIVED` 5、`DRIVE_TEXT_EXTRACTION_OK` 3、`OFFICIAL_PAGE_WEB_VERIFIED` 1、`WEB_TEXT_READ_IDENTITY_CORRECTED` 1），本卡只给 `PROPOSED_NOT_APPLIED` 映射（12 行），**未改登记表**。
- **本卡不判断任何公司是否披露**：空目录、缺件属采集卡职责；`NOT_TRIED` 不等于缺件。
- **SELF_CHECK，非独立审计**。

## 八、放行范围与下一张

P06 的技术/格式规则已可支撑 P07：P07 的五项依赖（P02/P03/P04/P05/P06）现在全部具备可读验收记录。
**P07 建议按本卡的 `handoff_to_p07` 五条执行**：三步探测 → 校准三类中位数（含 1 个季度槽）→ 滚动缓存 ≤ 8 GiB → 首个 `VERIFIED` 回执落库 → 才放开 M00_01。
全池批次仍等 P07；本卡不放行任何业务结论、指标筛选或公司深研。

## 九、复跑方式

```bash
python tools/p06_storage_plan.py                       # 重新生成三份交付 + 自检
python tools/p06_storage_plan.py --check               # 只跑自检
python tools/p06_storage_plan.py --validate-receipt X  # 校验一份回执
```

输入全部只读：`PROJECT_STATE.json`、`data/company_master.csv`、`data/document_registry.csv`、`data/drive_folders.csv`、`data/intake_company_queue.csv`、`data/intake_batch_index.csv`、`data/pdf_transfer_plan.csv`、`runs/issues/P00/collection_scope.json`、`runs/issues/P02/existing_assets.csv`、`runs/issues/P05/collector_config.json`、`runs/issues/P05/collection_index.csv`。
