from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

INTEGRATION = Path(__file__).resolve().parent
RECOVERY = INTEGRATION.parent
ROOT = next(p for p in Path(__file__).resolve().parents
            if (p / "tools" / "s01_rules_check.py").is_file())
sys.path.insert(0, str(INTEGRATION))

import comparability_adapter as C  # noqa: E402


def hold_spec():
    return {
        "version": C.EXPECTED_VERSION,
        "review_nature": "SELF_CHECK",
        "tag": C.EXPECTED_TAG,
        "basis": "synthetic adapter boundary test",
        "s03_release": False,
        "holds": [{
            "security_id": "SZ:002083",
            "period_key": "20260930",
            "document_id": "DOC-9DE6D7E8F6A6333C",
            "source_pdf": "sources/collection/originals/002083/q3_2026/DOC-9DE6D7E8F6A6333C.pdf",
            "source_sha256": "0" * 64,
            "source_page": 4,
            "evidence": "2026年8月新增纳入合并范围",
            "reason": "synthetic",
            "action": C.EXPECTED_ACTION,
            "release_condition": "external scope evidence",
        }],
    }


def norm_row(sec, period, field, basis, status, source_kind, value, **extra):
    row = {
        "security_id": sec,
        "period_key": period,
        "field_id": field,
        "period_basis": basis,
        "status": status,
        "source_kind": source_kind,
        "value_cny": value,
        "consolidation_scope": "CONSOLIDATED",
        "comparability_note": "",
        "upstream_hold_fields": "",
    }
    row.update(extra)
    return row


class ComparabilityAdapterTests(unittest.TestCase):
    def test_parent_hold_spec_is_registered_and_self_check_only(self):
        spec_path = RECOVERY / "comparability_holds.json"
        self.assertTrue(spec_path.is_file())
        spec = C.load_scope_hold_spec(spec_path)
        self.assertEqual(spec["version"], "RECOVERY18_SOURCE_COMPARABILITY_GUARD_20261030")
        self.assertFalse(spec["s03_release"])
        self.assertEqual(len(spec["holds"]), 1)
        self.assertEqual(spec["holds"][0]["security_id"], "SZ:002083")
        self.assertEqual(spec["holds"][0]["period_key"], "20260930")
        with self.assertRaisesRegex(ValueError, "escapes repository root"):
            C.verify_hold_source_files(spec, ROOT)

    def test_normalized_adapter_tags_all_period_rows_and_holds_only_cumulative_sq(self):
        rows = [
            norm_row("SZ:002083", "20260930", "FIN.REV.YTD", "YTD_CUMULATIVE",
                     "EXTRACTED", "OFFICIAL_PDF", "100", comparability_note="EXISTING_NOTE"),
            norm_row("SZ:002083", "20260930", "FIN.REV.SQ", "SINGLE_QUARTER",
                     "EXTRACTED_QUARTERLY_TABLE", "OFFICIAL_QUARTERLY_TABLE", "35"),
            norm_row("SZ:002083", "20260930", "FIN.NPP.SQ", "SINGLE_QUARTER",
                     "EXTRACTED_QUARTERLY_TABLE", "OFFICIAL_QUARTERLY_TABLE", "7"),
            norm_row("SZ:002083", "20260930", "FIN.NPDEDT.SQ", "SINGLE_QUARTER",
                     "EXTRACTED_QUARTERLY_TABLE", "OFFICIAL_QUARTERLY_TABLE", "6"),
            norm_row("SZ:002083", "20260930", "FIN.OCF.SQ", "SINGLE_QUARTER",
                     "DERIVED_CUMULATIVE_DIFF", "DERIVED_DIFF", "9"),
            norm_row("SZ:002083", "20260930", "FIN.CONTRACTASSET.INSTANT", "INSTANT",
                     "NOT_APPLICABLE", "NOT_IN_STATEMENT", ""),
            norm_row("SH:000001", "20260930", "FIN.REV.YTD", "YTD_CUMULATIVE",
                     "EXTRACTED", "OFFICIAL_PDF", "88"),
            norm_row("SZ:002083", "20260630", "FIN.REV.YTD", "YTD_CUMULATIVE",
                     "EXTRACTED", "OFFICIAL_PDF", "65"),
        ]
        before = [dict(row) for row in rows]
        transformed, stats = C.apply_normalized_scope_holds(rows, hold_spec())
        self.assertEqual(stats["tagged_row_count"], 6)
        self.assertEqual(stats["derived_sq_hold_count"], 1)
        for idx in (0, 1, 2, 3, 4, 5):
            self.assertIn(C.EXPECTED_TAG, transformed[idx]["comparability_note"])
        for idx in (6, 7):
            self.assertEqual(transformed[idx], before[idx])

        # Keep reported amounts and actual consolidated scope exactly as received.
        for idx in (0, 1, 2, 3, 4, 5):
            self.assertEqual(transformed[idx]["value_cny"], before[idx]["value_cny"])
            self.assertEqual(transformed[idx]["source_kind"], before[idx]["source_kind"])
            self.assertEqual(transformed[idx]["consolidation_scope"], "CONSOLIDATED")
        for idx in (1, 2, 3):
            self.assertEqual(transformed[idx]["status"], before[idx]["status"])
        self.assertEqual(transformed[5]["status"], "NOT_APPLICABLE")
        self.assertEqual(transformed[4]["status"], C.DERIVED_HOLD_STATUS)
        self.assertEqual(transformed[4]["value_cny"], "9")
        self.assertEqual(transformed[4]["upstream_hold_fields"],
                         "SOURCE_SCOPE_CHANGE_HOLD:DOC-9DE6D7E8F6A6333C:p4")
        self.assertEqual(transformed[4]["source_kind"], "DERIVED_DIFF")
        self.assertNotIn("EXTRACTED_XCHECK_MISMATCH", transformed[4]["upstream_hold_fields"])

    def test_s01_input_guard_only_holds_previously_ok_tagged_comparisons(self):
        def original_inputs(recs):
            if any(rec is None for rec in recs):
                return "MISSING", {"Q02"}
            if any(rec.get("status") == "NOT_APPLICABLE" for rec in recs):
                return "NOT_APPLICABLE", {"Q13"}
            if any(rec.get("status") in {"EXTRACTED_XCHECK_MISMATCH", "DERIVED_HOLD_UPSTREAM"}
                   for rec in recs):
                return "HOLD", {"Q01"}
            return "OK", set()

        module = SimpleNamespace(_inputs=original_inputs)
        original, stats = C.install_s01_inputs_guard(module)
        try:
            tagged_ok = {"status": "EXTRACTED", "comparability": C.EXPECTED_TAG}
            self.assertEqual(module._inputs([tagged_ok]), ("HOLD", {"Q01"}))

            non_target_ok = {"status": "EXTRACTED", "comparability": ""}
            self.assertEqual(module._inputs([non_target_ok]), ("OK", set()))

            # The wrapper cannot promote a missing or not-applicable input to HOLD.
            self.assertEqual(module._inputs([None]), ("MISSING", {"Q02"}))
            tagged_na = {"status": "NOT_APPLICABLE", "comparability": C.EXPECTED_TAG}
            self.assertEqual(module._inputs([tagged_na]), ("NOT_APPLICABLE", {"Q13"}))

            # Existing source HOLD remains exactly the original HOLD with Q01.
            preexisting_hold = {"status": "EXTRACTED_XCHECK_MISMATCH",
                                "comparability": C.EXPECTED_TAG}
            self.assertEqual(module._inputs([preexisting_hold]), ("HOLD", {"Q01"}))
        finally:
            C.restore_s01_inputs_guard(module, original)
        self.assertIs(module._inputs, original_inputs)
        self.assertEqual(stats["scope_tag_calls"], 1)
        self.assertEqual(stats["scope_hold_calls"], 1)
        self.assertEqual(stats["preserved_non_ok_calls"], 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
