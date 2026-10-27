# 上市日期回填报告（listing_date）

- 生成时间：2026-10-27T01:22:01Z
- 侧表：`data/company_listing_dates.csv`（sha256 `5a1eced9b3392bb78399a81a0ee4fdf51d1387997062a1cc359bacb0c4d2f9ef`）
- 覆盖：**1054/1054**，日期范围 1992-07-24 — 2026-09-09
- 未匹配：0；简称与交易所不同：2（代码一致，属除权标记 XD 或更名）

## 一、数据来源（全部为交易所官方名单）

| 市场 | 来源 | 原始行数 | 六位代码行数 | 原始快照 sha256 |
|---|---|---:|---:|---|
| SZ | 深交所上市公司列表（`stock_info_sz_name_code`） | 2906 | 2906 | `df02851865a26e1c…` |
| SH | 上交所主板A股列表（`stock_info_sh_name_code`） | 1700 | 1700 | `46b4183df327b11d…` |
| SH | 上交所科创板列表（`stock_info_sh_name_code`） | 618 | 618 | `84fccf2fab0083ad…` |
| BJ | 北交所上市公司列表（`stock_info_bj_name_code`） | 353 | 353 | `fd00a41c1bdab93f…` |

原始快照与归一化文件在 `runs/listing_dates/raw/`，`fetch_manifest.json` 记录每个文件的哈希。
注：上交所科创板是独立名单（`symbol=科创板`），默认参数只返回主板；首轮漏掉 157 家 688 代码即因此，已修正。

## 二、按 P00 规则重判空目录槽位

P00 `not_applicable_decision_table` 的三条硬规则：
- `listing_date > period_end` → `NOT_APPLICABLE_PRE_LISTING`
- `listing_date <= period_end` → `APPLICABLE`（应取得该期定期报告）
- 北交所公司上市前曾在股转系统挂牌 → `APPLICABLE_WITH_DIFFERENT_PLATFORM`（不得判不适用）

台账中带上市日期判定证据的槽位共 **77** 个，按 reason_code 分布：

| reason_code | 槽数 | 含义 |
|---|---:|---|
| `APPLICABLE_WITH_DIFFERENT_PLATFORM_NEEQ` | 5 | 北交所上市前在股转挂牌 → 平台不同，需另找股转归档 |
| `LISTING_DATE_AFTER_PERIOD_END` | 72 | 上市日晚于报告期结束 → 不适用（存在性已排除） |

### 逐槽明细

| 证券 | 简称 | 槽位 | 上市日 | 报告期结束 | 现状态 |
|---|---|---|---|---|---|
| 001232 | 嘉立创 | annual_2023 | 2026-08-04 | 2023-12-31 | NOT_APPLICABLE_PRE_LISTING |
| 001232 | 嘉立创 | annual_2024 | 2026-08-04 | 2024-12-31 | NOT_APPLICABLE_PRE_LISTING |
| 001232 | 嘉立创 | annual_2025 | 2026-08-04 | 2025-12-31 | NOT_APPLICABLE_PRE_LISTING |
| 001232 | 嘉立创 | h1_2024 | 2026-08-04 | 2024-06-30 | NOT_APPLICABLE_PRE_LISTING |
| 001232 | 嘉立创 | h1_2025 | 2026-08-04 | 2025-06-30 | NOT_APPLICABLE_PRE_LISTING |
| 001232 | 嘉立创 | q1_2026 | 2026-08-04 | 2026-03-31 | NOT_APPLICABLE_PRE_LISTING |
| 001365 | 天海电子 | annual_2023 | 2026-05-18 | 2023-12-31 | NOT_APPLICABLE_PRE_LISTING |
| 001365 | 天海电子 | annual_2024 | 2026-05-18 | 2024-12-31 | NOT_APPLICABLE_PRE_LISTING |
| 001365 | 天海电子 | annual_2025 | 2026-05-18 | 2025-12-31 | NOT_APPLICABLE_PRE_LISTING |
| 001365 | 天海电子 | h1_2024 | 2026-05-18 | 2024-06-30 | NOT_APPLICABLE_PRE_LISTING |
| 001365 | 天海电子 | h1_2025 | 2026-05-18 | 2025-06-30 | NOT_APPLICABLE_PRE_LISTING |
| 001365 | 天海电子 | q1_2026 | 2026-05-18 | 2026-03-31 | NOT_APPLICABLE_PRE_LISTING |
| 001388 | 信通电子 | annual_2023 | 2025-07-01 | 2023-12-31 | NOT_APPLICABLE_PRE_LISTING |
| 001388 | 信通电子 | annual_2024 | 2025-07-01 | 2024-12-31 | NOT_APPLICABLE_PRE_LISTING |
| 001388 | 信通电子 | h1_2024 | 2025-07-01 | 2024-06-30 | NOT_APPLICABLE_PRE_LISTING |
| 001400 | 江顺科技 | annual_2023 | 2025-04-24 | 2023-12-31 | NOT_APPLICABLE_PRE_LISTING |
| 001400 | 江顺科技 | annual_2024 | 2025-04-24 | 2024-12-31 | NOT_APPLICABLE_PRE_LISTING |
| 001400 | 江顺科技 | h1_2024 | 2025-04-24 | 2024-06-30 | NOT_APPLICABLE_PRE_LISTING |
| 300784 | 利安科技 | annual_2023 | 2024-06-07 | 2023-12-31 | NOT_APPLICABLE_PRE_LISTING |
| 301449 | 天溯计量 | annual_2023 | 2025-12-23 | 2023-12-31 | NOT_APPLICABLE_PRE_LISTING |
| 301449 | 天溯计量 | annual_2024 | 2025-12-23 | 2024-12-31 | NOT_APPLICABLE_PRE_LISTING |
| 301449 | 天溯计量 | h1_2024 | 2025-12-23 | 2024-06-30 | NOT_APPLICABLE_PRE_LISTING |
| 301449 | 天溯计量 | h1_2025 | 2025-12-23 | 2025-06-30 | NOT_APPLICABLE_PRE_LISTING |
| 301458 | 钧崴电子 | annual_2023 | 2025-01-10 | 2023-12-31 | NOT_APPLICABLE_PRE_LISTING |
| 301458 | 钧崴电子 | h1_2024 | 2025-01-10 | 2024-06-30 | NOT_APPLICABLE_PRE_LISTING |
| 301479 | 弘景光电 | annual_2023 | 2025-03-18 | 2023-12-31 | NOT_APPLICABLE_PRE_LISTING |
| 301479 | 弘景光电 | h1_2024 | 2025-03-18 | 2024-06-30 | NOT_APPLICABLE_PRE_LISTING |
| 301563 | 云汉芯城 | annual_2023 | 2025-09-30 | 2023-12-31 | NOT_APPLICABLE_PRE_LISTING |
| 301563 | 云汉芯城 | annual_2024 | 2025-09-30 | 2024-12-31 | NOT_APPLICABLE_PRE_LISTING |
| 301563 | 云汉芯城 | h1_2024 | 2025-09-30 | 2024-06-30 | NOT_APPLICABLE_PRE_LISTING |
| 301563 | 云汉芯城 | h1_2025 | 2025-09-30 | 2025-06-30 | NOT_APPLICABLE_PRE_LISTING |
| 301584 | 建发致新 | annual_2023 | 2025-09-25 | 2023-12-31 | NOT_APPLICABLE_PRE_LISTING |
| 301584 | 建发致新 | annual_2024 | 2025-09-25 | 2024-12-31 | NOT_APPLICABLE_PRE_LISTING |
| 301584 | 建发致新 | h1_2024 | 2025-09-25 | 2024-06-30 | NOT_APPLICABLE_PRE_LISTING |
| 301584 | 建发致新 | h1_2025 | 2025-09-25 | 2025-06-30 | NOT_APPLICABLE_PRE_LISTING |
| 301595 | 太力科技 | annual_2023 | 2025-05-19 | 2023-12-31 | NOT_APPLICABLE_PRE_LISTING |
| 301595 | 太力科技 | annual_2024 | 2025-05-19 | 2024-12-31 | NOT_APPLICABLE_PRE_LISTING |
| 301595 | 太力科技 | h1_2024 | 2025-05-19 | 2024-06-30 | NOT_APPLICABLE_PRE_LISTING |
| 301596 | 瑞迪智驱 | annual_2023 | 2024-05-13 | 2023-12-31 | NOT_APPLICABLE_PRE_LISTING |
| 301598 | 博科测试 | annual_2023 | 2024-12-20 | 2023-12-31 | NOT_APPLICABLE_PRE_LISTING |
| 301598 | 博科测试 | h1_2024 | 2024-12-20 | 2024-06-30 | NOT_APPLICABLE_PRE_LISTING |
| 301602 | 超研股份 | annual_2023 | 2025-01-22 | 2023-12-31 | NOT_APPLICABLE_PRE_LISTING |
| 301602 | 超研股份 | h1_2024 | 2025-01-22 | 2024-06-30 | NOT_APPLICABLE_PRE_LISTING |
| 301603 | 乔锋智能 | annual_2023 | 2024-07-10 | 2023-12-31 | NOT_APPLICABLE_PRE_LISTING |
| 301608 | 博实结 | annual_2023 | 2024-08-01 | 2023-12-31 | NOT_APPLICABLE_PRE_LISTING |
| 301613 | 新铝时代 | annual_2023 | 2024-10-25 | 2023-12-31 | NOT_APPLICABLE_PRE_LISTING |
| 301613 | 新铝时代 | h1_2024 | 2024-10-25 | 2024-06-30 | NOT_APPLICABLE_PRE_LISTING |
| 301622 | 英思特 | annual_2023 | 2024-12-04 | 2023-12-31 | NOT_APPLICABLE_PRE_LISTING |
| 301622 | 英思特 | h1_2024 | 2024-12-04 | 2024-06-30 | NOT_APPLICABLE_PRE_LISTING |
| 301631 | 壹连科技 | annual_2023 | 2024-11-22 | 2023-12-31 | NOT_APPLICABLE_PRE_LISTING |
| 301631 | 壹连科技 | h1_2024 | 2024-11-22 | 2024-06-30 | NOT_APPLICABLE_PRE_LISTING |
| 301632 | 广东建科 | annual_2023 | 2025-08-12 | 2023-12-31 | NOT_APPLICABLE_PRE_LISTING |
| 301632 | 广东建科 | annual_2024 | 2025-08-12 | 2024-12-31 | NOT_APPLICABLE_PRE_LISTING |
| 301632 | 广东建科 | h1_2024 | 2025-08-12 | 2024-06-30 | NOT_APPLICABLE_PRE_LISTING |
| 301638 | 南网数字 | annual_2023 | 2025-11-18 | 2023-12-31 | NOT_APPLICABLE_PRE_LISTING |
| 301638 | 南网数字 | annual_2024 | 2025-11-18 | 2024-12-31 | NOT_APPLICABLE_PRE_LISTING |
| 301638 | 南网数字 | h1_2024 | 2025-11-18 | 2024-06-30 | NOT_APPLICABLE_PRE_LISTING |
| 301638 | 南网数字 | h1_2025 | 2025-11-18 | 2025-06-30 | NOT_APPLICABLE_PRE_LISTING |
| 301677 | 欣兴工具 | annual_2023 | 2026-07-30 | 2023-12-31 | NOT_APPLICABLE_PRE_LISTING |
| 301677 | 欣兴工具 | annual_2024 | 2026-07-30 | 2024-12-31 | NOT_APPLICABLE_PRE_LISTING |
| 301677 | 欣兴工具 | annual_2025 | 2026-07-30 | 2025-12-31 | NOT_APPLICABLE_PRE_LISTING |
| 301677 | 欣兴工具 | h1_2024 | 2026-07-30 | 2024-06-30 | NOT_APPLICABLE_PRE_LISTING |
| 301677 | 欣兴工具 | h1_2025 | 2026-07-30 | 2025-06-30 | NOT_APPLICABLE_PRE_LISTING |
| 301677 | 欣兴工具 | q1_2026 | 2026-07-30 | 2026-03-31 | NOT_APPLICABLE_PRE_LISTING |
| 301682 | 宏明电子 | annual_2023 | 2026-03-25 | 2023-12-31 | NOT_APPLICABLE_PRE_LISTING |
| 301682 | 宏明电子 | annual_2024 | 2026-03-25 | 2024-12-31 | NOT_APPLICABLE_PRE_LISTING |
| 301682 | 宏明电子 | h1_2024 | 2026-03-25 | 2024-06-30 | NOT_APPLICABLE_PRE_LISTING |
| 301682 | 宏明电子 | h1_2025 | 2026-03-25 | 2025-06-30 | NOT_APPLICABLE_PRE_LISTING |
| 301696 | 三瑞智能 | annual_2023 | 2026-04-10 | 2023-12-31 | NOT_APPLICABLE_PRE_LISTING |
| 301696 | 三瑞智能 | annual_2024 | 2026-04-10 | 2024-12-31 | NOT_APPLICABLE_PRE_LISTING |
| 301696 | 三瑞智能 | h1_2024 | 2026-04-10 | 2024-06-30 | NOT_APPLICABLE_PRE_LISTING |
| 301696 | 三瑞智能 | h1_2025 | 2026-04-10 | 2025-06-30 | NOT_APPLICABLE_PRE_LISTING |
| 920011 | 晨光电机 | annual_2023 | 2026-04-08 | 2023-12-31 | NOT_TRIED |
| 920011 | 晨光电机 | annual_2024 | 2026-04-08 | 2024-12-31 | NOT_TRIED |
| 920011 | 晨光电机 | annual_2025 | 2026-04-08 | 2025-12-31 | NOT_TRIED |
| 920011 | 晨光电机 | h1_2024 | 2026-04-08 | 2024-06-30 | NOT_TRIED |
| 920011 | 晨光电机 | h1_2025 | 2026-04-08 | 2025-06-30 | NOT_TRIED |

## 三、口径说明与限制

1. **没有**把「已上市却目录空」直接写成 `NOT_DISCLOSED_BY_ISSUER`：检索式漏项的可能无法排除，按「不能凭一次失败断言未披露」交人工复核。本次该类为 0。
2. 北交所 5 个槽位（920011 晨光电机）**没有**判不适用：该公司上市前在股转系统挂牌，挂牌期间定期报告存在，只是披露平台不同。台账记 `NOT_TRIED` + `APPLICABLE_WITH_DIFFERENT_PLATFORM_NEEQ`，`next_action=SEARCH_NEEQ_ARCHIVE`。
3. 交易所名单只覆盖当前在市公司；退市/长期停牌不在名单内会记 `NOT_FOUND_IN_EXCHANGE_LIST`（本次 0 家）。
4. 上市日期按交易所口径（首次上市日），不区分借壳/重新上市；如需区分须另建实体映射。
5. 未改 `data/company_master.csv`（原始输入）。采集与批次执行改为优先读 `data/company_listing_dates.csv` 侧表。
6. P07 的 `calibration_coverage.csv` 是当时快照（5 槽记 NOT_TRIED），台账已按新证据更新；以 `runs/collection/collection_index.csv` 为准。
