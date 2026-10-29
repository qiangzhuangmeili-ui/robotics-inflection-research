#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Prepare and run the bounded recovery18 S00+S02 v3 recalculation.

This script is deliberately inert unless called with --execute. It imports the
accepted S00/S02 implementations and overlays immutable JSON extraction
records; it does not implement financial formulas or L0 classification rules.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import importlib.util
import io
import json
import os
import sys
import unittest
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def find_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "tools" / "s00_normalize.py").is_file() and \
                (candidate / "tools" / "s02_calculate.py").is_file():
            return candidate
    raise RuntimeError("Cannot locate robotics-inflection-research root")


ROOT = find_root()
INTEGRATION = Path(__file__).resolve().parent
RECOVERY = INTEGRATION.parent
V2_ROOT = ROOT / "runs/issues/S02/remediation_20261029"
V2_EXTRACTED = V2_ROOT / "extracted"
V2_S00 = V2_ROOT / "s00"
V2_S02 = V2_ROOT / "s02"
V2_PLAN = V2_ROOT / "reextract_plan.json"
COLLECTION_INDEX_PATH = ROOT / "runs/collection/collection_index.csv"
LEGACY_D_COLLECTION_ROOT = Path(
    r"D:\StockResearchLab\IndustryInflectionLab\robotics_data\collection\originals"
)
BASE_RULES_PATH = ROOT / "runs/issues/S01/screen_rules_v2.json"
L0_PATCH_PATH = V2_ROOT / "l0/l0_rules_patch.json"
GROUPS = {"xcheck11": 11, "scope5": 5, "ocr2": 2}
EXCLUDED_IDS = {"SH:603448", "SH:688836", "SZ:301699"}
EXPECTED_TARGET_COUNT = 18
EXPECTED_POOL_COMPANY_COUNT = 1054
EXPECTED_NON_TARGET_COUNT = EXPECTED_POOL_COMPANY_COUNT - EXPECTED_TARGET_COUNT
STATUS_ORDER = (
    "OK", "PROVISIONAL", "HOLD", "MISSING", "NOT_COMPARABLE",
    "UNDEFINED_BASE", "NOT_APPLICABLE", "EXCLUDED_SCOPE", "VERSION_MISMATCH",
)
Q16_NOTE_OVERRIDE = (
    "S00原已覆盖12槽；本轮修的是版式/单位/主体/重述或范围等剩余盲点，"
    "不能解释为缺半年报/季报执行"
)

sys.path.insert(0, str(ROOT / "tools"))
import a03_financial_field_extractor as A  # noqa: E402
import comparability_adapter as C  # noqa: E402
import l0_classify as L  # noqa: E402
import s00_normalize as N  # noqa: E402
import s02_calculate as S  # noqa: E402


class InputNotReady(RuntimeError):
    """Raised when source correction packages are absent or incomplete."""


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def gzip_payload_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with gzip.open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def repo_relative(path: Path) -> str:
    return path.resolve().relative_to(ROOT.resolve()).as_posix()


def resolve_repo_path(value: str | Path) -> Path:
    path = Path(value)
    path = (path if path.is_absolute() else ROOT / path).resolve()
    if path != ROOT and ROOT not in path.parents:
        raise ValueError(f"Path escapes repository root: {path}")
    return path


def resolve_collection_local_file(
    local_file: str, task: dict[str, Any],
) -> tuple[Path, Path]:
    """Use a root-local collection-index path; permit only its exact legacy D: target."""
    raw = Path(local_file)
    if raw.is_absolute() or ".." in raw.parts:
        raise InputNotReady(f"Collection index local_file must be a safe repository-relative path: {local_file}")
    lexical_root = Path(os.path.abspath(str(ROOT)))
    lexical_path = Path(os.path.abspath(str(lexical_root / raw)))
    if lexical_path != lexical_root and lexical_root not in lexical_path.parents:
        raise InputNotReady(f"Collection index local_file escapes repository root: {local_file}")
    if not lexical_path.is_file():
        raise InputNotReady(f"Collection-index PDF is missing: {lexical_path}")
    try:
        resolved_target = lexical_path.resolve(strict=True)
    except OSError as exc:
        raise InputNotReady(f"Cannot resolve collection-index PDF target: {lexical_path}: {exc}") from exc
    resolved_root = ROOT.resolve()
    if resolved_target != resolved_root and resolved_root not in resolved_target.parents:
        sec = str(task.get("security_id", ""))
        code = str(task.get("stock_code", "")) or sec.partition(":")[2]
        expected_target = (LEGACY_D_COLLECTION_ROOT / code / str(task.get("slot_id", "")) /
                           f"{task.get('document_id', '')}.pdf")
        try:
            expected_target = expected_target.resolve(strict=True)
        except OSError as exc:
            raise InputNotReady(f"Legacy D: PDF target is not available: {expected_target}") from exc
        if os.path.normcase(str(resolved_target)) != os.path.normcase(str(expected_target)):
            raise InputNotReady(
                f"Collection-index symlink target is outside the approved legacy D: location: {resolved_target}"
            )
    return lexical_path, resolved_target


def resolve_output_path(value: str | None) -> Path:
    if value is None:
        path = (INTEGRATION / "v3_output").resolve()
    else:
        raw = Path(value)
        path = (raw if raw.is_absolute() else ROOT / raw).resolve()
    return path


def output_path(value: str | None) -> Path:
    path = resolve_output_path(value)
    if path == INTEGRATION or INTEGRATION not in path.parents:
        raise ValueError(f"--out-dir must be a child of {INTEGRATION}")
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite existing recovery output: {path}")
    return path


def assert_science_rule_object_matches(rules: dict[str, Any], base: dict[str, Any]) -> list[str]:
    """Compare every frozen S01 top-level rule key, excluding only input metadata."""
    metadata_keys = {"input_fingerprint", "input_version", "base_rules_sha256", "l0_addendum_path"}
    science_keys = sorted(set(base) - {"input_fingerprint"})
    if set(rules) - metadata_keys != set(science_keys):
        raise AssertionError("V3 rule top-level keys differ from the complete frozen S01 rule contract")
    changed_science_keys = [key for key in science_keys if rules.get(key) != base.get(key)]
    if changed_science_keys:
        raise AssertionError(f"Scientific S01 rule content drifted: {changed_science_keys}")
    return science_keys


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def csv_header(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        try:
            return next(csv.reader(fh))
        except StopIteration as exc:
            raise RuntimeError(f"CSV has no header: {path}") from exc


def require_same_header(v2_path: Path, v3_path: Path, label: str) -> list[str]:
    old_header = csv_header(v2_path)
    new_header = csv_header(v3_path)
    if old_header != new_header:
        raise RuntimeError(f"v2/v3 {label} CSV schema changed: v2={old_header}; v3={new_header}")
    return old_header


def write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns, lineterminator="\n", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def csv_data_row_count(path: Path) -> int:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        return max(0, sum(1 for _ in csv.reader(stream)) - 1)


def record_core(doc: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Accept a plain A03 result or a small result/extraction envelope."""
    outer = doc
    for key in ("corrected_result", "result", "extraction"):
        nested = outer.get(key)
        if isinstance(nested, dict) and isinstance(nested.get("fields"), list):
            merged = dict(outer)
            merged.update(nested)
            return merged, outer
    return outer, outer


def require_record_identity(
    record: dict[str, Any], source: Path, allow_empty_fields: bool = False,
) -> tuple[str, str, str]:
    fields = record.get("fields")
    if not isinstance(fields, list):
        raise InputNotReady(f"Record fields must be an array: {source}")
    if not fields and not allow_empty_fields:
        raise InputNotReady(f"Corrected result has no non-empty fields array: {source}")
    first = fields[0] if fields else None
    if first is not None and not isinstance(first, dict):
        raise InputNotReady(f"Malformed first field row: {source}")
    sec = str(record.get("security_id") or (first or {}).get("security_id") or "")
    slot = str(record.get("slot_id") or (first or {}).get("slot_id") or "")
    doc_id = str(record.get("document_id") or (first or {}).get("document_id") or "")
    if not sec or not slot or not doc_id:
        raise InputNotReady(f"Missing security_id/slot_id/document_id: {source}")
    seen = set()
    for field in fields:
        if not isinstance(field, dict):
            raise InputNotReady(f"Non-object field row: {source}")
        identity = (str(field.get("security_id", "")), str(field.get("slot_id", "")),
                    str(field.get("document_id", "")))
        if identity != (sec, slot, doc_id):
            raise InputNotReady(f"Field identity differs from result identity in {source}: {identity}")
        field_id = str(field.get("field_id", ""))
        if not field_id:
            raise InputNotReady(f"Field row has no field_id: {source}")
        key = (field_id, str(field.get("note", "")))
        if key in seen:
            raise InputNotReady(f"Duplicate field/note key {key} in {source}")
        seen.add(key)
    return sec, slot, doc_id


def task_identity_map(plan: dict[str, Any]) -> tuple[dict[tuple[str, str], dict[str, Any]], set[str]]:
    tasks = plan.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise InputNotReady("Frozen v2 reextract plan has no tasks")
    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    by_doc: dict[str, dict[str, Any]] = {}
    companies: set[str] = set()
    for task in tasks:
        key = (str(task.get("security_id", "")), str(task.get("slot_id", "")))
        doc_id = str(task.get("document_id", ""))
        if not all(key) or not doc_id or key in by_key or doc_id in by_doc:
            raise InputNotReady(f"Duplicate or incomplete frozen task identity: {task}")
        by_key[key] = task
        by_doc[doc_id] = task
        companies.add(key[0])
    if len(tasks) != 360 or len(by_doc) != 360:
        raise InputNotReady(f"Expected the complete frozen 360-document v2 overlay; got {len(tasks)}")
    if plan.get("parser_sha256") is None:
        raise InputNotReady("Frozen v2 plan has no parser SHA256")
    return by_key, companies


def expected_recovery_groups_from_v2() -> tuple[dict[str, set[str]], set[str], set[str]]:
    """Freeze the unresolved 21-company v2 scope and the actual source-team split."""
    rows = read_csv(V2_ROOT / "coverage_resolution.csv")
    if len(rows) != 53 or len({row.get("security_id") for row in rows}) != 53:
        raise InputNotReady("Frozen v2 coverage_resolution must contain 53 unique companies")
    by_resolution: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        by_resolution[row.get("resolution", "")].add(row.get("security_id", ""))
    excluded = by_resolution.get("NO_CURRENT_PDF_LEGACY_ONLY", set())
    if excluded != EXCLUDED_IDS:
        raise InputNotReady(f"Frozen v2 exclusions differ from the declared three: {sorted(excluded)}")
    candidate21 = set().union(*by_resolution.values()) - by_resolution.get(
        "RECOVERED_AT_LEAST_8_USABLE_FIELDS", set())
    if len(candidate21) != 21:
        raise InputNotReady("Frozen v2 unresolved set is not exactly 21 companies before the three exclusions")

    # The source-team split crosses the old coverage-resolution labels. Pin the
    # named assignments from the parent handoff, then derive xcheck11 as the
    # exact remainder of the unresolved 21 after the three no-PDF exclusions.
    raw_scope_holds = by_resolution.get("STATEMENT_LOCATION_OR_SCOPE_HOLD", set())
    if len(raw_scope_holds) != 5:
        raise InputNotReady("Expected five original statement-location/scope rows in frozen v2 coverage")
    scope5 = {"BJ:920146", "BJ:920198", "SH:600444", "SZ:301348", "SZ:002594"}
    if not scope5 - {"SZ:002594"} <= raw_scope_holds:
        raise InputNotReady("Parent-assigned scope5 identities differ from the v2 statement-location rows")
    if "SZ:002594" not in by_resolution.get("PARTIAL_FIELDS_REMAIN_UNKNOWN", set()):
        raise InputNotReady("Parent-assigned scope5 SZ:002594 differs from the v2 partial-fields row")
    ocr2 = {"SH:601390", "SZ:002083"}
    if not scope5 <= candidate21 or not ocr2 <= candidate21:
        raise InputNotReady("Parent-assigned recovery IDs are not all in the frozen unresolved v2 set")
    groups = {
        "scope5": scope5,
        "ocr2": ocr2,
        "xcheck11": candidate21 - excluded - scope5 - ocr2,
    }
    if {key: len(value) for key, value in groups.items()} != GROUPS:
        raise InputNotReady(f"Frozen v2 scope does not resolve to the parent-assigned 11/5/2 split: "
                            f"{ {key: len(value) for key, value in groups.items()} }")
    covered = set().union(*groups.values())
    if covered & excluded or covered | excluded != candidate21 or len(covered) != EXPECTED_TARGET_COUNT:
        raise InputNotReady("Recovery groups and three no-PDF exclusions do not partition the 21-company set")
    known = set().union(*by_resolution.values())
    expected = candidate21 | by_resolution.get("RECOVERED_AT_LEAST_8_USABLE_FIELDS", set())
    if known != expected:
        raise InputNotReady(f"Unexpected v2 coverage-resolution category: {sorted(known - expected)}")
    return groups, excluded, candidate21


def validate_fields_against_task(
    record: dict[str, Any], task: dict[str, Any], source: Path, allow_empty_fields: bool = False,
) -> None:
    sec, slot, doc_id = require_record_identity(record, source, allow_empty_fields=allow_empty_fields)
    if (sec, slot, doc_id) != (task["security_id"], task["slot_id"], task["document_id"]):
        raise InputNotReady(f"Record does not match frozen task identity: {source}")
    declared_pdf_sha = str(record.get("ledger_sha256") or record.get("source_pdf_sha256") or "").lower()
    expected_pdf_sha = str(task.get("ledger_sha256", "")).lower()
    if declared_pdf_sha and expected_pdf_sha and declared_pdf_sha != expected_pdf_sha:
        raise InputNotReady(f"Declared PDF SHA differs from the frozen collection plan: {source}")


def resolve_registered_source_pdf(
    task: dict[str, Any], collection_rows: list[dict[str, str]], collection_index_sha256: str,
) -> tuple[Path, dict[str, str]]:
    """Resolve only through a unique, SHA-matching in-repository collection row."""
    identity = (str(task.get("document_id", "")), str(task.get("security_id", "")),
                str(task.get("slot_id", "")))
    matches = [row for row in collection_rows
               if (row.get("document_id", ""), row.get("security_id", ""),
                   row.get("slot_id", "")) == identity]
    if len(matches) != 1:
        raise InputNotReady(f"Collection index identity must match exactly once for PDF read: {identity}; found {len(matches)}")
    index_row = matches[0]
    expected_pdf_sha = str(task.get("ledger_sha256", "")).lower()
    index_pdf_sha = str(index_row.get("sha256", "")).lower()
    if not expected_pdf_sha or index_pdf_sha != expected_pdf_sha:
        raise InputNotReady(f"Collection index PDF SHA differs from the frozen task: {identity}")
    local_file = str(index_row.get("local_file", ""))
    if not local_file:
        raise InputNotReady(f"Collection index has no in-repository local_file for {identity}")
    pdf_path, resolved_pdf_path = resolve_collection_local_file(local_file, task)
    actual_pdf_sha = sha256(pdf_path)
    if actual_pdf_sha != expected_pdf_sha:
        raise InputNotReady(f"Collection-index PDF bytes differ from the frozen task SHA: {pdf_path}")
    return pdf_path, {
        "collection_index_path": repo_relative(COLLECTION_INDEX_PATH),
        "collection_index_sha256": collection_index_sha256,
        "collection_index_local_file": local_file,
        "actual_read_path": pdf_path.relative_to(Path(os.path.abspath(str(ROOT)))).as_posix(),
        "actual_resolved_path": str(resolved_pdf_path),
        "actual_pdf_sha256": actual_pdf_sha,
    }


def install_q16_note_override(s02_module: Any):
    """Replace only Q16's stale explanatory note in this isolated recovery run."""
    original = s02_module.add
    stats: dict[str, Any] = {"calls": 0, "note": Q16_NOTE_OVERRIDE}

    def add_with_corrected_q16_note(cid, item, ok, detail, blocking=True, result_override=None):
        if cid == "Q16":
            if not isinstance(detail, dict):
                raise RuntimeError("Q16 detail must be an object before applying its local explanation")
            detail = dict(detail)
            detail["note"] = Q16_NOTE_OVERRIDE
            stats["calls"] += 1
        return original(cid, item, ok, detail, blocking, result_override)

    s02_module.add = add_with_corrected_q16_note
    return original, stats


def restore_q16_note_override(s02_module: Any, original) -> None:
    s02_module.add = original


def load_source_overlays(
    plan: dict[str, Any],
    task_by_key: dict[tuple[str, str], dict[str, Any]],
    plan_company_ids: set[str],
) -> tuple[dict[tuple[str, str], dict[str, Any]], list[dict[str, Any]], set[str],
           dict[str, int], set[str], dict[str, list[str]]]:
    """Read all 360 v2 extraction JSONs, then read bounded recovery corrections."""
    overlays: dict[tuple[str, str], dict[str, Any]] = {}
    sources: list[dict[str, Any]] = []
    if not COLLECTION_INDEX_PATH.is_file():
        raise InputNotReady(f"Current collection index is missing: {COLLECTION_INDEX_PATH}")
    collection_index_sha = sha256(COLLECTION_INDEX_PATH)
    collection_rows = read_csv(COLLECTION_INDEX_PATH)
    if sha256(COLLECTION_INDEX_PATH) != collection_index_sha:
        raise InputNotReady("Current collection index changed while being loaded")
    for task in plan["tasks"]:
        path = V2_EXTRACTED / f"{task['document_id']}.json"
        if not path.is_file():
            raise InputNotReady(f"Missing frozen v2 extraction JSON: {path}")
        doc = read_json(path)
        validate_fields_against_task(doc, task, path, allow_empty_fields=True)
        key = (task["security_id"], task["slot_id"])
        overlays[key] = doc
        sources.append({
            "kind": "frozen_v2_extraction",
            "path": repo_relative(path),
            "sha256": sha256(path),
            "security_id": key[0],
            "slot_id": key[1],
            "document_id": task["document_id"],
            "registered_pdf_path": task.get("path"),
            "registered_pdf_sha256": task.get("ledger_sha256"),
        })
    if len(overlays) != 360:
        raise InputNotReady(f"Expected 360 unique v2 security/slot records, got {len(overlays)}")

    group_ids: dict[str, set[str]] = {}
    seen_target_ids: set[str] = set()
    group_counts: dict[str, int] = {}
    expected_groups, expected_excluded, candidate21 = expected_recovery_groups_from_v2()
    if expected_excluded != EXCLUDED_IDS:
        raise InputNotReady("The three no-current-PDF exclusions differ from this script's lock")
    for group, expected_count in GROUPS.items():
        result_dir = RECOVERY / group / "corrected_results"
        if not result_dir.is_dir():
            raise InputNotReady(f"Source corrections are not ready; missing {result_dir}")
        files = sorted(result_dir.rglob("*.json"))
        if not files:
            raise InputNotReady(f"Source corrections are not ready; no JSON files under {result_dir}")
        ids: set[str] = set()
        for path in files:
            outer = read_json(path)
            record, envelope = record_core(outer)
            sec, slot, doc_id = require_record_identity(record, path)
            key = (sec, slot)
            task = task_by_key.get(key)
            if task is None:
                raise InputNotReady(f"Correction does not target a frozen v2 task: {path} -> {key}")
            validate_fields_against_task(record, task, path)
            if sec not in plan_company_ids:
                raise InputNotReady(f"Correction company is outside the v2 task universe: {sec}")
            if key in overlays and overlays[key].get("_recovery_source_path"):
                previous = overlays[key]["_recovery_source_path"]
                raise InputNotReady(f"Multiple recovery corrections target {key}: {previous} and {path}")
            if doc_id != task["document_id"]:
                raise InputNotReady(f"Correction document differs from the frozen collection index: {path}")
            if sec in EXCLUDED_IDS:
                raise InputNotReady(f"Excluded company must not receive a v3 correction: {sec}")

            # Resolve PDF bytes only through the current in-repository collection
            # index; task.path may retain a historical D: drive registration.
            pdf_path, pdf_resolution = resolve_registered_source_pdf(
                task, collection_rows, collection_index_sha,
            )

            # Keep envelope fields available for provenance without using them as data.
            record = dict(record)
            record["_recovery_source_path"] = repo_relative(path)
            record["_recovery_group"] = group
            overlays[key] = record
            ids.add(sec)
            sources.append({
                "kind": "recovery18_corrected_result",
                "group": group,
                "path": repo_relative(path),
                "sha256": sha256(path),
                "security_id": sec,
                "slot_id": slot,
                "document_id": doc_id,
                "registered_pdf_path": task.get("path"),
                "registered_pdf_sha256": str(task.get("ledger_sha256", "")).lower(),
                **pdf_resolution,
                "declared_pdf_sha256": record.get("ledger_sha256") or record.get("source_pdf_sha256"),
                "source_page_fields": sorted({str(f.get("page", "")) for f in record["fields"]
                                               if f.get("page") not in (None, "")}),
                "field_count": len(record["fields"]),
                "envelope_metadata_keys": sorted(set(envelope) - set(record)),
            })
        if len(ids) != expected_count:
            raise InputNotReady(f"{group} must contain {expected_count} distinct companies; found {len(ids)}")
        if ids != expected_groups[group]:
            raise InputNotReady(
                f"{group} corrections do not exactly cover the frozen v2 group; "
                f"missing={sorted(expected_groups[group] - ids)}, extra={sorted(ids - expected_groups[group])}"
            )
        overlap = seen_target_ids & ids
        if overlap:
            raise InputNotReady(f"Recovery source groups overlap company IDs: {sorted(overlap)}")
        seen_target_ids.update(ids)
        group_ids[group] = ids
        group_counts[group] = len(ids)

    if len(seen_target_ids) != EXPECTED_TARGET_COUNT:
        raise InputNotReady(f"Expected exactly 18 recovery companies, found {len(seen_target_ids)}")
    if seen_target_ids & EXCLUDED_IDS:
        raise InputNotReady(f"Excluded IDs appeared in recovery scope: {sorted(seen_target_ids & EXCLUDED_IDS)}")
    return (overlays, sources, seen_target_ids, group_counts, candidate21,
            {group: sorted(ids) for group, ids in group_ids.items()})


def make_s00_loaders(overlays: dict[tuple[str, str], dict[str, Any]]) -> None:
    """Install ephemeral loaders, applying v2 first and recovery18 second."""
    by_slot: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for (sec, slot), record in overlays.items():
        by_slot[slot][sec] = record
    base_extract = N.load_extract
    base_diag = N.load_diag

    def load_extract(slot: str):
        out = base_extract(slot)
        for sec, record in by_slot.get(slot, {}).items():
            out[sec] = {(f["field_id"], f.get("note", "")): f for f in record["fields"]}
        return out

    def load_diag(slot: str):
        out = base_diag(slot)
        for sec, record in by_slot.get(slot, {}).items():
            d = dict(out.get(sec, {}))
            for key in ("parse_error", "restatement", "restatement_method", "n_pages", "text_chars"):
                d[key] = record.get(key, "")
            if isinstance(record.get("crosscheck"), dict):
                crosscheck = record["crosscheck"]
                d["xcheck_pass"] = A.xcheck_verdict(crosscheck)
                for field, key in (("FIN.REV.YTD", "xcheck_rev"),
                                   ("FIN.NPP.YTD", "xcheck_npp"),
                                   ("FIN.OCF.YTD", "xcheck_ocf")):
                    d[key] = crosscheck.get(field, "")
            out[sec] = d
        return out

    N.load_extract = load_extract
    N.load_diag = load_diag


def make_empty_slot_language_cache() -> None:
    """Reuse frozen v2 diagnoses for untouched empty PDFs, as the v2 wrapper did."""
    manifest_path = V2_S00 / "normalization_manifest.json"
    manifest = read_json(manifest_path)
    index = N.load_index()
    old_lang: dict[str, tuple[Any, Any, Any]] = {}
    items = manifest.get("empty_slots_no_value", {}).get("items", [])
    for item in items:
        key = (item.get("slot_id"), item.get("security_id"))
        row = index.get(key)
        if row is None or not row.get("local_file"):
            continue
        if item.get("document_id") and row.get("document_id") != item["document_id"]:
            continue
        _alias, p = resolve_collection_local_file(row["local_file"], row)
        old_lang[str(p)] = (item.get("language"), item.get("zh_ratio", 0), item.get("text_chars", 0))
    original = N.detect_doc_language

    def detect_doc_language(path, pages=3):
        return old_lang.get(str(Path(path).resolve())) or original(path, pages)

    N.detect_doc_language = detect_doc_language


def create_v3_rules(
    output_root: Path, normalized_gzip: Path, normalized_manifest: Path,
) -> tuple[Path, list[str]]:
    base = read_json(BASE_RULES_PATH)
    rules = json.loads(json.dumps(base))
    rules["input_fingerprint"]["files"] = []
    for path in (normalized_gzip, normalized_manifest, ROOT / "data/company_master.csv"):
        rules["input_fingerprint"]["files"].append({
            "path": repo_relative(path), "sha256": sha256(path), "bytes": path.stat().st_size,
        })
    rules["input_version"] = "S00_RECOVERY18_TARGETED_REEXTRACTION_V3_20261029"
    rules["base_rules_sha256"] = sha256(BASE_RULES_PATH)
    rules["l0_addendum_path"] = repo_relative(L0_PATCH_PATH)
    if rules["base_rules_sha256"] not in S.ACCEPTED_BASE_RULES_SHA256:
        raise RuntimeError("Current S01 base rules bytes are not one of the accepted frozen hashes")
    science_keys = assert_science_rule_object_matches(rules, base)
    repair_manifest = read_json(V2_S02 / "calculation_manifest.json")
    expected_patch_sha = repair_manifest.get("l0_addendum_sha256")
    if not expected_patch_sha or sha256(L0_PATCH_PATH) != expected_patch_sha:
        raise RuntimeError("Frozen L0 patch SHA differs from the accepted v2 calculation manifest")
    path = output_root / "rules_recovery18_v3.json"
    write_json(path, rules)
    return path, science_keys


def make_row_map(rows: list[dict[str, str]], key_fields: tuple[str, ...], label: str) -> dict[tuple[str, ...], dict[str, str]]:
    out: dict[tuple[str, ...], dict[str, str]] = {}
    for row in rows:
        key = tuple(row.get(k, "") for k in key_fields)
        if key in out:
            raise RuntimeError(f"Duplicate {label} key {key}")
        out[key] = row
    return out


def assert_non_target_rows_unchanged(
    old_rows: list[dict[str, str]],
    new_rows: list[dict[str, str]],
    target_ids: set[str],
    key_fields: tuple[str, ...],
    label: str,
    expected_company_count: int = EXPECTED_NON_TARGET_COUNT,
) -> int:
    """Require every non-target row and company identity to match in all fields."""
    old_map = make_row_map(old_rows, key_fields, f"v2 {label}")
    new_map = make_row_map(new_rows, key_fields, f"v3 {label}")
    old_company_ids = {row.get("security_id", "") for row in old_rows}
    new_company_ids = {row.get("security_id", "") for row in new_rows}
    if old_company_ids != new_company_ids:
        raise RuntimeError(f"{label} company universe changed between v2/v3")
    non_target_ids = old_company_ids - target_ids
    if len(non_target_ids) != expected_company_count:
        raise RuntimeError(
            f"{label} has {len(non_target_ids)} non-target companies; expected {expected_company_count}"
        )
    old_subset = {key: row for key, row in old_map.items() if key[0] not in target_ids}
    new_subset = {key: row for key, row in new_map.items() if key[0] not in target_ids}
    if old_subset != new_subset:
        differing = sorted(key for key in old_subset.keys() | new_subset.keys()
                           if old_subset.get(key) != new_subset.get(key))
        raise RuntimeError(f"{label} non-target rows changed in full fields: {differing[:10]}")
    return len(non_target_ids)


def assert_non_target_findings_unchanged(
    old_rows: list[dict[str, str]], new_rows: list[dict[str, str]], target_ids: set[str],
) -> int:
    """Compare all complete metric-QC finding rows for non-target securities."""
    old = Counter(tuple(sorted(row.items())) for row in old_rows
                  if row.get("security_id") and row.get("security_id") not in target_ids)
    new = Counter(tuple(sorted(row.items())) for row in new_rows
                  if row.get("security_id") and row.get("security_id") not in target_ids)
    if old != new:
        raise RuntimeError("metric_qc_findings.csv changed for a non-target security")
    return sum(old.values())


def compare_rows(
    old_rows: list[dict[str, str]],
    new_rows: list[dict[str, str]],
    key_fields: tuple[str, ...],
    columns: list[str],
    label: str,
) -> list[dict[str, Any]]:
    old_map = make_row_map(old_rows, key_fields, f"v2 {label}")
    new_map = make_row_map(new_rows, key_fields, f"v3 {label}")
    deltas: list[dict[str, Any]] = []
    for key in sorted(old_map.keys() | new_map.keys()):
        old = old_map.get(key)
        new = new_map.get(key)
        changed = [column for column in columns if (old or {}).get(column, "") != (new or {}).get(column, "")]
        if not changed:
            continue
        row = {field: value for field, value in zip(key_fields, key)}
        row.update({
            "change": "ADD" if old is None else "REMOVE" if new is None else "UPDATE",
            "changed_columns": ";".join(changed),
            "old_row_json": json.dumps(old, ensure_ascii=False, sort_keys=True) if old else "",
            "new_row_json": json.dumps(new, ensure_ascii=False, sort_keys=True) if new else "",
        })
        deltas.append(row)
    return deltas


def status_counts(rows: list[dict[str, str]]) -> dict[str, int]:
    counts = Counter(row.get("metric_status", "") for row in rows)
    return {key: counts.get(key, 0) for key in STATUS_ORDER if counts.get(key, 0)} | {
        key: count for key, count in sorted(counts.items()) if key not in STATUS_ORDER
    }


def output_hashes(paths: list[Path]) -> list[dict[str, Any]]:
    return [{"path": repo_relative(path), "sha256": sha256(path), "bytes": path.stat().st_size}
            for path in paths]


def run_comparability_adapter_tests() -> dict[str, Any]:
    test_paths = [
        INTEGRATION / "test_comparability_adapter.py",
        INTEGRATION / "test_rebuild_v3.py",
    ]
    missing = [path for path in test_paths if not path.is_file()]
    if missing:
        raise RuntimeError(f"Recovery18 boundary tests are missing: {missing}")
    sys.path.insert(0, str(INTEGRATION))
    modules = []
    for index, test_path in enumerate(test_paths):
        spec = importlib.util.spec_from_file_location(f"recovery18_boundary_tests_{index}", test_path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Cannot load recovery18 boundary tests: {test_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        modules.append(module)
    suite = unittest.TestSuite(
        unittest.defaultTestLoader.loadTestsFromModule(module) for module in modules
    )
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise RuntimeError("Recovery18 boundary tests failed:\n" + stream.getvalue())
    return {
        "path": repo_relative(test_paths[0]),
        "sha256": sha256(test_paths[0]),
        "additional_test_files": [
            {"path": repo_relative(path), "sha256": sha256(path)} for path in test_paths[1:]
        ],
        "result": "PASS",
        "tests_run": result.testsRun,
    }


def execute(args: argparse.Namespace) -> int:
    out_root = output_path(args.out_dir)
    adapter_test_result = run_comparability_adapter_tests()
    plan = read_json(V2_PLAN)
    task_by_key, plan_company_ids = task_identity_map(plan)
    (overlays, source_records, target_ids, group_counts, candidate21_ids,
     group_company_ids) = load_source_overlays(
        plan, task_by_key, plan_company_ids)

    hold_spec_path = RECOVERY / "comparability_holds.json"
    if not hold_spec_path.is_file():
        raise InputNotReady(f"P04 scope-hold specification is not ready: {hold_spec_path}")
    hold_spec = C.load_scope_hold_spec(hold_spec_path)
    hold_spec_sha = sha256(hold_spec_path)
    verified_hold_sources = C.verify_hold_source_files(
        hold_spec, ROOT, approved_source_records=source_records,
    )
    for event in hold_spec["holds"]:
        sec = str(event["security_id"])
        if sec not in target_ids:
            raise InputNotReady(f"Scope-hold company is outside recovery18 target IDs: {sec}")
        matching_corrections = [source for source in source_records
                                if source["kind"] == "recovery18_corrected_result"
                                and source["security_id"] == sec
                                and source["document_id"] == event["document_id"]]
        if not matching_corrections:
            raise InputNotReady(f"Scope evidence document has no matching corrected-result input: {event['document_id']}")
        if any(source.get("actual_pdf_sha256") != str(event["source_sha256"]).lower()
               for source in matching_corrections):
            raise InputNotReady(f"Scope evidence PDF SHA differs from corrected-result source: {event['document_id']}")

    # Fail closed if any frozen/source input changes between discovery and calculation.
    for source in source_records:
        source_path = resolve_repo_path(source["path"])
        if sha256(source_path) != source["sha256"]:
            raise InputNotReady(f"Source JSON changed during preflight: {source_path}")
    plan_sha = sha256(V2_PLAN)
    parser_sha_at_v2 = str(plan.get("parser_sha256", ""))
    current_parser_sha = sha256(ROOT / "tools/a03_financial_field_extractor.py")

    out_root.mkdir(parents=True, exist_ok=False)
    s00_out = out_root / "s00"
    s02_out = out_root / "s02"
    s00_out.mkdir()
    s02_out.mkdir()
    make_s00_loaders(overlays)
    make_empty_slot_language_cache()
    N.OUT = s00_out
    N.main()

    normalized_csv = s00_out / "financial_normalized.csv"
    normalized_manifest = s00_out / "normalization_manifest.json"
    if not normalized_csv.is_file() or not normalized_manifest.is_file():
        raise RuntimeError("S00 did not create its normalized CSV and manifest")
    scope_adapter_stats = C.apply_normalized_csv(normalized_csv, hold_spec)
    if scope_adapter_stats["derived_sq_hold_count"] < 1:
        raise RuntimeError("Scope guard did not hold any derived cumulative-difference SQ row")
    for hold in scope_adapter_stats["holds"]:
        derived_fields = set(hold["derived_sq_hold_fields"])
        preserved_sq_fields = set(hold["preserved_non_cumulative_sq_fields"])
        if "FIN.OCF.SQ" not in derived_fields:
            raise RuntimeError("Expected the undisclosed OCF SQ to remain an explicit derived scope hold")
        if not {"FIN.REV.SQ", "FIN.NPP.SQ", "FIN.NPDEDT.SQ"} <= preserved_sq_fields:
            raise RuntimeError("Directly reported Q3 revenue/profit SQ values were not preserved")
    s00_doc = read_json(normalized_manifest)
    s00_doc["review_nature"] = "SELF_CHECK"
    normalized_output = s00_doc.setdefault("outputs", {}).setdefault("financial_normalized.csv", {})
    normalized_output.update({
        "rows": csv_data_row_count(normalized_csv),
        "bytes": normalized_csv.stat().st_size,
        "sha256": sha256(normalized_csv),
        "post_s00_scope_guard": {
            "applied": True,
            "adapter_path": repo_relative(Path(C.__file__)),
            "adapter_sha256": sha256(Path(C.__file__)),
            "hold_spec_path": repo_relative(hold_spec_path),
            "hold_spec_sha256": hold_spec_sha,
        },
    })
    s00_doc["recovery18_v3_overlay"] = {
        "input_version": "S00_RECOVERY18_TARGETED_REEXTRACTION_V3_20261029",
        "v2_overlay_count": 360,
        "recovery18_correction_file_count": sum(1 for x in source_records
                                                   if x["kind"] == "recovery18_corrected_result"),
        "recovery18_target_company_count": len(target_ids),
        "group_company_counts": group_counts,
        "group_company_ids": group_company_ids,
        "target_security_ids": sorted(target_ids),
        "excluded_security_ids": sorted(EXCLUDED_IDS),
        "comparability_guard": {
            "spec_path": repo_relative(hold_spec_path),
            "spec_sha256": hold_spec_sha,
            "adapter_path": repo_relative(Path(C.__file__)),
            "adapter_sha256": sha256(Path(C.__file__)),
            "verified_scope_source_pdfs": verified_hold_sources,
            **scope_adapter_stats,
            "boundary_tests": adapter_test_result,
        },
        "scope_guard_execution_model": {
            "production_s02_calculate_alone_reproduces_guard": False,
            "required_adapter_path": repo_relative(Path(C.__file__)),
            "required_adapter_sha256": sha256(Path(C.__file__)),
            "runner_installs_adapter_for_s02_main": True,
            "independent_s02_or_p_recalculation_requires_same_adapter": True,
        },
        "sources": source_records,
        "external_source_evidence_review": "NOT_PERFORMED",
        "note": "仅按登记 JSON 优先级重建；本次脚本未独立审阅 PDF 页内容。",
    }
    write_json(normalized_manifest, s00_doc)

    normalized_gzip = s00_out / "financial_normalized.csv.gz"
    with normalized_gzip.open("wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as stream:
            stream.write(normalized_csv.read_bytes())
    normalized_payload_sha = sha256(normalized_csv)
    if gzip_payload_sha256(normalized_gzip) != normalized_payload_sha:
        raise RuntimeError("S00 normalized gzip payload hash differs from normalized CSV")

    rules_path, rule_science_keys = create_v3_rules(out_root, normalized_gzip, normalized_manifest)
    rules_sha = sha256(rules_path)
    # Use the current S02 CLI API. Its P01 lock validates rules content, P05 binds
    # the v3 gzip bytes, and P06 applies the locked L0 addendum automatically.
    s01_inputs_original, input_guard_stats = C.install_s01_inputs_guard(S.s01)
    s02_add_original, q16_note_stats = install_q16_note_override(S)
    try:
        code = S.main([
            "--normalized", str(normalized_gzip),
            "--out-dir", str(s02_out),
            "--rules", str(rules_path),
        ])
    finally:
        restore_q16_note_override(S, s02_add_original)
        C.restore_s01_inputs_guard(S.s01, s01_inputs_original)
    if code != 0:
        raise RuntimeError(f"S02 returned blocking exit code {code}")
    if input_guard_stats["scope_tag_calls"] < 1 or \
            input_guard_stats["scope_tag_calls"] != input_guard_stats["scope_hold_calls"]:
        raise RuntimeError("S02 did not hold all initially-OK comparisons carrying the registered scope tag")
    run_checks = {item.get("id"): item for item in S.checks}
    if q16_note_stats["calls"] != 1:
        raise RuntimeError(f"Expected exactly one Q16 note override; got {q16_note_stats['calls']}")
    q16_check = run_checks.get("Q16", {})
    if q16_check.get("detail", {}).get("note") != Q16_NOTE_OVERRIDE:
        raise RuntimeError("Q16 output does not carry the corrected recovery explanation")
    for check_id in ("P01", "P05", "P06"):
        if check_id not in run_checks or run_checks[check_id].get("result") != "PASS":
            raise RuntimeError(f"Required S02 preflight check is not PASS: {check_id}={run_checks.get(check_id)}")

    v2_norm_rows = read_csv(V2_S00 / "financial_normalized.csv")
    v3_norm_rows = read_csv(normalized_csv)
    norm_columns = require_same_header(V2_S00 / "financial_normalized.csv", normalized_csv,
                                       "financial_normalized")
    non_target_checks: dict[str, Any] = {}
    non_target_checks["normalized_company_count"] = assert_non_target_rows_unchanged(
        v2_norm_rows, v3_norm_rows, target_ids,
        ("security_id", "period_key", "field_id"), "financial_normalized",
    )
    norm_deltas = compare_rows(v2_norm_rows, v3_norm_rows,
                               ("security_id", "period_key", "field_id"),
                               norm_columns, "normalized")
    norm_changed_ids = {str(row["security_id"]) for row in norm_deltas}
    if norm_changed_ids - target_ids:
        raise RuntimeError(f"Normalized changes escaped the 18-company scope: {sorted(norm_changed_ids - target_ids)}")
    norm_delta_path = out_root / "normalized_delta_v2_v3.csv"
    write_csv(norm_delta_path, norm_deltas,
              ["security_id", "period_key", "field_id", "change", "changed_columns",
               "old_row_json", "new_row_json"])

    v2_metrics = read_csv(V2_S02 / "all_pool_metrics.csv")
    v3_metrics = read_csv(s02_out / "all_pool_metrics.csv")
    metric_columns = require_same_header(V2_S02 / "all_pool_metrics.csv",
                                         s02_out / "all_pool_metrics.csv", "all_pool_metrics")
    non_target_checks["metrics_company_count"] = assert_non_target_rows_unchanged(
        v2_metrics, v3_metrics, target_ids, ("security_id", "metric_id"), "all_pool_metrics",
    )
    v2_non_target_metric_rows = sum(1 for row in v2_metrics if row["security_id"] not in target_ids)
    v3_non_target_metric_rows = sum(1 for row in v3_metrics if row["security_id"] not in target_ids)
    if v2_non_target_metric_rows != EXPECTED_NON_TARGET_COUNT * 12 or \
            v3_non_target_metric_rows != EXPECTED_NON_TARGET_COUNT * 12:
        raise RuntimeError(
            "Expected 12,432 all-pool metric rows for the 1,036 non-target companies; "
            f"got v2={v2_non_target_metric_rows}, v3={v3_non_target_metric_rows}"
        )
    non_target_checks["metric_rows_identical"] = v3_non_target_metric_rows
    metric_deltas = compare_rows(v2_metrics, v3_metrics,
                                 ("security_id", "metric_id"), metric_columns, "metric")
    metric_changed_ids = {str(row["security_id"]) for row in metric_deltas}
    if metric_changed_ids - target_ids:
        raise RuntimeError(f"Metric changes escaped the 18-company scope: {sorted(metric_changed_ids - target_ids)}")
    if len(v3_metrics) != 12648 or len(v2_metrics) != 12648:
        raise RuntimeError(f"Expected 12,648 pool cells in both versions; got v2={len(v2_metrics)}, v3={len(v3_metrics)}")
    metric_delta_path = out_root / "metric_delta_v2_v3.csv"
    write_csv(metric_delta_path, metric_deltas,
              ["security_id", "metric_id", "change", "changed_columns", "old_row_json", "new_row_json"])

    v2_summary = read_csv(V2_S02 / "company_metric_summary.csv")
    v3_summary = read_csv(s02_out / "company_metric_summary.csv")
    summary_columns = require_same_header(V2_S02 / "company_metric_summary.csv",
                                          s02_out / "company_metric_summary.csv",
                                          "company_metric_summary")
    non_target_checks["summary_company_count"] = assert_non_target_rows_unchanged(
        v2_summary, v3_summary, target_ids, ("security_id",), "company_metric_summary",
    )
    summary_deltas = compare_rows(v2_summary, v3_summary, ("security_id",),
                                  summary_columns, "company_summary")
    summary_changed_ids = {str(row["security_id"]) for row in summary_deltas}
    if summary_changed_ids - target_ids:
        raise RuntimeError(f"Company summary changes escaped the 18-company scope: {sorted(summary_changed_ids - target_ids)}")
    if len(v3_summary) != 1054 or len(v2_summary) != 1054:
        raise RuntimeError(f"Expected 1,054 company summaries in both versions; got v2={len(v2_summary)}, v3={len(v3_summary)}")
    summary_delta_path = out_root / "company_summary_delta_v2_v3.csv"
    write_csv(summary_delta_path, summary_deltas,
              ["security_id", "change", "changed_columns", "old_row_json", "new_row_json"])

    v2_findings = read_csv(V2_S02 / "metric_qc_findings.csv")
    v3_findings = read_csv(s02_out / "metric_qc_findings.csv")
    non_target_checks["metric_qc_finding_rows_identical"] = assert_non_target_findings_unchanged(
        v2_findings, v3_findings, target_ids,
    )

    # The coverage table is a deterministic v2-v3 comparison, not source-level validation.
    v2_by_company: dict[str, list[dict[str, str]]] = defaultdict(list)
    v3_by_company: dict[str, list[dict[str, str]]] = defaultdict(list)
    v2_period_by_company: dict[str, set[str]] = defaultdict(set)
    v3_period_by_company: dict[str, set[str]] = defaultdict(set)
    for row in v2_metrics:
        v2_by_company[row["security_id"]].append(row)
        v2_period_by_company[row["security_id"]].add(row.get("period_key", ""))
    for row in v3_metrics:
        v3_by_company[row["security_id"]].append(row)
        v3_period_by_company[row["security_id"]].add(row.get("period_key", ""))
    metric_changes_by_company: dict[str, list[str]] = defaultdict(list)
    for row in metric_deltas:
        metric_changes_by_company[str(row["security_id"])].append(str(row["metric_id"]))
    norm_changes_by_company = Counter(str(row["security_id"]) for row in norm_deltas)
    summary_by_id = {row["security_id"]: row for row in v3_summary}
    coverage_rows: list[dict[str, Any]] = []
    for sec in sorted(v2_by_company.keys() | v3_by_company.keys()):
        old_rows = v2_by_company.get(sec, [])
        new_rows = v3_by_company.get(sec, [])
        old_counts = status_counts(old_rows)
        new_counts = status_counts(new_rows)
        old_usable = old_counts.get("OK", 0) + old_counts.get("PROVISIONAL", 0)
        new_usable = new_counts.get("OK", 0) + new_counts.get("PROVISIONAL", 0)
        changed = sorted(set(metric_changes_by_company.get(sec, [])))
        if sec in target_ids:
            resolution = "CHANGED_WITHIN_RECOVERY_SCOPE" if changed else "NO_METRIC_DELTA_WITHIN_SCOPE"
        else:
            resolution = "UNCHANGED_OUTSIDE_RECOVERY_SCOPE"
        old_periods = sorted(v2_period_by_company.get(sec, set()))
        new_periods = sorted(v3_period_by_company.get(sec, set()))
        coverage_rows.append({
            "security_id": sec,
            "stock_name": summary_by_id.get(sec, {}).get("stock_name", ""),
            "in_recovery18_scope": "YES" if sec in target_ids else "NO",
            "v2_latest_period_key": old_periods[-1] if old_periods else "",
            "v3_latest_period_key": new_periods[-1] if new_periods else "",
            "latest_period_changed": "YES" if old_periods != new_periods else "NO",
            "v2_metric_cell_count": len(old_rows),
            "v3_metric_cell_count": len(new_rows),
            "v2_usable_ok_or_provisional": old_usable,
            "v3_usable_ok_or_provisional": new_usable,
            "v2_status_counts_json": json.dumps(old_counts, ensure_ascii=False, sort_keys=True),
            "v3_status_counts_json": json.dumps(new_counts, ensure_ascii=False, sort_keys=True),
            "metric_changed_count": len(changed),
            "metric_changed_ids": ";".join(changed),
            "normalized_field_delta_count": norm_changes_by_company.get(sec, 0),
            "coverage_resolution": resolution,
            "external_source_evidence_review": "NOT_PERFORMED",
        })
    if len(coverage_rows) != 1054:
        raise RuntimeError(f"Coverage comparison omitted companies: {len(coverage_rows)}")
    coverage_path = out_root / "coverage_resolution_v2_v3.csv"
    write_csv(coverage_path, coverage_rows, list(coverage_rows[0]))

    # Ensure the source bytes used to create the in-memory overlays stayed fixed
    # through the S00/S02 calculation. Record no inferred or placeholder hashes.
    for source in source_records:
        source_path = resolve_repo_path(source["path"])
        if sha256(source_path) != source["sha256"]:
            raise RuntimeError(f"Extraction JSON changed during recalculation: {source_path}")
        if source["kind"] == "recovery18_corrected_result":
            collection_index_path = resolve_repo_path(source["collection_index_path"])
            if sha256(collection_index_path) != source["collection_index_sha256"]:
                raise RuntimeError(f"Collection index changed during recalculation: {collection_index_path}")
            pdf_path, resolved_pdf_path = resolve_collection_local_file(
                source["collection_index_local_file"], source,
            )
            actual_read_path = pdf_path.relative_to(Path(os.path.abspath(str(ROOT)))).as_posix()
            if (actual_read_path != source["actual_read_path"]
                    or str(resolved_pdf_path) != source["actual_resolved_path"]):
                raise RuntimeError(f"Collection-index PDF target changed during recalculation: {pdf_path}")
            if sha256(pdf_path) != source["actual_pdf_sha256"]:
                raise RuntimeError(f"Registered PDF changed during recalculation: {pdf_path}")
    if sha256(hold_spec_path) != hold_spec_sha:
        raise RuntimeError("comparability_holds.json changed during recalculation")
    for verified in verified_hold_sources:
        pdf_path, resolved_pdf_path = resolve_collection_local_file(verified["source_pdf"], verified)
        actual_read_path = pdf_path.relative_to(Path(os.path.abspath(str(ROOT)))).as_posix()
        if (actual_read_path != verified["source_pdf"]
                or str(resolved_pdf_path) != verified["actual_resolved_path"]):
            raise RuntimeError(f"Scope evidence PDF target changed during recalculation: {pdf_path}")
        collection_index_path = resolve_repo_path(verified["collection_index_path"])
        if sha256(collection_index_path) != verified["collection_index_sha256"]:
            raise RuntimeError(f"Collection index changed during recalculation: {collection_index_path}")
        if sha256(pdf_path) != verified["actual_sha256"]:
            raise RuntimeError(f"Scope evidence PDF changed during recalculation: {pdf_path}")

    # Validate the final execution trace and summarize only checks supported by this run.
    s02_manifest_path = s02_out / "calculation_manifest.json"
    s02_manifest = read_json(s02_manifest_path)
    l0_output = s02_manifest.get("l0_addendum", {})
    l0_source = s02_manifest.get("execution_sources", {}).get("l0_rules", {})
    expected_l0_sha = sha256(L0_PATCH_PATH)
    if (l0_output.get("applied") is not True
            or l0_output.get("version") != S.L0_ADDENDUM_VERSION
            or l0_output.get("path") != repo_relative(L0_PATCH_PATH)
            or l0_output.get("sha256") != expected_l0_sha
            or l0_output.get("manifest_sha256") != expected_l0_sha
            or l0_source.get("applied") is not True
            or l0_source.get("version") != S.L0_ADDENDUM_VERSION
            or l0_source.get("path") != repo_relative(L0_PATCH_PATH)
            or l0_source.get("sha256") != expected_l0_sha):
        raise RuntimeError("P06 did not record the locked L0 addendum as applied for v3")
    if s02_manifest.get("execution_sources", {}).get("l0_classifier", {}).get("executed") is not True:
        raise RuntimeError("S02 manifest does not record execution of the L0 classifier for v3")
    s02_review_path = s02_out / "review.json"
    s02_review = read_json(s02_review_path)
    if s02_review.get("decision", "").startswith("FAIL"):
        raise RuntimeError(f"S02 review contains a failure decision: {s02_review.get('decision')}")
    input_guard_manifest = {
        **input_guard_stats,
        "preserved_original_status_counts": dict(input_guard_stats["preserved_original_status_counts"]),
    }

    compared_outputs = [norm_delta_path, metric_delta_path, summary_delta_path, coverage_path]
    output_records = output_hashes([
        normalized_csv, normalized_gzip, normalized_manifest, rules_path,
        s02_out / "all_pool_metrics.csv", s02_out / "company_metric_summary.csv",
        s02_out / "metric_qc.csv", s02_out / "metric_qc_findings.csv", *compared_outputs,
    ])
    manifest = {
        "issue_key": "S02_RECOVERY18_V3",
        "input_version": "S00_RECOVERY18_TARGETED_REEXTRACTION_V3_20261029",
        "review_nature": "SELF_CHECK",
        "decision": "SELF_CHECK_PASS_EXTERNAL_REVIEW_REQUIRED",
        "next_stage_release": "S03_LOCKED",
        "calculation_executed": True,
        "external_source_evidence_review": "NOT_PERFORMED",
        "q16_explanation_override": {
            "check_id": "Q16",
            "note": Q16_NOTE_OVERRIDE,
            "applied_by_local_s02_add_wrapper": True,
            "calls": q16_note_stats["calls"],
            "qc_result_or_science_rule_changed": False,
        },
        "target_scope": {
            "expected_company_count": EXPECTED_TARGET_COUNT,
            "company_ids": sorted(target_ids),
            "frozen_unresolved_candidate21_ids": sorted(candidate21_ids),
            "source_group_company_counts": group_counts,
            "source_group_company_ids": group_company_ids,
            "excluded_ids": sorted(EXCLUDED_IDS),
            "changes_limited_to_target_ids": True,
        },
        "overlay_order": [
            "all 360 frozen v2 extraction JSONs from remediation_20261029/extracted",
            "recovery18 corrected_results JSONs, replacing the matching security_id/slot_id record",
        ],
        "source_records": source_records,
        "frozen_inputs": {
            "v2_reextract_plan": {"path": repo_relative(V2_PLAN), "sha256": plan_sha,
                                  "parser_sha256_at_v2": parser_sha_at_v2},
            "collection_index_for_registered_pdf_reads": {
                "path": repo_relative(COLLECTION_INDEX_PATH),
                "sha256": sha256(COLLECTION_INDEX_PATH),
                "resolution_key": ["document_id", "security_id", "slot_id"],
                "actual_pdf_root": "repository-local_file_only",
            },
            "comparability_holds": {"path": repo_relative(hold_spec_path), "sha256": hold_spec_sha,
                                    "version": hold_spec["version"]},
            "v2_normalized_csv": {"path": repo_relative(V2_S00 / "financial_normalized.csv"),
                                   "sha256": sha256(V2_S00 / "financial_normalized.csv")},
            "v2_normalized_manifest": {"path": repo_relative(V2_S00 / "normalization_manifest.json"),
                                        "sha256": sha256(V2_S00 / "normalization_manifest.json")},
            "v2_all_pool_metrics": {"path": repo_relative(V2_S02 / "all_pool_metrics.csv"),
                                    "sha256": sha256(V2_S02 / "all_pool_metrics.csv")},
            "v2_company_summary": {"path": repo_relative(V2_S02 / "company_metric_summary.csv"),
                                    "sha256": sha256(V2_S02 / "company_metric_summary.csv")},
            "v2_calculation_manifest": {"path": repo_relative(V2_S02 / "calculation_manifest.json"),
                                         "sha256": sha256(V2_S02 / "calculation_manifest.json")},
            "v2_normalized_gzip": {"path": repo_relative(V2_S00 / "financial_normalized.csv.gz"),
                                    "compressed_sha256": sha256(V2_S00 / "financial_normalized.csv.gz"),
                                    "payload_sha256": gzip_payload_sha256(V2_S00 / "financial_normalized.csv.gz")},
            "v2_rules": {"path": repo_relative(V2_ROOT / "rules_recalculation_inputs.json"),
                         "sha256": sha256(V2_ROOT / "rules_recalculation_inputs.json")},
            "l0_addendum": {"path": repo_relative(L0_PATCH_PATH), "sha256": sha256(L0_PATCH_PATH),
                            "version": L.L0_ADDENDUM_VERSION if hasattr(L, "L0_ADDENDUM_VERSION") else "recorded_in_s02_manifest"},
        },
        "execution_sources": {
            "recovery_runner": {"path": repo_relative(Path(__file__)), "sha256": sha256(Path(__file__))},
            "s00_normalizer": {"path": "tools/s00_normalize.py", "sha256": sha256(ROOT / "tools/s00_normalize.py")},
            "s02_calculator": {"path": "tools/s02_calculate.py", "sha256": sha256(ROOT / "tools/s02_calculate.py")},
            "formula_engine": {"path": "tools/s01_rules_check.py", "sha256": sha256(ROOT / "tools/s01_rules_check.py")},
            "l0_classifier": {"path": "tools/l0_classify.py", "sha256": sha256(ROOT / "tools/l0_classify.py"),
                               "executed_for_v3_summary": True},
            "a03_parser": {"path": "tools/a03_financial_field_extractor.py", "sha256": current_parser_sha,
                           "sha256_registered_in_v2_plan": parser_sha_at_v2,
                           "extraction_executed_this_run": False},
            "l0_addendum": {"path": repo_relative(L0_PATCH_PATH), "sha256": sha256(L0_PATCH_PATH)},
            "rules_file": {"path": repo_relative(rules_path), "sha256": rules_sha},
            "frozen_s01_rule_comparison": {
                "result": "PASS",
                "top_level_science_keys_compared": rule_science_keys,
                "top_level_science_key_count": len(rule_science_keys),
                "input_metadata_keys_excluded": [
                    "input_fingerprint", "input_version", "base_rules_sha256", "l0_addendum_path",
                ],
            },
            "comparability_adapter": {"path": repo_relative(Path(C.__file__)),
                                       "sha256": sha256(Path(C.__file__))},
            "comparability_adapter_tests": adapter_test_result,
        },
        "comparability_guard": {
            "spec_path": repo_relative(hold_spec_path),
            "spec_sha256": hold_spec_sha,
            "version": hold_spec["version"],
            "tag": hold_spec["tag"],
            "scope_events": hold_spec["holds"],
            "verified_scope_source_pdfs": verified_hold_sources,
            "normalized_adapter": scope_adapter_stats,
            "s02_input_gate": input_guard_manifest,
            "execution_model": {
                "production_s02_calculate_alone_reproduces_guard": False,
                "required_adapter_path": repo_relative(Path(C.__file__)),
                "required_adapter_sha256": sha256(Path(C.__file__)),
                "runner_installs_adapter_for_s02_main": True,
                "independent_s02_or_p_recalculation_requires_same_adapter": True,
                "guard_active_during_s02_main": True,
                "guard_restored_in_finally_after_s02_main": True,
                "independent_s02_or_p_recalculation_performed_after_restore": False,
            },
            "boundary_tests": adapter_test_result,
            "only_originally_ok_tagged_inputs_held": True,
            "non_target_inputs_unchanged": True,
            "direct_q3_sq_reported_values_preserved": True,
            "formula_or_threshold_changed": False,
            "s03_reproduction_requires_same_guard": True,
        },
        "generated_input": {
            "normalized_csv_path": repo_relative(normalized_csv),
            "normalized_csv_sha256": normalized_payload_sha,
            "normalized_gzip_path": repo_relative(normalized_gzip),
            "normalized_gzip_sha256": sha256(normalized_gzip),
            "normalization_manifest_path": repo_relative(normalized_manifest),
            "normalization_manifest_sha256": sha256(normalized_manifest),
        },
        "comparison": {
            "normalized_delta_rows": len(norm_deltas),
            "normalized_changed_company_count": len(norm_changed_ids),
            "metric_delta_rows": len(metric_deltas),
            "metric_changed_company_count": len(metric_changed_ids),
            "company_summary_delta_rows": len(summary_deltas),
            "company_summary_changed_company_count": len(summary_changed_ids),
            "non_target_company_count": EXPECTED_NON_TARGET_COUNT,
            "non_target_rows_identical_by_output": non_target_checks,
            "outside_target_changes": [],
            "coverage_resolution_path": repo_relative(coverage_path),
            "coverage_resolution_sha256": sha256(coverage_path),
        },
        "checks": [
            {"id": "R18_SOURCE_OVERLAY", "result": "PASS", "detail": "360 v2 JSON records plus exactly 18 corrected-result companies were loaded"},
            {"id": "R18_SCOPE", "result": "PASS", "detail": "normalized/S02 diffs are restricted to the 18 correction-company IDs"},
            {"id": "R18_FORMULA_LOCK", "result": "PASS", "detail": "S02 P01 passed against frozen S01 science rules; no formula or threshold was changed"},
            {"id": "R18_Q16_EXPLANATION", "result": "PASS",
             "note": Q16_NOTE_OVERRIDE,
             "calls": q16_note_stats["calls"],
             "detail": "Only Q16 detail.note was replaced locally; its QC result and scientific calculation were not changed"},
            {"id": "R18_RULE_CORE_LOCK", "result": "PASS",
             "top_level_science_keys_compared": len(rule_science_keys),
             "detail": "Every non-input-metadata top-level rule key matches the frozen S01 rules"},
            {"id": "R18_NON_TARGET_ROWS_IDENTICAL", "result": "PASS",
             "non_target_company_count": EXPECTED_NON_TARGET_COUNT,
             "outputs": non_target_checks,
             "detail": "All full rows match for the 1,036 non-target companies across normalized data, metrics, summary, and company-specific QC findings"},
            {"id": "R18_L0", "result": "PASS", "detail": "S02 P06 recorded the locked L0 addendum applied for the registered v3 gzip"},
            {"id": "R18_P04_SCOPE_GUARD", "result": "PASS", "detail": "Only originally-OK comparisons carrying the explicit scope tag are held; other statuses are preserved"},
            {"id": "R18_P04_ADAPTER_TESTS", "result": adapter_test_result["result"],
             "tests_run": adapter_test_result["tests_run"], "path": adapter_test_result["path"],
             "sha256": adapter_test_result["sha256"]},
            {"id": "R18_SOURCE_AUDIT", "result": "NOT_PERFORMED", "detail": "PDF page content and extraction judgment require external source review"},
            {"id": "S03_GATE", "result": "LOCKED", "detail": "This v3 self-check does not release S03"},
        ],
        "outputs": output_records,
    }

    # Preserve the original calculator output and add reproducibility metadata only
    # inside this isolated v3 run directory.
    s02_manifest["recovery18_v3"] = {
        "review_nature": "SELF_CHECK",
        "external_source_evidence_review": "NOT_PERFORMED",
        "next_stage_release": "S03_LOCKED",
        "q16_explanation_override": {
            "check_id": "Q16", "note": Q16_NOTE_OVERRIDE,
            "applied_by_local_s02_add_wrapper": True,
            "qc_result_or_science_rule_changed": False,
        },
        "recovery_manifest_path": repo_relative(out_root / "recovery18_manifest.json"),
        "comparability_guard_spec_path": repo_relative(hold_spec_path),
        "comparability_guard_spec_sha256": hold_spec_sha,
        "comparability_adapter_path": repo_relative(Path(C.__file__)),
        "comparability_adapter_sha256": sha256(Path(C.__file__)),
        "scope_guard_execution_model": {
            "production_s02_calculate_alone_reproduces_guard": False,
            "required_adapter_path": repo_relative(Path(C.__file__)),
            "required_adapter_sha256": sha256(Path(C.__file__)),
            "runner_installs_adapter_for_s02_main": True,
            "independent_s02_or_p_recalculation_requires_same_adapter": True,
            "guard_restored_in_finally_after_s02_main": True,
            "independent_s02_or_p_recalculation_performed_after_restore": False,
        },
        "comparability_tagged_rows": scope_adapter_stats["tagged_row_count"],
        "derived_sq_hold_count": scope_adapter_stats["derived_sq_hold_count"],
        "s02_scope_hold_calls": input_guard_stats["scope_hold_calls"],
    }
    write_json(s02_manifest_path, s02_manifest)
    s02_review.update({
        "review_nature": "SELF_CHECK",
        "decision": "SELF_CHECK_PASS_EXTERNAL_REVIEW_REQUIRED",
        "limits": list(s02_review.get("limits", [])) + [
            "Recovery18 corrections are machine-ingested but not independently audited against PDF pages.",
            "S03 remains locked pending external source review and control authorization.",
        ],
        "next_stage_release": "S03_LOCKED",
        "external_source_evidence_review": "NOT_PERFORMED",
        "recovery18_v3_checks": [
            {"id": "Q16_EXPLANATION", "result": "PASS",
             "note": Q16_NOTE_OVERRIDE,
             "qc_result_or_science_rule_changed": False},
            {"id": "P04_SCOPE_NORMALIZED", "result": "PASS",
             "tagged_rows": scope_adapter_stats["tagged_row_count"],
             "derived_sq_holds": scope_adapter_stats["derived_sq_hold_count"]},
            {"id": "P04_SCOPE_S02_INPUTS", "result": "PASS",
             "originally_ok_tagged_inputs_held": input_guard_stats["scope_hold_calls"],
             "preexisting_non_ok_inputs_preserved": input_guard_stats["preserved_non_ok_calls"]},
            {"id": "S03_GATE", "result": "LOCKED"},
        ],
    })
    write_json(s02_review_path, s02_review)
    recovery_manifest_path = out_root / "recovery18_manifest.json"
    write_json(recovery_manifest_path, manifest)
    print(json.dumps({
        "decision": manifest["decision"],
        "review_nature": manifest["review_nature"],
        "target_company_count": len(target_ids),
        "normalized_changed_companies": len(norm_changed_ids),
        "metric_changed_companies": len(metric_changed_ids),
        "summary_changed_companies": len(summary_changed_ids),
        "coverage_resolution": repo_relative(coverage_path),
        "s03": "LOCKED",
        "recovery_manifest": repo_relative(recovery_manifest_path),
    }, ensure_ascii=False, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true",
                        help="执行完整的隔离版 S00+S02 重算；未提供时仅显示待执行提示")
    parser.add_argument("--out-dir", default=None,
                        help="输出目录，必须位于 recovery18_20261029/integration 下，且必须不存在")
    args = parser.parse_args(argv)
    if not args.execute:
        print("NOT_RUN: source JSON corrections have not been authorized for execution; pass --execute only after parent confirmation.")
        return 2
    try:
        return execute(args)
    except InputNotReady as exc:
        print(f"INPUT_NOT_READY: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
