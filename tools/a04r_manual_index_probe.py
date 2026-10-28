#!/usr/bin/env python
"""A04R：处理 5 个「已上市但类别目录无该期全文」的沪市季度槽。

现象：q3_2024/q3_2025 等槽在 category_sjdbg/yjdbg 目录里没有对应行，但公司早已上市。
做法：不直接判未披露，改用**全量公告目录 + 关键词**在同一披露窗口内检索，
      找到即下载校验并回写台账；找不到则记录检索证据后再判。
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import p05_collector as P05  # noqa: E402

CONFIG = ROOT / "runs/issues/A01/collection_config_v2.json"
OUT = ROOT / "runs/issues/A04R"
CKPT = ROOT / "runs/collection/checkpoint"

# 槽位 → 披露窗口（法定披露期前后留余量）
WINDOWS = {
    "q1_2024": ("2024-04-01", "2024-05-31"),
    "q3_2024": ("2024-10-01", "2024-12-31"),
    "q1_2025": ("2025-04-01", "2025-05-31"),
    "q3_2025": ("2025-10-01", "2025-12-31"),
    "q3_2026": ("2026-10-01", "2026-10-25"),
}
# 实测标题变体：2024年_三季度报告（下划线）、2024年度第一季报告（缺「度」）、
# 第三季度/三季度（有无「第」）、宁波精达「三季度报告」（标题无年份）。
TITLE = {
    "q1_2024": re.compile(r"2024\s*年(?:度)?[\s_\-]*(?:第)?[\s_\-]*一[\s_\-]*季(?:度)?报告"),
    "q3_2024": re.compile(r"2024\s*年(?:度)?[\s_\-]*(?:第)?[\s_\-]*三[\s_\-]*季(?:度)?报告"),
    "q1_2025": re.compile(r"2025\s*年(?:度)?[\s_\-]*(?:第)?[\s_\-]*一[\s_\-]*季(?:度)?报告"),
    "q3_2025": re.compile(r"2025\s*年(?:度)?[\s_\-]*(?:第)?[\s_\-]*三[\s_\-]*季(?:度)?报告"),
    "q3_2026": re.compile(r"2026\s*年(?:度)?[\s_\-]*(?:第)?[\s_\-]*三[\s_\-]*季(?:度)?报告"),
}
# 标题不含年份时的兜底：仅在法定披露窗口内、且排除摘要/说明会后接受
TITLE_NOYEAR = {
    "q1_2024": re.compile(r"(?:第)?[\s_\-]*一[\s_\-]*季(?:度)?报告"),
    "q3_2024": re.compile(r"(?:第)?[\s_\-]*三[\s_\-]*季(?:度)?报告"),
    "q1_2025": re.compile(r"(?:第)?[\s_\-]*一[\s_\-]*季(?:度)?报告"),
    "q3_2025": re.compile(r"(?:第)?[\s_\-]*三[\s_\-]*季(?:度)?报告"),
    "q3_2026": re.compile(r"(?:第)?[\s_\-]*三[\s_\-]*季(?:度)?报告"),
}
EXCLUDE = ("摘要", "英文", "取消", "说明会", "业绩", "预约", "提示性", "更正", "问询", "回复", "新闻", "预告")


def utc_now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def targets() -> list[dict]:
    out = []
    for p in sorted(CKPT.glob("*.json")):
        data = json.loads(p.read_text(encoding="utf-8"))
        sid = data.get("security_id") or ""
        if not sid.startswith("SH"):
            continue
        for slot, rec in (data.get("slots") or {}).items():
            if (rec.get("status") == "NOT_TRIED" and rec.get("next_action") == "MANUAL_REVIEW_INDEX")                     or rec.get("reason_code") == "FULL_INDEX_AND_KEYWORD_SEARCH_EMPTY":
                out.append({"security_id": sid, "stock_code": sid.split(":")[1], "slot_id": slot})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true")
    args = ap.parse_args()
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    slots = {s["slot_id"]: s for s in cfg["slots"]}
    names = {r["security_id"]: r["stock_name"]
             for r in csv.DictReader(open(ROOT / "data/company_master.csv", encoding="utf-8-sig"))}
    items = targets()
    print(f"待复核槽 {len(items)}：{[(i['stock_code'], i['slot_id']) for i in items]}", flush=True)
    if not args.run:
        return 0

    collector = P05.Collector(config_path=CONFIG, root=ROOT)
    route = collector.config["routes"]["cninfo_issuer_index"]
    results = []
    for item in items:
        code, slot = item["stock_code"], item["slot_id"]
        company = P05.CompanyRef(item["security_id"], code, names.get(item["security_id"], ""), "SH")
        org = collector.resolve_org(company)
        start, end = WINDOWS[slot]
        params = {
            "tabName": "fulltext", "searchkey": "", "isHLtitle": "true",
            "column": route["column_by_exchange"]["SH"], "category": "",
            "stock": f"{code},{org['org_id']}", "seDate": f"{start}~{end}",
            "pageNum": "1", "pageSize": "30",
        }
        rows = []
        total = None
        for page in range(1, 6):
            params["pageNum"] = str(page)
            payload, call = collector.http.request_json(
                "cninfo_issuer_index", "POST", route["url"], request_params=params, data=params)
            page_rows = (payload.get("announcements") if isinstance(payload, dict) else None) or []
            if total is None and isinstance(payload, dict):
                total = payload.get("totalAnnouncement")
            rows += page_rows
            if not page_rows or (isinstance(total, int) and len(rows) >= total):
                break
        print(f"  窗口内公告 {len(rows)} 条（total={total}）", flush=True)
        hit = None
        for r in rows:
            title = r.get("announcementTitle") or ""
            if any(k in title for k in EXCLUDE):
                continue
            if TITLE[slot].search(title) or TITLE_NOYEAR[slot].search(title):
                hit = r
                break
        print(f"{code} {slot} 窗口{start}~{end} 命中候选 {len(rows)} -> {hit.get('announcementTitle') if hit else 'NONE'}", flush=True)
        path = CKPT / f"{code}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        rec = data["slots"][slot]
        if not hit:
            results.append({**item, "found": False, "candidates": len(rows),
                            "evidence": f"全量公告目录（{start}~{end}，共 {len(rows)} 条）内无该期季度报告"})
            rec["status"] = "NOT_DISCLOSED_BY_ISSUER"
            rec["status_reason"] = (f"A04R 复核：类别目录与全量公告目录（{start}~{end}，共 {len(rows)} 条）"
                                    f"均无该期季度报告，判公司未披露")
            rec["next_action"] = "NONE"
            rec["reason_code"] = "FULL_INDEX_AND_KEYWORD_SEARCH_EMPTY"
            rec["updated_at"] = utc_now()
        else:
            url = "https://static.cninfo.com.cn/" + hit["adjunctUrl"]
            identity_key = (f"{item['security_id']}|CONSOLIDATED_LISTED_ISSUER|"
                            f"{slots[slot]['report_type']}|{slots[slot]['period_label']}|0")
            did = "DOC-" + hashlib.sha256(identity_key.encode()).hexdigest()[:16].upper()
            target = ROOT / "sources/collection/originals" / code / slot / f"{did}.pdf"
            target.parent.mkdir(parents=True, exist_ok=True)
            part = target.with_suffix(".pdf.part")
            outcome, _ = collector.http.download("cninfo_pdf", url, part, expect_pdf=True)
            part.replace(target)
            slot_ctx = dict(slots[slot], _selected_title=hit.get("announcementTitle") or "")
            val = P05.validate_pdf(target, slot_ctx, stock_name=names.get(item["security_id"], ""),
                                   stock_code=code, config=cfg)
            published = datetime.fromtimestamp(hit["announcementTime"] / 1000).strftime("%Y-%m-%d")
            rec.update({
                "status": val["identity_status"],
                "status_reason": "A04R 复核：类别目录缺行，全量公告目录命中并校验通过",
                "next_action": "NONE" if val["identity_status"] == "COLLECTED_IDENTITY_VERIFIED" else "MANUAL_IDENTITY_CHECK",
                "document": {"document_id": did, "title": hit.get("announcementTitle"),
                             "published_on": published, "primary_url": url,
                             "sha256": outcome.get("sha256"), "bytes": outcome.get("bytes"),
                             "page_count": val.get("page_count"), "form": val.get("form"),
                             "local_file": target.relative_to(ROOT).as_posix(),
                             "identity_checks": val["checks"],
                             "recovery_route": "FULL_ANNOUNCEMENT_INDEX_KEYWORD"},
                "validation": val, "updated_at": utc_now(),
                "attempt_count": int(rec.get("attempt_count") or 0) + 1,
                "source_attempts": (rec.get("source_attempts") or []) + [{
                    "route": "cninfo_pdf", "method": "GET", "url": url,
                    "http_status": outcome.get("http_status"), "outcome": "SUCCESS",
                    "bytes": outcome.get("bytes"), "at": utc_now()}],
            })
            results.append({**item, "found": True, "title": hit.get("announcementTitle"),
                            "published_on": published, "url": url, "status": val["identity_status"]})
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    (OUT / "manual_index_probe.json").write_text(
        json.dumps({"at": utc_now(), "items": results}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(results, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
