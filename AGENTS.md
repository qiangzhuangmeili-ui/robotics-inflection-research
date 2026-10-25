# AI接手必读

这是研究组织仓库。首读README、PROJECT_STATE.json、data/package_index.csv。未被明确要求时，不执行全池调查、不改历史输入、不做买卖建议。一次领取一个READY包，先检查实际状态以免重复。

data/company_master.csv是调度总表；archive/latest_universe.csv是旧验收快照。分组只是检索线索，不能写成事实。公司商业阶段新流程统一UNKNOWN，阶段只在产品线判。旧主表6处公司阶段值在archive与新主表legacy_company_stage列保留供追溯，不作为新流程认定。

53家旧分类附限制采用；7家旧缺2025年报已在Drive读取但业务断言待复验；10家早期样本仅局部断言已核读。不得混算完成数。新研究所有结果先REVIEW_PENDING；验收人有原文核读记录后才放行。若执行者和验收者是同一AI，明确写SELF_CHECK，不能冒充独立审计。

新调度允许已完成证据验收的单家公司进入下一步，无须等待全1054家；这只替代旧R1全池推进顺序，不放宽证据规则。archive旧标准中“不上传仓库”属于历史任务；本次用户已要求建GitHub仓库，仅上传计划、名单、表格与追溯文本。sources、inbox、PDF、账号密钥不提交。

路径：用仓库相对路径，不依赖用户名/D盘。先查data/resource_map.csv。缺原文检索约15分钟后登记人工请求/HOLD；不得用摘要补成原文。不要声称云端AI能读本机盘或本机127.0.0.1。

先粗筛，后每包5家业务细筛与财务验证，再每包3家研究拐点。粗筛不估值；预计收入不当作已实现收入。所有日期、主体、报告口径按docs/执行规则.md。


## 原件存储：Google Drive为归档位置

原始PDF、扫描图、财务Excel和交接大ZIP归档Google Drive；GitHub仅存小型文本、证据摘录、关键数字、document_id、官方原文URL与Drive文件ID/链接。sources/inbox为可选本地收集与读取缓存，未归档原件不能因已有摘要就删除。按docs/Google Drive资料归档流程.md执行。

先查data/document_registry.csv，再查官方站点，避免重复下载。原文登记继承templates/来源登记.csv：document_id稳定，drive_file_id与drive_url真实取得才填；同一原文复用ID，不因被多个包引用就重复上传。更正版另存另ID并在limitations关联旧版，不覆盖追溯原件。

AI先通过已连接Drive按真实URL/ID查元数据，再取得完整原文核页码和短引文。用户能打开不代表AI可读；OWNER_ONLY_CHECKED不可当作AI_READ_CONFIRMED，摘要可读不表示完整PDF已核读。无权限或无法取得原文写ACCESS_BLOCKED/HOLD并列补件，不能声称已核实。不要要求将Drive公开，不扩大分享权限。

Drive根目录和分类目录已创建，真实URL/ID见PROJECT_STATE.json与data/drive_folders.csv。64份旧去重PDF和另外8份年报目前已在Drive找到共72份，详见data/document_registry.csv与data/manual_requests.csv。仅8份新年报已核对正文身份；64份旧PDF仅按文件名和元数据匹配，全部云端哈希/官方源及版本仍待核验。不得将文件已上传等同业务证据验收。
