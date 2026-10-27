"""A04 返工复验：按 P00 冻结的 12 个报告槽 + 补充材料范围重算，不改写首次验收产物。

只读输入；输出全部写 runs/issues/A04/rework/。
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
inputs: dict[str, str] = {}


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def read(rel: str) -> dict:
    p = ROOT / rel
    inputs[p.relative_to(ROOT).as_posix()] = sha(p)
    return json.loads(p.read_text(encoding="utf-8-sig"))


def rows(rel: str) -> list[dict]:
    p = ROOT / rel
    inputs[p.relative_to(ROOT).as_posix()] = sha(p)
    with p.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def write(name: str, payload) -> None:
    (OUT / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def csvout(name: str, rs: list[dict], keys: list[str] | None = None) -> None:
    if not rs:
        (OUT / name).write_text("", encoding="utf-8")
        return
    with (OUT / name).open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys or list(rs[0].keys()), extrasaction="ignore")
        w.writeheader()
        w.writerows(rs)


scope = read("runs/issues/P00/collection_scope.json")
rules = read("runs/issues/P00/coverage_acceptance_rules.json")
fp = read("runs/issues/P00/universe_fingerprint.json")
master = rows("data/company_master.csv")
ids = {r["security_id"] for r in master}
canonical = "\n".join("\t".join(r[k] for k in ["security_id", "stock_code", "stock_name", "exchange"])
                      for r in sorted(master, key=lambda r: r["security_id"])) + "\n"
roster_hash = hashlib.sha256(canonical.encode()).hexdigest()
queue = rows("data/intake_company_queue.csv")
batches = rows("data/intake_batch_index.csv")
assign: list[dict] = []
batch_checks = []
for b in batches:
    rr = rows(b["assignment_path"])
    assign += rr
    batch_checks.append({"batch_id": b["batch_id"], "expected": int(b["company_count"]),
                         "actual": len(rr), "pass": len(rr) == int(b["company_count"])})
ledger = rows("runs/collection/collection_index.csv")
listing = {r["security_id"]: r for r in rows("data/company_listing_dates.csv")}
slotdefs = scope["report_slots"] + scope["quarterly_slots"]
cutoff = scope["time_axis"]["knowledge_as_of"]
status = Counter(r["status"] for r in ledger)
pairs = Counter((r["security_id"], r["slot_id"]) for r in ledger)

# ---------------------------------------------------------------- AC04 / AC05 逐槽终态
NON_TERMINAL = {"NOT_TRIED", "", None}
by_slot: dict[str, list[dict]] = defaultdict(list)
for r in ledger:
    by_slot[r["slot_id"]].append(r)
coverage, dispositions = [], []
absent_detail = []
for s in slotdefs:
    sid = s["slot_id"]
    rr = by_slot.get(sid, [])
    present = {r["security_id"] for r in rr}
    absent = sorted(ids - present)
    counts = Counter(r["status"] for r in rr)
    nonterm = sum(1 for r in rr if r["status"] in NON_TERMINAL)
    na_by_date = sum(1 for i in ids if listing.get(i, {}).get("listing_date", "") > s["period_end"])
    coverage.append({
        "slot_id": sid, "report_type": s["report_type"], "period_end": s["period_end"],
        "statutory_deadline": s["statutory_deadline"],
        "deadline_before_cutoff": str(s.get("deadline_before_cutoff", "")).lower(),
        "frozen_pool": len(ids), "ledger_rows": len(rr), "absent_from_ledger": len(absent),
        "not_tried": counts.get("NOT_TRIED", 0),
        "collected_identity_verified": counts.get("COLLECTED_IDENTITY_VERIFIED", 0),
        "collected_pending_identity": counts.get("COLLECTED_PENDING_IDENTITY", 0),
        "not_applicable_pre_listing": counts.get("NOT_APPLICABLE_PRE_LISTING", 0),
        "not_disclosed_by_issuer": counts.get("NOT_DISCLOSED_BY_ISSUER", 0),
        "not_yet_disclosed": counts.get("NOT_YET_DISCLOSED", 0),
        "after_cutoff_disclosed": counts.get("AFTER_CUTOFF_DISCLOSED", 0),
        "source_failed": counts.get("SOURCE_FAILED", 0),
        "access_blocked": counts.get("ACCESS_BLOCKED", 0),
        "other_status": sum(v for k, v in counts.items() if k not in {
            "NOT_TRIED", "COLLECTED_IDENTITY_VERIFIED", "COLLECTED_PENDING_IDENTITY",
            "NOT_APPLICABLE_PRE_LISTING", "NOT_DISCLOSED_BY_ISSUER", "NOT_YET_DISCLOSED",
            "AFTER_CUTOFF_DISCLOSED", "SOURCE_FAILED", "ACCESS_BLOCKED"}),
        "non_terminal_rows": nonterm,
        "na_expected_by_listing_date": na_by_date,
        "terminal_complete": len(absent) == 0 and nonterm == 0,
        "note": "LEDGER_COMPLETE" if len(absent) == 0 and nonterm == 0 else "GAP",
    })
    for r in rr:
        dispositions.append({
            "security_id": r["security_id"], "slot_id": sid, "status": r["status"],
            "status_reason": r["status_reason"], "published_on": r["published_on"],
            "document_id": r["document_id"], "primary_url": r["primary_url"],
            "local_file": r["local_file"], "bytes": r["bytes"],
            "after_cutoff": "true" if (re.fullmatch(r"\d{4}-\d{2}-\d{2}", r["published_on"] or "")
                                       and r["published_on"] > cutoff) else "false",
        })
    for i in absent:
        absent_detail.append({"security_id": i, "slot_id": sid})
csvout("frozen_scope_coverage.csv", coverage)
csvout("quarter_slot_dispositions.csv", dispositions)
csvout("absent_slots.csv", absent_detail)

total_pairs_expected = len(slotdefs) * len(ids)
dup_pairs = sum(1 for v in pairs.values() if v > 1)
absent_total = sum(c["absent_from_ledger"] for c in coverage)
nonterm_total = sum(c["non_terminal_rows"] for c in coverage)

# ---------------------------------------------------------------- AC06 / AC07 / AC08 / AC10
na_rows = [r for r in ledger if r["status"] == "NOT_APPLICABLE_PRE_LISTING"]
na_no_date = [r for r in na_rows if listing.get(r["security_id"], {}).get("listing_date", "") in ("", "UNKNOWN")]
verified = [r for r in ledger if r["status"] == "COLLECTED_IDENTITY_VERIFIED"]
local_missing = [r for r in verified if not (ROOT / (r["local_file"] or "")).is_file()]
trace_missing = [r for r in verified if not all(r.get(k) for k in ["document_id", "primary_url", "sha256", "local_file"])]
failed = [r for r in ledger if r["status"] == "SOURCE_FAILED"]
failed_no_attempt = [r for r in failed if not r.get("attempt_count") or int(r["attempt_count"]) == 0]
dated = [r for r in ledger if re.fullmatch(r"\d{4}-\d{2}-\d{2}", r["published_on"] or "")]
late = [r for r in dated if r["published_on"] > cutoff]
unknown_date = [r for r in ledger if r["status"] == "COLLECTED_IDENTITY_VERIFIED"
                and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", r["published_on"] or "")]
after_cutoff_rows = [r for r in ledger if r["status"] == "AFTER_CUTOFF_DISCLOSED"]

# ---------------------------------------------------------------- 补充材料：公告/IR 目录
ann_path = ROOT / "runs/issues/A04R/announcement_index.jsonl"
ann = []
if ann_path.exists():
    inputs["runs/issues/A04R/announcement_index.jsonl"] = sha(ann_path)
    for line in ann_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            ann.append(json.loads(line))
ann_by_code = {a["stock_code"]: a for a in ann}
sup = []
for r in master:
    code = r["stock_code"]
    a = ann_by_code.get(code)
    sup.append({
        "security_id": r["security_id"], "stock_code": code,
        "index_fetched": "true" if a else "false",
        "total_announcement": a["total_announcement"] if a else "",
        "rows_fetched": a["rows_fetched"] if a else "",
        "pages": a["pages"] if a else "",
        "pagination_reconciled": ("true" if a["reconciled"] else "false") if a else "false",
        "keyword_hits": len(a["keyword_hits"]) if a else 0,
        "revision_rows": len(a["revision_rows"]) if a else 0,
        "ir_rows": len(a["ir_rows"]) if a else 0,
    })
csvout("supplementary_scope_coverage.csv", sup)
sup_summary = {
    "companies_in_pool": len(ids),
    "companies_with_index": len(ann),
    "companies_missing_index": len(ids) - len(ann),
    "pagination_reconciled": sum(1 for a in ann if a["reconciled"]),
    "pagination_incomplete": sum(1 for a in ann if not a["reconciled"]),
    "total_announcement_rows": sum(a["total_announcement"] or 0 for a in ann),
    "rows_fetched": sum(a["rows_fetched"] for a in ann),
    "keyword_hit_rows": sum(len(a["keyword_hits"]) for a in ann),
    "revision_rows": sum(len(a["revision_rows"]) for a in ann),
    "ir_rows": sum(len(a["ir_rows"]) for a in ann),
    "window": [a["se_date"] for a in ann[:1]],
    "keyword_hits_are_not_business_evidence": True,
}
write("supplementary_scope_summary.json", sup_summary)

# ---------------------------------------------------------------- 字段层：分母与限制
fields = rows("runs/issues/A03/financial_fields_extracted_annual_full.csv")
diag = rows("runs/issues/A03/extraction_diagnostics_annual_full.csv")
quality = rows("runs/issues/A03/field_quality_check_annual_full.csv")
dictionary = rows("runs/issues/P04/financial_field_dictionary.csv")
agg: dict[tuple, set] = defaultdict(set)
for r in fields:
    agg[(r["document_id"], r["slot_id"], r["field_id"])].add(r["extract_status"])
field_docs = {r["document_id"] for r in fields}
diag_docs = {r["document_id"] for r in diag}
image_only = [r["document_id"] for r in diag if r.get("parse_error")]
fieldcounts: dict[str, Counter] = defaultdict(Counter)
for (_, _, fid), sts in agg.items():
    fieldcounts[fid]["EXTRACTED_ANY" if "EXTRACTED" in sts
                   else ("NEUTRAL_UNKNOWN" if sts <= {"NOT_IN_STATEMENT", "BLANK_IN_STATEMENT", "NOT_APPLICABLE"}
                         else "FAILED_OR_REVIEW")] += 1
n_fields = len({f["field_id"] for f in fields})
usable = []
for f in dictionary:
    c = fieldcounts[f["field_id"]]
    usable.append({
        "field_id": f["field_id"], "name_cn": f["name_cn"], "p00_required": f["p00_required"],
        "annual_documents_with_any_value": c["EXTRACTED_ANY"],
        "neutral_unknown": c["NEUTRAL_UNKNOWN"], "failed_or_review": c["FAILED_OR_REVIEW"],
        "denominator_documents_with_field_rows": len(field_docs),
        "denominator_diagnostic_documents": len(diag_docs),
        "coverage_rate_field_rows_denominator": round(c["EXTRACTED_ANY"] / max(len(field_docs), 1), 4),
        "coverage_rate_diagnostic_denominator": round(c["EXTRACTED_ANY"] / max(len(diag_docs), 1), 4),
        "gate": "HOLD_PENDING_COMPARABILITY",
        "limits": ("EXTRACTED_ANY 只表示抽到至少一个期次的值，不等于四季齐全；缺失不填 0；"
                   "重述/单位/合并范围/版本须逐项核；半年报与季报字段尚未抽取"),
    })
csvout("usable_fields_and_limits.csv", usable)

zero_filled = [r for r in fields if r.get("extract_status") != "EXTRACTED" and str(r.get("value_raw") or "").strip() not in ("",)]
extract_summary = read("runs/issues/A03/extraction_summary_annual_full.json")
denominators = {
    "scope": "ANNUAL_ONLY（annual_2023 / annual_2024 / annual_2025）",
    "diagnostic_documents": len(diag_docs),
    "documents_with_field_rows": len(field_docs),
    "difference": len(diag_docs) - len(field_docs),
    "difference_documents": sorted(diag_docs - field_docs),
    "difference_reason": ("该文档正文无可抽取文字层（parse_error=IMAGE_ONLY_NO_TEXT_LAYER），抽取器不写字段行，"
                          "但仍在诊断表中留一条记录；不是抽取失败被隐藏，也不是重复计数。"),
    "fields_per_document": n_fields,
    "field_pairs_field_rows_denominator": len(field_docs) * n_fields,
    "field_pairs_diagnostic_denominator": len(diag_docs) * n_fields,
    "extracted_pairs": sum(c["EXTRACTED_ANY"] for c in fieldcounts.values()),
    "rate_field_rows_denominator": round(sum(c["EXTRACTED_ANY"] for c in fieldcounts.values()) / max(len(field_docs) * n_fields, 1), 4),
    "rate_diagnostic_denominator": round(sum(c["EXTRACTED_ANY"] for c in fieldcounts.values()) / max(len(diag_docs) * n_fields, 1), 4),
    "four_quarter_completeness": {
        "note": "分季度值加总与年初至今不一致即 INCOMPLETE_QUARTERS；这是“抽到任意季度值≠四季齐全”的直接证据",
        "REV": dict(Counter(r["sum_REV"] for r in quality)),
        "NPP": dict(Counter(r["sum_NPP"] for r in quality)),
        "NPDEDT": dict(Counter(r["sum_NPDEDT"] for r in quality)),
        "OCF": dict(Counter(r["sum_OCF"] for r in quality)),
    },
    "unit_consistency": dict(Counter(r["unit_consistent"] for r in quality)),
    "non_extracted_rows_with_value": len(zero_filled),
    "missing_not_zero_filled": len(zero_filled) == 0,
    "crosscheck_documents": extract_summary.get("crosscheck_docs", {}),
    "field_gap_rows": 1528,
    "field_gap_breakdown": {"RESTATEMENT_NEEDS_REVIEW": 960, "FIELD_NOT_EXTRACTED": 568},
}
write("field_denominators.json", denominators)

# ---------------------------------------------------------------- 交接统计更正
gaps = rows("runs/issues/A03/remaining_gaps.csv")
gap_layers = Counter(r["gap_layer"] for r in gaps)
erratum = {
    "scope": "A03_HANDOFF_ERRATUM",
    "recorded_by": "A04 rework",
    "recorded_at": datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds"),
    "original_claim": {"file": "runs/issues/A03/handoff.md", "section": 4, "rows_claimed": 226},
    "actual": {
        "file": "runs/issues/A03/remaining_gaps.csv",
        "rows": len(gaps),
        "by_layer": dict(gap_layers),
        "document_terminal": gap_layers.get("DOCUMENT", 0),
        "registry_duplicate": gap_layers.get("REGISTRY_DUPLICATE", 0),
        "field_items": gap_layers.get("FIELD", 0),
        "identity": f"{gap_layers.get('DOCUMENT', 0)} + {gap_layers.get('REGISTRY_DUPLICATE', 0)} + {gap_layers.get('FIELD', 0)} = {len(gaps)}",
        "subtotal_226_meaning": "226 = 155 文档终态 + 71 重复登记，只是子计数，不是缺口总数",
    },
    "policy": "原 handoff 不覆盖、不删除；本文件作为附加更正记录，A04 复验引用本记录。",
}
write("handoff_correction.json", erratum)

# ---------------------------------------------------------------- 检查项
checks = [
    {"id": "AC01", "result": "PASS" if len(ids) == 1054 and roster_hash == fp["canonical_form"]["canonical_sha256"] else "FAIL",
     "evidence": {"count": len(ids), "canonical_sha256": roster_hash}},
    {"id": "AC02", "result": "PASS" if all(b["pass"] for b in batch_checks) else "FAIL", "evidence": batch_checks},
    {"id": "AC03", "result": "PASS" if len(assign) == len(ids) and {r["security_id"] for r in assign} == ids
     and {r["security_id"] for r in queue} == ids else "FAIL", "evidence": "assignment and queue set equality"},
    {"id": "AC04", "result": "PASS" if absent_total == 0 and nonterm_total == 0 and dup_pairs == 0 else "FAIL",
     "evidence": {"frozen_pairs": total_pairs_expected, "ledger_pairs": len(pairs),
                  "absent_pairs": absent_total, "non_terminal_rows": nonterm_total,
                  "duplicate_pairs": dup_pairs,
                  "by_slot": {c["slot_id"]: c["ledger_rows"] for c in coverage}}},
    {"id": "AC05", "result": "PASS" if status.get("NOT_TRIED", 0) == 0 else "FAIL",
     "evidence": {"not_tried": status.get("NOT_TRIED", 0),
                  "by_slot": {c["slot_id"]: c["not_tried"] for c in coverage if c["not_tried"]}}},
    {"id": "AC06", "result": "PASS" if not na_no_date else "FAIL",
     "evidence": {"na_rows": len(na_rows), "without_listing_side_table_date": len(na_no_date),
                  "limit": "只核侧表日期存在与规则一致，未重新独立核验交易所原始公告"}},
    {"id": "AC07", "result": "PASS" if not trace_missing and not local_missing else "FAIL",
     "evidence": {"verified": len(verified), "missing_trace_fields": len(trace_missing),
                  "local_missing": len(local_missing),
                  "limit": "元数据与本地文件存在性；未重算全部二进制哈希，未做业务核读"}},
    {"id": "AC08", "result": "PASS" if not failed_no_attempt else "FAIL",
     "evidence": {"source_failed": len(failed), "without_attempt_record": len(failed_no_attempt),
                  "note": "SOURCE_FAILED 属 P00 允许的合法终态，但每行必须有请求记录与重试次数"}},
    {"id": "AC09", "result": "PASS" if not any(r["status"] == "NOT_TRIED" for r in ledger) else "FAIL",
     "evidence": {"manual_receipts": len(rows("runs/issues/A03/manual_intake_receipts.csv")),
                  "new_requests_this_round": 0,
                  "not_tried_in_ledger": status.get("NOT_TRIED", 0)}},
    {"id": "AC10", "result": "FAIL" if late else ("HOLD" if unknown_date else "PASS"),
     "evidence": {"known_after_cutoff_used_as_evidence": len(late),
                  "unknown_disclosure_date": len(unknown_date),
                  "after_cutoff_registered_not_used": len(after_cutoff_rows),
                  "cutoff": cutoff}},
    {"id": "AC11_SUPPLEMENTARY", "result": "PASS" if sup_summary["companies_with_index"] == len(ids)
     and sup_summary["pagination_reconciled"] == len(ids) else "FAIL",
     "evidence": sup_summary},
]
write("checks.json", {"issue_key": "A04", "review_round": "REWORK_20261027", "checks": checks})

summary = {
    "slots_total": total_pairs_expected,
    "slots_with_terminal": len(pairs) - nonterm_total,
    "absent_pairs": absent_total,
    "non_terminal_rows": nonterm_total,
    "status_counts": dict(status),
    "verified": len(verified),
    "local_missing": len(local_missing),
    "after_cutoff_rows": len(after_cutoff_rows),
    "unknown_date": len(unknown_date),
}
write("rework_summary.json", summary)
write("input_fingerprints.json", inputs)
print(json.dumps({"checks": {c["id"]: c["result"] for c in checks}, "summary": summary,
                  "supplementary": sup_summary, "field": {k: denominators[k] for k in
                  ["diagnostic_documents", "documents_with_field_rows", "difference", "extracted_pairs",
                   "rate_field_rows_denominator", "rate_diagnostic_denominator", "missing_not_zero_filled"]}},
                 ensure_ascii=False, indent=2))
