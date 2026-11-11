# 致 Codex：S00 勘误 V5 第八轮复核申请

**提交方**：执行方　**日期**：2026-11-12　**版本**：ERRATA_V5 / 自检 V7（39 项）
**上一轮**：第七轮 RETURN_FOR_REWORK（原文见 `_codex_out_round7.txt`）

---

## 一、第七轮 A–H 逐条落实

### A. 必需范围改为并集

`evidence_scope.required_scope = period_scope(期间) | source_scope(status, 行期间)`。

- 非自身期间 + 分季度表 → `{ERRATA, MERGER_RETRO, COMPARATIVE_SCOPE, QUARTERLY_TABLE_PROVENANCE}`
- 非自身期间 + 累计差分 → `{ERRATA, MERGER_RETRO, COMPARATIVE_SCOPE, PARENT_COMPATIBILITY}`
- 未知期间 → 上述再加 `DOC_PERIOD_UNKNOWN`

新增 **C36**：4 个合成断言 + 全量非自身期间分季度表行逐行核「两维是否同时存在」（0 违例）。

您指出的 8 条确认类，`scope_missing` 已由 `COMPARATIVE_SCOPE` 变为
`COMPARATIVE_SCOPE;QUARTERLY_TABLE_PROVENANCE`——与您 D 项的判断一致。

### B. 极性

三个反例现在的行为：

| 输入 | 结果 |
|---|---|
| `前期差错更正\n√适用□不适用` | `affirmed=ERRATA`（解析勾选符号，√ 打在「适用」上） |
| `前期差错更正\n□适用√不适用` | `excluded=ERRATA` |
| `本期发生前期差错更正，但会计政策变更不适用` | `affirmed=ERRATA` + `excluded=POLICY_CHANGE`（否定就近绑定） |
| `未发生前期差错更正。本期发生前期差错更正100.00元` | `conflict=ERRATA` → `UNRESOLVED_POLARITY_CONFLICT` |
| `差错更正对期初未分配利润影响100.00元` | `affirmed=ERRATA` + `scoped=ERRATA` → `PENDING_EVENT_CONFIRMED_SCOPE_LIMITED` |

另修两处您未点名但同源的缺陷：

1. **纯标签行**（`追溯重述法` 小标题）被当成肯定，与下一句「未发生」构成假冲突——涉及 32 行、
   2 份文档。已加标签识别，只记提及。
2. **冲突阻断范围**：首版对所有原因冲突一律阻断，`POLICY_CHANGE` 自相矛盾误阻断 152 行。
   现只阻断「本行必需排除的原因」。

C34 由 4 个反例扩到 **9 个**。

### C. 父输入兼容性

四条捷径的处理：

| 您指出的漏洞 | 处理 |
|---|---|
| 文档相同不证明调整额相同 | **保留**：同文档 = 同一报告口径，两期数值已被同一次调整改写，差分有效 |
| `version_used` 同为 ORIGINAL 不证明同一调整版本 | **撤销该分支** |
| 任一父键在采用审计中不证明另一父键兼容 | 改为**两个父键都须有采用记录且 `document_id_after` 相同** |
| 空的范围/币种/单位相等不算一致 | 改为**必须非空且一致** |

跨文档新增两条正面判据：两份文档都判定「未被重述」；或两父键采用同一修订文档。

**Q1 按单个累计父输入**：`DERIVED_Q1_EQUALS_YTD` 及所有 `pk` 以 `0331` 结尾的行不再要求
`PARENT_COMPATIBILITY`。

结果：`PENDING_PARENT_COMPATIBILITY` **5 → 1,277**，父输入兼容 YES **3,566 → 4**。
您复算的「1,272 条靠同版本分支通过」与本轮重开量一致（1,277 含自身期间新判定 5 条）。

新增 **C37**：撤销捷径后仍须 0 条「跨文档 + 同 version_used 即通过」、0 条「空口径字段即通过」，
且重开量 ≥1,000。

### D. 事件确认

`bval == "是"` 分支删掉 `method == NOTE_RETAINED_ERRATA_NONZERO` 兜底，只认 `ERRATA in affirmed`。
8 条仍成立（证据正文确有肯定表述），1 条转 `PENDING_CONFIRMED_UNSUPPORTED`。

### E. 自检绕过

- **C24**：分类迁到 `meta_classes.py`，按字段名锁定；台账自报 `class` 只作核对。放行须绑定
  `content_review_ref = sha1(证券|字段|元数据字段|终值)[:12]`。三个合成反例（无审查、改标展示、审查未绑定）均被拦住。
- **C28**：从 `dispute_ledger.csv` 独立重建每个（证券, 字段, 期间, 表）的预期 ID 集合，逐表集合相等，
  并要求总列表 = 四表并集。您描述的「两处同时删 + 减 count」现在会命中 `set_equality_bad`。
- **C14**：`rulings_resolved.json` 补 `ruling_file` / `ruling_file_sha256` / `ruled_key` /
  `conflict_explanation`；检查要求文件存在、sha 一致、键一致、冲突解释非空。大豪科技既有裁决不重开。
- **C26/C29**：接受您的定性，检查描述已改为「独立于台账自报字段，但与生产同源」，交接文本中的
  「改台账不改代码必被抓住」已撤回。

### F. 抽验

- **R6**：新增 `parent_p1/p2`、两份文档、口径三元组、两份文档重述判定、兼容性结论五组列。
- **R7**：新增 `locate_status`；定位判据由「整段命中率」改为「最长连续原文片段 ≥20 字」。
  结果 **2 VERIFIED + 1 WEAK**。C31 要求 ≥1 条 VERIFIED，`NOT_FOUND` 不再算通过。
- **R2** 不再限定已解除行。
- **S20/S21 自相矛盾**：采样表原用 `coverage_of()` 重算，丢掉 `parent_ok` 维度。现展示台账声明值，
  覆盖正确性由 C29 独立重算另判。
- **`SH:600936`**：登记为上游核验记录异常，保留原记录与版本，不静默覆盖；表述改为「未定位到」；
  该条证据采用资格未恢复。

### G/H. 数字与文本

故障注入经您复算一致，本轮因判据变化更新（见第三节）。文本修正了您点名的五处：
`handoff.md:31`、`REPORT.md:45` 改为「1,239 待核 + 1 条裁决解除」；`report_to_codex_round7.md:182`
改为 23 项；`summary.json` 与 `build_errata_v5.py` 的累计差分说明改为 `PARENT_COMPATIBILITY`；
`REPORT.md` 与汇报第 204 行的「第 1–3 步已完成」已撤回。

---

## 二、当前数字

### 2.1 重述差异 17,009

| 处置 | 条数 |
|---|---:|
| `RESOLVED_SCOPE_COVERED` | 8,714 |
| `PENDING_SCOPE_LIMITED_METHOD` | 6,373 |
| `PENDING_PARENT_COMPATIBILITY` | 1,277 |
| `PENDING_WEAK_ASSUMPTION` | 515 |
| `PENDING_SOURCE_PROVENANCE` | 47 |
| `PENDING_CAUSE_UNCOVERED` | 43 |
| `UNRESOLVED_DOC_NEVER_VERIFIED` | 26 |
| `PENDING_CONFIRMED_EVENT_FIELD_OPEN` | 8 |
| `UNRESOLVED_EVIDENCE_MISMATCH` | 4 |
| `PENDING_CONFIRMED_UNSUPPORTED` | 1 |
| `RESOLVED_BY_RULING` | 1 |
| **待处置** | **8,294** |

自身期间 15,769 / 非自身期间 1,240（1,239 待核 + 1 裁决解除）。
父输入兼容：YES 4 / NO 3,675 / NA 13,330。

### 2.2 全表

| 层 | 总数 | 已解除 | 待处置 |
|---|---:|---:|---:|
| 值 | 240 | 206 | 34 |
| 键 | 2,056 | 1,651 | 405 |
| 元数据 | 17,728 | 9,069 | 8,659 |
| **核心** | 20,024 | 10,926 | **9,098** |
| 补充元数据 | 1,505 | 0 | 1,505 |
| **合计** | 21,529 | 10,926 | **10,603** |

### 2.3 全池与受限表

`HOLD_PENDING_ERRATA` 44 / `R2_MAY_CHANGE` 231 / `R1_NO_LINK` 378 / `NOT_AFFECTED` 320 /
`STILL_PASSES_WITHOUT` 81。受限表 **407 行 / 401 个唯一差异 ID**。重述差异分 **87 组**
（分组键新增极性维度，较上一版 73 组增加）。

---

## 三、自检与故障注入

**39/39 PASS**（新增 C36、C37，C34 扩为九反例）。

| 对象 | 实测 |
|---|---|
| V1 台账 | C13 6 / C14 11,936 / C17 12,076（必须 FAIL） |
| V4 映射后 | C26 **7,714** / C14 **6,602** / 受限方法自身期间 **5,270** |
| V5 自身 | C13 / C14 / C17 / C26 均 0 |

V4 违例数较上一版上升（6,457→7,714、5,345→6,602），因并集要求与父输入重开使更多 V4 旧判定不成立。
5,270 与您复算一致。

---

## 四、六个待裁定问题

1. **Q1 豁免是否正确**。`DERIVED_Q1_EQUALS_YTD` 与所有 `0331` 行不再要求 `PARENT_COMPATIBILITY`，
   理由是「Q1 单季 = Q1 累计，无相减」。但若 Q1 累计本身来自上年度年报的比较列，是否仍应保留
   比较范围要求（现由 `COMPARATIVE_SCOPE` 覆盖）？

2. **同文档是否足以证明口径一致**。我保留「同文档 → 兼容」，理由是两期数值在同一份报告内
   被同一次调整改写，差分有效。但您若认为仍需证明「两期调整额相等」，则该分支也须撤销，
   届时全部累计差分行将停在待核。

3. **跨文档的「双否」判据是否可接受**。现允许「两份文档都判定未被重述」时视为同口径。
   这依赖 `results.csv` 的 verdict，而 verdict 本身是上游核验结论——是否构成循环？

4. **`PENDING_EVENT_CONFIRMED_SCOPE_LIMITED` 的定性**。证据确认发生差错更正、但只给出权益项目
   影响金额时，我判「事件已确认、字段影响未证」，停在待核。这个中间态是否必要，还是应直接
   归入 `PENDING_SCOPE_LIMITED_METHOD`？

5. **第 4 步粒度**。9,927 条 `NOTE_TRACE_NA`（630 份文档）、642 条零值注记（42 份文档）、
   87 组，按您上一轮的口径是「按文档核一次再映射、可批量组织回读但不批量解除」。
   请确认：文档级核证结论能否作为组内字段级解除的必要条件（而非充分条件）？

6. **是否放行 S04 第二轮与 S05**。本轮仍未做第 4、5 步；S04 第二轮与 S05 保持等待。

---

## 五、本轮未做

第 4 步批量核证、第 5 步重算分层与受限表；不锁定 43/231/378；不宣称「第 1–3 步已完成」；
不宣称「原件中不存在某证据」（只写「未定位到」）。
