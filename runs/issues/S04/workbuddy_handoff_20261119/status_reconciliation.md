# S04 交接口径对照（步骤A）

核对时间：2026-11-19（北京时间）
计划版本：`20261026_collection_first_v2`
性质：只读核对 + 自检；不领取 #39/#53，不改冻结结果、阈值、截止日、B 或旧验收。

## 1. 在线控制状态（本轮实读）

| 对象 | 值 | 说明 |
|---|---|---|
| main 最新提交 | `a308fab` / 2026-11-16T02:43:15Z | "Point current issue plan to verified scoped S04 handoff" |
| `data/active_issue.json` blob | `a8195c81d4ff2aab630c08bc843ef043eaf4350d` | 与 11-17 计划记录一致，未变 |
| `PROJECT_STATE.json` blob | `a334c5693c0cd7a10f874b4efa33ab993288048a` | 同上，未变 |
| `data/issue_execution_plan.csv` blob | `89aebf385b40bc92e932107110d01959ca84c264` | 同上，未变 |
| 占用 | #53 `S00_ERRATA_REVIEW`，executor **Codex** | 无明确交接记录 → 本轮不抢占 |
| `current_gate` | `S04_FORMAL_REVIEW_ARCHIVED_WITH_LIMITS_S05_LOCKED` | |
| `release_S04` | true（范围 `TECHNICAL_MULTIMETRIC_SCREEN_AND_TARGETED_QC_ONLY`） | 不是业务采用 |
| `release_S05` | **false** | S05 正式运行须新增明确 `release_S05` 记录 |
| #39 / #53 | 均 OPEN | 无整体关闭授权 |

三个 blob 与 11-17 计划所记完全相同，说明 11-16 之后控制面没有新的推进——本轮接手面对的就是同一冻结状态。

## 2. 归档与正式审查

| 项 | 值 |
|---|---|
| ZIP | `S04_completion_20261116_final_artifacts.zip` |
| 字节 | 24,347,716 |
| SHA256 | `87f4f4ee8bb884cdfb9203a0e4958e53148b710681948e7957663bef9e9294d6` |
| Drive file | `1VrpWyQct6xI5PpRdGNs6KFZmubbspYEA`（父目录 `13oqd9t1Lv2GgDIMUVZbzaDbmLuTa7CWa`） |
| 成员 | 344（含 `bundle_manifest.json`），逐个哈希匹配 344/344 |
| Drive 实时下载 | **ACCESS_BLOCKED**（`uc` 303→登录页 971,576B HTML；`api/v3` 403） |

结论：本轮**没有**重新下载远端二进制，核验方式是「本机归档 + 11-16 已 VERIFIED 回执 + 11-16 Drive 回读副本 `drive_readback_20261116.zip` 与本地逐字节相同」。因此归档状态记为 `OFFLINE_SNAPSHOT_MATCHING_VERIFIED_REMOTE_RECEIPT`，不新写 VERIFIED。

正式记录指纹（本机实算，全部匹配）：

| 文件 | SHA256 |
|---|---|
| `final_peer_review_20261116/peer_review.json` | `ab249f18…7c924` |
| `formal_gate_review_20261115/review.json`（S00 来源补充） | `d906efff…2d2d1` |
| `qualification_v3_20261115/manifest.json` | `2be3081c…85144` |
| `qualification_v3_20261115/scope_contract.json` | `a856b968…33242` |
| `final_delivery_20261116/REPORT.md` | `494c59f6…62adf` |
| 权威 B `s00_v10.csv.gz` | `fc312c52…fe2025` |

这些文件在 GitHub 上取回 404——线上控制文件把它们登记为 `archive_member`，只能从真实 ZIP 读。本轮是从 ZIP 成员读的。

## 3. 旧 445 家 → 当前 278 受限候选

| 档位 | 旧（S04 自检版，11-10） | 当前（11-16 冻结正式版） | 变化 |
|---|---:|---:|---:|
| 受限筛选候选 | 445 | **278** | −167 |
| 数据待核 HOLD | 10 | 328 | +318 |
| 当前未入选 | 322 | 171 | −151 |
| 不在本次 L2 范围 | 273 | 272 | −1 |
| 锚点待重选 | — | 1 | +1 |
| 截止日后隔离 | 4 | 4 | 0 |
| 合计 | 1054 | 1054 | — |

变化原因（来自正式记录，不是我的推断）：

1. **839 项精确争议处置**（827 个 ERRATA 标记成员 + 12 项两公司来源/状态/值/页差异）按成员逐条应用，不按公司广播。
2. **C/E 无 SG 用途的 2133 成员**全部连到 S02 源引用：48 条边、36 个质量指标格、15 家公司被保守置 HOLD，这 15 家全部落到观察表、零合格维度。
3. **5 条来源语言前提**按独立原页复核解除，仅限语言前提，未广播到其他字段。
4. 原「自检版」把大量依赖未闭合的信号当作可用；正式版按 Round5 §9 Q2 只放行「实际被消费且证据成立」的成员，其余转为 HOLD。

所以 **445 是历史自检口径，不能再作为派工池**；278 是「冻结财务信号的受限筛选候选」，既不等于机器人业务确认，也不等于投资候选。

## 4. 旧「待上传/未发布」文字 → 后续 VERIFIED 回执

冻结时生成的 `review.json` 里写的是 `remote_published: false`、`archive_status: LOCAL_ONLY_AWAITING_EXPLICIT_UPLOAD_AUTHORIZATION`；11-16 用户确认后才上传，产生 `drive_archive_receipt.json`（`archive_status: VERIFIED`，回读 SHA 匹配、父目录匹配、共享未改）。

处理口径（沿用线上控制文件措辞）：**后续在线回执只替代「归档状态」这一项，不替代科学限制**；冻结 CSV 与 `data_manifest` 保持原样，不回写、不掩盖旧文字。分发用 `reviewed_view`（只改审查上下文列）并附正式审查记录。

## 5. 计数口径不能混用

| 数字 | 含义 | 不能当成 |
|---|---|---|
| 9,050 / 10,555 / 8,762 | S00 v5 历史 SELF_CHECK 快照：核心未闭合 / 含补充列 / 已按范围覆盖 | 当前资格图 |
| 18,434 | 资格 manifest 的**开放争议成员触达数**（全量复算） | 坏值数、独立错误数、必须全清才能进下一步的数量 |
| 8,718 | 本轮重开的精确成员（原 `RESOLVED_SCOPE_COVERED` → `PENDING_REAUDIT`） | 新增错误 |
| 839 | 已采用精确处置 | 全池来源验收 |

`18,434` 与 `9,050` 是不同 manifest 的不同量纲，**不得相减**。

## 6. 强制守卫（本轮原样保留，未动）

- 4 家截止日后隔离：天博智能 `SH:603448`、宇树科技 `SH:688836`、蓝箭电子 `SZ:301348`、洛轴股份 `SZ:301699`。不用早期报告回退规避时间隔离。
- 1 家锚点待重选：孚日股份 `SZ:002083`。无版本化定锚与受影响链重算前保持隔离。
- 3 家项目模式 UNKNOWN：华工科技 `SZ:000988`、华菱线缆 `SZ:001208`、金财互联 `SZ:002530`。RH02 消失只表示来源待核，不是无风险。
- 15 家 CE 质量未知（`PENDING_CE_SOURCE`）：全部零合格维度、全部在观察表；S04 资格通过**不授权**这些质量值用于 S05。
- 禾川科技 `SH:688320`、联赢激光 `SH:688518`：仍 `HOLD_FOR_DATA`，各 9 条待核信号；禾川 NPP 争议 `D-a3a9ea277080` 仍 OPEN（UPDATE 终态 `EXTRACTED_XCHECK_MISMATCH` 与 B 的 `EXTRACTED` 不符）。
- 8 项父链提案：仅 SELF_CHECK 准备，未采用、非有效（`NTN-…` 8 条，涉及 `SH:688800`/`SH:600939`/`SH:601717`/`SH:603350`）。

## 7. 本轮没有做的事

- 未领取 #39/#53，未写 `PROJECT_STATE.json` / `data/active_issue.json`（两者工作区副本是 11-16 遗留、与在线 main 有差异，已登记并一律以在线为准）。
- 未重新下载 Drive 二进制，未改归档状态。
- 未改冻结阈值、截止日、B、S01 v3 规则或任何旧验收。
- 未重启全池抽取、全池精读或企业深研。
- 未给出 S05 放行；`release_S05` 仍为 false。
