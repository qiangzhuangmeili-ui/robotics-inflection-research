# P07 交接：10 家采集校准（只验接口和资料，不研究业务）

- **issue**：#18 / P07，plan_version `20261026_collection_first_v2`
- **执行者/自检者**：WorkBuddy AI（执行与自检同一主体，`review_nature=SELF_CHECK`，不冒充独立审计）
- **起止**：2026-10-26T19:30(+08) 领取 → 2026-10-26T19:45(+08) 完成
- **输入基线 commit**：`e5b9eb3`（P06 完成后的 main）
- **依赖**：P02/P03/P04/P05/P06，五张卡 `review.json` 均为 `SELF_CHECK_PASS`
- **本卡不做**：不做客户/订单/盈利归因、不做行业判断、不估值、不改名单、不改登记表

## 一、一句话结论

10 家 × 7 槽 = **70 个槽位全部有状态**：65 个 `COLLECTED_IDENTITY_VERIFIED`、5 个 `NOT_TRIED`（全部来自 920011 上市前空目录，`listing_date` 未知）。
校准**抓到 6 个采集器缺陷**（其中 2 个会让全池季度资料静默缺失、1 个会删除真原件），已修并复跑；**原件根已按用户指示迁到 D 盘**（`sources/collection` 目录联接 → `D:\StockResearchLab\IndustryInflectionLab\robotics_data\collection`），本次 183 MB 全部落在 D 盘，C 盘剩余未变（38 GiB）。
Drive 三步探测仍是 `ACCESS_BLOCKED`（302→ServiceLogin / 403 / 401），**没有产生任何 VERIFIED 回执**。

## 二、交付

| 文件 | 内容 | 规模 |
|---|---|---|
| `runs/issues/P07/calibration_assignment.csv` | 冻结的 10 家名单：市场、代码段、前导零、历史代码、上市前标记、旧财务、选样轴与理由、计划槽位 | 3.3 KB |
| `runs/issues/P07/calibration_coverage.csv` | 70 行逐槽覆盖：状态、复用来源、document_id、字节、页码、身份校验结论、HTTP 状态、断点偏移 | 31.3 KB |
| `runs/issues/P07/calibration_review.json` | 验收对照、覆盖率、容量、Drive、续传、6 条发现、限制 | 22.6 KB |
| `runs/issues/P07/collector_patches.json` | 6 个采集器缺陷：症状 / 证据 / 修法 / 影响面 / 风险 | 5.3 KB |
| `runs/issues/P07/capacity_calibration.json` | 三类字节实测分布 + 核心槽重算 + 缓存水位 | 20.6 KB |
| `runs/issues/P07/collection_config_v1.json` | 派生配置（COLLECTOR_V1 + 8 条覆盖项，含 D 盘根与共享台账） | 16.3 KB |
| `runs/issues/P07/drive_probe.json` | Drive 三步探测原始结果 | 2.0 KB |
| `runs/issues/P07/resume_test.json` | 断点续传实测（截断 40% → Range 206 → 哈希一致） | 0.5 KB |
| `runs/issues/P07/revalidation.json` | 校验器修正后的本地复检与状态变化留痕 | 0.2 KB |
| `runs/issues/P07/self_check.json` | 10 项可复算自检 | 17.0 KB |
| `runs/issues/P07/run_result.json` | 最后一次运行结果（0 次 HTTP，全部命中台账） | 15.3 KB |

代码：`tools/p07_calibration.py`（冻结/跑批/续传测试/Drive 探测/复检/容量/验收/自检/清单）。
共享产物：`runs/collection/checkpoint/*.json`（10 家台账）、`runs/collection/ledger_manifest.json`、`runs/collection/run_log.jsonl`。

## 三、名单：为什么是这 10 家

| 证券 | 简称 | 板 | 代码段 | 选样轴 |
|---|---|---|---|---|
| SZ:000026 | 飞亚达 | 深主板 | 000 | 前导零 + 无既有资料 |
| SZ:002031 | 巨轮智能 | 深主板 | 002 | 前导零 + 复用 P05 台账（annual_2025、h1_2026） |
| SZ:001306 | 夏厦精密 | 深主板 | 001 | 前导零 + 上市前招股书数据 + 复用登记表原件 |
| SZ:300024 | 机器人 | 创业板 | 300 | 池内最大段 + 简称与行业词同名 |
| SZ:301000 | 肇民科技 | 创业板 | 301 | 次新段 + 简称不是全称连续子串（F3 由此暴露） |
| SH:600699 | 均胜电子 | 沪主板 | 600 | 沪市 + 复用登记表原件 |
| SH:603667 | 五洲新春 | 沪主板 | 603 | 沪市 + 复用登记表原件 |
| SH:688218 | 江苏北人 | 科创板 | 688 | 科创板 + 台账与登记表同哈希（双来源一致） |
| BJ:920207 | 众诚科技 | 北交所 | 920 | 历史代码 835207 + 登记表 9 份 + 模板式封面（F5） |
| BJ:920011 | 晨光电机 | 北交所 | 920 | 缺资料（FINANCIAL_DATA_MISSING、登记表 0 份、上市前空目录） |

覆盖：沪 3 / 深 5 / 北 2；代码段 9 个（000/001/002/300/301/600/603/688/920）；前导零 3 家；历史代码 1 家；上市前 1 家；无财务快照 1 家；已有资料 6 家。

## 四、覆盖率：65/70，5 个空槽全是“上市日期未知”

| 市场 | 槽位 | 已取得 | 说明 |
|---|---:|---:|---|
| 深 | 35 | 35 | 含 301000 的 6 个核心槽（修复后全部 VERIFIED） |
| 沪 | 21 | 21 | 含 3 个季度槽（沪市标题带“第”字） |
| 北 | 14 | 9 | 920207 全部取得；920011 只有 h1_2026 与 q1_2026，其余 5 槽空目录 |

| 状态 | 槽数 | 含义 |
|---|---:|---|
| `COLLECTED_IDENTITY_VERIFIED` | 65 | 七项校验全过（含 PDF 可读、页数、主体、报告期、全文形态） |
| `NOT_TRIED` | 5 | 目录已完整检索但无该期全文；`listing_date` 未知 → **不判未披露、不判不适用** |

复用：**P05 台账 4 槽**（002031×2、688218、920207）、**登记表本地原件 3 槽**（001306/600699/603667 的 annual_2025）、**本卡新下载 63 槽**。
复用全部 **0 次 HTTP**（`self_check.SC5` 用“本轮 call_log 是否出现同一 URL 的下载请求”反向验证，违规 0）。

## 五、抓到的 6 个采集器缺陷（本卡最重要的产出）

| ID | 缺陷 | 若不修的后果 | 影响面 |
|---|---|---|---|
| F1 | 深/北季度标题是「2026年**一季度报告**」，沪市是「2026年第**一**季度报告」；正则要求“第”字 | 664 家（SZ 602 + BJ 62）× 4 个季度槽 = **2656 槽**静默判为“无该期全文” | 全池季度 |
| F2 | 前 3 页合计 200 字就认为“正文够用”，版式化封面拿空格去比简称 | 北交所 2024/2025 半年报全部误判 MISMATCH | BJ 62 家历史报告期 |
| F3 | 只认“简称连续子串”或“股票代码”；深市年报封面不印代码 | 简称是全称缩写的公司（如 301000 肇民科技）全部误判 | 全池未知比例 |
| F4 | 判 MISMATCH 时直接 `unlink` 已下载原件 | 误判即删原件，只能重下；首轮实测删了 8 份 | 全部采集 |
| F5 | 主体只查前 3 页；北交所 2026 半年报封面是**未填充模板**，简称在第 6 页 | 北交所 2026 半年报全部判主体不符 | BJ 62 家 2026H1 |
| F6 | 把“没找到”当“不符”（MISMATCH） | 首轮 9 个 MISMATCH **全部是本公司文件** | 全部采集 |

修法：`年第?[一三]季度报告`；主体检索放宽到前 8 页（报告期仍只用前 3 页）；简称→代码→字号三级匹配且命中方式留痕；抽取不足记 PENDING；只有“正文出现别的年份同类报告”这种**反证**才判 MISMATCH；MISMATCH 不再删原件（改名 `.pdf.rejected`）。
**未改动**：槽位定义、分页与 `totalAnnouncement` 对账、限速、熔断、重试预算、`runs/issues/P05/collector_config.json`。

## 六、存储：原件改存 D 盘（用户 2026-10-26 指示）

| 项 | 值 |
|---|---|
| 原件根 | `sources/collection/originals` → **D:\StockResearchLab\IndustryInflectionLab\robotics_data\collection\originals** |
| 挂接方式 | Windows 目录联接（`mklink /J`），仓库内路径不变，`Path.relative_to(root)` 不受影响 |
| 本次落盘 | 原件 **183 MB** / 原始响应 161 KB / orgId 缓存 640 KB，全部在 D 盘 |
| C 盘 | 剩余 **38 GiB**（与开跑前一致，未增加） |
| D 盘 | 剩余 **161 GiB** |
| 台账/索引 | `runs/collection/checkpoint`、`runs/collection/collection_index.csv`、`runs/collection/run_log.jsonl`（小文本，入库） |
| 入库红线 | `sources/**`、`*.pdf` 仍被 `.gitignore` 排除；`git ls-files` 二进制 0 |

为什么不是简单改一个相对路径：采集器用 `part_path.relative_to(self.root)` 记录断点，把绝对路径写进 `local_original_root` 会直接抛 `ValueError`；用目录联接可以让“物理在 D 盘、逻辑在仓库内”同时成立，且对 P05 的台账路径无影响。

## 七、容量：三类字节都有实测了

| 类别 | n | 中位 | p25—p75 | 与 P06 对比 |
|---|---:|---:|---|---|
| 年报全文 | 27 | **2,819,684 B** | 1,613,250—4,583,114 | P06 2,110,208（n=74）→ **+33.6%** |
| 半年报全文 | 28 | **2,111,476 B** | 1,324,499—3,662,142 | P06 2,449,992（n=4）→ −13.8% |
| **季度报告** | **10** | **225,413 B** | 163,279—384,508 | P06 **UNMEASURED** → 已有实测 |

- 核心槽全池估算（`1054 × (3×年报中位 + 3×半年报中位)`）= **14.52 GiB**，P06 中位估计 13.43 GiB，量级一致。
- 状态从 `PRE_CALIBRATION_ESTIMATE_NOT_FACT` 改为 `CALIBRATED_FROM_10_COMPANIES`；**n=10 是样本不是普查**，对外引用必须带 n。
- 极端样本：002031 h1_2024 = **48.9 MB**（疑似扫描件），不影响中位数，但单批缓存峰值要按 p75 以上留量。
- 滚动缓存上限 8 GiB 仍成立：本次 183 MB，远低于上限；单批 100 家按中位约 1.7 GiB/批（3 年报 + 3 半年报 + 季度），落在 8 GiB 内。

## 八、断点续传与失败恢复

`resume_test.json`：取 002031 h1_2024（48.9 MB），截断到 40%（19,548,843 B）写成 `.part`、删掉正式文件、重跑同槽位：

- HTTP **206 Partial Content**，`resumed_from=19,548,843`，只发 **1 次**请求；
- 最终 `sha256` 与截断前完全一致（`6d9132bf…8ba3d2`）；
- `.part` 无残留，状态回到 `COLLECTED_IDENTITY_VERIFIED`。

## 九、Drive：三步探测仍不可用

| 步骤 | 请求 | 结果 |
|---|---|---|
| 1 列目录（页面） | `GET /drive/folders/<root>` | **302** → `accounts.google.com/ServiceLogin` |
| 1 列目录（API） | `GET /drive/v3/files/<root>` | **403** |
| 2 上传 | `POST /upload/drive/v3/files` | **400/403**（无凭据） |
| 3 回读（子项） | `GET /drive/v3/files?q=…in parents` | **403** |
| 3 回读（文件页） | `GET /file/d/<id>/view` | **401** |

结论 `ACCESS_BLOCKED`：本卡未上传、未声称任何目录“已核实”、未产生任何 `VERIFIED` 回执。
P06 交接的第 5 条“首个 VERIFIED 回执落库后才放开 M00_01”**未达成**——这是外部权限阻断，不是采集器缺陷；M00 可以先用“本地 D 盘原件 + 索引 + 台账”推进，归档态一律留 `UPLOADED_UNVERIFIED`/未产生。

## 十、验收对照

| 验收标准 | 结果 | 证据 |
|---|---|---|
| 10 家均有采集状态，市场覆盖与特殊边界充分；只核文件/数据可用性 | **PASS** | 70/70 槽有状态；沪 3/深 5/北 2；9 个代码段；前导零 3、历史代码 1、上市前 1、无财务 1、已有资料 6 |
| 校准命中的文档后续不重复下载，队列证券总数仍为 1054 | **PASS** | 共享台账 `runs/collection/checkpoint`（M00 沿用）；7 个复用槽 0 次 HTTP；`intake_company_queue.csv` 1054 行 / 1054 唯一 |

自检 10/10 PASS（`self_check.json`）：名单覆盖、槽位无残留、队列 1054、原件根在 D 盘、复用 0 HTTP、续传哈希一致、容量带样本量、Drive 有结论、仓库无二进制、无业务判断。

## 十一、限制与未做

- **n=10 不是普查**：字节中位数、误判率都只能当样本；全池仍可能出现本次没覆盖的版式（如纯图片扫描、B 股、CDR）。
- **季度只跑 q1_2026**：`q3_2026` 法定披露期 2026-10-31 晚于截止日，未跑；其余季度槽未纳入本次 7 槽。
- **ST/\*ST、退市整理、B 股未纳入** 10 家；`*ST` 简称变更是否影响主体匹配未验证。
- **未做网络中断注入**：续传只测了“进程中断后重跑”，5xx/超时中断沿用 P05 的 10 项故障注入结论。
- **`listing_date` 仍 1054/1054 UNKNOWN**：920011 的 5 个空槽只能记 `NOT_TRIED`，不能写“未披露”。
- **登记表级幂等（P05 配置 lookup_order[2]）仍未进代码**：本卡用台账种子兜住 3 槽；M00 前建议补进采集器，否则 68 份 2025 年报会被重下。
- **校验器修正后的状态变化**依赖 `revalidation.json` 逐条追溯，不是重新下载核验。
- **SELF_CHECK，非独立审计**。

## 十二、放行范围与下一张

放行 **M00_01—M00_11**，前提三条：
1. 用 `runs/issues/P07/collection_config_v1.json` 派生参数（原件根 D 盘、台账 `runs/collection/checkpoint`），不要另起台账；
2. 单批滚动缓存 ≤ 8 GiB，批内“下载 → 索引 → 清理”，不跨批堆积；
3. 归档态在 Drive 可用前一律不写 `VERIFIED`。

不放行：业务结论、指标筛选、估值、把 10 家校准当成 1054 家已采。

## 十三、复跑方式

```bash
PY="C:/Users/zhangjianmei/.workbuddy-ai/binaries/python/versions/3.13.12/python.exe"
$PY -X utf8 tools/p07_calibration.py --freeze       # 名单 + 派生配置 + 台账种子（幂等）
$PY -X utf8 tools/p07_calibration.py --run          # 实跑 10 家 7 槽（已跑过则 0 次 HTTP）
$PY -X utf8 tools/p07_calibration.py --resume-test  # 断点续传实测（会重下一次被截断的文件）
$PY -X utf8 tools/p07_calibration.py --probe-drive  # Drive 三步探测
$PY -X utf8 tools/p07_calibration.py --finalize     # 覆盖表 / 容量 / 验收 / 自检 / 清单
```

只读输入：`PROJECT_STATE.json`、`data/company_master.csv`、`data/document_registry.csv`、`data/intake_company_queue.csv`、`runs/issues/P05/collector_config.json`、`runs/issues/P06/storage_plan.json`、`runs/issues/P03/source_circuit_policy.json`。
