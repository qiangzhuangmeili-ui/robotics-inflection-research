# 复制给下一位AI的指令

2026-10-26用户已调整优先级：先尽量一次批量收齐整个候选池的基础财务、定期报告和公告目录，整轮自动尝试/重试后再统一请用户补缺；不要遇到一家公司就补一家公司，也不要先深读全池公告。

先读AGENTS.md、PROJECT_STATE.json、docs/第一轮基础资料批量收集.md和data/intake_batch_index.csv。先复用最新GitHub/Drive索引与本机缓存，校验证券主体/报告期/数据字段，然后分批采集并保留断点。财务数值和原件完整性先查，业务结论后查。所有缺口分清尚未尝试、自动失败、未披露、不适用，不填零。

旧C00/B00等结果和待验收成果保留；当前不要按旧启动指令直接继续逐家公司深挖。基础资料自动轮次结束后，给一份按网站/软件/报告期分组的人工补缺总表，再进行指标宽筛→逐轮收紧→重点公司业务核验。原件存Drive，GitHub只存索引与状态，当前研究截止日按PROJECT_STATE.json执行。

以下保留旧启动说明作为后期业务核验参考；与以上新优先级冲突时，以本段新指令为准。

---


请接手机器人企业行业拐点研究。仓库 https://github.com/qiangzhuangmeili-ui/robotics-inflection-research 是私有仓库，你若打不开就明确告诉我需要哪些附件，不要假称已读取。研究信息截止日2026-10-24。

先读AGENTS.md、PROJECT_STATE.json、docs/执行规则.md、docs/阶段与验收.md和data/package_index.csv。第一次只执行C00_PILOT_01的10家公司，确认为未完成后领取；如果已经完成，则从包顺序表中领取下一个READY且未被占用的包。读取对应TASK.md和assignment.csv，不擅自换公司或扩大范围。

先找现有archive证据、data/resource_map.csv和data/document_registry.csv中的Drive原件；缺原文才补查。只做本包要求的粗筛/补证/细筛，不自动开展估值。找不到原文约15分钟后记HOLD，写明让我用哪个软件、找什么标题/年份、下载什么文件；不能把网页失败当没有业务。

新成果保存在packages/<包ID>/results/。交付每家公司状态、证据、来源定位、缺口和下一步，状态REVIEW_PENDING。缺文件时请列具体相对路径，我可把本包ZIP和PDF作为附件补给你。不要要求云端读取我的D盘或本机127.0.0.1。


原始PDF、扫描图、大型表格与交接ZIP按docs/Google Drive资料归档流程.md归档Google Drive，GitHub只存关键证据和索引。先用真实Drive URL/ID查询元数据，再取得完整原文核读；只有摘要或链接不可当作全文已核验。无法访问就记录ACCESS_BLOCKED/HOLD并列所需附件，不要求公开分享。没有实际上传结果时，Drive URL/ID留空，不声称已迁移。
