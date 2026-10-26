# P05 采集器运行手册（COLLECTOR_V1）

- 版本：`20261026_collection_first_v2` / `COLLECTOR_V1`
- 对应 issue：[#16 P05](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/16)
- 参数唯一来源：`runs/issues/P05/collector_config.json`（改参数必须另存版本并重算，不得为凑数量放宽校验）
- 本手册只讲**怎么跑**；字段口径见 P04，来源路由与熔断见 P03，文档身份见 P01。

## 1. 环境

```bash
# 受管 Python（已含 requests / pypdf）
PY="C:/Users/zhangjianmei/.workbuddy-ai/binaries/python/versions/3.13.12/python.exe"
```

不需要额外安装、不改系统代理、不动 AKShare 环境。P03 已确认本机沙箱内直连巨潮可用。

## 2. 文件与目录

| 路径 | 内容 | 是否入库 |
|---|---|---|
| `runs/issues/P05/collector_config.json` | 采集参数（槽位、路由、限速、重试、校验阈值） | 是 |
| `runs/issues/P05/checkpoint/<code>.json` | 单证券台账：槽位状态、尝试记录、目录分页与行缓存 | 是（小文本） |
| `runs/issues/P05/collection_index.csv` | 全槽位索引（一槽一行） | 是 |
| `runs/issues/P05/run_log.jsonl` | 追加式事件流（翻页、下载、跳过、拒收） | 是 |
| `sources/p05_validation/<code>/<slot>/<DOC-ID>.pdf` | 原件 | 否（`.gitignore` 排除） |
| `sources/p05_raw/<code>/<category>_p<N>.json` | 每页原始响应 | 否 |
| `sources/p05_cache/szse_stock.json` | 全市场代码↔orgId 缓存（24h） | 否 |

## 3. 常用命令

```bash
# 单公司单槽（最常用）
$PY -X utf8 tools/p05_collector.py --security SH:688218 --slot annual_2025

# 单公司全部 12 个槽（6 核心 + 6 季度；季度 PDF 默认不下载）
$PY -X utf8 tools/p05_collector.py --security BJ:920207

# 季度 PDF 一并下载
$PY -X utf8 tools/p05_collector.py --security SZ:002031 --include-optional-pdf

# 只用本地缓存复算，不发新请求
$PY -X utf8 tools/p05_collector.py --security SH:688218 --offline

# 自检与实跑验证（可复算）
$PY -X utf8 tools/p05_fault_tests.py        # 10 项故障注入，离线
$PY -X utf8 tools/p05_live_validation.py    # 3 家 × 1 槽 + 多页 + 半年报
$PY -X utf8 tools/p05_finalize.py           # 重建 collection_index / validation / manifest / review
```

退出码：`0` 正常；`2` 传入的证券不在 `company_master.csv`；`130` 被 Ctrl-C 中断（台账已落盘）。

## 4. 断点续跑语义

一次 `collect_slot` 的生命周期：

```
PENDING → IN_PROGRESS(checkpoint=DOWNLOAD_STARTED) → COLLECTED_* / SOURCE_FAILED / ...
```

- 每个槽位写盘是**原子替换**（`tmp` + `os.replace`），进程被杀不会留下半截 JSON。
- 下载先写 `<DOC-ID>.pdf.part`，完成后校验再 `os.replace` 成 `.pdf`；`.part` 就是断点。
- 重跑时：台账状态为 `COLLECTED_*`/`SKIPPED` 且本地文件哈希一致 → 直接 `SKIPPED_ALREADY_HAVE`，**0 次 HTTP**。
- `.part` 存在时按 `Range: bytes=N-` 续传；服务端若忽略 Range 返回 200，会丢弃旧片段从头写，不拼接脏数据。
- 目录（公告索引）在台账内缓存 6 小时；重跑不必重新翻页，过期自动重取。

## 5. 状态码与处置

| 状态 | 含义 | 下一步 |
|---|---|---|
| `COLLECTED_IDENTITY_VERIFIED` | 文件取得且主体/报告期/全文形态七项校验通过 | 无 |
| `COLLECTED_PENDING_IDENTITY` | 文件取得，但正文抽取不足（扫描件/版式化） | `MANUAL_IDENTITY_CHECK`：人工看封面 |
| `SKIPPED_ALREADY_HAVE` | 台账已有同哈希原件，本次未发请求 | 无 |
| `DUPLICATE_SAME_CONTENT` | 与另一槽位字节相同，未重复入库 | 无 |
| `SUMMARY_ONLY` | 目录只有摘要，核心槽缺全文 | `SEARCH_FULL_TEXT_ALTERNATE_SOURCE` |
| `INDEX_INCOMPLETE_PAGINATION` | 累计行数 ≠ `totalAnnouncement` | `RETRY_INDEX_WITH_CORRECTED_PARAMS` |
| `NOT_DISCLOSED_BY_ISSUER` | 目录有记录但 PDF 404 | `REINDEX_THEN_RETRY` |
| `NOT_TRIED` | 未尝试，或目录空但 `listing_date` 未知 | `RESOLVE_LISTING_DATE`；**不得计完成** |
| `NOT_YET_DISCLOSED` | 法定披露期晚于 `knowledge_as_of` | 等下一轮 |
| `AFTER_CUTOFF_DISCLOSED` | 披露日晚于研究截止日 | 只登记增量候选 |
| `SOURCE_FAILED` | 有限重试后仍失败（超时/5xx/非 PDF/截断） | `WAIT_CIRCUIT_HALF_OPEN` 或 `RETRY_DOWNLOAD` |
| `ACCESS_BLOCKED` | 401/403/429 | `MANUAL_REVIEW_ACCESS`，不当成未披露 |
| `IDENTITY_MISMATCH` | 主体或报告期对不上，原件已删 | `MANUAL_REVIEW_IDENTITY` |

**计数口径**：只有 `COLLECTED_IDENTITY_VERIFIED` / `COLLECTED_PENDING_IDENTITY` / `SKIPPED_ALREADY_HAVE` 算"已取得原件"。`NOT_TRIED`、`SOURCE_FAILED` 一律不算。

## 6. 故障处置

- **空目录不等于未披露**。巨潮 `orgId` 猜错会返回 `totalAnnouncement=0`；必须走 `szse_stock.json` 解析。确认参数正确后才允许继续判断。
- **分页不要信 `totalpages`/`hasMore`**。实测 `pageSize=30`、8 条时 `totalpages=0`；`pageSize=5` 时 `totalpages=1` 但实际 2 页。只以 `totalAnnouncement` 与累计去重行数对账。
- **熔断**：复用 P03 策略。运输层连续 2 次失败或源层连续 3 次失败即开闸，401/403/429 立即开闸；冷却 900 秒后只允许带 `known_good_probe` 的已知正常样本复探。开闸期间排队槽位记 `SOURCE_FAILED`，不逐家催用户补件。
- **北交所**：`column=szse`（`bjse` 列实测 500）。2024 年及以前年报常以旧代码（如 `835207`）出现在行内 `secCode`，按证券简称一致接受并标 `historical_code`；简称也不一致则拒收。
- **版式化封面**：北交所年报封面没有连续「2025年年度报告」字样，报告期核对会退化为「官方目录标题 + 正文年份」，`period_match_method=TITLE_PLUS_YEAR_IN_BODY` 留痕；两条都不成立才判 `IDENTITY_MISMATCH`。

## 7. 与上下游的边界

- 上游：P01 的 `IDENTITY_V1`（`DOC-` + sha256(identity_key)[:16]）、P03 的路由与熔断策略、P04 的槽位/字段口径。
- 下游：P07 用本采集器做 10 家校准；M00_01—M00_11 用本采集器跑全池。**本卡不跑全池。**
- 本采集器只负责"把原件取回并核身份"。扣非归母净利润等字段抽取仍按 P04 规则从 PDF 解析，不在本卡。

## 8. 不要做的事

1. 不要为提高成功率调高并发或取消限速（`concurrency` 上限 2，默认 1）。
2. 不要无限重试；单槽 3 次尝试后必须转 `MANUAL_REVIEW`。
3. 不要把 `NOT_TRIED`、`SOURCE_FAILED` 写进完成数，也不要据此生成人工补件清单。
4. 不要用摘要、网页正文或二手转录替代全文 PDF。
5. 不要把原件提交到 GitHub（`sources/**`、`*.pdf` 已在 `.gitignore`）。
6. 不要改动 `data/` 下任何原始输入。
