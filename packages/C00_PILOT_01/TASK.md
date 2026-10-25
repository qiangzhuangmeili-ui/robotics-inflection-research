# C00_PILOT_01：粗筛尺度校准

状态：REVIEW_PENDING（14份必需PDF已在Drive找到并可提取全文；当前建议分类5 ADVANCE、4 HOLD、1 DEFER；仍待独立验收）。依赖：无；先完成并验收再开其余C包。公司数：10。截止日：2026-10-24。

10个线索组各选1家试跑，只回答是否有明确对外机器人业务、具体产品和原文，确定ADVANCE/HOLD/DEFER规则。

本包名单：巨轮智能(002031)、汉宇集团(300403)、机科股份(920579)、宝信软件(600845)、德昌股份(605555)、伟创电气(688698)、宁波韵升(600366)、睿能科技(603933)、威贸电子(920346)、新睿电子(920211)

1. 只处理 assignment.csv 中的公司，证券代码按文字保留。routing 是查找资料的线索，不是已证实的业务。
2. 先读仓库 AGENTS.md、docs/执行规则.md、docs/阶段与验收.md。继承材料见 archive/，查找入口见 data/resource_map.csv。
3. 每处理一家公司就保存结果，不必等全包完成。新结果写本包 results/，原 assignment.csv 和 archive 不覆盖。
4. 粗筛提交 results/screening.csv；补证/细筛提交 results/evidence.csv 和 results/product_lines.csv；所有包提交 results/缺口.csv 与 results/交接.md。使用 templates/ 的表头。
5. 归档严格按docs/资料保存分级规则.md和docs/Google Drive资料归档流程.md执行：全池候选只做L1索引；本包实际用于判断的文件达到L2原件归档；关键判断达到L3证据链。先查document_registry和Drive防重复，再由AI优先尝试下载官方全文PDF并上传。只有拿到PDF二进制、上传成功并回读核验后才可标已归档；网页文字/镜像/链接不算原件。工具链失败时记录错误、官方入口和目标Drive文件夹，再提出精确人工补件。归档状态和AI读取状态分开填写；保持Drive受限权限。
6. 找不到路径先看 data/resource_map.csv；找不到原文约15分钟就登记 data/manual_requests.csv，状态 HOLD，不编造、不以失败作无业务。
7. 交付状态只写 REVIEW_PENDING。验收人逐项核原文后另写 review.json；通过的公司单独进入下一步，有缺口的公司留在本步骤。

完成标准：每家公司都有状态；每个非未知结论都有同主体、同产品、同时间原文依据；列清完成/待补/未处理数量。包名表示计划，不表示研究已执行。


2026-10-25更新：本轮已通过网页PDF/文本镜像纠正若干过强业务断言，但按仓库规则，网页全文/镜像不替代Drive原件核验；本包仍REVIEW_PENDING，C01未开放。详见results/交接.md与data/manual_requests.csv。
