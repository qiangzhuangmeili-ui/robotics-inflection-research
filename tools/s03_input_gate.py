"""S03 first-step input and route guard for the S02 remediation snapshot.

This module validates immutable upstream artifacts and protects unresolved
coverage routes. It does not calculate metrics/signals, rank companies, or
write S03 outputs.
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Iterable, Mapping


CONTRACT_RELATIVE_PATH = Path("runs/issues/S02/recheck_20261029/gates/gate_contract.json")
EXPECTED_CONTRACT_ID = "S02_S03_GATE_CONTRACT_20261029"
EXPECTED_CONTRACT_VERSION = "1.1.0"
EXPECTED_CONTRACT_SHA256 = "dfe00fc2cea822dfff2c475fb2aee41f3905b7a36bd7a96adc5fbec6797f418a"
EXPECTED_INPUT_VERSION = "S00_TARGETED_REEXTRACTION_20261029"
EXPECTED_RULES_VERSION = "S01_SCREEN_RULES_V2"
EXPECTED_RULES_SHA256 = "ada501e8bcd276ce670a4799c730a81cdf2f9dc70c244f9255485b00168c6a85"
EXPECTED_L0_PATCH_VERSION = "S01_SCREEN_RULES_V2_L0_ADDENDUM_20261029"

EXPECTED_ARTIFACT_SHA256 = {
    "runs/issues/S02/remediation_20261029/s02/calculation_manifest.json": "2bb41a7b6510b7d0174d1b0baea384accf8919fd730ed5be6eabfb55c76e1af6",
    "runs/issues/S02/remediation_20261029/s00/financial_normalized.csv.gz": "b18c807917e3dcdec9241934008b180966a890be67b82816cff1243a48700824",
    "runs/issues/S02/remediation_20261029/s00/normalization_manifest.json": "4d22392e3344382ea759525c1873abb502275e622ee7f09f9d5311ba8cf7baf6",
    "data/company_master.csv": "9d9e83ea3880d18f91c3ccc15ba4c26ef5c569fab3943d0bce4246da428243f6",
    "runs/issues/S02/remediation_20261029/s02/all_pool_metrics.csv": "69f82db2896c746ee9e732354708f2d106d32ca115ccada9ee985ba322958425",
    "runs/issues/S02/remediation_20261029/s02/company_metric_summary.csv": "1dcd40932ec68c4c5d225c56e168906930a1a3b5beda43f3017d33470863bf95",
    "runs/issues/S02/remediation_20261029/l0/l0_rules_patch.json": "cd949466cae39847038a2f5929e9df9856c8d5900d6d7d42deb6cd7a55ddc811",
    "runs/issues/S02/remediation_20261029/l0/repaired/l0_reclassification.csv": "6bc02248555e883bf08c1df67ff2b02a6d3a7ef9530c15c2233321ee737b992f",
    "runs/issues/S02/remediation_20261029/l0/repaired/self_check.json": "cbcb1f7ebcf814e0c3a219964e8d66dc23b3c270e42a606ab5afe403890c9445",
    "runs/issues/S02/remediation_20261029/coverage_resolution.csv": "bd91619c6f1a8be85538abfb3afdb7ee83d53af1e082e1ab0572397f934efff1",
    "runs/issues/S02/recheck_20261029/gates/protected_21.csv": "74753e9ae7c61361aedd7796d91605bb6c0f7070b7d13fdd42490a5d791e6cc2",
    "runs/issues/S01/screen_rules_v2.json": "ada501e8bcd276ce670a4799c730a81cdf2f9dc70c244f9255485b00168c6a85",
    "runs/issues/S01/acceptance_20261029.json": "376dc407a7c24873433d6e8024fa962b80016cb5e6a1f7a98ba8acc04452e058",
}
KNOWN_JSON_EOL_EQUIVALENTS = {
    "runs/issues/S01/screen_rules_v2.json": {
        "lf_sha256": "d9a6b3cc77fcd3afb498673668be2d5c86412b6b83ffe0193e6c78f4979ecabf",
        "crlf_sha256": "ada501e8bcd276ce670a4799c730a81cdf2f9dc70c244f9255485b00168c6a85",
    },
    "runs/issues/S01/acceptance_20261029.json": {
        "lf_sha256": "376dc407a7c24873433d6e8024fa962b80016cb5e6a1f7a98ba8acc04452e058",
        "crlf_sha256": "4895452e461953193d3baa03ece5c974b02367d42b29a14e8b3e01ea15b074dc",
    },
}

STATUS_COLUMNS = {
    "OK": "ok",
    "PROVISIONAL": "provisional",
    "HOLD": "hold",
    "MISSING": "missing",
    "NOT_COMPARABLE": "not_comparable",
    "UNDEFINED_BASE": "undefined_base",
    "NOT_APPLICABLE": "not_applicable",
    "EXCLUDED_SCOPE": "excluded_scope",
    "VERSION_MISMATCH": "version_mismatch",
}
KNOWN_STATUSES = frozenset(STATUS_COLUMNS)
L0_ROUTES = frozenset({"EVALUABLE", "W5_PROVISIONAL_ONLY", "W9_MIXED_NON_EVALUABLE"})
L1_ROUTES = frozenset({"OBSERVE_QUEUE", "RISK_WATCH", "NO_SIGNAL"})
KNOWN_QUALITY_FLAGS = frozenset({f"Q{i:02}" for i in range(1, 13)})
CLEAN_BLOCKING_FLAGS = frozenset({"Q01", "Q06", "Q07", "Q12"})
EXPECTED_PROTECTED_L0_COUNTS = {
    "EVALUABLE": 10,
    "W5_PROVISIONAL_ONLY": 8,
    "W9_MIXED_NON_EVALUABLE": 3,
}
EXPECTED_GLOBAL_L0_COUNTS = {
    "EVALUABLE": 664,
    "W5_PROVISIONAL_ONLY": 387,
    "W9_MIXED_NON_EVALUABLE": 3,
}


class GateError(RuntimeError):
    """Raised whenever an input or route cannot be trusted by this gate."""


@dataclass(frozen=True)
class GateSnapshot:
    repo_root: Path
    contract: Mapping[str, Any]
    contract_sha256: str
    company_l0: Mapping[str, str]
    company_status_counts: Mapping[str, Mapping[str, int]]
    protected_rows: Mapping[str, Mapping[str, str]]


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _verify_file_hash(path: Path, expected: str, label: str, relative_path: str | None = None) -> None:
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise GateError(f"Required gate input is unavailable: {path}") from exc
    actual = _sha256_bytes(data)
    equivalent = KNOWN_JSON_EOL_EQUIVALENTS.get(relative_path or "")
    if equivalent is not None and expected not in {equivalent["lf_sha256"], equivalent["crlf_sha256"]}:
        raise GateError(f"Unpinned expected hash for newline-sensitive JSON: {label}")
    if actual == expected:
        return
    if equivalent is None:
        raise GateError(f"Artifact hash mismatch: {label}")
    # Accept only the two recorded, all-LF/all-CRLF byte forms of these
    # specific frozen JSON files. Mixed endings, bare CR, and content changes fail.
    lf_data = data.replace(b"\r\n", b"\n")
    if b"\r" in lf_data:
        raise GateError(f"Artifact hash mismatch: {label}")
    crlf_data = lf_data.replace(b"\n", b"\r\n")
    if data not in (lf_data, crlf_data):
        raise GateError(f"Artifact hash mismatch: {label}")
    if _sha256_bytes(lf_data) != equivalent["lf_sha256"]:
        raise GateError(f"Artifact content differs from frozen JSON: {label}")
    if actual not in {equivalent["lf_sha256"], equivalent["crlf_sha256"]}:
        raise GateError(f"Artifact hash mismatch: {label}")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise GateError(f"Invalid JSON gate input: {path}") from exc


def _read_csv(path: Path) -> list[dict[str, str]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            return list(csv.DictReader(stream))
    except (OSError, UnicodeError, csv.Error) as exc:
        raise GateError(f"Invalid CSV gate input: {path}") from exc


def _resolve_inside(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise GateError(f"Gate artifact path escapes repository root: {relative}") from exc
    return path


def validate_contract_document(contract: Mapping[str, Any], contract_sha256: str) -> None:
    """Validate the pinned contract identity, version, and canonical bindings."""
    if contract_sha256 != EXPECTED_CONTRACT_SHA256:
        raise GateError("Gate contract hash mismatch; contract is missing, stale, or modified")
    if contract.get("contract_id") != EXPECTED_CONTRACT_ID:
        raise GateError("Unknown gate contract ID")
    if contract.get("contract_version") != EXPECTED_CONTRACT_VERSION:
        raise GateError("Unsupported or stale gate contract version")
    if contract.get("status") != "SELF_CHECK_PASS_READY_FOR_S03_FIRST_STEP_INTEGRATION":
        raise GateError("Gate contract is not in the expected self-check state")
    if contract.get("review_nature") != "SELF_CHECK":
        raise GateError("Gate contract review nature is missing or unexpected")
    binding = contract.get("canonical_binding")
    if not isinstance(binding, Mapping):
        raise GateError("Canonical S02 binding is missing")
    if binding.get("input_version") != EXPECTED_INPUT_VERSION:
        raise GateError("Unknown or stale S02 input version")
    # Lists of {path, sha256} are verified separately; avoid accepting another schema.
    if not isinstance(binding.get("input_files"), list) or len(binding["input_files"]) != 3:
        raise GateError("Canonical S02 input file list is incomplete")
    if binding.get("metric_file", {}).get("path") != "runs/issues/S02/remediation_20261029/s02/all_pool_metrics.csv":
        raise GateError("Non-canonical metric output path")
    if binding.get("company_summary", {}).get("path") != "runs/issues/S02/remediation_20261029/s02/company_metric_summary.csv":
        raise GateError("Non-canonical company summary path")
    if binding.get("l0_routes", {}).get("path") != "runs/issues/S02/remediation_20261029/l0/repaired/l0_reclassification.csv":
        raise GateError("Non-canonical L0 route path")
    if binding.get("protected_queue", {}).get("path") != "runs/issues/S02/recheck_20261029/gates/protected_21.csv":
        raise GateError("Non-canonical protected queue path")
    frozen = contract.get("frozen_rule_reference", {})
    if frozen.get("rules_version") != EXPECTED_RULES_VERSION or frozen.get("rules_sha256") != EXPECTED_RULES_SHA256:
        raise GateError("Frozen S01 v2 rules identity does not match the gate")
    if frozen.get("l0_patch_version") != EXPECTED_L0_PATCH_VERSION:
        raise GateError("Unknown L0 addendum version")
    # Contract artifact hashes must match the allowlisted immutable snapshot.
    listed = {row.get("path"): row.get("sha256") for row in contract.get("source_files", [])}
    for path, digest in EXPECTED_ARTIFACT_SHA256.items():
        if listed.get(path) != digest:
            raise GateError(f"Contract source binding differs from pinned snapshot: {path}")
    expected_paths = set(EXPECTED_ARTIFACT_SHA256)
    if set(listed) != expected_paths:
        raise GateError("Contract source list contains missing or unexpected artifacts")


def _verify_artifact_hashes(root: Path, contract: Mapping[str, Any]) -> None:
    binding = contract["canonical_binding"]
    declared: dict[str, str] = {}
    for item in binding["input_files"]:
        if not isinstance(item, Mapping) or not isinstance(item.get("path"), str):
            raise GateError("Malformed canonical input-file binding")
        declared[item["path"]] = item.get("sha256", "")
    for key in (
        "s02_calculation_manifest", "metric_file", "company_summary", "l0_patch",
        "l0_routes", "l0_self_check", "coverage_resolution", "protected_queue",
        "screen_rules_v2", "s01_acceptance",
    ):
        item = binding.get(key)
        if not isinstance(item, Mapping) or not isinstance(item.get("path"), str):
            raise GateError(f"Missing canonical artifact binding: {key}")
        declared[item["path"]] = item.get("sha256", "")
    if set(declared) != set(EXPECTED_ARTIFACT_SHA256):
        raise GateError("Canonical artifact set differs from the pinned snapshot")
    for relative, expected in EXPECTED_ARTIFACT_SHA256.items():
        if declared.get(relative) != expected:
            raise GateError(f"Contract hash does not match pinned artifact: {relative}")
        path = _resolve_inside(root, relative)
        _verify_file_hash(path, expected, relative, relative)


def _status_counts(row: Mapping[str, str]) -> dict[str, int]:
    try:
        counts = {status: int(row[column]) for status, column in STATUS_COLUMNS.items()}
    except (KeyError, TypeError, ValueError) as exc:
        raise GateError("Company summary has a missing or invalid status count") from exc
    if any(value < 0 for value in counts.values()) or sum(counts.values()) != 12:
        raise GateError(f"Company status vector is invalid for {row.get('security_id', '<unknown>')}")
    return counts


def _expected_l0(counts: Mapping[str, int]) -> str:
    if counts["OK"] >= 1:
        return "EVALUABLE"
    if counts["PROVISIONAL"] >= 1:
        return "W5_PROVISIONAL_ONLY"
    return "W9_MIXED_NON_EVALUABLE"


def _validate_bundle_content(root: Path, contract: Mapping[str, Any]) -> tuple[dict, dict, dict]:
    binding = contract["canonical_binding"]
    manifest = _read_json(_resolve_inside(root, binding["s02_calculation_manifest"]["path"]))
    if manifest.get("input_version") != EXPECTED_INPUT_VERSION:
        raise GateError("Calculation manifest contains an old or unknown input version")
    if manifest.get("rules_version") != EXPECTED_RULES_VERSION:
        raise GateError("Calculation manifest does not use frozen S01 v2")
    if manifest.get("base_metric_rules_sha256") != EXPECTED_RULES_SHA256:
        raise GateError("Calculation manifest frozen-rule hash mismatch")
    patch = _read_json(_resolve_inside(root, binding["l0_patch"]["path"]))
    if patch.get("rules_version") != EXPECTED_L0_PATCH_VERSION or patch.get("base_rules_sha256") != EXPECTED_RULES_SHA256:
        raise GateError("L0 patch version/base rules mismatch")
    rules = _read_json(_resolve_inside(root, binding["screen_rules_v2"]["path"]))
    if rules.get("rules_version") != EXPECTED_RULES_VERSION:
        raise GateError("Unknown frozen metric-rule version")
    acceptance = _read_json(_resolve_inside(root, binding["s01_acceptance"]["path"]))
    if acceptance.get("rules_version_for_S02") != EXPECTED_RULES_VERSION:
        raise GateError("S01 acceptance does not bind S02 to frozen v2 rules")

    metrics = _read_csv(_resolve_inside(root, binding["metric_file"]["path"]))
    summary = _read_csv(_resolve_inside(root, binding["company_summary"]["path"]))
    l0_rows = _read_csv(_resolve_inside(root, binding["l0_routes"]["path"]))
    l0_check = _read_json(_resolve_inside(root, binding["l0_self_check"]["path"]))
    queue = _read_csv(_resolve_inside(root, binding["protected_queue"]["path"]))

    if len(metrics) != 12648 or len(summary) != 1054 or len(l0_rows) != 1054 or len(queue) != 21:
        raise GateError("Canonical S02/L0/protected queue row counts are incomplete")
    metric_keys = [(r.get("security_id"), r.get("metric_id")) for r in metrics]
    if len(set(metric_keys)) != 12648 or any(not a or not b for a, b in metric_keys):
        raise GateError("Canonical metric rows contain duplicate or missing company/metric keys")
    summary_by_id = {row.get("security_id"): row for row in summary}
    l0_by_id = {row.get("security_id"): row for row in l0_rows}
    queue_by_id = {row.get("security_id"): row for row in queue}
    if len(summary_by_id) != 1054 or len(l0_by_id) != 1054 or len(queue_by_id) != 21:
        raise GateError("Duplicate or missing company IDs in summary, L0, or protected queue")
    if set(summary_by_id) != set(l0_by_id):
        raise GateError("Company IDs differ between canonical summary and repaired L0 routes")

    computed_l0: dict[str, str] = {}
    status_totals = {status: 0 for status in KNOWN_STATUSES}
    for sid, row in summary_by_id.items():
        counts = _status_counts(row)
        l0 = _expected_l0(counts)
        observed = l0_by_id[sid].get("l0_evaluability_v3_addendum")
        if observed != l0:
            raise GateError(f"L0 classification mismatch for {sid}: {observed} != {l0}")
        computed_l0[sid] = l0
        for status, amount in counts.items():
            status_totals[status] += amount
    expected_l0_counts = dict(Counter(computed_l0.values()))
    if expected_l0_counts != EXPECTED_GLOBAL_L0_COUNTS:
        raise GateError("Global repaired L0 counts differ from the pinned snapshot")
    if status_totals != contract["canonical_s02_snapshot"]["metric_status_counts"]:
        raise GateError("Canonical company status totals differ from the gate contract")

    summary_hash = EXPECTED_ARTIFACT_SHA256[binding["company_summary"]["path"]]
    if l0_check.get("status") != "SELF_CHECK_PASS" or l0_check.get("input_sha256") != summary_hash:
        raise GateError("L0 repaired self-check does not bind the canonical company summary")
    if l0_check.get("input_companies") != 1054 or l0_check.get("input_cells_per_company") != 12:
        raise GateError("L0 repaired self-check has an unexpected input shape")
    if l0_check.get("reclassified_company_counts") != EXPECTED_GLOBAL_L0_COUNTS:
        raise GateError("L0 repaired self-check counts differ from the pinned snapshot")

    coverage = _read_csv(_resolve_inside(root, binding["coverage_resolution"]["path"]))
    open_ids = {r["security_id"] for r in coverage if r.get("resolution") != "RECOVERED_AT_LEAST_8_USABLE_FIELDS"}
    if len(open_ids) != 21 or open_ids != set(queue_by_id):
        raise GateError("Protected queue does not match the 21 open coverage rows")
    for sid, qrow in queue_by_id.items():
        counts = _status_counts(qrow)
        if counts != _status_counts(summary_by_id[sid]):
            raise GateError(f"Protected queue status vector differs from canonical summary: {sid}")
        if qrow.get("l0_route") != computed_l0[sid]:
            raise GateError(f"Protected queue L0 route differs from repaired route: {sid}")
        if qrow.get("terminal_exclusion_allowed_while_open") != "NO":
            raise GateError(f"Protected queue permits a terminal exclusion: {sid}")
    protected_counts = dict(Counter(q["l0_route"] for q in queue))
    if protected_counts != EXPECTED_PROTECTED_L0_COUNTS:
        raise GateError("Protected queue L0 branch counts differ from the pinned snapshot")

    manifest_outputs = {row.get("path"): row.get("sha256") for row in manifest.get("outputs", [])}
    for key in ("metric_file", "company_summary"):
        path = binding[key]["path"]
        if manifest_outputs.get(path) != binding[key]["sha256"]:
            raise GateError(f"Calculation manifest does not bind {key}")
    manifest_inputs = {row.get("path"): row.get("sha256") for row in manifest.get("inputs", [])}
    for item in binding["input_files"]:
        if manifest_inputs.get(item["path"]) != item["sha256"]:
            raise GateError(f"Calculation manifest does not bind input {item['path']}")

    return summary_by_id, l0_by_id, queue_by_id


def load_gate_inputs(repo_root: str | Path, contract_path: str | Path | None = None) -> GateSnapshot:
    """Load and fully validate the pinned S02/L0/21-company gate bundle.

    Missing, stale, modified, non-canonical, or internally inconsistent inputs
    raise GateError. No fallback input directory is attempted.
    """
    root = Path(repo_root).resolve()
    chosen = Path(contract_path) if contract_path is not None else CONTRACT_RELATIVE_PATH
    contract_file = chosen.resolve() if chosen.is_absolute() else (root / chosen).resolve()
    try:
        contract_file.relative_to(root)
    except ValueError as exc:
        raise GateError("Gate contract must be inside the repository root") from exc
    try:
        contract_bytes = contract_file.read_bytes()
    except OSError as exc:
        raise GateError(f"Required gate contract is missing: {contract_file}") from exc
    contract_sha = _sha256_bytes(contract_bytes)
    try:
        contract = json.loads(contract_bytes.decode("utf-8-sig"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise GateError("Gate contract is not valid UTF-8 JSON") from exc
    if not isinstance(contract, dict):
        raise GateError("Gate contract must be a JSON object")
    validate_contract_document(contract, contract_sha)
    _verify_artifact_hashes(root, contract)
    summary, l0, queue = _validate_bundle_content(root, contract)
    return GateSnapshot(
        repo_root=root,
        contract=MappingProxyType(contract),
        contract_sha256=contract_sha,
        company_l0=MappingProxyType({sid: row["l0_evaluability_v3_addendum"] for sid, row in l0.items()}),
        company_status_counts=MappingProxyType({sid: MappingProxyType(_status_counts(row)) for sid, row in summary.items()}),
        protected_rows=MappingProxyType({sid: MappingProxyType(row) for sid, row in queue.items()}),
    )


def metric_evidence_is_clean(
    metric_status: str,
    quality_flags: Iterable[str] = (),
    low_base_confirmed: bool | None = None,
) -> bool:
    """Check metric readiness without replacing the frozen S01 signal logic.

    Q05 requires an explicit boolean confirmation from the caller. This helper
    does not calculate that confirmation, run ``signals_of``/``confirm_low_base``
    or ``layers``, decide L2, or reject S01 absolute-value fallback paths such as
    SG06. Unknown statuses, flags, and confirmation types fail closed. HOLD and
    PROVISIONAL are never clean, even when ``low_base_confirmed`` is true.
    """
    if low_base_confirmed is not None and type(low_base_confirmed) is not bool:
        raise GateError("low_base_confirmed must be exactly bool or None")
    if metric_status not in KNOWN_STATUSES:
        raise GateError(f"Unknown metric status: {metric_status!r}")
    if isinstance(quality_flags, (str, bytes)):
        raise GateError("Quality flags must be a collection of flag IDs")
    try:
        flags = set(quality_flags)
    except TypeError as exc:
        raise GateError("Quality flags must be iterable") from exc
    if any(not isinstance(flag, str) or flag not in KNOWN_QUALITY_FLAGS for flag in flags):
        raise GateError("Unknown quality flag; clean evidence fails closed")
    if metric_status != "OK" or flags & CLEAN_BLOCKING_FLAGS:
        return False
    if "Q05" in flags and low_base_confirmed is not True:
        return False
    return True


def protect_existing_route(
    gate: GateSnapshot,
    security_id: str,
    l0_route: str,
    l1_route: str | None,
    metric_status_counts: Mapping[str, int],
) -> dict[str, Any]:
    """Apply queue-only protection to an existing L0/L1 result.

    The caller supplies already-computed routes and the 12-cell status vector.
    Signal logic remains outside this module.
    """
    if security_id not in gate.company_l0:
        raise GateError(f"Unknown company ID: {security_id}")
    expected_l0 = gate.company_l0[security_id]
    if l0_route not in L0_ROUTES or l0_route != expected_l0:
        raise GateError(f"Unknown or mismatched L0 route for {security_id}")
    if l1_route is not None and l1_route not in L1_ROUTES:
        raise GateError(f"Unknown L1 route for {security_id}: {l1_route!r}")
    if set(metric_status_counts) != KNOWN_STATUSES:
        raise GateError("Runtime status vector must contain exactly the nine known statuses")
    try:
        counts = {status: metric_status_counts[status] for status in KNOWN_STATUSES}
    except (KeyError, TypeError) as exc:
        raise GateError("Runtime status vector is incomplete") from exc
    if any(type(value) is not int or value < 0 for value in counts.values()) or sum(counts.values()) != 12:
        raise GateError("Runtime status vector is invalid")
    if dict(counts) != dict(gate.company_status_counts[security_id]):
        raise GateError(f"Runtime status vector differs from the canonical S02 summary for {security_id}")

    protected = security_id in gate.protected_rows
    final_route = l1_route
    keep_open = False
    if l0_route == "W9_MIXED_NON_EVALUABLE":
        final_route = "HOLD_FOR_DATA_OR_SCOPE_REVIEW"
        keep_open = True
    elif l0_route == "W5_PROVISIONAL_ONLY":
        final_route = "W5_PROVISIONAL_OBSERVATION_ONLY" if l1_route in {"OBSERVE_QUEUE", "RISK_WATCH"} else "W5_PROVISIONAL_WATCHLIST"
        keep_open = True
    elif protected and l1_route in {None, "NO_SIGNAL"}:
        final_route = "REVIEW_PENDING_UPSTREAM_COVERAGE"
        keep_open = True
    elif protected:
        keep_open = True

    return {
        "security_id": security_id,
        "raw_l0_route": l0_route,
        "raw_l1_route": l1_route,
        "final_route": final_route,
        "protected_coverage_case": protected,
        "keep_open_coverage_review": keep_open,
        "terminal_exclusion_allowed_by_this_gate": False if protected or l0_route != "EVALUABLE" else None,
        "has_provisional": counts["PROVISIONAL"] > 0,
        "has_hold": counts["HOLD"] > 0,
        "all_12_metric_statuses_ok": counts["OK"] == 12,
    }

