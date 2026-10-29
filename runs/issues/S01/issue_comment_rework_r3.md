三处剩余问题已修完。**27 项机器校验 + 21 项合成测试全过**，四项政策违例计数均为 0。
本轮**没有重采、没有按命中率调门槛**；SG02 是单位矛盾，按版本纪律处理，v1 原文件一个字节没动。

## 1. SG07 漏传质量标记

- 每个信号现在声明**全部依赖指标**：`SG07 = M08 ∪ M09`、`SG08 = M09`、`SG06 = M05`；信号的 flags 由依赖指标重新合并。
- 更关键的是：**L2 判定不再读信号自报的 flags**，而是从原始指标结果重取（`signal_flags`），所以「输入层漏传」不会因为事后检验也读同一份脏数据而漏过。
- `m08` 补读原始 OCF / 归母的 `low_base_flag`，命中即加 Q05；M08 没有绝对额口径，低基数一律 `NO_CONFIRM_INPUT`，不自动算干净。

新增不变量核验 `signal_flags_missing_dep`，要求为 0（当前 0）。用例 T18（M08 干净、M09 带 Q06 → SG07 继承 Q06、不进 L2）、T19（M08 原始输入带低基数 → Q05 + NO_CONFIRM_INPUT）。

## 2. SG02 的 100 倍单位矛盾

确认是既存错误：M03 返回 pp，JSON 却写 `threshold=0.05, unit=pp`，等于 0.05pp。按你给的两个选项，选了「保留 v1 + 新版本」：

| 文件 | 处理 |
|---|---|
| `screen_rules_v1.json` | **原样保留**，sha256 仍为 `c76d0461…`（校验 C14 通过） |
| `screen_rules_v2.json` | 新建，只改 `signals[SG02].threshold` 0.05 → **5.0**，加 `change_log` 记录来源 |

v1→v2 的机器枚举差异只有 5 个路径：`rules_version`、`frozen_at`、`change_log`、`signals[1].threshold`、`signals[1].note`，**无其他改动**（校验 C15）。勘误见 `runs/issues/S01/erratum_sg02_unit_20261029.md`。

另外把代码里写死的阈值改成**从规则文件读**，以后不会再出现「文字一套、JSON 一套、代码一套」。

匿名重算：SG02 命中 522 → **415**（正是你说的 107 条低于 5pp 的误触发被剔除）；L1 867 → 841；L2 290 → **281**。这是单位一致的算术结果，不是调参。

## 3. UNKNOWN 非旧快照

`_inputs` 改为：**非旧快照必须明确 `CONSOLIDATED`**；`UNKNOWN` 只在 `LEGACY_SNAPSHOT` 行放行（记 Q07，单列例外）。用例 T17（EXTRACTED + UNKNOWN → EXCLUDED_SCOPE/Q12）、T17b（LEGACY + UNKNOWN → OK + Q07）。`ok_with_q12 = 0`。

## 政策违例计数（匿名）

| 计数 | 值 |
|---|---|
| `ok_with_q06` | 0 |
| `ok_with_q12` | 0 |
| `l2_without_two_clean_dims` | 0 |
| `signal_flags_missing_dep` | 0 |
| `q06_signal_fired` / `q06_dimension_flip` | 836 / 202 |
| `q05_confirmed` / `unconfirmed` / `no_confirm_input` | 23 / 48 / 34 |

## 干跑（匿名计数，不是名单）

L1 观察 841 / 仅风险 138 / 无信号 75；L2 收紧 281 / 未入选 715 / 数据不足 58；M01 仍为 565 OK + 386 PROVISIONAL。

## 未变的限制

阈值偏松（SG01∪SG02 覆盖 68%、L1 80%）、MARGIN/PROFIT 维度同源——按你的意见不在本轮处理；收紧留到 S04 前 `screen_rules_v3.json` 全池重算。

逐条映射见 `runs/issues/S01/implementation_notes.md`。S02 继续保持 `WAITING_DEPENDENCIES`。
