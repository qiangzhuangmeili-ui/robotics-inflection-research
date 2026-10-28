#!/usr/bin/env python
"""A04R 补充材料采集：研究截止日前两年（2024-10-26~2026-10-25）全池公告/IR 目录。

P00 冻结的补充材料要求：
- announcement_ir_index：全候选池目录先行覆盖，含分页与公司代码；
- keyword_originals：机器人/人形/减速器/执行器/传感器/送样/量产/谐波/丝杠/灵巧手/伺服/关节模组
  等命中原件，仅命中项，不做全量抓取；
- financial_corrections：更正/修订/补充材料另存另 ID，并关联被替代版本。

本工具只做目录覆盖与命中登记（以及命中原件下载，见 --download-hits）。
关键词只用于取件排序，不作为机器人业务证据。

分页口径沿用 P05 冻结规则：累计去重行数必须等于 totalAnnouncement，
totalpages/hasMore 不作为判据；不完整即记 INDEX_INCOMPLETE_PAGINATION。
"""
from __future__ import annotations

import argparse
import csv
import time
import datetime as dt
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import m00_batch as M00  # noqa: E402
import p05_collector as P05  # noqa: E402

CONFIG_PATH = ROOT / "runs/issues/A01/collection_config_v2.json"
OUT_DIR = ROOT / "runs/issues/A04R"
INDEX_JSONL = OUT_DIR / "announcement_index.jsonl"
RAW_ROOT = ROOT / "sources/collection/raw_ann"
HIT_ROOT = ROOT / "sources/collection/originals_ann"

SE_START = "2024-10-26"
SE_END = "2026-10-25"
KEYWORDS = ["机器人", "人形", "减速器", "执行器", "传感器", "送样", "量产",
            "谐波", "丝杠", "灵巧手", "伺服", "关节模组"]
REVISION_PAT = re.compile(r"更正|修订|补充公告|补充说明|勘误")
IR_PAT = re.compile(r"投资者关系|机构调研|业绩说明会|路演|现场参观")


def read_csv(path: Path) -> list[dict]:
    with Path(path).open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def ts_to_date(ts) -> str:
    if isinstance(ts, (int, float)):
        return dt.datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d")
    return str(ts or "")


def done_codes() -> set[str]:
    if not INDEX_JSONL.exists():
        return set()
    out = set()
    for line in INDEX_JSONL.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        if d.get("reconciled"):
            out.add(d["stock_code"])
    return out


def fetch_all(collector: P05.Collector, company: P05.CompanyRef, org_id: str) -> dict:
    route = collector.config["routes"]["cninfo_issuer_index"]
    column = route["column_by_exchange"][company.exchange]
    page_size = int(route["page_size"])
    max_pages = int(route["max_pages"])
    base = {
        "tabName": route["base_params"]["tabName"], "searchkey": "", "isHLtitle": "true",
        "column": column, "category": "",
        "stock": route["stock_param_format"].format(stock_code=company.stock_code, org_id=org_id),
        "seDate": f"{SE_START}~{SE_END}",
    }
    rows: list[dict] = []
    seen: set[str] = set()
    total = None
    pages = 0
    raw_dir = RAW_ROOT / company.stock_code
    for page in range(1, max_pages + 1):
        params = dict(base, pageNum=str(page), pageSize=str(page_size))
        payload, call = collector.http.request_json(
            "cninfo_issuer_index", route["method"], route["url"], request_params=params, data=params)
        page_rows = (payload.get("announcements") if isinstance(payload, dict) else None) or []
        if total is None and isinstance(payload, dict):
            total = payload.get("totalAnnouncement")
        raw_dir.mkdir(parents=True, exist_ok=True)
        (raw_dir / f"p{page}.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        pages = page
        new = 0
        for row in page_rows:
            key = str(row.get("announcementId") or "")
            if key and key in seen:
                continue
            if key:
                seen.add(key)
            rows.append(row)
            new += 1
        if not page_rows or new == 0:
            break
        if isinstance(total, int) and len(rows) >= total:
            break
    reconciled = isinstance(total, int) and len(rows) == total
    hits, revisions, irs = [], [], []
    for row in rows:
        title = row.get("announcementTitle") or ""
        item = {
            "announcement_id": row.get("announcementId"), "title": title,
            "published_on": ts_to_date(row.get("announcementTime")),
            "url": "https://static.cninfo.com.cn/" + (row.get("adjunctUrl") or ""),
            "size_kb": row.get("adjunctSize"), "type": row.get("adjunctType"),
        }
        matched = [k for k in KEYWORDS if k in title]
        if matched:
            hits.append(dict(item, matched_keywords=matched))
        if REVISION_PAT.search(title):
            revisions.append(item)
        if IR_PAT.search(title):
            irs.append(item)
    return {
        "security_id": company.security_id, "stock_code": company.stock_code,
        "stock_name": company.stock_name, "exchange": company.exchange, "org_id": org_id,
        "se_date": f"{SE_START}~{SE_END}", "total_announcement": total,
        "rows_fetched": len(rows), "pages": pages, "reconciled": reconciled,
        "first_published_on": min((h["published_on"] for h in []), default="") or
        (min((ts_to_date(r.get("announcementTime")) for r in rows), default="") if rows else ""),
        "last_published_on": max((ts_to_date(r.get("announcementTime")) for r in rows), default="") if rows else "",
        "keyword_hits": hits, "revision_rows": revisions, "ir_rows": irs,
        "fetched_at": P05.utc_now(),
    }


def download_hits(collector: P05.Collector) -> dict:
    """把关键词命中的原件下载到 sources/collection/originals_ann/<code>/<announcement_id>.pdf。"""
    records = [json.loads(l) for l in INDEX_JSONL.read_text(encoding="utf-8").splitlines() if l.strip()]
    by_id = {r["security_id"]: r for r in records}
    manifest_path = OUT_DIR / "keyword_originals.jsonl"
    done = set()
    if manifest_path.exists():
        for line in manifest_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    done.add(json.loads(line)["announcement_id"])
                except Exception:
                    continue
    got = fail = 0
    with manifest_path.open("a", encoding="utf-8") as fh:
        for rec in records:
            company = P05.CompanyRef(rec["security_id"], rec["stock_code"], rec["stock_name"], rec["exchange"])
            for hit in rec.get("keyword_hits") or []:
                aid = str(hit["announcement_id"])
                if aid in done:
                    continue
                target_dir = HIT_ROOT / rec["stock_code"]
                target_dir.mkdir(parents=True, exist_ok=True)
                target = target_dir / f"{aid}.pdf"
                part = target.with_suffix(".pdf.part")
                try:
                    outcome, calls = collector.http.download("cninfo_pdf", hit["url"], part, expect_pdf=True)
                    part.replace(target)
                    got += 1
                    out = {"announcement_id": aid, "stock_code": rec["stock_code"],
                           "security_id": rec["security_id"], "title": hit["title"],
                           "published_on": hit["published_on"], "url": hit["url"],
                           "bytes": outcome.get("bytes"), "sha256": outcome.get("sha256"),
                           "status": "DOWNLOADED", "local_file": target.relative_to(ROOT).as_posix(),
                           "http_status": outcome.get("http_status"), "at": P05.utc_now()}
                except Exception as exc:
                    fail += 1
                    out = {"announcement_id": aid, "stock_code": rec["stock_code"],
                           "security_id": rec["security_id"], "title": hit["title"],
                           "published_on": hit["published_on"], "url": hit["url"],
                           "status": f"FAILED:{type(exc).__name__}:{exc}", "at": P05.utc_now()}
                fh.write(json.dumps(out, ensure_ascii=False) + "\n")
                fh.flush()
    return {"downloaded": got, "failed": fail, "manifest": manifest_path.relative_to(ROOT).as_posix()}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--code", action="append", default=None)
    ap.add_argument("--download-hits", action="store_true")
    ap.add_argument("--resume", action="store_true", help="跳过已 reconciled 的公司")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    collector = P05.Collector(config_path=CONFIG_PATH, root=ROOT)

    if args.download_hits:
        print(json.dumps(download_hits(collector), ensure_ascii=False), flush=True)
        return 0

    dates = M00.listing_date_map()
    refs = [P05.CompanyRef(r["security_id"], r["stock_code"], r["stock_name"],
                           r["security_id"].split(":")[0], dates.get(r["security_id"]))
            for r in read_csv(ROOT / "data/company_master.csv")]
    if args.code:
        want = set(args.code)
        refs = [c for c in refs if c.stock_code in want]
    if args.resume:
        skip = done_codes()
        refs = [c for c in refs if c.stock_code not in skip]
    if args.limit:
        refs = refs[: args.limit]

    print(f"待采集公司 {len(refs)}", flush=True)
    ok = bad = err = 0
    cooldown = float(collector.http.policy["cooldown_seconds"])
    waits = 0
    with INDEX_JSONL.open("a", encoding="utf-8") as fh:
        for i, company in enumerate(refs, 1):
            attempt = 0
            while True:
                attempt += 1
                try:
                    org = collector.resolve_org(company)
                    rec = fetch_all(collector, company, org["org_id"])
                    break
                except Exception as exc:
                    opened = [v["opened_at"] for v in collector.http.circuit_snapshot().values() if v["opened_at"]]
                    if opened and waits < 8:
                        wait = max(5.0, cooldown - (time.time() - max(opened)) + 5)
                        waits += 1
                        print(f"[{i}/{len(refs)}] {company.stock_code} 源熔断（{exc}），冷却 {wait:.0f}s 后重试"
                              f"（第 {waits}/8 次）", flush=True)
                        time.sleep(wait)
                        collector.http.states.clear()
                        continue
                    err += 1
                    print(f"[{i}/{len(refs)}] {company.stock_code} ERROR {type(exc).__name__}: {exc}", flush=True)
                    rec = None
                    break
            if rec is None:
                continue
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fh.flush()
            ok += 1 if rec["reconciled"] else 0
            bad += 0 if rec["reconciled"] else 1
            print(f"[{i}/{len(refs)}] {company.stock_code} total={rec['total_announcement']} "
                  f"rows={rec['rows_fetched']} pages={rec['pages']} hits={len(rec['keyword_hits'])} "
                  f"rev={len(rec['revision_rows'])} ir={len(rec['ir_rows'])} "
                  f"{'OK' if rec['reconciled'] else 'INCOMPLETE'}", flush=True)
    collector.flush_events()
    print(f"DONE ok={ok} incomplete={bad} errors={err}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
