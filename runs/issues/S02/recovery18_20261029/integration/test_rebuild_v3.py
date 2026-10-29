from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

INTEGRATION = Path(__file__).resolve().parent
ROOT = next(p for p in Path(__file__).resolve().parents
            if (p / "tools" / "s02_calculate.py").is_file())
sys.path.insert(0, str(ROOT / "tools"))

SPEC = importlib.util.spec_from_file_location("recovery18_rebuild_v3_under_test", INTEGRATION / "rebuild_v3.py")
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Cannot load rebuild_v3.py for boundary tests")
R = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = R
SPEC.loader.exec_module(R)


class RebuildV3BoundaryTests(unittest.TestCase):
    def test_q16_note_override_changes_only_local_explanation(self):
        received = []

        def add(cid, item, ok, detail, blocking=True, result_override=None):
            received.append((cid, item, ok, detail, blocking, result_override))

        module = SimpleNamespace(add=add)
        original, stats = R.install_q16_note_override(module)
        q16_detail = {"note": "A03 stale note", "other": "unchanged"}
        other_detail = {"note": "other check"}
        try:
            module.add("Q16", "coverage", False, q16_detail, False, "WARN")
            module.add("P05", "input", True, other_detail, True, None)
        finally:
            R.restore_q16_note_override(module, original)

        self.assertIs(module.add, add)
        self.assertEqual(stats["calls"], 1)
        self.assertEqual(received[0][:3], ("Q16", "coverage", False))
        self.assertEqual(received[0][3], {"note": R.Q16_NOTE_OVERRIDE, "other": "unchanged"})
        self.assertEqual(received[0][4:], (False, "WARN"))
        self.assertEqual(received[1], ("P05", "input", True, other_detail, True, None))
        self.assertEqual(q16_detail["note"], "A03 stale note")

    def test_empty_fields_allowed_only_for_identity_complete_v2_baseline(self):
        source = Path("synthetic-v2-image-only.json")
        task = {
            "security_id": "SZ:002083",
            "slot_id": "annual_2025",
            "document_id": "DOC-41A995E12934526B",
            "ledger_sha256": "a" * 64,
        }
        baseline = {
            "security_id": task["security_id"],
            "slot_id": task["slot_id"],
            "document_id": task["document_id"],
            "fields": [],
        }
        self.assertEqual(R.require_record_identity(baseline, source, allow_empty_fields=True),
                         (task["security_id"], task["slot_id"], task["document_id"]))
        R.validate_fields_against_task(baseline, task, source, allow_empty_fields=True)
        with self.assertRaisesRegex(R.InputNotReady, "no non-empty fields array"):
            R.validate_fields_against_task(baseline, task, source)

    def test_registered_image_only_baseline_matches_its_frozen_task(self):
        source = R.V2_EXTRACTED / "DOC-41A995E12934526B.json"
        self.assertTrue(source.is_file())
        record = R.read_json(source)
        self.assertEqual(record.get("fields"), [])
        plan = R.read_json(R.V2_PLAN)
        task = next(item for item in plan["tasks"]
                    if item.get("document_id") == "DOC-41A995E12934526B")
        R.validate_fields_against_task(record, task, source, allow_empty_fields=True)

    def test_legacy_d_drive_task_uses_exact_collection_index_local_pdf(self):
        task_doc = "DOC-08E9C620CE2D4DEC"
        plan = R.read_json(R.V2_PLAN)
        task = dict(next(item for item in plan["tasks"] if item.get("document_id") == task_doc))
        self.assertEqual(task["security_id"], "SZ:001239")
        self.assertEqual(task["slot_id"], "q3_2026")
        # Recreate the frozen legacy registration for this real collection-index
        # identity without altering the plan or the extraction JSON.
        task["path"] = (
            "D:\\StockResearchLab\\IndustryInflectionLab\\robotics_data\\collection\\originals"
            "\\001239\\q3_2026\\DOC-08E9C620CE2D4DEC.pdf"
        )
        collection_rows = R.read_csv(R.COLLECTION_INDEX_PATH)
        collection_index_sha = R.sha256(R.COLLECTION_INDEX_PATH)
        pdf_path, record = R.resolve_registered_source_pdf(task, collection_rows, collection_index_sha)
        self.assertEqual(record["actual_read_path"],
                         "sources/collection/originals/001239/q3_2026/DOC-08E9C620CE2D4DEC.pdf")
        self.assertEqual(pdf_path, ROOT / record["actual_read_path"])
        self.assertEqual(record["collection_index_sha256"], collection_index_sha)
        self.assertEqual(record["actual_pdf_sha256"], task["ledger_sha256"])
        self.assertEqual(record["actual_resolved_path"],
                         str((R.LEGACY_D_COLLECTION_ROOT / "001239" / "q3_2026" /
                              "DOC-08E9C620CE2D4DEC.pdf").resolve()))

    def test_scope_hold_uses_only_the_matching_approved_collection_record(self):
        plan = R.read_json(R.V2_PLAN)
        task = dict(next(item for item in plan["tasks"]
                         if item.get("document_id") == "DOC-9DE6D7E8F6A6333C"))
        collection_rows = R.read_csv(R.COLLECTION_INDEX_PATH)
        index_sha = R.sha256(R.COLLECTION_INDEX_PATH)
        _, resolved = R.resolve_registered_source_pdf(task, collection_rows, index_sha)
        source = {
            "kind": "recovery18_corrected_result",
            "security_id": task["security_id"], "slot_id": task["slot_id"],
            "document_id": task["document_id"],
            "registered_pdf_sha256": str(task["ledger_sha256"]).lower(),
            **resolved,
        }
        spec = R.C.load_scope_hold_spec(R.RECOVERY / "comparability_holds.json")
        verified = R.C.verify_hold_source_files(spec, ROOT, [source])
        self.assertEqual(len(verified), 1)
        self.assertEqual(verified[0]["source_pdf"], source["actual_read_path"])
        self.assertEqual(verified[0]["actual_resolved_path"], source["actual_resolved_path"])
        wrong_path = dict(source, actual_read_path="sources/collection/originals/000001/wrong.pdf")
        with self.assertRaisesRegex(ValueError, "Scope PDF path differs"):
            R.C.verify_hold_source_files(spec, ROOT, [wrong_path])

    def test_collection_index_identity_or_sha_mismatch_blocks_pdf_read(self):
        task = {
            "security_id": "SZ:001239", "slot_id": "q3_2026",
            "document_id": "DOC-08E9C620CE2D4DEC", "ledger_sha256": "a" * 64,
        }
        mismatched_sha_rows = [{
            "security_id": task["security_id"], "slot_id": task["slot_id"],
            "document_id": task["document_id"], "sha256": "b" * 64,
            "local_file": "sources/collection/originals/001239/q3_2026/example.pdf",
        }]
        with self.assertRaisesRegex(R.InputNotReady, "PDF SHA differs from the frozen task"):
            R.resolve_registered_source_pdf(task, mismatched_sha_rows, "c" * 64)
        with self.assertRaisesRegex(R.InputNotReady, "must match exactly once"):
            R.resolve_registered_source_pdf(task, [], "c" * 64)
        arbitrary_external_rows = [{
            "security_id": task["security_id"], "slot_id": task["slot_id"],
            "document_id": task["document_id"], "sha256": task["ledger_sha256"],
            "local_file": "D:\\arbitrary\\unregistered.pdf",
        }]
        with self.assertRaisesRegex(R.InputNotReady, "safe repository-relative path"):
            R.resolve_registered_source_pdf(task, arbitrary_external_rows, "c" * 64)

    def test_empty_baseline_with_wrong_identity_is_rejected(self):
        source = Path("synthetic-v2-image-only.json")
        task = {
            "security_id": "SZ:002083",
            "slot_id": "annual_2025",
            "document_id": "DOC-41A995E12934526B",
            "ledger_sha256": "a" * 64,
        }
        wrong_identity = {
            "security_id": "SZ:000001",
            "slot_id": task["slot_id"],
            "document_id": task["document_id"],
            "fields": [],
        }
        with self.assertRaisesRegex(R.InputNotReady, "does not match frozen task identity"):
            R.validate_fields_against_task(wrong_identity, task, source, allow_empty_fields=True)

    def test_empty_identity_fields_are_not_allowed_for_recovery_corrections(self):
        correction = {
            "security_id": "SZ:002083",
            "slot_id": "annual_2025",
            "document_id": "DOC-41A995E12934526B",
            "fields": [],
        }
        with self.assertRaisesRegex(R.InputNotReady, "no non-empty fields array"):
            R.require_record_identity(correction, Path("synthetic-correction.json"))

    def test_default_output_resolves_inside_integration_directory(self):
        self.assertEqual(R.resolve_output_path(None), (INTEGRATION / "v3_output").resolve())

    def test_explicit_relative_output_remains_repo_relative(self):
        expected = (ROOT / "runs/issues/S02/recovery18_20261029/integration/test-output").resolve()
        self.assertEqual(R.resolve_output_path("runs/issues/S02/recovery18_20261029/integration/test-output"),
                         expected)

    def test_all_nonmetadata_top_level_rules_are_locked(self):
        base = {
            "rules_version": "v2",
            "metrics": [{"id": "M1"}],
            "signals": [{"id": "S1"}],
            "decision_layers": {"L0": {"rule": "keep"}},
            "input_fingerprint": {"files": []},
        }
        selected = {
            **base,
            "input_version": "v3",
            "base_rules_sha256": "accepted",
            "l0_addendum_path": "locked.json",
            "input_fingerprint": {"files": [{"sha256": "new-input"}]},
        }
        keys = R.assert_science_rule_object_matches(selected, base)
        self.assertEqual(keys, ["decision_layers", "metrics", "rules_version", "signals"])
        selected["decision_layers"] = {"L0": {"rule": "changed"}}
        with self.assertRaisesRegex(AssertionError, "decision_layers"):
            R.assert_science_rule_object_matches(selected, base)

    def test_non_target_comparison_checks_every_row_field(self):
        old = [
            {"security_id": "SZ:000001", "metric_id": "M1", "value": "1", "source_refs": "A"},
            {"security_id": "SZ:002083", "metric_id": "M1", "value": "2", "source_refs": "B"},
        ]
        self.assertEqual(
            R.assert_non_target_rows_unchanged(old, [dict(row) for row in old], {"SZ:002083"},
                                               ("security_id", "metric_id"), "synthetic", 1),
            1,
        )
        changed = [dict(row) for row in old]
        changed[0]["source_refs"] = "ALTERED"
        with self.assertRaisesRegex(RuntimeError, "non-target rows changed in full fields"):
            R.assert_non_target_rows_unchanged(old, changed, {"SZ:002083"},
                                               ("security_id", "metric_id"), "synthetic", 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
