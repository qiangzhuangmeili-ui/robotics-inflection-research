#!/usr/bin/env python3
"""P01 dry-run：把现有 document_registry.csv 按新身份规则跑一遍，输出迁移后长什么样。

只读 data/document_registry.csv，不修改任何原表；输出写到 runs/issues/P01/。
本脚本是 P01 的审计证据，不是迁移执行器——真正落列由 P02 或专门卡按
registry_migration_plan.md 执行。

用法：python tools/p01_registry_dryrun.py
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "document_registry.csv"
OUT = ROOT / "runs" / "issues" / "P01"

OFFICIAL_HOSTS = ("cninfo.com.cn", "sse.com.cn", "szse.cn", "bse.cn", "neeq.com.cn")

# ---------------------------------------------------------------- 枚举与映射
# 文档类型：标题模式推断。顺序敏感——摘要必须先于年度报告。
TITLE_RULES = [
    (r"投资者关系活动记录表|投资者关系活动记录", "INVESTOR_RELATIONS_ARTICLE"),
    (r"可持续发展报告|社会责任报告|ESG报告", "SUSTAINABILITY_REPORT"),
    (r"上市公告书|上市公告", "LISTING_DISCLOSURE"),
    (r"年度报告摘要", "ANNUAL_REPORT_SUMMARY"),
    (r"半年度报告摘要", "SEMI_ANNUAL_REPORT_SUMMARY"),
    (r"年度报告", "ANNUAL_REPORT"),
    (r"半年度报告|中期报告", "SEMI_ANNUAL_REPORT"),
    (r"第[一三]季度报告|季度报告", "QUARTERLY_REPORT"),
    (r"招股说明书|招股意向书", "PROSPECTUS"),
    (r"更正|补充公告|勘误", "CORRECTION_NOTICE"),
    (r"股东大会|股东会", "SHAREHOLDER_MEETING_MATERIAL"),
    (r"中标|招标|采购公告", "TENDER_NOTICE"),
    (r"合同|签约|框架协议", "CONTRACT_ANNOUNCEMENT"),
]

# source_type 拆成两件事：这是什么（document_type 兜底）+ 怎么拿到的（acquisition_channel）
SOURCE_TYPE_MAP = {
    "LOCAL_PDF_PENDING_SOURCE_CHECK": ("UNKNOWN", "LOCAL_PDF_UNVERIFIED_SOURCE"),
    "USER_UPLOADED_ANNUAL_REPORT": ("ANNUAL_REPORT", "USER_UPLOAD"),
    "USER_UPLOADED_ANNUAL_REPORT_OFFICIAL_FULL_REPORT_URL_PENDING": ("ANNUAL_REPORT", "USER_UPLOAD"),
    "USER_UPLOADED_ANNUAL_REPORT_ORIGIN_PENDING_OFFICIAL_NEEQ_PDF": ("ANNUAL_REPORT", "USER_UPLOAD"),
    "OFFICIAL_CNINFO_FULL_PDF_WEB_READ": ("UNKNOWN", "OFFICIAL_CNINFO"),
    "OFFICIAL_CNINFO_URL_PLUS_FULL_PDF_MIRROR_READ": ("UNKNOWN", "OFFICIAL_CNINFO_PLUS_MIRROR"),
    "OFFICIAL_CNINFO_PROSPECTUS_PDF_WEB_READ_NOT_DRIVE_ARCHIVED": ("PROSPECTUS", "OFFICIAL_CNINFO"),
    "OFFICIAL_CNINFO_CONTRACT_ANNOUNCEMENT": ("CONTRACT_ANNOUNCEMENT", "OFFICIAL_CNINFO"),
    "OFFICIAL_SSE_URL_PLUS_FULL_PDF_MIRROR_READ": ("UNKNOWN", "OFFICIAL_SSE_PLUS_MIRROR"),
    "OFFICIAL_SSE_SHAREHOLDER_MEETING_MATERIALS": ("SHAREHOLDER_MEETING_MATERIAL", "OFFICIAL_SSE"),
    "OFFICIAL_BSE_HALF_YEAR_REPORT": ("SEMI_ANNUAL_REPORT", "OFFICIAL_BSE"),
    "OFFICIAL_BSE_LISTING_DISCLOSURE_URL": ("LISTING_DISCLOSURE", "OFFICIAL_BSE"),
    "OFFICIAL_BSE_ANNUAL_REPORT_SUMMARY_SEARCH_RESULT_ONLY": ("ANNUAL_REPORT_SUMMARY", "OFFICIAL_BSE"),
    "OFFICIAL_SOURCE_PORTAL_PLUS_DRIVE_PDF_TEXT_READ": ("UNKNOWN", "OFFICIAL_PORTAL_PLUS_DRIVE"),
    "OFFICIAL_COMPANY_WEBSITE_ARTICLE": ("OFFICIAL_WEBSITE_ARTICLE", "OFFICIAL_COMPANY_SITE"),
    "TENDER_CANDIDATE_NOTICE": ("TENDER_NOTICE", "THIRD_PARTY_TENDER_PLATFORM"),
    "COMPANY_ANNOUNCEMENT_TRANSCRIPT_SECONDARY": ("CONTRACT_ANNOUNCEMENT", "SECONDARY_TRANSCRIPT"),
}

# 报告期自由文本 → 受控 period_key
PERIOD_MAP = {
    "2025年度": "FY2025",
    "2026H1": "2026H1",
    "2026半年度": "2026H1",
    "2025年度报告摘要": "FY2025",
    "2023-2025审计财务数据": "MULTI_PERIOD_FY2023_FY2025",
    "2026年度": "PERIOD_UNRESOLVED",
    "2026年度_投资者关系": "NOT_APPLICABLE_EVENT_BASED",
    "2025年度_投资者关系": "NOT_APPLICABLE_EVENT_BASED",
    "2026年度_上市前材料": "PRE_LISTING_MATERIALS",
    "2026年上市披露": "LISTING_YEAR_2026",
    "2026年年度股东会材料": "AGM_2026",
}

# file_status（复合值）→ 五轴基线。file_status 是信息最全的字段，作为主轴来源。
FILE_STATUS_MAP = {
    "DRIVE_FILE_PRESENT_METADATA_ONLY": dict(
        link="FROM_SOURCE_TYPE", binary="OBTAINED", archive="UPLOADED_UNVERIFIED",
        access="NOT_CHECKED", evidence="NOT_USED"),
    "DRIVE_BINARY_READ_SHA256_CALCULATED_KEY_PAGE_VISUALLY_CHECKED": dict(
        link="FROM_SOURCE_TYPE", binary="OBTAINED", archive="VERIFIED",
        access="AI_READ_CONFIRMED", evidence="SELF_CHECK_ONLY"),
    "DRIVE_BINARY_DOWNLOADED_AND_PDF_PAGE_CHECKED": dict(
        link="FROM_SOURCE_TYPE", binary="OBTAINED", archive="UPLOADED_UNVERIFIED",
        access="AI_READ_CONFIRMED", evidence="NOT_USED"),
    "WEB_PAGE_READ_NOT_ARCHIVED": dict(
        link="FROM_SOURCE_TYPE", binary="NOT_ATTEMPTED", archive="NOT_UPLOADED",
        access="NOT_CHECKED", evidence="NOT_USED"),
    "DRIVE_BINARY_READ_SHA256_CALCULATED_KEY_PAGES_VISUALLY_CHECKED_SOURCE_PROVENANCE_PENDING": dict(
        link="NOT_RECORDED", binary="OBTAINED", archive="VERIFIED",
        access="AI_READ_CONFIRMED", evidence="SELF_CHECK_ONLY"),
    "DRIVE_BINARY_READ_SHA256_CALCULATED_KEY_PAGE_VISUALLY_CHECKED_SOURCE_PROVENANCE_PENDING": dict(
        link="NOT_RECORDED", binary="OBTAINED", archive="VERIFIED",
        access="AI_READ_CONFIRMED", evidence="SELF_CHECK_ONLY"),
    "OFFICIAL_WEB_PAGE_READ": dict(
        link="FROM_SOURCE_TYPE", binary="NOT_ATTEMPTED", archive="NOT_UPLOADED",
        access="NOT_CHECKED", evidence="NOT_USED"),
    "SOURCE_IDENTITY_CORRECTED_REFERENCE_ONLY": dict(
        link="FROM_SOURCE_TYPE", binary="NOT_ATTEMPTED", archive="NOT_REQUIRED_REFERENCE_ONLY",
        access="IDENTITY_MISMATCH", evidence="NOT_USED"),
    "DRIVE_PDF_UPLOADED_TEXT_EXTRACTED": dict(
        link="NOT_RECORDED", binary="OBTAINED", archive="UPLOADED_UNVERIFIED",
        access="AI_TEXT_EXTRACTED_UNVERIFIED", evidence="NOT_USED"),
    "OFFICIAL_BSE_URL_FOUND_DRIVE_PDF_TEXT_EXTRACTED": dict(
        link="FROM_SOURCE_TYPE", binary="OBTAINED", archive="UPLOADED_UNVERIFIED",
        access="AI_TEXT_EXTRACTED_UNVERIFIED", evidence="NOT_USED"),
    "DRIVE_PDF_UPLOADED_TEXT_EXTRACTED_OFFICIAL_URL_PENDING": dict(
        link="NOT_RECORDED", binary="OBTAINED", archive="UPLOADED_UNVERIFIED",
        access="AI_TEXT_EXTRACTED_UNVERIFIED", evidence="NOT_USED"),
    "OFFICIAL_PDF_WEB_FULL_TEXT_READ_RAW_DOWNLOAD_FAILED": dict(
        link="FROM_SOURCE_TYPE", binary="FAILED", archive="NOT_UPLOADED",
        access="NOT_CHECKED", evidence="NOT_USED"),
    "OFFICIAL_SEARCH_RESULT_FOUND_OPEN_FAILED_REDIRECT_LOOP": dict(
        link="FROM_SOURCE_TYPE", binary="FAILED", archive="NOT_UPLOADED",
        access="NOT_CHECKED", evidence="NOT_USED"),
    "SECONDARY_TRANSCRIPT_READ_ORIGINAL_PDF_URL_PENDING": dict(
        link="FOUND_SECONDARY", binary="NOT_ATTEMPTED", archive="NOT_UPLOADED",
        access="NOT_CHECKED", evidence="NOT_USED"),
}

# 规则外自造值 → 规范值（原文保留在 *_legacy）
ARCHIVE_NORMALIZE = {
    "L1_SOURCE_INDEX_ONLY": "NOT_UPLOADED",
    "UPLOADED_AND_TEXT_READ": "UPLOADED_UNVERIFIED",
}
ARCHIVE_LEGAL = {"NOT_UPLOADED", "UPLOADED_UNVERIFIED", "VERIFIED",
                 "NOT_REQUIRED_REFERENCE_ONLY", "SOURCE_UNAVAILABLE"}

ACCESS_MAP = {
    "NOT_CHECKED": "NOT_CHECKED",
    "OWNER_ONLY_CHECKED": "OWNER_ONLY_CHECKED",
    "AI_READ_CONFIRMED": "AI_READ_CONFIRMED",
    "ACCESS_BLOCKED": "ACCESS_BLOCKED",
    "DRIVE_TEXT_EXTRACTION_OK": "AI_TEXT_EXTRACTED_UNVERIFIED",
    "WEB_PAGE_READ_NOT_DRIVE_ARCHIVED": "NOT_CHECKED",
    "OFFICIAL_PAGE_WEB_VERIFIED": "NOT_CHECKED",
    "WEB_TEXT_READ_IDENTITY_CORRECTED": "IDENTITY_MISMATCH",
}
# 《资料保存分级规则 v1.1》定义的四个合法值；其余均为自造值，须标记待归一
ACCESS_LEGAL = {"NOT_CHECKED", "OWNER_ONLY_CHECKED", "AI_READ_CONFIRMED", "ACCESS_BLOCKED"}

# source_type 隐含的链接状态
LINK_FROM_SOURCE = {
    "OFFICIAL_CNINFO": "FOUND_OFFICIAL",
    "OFFICIAL_CNINFO_PLUS_MIRROR": "FOUND_OFFICIAL",
    "OFFICIAL_SSE_PLUS_MIRROR": "FOUND_OFFICIAL",
    "OFFICIAL_SSE": "FOUND_OFFICIAL",
    "OFFICIAL_BSE": "FOUND_OFFICIAL",
    "OFFICIAL_PORTAL_PLUS_DRIVE": "FOUND_OFFICIAL",
    "OFFICIAL_COMPANY_SITE": "FOUND_SECONDARY",
    "THIRD_PARTY_TENDER_PLATFORM": "FOUND_SECONDARY",
    "SECONDARY_TRANSCRIPT": "FOUND_SECONDARY",
    "USER_UPLOAD": "NOT_RECORDED",
    "LOCAL_PDF_UNVERIFIED_SOURCE": "NOT_RECORDED",
}


def classify_id(doc_id: str, sha: str) -> str:
    if sha and doc_id == "DOC-" + sha[:16].upper():
        return "SHA16"
    if re.match(r"^DOC-\d{4}AR-\d{6}$", doc_id):
        return "LEGACY_SEMANTIC_AR"
    if re.match(r"^DOC-C00-\d{4}-", doc_id):
        return "LEGACY_SEMANTIC_C00"
    if re.match(r"^DOC-\d{4}H\d-\d{6}$", doc_id):
        return "LEGACY_SEMANTIC_H1"
    return "LEGACY_SEMANTIC_ADHOC"


def doc_type_from_title(title: str) -> str | None:
    for pattern, dtype in TITLE_RULES:
        if re.search(pattern, title):
            return dtype
    return None


def link_from_url(url: str) -> str | None:
    if not url or url == "UNKNOWN":
        return None
    host = re.sub(r"^https?://", "", url).split("/")[0].lower()
    return "FOUND_OFFICIAL" if any(h in host for h in OFFICIAL_HOSTS) else "FOUND_SECONDARY"


def next_action(axes: dict, unknowns: list[str], period_key: str) -> str:
    steps = []
    if axes["link"] in ("NOT_RECORDED", "NOT_SEARCHED"):
        steps.append("RECOVER_OFFICIAL_URL")
    if axes["binary"] in ("FAILED", "NOT_ATTEMPTED"):
        steps.append("FETCH_BINARY")
    if axes["archive"] == "NOT_UPLOADED" and axes["binary"] == "OBTAINED":
        steps.append("UPLOAD_TO_DRIVE")
    if axes["access"] in ("NOT_CHECKED", "AI_TEXT_EXTRACTED_UNVERIFIED") and axes["archive"] != "NOT_UPLOADED":
        steps.append("VERIFY_IDENTITY_AND_PAGES")
    if "sha256" in unknowns and axes["binary"] == "OBTAINED":
        steps.append("COMPUTE_SHA256")
    if "published_on" in unknowns:
        steps.append("RESOLVE_PUBLISHED_ON")
    if period_key == "PERIOD_UNRESOLVED":
        steps.append("RESOLVE_PERIOD")
    return ";".join(steps) if steps else "NONE"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with SRC.open("r", encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))

    out_rows = []
    unmapped: dict[str, set] = defaultdict(set)

    for r in rows:
        sha = r["sha256"].strip()
        st = r["source_type"]
        fs = r["file_status"]
        ac = r["access_check_status"]
        flags: list[str] = []

        if st not in SOURCE_TYPE_MAP:
            unmapped["source_type"].add(st)
        if fs not in FILE_STATUS_MAP:
            unmapped["file_status"].add(fs)
        if ac not in ACCESS_MAP:
            unmapped["access_check_status"].add(ac)
        if r["period_covered"] not in PERIOD_MAP:
            unmapped["period_covered"].add(r["period_covered"])

        base_type, channel = SOURCE_TYPE_MAP.get(st, ("UNKNOWN", "UNKNOWN"))
        title_type = doc_type_from_title(r["original_title"])
        if base_type == "UNKNOWN" and title_type:
            doc_type, type_source = title_type, "TITLE_PATTERN"
        elif base_type != "UNKNOWN":
            doc_type, type_source = base_type, "SOURCE_TYPE"
        else:
            doc_type, type_source = "UNKNOWN", "UNKNOWN"

        period_key = PERIOD_MAP.get(r["period_covered"], "PERIOD_UNRESOLVED")

        axes = dict(FILE_STATUS_MAP.get(fs, dict(
            link="NOT_SEARCHED", binary="NOT_ATTEMPTED", archive="NOT_UPLOADED",
            access="NOT_CHECKED", evidence="NOT_USED")))

        url_link = link_from_url(r["primary_url"])
        if axes["link"] == "FROM_SOURCE_TYPE":
            axes["link"] = url_link or LINK_FROM_SOURCE.get(channel, "NOT_RECORDED")
        elif url_link == "FOUND_OFFICIAL" and axes["link"] == "NOT_RECORDED":
            axes["link"] = "FOUND_OFFICIAL"

        raw_archive = r["archive_status"]
        archive_norm = ARCHIVE_NORMALIZE.get(raw_archive, raw_archive)
        if raw_archive not in ARCHIVE_LEGAL:
            flags.append("ARCHIVE_STATUS_NONSTANDARD")
        # 冲突不自动取舍：保留旧值（已归一），标记待人工复核，避免静默升降级
        if archive_norm != axes["archive"]:
            flags.append("ARCHIVE_AXIS_CONFLICT")

        access_norm = ACCESS_MAP.get(ac, "NOT_CHECKED")
        if ac not in ACCESS_LEGAL:
            flags.append("ACCESS_STATUS_NONSTANDARD")
        if axes["access"] != access_norm:
            flags.append("ACCESS_AXIS_CONFLICT")

        unknowns = []
        if not r["published_on"].strip() or r["published_on"] == "UNKNOWN":
            unknowns.append("published_on")
        if not r["primary_url"].strip() or r["primary_url"] == "UNKNOWN":
            unknowns.append("primary_url")
        if not sha:
            unknowns.append("sha256")
        if not r["page_count"].strip():
            unknowns.append("page_count")
        if not r["collected_on"].strip():
            unknowns.append("collected_on")

        if classify_id(r["document_id"], sha) != "SHA16":
            flags.append("LEGACY_DOCUMENT_ID_KEPT")
        if not sha:
            flags.append("CONTENT_HASH_MISSING")
        if period_key != r["period_covered"]:
            flags.append("PERIOD_KEY_NORMALIZED")
        if period_key == "PERIOD_UNRESOLVED":
            flags.append("PERIOD_AMBIGUOUS")
        if doc_type == "UNKNOWN":
            flags.append("DOCUMENT_TYPE_UNRESOLVED")
        if r["storage_provider"] in ("WEB_SOURCE", "EXTERNAL_SOURCE_ONLY",
                                     "EXTERNAL_SOURCE_REFERENCE_ONLY", "WEB_REFERENCE"):
            flags.append("NOT_A_STORED_BINARY")
        if not flags:
            flags.append("CLEAN")

        out_rows.append({
            "document_id": r["document_id"],
            "id_scheme": classify_id(r["document_id"], sha),
            "stock_code": r["stock_code"],
            "stock_name": r["stock_name"],
            "original_title": r["original_title"],
            "old_source_type": st,
            "new_document_type": doc_type,
            "new_document_type_source": type_source,
            "new_acquisition_channel": channel,
            "old_period_covered": r["period_covered"],
            "new_period_key": period_key,
            "old_file_status": fs,
            "new_link_status": axes["link"],
            "new_binary_status": axes["binary"],
            "old_archive_status": raw_archive,
            "new_archive_status": archive_norm,
            "old_access_check_status": ac,
            "new_access_identity_status": access_norm,
            "new_evidence_status": axes["evidence"],
            "new_revision_no": 0,
            "new_issuer_scope": "UNKNOWN",
            "new_unknown_fields": ";".join(unknowns),
            "new_next_action": next_action(axes, unknowns, period_key),
            "migration_flags": ";".join(flags),
        })

    fieldnames = list(out_rows[0].keys())
    with (OUT / "migration_dryrun.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(out_rows)

    def dist(key: str) -> dict:
        return dict(sorted(Counter(x[key] for x in out_rows).items(), key=lambda kv: -kv[1]))

    all_flags = Counter()
    for x in out_rows:
        for f in x["migration_flags"].split(";"):
            all_flags[f] += 1

    checks = [
        {"check": "row_count_unchanged", "expected": 100, "actual": len(out_rows),
         "pass": len(out_rows) == 100},
        {"check": "document_id_all_preserved",
         "expected": "100/100 原值不变",
         "actual": sum(1 for a, b in zip(rows, out_rows) if a["document_id"] == b["document_id"]),
         "pass": all(a["document_id"] == b["document_id"] for a, b in zip(rows, out_rows))},
        {"check": "no_unmapped_enum_values", "expected": 0,
         "actual": {k: sorted(v) for k, v in unmapped.items()},
         "pass": not any(unmapped.values())},
        {"check": "archive_status_after_normalization_all_legal",
         "expected": sorted(ARCHIVE_LEGAL),
         "actual": sorted(set(x["new_archive_status"] for x in out_rows)),
         "pass": set(x["new_archive_status"] for x in out_rows) <= ARCHIVE_LEGAL},
        {"check": "evidence_status_never_upgraded_to_independent",
         "expected": "无 VERIFIED_INDEPENDENT（本库从未做过独立验收）",
         "actual": sorted(set(x["new_evidence_status"] for x in out_rows)),
         "pass": "VERIFIED_INDEPENDENT" not in set(x["new_evidence_status"] for x in out_rows)},
        {"check": "no_row_silently_dropped",
         "expected": "每行都有 migration_flags",
         "actual": sum(1 for x in out_rows if x["migration_flags"]),
         "pass": all(x["migration_flags"] for x in out_rows)},
    ]

    summary = {
        "generated_at_utc": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc).isoformat(timespec="seconds"),
        "source": {"path": "data/document_registry.csv",
                   "sha256": hashlib.sha256(SRC.read_bytes()).hexdigest(),
                   "rows": len(rows), "columns": len(rows[0])},
        "dryrun_scope": "只读原表；未修改 data/document_registry.csv；输出为迁移后的建议值。",
        "distributions": {
            "id_scheme": dist("id_scheme"),
            "new_document_type": dist("new_document_type"),
            "new_document_type_source": dist("new_document_type_source"),
            "new_acquisition_channel": dist("new_acquisition_channel"),
            "new_period_key": dist("new_period_key"),
            "new_link_status": dist("new_link_status"),
            "new_binary_status": dist("new_binary_status"),
            "new_archive_status": dist("new_archive_status"),
            "new_access_identity_status": dist("new_access_identity_status"),
            "new_evidence_status": dist("new_evidence_status"),
            "migration_flags": dict(sorted(all_flags.items(), key=lambda kv: -kv[1])),
        },
        "checks": checks,
        "all_checks_pass": all(c["pass"] for c in checks),
    }
    (OUT / "migration_dryrun_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({
        "all_checks_pass": summary["all_checks_pass"],
        "failed_checks": [c["check"] for c in checks if not c["pass"]],
        "rows": len(out_rows),
        "id_scheme": summary["distributions"]["id_scheme"],
        "flags": summary["distributions"]["migration_flags"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
