#!/usr/bin/env python3
"""Independent, read-only structure check for the research plan. Writes only validation/independent_check.json."""
from __future__ import annotations
import csv
import hashlib
import json
import re
import sys
import zipfile
from urllib.parse import unquote
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "validation" / "independent_check.json"
checks = []


def check(name, passed, expected=None, actual=None, detail=None):
    item = {"name": name, "status": "PASS" if passed else "FAIL"}
    if expected is not None:
        item["expected"] = expected
    if actual is not None:
        item["actual"] = actual
    if detail is not None:
        item["detail"] = detail
    checks.append(item)


def read_csv(rel):
    path = ROOT / rel
    if not path.is_file():
        check(f"file_exists:{rel}", False, True, False)
        return [], []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames or []
        rows = list(reader)
    malformed = [i + 2 for i, row in enumerate(rows) if None in row]
    check(f"csv_parse:{rel}", not malformed, "consistent row widths", "inconsistent" if malformed else "consistent", {"rows": len(rows), "columns": len(fields), "malformed_lines": malformed[:20]})
    return fields, rows


def read_text(rel):
    path = ROOT / rel
    if not path.is_file():
        check(f"file_exists:{rel}", False, True, False)
        return ""
    return path.read_text(encoding="utf-8-sig")


def unique_values(rows, key):
    return {row.get(key, "") for row in rows}


# Core master table and disjoint starting partitions.
master_fields, master = read_csv("data/company_master.csv")
master_ids = [r.get("security_id", "") for r in master]
master_codes = [r.get("stock_code", "") for r in master]
master_by_id = {r.get("security_id", ""): r for r in master}
check("master_row_count", len(master) == 1054, 1054, len(master))
check("master_security_id_unique", len(set(master_ids)) == len(master_ids), len(master), len(set(master_ids)))
check("master_stock_code_unique", len(set(master_codes)) == len(master_codes), len(master), len(set(master_codes)))
invalid_codes = [c for c in master_codes if not re.fullmatch(r"\d{6}", c)]
invalid_security_ids = [r.get("security_id", "") for r in master if r.get("security_id", "") != f"{r.get('exchange', '')}:{r.get('stock_code', '')}"]
check("master_codes_six_digit_text", not invalid_codes, "all six digits", invalid_codes[:20])
check("master_security_key_matches_exchange_and_code", not invalid_security_ids, "exchange:stock_code", invalid_security_ids[:20])

partition_counts = Counter(r.get("initial_route_status", "") for r in master)
expected_partition_counts = {"REUSE_WITH_LIMITS": 53, "SOURCE_PENDING": 7, "SAMPLE_PARTIAL_REVIEW": 10, "NOT_SCREENED": 984}
check("1054_partition_counts", dict(partition_counts) == expected_partition_counts, expected_partition_counts, dict(partition_counts))
partition_sets = {status: {r["security_id"] for r in master if r.get("initial_route_status") == status} for status in expected_partition_counts}
partition_overlap = {}
keys = list(partition_sets)
for i, first in enumerate(keys):
    for second in keys[i + 1:]:
        overlap = partition_sets[first] & partition_sets[second]
        if overlap:
            partition_overlap[f"{first}|{second}"] = sorted(overlap)
partition_union = set().union(*partition_sets.values()) if partition_sets else set()
check("starting_partitions_disjoint", not partition_overlap, "no cross-partition duplicate", partition_overlap)
check("starting_partitions_cover_master", partition_union == set(master_ids), {"master_ids": len(master_ids)}, {"partition_ids": len(partition_union), "missing": sorted(set(master_ids) - partition_union)[:20], "extra": sorted(partition_union - set(master_ids))[:20]})

# Package index, paths, assignment sizes, primary and conditional overlap.
index_fields, index = read_csv("data/package_index.csv")
package_ids = [r.get("package_id", "") for r in index]
check("package_index_count", len(index) == 67, 67, len(index))
check("package_index_ids_unique", len(set(package_ids)) == len(package_ids), len(package_ids), len(set(package_ids)))
primary_index = [r for r in index if r.get("primary_partition") == "YES"]
conditional_index = [r for r in index if r.get("primary_partition") == "NO_NEXT_STAGE"]
check("primary_package_count", len(primary_index) == 58, 58, len(primary_index))
check("conditional_detail_package_count", len(conditional_index) == 9, 9, len(conditional_index))

all_assignments = {}
package_path_errors = []
assignment_count_errors = []
assignment_id_errors = []
package_task_cutoff_errors = []
for package in index:
    pid = package.get("package_id", "")
    assignment_rel = package.get("assignment_path", "")
    task_rel = f"packages/{pid}/TASK.md"
    if not assignment_rel or not (ROOT / assignment_rel).is_file():
        package_path_errors.append({"package_id": pid, "missing": assignment_rel or "assignment_path"})
        continue
    task_text = read_text(task_rel)
    if not task_text or "2026-10-24" not in task_text or "截止" not in task_text:
        package_task_cutoff_errors.append(pid)
    fields, rows = read_csv(assignment_rel)
    all_assignments[pid] = rows
    if len(rows) != int(package.get("count", "-1")):
        assignment_count_errors.append({"package_id": pid, "index_count": package.get("count"), "assignment_rows": len(rows)})
    ids = [r.get("security_id", "") for r in rows]
    if len(ids) != len(set(ids)):
        assignment_id_errors.append({"package_id": pid, "rows": len(ids), "unique": len(set(ids))})
    for row in rows:
        if row.get("package_id") != pid:
            assignment_id_errors.append({"package_id": pid, "row_package_id": row.get("package_id"), "security_id": row.get("security_id")})
        if not re.fullmatch(r"\d{6}", row.get("stock_code", "")):
            assignment_id_errors.append({"package_id": pid, "invalid_stock_code": row.get("stock_code")})
        if row.get("security_id") != f"{row.get('exchange', '')}:{row.get('stock_code', '')}":
            assignment_id_errors.append({"package_id": pid, "invalid_security_id": row.get("security_id")})
check("package_assignment_and_task_paths", not package_path_errors, "all 67 assignment.csv and TASK.md exist", len(package_path_errors) == 0, package_path_errors[:20])
check("package_task_cutoff", not package_task_cutoff_errors, "2026-10-24 in every TASK.md", package_task_cutoff_errors[:20])
check("package_assignment_counts_match_index", not assignment_count_errors, "each count matches assignment row count", assignment_count_errors[:20])
check("package_assignment_ids_and_codes", not assignment_id_errors, "unique keys and six-digit codes", assignment_id_errors[:20])

primary_rows = [(r, pid) for pid, rows in all_assignments.items() for r in rows if next((p.get("primary_partition") for p in index if p.get("package_id") == pid), "") == "YES"]
primary_ids = [r.get("security_id", "") for r, _ in primary_rows]
primary_duplicates = [key for key, count in Counter(primary_ids).items() if count > 1]
primary_id_set = set(primary_ids)
check("primary_packages_cover_master_once", primary_id_set == set(master_ids) and not primary_duplicates, {"companies": 1054, "duplicates": 0}, {"companies": len(primary_ids), "unique": len(primary_id_set), "duplicate_ids": primary_duplicates[:20], "missing": sorted(set(master_ids) - primary_id_set)[:20], "extra": sorted(primary_id_set - set(master_ids))[:20]})
primary_assignment_mismatch = [{"security_id": r.get("security_id"), "assignment_package": pid, "master_package": master_by_id.get(r.get("security_id"), {}).get("primary_package_id")} for r, pid in primary_rows if master_by_id.get(r.get("security_id"), {}).get("primary_package_id") != pid]
check("master_primary_package_matches_assignment", not primary_assignment_mismatch, "same package per company", primary_assignment_mismatch[:20])

# 10-company calibration and remaining 974 broad-screen assignments.
calibration = all_assignments.get("C00_PILOT_01", [])
coarse_packages = [r for r in index if r.get("package_id", "").startswith("C") and r.get("package_id") != "C00_PILOT_01"]
coarse_rows = [row for pkg in coarse_packages for row in all_assignments.get(pkg.get("package_id", ""), [])]
check("calibration_package_has_10", len(calibration) == 10, 10, len(calibration))
check("remaining_coarse_has_974", len(coarse_rows) == 974, 974, len(coarse_rows))
check("pilot_and_remaining_coarse_partition_984", set(r["security_id"] for r in calibration + coarse_rows) == partition_sets.get("NOT_SCREENED", set()) and len(calibration) + len(coarse_rows) == 984, {"total": 984, "pilot": 10, "remaining": 974}, {"total": len(calibration) + len(coarse_rows), "pilot": len(calibration), "remaining": len(coarse_rows)})

# Historical references and the 45-of-53 conditional detail list (8 remain reserve).
b02 = all_assignments.get("B02_REUSE_REFERENCE", [])
b02_ids = {r.get("security_id", "") for r in b02}
detail_index_ids = {r.get("package_id", "") for r in conditional_index}
detail_rows = [row for pid in detail_index_ids for row in all_assignments.get(pid, [])]
detail_ids = {r.get("security_id", "") for r in detail_rows}
reserve_ids = b02_ids - detail_ids
check("adopted_reference_package_53", len(b02) == 53 and b02_ids == partition_sets.get("REUSE_WITH_LIMITS", set()), {"rows": 53, "same_as_partition": True}, {"rows": len(b02), "same_as_partition": b02_ids == partition_sets.get("REUSE_WITH_LIMITS", set())})
check("conditional_detail_45_and_reserve_8", len(detail_index_ids) == 9 and len(detail_rows) == 45 and len(detail_ids) == 45 and detail_ids <= b02_ids and len(reserve_ids) == 8, {"packages": 9, "detail_candidates": 45, "reserve": 8, "overlap_source": "B02_REUSE_REFERENCE"}, {"packages": len(detail_index_ids), "detail_rows": len(detail_rows), "detail_unique": len(detail_ids), "overlap_with_B02": len(detail_ids & b02_ids), "reserve": len(reserve_ids), "reserve_codes": sorted(r["stock_code"] for r in b02 if r.get("security_id") in reserve_ids)})
required_overlap_fields = {"primary_partition", "predecessor_package_id", "next_stage_overlap_id"}
overlap_errors = []
for row in detail_rows:
    security_id = row.get("security_id", "")
    expected_overlap = f"{security_id}@B02_REUSE_REFERENCE"
    if row.get("primary_partition") != "NO_NEXT_STAGE" or row.get("predecessor_package_id") != "B02_REUSE_REFERENCE" or row.get("next_stage_overlap_id") != expected_overlap or security_id not in b02_ids:
        overlap_errors.append({"security_id": security_id, "primary_partition": row.get("primary_partition"), "predecessor_package_id": row.get("predecessor_package_id"), "next_stage_overlap_id": row.get("next_stage_overlap_id"), "expected_overlap_id": expected_overlap})
detail_assignment_fields = set(detail_rows[0]) if detail_rows else set()
missing_overlap_fields = sorted(required_overlap_fields - detail_assignment_fields)
check("conditional_assignment_overlap_identifiers", not overlap_errors and not missing_overlap_fields and len(detail_rows) == 45, {"fields": sorted(required_overlap_fields), "identifier_format": "security_id@B02_REUSE_REFERENCE", "rows": 45}, {"missing_index_fields": missing_overlap_fields, "error_count": len(overlap_errors), "errors": overlap_errors[:10]})

# Source-pending and early partial-sample sets remain separate and match the archived records.
source_assignments = all_assignments.get("B00_SOURCE_01", []) + all_assignments.get("B00_SOURCE_02", [])
sample_assignments = all_assignments.get("B01_SAMPLE_01", []) + all_assignments.get("B01_SAMPLE_02", [])
source_ids = {r.get("security_id", "") for r in source_assignments}
sample_ids = {r.get("security_id", "") for r in sample_assignments}
source_overlap_errors = []
for row in source_assignments:
    if row.get("initial_route_status", "SOURCE_PENDING") not in ("", "SOURCE_PENDING"):
        source_overlap_errors.append(row.get("security_id"))
check("source_pending_seven", len(source_ids) == 7 and source_ids == partition_sets.get("SOURCE_PENDING", set()) and not source_overlap_errors, {"companies": 7}, {"companies": len(source_ids), "matches_partition": source_ids == partition_sets.get("SOURCE_PENDING", set())})
check("early_samples_ten_separate", len(sample_ids) == 10 and sample_ids == partition_sets.get("SAMPLE_PARTIAL_REVIEW", set()) and not (sample_ids & b02_ids), {"companies": 10, "disjoint_from_adopted": True}, {"companies": len(sample_ids), "matches_partition": sample_ids == partition_sets.get("SAMPLE_PARTIAL_REVIEW", set()), "overlap_with_adopted": len(sample_ids & b02_ids)})

# Group counts must be computed from master, not copied from the summary file.
group_fields, group_rows = read_csv("data/group_summary.csv")
group_actual = defaultdict(lambda: {"total_count": 0, "new_screening_count": 0})
for row in master:
    group = row.get("routing_group", "")
    group_actual[group]["total_count"] += 1
    if row.get("initial_route_status") == "NOT_SCREENED":
        group_actual[group]["new_screening_count"] += 1
group_expected = {r.get("group_id", ""): {"total_count": int(r.get("total_count", "-1")), "new_screening_count": int(r.get("new_screening_count", "-1"))} for r in group_rows}
group_mismatches = {g: {"declared": group_expected.get(g), "actual": values} for g, values in group_actual.items() if group_expected.get(g) != values}
check("group_summary_matches_master_rows", not group_mismatches and set(group_expected) == set(group_actual) and sum(v["total_count"] for v in group_actual.values()) == 1054 and sum(v["new_screening_count"] for v in group_actual.values()) == 984, {"groups": 10, "total": 1054, "new_screening": 984}, {"group_counts": dict(group_actual), "mismatches": group_mismatches})

# Dates and company-stage separation.
project_state = json.loads(read_text("PROJECT_STATE.json") or "{}")
check("research_cutoff_consistent", project_state.get("knowledge_as_of") == "2026-10-24" and all(r.get("research_as_of") == "2026-10-24" for r in master), "2026-10-24", {"project_state": project_state.get("knowledge_as_of"), "master_dates": dict(Counter(r.get("research_as_of", "") for r in master))})
new_stage_values = Counter(r.get("company_stage_for_new_workflow", "") for r in master)
check("new_company_stage_all_unknown", new_stage_values == Counter({"UNKNOWN": 1054}), {"UNKNOWN": 1054}, dict(new_stage_values))
archive_fields, legacy_rows = read_csv("archive/latest_universe.csv")
legacy_by_id = {r.get("security_id", ""): r for r in legacy_rows}
legacy_mismatches = [{"security_id": r.get("security_id"), "company": r.get("legacy_company_stage"), "archive": legacy_by_id.get(r.get("security_id"), {}).get("commercial_stage")} for r in master if r.get("legacy_company_stage") != legacy_by_id.get(r.get("security_id"), {}).get("commercial_stage")]
legacy_non_unknown = [{"stock_code": r.get("stock_code"), "stock_name": r.get("stock_name"), "legacy_stage": r.get("legacy_company_stage")} for r in master if r.get("legacy_company_stage") not in ("", "UNKNOWN")]
check("legacy_stage_matches_archive", not legacy_mismatches and len(legacy_non_unknown) == 6, {"all_match_archive": True, "non_unknown_legacy_rows": 6}, {"mismatches": legacy_mismatches[:20], "non_unknown_legacy_rows": legacy_non_unknown})
check("old_commercial_stage_not_used_as_new_stage", all(r.get("commercial_stage") == "UNKNOWN" for r in master), "commercial_stage all UNKNOWN; old values only in legacy_company_stage/archive", dict(Counter(r.get("commercial_stage", "") for r in master)))

# Financial data gaps: the gap register states missingness and contains no numeric financial fields.
gap_fields, gaps = read_csv("data/financial_gaps.csv")
gap_ids = {r.get("security_id", "") for r in gaps}
master_gap_ids = {r.get("security_id", "") for r in master if r.get("financial_gap") == "NO_LOCAL_FINANCIAL"}
gap_statuses = Counter(r.get("data_status", "") for r in gaps)
financial_amount_columns = [f for f in gap_fields if any(token in f.lower() for token in ("revenue_cny", "profit_cny", "cashflow_cny", "amount_cny", "financial_value"))]
zero_gaps = [{"security_id": r.get("security_id"), "fields": [f for f in financial_amount_columns if r.get(f) in ("0", "0.0", "0.00")]} for r in gaps if any(r.get(f) in ("0", "0.0", "0.00") for f in financial_amount_columns)]
check("financial_missing_62_not_zero_filled", len(gaps) == 62 and len(gap_ids) == 62 and gap_ids == master_gap_ids and gap_statuses == Counter({"FINANCIAL_DATA_MISSING": 62}) and not financial_amount_columns and not zero_gaps, {"missing_companies": 62, "matching_master": True, "status": "FINANCIAL_DATA_MISSING", "financial_amounts": "not recorded as zero"}, {"rows": len(gaps), "unique_ids": len(gap_ids), "matches_master": gap_ids == master_gap_ids, "statuses": dict(gap_statuses), "financial_amount_columns_in_gap_register": financial_amount_columns, "zero_filled_rows": zero_gaps})

# Resource-map SHA-256 checks against the full archived files; packaged cropped files are checked separately.
resource_fields, resources = read_csv("data/resource_map.csv")
hash_errors = []
missing_resource_paths = []
checked_hashes = 0
for row in resources:
    rel = row.get("repo_path", "")
    availability = row.get("availability", "")
    if availability == "COPIED":
        target = ROOT / rel
        if not rel or not target.is_file():
            missing_resource_paths.append(rel or row.get("resource_id", "(no path)"))
            continue
        expected_hash = row.get("sha256", "")
        if not re.fullmatch(r"[0-9a-fA-F]{64}", expected_hash):
            hash_errors.append({"resource_id": row.get("resource_id"), "path": rel, "issue": "invalid or missing SHA-256"})
            continue
        checked_hashes += 1
        actual_hash = hashlib.sha256(target.read_bytes()).hexdigest()
        if actual_hash.lower() != expected_hash.lower():
            hash_errors.append({"resource_id": row.get("resource_id"), "path": rel, "expected": expected_hash, "actual": actual_hash})
check("resource_map_hashes_match_full_archive_files", not missing_resource_paths and not hash_errors and checked_hashes > 0, "every COPIED row exists and matches SHA-256", {"copied_hashes_checked": checked_hashes, "mismatches": hash_errors, "missing_paths": missing_resource_paths})

# Our two user guides should point to paths that exist in this repository.
manual_rel_paths = ["data/company_master.csv", "data/package_index.csv", "data/manual_requests.csv", "inbox", "sources", "templates/来源登记.csv", "archive/toolbox_guide.md", "packages"]
manual_path_errors = [rel for rel in manual_rel_paths if not (ROOT / rel).exists()]
markdown_link_errors = []
link_pattern = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
for rel in ("docs/新手执行手册.md", "docs/手动补资料指南.md"):
    text = read_text(rel)
    for target in link_pattern.findall(text):
        target = unquote(target.split("#", 1)[0])
        if not target or re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://", target) or target.startswith("mailto:"):
            continue
        if "<" in target or ">" in target:
            continue
        if not (ROOT / Path(rel).parent / target).exists():
            markdown_link_errors.append({"document": rel, "target": target})
check("manual_paths_resolve_inside_repository", not manual_path_errors and not markdown_link_errors and "AKShare升级工作区/A股研究大礼包使用说明.md" not in read_text("docs/手动补资料指南.md"), "all local manual paths/links resolve", {"missing_paths": manual_path_errors, "broken_links": markdown_link_errors})

# Local single-package ZIPs: verify the 67 prepared attachments and the calibration starter.
ignored = read_text(".gitignore")
check("deliveries_not_committed", any(line.strip().replace("\\", "/") in ("deliveries/", "deliveries/**") for line in ignored.splitlines()), "deliveries/ ignored by Git", ignored.splitlines())
zip_files = sorted((ROOT / "deliveries").glob("*.zip")) if (ROOT / "deliveries").is_dir() else []
zip_errors = []
for package in index:
    pid = package.get("package_id", "")
    zpath = ROOT / "deliveries" / f"{pid}.zip"
    if not zpath.is_file():
        zip_errors.append({"package_id": pid, "issue": "missing ZIP"})
        continue
    try:
        with zipfile.ZipFile(zpath, "r") as archive:
            corrupt = archive.testzip()
            names = archive.namelist()
            if corrupt:
                zip_errors.append({"package_id": pid, "issue": "corrupt member", "member": corrupt})
            pdf_names = [n for n in names if n.lower().endswith(".pdf")]
            assign_names = [n for n in names if re.fullmatch(r"packages/[^/]+/assignment\.csv", n)]
            if pdf_names:
                zip_errors.append({"package_id": pid, "issue": "unexpected PDFs in default ZIP", "pdfs": pdf_names})
            if assign_names != [f"packages/{pid}/assignment.csv"]:
                zip_errors.append({"package_id": pid, "issue": "assignment scope mismatch", "assignment_paths": assign_names})
            if "START_HERE.md" not in names or "attachment_manifest.json" not in names:
                zip_errors.append({"package_id": pid, "issue": "missing START_HERE or attachment manifest"})
            if "attachment_manifest.json" in names:
                manifest = json.loads(archive.read("attachment_manifest.json").decode("utf-8-sig"))
                expected_count = len(all_assignments.get(pid, []))
                if manifest.get("package_id") != pid or manifest.get("company_count") != expected_count or manifest.get("pdf_count") != 0:
                    zip_errors.append({"package_id": pid, "issue": "manifest scope/count mismatch", "manifest": manifest, "expected_company_count": expected_count})
    except Exception as exc:
        zip_errors.append({"package_id": pid, "issue": "zip read error", "detail": str(exc)})
check("all_local_package_zips_match_index", len(zip_files) == 67 and not zip_errors, {"zip_count": 67, "all text-only and package-scoped": True}, {"zip_count": len(zip_files), "errors": zip_errors[:30]})

starter_errors = []
starter = ROOT / "deliveries" / "C00_PILOT_01.zip"
if starter.is_file():
    with zipfile.ZipFile(starter, "r") as archive:
        names = archive.namelist()
        start_text = archive.read("START_HERE.md").decode("utf-8-sig") if "START_HERE.md" in names else ""
        manifest = json.loads(archive.read("attachment_manifest.json").decode("utf-8-sig")) if "attachment_manifest.json" in names else {}
        task_assignment = list(csv.DictReader(archive.read("packages/C00_PILOT_01/assignment.csv").decode("utf-8-sig").splitlines())) if "packages/C00_PILOT_01/assignment.csv" in names else []
        cropped_master = list(csv.DictReader(archive.read("data/company_master.csv").decode("utf-8-sig").splitlines())) if "data/company_master.csv" in names else []
        if len(task_assignment) != 10 or len(cropped_master) != 10 or manifest.get("company_count") != 10:
            starter_errors.append({"assignment": len(task_assignment), "cropped_master": len(cropped_master), "manifest": manifest.get("company_count")})
        if any(name.lower().endswith(".pdf") for name in names) or manifest.get("pdf_count") != 0:
            starter_errors.append("starter ZIP contains a PDF or claims a PDF")
        if "不能与原始完整表哈希直接比较" not in start_text:
            starter_errors.append("START_HERE does not explain cropped-table hashes")
        if not zipfile.is_zipfile(starter):
            starter_errors.append("starter is not a ZIP")
else:
    starter_errors.append("missing deliveries/C00_PILOT_01.zip")
check("calibration_zip_is_ten_company_text_only_and_hash_note_present", not starter_errors, {"companies": 10, "pdfs": 0, "hash_note": True}, starter_errors or {"companies": 10, "pdfs": 0, "hash_note": True})

failures = [item for item in checks if item["status"] != "PASS"]
report = {
    "report_version": 1,
    "checked_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    "research_cutoff": "2026-10-24",
    "result": "PASS" if not failures else "FAIL",
    "summary": {
        "master_companies": len(master),
        "starting_partition_counts": dict(partition_counts),
        "primary_packages": len(primary_index),
        "conditional_detail_packages": len(conditional_index),
        "detail_candidates": len(detail_ids),
        "detail_reserve": len(reserve_ids),
        "financial_missing": len(gaps),
        "group_count": len(group_rows),
        "package_index_rows": len(index),
        "local_zip_count": len(zip_files),
        "copied_resource_hashes_checked": checked_hashes,
        "checks_passed": len(checks) - len(failures),
        "checks_failed": len(failures),
    },
    "checks": checks,
    "blocking_issues": failures,
    "limitations": [
        "This audit checks plan structure and file integrity, not whether research conclusions are correct.",
        "The 45 detail candidate companies are listed in nine conditional packages; their identifiers are checked against B02_REUSE_REFERENCE.",
        "Deliveries are local attachment ZIPs and are excluded from GitHub; source PDFs are not expected in the default ZIPs.",
    ],
}
REPORT.parent.mkdir(parents=True, exist_ok=True)
REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"result": report["result"], "summary": report["summary"], "blocking_issues": failures}, ensure_ascii=True, indent=2))
sys.exit(0 if not failures else 1)

