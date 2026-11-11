# S00 勘误 V5 交接说明

## 一句话

V5 换掉了「期间相等即闭合」这个错判据，改成「证据覆盖范围 ⊇ 该行断言必需范围」，并把依赖引擎改成读 B 的实际行状态。核心待处置 2,496 → 7,807（含 5,270 条受限方法重开），含补充列 9,312。

## 复现

```bash
cd runs/issues/S00/errata_20261111_v5
python build_errata_v5.py     # 生成四份台账 + summary.json
python check_l2_v5.py         # 全池 1054 家影响判定 + 受限表 + 差异台账
python sampling_v5.py         # 分层抽验 28 条 + 原件物理页回读
python verify_v5.py           # 34 项自检
```

依赖顺序：`build` → `check_l2` → `sampling` → `verify`。`verify` 会读前面三步的产物。

## 文件

| 文件 | 作用 |
|---|---|
| `evidence_scope.py` | 证据覆盖模型（生产与自检共用，判据唯一实现） |
| `l2_core.py` | 依赖引擎（按 status 展开父键，生产与自检共用） |
| `build_errata_v5.py` | 四份差异台账 |
| `check_l2_v5.py` | 全池影响判定、受限表、差异 ID 台账 |
| `sampling_v5.py` | 分层抽验 + 原件回读 |
| `verify_v5.py` | 34 项自检 |
| `cell_diff.csv` | 值差异 240 |
| `key_diff.csv` | 键差异 2,056 |
| `meta_diff.csv` | 核心元数据 17,728（含 scope 六列） |
| `extra_meta_diff.csv` | 补充元数据 1,505（含来源变更两列） |
| `dispute_ledger.csv` | 9,312 条唯一差异 ID |
| `restricted_claims.csv` | 292 行受限声明 |
| `l2_dependency_check.csv` | 1054 家分层 |
| `sampling_v5.csv` | 28 条抽验样本 |
| `rulings_resolved.json` | 已裁决解除项（防止被新判据重开） |
| `summary.json` / `review.json` | 汇总与自检结果 |

## 下一步（按裁决第十节顺序）

第 1、2、3 步已完成。剩：

**第 4 步 按已验证方法批量核证**，优先级：

1. `PENDING_SCOPE_LIMITED_METHOD` 6,373 条，先做 `NOTE_RETAINED_ERRATA_ZERO` 的 563 条——证据已量化 0.00 元，回读原注确认口径即可批量处理。
2. `PENDING_WEAK_ASSUMPTION` 515 条——从未查过原文，须回读。
3. `PENDING_SOURCE_PROVENANCE` 48 条——分季度表来源与采用链。
4. `UNRESOLVED_EVIDENCE_CONTRADICTS` 8 条——`*ST九鼎`/`派斯林` 等，须定性。
5. 补充元数据 1,505 格，按 `FIELD_REQ` 的分类要求逐项核。

**第 5 步 重算分层与受限表再报**。不固定维持 445 / 43 / 207。

## 坑（别踩）

- `meta_diff.csv` 的 `scope_required`/`scope_covered`/`scope_missing` 是台账自报，`C14`/`C26` 会独立重算并比对，改台账不改代码会被抓。
- `l2_core.expand()` 里 `QUARTERLY_TABLE` 分支必须排在 Q1 判断之前：分季度表直接取值连 YTD 父键都没有；若顺序反了，Q1 行会多出 YTD(t)。
- `dependency_keys` 不传 `status_of` 时走并集保守口径，只能用于自检；生产必须传。
- `rulings_resolved.json` 里的大豪科技条目不要删。删了 C32 会 FAIL。
- 原件在 `D:/StockResearchLab/IndustryInflectionLab/robotics_data/collection/originals/<code>/<slot>/<document_id>.pdf`。
