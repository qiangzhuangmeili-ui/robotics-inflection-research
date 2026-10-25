# D01_DETAIL_01：业务细筛

状态：PLANNED_CONDITIONAL。依赖：B02参考限制核对；每家公司原文可读并由验收人放行。公司数：5。截止日：2026-10-24。

候选细筛包：只补商业化、付费客户/交付、机器人用途和收入范围。45家仅具备进入细筛的初步业务依据，不等于45家已通过细筛。

本包名单：苏轴股份(920418)、丰光精密(920510)、五洲新春(603667)、秦川机床(000837)、国茂股份(603915)

1. 只处理 assignment.csv 中的公司，证券代码按文字保留。routing 是查找资料的线索，不是已证实的业务。
2. 先读仓库 AGENTS.md、docs/执行规则.md、docs/阶段与验收.md。继承材料见 archive/，查找入口见 data/resource_map.csv。
3. 每处理一家公司就保存结果，不必等全包完成。新结果写本包 results/，原 assignment.csv 和 archive 不覆盖。
4. 粗筛提交 results/screening.csv；补证/细筛提交 results/evidence.csv 和 results/product_lines.csv；所有包提交 results/缺口.csv 与 results/交接.md。使用 templates/ 的表头。
5. 原文存 sources/<证券代码>/，登记文件名、URL、报告期、发布日期和物理页。上传给云端AI时，将本包与通用说明、相关原文一起压缩；仅发 GitHub 链接不能保证其已取得原文。
6. 找不到路径先看 data/resource_map.csv；找不到原文约15分钟就登记 data/manual_requests.csv，状态 HOLD，不编造、不以失败作无业务。
7. 交付状态只写 REVIEW_PENDING。验收人逐项核原文后另写 review.json；通过的公司单独进入下一步，有缺口的公司留在本步骤。

完成标准：每家公司都有状态；每个非未知结论都有同主体、同产品、同时间原文依据；列清完成/待补/未处理数量。包名表示计划，不表示研究已执行。
