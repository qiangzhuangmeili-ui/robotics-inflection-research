import csv
import json
import re
import hashlib
from pathlib import Path

import pypdfium2

OUT = Path(__file__).resolve().parent
REPO = OUT.parents[4]
S02 = REPO / "runs/issues/S02/remediation_20261029"
BASE = S02 / "extracted"
CORRECTED = OUT / "corrected_results"
INDEX = REPO / "runs/collection/collection_index.csv"
METRICS = S02 / "s02/all_pool_metrics.csv"
NORMALIZED = S02 / "s00/financial_normalized.csv"

TARGETS = {
    "SH:600100", "SH:600879", "SH:601727", "SH:688051", "SH:688320",
    "SH:688518", "SH:688582", "SH:688661", "SZ:000625", "SZ:001239",
    "SZ:300193",
}
CORE = {
    "FIN.REV.YTD", "FIN.REV.SQ", "FIN.COST.YTD",
    "FIN.NPP.YTD", "FIN.NPP.SQ",
    "FIN.NPDEDT.YTD", "FIN.NPDEDT.SQ",
    "FIN.OCF.YTD", "FIN.OCF.SQ",
    "FIN.AR.INSTANT", "FIN.INV.INSTANT", "FIN.CONTRACTASSET.INSTANT",
}

SUPPORTING_PAGES = {
    "DOC-88C2F8E42C5514C6": 75,
    "DOC-4B9B83B742824338": 84,
    "DOC-F9C864F9A0536DCC": 82,
}

MANUAL_NOTE_SCOPE = {
    ("DOC-F9454692F6BBE32A", "FIN.REV.YTD", 136): "H1 2025合并附注48按主营及其他业务列出收入合计；原页行值与单位可直接回溯。",
    ("DOC-CAADA5BC063F7BEA", "FIN.REV.YTD", 137): "H1 2026合并附注48按主营及其他业务列出收入合计；原页行值与单位可直接回溯。",
    ("DOC-B829722A2198EEEC", "FIN.REV.YTD", 97): "H1 2025合并附注49按主营及其他业务列出收入合计；金额与母公司报表区分，符合P04。",
    ("DOC-BB4A8F9DB0289566", "FIN.REV.YTD", 118): "H1 2026合并附注49按主营及其他业务列出收入合计；金额与母公司报表区分，符合P04。",
}


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


index = {r["document_id"]: r for r in read_csv(INDEX)}
norm_rows = read_csv(NORMALIZED)
norm_by_doc_field = {}
for r in norm_rows:
    if r["security_id"] in TARGETS and r["field_id"] in CORE and r["document_id"]:
        norm_by_doc_field.setdefault(
            (r["security_id"], r["document_id"], r["field_id"]), []
        ).append(r)

metric_rows = [r for r in read_csv(METRICS) if r["security_id"] in TARGETS]
refs = {}
for metric in metric_rows:
    for item in (metric.get("source_refs") or "").split(";"):
        parts = item.split("|")
        if len(parts) < 3 or "@" not in parts[0]:
            continue
        fid, period = parts[0].rsplit("@", 1)
        doc = parts[2]
        if not doc.startswith("DOC-"):
            continue
        if fid in CORE:
            key = (metric["security_id"], doc, fid)
            rec = refs.setdefault(key, {"periods": set(), "metrics": set(), "ref_status": set()})
            rec["periods"].add(period)
            rec["metrics"].add(metric["metric_id"])
            rec["ref_status"].add(parts[1])

# For every metric-referenced source document, audit all twelve normalized basic fields,
# including fields that the current metric formula does not consume directly.
relevant_docs = {(security, doc): periods for (security, doc, _), rec in refs.items() for periods in [rec["periods"]]}
for nrow in norm_rows:
    key_doc = (nrow["security_id"], nrow.get("document_id", ""))
    fid = nrow.get("field_id", "")
    if key_doc not in relevant_docs or fid not in CORE:
        continue
    key = (key_doc[0], key_doc[1], fid)
    rec = refs.setdefault(key, {"periods": set(), "metrics": set(), "ref_status": set()})
    rec["periods"].add(nrow.get("period_key", ""))
    rec["ref_status"].add("SUPPLEMENTAL_ALL_12_BASIC_FIELDS")

pdfs = {}
page_texts = {}
rows = []
page_images = set()


def compact(s):
    return re.sub(r"\s+", "", (s or "").replace("\u3000", ""))


def compact_number(s):
    return compact(str(s or "")).replace(",", "").replace("，", "").replace("−", "-")


for (security, doc, fid), ref in sorted(refs.items()):
    if doc not in index:
        continue
    idx = index[doc]
    old_path = BASE / f"{doc}.json"
    corrected_path = CORRECTED / f"{doc}.json"
    result_path = corrected_path if corrected_path.exists() else old_path
    result_kind = "CORRECTED_RESULT" if corrected_path.exists() else "A03_BASE"
    j = json.loads(result_path.read_text(encoding="utf-8"))
    candidates = [f for f in j.get("fields", []) if f.get("field_id") == fid]
    nrows = norm_by_doc_field.get((security, doc, fid), [])
    nrow = next((x for x in nrows if x["period_key"] in ref["periods"]), nrows[0] if nrows else {})
    # Where A03 has repeated quarter fields in annual reports, pick the field matching S00's value.
    field = None
    nv = (nrow.get("value_cny") or "").strip()
    for c in candidates:
        if nv and str(c.get("value_cny", "")).strip() == nv:
            field = c
            break
    if field is None and len(candidates) == 1:
        field = candidates[0]
    if field is None and candidates:
        field = candidates[0]

    page = ""
    if field and str(field.get("page", "")).strip():
        try:
            page = int(field["page"])
        except ValueError:
            page = ""
    if not page and nrow:
        try:
            page = int(nrow.get("source_page", ""))
        except ValueError:
            page = ""

    unit = field.get("unit_raw", "") if field else nrow.get("unit_raw", "")
    value_raw = field.get("value_raw", "") if field else nrow.get("value_raw", "")
    value_cny = field.get("value_cny", "") if field else nrow.get("value_cny", "")
    label = field.get("evidence_label", "") if field else nrow.get("evidence_label", "")
    status = field.get("extract_status", "") if field else nrow.get("status", "")
    corrected_value = (
        field.get("value_raw", "") if field else nrow.get("value_raw", "")
    )

    if doc not in pdfs:
        pdfs[doc] = pypdfium2.PdfDocument(str(REPO / idx["local_file"]))
    pdf = pdfs[doc]
    text = ""
    support_page = SUPPORTING_PAGES.get(doc, "")
    support_text = ""
    if page and 1 <= page <= len(pdf):
        text = pdf[page - 1].get_textpage().get_text_range()
        page_texts[(doc, page)] = text
        page_images.add((doc, page))
    if support_page and 1 <= support_page <= len(pdf):
        support_text = pdf[support_page - 1].get_textpage().get_text_range()
        page_texts[(doc, support_page)] = support_text
        page_images.add((doc, support_page))

    page_compact = compact_number(text)
    evidence_compact = compact_number(text + "\n" + support_text)
    number_token = compact_number(corrected_value)
    value_found = bool(number_token and number_token in page_compact)
    label_found = bool(label and compact(label) in evidence_compact)
    if not label_found and support_page and label:
        compact_label = compact(label)
        support_compact = compact_number(support_text)
        label_found = any(
            compact_label[:cut] in page_compact and compact_label[cut:] in support_compact
            for cut in range(1, len(compact_label))
        )
    header = " ".join(text.splitlines()[:12])
    mother_headings = ("母公司利润表", "母公司现金流量表", "母公司资产负债表")
    consolidated_headings = (
        "合并利润表", "合并现金流量表", "合并资产负债表",
        "合并年初到报告期末利润表", "合并年初到报告期末现金流量表",
        "合并年初到报告期末资产负债表",
    )
    mother_positions = [text.find(x) for x in mother_headings if text.find(x) >= 0]
    mother_position = min(mother_positions) if mother_positions else -1
    value_position = page_compact.find(number_token) if number_token else -1
    mother = mother_position >= 0
    consolidated = any(x in text for x in consolidated_headings)
    section_context_page = page if consolidated else ""
    section_context_kind = "CONSOLIDATED" if consolidated else ""
    # Continued statements may have their heading on the previous physical page.
    if page and not consolidated and not mother:
        for candidate_page in range(max(1, page - 3), page):
            candidate_text = pdf[candidate_page - 1].get_textpage().get_text_range()
            found_consolidated = any(x in candidate_text for x in consolidated_headings)
            found_mother = any(x in candidate_text for x in mother_headings)
            if found_consolidated or found_mother:
                section_context_page = candidate_page
                section_context_kind = "CONSOLIDATED" if found_consolidated else "MOTHER_COMPANY"
    if section_context_kind == "CONSOLIDATED":
        consolidated = True
        page_images.add((doc, section_context_page))
    official_summary = (
        "主要会计数据" in text or "主要财务数据" in text or
        (field and "主要会计数据表" in field.get("note", "")) or
        (fid.startswith("FIN.NPDEDT.") and "本报告期" in text and "归属于上市公司股东" in text)
    )
    official_quarterly_summary = "分季度主要财务指标" in text or "第一季度" in text and "第四季度" in text and "营业收入" in text
    derived = (
        "DERIVED" in status or
        "DERIVED" in " ".join(ref["ref_status"]) or
        "DERIVED" in nrow.get("status", "") or
        nrow.get("source_kind") == "DERIVED_DIFF"
    )
    direct_or_derived = (
        derived
    )

    if derived:
        scope_heading = "DERIVED_OR_HELD_UPSTREAM"
    elif mother and value_position >= 0 and value_position < mother_position:
        scope_heading = "SOURCE_VALUE_BEFORE_MOTHER_STATEMENT"
    elif mother:
        scope_heading = "MOTHER_COMPANY_SECTION_PRESENT"
    elif consolidated:
        scope_heading = "EXPLICIT_CONSOLIDATED_STATEMENT" if section_context_page == page else "CONSOLIDATED_CONTINUATION_PAGE"
    elif official_summary:
        scope_heading = "OFFICIAL_KEY_FINANCIALS_SUMMARY"
    elif official_quarterly_summary:
        scope_heading = "OFFICIAL_QUARTERLY_SUMMARY"
    else:
        scope_heading = "NOT_EXPLICIT"
    manual_scope_note = MANUAL_NOTE_SCOPE.get((doc, fid, page), "")
    if manual_scope_note:
        scope_heading = "CONSOLIDATED_FINANCIAL_STATEMENT_NOTE"

    findings = []
    if not candidates:
        findings.append("NO_A03_FIELD_RECORD")
    if not nrow:
        findings.append("NO_NORMALIZED_ROW")
    if not page:
        findings.append("NO_PHYSICAL_SOURCE_PAGE")
    if page and not value_found and corrected_value:
        findings.append("VALUE_NOT_FOUND_ON_RECORDED_PAGE")
    if page and label and not label_found:
        findings.append("LABEL_NOT_FOUND_ON_RECORDED_PAGE")
    if mother and (value_position < 0 or value_position >= mother_position) and not direct_or_derived:
        findings.append("MOTHER_COMPANY_SOURCE_SECTION")
    if not consolidated and not official_summary and not official_quarterly_summary and page and not direct_or_derived and scope_heading == "NOT_EXPLICIT" and not (mother and value_position >= 0 and value_position < mother_position):
        findings.append("NO_EXPLICIT_CONSOLIDATED_HEADING")
    if number_token in {"65", "1", "8"} and fid in {
        "FIN.REV.YTD", "FIN.COST.YTD", "FIN.NPP.YTD", "FIN.NPDEDT.YTD", "FIN.OCF.YTD"
    }:
        findings.append("LOW_VALUE_NUMBER_REQUIRES_REVIEW")

    sha = hashlib.sha256((REPO / idx["local_file"]).read_bytes()).hexdigest()
    rows.append({
        "security_id": security,
        "company_name": idx.get("title", ""),
        "slot_id": idx.get("slot_id", ""),
        "document_id": doc,
        "period_keys": ";".join(sorted(ref["periods"])),
        "metric_ids": ";".join(sorted(ref["metrics"])),
        "field_id": fid,
        "metric_source_status": ";".join(sorted(ref["ref_status"])),
        "normalized_status": nrow.get("status", ""),
        "normalized_source_kind": nrow.get("source_kind", ""),
        "normalized_source_page": nrow.get("source_page", ""),
        "normalized_source_raw": nrow.get("value_raw", ""),
        "normalized_value_cny": nrow.get("value_cny", ""),
        "normalized_quarterly_inputs": nrow.get("quarterly_inputs", ""),
        "upstream_hold_fields": nrow.get("upstream_hold_fields", ""),
        "consolidation_scope": nrow.get("consolidation_scope", ""),
        "result_version": result_kind,
        "value_raw_reviewed": value_raw,
        "unit_raw": unit,
        "value_cny_reviewed": value_cny,
        "extract_status": status,
        "source_physical_page": page,
        "evidence_label": label,
        "source_row_in_pdf_text": "YES" if value_found and label_found else ("PARTIAL" if value_found or label_found else "NO"),
        "source_scope_heading": scope_heading,
        "section_context_page": section_context_page,
        "section_context_kind": section_context_kind,
        "manual_scope_note": manual_scope_note,
        "supporting_physical_page": support_page,
        "supporting_page_header_excerpt": " ".join(support_text.splitlines()[:12])[:220],
        "page_header_excerpt": header[:220],
        "findings": ";".join(findings),
        "manual_review_status": (
            "MANUAL_PDF_NOTE_SCOPE_CONFIRMED" if manual_scope_note else
            "DERIVED_FIELD_TRACE_ONLY" if derived else
            "AUTO_SOURCE_ROW_AND_SCOPE_MATCH" if not findings else
            "REVIEW_REQUIRED"
        ),
        "source_pdf": idx["local_file"],
        "source_sha256": sha,
        "page_image": f"evidence/pages/{doc}_p{page:03}.png" if page else "",
    })

out = OUT / "field_audit.csv"
with out.open("w", encoding="utf-8-sig", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)

# Render audited source pages so manual review can use the original page image.
image_dir = OUT / "evidence/pages"
image_dir.mkdir(parents=True, exist_ok=True)
rendered = 0
for doc, page in sorted(page_images):
    dest = image_dir / f"{doc}_p{page:03}.png"
    if not dest.exists():
        pdfs[doc][page - 1].render(scale=1.5).to_pil().save(dest)
        rendered += 1

flags = [r for r in rows if r["findings"]]
print(f"field_audit.csv rows={len(rows)}; new page images={rendered}; findings={len(flags)}")
for r in flags:
    print(r["security_id"], r["document_id"], r["field_id"], r["value_raw_reviewed"], r["source_physical_page"], r["findings"])
