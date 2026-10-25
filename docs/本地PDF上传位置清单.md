# 本地PDF上传位置清单

Drive项目主目录已建立：[机器人行业拐点研究](https://drive.google.com/drive/folders/1v8RYlfohKcrGrulwCFq3fZSnGdjFxUYQ)。已建5个分类目录及首个包的交接目录；截至2026-10-25，已在Drive找到旧64份PDF及8份新增年报（共72份），本清单保留最初本地取件位置作历史溯源；本次索引同步未删除或移动原文件。

## 现在最省事的上传方法

1. 打开本机已整理目录：`C:\Users\zhangjianmei\Documents\ChatGPT\机器人企业行业拐点研究\GoogleDrive_待上传_20261025\01_原始资料`。
2. 打开Drive已创建的 [01_原始资料](https://drive.google.com/drive/folders/1uC1sk5q7PKMZMLPLt-xIxOj2nPk4z0Ne)。
3. 在本机目录内选中各公司文件夹，拖入Drive的01_原始资料窗口。公司/报告期子目录会随文件夹上传创建；目前这些子目录只有本地副本，不能说云端已建好。不要把外层01_原始资料本身再拖进同名目录，避免多嵌套一层。
4. 等上传完成，检查份数、文件可打开和版本。然后按真实Drive文件ID/URL补data/document_registry.csv；目录链接不是PDF文件链接，不能填进drive_file_id。

也可逐个用Drive“新建→文件夹上传”选择本机公司文件夹。官方方法见[Google上传帮助](https://support.google.com/drive/answer/2424368?hl=zh-CN)。第一次先传一家公司确认层级，再传其余；已经上传的不要重复拖入。

本机原来86份PDF，去重后64份、约169.05 MB；22份重复副本无需再上传。整理目录是另行复制的副本，原始资料保持不动。

## 不同文档放哪

|类型|Drive位置|规则|
|---|---|---|
|年报、中报、公告、正式IR、ESG、原始扫描PDF|[01_原始资料](https://drive.google.com/drive/folders/1uC1sk5q7PKMZMLPLt-xIxOj2nPk4z0Ne) / 证券代码_公司 / 报告期|同一原文只传一份；IR用发生年度或已核实报告期|
|任务包ZIP、大型交接附件|[02_批次交接](https://drive.google.com/drive/folders/1uep8rD84ZuK-RIDvwBXhnhhw3px_obr5) / 包ID|首包目录已建，见下方直接上传ZIP|
|被更正/撤回的旧文件|[03_历史版本](https://drive.google.com/drive/folders/1i-HqmZKBxx_fMJMo1mA_nHW9JPe2ijqi)|保留旧版本，登记与新版关联，不把普通旧年度年报随意移为废弃版|
|东方财富、AKShare的原始Excel/CSV/数据ZIP|[04_财务与数据导出](https://drive.google.com/drive/folders/1rbZSpFszk4i6nWbN4NwrxeqlEGtLX_St) / 来源 / 日期|保留原始导出、单位和报告口径|
|行业产销量、政策、标准及跨公司行业报告|[05_行业资料](https://drive.google.com/drive/folders/1g3LMjH1SXHdosoqdQ8m-g3gfSq43Zll1) / 主题 / 日期|行业资料不冒充公司业务证据|

首包本地ZIP：`C:\Users\zhangjianmei\Documents\ChatGPT\机器人企业行业拐点研究\robotics-inflection-research\deliveries\C00_PILOT_01.zip`，直接上传到已创建的 [C00_PILOT_01](https://drive.google.com/drive/folders/1KMLa5ntVnXb24ioZBK53ItY7IoHc8kMp) 目录。

## 原始PDF在哪些本地目录

下面3处是先前64份唯一原件的本地准备来源，目前这些文件已在Drive找到并写入真实文件ID；不必再逐处翻找或重复上传。02A补证_normalized/sources和tmp/verify02b_*中的22份重复副本不用另传。

- `C:\Users\zhangjianmei\Documents\ChatGPT\机器人企业行业拐点研究\R1_parallel_parent_reviewed_20261024\sources`：22份。
- `C:\Users\zhangjianmei\Documents\ChatGPT\机器人企业行业拐点研究\tmp\chat02a_parent_sources`：21份。
- `C:\Users\zhangjianmei\Documents\ChatGPT\机器人企业行业拐点研究\tmp\batch01_parent_sources`：21份。

## 逐文件对照（同SHA256只上传一次）

原始标题、报告期、URL、披露日的未知项保持UNKNOWN，上传归档不等于研究验收通过。完整表见data/pdf_transfer_plan.csv；prepared_local_path是整理副本，original_local_path是原件原位置。公司名如含*等Windows非法字符仅在目录名中移除，股票代码与主体记录不变。

|公司|类型/报告期|本机原件路径|Drive内目标路径|
|---|---|---|---|
|000795 英洛华|年度报告 / 2025年度|`C:\Users\zhangjianmei\Documents\ChatGPT\机器人企业行业拐点研究\tmp\chat02a_parent_sources\000795_07.pdf`|`机器人行业拐点研究/01_原始资料/000795_英洛华/2025年度`|
|000837 秦川机床|半年度报告 / 2026半年度|`C:\Users\zhangjianmei\Documents\ChatGPT\机器人企业行业拐点研究\tmp\chat02a_parent_sources\000837_30.pdf`|`机器人行业拐点研究/01_原始资料/000837_秦川机床/2026半年度`|
|001306 夏厦精密|年度报告 / 2025年度|`C:\Users\zhangjianmei\Documents\ChatGPT\机器人企业行业拐点研究\tmp\chat02a_parent_sources\001306_08.pdf`|`机器人行业拐点研究/01_原始资料/001306_夏厦精密/2025年度`|
|002048 宁波华翔|年度报告 / 2025年度|`C:\Users\zhangjianmei\Documents\ChatGPT\机器人企业行业拐点研究\R1_parallel_parent_reviewed_20261024\sources\02B_002048.pdf`|`机器人行业拐点研究/01_原始资料/002048_宁波华翔/2025年度`|
|002050 三花智控|年度报告 / 2025年度|`C:\Users\zhangjianmei\Documents\ChatGPT\机器人企业行业拐点研究\tmp\batch01_parent_sources\002050.pdf`|`机器人行业拐点研究/01_原始资料/002050_三花智控/2025年度`|
|002117 东港股份|年度报告 / 2025年度|`C:\Users\zhangjianmei\Documents\ChatGPT\机器人企业行业拐点研究\R1_parallel_parent_reviewed_20261024\sources\02B_002117.pdf`|`机器人行业拐点研究/01_原始资料/002117_东港股份/2025年度`|
|002230 科大讯飞|年度报告 / 2025年度|`C:\Users\zhangjianmei\Documents\ChatGPT\机器人企业行业拐点研究\R1_parallel_parent_reviewed_20261024\sources\02B_002230.pdf`|`机器人行业拐点研究/01_原始资料/002230_科大讯飞/2025年度`|
|002403 爱仕达|年度报告 / 2025年度|`C:\Users\zhangjianmei\Documents\ChatGPT\机器人企业行业拐点研究\tmp\chat02a_parent_sources\002403_22.pdf`|`机器人行业拐点研究/01_原始资料/002403_爱仕达/2025年度`|
|002403 爱仕达|半年度报告 / 2026半年度|`C:\Users\zhangjianmei\Documents\ChatGPT\机器人企业行业拐点研究\tmp\chat02a_parent_sources\002403_23.pdf`|`机器人行业拐点研究/01_原始资料/002403_爱仕达/2026半年度`|
|002527 新时达|年度报告 / 2025年度|`C:\Users\zhangjianmei\Documents\ChatGPT\机器人企业行业拐点研究\tmp\batch01_parent_sources\002527.pdf`|`机器人行业拐点研究/01_原始资料/002527_新时达/2025年度`|
|002698 博实股份|年度报告 / 2025年度|`C:\Users\zhangjianmei\Documents\ChatGPT\机器人企业行业拐点研究\tmp\chat02a_parent_sources\002698_15.pdf`|`机器人行业拐点研究/01_原始资料/002698_博实股份/2025年度`|
|002768 国恩股份|年度报告 / 2025年度|`C:\Users\zhangjianmei\Documents\ChatGPT\机器人企业行业拐点研究\R1_parallel_parent_reviewed_20261024\sources\02B_002768.pdf`|`机器人行业拐点研究/01_原始资料/002768_国恩股份/2025年度`|
|002896 中大力德|年度报告 / 2025年度|`C:\Users\zhangjianmei\Documents\ChatGPT\机器人企业行业拐点研究\tmp\batch01_parent_sources\002896.pdf`|`机器人行业拐点研究/01_原始资料/002896_中大力德/2025年度`|
|002979 雷赛智能|年度报告 / 2025年度|`C:\Users\zhangjianmei\Documents\ChatGPT\机器人企业行业拐点研究\tmp\batch01_parent_sources\002979.pdf`|`机器人行业拐点研究/01_原始资料/002979_雷赛智能/2025年度`|
|003021 兆威机电|年度报告 / 2025年度|`C:\Users\zhangjianmei\Documents\ChatGPT\机器人企业行业拐点研究\tmp\batch01_parent_sources\003021.pdf`|`机器人行业拐点研究/01_原始资料/003021_兆威机电/2025年度`|
|300031 宝通科技|年度报告 / 2025年度|`C:\Users\zhangjianmei\Documents\ChatGPT\机器人企业行业拐点研究\R1_parallel_parent_reviewed_20261024\sources\02B_300031.pdf`|`机器人行业拐点研究/01_原始资料/300031_宝通科技/2025年度`|
|300115 长盈精密|投资者关系材料 / 2025年度_投资者关系|`C:\Users\zhangjianmei\Documents\ChatGPT\机器人企业行业拐点研究\tmp\chat02a_parent_sources\300115_09.pdf`|`机器人行业拐点研究/01_原始资料/300115_长盈精密/2025年度_投资者关系`|
|300115 长盈精密|半年度报告摘要 / 2026半年度|`C:\Users\zhangjianmei\Documents\ChatGPT\机器人企业行业拐点研究\tmp\chat02a_parent_sources\300115_26.pdf`|`机器人行业拐点研究/01_原始资料/300115_长盈精密/2026半年度`|
|300276 三丰智能|年度报告 / 2025年度|`C:\Users\zhangjianmei\Documents\ChatGPT\机器人企业行业拐点研究\tmp\chat02a_parent_sources\300276_16.pdf`|`机器人行业拐点研究/01_原始资料/300276_三丰智能/2025年度`|
|300607 拓斯达|年度报告 / 2025年度|`C:\Users\zhangjianmei\Documents\ChatGPT\机器人企业行业拐点研究\tmp\batch01_parent_sources\300607.pdf`|`机器人行业拐点研究/01_原始资料/300607_拓斯达/2025年度`|
|301112 信邦智能|年度报告摘要 / 2025年度|`C:\Users\zhangjianmei\Documents\ChatGPT\机器人企业行业拐点研究\tmp\chat02a_parent_sources\301112_25.pdf`|`机器人行业拐点研究/01_原始资料/301112_信邦智能/2025年度`|
|301199 迈赫股份|年度报告 / 2025年度|`C:\Users\zhangjianmei\Documents\ChatGPT\机器人企业行业拐点研究\tmp\chat02a_parent_sources\301199_17.pdf`|`机器人行业拐点研究/01_原始资料/301199_迈赫股份/2025年度`|
|600053 *ST九鼎|年度报告 / 2025年度|`C:\Users\zhangjianmei\Documents\ChatGPT\机器人企业行业拐点研究\R1_parallel_parent_reviewed_20261024\sources\02B_600053.pdf`|`机器人行业拐点研究/01_原始资料/600053_ST九鼎/2025年度`|
|600699 均胜电子|年度报告 / 2025年度|`C:\Users\zhangjianmei\Documents\ChatGPT\机器人企业行业拐点研究\R1_parallel_parent_reviewed_20261024\sources\02B_600699.pdf`|`机器人行业拐点研究/01_原始资料/600699_均胜电子/2025年度`|
|601689 拓普集团|年度报告 / 2025年度|`C:\Users\zhangjianmei\Documents\ChatGPT\机器人企业行业拐点研究\tmp\chat02a_parent_sources\601689_11.pdf`|`机器人行业拐点研究/01_原始资料/601689_拓普集团/2025年度`|
|601689 拓普集团|半年度报告 / 2026半年度|`C:\Users\zhangjianmei\Documents\ChatGPT\机器人企业行业拐点研究\tmp\chat02a_parent_sources\601689_12.pdf`|`机器人行业拐点研究/01_原始资料/601689_拓普集团/2026半年度`|
|603219 富佳股份|年度报告 / 2025年度|`C:\Users\zhangjianmei\Documents\ChatGPT\机器人企业行业拐点研究\tmp\batch01_parent_sources\603219.pdf`|`机器人行业拐点研究/01_原始资料/603219_富佳股份/2025年度`|
|603296 华勤技术|年度报告 / 2025年度|`C:\Users\zhangjianmei\Documents\ChatGPT\机器人企业行业拐点研究\R1_parallel_parent_reviewed_20261024\sources\02B_603296.pdf`|`机器人行业拐点研究/01_原始资料/603296_华勤技术/2025年度`|
|603416 信捷电气|年度报告 / 2025年度|`C:\Users\zhangjianmei\Documents\ChatGPT\机器人企业行业拐点研究\tmp\chat02a_parent_sources\603416_18.pdf`|`机器人行业拐点研究/01_原始资料/603416_信捷电气/2025年度`|
|603466 风语筑|年度报告 / 2025年度|`C:\Users\zhangjianmei\Documents\ChatGPT\机器人企业行业拐点研究\R1_parallel_parent_reviewed_20261024\sources\02B_603466.pdf`|`机器人行业拐点研究/01_原始资料/603466_风语筑/2025年度`|
|603583 捷昌驱动|年度报告 / 2025年度|`C:\Users\zhangjianmei\Documents\ChatGPT\机器人企业行业拐点研究\tmp\chat02a_parent_sources\603583_13.pdf`|`机器人行业拐点研究/01_原始资料/603583_捷昌驱动/2025年度`|
|603662 柯力传感|年度报告 / 2025年度|`C:\Users\zhangjianmei\Documents\ChatGPT\机器人企业行业拐点研究\tmp\batch01_parent_sources\603662.pdf`|`机器人行业拐点研究/01_原始资料/603662_柯力传感/2025年度`|
|603666 亿嘉和|年度报告 / 2025年度|`C:\Users\zhangjianmei\Documents\ChatGPT\机器人企业行业拐点研究\tmp\batch01_parent_sources\603666.pdf`|`机器人行业拐点研究/01_原始资料/603666_亿嘉和/2025年度`|
|603667 五洲新春|年度报告 / 2025年度|`C:\Users\zhangjianmei\Documents\ChatGPT\机器人企业行业拐点研究\tmp\batch01_parent_sources\603667.pdf`|`机器人行业拐点研究/01_原始资料/603667_五洲新春/2025年度`|
|603728 鸣志电器|年度报告 / 2025年度|`C:\Users\zhangjianmei\Documents\ChatGPT\机器人企业行业拐点研究\tmp\batch01_parent_sources\603728.pdf`|`机器人行业拐点研究/01_原始资料/603728_鸣志电器/2025年度`|
|603915 国茂股份|年度报告 / 2025年度|`C:\Users\zhangjianmei\Documents\ChatGPT\机器人企业行业拐点研究\tmp\batch01_parent_sources\603915.pdf`|`机器人行业拐点研究/01_原始资料/603915_国茂股份/2025年度`|
|688003 天准科技|年度报告 / 2025年度|`C:\Users\zhangjianmei\Documents\ChatGPT\机器人企业行业拐点研究\R1_parallel_parent_reviewed_20261024\sources\02B_688003.pdf`|`机器人行业拐点研究/01_原始资料/688003_天准科技/2025年度`|
|688088 虹软科技|年度报告 / 2025年度|`C:\Users\zhangjianmei\Documents\ChatGPT\机器人企业行业拐点研究\R1_parallel_parent_reviewed_20261024\sources\02B_688088.pdf`|`机器人行业拐点研究/01_原始资料/688088_虹软科技/2025年度`|
|688090 瑞松科技|年度报告 / 2025年度|`C:\Users\zhangjianmei\Documents\ChatGPT\机器人企业行业拐点研究\tmp\batch01_parent_sources\688090.pdf`|`机器人行业拐点研究/01_原始资料/688090_瑞松科技/2025年度`|
|688160 步科股份|年度报告 / 2025年度|`C:\Users\zhangjianmei\Documents\ChatGPT\机器人企业行业拐点研究\tmp\batch01_parent_sources\688160.pdf`|`机器人行业拐点研究/01_原始资料/688160_步科股份/2025年度`|
|688165 埃夫特|年度报告 / 2025年度|`C:\Users\zhangjianmei\Documents\ChatGPT\机器人企业行业拐点研究\tmp\batch01_parent_sources\688165.pdf`|`机器人行业拐点研究/01_原始资料/688165_埃夫特/2025年度`|
|688218 江苏北人|年度报告 / 2025年度|`C:\Users\zhangjianmei\Documents\ChatGPT\机器人企业行业拐点研究\tmp\chat02a_parent_sources\688218_19.pdf`|`机器人行业拐点研究/01_原始资料/688218_江苏北人/2025年度`|
|688255 凯尔达|年度报告 / 2025年度|`C:\Users\zhangjianmei\Documents\ChatGPT\机器人企业行业拐点研究\tmp\chat02a_parent_sources\688255_20.pdf`|`机器人行业拐点研究/01_原始资料/688255_凯尔达/2025年度`|
|688290 景业智能|年度报告 / 2025年度|`C:\Users\zhangjianmei\Documents\ChatGPT\机器人企业行业拐点研究\tmp\chat02a_parent_sources\688290_21.pdf`|`机器人行业拐点研究/01_原始资料/688290_景业智能/2025年度`|
|688322 奥比中光|年度报告 / 2025年度|`C:\Users\zhangjianmei\Documents\ChatGPT\机器人企业行业拐点研究\tmp\batch01_parent_sources\688322.pdf`|`机器人行业拐点研究/01_原始资料/688322_奥比中光/2025年度`|
|688327 云从科技|年度报告 / 2025年度|`C:\Users\zhangjianmei\Documents\ChatGPT\机器人企业行业拐点研究\R1_parallel_parent_reviewed_20261024\sources\02B_688327.pdf`|`机器人行业拐点研究/01_原始资料/688327_云从科技/2025年度`|
|688557 兰剑智能|年度报告 / 2025年度|`C:\Users\zhangjianmei\Documents\ChatGPT\机器人企业行业拐点研究\tmp\batch01_parent_sources\688557.pdf`|`机器人行业拐点研究/01_原始资料/688557_兰剑智能/2025年度`|
|688626 翔宇医疗|年度报告 / 2025年度|`C:\Users\zhangjianmei\Documents\ChatGPT\机器人企业行业拐点研究\tmp\batch01_parent_sources\688626.pdf`|`机器人行业拐点研究/01_原始资料/688626_翔宇医疗/2025年度`|
|688787 海天瑞声|年度报告 / 2025年度|`C:\Users\zhangjianmei\Documents\ChatGPT\机器人企业行业拐点研究\R1_parallel_parent_reviewed_20261024\sources\02B_688787.pdf`|`机器人行业拐点研究/01_原始资料/688787_海天瑞声/2025年度`|
|688836 宇树科技|上市前材料 / 2026年度_上市前材料|`C:\Users\zhangjianmei\Documents\ChatGPT\机器人企业行业拐点研究\tmp\chat02a_parent_sources\688836_14.pdf`|`机器人行业拐点研究/01_原始资料/688836_宇树科技/2026年度_上市前材料`|
|688836 宇树科技|上市前材料 / 2026年度_上市前材料|`C:\Users\zhangjianmei\Documents\ChatGPT\机器人企业行业拐点研究\tmp\chat02a_parent_sources\688836_24.pdf`|`机器人行业拐点研究/01_原始资料/688836_宇树科技/2026年度_上市前材料`|
|920002 万达轴承|投资者关系材料 / 2026年度_投资者关系|`C:\Users\zhangjianmei\Documents\ChatGPT\机器人企业行业拐点研究\R1_parallel_parent_reviewed_20261024\sources\02A_wanda_920002_IR_2026-08-05_misattributed_from_E039.pdf`|`机器人行业拐点研究/01_原始资料/920002_万达轴承/2026年度_投资者关系`|
|920007 酉立智能|年度报告 / 2025年度|`C:\Users\zhangjianmei\Documents\ChatGPT\机器人企业行业拐点研究\tmp\batch01_parent_sources\920007.pdf`|`机器人行业拐点研究/01_原始资料/920007_酉立智能/2025年度`|
|920100 三协电机|年度报告 / 2025年度|`C:\Users\zhangjianmei\Documents\ChatGPT\机器人企业行业拐点研究\R1_parallel_parent_reviewed_20261024\sources\02A_sanxie_2025AR.pdf`|`机器人行业拐点研究/01_原始资料/920100_三协电机/2025年度`|
|920124 南特科技|年度报告 / 2025年度|`C:\Users\zhangjianmei\Documents\ChatGPT\机器人企业行业拐点研究\R1_parallel_parent_reviewed_20261024\sources\02A_nante_2025AR.pdf`|`机器人行业拐点研究/01_原始资料/920124_南特科技/2025年度`|
|920418 苏轴股份|年度报告 / 2025年度|`C:\Users\zhangjianmei\Documents\ChatGPT\机器人企业行业拐点研究\R1_parallel_parent_reviewed_20261024\sources\02A_suzhouzhou_2025AR.pdf`|`机器人行业拐点研究/01_原始资料/920418_苏轴股份/2025年度`|
|920418 苏轴股份|ESG报告 / 2025年度|`C:\Users\zhangjianmei\Documents\ChatGPT\机器人企业行业拐点研究\R1_parallel_parent_reviewed_20261024\sources\02A_suzhouzhou_ESG2025.pdf`|`机器人行业拐点研究/01_原始资料/920418_苏轴股份/2025年度`|
|920418 苏轴股份|投资者关系材料 / 2026年度_投资者关系|`C:\Users\zhangjianmei\Documents\ChatGPT\机器人企业行业拐点研究\R1_parallel_parent_reviewed_20261024\sources\02A_suzhouzhou_IR_2026-01-08_ann2026-002.pdf`|`机器人行业拐点研究/01_原始资料/920418_苏轴股份/2026年度_投资者关系`|
|920418 苏轴股份|投资者关系材料 / 2026年度_投资者关系|`C:\Users\zhangjianmei\Documents\ChatGPT\机器人企业行业拐点研究\R1_parallel_parent_reviewed_20261024\sources\02A_suzhouzhou_IR_2026-03-05_ann2026-009.pdf`|`机器人行业拐点研究/01_原始资料/920418_苏轴股份/2026年度_投资者关系`|
|920418 苏轴股份|投资者关系材料 / 2026年度_投资者关系|`C:\Users\zhangjianmei\Documents\ChatGPT\机器人企业行业拐点研究\R1_parallel_parent_reviewed_20261024\sources\02A_suzhouzhou_IR_2026-04-12_ann2026-033.pdf`|`机器人行业拐点研究/01_原始资料/920418_苏轴股份/2026年度_投资者关系`|
|920418 苏轴股份|投资者关系材料 / 2026年度_投资者关系|`C:\Users\zhangjianmei\Documents\ChatGPT\机器人企业行业拐点研究\R1_parallel_parent_reviewed_20261024\sources\02A_suzhouzhou_IR_2026-05-13_ann2026-041.pdf`|`机器人行业拐点研究/01_原始资料/920418_苏轴股份/2026年度_投资者关系`|
|920491 奥迪威|投资者关系材料 / 2026年度_投资者关系|`C:\Users\zhangjianmei\Documents\ChatGPT\机器人企业行业拐点研究\tmp\chat02a_parent_sources\920491_04.pdf`|`机器人行业拐点研究/01_原始资料/920491_奥迪威/2026年度_投资者关系`|
|920510 丰光精密|年度报告 / 2025年度|`C:\Users\zhangjianmei\Documents\ChatGPT\机器人企业行业拐点研究\tmp\batch01_parent_sources\920510.pdf`|`机器人行业拐点研究/01_原始资料/920510_丰光精密/2025年度`|
|920593 鼎智科技|年度报告 / 2025年度|`C:\Users\zhangjianmei\Documents\ChatGPT\机器人企业行业拐点研究\tmp\batch01_parent_sources\920593.pdf`|`机器人行业拐点研究/01_原始资料/920593_鼎智科技/2025年度`|
