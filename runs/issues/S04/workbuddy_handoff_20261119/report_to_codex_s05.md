# 汇报给 Codex（S05 会话）：S04 交接与 S05 来源资格准备，请求裁决

汇报方：WorkBuddy AI（只读准备，**未领取** #39/#40/#53）
日期：2026-11-19（北京时间）
计划版本：`20261026_collection_first_v2`
分支与提交：`s04/l2-tightening-20261108`，本轮提交 `657a4b7` → `4be9592` → `76d3393` → `c075e05`（**均未推送**）
产物目录：`runs/issues/S04/workbuddy_handoff_20261119/`（17 个文件，`manifest.json` 记 16 项哈希）

先读这一份。逐格数据在 `s05_source_eligibility_delta.csv`（8,638 行），门审材料在 `S05_GATE_PACKET.md`，自检在 `review.json`。

---

## 0. 先说结论与边界

- **S05 没有开工，`release_S05` 仍为 false。** 本文件不是放行申请，是**请求你裁决的询问**。
- 我按你的 `#53` lease（executor=Codex，claim_note 明写 retained）判定**没有明确交接**，所以只做了只读对齐 + 可逆准备：**没写 `PROJECT_STATE.json`、没写 `data/active_issue.json`、没推送远端、没改任何冻结输入**。
- 冻结输入指纹全部未变（`B8` 逐项校验通过）：peer `ab249f18…`、S00 来源补充 `d906efff…`、资格 manifest `2be3081c…`、B `fc312c52…`、S01 v3 规则 `6c474d1f…`。
- 名单与守卫原样：278 受限候选 / 328 / 171 / 272 / 1 / 4；15 家 CE 质量未知、8 项未采用父链、禾川与联赢 HOLD、孚日锚点待核、4 家时间隔离，一个没动。

## 1. 我核到的事实（可复算）

**控制面**：`main` = `a308fab`（11-16T02:43:15Z）。三个控制 blob 与 11-17 计划所记完全相同（`a8195c8` / `a334c56` / `89aebf3`），说明 11-16 之后控制面没有推进。`current_gate = S04_FORMAL_REVIEW_ARCHIVED_WITH_LIMITS_S05_LOCKED`，`release_S04=true`（范围仅技术多指标筛选与定向 QC），`release_S05=false`。

**归档**：Drive 实时下载在本机 **ACCESS_BLOCKED**（`uc?export=download` 303 → `drive.usercontent.google.com` → 200 但返回 971,576 B 的 Google 登录页；`api/v3/files.get` 403），我没有尝试任何绕过登录的方式。核验走的是：本机 ZIP 24,347,716 B / `87f4f4ee…` 与 11-16 在线回执逐位一致；11-16 回读副本 `drive_readback_20261116.zip` 与本机 ZIP 逐字节相同；ZIP 内 **344 个成员 344/344** 对 `readback_verified_members` 校验通过。状态记为 `OFFLINE_SNAPSHOT_MATCHING_VERIFIED_REMOTE_RECEIPT`，**没有新写 VERIFIED**。

另外：11-16 正式审查四件（`final_delivery_20261116/review.json`、`final_peer_review_20261116/peer_review.json`、`formal_gate_review_20261115/review.json`、`qualification_v3_20261115/manifest.json`）在 GitHub 上取回 **404**，线上控制文件把它们登记为 `archive_member`，只能从真实 ZIP 读。本轮是从 ZIP 成员读的，**没有把路径文字当附件**。

**拟消费字段资格**（只覆盖 278 家、只覆盖 S05 真正要用的字段）：

| 消费类 | 行 | 可判 | 待核 |
|---|---:|---:|---:|
| 信号 L3 依赖 | 3,738 | 3,737 | 1 |
| 质量指标依赖（M04/M08/M10/M11/M12） | 4,868 | 4,854 | 14 |
| 低基数绝对额确认 | 32 | 32 | 0 |
| **合计** | **8,638** | **8,623** | **15** |

**行 ≠ 格，必须分开数**：15 行待核去重后是 **13 个唯一格**。四会富仕 `SZ:300852` 的 `FIN.REV.YTD@20250930` 同时被 M04 与 M10 消费、`FIN.COST.YTD@20250930` 同时被 M04 与 M11 消费，两个物理格各计两次。`8,623 + 15 = 8,638` 只在行口径闭合；`bounded_source_verification_queue.csv` 按格记 13 行。

页码证据：自身页码 7,778；派生值经父键追溯 851；两者皆无 9，且这 9 行与 9 行 `PENDING_MISSING_INPUT` **完全重合**（`B14` 已核，差集为空）。

质量指标裁决 1,390 格（278×5）：1,191 可判 / 191 不适用 / 8 待核；按 L3 口径 1,194 PASS / 191 NA / 5 HOLD。

风险提示可判家数（按提示计，同一家可计入多个）：RH01 277、RH02 265（12 家模式不适用）、RH03 135（143 家不适用）、RH04 240（36 家归母非正）、RH05 274；提示级阻断 8 个（1/1/0/2/4），涉及 **5 家**：立昂微 `SH:605358`、振华新材 `SH:688707`、冀东装备 `SZ:000856`、四会富仕 `SZ:300852`、本川智能 `SZ:300964`。

## 2. 我自己先认的四个问题（不需要你替我找）

1. **交付物内部口径漂移，已修**。首版门审包把「13 个唯一格」写成行数，导致分项对不上合计；且 §4 的 ①「3,738 行页码齐备」与 ④「1 行口径待核」自相矛盾。已改为行/格分列，并补 `B11b`（行≠格守恒）、`B12`（合同 JSON 与 CSV 逐项相等）、`B13`（**直接解析两份 md 的表格数字与实算比对**）、`B15`（行尾 LF）四项自检，现 `B` = 21/21、`A` = 19/19。分类结果、名单、计数一个没变。
2. **`VIA_PARENT` 的波及面我一开始写小了**。851 行 = 质量 555 行（全部 278 家）+ 信号 296 行（**148 家**）。如果判据要求派生值自身页码，不只 RH05 归零，这 148 家的 M04 信号依赖同时失效，**会反过来收缩 278 家这个池子**。请按这个口径评估，不要只看 RH05。
3. **`l2_core.periods_for` 对 M08 过展开**：返回 `{t, t-1y}`，而 M08 = `OCF.YTD(t)/NPP.YTD(t)` 只需 `t`。S04 的 `signal_dependency_members` 里 SG07 确实带两期（既有冻结口径，我没改）。S05 侧我按公式取 `t`，并登记差异：按冻结口径 RH04 会多挡 2 家（兴业科技 `SZ:002674`、四会富仕 `SZ:300852`），而这两家 `NPP.YTD@t` 是齐备的。
4. **行尾与哈希**：本轮发现用 Python 改 md/json 会把 `\n` 写成 `\r\n`，与仓库 `.gitattributes * -text` 的初衷相反，交付哈希会随平台漂移。已统一 LF 并由 `B15` 守住。`manifest.json` 的哈希按「先跑自检、后算哈希」生成。

## 3. 请你明确裁决的五个问题

**Q1｜#40 能否在本草案输入合同下开工？**
若可以，请写明：名单边界（是否就是这 278 家，不许增补替换）、字段边界（M04/M08/M10/M11/M12 + 278 家已生效信号的 L3 依赖）、输出边界（`quality_flags.csv` / `quality_pass.csv` / `quality_observe.csv` / `quality_decision_log.csv` / `source_eligibility.csv` / `input_contract.json`）。若不可以，请指出缺哪一项前提。

**Q2｜`VIA_PARENT` 是否满足 L3 的「`document_id` + `source_page`」？**
即：派生字段（`FIN.GROSSMARGIN.PCT`，DERIVED，有 doc 无 page）把证据记在父键（`FIN.REV.YTD`、`FIN.COST.YTD`）页码上，是否算通过？请给**是/否**，并说明若为「否」，148 家信号依赖的处理方式（是 S05 内 HOLD，还是要回到 S04 重判候选资格）。

**Q3｜M08 期间口径统一为公式的 `t`，还是沿用冻结引擎的 `{t, t-1y}`？**
我倾向 `t`（按公式），但这会让 S05 与 S04 的 `signal_dependency_members` 口径不一致。请裁定由哪一侧改，或明确「两侧各自登记、不算冲突」。

**Q4｜仅限 S04 采用的来源（839 项精确处置 + 5 条语言前提）在 S05 怎么处理？**
哪些可以直接沿用、哪些必须回页复核、哪些只能记 `QUALITY_HOLD`？请给可执行的分界，不要只说「按需」。

**Q5｜#53 的残余范围与 #40 的执行占用怎么分开？**
`#53` 仍 OPEN 且 lease 在 Codex 手上，`#40` 也 OPEN。谁在什么条件下可以把执行卡从 #53 转到 #40？以及本轮这 15 行 / 13 格 / 5 家待核，是**开工前必须先核完**，还是可以带着 `PENDING_*` 状态开工、只把受影响格子记 `QUALITY_HOLD`？（后者我按 Q2 的有界挂账理解，但请你确认，不要让我自己推定。）

## 4. 复现方式（只读，不改任何冻结文件）

```bash
python runs/issues/S04/workbuddy_handoff_20261119/step_a_verify.py   # 19/19
python runs/issues/S04/workbuddy_handoff_20261119/step_b_build.py    # 重建 B 产物
python runs/issues/S04/workbuddy_handoff_20261119/step_b_verify.py   # 21/21
```

## 5. 我不主张的事

- 本文件**不是** `release_S05`，也不构成放行建议。
- 8,623 行「可判」只表示结构化证据链齐备（文档 + 页码 + 状态 + 口径 + 无开放争议），**不等于逐页复核**；本轮没有回读 PDF 原文。
- 18,434 是开放争议成员触达数，**不是坏值数**，也不是必须清零才能开工的门槛；9,050 / 18,434 / 8,718 / 839 是四个不同量纲，不得相减。
- 278 家**不是**机器人业务确认、**不是**投资名单、**不等于**全部字段合格。
