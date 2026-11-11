# S00 勘误 V5 交接说明（第六轮返工后，2026-11-12）

## 一句话

V5 换掉了「期间相等即闭合」这个错判据，改成「证据覆盖范围 ⊇ 该行断言必需范围」；第六轮返工把期间参数改成显式三态、极性改成三分、累计差分的父输入兼容性单列成证据维度。核心待处置 2,496 → **7,841**，含补充列 **9,346**。

## 复现

```bash
cd runs/issues/S00/errata_20261111_v5
python build_errata_v5.py     # 四份台账 + summary.json
python check_l2_v5.py         # 全池 1054 家影响判定 + 受限表 + 差异台账
python sampling_v5.py         # 分层抽验 37 条 + 原件物理页回读 + PARTIAL 全文定位
python verify_v5.py           # 37 项自检
```

依赖顺序：`build` → `check_l2` → `sampling` → `verify`。`verify` 读前两步产物，并对台账做独立重算。

## 关键数

| 项 | 数 |
|---|---|
| 重述差异 | 17,009（`RESOLVED_SCOPE_COVERED` 9,971 / 待核未闭合 7,037 / 裁决解除 1） |
| 值差异 | 240（已解决 206，未闭合 34） |
| 键差异 | 2,056（已解决 1,651，未闭合 405） |
| 核心元数据差异 | 17,728 |
| 补充元数据差异 | 1,505（19 列，全部字段级待核） |
| 唯一差异 ID | 9,346 |
| 受限声明 | 294 行 / 283 个唯一差异 ID |
| 全池 1054 家 | NOT_AFFECTED 329 / STILL_PASSES_WITHOUT 73 / HOLD_PENDING_ERRATA 43 / R2_MAY_CHANGE 207 / R1_NO_LINK 402 |
| 非自身期间行 | 1,240（一律要求 `COMPARATIVE_SCOPE`，当前全部未闭合） |
| 自检 | 37/37 PASS → `SELF_CHECK_PASS_WITH_UNRESOLVED_ITEMS` |
| 故障注入 | V1：C13 6 / C14 11,936 / C17 12,076；V4 映射后：C26 6,457 / C14 5,345 / 受限方法自身期间 5,270 |

## 文件

| 文件 | 作用 |
|---|---|
| `evidence_scope.py` | 证据覆盖模型（判据唯一实现：期间三态 / 极性三分 / 父输入兼容） |
| `l2_core.py` | 依赖引擎（按 status 展开父键，生产与自检共用） |
| `build_errata_v5.py` | 四份差异台账 |
| `check_l2_v5.py` | 全池影响判定、受限表、差异 ID 台账 |
| `sampling_v5.py` | 分层抽验 + 原件回读 + PARTIAL 全文定位 |
| `verify_v5.py` | 37 项自检（C01–C35，含 C21a/b/c） |
| `cell_diff.csv` | 值差异 240 |
| `key_diff.csv` | 键差异 2,056 |
| `meta_diff.csv` | 核心元数据 17,728（含 status_B / is_own_period / parent_compatible / polarity / scope 六列） |
| `extra_meta_diff.csv` | 补充元数据 1,505（含 document_changed / period_source_changed） |
| `dispute_ledger.csv` | 9,346 条唯一差异 ID（含逐条源表哈希） |
| `restricted_claims.csv` | 294 行受限声明（逐表差异 ID + 逐表哈希） |
| `l2_dependency_check.csv` | 1054 家分层 |
| `sampling_v5.csv` | 37 条抽验样本 / 20 类风险 |
| `rulings_resolved.json` | 已裁决解除项（防止被新判据重开） |
| `summary.json` / `review.json` | 汇总与自检结果 |

## 下一步（按第六轮裁决第十节顺序）

第 1、2、3 步已完成。剩：

**第 4 步 按已验证方法批量核证**，优先级：

1. `PENDING_SCOPE_LIMITED_METHOD` 6,373 条。先做 `NOTE_RETAINED_ERRATA_ZERO`：自身期间 563 条、非自身期间 79 条，共 642 条——证据已量化 0.00 元，但只对权益项目给零，**不能凭注记批量放行**，须逐条回读原注确认口径。
2. `PENDING_WEAK_ASSUMPTION` 515 条——从未查过原文，须回读。
3. `PENDING_SOURCE_PROVENANCE` 47 条——分季度表来源与采用链。
4. `PENDING_CONFIRMED_EVENT_FIELD_OPEN` 8 条（`*ST九鼎`、`派斯林` 等）——事件已确认、来源维度未核，须定性。
5. 补充元数据 1,505 格，按 `FIELD_REQ` 的分类要求逐项核，放行必须有 `content_review` 记录。

**第 5 步 重算分层与受限表再报**。不固定维持 43 / 207 / 445。

## 坑（别踩）

- `meta_diff.csv` 的 `scope_required`/`scope_covered`/`scope_missing` 是台账自报，`C14`/`C26`/`C29` 会独立重算并比对；改台账不改代码会被抓。
- `required_scope(status, document_period, row_period)` 必须传三个参数。传两个或把文档期间字符串当布尔用，会让非自身期间行悄悄丢掉 `COMPARATIVE_SCOPE`——这正是第六轮退回来的原因。
- 极性不能「出现即排除」：`同一控制合并范围变更0.00元` 只对权益项目给零，不算排除本字段；`0.00元` 正则必须带负向后视，否则命中 `100.00元`。
- `l2_core.expand()` 里 `QUARTERLY_TABLE` 分支必须排在 Q1 判断之前：分季度表直接取值连 YTD 父键都没有；若顺序反了，Q1 行会多出 YTD(t)。
- `dependency_keys` 不传 `status_of` 时走并集保守口径，只能用于自检；生产必须传。
- `rulings_resolved.json` 里的大豪科技条目不要删。删了 C32 会 FAIL。
- `dispute_id` 不含 `resolution`：处置标签一改 ID 就漂移，无法作为持久引用。
- 原件在 `D:/StockResearchLab/IndustryInflectionLab/robotics_data/collection/originals/<code>/<slot>/<document_id>.pdf`。
