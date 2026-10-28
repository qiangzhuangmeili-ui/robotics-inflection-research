"""A04 AC12 独立核验：财务更正版本链的「发现范围 vs 实际链集合」与逐项文件/哈希/关联校验。

设计原则：不读取上游 correction_chains.json 的 complete 计数，而是
1) 用与采集器同一口径，从全量公告目录重新推导「应有哪些更正组」；
2) 与链集合、缺口集合做双向差集；
3) 对每组逐项核：原件/更正件/公告件的文件存在性、sha256、supersedes 互链、原版与更正版标题不同。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

REP = re.compile(r"(年度报告|半年度报告|季度报告)")
FIX = re.compile(r"(更正|重述|勘误|修订)")
BAD = re.compile(r"(预案|股东大会|说明会|问询|回复|审计报告|专项报告|核查意见|法律意见|保荐|督导|"
                 r"募集资金|内部控制|社会责任|可持续发展|审计委员会|独立董事|监事会|"
                 r"提示性公告|披露提示|预约披露|业绩预告|业绩快报)")
H1 = re.compile(r"(20\d{2})\s*年\s*半年度报告")
Q1 = re.compile(r"(20\d{2})\s*年(?:度)?[\s_\-]*(?:第)?[\s_\-]*一[\s_\-]*季(?:度)?报告")
Q3 = re.compile(r"(20\d{2})\s*年(?:度)?[\s_\-]*(?:第)?[\s_\-]*三[\s_\-]*季(?:度)?报告")
AN = re.compile(r"(20\d{2})\s*(?:年)?(?:度)?\s*年度报告")


def slot_of(title: str) -> str | None:
    for pat, pre in ((H1, "h1"), (Q1, "q1"), (Q3, "q3"), (AN, "annual")):
        m = pat.search(title)
        if m:
            return f"{pre}_{m.group(1)}"
    return None


def discover(ann_path: Path, valid_slots: set[str]) -> tuple[set[tuple[str, str]], list[dict]]:
    """返回 (在冻结范围内的财报版本事件集合, 逐行处置登记表)。

    登记表覆盖**所有**含「报告 + 更正/重述/勘误/修订」的公告行，逐条写明处置与原因，
    便于复核「排除项为什么被排除」，而不是只给一个筛选后的子集。
    """
    out: set[tuple[str, str]] = set()
    register: list[dict] = []
    if not ann_path.exists():
        return out, register
    for line in ann_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        for it in rec.get("revision_rows") or []:
            t = it.get("title") or ""
            if not (REP.search(t) and FIX.search(t)):
                continue
            sl = slot_of(t)
            row = {"security_id": rec["security_id"], "stock_code": rec["stock_code"],
                   "title": t, "published_on": it.get("published_on", ""),
                   "matched_slot": sl or "", "url": it.get("url", "")}
            if "摘要" in t:
                row.update(disposition="EXCLUDED_SUMMARY", reason="摘要件，不是报告全文")
            elif BAD.search(t):
                row.update(disposition="EXCLUDED_NON_FINANCIAL",
                           reason="命中预案/股东大会/说明会/审计报告/独立董事制度/提示性公告等非财报更正关键词")
            elif sl not in valid_slots:
                row.update(disposition="EXCLUDED_OUT_OF_FROZEN_SCOPE",
                           reason=f"标题可解析到 {sl or 'NA'}，不在冻结 12 槽内")
            else:
                row.update(disposition="IN_SCOPE", reason="计入冻结范围内的财报版本事件")
                out.add((rec["security_id"], sl))
            register.append(row)
    return out, register


def verify_file(root: Path, entry: dict | None, sha) -> tuple[bool, bool, str]:
    if not entry:
        return True, True, "absent"
    lf = entry.get("local_file")
    if not lf or not (root / lf).is_file():
        return False, False, "file_missing"
    if entry.get("sha256"):
        ok = sha(root / lf) == entry["sha256"]
        return True, ok, "ok" if ok else "hash_mismatch"
    return True, False, "no_hash_recorded"


def audit(root: Path, period_end: dict[str, str], sha) -> dict:
    chain_path = root / "runs/issues/A04R/correction_chains.json"
    ann_path = root / "runs/issues/A04R/announcement_index.jsonl"
    chain = json.loads(chain_path.read_text(encoding="utf-8")) if chain_path.exists() else {}
    discovered, register = discover(ann_path, set(period_end))
    chains = {(r["security_id"], r["slot_id"]): r for r in chain.get("rows", [])}
    gaps = {(g["security_id"], g["slot_id"]): g for g in chain.get("gap_rows", [])}
    missing = sorted(discovered - set(chains) - set(gaps))
    extra = sorted(set(chains) - discovered)

    ck_cache: dict[str, dict] = {}

    def checkpoint(sid: str) -> dict:
        code = sid.split(":")[1]
        if code not in ck_cache:
            p = root / "runs/collection/checkpoint" / f"{code}.json"
            ck_cache[code] = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
        return ck_cache[code]

    rows, violations = [], []
    files_checked = 0
    for (sid, slot), row in sorted(chains.items()):
        ck = checkpoint(sid)
        vc = ((ck.get("slots") or {}).get(slot) or {}).get("document", {}).get("version_chain") or {}
        versions = {v["revision_no"]: v for v in vc.get("versions", [])}
        notice = vc.get("correction_notice") or {}
        orig, corr = versions.get(0), versions.get(1)
        o_ex, o_hash, o_note = verify_file(root, orig, sha)
        c_ex, c_hash, c_note = verify_file(root, corr, sha)
        n_ex, n_hash, n_note = verify_file(root, notice, sha)
        files_checked += sum(1 for e in (orig, corr, notice) if e)
        sup_ok = True
        if orig and corr:
            sup_ok = (corr.get("supersedes") == orig.get("document_id")
                      and orig.get("superseded_by") == corr.get("document_id"))
        notice_ok = bool(notice.get("document_id")) and n_ex and n_hash if notice else True
        same_title = bool(orig and corr and orig.get("title") == corr.get("title"))
        row_ok = bool(o_ex and o_hash and c_ex and c_hash and notice_ok and sup_ok and not same_title)
        rows.append({
            "security_id": sid, "slot_id": slot,
            "original_id": (orig or {}).get("document_id", ""),
            "corrected_id": (corr or {}).get("document_id", ""),
            "notice_id": notice.get("document_id", ""),
            "original_file": o_note, "original_hash": o_hash,
            "corrected_present": bool(corr), "corrected_file": c_note, "corrected_hash": c_hash,
            "notice_file": n_note, "notice_hash": n_hash,
            "supersedes_ok": sup_ok, "same_title": same_title, "ok": row_ok,
        })
        if not row_ok:
            violations.append({"security_id": sid, "slot_id": slot, "original": o_note,
                               "corrected": c_note, "notice": n_note,
                               "supersedes_ok": sup_ok, "same_title": same_title})

    ok_rows = sum(1 for r in rows if r["ok"])
    result = {
        "discovered_pairs": len(discovered), "chains": len(chains), "gaps": len(gaps),
        "missing_from_chains": missing, "extra_chains": extra,
        "chains_verified_ok": ok_rows, "violations": violations,
        "files_checked": files_checked,
        "notice_chains": sum(1 for r in rows if r["notice_id"]),
        "notice_with_file_and_hash": sum(1 for r in rows if r["notice_id"] and r["notice_file"] == "ok" and r["notice_hash"]),
        "notice_only_chains": sum(1 for r in chains.values() if r.get("corrected_full_text_missing")),
        "disposition_counts": {k: sum(1 for r in register if r["disposition"] == k)
                               for k in sorted({r["disposition"] for r in register})},
        "pass": (not missing and not extra and not violations and ok_rows == len(chains) and len(chains) > 0),
    }
    return {"summary": result, "rows": rows, "register": register}
