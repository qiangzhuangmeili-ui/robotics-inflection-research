# S06 早期储备与缺数据观察交接（#41，返修轮 R1）

- 执行者：Antigravity
- 复核方：Codex（待第二轮独立复核）
- 计划版本：`20261026_collection_first_v2`
- 知识截止日：`2026-10-25`
- 放行依据：`runs/issues/S06/release_20261122.json`、`runs/issues/S06/handoff_from_s05_20261122.md`
- 返修依据：`runs/issues/S06/codex_review_s06_20261122.md`
- 性质：执行方自检（`SELF_CHECK`），**不等同独立验收**；待 Codex 复核通过后再决定是否验收与放行 S07。

---

## 一、本轮针对 Codex 复核意见的逐项修订（R1）

1. **阶段、事实与主体修正（对应 1.1）**：
   - **德昌股份 `SH:605555`**：移出 `EARLY_PILOT_SMALL_BATCH`（移出 S3 计数），改归 `EVIDENCED_PRODUCT_STAGE_UNKNOWN`（`PRODUCT_RAMP_DELIVERY_STAGE_UNKNOWN`）；采用 `C00-EV-605555-03` 物理第 12 页原文定位，不再沿用已纠正的第 11 页。
   - **宁波韵升 `SH:600366`**：同步采用 2026H1 物理第 11 页 `C00-EV-600366-03`（人形机器人领域与头部企业绑定、签订长期协议、完成样品交付与供货），显式保留客户/供货规模/收入/毛利 `UNKNOWN` 边界，不推定 S3/S4 或量化在手订单金额；阶段更新为 `SAMPLING_AND_SUPPLY_SCALE_UNKNOWN`，优先级 `P1_HIGH`。
   - **多产品线保留（华勤技术 `SH:603296`、捷昌驱动 `SH:603583`、埃夫特 `SH:688165`、新时达 `SZ:002527` 等）**：保持每家一行主键去重，新增 `bucket_selection_rule`、`other_verified_stages`、`entity_scope_and_ownership` 与 `all_recorded_product_lines` 四列，完整保留华勤 `R1B02-PL041`(S4)、捷昌 `R1A02-PL013`(S4)、埃夫特 `R1B1-PL001`(S4)、新时达 `R1B1-PL006/007`(S3) 等全部已核产品线、阶段、主体和来源。
   - **富佳股份 `SH:603219`**：按主体分离口径——上市母公司扫地机器人 ODM（`R1B1-PL046`，`stage=UNKNOWN`）归入 `EVIDENCED_PRODUCT_STAGE_UNKNOWN`（`LISTED_PARENT_STAGE_UNKNOWN_WITH_ASSOCIATE_EARLY_OBSERVE`），未并表参股公司芯禾机器人（`R1B1-PL047` S3 / `R1B1-PL048` S1）仅作非并表间接观察保留，不再混入上市主体 S1 计数。
2. **来源定位与采用边界修正（对应 1.2）**：
   - 修复归档登记页码读取逻辑（兼容 `page_physical` 与 `page_or_section`），补回此前为 `UNKNOWN` 的全部 24 家物理页码（包括三协电机物理第 2 页、宇树科技物理第 139 页等）。
   - **南特科技 `BJ:920124`**：将 `OFFICIAL_ORIGINAL_PENDING_DO_NOT_ADOPT` 的旧镜像 `R1A02-E001` 移出采用 `evidence_ids`，降格记录在 `non_adopted_historical_locators`；采用证据仅保留已核官方原文 `R1A02S-E001`（物理第 41 页）。
   - 新增 `primary_evidence_binding` 列，将核心主张与证据 ID、文档/URL、披露日期、物理页和采用状态 1 对 1 绑定；升级 `step_s06_verify.py` 逐项校验同主键、物理页非漏读与零 `DO_NOT_ADOPT` 混入。
3. **输入清单补全（对应 1.3）**：
   - 移除 `step_s06_build.py` 中未使用的 `s04_log` 与 `b00_ev` 读取；在 `manifest.json` 中完整登记脚本实际读取与辅助对照引用的全部 **33 份输入文件**的字节数与 SHA-256。
4. **重进条件与截止日诊断澄清（对应 1.4）**：
   - `early_stage_watch.csv` 将【主线重进（按冻结规则）】与【业务核证目标】分开表述，取消一刀切“单列机器人收入与毛利”模板。
   - `missing_data_watch.csv` 新增 `s02_gap_diagnostic_scope` 列，将 4 家截止日后隔离公司的 S02 裸缺口显式标为 `AFTER_CUTOFF_ISOLATED_DIAGNOSTIC_ONLY_NOT_ADMISSIBLE_BEFORE_R05`。

---

## 二、R1 重算结果汇总

1. **全池 1,054 家主键守恒与去重**：
   - S05 主线对照 **278 家** = `quality_pass.csv` **277 家** + `quality_observe.csv` **1 家**（`SZ:000856` 冀东装备）。
   - 上游保留观察入口 `observe_pool_preserved_776.csv` **776 家**。
   - `277 + 1 + 776 = 1,054`，互斥且等于 `company_master.csv`。
2. **早期储备观察（`early_stage_watch.csv`：共 54 家，全部来自 776 非主线池，与 S05 278 主线 0 重叠）**：
   - `EARLY_RD_PROTOTYPE_SAMPLING`：**15 家**（较初版 16 减 1：富佳股份按上市母公司口径移至阶段待核）
   - `EARLY_PILOT_SMALL_BATCH`：**6 家**（较初版 7 减 1：德昌股份移出 S3 计数）
   - `COMMERCIAL_NON_MAINLINE_RESERVE`：**11 家**（不变）
   - `EVIDENCED_PRODUCT_STAGE_UNKNOWN`：**22 家**（较初版 20 增 2：承接富佳股份与德昌股份）
3. **缺数据观察（`missing_data_watch.csv`：共 379 家 = 378 家非主线 776 + 1 家 S05 主线观察结转，与 S05 277 `quality_pass.csv` 0 重叠）**：
   - 7 类分布与初版完全一致（已由 Codex 独立复算 12,648 格验证通过）：冀东装备 1、截止日后隔离 4、锚点待重选 1、S04 待核且质量来源未知 9、非主线质量来源未知 6、其余 S04 待核 319、其余 S02 HOLD/MISSING 39。
4. **两表交集与并集**：交集 **33 家**，776 池内去重并集 **399 家**。

---

## 三、与 S05 主线去重清单（20 家，不重复计入 `early_stage_watch.csv`）

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

## 四、已核查但未纳入早期储备的非主线公司（6 家）

| security_id | 公司简称 | 核查来源 | 不纳入理由 |
|---|---|---|---|
| `BJ:920002` | 万达轴承 | `ARCHIVE_EARLY_SAMPLE` | 2024年报抽查段落仅列叉车轴承与回转支承，未见机器人专属产品或研发证据（证据不足记UNKNOWN） |
| `BJ:920198` | 微创光电 | `B00_SOURCE_01` | 2025年报及2026H1全文未命中机器人关键词，主业为交通监控信息化，无机器人产品或研发事实 |
| `BJ:920263` | 中航泰达 | `B00_SOURCE_01` | 2025年报仅披露战略合作意向及唐山地块储备，无研发成果、样机、送样或合同事实 |
| `SH:600699` | 均胜电子 | `ARCHIVE_R1_02B` | 2025新设并表子公司未见产品或收入，人形机器人关联主体为非并表关联方，无上市公司产品/研发事实 |
| `SH:603466` | 风语筑 | `ARCHIVE_R1_02B` | 仅2026经营计划与文旅合作探索，未核实已完成的研发、样机或产品事实 |
| `SH:688327` | 云从科技 | `ARCHIVE_R1_02B` | 前瞻生态布局，无自研机器人本体/产品/收入；财报所提机器人为RPA软件 |

另：历史 `BJ:920007`（酉立智能）不在冻结 1,054 主表内，已剔除。其余未深研非主线公司保持 `UNKNOWN`。

---

## 五、限制与下一步

- 本轮仍为执行方自检（`SELF_CHECK`），不等同独立验收；不释放 S07/S08，不改动 `#53` 残余结论。
- 合同负债与可信在手订单按 `S06_AUX_LEAD_V1` 保持 `UNKNOWN`，不填 0，合同资产分列。
- 下一步：提交 Codex 进行 R1 独立复核。
