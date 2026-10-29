from __future__ import annotations
import contextlib
import csv
import hashlib
import io
import json
import shutil
import sys
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / "tools"))
import s02_calculate as S

INTEGRATION = Path(__file__).resolve().parent
BASE_RULES_PATH = ROOT / "runs/issues/S01/screen_rules_v2.json"
V1_CSV = ROOT / "runs/issues/S00/financial_normalized.csv"
V2_CSV = ROOT / "runs/issues/S02/remediation_20261029/s00/financial_normalized.csv"
V2_GZ = ROOT / "runs/issues/S02/remediation_20261029/s00/financial_normalized.csv.gz"
CUSTOM_RULES_PATH = ROOT / "runs/issues/S02/remediation_20261029/rules_recalculation_inputs.json"
V1_METRICS = ROOT / "runs/issues/S02/all_pool_metrics.csv"
V2_METRICS = ROOT / "runs/issues/S02/remediation_20261029/s02/all_pool_metrics.csv"
V2_SUMMARY = ROOT / "runs/issues/S02/remediation_20261029/s02/company_metric_summary.csv"
PROJECT_STATE = json.loads((ROOT / "PROJECT_STATE.json").read_text(encoding="utf-8"))
V2_SHA = PROJECT_STATE["current_valid_versions"]["S00_data"]["v2_sha256"]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def metric_signature(path: Path) -> dict[tuple[str, str], tuple[str, str, str]]:
    rows = read_csv(path)
    return {
        (row["security_id"], row["metric_id"]):
            (row["value"], row["metric_status"], row["quality_flags"])
        for row in rows
    }


def run_s02(argv, out_dir: Path, *, patched_input: Path | None = None,
            patched_rules: Path | None = None, inherited_argv: list[str] | None = None,
            l0_loader=None):
    previous = {
        "S02": S.S02,
        "RULES": S.RULES,
        "RULES_SHA_REQUIRED": S.RULES_SHA_REQUIRED,
        "NORMALIZED": S.s01.NORMALIZED,
        "L0_PATH": S.DEFAULT_L0_PATCH_RELATIVE,
        "L0_LOADER": S.load_l0_addendum,
        "add": S.add,
    }
    captured = {}
    original_add = S.add

    def capture(cid, item, ok, detail, blocking=True, result_override=None):
        original_add(cid, item, ok, detail, blocking, result_override)
        captured[cid] = {"ok": ok, "blocking": blocking, "detail": detail,
                         "result": S.checks[-1]["result"]}

    S.S02 = out_dir
    if patched_rules is not None:
        S.RULES = patched_rules
        S.RULES_SHA_REQUIRED = S.sha256(patched_rules)
    if patched_input is not None:
        S.s01.NORMALIZED = patched_input
    if l0_loader is not None:
        S.load_l0_addendum = l0_loader
    S.add = capture
    saved_argv = sys.argv
    if inherited_argv is not None:
        sys.argv = inherited_argv
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            code = S.main() if argv is None else S.main(argv)
    finally:
        sys.argv = saved_argv
        S.S02 = previous["S02"]
        S.RULES = previous["RULES"]
        S.RULES_SHA_REQUIRED = previous["RULES_SHA_REQUIRED"]
        S.s01.NORMALIZED = previous["NORMALIZED"]
        S.DEFAULT_L0_PATCH_RELATIVE = previous["L0_PATH"]
        S.load_l0_addendum = previous["L0_LOADER"]
        S.add = previous["add"]
    return code, captured


class S02IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.results = {}

    def check_passes(self, captured, ids=("P01", "P02", "P05", "P06")):
        for cid in ids:
            self.assertIn(cid, captured)
            self.assertTrue(captured[cid]["ok"], f"{cid} failed: {captured[cid]}")

    def test_rules_hash_allowlist_and_science_lock(self):
        base_doc = json.loads(BASE_RULES_PATH.read_text(encoding="utf-8"))
        raw = BASE_RULES_PATH.read_bytes()
        lf_sha = sha256_bytes(raw.replace(b"\r\n", b"\n"))
        current_sha = S.sha256(BASE_RULES_PATH)
        self.assertIn(current_sha, S.ACCEPTED_BASE_RULES_SHA256)
        self.assertIn(lf_sha, S.ACCEPTED_BASE_RULES_SHA256)
        self.assertTrue(S.science_rules_match(base_doc, base_doc, current_sha)[0])
        self.assertTrue(S.science_rules_match(base_doc, base_doc, lf_sha)[0])
        self.assertFalse(S.science_rules_match(base_doc, base_doc, "0" * 64)[0])
        changed = json.loads(json.dumps(base_doc))
        changed["signals"][0]["threshold"] = changed["signals"][0]["threshold"] + 0.001
        self.assertFalse(S.science_rules_match(changed, base_doc, current_sha)[0])
        self.results["rules_hash_allowlist_and_science_lock"] = {"status": "PASS"}

    def test_default_v1_keeps_historical_labels_and_metrics(self):
        out = INTEGRATION / "default_v1"
        code, checks = run_s02(["--out-dir", str(out)], out)
        self.assertEqual(code, 0)
        self.check_passes(checks)
        self.assertEqual(checks["P05"]["detail"]["verified_against"],
                         "rules_input_fingerprint_gzip:runs/issues/S00/financial_normalized.csv.gz")
        self.assertEqual(checks["P06"]["result"], "NOT_APPLICABLE")
        self.assertFalse(checks["P06"]["detail"]["required"])
        manifest = json.loads((out / "calculation_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["rules_file"], "runs/issues/S01/screen_rules_v2.json")
        self.assertFalse(manifest["l0_addendum"]["applied"])
        self.assertEqual(metric_signature(out / "all_pool_metrics.csv"), metric_signature(V1_METRICS))
        self.assertEqual((out / "all_pool_metrics.csv").read_bytes(), V1_METRICS.read_bytes())
        self.assertEqual(read_csv(out / "company_metric_summary.csv"),
                         read_csv(ROOT / "runs/issues/S02/company_metric_summary.csv"))
        rows = read_csv(out / "company_metric_summary.csv")
        l0 = {row["l0_evaluability"] for row in rows}
        self.assertIn("MIXED_NOT_DEFINED_BY_RULE", l0)
        review = json.loads((out / "review.json").read_text(encoding="utf-8"))
        self.assertEqual(len(S.checks), review["checks_total"])
        self.results["default_v1"] = {
            "status": "PASS",
            "cells": len(metric_signature(out / "all_pool_metrics.csv")),
            "l0_counts": manifest["l0_distribution"],
            "input_sha256": manifest["normalized_input_used"]["sha256"],
        }

    def test_v2_cli_verifies_state_and_applies_addendum_without_metric_drift(self):
        out = INTEGRATION / "v2_cli"
        code, checks = run_s02(
            ["--normalized", str(V2_CSV), "--out-dir", str(out)],
            out,
        )
        self.assertEqual(code, 0)
        self.check_passes(checks)
        self.assertEqual(checks["P05"]["detail"]["verified_against"],
                         "PROJECT_STATE.current_valid_versions.S00_data.v2_repair")
        self.assertEqual(checks["P06"]["result"], "PASS")
        self.assertTrue(checks["P06"]["detail"]["required"])
        self.assertTrue(checks["P06"]["detail"]["applied"])
        manifest = json.loads((out / "calculation_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["normalized_input_used"]["sha256"], V2_SHA)
        self.assertEqual(manifest["rules_file"], "runs/issues/S01/screen_rules_v2.json")
        self.assertTrue(manifest["l0_addendum"]["applied"])
        self.assertEqual(manifest["l0_addendum"]["version"],
                         "S01_SCREEN_RULES_V2_L0_ADDENDUM_20261029")
        self.assertEqual(manifest["l0_addendum"]["sha256"],
                         manifest["l0_addendum"]["manifest_sha256"])
        self.assertEqual(read_csv(out / "all_pool_metrics.csv"), read_csv(V2_METRICS))
        self.assertEqual((out / "all_pool_metrics.csv").read_bytes(), V2_METRICS.read_bytes())
        rows = read_csv(out / "company_metric_summary.csv")
        self.assertEqual(rows, read_csv(V2_SUMMARY))
        self.assertEqual((out / "company_metric_summary.csv").read_bytes(), V2_SUMMARY.read_bytes())
        self.assertNotIn("MIXED_NOT_DEFINED_BY_RULE",
                         {row["l0_evaluability"] for row in rows})
        self.assertEqual(manifest["l0_distribution"], {
            "EVALUABLE": 664, "W5_PROVISIONAL_ONLY": 387, "W9_MIXED_NON_EVALUABLE": 3
        })
        review = json.loads((out / "review.json").read_text(encoding="utf-8"))
        self.assertEqual(len(S.checks), review["checks_total"])
        sources = manifest["execution_sources"]
        self.assertEqual(sources["calculator"]["sha256"], S.sha256(ROOT / "tools/s02_calculate.py"))
        self.assertEqual(sources["formula_engine"]["sha256"], S.sha256(ROOT / "tools/s01_rules_check.py"))
        self.assertEqual(sources["l0_classifier"]["sha256"], S.sha256(ROOT / "tools/l0_classify.py"))
        self.assertTrue(sources["l0_classifier"]["executed"])
        self.assertEqual(sources["l0_rules"]["sha256"], S.sha256(ROOT / "runs/issues/S02/remediation_20261029/l0/l0_rules_patch.json"))
        self.assertEqual(sources["upstream_a03"]["source_sha256"], S.sha256(ROOT / "tools/a03_financial_field_extractor.py"))
        self.assertEqual(sources["upstream_a03"]["reextract_plan_sha256"], S.sha256(ROOT / "runs/issues/S02/remediation_20261029/reextract_plan.json"))
        self.assertEqual(sources["upstream_a03"]["registered_parser_sha256"],
                         json.loads((ROOT / "runs/issues/S02/remediation_20261029/reextract_plan.json").read_text(encoding="utf-8"))["parser_sha256"])
        self.assertFalse(sources["upstream_a03"]["extraction_executed_this_run"])
        self.results["v2_cli"] = {
            "status": "PASS",
            "cells": len(metric_signature(out / "all_pool_metrics.csv")),
            "l0_counts": manifest["l0_distribution"],
            "input_sha256": manifest["normalized_input_used"]["sha256"],
            "rules_file": manifest["rules_file"],
            "addendum": manifest["l0_addendum"],
            "execution_sources": sources,
            "all_pool_metrics_byte_equal_canonical": True,
            "company_summary_byte_equal_canonical": True,
        }

    def test_v2_csv_copy_matches_registered_gzip_payload_and_routes_l0(self):
        copy_path = INTEGRATION / "reasonix_recalc_input.csv"
        shutil.copyfile(V2_CSV, copy_path)
        out = INTEGRATION / "v2_csv_copy"
        try:
            code, checks = run_s02(
                ["--normalized", str(copy_path), "--rules", str(CUSTOM_RULES_PATH),
                 "--out-dir", str(out)],
                out,
            )
        finally:
            copy_path.unlink(missing_ok=True)
        self.assertEqual(code, 0)
        self.check_passes(checks)
        self.assertEqual(checks["P05"]["detail"]["verified_against"],
                         "rules_input_fingerprint_gzip:runs/issues/S02/remediation_20261029/s00/financial_normalized.csv.gz")
        self.assertTrue(checks["P06"]["detail"]["required"])
        self.assertTrue(checks["P06"]["detail"]["applied"])
        manifest = json.loads((out / "calculation_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["normalized_input_used"]["source_path"],
                         "runs/issues/S02/recheck_20261029/integration/reasonix_recalc_input.csv")
        self.assertEqual(manifest["normalized_input_used"]["source_sha256"], V2_SHA)
        self.assertTrue(manifest["l0_addendum"]["applied"])
        self.assertEqual((out / "all_pool_metrics.csv").read_bytes(), V2_METRICS.read_bytes())
        self.assertEqual((out / "company_metric_summary.csv").read_bytes(), V2_SUMMARY.read_bytes())
        self.results["v2_csv_copy"] = {"status": "PASS", "registered_gzip_payload_match": True,
                                      "l0_counts": manifest["l0_distribution"]}

    def test_v2_project_state_payload_hash_identifies_csv_copy(self):
        copy_path = INTEGRATION / "project_state_recalc_input.csv"
        shutil.copyfile(V2_CSV, copy_path)
        out = INTEGRATION / "v2_project_state_copy"
        try:
            code, checks = run_s02(
                ["--normalized", str(copy_path), "--out-dir", str(out)],
                out,
            )
        finally:
            copy_path.unlink(missing_ok=True)
        self.assertEqual(code, 0)
        self.check_passes(checks)
        self.assertEqual(checks["P05"]["detail"]["verified_against"],
                         "PROJECT_STATE.current_valid_versions.S00_data.v2_repair")
        self.assertTrue(checks["P06"]["detail"]["required"])
        self.assertTrue(checks["P06"]["detail"]["applied"])
        manifest = json.loads((out / "calculation_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual((out / "all_pool_metrics.csv").read_bytes(), V2_METRICS.read_bytes())
        self.assertEqual((out / "company_metric_summary.csv").read_bytes(), V2_SUMMARY.read_bytes())
        self.results["v2_project_state_copy"] = {"status": "PASS", "payload_sha_match": True,
                                                "l0_counts": manifest["l0_distribution"]}

    def test_v2_gzip_cli_uses_out_dir_cache_and_preserves_source_hashes(self):
        out = INTEGRATION / "v2_gzip_cli"
        code, checks = run_s02(
            ["--normalized", str(V2_GZ), "--rules", str(CUSTOM_RULES_PATH),
             "--out-dir", str(out)],
            out,
        )
        self.assertEqual(code, 0)
        self.check_passes(checks)
        self.assertEqual(checks["P05"]["detail"]["verified_against"],
                         "rules_input_fingerprint_gzip:runs/issues/S02/remediation_20261029/s00/financial_normalized.csv.gz")
        manifest = json.loads((out / "calculation_manifest.json").read_text(encoding="utf-8"))
        input_used = manifest["normalized_input_used"]
        self.assertEqual(input_used["source_path"],
                         "runs/issues/S02/remediation_20261029/s00/financial_normalized.csv.gz")
        self.assertEqual(input_used["source_sha256"], S.sha256(V2_GZ))
        self.assertEqual(input_used["loaded_csv_sha256"], V2_SHA)
        self.assertTrue(input_used["loaded_csv_path"].startswith(
            "runs/issues/S02/recheck_20261029/integration/v2_gzip_cli/.input_cache/"))
        self.assertTrue((ROOT / input_used["loaded_csv_path"]).is_file())
        self.assertEqual((out / "all_pool_metrics.csv").read_bytes(), V2_METRICS.read_bytes())
        self.assertEqual((out / "company_metric_summary.csv").read_bytes(), V2_SUMMARY.read_bytes())
        self.results["v2_gzip_cli"] = {
            "status": "PASS", "source_sha256": input_used["source_sha256"],
            "loaded_csv_sha256": input_used["loaded_csv_sha256"],
            "loaded_csv_path": input_used["loaded_csv_path"],
            "l0_counts": manifest["l0_distribution"],
        }

    def test_v2_required_but_loader_returns_unapplied_fails_p06(self):
        out = INTEGRATION / "v2_loader_unapplied"

        def loader_returns_unapplied(_rules, _actual, _actual_sha, _input_identity):
            return {"applied": False, "version": None, "path": None, "sha256": None,
                    "manifest_sha256": None, "note": "fault injected"}

        code, checks = run_s02(
            ["--normalized", str(V2_CSV), "--out-dir", str(out)],
            out,
            l0_loader=loader_returns_unapplied,
        )
        self.assertEqual(code, 1)
        self.assertTrue(checks["P05"]["ok"])
        self.assertTrue(checks["P06"]["detail"]["required"])
        self.assertFalse(checks["P06"]["detail"]["applied"])
        self.assertEqual(checks["P06"]["result"], "FAIL")
        self.assertFalse((out / "all_pool_metrics.csv").exists())
        self.results["v2_loader_unapplied"] = {"status": "PASS", "preflight_blocked": True}

    def test_legacy_wrapper_call_uses_patched_input_and_rules_without_sys_argv_leak(self):
        out = INTEGRATION / "old_wrapper"
        code, checks = run_s02(
            None,
            out,
            patched_input=V2_CSV,
            patched_rules=CUSTOM_RULES_PATH,
            inherited_argv=["rebuild.py", "--wrapper-owned-flag", "value"],
        )
        self.assertEqual(code, 0)
        self.check_passes(checks)
        self.assertEqual(checks["P05"]["detail"]["verified_against"],
                         "rules_input_fingerprint_gzip:runs/issues/S02/remediation_20261029/s00/financial_normalized.csv.gz")
        manifest = json.loads((out / "calculation_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["normalized_input_used"]["path"],
                         "runs/issues/S02/remediation_20261029/s00/financial_normalized.csv")
        self.assertEqual(manifest["normalized_input_used"]["sha256"], V2_SHA)
        self.assertEqual(manifest["rules_file"],
                         "runs/issues/S02/remediation_20261029/rules_recalculation_inputs.json")
        self.assertEqual(metric_signature(out / "all_pool_metrics.csv"), metric_signature(V2_METRICS))
        self.assertNotIn("MIXED_NOT_DEFINED_BY_RULE",
                         {row["l0_evaluability"] for row in read_csv(out / "company_metric_summary.csv")})
        review = json.loads((out / "review.json").read_text(encoding="utf-8"))
        self.assertEqual(len(S.checks), review["checks_total"])
        self.results["old_wrapper"] = {
            "status": "PASS",
            "cells": len(metric_signature(out / "all_pool_metrics.csv")),
            "l0_counts": manifest["l0_distribution"],
            "input_sha256": manifest["normalized_input_used"]["sha256"],
            "rules_file": manifest["rules_file"],
        }

    def test_wrong_expected_sha_blocks_before_calculation(self):
        out = INTEGRATION / "wrong_sha"
        code, checks = run_s02(
            ["--normalized", str(V2_CSV), "--out-dir", str(out),
             "--normalized-sha256", "0" * 64],
            out,
        )
        self.assertEqual(code, 1)
        self.assertFalse(checks["P05"]["ok"])
        self.assertTrue(checks["P05"]["blocking"])
        self.assertFalse((out / "all_pool_metrics.csv").exists())
        self.results["wrong_sha"] = {"status": "PASS", "blocked": True}

    def test_tampered_csv_blocks_against_expected_v2_sha(self):
        tampered = INTEGRATION / "tampered_normalized.csv"
        original = V2_CSV.read_bytes()
        altered = original.replace(b"FIN.REV.YTD", b"FIN.REV.XTD", 1)
        self.assertNotEqual(altered, original)
        tampered.write_bytes(altered)
        unknown_out = INTEGRATION / "unknown_csv"
        unknown_code, unknown_checks = run_s02(
            ["--normalized", str(tampered), "--out-dir", str(unknown_out)],
            unknown_out,
        )
        self.assertEqual(unknown_code, 1)
        self.assertFalse(unknown_checks["P05"]["ok"])
        self.assertTrue(unknown_checks["P05"]["blocking"])
        out = INTEGRATION / "tampered_csv"
        code, checks = run_s02(
            ["--normalized", str(tampered), "--out-dir", str(out),
             "--normalized-sha256", V2_SHA],
            out,
        )
        self.assertEqual(code, 1)
        self.assertFalse(checks["P05"]["ok"])
        self.assertTrue(checks["P05"]["blocking"])
        self.assertFalse((out / "all_pool_metrics.csv").exists())
        self.results["unknown_and_tampered_csv"] = {
            "status": "PASS", "unknown_blocked": True, "wrong_expected_hash_blocked": True
        }

    def test_tampered_l0_patch_sha_blocks_without_touching_formal_patch(self):
        formal_patch = ROOT / "runs/issues/S02/remediation_20261029/l0/l0_rules_patch.json"
        patch_copy = INTEGRATION / "tampered_l0_rules_patch.json"
        patch_doc = json.loads(formal_patch.read_text(encoding="utf-8"))
        patch_doc["migration_note"] += " tampered"
        patch_copy.write_text(json.dumps(patch_doc, ensure_ascii=False, indent=2) + "\n",
                              encoding="utf-8")
        rules_copy = INTEGRATION / "rules_with_tampered_l0_path.json"
        rules_doc = json.loads(CUSTOM_RULES_PATH.read_text(encoding="utf-8"))
        rules_doc["l0_addendum_path"] = patch_copy.relative_to(ROOT).as_posix()
        rules_copy.write_text(json.dumps(rules_doc, ensure_ascii=False, indent=2) + "\n",
                              encoding="utf-8")
        out = INTEGRATION / "tampered_l0_patch"
        original_default = S.DEFAULT_L0_PATCH_RELATIVE
        try:
            S.DEFAULT_L0_PATCH_RELATIVE = patch_copy.relative_to(ROOT).as_posix()
            code, checks = run_s02(
                ["--normalized", str(V2_CSV), "--rules", str(rules_copy),
                 "--out-dir", str(out)],
                out,
            )
        finally:
            S.DEFAULT_L0_PATCH_RELATIVE = original_default
        self.assertEqual(code, 1)
        self.assertTrue(checks["P05"]["ok"])
        self.assertFalse(checks["P06"]["ok"])
        self.assertTrue(checks["P06"]["blocking"])
        self.assertFalse((out / "all_pool_metrics.csv").exists())
        self.assertEqual(S.sha256(formal_patch),
                         json.loads((ROOT / "runs/issues/S02/remediation_20261029/s02/calculation_manifest.json").read_text(encoding="utf-8"))["l0_addendum_sha256"])
        self.results["tampered_l0_patch"] = {"status": "PASS", "blocked": True}

    @classmethod
    def tearDownClass(cls):
        result_path = INTEGRATION / "test_results.json"
        result_path.write_text(json.dumps({
            "review_nature": "SELF_CHECK/INTEGRATION_REVIEW",
            "tests": cls.results,
            "test_count": len(cls.results),
            "no_s03_started": True,
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main(verbosity=2)
