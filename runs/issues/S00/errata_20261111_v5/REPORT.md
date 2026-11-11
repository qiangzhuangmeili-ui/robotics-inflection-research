# S00 勘误台账 V5 报告（第六轮返工后）

**版本**：ERRATA_V5　**自检版本**：V6（37 项）　**性质**：SELF_CHECK（执行方自检，不构成独立验收）
**日期**：2026-11-12　**上游裁决**：`codex_ruling_round5.md`（第五轮）＋ 第六轮复核（RETURN_FOR_REWORK）

---

## 一、这一版改了什么

### 1.1 第五轮：换判据，不是加补丁

V4 用「行期间 == 文档自身期间」当作「该行未被重述」的充分条件。期间相等只说明日期对得上，不能证明核验记录覆盖了该字段、该表格、该调整原因和派生输入。

| 维度 | V4 | V5 |
|---|---|---|
| 重述闭合判据 | 行期间 == 文档自身期间 | 证据实际覆盖范围 ⊇ 该行断言必需范围 |
| 覆盖范围来源 | 方法名整体认可 | 从证据正文按分句抽极性（`evidence_scope.analyse`） |
| 必需范围来源 | 无 | 按 B 的实际取值状态（`required_scope`） |
| 受限方法 | 定义了 `SCOPE_LIMITED_METHODS` 但未使用 | 强制待核 |
| 依赖展开 | 统一字段映射 | 读 B 的实际 status |
| 补充元数据 | 232 格归「溯源/展示」 | 四类实质字段，全部字段级待核 |
| 差异追溯 | 多标签拼一个 `dispute_id` | 每条差异一个稳定 ID（不含处置状态），逐表哈希 |

### 1.2 第六轮退回的四类实现错误，及修法

| 裁决 | 错在哪 | 修法 | 检验 |
|---|---|---|---|
| 第二节 | `required_scope` 用 `if not own_period` 判断非自身期间，但调用方传的是文档期间字符串 `"20251231"`，非空恒真——1,240 条非自身期间行从未要求 `COMPARATIVE_SCOPE` | 改 `is_own_period(document_period, row_period)` 三态（True/False/None），未知期间单列 `DOC_PERIOD_UNKNOWN` | C33 |
| 第三节 | 极性「出现即视为排除」；`0.00元` 正则会命中 `100.00元` 尾部；「本期发生前期差错更正」被记成排除 | 按分句判 `EXCLUDED` / `AFFIRMED` / `SCOPED_ONLY` 三分，零值正则加负向后视，勾选式版面（标签句 + 下一句「□适用√不适用」）向下配对 | C34 |
| 第二节 | 「同一报告内两个 YTD 相减自动抵消」不成立——`Δ单季 = Δ本期累计 − Δ前季累计`，只有两项调整额相等才抵消；实际父输入常来自不同公告 | 撤销该理由，新增 `PARENT_COMPATIBILITY` 证据维度：两个父输入的文档 / 版本 / 合并范围 / 单位必须兼容 | C26 / C30 |
| 第五、八节 | C14 裁决类只查 evidence 非空；C26 跳过裁决类与确认类；C29 只查列非空；C30 只证明旧标签不被接受；受限表 `ledger_sha256` 全填 `meta_diff.csv` | 逐项改为重算与精确核对（见第四节） | C14 / C24 / C26 / C28 / C29 / C30 / C35 |

### 1.3 极性三分带来的实质变化

全量 17,009 条重述差异的极性分布：

| 极性 | 条数 | 含义 |
|---|---:|---|
| `excluded=ERRATA` | 11,460 | 证据同句明确排除差错更正 |
| `excluded=ERRATA,POLICY_CHANGE` | 4,056 | 同时排除政策变更 |
| `scoped=ERRATA` | 646 | 只对期初未分配利润等权益项目给零值，**不覆盖本字段** |
| 无极性（仅提及） | 591 | 提到但不构成排除 |
| `excluded=POLICY_CHANGE` | 224 | 只排除政策变更，未涉差错更正 |

关键后果：`MERGER_RETRO` 在全量中**已无「明确排除」实例**。典型证据是「同一控制合并范围变更0.00元」——它只说明对期初未分配利润的影响为零，不能推出本字段未被追溯调整。因此所有非自身期间行（1,240 条）在 `COMPARATIVE_SCOPE` 或 `MERGER_RETRO` 上必然留缺口，一律停在待核。这是判据变严的直接结果，不是新的漏判。

### 1.4 累计差分改为父输入兼容性

`required_scope` 对 `DERIVED_CUMULATIVE_DIFF` 行要求 `ERRATA + PARENT_COMPATIBILITY`。兼容性逐行由 B 实算：

```
两个父输入 YTD(t) 与 YTD(t−1q)：
  合并范围 / 单位缩放 / 币种 必须一致
  文档相同 → 兼容
  版本相同（version_used 非空）→ 兼容
  任一父输入在采用审计内 → 兼容
  否则 → 不兼容
```

实测：`parent_compatible` YES 3,566 / NO 133 / NA 13,310（非单季字段不适用）。

### 1.5 5,270 条受限方法转待核

`IMPORTANT_MATTER_NA`、`NOTE_RETAINED_ERRATA_ZERO` 两类方法只覆盖「重大会计差错更正」一节，且不绑定字段/表格/行列：

- 自身期间 **5,270 条**（与裁决复算数完全一致）
- 非自身期间 1,103 条
- 合计 `PENDING_SCOPE_LIMITED_METHOD` **6,373 条**

### 1.6 232 格不再整体归展示

| 字段 | 格数 | 新类别 | 依据 |
|---|---:|---|---|
| `evidence_label` | 85 | AFFECTS_ADOPTION_EXPLANATION | 采用解释（国机通用新增仲裁标签） |
| `source_page` | 78 | AFFECTS_TRACE_LOCATION | 证据定位（同方股份 61→137） |
| `slot_id` | 43 | AFFECTS_PROVENANCE | 供给槽位（q1_2025→annual_2025） |
| `status_reason` | 26 | AFFECTS_QUALIFICATION_REASON | 资格理由 |

---

## 二、结果

### 2.1 台账总量不变，分类重排

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

`RESOLVED_RESTATEMENT_CONFIRMED` 为 **0 条**：8 条 B=是 的行事件已由证据确认，但取值来源为分季度表/比较列，来源维度未核，按新判据只能停在 `PENDING_CONFIRMED_EVENT_FIELD_OPEN`。这比 V5 首版把它们记为「已确认」更严格，也是第六轮第三节要求的。

### 2.2 重述差异：73 个同质分组

| 条数 | 文档 | 分组 | 处置 |
|---:|---:|---|---|
| 3,406 | 365 | NOTE_TRACE_NA \| ERRATA \| EXTRACTED \| OWN | 已解决 |
| 2,346 | 252 | IMPORTANT_MATTER_NA \| ERRATA \| EXTRACTED \| OWN | **待核** |
| 2,319 | 249 | NOTE_TRACE_NA \| ERRATA+POLICY \| EXTRACTED \| OWN | 已解决 |
| 1,335 | 355 | NOTE_TRACE_NA \| ERRATA \| DERIVED \| OWN | 已解决 |
| 978 | 259 | IMPORTANT_MATTER_NA \| ERRATA \| 分季度表 \| **比较列** | **待核**（1 条裁决解除） |
| 926 | 249 | IMPORTANT_MATTER_NA \| ERRATA \| 分季度表 \| OWN | **待核** |
| 917 | 244 | IMPORTANT_MATTER_NA \| ERRATA \| DERIVED \| OWN | **待核** |
| 914 | 245 | NOTE_TRACE_NA \| ERRATA+POLICY \| DERIVED \| OWN | 已解决 |

### 2.3 全池影响（1054 家）

| 分类 | V4 | V5 |
|---|---:|---:|
| NOT_AFFECTED | 331 | 329 |
| STILL_PASSES_WITHOUT | 77 | 73 |
| HOLD_PENDING_ERRATA | 37 | **43** |
| R2_MAY_CHANGE | 203 | 207 |
| R1_NO_LINK | 406 | 402 |

HOLD 43 是待核传播范围扩大的直接结果，**不是最终结论**；207 只表示候选依赖命中待核键，不证明漏筛或应入选。受限声明 294 行 / 283 个唯一差异 ID。

---

## 三、分层方法抽验

37 条样本、20 个风险类型（`sampling_v5.csv`），按风险类型确定性抽样。第六轮要求补的三类：

| 风险类型 | 条数 | 覆盖内容 |
|---|---:|---|
| R1 分季度表自身期间 | 3 | 直接取自分季度表，NA 证据不涉该表 |
| R2 累计差分 | 3 | YTD(t)/YTD(t−1q) 父输入 |
| R3 Q1 | 1 | SQ == YTD，不减上年年末 |
| R4 比较列 | 3 | 行期间≠文档自身期间 |
| R5 重述原因 | 2+2+4 | MERGER_RETRO（提到但未排除）/ POLICY_CHANGE / **肯定发生** |
| **R6 跨文档父输入** | 3 | 两父输入来自不同文档，须核文档/版本/范围/单位兼容 |
| **R7 PARTIAL 原文定位** | 3 | 记录页只部分命中，须在全文定位证据实际所在页 |
| R8 山东钢铁正例 | 1 | 裁决点名 |
| R9 大豪科技已解除 | 1 | 裁决点名 |
| R10 杭叉跨来源 | 2 | 采用审计为候选待复核 |
| R11 补充字段 | 6 | source_page / evidence_label / slot_id / status_reason / value_raw / unit_scale |
| R14 假设方法 / R15 证据冲突 | 2 / 1 | `ASSUMED_NO_PENDING_REVIEW` / 旧判定与 B 相反 |

**原件回读**（`pymupdf`，按核验记录页码取页）：

| 结果 | 条数 | 说明 |
|---|---:|---|
| MATCH | 17 | 页码 + 证据 + 文档身份三者对得上 |
| PARTIAL | 7 | 核验者写的汇总注，非原文逐字 |
| NO_PAGE_RECORDED | 4 | 假设方法行，记录本身无页码 |
| NOT_APPLICABLE | 6 | 补充字段样本，按字段类型核验 |

**PARTIAL 全文定位**（R7，3 条）：

| 样本 | 记录页 | 全文最佳匹配 | 结论 |
|---|---|---|---|
| `SH:600053 FIN.NPDEDT.SQ@20250630` | p.168 | p.60，命中率 0.143 | 汇总注，非原文，不能作字段级证据 |
| `SH:600215 FIN.NPDEDT.SQ@20250630` | p.159 | p.159，命中率 0.286 | 同上，记录页正确但内容为汇总注 |
| `SH:600936 FIN.REV.SQ@20250630` | p.11 | 全文未找到 | **证据文本在原件中不存在，须重新核验** |

第三条是这轮抽验的新发现：该行的核验证据无法在供给文档里定位，属于上游核验记录本身的问题，已记入待核清单。

裁决点名的三项：

- **大豪科技 `SH:603025 FIN.REV.SQ@20250331`**：`RESOLVED_BY_RULING`，回读 p.56 MATCH 1.00，未被重新挂起。该行 `scope_required` 记 `ERRATA;COMPARATIVE_SCOPE;MERGER_RETRO`、`scope_missing` 同值——裁决解除不等于范围已证成，必需范围照常登记。
- **山东钢铁 `SH:600022` 四条（`FIN.REV.SQ`/`NPDEDT.SQ`/`NPP.SQ`/`OCF.SQ` @20250630）**：全部 `PENDING_SCOPE_LIMITED_METHOD`，保持重开。
- **杭叉 `SH:603298`**：两条样本 `RESOLVED_SCOPE_COVERED`，但受限表将其采用链标为候选待复核，不充当独立验收。

---

## 四、自检（V6，37 项）

`verify_v5.py` **37/37 PASS** → `SELF_CHECK_PASS_WITH_UNRESOLVED_ITEMS`。相对上一版 34 项，本轮新增/重写：

| 检查 | 内容 |
|---|---|
| C14 | 裁决类必须命中 `rulings_resolved.json` 且键一致、依据非空；确认类须 B=是 **且** 事件层确认 **且** 来源维度无缺口；覆盖类按重算范围比对 |
| C24 | 放行必须有 `content_review=CONFIRMED` 记录，并注入「无审查记录放行」反例验证能拦住 |
| C26 | 全类别双向重算（含裁决类、确认类），标签必须等于重算得到的唯一允许标签 |
| C28 | 重算 `dispute_id`（不含处置状态）+ 逐表引用同键 + `dispute_count` 与列表一致 |
| C29 | 按重算覆盖判定，不看台账自报的 `scope_*` 列 |
| C30 | 先把 V4 旧标签映射为当前类别，再注入三种实质反例 |
| C31 | 必需风险类型扩到 12 类，R7 须给出定位结论 |
| C33 新 | 期间参数三态 + 非自身期间必须要求 `COMPARATIVE_SCOPE`（全量 1,240 行核验） |
| C34 新 | 极性四反例：肯定发生 / 政策变更 / `100.00元` 不误命中 / 勾选式不适用 / 权益零值只算 `SCOPED_ONLY` |
| C35 新 | 受限表 4 列逐表哈希 + 基础列改四表联合摘要 + `dispute_ledger` 逐条源表哈希 |

**故障注入实测**：

| 对象 | 结果 |
|---|---|
| V1 台账 | C13 检出 **6**、C14 检出 **11,936**、C17 检出 **12,076**，三项独立拦截 |
| V4 台账（标签映射后） | C26 检出 **6,457**、C14 检出 **5,345**、受限方法自身期间 **5,270** |
| V5 台账自身 | 四项全 0，`pass=true` |
| 定向反例 | 范围不足 → `PENDING_SOURCE_PROVENANCE`；肯定发生 → `UNRESOLVED_EVIDENCE_CONTRADICTS`；父输入不兼容 → `PENDING_PARENT_COMPATIBILITY` |

上一版报告写的「C14 437 / C17 140」是错误数（当时只统计了 V1 的部分行），本轮实测为 11,936 / 12,076。

---

## 五、仍未覆盖（不作放行依据）

1. **未回读全部原文**。抽验回读 37 条，覆盖 1,007 份核验文档中的 20 份。
2. **9,927 条 `NOTE_TRACE_NA` 已解决项未做方法适用性复审**。它们目前按「排除差错更正」闭合，但 `NOTE_TRACE_NA` 是勾选式版面，仍需确认勾选指向的栏目是否就是本字段。
3. **`NOTE_RETAINED_ERRATA_ZERO` 642 条（自身 563 + 非自身 79）待核实**，未凭注记批量放行。
4. **锚定期回退与上游准入的间接依赖未覆盖**。
5. **1,505 格补充元数据只登记了字段级核验要求**，尚未逐项核完。
6. **`AFFECTS_QUALIFICATION` 类未判定是否影响本次资格**，仅登记。
7. **第 4 步批量核证、第 5 步重算分层未做**，43 / 207 / 445 均未锁定。
8. **`SH:600936` 的证据文本在原件中无法定位**，属上游核验记录问题。

---

## 六、状态

| 事项 | 状态 |
|---|---|
| 第六轮裁决第 1–3 步（修方法 / 分层抽验 / 修自检与追溯） | 已完成，37/37 PASS |
| 第 4 步批量核证 | 未开始 |
| 第 5 步重算分层与受限表 | 未开始 |
| S00 补充验收 | 仍 RETURN_FOR_REWORK，待第七轮复核 |
| B 输入 | 保留计算与追溯用途 |
| S04 第二轮正式验收 | 暂不启动 |
| S05 | WAITING_DEPENDENCIES，不放行 |

执行方自检通过不等于独立验收通过。
