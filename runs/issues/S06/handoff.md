# S06 早期储备与缺数据观察交接（#41）

- 执行者：Antigravity
- 复核方：Codex（待独立复核）
- 计划版本：`20261026_collection_first_v2`
- 知识截止日：`2026-10-25`
- 放行依据：`runs/issues/S06/release_20261122.json`、`runs/issues/S06/handoff_from_s05_20261122.md`
- 性质：执行方自检（`SELF_CHECK`），**不等同独立验收**；待 Codex 独立复核后决定是否放行 S07。

---

## 一、核心结果汇总

1. **全池 1,054 家主键守恒与去重**：
   - S05 主线对照 **278 家** = `quality_pass.csv` **277 家** + `quality_observe.csv` **1 家**（`SZ:000856` 冀东装备）。
   - 上游保留观察入口 `observe_pool_preserved_776.csv` **776 家**。
   - `277 + 1 + 776 = 1,054`，与 `data/company_master.csv` 完全一致。
2. **早期储备观察（`early_stage_watch.csv`）**：共 **54 家**（全部来自 776 非主线池，与 S05 278 主线 **0 重叠**）：
   - `EARLY_RD_PROTOTYPE_SAMPLING`（研发 S0 / 样机 S1 / 送样 S2）：**16 家**
   - `EARLY_PILOT_SMALL_BATCH`（付费试点 / 小批量 S3）：**7 家**
   - `COMMERCIAL_NON_MAINLINE_RESERVE`（已记录 S4 / 商业化产品但未入主线）：**11 家**
   - `EVIDENCED_PRODUCT_STAGE_UNKNOWN`（已核实直接/间接产品存在，阶段标 UNKNOWN）：**20 家**
3. **缺数据观察（`missing_data_watch.csv`）**：共 **379 家** = **378 家非主线 776** + **1 家 S05 主线观察结转**（`SZ:000856` 冀东装备，显式标明不与 776 重复计数；与 S05 277 `quality_pass.csv` **0 重叠**）：
   - `S05_QUALITY_HOLD_CONSOLIDATION_SCOPE_UNKNOWN`：**1 家**（`SZ:000856`）
   - `AFTER_CUTOFF_ISOLATED`：**4 家**（`SH:603448`、`SH:688836`、`SZ:301348`、`SZ:301699`）
   - `PENDING_ANCHOR_RESELECTION`：**1 家**（`SZ:002083`）
   - `S04_HOLD_FOR_DATA_AND_QUALITY_SOURCE_UNKNOWN`：**9 家**
   - `QUALITY_SOURCE_UNKNOWN_NON_MAINLINE`：**6 家**（与上一类合计 = **15 家**质量来源未知）
   - `S04_HOLD_FOR_DATA`：**319 家**（与上面 9 家合计 = **328 家** `HOLD_FOR_DATA`）
   - `S02_METRIC_HOLD_OR_MISSING_NON_MAINLINE`：**39 家**
4. **两表交集与去重并集**：
   - `early_stage_watch.csv` 与 `missing_data_watch.csv` 交集为 **33 家**（已在 `missing_data_watch.csv` 的 `in_early_stage_watch=YES` 标明）。
   - 非主线观察去重并集为 **399 家**（全部属于 776 非主线池）。

---

## 二、与 S05 主线去重清单（已入主线，不重复计入 `early_stage_watch.csv`）

共 **20 家**在历史证据包（`archive/`、B00/C00/D00、早期样本）中有记录但已进入 S05 主线（`S05_QUALITY_PASS`），已按主键去重：

| security_id | 公司简称 | S05 主线路由 | 已有证据来源 |
|---|---|---|---|
| `BJ:920199` | 倍益康 | `S05_QUALITY_PASS` | `ARCHIVE_R1_02B;B00_SOURCE_01` |
| `BJ:920207` | 众诚科技 | `S05_QUALITY_PASS` | `ARCHIVE_R1_02B;B00_SOURCE_01` |
| `BJ:920346` | 威贸电子 | `S05_QUALITY_PASS` | `C00_PILOT_01` |
| `BJ:920491` | 奥迪威 | `S05_QUALITY_PASS` | `ARCHIVE_R1_02A` |
| `BJ:920510` | 丰光精密 | `S05_QUALITY_PASS` | `ARCHIVE_R1_BATCH01` |
| `BJ:920578` | 巨能股份 | `S05_QUALITY_PASS` | `ARCHIVE_R1_02B;B00_SOURCE_02` |
| `BJ:920593` | 鼎智科技 | `S05_QUALITY_PASS` | `ARCHIVE_R1_BATCH01` |
| `SH:688003` | 天准科技 | `S05_QUALITY_PASS` | `ARCHIVE_R1_02B` |
| `SZ:002117` | 东港股份 | `S05_QUALITY_PASS` | `ARCHIVE_R1_02B` |
| `SZ:002354` | 天娱数科 | `S05_QUALITY_PASS` | `ARCHIVE_R1_02B;B00_SOURCE_02` |
| `SZ:002472` | 双环传动 | `S05_QUALITY_PASS` | `ARCHIVE_EARLY_SAMPLE` |
| `SZ:002698` | 博实股份 | `S05_QUALITY_PASS` | `ARCHIVE_R1_02A` |
| `SZ:002747` | 埃斯顿 | `S05_QUALITY_PASS` | `ARCHIVE_EARLY_SAMPLE` |
| `SZ:002768` | 国恩股份 | `S05_QUALITY_PASS` | `ARCHIVE_R1_02B` |
| `SZ:002979` | 雷赛智能 | `S05_QUALITY_PASS` | `ARCHIVE_R1_BATCH01` |
| `SZ:003032` | 传智教育 | `S05_QUALITY_PASS` | `ARCHIVE_R1_02B;B00_SOURCE_02` |
| `SZ:300031` | 宝通科技 | `S05_QUALITY_PASS` | `ARCHIVE_R1_02B` |
| `SZ:300403` | 汉宇集团 | `S05_QUALITY_PASS` | `C00_PILOT_01` |
| `SZ:300607` | 拓斯达 | `S05_QUALITY_PASS` | `ARCHIVE_R1_BATCH01` |
| `SZ:301603` | 乔锋智能 | `S05_QUALITY_PASS` | `ARCHIVE_EARLY_SAMPLE` |

---

## 三、已核查但因概念/意向/证据不足未纳入早期储备的非主线公司（6 家）

| security_id | 公司简称 | 核查来源 | 不纳入理由 |
|---|---|---|---|
| `BJ:920002` | 万达轴承 | `ARCHIVE_EARLY_SAMPLE` | 2024年报抽查段落仅列叉车轴承与回转支承，未见机器人专属产品或研发证据（证据不足记UNKNOWN） |
| `BJ:920198` | 微创光电 | `B00_SOURCE_01` | 2025年报及2026H1全文未命中机器人关键词，主业为交通监控信息化，无机器人产品或研发事实 |
| `BJ:920263` | 中航泰达 | `B00_SOURCE_01` | 2025年报仅披露战略合作意向及唐山地块储备，无研发成果、样机、送样或合同事实 |
| `SH:600699` | 均胜电子 | `ARCHIVE_R1_02B` | 2025新设并表子公司未见产品或收入，人形机器人关联主体为非并表关联方，无上市公司产品/研发事实 |
| `SH:603466` | 风语筑 | `ARCHIVE_R1_02B` | 仅2026经营计划与文旅合作探索，未核实已完成的研发、样机或产品事实 |
| `SH:688327` | 云从科技 | `ARCHIVE_R1_02B` | 前瞻生态布局，无自研机器人本体/产品/收入；财报所提机器人为RPA软件 |

另：历史 `archive/R1_batch01_parent_reviewed_20261024` 中的 `BJ:920007`（酉立智能）不在冻结 1,054 家 `company_master.csv` 主表内，已剔除。其余未经过业务精读的非主线公司保持 `UNKNOWN`，不凭概念标签纳入，也不反推精确的“无业务公司数”。

---

## 四、需求先行辅助观察与未决守卫结转

1. **合同负债与可信在手订单（`S06_AUX_LEAD_V1`）**：已按 `METHOD_20261107_LEADING_INDICATORS` 在 `watch_reentry_rules.md` 第四节登记字段定义、来源、期间、适用业务模式、缺失语义与重进条件。因合同负债不在 P04/S00 冻结标准化字段内且无全池结构化在手订单台账，非主线观察行全部如实记 `UNKNOWN`，不填 0、不作全池补抽；合同资产继续与合同负债分列。
2. **未决守卫与 #53 开放态**：4 家截止日后隔离、1 家锚点待重选、15 家质量来源未知、8 项未采用父链提议、S05 专门待核（RH02 129、RH03 19、RH06 7、既有待核 5 家、越界 20 格）全部原样结转；`#53` 保持 OPEN，不采纳 `44/231/378` 历史未冻结统计作为当前派工名单。

---

## 五、限制、环境备注与下一步

1. **限制**：
   - 本轮仅复用已有可追溯证据与 S02/S05 冻结产物，未新增全池采集或逐家企业深研；`archive/` 53 家旧采用、10 家早期样本及 B00/C00/D00 各自保留原有限制与待核状态。
   - 观察名单不是买入推荐或已商业化认定，不跳过 S07/S08 进入估值。
   - 执行方自检（`SELF_CHECK`）不等同独立验收。
2. **环境备注**：本机 git 默认代理 `127.0.0.1:7890` 未启动，拉取/推送远端时临时清代理直连；`gh api` 直连正常。
3. **下一步建议**：提交 Codex 独立复核（核对主键去重、证据定位与事实分层、时间隔离、未决项结转、辅助观察口径登记及每家重进条件）；待 Codex 验收并新增明确放行记录后再推进 S07（#42）。
