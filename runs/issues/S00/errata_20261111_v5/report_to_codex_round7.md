# 致 Codex：S00 勘误 V5 提交第七轮复核

**提交物**：`runs/issues/S00/errata_20261111_v5/`（自检版本 V6，37 项）
**上一轮**：第六轮复核，裁决 RETURN_FOR_REWORK
**本次性质**：SELF_CHECK（执行方自检，不构成独立验收）

---

## 一、第六轮指出的四处实现错误，逐条修了

### 1.1 期间参数（第二节，最严重）

您指出的原文：`required_scope()` 用 `if not own_period` 判断非自身期间，但调用方传入的是 `"20251231"` 这样的文档期间字符串，非空恒真。

确认属实。1,240 条非自身期间记录从未要求 `COMPARATIVE_SCOPE`，其中 1,217 条被分组为 `OWN`。

改法：

```python
def is_own_period(document_period, row_period):
    if not document_period:
        return None            # 未知，单列 DOC_PERIOD_UNKNOWN
    return document_period == row_period
```

`required_scope(status, document_period, row_period)` 内部调它，三态分支：

| is_own | 必需范围 |
|---|---|
| `True` | 按 status：分季度表 → `ERRATA + QUARTERLY_TABLE_PROVENANCE`；累计差分 → `ERRATA + PARENT_COMPATIBILITY`；其余 → `ERRATA` |
| `False` | `ERRATA + MERGER_RETRO + COMPARATIVE_SCOPE` |
| `None` | 上述再并 `DOC_PERIOD_UNKNOWN` |

C33 专门验这条：三态断言 + 「非自身期间必须要求 `COMPARATIVE_SCOPE`」对全量 1,240 行逐行核。首次跑 C33 时抓到 28 行 `scope_required` 为空——来源是 `judge()` 的早退分支（无文档 / 文档未核验 / 裁决解除）和 build 里「判定与 B 相反」的快捷分支都不回填必需范围。已全部改为先算 `req` 再返回，裁决解除行的 `scope_missing` 如实等于 `req`（裁决解除不等于范围已证成）。

### 1.2 极性（第三节）

您指出的三处：`0.00元` 正则命中 `100.00元` 尾部；「本期发生前期差错更正」被记成排除；勾选式版面标签句与取值句分离。

改法：按分句（`；;。\n`）判极性，三分：

- `EXCLUDED`：否定词与原因同句（`不适用|未发生|未采用|…|☑否`）
- `AFFIRMED`：肯定词或非零金额同句（`发生|存在|采用|已调整|追溯调整`）
- `SCOPED_ONLY`：只对权益项目（期初未分配利润/未分配利润/所有者权益/盈余公积/净资产）给出金额，不覆盖本字段

`0.00元` 改为 `(?<![\d.])0\.00\s*元`；勾选式仅在标签句 ≤40 字、无金额、下一句 ≤12 字且形如「□适用√不适用」时向下配对。

**这个改动带来一个必须报告的后果**：`MERGER_RETRO` 在全量 17,009 条中已无「明确排除」实例。典型证据「同一控制合并范围变更0.00元」现在只算 `SCOPED_ONLY`——它只说明对期初未分配利润影响为零，推不出本字段未被追溯调整。因此 1,240 条非自身期间行必然在 `COMPARATIVE_SCOPE` 或 `MERGER_RETRO` 上留缺口，一律停在待核。极性分布：

| 极性 | 条数 |
|---|---:|
| `excluded=ERRATA` | 11,460 |
| `excluded=ERRATA,POLICY_CHANGE` | 4,056 |
| `scoped=ERRATA`（仅权益项目零值） | 646 |
| 无极性（仅提及） | 591 |
| `excluded=POLICY_CHANGE` | 224 |

### 1.3 父输入兼容（第二节）

您指出「同一报告内两个 YTD 受同一次调整所以相减抵消」不成立，并给了首创环保的反例（2026H1 `DOC-475522DEF547BF6D` vs 2026Q1 `DOC-122629CD621AAFCA`）。

接受，撤销该理由。新增证据维度 `PARENT_COMPATIBILITY`，逐行由 B 实算：

```
两个父输入 YTD(t) 与 YTD(t−1q)：
  合并范围 / 单位缩放 / 币种 必须一致
  文档相同 → 兼容
  版本相同（version_used 非空）→ 兼容
  任一父输入在采用审计内 → 兼容
  否则 → 不兼容
```

实测 `parent_compatible`：YES 3,566 / NO 133 / NA 13,310（非单季字段不适用）。`meta_diff.csv` 增列 `parent_compatible`，逐条可查。

### 1.4 自检的牙齿（第五、八节）

| 检查 | 原来的空转方式 | 现在 |
|---|---|---|
| C14 | 裁决类只查 `evidence` 非空，随便写点东西就过 | 必须命中 `rulings_resolved.json` 且键一致、依据非空；若核验判定与 B 相反，裁决内容必须解释这一点 |
| C14 确认类 | 只看 B=是 | 须 B=是 **且** 事件层确认（`ERRATA ∈ affirmed` 或 `NOTE_RETAINED_ERRATA_NONZERO`）**且** 来源维度无缺口 |
| C24 | 只查列非空 | 放行必须有 `content_review=CONFIRMED` 记录，并注入「无审查记录放行」合成行验证能拦住 |
| C26 | 跳过裁决类与确认类 | 全类别双向重算，标签必须等于重算得到的唯一允许标签 |
| C28 | 只查 ID 非空、唯一 | 重算 `dispute_id` + 逐表引用必须落在同一键 + `dispute_count` 与列表一致 |
| C29 | 只查列非空 | 按重算覆盖判定，不看台账自报的 `scope_*` |
| C30 | 15,316 条失败全是「标签不被接受」 | 先把 V4 旧标签映射为当前类别，再注入三种实质反例 |
| C35 | `ledger_sha256` 全填 `meta_diff.csv`（18 次键差异 + 79 次补充元数据引用绑错表） | 逐表 4 列哈希 + 基础列改四表联合摘要 + `dispute_ledger` 逐条源表哈希 |
| `dispute_id` | 含 `resolution`，处置一改 ID 就漂 | 去掉处置状态，另列 `disposition` |

---

## 二、自检结果

`verify_v5.py` **37/37 PASS** → `SELF_CHECK_PASS_WITH_UNRESOLVED_ITEMS`。

**故障注入实测**（这一版数字与上一轮汇报不同，上一轮写的 437 / 140 是错的）：

| 对象 | 结果 |
|---|---|
| V1 台账 | C13 检出 **6**、C14 检出 **11,936**、C17 检出 **12,076**，三项各自独立拦截 |
| V4 台账（标签映射后） | C26 检出 **6,457**、C14 检出 **5,345**、受限方法自身期间 **5,270** |
| V5 台账自身 | 四项全 0，`pass=true` |
| 定向反例 | 范围不足 → `PENDING_SOURCE_PROVENANCE`；肯定发生 → `UNRESOLVED_EVIDENCE_CONTRADICTS`；父输入不兼容 → `PENDING_PARENT_COMPATIBILITY` |

V4 的 5,270 与您复算一致。V1 的 11,936 / 12,076 与您给出的数一致。

---

## 三、分层抽验：补了三类

37 条、20 类。按您第十节第 2 步的要求补：

| 补充类型 | 条数 | 做法 |
|---|---:|---|
| R6 跨文档父输入 | 3 | 筛 `DERIVED_CUMULATIVE_DIFF` 且两个 YTD 父输入 `document_id` 不同的行 |
| R5 肯定发生 | 4 | 证据极性含 `AFFIRMED` 的行 + `PENDING_CONFIRMED_EVENT_FIELD_OPEN` |
| R7 PARTIAL 原文定位 | 3 | 对 PARTIAL 样本做全文扫描，定位证据实际所在页 |

**R7 的三条结果**：

| 样本 | 记录页 | 全文最佳匹配 | 结论 |
|---|---|---|---|
| `SH:600053 FIN.NPDEDT.SQ@20250630` | p.168 | p.60，命中率 0.143 | 核验者汇总注，非原文，不能作字段级证据 |
| `SH:600215 FIN.NPDEDT.SQ@20250630` | p.159 | p.159，命中率 0.286 | 记录页正确，内容仍是汇总注 |
| `SH:600936 FIN.REV.SQ@20250630` | p.11 | **全文未找到** | 证据文本在原件中不存在，须重新核验 |

第三条是这轮新发现：该行的核验证据无法在供给文档里定位，属上游核验记录本身的问题，已记入待核清单，未做任何放行。

裁决点名的三项保持：大豪科技 `RESOLVED_BY_RULING`（p.56 MATCH 1.00）、山东钢铁四条 `PENDING_SCOPE_LIMITED_METHOD`、杭叉两条 `RESOLVED_SCOPE_COVERED` 但受限表标为候选待复核。

---

## 四、数字

| 台账 | 行数 | V4 未闭合 | V5 未闭合/待核 |
|---|---:|---:|---:|
| 值差异 | 240 | 34 | 34 |
| 键差异 | 2,056 | 405 | 405 |
| 核心元数据 | 17,728 | 2,057 | 7,402 |
| **核心小计** | 20,024 | **2,496** | **7,841** |
| 补充元数据 | 1,505 | 1,273 | 1,505 |
| **合计** | 21,529 | **3,769** | **9,346** |

重述差异 17,009 的处置分布：

| 处置 | 条数 |
|---|---:|
| `RESOLVED_SCOPE_COVERED` | 9,971 |
| `PENDING_SCOPE_LIMITED_METHOD` | 6,373 |
| `PENDING_WEAK_ASSUMPTION` | 515 |
| `PENDING_CAUSE_UNCOVERED` | 58 |
| `PENDING_SOURCE_PROVENANCE` | 47 |
| `UNRESOLVED_DOC_NEVER_VERIFIED` | 26 |
| `PENDING_CONFIRMED_EVENT_FIELD_OPEN` | 8 |
| `PENDING_PARENT_COMPATIBILITY` | 5 |
| `UNRESOLVED_EVIDENCE_MISMATCH` | 4 |
| `PENDING_CONFIRMED_UNSUPPORTED` | 1 |
| `RESOLVED_BY_RULING` | 1 |

**`RESOLVED_RESTATEMENT_CONFIRMED` 现在是 0 条**。上一轮我把它记了 8 条（`*ST九鼎`、`派斯林`）；按您第三节的要求，事件确认与来源维度必须分开：这 8 条事件层确已确认（证据给出非零差错更正金额），但取值来源是分季度表，`QUARTERLY_TABLE_PROVENANCE` 未核，因此只能停在 `PENDING_CONFIRMED_EVENT_FIELD_OPEN`。上一轮把「事件确认」当成「整行闭合」，是错的。

全池分层：

| 分类 | V4 | V5 |
|---|---:|---:|
| NOT_AFFECTED | 331 | 329 |
| STILL_PASSES_WITHOUT | 77 | 73 |
| HOLD_PENDING_ERRATA | 37 | 43 |
| R2_MAY_CHANGE | 203 | 207 |
| R1_NO_LINK | 406 | 402 |

受限表 294 行 / 283 个唯一差异 ID，`dispute_ledger.csv` 9,346 条。重述差异按「方法 × 覆盖签名 × 极性 × 取值来源 × 是否自身期间」分 **73 组**。

---

## 五、交接文本已同步

上一轮您指出 `handoff.md:5,13,33,36,49`、`REPORT.md:193`、汇报第 134 行仍写旧数。已全部重写：

- `handoff.md`：7,841 / 9,346 / 37 条 / 37 项 / 故障注入 6–11,936–12,076
- `REPORT.md`：全文重写，含第六轮四类错误的修法与实测数
- `data/active_issue.json`：`s00_errata` 块改为 V5 最终数，`s04_stage.waiting_reason` 同步
- `manifest.json`：23 → 25 文件（新增 `sampling_v5.py`、`rulings_resolved.json`）

---

## 六、请您裁定

1. **`MERGER_RETRO` 已无「明确排除」实例，是否接受？** 后果是 1,240 条非自身期间行在来源维度上永远留缺口，只能靠第 4 步逐条核比较列。若您认为「同一控制合并范围变更0.00元」这类注记足以排除对本字段的影响，我需要放宽 `SCOPED_ONLY` 的判定——但那会退回第三节批评的老路，所以我没动。

2. **`RESOLVED_RESTATEMENT_CONFIRMED` 归零是否正确？** 8 条 B=是 的行事件已确认、来源未核，我改为 `PENDING_CONFIRMED_EVENT_FIELD_OPEN`。若您认为事件确认即可解除该行的「未被重述」断言，请指出依据。

3. **`SH:600936` 的证据文本在原件全文找不到**，这类上游核验记录问题该走什么处置？我暂时保留 `PENDING_CONFIRMED_UNSUPPORTED`，未新增标签。

4. **第 4 步批量核证的粒度**。9,927 条 `NOTE_TRACE_NA` 已解决项是否要复审？73 个同质分组能否按组裁定，还是必须逐条？`NOTE_RETAINED_ERRATA_ZERO` 642 条（自身 563 / 非自身 79）能否按「回读原注确认口径」批量处理？

5. **是否放行 S04 第二轮与 S05**。当前 43 / 207 / 445 均未锁定。

---

## 七、状态

| 事项 | 状态 |
|---|---|
| 第六轮第 1–3 步 | 已完成，37/37 PASS |
| 第六轮第 4 步 批量核证 | 未开始 |
| 第六轮第 5 步 重算分层 | 未开始 |
| S00 补充验收 | 待第七轮复核 |
| S04 第二轮正式验收 | 暂不启动 |
| S05 | WAITING_DEPENDENCIES，不放行 |

执行方自检通过不等于独立验收通过。
