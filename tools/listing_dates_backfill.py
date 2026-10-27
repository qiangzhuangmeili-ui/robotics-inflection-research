"""上市日期回填：沪深北三个交易所官方名单 → 侧表 → 按 P00 规则重判空目录槽位。

背景：P00 冻结时 listing_date 全 1054/1054 UNKNOWN，导致次新股批次的空目录只能记
NOT_TRIED（不得判不适用）。M00_01—06 累计 72 个 NOT_TRIED 全部来自次新股，已成为
覆盖率的主要缺口来源。

用法：
    python tools/listing_dates_backfill.py --fetch        # 取三个官方源并存快照
    python tools/listing_dates_backfill.py --build        # 映射到 1054 池，写 data/company_listing_dates.csv
    python tools/listing_dates_backfill.py --reclassify   # 按 P00 规则重判台账里的空目录槽位
    python tools/listing_dates_backfill.py --report       # 写回填报告

口径（严格照 P00 not_applicable_decision_table）：
- listing_date > period_end            → NOT_APPLICABLE_PRE_LISTING
- listing_date <= period_end 且目录空  → 保留 NOT_TRIED，改原因与 next_action=MANUAL_REVIEW_INDEX
                                        （不直接判 NOT_DISCLOSED_BY_ISSUER：检索式漏项的可能性
                                          无法排除，交由人工复核，避免过度断言）
不改 data/company_master.csv（原始输入），只新增侧表并在采集时优先读侧表。
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs/listing_dates"
RAW = OUT / "raw"
MASTER = ROOT / "data/company_master.csv"
SIDE_TABLE = ROOT / "data/company_listing_dates.csv"
LEDGER = ROOT / "runs/collection/checkpoint"

SIDE_FIELDS = ["security_id", "stock_code", "stock_name", "listing_date", "listing_date_status",
               "source_exchange", "source_table", "name_at_source", "name_match",
               "fetched_at", "note"]

# 报告期结束日与槽位对应（与 P07 collection_config_v1.slots 一致）
SLOT_PERIOD_END = {
    "annual_2023": "2023-12-31", "annual_2024": "2024-12-31", "annual_2025": "2025-12-31",
    "h1_2024": "2024-06-30", "h1_2025": "2025-06-30", "h1_2026": "2026-06-30",
    "q1_2024": "2024-03-31", "q3_2024": "2024-09-30", "q1_2025": "2025-03-31",
    "q3_2025": "2025-09-30", "q1_2026": "2026-03-31", "q3_2026": "2026-09-30",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def read_csv(path: Path) -> list[dict]:
    with Path(path).open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def norm_name(value: str) -> str:
    return (value or "").replace(" ", "").replace("\u3000", "").replace("Ａ", "A").strip().upper()


# ---------------------------------------------------------------- 取数
def fetch() -> dict:
    import akshare as ak

    RAW.mkdir(parents=True, exist_ok=True)
    fetched_at = utc_now()
    plan = [
        ("SZ", "stock_info_sz_name_code", "深交所上市公司列表",
         "https://www.szse.cn/market/product/stock/list/index.html",
         {"code": "A股代码", "name": "A股简称", "date": "A股上市日期"}, {}),
        ("SH", "stock_info_sh_name_code", "上交所主板A股列表",
         "https://www.sse.com.cn/assortment/stock/list/share/",
         {"code": "证券代码", "name": "证券简称", "date": "上市日期"}, {"symbol": "主板A股"}),
        # 科创板在上交所是独立名单，默认参数只返回主板，必须单独取（157/1054 家）
        ("SH", "stock_info_sh_name_code", "上交所科创板列表",
         "https://www.sse.com.cn/assortment/stock/list/share/",
         {"code": "证券代码", "name": "证券简称", "date": "上市日期"}, {"symbol": "科创板"}),
        ("BJ", "stock_info_bj_name_code", "北交所上市公司列表",
         "https://www.bse.cn/nqxxController/nqxxCnzq.do",
         {"code": "证券代码", "name": "证券简称", "date": "上市日期"}, {}),
    ]
    manifest = {"fetched_at": fetched_at, "sources": []}
    for exchange, func_name, label, url, cols, kwargs in plan:
        df = getattr(ak, func_name)(**kwargs)
        board_tag = {"主板A股": "main", "科创板": "star"}.get(kwargs.get("symbol", ""), "listed")
        tag = f"{exchange.lower()}_{board_tag}"
        raw_path = RAW / f"{tag}.csv"
        df.to_csv(raw_path, index=False, encoding="utf-8-sig")
        rows = []
        for _, row in df.iterrows():
            code = str(row[cols["code"]]).strip()
            if len(code) == 6 and code.isdigit():
                rows.append({"stock_code": code, "stock_name": str(row[cols["name"]]).strip(),
                             "listing_date": str(row[cols["date"]]).strip()[:10]})
        norm_path = RAW / f"{tag}_normalized.csv"
        write_csv(norm_path, rows, ["stock_code", "stock_name", "listing_date"])
        manifest["sources"].append({
            "exchange": exchange, "function": func_name, "label": label, "url": url,
            "raw_file": raw_path.relative_to(ROOT).as_posix(),
            "raw_sha256": sha256_file(raw_path),
            "raw_rows": len(df), "normalized_rows": len(rows),
            "normalized_file": norm_path.relative_to(ROOT).as_posix(),
        })
        print(f"[{exchange}] {label}: {len(df)} 行 → {len(rows)} 条六位代码", flush=True)
    write_json(OUT / "fetch_manifest.json", manifest)
    return manifest


# ---------------------------------------------------------------- 建侧表
def build() -> dict:
    master = read_csv(MASTER)
    by_code: dict[str, dict] = {}
    norm_files = sorted(RAW.glob("*_normalized.csv"))
    if not norm_files:
        raise SystemExit("缺少 runs/listing_dates/raw/*_normalized.csv，先跑 --fetch")
    for path in norm_files:
        exchange = path.name.split("_")[0]
        for row in read_csv(path):
            code = row["stock_code"]
            if code in by_code:
                # 同代码多市场（B股等）只保留先到的 A 股口径
                continue
            by_code[code] = {"exchange": exchange.upper(), **row}
    fetched_at = utc_now()
    rows, missing, name_diff = [], [], []
    for item in master:
        code = item["stock_code"]
        hit = by_code.get(code)
        if not hit:
            missing.append({"security_id": item["security_id"], "stock_code": code,
                            "stock_name": item["stock_name"]})
            rows.append({
                "security_id": item["security_id"], "stock_code": code, "stock_name": item["stock_name"],
                "listing_date": "", "listing_date_status": "NOT_FOUND_IN_EXCHANGE_LIST",
                "source_exchange": item["security_id"].split(":")[0], "source_table": "",
                "name_at_source": "", "name_match": "", "fetched_at": fetched_at,
                "note": "交易所名单未匹配到该代码",
            })
            continue
        match = "SAME" if norm_name(item["stock_name"]) == norm_name(hit["stock_name"]) else "DIFF"
        if match == "DIFF":
            name_diff.append({"security_id": item["security_id"], "pool_name": item["stock_name"],
                              "exchange_name": hit["stock_name"], "listing_date": hit["listing_date"]})
        rows.append({
            "security_id": item["security_id"], "stock_code": code, "stock_name": item["stock_name"],
            "listing_date": hit["listing_date"], "listing_date_status": "RESOLVED_FROM_EXCHANGE",
            "source_exchange": hit["exchange"], "source_table": f"{hit['exchange']}_LISTED_COMPANIES",
            "name_at_source": hit["stock_name"], "name_match": match, "fetched_at": fetched_at,
            "note": "" if match == "SAME" else "简称与交易所名单不同（可能更名/风险警示），代码一致",
        })
    write_csv(SIDE_TABLE, rows, SIDE_FIELDS)
    resolved = [r for r in rows if r["listing_date_status"] == "RESOLVED_FROM_EXCHANGE"]
    payload = {
        "built_at": fetched_at,
        "side_table": SIDE_TABLE.relative_to(ROOT).as_posix(),
        "side_table_sha256": sha256_file(SIDE_TABLE),
        "pool_rows": len(master),
        "resolved": len(resolved),
        "missing": len(missing),
        "name_diff": len(name_diff),
        "name_diff_rows": name_diff[:20],
        "missing_rows": missing[:20],
        "coverage": f"{len(resolved)}/{len(master)}",
        "date_min": min((r["listing_date"] for r in resolved), default=""),
        "date_max": max((r["listing_date"] for r in resolved), default=""),
    }
    write_json(OUT / "build_summary.json", payload)
    return payload


# ---------------------------------------------------------------- 重判空目录
def load_listing_dates() -> dict[str, str]:
    if not SIDE_TABLE.exists():
        raise SystemExit("缺少 data/company_listing_dates.csv，先跑 --build")
    return {r["security_id"]: r["listing_date"] for r in read_csv(SIDE_TABLE)
            if r["listing_date_status"] == "RESOLVED_FROM_EXCHANGE"}


def reclassify(dry_run: bool = False) -> dict:
    dates = load_listing_dates()
    changes = []
    for path in sorted(LEDGER.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        security_id = data.get("security_id")
        listing = dates.get(security_id)
        if not listing:
            continue
        dirty = False
        exchange = (security_id or "").split(":")[0]
        # 清理：已取得原件的槽位不应残留「空目录」类 reason_code（历史补采留下的痕迹）
        for slot_id, rec in (data.get("slots") or {}).items():
            if str(rec.get("status", "")).startswith("COLLECTED") and rec.get("reason_code"):
                rec["reason_code"] = None
                dirty = True
        for slot_id, rec in (data.get("slots") or {}).items():
            status = rec.get("status")
            # 只处理两类：空目录留下的 NOT_TRIED；以及此前被误判为不适用、需按北交所规则回退的
            is_empty_not_tried = status == "NOT_TRIED"
            is_bj_misjudged = (exchange == "BJ" and status == "NOT_APPLICABLE_PRE_LISTING"
                               and rec.get("reason_code") == "LISTING_DATE_AFTER_PERIOD_END")
            if not (is_empty_not_tried or is_bj_misjudged):
                continue
            period_end = SLOT_PERIOD_END.get(slot_id) or rec.get("period_end")
            if not period_end:
                continue
            before = {"status": status, "status_reason": rec.get("status_reason"),
                      "next_action": rec.get("next_action")}
            if listing > period_end and exchange == "BJ":
                # P00：北交所公司上市前在股转系统挂牌，挂牌期间定期报告存在，
                # 只是披露平台与主体口径不同 → 记 NOT_TRIED + 平台原因，不得判不适用。
                target = {
                    "status": "NOT_TRIED",
                    "status_reason": (f"上市日 {listing} 晚于报告期结束 {period_end}，但北交所公司上市前在股转系统挂牌，"
                                      "挂牌期间定期报告存在（披露平台与主体口径不同），不得判不适用"),
                    "next_action": "SEARCH_NEEQ_ARCHIVE",
                    "reason_code": "APPLICABLE_WITH_DIFFERENT_PLATFORM_NEEQ",
                    "listing_date_evidence": {"listing_date": listing, "period_end": period_end,
                                              "rule": "P00: 北交所公司上市前曾在股转系统挂牌 → APPLICABLE_WITH_DIFFERENT_PLATFORM"},
                }
                action = "→NOT_TRIED(NEEQ_PLATFORM)"
            elif listing > period_end:
                target = {
                    "status": "NOT_APPLICABLE_PRE_LISTING",
                    "status_reason": f"上市日 {listing} 晚于报告期结束日 {period_end}，公司当时未上市",
                    "next_action": "NONE",
                    "reason_code": "LISTING_DATE_AFTER_PERIOD_END",
                    "listing_date_evidence": {"listing_date": listing, "period_end": period_end,
                                              "rule": "P00 not_applicable_decision_table: listing_date > period_end"},
                    "last_error": None,
                }
                action = "→NOT_APPLICABLE_PRE_LISTING"
            else:
                target = {
                    "status": "NOT_TRIED",
                    "status_reason": f"已上市（{listing} ≤ 报告期结束 {period_end}）但目录无该期全文，待人工复核检索式",
                    "next_action": "MANUAL_REVIEW_INDEX",
                    "reason_code": "APPLICABLE_BUT_EMPTY_INDEX",
                    "listing_date_evidence": {"listing_date": listing, "period_end": period_end,
                                              "rule": "P00: listing_date <= period_end → APPLICABLE"},
                }
                action = "→NOT_TRIED(APPLICABLE_BUT_EMPTY)"
            if status == target["status"] and rec.get("reason_code") == target["reason_code"]:
                continue  # 幂等：状态与原因都没变
            target["updated_at"] = utc_now()
            rec.update(target)
            changes.append({"security_id": security_id, "stock_code": path.stem, "slot_id": slot_id,
                            "action": action, "listing_date": listing, "period_end": period_end,
                            "before": before})
            dirty = True
        if dirty and not dry_run:
            tmp = path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
            tmp.replace(path)
    summary = {
        "run_at": utc_now(), "dry_run": dry_run,
        "listing_dates_available": len(dates),
        "changed_slots": len(changes),
        "to_not_applicable": sum(1 for c in changes if c["action"].startswith("NOT_TRIED→NOT_APPLICABLE")),
        "to_applicable_but_empty": sum(1 for c in changes if "APPLICABLE_BUT_EMPTY" in c["action"]),
        "changes": changes,
    }
    if not dry_run:
        write_json(OUT / "reclassify.json", summary)
    return summary


# ---------------------------------------------------------------- 报告
def ledger_evidence() -> list[dict]:
    """直接扫台账，列出所有带上市日期判定证据的槽位（不依赖运行历史）。"""
    rows = []
    for path in sorted(LEDGER.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for slot_id, rec in sorted((data.get("slots") or {}).items()):
            ev = rec.get("listing_date_evidence")
            if not ev:
                continue
            rows.append({
                "security_id": data.get("security_id"), "stock_code": path.stem,
                "slot_id": slot_id, "status": rec.get("status"),
                "reason_code": rec.get("reason_code"),
                "listing_date": ev.get("listing_date"), "period_end": ev.get("period_end"),
            })
    return rows


def report() -> Path:
    build_sum = json.loads((OUT / "build_summary.json").read_text(encoding="utf-8"))
    fetch_man = json.loads((OUT / "fetch_manifest.json").read_text(encoding="utf-8"))
    rows = ledger_evidence()
    by_code: dict[str, int] = {}
    for row in rows:
        by_code[row["reason_code"]] = by_code.get(row["reason_code"], 0) + 1
    lines = [
        "# 上市日期回填报告（listing_date）",
        "",
        f"- 生成时间：{utc_now()}",
        f"- 侧表：`{build_sum['side_table']}`（sha256 `{build_sum['side_table_sha256']}`）",
        f"- 覆盖：**{build_sum['coverage']}**，日期范围 {build_sum['date_min']} — {build_sum['date_max']}",
        f"- 未匹配：{build_sum['missing']}；简称与交易所不同：{build_sum['name_diff']}（代码一致，属除权标记 XD 或更名）",
        "",
        "## 一、数据来源（全部为交易所官方名单）",
        "",
        "| 市场 | 来源 | 原始行数 | 六位代码行数 | 原始快照 sha256 |",
        "|---|---|---:|---:|---|",
    ]
    for src in fetch_man["sources"]:
        lines.append(f"| {src['exchange']} | {src['label']}（`{src['function']}`） | {src['raw_rows']} | "
                     f"{src['normalized_rows']} | `{src['raw_sha256'][:16]}…` |")
    lines += [
        "",
        "原始快照与归一化文件在 `runs/listing_dates/raw/`，`fetch_manifest.json` 记录每个文件的哈希。",
        "注：上交所科创板是独立名单（`symbol=科创板`），默认参数只返回主板；首轮漏掉 157 家 688 代码即因此，已修正。",
        "",
        "## 二、按 P00 规则重判空目录槽位",
        "",
        "P00 `not_applicable_decision_table` 的三条硬规则：",
        "- `listing_date > period_end` → `NOT_APPLICABLE_PRE_LISTING`",
        "- `listing_date <= period_end` → `APPLICABLE`（应取得该期定期报告）",
        "- 北交所公司上市前曾在股转系统挂牌 → `APPLICABLE_WITH_DIFFERENT_PLATFORM`（不得判不适用）",
        "",
        f"台账中带上市日期判定证据的槽位共 **{len(rows)}** 个，按 reason_code 分布：",
        "",
        "| reason_code | 槽数 | 含义 |",
        "|---|---:|---|",
    ]
    meaning = {
        "LISTING_DATE_AFTER_PERIOD_END": "上市日晚于报告期结束 → 不适用（存在性已排除）",
        "APPLICABLE_WITH_DIFFERENT_PLATFORM_NEEQ": "北交所上市前在股转挂牌 → 平台不同，需另找股转归档",
        "APPLICABLE_BUT_EMPTY_INDEX": "已上市却目录空 → 待人工复核检索式",
    }
    for code, n in sorted(by_code.items()):
        lines.append(f"| `{code}` | {n} | {meaning.get(code, '')} |")
    lines += [
        "",
        "### 逐槽明细",
        "",
        "| 证券 | 简称 | 槽位 | 上市日 | 报告期结束 | 现状态 |",
        "|---|---|---|---|---|---|",
    ]
    names = {r["security_id"]: r["stock_name"] for r in read_csv(SIDE_TABLE)}
    for row in rows:
        lines.append(f"| {row['stock_code']} | {names.get(row['security_id'], '')} | {row['slot_id']} | "
                     f"{row['listing_date']} | {row['period_end']} | {row['status']} |")
    lines += [
        "",
        "## 三、口径说明与限制",
        "",
        "1. **没有**把「已上市却目录空」直接写成 `NOT_DISCLOSED_BY_ISSUER`：检索式漏项的可能无法排除，按「不能凭一次失败断言未披露」交人工复核。本次该类为 0。",
        "2. 北交所 5 个槽位（920011 晨光电机）**没有**判不适用：该公司上市前在股转系统挂牌，挂牌期间定期报告存在，只是披露平台不同。台账记 `NOT_TRIED` + `APPLICABLE_WITH_DIFFERENT_PLATFORM_NEEQ`，`next_action=SEARCH_NEEQ_ARCHIVE`。",
        "3. 交易所名单只覆盖当前在市公司；退市/长期停牌不在名单内会记 `NOT_FOUND_IN_EXCHANGE_LIST`（本次 0 家）。",
        "4. 上市日期按交易所口径（首次上市日），不区分借壳/重新上市；如需区分须另建实体映射。",
        "5. 未改 `data/company_master.csv`（原始输入）。采集与批次执行改为优先读 `data/company_listing_dates.csv` 侧表。",
        "6. P07 的 `calibration_coverage.csv` 是当时快照（5 槽记 NOT_TRIED），台账已按新证据更新；以 `runs/collection/collection_index.csv` 为准。",
        "",
    ]
    path = OUT / "backfill_report.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="上市日期回填")
    parser.add_argument("--fetch", action="store_true")
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--reclassify", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--report", action="store_true")
    args = parser.parse_args(argv)
    if args.fetch:
        print(json.dumps(fetch(), ensure_ascii=False, indent=2))
    if args.build:
        print(json.dumps(build(), ensure_ascii=False, indent=2))
    if args.reclassify:
        s = reclassify(dry_run=args.dry_run)
        print(json.dumps({k: v for k, v in s.items() if k != "changes"}, ensure_ascii=False, indent=2))
    if args.report:
        print(report())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
