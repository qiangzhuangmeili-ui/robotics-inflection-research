# Issue执行总计划：先收料，再逐轮筛选

计划版本`20261026_collection_first_v2`，更新日2026-10-26。当前研究截止日沿用PROJECT_STATE.json（目前2026-10-25），P00负责冻结，采集日期另记。

这是本轮唯一执行路线。已新增39个issue，旧#2—#9保留成果并后移。建卡不表示采集或研究已执行。

## 从这里开始

先看[主控总路线 #1](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/1)，当前首张执行任务是 [#11 P00](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/11)。一次只执行一张依赖已验收的卡，不跳到企业深研。

## 阶段与放行

|阶段|新卡数|任务|边界|
|---|---:|---|---|
|准备|8|P00—P07：范围、资料身份、旧资产、连接、财务字段、采集器、容量、10家采集校准|P07采集校准通过后才能启动全池批次|
|采集批次|11|M00_01—M00_11：100家公司×10批+54家，互斥覆盖1054|只收集文件/数据，不逐家业务深读|
|收尾补缺|5|A00—A04：覆盖汇总、重试、一次人工补缺、回填、资料轮验收|A04通过后才放行指标轮|
|指标筛选|9|S00—S08：标准化、规则预登记、计算、宽筛、收紧、质量、储备观察、抽查、名单验收|S08冻结筛后名单后才新增公司深读|
|重点研究|6|R00—R05：业务、财务归因、行业、公司拐点、最后估值、增量防偏|每5家业务/财务、每3家拐点/估值另建实际子issue|

1054×6=6324只是核心报告槽上界，不是实际/应有文件数；上市前、不适用、未披露、失败分别登记。10家采集校准产物在正式批次幂等复用，证券总数仍为1054，不能再加10家。

## 防跑偏规则

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

## 每张卡怎样验收

专用交付见issue，共同使用[交接模板](../templates/issue_handoff.md)和[验收模板](../templates/issue_review.json)。执行者、复核者、方法、实际文件、范围覆盖、失败/未尝试、结论与限制必须明确。模板不能当已验收记录。技术自检可放行相应技术依赖，最终业务采用仍须原规则独立核验；这不新增用户逐卡批准流程。

资料可用性与业务断言分开：链接、下载、Drive归档、可读/身份确认、业务证据核实分别记录。第一轮不逐份精读，后期采用结论仍须原句、物理页、主体和时间边界。

## 39张新卡索引

|顺序|阶段|任务|依赖|计划状态|
|---|---|---|---|---|
|1|准备|[#11 P00：冻结资料范围、候选名单和研究截止日](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/11)|无|READY|
|2|准备|[#12 P01：统一文件身份、来源登记与去重规则](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/12)|[#11 P00](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/11)|WAITING_DEPENDENCIES|
|3|准备|[#13 P02：盘点现有Drive、本机与旧研究库，避免重复收集](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/13)|[#12 P01](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/12)|WAITING_DEPENDENCIES|
|4|准备|[#14 P03：恢复并验证采集连接，建立来源故障熔断](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/14)|[#11 P00](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/11)|WAITING_DEPENDENCIES|
|5|准备|[#15 P04：冻结财务字段、单位、报表与时间口径](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/15)|[#11 P00](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/11)|WAITING_DEPENDENCIES|
|6|准备|[#16 P05：实现可断点续跑的采集器与下载校验](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/16)|[#12 P01](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/12)、[#14 P03](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/14)、[#15 P04](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/15)|WAITING_DEPENDENCIES|
|7|准备|[#17 P06：确定容量、目录、归档与交接规则](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/17)|[#11 P00](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/11)、[#13 P02](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/13)|WAITING_DEPENDENCIES|
|8|准备|[#18 P07：10家采集校准：只验接口和资料，不研究业务](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/18)|[#13 P02](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/13)、[#14 P03](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/14)、[#15 P04](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/15)、[#16 P05](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/16)、[#17 P06](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/17)|WAITING_DEPENDENCIES|
|9|采集批次|[#19 M00_01：基础资料自动采集第01批：固定100家公司](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/19)|[#18 P07](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/18)|WAITING_DEPENDENCIES|
|10|采集批次|[#20 M00_02：基础资料自动采集第02批：固定100家公司](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/20)|[#18 P07](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/18)|WAITING_DEPENDENCIES|
|11|采集批次|[#21 M00_03：基础资料自动采集第03批：固定100家公司](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/21)|[#18 P07](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/18)|WAITING_DEPENDENCIES|
|12|采集批次|[#22 M00_04：基础资料自动采集第04批：固定100家公司](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/22)|[#18 P07](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/18)|WAITING_DEPENDENCIES|
|13|采集批次|[#23 M00_05：基础资料自动采集第05批：固定100家公司](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/23)|[#18 P07](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/18)|WAITING_DEPENDENCIES|
|14|采集批次|[#24 M00_06：基础资料自动采集第06批：固定100家公司](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/24)|[#18 P07](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/18)|WAITING_DEPENDENCIES|
|15|采集批次|[#25 M00_07：基础资料自动采集第07批：固定100家公司](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/25)|[#18 P07](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/18)|WAITING_DEPENDENCIES|
|16|采集批次|[#26 M00_08：基础资料自动采集第08批：固定100家公司](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/26)|[#18 P07](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/18)|WAITING_DEPENDENCIES|
|17|采集批次|[#27 M00_09：基础资料自动采集第09批：固定100家公司](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/27)|[#18 P07](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/18)|WAITING_DEPENDENCIES|
|18|采集批次|[#28 M00_10：基础资料自动采集第10批：固定100家公司](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/28)|[#18 P07](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/18)|WAITING_DEPENDENCIES|
|19|采集批次|[#29 M00_11：基础资料自动采集第11批：固定54家公司](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/29)|[#18 P07](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/18)|WAITING_DEPENDENCIES|
|20|收尾补缺|[#30 A00：汇总11批覆盖率，核对全池和全部资料槽](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/30)|[#19 M00_01](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/19)、[#20 M00_02](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/20)、[#21 M00_03](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/21)、[#22 M00_04](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/22)、[#23 M00_05](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/23)、[#24 M00_06](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/24)、[#25 M00_07](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/25)、[#26 M00_08](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/26)、[#27 M00_09](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/27)、[#28 M00_10](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/28)、[#29 M00_11](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/29)|WAITING_DEPENDENCIES|
|21|收尾补缺|[#31 A01：集中重试失败项与备用官方来源](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/31)|[#30 A00](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/30)|WAITING_DEPENDENCIES|
|22|收尾补缺|[#32 A02：只发一次：按软件、网站和报告期合并人工补缺](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/32)|[#31 A01](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/31)|WAITING_DEPENDENCIES|
|23|收尾补缺|[#33 A03：人工补件回填、去重与缺口核销](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/33)|[#32 A02](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/32)|WAITING_DEPENDENCIES|
|24|收尾补缺|[#34 A04：资料轮验收：放行指标计算，明确保留缺口](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/34)|[#33 A03](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/33)|WAITING_DEPENDENCIES|
|25|指标筛选|[#35 S00：标准化全池财务，保留原值、单位和版本](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/35)|[#34 A04](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/34)|WAITING_DEPENDENCIES|
|26|指标筛选|[#36 S01：预先登记筛选公式、阈值、缺失与亏损规则](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/36)|[#35 S00](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/35)|WAITING_DEPENDENCIES|
|27|指标筛选|[#37 S02：计算全池指标与口径检查](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/37)|[#36 S01](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/36)|WAITING_DEPENDENCIES|
|28|指标筛选|[#38 S03：第一道宽筛：任一改善信号，保留观察队列](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/38)|[#37 S02](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/37)|WAITING_DEPENDENCIES|
|29|指标筛选|[#39 S04：第二道收紧：核多指标共同改善](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/39)|[#38 S03](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/38)|WAITING_DEPENDENCIES|
|30|指标筛选|[#40 S05：第三道质量检查：现金流、应收存货与低基数](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/40)|[#39 S04](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/39)|WAITING_DEPENDENCIES|
|31|指标筛选|[#41 S06：保留早期储备与缺数据观察名单](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/41)|[#36 S01](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/36)、[#37 S02](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/37)|WAITING_DEPENDENCIES|
|32|指标筛选|[#42 S07：抽查阈值边界、漏筛和缺数据偏差](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/42)|[#38 S03](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/38)、[#39 S04](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/39)、[#40 S05](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/40)、[#41 S06](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/41)|WAITING_DEPENDENCIES|
|33|指标筛选|[#43 S08：验收筛选结果，冻结后期业务核验名单](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/43)|[#42 S07](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/42)|WAITING_DEPENDENCIES|
|34|重点研究|[#44 R00：后期业务核验：只给筛后公司分5家小包](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/44)|[#43 S08](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/43)|WAITING_DEPENDENCIES|
|35|重点研究|[#45 R01：筛后公司财务归因与收入范围核验](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/45)|[#44 R00](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/44)|WAITING_DEPENDENCIES|
|36|重点研究|[#46 R02：行业信号核验与同口径比较](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/46)|[#43 S08](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/43)|WAITING_DEPENDENCIES|
|37|重点研究|[#47 R03：公司与行业拐点研究：每包最多3家公司](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/47)|[#45 R01](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/45)、[#46 R02](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/46)|WAITING_DEPENDENCIES|
|38|重点研究|[#48 R04：最后做估值情景与假设敏感性](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/48)|[#47 R03](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/47)|WAITING_DEPENDENCIES|
|39|重点研究|[#49 R05：增量更新、规则变更与计划防偏检查](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/49)|[#48 R04](https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/48)|WAITING_DEPENDENCIES|

## 旧卡和旧资料包

旧#2/#3为历史C00/B00业务研究；旧#4资产盘点由P02承接，业务采用以后由R00核对；旧#5/#6由S08后R00给具体公司派卡；旧#7后期归因由R01承接，基础财务口径前移P04/S00；旧#8在R02/R03，旧#9在R04。

旧data/package_index.csv增列执行门槛，不删除原状态/证据，它不再是开局入口。采集批次从data/intake_batch_index.csv进入，39卡总顺序从data/issue_execution_plan.csv进入。实际方法见[第一轮批量收集](第一轮基础资料批量收集.md)。
