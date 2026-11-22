# S06 早期储备与缺数据观察交接（#41，返修轮 R2）

- 执行者：Antigravity
- 复核方：Codex（待 R2 独立复核）
- 计划版本：`20261026_collection_first_v2`
- 知识截止日：`2026-10-25`
- 放行依据：`runs/issues/S06/release_20261122.json`、`runs/issues/S06/handoff_from_s05_20261122.md`
- 返修依据：`runs/issues/S06/codex_review_s06_20261122.md`、`runs/issues/S06/codex_review_s06_r1_20261123.md`（本地复核溯源引用，非运行必需输入）
- 性质：执行方自检（`SELF_CHECK`），**不等同独立验收**；待 Codex 复核通过后再决定是否验收与放行 S07。

---

## 一、本轮针对 Codex 复核意见的逐项修订（R1 + R2）

1. **R2 发布复现与哈希口径修正（对应 R1 复核第 1 节）**：
   - 将未进入 Git 提交的本地复核记录移出运行必需输入清单，转入 `manifest.json` 的 `review_provenance_refs`；运行时实际读取的全部 **33 份输入文件**（含 `data/document_registry.csv`）100% 位于目标 Git 提交树内。
   - `manifest.json` 显式采用 `input_hash_basis = CANONICAL_LF_BYTES`（对文本输入统一按 `
 -> 
` 规范化字节计算字节数与 SHA-256，消除 Git blob 与 Windows CRLF 检出换行差异），全部交付文件以纯 LF 写入（`deliverable_hash_basis = EXACT_BYTES_LF`），支持从干净 Git 提交独立重放 `step_s06_build.py` 与 `step_s06_verify.py` 逐字节复现全部交付、清单与根摘要。
2. **R2 埃夫特 `SH:688165` Yobot R1 原页绑定修正（对应 R1 复核第 2 节）**：
   - 直接核读本地归档 2025 年报原文 `DOC-586ED2C18DB28CDE`（277 页，SHA-256 `586ed2c18db28cdeb8b2df23bc9dc8ff995ec33bc37895c885b5e9aa8e426517`，与 `data/document_registry.csv` 一致）：绑定**物理/印刷第 32 页**（2025 年 2 月发布第一款人形机器人 Yobot R1 和 Yobot W1 并配具名产品图）为 S1 样机观察的决定性原页；绑定**物理/印刷第 25 页**支撑安徽省第十二届工业设计大赛金奖事实；保留**物理/印刷第 19 页（`R1B1-E001`）**作为截至 2025-12-31 尚未量产的状态边界（不支持外部试点、销售或该型号量产）；工业机器人整机 S4（`R1B1-PL001`）继续作为单独已核产品线保留。
3. **沿用已复核通过的 R1 修订（1.1–1.4）**：
   - 德昌股份 `SH:605555`（移出 S3，采用物理第 12 页 `C00-EV-605555-03`）、宁波韵升 `SH:600366`（同步采用物理第 11 页 `C00-EV-600366-03`，规模/收入/订单金额留 `UNKNOWN`）、富佳股份 `SH:603219`（上市母公司 ODM 与参股芯禾分离）、华勤/捷昌/埃夫特/新时达多产品线全量保留、24 家物理页码补齐、南特科技 `BJ:920124` 仅采用官方原文 `R1A02S-E001`（物理第 41 页）、重进条件分列主线重进与业务核证目标、4 家截止日后隔离公司显式标明隔离期诊断。

---

## 二、R2 重算结果汇总

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
