#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Independently replay S02 from a frozen recovery18 v3 normalized gzip.

The replay consumes only the v3 manifest, its registered normalized gzip and
rules, the scope-hold specification, and the version-locked source tools. It
does not load the 360 extraction JSONs or any source PDFs, and it never writes
to the v3/canonical output directories.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


def find_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "tools" / "s02_calculate.py").is_file():
            return parent
    raise RuntimeError("Cannot locate robotics-inflection-research root")


ROOT = find_root()
INTEGRATION = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(INTEGRATION))

import comparability_adapter as C  # noqa: E402
import s02_calculate as S  # noqa: E402


EXPECTED_TAG = C.EXPECTED_TAG
Q16_NOTE_OVERRIDE = (
    "S00原已覆盖12槽；本轮修的是版式/单位/主体/重述或范围等剩余盲点，"
    "不能解释为缺半年报/季报执行"
)
EXPECTED_DEFAULT_MANIFEST = INTEGRATION / "v3_output" / "recovery18_manifest.json"
EXPECTED_DEFAULT_OUT = INTEGRATION / "s02_replay_v3"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def gzip_payload_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with gzip.open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def gzip_payload_size(path: Path) -> int:
    size = 0
    with gzip.open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            size += len(chunk)
    return size


def resolve_repo_path(value: str | Path) -> Path:
    path = Path(value)
    path = (path if path.is_absolute() else ROOT / path).resolve()
    if path != ROOT and ROOT not in path.parents:
        raise ValueError(f"Manifest path escapes repository root: {path}")
    return path


def resolve_output_path(value: str | None) -> Path:
    raw = Path(value) if value else EXPECTED_DEFAULT_OUT
    path = (raw if raw.is_absolute() else ROOT / raw).resolve()
    if path == INTEGRATION or INTEGRATION not in path.parents:
        raise ValueError(f"--out-dir must be a child of {INTEGRATION}")
    return path


def output_path(value: str | None) -> Path:
    path = resolve_output_path(value)
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite replay output: {path}")
    return path


def read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return data


def repo_relative(path: Path) -> str:
    return path.resolve().relative_to(ROOT.resolve()).as_posix()


def find_output_record(manifest: dict[str, Any], basename: str) -> dict[str, Any]:
    records = manifest.get("outputs")
    if not isinstance(records, list):
        raise ValueError("v3 manifest has no outputs list")
    matches = [item for item in records
               if Path(str(item.get("path", ""))).name.lower() == basename.lower()]
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one registered {basename}; found {len(matches)}")
    record = matches[0]
    if not record.get("path") or not record.get("sha256") or record.get("bytes") is None:
        raise ValueError(f"Incomplete output record for {basename}: {record}")
    return record


def verify_source_hashes(manifest: dict[str, Any]) -> list[dict[str, str]]:
    sources = manifest.get("execution_sources", {})
    if not isinstance(sources, dict):
        raise ValueError("v3 manifest has no execution_sources object")
    required = (
        "recovery_runner", "s00_normalizer", "s02_calculator", "formula_engine",
        "l0_classifier", "a03_parser", "l0_addendum", "rules_file",
        "comparability_adapter",
    )
    checked: list[dict[str, str]] = []
    for key in required:
        record = sources.get(key)
        if not isinstance(record, dict) or not record.get("path") or not record.get("sha256"):
            raise ValueError(f"v3 manifest is missing execution source hash: {key}")
        path = resolve_repo_path(record["path"])
        if not path.is_file():
            raise FileNotFoundError(f"Registered execution source is missing: {path}")
        actual = sha256_file(path)
        expected = str(record["sha256"]).lower()
        if actual != expected:
            raise ValueError(f"Execution source SHA differs from v3 manifest: {key} ({path})")
        checked.append({"name": key, "path": str(record["path"]), "sha256": actual})

    tests = sources.get("comparability_adapter_tests", {})
    if not isinstance(tests, dict):
        raise ValueError("v3 manifest has no comparability adapter test hashes")
    test_records = [{"path": tests.get("path"), "sha256": tests.get("sha256")},
                    *tests.get("additional_test_files", [])]
    for record in test_records:
        if not isinstance(record, dict) or not record.get("path") or not record.get("sha256"):
            raise ValueError(f"Malformed boundary-test source record: {record}")
        path = resolve_repo_path(record["path"])
        actual = sha256_file(path)
        if actual != str(record["sha256"]).lower():
            raise ValueError(f"Boundary-test source SHA differs from v3 manifest: {path}")
        checked.append({"name": "comparability_adapter_test", "path": str(record["path"]),
                        "sha256": actual})
    return checked


def verify_registered_pdf_metadata(spec: dict[str, Any], guard: dict[str, Any]) -> list[dict[str, str]]:
    """Cross-check prior PDF byte-hash claims without opening any PDF in replay."""
    verified = guard.get("verified_scope_source_pdfs", [])
    by_identity = {
        (str(item.get("security_id", "")), str(item.get("period_key", "")),
         str(item.get("document_id", ""))): item
        for item in verified
    }
    output = []
    for event in spec["holds"]:
        key = (str(event["security_id"]), str(event["period_key"]), str(event["document_id"]))
        record = by_identity.get(key)
        if record is None:
            raise ValueError(f"v3 manifest has no previously-verified PDF identity for scope event {key}")
        expected_sha = str(event["source_sha256"]).lower()
        # PDF paths are provenance strings in this replay, not files to open.
        # Do not dereference a local junction or require the original PDF corpus.
        source_ref = Path(event["source_pdf"])
        if source_ref.is_absolute() or ".." in source_ref.parts:
            raise ValueError("Scope source metadata must use a repository-relative path")
        expected_path = source_ref.as_posix()
        if (str(record.get("expected_sha256", "")).lower() != expected_sha
                or str(record.get("actual_sha256", "")).lower() != expected_sha
                or str(record.get("source_page", "")) != str(event["source_page"])
                or str(record.get("source_pdf", "")) != expected_path):
            raise ValueError(f"Scope PDF hash/page record differs between spec and v3 manifest: {key}")
        output.append({
            "security_id": key[0], "period_key": key[1], "document_id": key[2],
            "source_pdf": str(record.get("source_pdf", event["source_pdf"])),
            "source_sha256": expected_sha, "source_page": str(event["source_page"]),
            "read_during_replay": "NO",
        })
    if len(by_identity) != len(spec["holds"]):
        raise ValueError("v3 manifest contains extra or duplicate verified scope PDF records")
    return output


def validate_scope_tag_rows(
    rows: list[dict[str, str]], spec: dict[str, Any], adapter_stats: dict[str, Any],
) -> dict[str, Any]:
    """Confirm the frozen normalized input carries exactly the registered guard tags."""
    event_by_key = {
        (str(event["security_id"]), str(event["period_key"])): event
        for event in spec["holds"]
    }
    adapter_holds = {
        (str(item["security_id"]), str(item["period_key"])): item
        for item in adapter_stats.get("holds", [])
    }
    if set(event_by_key) != set(adapter_holds):
        raise ValueError("v3 manifest adapter event list differs from the registered hold specification")
    matched = Counter()
    tagged_count = 0
    derived_hold_count = 0
    derived_fields: dict[tuple[str, str], set[str]] = {key: set() for key in event_by_key}
    direct_fields: dict[tuple[str, str], set[str]] = {key: set() for key in event_by_key}
    for row in rows:
        key = (str(row.get("security_id", "")), str(row.get("period_key", "")))
        note_tokens = [token for token in (row.get("comparability_note") or "").split("|") if token]
        has_tag = EXPECTED_TAG in note_tokens
        event = event_by_key.get(key)
        if has_tag:
            if event is None:
                raise ValueError(f"Unregistered scope tag on normalized row: {key}")
            tagged_count += 1
        if event is not None:
            matched[key] += 1
            if not has_tag:
                raise ValueError(f"Registered scope row is missing its tag: {key}")
            if row.get("period_basis") == C.SINGLE_QUARTER_BASIS:
                source_kind = row.get("source_kind")
                status = row.get("status")
                if source_kind == C.DERIVED_DIFF_SOURCE_KIND:
                    if status == C.DERIVED_DIFF_STATUS:
                        raise ValueError(f"Derived cumulative SQ remains unheld: {key}/{row.get('field_id')}")
                    trace = (f"{C.EVIDENCE_MARKER_PREFIX}:{event['document_id']}"
                             f":p{event['source_page']}")
                    upstream_tokens = [token for token in (row.get("upstream_hold_fields") or "").split("|")
                                       if token]
                    if status == C.DERIVED_HOLD_STATUS and trace in upstream_tokens:
                        derived_fields[key].add(str(row.get("field_id", "")))
                        derived_hold_count += 1
                else:
                    direct_fields[key].add(str(row.get("field_id", "")))
    for key, event in event_by_key.items():
        if matched[key] == 0:
            raise ValueError(f"No normalized rows match registered scope event: {key}")
        expected_count = int(adapter_holds[key].get("matched_row_count", -1))
        if matched[key] != expected_count:
            raise ValueError(f"Tagged row count differs from v3 manifest for {key}: {matched[key]} != {expected_count}")
        expected_derived = set(adapter_holds[key].get("derived_sq_hold_fields", []))
        expected_direct = set(adapter_holds[key].get("preserved_non_cumulative_sq_fields", []))
        if derived_fields[key] != expected_derived:
            raise ValueError(f"Derived SQ scope holds differ from v3 manifest for {key}")
        if not expected_direct <= direct_fields[key]:
            raise ValueError(f"Direct reported SQ fields differ from v3 manifest for {key}")
        if "FIN.OCF.SQ" not in expected_derived:
            raise ValueError(f"Registered scope event lacks the required derived OCF SQ hold: {key}")
        if not {"FIN.REV.SQ", "FIN.NPP.SQ", "FIN.NPDEDT.SQ"} <= expected_direct:
            raise ValueError(f"Directly reported Q3 values are not explicitly preserved: {key}")
    expected_tagged = int(adapter_stats.get("tagged_row_count", -1))
    expected_derived_total = int(adapter_stats.get("derived_sq_hold_count", -1))
    if tagged_count != expected_tagged or derived_hold_count != expected_derived_total:
        raise ValueError(
            "Normalized scope tag/hold totals differ from v3 manifest: "
            f"tags={tagged_count}/{expected_tagged}, derived={derived_hold_count}/{expected_derived_total}"
        )
    return {"tagged_row_count": tagged_count, "derived_sq_hold_count": derived_hold_count,
            "event_row_counts": {f"{sec}|{period}": matched[(sec, period)]
                                 for sec, period in sorted(event_by_key)}}


def install_q16_note_override(s02_module: Any, note: str):
    """Mirror the recovery runner's Q16-only explanatory note override."""
    if note != Q16_NOTE_OVERRIDE:
        raise ValueError("v3 manifest Q16 explanation differs from the registered recovery wording")
    original = s02_module.add
    stats: dict[str, Any] = {"calls": 0, "note": note}

    def add_with_corrected_q16_note(cid, item, ok, detail, blocking=True, result_override=None):
        if cid == "Q16":
            if not isinstance(detail, dict):
                raise RuntimeError("Q16 detail must be an object before applying the replay explanation")
            detail = dict(detail)
            detail["note"] = note
            stats["calls"] += 1
        return original(cid, item, ok, detail, blocking, result_override)

    s02_module.add = add_with_corrected_q16_note
    return original, stats


def restore_q16_note_override(s02_module: Any, original) -> None:
    s02_module.add = original


def compare_csv_payloads(canonical: bytes, replay: bytes) -> dict[str, Any]:
    """Compare exact file bytes and parsed header/field rows independently."""
    canonical_rows = list(csv.reader(io.StringIO(canonical.decode("utf-8-sig"), newline="")))
    replay_rows = list(csv.reader(io.StringIO(replay.decode("utf-8-sig"), newline="")))
    header_equal = bool(canonical_rows and replay_rows and canonical_rows[0] == replay_rows[0])
    fields_equal = canonical_rows == replay_rows
    return {
        "byte_equal": canonical == replay,
        "header_equal": header_equal,
        "full_field_rows_equal": fields_equal,
        "canonical_data_rows": max(0, len(canonical_rows) - 1),
        "replay_data_rows": max(0, len(replay_rows) - 1),
        "canonical_sha256": sha256_bytes(canonical),
        "replay_sha256": sha256_bytes(replay),
        "canonical_bytes": len(canonical),
        "replay_bytes": len(replay),
    }


def load_registered_csv_from_gzip(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with gzip.open(path, "rt", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames:
            raise ValueError("Registered normalized gzip has no CSV header")
        if "comparability_note" not in reader.fieldnames:
            raise ValueError("Registered normalized gzip lacks comparability_note")
        return list(reader), list(reader.fieldnames)


def check_s02_manifest(manifest: dict[str, Any], l0_record: dict[str, Any], expected_payload_sha: str) -> None:
    checks = {item.get("id"): item for item in S.checks}
    for check_id in ("P01", "P05", "P06"):
        if checks.get(check_id, {}).get("result") != "PASS":
            raise RuntimeError(f"Required S02 replay check is not PASS: {check_id}={checks.get(check_id)}")
    if (checks["P05"].get("detail", {}).get("loaded_csv_sha256") != expected_payload_sha
            or manifest.get("normalized_input_used", {}).get("loaded_csv_sha256") != expected_payload_sha):
        raise RuntimeError("S02 P05 did not load the registered normalized gzip payload")
    output_l0 = manifest.get("l0_addendum", {})
    source_l0 = manifest.get("execution_sources", {}).get("l0_rules", {})
    if (output_l0.get("applied") is not True
            or output_l0.get("path") != l0_record["path"]
            or output_l0.get("sha256") != l0_record["sha256"]
            or source_l0.get("applied") is not True
            or source_l0.get("path") != l0_record["path"]
            or source_l0.get("sha256") != l0_record["sha256"]):
        raise RuntimeError("S02 replay did not apply the v3-locked L0 addendum")
    classifier = manifest.get("execution_sources", {}).get("l0_classifier", {})
    if classifier.get("executed") is not True:
        raise RuntimeError("S02 replay manifest does not record execution of the L0 classifier")


def execute(args: argparse.Namespace) -> int:
    out_root = output_path(args.out_dir)
    replay_runner_sha = sha256_file(Path(__file__))
    manifest_path = resolve_repo_path(args.v3_manifest) if args.v3_manifest else EXPECTED_DEFAULT_MANIFEST.resolve()
    if not manifest_path.is_file():
        raise FileNotFoundError(f"v3 recovery manifest is missing: {manifest_path}")
    source_manifest_sha = sha256_file(manifest_path)
    v3 = read_json(manifest_path)
    if v3.get("review_nature") != "SELF_CHECK" or v3.get("next_stage_release") != "S03_LOCKED":
        raise ValueError("Input v3 manifest is not the expected SELF_CHECK/S03_LOCKED artifact")
    if v3.get("external_source_evidence_review") != "NOT_PERFORMED":
        raise ValueError("v3 manifest source-audit state differs from the expected handoff scope")
    if v3.get("calculation_executed") is not True:
        raise ValueError("Input v3 manifest does not record a completed S00/S02 calculation")
    q16_metadata = v3.get("q16_explanation_override", {})
    if (q16_metadata.get("check_id") != "Q16"
            or q16_metadata.get("note") != Q16_NOTE_OVERRIDE
            or q16_metadata.get("applied_by_local_s02_add_wrapper") is not True
            or int(q16_metadata.get("calls", 0)) != 1
            or q16_metadata.get("qc_result_or_science_rule_changed") is not False):
        raise ValueError("v3 manifest does not record the approved local Q16 explanation override")

    checked_sources = verify_source_hashes(v3)
    generated = v3.get("generated_input", {})
    normalized_gzip = resolve_repo_path(generated.get("normalized_gzip_path", ""))
    normalized_gzip_sha = sha256_file(normalized_gzip)
    if normalized_gzip_sha != str(generated.get("normalized_gzip_sha256", "")).lower():
        raise ValueError("Normalized gzip bytes differ from the v3 manifest")
    gzip_record = find_output_record(v3, "financial_normalized.csv.gz")
    if (gzip_record["path"] != repo_relative(normalized_gzip)
            or gzip_record["sha256"] != normalized_gzip_sha
            or int(gzip_record["bytes"]) != normalized_gzip.stat().st_size):
        raise ValueError("Normalized gzip output record differs from the generated-input manifest")
    payload_sha = gzip_payload_sha256(normalized_gzip)
    if payload_sha != str(generated.get("normalized_csv_sha256", "")).lower():
        raise ValueError("Normalized gzip payload differs from the v3 manifest CSV SHA")
    normalized_record = find_output_record(v3, "financial_normalized.csv")
    if (normalized_record["sha256"] != payload_sha
            or int(normalized_record["bytes"]) != gzip_payload_size(normalized_gzip)):
        raise ValueError("Normalized CSV output record differs from the gzip payload")

    execution_sources = v3["execution_sources"]
    rules_record = execution_sources["rules_file"]
    rules_path = resolve_repo_path(rules_record["path"])
    rules_sha = sha256_file(rules_path)
    if rules_sha != str(rules_record["sha256"]).lower():
        raise ValueError("Rules file SHA differs from the v3 manifest")
    rules = read_json(rules_path)
    base_rules_path = ROOT / "runs/issues/S01/screen_rules_v2.json"
    base_rules_sha = sha256_file(base_rules_path)
    if base_rules_sha != str(rules.get("base_rules_sha256", "")).lower():
        raise ValueError("Frozen S01 base rules SHA differs from the v3 recalculation rules")
    checked_sources.append({"name": "frozen_s01_rules", "path": repo_relative(base_rules_path),
                            "sha256": base_rules_sha})
    gzip_entries = [item for item in rules.get("input_fingerprint", {}).get("files", [])
                    if item.get("path") == repo_relative(normalized_gzip)]
    if len(gzip_entries) != 1 or gzip_entries[0].get("sha256") != normalized_gzip_sha:
        raise ValueError("Frozen rules do not register the v3 normalized gzip bytes")

    guard = v3.get("comparability_guard", {})
    spec_path = resolve_repo_path(guard.get("spec_path", ""))
    spec_sha = sha256_file(spec_path)
    if spec_sha != str(guard.get("spec_sha256", "")).lower():
        raise ValueError("Scope-hold specification SHA differs from the v3 manifest")
    spec = C.load_scope_hold_spec(spec_path)
    if (spec.get("version") != guard.get("version") or spec.get("tag") != guard.get("tag")
            or spec.get("holds") != guard.get("scope_events")):
        raise ValueError("Scope-hold specification content differs from the v3 manifest")
    registered_pdf_identities = verify_registered_pdf_metadata(spec, guard)
    adapter_record = execution_sources["comparability_adapter"]
    if (adapter_record.get("path") != guard.get("execution_model", {}).get("required_adapter_path")
            or adapter_record.get("sha256") != guard.get("execution_model", {}).get("required_adapter_sha256")
            or guard.get("execution_model", {}).get("production_s02_calculate_alone_reproduces_guard") is not False):
        raise ValueError("v3 manifest does not lock the required S02 scope adapter")

    normalized_rows, normalized_header = load_registered_csv_from_gzip(normalized_gzip)
    tag_verification = validate_scope_tag_rows(normalized_rows, spec, guard.get("normalized_adapter", {}))
    canonical_records = {
        name: find_output_record(v3, name)
        for name in ("all_pool_metrics.csv", "company_metric_summary.csv")
    }
    canonical_paths: dict[str, Path] = {}
    for name, record in canonical_records.items():
        path = resolve_repo_path(record["path"])
        if not path.is_file():
            raise FileNotFoundError(f"Canonical v3 comparison output is missing: {path}")
        if sha256_file(path) != record["sha256"] or path.stat().st_size != int(record["bytes"]):
            raise ValueError(f"Canonical v3 output differs from its manifest: {path}")
        canonical_paths[name] = path

    l0_record = v3.get("frozen_inputs", {}).get("l0_addendum", {})
    if not l0_record.get("path") or not l0_record.get("sha256"):
        raise ValueError("v3 manifest does not freeze the L0 addendum")
    source_l0_record = execution_sources.get("l0_addendum", {})
    if (source_l0_record.get("path") != l0_record.get("path")
            or source_l0_record.get("sha256") != l0_record.get("sha256")):
        raise ValueError("Frozen-input and execution-source L0 hashes differ in v3 manifest")
    l0_path = resolve_repo_path(l0_record["path"])
    if sha256_file(l0_path) != str(l0_record["sha256"]).lower():
        raise ValueError("L0 addendum SHA differs from the v3 manifest")
    repair_manifest_record = v3.get("frozen_inputs", {}).get("v2_calculation_manifest", {})
    if not repair_manifest_record.get("path") or not repair_manifest_record.get("sha256"):
        raise ValueError("v3 manifest does not freeze the repair S02 L0 lock manifest")
    repair_manifest_path = resolve_repo_path(repair_manifest_record["path"])
    if sha256_file(repair_manifest_path) != str(repair_manifest_record["sha256"]).lower():
        raise ValueError("Repair S02 L0 lock manifest SHA differs from the v3 manifest")
    repair_manifest = read_json(repair_manifest_path)
    if str(repair_manifest.get("l0_addendum_sha256", "")).lower() != str(l0_record["sha256"]).lower():
        raise ValueError("Repair S02 L0 lock manifest does not approve the registered addendum")

    out_root.mkdir(parents=True, exist_ok=False)
    original_inputs, guard_stats = C.install_s01_inputs_guard(S.s01)
    original_add, q16_note_stats = install_q16_note_override(S, q16_metadata["note"])
    try:
        code = S.main([
            "--normalized", str(normalized_gzip),
            "--rules", str(rules_path),
            "--out-dir", str(out_root / "s02"),
        ])
    finally:
        restore_q16_note_override(S, original_add)
        C.restore_s01_inputs_guard(S.s01, original_inputs)
    if code != 0:
        raise RuntimeError(f"S02 replay returned blocking exit code {code}")
    if guard_stats["scope_tag_calls"] < 1 or guard_stats["scope_tag_calls"] != guard_stats["scope_hold_calls"]:
        raise RuntimeError("Replay did not hold every initially-OK comparison carrying the registered tag")
    expected_gate = guard.get("s02_input_gate", {})
    for key in ("calls", "scope_tag_calls", "scope_hold_calls", "preserved_non_ok_calls"):
        if key in expected_gate and int(guard_stats[key]) != int(expected_gate[key]):
            raise RuntimeError(f"Replay scope-input gate count differs from v3 manifest: {key}")
    run_manifest_path = out_root / "s02" / "calculation_manifest.json"
    run_manifest = read_json(run_manifest_path)
    check_s02_manifest(run_manifest, {
        "path": l0_record["path"], "sha256": l0_record["sha256"],
    }, payload_sha)
    review = read_json(out_root / "s02" / "review.json")
    if str(review.get("decision", "")).startswith("FAIL"):
        raise RuntimeError(f"S02 replay review failed: {review.get('decision')}")
    q16_checks = [item for item in S.checks if item.get("id") == "Q16"]
    if (q16_note_stats["calls"] != 1 or len(q16_checks) != 1
            or q16_checks[0].get("detail", {}).get("note") != Q16_NOTE_OVERRIDE):
        raise RuntimeError("S02 replay did not retain the approved Q16-only explanation")

    comparisons: dict[str, Any] = {}
    for name, canonical_path in canonical_paths.items():
        replay_path = out_root / "s02" / name
        if not replay_path.is_file():
            raise FileNotFoundError(f"S02 replay did not create {name}")
        comparison = compare_csv_payloads(canonical_path.read_bytes(), replay_path.read_bytes())
        expected_rows = 12648 if name == "all_pool_metrics.csv" else 1054
        if (not comparison["byte_equal"] or not comparison["header_equal"]
                or not comparison["full_field_rows_equal"]
                or comparison["replay_data_rows"] != expected_rows):
            raise RuntimeError(f"Replay differs from canonical v3 {name}: {comparison}")
        comparisons[name] = {
            "canonical_path": repo_relative(canonical_path),
            "replay_path": repo_relative(replay_path),
            **comparison,
        }

    # Ensure no frozen artifact moved while the replay was running.
    if sha256_file(manifest_path) != source_manifest_sha:
        raise RuntimeError("v3 recovery manifest changed during replay")
    if sha256_file(Path(__file__)) != replay_runner_sha:
        raise RuntimeError("Replay script changed during replay")
    if sha256_file(normalized_gzip) != normalized_gzip_sha or gzip_payload_sha256(normalized_gzip) != payload_sha:
        raise RuntimeError("Normalized gzip changed during replay")
    if (sha256_file(rules_path) != rules_sha or sha256_file(spec_path) != spec_sha
            or sha256_file(base_rules_path) != base_rules_sha):
        raise RuntimeError("Rules or scope-hold specification changed during replay")
    if sha256_file(l0_path) != str(l0_record["sha256"]).lower():
        raise RuntimeError("L0 addendum changed during replay")
    if sha256_file(repair_manifest_path) != str(repair_manifest_record["sha256"]).lower():
        raise RuntimeError("Repair S02 L0 lock manifest changed during replay")
    checked_sources = verify_source_hashes(v3)
    checked_sources.append({"name": "frozen_s01_rules", "path": repo_relative(base_rules_path),
                            "sha256": base_rules_sha})
    for name, path in canonical_paths.items():
        expected_record = canonical_records[name]
        if sha256_file(path) != expected_record["sha256"] or path.stat().st_size != int(expected_record["bytes"]):
            raise RuntimeError(f"Canonical output changed during replay: {path}")

    gate_manifest = {
        **guard_stats,
        "preserved_original_status_counts": dict(guard_stats["preserved_original_status_counts"]),
    }
    output_hashes = [
        {"path": repo_relative(out_root / "s02" / name),
         "sha256": sha256_file(out_root / "s02" / name),
         "bytes": (out_root / "s02" / name).stat().st_size}
        for name in ("all_pool_metrics.csv", "company_metric_summary.csv", "calculation_manifest.json", "review.json")
    ]
    replay_manifest = {
        "issue_key": "S02_RECOVERY18_V3_INDEPENDENT_REPLAY",
        "review_nature": "SELF_CHECK",
        "decision": "SELF_CHECK_PASS_EXTERNAL_SOURCE_REVIEW_REQUIRED",
        "source_manifest_path": repo_relative(manifest_path),
        "source_manifest_sha256": source_manifest_sha,
        "replay_runner": {"path": repo_relative(Path(__file__)), "sha256": replay_runner_sha},
        "review_scope": "S02 replay from the frozen v3 normalized gzip",
        "external_source_evidence_review": "NOT_PERFORMED",
        "raw_extraction_jsons_loaded": False,
        "raw_source_pdfs_read": 0,
        "next_stage_release": "S03_LOCKED",
        "input": {
            "normalized_gzip_path": repo_relative(normalized_gzip),
            "normalized_gzip_sha256": normalized_gzip_sha,
            "normalized_csv_payload_sha256": payload_sha,
            "normalized_csv_header": normalized_header,
            "rules_path": repo_relative(rules_path),
            "rules_sha256": rules_sha,
            "scope_spec_path": repo_relative(spec_path),
            "scope_spec_sha256": spec_sha,
            "scope_tag_verification": tag_verification,
        "registered_scope_pdf_identities_not_read": registered_pdf_identities,
        },
        "execution_sources_verified_against_v3_manifest": checked_sources,
        "comparability_guard": {
            "adapter_path": adapter_record["path"],
            "adapter_sha256": adapter_record["sha256"],
            "production_s02_alone_reproduces_guard": False,
            "adapter_installed_during_s02_main": True,
            "adapter_restored_in_finally": True,
            "independent_recalculation_after_restore": False,
            "s02_input_gate": gate_manifest,
        },
        "q16_explanation_override": {
            "check_id": "Q16", "note": Q16_NOTE_OVERRIDE,
            "applied_by_local_s02_add_wrapper": True,
            "calls": q16_note_stats["calls"],
            "qc_result_or_science_rule_changed": False,
        },
        "l0_addendum": {
            "path": l0_record["path"], "sha256": l0_record["sha256"],
            "applied": True,
            "lock_manifest_path": repair_manifest_record["path"],
            "lock_manifest_sha256": repair_manifest_record["sha256"],
        },
        "canonical_comparison": {
            "all_pool_metrics_rows": 12648,
            "company_summary_rows": 1054,
            "all_fields_equal": True,
            "bytes_equal": True,
            "outputs": comparisons,
        },
        "outputs": output_hashes,
        "checks": [
            {"id": "REPLAY_INPUT_HASHES", "result": "PASS"},
            {"id": "REPLAY_SCOPE_TAGS", "result": "PASS", **tag_verification},
            {"id": "REPLAY_S02_P01_P05_P06", "result": "PASS"},
            {"id": "REPLAY_Q16_EXPLANATION", "result": "PASS",
             "note": Q16_NOTE_OVERRIDE, "qc_result_or_science_rule_changed": False},
            {"id": "REPLAY_CANONICAL_BYTES_AND_FIELDS", "result": "PASS", "outputs": comparisons},
            {"id": "RAW_SOURCE_AUDIT", "result": "NOT_PERFORMED"},
            {"id": "S03_GATE", "result": "LOCKED"},
        ],
    }
    manifest_out = out_root / "replay_manifest.json"
    manifest_out.write_text(json.dumps(replay_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "decision": replay_manifest["decision"],
        "comparison": comparisons,
        "raw_source_pdfs_read": 0,
        "s03": "LOCKED",
        "replay_manifest": repo_relative(manifest_out),
    }, ensure_ascii=False, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v3-manifest", default=None,
                        help="已完成的 recovery18_manifest.json；默认 integration/v3_output 下的 manifest")
    parser.add_argument("--out-dir", default=None,
                        help="fresh replay 输出目录，必须是 integration 子目录且不存在")
    parser.add_argument("--execute", action="store_true",
                        help="执行隔离的 S02 重算；未提供时仅显示准备状态")
    args = parser.parse_args(argv)
    if not args.execute:
        print("PREPARED_NOT_RUN: pass --execute only after the v3 manifest and source package are frozen")
        return 2
    try:
        return execute(args)
    except Exception as exc:
        print(f"REPLAY_BLOCKED: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
