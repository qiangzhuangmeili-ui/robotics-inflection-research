from __future__ import annotations

import importlib.util
import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace

INTEGRATION = Path(__file__).resolve().parent
ROOT = next(p for p in Path(__file__).resolve().parents
            if (p / "tools" / "s02_calculate.py").is_file())
sys.path.insert(0, str(INTEGRATION))
sys.path.insert(0, str(ROOT / "tools"))

SPEC = importlib.util.spec_from_file_location("recovery18_replay_metrics_v3_under_test",
                                               INTEGRATION / "replay_metrics_v3.py")
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Cannot load replay_metrics_v3.py for boundary tests")
R = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = R
SPEC.loader.exec_module(R)


def hold_spec():
    return {
        "holds": [{
            "security_id": "SZ:002083",
            "period_key": "20260930",
            "document_id": "DOC-9DE6D7E8F6A6333C",
            "source_page": 4,
        }],
    }


def tagged_row(field_id, period_basis, source_kind, status, **extra):
    row = {
        "security_id": "SZ:002083",
        "period_key": "20260930",
        "field_id": field_id,
        "period_basis": period_basis,
        "source_kind": source_kind,
        "status": status,
        "comparability_note": R.EXPECTED_TAG,
        "upstream_hold_fields": "",
    }
    row.update(extra)
    return row


def adapter_stats():
    return {
        "tagged_row_count": 5,
        "derived_sq_hold_count": 1,
        "holds": [{
            "security_id": "SZ:002083",
            "period_key": "20260930",
            "matched_row_count": 5,
            "derived_sq_hold_fields": ["FIN.OCF.SQ"],
            "preserved_non_cumulative_sq_fields": ["FIN.REV.SQ", "FIN.NPP.SQ", "FIN.NPDEDT.SQ"],
        }],
    }


class ReplayMetricsV3Tests(unittest.TestCase):
    def test_replay_q16_override_matches_v3_note_and_preserves_check_decision(self):
        captured = []

        def add(cid, item, ok, detail, blocking=True, result_override=None):
            captured.append((cid, item, ok, detail, blocking, result_override))

        module = SimpleNamespace(add=add)
        original, stats = R.install_q16_note_override(module, R.Q16_NOTE_OVERRIDE)
        try:
            module.add("Q16", "coverage", False, {"note": "stale", "count": 53}, False, "WARN")
        finally:
            R.restore_q16_note_override(module, original)
        self.assertEqual(stats["calls"], 1)
        self.assertEqual(captured[0][:3], ("Q16", "coverage", False))
        self.assertEqual(captured[0][3], {"note": R.Q16_NOTE_OVERRIDE, "count": 53})
        self.assertEqual(captured[0][4:], (False, "WARN"))
        with self.assertRaisesRegex(ValueError, "differs from the registered recovery wording"):
            R.install_q16_note_override(module, "different wording")

    def test_cli_stays_inert_without_execute(self):
        output = io.StringIO()
        with redirect_stdout(output):
            result = R.main([])
        self.assertEqual(result, 2)
        self.assertIn("PREPARED_NOT_RUN", output.getvalue())

    def test_default_and_explicit_output_paths_stay_inside_integration(self):
        self.assertEqual(R.resolve_output_path(None), (INTEGRATION / "s02_replay_v3").resolve())
        explicit = "runs/issues/S02/recovery18_20261029/integration/replay_retry"
        self.assertEqual(R.resolve_output_path(explicit), (ROOT / explicit).resolve())
        with self.assertRaisesRegex(ValueError, "child of"):
            R.resolve_output_path("runs/issues/S02/forbidden")

    def test_scope_tag_and_direct_and_derived_rows_match_locked_manifest(self):
        rows = [
            tagged_row("FIN.REV.YTD", "YTD_CUMULATIVE", "OFFICIAL_PDF", "EXTRACTED"),
            tagged_row("FIN.REV.SQ", "SINGLE_QUARTER", "OFFICIAL_QUARTERLY_TABLE", "EXTRACTED_QUARTERLY_TABLE"),
            tagged_row("FIN.NPP.SQ", "SINGLE_QUARTER", "OFFICIAL_QUARTERLY_TABLE", "EXTRACTED_QUARTERLY_TABLE"),
            tagged_row("FIN.NPDEDT.SQ", "SINGLE_QUARTER", "OFFICIAL_QUARTERLY_TABLE", "EXTRACTED_QUARTERLY_TABLE"),
            tagged_row("FIN.OCF.SQ", "SINGLE_QUARTER", "DERIVED_DIFF", "DERIVED_HOLD_UPSTREAM",
                       upstream_hold_fields="SOURCE_SCOPE_CHANGE_HOLD:DOC-9DE6D7E8F6A6333C:p4"),
        ]
        result = R.validate_scope_tag_rows(rows, hold_spec(), adapter_stats())
        self.assertEqual(result["tagged_row_count"], 5)
        self.assertEqual(result["derived_sq_hold_count"], 1)

    def test_rejects_unregistered_scope_tag_or_unheld_derived_value(self):
        rows = [
            tagged_row("FIN.REV.YTD", "YTD_CUMULATIVE", "OFFICIAL_PDF", "EXTRACTED"),
            tagged_row("FIN.REV.SQ", "SINGLE_QUARTER", "OFFICIAL_QUARTERLY_TABLE", "EXTRACTED_QUARTERLY_TABLE"),
            tagged_row("FIN.NPP.SQ", "SINGLE_QUARTER", "OFFICIAL_QUARTERLY_TABLE", "EXTRACTED_QUARTERLY_TABLE"),
            tagged_row("FIN.NPDEDT.SQ", "SINGLE_QUARTER", "OFFICIAL_QUARTERLY_TABLE", "EXTRACTED_QUARTERLY_TABLE"),
            tagged_row("FIN.OCF.SQ", "SINGLE_QUARTER", "DERIVED_DIFF", "DERIVED_HOLD_UPSTREAM",
                       upstream_hold_fields="SOURCE_SCOPE_CHANGE_HOLD:DOC-9DE6D7E8F6A6333C:p4"),
        ]
        rows[0]["security_id"] = "SZ:000001"
        with self.assertRaisesRegex(ValueError, "Unregistered scope tag"):
            R.validate_scope_tag_rows(rows, hold_spec(), adapter_stats())
        rows[0]["security_id"] = "SZ:002083"
        rows[-1]["status"] = "DERIVED_CUMULATIVE_DIFF"
        with self.assertRaisesRegex(ValueError, "remains unheld"):
            R.validate_scope_tag_rows(rows, hold_spec(), adapter_stats())

    def test_canonical_comparison_reports_bytes_and_fields_separately(self):
        canonical = b"\xef\xbb\xbfsecurity_id,value\r\nSZ:1,12\r\n"
        exact = R.compare_csv_payloads(canonical, canonical)
        self.assertTrue(exact["byte_equal"])
        self.assertTrue(exact["full_field_rows_equal"])
        newline_only = R.compare_csv_payloads(canonical, canonical.replace(b"\r\n", b"\n"))
        self.assertFalse(newline_only["byte_equal"])
        self.assertTrue(newline_only["full_field_rows_equal"])
        changed = R.compare_csv_payloads(canonical, canonical.replace(b"12", b"13"))
        self.assertFalse(changed["full_field_rows_equal"])

    def test_registered_pdf_identity_is_crosschecked_without_pdf_io(self):
        source_sha = "a" * 64
        spec = {"holds": [{
            "security_id": "SZ:002083", "period_key": "20260930",
            "document_id": "DOC-9DE6D7E8F6A6333C", "source_pdf": "sources/doc.pdf",
            "source_sha256": source_sha, "source_page": 4,
        }]}
        guard = {"verified_scope_source_pdfs": [{
            "security_id": "SZ:002083", "period_key": "20260930",
            "document_id": "DOC-9DE6D7E8F6A6333C", "source_pdf": "sources/doc.pdf",
            "expected_sha256": source_sha, "actual_sha256": source_sha, "source_page": "4",
        }]}
        result = R.verify_registered_pdf_metadata(spec, guard)
        self.assertEqual(result[0]["read_during_replay"], "NO")
        guard["verified_scope_source_pdfs"][0]["actual_sha256"] = "b" * 64
        with self.assertRaisesRegex(ValueError, "hash/page record differs"):
            R.verify_registered_pdf_metadata(spec, guard)


if __name__ == "__main__":
    unittest.main(verbosity=2)
