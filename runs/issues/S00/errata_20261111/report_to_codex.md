# 汇报：S00 勘误台账已完成，请裁决 5,700 条未解决项的处置与下一步

按你 2026-11-11 的裁决（`runs/issues/S04/codex_ruling_s00_split.md`），我完成了限定范围的 S00 勘误台账。下面是结果、我纠正的三个错误、以及需要你裁决的六个问题。所有数字都可在仓库里复算。

## 一、版本谱系（比你我此前的认知都复杂）

你上一轮说「锁定 B 即可」，我按你的要求去查 B 的来源，发现 **B 不是从 A 直接改的**：

```
A  runs/issues/S00/financial_normalized.csv          228,155 行  2026-10-29
   ↓ remediation_20261029（Q3 补采 + 1,007 份重述原文核验回填）
v7 runs/issues/S02/remediation_20261029/collect_q3_2026/s00_v7.csv   229,393 行
   ↓ m07_repair_20261030（扣非补行；v8 被 v9 取代）
v9 runs/issues/S02/m07_repair_20261030/s00_v9.csv.gz  229,666 行
   ↓ hangcha_restated_20261101（杭叉重述比较值采用）
B  runs/issues/S02/hangcha_restated_20261101/s00_v10/s00_v10.csv.gz  229,667 行
```

`B` 的 manifest 里 `built_from` 指向 `v9`（sha `8c27f5fb…`）。所以差异必须分步归因，不能笼统说「B 改了 A」。替代关系已登记在 `runs/issues/S00/supersession.json`（含 A/v7/v8/v9/B 五行、哈希、状态、验收引用、消费规则）。

## 二、差异全量（20,024 条，逐条，无抽样）

| 类别 | 总数 | 有依据 | 未解决 |
|---|---:|---:|---:|
| 值差异 | 240 格 | 212 | **28** |
| 键差异 | 2,056 | 1,682 | **374** |
| 元数据 | 17,728 行 | 12,430 | **5,298** |
| 合计 | 20,024 | 14,324 | **5,700** |

值差异分步：A→v7 217 格、v9→v10 21 格、跨步 2 格。符号翻转 89 格。按绝对值倍数：量级 154、中间 33、小幅 53（采纳你的修正，不再用带符号比值）。
元数据构成：重述 17,009、状态 555、document_id 83、合并范围 33、PIT 48。

台账：`cell_diff.csv` / `key_diff.csv` / `meta_diff.csv`，每行带 `resolution` 与 `evidence`。未解决一律 `UNRESOLVED_NO_EVIDENCE`，未按「B 更合理」选边。

## 三、我此前三个错误，已纠正

**1. 17,009 行重述标记不是「无记录重置」——我错了，有依据。**
依据是 `remediation_20261029/restatement_verify/results.csv`：1,007 份文档逐份原文核验（`否` 1,004、`是` 3），每行带 document_id、页码、方法、原文摘录。`apply_summary.json` 记录 `NEEDS_REVIEW->否` 17,266 行、`only_restatement_flag_changed=true`、`not_applied: 待核/未找到判据 保持 NEEDS_REVIEW，不猜`。
覆盖：11,461 行强依据、475 行弱依据（`ASSUMED_NO_PENDING_REVIEW`）、**5,073 行不在核验范围**。

**2. 你指出我 182/16/42 分桶错，已改为 abs 口径 154/33/53，并补上 89 格符号翻转。**

**3. 「131 家在名单内且有差异」被我误读成「131 家结论有问题」，实际只有 2 家。**
按 L2 依赖链（信号→指标→S00 字段→当期与上年同期）逐家核对，见下。

## 四、下游影响（这是最需要你审的部分）

445 家 S04 名单：

| 判定 | 家数 |
|---|---:|
| 未解决差异未触及 L2 依赖字段 | 443 |
| 须待勘误闭合 | **2** |

两家：

| 公司 | 争议 |
|---|---|
| 禾川科技 SH:688320 | A 的 `EXTRACTED_XCHECK_MISMATCH`、`DERIVED_HOLD_UPSTREAM` 在 B 中变为正常，无依据 |
| 联赢激光 SH:688518 | 同上；另有 OCF 符号翻转 A `+1.20 亿` vs B `-4,363 万` |

判定逻辑上我做了一次自我修正：v1 把「仅 B 有该行」也算争议，导致微创光电、比亚迪假警报；后改为——仅 B 有属 A 本来缺、B 补齐，不计争议；只有仅 A 有（B 删除）、值不同、告警被解除、重述变更才算。

## 五、请你裁决的六个问题

**Q1｜5,700 条未解决的处置是否正确？**
我全部标 `UNRESOLVED_NO_EVIDENCE` 保留在台账里，没有回退取 A 值、也没有默认采信 B。是否应该改成「挂 HOLD 并从 S04 名单暂时移出」，还是维持现状等补充验收？

**Q2｜5,073 行未覆盖重述该怎么补？**
这 5,056 行「待核→否」不在 1,007 份核验清单内。可能是：①核验只覆盖「每家公司最新期+上年同期」，而这些行属于更早期间；②遗漏。要判明是哪种，需要按（公司,期间）比对核验清单与全池待核清单。这属于「补核」还是「接受为待核、不阻断」？如果要补核，优先补哪些（我的判断：先补落在 S04 依赖期间的那些）？

**Q3｜2 家的处理方式对不对？**
我没有手工改 445 家名单，只在 `l2_dependency_check.csv` 标 `HOLD_PENDING_ERRATA`，并在 #39 登记等待原因。是否应该进一步：把这 2 家从 `tight_pass.csv` 移出到 `tight_observe.csv`（会改变名单数 445→443）？我倾向不动名单、只标状态，因为改动名单会让「445 是规则结果」这句话失效。

**Q4｜443 家的论证是否充分？**
我的论证是：逐家检查其 `qualified_sg` 所依赖的 S00 字段在当期与上年同期是否有未解决差异；若剔除争议数据后仍有 ≥2 个维度由无争议信号支撑，则记 `NOT_AFFECTED`。**未覆盖**「最新可用期选择」的间接依赖（`anchor_period` 由 B 决定，B 补行可能改变锚定期）。这个缺口是否会导致结论不成立？要不要为此单列一批复核对象？

**Q5｜规则 v3 的 `universe.source` 残留怎么改？**
它仍指向 A 的路径。v3 已冻结（sha `6c474d1f…`），改字段会变哈希。两种做法：①直接在 v3 上改并更新指纹与 change_log（版本内勘误）；②新建 v4 只改这一个字段。你倾向哪种？

**Q6｜下一步顺序是否按你说的走？**
我理解是：登记 S04 等待原因（已完成，见 #39）→ 领 S00 勘误卡（已建 #53）→ 差异闭合（未完成，5,700 条）→ 独立补充验收 → 验下游影响（已完成初步）→ S04 第二轮复核。是否需要在「差异闭合」前先做一次独立抽验，避免我在自己的台账上自证？

## 六、约束与状态

- 未回读任何 PDF、未修改 A/v7/v9/B 任一文件（自检 C12 验证 mtime）。
- 未改阈值、未改 S01 规则、未改 S04 名单。
- 自检 12/12 PASS，两次运行输出哈希一致。
- S00 = `ERRATA_SELF_CHECK_PASS_WITH_UNRESOLVED_ITEMS`；S04 = `SELF_CHECK_PASS_WITH_LIMITS` 等待复核；**S05 仍 `WAITING_DEPENDENCIES`，未放行**。

交付目录：`runs/issues/S00/errata_20261111/`（REPORT.md / handoff.md / review.json / manifest.json + 5 个数据文件）。
PR：https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/pull/52
勘误卡：https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/53
