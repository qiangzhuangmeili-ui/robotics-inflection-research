# S08 / #43 交接：指标轮验收与 R00 业务核验名单冻结

- 计划版本：`20261026_collection_first_v2`
- 生成时间（固定）：`2026-11-26T14:30:00+08:00`
- 执行方：CodeBuddy；统筹方：Antigravity；独立复核指派：Codex
- 结论：`ACCEPTED_WITH_LIMITS`（对账异常 0 项）
- 放行控制：`release_R00=false`、`release_R02=false`、`issue_53_touched=false`

## 1. 全池 1,054 家对账

| 阶段 | 计数 |
|---|---|
| S03 宽筛 | 777 pass + 149 defer + 128 unknown = 1,054 |
| S04 收紧 | 445 家 `L2_SHORTLIST_CANDIDATE`（全部位于 wide_pass） |
| S05 质量 | 277 `QUALITY_PASS` + 1 `QUALITY_HOLD` + 776 `OBSERVE_POOL_PRESERVED` = 1,054 |
| S06 观察 | 早期 54 + 缺数据 379；交集 33；非主线并集 399 |
| S08 六分区 | 277 + 1 + 33 + 21 + 345 + 377 = 1,054 |

## 2. S07 F10 闭环：445 -> 278

`s04_to_s05_bridge_445_to_278.csv` 共 445 行，逐家去向：

- `ADMITTED_TO_S05_QUALITY_PASS`：277
- `ADMITTED_TO_S05_QUALITY_HOLD`：1（SZ:000856 冀东装备）
- `DEFERRED_TO_HOLD_FOR_DATA`：167

映射 100% 来自 Git 跟踪冻结表，并关联 Drive 归档 ID `1VrpWyQct6xI5PpRdGNs6KFZmubbspYEA`。

## 3. R00 主线优先级

- `TIER_1_EVIDENCED_AND_CLEAN_OR_LOW_RISK`：18
- `TIER_2_CLEAN_NO_QUALITY_TRIGGER`：40
- `TIER_3_TRIGGERED_OR_PENDING_QUALITY`：219
- 合计：277

说明：零触发共 111 家；其中 69 家仍有 RH02/RH03/RH06 待核。7 家零触发历史资产进入 TIER_1（其中 5 家带待核），64 家零触发带待核公司进入 TIER_3，40 家零触发无待核非历史资产进入 TIER_2。

## 4. 历史成果复用

- 旧 53 家采用：53
- 旧 45 家条件细筛候选：45
- 10 家早期局部样本：10
- B00：7；C00：10；D00：2
- 主表内并集：80；`auto_promoted` 全部为 False
- 剔除不在主表的历史证券：`BJ:920007`（酉立智能）

旧“概念粗筛 20 家先读 PDF”顺序不再提前执行；R00 只按本冻结名单分 5 家小包执行。

## 5. 结转限制

F05 锚定期分层、F06 RH02 项目制豁免 31 家、F07 低基数冻结、F08 BJ 差异仅描述、F09 反向重推限 5 家、F10 已由本桥表闭环、F11 20 格越界值保留、F12 RH06 7 家待核。

守卫：4 家截止日隔离、1 家锚点待重选、15 家质量来源未知、8 项未采用父链、冀东 `SZ:000856` QUALITY_HOLD、`#53` 保持 OPEN。

## 6. 复现

```bash
S08_FIXED_NOW=2026-11-26T14:30:00+08:00 py runs/issues/S08/step_s08_build.py
S08_FIXED_NOW=2026-11-26T14:30:00+08:00 py runs/issues/S08/step_s08_verify.py
```

## 7. 下一步

等待 Codex 独立复核；未获独立验收前不启动 R00/R02，不开展公司业务深研或估值。
