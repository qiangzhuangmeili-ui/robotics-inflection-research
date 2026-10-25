# Google Drive 原文归档流程

本流程按[资料保存分级规则 v1.1](资料保存分级规则.md)执行。研究截止日沿用项目当前设定；每个包开始时检查任务卡的截止日。

## 文件放哪里

| 位置 | 内容 | 原则 |
|---|---|---|
| GitHub | 来源索引、关键短引文、页码、数字、判断、缺口、验收状态 | 小型可追溯文本；不放完整PDF |
| Google Drive | 被实际用于研究的官方年报/中报/公告/正式IR、扫描件、大型财务附件和交接ZIP | 原件正式归档位置 |
| 本机 `sources/` / `inbox/` | 下载中、待读、计算缓存和附件中转 | 临时副本；确认云端归档后才清理 |

## L1—L3如何执行

- **L1全池索引：** 1054家候选公司只保留可追溯的官方入口和文件元数据，不提前下载所有公告。
- **L2原件归档：** 对本轮实际用于分类或判断的每份文件，优先获取官方全文PDF并归档到Drive。网页摘要、镜像、PDF链接都不能代替上传后的原件。
- **L3证据链：** 对关键判断记录document_id、PDF物理页、原文短句、主体范围、事实发生时间、披露时间、事实/计划性质、财务口径和限制。

## 标准目录

```text
机器人行业拐点研究/
├── 01_原始资料/
│   └── 证券代码_公司简称/
│       ├── 2025年度/
│       ├── 2026H1/
│       └── 其他报告期或公告日期/
├── 02_批次交接/包ID/
├── 03_历史版本/
├── 04_财务与数据导出/
└── 05_行业资料/
```

已有主目录、分类目录与公司文件夹见[data/drive_folders.csv](../data/drive_folders.csv)。本次C00缺件的目标文件夹链接见[归档执行清单](../packages/C00_PILOT_01/results/归档执行清单.csv)。

## 自动下载/上传优先

1. 先查 `data/document_registry.csv` 和Drive，确认是否已有同一份文件。已有原件就复用真实Drive ID/URL，不重复上传。
2. 由AI优先尝试官方URL和当前可用的文件传输/上传工具。必须实际取得二进制PDF并上传；只读到网页文字不算下载，不能把网址直接登记为Drive文件。
3. 上传到对应公司/报告期子目录。文件名尽量保留原始名称；报告全文和摘要分开。
4. 重新列出或搜索Drive，确认文件ID、URL、MIME类型、名称、大小、父目录。能读回文件时检查首页标题、报告期、页数和目标页；能取得原始二进制时计算SHA-256。
5. 更新 `data/document_registry.csv`：原文官方URL、Drive真实ID/URL、报告期、披露日、原始文件名、页数、SHA-256（若已计算）、归档状态、AI读取状态。字段不能猜测。
6. 若自动下载/上传被阻断，先登记准确错误与尝试过的入口，再生成具体人工任务，提供官方入口和目标Drive文件夹直达链接。若本地Remote Desktop Commander设备离线，明确标注；用户重新上线后应先尝试自动化，避免要求用户手动做AI可以完成的工作。
7. 只有原件已归档、回读确认、索引已更新后，才清理本机重复缓存。

## 状态字段

`archive_status`与`access_check_status`必须分开填写。归档状态可用：`NOT_UPLOADED`、`UPLOADED_UNVERIFIED`、`VERIFIED`、`NOT_REQUIRED_REFERENCE_ONLY`、`SOURCE_UNAVAILABLE`。读取状态可用：`NOT_CHECKED`、`OWNER_ONLY_CHECKED`、`AI_READ_CONFIRMED`、`ACCESS_BLOCKED`。

- `VERIFIED`只表示Drive原件的身份、版本、链接/ID和可打开状态已核验，不代表业务判断通过。
- `AI_READ_CONFIRMED`只有在当前AI读到完整PDF，并能复述指定物理页内容时才可填写。
- 文件下载失败或AI读取失败都不能推导“公司没有机器人业务”；按任务规则保持HOLD/待补。
- 更正报告保留旧版并另建document_id；同一原件跨包复用，不重复上传。

## 权限

保留Drive现有受限权限。不要为了方便读取而设置“知道链接的任何人”。用户能打开不代表AI连接账号能打开；权限不足时记录`ACCESS_BLOCKED`并通过已有授权流程或当前对话附件解决。

官方参考：[Google Drive文件上传说明](https://support.google.com/drive/answer/2424368?hl=zh-CN)、[共享和权限说明](https://support.google.com/drive/answer/7166529?hl=zh-CN)。
