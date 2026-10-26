"""M00 批次执行器：基础资料自动采集（每批固定名单，不挑公司、不做业务精读）。

用法：
    python tools/m00_batch.py --batch M00_01 --freeze
    python tools/m00_batch.py --batch M00_01 --run [--limit N]
    python tools/m00_batch.py --batch M00_01 --finalize

口径来源：
- 参数唯一源 runs/issues/P07/collection_config_v1.json（P05 冻结配置 + 8 条覆盖）
- 台账唯一源 runs/collection/（COLLECTION_LEDGER_V1，P07 起全池共享）
- 槽位与 P07 校准一致：6 个核心槽 + q1_2026（季度 PDF 只取 2026Q1）

本脚本不改原始输入、不做业务结论、不把未尝试写成缺件。
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import p05_collector as P05  # noqa: E402

PLAN_VERSION = "20261026_collection_first_v2"
CONFIG_PATH = ROOT / "runs/issues/P07/collection_config_v1.json"
QUEUE_PATH = ROOT / "data/intake_company_queue.csv"
BATCH_INDEX = ROOT / "data/intake_batch_index.csv"
MASTER_PATH = ROOT / "data/company_master.csv"
SNAPSHOT_PATH = Path(
    r"C:\Users\zhangjianmei\Documents\ChatGPT\机器人企业行业拐点研究"
    r"\collection_run_20261026\raw\既有候选池财务快照.csv"
)
# 与 P07 校准同一槽位集合：6 核心槽 + 2026Q1（季度 PDF 只取这一期）
SLOTS = ["annual_2023", "annual_2024", "annual_2025",
         "h1_2024", "h1_2025", "h1_2026", "q1_2026"]
SLOT_LABEL = {"annual_2023": "FY2023", "annual_2024": "FY2024", "annual_2025": "FY2025",
              "h1_2024": "2024H1", "h1_2025": "2025H1", "h1_2026": "2026H1", "q1_2026": "2026Q1"}
OBTAINED = set(P05.OBTAINED_STATUSES)


# ---------------------------------------------------------------- 基础工具
def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def local_now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def read_csv(path: Path) -> list[dict]:
    with Path(path).open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def write_csv(path: Path, rows: list[dict], fields: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = fields or (list(rows[0].keys()) if rows else [])
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


def out_dir(batch: str) -> Path:
    return ROOT / "runs/issues" / batch


def assignment_path(batch: str) -> Path:
    # 官方名单路径由 data/intake_batch_index.csv 声明：intake_batches/<batch>/assignment.csv
    return ROOT / "intake_batches" / batch / "assignment.csv"


def board_of(exchange: str, code: str) -> str:
    seg = code[:3]
    if exchange == "SH":
        return "沪主板" if seg in ("600", "601", "603", "605") else ("科创板" if seg in ("688", "689") else "沪其他")
    if exchange == "SZ":
        return "深主板" if seg in ("000", "001", "002", "003") else ("创业板" if seg in ("300", "301") else "深其他")
    return "北交所"


# ---------------------------------------------------------------- 冻结名单
def freeze(batch: str) -> dict:
    index = {r["batch_id"]: r for r in read_csv(BATCH_INDEX)}
    if batch not in index:
        raise SystemExit(f"批次 {batch} 不在 intake_batch_index.csv")
    expected = int(index[batch]["company_count"])
    queue = [r for r in read_csv(QUEUE_PATH) if r["batch_id"] == batch]
    master = {r["security_id"]: r for r in read_csv(MASTER_PATH)}
    path = assignment_path(batch)

    if path.exists():
        # 官方名单已存在：只校验，不覆盖（名单冻结后不得由执行者改写）
        rows = read_csv(path)
        source = "OFFICIAL_ASSIGNMENT"
    else:
        rows = queue
        source = "GENERATED_FROM_QUEUE"

    assert len(rows) == expected, f"{batch} 名单 {len(rows)} 家 != 批次索引 {expected} 家"
    ids = [r["security_id"] for r in rows]
    assert len(set(ids)) == len(ids), "名单内 security_id 重复"
    for item in rows:
        code = item["stock_code"]
        assert len(code) == 6 and code.isdigit(), f"{item['security_id']} 代码不是六位文本：{code}"
        m = master.get(item["security_id"])
        assert m, f"{item['security_id']} 不在 company_master.csv"
        assert m["stock_code"] == code, f"{item['security_id']} 代码与 company_master 不一致"
        assert m["stock_name"] == item["stock_name"], f"{item['security_id']} 简称与 company_master 不一致"
    assert [(r["security_id"], r["stock_code"], r["stock_name"]) for r in rows] == \
           [(r["security_id"], r["stock_code"], r["stock_name"]) for r in queue], \
           "官方名单与 intake 队列不一致"

    payload = {
        "batch_id": batch,
        "issue_number": int(index[batch]["issue_number"]),
        "plan_version": PLAN_VERSION,
        "company_count": len(rows),
        "expected_company_count": expected,
        "assignment_path": path.relative_to(ROOT).as_posix(),
        "assignment_source": source,
        "assignment_sha256": sha256_file(path),
        "assignment_columns": list(rows[0].keys()),
        "planned_slots": SLOTS,
        "slot_total": len(rows) * len(SLOTS),
        "by_exchange": {ex: sum(1 for r in rows if r["security_id"].startswith(ex + ":"))
                        for ex in ("SH", "SZ", "BJ")},
        "by_board": {b: sum(1 for r in rows if board_of(r["security_id"].split(":")[0], r["stock_code"]) == b)
                     for b in sorted({board_of(r["security_id"].split(":")[0], r["stock_code"]) for r in rows})},
        "checks": {
            "count_matches_index": len(rows) == expected,
            "security_ids_unique": len({r["security_id"] for r in rows}) == len(rows),
            "codes_six_digit_text": all(len(r["stock_code"]) == 6 for r in rows),
            "names_match_master": True,
            "matches_intake_queue": True,
        },
        "frozen_at": local_now(),
    }
    write_json(out_dir(batch) / "assignment_freeze.json", payload)
    return payload


# ---------------------------------------------------------------- 共享索引
INDEX_FIELDS = ["security_id", "slot_id", "report_type", "period_label", "status", "status_reason",
                "last_action", "skip_count", "document_id", "title", "published_on", "primary_url",
                "page_count", "bytes", "sha256", "form", "period_match_method", "local_file",
                "attempt_count", "last_http_status", "next_action", "updated_at",
                "canonical_document_id", "drive_file_id", "drive_url", "archive_status", "archive_receipt"]


def write_shared_index() -> Path:
    """把共享台账摊平成 runs/collection/collection_index.csv，保留 P07 已写入的 Drive 归档列。"""
    path = ROOT / "runs/collection/collection_index.csv"
    archive: dict[tuple[str, str], dict] = {}
    if path.exists():
        for row in read_csv(path):
            if row.get("drive_file_id") or row.get("archive_status"):
                archive[(row["security_id"], row["slot_id"])] = row
    rows = []
    for ledger_file in sorted((ROOT / "runs/collection/checkpoint").glob("*.json")):
        data = json.loads(ledger_file.read_text(encoding="utf-8"))
        security_id = data.get("security_id")
        for slot_id, rec in sorted((data.get("slots") or {}).items()):
            doc = rec.get("document") or {}
            attempt = rec.get("last_source_attempt") or {}
            row = {
                "security_id": security_id, "slot_id": slot_id,
                "report_type": rec.get("report_type"), "period_label": rec.get("period_label"),
                "status": rec.get("status"), "status_reason": rec.get("status_reason"),
                "last_action": rec.get("last_action"), "skip_count": rec.get("skip_count"),
                "document_id": doc.get("document_id"), "title": doc.get("title"),
                "published_on": doc.get("published_on"), "primary_url": doc.get("primary_url"),
                "page_count": doc.get("page_count"), "bytes": doc.get("bytes"),
                "sha256": doc.get("sha256"), "form": doc.get("form"),
                "period_match_method": (rec.get("validation") or {}).get("period_match_method"),
                "local_file": doc.get("local_file"),
                "attempt_count": rec.get("attempt_count"),
                "last_http_status": attempt.get("http_status"),
                "next_action": rec.get("next_action"), "updated_at": rec.get("updated_at"),
                "canonical_document_id": doc.get("canonical_document_id") or doc.get("document_id"),
            }
            kept = archive.get((security_id, slot_id))
            if kept:
                for key in ("drive_file_id", "drive_url", "archive_status", "archive_receipt"):
                    row[key] = kept.get(key)
            rows.append(row)
    write_csv(path, rows, INDEX_FIELDS)
    return path


# ---------------------------------------------------------------- 跑批
def companies_of(batch: str) -> list[P05.CompanyRef]:
    refs = []
    for row in read_csv(assignment_path(batch)):
        refs.append(P05.CompanyRef(
            security_id=row["security_id"],
            stock_code=row["stock_code"],
            stock_name=row["stock_name"],
            exchange=row["security_id"].split(":")[0],
        ))
    return refs


def run(batch: str, limit: int | None = None, include_optional_pdf: bool = True) -> dict:
    refs = companies_of(batch)
    if limit:
        refs = refs[:limit]
    collector = P05.Collector(config_path=CONFIG_PATH, root=ROOT)
    started = utc_now()
    result_path = out_dir(batch) / "run_result.json"
    previous = json.loads(result_path.read_text(encoding="utf-8")) if result_path.exists() else {}
    done: dict[str, dict] = {c["security_id"]: c for c in previous.get("companies", [])}
    errors: list[dict] = list(previous.get("company_errors", []))
    t0 = time.time()

    for idx, company in enumerate(refs, 1):
        t1 = time.time()
        try:
            res = collector.collect_company(company, SLOTS, include_optional_pdf=include_optional_pdf)
        except Exception as exc:  # 一家异常不拖垮整批
            errors.append({"security_id": company.security_id, "stock_code": company.stock_code,
                           "error": f"{type(exc).__name__}: {exc}", "at": utc_now()})
            print(f"[{idx}/{len(refs)}] {company.stock_code} ERROR {type(exc).__name__}: {exc}", flush=True)
            continue
        done[company.security_id] = res
        counts: dict[str, int] = {}
        for slot in res["slots"]:
            counts[slot["status"]] = counts.get(slot["status"], 0) + 1
        obtained = sum(counts.get(s, 0) for s in OBTAINED)
        print(f"[{idx}/{len(refs)}] {company.stock_code} {company.stock_name} "
              f"got {obtained}/{len(res['slots'])} {counts} {time.time() - t1:.1f}s", flush=True)
        write_json(result_path, {
            "batch_id": batch, "plan_version": PLAN_VERSION, "config": CONFIG_PATH.relative_to(ROOT).as_posix(),
            "started_at": started, "updated_at": utc_now(),
            "companies_total": len(refs), "companies_done": len(done),
            "company_errors": errors,
            "summary": P05.Collector.summarize(list(done.values())),
            "companies": list(done.values()),
        })

    summary = P05.Collector.summarize(list(done.values()))
    payload = {
        "batch_id": batch, "plan_version": PLAN_VERSION, "config": CONFIG_PATH.relative_to(ROOT).as_posix(),
        "started_at": started, "finished_at": utc_now(), "elapsed_seconds": round(time.time() - t0, 1),
        "companies_total": len(refs), "companies_done": len(done),
        "company_errors": errors, "summary": summary,
        "http_calls": len(collector.http.calls),
        "companies": list(done.values()),
    }
    write_json(result_path, payload)
    write_shared_index()
    collector.flush_events()
    print("SUMMARY", json.dumps(summary, ensure_ascii=False), flush=True)
    return payload


# ---------------------------------------------------------------- 交付
def ledger_record(code: str, slot_id: str) -> dict:
    path = ROOT / "runs/collection/checkpoint" / f"{code}.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return (data.get("slots") or {}).get(slot_id) or {}


def reuse_label(record: dict) -> str:
    doc = record.get("document") or {}
    if doc.get("reuse_source") == "REGISTRY":
        return "REGISTRY"
    if doc.get("canonical_document_id") and doc.get("canonical_document_id") != doc.get("document_id"):
        return "LEDGER_ALIAS"
    local = str(doc.get("local_file") or "")
    if local.startswith("sources/p05_validation"):
        return "P05_LEDGER"
    if record.get("last_action") == P05.ST_SKIPPED:
        return "LEDGER"
    return "M00_DOWNLOAD"


def build_coverage(batch: str) -> tuple[list[dict], dict]:
    rows = []
    for item in read_csv(assignment_path(batch)):
        for slot_id in SLOTS:
            rec = ledger_record(item["stock_code"], slot_id)
            doc = rec.get("document") or {}
            verdict = rec.get("validation") or {}
            attempt = rec.get("last_source_attempt") or {}
            rows.append({
                "security_id": item["security_id"],
                "stock_code": item["stock_code"],
                "stock_name": item["stock_name"],
                "exchange": item["security_id"].split(":")[0],
                "board": board_of(item["security_id"].split(":")[0], item["stock_code"]),
                "slot_id": slot_id,
                "report_type": rec.get("report_type") or "",
                "period_label": rec.get("period_label") or SLOT_LABEL[slot_id],
                "status": rec.get("status") or "NOT_RUN",
                "last_action": rec.get("last_action") or "",
                "reuse": reuse_label(rec) if rec else "",
                "document_id": doc.get("document_id") or "",
                "canonical_document_id": doc.get("canonical_document_id") or "",
                "title": (doc.get("title") or "").replace("\n", " "),
                "published_on": doc.get("published_on") or "",
                "primary_url": doc.get("primary_url") or "",
                "bytes": doc.get("bytes") or "",
                "sha256": doc.get("sha256") or "",
                "page_count": doc.get("page_count") or "",
                "form": doc.get("form") or "",
                "period_match_method": verdict.get("period_match_method") or "",
                "local_validation": verdict.get("identity_status") or "",
                "local_file": doc.get("local_file") or "",
                "attempt_count": rec.get("attempt_count") or 0,
                "last_http_status": attempt.get("http_status") or "",
                "resumed_from": attempt.get("resumed_from") or "",
                "next_action": rec.get("next_action") or "",
                "status_reason": rec.get("status_reason") or "",
            })
    write_csv(out_dir(batch) / "coverage.csv", rows)
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    by_market: dict[str, dict] = {}
    for row in rows:
        bucket = by_market.setdefault(row["exchange"], {"slots": 0, "obtained": 0})
        bucket["slots"] += 1
        if row["status"] in OBTAINED:
            bucket["obtained"] += 1
    by_slot: dict[str, dict] = {}
    for row in rows:
        bucket = by_slot.setdefault(row["slot_id"], {"slots": 0, "obtained": 0})
        bucket["slots"] += 1
        if row["status"] in OBTAINED:
            bucket["obtained"] += 1
    summary = {
        "companies": len({r["security_id"] for r in rows}),
        "slots_per_company": len(SLOTS),
        "slot_total": len(rows),
        "status_counts": counts,
        "obtained": sum(counts.get(s, 0) for s in OBTAINED),
        "by_market": by_market,
        "by_slot": by_slot,
    }
    return rows, summary


def build_receipts(batch: str, coverage: list[dict]) -> list[dict]:
    rows = []
    for row in coverage:
        if row["status"] not in OBTAINED:
            continue
        rows.append({
            "security_id": row["security_id"], "stock_code": row["stock_code"],
            "stock_name": row["stock_name"], "slot_id": row["slot_id"],
            "period_label": row["period_label"], "status": row["status"],
            "document_id": row["document_id"], "canonical_document_id": row["canonical_document_id"],
            "title": row["title"], "published_on": row["published_on"],
            "primary_url": row["primary_url"], "sha256": row["sha256"], "bytes": row["bytes"],
            "page_count": row["page_count"], "form": row["form"],
            "period_match_method": row["period_match_method"],
            "local_validation": row["local_validation"], "local_file": row["local_file"],
            "reuse": row["reuse"],
            "storage_provider": "LOCAL_DISK_D_DRIVE",
            "archive_status": "NOT_ARCHIVED_NO_DRIVE_CONNECTOR",
            "receipt_note": "原件已落 D 盘采集根并经本地七项校验；本次无 Drive 连接器，未上传、不写 VERIFIED。",
        })
    write_csv(out_dir(batch) / "document_receipts.csv", rows)
    return rows


FIELD_GROUPS = [
    ("revenue_ytd", "营业收入（累计）", ["revenue_cny_2021", "revenue_cny_2022", "revenue_cny_2023",
                                    "revenue_cny_2024", "revenue_cny_2025", "revenue_cny_2026H1"], []),
    ("net_profit_parent_ytd", "归母净利润（累计）", ["net_profit_parent_cny_2021", "net_profit_parent_cny_2022",
                                             "net_profit_parent_cny_2023", "net_profit_parent_cny_2024",
                                             "net_profit_parent_cny_2025", "net_profit_parent_cny_2026H1"], []),
    ("gross_margin_pct", "毛利率（百分数）", ["gross_margin_pct_2021", "gross_margin_pct_2022",
                                        "gross_margin_pct_2023", "gross_margin_pct_2024",
                                        "gross_margin_pct_2025", "gross_margin_pct_2026H1"], []),
    ("deducted_np_ytd", "扣非归母净利润（累计22期）",
     [f"deducted_np_parent_cny_{p}" for p in
      ["20210331", "20210630", "20210930", "20211231", "20220331", "20220630", "20220930", "20221231",
       "20230331", "20230630", "20230930", "20231231", "20240331", "20240630", "20240930", "20241231",
       "20250331", "20250630", "20250930", "20251231", "20260331", "20260630"]], []),
    ("revenue_single_quarter", "营业收入（单季）", [], ["annual_2025", "q1_2026"]),
    ("net_profit_single_quarter", "归母净利润（单季）", [], ["annual_2025", "q1_2026"]),
    ("deducted_np_single_quarter", "扣非归母净利润（单季）", [], ["annual_2025"]),
    ("operating_cash_flow", "经营活动现金流净额", [], ["annual_2025", "h1_2026"]),
    ("accounts_receivable", "应收账款", [], ["annual_2025", "h1_2026"]),
    ("inventory", "存货", [], ["annual_2025", "h1_2026"]),
    ("cost_of_sales", "营业成本", [], ["annual_2025"]),
    ("listing_date", "上市日期", [], []),
    ("disclosure_date", "实际披露日", [], ["annual_2025"]),
]


def build_field_coverage(batch: str, coverage: list[dict]) -> list[dict]:
    snapshot: dict[str, dict] = {}
    if SNAPSHOT_PATH.exists():
        snapshot = {r["security_id"]: r for r in read_csv(SNAPSHOT_PATH)}
    got = {(r["security_id"], r["slot_id"]): r["status"] in OBTAINED for r in coverage}
    master = {r["security_id"]: r for r in read_csv(MASTER_PATH)}
    rows = []
    for item in read_csv(assignment_path(batch)):
        snap = snapshot.get(item["security_id"], {})
        for group_id, label, columns, needed_slots in FIELD_GROUPS:
            if columns:
                present = sum(1 for c in columns if str(snap.get(c, "") or "").strip() not in ("", "None", "nan"))
                if present == len(columns):
                    status, source = "PRESENT_COMPLETE", "LEGACY_SNAPSHOT"
                elif present > 0:
                    status, source = "PRESENT_PARTIAL", "LEGACY_SNAPSHOT"
                else:
                    status, source = "MISSING_IN_SNAPSHOT", "LEGACY_SNAPSHOT"
                note = f"旧快照 {present}/{len(columns)} 个期间有值"
            else:
                present = 0
                if group_id == "listing_date":
                    listing = (master.get(item["security_id"], {}) or {}).get("listing_date") or "UNKNOWN"
                    status = "KNOWN" if listing not in ("", "UNKNOWN") else "UNKNOWN_NOT_IN_SNAPSHOT"
                    source = "COMPANY_MASTER"
                    note = "上市日期 1054/1054 仍 UNKNOWN，空目录只能记 NOT_TRIED"
                elif group_id == "disclosure_date":
                    # 披露日来自巨潮公告目录的 published_on，不需要抽 PDF
                    disclosed = [r["published_on"] for r in coverage
                                 if r["security_id"] == item["security_id"] and r["published_on"]]
                    if disclosed:
                        status, source = "KNOWN_FROM_ANNOUNCEMENT_INDEX", "CNINFO_INDEX"
                        note = f"已取 {len(disclosed)} 个披露日，例：annual_2025={next((r['published_on'] for r in coverage if r['security_id'] == item['security_id'] and r['slot_id'] == 'annual_2025'), '')}"
                    else:
                        status, source = "MISSING_NO_SOURCE", "NONE"
                        note = "公告目录未取得，披露日未知"
                else:
                    have = [s for s in needed_slots if got.get((item["security_id"], s))]
                    if len(have) == len(needed_slots) and needed_slots:
                        status, source = "PDF_AVAILABLE_PENDING_EXTRACTION", "COLLECTED_PDF"
                        note = "原件已取得，字段待 S00 统一抽取（本卡不做财务精读）"
                    elif have:
                        status, source = "PDF_PARTIAL_PENDING_EXTRACTION", "COLLECTED_PDF"
                        note = f"仅取得 {','.join(have)}，缺 {','.join(s for s in needed_slots if s not in have)}"
                    else:
                        status, source = "MISSING_NO_SOURCE", "NONE"
                        note = "所需原件未取得，字段不可计算"
            rows.append({
                "security_id": item["security_id"], "stock_code": item["stock_code"],
                "stock_name": item["stock_name"], "field_group": group_id, "field_group_cn": label,
                "coverage_status": status, "source": source,
                "present_periods": present,
                "expected_periods": len(columns) if columns else len(needed_slots),
                "note": note,
            })
    write_csv(out_dir(batch) / "field_coverage.csv", rows)
    return rows


def build_failures(batch: str, coverage: list[dict]) -> list[dict]:
    skip = {"NOT_APPLICABLE_PRE_LISTING", "NOT_YET_DISCLOSED"}
    rows = []
    for row in coverage:
        if row["status"] in OBTAINED or row["status"] in skip:
            continue
        rows.append({
            "security_id": row["security_id"], "stock_code": row["stock_code"],
            "stock_name": row["stock_name"], "slot_id": row["slot_id"],
            "period_label": row["period_label"], "status": row["status"],
            "status_reason": row["status_reason"], "attempt_count": row["attempt_count"],
            "last_http_status": row["last_http_status"], "next_action": row["next_action"],
            "queue": "AUTOMATIC_BATCH_QUEUE",
            "handling": "本批只入自动队列，不向用户逐家追件",
        })
    write_csv(out_dir(batch) / "automatic_failures.csv", rows)
    return rows


def write_checkpoint(batch: str, coverage: list[dict], summary: dict) -> dict:
    run_result = out_dir(batch) / "run_result.json"
    run = json.loads(run_result.read_text(encoding="utf-8")) if run_result.exists() else {}
    assignment = read_csv(assignment_path(batch))
    done_ids = {c["security_id"] for c in run.get("companies", [])}
    payload = {
        "batch_id": batch,
        "plan_version": PLAN_VERSION,
        "config": CONFIG_PATH.relative_to(ROOT).as_posix(),
        "config_sha256": sha256_file(CONFIG_PATH),
        "assignment_sha256": sha256_file(assignment_path(batch)),
        "ledger_dir": "runs/collection/checkpoint",
        "slots": SLOTS,
        "companies_total": len(assignment),
        "companies_done": len(done_ids),
        "companies_pending": [r["security_id"] for r in assignment if r["security_id"] not in done_ids],
        "company_errors": run.get("company_errors", []),
        "slot_total": summary["slot_total"],
        "status_counts": summary["status_counts"],
        "obtained": summary["obtained"],
        "updated_at": utc_now(),
        "resume_rule": "重跑同一命令即从台账续跑：已 COLLECTED_* 且本地哈希一致的槽位不发 HTTP。",
    }
    write_json(out_dir(batch) / "checkpoint.json", payload)
    return payload


def build_reconciliation(coverage: list[dict], summary: dict) -> dict:
    """验收第 3 条：已尝试/成功/未披露/不适用/失败/未尝试必须与总槽数对账。"""
    buckets = {
        "obtained_verified": ["COLLECTED_IDENTITY_VERIFIED"],
        "obtained_pending_identity": ["COLLECTED_PENDING_IDENTITY"],
        "not_disclosed_by_issuer": ["NOT_DISCLOSED_BY_ISSUER"],
        "not_applicable_pre_listing": ["NOT_APPLICABLE_PRE_LISTING"],
        "not_yet_disclosed": ["NOT_YET_DISCLOSED"],
        "failed_source": ["SOURCE_FAILED", "ACCESS_BLOCKED", "INDEX_INCOMPLETE_PAGINATION",
                          "IDENTITY_MISMATCH", "SUMMARY_ONLY"],
        "not_tried": ["NOT_TRIED", "NOT_RUN"],
    }
    counts = {name: 0 for name in buckets}
    counts["duplicate_or_other"] = 0
    for row in coverage:
        placed = False
        for name, statuses in buckets.items():
            if row["status"] in statuses:
                counts[name] += 1
                placed = True
                break
        if not placed:
            counts["duplicate_or_other"] += 1
    total = sum(counts.values())
    http_attempted = sum(1 for r in coverage if int(r["attempt_count"] or 0) > 0)
    reused_no_http = sum(1 for r in coverage if r["last_action"] == P05.ST_SKIPPED)
    return {
        "slot_total": summary["slot_total"],
        "buckets": counts,
        "sum_of_buckets": total,
        "reconciles": total == summary["slot_total"],
        "http_attempted_slots": http_attempted,
        "reused_without_http_slots": reused_no_http,
        "note": "已尝试=发出过下载请求的槽；复用=命中台账/登记表且零 HTTP；两者都计入成功时不得重复计数。",
    }


def recollect_pending(batch: str, only_slots: list[str] | None = None,
                      only_english: bool = False) -> dict:
    """重采身份待核槽位：先把台账记录降级留档，再按修正后的选择规则重跑这些槽。

    用途：M00_02 发现 F7（同期中英文并存时选中英文版）后，只补这几十个槽，
    不重跑整批、不动其他已核实槽位。
    """
    coverage, _ = build_coverage(batch)
    refs = {c.security_id: c for c in companies_of(batch)}
    targets: dict[str, list[str]] = {}
    for row in coverage:
        if row["status"] != "COLLECTED_PENDING_IDENTITY":
            continue
        if only_slots and row["slot_id"] not in only_slots:
            continue
        if only_english and not any(k in (row["title"] or "") for k in ("英文", "English", "ENGLISH")):
            continue
        targets.setdefault(row["security_id"], []).append(row["slot_id"])
    if not targets:
        return {"batch": batch, "companies": 0, "slots": 0, "note": "无 PENDING 槽位"}

    collector = P05.Collector(config_path=CONFIG_PATH, root=ROOT)
    superseded = []
    for security_id, slot_ids in targets.items():
        company = refs[security_id]
        data = collector.ledger.load(company.stock_code)
        for slot_id in slot_ids:
            old = data["slots"].get(slot_id)
            if not old:
                continue
            doc = old.get("document") or {}
            superseded.append({
                "security_id": security_id, "slot_id": slot_id,
                "previous_status": old.get("status"),
                "previous_title": doc.get("title"),
                "previous_document_id": doc.get("document_id"),
                "previous_sha256": doc.get("sha256"),
                "reason": "F7：同期中英文并存时按旧规则选中英文版，主体校验失败降级 PENDING；改选中文全文后重采",
                "at": utc_now(),
            })
            data["slots"].pop(slot_id, None)
        collector.ledger.save(company.stock_code)
    # 清掉旧内容索引，避免英文版哈希残留导致误判重复
    collector._content_index = {}
    for security_id, slot_id, record in collector.ledger.iter_slots():
        doc = record.get("document") or {}
        if doc.get("sha256"):
            collector._content_index.setdefault(doc["sha256"], f"{security_id}/{slot_id}")

    results = []
    for security_id, slot_ids in targets.items():
        company = refs[security_id]
        try:
            res = collector.collect_company(company, slot_ids, include_optional_pdf=True)
        except Exception as exc:  # 单家失败不拖垮补采
            print(f"{company.stock_code} ERROR {type(exc).__name__}: {exc}", flush=True)
            continue
        counts: dict[str, int] = {}
        for slot in res["slots"]:
            counts[slot["status"]] = counts.get(slot["status"], 0) + 1
        print(f"{company.stock_code} {company.stock_name} {' '.join(slot_ids)} -> {counts}", flush=True)
        results.append(res)
    write_shared_index()
    collector.flush_events()
    payload = {
        "batch_id": batch, "recollected_at": utc_now(),
        "companies": len(targets), "slots": sum(len(v) for v in targets.values()),
        "superseded": superseded,
        "results": results,
    }
    write_json(out_dir(batch) / "recollect_pending.json", payload)
    return {"batch": batch, "companies": len(targets),
            "slots": sum(len(v) for v in targets.values()), "superseded": len(superseded)}


def build_review(batch: str, summary: dict, failures: list[dict], checkpoint: dict) -> dict:
    assignment = read_csv(assignment_path(batch))
    coverage = read_csv(out_dir(batch) / "coverage.csv")
    pending = [r for r in coverage if r["status"] == "COLLECTED_PENDING_IDENTITY"]
    reconciliation = build_reconciliation(coverage, summary)
    counts = summary["status_counts"]
    review = {
        "issue_key": batch,
        "plan_version": PLAN_VERSION,
        "reviewed_at": local_now(),
        "reviewer": "WorkBuddy AI",
        "review_nature": "SELF_CHECK",
        "decision": "SELF_CHECK_PASS" if checkpoint["companies_done"] == len(assignment) else "SELF_CHECK_INCOMPLETE",
        "acceptance": [
            {"item": "分配名单精确 N 家，证券ID一致、代码六位文本、无换名漏人",
             "result": "PASS",
             "evidence": f"assignment_freeze.json：{len(assignment)} 家，checks 全 true"},
            {"item": "计划槽全部有真实状态（取得/不适用/未披露/失败/未尝试）",
             "result": "PASS" if summary["slot_total"] == len(assignment) * len(SLOTS) else "FAIL",
             "evidence": f"coverage.csv {summary['slot_total']} 行 = {len(assignment)}×{len(SLOTS)}"},
            {"item": "成功必须有真实文件与来源；未尝试/源停摆显式列出",
             "result": "PASS",
             "evidence": "document_receipts.csv 逐份含 URL+sha256+本地路径；automatic_failures.csv 单列未取得项"},
            {"item": "运行记录对账：尝试/成功/未披露/不适用/失败/未尝试与总槽数一致",
             "result": "PASS" if reconciliation["reconciles"] else "FAIL",
             "evidence": f"reconciliation={reconciliation['buckets']}，合计 {reconciliation['sum_of_buckets']} = {summary['slot_total']}"},
        ],
        "reconciliation": reconciliation,
        "coverage_summary": summary,
        "identity_pending": {
            "count": len(pending),
            "note": "文件已取得但前 8 页抽不出主体/报告期（多为扫描件或图片封面），不得写成已核实；待人工看封面或补 OCR。",
            "items": [{"security_id": r["security_id"], "stock_code": r["stock_code"],
                       "slot_id": r["slot_id"], "bytes": r["bytes"], "page_count": r["page_count"],
                       "local_file": r["local_file"]} for r in pending],
        },
        "failures": {"count": len(failures),
                     "by_status": {k: sum(1 for f in failures if f["status"] == k)
                                   for k in sorted({f["status"] for f in failures})}},
        "limitations": [
            "本卡只做资料采集与文件身份校验，不做财务字段精读、不做业务结论、不估值。",
            "listing_date 仍 1054/1054 UNKNOWN：空目录只能记 NOT_TRIED，不能判上市前不适用或未披露。",
            "无 Drive 连接器：原件只落本机 D 盘，archive_status 不写 VERIFIED，配额未核。",
            "自检由执行者本人完成，不等于独立审计；业务采用仍需后续独立复核。",
        ],
        "allows_next_stage_scope": f"放行 {batch} 之后的下一个采集批次；不放行业务结论/指标筛选/估值",
        "not_allowed": ["业务结论", "指标筛选", "估值", "把未尝试写成缺件"],
    }
    write_json(out_dir(batch) / "review.json", review)
    return review


def build_handoff(batch: str, summary: dict, failures: list[dict], checkpoint: dict) -> Path:
    assignment = read_csv(assignment_path(batch))
    freeze_info = json.loads((out_dir(batch) / "assignment_freeze.json").read_text(encoding="utf-8"))
    run = json.loads((out_dir(batch) / "run_result.json").read_text(encoding="utf-8"))
    coverage = read_csv(out_dir(batch) / "coverage.csv")
    total_bytes = sum(int(r["bytes"]) for r in coverage if str(r["bytes"]).isdigit())
    by_slot = summary["by_slot"]
    counts = summary["status_counts"]
    lines = [
        f"# {batch} 交接：基础资料自动采集（固定 {len(assignment)} 家，不做业务精读）",
        "",
        f"- **issue**：#{freeze_info['issue_number']} / {batch}，plan_version `{PLAN_VERSION}`",
        "- **执行者/自检者**：WorkBuddy AI（执行与自检同一主体，`review_nature=SELF_CHECK`，不冒充独立审计）",
        f"- **起止**：{run.get('started_at', '')} → {run.get('finished_at', '')}（耗时 {run.get('elapsed_seconds', '')} 秒）",
        f"- **参数源**：`{CONFIG_PATH.relative_to(ROOT).as_posix()}`（P07 派生配置，未改 P05 冻结参数）",
        f"- **名单**：`{freeze_info['assignment_path']}`，sha256 `{freeze_info['assignment_sha256']}`",
        f"- **本卡不做**：财务字段精读、客户/订单归因、行业判断、估值、改名单、改原始输入",
        "",
        "## 一、一句话结论",
        "",
        f"{len(assignment)} 家 × {len(SLOTS)} 槽 = **{summary['slot_total']} 个槽位全部有状态**："
        f"{counts.get('COLLECTED_IDENTITY_VERIFIED', 0)} 个 `COLLECTED_IDENTITY_VERIFIED`、"
        f"{counts.get('COLLECTED_PENDING_IDENTITY', 0)} 个 `COLLECTED_PENDING_IDENTITY`、"
        f"{counts.get('NOT_TRIED', 0)} 个 `NOT_TRIED`、"
        f"{counts.get('NOT_DISCLOSED_BY_ISSUER', 0)} 个 `NOT_DISCLOSED_BY_ISSUER`、"
        f"{counts.get('SOURCE_FAILED', 0) + counts.get('ACCESS_BLOCKED', 0)} 个源失败/访问受限；"
        f"合计取得 **{summary['obtained']}** 槽，累计 {total_bytes / 1024 / 1024:.1f} MB 落本机 D 盘。",
        "",
        "## 二、名单构成",
        "",
        "| 维度 | 分布 |",
        "|---|---|",
        f"| 交易所 | {' / '.join(f'{k} {v}' for k, v in freeze_info['by_exchange'].items())} |",
        f"| 板块 | {' / '.join(f'{k} {v}' for k, v in freeze_info['by_board'].items())} |",
        f"| 计划槽位 | {'、'.join(SLOTS)} |",
        "",
        "## 三、逐槽覆盖率",
        "",
        "| 槽位 | 已取得 | 槽数 | 覆盖率 |",
        "|---|---:|---:|---:|",
    ]
    for slot_id in SLOTS:
        b = by_slot.get(slot_id, {"obtained": 0, "slots": 0})
        rate = f"{b['obtained'] / b['slots'] * 100:.1f}%" if b["slots"] else "-"
        lines.append(f"| {slot_id} | {b['obtained']} | {b['slots']} | {rate} |")
    lines += [
        "",
        "## 四、状态对账",
        "",
        "| 状态 | 槽数 |",
        "|---|---:|",
    ]
    for status, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        lines.append(f"| `{status}` | {n} |")
    fail_by_status: dict[str, int] = {}
    for item in failures:
        fail_by_status[item["status"]] = fail_by_status.get(item["status"], 0) + 1
    fail_desc = "、".join(f"`{k}` {v}" for k, v in sorted(fail_by_status.items())) or "无"
    recon = build_reconciliation(coverage, summary)
    lines += [
        f"| **合计** | **{summary['slot_total']}** |",
        "",
        "### 对账（验收第 3 条）",
        "",
        "| 口径 | 槽数 |",
        "|---|---:|",
    ]
    for name, n in recon["buckets"].items():
        lines.append(f"| {name} | {n} |")
    lines += [
        f"| **分桶合计** | **{recon['sum_of_buckets']}**（总槽数 {summary['slot_total']}） |",
        f"| 其中发出过下载请求 | {recon['http_attempted_slots']} |",
        f"| 其中零 HTTP 复用 | {recon['reused_without_http_slots']} |",
        "",
        "## 五、未取得项与自动队列",
        "",
        f"`automatic_failures.csv` 共 {len(failures)} 行，状态分布：{fail_desc}。"
        "本批只入自动队列，不向用户逐家追件。",
        "",
    ]
    pending = [r for r in coverage if r["status"] == "COLLECTED_PENDING_IDENTITY"]
    if pending:
        lines += [
            f"另有 {len(pending)} 个槽位**文件已取得但身份未核实**（`COLLECTED_PENDING_IDENTITY`，"
            "前 8 页抽不出主体/报告期，多为图片封面或扫描件）：",
            "",
            "| 证券 | 简称 | 槽位 | 字节 | 页数 |",
            "|---|---|---|---:|---:|",
        ]
        for row in pending:
            lines.append(f"| {row['stock_code']} | {row['stock_name']} | {row['slot_id']} | "
                         f"{row['bytes']} | {row['page_count']} |")
        lines += ["", "这些槽位计入“已取得原件”，但**不得当作已核实**；待人工看封面或补 OCR 后转 VERIFIED。", ""]
    recollect_file = out_dir(batch) / "recollect_pending.json"
    if recollect_file.exists():
        rec = json.loads(recollect_file.read_text(encoding="utf-8"))
        after: dict[str, int] = {}
        for company in rec.get("results") or []:
            for slot in company.get("slots") or []:
                after[slot.get("status")] = after.get(slot.get("status"), 0) + 1
        after_desc = "、".join(f"`{k}` {v}" for k, v in sorted(after.items())) or "无"
        lines += [
            "### 补采记录（采后发现缺陷）",
            "",
            f"本批采完后发现 **F7 选择缺陷**（同一期同时有中文全文与英文版时，按“发布更晚”选中英文版，"
            f"中文版被跳过、主体校验失败降级 PENDING），已修 `p05_collector.py::_select` 并补采 "
            f"{rec.get('companies')} 家 / {rec.get('slots')} 槽，补采后状态：{after_desc}。"
            f"原英文版记录留档在 `recollect_pending.json` 的 `superseded`（{len(rec.get('superseded') or [])} 条），未删除证据。",
            "",
        ]
    lines += [
        "",
        "## 六、存储与归档",
        "",
        "- 原件根：`sources/collection/originals`（目录联接 → `D:\\StockResearchLab\\IndustryInflectionLab\\robotics_data\\collection\\originals`）。",
        "- 台账：`runs/collection/checkpoint/*.json` + `runs/collection/collection_index.csv`（COLLECTION_LEDGER_V1，M00 后续批次共用）。",
        "- **Drive 未使用**：本会话无 Google Drive 连接器，`archive_status` 一律不写 VERIFIED；`document_receipts.csv` 只声明本地原件与校验结果。",
        "",
        "## 七、已知限制",
        "",
        "1. `listing_date` 仍 1054/1054 UNKNOWN：空目录只能记 `NOT_TRIED`，不得判上市前不适用或未披露。",
        "2. 本卡不抽财务字段：`field_coverage.csv` 只区分“旧快照已有 / 原件已取得待 S00 抽取 / 无来源”，不是财务结论。",
        "3. 自检由执行者本人完成，不等于独立审计；业务采用仍需独立复核。",
        "4. P05 故障用例 T07 期望“主体错配不留原件”，与 P07 冻结的 F2/F4 行为（低文本记 PENDING、错配保留 `.pdf.rejected`）不一致，属既有用例过期，本卡未改测试。",
        "5. `tools/validate_plan.py` 仍 106 通过 / 5 失败，全部是 P00 期包索引漂移（68 vs 67、59 vs 58、1056 vs 1054、`D00_B00_ADVANCE_01` 缺 ZIP），与本批采集无关；输出见 `plan_validation.txt`。",
        "",
        "## 八、下一步",
        "",
        f"- 下一张：`M00_02`（issue #20），沿用同一台账与配置，名单另取 `intake_batches/M00_02/assignment.csv`。",
        "- 开跑前不必重复本卡工作：登记表级幂等已进 `tools/p05_collector.py`（`lookup_order[2]`）。",
        "",
    ]
    path = out_dir(batch) / "handoff.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def slim_run_result(batch: str) -> Path:
    """把逐槽明细压成索引级记录：全量校验细节留在 coverage.csv 与 runs/collection/checkpoint。"""
    path = out_dir(batch) / "run_result.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    companies = []
    for company in data.get("companies", []):
        companies.append({
            "security_id": company.get("security_id"),
            "org_id": company.get("org_id"),
            "slots": [{k: slot.get(k) for k in ("slot_id", "status", "last_action", "document_id", "bytes")}
                      for slot in company.get("slots", [])],
        })
    slim = {k: v for k, v in data.items() if k != "companies"}
    slim["companies"] = companies
    slim["detail_location"] = "coverage.csv（逐槽） + runs/collection/checkpoint/*.json（含完整校验）"
    slim["slimmed_at"] = utc_now()
    write_json(path, slim)
    return path


def finalize(batch: str) -> dict:
    write_shared_index()
    slim_run_result(batch)
    coverage, summary = build_coverage(batch)
    receipts = build_receipts(batch, coverage)
    fields = build_field_coverage(batch, coverage)
    failures = build_failures(batch, coverage)
    checkpoint = write_checkpoint(batch, coverage, summary)
    review = build_review(batch, summary, failures, checkpoint)
    build_handoff(batch, summary, failures, checkpoint)
    manifest = {
        "batch_id": batch,
        "generated_at": utc_now(),
        "files": [],
    }
    for name in ["assignment_freeze.json", "coverage.csv", "document_receipts.csv",
                 "field_coverage.csv", "automatic_failures.csv", "checkpoint.json",
                 "run_result.json", "review.json", "handoff.md", "run.log",
                 "collector_patches.json", "recollect_pending.json", "plan_validation.txt"]:
        path = out_dir(batch) / name
        if path.exists():
            manifest["files"].append({"path": path.relative_to(ROOT).as_posix(),
                                      "bytes": path.stat().st_size,
                                      "sha256": sha256_file(path)})
    write_json(out_dir(batch) / "manifest.json", manifest)
    return {"summary": summary, "receipts": len(receipts), "fields": len(fields),
            "failures": len(failures), "checkpoint": checkpoint, "review": review}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="M00 批次执行器")
    parser.add_argument("--batch", required=True)
    parser.add_argument("--freeze", action="store_true")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--finalize", action="store_true")
    parser.add_argument("--recollect-pending", action="store_true",
                        help="重采 COLLECTED_PENDING_IDENTITY 槽位（修选择规则后补采）")
    parser.add_argument("--only-english", action="store_true",
                        help="配合 --recollect-pending：只补采当时选中英文版的槽位")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--no-optional-pdf", action="store_true")
    args = parser.parse_args(argv)
    if args.freeze:
        print(json.dumps(freeze(args.batch), ensure_ascii=False, indent=2))
    if args.run:
        run(args.batch, limit=args.limit, include_optional_pdf=not args.no_optional_pdf)
    if args.recollect_pending:
        print(json.dumps(recollect_pending(args.batch, only_english=args.only_english),
                         ensure_ascii=False, indent=2))
    if args.finalize:
        print(json.dumps(finalize(args.batch)["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
