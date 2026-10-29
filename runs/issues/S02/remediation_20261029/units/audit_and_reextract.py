#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Re-extract the latest and same-period base NPDEDT values for six S02 findings.

Reads source PDFs already in the collection cache. It writes new, traceable evidence
under this remediation folder and never edits normalized inputs or S02 deliverables.
"""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pypdfium2 as pdfium
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[5]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
import a03_financial_field_extractor as extractor  # noqa: E402

CASES = {
    "SZ:000333": {
        "code": "000333", "name": "美的集团", "slot": "h1_2026",
        "base_slot": "h1_2025", "expected": {
            "h1_2025": ("26,235,399", "千元", 7),
            "h1_2026": ("19,595,179", "千元", 7),
        },
    },
    "SZ:002460": {
        "code": "002460", "name": "赣锋锂业", "slot": "q3_2026",
        "base_slot": "q3_2025", "expected": {
            "q3_2025": ("-941,980,290.41", "元", 2),
            "q3_2026": ("4,635,869,494.31", "元", 2),
        },
    },
    "SZ:300678": {
        "code": "300678", "name": "中科信息", "slot": "q3_2026",
        "base_slot": "q3_2025", "expected": {
            "q3_2025": ("1,971,597.85", "元", 1),
            "q3_2026": ("7,835,325.36", "元", 1),
        },
    },
    "SZ:301041": {
        "code": "301041", "name": "金百泽", "slot": "q3_2026",
        "base_slot": "q3_2025", "expected": {
            "q3_2025": ("747,312.01", "元", 2),
            "q3_2026": ("31,367,387.91", "元", 2),
        },
    },
    "SZ:300420": {
        "code": "300420", "name": "五洋自控", "slot": "q3_2026",
        "base_slot": "q3_2025", "expected": {
            "q3_2025": ("5,511,036.95", "元", 2),
            "q3_2026": ("-19,766,096.84", "元", 2),
        },
    },
    "SZ:002420": {
        "code": "002420", "name": "毅昌科技", "slot": "q3_2026",
        "base_slot": "q3_2025", "expected": {
            "q3_2025": ("27,304,781.59", "元", 2),
            "q3_2026": ("68,656,177.77", "元", 2),
        },
    },
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    evidence_dir = OUT / "evidence_pages"
    evidence_dir.mkdir(exist_ok=True)
    index_rows = read_csv(ROOT / "runs/collection/collection_index.csv")
    old_rows = read_csv(ROOT / "runs/issues/S00/financial_normalized.csv")
    index = {(r["security_id"], r["slot_id"]): r for r in index_rows}
    old = {(r["security_id"], r["period_key"], r["field_id"]): r for r in old_rows}

    extracted_rows: list[dict] = []
    comparison_rows: list[dict] = []
    evidence_text: list[str] = [
        "S02 unit/column remediation: source page text (pypdf extraction)",
        "Physical page numbers below are the printed page numbers visible on the same page.",
    ]
    source_fingerprints: list[dict] = []
    checks: list[dict] = []

    for security_id, case in CASES.items():
        for slot in (case["base_slot"], case["slot"]):
            source = index[(security_id, slot)]
            pdf_path = ROOT / source["local_file"]
            if not pdf_path.is_file():
                raise FileNotFoundError(pdf_path)
            task = {
                "document_id": source["document_id"],
                "security_id": security_id,
                "stock_code": case["code"],
                "slot_id": slot,
                "period_label": source["period_label"],
                "path": str(pdf_path),
            }
            result = extractor.extract_one(task)
            row = next(r for r in result["fields"] if r["field_id"] == "FIN.NPDEDT.YTD")
            exp_raw, exp_unit, exp_page = case["expected"][slot]
            passed = (row["value_raw"] == exp_raw and row["unit_raw"] == exp_unit
                      and int(row["page"]) == exp_page)
            checks.append({
                "check": "REEXTRACTION_MATCHES_REVIEWED_SOURCE_ROW",
                "security_id": security_id, "slot_id": slot,
                "expected_raw": exp_raw, "actual_raw": row["value_raw"],
                "expected_unit": exp_unit, "actual_unit": row["unit_raw"],
                "expected_physical_page": exp_page, "actual_physical_page": row["page"],
                "result": "PASS" if passed else "FAIL",
            })
            if not passed:
                raise AssertionError(checks[-1])

            period_key = "20260630" if slot == "h1_2026" else (
                "20250630" if slot == "h1_2025" else
                ("20260930" if slot == "q3_2026" else "20250930")
            )
            prior = old.get((security_id, period_key, "FIN.NPDEDT.YTD"), {})
            local_case = {
                "security_id": security_id, "stock_code": case["code"],
                "stock_name": case["name"], "period_key": period_key,
                "period_label": source["period_label"], "slot_id": slot,
                "field_id": "FIN.NPDEDT.YTD", "old_value_raw": prior.get("value_raw", ""),
                "old_unit_raw": prior.get("unit_raw", ""),
                "old_value_cny": prior.get("value_cny", ""),
                "new_value_raw": row["value_raw"], "new_unit_raw": row["unit_raw"],
                "new_unit_scale": row["unit_scale"], "new_value_cny": row["value_cny"],
                "status": row["extract_status"], "document_id": source["document_id"],
                "source_page_physical": row["page"], "evidence_label": row["evidence_label"],
                "pdf_sha256": sha256(pdf_path), "primary_url": source["primary_url"],
                "old_value_disposition": "UNCHANGED" if (
                    prior.get("value_raw") == row["value_raw"]
                    and prior.get("unit_raw") == row["unit_raw"]
                ) else "REPLACE_AFTER_S00_RECOMPUTE",
            }
            extracted_rows.append(local_case)
            comparison_rows.append(local_case.copy())
            source_fingerprints.append({
                "document_id": source["document_id"], "path": source["local_file"],
                "sha256": local_case["pdf_sha256"], "primary_url": source["primary_url"],
                "printed_physical_page": exp_page,
            })

            reader = PdfReader(str(pdf_path))
            page_text = reader.pages[exp_page - 1].extract_text() or ""
            # The exact line is captured as context, retaining the table row and unit header.
            lines = page_text.splitlines()
            hits = [i for i, line in enumerate(lines)
                    if "扣除非经常性损益" in line or exp_raw in line]
            lo = max(0, min(hits, default=0) - 4)
            hi = min(len(lines), (max(hits) + 8) if hits else min(len(lines), 45))
            evidence_text.extend([
                "", f"=== {case['name']} {source['period_label']} ===",
                f"security_id={security_id}; document_id={source['document_id']}; "
                f"physical_page={exp_page}; sha256={local_case['pdf_sha256']};",
                f"official_url={source['primary_url']}",
                *lines[lo:hi],
            ])

            # Render the source page as it appears in the PDF for a visual audit trail.
            pdf_doc = pdfium.PdfDocument(str(pdf_path))
            page = pdf_doc[exp_page - 1]
            bitmap = page.render(scale=2.0)
            image = bitmap.to_pil()
            image.save(evidence_dir / f"{case['code']}_{slot}_p{exp_page:03d}.png")
            pdf_doc.close()

    write_csv(OUT / "normalized_corrections.csv", extracted_rows,
              list(extracted_rows[0].keys()))
    write_csv(OUT / "reextraction_checks.csv", checks, list(checks[0].keys()))
    (OUT / "source_rows.txt").write_text("\n".join(evidence_text) + "\n", encoding="utf-8")

    unit_checks = []
    for sample, expected in (
        ("单位：人民币元", "元"), ("单位为人民币千元", "千元"),
        ("金额单位为人民币千元", "千元"),
    ):
        got = extractor.detect_unit([sample])
        unit_checks.append({"input": sample, "expected": expected, "actual": got,
                            "result": "PASS" if got == expected else "FAIL"})
    if any(r["result"] != "PASS" for r in unit_checks):
        raise AssertionError(unit_checks)

    comparison_fields = list(comparison_rows[0].keys())
    write_csv(OUT / "old_vs_source_reextraction.csv", comparison_rows, comparison_fields)
    (OUT / "review.json").write_text(json.dumps({
        "issue": "S02 remediation: units and summary-table value-column selection",
        "review_nature": "SELF_CHECK_SOURCE_PAGE_REEXTRACTION",
        "status": "SELF_CHECK_PASS_WITH_SOURCE_BACKED_CORRECTIONS",
        "companies": len(CASES), "period_rows": len(extracted_rows),
        "latest_rows_corrected": sum(r["old_value_disposition"] != "UNCHANGED"
                                      for r in extracted_rows if r["slot_id"].endswith("2026")),
        "same_period_base_rows": sum(r["slot_id"].endswith("2025") for r in extracted_rows),
        "period_rows_checked": len(checks), "period_rows_pass": sum(
            r["result"] == "PASS" for r in checks),
        "unit_parser_cases": unit_checks,
        "source_pdf_fingerprints": source_fingerprints,
        "completed_at": datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds"),
        "limitations": [
            "This package contains source-backed replacement rows only; it does not edit S00 normalized inputs or recalculate S02 metrics.",
            "All results are a technical self-check by one executor; independent review remains pending.",
            "The comparison base is the same fiscal period: H1 2025 for Midea, Q3 2025 for the other five.",
        ],
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
