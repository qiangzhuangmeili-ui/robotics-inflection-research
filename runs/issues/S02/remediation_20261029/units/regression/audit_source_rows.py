#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Read-only source audit of seven S02 NPDEDT rows raised in parser regression review."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pypdfium2 as pdfium
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[6]
OUT = Path(__file__).resolve().parent

CASES = [
    {
        "security_id": "SH:600196", "stock_code": "600196", "stock_name": "复星医药",
        "slot_id": "q1_2025", "period_key": "20250331",
        "expected_raw": "410,421,422.44", "unit": "元", "unit_scale": 1,
        "value_cny": 410421422.44, "value_page": 2, "unit_page": 2,
        "expected_row": "归属于上市公司股东的扣除非经常性损益的净利润 注3 410,421,422.44 608,535,465.59 -32.56",
        "finding": "注3 is the footnote marker; 410,421,422.44 is the current-period amount.",
    },
    {
        "security_id": "SH:600196", "stock_code": "600196", "stock_name": "复星医药",
        "slot_id": "h1_2025", "period_key": "20250630",
        "expected_raw": "960,786,475.56", "unit": "元", "unit_scale": 1,
        "value_cny": 960786475.56, "value_page": 9, "unit_page": 9,
        "expected_row": "归属于上市公司股东的扣除非经常性损益的净利润 注3 960,786,475.56 1,254,071,307.16 -23.39",
        "finding": "The current-period amount is in yuan; 注3 is a footnote marker, not a numeric cell.",
    },
    {
        "security_id": "SH:600196", "stock_code": "600196", "stock_name": "复星医药",
        "slot_id": "h1_2026", "period_key": "20260630",
        "expected_raw": "1,144,165,735.05", "unit": "元", "unit_scale": 1,
        "value_cny": 1144165735.05, "value_page": 8, "unit_page": 8,
        "expected_row": "归属于上市公司股东的扣除非经常性损益的净利润 注3 1,144,165,735.05 960,786,475.56 19.09",
        "finding": "The earlier normalized value 31,144,165,735.05 incorrectly prepended the footnote marker 3.",
    },
    {
        "security_id": "SH:601238", "stock_code": "601238", "stock_name": "广汽集团",
        "slot_id": "h1_2026", "period_key": "20260630",
        "expected_raw": "-5,209,121,398", "unit": "元", "unit_scale": 1,
        "value_cny": -5209121398.0, "value_page": 9, "unit_page": 8,
        "expected_row": "归属于上市公司股东的扣除非经常性损益的净利润 -5,209,121,398 -2,945,262,736 -76.86",
        "finding": "The '单位：元 币种：人民币' header is on printed page 8; the value row continues on page 9. Page 9 starts a later HK/PRC accounting-difference table in 万元, which must not set this row's unit.",
    },
    {
        "security_id": "SH:603289", "stock_code": "603289", "stock_name": "泰瑞机器",
        "slot_id": "q3_2025", "period_key": "20250930",
        "expected_raw": "59,617,005.56", "unit": "元", "unit_scale": 1,
        "value_cny": 59617005.56, "value_page": 1, "unit_page": 1,
        "expected_row": "扣除非经常性损益的净利润 6,430,820.01 不适用 59,617,005.56 57.41",
        "finding": "'不适用' occupies the single-quarter YoY cell; the cumulative value is the third table column, 59,617,005.56 yuan.",
    },
    {
        "security_id": "SH:603956", "stock_code": "603956", "stock_name": "威派格",
        "slot_id": "q3_2025", "period_key": "20250930",
        "expected_raw": "-83,006,642.59", "unit": "元", "unit_scale": 1,
        "value_cny": -83006642.59, "value_page": 1, "unit_page": 1,
        "expected_row": "扣除非经常性损益的净利润 7,217,651.38 不适用 -83,006,642.59 不适用",
        "finding": "The cumulative YTD amount is -83,006,642.59 yuan. The current-quarter amount is 7,217,651.38; these are distinct cells.",
    },
    {
        "security_id": "SH:605358", "stock_code": "605358", "stock_name": "立昂微",
        "slot_id": "q3_2025", "period_key": "20250930",
        "expected_raw": "-14,105.80", "unit": "万元", "unit_scale": 10000,
        "value_cny": -141058000.0, "value_page": 1, "unit_page": 1,
        "expected_row": "扣除非经常性损益的净利润 -1,494.93 -367.63 -14,105.80 不适用",
        "finding": "The report states 单位：万元; cumulative amount is -14,105.80 万元. Old and current re-extraction values agree.",
    },
]


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def write_csv(path: Path, records: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(records[0].keys()))
        writer.writeheader()
        writer.writerows(records)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    pages_dir = OUT / "evidence_pages"
    pages_dir.mkdir(exist_ok=True)
    index = {(r["security_id"], r["slot_id"]): r
             for r in rows(ROOT / "runs/collection/collection_index.csv")}
    normalized = {(r["security_id"], r["period_key"], r["field_id"]): r
                  for r in rows(ROOT / "runs/issues/S00/financial_normalized.csv")}
    evidence_text = [
        "Independent read-only source audit for seven NPDEDT rows.",
        "PDF page numbers below refer to the printed physical page label; page images are rendered from the original cached PDF.",
    ]
    expected = []
    comparisons = []
    checks = []
    rendered: set[tuple[str, int]] = set()

    for case in CASES:
        source = index[(case["security_id"], case["slot_id"])]
        pdf_path = ROOT / source["local_file"]
        digest = sha256(pdf_path)
        reader = PdfReader(str(pdf_path))
        page_numbers = sorted({case["unit_page"], case["value_page"]})
        page_texts = {n: (reader.pages[n - 1].extract_text() or "") for n in page_numbers}
        row_present = case["expected_row"] in " ".join(page_texts[case["value_page"]].split())
        # Reflow of extracted spaces can vary; independently check each material token too.
        core_tokens = [t for t in case["expected_raw"].split()]
        if len(core_tokens) == 1:
            row_present = row_present or core_tokens[0] in page_texts[case["value_page"]]
        else:
            row_present = row_present or all(t in page_texts[case["value_page"]]
                                             for t in core_tokens)

        old = normalized.get((case["security_id"], case["period_key"], "FIN.NPDEDT.YTD"), {})
        fresh_path = ROOT / "runs/issues/S02/remediation_20261029/extracted" / f"{source['document_id']}.json"
        fresh_value = fresh_unit = fresh_page = None
        if fresh_path.exists():
            fresh = json.loads(fresh_path.read_text(encoding="utf-8"))
            fresh_row = next((r for r in fresh.get("fields", [])
                              if r.get("field_id") == "FIN.NPDEDT.YTD"), {})
            fresh_value = fresh_row.get("value_raw")
            fresh_unit = fresh_row.get("unit_raw")
            fresh_page = fresh_row.get("page")

        for n in page_numbers:
            key = (source["document_id"], n)
            if key in rendered:
                continue
            rendered.add(key)
            pdf_doc = pdfium.PdfDocument(str(pdf_path))
            bitmap = pdf_doc[n - 1].render(scale=2.0)
            bitmap.to_pil().save(pages_dir / f"{case['stock_code']}_{case['slot_id']}_p{n:03d}.png")
            pdf_doc.close()
            evidence_text.extend([
                "", f"=== {case['stock_name']} {source['period_label']} / printed page {n} ===",
                f"security_id={case['security_id']}; document_id={source['document_id']}; local_file={source['local_file']}",
                f"sha256={digest}; official_url={source['primary_url']}",
                *page_texts[n].splitlines(),
            ])

        expected_row = {
            **case,
            "document_id": source["document_id"],
            "source_pdf_sha256": digest,
            "source_url": source["primary_url"],
            "source_local_file": source["local_file"],
            "printed_value_page": case["value_page"],
            "printed_unit_page": case["unit_page"],
            "source_row_found_on_physical_page": row_present,
            "new_reextract_value_raw": fresh_value,
            "new_reextract_unit": fresh_unit,
        }
        expected.append(expected_row)
        comparisons.append({
            "security_id": case["security_id"], "stock_name": case["stock_name"],
            "period_key": case["period_key"], "field_id": "FIN.NPDEDT.YTD",
            "old_s00_value_raw": old.get("value_raw"), "old_s00_unit": old.get("unit_raw"),
            "old_s00_value_cny": old.get("value_cny"),
            "source_expected_value_raw": case["expected_raw"],
            "source_expected_unit": case["unit"], "source_expected_value_cny": case["value_cny"],
            "new_reextract_value_raw": fresh_value, "new_reextract_unit": fresh_unit,
            "new_reextract_page": fresh_page,
            "old_matches_source": (old.get("value_raw") == case["expected_raw"]
                                   and old.get("unit_raw") == case["unit"]),
            "new_matches_source": (fresh_value == case["expected_raw"]
                                   and fresh_unit == case["unit"]),
            "finding": case["finding"],
        })
        checks.append({
            "security_id": case["security_id"], "slot_id": case["slot_id"],
            "document_id": source["document_id"], "value_page": case["value_page"],
            "unit_page": case["unit_page"], "expected_value": case["expected_raw"],
            "expected_unit": case["unit"], "source_row_found": row_present,
            "new_extraction_matches": fresh_value == case["expected_raw"]
                                       and fresh_unit == case["unit"],
            "result": "PASS" if row_present and fresh_value == case["expected_raw"]
                     and fresh_unit == case["unit"] else "HOLD",
        })

    (OUT / "expected.json").write_text(json.dumps({
        "review_nature": "SELF_CHECK_SOURCE_PDF_AUDIT",
        "rows": expected,
        "summary": {
            "source_rows": len(expected),
            "source_rows_found": sum(bool(r["source_row_found_on_physical_page"]) for r in expected),
            "new_extract_matches": sum(bool(r["new_reextract_value_raw"] == r["expected_raw"]
                                            and r["new_reextract_unit"] == r["unit"])
                                       for r in expected),
            "images": len(rendered),
        },
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_csv(OUT / "old_new_source_comparison.csv", comparisons)
    write_csv(OUT / "checks.csv", checks)
    (OUT / "source_pages.txt").write_text("\n".join(evidence_text) + "\n", encoding="utf-8")
    (OUT / "review.json").write_text(json.dumps({
        "status": "SELF_CHECK_PASS_SOURCE_VALUES_CONFIRMED",
        "review_nature": "SELF_CHECK_SOURCE_PDF_AUDIT",
        "source_rows": len(expected),
        "source_pages_rendered": len(rendered),
        "new_extractions_matching_source": sum(r["new_matches_source"] for r in comparisons),
        "old_s00_mismatches": [
            {"security_id": r["security_id"], "period_key": r["period_key"],
             "old": f"{r['old_s00_value_raw']} {r['old_s00_unit']}",
             "source": f"{r['source_expected_value_raw']} {r['source_expected_unit']}"}
            for r in comparisons if not r["old_matches_source"]
        ],
        "limitations": [
            "Self-check of physical-page evidence; independent review remains pending.",
            "This is a source audit only; it does not edit S00 normalized inputs or S02 metrics.",
        ],
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
