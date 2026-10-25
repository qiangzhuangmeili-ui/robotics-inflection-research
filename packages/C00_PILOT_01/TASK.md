# C00_PILOT_01：粗筛尺度校准

状态：READY。依赖：无；先完成并验收再开其余C包。公司数：10。截止日：2026-10-24。

10个线索组各选1家试跑，只回答是否有明确对外机器人业务、具体产品和原文，确定ADVANCE/HOLD/DEFER规则。

本包名单：巨轮智能(002031)、汉宇集团(300403)、机科股份(920579)、宝信软件(600845)、德昌股份(605555)、伟创电气(688698)、宁波韵升(600366)、睿能科技(603933)、威贸电子(920346)、新睿电子(920211)

1. 只处理 assignment.csv 中的公司，证券代码按文字保留。routing 是查找资料的线索，不是已证实的业务。
2. 先读仓库 AGENTS.md、docs/执行规则.md、docs/阶段与验收.md。继承材料见 archive/，查找入口见 data/resource_map.csv。
3. 每处理一家公司就保存结果，不必等全包完成。新结果写本包 results/，原 assignment.csv 和 archive 不覆盖。
4. 粗筛提交 results/screening.csv；补证/细筛提交 results/evidence.csv 和 results/product_lines.csv；所有包提交 results/缺口.csv 与 results/交接.md。使用 templates/ 的表头。
5. 完整PDF、扫描件、大型表格和交接ZIP归档Google Drive，按docs/Google Drive资料归档流程.md执行；sources/inbox只作可选本机缓存。先查data/document_registry.csv避免重复下载，登记document_id、官方URL、真实Drive链接/ID、报告期、披露日和物理页。AI通过已连接Drive获取完整原文；读不到记ACCESS_BLOCKED/HOLD并补本包附件，不要求公开分享。GitHub仅放关键证据与索引，不能把链接或摘要当全文已读。
6. 找不到路径先看 data/resource_map.csv；找不到原文约15分钟就登记 data/manual_requests.csv，状态 HOLD，不编造、不以失败作无业务。
7. 交付状态只写 REVIEW_PENDING。验收人逐项核原文后另写 review.json；通过的公司单独进入下一步，有缺口的公司留在本步骤。

完成标准：每家公司都有状态；每个非未知结论都有同主体、同产品、同时间原文依据；列清完成/待补/未处理数量。包名表示计划，不表示研究已执行。
