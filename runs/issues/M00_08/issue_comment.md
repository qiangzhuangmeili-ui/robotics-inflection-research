## M00_08 执行结果（自检 SELF_CHECK_PASS，4/4 验收项通过）

**名单**：100 家，官方 `intake_batches/M00_08/assignment.csv`；**全部沪市 603 段**（603013 亚普股份 → 603890 春秋电子），无 ST。

**结果**：7 槽/家 = 700 槽
- `COLLECTED_IDENTITY_VERIFIED` **667**
- `NOT_APPLICABLE_PRE_LISTING` **33**（12 家次新股，2024—2026 年上市，报告期在上市前）
- NOT_TRIED 0、PENDING 0、未披露 0、源失败 0
- **取得 667/667（应取得口径 100%）**；1.37 GB 落 D 盘

首轮其实是 665 VERIFIED + 2 NOT_DISCLOSED_BY_ISSUER，修完 F15 后两槽也拿到了。

### F15：同期两条同标题行、死链那条体积更大

603015 弘讯科技 h1_2024、603381 永臻股份 h1_2024 首轮判「未披露」，理由「目录有记录但 PDF 返回 404」。查下去发现同一期有**两条同标题「2024年半年度报告」**：

| 公司 | 有效链接 | 死链 |
|---|---|---|
| 603015 | 1221291803（2811 KB，200） | 1220935724（3484 KB，**404**） |
| 603381 | 1221291632（4237 KB，200） | 1220926473（4946 KB，**404**） |

死链那条**体积更大**——F14 的「同标题取大文件」规则正好把它挑中了。而 404 分支又直接写 `NOT_DISCLOSED_BY_ISSUER`，语义上错得离谱：公司明明披露了，是源站文件没了。

修法：
1. `collect_slot` 增加 `exclude_urls`，选择前先剔除已确认 404 的候选；
2. 404 时轮替到同期下一个非摘要候选（递归，最多试 3 个链接），每次轮替写 `fallback_from` 留痕；
3. 全部候选都 404 才判 `SOURCE_FAILED` + `next_action=SEARCH_ALTERNATE_SOURCE`，理由写明「源站文件缺失，非公司未披露」。

这条和 F14 是配对的：**取大规则会放大死链风险，必须有候选轮替兜住**。

### 交付

`runs/issues/M00_08/` 下 coverage.csv(700)、document_receipts.csv(667)、field_coverage.csv(1300)、automatic_failures.csv(0 行)、checkpoint.json，另 handoff.md / manifest.json / review.json / collector_patches.json / recollect_pending.json / run.log。

提交：`52b57d2`
