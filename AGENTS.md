# AI接手必读

## 2026-11-07 已确认的方法分工补充

接手 S04 / S06 / 筛后核验前，必须读 [需求先行指标分工](docs/需求先行指标分工_20261107.md) 和 data/methodology_decision_20261107.json：S04 不新增三项硬筛门槛；合同负债、可信在手订单用于 S06 辅助早期观察（采用前登记口径和版本）；在建工程及订单转化留到筛后核验。缺披露不填 0、不淘汰。此补充不改冻结阈值、截止日、既有验收或当前占用。发布不等于 WorkBuddy 已阅读确认。


这是研究组织仓库。首读README、docs/Issue执行总计划.md、PROJECT_STATE.json、data/issue_execution_plan.csv和data/active_issue.json。用户已授权全池基础资料批量采集；未被明确要求时，不执行全池企业深度调查、不改历史输入、不做买卖建议。一次只领取一个依赖已验收的执行issue；旧包即使READY也不能绕过新门槛。

data/company_master.csv是调度总表；archive/latest_universe.csv是旧验收快照。分组只是检索线索，不能写成事实。公司商业阶段新流程统一UNKNOWN，阶段只在产品线判。旧主表6处公司阶段值在archive与新主表legacy_company_stage列保留供追溯，不作为新流程认定。

53家旧分类附限制采用；7家旧缺2025年报已在Drive读取但业务断言待复验；10家早期样本仅局部断言已核读。不得混算完成数。新研究所有结果先REVIEW_PENDING；验收人有原文核读记录后才放行。若执行者和验收者是同一AI，明确写SELF_CHECK，不能冒充独立审计。

本轮先完成全池资料轮和指标轮验收；之后R00/R01已放行的筛后公司可以局部推进，不必等全部筛后公司研究完成。这不声明旧R1全池已通过，也不放宽证据规则。archive旧标准中“不上传仓库”属于历史任务；本次用户已要求建GitHub仓库，仅上传计划、名单、表格与追溯文本。sources、inbox、PDF、账号密钥不提交。

路径：用仓库相对路径，不依赖用户名/D盘。先查data/resource_map.csv。缺原文检索约15分钟后登记人工请求/HOLD；不得用摘要补成原文。不要声称云端AI能读本机盘或本机127.0.0.1。

资料轮验收后先指标宽筛和逐轮收紧；S08后才由R00给少量公司派5家业务/财务、3家拐点小包。粗筛不估值；预计收入不当作已实现收入。所有日期、主体、报告口径按docs/执行规则.md。


## 原件存储：Google Drive为归档位置

原始PDF、扫描图、财务Excel和交接大ZIP归档Google Drive；GitHub仅存小型文本、证据摘录、关键数字、document_id、官方原文URL与Drive文件ID/链接。sources/inbox为可选本地收集与读取缓存，未归档原件不能因已有摘要就删除。按docs/Google Drive资料归档流程.md执行。

先查data/document_registry.csv，再查官方站点，避免重复下载。原文登记继承templates/来源登记.csv：document_id稳定，drive_file_id与drive_url真实取得才填；同一原文复用ID，不因被多个包引用就重复上传。更正版另存另ID并在limitations关联旧版，不覆盖追溯原件。

AI先通过已连接Drive按真实URL/ID查元数据，再取得完整原文核页码和短引文。用户能打开不代表AI可读；OWNER_ONLY_CHECKED不可当作AI_READ_CONFIRMED，摘要可读不表示完整PDF已核读。无权限或无法取得原文写ACCESS_BLOCKED/HOLD并列补件，不能声称已核实。不要要求将Drive公开，不扩大分享权限。

Drive根目录和分类目录已创建，真实URL/ID见PROJECT_STATE.json与data/drive_folders.csv。64份旧去重PDF和另外8份年报目前已在Drive找到共72份，详见data/document_registry.csv与data/manual_requests.csv。仅8份新年报已核对正文身份；64份旧PDF仅按文件名和元数据匹配，全部云端哈希/官方源及版本仍待核验。不得将文件已上传等同业务证据验收。


## 2026-10-26用户新优先级：先广收资料，再按指标收紧

先执行docs/第一轮基础资料批量收集.md：全池批量匹配现有资料、自动采集与有限重试；缺件先入自动队列，整轮完成后按软件/网站和报告期合并给用户一次补缺表。不要每处理一家公司就催用户补资料，也不要在新批次指标宽筛前继续无边界追客户/订单/履约。已有研究和归档结果全部复用，不回退验收状态。

第一轮仅验证文件与数据可用性，不逐份PDF做业务精读；采用业务结论时仍须按原规则核验。资料收集状态与研究验收状态分别维护。data/intake_company_queue.csv与intake_batch_index.csv为采集调度，不是已经取得报告的证明。旧的“每家找15分钟再人工补件”规则仅用于后期重点公司特殊证据，基础资料遵循整轮汇总。


## Issue计划v2为唯一调度

版本20261026_collection_first_v2，首张P00 #11。先读docs/Issue执行总计划.md和data/issue_execution_plan.json；当前只完成详细建卡，未执行新采集或研究。#1主控，旧#2—#9后移。

- **入口固定**：README → docs/Issue执行总计划.md → data/issue_execution_plan.csv → 当前issue。旧“今天先领C00”已后移。
- **一次只占一张执行卡**：领取前读data/active_issue.json；已有其他执行者占用时不抢占，更新用最新文件版本，冲突先重读。
- **范围写死**：每卡固定范围、依赖、输入、输出、验收与停止条件。采集固定名单在intake_batches/<批ID>/assignment.csv；100家技术批次不是100家深研。
- **完成不等于放行**：runs/issues/<key>/须有实际专用结果、manifest.json、handoff.md、review.json。关issue不能替代验收，计划路径不算已存在成果。
- **验收不要求逐卡问用户**：技术/格式可复算自检如实标SELF_CHECK，不冒充独立审计；业务最终采用维持原独立复核要求。正常已授权工作自行推进，真实缺信息或权限边界才询问。
- **手补整轮汇总**：先自动遍历、有限重试/备用源，A02才集中给用户；全局源故障回P03，不生成1054条逐家手补。未尝试、未披露、不适用不派补件。
- **规则先锁定**：S01先冻结公式、阈值、亏损/缺失规则；不能为凑N家公司调阈值。变更另版本重算，不手工加回喜欢的公司。
- **未知保持未知**：缺失不是0，取件失败不证明无业务。公司总收入不冒充机器人收入，混合收入不全算机器人。
- **旧成果只复用**：C00/B00/D00与53采用事实保留；旧45家候选不自动绕过S08，当前不继续无限追单家公司合同履约。
- **续跑靠交接**：每次写清完成/失败/未做、实际文件、限制、断点、下一步建议；重新接手先读控制文件，不凭聊天记忆。

领取时使用最新文件SHA更新active_issue.json，避免覆盖他人。专用结果与manifest/handoff/review写runs/issues/<key>/；关闭issue不代替验收。技术自检明示SELF_CHECK，最终业务采用按原独立复核规则。R00/R01/R02/R03/R04后续实际小包须另建固定名单子issue，不让父卡无限研究。
