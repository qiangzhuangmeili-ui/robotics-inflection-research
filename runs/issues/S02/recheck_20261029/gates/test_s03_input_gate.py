"""Focused self-checks for the S03 input and protected-route gate."""

from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[5]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import s03_input_gate as gate  # noqa: E402


class S03InputGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = REPO_ROOT
        cls.snapshot = gate.load_gate_inputs(cls.root)

    def _counts(self, security_id):
        return dict(self.snapshot.company_status_counts[security_id])

    def test_pinned_canonical_bundle_loads(self):
        self.assertEqual(self.snapshot.contract["canonical_binding"]["input_version"], gate.EXPECTED_INPUT_VERSION)
        self.assertEqual(len(self.snapshot.protected_rows), 21)
        self.assertEqual(self.snapshot.contract["canonical_s02_snapshot"]["l0_company_counts"], gate.EXPECTED_GLOBAL_L0_COUNTS)
        self.assertEqual(self.snapshot.contract_sha256, gate.EXPECTED_CONTRACT_SHA256)

    def test_tampered_contract_file_fails_closed(self):
        original = (self.root / gate.CONTRACT_RELATIVE_PATH).read_text(encoding="utf-8")
        tampered = original.replace('"contract_version": "1.1.0"', '"contract_version": "1.0.0"', 1)
        self.assertNotEqual(original, tampered)
        with tempfile.TemporaryDirectory(dir=self.root) as temp_dir:
            path = Path(temp_dir) / "tampered_contract.json"
            path.write_text(tampered, encoding="utf-8")
            with self.assertRaisesRegex(gate.GateError, "contract hash mismatch"):
                gate.load_gate_inputs(self.root, path)

    def test_stale_input_version_fails_closed(self):
        contract = json.loads((self.root / gate.CONTRACT_RELATIVE_PATH).read_text(encoding="utf-8"))
        contract["canonical_binding"]["input_version"] = "S00_BASELINE_OLD"
        with self.assertRaisesRegex(gate.GateError, "old or stale S02 input version|Unknown or stale S02 input version"):
            gate.validate_contract_document(contract, gate.EXPECTED_CONTRACT_SHA256)

    def test_missing_contract_fails_closed(self):
        missing = self.root / "runs/issues/S02/recheck_20261029/gates/missing_contract.json"
        with self.assertRaisesRegex(gate.GateError, "contract is missing"):
            gate.load_gate_inputs(self.root, missing)

    def test_tampered_metric_artifact_fails_hash_check(self):
        with tempfile.TemporaryDirectory(dir=self.root) as temp_dir:
            altered = Path(temp_dir) / "all_pool_metrics.csv"
            altered.write_text("security_id,metric_id\nTAMPERED,M01\n", encoding="utf-8")
            with self.assertRaisesRegex(gate.GateError, "Artifact hash mismatch"):
                gate._verify_file_hash(altered, gate.EXPECTED_ARTIFACT_SHA256[
                    "runs/issues/S02/remediation_20261029/s02/all_pool_metrics.csv"
                ], "test all_pool_metrics.csv")

    def test_only_pure_lf_crlf_variants_of_the_two_frozen_jsons_are_accepted(self):
        for relative_path, equivalents in gate.KNOWN_JSON_EOL_EQUIVALENTS.items():
            original = (self.root / relative_path).read_bytes()
            lf_bytes = original.replace(b"\r\n", b"\n")
            crlf_bytes = lf_bytes.replace(b"\n", b"\r\n")
            self.assertEqual(gate._sha256_bytes(lf_bytes), equivalents["lf_sha256"])
            self.assertEqual(gate._sha256_bytes(crlf_bytes), equivalents["crlf_sha256"])
            expected = gate.EXPECTED_ARTIFACT_SHA256[relative_path]
            with tempfile.TemporaryDirectory(dir=self.root) as temp_dir:
                path = Path(temp_dir) / "frozen.json"
                for variant in (lf_bytes, crlf_bytes):
                    path.write_bytes(variant)
                    gate._verify_file_hash(path, expected, relative_path, relative_path)
                    with self.assertRaises(gate.GateError):
                        gate._verify_file_hash(path, "0" * 64, relative_path, relative_path)

                    changed = bytearray(variant)
                    first = next(i for i, byte in enumerate(changed) if byte not in b" \t\r\n")
                    changed[first] = ord("[") if changed[first] == ord("{") else ord("!")
                    path.write_bytes(changed)
                    with self.assertRaises(gate.GateError):
                        gate._verify_file_hash(path, expected, relative_path, relative_path)

                if b"\n" in lf_bytes:
                    mixed = lf_bytes.replace(b"\n", b"\r\n", 1)
                    path.write_bytes(mixed)
                    with self.assertRaises(gate.GateError):
                        gate._verify_file_hash(path, expected, relative_path, relative_path)

    def test_all_ten_evaluable_open_cases_keep_no_signal_under_review(self):
        rows = [r for r in self.snapshot.protected_rows.values() if r["l0_route"] == "EVALUABLE"]
        self.assertEqual(len(rows), 10)
        for row in rows:
            result = gate.protect_existing_route(
                self.snapshot, row["security_id"], row["l0_route"], "NO_SIGNAL", self._counts(row["security_id"])
            )
            self.assertEqual(result["final_route"], "REVIEW_PENDING_UPSTREAM_COVERAGE")
            self.assertTrue(result["keep_open_coverage_review"])
            self.assertFalse(result["terminal_exclusion_allowed_by_this_gate"])
            self.assertEqual(result["raw_l1_route"], "NO_SIGNAL")

    def test_evaluable_positive_l1_route_is_preserved_and_stays_queued(self):
        row = next(r for r in self.snapshot.protected_rows.values() if r["l0_route"] == "EVALUABLE")
        result = gate.protect_existing_route(
            self.snapshot, row["security_id"], row["l0_route"], "OBSERVE_QUEUE", self._counts(row["security_id"])
        )
        self.assertEqual(result["final_route"], "OBSERVE_QUEUE")
        self.assertTrue(result["keep_open_coverage_review"])

    def test_all_w5_no_trigger_cases_remain_on_watchlist(self):
        rows = [r for r in self.snapshot.protected_rows.values() if r["l0_route"] == "W5_PROVISIONAL_ONLY"]
        self.assertEqual(len(rows), 8)
        for row in rows:
            result = gate.protect_existing_route(
                self.snapshot, row["security_id"], row["l0_route"], "NO_SIGNAL", self._counts(row["security_id"])
            )
            self.assertEqual(result["final_route"], "W5_PROVISIONAL_WATCHLIST")
            self.assertTrue(result["has_provisional"])
            self.assertFalse(result["terminal_exclusion_allowed_by_this_gate"])

    def test_w5_triggered_case_remains_flagged_observation_only(self):
        row = next(r for r in self.snapshot.protected_rows.values() if r["l0_route"] == "W5_PROVISIONAL_ONLY")
        result = gate.protect_existing_route(
            self.snapshot, row["security_id"], row["l0_route"], "OBSERVE_QUEUE", self._counts(row["security_id"])
        )
        self.assertEqual(result["final_route"], "W5_PROVISIONAL_OBSERVATION_ONLY")
        self.assertTrue(result["has_provisional"])

    def test_all_w9_cases_stay_in_data_or_scope_review(self):
        rows = [r for r in self.snapshot.protected_rows.values() if r["l0_route"] == "W9_MIXED_NON_EVALUABLE"]
        self.assertEqual(len(rows), 3)
        for row in rows:
            result = gate.protect_existing_route(
                self.snapshot, row["security_id"], row["l0_route"], "NO_SIGNAL", self._counts(row["security_id"])
            )
            self.assertEqual(result["final_route"], "HOLD_FOR_DATA_OR_SCOPE_REVIEW")
            self.assertFalse(result["terminal_exclusion_allowed_by_this_gate"])

    def test_hold_and_provisional_are_never_clean(self):
        self.assertFalse(gate.metric_evidence_is_clean("HOLD"))
        self.assertFalse(gate.metric_evidence_is_clean("PROVISIONAL"))
        self.assertFalse(gate.metric_evidence_is_clean("OK", ["Q01"]))
        self.assertFalse(gate.metric_evidence_is_clean("OK", ["Q06"]))
        self.assertFalse(gate.metric_evidence_is_clean("OK", ["Q07"]))
        self.assertFalse(gate.metric_evidence_is_clean("OK", ["Q12"]))

    def test_low_base_requires_explicit_s01_confirmation(self):
        self.assertFalse(gate.metric_evidence_is_clean("OK", ["Q05"]))
        self.assertFalse(gate.metric_evidence_is_clean("OK", ["Q05"], low_base_confirmed=None))
        self.assertFalse(gate.metric_evidence_is_clean("OK", ["Q05"], low_base_confirmed=False))
        self.assertTrue(gate.metric_evidence_is_clean("OK", ["Q05"], low_base_confirmed=True))

        # Confirmation cannot override another blocker or non-OK metric status.
        self.assertFalse(gate.metric_evidence_is_clean("OK", ["Q05", "Q06"], low_base_confirmed=True))
        self.assertFalse(gate.metric_evidence_is_clean("OK", ["Q05", "Q01"], low_base_confirmed=True))
        self.assertFalse(gate.metric_evidence_is_clean("PROVISIONAL", ["Q05"], low_base_confirmed=True))
        self.assertFalse(gate.metric_evidence_is_clean("HOLD", ["Q05"], low_base_confirmed=True))

    def test_only_unflagged_ok_can_be_clean(self):
        self.assertTrue(gate.metric_evidence_is_clean("OK"))
        self.assertTrue(gate.metric_evidence_is_clean("OK", ["Q11"]))

    def test_unknown_metric_status_or_flag_fails_closed(self):
        with self.assertRaises(gate.GateError):
            gate.metric_evidence_is_clean("OKAY")
        with self.assertRaises(gate.GateError):
            gate.metric_evidence_is_clean("OK", ["Q99"])
        with self.assertRaises(gate.GateError):
            gate.metric_evidence_is_clean("OK", ["Q05"], low_base_confirmed="confirmed")
        with self.assertRaises(gate.GateError):
            gate.metric_evidence_is_clean("OK", ["Q05"], low_base_confirmed=1)

    def test_wrong_runtime_status_vector_fails_closed(self):
        row = next(r for r in self.snapshot.protected_rows.values() if r["l0_route"] == "EVALUABLE")
        counts = self._counts(row["security_id"])
        counts["OK"] -= 1
        counts["MISSING"] += 1
        with self.assertRaisesRegex(gate.GateError, "differs from the canonical S02 summary"):
            gate.protect_existing_route(self.snapshot, row["security_id"], row["l0_route"], "NO_SIGNAL", counts)

    def test_unknown_company_or_route_fails_closed(self):
        row = next(r for r in self.snapshot.protected_rows.values() if r["l0_route"] == "EVALUABLE")
        with self.assertRaisesRegex(gate.GateError, "Unknown company ID"):
            gate.protect_existing_route(self.snapshot, "XX:999999", "EVALUABLE", "NO_SIGNAL", self._counts(row["security_id"]))
        with self.assertRaisesRegex(gate.GateError, "Unknown L1 route"):
            gate.protect_existing_route(self.snapshot, row["security_id"], row["l0_route"], "DROP", self._counts(row["security_id"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)

