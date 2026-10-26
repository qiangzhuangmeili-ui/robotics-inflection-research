# P05 交接：实现可断点续跑的采集器与下载校验

- **issue**：#16 / P05，plan_version `20261026_collection_first_v2`
- **执行者/自检者**：WorkBuddy AI（执行与自检同一主体，`review_nature=SELF_CHECK`，不冒充独立审计）
- **起止**：2026-10-26T16:20(+08) 领取 → 2026-10-26T16:45(+08) 完成
- **输入基线 commit**：`437bbd2`（P04 完成后的 main）
- **依赖**：P01 #12、P03 #14、P04 #15，三者 `review.json` 均为 `SELF_CHECK_PASS` 且放行范围含 P05
- **本卡不做**：不跑全池、不做 10 家校准（P07）、不做业务结论/拐点/估值、不改任何原始输入

## 一、一句话结论

采集器已经能**在真实巨潮接口上把定期报告取回来并证明取对了**：全分页对账、七项原文校验、Range 断点续传、按源熔断、幂等跳过全部落地。
离线故障注入 10/10、真实三市场 11/11 通过。最有价值的三条不是"能下载"，而是**三个会让人误判的坑**（见第三节）。

## 二、交付

| 文件 | 内容 | 规模 |
|---|---|---|
| `runs/issues/P05/collector_config.json` | 采集参数唯一来源：12 个报告槽、3 条路由、限速/重试/熔断、七项校验阈值、幂等顺序、状态口径 | 12.6 KB |
| `runs/issues/P05/collector_runbook.md` | 运行手册：命令、断点语义、状态码处置、故障处置、禁区 | 6.8 KB |
| `runs/issues/P05/collector_validation.json` | 6 条验收标准逐条对照 + 未覆盖项 | 6.3 KB |
| `runs/issues/P05/fault_tests.json` | 10 项离线故障注入结果 | 4.4 KB |
| `runs/issues/P05/live_validation.json` | 三市场实跑 + 多页翻页 + 半年报槽结果 | 15.5 KB |
| `runs/issues/P05/collection_index.csv` | 槽位索引（一槽一行，含 document_id/哈希/页数/校验方法） | 4 行 |
| `runs/issues/P05/checkpoint/*.json` | 单证券台账：状态、尝试记录、目录分页与行缓存 | 3 份 |
| `runs/issues/P05/run_log.jsonl` | 追加式事件流 | 222 行 |

代码：`tools/p05_collector.py`（采集器）、`tools/p05_fault_tests.py`（故障注入）、`tools/p05_live_validation.py`（实跑验证）、`tools/p05_finalize.py`（收尾）、`tools/p05_normalize_ledger.py`（台账一次性归一化）。

原件与原始响应（**不入库**）：`sources/p05_validation/` 4 份 PDF 共 13,988,588 字节；`sources/p05_raw/` 4 份目录原始 JSON。

## 三、五条实测发现（每条都能回到文件）

### 1. orgId 猜错会返回 0 条，空结果最容易被误写成"未披露"
巨潮 `hisAnnouncement/query` 的 `stock` 参数是 `代码,orgId`。第一次用臆造的 `gssh0608218` 查询 688218，**HTTP 200、totalAnnouncement=0**；换成 `szse_stock.json` 里的真实 `gfbj0836084` 后返回 8 条。
→ 采集器必须先做 orgId 解析（`/new/data/szse_stock.json`，实测 **1054/1054 覆盖**，含 BJ 62 家），否则会把参数错误当成公司没披露。

### 2. 分页不能信 `totalpages`/`hasMore`
同一家公司（688218，8 条年报目录）：
- `pageSize=30` → `totalpages=0`、`hasMore=false`，但一次返回 8 条；
- `pageSize=5` → `totalpages=1`、`hasMore=true`，实际第 2 页还有 3 条。

→ 只以 `totalAnnouncement` 与累计去重行数对账，不等即 `INDEX_INCOMPLETE_PAGINATION`。这一条已写成故障用例 T01 和实跑用例 L10。

### 3. 北交所历史代码必须接受，不能按 secCode 硬卡
BJ:920207（众诚科技）的年报目录里，2024 年及以前 6 条记录的 `secCode` 是 **835207**（股转时期旧代码），2025 年才是 920207。
→ 按证券简称一致即接受并标 `historical_code`；简称也不一致（如混入 000001 平安银行）才拒收。已写成用例 T08。

### 4. 北交所年报封面是版式化排版，正文没有「2025年年度报告」这句话
920207 的 2025 年报首页只有「2025」「众诚科技」「920207」「河南众诚信息科技股份有限公司」分散排布，正文搜不到连续短语，报告期校验会误判为 `IDENTITY_MISMATCH`。
→ 增加有记录的降级：正文出现年份 **且** 官方目录标题含「{year}年 + 报告类型」→ 通过，并记 `period_match_method=TITLE_PLUS_YEAR_IN_BODY`。沪/深两份仍是 `BODY_PHRASE`，差异在 `collection_index.csv` 可见。

### 5. "跳过"是动作，不是状态
早期实现把 `SKIPPED_ALREADY_HAVE` 写进 `status`，会覆盖真实的 `COLLECTED_IDENTITY_VERIFIED`。已改为：`status` 保留取得状态，另记 `last_action` + `skip_count`。`tools/p05_normalize_ledger.py` 对已产生的台账做了幂等迁移。

## 四、验收对照（issue #16 原文）

| 验收标准 | 结果 | 证据 |
|---|---|---|
| 至少覆盖分页不完整、HTML伪PDF、同文件重复、下载中断与源故障；运行可复算 | PASS | `fault_tests.json` 10/10：T01 分页不完整、T02 HTML伪PDF、T03 同文件重复、T04 中断+Range续传、T05 源故障熔断；另加 T06 摘要冒充、T07 主体错配、T08 北交所历史代码、T09 截断PDF、T10 限速预算。`python tools/p05_fault_tests.py` 可复算 |
| 公告全分页与上游总数核对，保留原始响应/请求参数/来源时间/游标 | PASS | `live_validation.json#pagination_probe`（pageSize=5 分 2 页、8=8 对账）；`checkpoint/*.json#indexes.pages` 存 request_params、response_sha256、fetched_at、cursor；原始 JSON 落 `sources/p05_raw/` |
| 每证券/报告槽记录 source_attempt、attempt_count、last_error、next_action、checkpoint；幂等跳过 | PASS | `collection_index.csv` + `checkpoint/*.json`；幂等重放 `http_calls=0`（L6）；跳过不发请求 |
| 原文检查 HTTP/文件头/PDF可读/标题主体报告期/页数/SHA256；链接不算下载成功 | PASS | `validate_pdf` 七项校验；4 份原件全 PASS（L5）；T02/T09 证明非 PDF 与截断不计成功 |
| 低并发、限速、重试预算、熔断、中断恢复；北交所/历史代码独立用例 | PASS | concurrency=1、1.2s/主机、单请求 2 次、单槽 3 次；熔断复用 P03 策略（T05：熔断后 6 个槽位 0 次额外请求）；BJ 走 `column=szse`（L3）；历史代码 L4 |
| 原始大文件旁路存本机/Drive，GitHub 只存小型索引与运行记录 | PASS | `.gitignore` 已排除 `sources/**`、`*.pdf`；入库最大文件 42 KB |

**6/6 PASS。这是 SELF_CHECK，不是独立审计。**

## 五、实跑明细（真实网络，2026-10-26）

| 证券 | orgId | 目录列 | 目录对账 | 槽位 | 页数 | 字节 | 报告期核对方法 |
|---|---|---|---|---:|---:|---|---|
| SH:688218 江苏北人 | gfbj0836084 | sse | 8=8 | annual_2025 | 263 | 3,951,900 | BODY_PHRASE |
| SZ:002031 巨轮智能 | gssz0002031 | szse | 8=8 | annual_2025 | 204 | 2,317,799 | BODY_PHRASE |
| SZ:002031 巨轮智能 | gssz0002031 | szse | 6=6 | h1_2026 | 171 | 4,608,089 | BODY_PHRASE |
| BJ:920207 众诚科技 | gfbj0835207 | szse | 8=8 | annual_2025 | 178 | 3,110,800 | TITLE_PLUS_YEAR_IN_BODY |

## 六、限制与未做

1. **不是全池覆盖**：只跑 3 家 × 1 个年度槽 + 1 个半年报槽。全池 1054 家属 M00_01—M00_11，10 家校准属 P07。
2. **PDF 正文比对依赖 pypdf 文本层**：扫描件或纯图版式会退化为 `COLLECTED_PENDING_IDENTITY`（文件已取得、身份待人工核），不会被写成已验证。
3. **季度 PDF 未实跑**：开关 `--include-optional-pdf` 已实现并有配置位，本次按 P00「季度以结构化为主」的定位默认关闭。
4. **结构化财务接口未接**：新浪接口属 P04 映射范围，本卡只负责原件取回，不抽字段。
5. **listing_date 仍 1054/1054 UNKNOWN**：空目录只能记 `NOT_TRIED` + `RESOLVE_LISTING_DATE`，不能判"上市前不适用"，也不能判"未披露"。
6. **run_log.jsonl 是追加式历史**：包含本卡调试期的中间事件（含修复前的 920207 报告期误判），最终状态以 `checkpoint/` 与 `collection_index.csv` 为准。
7. **SELF_CHECK**，不是独立审计。

## 七、给 P06 / P07 的直接输入

- **P06（容量/目录/归档）**：单份年报实测 2.3—4.6 MB、171—263 页；季度 PDF 更小。用 `collection_index.csv` 的 `bytes` 列按槽位求中位数即可估容量，不必等全池。归档目录建议沿用 `sources/p05_validation/<code>/<slot>/<DOC-ID>.pdf`，DOC-ID 由 `IDENTITY_V1` 在下载前分配。
- **P07（10 家校准）**：直接复用 `Collector`，把 `--security` 换成 10 家即可；校准重点应是**尚未覆盖的市场/报告期组合**（北交所半年报、2023 年及以前、季报 PDF），而不是重复沪市年报。
- **M00 批次**：`concurrency=1`、1.2s/主机、单槽 3 次尝试。按当前实测（每家 2—3 次请求 + 1—2 次下载），全池量级可在单机串行跑完，但必须整轮汇总缺口后再给用户，不逐家催补。
- **已知待办**：① 扣非仍要回 PDF 解析（P04）；② 62 家北交所旧快照缺口要靠本采集器的 BJ 路由补；③ `listing_date` 回填后才能做"上市前不适用"判定。
