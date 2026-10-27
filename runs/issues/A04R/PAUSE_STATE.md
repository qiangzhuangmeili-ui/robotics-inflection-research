# A04R 断点与续跑说明（2026-10-27 收工）

- **停机原因**：用户要求当日收尾关机，非故障停机
- **停机方式**：`TaskStop` 终止 `tools/a04r_scope_backfill.py` 第二轮；台账按槽落盘、进度按公司落盘，无数据丢失
- **当前状态**：`PAUSED_MID_COLLECTION`，A04 未放行 S00

## 一、已完成

| 项 | 结果 |
|---|---|
| 12 槽台账行数 | 12648 / 12648（每槽 1054 行，无缺失、无重复） |
| 已核取得 | 11058 |
| 待核（正文抽取不足） | 9 |
| 上市前不适用 | 244 |
| 未到期（q3_2026 为主） | 767 |
| 公司未披露 | 4 |
| 截止日后登记 | 0 |
| 未尝试 | 565（116 家） |
| 7 份披露日 UNKNOWN | 已补官方日期 7/7，全部 ≤ 2026-10-25，AC10 转 PASS |
| A03 handoff 计数更正 | 已另存 erratum，未改原文件 |

## 二、剩余工作（按顺序）

1. **续跑季度补采**（约 10 分钟）
   ```bash
   python tools/a04r_scope_backfill.py
   ```
   只处理 116 家（BJ 62 + SH 54）共 565 槽。脚本已内置熔断冷却重试：熔断打开后按 policy 冷却 900s、重置状态、重试同一家，最多 5 次。

2. **北交所挂牌期季度槽判定**（约 10 分钟）
   ```bash
   python tools/a04r_bj_applicability.py --probe    # 拉股转定期报告索引
   python tools/a04r_bj_applicability.py --decide   # 判定 NA / 未披露 / 下载原件
   ```

3. **两年公告/IR 目录补采**（约 2.5 小时，1054 家 × 约 6 页）
   ```bash
   python tools/a04r_announcement_index.py --resume
   python tools/a04r_announcement_index.py --download-hits
   ```
   已完成 1 家（SZ:000026，155 条、6 页、对账通过）作为冒烟样本。

4. **收口**
   ```bash
   python tools/a04r_finalize.py                      # A04R review/handoff/manifest
   python runs/issues/A04/rework/audit_rework.py      # A04 返工复算
   python runs/issues/A04/rework/finalize_rework.py   # A04 复验 review/handoff/manifest
   ```

## 三、已知问题与注意

- **熔断不会自愈**：`source_access.Circuit.allow()` 只有在 `known_good_probe=True` 时才认冷却到期，P05 调用未传该参数，因此同一进程内一旦熔断就永久拒绝。第一轮 357 家、1785 槽因此全部记 NOT_TRIED（已由第二轮回收大部分）。续跑脚本已按「冷却到期 → 清空 states → 重试同一家」处理。
- **2 个槽待人工复核**：`SH:600889 *ST京化` 的 q3_2024/q3_2025 目录 `totalAnnouncement=0`，需换检索式或换源核对；不得直接判未披露。
- **q3_2026 逐项判定已生效**：有目录行且披露日 ≤ 2026-10-25 才取件（已核 132+13 家），无行记 NOT_YET_DISCLOSED，晚于截止日记 AFTER_CUTOFF_DISCLOSED。
- **公告目录尚未开始**：AC11 目前 1/1054，A04 因此不能放行。

## 四、不要做的事

- 不要重置 M00/A00—A03 验收，不要重跑已取得的核心槽。
- 不要因公告目录未完成就先把 A04 判通过。
- 不要在无真实上传与回读回执时给 Drive 写 VERIFIED。
