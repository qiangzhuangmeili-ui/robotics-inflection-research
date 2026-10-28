# A04R / A04返工成果复核（2026-10-28）

结论：已完成大量真实返工，但当前证据不足以认可“11/11全部通过、A04正式放行”。建议局部修正后复验；不推翻已取得资料，不重跑全池。

## 已复核通过

- GitHub两次提交efb7d7e、e293052存在；远端当前验收记录为ACCEPTED_WITH_LIMITS。
- 本地collection_index按CRLF→LF规范化后的Git blob SHA为2b83a3074e7c76b06dd19f68892495970ed3c592，与远端相同。
- 12648槽状态计数11468已核、864未到期、278不适用、38未披露，集合数量成立。11468份已核文档路径均存在，已核台账SHA256无重复。
- A04R和A04/rework两个manifest中的全部交付文件在本地存在且SHA256匹配。本次未重新计算全部原文二进制哈希。
- 公告目录1054条且1054个唯一主体，259440条累计记录，1054条reconciled；关键词原件264条DOWNLOADED且本地文件全部存在。这验证记录和文件存在性，未重核全部网络响应或正文。

## 必须修复：挂牌日被最早披露日替代

位置：tools/a04r_bj_applicability.py:267。以earliest_publish_date > period_end推断公司未挂牌，没有实际挂牌日支撑。neeq_slot_decisions.csv中12条NOT_APPLICABLE_PRE_LISTING使用此推理，须全部重新核对，不能预先断言12条全错。

已与项目既存日期证据直接冲突的至少3槽：
- BJ:920211新睿电子，2024Q3和2025Q1。P03 applicability_review.json登记当前股转挂牌日2024-09-25，均早于对应报告期末；A04R却用最早定期披露日2025-04-25判NA。
- BJ:920238长鹰硬科，2025Q1。既存股转挂牌日2025-03-10早于2025-03-31；A04R却用最早定期披露日2025-04-21判NA。
- BJ:920096嘉晨智能2024Q1亦值得复核：最早目录记录是2024-04-25披露2023年报，不是挂牌日期，不能据此宣称2024Q1尚未挂牌。

修复：以可追溯实际股转挂牌日比较period_end；没有季报但有完整索引时，按适用义务及未披露证据判定；证据不足保留HOLD，禁止为了清零NOT_TRIED硬判NA。重算不适用/未披露分子和取得率。

## 必须修复：验收门槛未验证挂牌日期关系

runs/issues/A04/rework/audit_rework.py:135、291的AC06只检查company_listing_dates中的日期非空，未检查挂牌日和报告期末，也未区分北交所上市日与此前股转挂牌日。finalize_rework.py:35的hard列表还排除了AC06。故目前11/11 PASS不能证明P00的NA有据条件成立。应对所有NA逐行验证正确市场阶段的实际挂牌日期，并让所有必需验收项约束放行。

## 必须修复：财务更正版本链仍未闭环

luna_worker独立只读审计确认264份关键词PDF大小、PDF头、逐份SHA256均匹配，目录集合、9150页及时间窗口均通过；这部分成果可信。

但下载器只处理keyword_hits，不处理financial corrections。神州数码SZ:000034的2025年报：raw_ann/000034/p5.json有原版announcement_id=1225058636（2026-03-31），p3.json有更正版1225367858和更正公告1225367857（2026-06-13）。现台账及对应原件目录仅见更正版，data/runs索引无原版登记或supersedes关联。不能以11183条修订分类统计替代P00要求的ORIGINAL_PDF_PLUS_LINK_TO_SUPERSEDED。

revision_chain_breakdown.json的financial_correction_samples含000048股票发行预案更正、000551股东大会通知更正，非财务报表更正，因此576计数须修正分类后复算。A04R manifest未覆盖此分类文件。应补原版/更正版/更正公告关联与原件处置证据；无法补齐时逐条记有据HOLD和责任项，不宣称更正链完成。

工具a04r_finalize.py:99的截止检查条件status.get('AFTER_CUTOFF_DISCLOSED',0)>=0恒真，应修复；A04返工复验脚本另外有真实日期比较，不能把A04R这一恒真检查描述为截止日有效验证。

## 可随S00保留的限制

年报字段覆盖/1528待办、119交叉校验不匹配、54单位不一致等可在S00标准化中保留字段级HOLD；它们不要求全池重采。半年报/季报字段尚未抽取不能表述为标准化完成。Drive未回读和登记表双轨继续保留限制。更正/重述分类统计不等于已完成原件及原始版—更正版链接，须另核。

## 控制文件注意

data/active_issue.json顶层last_completed/status已放行，但a04_review子字段仍保留旧RETURN_FOR_REWORK及release_S00=false；resume.pending也仍是旧断点。应将旧记录明确标历史并设唯一当前验收指针，避免后续执行器读出相反门槛。

本次仅复核，不修改WorkBuddy成果、不重开issue、不变更远端调度。此为技术复核，不是逐份业务证据独立验收。

