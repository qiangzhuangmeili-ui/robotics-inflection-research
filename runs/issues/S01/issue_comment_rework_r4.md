SG09 依赖已补齐，并把这**类**问题从结构上堵死。**28 项机器校验 + 23 项合成测试全过**，六项政策违例计数全为 0。规则文件未改（仍是 v2），没有调阈值，没有重采。

## 改了三处

1. **补齐依赖**：`SIGNAL_DEPS` 增加 `SG09: ["M07"]`。
2. **取消默认空集**：`signal_flags()` 原来用 `.get(sid, [])`，依赖没登记就返回空集——「没标记」被当成「干净」。现在改为**未登记返回 None**，L2 判定直接视为不干净，并计 `signal_deps_unregistered`。
3. **新增校验 C16**：规则里每个信号都必须有非空依赖、且依赖里必须包含该信号的主指标；缺项直接 **FAIL**，不再有静默通道。

## 证据

- 新增用例 T21：SG09 在 M07 带 Q06 时继承 Q06、不进 L2。
- 新增用例 T22：SG09 低基数按绝对额确认——增量 1,500 万确认、400 万不确认。
- 匿名计数：`signal_flags_missing_dep = 0`、`signal_deps_unregistered = 0`、`ok_with_q06 = 0`、`ok_with_q12 = 0`、`l2_without_two_clean_dims = 0`。

## 重算变化（匿名计数，不是名单）

| 项 | R3 | R4 |
|---|---|---|
| L2 收紧 | 281 | **280** |
| L2 未入选 | 715 | 716 |
| `q06_signal_fired` | 836 | 910 |
| `q05_confirmed` / `unconfirmed` / `no_confirm_input` | 23 / 48 / 34 | 43 / 77 / 34 |

你复算的 106 条 SG09 缺标记（74 漏 Q06、49 漏 Q05）与这里的增量方向一致：SG09 现在会带上 M07 的 Q06/Q05，L2 少 1 家（对应你提到的「22 条漏 Q05 中影响 1 个 L2 判定」）。

顺带更正一处我上一轮写错的口径：SG01∪SG02 的并集是 **659 家（62.5%）**，不是 718——那个数是我在 SG02 还是 0.05pp 时算的，单位修正后没有同步。已改到 `threshold_rationale.md`、`review.json`、`handoff.md`。

## 未变

阈值偏松（L1 79.8%）、MARGIN/PROFIT 维度同源，按你的意见留到 S04 前 `screen_rules_v3.json`。S02 继续保持 `WAITING_DEPENDENCIES`。
