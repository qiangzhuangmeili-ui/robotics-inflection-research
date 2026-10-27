#!/usr/bin/env python
"""A04 返工：把 cutoff_hold.csv 中 7 份披露日 UNKNOWN 的文档补上官方日期证据。

证据只取本机已落盘的官方目录原始响应（sources/collection/raw/<code>/category_ndbg_szsh_p*.json），
不新发 HTTP 请求；同时用目录行 adjunctSize(KB) 与本地原件字节数做量级一致性校验。
结论：日期 <= 2026-10-25 才可进入本轮证据链；否则仍保持 HOLD 并记 AFTER_CUTOFF。
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOLD = ROOT / "runs/issues/A04/cutoff_hold.csv"
OUT_DIR = ROOT / "runs/issues/A04/rework"
CUTOFF = "2026-10-25"


def read_csv(path: Path) -> list[dict]:
    with Path(path).open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def ts_to_date(ts) -> str:
    if isinstance(ts, (int, float)):
        return dt.datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d")
    return str(ts or "")


def main() -> int:
    rows = read_csv(HOLD)
    out = []
    for r in rows:
        code = r["security_id"].split(":")[1]
        slot = r["slot_id"]
        year = re.search(r"(\d{4})", slot).group(1)
        ledger = json.loads((ROOT / "runs/collection/checkpoint" / f"{code}.json").read_text(encoding="utf-8"))
        rec = (ledger.get("slots") or {}).get(slot) or {}
        doc = rec.get("document") or {}
        local = ROOT / (doc.get("local_file") or "")
        local_bytes = local.stat().st_size if local.exists() else None

        hits = []
        for raw in sorted((ROOT / "sources/collection/raw" / code).glob("category_ndbg_szsh_p*.json")):
            data = json.loads(raw.read_text(encoding="utf-8"))
            for a in data.get("announcements") or []:
                title = a.get("announcementTitle") or ""
                if f"{year}年年度报告" not in title:
                    continue
                if "摘要" in title or "英文" in title or "取消" in title:
                    continue
                hits.append({
                    "raw_file": raw.relative_to(ROOT).as_posix(),
                    "raw_sha256": sha256_file(raw),
                    "announcement_id": a.get("announcementId"),
                    "title": title,
                    "published_on": ts_to_date(a.get("announcementTime")),
                    "adjunct_url": "https://static.cninfo.com.cn/" + (a.get("adjunctUrl") or ""),
                    "adjunct_size_kb": a.get("adjunctSize"),
                })
        best = sorted(hits, key=lambda x: x["published_on"])[-1] if hits else None
        size_ok = None
        if best and local_bytes and isinstance(best.get("adjunct_size_kb"), (int, float)):
            diff = abs(local_bytes - best["adjunct_size_kb"] * 1024)
            size_ok = diff <= 2048  # 目录只给 KB 级整数，允许 ±2KB 舍入
        verdict = "UNRESOLVED"
        if best:
            verdict = "DATE_RESOLVED_WITHIN_CUTOFF" if best["published_on"] <= CUTOFF else "AFTER_CUTOFF_KEEP_HOLD"
        out.append({
            "security_id": r["security_id"], "slot_id": slot,
            "document_id": r["document_id"],
            "previous_published_on": r["published_on"],
            "official_published_on": best["published_on"] if best else "",
            "index_raw_file": best["raw_file"] if best else "",
            "index_raw_sha256": best["raw_sha256"] if best else "",
            "announcement_id": best["announcement_id"] if best else "",
            "adjunct_url": best["adjunct_url"] if best else "",
            "local_bytes": local_bytes or "",
            "adjunct_size_kb": best["adjunct_size_kb"] if best else "",
            "byte_size_consistent": "" if size_ok is None else str(size_ok).lower(),
            "cutoff": CUTOFF,
            "verdict": verdict,
            "hold_released": "true" if verdict == "DATE_RESOLVED_WITHIN_CUTOFF" else "false",
        })

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / "cutoff_hold_resolved.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0].keys()))
        w.writeheader()
        w.writerows(out)

    summary = {
        "scope": "A04_CUTOFF_HOLD_RESOLUTION",
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "cutoff": CUTOFF,
        "input": HOLD.relative_to(ROOT).as_posix(),
        "documents": len(out),
        "resolved_within_cutoff": sum(1 for r in out if r["verdict"] == "DATE_RESOLVED_WITHIN_CUTOFF"),
        "after_cutoff": sum(1 for r in out if r["verdict"] == "AFTER_CUTOFF_KEEP_HOLD"),
        "unresolved": sum(1 for r in out if r["verdict"] == "UNRESOLVED"),
        "byte_size_consistent": sum(1 for r in out if r["byte_size_consistent"] == "true"),
        "evidence_nature": "OFFICIAL_INDEX_RAW_RESPONSE_ON_DISK_NO_NEW_HTTP",
        "limits": [
            "日期来自本机已落盘的巨潮年度报告目录原始响应（2026-10-26 抓取），本次未重新请求官方站。",
            "adjunctSize 为 KB 整数，字节一致性只做 ±2KB 舍入校验，不等于逐字节哈希核验。",
            "日期结论只用于截止日判定，不构成业务证据或全文核读。",
        ],
        "rows": out,
    }
    (OUT_DIR / "cutoff_hold_resolution.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "rows"}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
