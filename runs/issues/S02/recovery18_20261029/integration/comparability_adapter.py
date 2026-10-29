"""S02-local P04 comparability guard for explicitly registered scope changes.

This adapter is intentionally kept under the recovery integration directory.
It does not modify S00/S01/S02 production tools or financial formulas.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
from pathlib import Path
from typing import Any
from collections import Counter


EXPECTED_VERSION = "RECOVERY18_SOURCE_COMPARABILITY_GUARD_20261030"
EXPECTED_TAG = "SOURCE_SCOPE_CHANGE_HOLD"
EXPECTED_ACTION = "PRESERVE_REPORTED_VALUES_HOLD_COMPARISONS_AND_DERIVED_CUMULATIVE_DIFF"
EVIDENCE_MARKER_PREFIX = "SOURCE_SCOPE_CHANGE_HOLD"
DERIVED_DIFF_STATUS = "DERIVED_CUMULATIVE_DIFF"
DERIVED_HOLD_STATUS = "DERIVED_HOLD_UPSTREAM"
DERIVED_DIFF_SOURCE_KIND = "DERIVED_DIFF"
SINGLE_QUARTER_BASIS = "SINGLE_QUARTER"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_scope_hold_spec(path: Path) -> dict[str, Any]:
    spec = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(spec, dict):
        raise ValueError("comparability_holds.json must contain a JSON object")
    if spec.get("version") != EXPECTED_VERSION:
        raise ValueError(f"Unsupported comparability hold version: {spec.get('version')!r}")
    if spec.get("review_nature") != "SELF_CHECK":
        raise ValueError("Scope hold spec must identify itself as SELF_CHECK")
    if spec.get("tag") != EXPECTED_TAG:
        raise ValueError(f"Scope hold tag must be {EXPECTED_TAG}")
    if spec.get("s03_release") is not False:
        raise ValueError("Scope hold spec must keep S03 locked")
    holds = spec.get("holds")
    if not isinstance(holds, list) or not holds:
        raise ValueError("Scope hold spec must contain at least one hold")
    seen: set[tuple[str, str]] = set()
    required = ("security_id", "period_key", "document_id", "source_pdf", "source_sha256",
                "source_page", "evidence", "reason", "action", "release_condition")
    for item in holds:
        if not isinstance(item, dict):
            raise ValueError("Each scope hold must be a JSON object")
        missing = [key for key in required if item.get(key) in (None, "")]
        if missing:
            raise ValueError(f"Scope hold is missing fields: {missing}")
        key = (str(item["security_id"]), str(item["period_key"]))
        if key in seen:
            raise ValueError(f"Duplicate scope hold identity: {key}")
        seen.add(key)
        if not str(item["source_sha256"]).lower() or len(str(item["source_sha256"])) != 64:
            raise ValueError(f"Invalid source SHA256 for {key}")
        if item["action"] != EXPECTED_ACTION:
            raise ValueError(f"Unsupported scope action for {key}: {item['action']!r}")
    return spec


def verify_hold_source_files(
    spec: dict[str, Any], repo_root: Path,
    approved_source_records: list[dict[str, Any]] | None = None,
) -> list[dict[str, str]]:
    """Verify registered PDF bytes, optionally using the runner's verified index record.

    Without approved source records, retain the strict resolved-ROOT boundary.
    The optional path only permits a root-local collection-index alias whose
    exact identity and SHA match an already validated v2 task record; a
    root-junction target is accepted only at its corresponding legacy D: asset.
    """
    verified = []
    root = repo_root.resolve()
    for item in spec["holds"]:
        expected = str(item["source_sha256"]).lower()
        source = None
        if approved_source_records is None:
            key = (str(item["security_id"]), str(item["document_id"]))
            path = Path(item["source_pdf"])
            path = (path if path.is_absolute() else root / path).resolve()
            if path != root and root not in path.parents:
                raise ValueError(f"Registered PDF path escapes repository root: {path}")
            if not path.is_file():
                raise FileNotFoundError(f"Registered scope evidence PDF is missing: {path}")
            lexical_path = path
            resolved_path = path
        else:
            matched = [record for record in approved_source_records
                       if record.get("kind") == "recovery18_corrected_result"
                       and str(record.get("security_id", "")) == str(item["security_id"])
                       and str(record.get("document_id", "")) == str(item["document_id"])]
            # Current scope specifications carry no slot_id; resolve by exact
            # document/company identity and require a unique approved record.
            key = (str(item["security_id"]), str(item["document_id"]))
            if len(matched) != 1:
                raise ValueError(f"Scope PDF requires exactly one approved corrected source record: {key}")
            source = matched[0]
            if (str(source.get("actual_pdf_sha256", "")).lower() != expected
                    or str(source.get("registered_pdf_sha256", "")).lower() != expected):
                raise ValueError(f"Scope PDF SHA differs from the approved task source record: {key}")
            source_path = str(source.get("actual_read_path", ""))
            registered_path = str(item["source_pdf"]).replace("\\", "/")
            if (not source_path or source_path != registered_path
                    or source.get("collection_index_local_file") != source_path):
                raise ValueError(f"Scope PDF path differs from the approved collection-index record: {key}")
            if (source.get("collection_index_path") != "runs/collection/collection_index.csv"
                    or not source.get("collection_index_sha256")):
                raise ValueError(f"Approved source record lacks the frozen collection index identity: {key}")
            index_path = root / "runs/collection/collection_index.csv"
            if sha256(index_path) != str(source["collection_index_sha256"]).lower():
                raise ValueError("Collection index changed after PDF source resolution")
            with index_path.open("r", encoding="utf-8-sig", newline="") as stream:
                index_rows = list(csv.DictReader(stream))
            index_matches = [row for row in index_rows
                             if row.get("security_id") == str(item["security_id"])
                             and row.get("slot_id") == str(source.get("slot_id", ""))
                             and row.get("document_id") == str(item["document_id"])]
            if (len(index_matches) != 1
                    or str(index_matches[0].get("sha256", "")).lower() != expected
                    or index_matches[0].get("local_file", "").replace("\\", "/") != source_path):
                raise ValueError(f"Collection index no longer matches the approved scope source record: {key}")
            raw = Path(source_path)
            if raw.is_absolute() or ".." in raw.parts:
                raise ValueError(f"Approved scope PDF alias is not repository-relative: {source_path}")
            lexical_root = Path(os.path.abspath(str(root)))
            lexical_path = Path(os.path.abspath(str(lexical_root / raw)))
            if lexical_path != lexical_root and lexical_root not in lexical_path.parents:
                raise ValueError(f"Approved scope PDF alias escapes repository root: {source_path}")
            if not lexical_path.is_file():
                raise FileNotFoundError(f"Approved scope PDF alias is missing: {lexical_path}")
            resolved_path = lexical_path.resolve(strict=True)
            if resolved_path != root and root not in resolved_path.parents:
                sec = str(item["security_id"])
                code = sec.partition(":")[2]
                expected_legacy = (Path(r"D:\StockResearchLab\IndustryInflectionLab\robotics_data\collection\originals")
                                   / code / str(source.get("slot_id", ""))
                                   / f"{item['document_id']}.pdf").resolve(strict=True)
                if os.path.normcase(str(resolved_path)) != os.path.normcase(str(expected_legacy)):
                    raise ValueError(f"Scope PDF alias resolves outside the approved legacy D: asset: {resolved_path}")
            if str(resolved_path) != str(source.get("actual_resolved_path", "")):
                raise ValueError(f"Scope PDF resolved target differs from the approved source record: {key}")
        actual = sha256(lexical_path)
        if actual != expected:
            raise ValueError(f"Scope evidence PDF SHA differs from comparability_holds.json: {lexical_path}")
        verified.append({
            "security_id": str(item["security_id"]),
            "period_key": str(item["period_key"]),
            "document_id": str(item["document_id"]),
            "slot_id": str(source.get("slot_id", "")) if source is not None else "",
            "source_pdf": source_path if source is not None else lexical_path.relative_to(root).as_posix(),
            "actual_resolved_path": str(resolved_path),
            "expected_sha256": expected,
            "actual_sha256": actual,
            "source_page": str(item["source_page"]),
            **({
                "collection_index_path": str(source.get("collection_index_path", "")),
                "collection_index_sha256": str(source.get("collection_index_sha256", "")),
                "collection_index_local_file": str(source.get("collection_index_local_file", "")),
            } if source is not None else {}),
        })
    return verified


def _append_token(value: str, token: str) -> str:
    value = value or ""
    parts = [part for part in value.split("|") if part]
    if token not in parts:
        parts.append(token)
    return "|".join(parts)


def apply_normalized_scope_holds(
    rows: list[dict[str, str]], spec: dict[str, Any],
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    """Tag all scoped period rows and hold only cumulative-difference SQ rows.

    Reported values, source kind, and consolidation scope remain unchanged.
    Directly reported SQ rows keep their original status and value.
    """
    by_key = {(str(item["security_id"]), str(item["period_key"])): item
              for item in spec["holds"]}
    matches: dict[tuple[str, str], int] = {key: 0 for key in by_key}
    output = [dict(row) for row in rows]
    held_fields: dict[str, set[str]] = {key[0]: set() for key in by_key}
    direct_sq_fields: dict[str, set[str]] = {key[0]: set() for key in by_key}
    derived_hold_count = 0
    tagged_count = 0
    for row in output:
        key = (str(row.get("security_id", "")), str(row.get("period_key", "")))
        event = by_key.get(key)
        if event is None:
            continue
        matches[key] += 1
        row["comparability_note"] = _append_token(row.get("comparability_note", ""), EXPECTED_TAG)
        tagged_count += 1
        if row.get("period_basis") == SINGLE_QUARTER_BASIS:
            field_id = str(row.get("field_id", ""))
            if (row.get("status") == DERIVED_DIFF_STATUS
                    and row.get("source_kind") == DERIVED_DIFF_SOURCE_KIND):
                row["status"] = DERIVED_HOLD_STATUS
                trace = (f"{EVIDENCE_MARKER_PREFIX}:{event['document_id']}"
                         f":p{event['source_page']}")
                row["upstream_hold_fields"] = _append_token(row.get("upstream_hold_fields", ""), trace)
                held_fields[key[0]].add(field_id)
                derived_hold_count += 1
            elif row.get("source_kind") != DERIVED_DIFF_SOURCE_KIND:
                direct_sq_fields[key[0]].add(field_id)
    for key, count in matches.items():
        if count == 0:
            raise ValueError(f"Scope hold did not match normalized rows: {key}")
    details = [
        {"security_id": sec, "period_key": period,
         "matched_row_count": matches[(sec, period)],
         "derived_sq_hold_fields": sorted(held_fields.get(sec, set())),
         "preserved_non_cumulative_sq_fields": sorted(direct_sq_fields.get(sec, set()))}
        for sec, period in sorted(matches)
    ]
    return output, {
        "tag": EXPECTED_TAG,
        "tagged_row_count": tagged_count,
        "derived_sq_hold_count": derived_hold_count,
        "holds": details,
    }


def apply_normalized_csv(path: Path, spec: dict[str, Any]) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        columns = list(reader.fieldnames or [])
        rows = list(reader)
    if not columns:
        raise ValueError(f"Normalized CSV has no header: {path}")
    transformed, details = apply_normalized_scope_holds(rows, spec)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\r\n")
        writer.writeheader()
        writer.writerows(transformed)
    details["normalized_csv_sha256"] = sha256(path)
    details["normalized_csv_path"] = str(path)
    return details


def install_s01_inputs_guard(s01_module: Any, tag: str = EXPECTED_TAG):
    """Wrap the accepted _inputs gate, preserving every pre-existing non-OK result."""
    original = s01_module._inputs
    stats: dict[str, Any] = {
        "calls": 0,
        "scope_tag_calls": 0,
        "scope_hold_calls": 0,
        "preserved_non_ok_calls": 0,
        "preserved_original_status_counts": Counter(),
    }

    def guarded_inputs(recs):
        stats["calls"] += 1
        status, flags = original(recs)
        if status != "OK":
            stats["preserved_non_ok_calls"] += 1
            stats["preserved_original_status_counts"][status] += 1
            return status, flags
        tagged = any(rec is not None and tag in str(rec.get("comparability", "")) for rec in recs)
        if tagged:
            stats["scope_tag_calls"] += 1
            stats["scope_hold_calls"] += 1
            return "HOLD", set(flags) | {"Q01"}
        return status, flags

    s01_module._inputs = guarded_inputs
    return original, stats


def restore_s01_inputs_guard(s01_module: Any, original) -> None:
    s01_module._inputs = original
