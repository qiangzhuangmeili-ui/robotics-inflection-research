#!/usr/bin/env python
"""A04R 修正：财务报告更正版本链（原版 + 更正版 + 更正公告 + 替代关系）。

P00 要求：financial_corrections 的 required_form = ORIGINAL_PDF_PLUS_LINK_TO_SUPERSEDED，
即"保留原始版与更正版并建立关联，不覆盖追溯原件"。

做法：
1. 从已落盘的全量公告目录（sources/collection/raw_ann/<code>/p*.json）里筛出**财务报告类**更正行；
   排除发行预案、股东大会通知、说明会、问询回复等非财报更正。
2. 按 (security_id, slot_id) 归组：原版 / 更正后 / 更正公告 / 专项说明。
3. 缺哪一版就下哪一版，落到 originals/<code>/<slot>/<document_id>.pdf；document_id 按
   IDENTITY_V1 的 revision_no 区分（原版 0、更正版 1），不覆盖原文件。
4. 在台账槽记录里写 document.version_chain（含 supersedes / superseded_by / notice）。
5. 2 年窗口外无法定位原版的，逐条记 GAP 并写明原因，不宣称已闭环。

用法：python tools/a04r_correction_chain.py [--run] [--limit N]
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
RAW = ROOT / "sources/collection/raw_ann"
CKPT = ROOT / "runs/collection/checkpoint"

REP = re.compile(r"(年度报告|半年度报告|季度报告)")
FIX = re.compile(r"(更正|重述|勘误|修订)")  # 复核要求：修订版/修订公告同样纳入版本发现
BAD = re.compile(r"(预案|股东大会|说明会|问询|回复|审计报告|专项报告|核查意见|法律意见|保荐|督导|"
                 r"募集资金|内部控制|社会责任|可持续发展|审计委员会|独立董事|监事会|"
                 r"提示性公告|披露提示|预约披露|业绩预告|业绩快报)")
H1 = re.compile(r"(20\d{2})\s*年\s*半年度报告")
AN = re.compile(r"(20\d{2})\s*年(?:度)?\s*年度报告")
Q1 = re.compile(r"(20\d{2})\s*年(?:度)?[\s_\-]*(?:第)?[\s_\-]*一[\s_\-]*季(?:度)?报告")
Q3 = re.compile(r"(20\d{2})\s*年(?:度)?[\s_\-]*(?:第)?[\s_\-]*三[\s_\-]*季(?:度)?报告")


def utc_now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def slot_of(title: str) -> str | None:
    m = H1.search(title)
    if m:
        return f"h1_{m.group(1)}"
    m = Q1.search(title)
    if m:
        return f"q1_{m.group(1)}"
    m = Q3.search(title)
    if m:
        return f"q3_{m.group(1)}"
    m = AN.search(title)
    if m:
        return f"annual_{m.group(1)}"
    return None


def kind_of(title: str) -> str:
    """实测标题变体：「更正后」「更正版」「更正的公告」「更正公告」都要认。"""
    if "摘要" in title:
        return "summary"
    if re.search(r"更正后|更正版|修订后|修订版|更新后|更新稿|更新版|修正版|（更正）|\(更正\)", title):
        return "corrected"
    if ("更正公告" in title or "更正的公告" in title or "修订公告" in title
            or ("更正" in title and "公告" in title) or ("修订" in title and "公告" in title)):
        return "notice"
    if "专项说明" in title or "专项意见" in title or "专项鉴证" in title:
        return "auditor_note"
    return "original"


CAT = {"annual": "ndbg", "h1": "bndbg", "q1": "yjdbg", "q3": "sjdbg"}


def category_rows(code: str, slot: str) -> list[dict]:
    """定期报告类别目录（覆盖 2023-01-01 起），用于补两年窗口外的原版。"""
    cat = CAT[slot.split("_")[0]]
    out = []
    for f in sorted((ROOT / "sources/collection/raw" / code).glob(f"category_{cat}_szsh_p*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        out += d.get("announcements") or []
    return out


def read_rows(code: str) -> list[dict]:
    out = []
    for f in sorted(RAW.joinpath(code).glob("p*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        for a in d.get("announcements") or []:
            out.append(a)
    return out


def to_date(ts) -> str:
    try:
        return datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d")
    except Exception:
        return ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    ann = [json.loads(l) for l in (OUT / "announcement_index.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    slots = {s["slot_id"]: s for s in cfg["slots"]}
    names = {r["security_id"]: r["stock_name"]
             for r in csv.DictReader(open(ROOT / "data/company_master.csv", encoding="utf-8-sig"))}

    # 1) 找出有财报更正的 (security_id, slot)
    affected = {}
    for rec in ann:
        for it in rec["revision_rows"]:
            t = it["title"]
            if not (REP.search(t) and FIX.search(t)) or BAD.search(t):
                continue
            slot = slot_of(t)
            if slot not in slots:
                continue
            affected.setdefault((rec["security_id"], slot), set()).add(rec["stock_code"])
    print(f"涉及财报更正的 (公司, 槽) 组合 {len(affected)}", flush=True)
    if not args.run:
        print(sorted({s for _, s in affected})[:10])
        return 0

    collector = P05.Collector(config_path=CONFIG, root=ROOT)
    prev_titles = {}
    prev_path = OUT / "correction_titles.json"
    if prev_path.exists():
        try:
            prev_titles = json.loads(prev_path.read_text(encoding="utf-8"))
        except Exception:
            prev_titles = {}
    chains, gaps = [], []
    items = sorted(affected.items())
    if args.limit:
        items = items[: args.limit]
    for (sid, slot), _codes in items:
        code = sid.split(":")[1]
        rows = read_rows(code)
        period_rows = []
        for a in rows:
            t = a.get("announcementTitle") or ""
            if slot_of(t) != slot:
                continue
            if BAD.search(t) or "摘要" in t:
                continue
            period_rows.append({
                "announcement_id": a.get("announcementId"), "title": t,
                "published_on": to_date(a.get("announcementTime")),
                "url": "https://static.cninfo.com.cn/" + (a.get("adjunctUrl") or ""),
                "size_kb": a.get("adjunctSize"), "kind": kind_of(t),
            })
        # 只有「更正后全文」或「更正公告」之一也算有更正链；两者都没有才记缺口（在后面统一判）
        if not any(r["kind"] in ("corrected", "notice") for r in period_rows):
            gaps.append({"security_id": sid, "slot_id": slot, "gap": "NO_CORRECTION_ROW_IN_WINDOW",
                         "reason": "两年目录窗口内没有「更正后全文」也没有「更正公告」行"})
            continue
        original = next((r for r in period_rows if r["kind"] == "original"), None)
        corrected = next((r for r in period_rows if r["kind"] == "corrected"), None)
        notice = next((r for r in period_rows if r["kind"] == "notice"), None)
        if original is None:
            # 两年公告窗口未覆盖原版时，回定期报告类别目录（2023-01-01 起）取原版
            for a in category_rows(code, slot):
                t = a.get("announcementTitle") or ""
                if slot_of(t) != slot or "摘要" in t or "英文" in t:
                    continue
                if re.search(r"更正|修订|更新|重述|勘误", t):
                    continue
                original = {"announcement_id": a.get("announcementId"), "title": t,
                            "published_on": to_date(a.get("announcementTime")),
                            "url": "https://static.cninfo.com.cn/" + (a.get("adjunctUrl") or ""),
                            "size_kb": a.get("adjunctSize"), "kind": "original",
                            "source": "CATEGORY_INDEX"}
                break
        if original is None:
            gaps.append({"security_id": sid, "slot_id": slot, "gap": "ORIGINAL_NOT_FOUND",
                         "reason": "两年公告目录与定期报告类别目录均未定位到原版；需回官方历史检索",
                         "corrected": corrected})
            continue
        if corrected is None:
            # 只有更正公告、公司未重发全文：按「原版 + 更正公告」结链，并标注未重发全文
            if notice is None:
                gaps.append({"security_id": sid, "slot_id": slot, "gap": "NO_CORRECTED_VERSION_IN_WINDOW",
                             "reason": "窗口内只有更正标记，无「更正后」全文，也无更正公告"})
                continue

        path = CKPT / f"{code}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        rec = data["slots"][slot]
        chain = []
        versions = [(0, original)] + ([(1, corrected)] if corrected else [])
        for rev, item in versions:
            ident = (f"{sid}|CONSOLIDATED_LISTED_ISSUER|{slots[slot]['report_type']}|"
                     f"{slots[slot]['period_label']}|{rev}")
            did = "DOC-" + hashlib.sha256(ident.encode()).hexdigest()[:16].upper()
            target = ROOT / "sources/collection/originals" / code / slot / f"{did}.pdf"
            target.parent.mkdir(parents=True, exist_ok=True)
            prev = (prev_titles or {}).get(did)
            if target.exists() and prev and prev != item["title"]:
                target.unlink()  # 同 ID 但来源行变了：旧文件是另一份文档，不能复用
            entry = {"revision_no": rev, "document_id": did, "title": item["title"],
                     "published_on": item["published_on"], "primary_url": item["url"],
                     "role": "original" if rev == 0 else "corrected"}
            if target.exists():
                entry.update({"local_file": target.relative_to(ROOT).as_posix(),
                              "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                              "bytes": target.stat().st_size, "downloaded_now": False})
            else:
                part = target.with_suffix(".pdf.part")
                try:
                    outcome, _ = collector.http.download("cninfo_pdf", item["url"], part, expect_pdf=True)
                    part.replace(target)
                    entry.update({"local_file": target.relative_to(ROOT).as_posix(),
                                  "sha256": outcome.get("sha256"), "bytes": outcome.get("bytes"),
                                  "downloaded_now": True})
                except Exception as exc:
                    entry.update({"download_error": f"{type(exc).__name__}: {exc}"[:200],
                                  "downloaded_now": False})
            chain.append(entry)
            print(f"  {sid} {slot} rev{rev} {'OK' if 'sha256' in entry else 'FAIL'} {item['title'][:40]}", flush=True)

        notice_entry = None
        if notice:
            nkey = (f"{sid}|CONSOLIDATED_LISTED_ISSUER|CORRECTION_NOTICE|"
                    f"{slots[slot]['period_label']}|0")
            ndid = "DOC-" + hashlib.sha256(nkey.encode()).hexdigest()[:16].upper()
            ntarget = ROOT / "sources/collection/originals" / code / slot / f"{ndid}.pdf"
            ntarget.parent.mkdir(parents=True, exist_ok=True)
            nprev = (prev_titles or {}).get(ndid)
            if ntarget.exists() and nprev and nprev != notice["title"]:
                ntarget.unlink()
            notice_entry = {"role": "notice", "document_id": ndid, "title": notice["title"],
                            "published_on": notice["published_on"], "primary_url": notice["url"]}
            if ntarget.exists():
                notice_entry.update({"local_file": ntarget.relative_to(ROOT).as_posix(),
                                     "sha256": hashlib.sha256(ntarget.read_bytes()).hexdigest(),
                                     "bytes": ntarget.stat().st_size, "downloaded_now": False})
            else:
                npart = ntarget.with_suffix(".pdf.part")
                try:
                    out_n, _ = collector.http.download("cninfo_pdf", notice["url"], npart, expect_pdf=True)
                    npart.replace(ntarget)
                    notice_entry.update({"local_file": ntarget.relative_to(ROOT).as_posix(),
                                         "sha256": out_n.get("sha256"), "bytes": out_n.get("bytes"),
                                         "downloaded_now": True})
                except Exception as exc:
                    notice_entry["download_error"] = f"{type(exc).__name__}: {exc}"[:200]
            print(f"  {sid} {slot} notice {'OK' if 'sha256' in notice_entry else 'FAIL'} {notice['title'][:36]}", flush=True)
        ok = all("sha256" in e for e in chain) and (notice_entry is None or "sha256" in notice_entry)
        for e in chain:
            e["supersedes"] = chain[0]["document_id"] if e["role"] == "corrected" else None
            e["superseded_by"] = chain[1]["document_id"] if (e["role"] == "original" and len(chain) > 1) else None
        rec.setdefault("document", {})["version_chain"] = {
            "policy": "ORIGINAL_PDF_PLUS_LINK_TO_SUPERSEDED",
            "effective_document_id": chain[-1]["document_id"],
            "versions": chain,
            "correction_notice": notice_entry,
            "complete": ok,
            "recorded_at": utc_now(),
        }
        rec["document"]["supersedes"] = chain[0]["document_id"]
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        chains.append({"security_id": sid, "slot_id": slot,
                       "original": chain[0]["document_id"],
                       "corrected": chain[1]["document_id"] if len(chain) > 1 else "",
                       "corrected_full_text_missing": corrected is None,
                       "original_title": chain[0]["title"],
                       "corrected_title": chain[1]["title"] if len(chain) > 1 else "",
                       "notice": notice_entry["primary_url"] if notice_entry else "",
                       "notice_document_id": (notice_entry or {}).get("document_id", ""),
                       "notice_title": (notice_entry or {}).get("title", ""),
                       "notice_sha256": (notice_entry or {}).get("sha256", ""),
                       "complete": ok})
        if not ok:
            gaps.append({"security_id": sid, "slot_id": slot, "gap": "DOWNLOAD_FAILED",
                         "reason": "原版或更正版下载失败，保留错误码"})

    payload = {
        "scope": "A04R_FINANCIAL_CORRECTION_CHAINS",
        "generated_at": utc_now(),
        "policy": "ORIGINAL_PDF_PLUS_LINK_TO_SUPERSEDED；不覆盖原件",
        "pairs": len(chains), "complete": sum(1 for c in chains if c["complete"]),
        "gaps": len(gaps), "rows": chains, "gap_rows": gaps,
    }
    (OUT / "correction_chains.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                                               encoding="utf-8")
    with (OUT / "correction_chains.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["security_id", "slot_id", "original", "corrected", "notice", "complete",
                         "corrected_full_text_missing", "original_title", "corrected_title",
                         "notice_document_id", "notice_sha256", "notice_title"])
        w.writeheader()
        w.writerows(chains)
    print(json.dumps({"pairs": len(chains), "complete": payload["complete"], "gaps": len(gaps)},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
