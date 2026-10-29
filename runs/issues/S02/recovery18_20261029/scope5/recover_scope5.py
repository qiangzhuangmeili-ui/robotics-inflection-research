"""Recover scope5 source fields without changing production extraction code.

Writes only inside this task's scope5 directory. Values whose statement scope
is not established stay blocked in corrected_results and are preserved in
evidence/recovered_values.csv for parent review.
"""
from __future__ import annotations

import csv
import json
import re
import sys
from copy import deepcopy
from pathlib import Path

import pypdfium2 as pdfium

HERE = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / "tools"))
import a03_financial_field_extractor as a03  # noqa: E402

INDEX = ROOT / "runs/collection/collection_index.csv"
BASE = ROOT / "runs/issues/S02/remediation_20261029/extracted"
OUT = HERE / "corrected_results"
EVIDENCE = HERE / "evidence"
SOURCE_PAGES = EVIDENCE / "source_pages"
EXTERNAL_SOURCES = EVIDENCE / "external_sources"
TARGETS = {"BJ:920146", "BJ:920198", "SH:600444", "SZ:301348", "SZ:002594"}
SLOTS = {"h1_2026", "h1_2025", "q1_2026", "q1_2025"}
CORE_FIELDS = {
    "FIN.AR.INSTANT", "FIN.NR.INSTANT", "FIN.CONTRACTASSET.INSTANT",
    "FIN.INV.INSTANT", "FIN.ASSET.INSTANT", "FIN.REV.YTD",
    "FIN.COST.YTD", "FIN.NP.YTD", "FIN.NPP.YTD", "FIN.OCF.YTD",
    "FIN.NPDEDT.YTD",
}


def load_rows():
    with INDEX.open("r", encoding="utf-8-sig", newline="") as f:
        return [r for r in csv.DictReader(f)
                if r.get("security_id") in TARGETS
                and r.get("slot_id") in SLOTS
                and r.get("status") == "COLLECTED_IDENTITY_VERIFIED"
                and r.get("local_file")]


def patch_parser():
    original_title = a03.is_title
    original_unit = a03.detect_unit

    def title(line):
        key = original_title(line)
        if key:
            return key
        value = a03.normalize(line).replace(" ", "").lstrip("、.．")
        value = re.sub(r"^\d{4}年(?:半年度|年度|第一季度|第三季度)?", "", value)
        # Only a candidate locator: scope is adjudicated independently below.
        return {"资产负债表": "BS_CONS", "利润表": "IS_CONS",
                "现金流量表": "CF_CONS"}.get(value)

    def unit(lines):
        value = original_unit(lines)
        if value:
            return value
        for line in lines:
            match = re.search(r"单位.{0,10}(百万元|千万元|千元|万元|元)",
                              re.sub(r"\s+", "", line))
            if match:
                return match.group(1)
        return None

    a03.is_title = title
    a03.detect_unit = unit


def all_regions(pages):
    """Use A03's guarded locator and recover CF after equity tables if needed."""
    regions = a03.build_statement_map(pages)
    # Summary/analysis pages can contain generic titles such as “资产负债表”
    # before the actual statements. When an explicit consolidated statement
    # title exists, prefer that source page for extraction and scope evidence.
    explicit_starts = {}
    for pi in range(min(2, len(pages)), len(pages)):
        for line in a03.page_lines(pages[pi]):
            key = a03.is_title(line)
            normalized = a03.normalize(line)
            if (key in {"BS_CONS", "IS_CONS", "CF_CONS"}
                    and "合并" in normalized and "母公司" not in normalized
                    and a03._looks_like_statement(pages, pi, key)):
                explicit_starts.setdefault(key, pi)
    if explicit_starts:
        ordered_starts = sorted((pi, key) for key, pi in explicit_starts.items())
        for index, (pi, key) in enumerate(ordered_starts):
            old_end = regions.get(key, (pi, len(pages) - 1, None))[1]
            end = min(old_end, ordered_starts[index + 1][0] - 1) if index + 1 < len(ordered_starts) else old_end
            unit = a03.detect_unit(a03.page_lines(pages[pi]))
            regions[key] = (pi, end, unit)
    if "CF_CONS" not in regions:
        start = min(15, len(pages)) if len(pages) > 40 else min(2, len(pages))
        for pi in range(start, len(pages)):
            if any(a03.is_title(line) == "CF_CONS" for line in a03.page_lines(pages[pi])):
                if a03._looks_like_statement(pages, pi, "CF_CONS"):
                    regions["CF_CONS"] = (pi, len(pages) - 1,
                                          a03.detect_unit(a03.page_lines(pages[pi])))
                    break
    # A three-statement report may declare a shared unit once, before all tables.
    for key, (s, e, current_unit) in list(regions.items()):
        if not key.endswith("_CONS") or current_unit:
            continue
        for pi in range(max(0, s - 8), min(len(pages), e + 1, s + 10)):
            current_unit = a03.detect_unit(a03.page_lines(pages[pi]))
            if current_unit:
                regions[key] = (s, e, current_unit)
                break
    return regions


def manual_row(pages, regions, field_id, labels):
    statement = next((st for st, fid, _labels, _join in a03.STATEMENT_FIELDS
                      if fid == field_id), None)
    if not statement or statement not in regions:
        return None
    start, end, _ = regions[statement]
    for pi in range(start, min(end + 1, len(pages))):
        lines = a03.page_lines(pages[pi])
        for i, line in enumerate(lines):
            normalized = a03.normalize(line)
            match = next(((label, normalized.find(a03.normalize(label)))
                          for label in labels
                          if normalized.find(a03.normalize(label)) >= 0), None)
            if match is None:
                continue
            label, position = match
            normalized_label = a03.normalize(label)
            raw_position = line.find(label)
            raw_aligned = raw_position >= 0
            # Search the same table row across PDF line breaks. Blank BS rows
            # remain unfilled. PDFium sometimes collapses a whole continuation
            # page to one line, so search only after the target label and take
            # the first amount in its row.
            tail = (line[raw_position + len(label):] if raw_aligned
                    else normalized[position + len(normalized_label):])
            parts = [tail]
            for next_line in lines[i + 1:i + 6]:
                next_normalized = a03.normalize(next_line)
                if re.match(r"^[\u4e00-\u9fff]", next_normalized) and not next_normalized.startswith(("注", "五、", "七、")):
                    break
                parts.append(next_line if raw_aligned else next_normalized)
                if a03.MONEY.search(" ".join(parts)):
                    break
            raw_start = raw_position if raw_aligned else position
            raw = (line[raw_start:raw_start + 180]
                   if raw_start > 0 or len(line) > 200 else line[:200])
            # Parse from immediately after the requested label so a prior row
            # on a collapsed page cannot be mistaken for this row's value.
            vals = a03.statement_amounts(" ".join(parts), note_column=True)
            if vals:
                return vals[0][0], pi + 1, labels[0], raw[:200]
    return None


def make_candidate(task, base, pages, regions):
    units = {"BS_CONS": regions.get("BS_CONS", (None, None, None))[2],
             "IS_CONS": regions.get("IS_CONS", (None, None, None))[2],
             "CF_CONS": regions.get("CF_CONS", (None, None, None))[2]}
    # BYD's audited reporting pages explicitly give a shared statement unit
    # at the top of the financial statements: "报表及附注的单位为：千元".
    if task["security_id"] == "SZ:002594" and task["slot_id"] in {"h1_2025", "h1_2026"}:
        units = {"BS_CONS": "千元", "IS_CONS": "千元", "CF_CONS": "千元"}
    unit_scale = a03.UNIT_SCALE
    rows = []
    evidence = []

    def append(fid, value, unit_value, page, label, status, note="", raw=""):
        scale = unit_scale.get(unit_value) if unit_value else None
        cny = ""
        if value not in (None, "") and scale is not None:
            try:
                cny = round(float(str(value).replace(",", "")) * scale, 2)
            except ValueError:
                cny = ""
        row = {
            "document_id": task["document_id"],
            "security_id": task["security_id"],
            "stock_code": task["stock_code"],
            "slot_id": task["slot_id"],
            "period_label": task["period_label"],
            "field_id": fid,
            "value_raw": value if value is not None else "",
            "unit_raw": unit_value or "UNKNOWN",
            "unit_scale": scale if scale is not None else "",
            "value_cny": cny,
            "page": page or "",
            "evidence_label": label or "",
            "extract_status": status,
            "note": note,
            "raw_row": (raw or "")[:200],
        }
        rows.append(row)
        if fid in CORE_FIELDS:
            evidence.append(deepcopy(row))

    extracted = {}
    for statement, fid, labels, allow_join in a03.STATEMENT_FIELDS:
        value, page, label, status = a03.extract_statement_field(
            pages, regions, statement, fid, labels, allow_join)
        raw = ""
        if value is not None:
            # Capture the original source row for the handoff record.
            if page and page <= len(pages):
                for line in a03.page_lines(pages[page - 1]):
                    if any(a03.normalize(line).startswith(x) for x in labels):
                        raw = line
                        break
            extracted[fid] = (value, page, label, raw, "STATEMENT")
        elif fid in {"FIN.REV.YTD", "FIN.COST.YTD", "FIN.ASSET.INSTANT",
                     "FIN.NPP.YTD", "FIN.OCF.YTD"}:
            manual = manual_row(pages, regions, fid, labels)
            if manual:
                raw_value, raw_page, raw_label, raw_row = manual
                extracted[fid] = (raw_value, raw_page, raw_label, raw_row, "STATEMENT_MANUAL_ROW")
            else:
                extracted[fid] = (None, page, label, "", status)

    key_values, key_page, key_unit, key_details = a03.extract_key_financials(
        pages, with_details=True)
    # Summary data remains an independent crosscheck only. Revenue, parent
    # profit, and operating cash flow are never populated from that summary.
    npdedt_detail = key_details.get("FIN.NPDEDT.YTD", {})
    npdedt = key_values.get("FIN.NPDEDT.YTD")
    extracted["FIN.NPDEDT.YTD"] = (
        npdedt, npdedt_detail.get("page") or key_page,
        "归属于上市公司股东的扣除非经常性损益后的净利润",
        npdedt_detail.get("raw_row", ""), "KEY_FINANCIALS")

    for fid in CORE_FIELDS:
        if fid == "FIN.NPDEDT.YTD":
            val, page, label, raw, source = extracted[fid]
            unit_value = npdedt_detail.get("unit") or key_unit
        elif fid in extracted:
            val, page, label, raw, source = extracted[fid]
            st = next((x[0] for x in a03.STATEMENT_FIELDS if x[1] == fid), None)
            unit_value = units.get(st)
        else:
            val, page, label, raw, source, unit_value = None, None, "", "", "MISSING", None
        status = "EXTRACTED" if val is not None else "NOT_FOUND"
        append(fid, val, unit_value, page, label, status,
               note=f"source={source}", raw=raw)

    direct = {row["field_id"]: row for row in rows}
    crosscheck = {}
    for fid in ("FIN.REV.YTD", "FIN.NPP.YTD", "FIN.OCF.YTD"):
        if fid not in key_values:
            crosscheck[fid] = "SUMMARY_NOT_FOUND"
            continue
        if fid not in direct or direct[fid]["value_cny"] == "":
            crosscheck[fid] = "STATEMENT_VALUE_NOT_FOUND"
            continue
        detail = key_details.get(fid, {})
        summary_unit = detail.get("unit") or key_unit
        scale = unit_scale.get(summary_unit)
        if scale is None:
            crosscheck[fid] = "UNPARSED"
            continue
        left = float(str(key_values[fid]).replace(",", "")) * scale
        right = float(direct[fid]["value_cny"])
        crosscheck[fid] = "MATCH" if abs(left - right) <= max(1, abs(left) * 1e-6) else "MISMATCH"

    # Scope rules are separate from extraction. Only these exact source periods
    # are allowed to enter S00; single-entity equivalents remain candidates.
    scope_key = (task["security_id"], task["slot_id"])
    release = scope_key in {
        ("SZ:002594", "h1_2025"), ("SZ:002594", "h1_2026"),
        ("SZ:002594", "q1_2025"), ("SZ:002594", "q1_2026"),
        ("SH:600444", "h1_2025"), ("SH:600444", "q1_2025"),
        # Parent approved evidence-based full-reporting-entity, zero-subsidiary
        # equivalence on 2026-10-30; generic source titles remain documented.
        ("SH:600444", "h1_2026"), ("SH:600444", "q1_2026"),
        ("SZ:301348", "q1_2025"), ("SZ:301348", "q1_2026"),
    }
    if not release:
        for row in rows:
            row["value_raw"] = ""
            row["unit_raw"] = "UNKNOWN"
            row["unit_scale"] = ""
            row["value_cny"] = ""
            row["page"] = ""
            row["evidence_label"] = ""
            row["extract_status"] = "STMT_SCOPE_HOLD"
            row["note"] = "scope unresolved/candidate; raw source value is in evidence/recovered_values.csv"
            row["raw_row"] = ""

    merged = [r for r in base.get("fields", []) if r.get("field_id") not in CORE_FIELDS]
    merged.extend(rows)
    result = deepcopy(base)
    result["fields"] = merged
    if release:
        result["unit_bs"] = units.get("BS_CONS")
        result["unit_is"] = units.get("IS_CONS")
        result["unit_cf"] = units.get("CF_CONS")
        result["regions"] = {k: {"start_page": v[0] + 1, "end_page": v[1] + 1, "unit": v[2]}
                             for k, v in regions.items() if k.endswith("_CONS")}
        result["key_financials_values"] = key_values
        result["key_financials_details"] = key_details
        result["key_financials_page"] = key_page
        result["key_financials_unit"] = key_unit
        result["crosscheck"] = crosscheck
    return result, evidence, regions, key_page, crosscheck


def scope_record(task):
    sid, slot, doc = task["security_id"], task["slot_id"], task["document_id"]
    status = "STMT_SCOPE_HOLD"
    classification = "UNRESOLVED"
    summary = "The financial table values are recoverable, but a consolidated or single-entity-equivalent scope has not been proven for this period."
    evidence = []
    if sid == "SZ:002594":
        status, classification = "RELEASED_CONSOLIDATED", "CONSOLIDATED"
        summary = "The report labels the balance sheet, income statement, and cash flow statement as consolidated. The statement unit is thousand yuan."
        if slot == "h1_2026":
            evidence = [
                {"page": 65, "quote": "合并资产负债表；财务报表及附注的单位为：千元"},
                {"page": 67, "quote": "合并利润表"},
                {"page": 71, "quote": "合并现金流量表"},
                {"page": 7, "quote": "财务数据（元），收入/归母净利/扣非/经营现金流"},
            ]
        elif slot == "h1_2025":
            evidence = [
                {"page": 63, "quote": "合并资产负债表；财务报表及附注的单位为：千元"},
                {"page": 65, "quote": "合并利润表"},
                {"page": 69, "quote": "合并现金流量表"},
                {"page": 7, "quote": "财务数据（元），收入/归母净利/扣非/经营现金流"},
            ]
        else:
            evidence = ([{"page": 5, "quote": "合并资产负债表"},
                         {"page": 7, "quote": "合并利润表"},
                         {"page": 8, "quote": "合并现金流量表"}]
                        if slot == "q1_2025" else
                        [{"page": 5, "quote": "合并资产负债表"},
                         {"page": 7, "quote": "合并利润表"},
                         {"page": 8, "quote": "合并现金流量表"}])
    elif sid == "SH:600444" and slot in {"h1_2025", "q1_2025"}:
        status, classification = "RELEASED_CONSOLIDATED", "CONSOLIDATED"
        summary = "Each of the three statements is explicitly titled consolidated in the report."
        evidence = ([{"page": 27, "quote": "合并资产负债表"},
                     {"page": 31, "quote": "合并利润表"},
                     {"page": 35, "quote": "合并现金流量表"}]
                    if slot == "h1_2025" else
                    [{"page": 5, "quote": "合并资产负债表"},
                     {"page": 8, "quote": "合并利润表"},
                     {"page": 10, "quote": "合并现金流量表"}])
    elif sid == "SZ:301348" and slot in {"q1_2025", "q1_2026"}:
        status, classification = "RELEASED_CONSOLIDATED", "CONSOLIDATED"
        summary = "Each of the three statements is explicitly titled consolidated in the quarterly report."
        evidence = [{"page": 5, "quote": "合并资产负债表"},
                    {"page": 7, "quote": "合并利润表"},
                    {"page": 8, "quote": "合并现金流量表"}]
    elif sid == "SH:600444" and slot == "h1_2026":
        status = "RELEASED_EQUIVALENT_SCOPE"
        classification = "SINGLE_ENTITY_EQUIVALENT_PARENT_APPROVED"
        summary = "Parent approved standardization as the full reporting entity with zero-subsidiary-equivalent scope. The statements retain their generic original titles; evidence links the 2024 absorption/deregistration, H1 2026 scope-change notes, and only one statement set."
        evidence = [{"document_id": "DOC-52FA26EF30DFB266", "page": 118,
                     "quote": "在子公司中的权益；企业集团的构成 □适用 √不适用"},
                    {"document_id": "DOC-52FA26EF30DFB266", "page": 125,
                     "quote": "本企业的子公司情况 □适用 √不适用"},
                    {"document_id": "DOC-52FA26EF30DFB266", "page": 36,
                     "quote": "2024年，公司实施对合肥通用环境控制技术有限责任公司的吸收合并，该公司注销，原有全部业务和债权、债务由公司承继"},
                    {"document_id": "DOC-52FA26EF30DFB266", "page": 118,
                     "quote": "九、合并范围的变更；本期企业合并、反向购买、处置子公司等均不适用"}]
    elif sid == "SH:600444" and slot == "q1_2026":
        status = "RELEASED_EQUIVALENT_SCOPE"
        classification = "SINGLE_ENTITY_EQUIVALENT_PARENT_APPROVED_CROSS_PERIOD_CHAIN"
        summary = "Parent approved standardization as the full reporting entity with zero-subsidiary-equivalent scope. Q1 uses generic titles; the evidence chain combines FY2025 group/subsidiary notes with the 2024 absorption and H1 2026 scope-change notes."
        evidence = [{"page": 5, "quote": "资产负债表（未标注合并）"},
                    {"page": 7, "quote": "利润表（未标注合并）"},
                    {"page": 9, "quote": "现金流量表（未标注合并）"},
                    {"document_id": "DOC-B62C30AEA19800D8", "page": 163,
                     "quote": "FY2025年报：企业集团的构成 □适用 √不适用"},
                    {"document_id": "DOC-B62C30AEA19800D8", "page": 169,
                     "quote": "FY2025年报：本企业的子公司情况 □适用 √不适用"},
                    {"document_id": "DOC-52FA26EF30DFB266", "page": 36,
                     "quote": "2024年实施对合肥通用环境控制技术有限责任公司的吸收合并，该公司注销，原有全部业务和债权、债务由公司承继"},
                    {"document_id": "DOC-52FA26EF30DFB266", "page": 118,
                     "quote": "2026H1报告：合并范围的变更各项不适用；企业集团的构成不适用"},
                    {"document_id": "DOC-52FA26EF30DFB266", "page": 125,
                     "quote": "2026H1报告：本企业的子公司情况 □适用 √不适用"}]
    elif sid == "SZ:301348" and slot == "h1_2025":
        classification = "SINGLE_ENTITY_EQUIVALENT_CANDIDATE"
        summary = "The report's related-party note explicitly says there were no subsidiaries during the reporting period. The three financial statement headings are generic. Parent review is required before adding an equivalent single-entity scope to P04."
        evidence = [{"page": 120, "quote": "本企业子公司的情况详见附注；报告期内公司无子公司"}]
    elif sid == "SZ:301348" and slot == "h1_2026":
        classification = "SINGLE_ENTITY_EQUIVALENT_CANDIDATE_PENDING_TRANSACTION"
        summary = "The report says the 60% acquisition of Chengdu Xinyi will be included in the consolidated statements after the transaction completes, but it does not establish whether completion had occurred by 2026-06-30. Keep blocked."
        evidence = [{"page": 42, "quote": "本次交易完成后...将其纳入公司合并报表范围"},
                    {"page": 118, "quote": "本企业的子公司情况详见附注"}]
    elif sid == "BJ:920198":
        classification = "SINGLE_ENTITY_EQUIVALENT_CANDIDATE_UNPROVEN"
        summary = "The disclosed investee table identifies the two named investees as associates, and the report says there was no change in consolidation scope. It does not provide an exhaustive statement that no subsidiaries exist. Keep blocked."
        if slot == "h1_2026":
            evidence = [{"page": 19, "quote": "湖北楚道睿科、北京博研智通均列为参股公司"},
                        {"page": 20, "quote": "合并范围是否发生变化：否"}]
        elif slot == "h1_2025":
            evidence = [{"page": 15, "quote": "列示两家参股公司"},
                        {"page": 16, "quote": "合并范围是否发生变化：否"}]
        else:
            evidence = [{"page": 3, "quote": "摘要分别报告母公司及合并资产负债率"}]
    elif sid == "BJ:920146":
        summary = "The H1 reports say no major subsidiary/associate operating information is applicable and no consolidation-scope change occurred. This does not prove that the reporting entity has no subsidiaries; headings remain generic. Keep blocked."
        if slot in {"h1_2026", "h1_2025"}:
            evidence = [{"page": 17, "quote": "主要子公司/参股公司经营情况：不适用"},
                        {"page": 17, "quote": "合并财务报表的合并范围是否发生变化：否"}]
        else:
            evidence = [{"page": 3, "quote": "母公司及合并资产负债率列示为相同数值"}]
    return {
        "security_id": sid, "period_label": task["period_label"],
        "slot_id": slot, "document_id": doc, "status": status,
        "classification": classification, "summary": summary,
        "statement_scope": ("CONSOLIDATED" if status == "RELEASED_CONSOLIDATED"
                            else "CONSOLIDATED_EQUIVALENT" if status == "RELEASED_EQUIVALENT_SCOPE"
                            else "UNRESOLVED_OR_CANDIDATE"),
        "statement_scope_original": ("GENERIC_SINGLE_ENTITY"
                                     if status == "RELEASED_EQUIVALENT_SCOPE" else None),
        "s00_scope_mapping": ("CONSOLIDATED" if status == "RELEASED_EQUIVALENT_SCOPE" else None),
        "scope_equivalence_basis": ({
            "decision": "Parent approved full-reporting-entity, zero-subsidiary equivalence on 2026-10-30.",
            "semantic_mapping": "S00 may map to CONSOLIDATED to mean the full reporting entity is covered; this is an evidence-based scope standardization, not a claim that the source statement titles say consolidated and not a threshold change.",
            "source_evidence": evidence,
            "separate_parent_statement_set_found": False,
            "p04_contract_change_required": "Parent approval covers this scoped recovery output; P04 must state the equivalent-scope branch before S00 consumes it.",
        } if status == "RELEASED_EQUIVALENT_SCOPE" else None),
        "evidence": evidence,
        "release_condition": ("Use only after independent source review." if status == "RELEASED_CONSOLIDATED"
                              else "Parent approved the evidence-based equivalent scope; P04 must explicitly encode this branch before S00 ingestion." if status == "RELEASED_EQUIVALENT_SCOPE"
                              else "Parent must approve the equivalent single-entity scope or resolve the scope evidence; no S00 ingestion while STMT_SCOPE_HOLD."),
    }


def report_structure(task, pages, regions):
    """Record same-report statement titles, parent tables, and scope-note searches."""
    statement_words = {
        "BS_CONS": "资产负债表", "IS_CONS": "利润表", "CF_CONS": "现金流量表",
    }
    titles = []
    for key, word in statement_words.items():
        if key not in regions:
            continue
        start, end, _unit = regions[key]
        lines = a03.page_lines(pages[start])
        match = next((line.strip() for line in lines if word in a03.normalize(line)), "")
        normalized = a03.normalize(match)
        scope_word = ("CONSOLIDATED" if "合并" in normalized else
                      "PARENT_COMPANY" if "母公司" in normalized else "GENERIC")
        titles.append({"statement": key, "physical_pdf_page": start + 1,
                       "title_as_printed": match, "scope_word": scope_word,
                       "region_end_physical_pdf_page": end + 1})

    parent_titles = []
    for page_index, page_text in enumerate(pages):
        for line in a03.page_lines(page_text):
            normalized = a03.normalize(line)
            flat = re.sub(r"\s+", "", normalized)
            flat = re.sub(r"^[（(]?[一二三四五六七八九十0-9]+[）)、.．]", "", flat)
            flat = flat.replace("（", "").replace("）", "").replace("(", "").replace(")", "")
            if ("母公司" not in flat or len(flat) > 60):
                continue
            statement = next((key for key, word in statement_words.items() if word in normalized), None)
            title_shape = bool(re.fullmatch(
                r"(?:母公司(?:合并)?(?:资产负债表|利润表|现金流量表)|"
                r"(?:资产负债表|利润表|现金流量表)母公司)(?:续)?", flat))
            if statement and title_shape:
                parent_titles.append({"statement": statement,
                                      "physical_pdf_page": page_index + 1,
                                      "title_as_printed": line.strip()})

    note_terms = {
        "explicit_no_subsidiaries": "报告期内公司无子公司",
        "enterprise_group_composition": "企业集团的构成",
        "subsidiary_equity_note": "在子公司中的权益",
        "subsidiary_note": "本企业的子公司情况",
        "consolidation_scope_change": "合并财务报表的合并范围是否发生变化",
        "changes_in_scope_heading": "合并范围的变更",
        "subsidiaries_acquired_or_disposed": "报告期内取得和处置子公司",
        "major_subsidiary_operating_information": "主要子公司",
    }
    note_search = {}
    for label, term in note_terms.items():
        hits = []
        for page_index, page_text in enumerate(pages):
            position = page_text.find(term)
            if position < 0:
                continue
            quote = page_text[max(0, position - 60):position + 220]
            hits.append({"physical_pdf_page": page_index + 1,
                         "quote": re.sub(r"\s+", " ", quote).strip()})
        note_search[label] = {"status": "FOUND" if hits else "NOT_FOUND",
                              "pages": [x["physical_pdf_page"] for x in hits[:6]],
                              "excerpts": hits[:3]}

    transaction_review = None
    cross_period_scope_chain = None
    if task["security_id"] == "SH:600444" and task["slot_id"] == "q1_2026":
        cross_period_scope_chain = {
            "status": "PARENT_APPROVED_EQUIVALENT_SCOPE; release with generic-title metadata",
            "evidence": [
                {"document_id": "DOC-B62C30AEA19800D8", "period": "FY2025",
                 "physical_pdf_page": 163,
                 "quote": "企业集团的构成 □适用 √不适用"},
                {"document_id": "DOC-B62C30AEA19800D8", "period": "FY2025",
                 "physical_pdf_page": 169,
                 "quote": "本企业的子公司情况 □适用 √不适用"},
                {"document_id": "DOC-52FA26EF30DFB266", "period": "2026H1",
                 "physical_pdf_page": 36,
                 "quote": "2024年，公司实施了对合肥通用环境控制技术有限责任公司的吸收合并，合肥通用环境控制技术有限责任公司注销，原有全部业务和债权、债务由公司承继。"},
                {"document_id": "DOC-52FA26EF30DFB266", "period": "2026H1",
                 "physical_pdf_page": 118,
                 "quote": "九、合并范围的变更：本期企业合并、反向购买、处置子公司等事项均不适用；企业集团的构成不适用。"},
                {"document_id": "DOC-52FA26EF30DFB266", "period": "2026H1",
                 "physical_pdf_page": 125,
                 "quote": "本企业的子公司情况 □适用 √不适用。"}
            ],
            "q1_statement_scope": "Three generic statement titles on DOC-6B0CAFDCCFF7978D physical pages 5, 7, 9; no separate parent statement titles identified.",
            "limitation": "This is not a consolidated-title proof. Parent approved the evidence-based full-reporting-entity, zero-subsidiary equivalent; P04 must explicitly encode the branch before S00 ingestion.",
        }
    if task["security_id"] == "SZ:301348" and task["slot_id"] == "h1_2026":
        terms = ("成都芯翼", "本次交易完成后", "完成交割", "已完成交割", "股权变更登记")
        hits = []
        for page_index, page_text in enumerate(pages):
            if "成都芯翼" not in page_text:
                continue
            snippets = []
            for term in terms:
                position = page_text.find(term)
                if position >= 0:
                    snippets.append(re.sub(r"\s+", " ",
                                           page_text[max(0, position - 50):position + 240]).strip())
            if snippets:
                hits.append({"physical_pdf_page": page_index + 1, "quotes": snippets[:3]})
        asset_lines = []
        for page_index, page_text in enumerate(pages):
            for term in ("长期股权投资", "商誉"):
                position = page_text.find(term)
                if position >= 0 and page_index + 1 in {25, 49}:
                    asset_lines.append({"physical_pdf_page": page_index + 1,
                                        "quote": re.sub(r"\s+", " ",
                                                         page_text[max(0, position - 40):position + 190]).strip()})
        transaction_review = {
            "status_as_of_reporting_period": "COMPLETION_NOT_ESTABLISHED; wording remains conditional",
            "approval_milestones": [
                {"physical_pdf_page": 41, "printed_page": 40, "date": "2026-06-11",
                 "event": "第五届董事会第五次会议审议收购成都芯翼60%股权议案。"},
                {"physical_pdf_page": 41, "printed_page": 40, "date": "2026-06-29",
                 "event": "2026年第二次临时股东会审议通过收购成都芯翼60%股权议案。"},
                {"physical_pdf_page": 42, "printed_page": 41, "date": "not stated on this page",
                 "event": "成都芯翼全体股东签署股权收购协议；公司表述为“本次交易完成后”才持有60%股权并纳入合并报表。"}
            ],
            "evidence": hits,
            "asset_merge_clues": asset_lines,
            "completion_check": {
                "report_period_end": "2026-06-30",
                "terms_searched_in_full_h1_report": list(terms),
                "completion_date_or_transfer_registration_found": False,
                "conclusion": "Approval and agreement signing are evidenced; completion by 2026-06-30 is not evidenced."
            },
            "interpretation_limit": "The contract approval, conditional wording, and balance-sheet line items do not by themselves prove acquisition completion by 2026-06-30 or the inclusion of Chengdu Xinyi in these statements.",
        }

    return {
        "physical_page_numbering": "All page references are 1-based physical PDF page numbers.",
        "main_statement_titles": titles,
        "main_statement_set_complete": all(x["statement"] in {t["statement"] for t in titles}
                                            for x in [{"statement": k} for k in statement_words]),
        "separate_parent_statement_titles": parent_titles,
        "separate_parent_statement_types": sorted({x["statement"] for x in parent_titles}),
        "scope_note_search": note_search,
        "transaction_review": transaction_review,
        "cross_period_scope_chain": cross_period_scope_chain,
    }


def render_pages(task, page_numbers):
    path = ROOT / task["local_file"]
    doc = pdfium.PdfDocument(str(path))
    for page in sorted({p for p in page_numbers if isinstance(p, int) and 1 <= p <= len(doc)}):
        out = SOURCE_PAGES / f"{task['document_id']}_p{page:03d}.png"
        if not out.exists():
            doc[page - 1].render(scale=1.5).to_pil().save(out)
    doc.close()


def main():
    patch_parser()
    corrections = []
    recovered = []
    scope_rows = []
    crosscheck_rows = []
    result_rows = []
    tasks_by_doc = {}
    for row in load_rows():
        task = {"document_id": row["document_id"], "security_id": row["security_id"],
                "stock_code": row["security_id"].split(":", 1)[1],
                "slot_id": row["slot_id"], "period_label": row["period_label"],
                "path": str(ROOT / row["local_file"]), "local_file": row["local_file"]}
        tasks_by_doc[task["document_id"]] = task
        old_path = BASE / f"{task['document_id']}.json"
        if not old_path.exists():
            raise FileNotFoundError(f"baseline A03 extraction missing: {old_path}")
        old = json.loads(old_path.read_text(encoding="utf-8"))
        pdf = pdfium.PdfDocument(task["path"])
        pages = [pdf[i].get_textpage().get_text_range() for i in range(len(pdf))]
        regions = all_regions(pages)
        new, evidence_rows, regions, key_page, checks = make_candidate(task, old, pages, regions)
        crosscheck_rows.append({"document_id": task["document_id"],
                                "security_id": task["security_id"],
                                "slot_id": task["slot_id"],
                                "checks": checks})
        decision = scope_record(task)
        decision["report_structure"] = report_structure(task, pages, regions)
        if decision["status"] == "RELEASED_CONSOLIDATED":
            title_scopes = {x["statement"]: x["scope_word"]
                            for x in decision["report_structure"]["main_statement_titles"]}
            if not all(title_scopes.get(k) == "CONSOLIDATED"
                       for k in ("BS_CONS", "IS_CONS", "CF_CONS")):
                raise ValueError(f"release scope lacks three explicit consolidated titles: {task['document_id']}")
        scope_rows.append(decision)
        allowed = decision["status"] in {"RELEASED_CONSOLIDATED", "RELEASED_EQUIVALENT_SCOPE"}
        if decision["status"] == "RELEASED_EQUIVALENT_SCOPE":
            new["statement_scope_original"] = "GENERIC_SINGLE_ENTITY"
            new["statement_scope_normalized_for_s00"] = "CONSOLIDATED"
            new["scope_equivalence_basis"] = decision["scope_equivalence_basis"]
            new["parent_review_resolution"] = {
                "approved": True,
                "approved_by": "parent agent",
                "approval_date": "2026-10-30",
                "decision": "Treat the statements as covering the full reporting entity with zero subsidiaries; S00 may normalize scope to CONSOLIDATED. Preserve generic source title and disclose this as evidence-based scope standardization, not a source title claim or threshold change.",
                "self_check_reference": "scope_decisions.json:parent_approved_scope_equivalence; SELF_CHECK.json:parent_approved_equivalent_scope_released",
            }
        # Parent-approved full-entity equivalent scope is released with its
        # generic source title preserved; unresolved generic statements stay held.
        if not allowed:
            out_fields = []
            for item in new["fields"]:
                if item.get("field_id") in CORE_FIELDS:
                    item = deepcopy(item)
                    item.update({"value_raw": "", "unit_raw": "UNKNOWN", "unit_scale": "",
                                 "value_cny": "", "page": "", "evidence_label": "",
                                 "extract_status": "STMT_SCOPE_HOLD",
                                 "note": "Scope not cleared; source candidate is separately recorded in evidence/recovered_values.csv",
                                 "raw_row": ""})
                out_fields.append(item)
            new["fields"] = out_fields
        # Scope status and recovered candidates are explicit in a sidecar CSV.
        for ev in evidence_rows:
            raw_val = ev.get("value_raw", "")
            if raw_val == "" and ev.get("extract_status") not in {"BLANK_IN_STATEMENT", "NOT_IN_STATEMENT"}:
                continue
            recovered.append({
                "security_id": task["security_id"], "stock_code": task["stock_code"],
                "period_label": task["period_label"], "slot_id": task["slot_id"],
                "document_id": task["document_id"], "field_id": ev["field_id"],
                "candidate_value_raw": raw_val,
                "candidate_unit_raw": ev.get("unit_raw", "UNKNOWN"),
                "candidate_value_cny": ev.get("value_cny", ""),
                "extract_status_before_scope_gate": ev.get("extract_status", ""),
                "scope_status": decision["status"], "scope_classification": decision["classification"],
                "physical_pdf_page": ev.get("page", ""), "evidence_label": ev.get("evidence_label", ""),
                "raw_row": ev.get("raw_row", ""), "note": ev.get("note", ""),
            })
            # Compare old A03 field to corrected A03 field for audit trail.
            prior = next((x for x in old.get("fields", []) if x.get("field_id") == ev["field_id"]), {})
            final = next((x for x in new.get("fields", []) if x.get("field_id") == ev["field_id"]), {})
            if any(prior.get(k) != final.get(k) for k in
                   ("value_raw", "unit_raw", "unit_scale", "value_cny", "page", "extract_status", "note")):
                corrections.append({
                    "security_id": task["security_id"], "stock_code": task["stock_code"],
                    "period_label": task["period_label"], "slot_id": task["slot_id"],
                    "document_id": task["document_id"], "field_id": ev["field_id"],
                    "old_value_raw": prior.get("value_raw", ""), "old_unit_raw": prior.get("unit_raw", ""),
                    "old_status": prior.get("extract_status", ""),
                    "new_value_raw": final.get("value_raw", ""), "new_unit_raw": final.get("unit_raw", ""),
                    "new_value_cny": final.get("value_cny", ""), "new_status": final.get("extract_status", ""),
                    "candidate_value_raw": raw_val, "candidate_unit_raw": ev.get("unit_raw", "UNKNOWN"),
                    "candidate_value_cny": ev.get("value_cny", ""),
                    "physical_pdf_page": ev.get("page", ""), "scope_status": decision["status"],
                    "evidence_label": ev.get("evidence_label", ""),
                    "raw_row": ev.get("raw_row", ""), "note": ev.get("note", ""),
                })
        OUT.joinpath(f"{task['document_id']}.json").write_text(
            json.dumps(new, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        result_rows.append(new)
        # Render every page used by field extraction or scope evidence.
        used_pages = [int(x["page"]) for x in evidence_rows if str(x.get("page", "")).isdigit()]
        used_pages += [int(x["page"]) for x in decision["evidence"] if str(x.get("page", "")).isdigit()]
        structure = decision["report_structure"]
        used_pages += [x["physical_pdf_page"] for x in structure["main_statement_titles"]]
        used_pages += [x["physical_pdf_page"] for x in structure["separate_parent_statement_titles"]]
        used_pages += [p for note in structure["scope_note_search"].values()
                       for p in note["pages"]]
        if structure["transaction_review"]:
            used_pages += [x["physical_pdf_page"] for x in structure["transaction_review"]["evidence"]]
            used_pages += [x["physical_pdf_page"] for x in structure["transaction_review"]["asset_merge_clues"]]
        render_pages(task, used_pages)
        if structure["cross_period_scope_chain"]:
            with INDEX.open("r", encoding="utf-8-sig", newline="") as f:
                source_index = {r["document_id"]: r for r in csv.DictReader(f)}
            external_pages = {}
            for item in structure["cross_period_scope_chain"]["evidence"]:
                evidence_doc = item["document_id"]
                if evidence_doc != task["document_id"]:
                    external_pages.setdefault(evidence_doc, []).append(item["physical_pdf_page"])
            for evidence_doc, page_list in external_pages.items():
                source_row = source_index.get(evidence_doc)
                if source_row and source_row.get("local_file"):
                    render_pages({"document_id": evidence_doc, "local_file": source_row["local_file"]}, page_list)
        pdf.close()

    company_scope_reviews = [
        {
            "security_id": "SZ:301348",
            "subject": "2026H1 Chengdu Xinyi 60% acquisition completion and statement scope",
            "reviewed_documents": [
                {"document_id": "DOC-49C039910AC36BAC", "period": "2026H1",
                 "pages_in_full_report": 135, "review_extent": "full extracted report text; transaction, completion, transfer-registration and subsidiary-note terms searched"}
            ],
            "source_evidence": [
                {"document_id": "DOC-49C039910AC36BAC", "physical_pdf_page": 41, "printed_page": 40,
                 "quote": "2026-06-11第五届董事会第五次会议及2026-06-29第二次临时股东会审议通过收购成都芯翼60%股权议案。"},
                {"document_id": "DOC-49C039910AC36BAC", "physical_pdf_page": 42, "printed_page": 41,
                 "quote": "成都芯翼全体股东签署股权收购协议；本次交易完成后，公司将持有成都芯翼60%股权并将其纳入合并报表范围。"},
                {"document_id": "DOC-49C039910AC36BAC", "physical_pdf_page": 118, "printed_page": 117,
                 "quote": "本企业的子公司情况详见附注。"}
            ],
            "official_announcement_follow_up": {
                "local_announcement_index": "sources/collection/raw_ann/301348/p2.json",
                "announcement_id": "1225471984",
                "announcement_number": "2026-037",
                "title": "关于收购成都芯翼科技有限公司60%股权的进展公告",
                "publication_date": "2026-08-14",
                "board_signing_date": "2026-08-13",
                "official_pdf_url": "https://static.cninfo.com.cn/finalpage/2026-08-14/1225471984.PDF",
                "pdf_page": 1,
                "source_quote": "近日，成都芯翼已完成工商变更登记手续，并取得了金牛区市场监督管理局换发的纸质版《营业执照》。",
                "exact_registration_or_completion_date_disclosed": False,
                "interpretation": "Confirms completion by the August 2026 announcement, but the term ‘近日’ does not establish whether completion was before or after the 2026-06-30 reporting cutoff. The H1 scope remains held."
            },
            "initial_acquisition_announcement": {
                "announcement_id": "1225365961",
                "announcement_number": "2026-026",
                "title": "关于收购成都芯翼科技有限公司60%股权的公告",
                "publication_date": "2026-06-12",
                "official_pdf_url": "https://static.cninfo.com.cn/finalpage/2026-06-12/1225365961.PDF",
                "pdf_page": 1,
                "source_quote": "公司于2026年6月11日与成都芯翼股东签署《股权收购协议》；本次交易完成后，成都芯翼将成为控股子公司，纳入公司合并报表范围。",
                "exact_completion_date_disclosed": False
            },
            "conclusion": "The two approval dates and agreement signing are sourced; the report uses conditional completion wording and does not establish a completion date or transfer registration by 2026-06-30. Keep H1 2026 scope held.",
            "limitations": ["Agreement signing is not treated as proof of completion.", "The post-completion consolidation statement is not treated as proof that Chengdu Xinyi was included in H1 statements."]
        },
        {
            "security_id": "BJ:920146",
            "subject": "Scope investigation across FY2025, H1 2025/2026 and Q1 2025/2026",
            "reviewed_documents": [
                {"document_id": "DOC-95E396B07ECF1710", "period": "FY2025", "pages_in_full_report": 142,
                 "review_extent": "all extracted pages searched for no-subsidiary, group-composition, subsidiary-note and scope-change disclosures"},
                {"document_id": "DOC-40C94FA974D2DB83", "period": "2025H1", "pages_in_full_report": 96,
                 "review_extent": "scope note pages 17 and 38 plus report-wide statement-title scan"},
                {"document_id": "DOC-E0F76F5E68FB4ED1", "period": "2026H1", "pages_in_full_report": 102,
                 "review_extent": "scope note pages 17 and 39 plus report-wide statement-title scan"},
                {"document_id": "DOC-40311A189C4A6963", "period": "2025Q1", "pages_in_full_report": 13,
                 "review_extent": "full extracted report text and statement-title scan"},
                {"document_id": "DOC-1C22AABCBF36A692", "period": "2026Q1", "pages_in_full_report": 17,
                 "review_extent": "full extracted report text and statement-title scan"}
            ],
            "source_evidence": [
                {"document_id": "DOC-40C94FA974D2DB83", "physical_pdf_page": 17,
                 "quote": "主要控股子公司、参股公司经营情况不适用；报告期内取得和处置子公司的情况不适用；合并财务报表的合并范围是否发生变化：否。"},
                {"document_id": "DOC-E0F76F5E68FB4ED1", "physical_pdf_page": 17,
                 "quote": "主要控股子公司、参股公司经营情况不适用；报告期内取得和处置子公司的情况不适用；合并财务报表的合并范围是否发生变化：否。"},
                {"document_id": "DOC-95E396B07ECF1710", "physical_pdf_page": 51,
                 "quote": "在职员工（公司及控股子公司）基本情况。"}
            ],
            "full_report_search_findings": [
                "FY2025 142-page annual report has no extracted hit for ‘报告期内公司无子公司’, ‘企业集团的构成’, ‘本企业的子公司情况’ or ‘合并财务报表的合并范围是否发生变化’; the employee table says company and controlled subsidiaries but gives no entity list.",
                "The two H1 reports state no scope change and mark major subsidiary operating information/acquisition-disposal tables not applicable. This does not establish that no subsidiaries existed at period end.",
                "The two Q1 reports have generic three-statement headings and no affirmative period scope note. No separate parent-statement title set was identified in the H1/Q1 full-text scan."
            ],
            "decision": "STMT_SCOPE_HOLD; no evidence-backed zero-subsidiary equivalent scope candidate."
        },
        {
            "security_id": "BJ:920198",
            "subject": "Scope investigation across FY2025, H1 2025/2026 and Q1 2025/2026",
            "reviewed_documents": [
                {"document_id": "DOC-30865C1A8F82E81A", "period": "FY2025", "pages_in_full_report": 188,
                 "review_extent": "all extracted pages searched for no-subsidiary, group-composition, subsidiary-note and scope-change disclosures"},
                {"document_id": "DOC-2D401B5A96AA7CD7", "period": "2025H1", "pages_in_full_report": 93,
                 "review_extent": "company investment/associate and scope-change disclosures plus report-wide statement-title scan"},
                {"document_id": "DOC-F71C231A9FD7C56D", "period": "2026H1", "pages_in_full_report": 118,
                 "review_extent": "company investment/associate and scope-change disclosures plus report-wide statement-title scan"},
                {"document_id": "DOC-96A9C15CA60B5BEB", "period": "2025Q1", "pages_in_full_report": 15,
                 "review_extent": "full extracted report text and statement-title scan"},
                {"document_id": "DOC-39651CB2EA95065B", "period": "2026Q1", "pages_in_full_report": 22,
                 "review_extent": "full extracted report text and statement-title scan"}
            ],
            "source_evidence": [
                {"document_id": "DOC-30865C1A8F82E81A", "physical_pdf_page": 29,
                 "quote": "主要子公司及对公司净利润影响达10%以上的参股公司表为空；子公司情况说明中取得/处置及管理控制情况不适用。"},
                {"document_id": "DOC-F71C231A9FD7C56D", "physical_pdf_page": 19,
                 "quote": "湖北楚道睿科私募股权投资合伙企业（有限合伙）和北京博研智通科技有限公司均列为参股公司。"},
                {"document_id": "DOC-F71C231A9FD7C56D", "physical_pdf_page": 20,
                 "quote": "报告期内取得和处置子公司的情况不适用；合并财务报表的合并范围是否发生变化：否。"},
                {"document_id": "DOC-2D401B5A96AA7CD7", "physical_pdf_page": 16,
                 "quote": "报告期内取得和处置子公司的情况不适用；合并财务报表的合并范围是否发生变化：否。"}
            ],
            "full_report_search_findings": [
                "FY2025 annual report has no extracted hit for ‘报告期内公司无子公司’, ‘企业集团的构成’, ‘本企业的子公司情况’ or ‘合并财务报表的合并范围是否发生变化’; its major-subsidiary disclosure is not an exhaustive group-composition note.",
                "H1 2025 and H1 2026 identify the two named investees as associates and report no scope change/acquisition-disposal event, but do not state that the company has no subsidiaries.",
                "Both Q1 reports use generic statement headings and provide no affirmative statement-scope note. No separate parent-statement title set was identified in the H1/Q1 full-text scan."
            ],
            "decision": "STMT_SCOPE_HOLD; the disclosed associates and unchanged-scope statements do not prove the subsidiary population is empty."
        }
    ]
    external_source_manifest = [
        {
            "source_id": "EXT-CNINFO-2026-037-301348",
            "announcement_number": "2026-037",
            "title": "关于收购成都芯翼科技有限公司60%股权的进展公告",
            "url": "https://static.cninfo.com.cn/finalpage/2026-08-14/1225471984.PDF",
            "access_date": "2026-10-30",
            "source_page": 1,
            "pdf_pages": 1,
            "retrieval_status": "WEB_TEXT_ONLY_BINARY_UNAVAILABLE",
            "access_method": "Official CNINFO PDF opened and read through the web PDF text reader.",
            "local_binary_path": None,
            "bytes": None,
            "sha256": None,
            "local_binary_attempt": "Python urllib download failed with Windows WinError 10013 (socket access denied); no binary or hash was fabricated.",
            "source_quote": "近日，成都芯翼已完成工商变更登记手续，并取得了金牛区市场监督管理局换发的纸质版《营业执照》。",
            "date_limit": "The announcement is signed 2026-08-13 and published 2026-08-14, but does not specify the actual registration date."
        },
        {
            "source_id": "EXT-CNINFO-2026-026-301348",
            "announcement_number": "2026-026",
            "title": "关于收购成都芯翼科技有限公司60%股权的公告",
            "url": "https://static.cninfo.com.cn/finalpage/2026-06-12/1225365961.PDF",
            "access_date": "2026-10-30",
            "source_page": 1,
            "pdf_pages": 19,
            "retrieval_status": "WEB_TEXT_ONLY_BINARY_UNAVAILABLE",
            "access_method": "Official CNINFO PDF opened and read through the web PDF text reader.",
            "local_binary_path": None,
            "bytes": None,
            "sha256": None,
            "local_binary_attempt": "Python urllib download failed with Windows WinError 10013 (socket access denied); no binary or hash was fabricated.",
            "source_quote": "公司于2026年6月11日与成都芯翼股东签署《股权收购协议》；本次交易完成后，成都芯翼将成为控股子公司，纳入公司合并报表范围。",
            "date_limit": "The announcement describes the proposed post-completion scope and does not state the transaction completion date."
        }
    ]
    EXTERNAL_SOURCES.mkdir(parents=True, exist_ok=True)
    (EXTERNAL_SOURCES / "manifest.json").write_text(
        json.dumps(external_source_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # Render annual-report pages cited only by the scope investigation; all writes
    # remain in this recovery scope directory.
    with INDEX.open("r", encoding="utf-8-sig", newline="") as f:
        source_index = {r["document_id"]: r for r in csv.DictReader(f)}
    for review in company_scope_reviews:
        pages_by_doc = {}
        for item in review["source_evidence"]:
            pages_by_doc.setdefault(item["document_id"], []).append(item["physical_pdf_page"])
        for evidence_doc, page_list in pages_by_doc.items():
            source_row = source_index.get(evidence_doc)
            if source_row and source_row.get("local_file"):
                render_pages({"document_id": evidence_doc, "local_file": source_row["local_file"]}, page_list)

    def save_csv(path, data, fieldnames):
        with path.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(data)

    correction_fields = ["security_id", "stock_code", "period_label", "slot_id", "document_id", "field_id",
                         "old_value_raw", "old_unit_raw", "old_status", "new_value_raw", "new_unit_raw",
                         "new_value_cny", "new_status", "candidate_value_raw", "candidate_unit_raw",
                         "candidate_value_cny", "physical_pdf_page", "scope_status", "evidence_label", "raw_row", "note"]
    recovered_fields = ["security_id", "stock_code", "period_label", "slot_id", "document_id", "field_id",
                        "candidate_value_raw", "candidate_unit_raw", "candidate_value_cny",
                        "extract_status_before_scope_gate", "scope_status", "scope_classification",
                        "physical_pdf_page", "evidence_label", "raw_row", "note"]
    save_csv(HERE / "source_corrections.csv", corrections, correction_fields)
    save_csv(EVIDENCE / "recovered_values.csv", recovered, recovered_fields)
    (HERE / "scope_decisions.json").write_text(
        json.dumps({"version": "S02_SCOPE5_RECOVERY_20261030_V5",
                    "rule": "Explicit consolidated source titles may release directly. Parent-approved full-reporting-entity, zero-subsidiary equivalents may also release when generic source titles and the scope basis remain explicit; all other unresolved generic statements are STMT_SCOPE_HOLD.",
                    "parent_approved_scope_equivalence": {
                        "approval_date": "2026-10-30",
                        "approved_by": "parent agent",
                        "document_ids": ["DOC-6B0CAFDCCFF7978D", "DOC-52FA26EF30DFB266"],
                        "security_id": "SH:600444",
                        "decision": "Standardize as full reporting entity with zero subsidiaries; S00 may map consolidation_scope to CONSOLIDATED.",
                        "meaning_and_limit": "This is an evidence-based scope standardization that the report covers the full reporting entity, not a claim that generic source statement titles say consolidated and not a change to metric thresholds.",
                        "p04_contract": "P04 must explicitly define the full-reporting-entity, zero-subsidiary-equivalent branch before S00 ingestion.",
                    },
                    "external_primary_sources": external_source_manifest,
                    "handoff_state": "SOURCE_FINALIZED_READY_FOR_INTEGRATION",
                    "recommended_parent_review_candidates": [
                        {"document_id": "DOC-699579136779760A", "security_id": "SZ:301348",
                         "slot_id": "h1_2025", "release_status": "HOLD pending P04 equivalence review",
                         "reason": "Same-period note explicitly states no subsidiaries; three generic statements form the only statement set and no separate parent statement titles were found."}
                    ],
                    "additional_company_scope_reviews": company_scope_reviews,
                    "not_recommended_for_release": [
                        {"document_id": "DOC-49C039910AC36BAC", "security_id": "SZ:301348",
                         "slot_id": "h1_2026", "reason": "Official 2026-08-14 progress announcement confirms registration completion by then but says only ‘近日’ and gives no exact date; cannot resolve whether completion preceded the 2026-06-30 cutoff."},
                        {"security_id": "BJ:920146", "reason": "No same-period no-subsidiary proof; 'major subsidiary/associate information not applicable' is not proof of no subsidiaries."},
                        {"security_id": "BJ:920198", "reason": "Two named investees are identified as associates and consolidation scope change is marked no, but disclosure is not exhaustive proof that no subsidiaries exist."}
                    ],
                    "documents": scope_rows}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    mismatches = [{"document_id": row["document_id"], "security_id": row["security_id"],
                   "slot_id": row["slot_id"], "field_id": fid, "status": status}
                  for row in crosscheck_rows for fid, status in row["checks"].items()
                  if status in {"MISMATCH", "UNPARSED"}]
    crosscheck_unavailable = [
        {"document_id": row["document_id"], "security_id": row["security_id"],
         "slot_id": row["slot_id"], "field_id": fid, "status": status}
        for row in crosscheck_rows for fid, status in row["checks"].items()
        if status in {"SUMMARY_NOT_FOUND", "STATEMENT_VALUE_NOT_FOUND"}]
    held_values_leaked = [
        {"document_id": result.get("document_id"), "field_id": field.get("field_id"),
         "extract_status": field.get("extract_status")}
        for result in result_rows for field in result.get("fields", [])
        if field.get("field_id") in CORE_FIELDS
        and field.get("extract_status") == "STMT_SCOPE_HOLD"
        and any(field.get(k) not in (None, "") for k in
                ("value_raw", "unit_scale", "value_cny", "page", "evidence_label", "raw_row"))]
    summary_fallback_fields = [
        {"document_id": result.get("document_id"), "field_id": field.get("field_id"),
         "note": field.get("note", "")}
        for result in result_rows for field in result.get("fields", [])
        if field.get("field_id") in {"FIN.REV.YTD", "FIN.NPP.YTD", "FIN.OCF.YTD"}
        and "SUMMARY_FALLBACK" in str(field.get("note", ""))]
    missing_evidence_pages = []
    for decision in scope_rows:
        structure = decision["report_structure"]
        page_refs = [(item.get("document_id", decision["document_id"]), item.get("page"))
                     for item in decision["evidence"]]
        page_refs += [(decision["document_id"], x["physical_pdf_page"])
                      for x in structure["main_statement_titles"]]
        page_refs += [(decision["document_id"], x["physical_pdf_page"])
                      for x in structure["separate_parent_statement_titles"]]
        page_refs += [(decision["document_id"], p)
                      for note in structure["scope_note_search"].values()
                      for p in note["pages"]]
        if structure["cross_period_scope_chain"]:
            page_refs += [(item["document_id"], item["physical_pdf_page"])
                          for item in structure["cross_period_scope_chain"]["evidence"]]
        if structure["transaction_review"]:
            page_refs += [(decision["document_id"], x["physical_pdf_page"])
                          for x in structure["transaction_review"]["evidence"]]
            page_refs += [(decision["document_id"], x["physical_pdf_page"])
                          for x in structure["transaction_review"]["asset_merge_clues"]]
        for evidence_doc, page in page_refs:
            if isinstance(page, int):
                expected = SOURCE_PAGES / f"{evidence_doc}_p{page:03d}.png"
                if not expected.exists():
                    missing_evidence_pages.append({"document_id": evidence_doc, "page": page})
    for review in company_scope_reviews:
        for item in review["source_evidence"]:
            evidence_doc, page = item.get("document_id"), item.get("physical_pdf_page")
            if isinstance(page, int):
                expected = SOURCE_PAGES / f"{evidence_doc}_p{page:03d}.png"
                if not expected.exists():
                    missing_evidence_pages.append({"document_id": evidence_doc, "page": page,
                                                   "review": review["subject"]})
    incomplete_statement_sets = [
        {"document_id": x["document_id"], "security_id": x["security_id"],
         "slot_id": x["slot_id"]}
        for x in scope_rows if not x["report_structure"]["main_statement_set_complete"]]
    parent_equiv_ids = {"DOC-6B0CAFDCCFF7978D", "DOC-52FA26EF30DFB266"}
    parent_equiv_results = [x for x in result_rows if x.get("document_id") in parent_equiv_ids]
    parent_equiv_metadata_ok = (
        {x.get("document_id") for x in parent_equiv_results} == parent_equiv_ids
        and all(x.get("statement_scope_original") == "GENERIC_SINGLE_ENTITY"
                and x.get("statement_scope_normalized_for_s00") == "CONSOLIDATED"
                and x.get("parent_review_resolution", {}).get("approved") is True
                and all(f.get("extract_status") != "STMT_SCOPE_HOLD"
                        for f in x.get("fields", []) if f.get("field_id") in CORE_FIELDS)
                for x in parent_equiv_results)
    )
    summary = {
        "status": "SELF_CHECK",
        "documents": len(tasks_by_doc),
        "corrected_results": len(list(OUT.glob("DOC-*.json"))),
        "scope_release_documents": sum(x["status"] in {"RELEASED_CONSOLIDATED", "RELEASED_EQUIVALENT_SCOPE"} for x in scope_rows),
        "scope_held_documents": sum(x["status"] not in {"RELEASED_CONSOLIDATED", "RELEASED_EQUIVALENT_SCOPE"} for x in scope_rows),
        "handoff_state": "SOURCE_FINALIZED_READY_FOR_INTEGRATION",
        "external_source_metadata": external_source_manifest,
        "parent_approved_equivalent_scope_released": [
            {"document_id": x["document_id"], "status": x["status"],
             "scope_mapping": x.get("s00_scope_mapping")}
            for x in scope_rows if x["status"] == "RELEASED_EQUIVALENT_SCOPE"],
        "source_correction_rows": len(corrections),
        "recovered_value_rows": len(recovered),
        "crosscheck_results": crosscheck_rows,
        "crosscheck_mismatches": mismatches,
        "crosscheck_unavailable": crosscheck_unavailable,
        "scope_held_core_values_leaked": held_values_leaked,
        "summary_fallback_fields": summary_fallback_fields,
        "incomplete_main_statement_sets": incomplete_statement_sets,
        "missing_rendered_scope_evidence_pages": missing_evidence_pages,
        "checks": {
            "exactly_20_documents": len(tasks_by_doc) == 20,
            "one_corrected_json_per_document": len(list(OUT.glob("DOC-*.json"))) == len(tasks_by_doc),
            "scope_held_core_values_blank": len(held_values_leaked) == 0,
            "parent_approved_equivalent_scope_released": {
                x["document_id"] for x in scope_rows if x["status"] == "RELEASED_EQUIVALENT_SCOPE"
            } == {"DOC-6B0CAFDCCFF7978D", "DOC-52FA26EF30DFB266"},
            "parent_approved_equivalent_results_preserve_scope_and_release_fields": parent_equiv_metadata_ok,
            "external_source_metadata_does_not_fabricate_hashes": all(
                (x["retrieval_status"] == "DOWNLOADED" and x.get("bytes") is not None and x.get("sha256"))
                or (x["retrieval_status"] != "DOWNLOADED" and x.get("bytes") is None and x.get("sha256") is None)
                for x in external_source_manifest),
            "external_source_manifest_written_and_cited": (
                (EXTERNAL_SOURCES / "manifest.json").exists()
                and all(x.get("url") and x.get("source_quote") and x.get("source_page") == 1
                        for x in external_source_manifest)
            ),
            "bluearrow_h1_scope_stays_held_without_exact_completion_date": any(
                x["document_id"] == "DOC-49C039910AC36BAC"
                and x["status"] == "STMT_SCOPE_HOLD"
                and x["report_structure"]["transaction_review"]["completion_check"]["completion_date_or_transfer_registration_found"] is False
                for x in scope_rows),
            "no_summary_fallback_for_statement_fields": len(summary_fallback_fields) == 0,
            "all_main_statement_sets_located": len(incomplete_statement_sets) == 0,
            "all_scope_evidence_pages_rendered": len(missing_evidence_pages) == 0,
            "no_numeric_statement_summary_mismatches": len(mismatches) == 0,
        },
        "claims": [
            "Scope-held candidates are blanked from corrected_results and retained in evidence/recovered_values.csv.",
            "Explicit consolidated titles and parent-approved full-reporting-entity equivalents are released as EXTRACTED, with generic source titles preserved for the latter.",
            "BYD H1 statement units are千元; key financial-data table figures are元.",
            "No S00 standardization, S03 screening, formula change, or production-code edit was performed.",
        ],
    }
    summary["all_checks_pass"] = all(summary["checks"].values())
    summary["status"] = "SELF_CHECK_PASS" if summary["all_checks_pass"] else "SELF_CHECK_FAIL"
    (HERE / "SELF_CHECK.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
