#!/usr/bin/env python
"""A04R 修正：从本地已取得的年报原件中提取"股转挂牌日"，替换"最早定期报告披露日"的错误推断。

证据口径：年报"公司简介/挂牌情况"表格中的「挂牌时间」或「挂牌日期」，
或"公司股票简况"中的上市（挂牌）日期。逐条记录 document_id、页码、原句片段。

用法：python tools/a04r_bj_listing_dates.py [--write]
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs/issues/A04R"
P03 = ROOT / "runs/issues/P03/neeq_recheck_20261027"

PATTERNS = [
    re.compile(r"挂牌(?:时间|日期)\s*[:：]?\s*(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日"),
    re.compile(r"挂牌(?:时间|日期)\s*[:：]?\s*(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})"),
    re.compile(r"(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日[^。；\n]{0,20}在全国(?:中小企业股份转让系统|股转系统)挂牌"),
]


def read_csv(p: Path) -> list[dict]:
    with p.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def scan_pdf(path: Path, max_pages: int = 30) -> dict | None:
    try:
        rd = PdfReader(str(path))
    except Exception:
        return None
    for i, page in enumerate(rd.pages[:max_pages]):
        text = page.extract_text() or ""
        for pat in PATTERNS:
            m = pat.search(text)
            if not m:
                continue
            y, mo, d = (int(x) for x in m.groups())
            try:
                date = f"{y:04d}-{mo:02d}-{d:02d}"
                datetime.strptime(date, "%Y-%m-%d")
            except ValueError:
                continue
            s = max(0, m.start() - 40)
            e = min(len(text), m.end() + 40)
            return {"neeq_listing_date": date, "page": i + 1,
                    "snippet": re.sub(r"\s+", " ", text[s:e]).strip()}
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    codes = {x["security_id"]: x["old_neeq_code"]
             for x in json.loads((P03 / "historical_code_mapping.json").read_text(encoding="utf-8"))}
    names = {r["security_id"]: r["stock_name"] for r in read_csv(ROOT / "data/company_master.csv")}
    ledger = read_csv(ROOT / "runs/collection/collection_index.csv")
    out = []
    for sid, old in sorted(codes.items()):
        code = sid.split(":")[1]
        rows = [r for r in ledger if r["security_id"] == sid and r["slot_id"].startswith("annual_")]
        rows.sort(key=lambda r: r["slot_id"])
        hit = None
        for r in rows:
            p = ROOT / (r["local_file"] or "")
            if not p.exists():
                continue
            got = scan_pdf(p)
            if got:
                hit = {**got, "document_id": r["document_id"], "slot_id": r["slot_id"],
                       "local_file": r["local_file"]}
                break
        out.append({"security_id": sid, "stock_code": code, "stock_name": names.get(sid, ""),
                    "old_neeq_code": old,
                    "neeq_listing_date": hit["neeq_listing_date"] if hit else "",
                    "evidence_kind": "LOCAL_ANNUAL_REPORT_PAGE" if hit else "NOT_FOUND",
                    "evidence_document_id": hit["document_id"] if hit else "",
                    "evidence_page": hit["page"] if hit else "",
                    "evidence_snippet": hit["snippet"] if hit else "",
                    "evidence_file": hit["local_file"] if hit else ""})
        print(f"{sid} {names.get(sid,'')} old={old} 挂牌日={out[-1]['neeq_listing_date'] or 'NOT_FOUND'} "
              f"({out[-1]['evidence_page']})", flush=True)

    payload = {
        "scope": "A04R_NEEQ_LISTING_DATES_FROM_LOCAL_ANNUALS",
        "generated_at": datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds"),
        "purpose": "替换 tools/a04r_bj_applicability.py 中以 earliest_publish_date 推断挂牌日的错误做法",
        "rule": "period_end < neeq_listing_date → NOT_APPLICABLE_PRE_LISTING；否则按季报索引判定未披露/取得",
        "found": sum(1 for r in out if r["neeq_listing_date"]),
        "missing": [r["security_id"] for r in out if not r["neeq_listing_date"]],
        "rows": out,
    }
    if args.write:
        (OUT / "neeq_listing_dates.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("written", OUT / "neeq_listing_dates.json")
    print(json.dumps({k: v for k, v in payload.items() if k != "rows"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
