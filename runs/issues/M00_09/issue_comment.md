## M00_09 执行结果（自检 SELF_CHECK_PASS，4/4 验收项通过）

**名单**：100 家，官方 `intake_batches/M00_09/assignment.csv`；**沪市**（**科创板 688 段 65 家** + 605 段 20 + 603 段 15），无 ST。**科创板首批。**

**结果**：7 槽/家 = 700 槽，**全部 `COLLECTED_IDENTITY_VERIFIED`**
- 零 NOT_TRIED、零 PENDING、零未披露、零源失败、零上市前不适用
- 1.63 GB 落 D 盘

这是继 M00_04 之后第二批完全干净的，而且难度更高——科创板是本轮第一次成批出现。**M00_07 修的 F14（沪市标题分层解析）在本批直接生效**，没有出现「目录无该期全文」或「只找到摘要」。

### F16：季度报告标题漏字

只有 1 个槽位异常：688057 金达莱 q1_2026 判「已上市却目录无该期全文」。查目录发现巨潮把标题写成了「2026年第一季度**报**」——漏了一个「告」字。

季度正则从 `季度报告` 放宽为 `季度报(?:告)?`，并补上 `[一二三]季报` 写法。补采后拿到 158 KB / 12 页的正式季报。

这属于数据源录入瑕疵，不是系统性问题，但容错成本几乎为零。

### 交付

`runs/issues/M00_09/` 下 coverage.csv(700)、document_receipts.csv(700)、field_coverage.csv(1300)、automatic_failures.csv(0 行)、checkpoint.json，另 handoff.md / manifest.json / review.json / collector_patches.json / recollect_pending.json / run.log。

提交：`b96c022`
