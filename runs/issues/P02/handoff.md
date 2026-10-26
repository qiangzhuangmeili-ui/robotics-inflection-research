# P02 交接：盘点现有 Drive、本机与旧研究库

- **issue**：#13 / P02，plan_version `20261026_collection_first_v2`
- **执行者**：WorkBuddy AI（执行与自检同一主体，见 review.json 的 SELF_CHECK 标注）
- **起止**：2026-10-26T14:02 领取 → 2026-10-26T14:05 完成
- **输入基线 commit**：`555f416`
- **依赖**：P01（#12），review.json 为 `SELF_CHECK_PASS`，放行范围含 P02

## 一、本卡做了什么

把四类来源合成一份可复用资产清单：**Drive 目录快照**（用户提供）、**本机缓存**（3 个目录 64 份 PDF）、**旧研究库**（68 个包 / 24 个结果文件 / 27 个仓库文本资产）、**财务快照**（1054 行 × 50 列）。只盘点、只建索引，不重新认定业务，不移动或删除任何原件。

## 二、交付

| 文件 | 内容 |
|---|---|
| `runs/issues/P02/existing_assets.csv` | 226 条资产，26 列 |
| `runs/issues/P02/existing_field_coverage.csv` | 47 个字段的逐字段覆盖 |
| `runs/issues/P02/reuse_manifest.json` | 汇总、阻断项、四项验收计数 |
| `tools/p02_inventory.py` | 只读生成器，可复算 |

## 三、四项计数（验收要求分别计数）

| 口径 | 数量 | 说明 |
|---|---:|---|
| 文档数 | 100 | 登记表全部行 |
| 唯一数（document_id） | 100 | 无重复 ID |
| 唯一数（内容 SHA256） | 87 | 13 条无哈希，故少于文档数 |
| 已读取数（AI_READ_CONFIRMED） | 24 | AI 真读到原文并核过物理页 |
| **已业务验收数（VERIFIED_INDEPENDENT）** | **0** | 从未做过独立复核 |

**这四个数不能互相替代**：已归档 ≠ 已读取，已读取 ≠ 已验收。

## 四、资产清单构成

| 类型 | 条数 |
|---|---:|
| REGISTERED_DOCUMENT | 100 |
| RESEARCH_PACKAGE | 68 |
| REPO_TEXT_ASSET | 27 |
| RESEARCH_RESULT_FILE | 24 |
| VALIDATION_REPORT | 6 |
| FINANCIAL_SNAPSHOT | 1 |
| **合计** | **226** |

复用判定：`REUSE_INDEX_ONLY` 142、`REUSE_WITH_LIMITS` 43、`REUSE_AS_IS` 30、`HOLD_PENDING_VERIFICATION` 11。

## 五、关键核对结果

1. **本机 64 份 PDF 哈希全部对得上**：64/64 `MATCH`，0 `MISMATCH`。说明本机缓存与登记表记录的是同一批字节。
2. **本机无未登记文件**：3 个缓存目录共 64 份 PDF，全部已被登记表引用，`unregistered_extras = 0`。
3. **Drive 目录快照与登记表完全对齐**：87 个唯一（代码+文件名）组合全部能在登记表找到，`unmatched = 0`。另有 8 条是重复文件夹导致的重复条目，不是新文件。
4. **10 条登记项在 Drive 看不到同名文件**，全部是合理情况：官网文章 4 条、招股说明书、年报摘要、股东会材料、上市披露、中标公示、合同转录——这些本就不以 PDF 存在公司文件夹里。
5. **重复文件夹 3 组**：`920418 苏轴股份 2025年度 ×3`、`920207 众诚科技 2026H1 ×3`、`920491 奥迪威 2026年度_投资者关系 ×3`。去重时不得当成多份不同文件。
6. **空文件夹 7 个**：属「建了但没传」，不是「公司未披露」。

## 六、财务快照逐字段覆盖

文件：`C:\Users\zhangjianmei\Documents\ChatGPT\机器人企业行业拐点研究\collection_run_20261026\raw\既有候选池财务快照.csv`
1054 行 × 50 列，SHA-256 见 manifest。

| 字段组 | 字段数 | 覆盖率区间 |
|---|---:|---|
| 营业收入 | 6（2021—2025 + 2026H1） | 92.98%—94.12% |
| 归母净利润 | 6 | 同上 |
| 毛利率 | 6 | 同上 |
| 扣非归母净利润（单季） | 22（2021Q1—2026Q2） | **80.17%—94.12%** |

最低的是 `deducted_np_parent_cny_20210331`（845/1054，80.17%），最高的是 `deducted_np_parent_cny_20231231`（992/1054，94.12%）。**越往前覆盖率越低**，2021 年那几期缺口最明显。

**P00 契约要求、但快照完全没有的 7 个字段**：经营活动现金流净额、应收账款、存货、营业成本/毛利额、实际披露日、上市日期、单季度营收。

这解释了为什么 P00 的契约里写着「缺字段单独标记」——**这 7 个必须靠 P05 采集补，不能靠现有快照**。

## 七、阻断项

**Drive 二进制回读与哈希校验做不了。**

- 原因：本机未安装 Google Drive 连接器；实测私有链接返回 302 登录跳转、文件返回 401
- 影响：90 条有 `drive_file_id` 的记录无法回读；73 条 `UPLOADED_UNVERIFIED` 无法转 `VERIFIED`
- 本卡处理：**没有假装做到了**。这些行的 `sha256_match = NOT_COMPUTED`，`reuse_decision = REUSE_INDEX_ONLY` 或 `REUSE_WITH_LIMITS`，`limitations` 里明写「本会话无 Drive 权限，无法回读」
- 解锁：装 Drive 连接器，或手动下载到本地目录

## 八、限制

1. **Drive 目录来自用户贴的文本快照，不是 API 列举**。只能证明「存在同名文件」，不能证明可打开、是全文、身份正确。
2. **64 份本机 PDF 的路径是机器绝对路径**，全在仓库外。换机即失效。建议后续迁入 `sources/` 或上传 Drive 后清理缓存——但**不得删除唯一原件**。
3. **27 个仓库文本资产里有 3 个是「指针」而非内容**（`sources/`、`archive/toolbox_guide.md`、`data/document_registry.csv`），清单里已按实际路径记录。
4. **68 个研究包只有 4 个有结果文件**，其余 64 个只有 TASK.md 和 assignment.csv，标 `SHELL_ONLY_NO_RESULTS`。
5. **P01 的迁移方案仍未执行**，`document_registry.csv` 一字未改。

## 九、验收结论与放行

- 两条验收标准对照见 `review.json`，结论 **SELF_CHECK_PASS**。
- **放行**：P06（#17，容量/目录/归档规则——本卡给出了真实资产规模）、P07（#18，十家校准——可复用本卡的本机文件做输入）。
- **不放行**：任何业务结论采用、指标筛选。
- **声明**：自检由执行者本人完成，不是独立审计。

## 十、下一步建议

1. **P04（#15）建议优先**：财务口径定义不依赖 Drive，且本卡已把快照的真实字段摊开——P04 可以直接照这 47 行写规则。
2. P03（#14）通通道，解决「新文件怎么下来」。
3. 装 Drive 连接器后，建议开一张补验卡，把 73 条 `UPLOADED_UNVERIFIED` 逐个转 `VERIFIED`。


## 2026-10-26 Codex 接续收尾（以本节更新Drive阻断项）

用户明确指定由Codex补完Drive部分。使用已连接的私有Drive工具读取90条登记文件的真实元数据，取得90份原始PDF并保存到仓库忽略的sources/drive_readback_20261026/。90/90可解析且大小匹配；87/87旧SHA-256及87/87旧页数匹配，另3份此前无哈希/页数，本轮实算并保留NO_BASELINE_HASH。51份首页登记标题精确匹配，39份在前6物理页核对主体、年份及报告类型要素。

未精读业务、不新增业务独立验收、不改原登记表或旧归档/AI读取状态。官方源同源性和完整正文/关键页核读仍独立记录。P02原先的Drive访问阻断在Codex当前会话已解除；不能推断WorkBuddy也获得了连接能力。

计数澄清：原登记表73条UPLOADED_UNVERIFIED，另3条UPLOADED_AND_TEXT_READ经P01保守归一后，P02清单计76条。90条Drive记录=73+14+3。旧交接中的87个文件名匹配说法由reuse_manifest的90个唯一文件名匹配口径更正；87为已有内容哈希数，非Drive记录总数。

本卡范围已收尾，技术核验结论SELF_CHECK_PASS。P07仍需其余依赖全部通过，不因P02单卡通过而提前放行。下一步按用户指定转P03 #14；P04仍待办。详情见drive_followup_summary.json、drive_readback_checks.csv/json；旧输出在workbuddy_baseline_*保留。
