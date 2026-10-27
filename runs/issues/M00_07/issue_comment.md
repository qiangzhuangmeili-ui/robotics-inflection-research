## M00_07 执行结果（自检 SELF_CHECK_PASS，4/4 验收项通过）

**名单**：100 家，官方 `intake_batches/M00_07/assignment.csv`（sha256 `6bbd0d1c…`）；**沪市 98**（600 段 76 / 601 段 17 / 603 段 5）+ 深市 2（301/302），含 4 家 ST。**沪市首次成批，暴露了两个系统性问题。**

**结果**：7 槽/家 = 700 槽
- `COLLECTED_IDENTITY_VERIFIED` **693**
- `NOT_APPLICABLE_PRE_LISTING` **7**（301699 洛轴股份，2026-09-09 上市，全部报告期在上市前）
- NOT_TRIED 0、PENDING 0、源失败 0
- **取得 693/693（应取得口径 100%）**；1.71 GB 落 D 盘

首轮其实是 664 VERIFIED / 22 NOT_TRIED / 4 SUMMARY_ONLY / 3 PENDING，修完两个缺陷后回收了 29 槽。

### F14（HIGH，沪市系统性）：定期报告标题写法极不统一

旧正则只认深市写法 `(\d{4})年年度报告`。实测沪市有四种变体：

| 写法 | 实例 |
|---|---|
| 少一个「年」 | `2025年度报告全文` |
| 上传件命名带分隔符 | `600704_物产中大_2025年_年度报告20260427` |
| 漏字 | `2023年年报告全文`、`2024年年报-全文` |
| 完全不带年份 | `创力集团半年度报告` |

结果 600845 宝信软件三期年报全部被判「目录无该期全文」，600704 物产中大只找到摘要。

另一层问题：**同一期常有同标题多行**（摘要被标成报告、正文与全文并存）。600860 京城股份有两条「2024年年度报告」，523 KB（7 页）和 4.73 MB（272 页），旧排序按披露日取，选到了前者。

修法：
1. `_period_of` 分层解析——年份可有可无、年与报告类型间允许空格/下划线/连字符、接受「年度报告|年报告|年报」「半年度报告|半年报」；
2. 标题完全无年份时按披露月份推断（半年报 7—12 月→当年 H1，年报 1—6 月→上一年），**推断结果仍要过正文年份校验**，推错只会记 PENDING 不会误判 VERIFIED；
3. 索引行保留巨潮的 `adjunctSize(KB)`，`_select` 改为「非英文 → 修订号高 → 标题含全文 → 体积大 → 披露日晚」；
4. 排除词从只挡「公告」扩到问询/回复/关注函/监管/告知书/说明会/路演。

### F13（MEDIUM）：同一 orgId 下改代码的历史行被当别家拒收

302132 中航成飞 annual_2023、h1_2024 判「已上市却目录空」。实际目录里有两行，但 `sec_code=300114`、`sec_name=中航电测`。

关键证据：**300114 中航电测与 302132 中航成飞的巨潮 orgId 同为 `9900013408`**，同一发行主体。目录是按 orgId 检索的，不可能混入别家。

修法：目录内同时出现本公司现用简称时，代码不同的行按历史行接受（记 `historical_name` / `entity_mapping=SAME_ORG_ID_HISTORICAL_NAME`）；`validate_pdf` 增加 `aliases`，历史简称及其字号作为有效主体证据，命中记 `HISTORICAL_SEC_NAME`。两槽重采后 2.99 MB / 2.54 MB。

### 交付

`runs/issues/M00_07/` 下 coverage.csv(700)、document_receipts.csv(693)、field_coverage.csv(1300)、automatic_failures.csv(0 行)、checkpoint.json，另 handoff.md / manifest.json / review.json / collector_patches.json（含 F13/F14 完整证据）/ recollect_pending.json / run.log。

提交：`1bd472b`
