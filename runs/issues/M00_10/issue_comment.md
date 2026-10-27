## M00_10 执行结果（自检 SELF_CHECK_PASS，4/4 验收项通过）

**名单**：100 家，官方 `intake_batches/M00_10/assignment.csv`；688 科创板 92 + **920 北交所 8（北交所首批）**，无 ST。

**结果**：7 槽/家 = 700 槽
- `COLLECTED_IDENTITY_VERIFIED` **646**
- `NOT_APPLICABLE_PRE_LISTING` **28**（次新股，报告期在上市前）
- `NOT_TRIED` **26**（全部是北交所 8 家的股转挂牌期槽位，见下）
- 零 PENDING、零未披露、零源失败
- **应取得 672 槽，取得 646（96.1%）**；1.5 GB 落 D 盘

### F17：季报标题不带年份

688638 誉辰智能 q1_2026 判「已上市却目录空」。标题是「深圳市誉辰智能装备股份有限公司**第一季度报告**」——完全没有年份。季度解析增加第三层兜底：无年份时按披露年份推断（一季报 4—5 月、三季报 10—11 月披露），结果仍要过正文年份校验。

现在年报 / 半年报 / 季报三层都有"无年份"兜底。

### 26 个北交所槽位：平台缺口是真实的，不是采集器缺陷

这 26 槽分布在 8 家北交所公司（920011 5、920022 4、920055 4、920080 4、920091 4、920060 2、920066 2、920002 1），报告期都早于北交所上市日，但公司在**股转系统挂牌期间有定期报告**。

按 P00 `not_applicable_decision_table` 明令「不得因平台不同判不适用」，所以记 `NOT_TRIED` + `APPLICABLE_WITH_DIFFERENT_PLATFORM_NEEQ` + `next_action=SEARCH_NEEQ_ARCHIVE`。

**我实测过同一条路由能不能取到，结论是不能**：
- `column=neeq`（股转列）+ 各自 orgId → `totalAnnouncement` 均为 0
- 改用 `searchkey=公司简称` 在全股转列检索 → 同样为 0

即巨潮股转列**不索引这些主体**。要拿到需按股转代码（8xxxxx，与 920xxx 不同）另建实体映射，从股转/北交所老公告库取。已把这段证据写进 `collector_patches.json` 的 `not_a_defect`，避免 A01 重复踩同一个死胡同。

### 交付

`runs/issues/M00_10/` 下 coverage.csv(700)、document_receipts.csv(646)、field_coverage.csv(1300)、automatic_failures.csv(26)、checkpoint.json，另 handoff.md / manifest.json / review.json / collector_patches.json / recollect_pending.json / run.log。

提交：`6c05108`
