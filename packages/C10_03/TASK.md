# C10_03：分组粗筛

状态：PLANNED。依赖：C00_PILOT_01校准规则已验收。公司数：20。截止日：2026-10-24。

使用2025年报主营/产品章节，必要时补2026中报或正式IR；不做财务预测或估值。单家公司约10—15分钟的检索预算，原文受阻及时HOLD。

本包名单：中国中铁(601390)、中国能建(601868)、全筑股份(603030)、热威股份(603075)、华翔股份(603112)、建研院(603183)、立航科技(603261)、南都物业(603506)、振江股份(603507)、荣泰健康(603579)、中曼石油(603619)、畅联股份(603648)、奇精机械(603677)、福龙马(603686)、天安新材(603725)、隆鑫通用(603766)、永安行(603776)、正和生态(605069)、金达莱(688057)、中信博(688408)

1. 只处理 assignment.csv 中的公司，证券代码按文字保留。routing 是查找资料的线索，不是已证实的业务。
2. 先读仓库 AGENTS.md、docs/执行规则.md、docs/阶段与验收.md。继承材料见 archive/，查找入口见 data/resource_map.csv。
3. 每处理一家公司就保存结果，不必等全包完成。新结果写本包 results/，原 assignment.csv 和 archive 不覆盖。
4. 粗筛提交 results/screening.csv；补证/细筛提交 results/evidence.csv 和 results/product_lines.csv；所有包提交 results/缺口.csv 与 results/交接.md。使用 templates/ 的表头。
5. 完整PDF、扫描件、大型表格和交接ZIP归档Google Drive，按docs/Google Drive资料归档流程.md执行；sources/inbox只作可选本机缓存。先查data/document_registry.csv避免重复下载，登记document_id、官方URL、真实Drive链接/ID、报告期、披露日和物理页。AI通过已连接Drive获取完整原文；读不到记ACCESS_BLOCKED/HOLD并补本包附件，不要求公开分享。GitHub仅放关键证据与索引，不能把链接或摘要当全文已读。
6. 找不到路径先看 data/resource_map.csv；找不到原文约15分钟就登记 data/manual_requests.csv，状态 HOLD，不编造、不以失败作无业务。
7. 交付状态只写 REVIEW_PENDING。验收人逐项核原文后另写 review.json；通过的公司单独进入下一步，有缺口的公司留在本步骤。

完成标准：每家公司都有状态；每个非未知结论都有同主体、同产品、同时间原文依据；列清完成/待补/未处理数量。包名表示计划，不表示研究已执行。
