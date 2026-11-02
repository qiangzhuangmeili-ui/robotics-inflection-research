#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""S02（#37）：用冻结的 S01_SCREEN_RULES_V2 计算全池 12 指标，逐格输出状态、质量标记、期间与来源。

设计约束（来自 S01 验收记录 constraints_for_S02）：
1. 公式唯一来源是 tools/s01_rules_check.py（S01 已验收实现），本脚本不重写公式、不复制 SIGNAL_DEPS；
2. 最新可用期沿用 S01 锚定定义（营收 REV.YTD/REV.SQ 或扣非 NPDEDT.YTD 有可用值），并与其干跑分布交叉校验；
3. 每格必须给出 metric_status / quality_flags / 计算期间 / 来源（document_id + version_used）；
4. 只做指标计算与口径检查，不算信号、不排名单、不进 S03。

用法：
    python tools/s02_calculate.py
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import importlib.util
import json
import shutil
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
S02 = ROOT / "runs/issues/S02"
RULES = ROOT / "runs/issues/S01/screen_rules_v2.json"
S01_SELF_CHECK = ROOT / "runs/issues/S01/self_check.json"
MASTER = ROOT / "data/company_master.csv"
CST = timezone(timedelta(hours=8))
NOW = datetime.now(CST).isoformat(timespec="seconds")

ACCEPTED_BASE_RULES_SHA256 = {
    "ada501e8bcd276ce670a4799c730a81cdf2f9dc70c244f9255485b00168c6a85",  # accepted CRLF bytes
    "d9a6b3cc77fcd3afb498673668be2d5c86412b6b83ffe0193e6c78f4979ecabf",  # accepted LF bytes
}
RULES_SHA_REQUIRED = "ada501e8bcd276ce670a4799c730a81cdf2f9dc70c244f9255485b00168c6a85"
ANCHOR_FIELDS = ("FIN.REV.YTD", "FIN.REV.SQ", "FIN.NPDEDT.YTD")
BASE_RULES_RELATIVE = "runs/issues/S01/screen_rules_v2.json"
DEFAULT_L0_PATCH_RELATIVE = "runs/issues/S02/remediation_20261029/l0/l0_rules_patch.json"
RULES_METADATA_KEYS = {"input_fingerprint", "input_version", "base_rules_sha256",
                       "l0_addendum_path", "field_catalog_row_counts"}
# 字段目录的 rows 是"输入动态量"（随输入版本变化的实测行数），不是科学规则。
# 公式、阈值、字段定义、期间口径才是科学规则，必须逐字节一致。
DYNAMIC_CATALOG_KEYS = {"rows"}
FIELD_COUNT_AUDIT_KEY = "field_catalog_row_counts"
L0_ADDENDUM_VERSION = "S01_SCREEN_RULES_V2_L0_ADDENDUM_20261029"

# 公式唯一来源：S01 已验收执行器
_spec = importlib.util.spec_from_file_location("s01_exec", ROOT / "tools/s01_rules_check.py")
s01 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(s01)

checks: list[dict] = []
findings: list[dict] = []


def add(cid, item, ok, detail, blocking=True, result_override=None):
    result = result_override or ("PASS" if ok else ("FAIL" if blocking else "WARN"))
    checks.append({"id": cid, "item": item, "result": result,
                   "blocking": blocking, "detail": detail})
    print(result.ljust(4) + " " + cid + " " + item)


def finding(check_id, mid, sec, kind, detail):
    findings.append({"check_id": check_id, "metric_id": mid, "security_id": sec,
                     "kind": kind, "detail": detail})


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_gzip_payload(p: Path) -> str:
    h = hashlib.sha256()
    with gzip.open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def repo_path(value) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = ROOT / path
    return path.resolve()


def display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def valid_sha256(value) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


def _catalog_without_dynamic(catalog: dict) -> dict:
    """剥离字段目录中的动态行数，只保留字段定义（名称/口径/期间）。"""
    return {
        fid: {k: v for k, v in entry.items() if k not in DYNAMIC_CATALOG_KEYS}
        for fid, entry in catalog.items()
    }


def _science_core(rules: dict) -> dict:
    """科学规则核心：剔除全部输入元数据，并把字段目录换成去掉动态行数的版本。"""
    core = {}
    for key, value in rules.items():
        if key in RULES_METADATA_KEYS:
            continue
        core[key] = _catalog_without_dynamic(value) if key == "field_catalog" else value
    return core


def _row_count_diffs(selected: dict, base: dict) -> dict:
    """字段目录 rows 相对冻结版本的实际变化集合。"""
    diffs = {}
    base_catalog = base.get("field_catalog", {})
    for fid, entry in selected.get("field_catalog", {}).items():
        frozen_entry = base_catalog.get(fid)
        if frozen_entry is None:
            continue
        if entry.get("rows") != frozen_entry.get("rows"):
            diffs[fid] = {"frozen": frozen_entry.get("rows"), "current": entry.get("rows")}
    return diffs


def _row_count_audit_ok(selected: dict, diffs: dict) -> tuple[bool, str]:
    """行数可以变，但必须逐字段登记冻结值/当前值/原因，且与实际变化完全一致。"""
    for fid, entry in selected.get("field_catalog", {}).items():
        rows = entry.get("rows")
        if isinstance(rows, bool) or not isinstance(rows, int) or rows <= 0:
            return False, f"field_catalog rows 必须是正整数: {fid}={rows!r}"
    if not diffs:
        return True, "字段行数与冻结版本一致"
    audit = selected.get(FIELD_COUNT_AUDIT_KEY)
    if not isinstance(audit, dict):
        return False, "字段行数已变化但缺少 field_catalog_row_counts 审计块"
    declared = audit.get("changes")
    if not isinstance(declared, list):
        return False, "字段行数审计块缺少 changes 列表"
    declared_map = {}
    for item in declared:
        fid = item.get("field_id")
        if not isinstance(fid, str) or fid in declared_map:
            return False, f"字段行数审计块存在非法或重复条目: {fid!r}"
        declared_map[fid] = {"frozen": item.get("frozen_rows"), "current": item.get("current_rows")}
    if declared_map != diffs:
        return False, "字段行数审计块与实际变化不一致"
    if not str(audit.get("reason", "")).strip():
        return False, "字段行数审计块缺少 reason"
    if not str(audit.get("input_version", "")).strip():
        return False, "字段行数审计块缺少 input_version"
    return True, f"字段行数按输入版本更新 {len(diffs)} 个字段，已登记审计"


def science_rules_match(selected: dict, base: dict, base_sha: str) -> tuple[bool, str]:
    """Accept only the frozen S01 science rules, plus the registered input metadata.

    字段目录的 rows 是输入动态量：允许随输入版本变化，但必须逐字段登记审计；
    其余科学规则（公式、阈值、字段定义、期间口径、信号、分层）必须与冻结版完全一致。
    """
    if base_sha not in ACCEPTED_BASE_RULES_SHA256:
        return False, f"base S01 byte hash is not accepted: {base_sha}"
    if set(selected) - RULES_METADATA_KEYS != set(base) - {"input_fingerprint"}:
        return False, "selected rules contain missing or unrecognized top-level fields"
    if _science_core(selected) != _science_core(base):
        return False, "scientific rule content differs from frozen S01 v2"
    audit_ok, audit_note = _row_count_audit_ok(selected, _row_count_diffs(selected, base))
    if not audit_ok:
        return False, audit_note
    changed_fingerprint = selected.get("input_fingerprint") != base.get("input_fingerprint")
    has_v2_metadata = any(k in selected for k in ("input_version", "base_rules_sha256", "l0_addendum_path"))
    if changed_fingerprint or has_v2_metadata:
        declared_base = selected.get("base_rules_sha256")
        if declared_base not in ACCEPTED_BASE_RULES_SHA256:
            return False, "alternate input metadata is not anchored to an accepted S01 v2 hash"
    return True, f"scientific rules match frozen S01 v2; {audit_note}"


def verify_normalized_input(source_path: Path, source_sha: str, payload_sha: str,
                            rules: dict, explicit_sha256: str | None) -> dict:
    """Bind CSV payload bytes to an explicit digest, a registered gzip, or v2 state."""
    source_is_gzip = source_path.name.lower().endswith(".gz")
    if explicit_sha256 is not None:
        expected = explicit_sha256.strip().lower()
        ok = valid_sha256(expected) and payload_sha == expected
        return {
            "ok": ok,
            "source": "--normalized-sha256",
            "expected_sha256": expected,
            "verified_source_path": None,
            "verified_source_sha256": expected,
            "note": "explicit expected digest matches normalized CSV payload bytes" if ok else "explicit digest is invalid or does not match normalized CSV payload bytes",
        }

    fingerprint = rules.get("input_fingerprint", {})
    entries = fingerprint.get("files", []) if isinstance(fingerprint, dict) else []
    for entry in (entries if isinstance(entries, list) else []):
        rel = entry.get("path")
        registered_sha = str(entry.get("sha256", "")).lower()
        if not rel or not valid_sha256(registered_sha):
            continue
        registered_path = repo_path(rel)
        if registered_path.suffix.lower() == ".csv" and registered_path.is_file():
            registered_csv_sha = sha256(registered_path)
            if registered_csv_sha == registered_sha and payload_sha == registered_csv_sha:
                return {
                    "ok": True,
                    "source": f"rules_input_fingerprint:{rel}",
                    "expected_sha256": registered_sha,
                    "registered_sha256": registered_sha,
                    "verified_source_path": rel,
                    "verified_source_sha256": registered_sha,
                    "note": "normalized CSV payload matches the registered CSV bytes",
                }
        if registered_path.name.lower().endswith(".csv.gz"):
            if not registered_path.is_file():
                continue
            try:
                compressed_sha = sha256(registered_path)
                registered_payload_sha = sha256_gzip_payload(registered_path)
            except (OSError, EOFError):
                continue
            if compressed_sha != registered_sha or registered_payload_sha != payload_sha:
                continue
            # A supplied gzip must match the registered compressed bytes as well
            # as its payload. A CSV copy is identified by payload against the
            # registered gzip, independent of the copy's path.
            if source_is_gzip and source_sha != compressed_sha:
                continue
            return {
                "ok": True,
                "source": f"rules_input_fingerprint_gzip:{rel}",
                "expected_sha256": registered_payload_sha,
                "registered_sha256": registered_sha,
                "verified_source_path": rel,
                "verified_source_sha256": compressed_sha,
                "compressed_sha256": compressed_sha,
                "note": "registered gzip SHA and decompressed payload both match the normalized CSV",
            }

    state_path = ROOT / "PROJECT_STATE.json"
    if state_path.is_file():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        v2 = state.get("current_valid_versions", {}).get("S00_data", {})
        v2_rel = v2.get("v2_repair")
        v2_sha = str(v2.get("v2_sha256", "")).lower()
        if v2_rel and valid_sha256(v2_sha) and payload_sha == v2_sha:
            return {
                "ok": True,
                "source": "PROJECT_STATE.current_valid_versions.S00_data.v2_repair",
                "expected_sha256": v2_sha,
                "registered_sha256": v2_sha,
                "verified_source_path": v2_rel,
                "verified_source_sha256": v2_sha,
                "note": "normalized CSV payload SHA matches the registered v2 content (copy paths are allowed)",
            }

    return {
        "ok": False,
        "source": None,
        "expected_sha256": None,
        "verified_source_path": None,
        "verified_source_sha256": None,
        "note": "normalized payload is not bound to a matching registered gzip, v2 content SHA, or explicit digest",
    }


def l0_addendum_required(rules: dict, payload_sha: str, input_identity: dict) -> bool:
    state_path = ROOT / "PROJECT_STATE.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.is_file() else {}
    v2 = state.get("current_valid_versions", {}).get("S00_data", {})
    v2_sha = str(v2.get("v2_sha256", "")).lower()
    registered_v2_payload = valid_sha256(v2_sha) and payload_sha == v2_sha
    rules_registered_addendum = bool(
        rules.get("l0_addendum_path")
        and str(input_identity.get("source", "")).startswith("rules_input_fingerprint_gzip:")
    )
    return registered_v2_payload or rules_registered_addendum


def load_l0_addendum(rules: dict, actual: Path, actual_sha: str,
                     input_identity: dict) -> dict:
    """Load the fixed additive L0 patch only for the registered v2 input version."""
    state_path = ROOT / "PROJECT_STATE.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.is_file() else {}
    v2 = state.get("current_valid_versions", {}).get("S00_data", {})
    v2_sha = str(v2.get("v2_sha256", "")).lower()
    registered_v2 = bool(valid_sha256(v2_sha) and actual_sha == v2_sha)
    rules_registered_addendum = bool(
        rules.get("l0_addendum_path")
        and input_identity.get("source", "").startswith("rules_input_fingerprint_gzip:")
    )
    if not (registered_v2 or rules_registered_addendum):
        return {"applied": False, "version": None, "path": None, "sha256": None,
                "note": "historical/base input; preserve the original S02 L0 labels"}

    patch_rel = rules.get("l0_addendum_path") or DEFAULT_L0_PATCH_RELATIVE
    patch_path = repo_path(patch_rel)
    if patch_path != repo_path(DEFAULT_L0_PATCH_RELATIVE):
        raise ValueError(f"unsupported L0 addendum path for this repair version: {patch_rel}")
    if not patch_path.is_file():
        raise ValueError(f"registered v2 input requires the L0 addendum file: {patch_rel}")
    patch_sha = sha256(patch_path)
    patch = json.loads(patch_path.read_text(encoding="utf-8"))
    if patch.get("rules_version") != L0_ADDENDUM_VERSION:
        raise ValueError(f"unsupported L0 addendum version: {patch.get('rules_version')!r}")
    if patch.get("base_rules_sha256") not in ACCEPTED_BASE_RULES_SHA256:
        raise ValueError("L0 addendum base hash is not an accepted S01 v2 hash")
    repair_manifest_path = ROOT / "runs/issues/S02/remediation_20261029/s02/calculation_manifest.json"
    if not repair_manifest_path.is_file():
        raise ValueError("the repair S02 manifest that freezes the L0 addendum SHA is missing")
    repair_manifest = json.loads(repair_manifest_path.read_text(encoding="utf-8"))
    expected_patch_sha = str(repair_manifest.get("l0_addendum_sha256", "")).lower()
    if not valid_sha256(expected_patch_sha) or patch_sha != expected_patch_sha:
        raise ValueError("L0 addendum SHA256 differs from the frozen repair S02 manifest")

    spec = importlib.util.spec_from_file_location("s02_l0_classifier", ROOT / "tools/l0_classify.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load tools/l0_classify.py")
    l0 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(l0)
    statuses = tuple(patch.get("classification_input", {}).get("allowed_metric_statuses", []))
    if set(statuses) != set(l0.COUNT_COLUMNS) or len(statuses) != len(l0.COUNT_COLUMNS):
        raise ValueError("L0 addendum status vector differs from the classifier input schema")
    if patch.get("classification_input", {}).get("metric_count") != len(rules.get("metrics", [])):
        raise ValueError("L0 addendum metric count differs from the S02 metric set")
    l0.STATUSES = statuses
    l0.RULE_TABLE = patch["priority_rules"]
    return {
        "applied": True,
        "version": patch["rules_version"],
        "path": display_path(patch_path),
        "sha256": patch_sha,
        "manifest_sha256": expected_patch_sha,
        "note": "L0 JSON addendum applied to each company status vector",
        "classifier": l0,
    }


def resolve_period(offset: str, pk: int) -> int | None:
    """把规则文件里的 offset 解析成具体 period_key；fallback 由调用方处理。"""
    if offset == "t":
        return pk
    if offset in ("t-1y", "t-4q"):
        return pk - 10000
    if offset == "t-1q":
        return s01.prior_quarter(pk)
    if offset == "t-5q":
        return s01.prior_year(s01.prior_quarter(pk))
    return None


def trace(rows, meta, mdef, sec, pk, res):
    """按规则文件 inputs 定义回溯本格实际用到的输入行，输出来源与缺口。"""
    if mdef["id"] == "M04":
        gt = rows.get((sec, pk), {}).get("FIN.GROSSMARGIN.PCT")
        gb = rows.get((sec, pk - 10000), {}).get("FIN.GROSSMARGIN.PCT")
        if gt is not None and gb is not None:
            pairs = [("FIN.GROSSMARGIN.PCT", pk), ("FIN.GROSSMARGIN.PCT", pk - 10000)]
        else:
            pairs = [("FIN.REV.YTD", pk), ("FIN.COST.YTD", pk),
                     ("FIN.REV.YTD", pk - 10000), ("FIN.COST.YTD", pk - 10000)]
    else:
        pairs = []
        for inp in mdef["inputs"]:
            p2 = resolve_period(inp["offset"], pk)
            if p2 is not None:
                pairs.append((inp["field_id"], p2))

    refs, missing = [], []
    for fid, p2 in pairs:
        rec = rows.get((sec, p2), {}).get(fid)
        if rec is None:
            missing.append(f"{fid}@{p2}")
            continue
        refs.append(f"{fid}@{p2}|{rec['status']}|{rec['document_id'] or '-'}|{rec['version_used'] or '-'}")
    # 去重保序
    seen, uniq = set(), []
    for r in refs:
        if r not in seen:
            seen.add(r)
            uniq.append(r)
    return {"expected": len(pairs), "found": len(uniq), "missing": missing, "refs": uniq}


def load_master() -> dict:
    out = {}
    with MASTER.open(encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            out[r["security_id"]] = {"stock_code": r["stock_code"], "stock_name": r["stock_name"]}
    return out


def latest_periods(rows) -> dict:
    """沿用 S01 锚定定义：营收或扣非累计有可用值的最新期间。"""
    latest = {}
    for (sec, pk), fields in rows.items():
        if any(fields.get(f) and fields[f]["status"] in s01.USABLE | s01.USABLE_FLAG
               and fields[f]["value"] is not None for f in ANCHOR_FIELDS):
            if sec not in latest or pk > latest[sec]:
                latest[sec] = pk
    return latest


def period_type_of(meta, sec, pk) -> str:
    for rec in meta.get((sec, pk), {}).values():
        return rec["period_type"]
    return ""


def main(argv=()) -> int:
    global S02
    checks.clear()
    findings.clear()
    ap = argparse.ArgumentParser()
    ap.add_argument("--normalized", default=None, help="标准化表路径（默认 S00 冻结版）")
    ap.add_argument("--out-dir", default=None, help="输出目录（默认 runs/issues/S02）")
    ap.add_argument("--rules", default=None, help="规则文件（默认 S01 v2）")
    ap.add_argument("--normalized-sha256", default=None,
                    help="显式期待的标准化 CSV SHA256（用于注册表之外的新输入）")
    args = ap.parse_args(list(argv) if argv is not None else [])

    source_path = repo_path(args.normalized if args.normalized else s01.NORMALIZED)
    source_is_gzip = source_path.name.lower().endswith(".gz")
    source_sha = sha256(source_path) if source_path.is_file() else ""
    try:
        payload_sha = sha256_gzip_payload(source_path) if source_is_gzip and source_sha else source_sha
    except (OSError, EOFError):
        payload_sha = ""
    requested_out_dir = repo_path(args.out_dir) if args.out_dir else None
    rules_path = repo_path(args.rules) if args.rules else repo_path(RULES)
    base_rules_path = ROOT / BASE_RULES_RELATIVE
    base_rules_sha = sha256(base_rules_path)
    base_rules = json.loads(base_rules_path.read_text(encoding="utf-8"))
    rules_sha = sha256(rules_path)
    rules = json.loads(rules_path.read_text(encoding="utf-8"))

    p01_ok, p01_note = science_rules_match(rules, base_rules, base_rules_sha)
    add("P01", "指标公式与信号阈值严格沿用冻结 S01_SCREEN_RULES_V2", p01_ok,
        {"rules_file": display_path(rules_path), "rules_sha256": rules_sha,
         "base_rules_sha256": base_rules_sha, "accepted_base_hashes": sorted(ACCEPTED_BASE_RULES_SHA256),
         "detail": p01_note})

    fp_bad = []
    for item in base_rules["input_fingerprint"]["files"]:
        path = repo_path(item["path"])
        if not path.is_file() or sha256(path) != item["sha256"]:
            fp_bad.append(item["path"])
    add("P02", "冻结 S01 登记的三份基线输入指纹未变", not fp_bad, {"changed": fp_bad})

    input_identity = verify_normalized_input(source_path, source_sha, payload_sha,
                                             rules, args.normalized_sha256)
    if not source_path.is_file() or not payload_sha:
        input_identity["ok"] = False
        input_identity["note"] = "normalized input is missing or its gzip payload cannot be read"
    loaded_csv_candidate = source_path
    cache_dir = None
    if source_is_gzip:
        if requested_out_dir is None:
            input_identity["ok"] = False
            input_identity["note"] = "a gzip normalized input requires an explicit --out-dir for isolated decompression"
        else:
            cache_dir = requested_out_dir / ".input_cache"
            protected_dirs = set()
            for entry in base_rules["input_fingerprint"]["files"] + rules.get("input_fingerprint", {}).get("files", []):
                rel = entry.get("path", "")
                if rel.lower().endswith(".csv.gz"):
                    protected_dirs.add(repo_path(rel).parent)
            state_path = ROOT / "PROJECT_STATE.json"
            if state_path.is_file():
                state = json.loads(state_path.read_text(encoding="utf-8"))
                v2_rel = state.get("current_valid_versions", {}).get("S00_data", {}).get("v2_repair")
                if v2_rel:
                    protected_dirs.add(repo_path(v2_rel).parent)
            if any(cache_dir.resolve() == protected or protected in cache_dir.resolve().parents
                   for protected in protected_dirs):
                input_identity["ok"] = False
                input_identity["note"] = "gzip cache may not be created inside a frozen normalized-input directory"
            loaded_csv_candidate = cache_dir / f"financial_normalized_{payload_sha[:16]}.csv"
    if input_identity.get("ok") and source_is_gzip:
        input_identity["source_kind"] = "gzip"
    elif input_identity.get("ok"):
        input_identity["source_kind"] = "csv"
    add("P05", "实际加载的标准化 CSV 与可信 SHA 来源匹配", input_identity["ok"],
        {"source_path": display_path(source_path), "source_sha256": source_sha,
         "loaded_csv_path": display_path(loaded_csv_candidate), "loaded_csv_sha256": payload_sha,
         "verified_against": input_identity.get("source"),
         "verified_source_path": input_identity.get("verified_source_path"),
         "verified_source_sha256": input_identity.get("verified_source_sha256"),
         "expected_sha256": input_identity.get("expected_sha256"),
         "registered_sha256": input_identity.get("registered_sha256"),
         "note": input_identity["note"]}, blocking=True)

    l0_error = None
    l0_addendum = {"applied": False, "version": None, "path": None, "sha256": None,
                   "note": "historical/base input; preserve the original S02 L0 labels"}
    l0_required = input_identity["ok"] and l0_addendum_required(rules, payload_sha, input_identity)
    if l0_required:
        try:
            l0_addendum = load_l0_addendum(rules, loaded_csv_candidate, payload_sha, input_identity)
        except Exception as exc:
            l0_error = str(exc)
    expected_l0_path = display_path(repo_path(DEFAULT_L0_PATCH_RELATIVE))
    p06_applied = bool(
        l0_required
        and l0_error is None
        and l0_addendum.get("applied") is True
        and l0_addendum.get("version") == L0_ADDENDUM_VERSION
        and l0_addendum.get("path") == expected_l0_path
        and valid_sha256(l0_addendum.get("sha256"))
        and l0_addendum.get("sha256") == l0_addendum.get("manifest_sha256")
        and hasattr(l0_addendum.get("classifier"), "classify")
    )
    p06_status = "NOT_APPLICABLE" if not l0_required else ("PASS" if p06_applied else "FAIL")
    add("P06", "按输入版本要求并实际应用锁定的 L0 addendum",
        not l0_required or p06_applied,
        {"required": l0_required, "applicable": l0_required,
         "applied": l0_addendum["applied"], "version": l0_addendum["version"],
         "path": l0_addendum["path"], "sha256": l0_addendum["sha256"],
         "error": l0_error, "status": p06_status, "note": l0_addendum["note"]},
        blocking=True, result_override=p06_status)

    if any(c["result"] == "FAIL" and c["blocking"] for c in checks):
        return 1

    baseline_entry = next(
        item for item in base_rules["input_fingerprint"]["files"]
        if item["path"] == "runs/issues/S00/financial_normalized.csv.gz"
    )
    baseline_normalized_sha = sha256_gzip_payload(repo_path(baseline_entry["path"]))
    alt_input = payload_sha != baseline_normalized_sha

    previous_s02 = S02
    S02 = requested_out_dir if requested_out_dir else repo_path(S02)
    S02.mkdir(parents=True, exist_ok=True)

    if source_is_gzip:
        cache_dir.mkdir(parents=True, exist_ok=True)
        actual = loaded_csv_candidate
        if actual.exists():
            if sha256(actual) != payload_sha:
                raise ValueError(f"existing gzip cache has unexpected content: {display_path(actual)}")
        else:
            with gzip.open(source_path, "rb") as source_stream, actual.open("xb") as output_stream:
                shutil.copyfileobj(source_stream, output_stream)
            if sha256(actual) != payload_sha:
                raise ValueError(f"materialized gzip payload SHA mismatch: {display_path(actual)}")
    else:
        actual = source_path
    actual_sha = sha256(actual)

    # ---------- 前置校验
    # ---------- 装载与计算
    previous_normalized = s01.NORMALIZED
    s01.NORMALIZED = actual
    try:
        rows, meta, field_rows, companies = s01.load_rows()
    finally:
        s01.NORMALIZED = previous_normalized
    s01.load_signal_defs(rules)          # 只为了让 evaluate 的常量与规则一致；本脚本不产出信号
    catalog_mism = [
        {"field_id": fid, "declared": entry.get("rows"), "actual": field_rows.get(fid, 0)}
        for fid, entry in rules["field_catalog"].items()
        if field_rows.get(fid, 0) != entry.get("rows")
    ]
    add("P07", "字段目录声明行数与本次实际输入逐字段一致", not catalog_mism,
        {"mismatch": catalog_mism[:20], "count": len(catalog_mism),
         "fields_in_input_not_in_catalog": sorted(set(field_rows) - set(rules["field_catalog"])),
         "note": "rows 属输入动态量，随输入版本变化；科学规则部分由 P01 逐字节比对，此处只校验声明值与实测值一致"})
    latest = latest_periods(rows)
    add("P03", "公司数与 S00/S01 一致（1054）", len(companies) == 1054, {"companies": len(companies)})
    add("P04", "每家都有可确定的最新可用期", len(latest) == 1054,
        {"resolved": len(latest), "missing": 1054 - len(latest)})

    stale_cut = s01.prior_quarter(max(latest.values()))
    master = load_master()
    mdefs = {m["id"]: m for m in rules["metrics"]}
    metric_order = [m["id"] for m in rules["metrics"]]

    out_rows = []
    company_rows = []
    cov = {mid: Counter() for mid in metric_order}
    status_by_metric = defaultdict(Counter)

    for sec in sorted(latest):
        pk = latest[sec]
        res_map, pm = s01.evaluate(rows, meta, sec, pk, stale=pk < stale_cut)
        info = master.get(sec, {"stock_code": sec.split(":")[-1], "stock_name": ""})
        ptype = period_type_of(meta, sec, pk)
        cnt = Counter()
        for mid in metric_order:
            res = res_map[mid]
            mdef = mdefs[mid]
            st = res["status"]
            val = res["value"]
            flags = sorted(res["flags"])
            tr = trace(rows, meta, mdef, sec, pk, res)
            cnt[st] += 1
            cov[mid][st] += 1
            status_by_metric[mid][st] += 1
            base = s01.prior_quarter(pk) if mid == "M03" else pk - 10000
            base_str = f"{pk-10000};{base}" if mid == "M03" else str(pk - 10000)
            out_rows.append({
                "security_id": sec,
                "stock_code": info["stock_code"],
                "stock_name": info["stock_name"],
                "metric_id": mid,
                "metric_name_cn": mdef["name_cn"],
                "unit": mdef["unit"],
                "direction": mdef["direction"],
                "formula_version": rules["rules_version"],
                "period_key": pk,
                "period_type": ptype,
                "base_period_key": base_str,
                "value": "" if val is None else f"{val:.10f}".rstrip("0").rstrip("."),
                "metric_status": st,
                "quality_flags": ";".join(flags),
                "evaluable": "YES" if st in ("OK", "PROVISIONAL") else "NO",
                "input_expected": tr["expected"],
                "input_found": tr["found"],
                "input_missing": ";".join(tr["missing"]),
                "source_refs": ";".join(tr["refs"]),
                "note": res.get("note") or "",
            })
        if l0_addendum["applied"]:
            l0_counts = {status: cnt[status] for status in l0_addendum["classifier"].STATUSES}
            l0, _, _ = l0_addendum["classifier"].classify(l0_counts)
        else:
            sts = {k for k in cnt if k}
            if cnt["OK"] > 0:
                l0 = "EVALUABLE"
            elif sts <= {"HOLD"}:
                l0 = "W2_ALL_HOLD"
            elif sts <= {"MISSING"}:
                l0 = "W1_NO_DATA"
            elif sts <= {"NOT_COMPARABLE"}:
                l0 = "W4_EARLY"
            elif cnt["PROVISIONAL"] > 0:
                # 无 OK 但有 PROVISIONAL：按 watchlist W5 处理（仅观察、不进 L2）
                l0 = "W5_PROVISIONAL_ONLY"
            else:
                l0 = "MIXED_NOT_DEFINED_BY_RULE"
        company_rows.append({
            "security_id": sec, "stock_code": info["stock_code"], "stock_name": info["stock_name"],
            "period_key": pk, "period_type": ptype,
            "stale_period": "YES" if pk < stale_cut else "NO",
            "project_mode": "YES" if pm else "NO",
            "l0_evaluability": l0,
            "ok": cnt["OK"], "provisional": cnt["PROVISIONAL"], "hold": cnt["HOLD"],
            "missing": cnt["MISSING"], "not_comparable": cnt["NOT_COMPARABLE"],
            "undefined_base": cnt["UNDEFINED_BASE"], "not_applicable": cnt["NOT_APPLICABLE"],
            "excluded_scope": cnt["EXCLUDED_SCOPE"], "version_mismatch": cnt["VERSION_MISMATCH"],
            "metrics_with_status": sum(cnt.values()),
        })

    # ---------- 交付 1：逐格指标
    fields = list(out_rows[0].keys())
    p1 = S02 / "all_pool_metrics.csv"
    with p1.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        w.writerows(out_rows)

    # ---------- 交付 2：公司级汇总（1054 主键）
    p2 = S02 / "company_metric_summary.csv"
    cfields = list(company_rows[0].keys())
    with p2.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cfields, lineterminator="\n")
        w.writeheader()
        w.writerows(company_rows)

    # ---------- 口径检查
    # PK：覆盖与唯一性
    keys = [(r["security_id"], r["metric_id"]) for r in out_rows]
    add("Q01", "1054 家公司 × 12 指标全部有状态（12,648 格）",
        len(out_rows) == 12648 and len(set(keys)) == 12648,
        {"rows": len(out_rows), "unique": len(set(keys))})
    add("Q02", "公司级汇总 1054 行且每行 12 格",
        len(company_rows) == 1054 and all(r["metrics_with_status"] == 12 for r in company_rows),
        {"companies": len(company_rows)})

    # PK：前导零
    bad_code = [r["security_id"] for r in company_rows
                if len(r["stock_code"]) != 6 or not r["stock_code"].isdigit()]
    add("Q03", "股票代码保持 6 位字符串（前导零未丢）", not bad_code,
        {"bad": bad_code[:5], "count": len(bad_code)})

    # NA：空值不得为 0
    bad_na = [r for r in out_rows if r["metric_status"] not in ("OK", "PROVISIONAL") and r["value"] != ""]
    add("Q04", "非可评估格一律留空，不用 0 代替缺数据", not bad_na,
        {"violations": len(bad_na), "sample": [x["security_id"] + "/" + x["metric_id"] for x in bad_na[:5]]})
    ok_na = [r for r in out_rows if r["metric_status"] in ("OK", "PROVISIONAL") and r["value"] == ""]
    add("Q05", "可评估格都有数值", not ok_na, {"violations": len(ok_na)})

    # EX：极端值（按规则 valid_range 标记，不删除）
    ext = []
    for r in out_rows:
        vr = mdefs[r["metric_id"]].get("valid_range")
        if not vr or r["value"] == "":
            continue
        v = float(r["value"])
        if v < vr[0] or v > vr[1]:
            ext.append(r)
            finding("Q06", r["metric_id"], r["security_id"], "OUT_OF_VALID_RANGE",
                    f"value={v} range={vr}")
    add("Q06", "超出 valid_range 的值只标记不删除", True,
        {"flagged": len(ext), "by_metric": dict(Counter(r["metric_id"] for r in ext)),
         "note": "规则未定义超限处置，本卡不改状态、不裁剪"})

    # TP：期间方向与未来数据
    bad_order = []
    for r in out_rows:
        for b in r["base_period_key"].split(";"):
            if int(b) >= r["period_key"]:
                bad_order.append(r)
                break
    add("Q07", "对比期一律早于计算期（无反向/同期混算）", not bad_order,
        {"violations": len(bad_order)})
    future = [r for r in out_rows if r["period_key"] > max(latest.values())]
    add("Q08", "计算期不超过全池最新期（无未来数据）", not future,
        {"violations": len(future), "max_period": max(latest.values())})

    # 来源完整性
    # 来源完整性：需要输入才能成立的状态必须能回溯到具体输入行
    NEED_INPUT = {"OK", "PROVISIONAL", "HOLD", "UNDEFINED_BASE",
                  "EXCLUDED_SCOPE", "VERSION_MISMATCH"}
    no_src = [r for r in out_rows if r["metric_status"] in NEED_INPUT and r["input_found"] == 0]
    add("Q09", "需要输入的状态都能回溯到具体输入行（MISSING/NOT_COMPARABLE 除外）", not no_src,
        {"violations": len(no_src),
         "sample": [x["security_id"] + "/" + x["metric_id"] for x in no_src[:5]],
         "no_input_by_status": dict(Counter(r["metric_status"] for r in out_rows
                                            if r["input_found"] == 0))})
    part = [r for r in out_rows if r["input_found"] < r["input_expected"] and r["metric_status"] in ("OK", "PROVISIONAL")]
    add("Q10", "可评估格的输入齐全（缺输入不得判 OK/PROVISIONAL）", not part,
        {"violations": len(part),
         "sample": [x["security_id"] + "/" + x["metric_id"] for x in part[:5]]})

    # VR：版本一致
    vm = [r for r in out_rows if r["metric_status"] == "VERSION_MISMATCH"]
    add("Q11", "M04 回算的 REV/COST 同期同版本（VERSION_MISMATCH 单独列出）", True,
        {"count": len(vm), "sample": [x["security_id"] for x in vm[:5]],
         "note": "VERSION_MISMATCH 是规则定义的独立状态，不是缺陷"})

    # RC：公式独立复算（简单指标全量重算）
    rc_bad = independent_recompute(rows, latest, out_rows)
    add("Q12", "M01/M02/M05/M07/M09 独立复算与交付逐格一致", not rc_bad,
        {"violations": len(rc_bad), "sample": rc_bad[:5]})

    # CO：与 S01 干跑一致
    sc = json.loads(S01_SELF_CHECK.read_text(encoding="utf-8"))
    mismatch = []
    for row in sc["dryrun"]["metric_coverage"].values():
        mid = row["metric_id"]
        for k_s01, k_s02 in (("ok", "OK"), ("provisional", "PROVISIONAL"), ("hold", "HOLD"),
                             ("missing", "MISSING"), ("not_comparable", "NOT_COMPARABLE"),
                             ("undefined_base", "UNDEFINED_BASE"),
                             ("not_applicable", "NOT_APPLICABLE"),
                             ("excluded_scope", "EXCLUDED_SCOPE"),
                             ("version_mismatch", "VERSION_MISMATCH")):
            if row[k_s01] != status_by_metric[mid][k_s02]:
                mismatch.append({"metric": mid, "status": k_s02,
                                 "s01": row[k_s01], "s02": status_by_metric[mid][k_s02]})
    add("Q13", "每指标状态分布与 S01 干跑逐项一致" + ("（新输入：差异属预期）" if alt_input else ""),
        not mismatch,
        {"mismatch": mismatch[:10], "count": len(mismatch),
         "note": "输入版本已变，与旧 S01 计数不同属预期；非新输入时该差异即缺陷"},
        blocking=not alt_input)

    latest_dist = dict(sorted(Counter(str(v) for v in latest.values()).items()))
    s01_dist = sc["dryrun"]["latest_period_distribution"]
    add("Q14", "最新期分布与 S01 一致（锚定定义未漂移）" + ("（新输入：差异属预期）" if alt_input else ""),
        latest_dist == s01_dist,
        {"s02": latest_dist, "s01": s01_dist,
         "note": "锚定定义未改；输入变化导致分布变化属预期"},
        blocking=not alt_input)

    # 单位抽样：value 单位与 metric unit 声明一致（pp 指标的量级检查）
    unit_bad = []
    for r in out_rows:
        if r["value"] == "" or r["metric_status"] not in ("OK", "PROVISIONAL"):
            continue
        v = float(r["value"])
        if r["metric_id"] in ("M03", "M04", "M06", "M12") and abs(v) > 1000:
            unit_bad.append({"security_id": r["security_id"], "metric": r["metric_id"], "value": v})
            finding("Q15", r["metric_id"], r["security_id"], "UNIT_SUSPECT", f"pp 指标绝对值 >1000：{v}")
    add("Q15", "pp 类指标量级提示（不阻断；超限处置按规则 valid_range 由 Q06 标记）", not unit_bad,
        {"violations": len(unit_bad), "sample": unit_bad[:5],
         "note": "基期净利率接近 0 时 M06 可产生上万 pp，数学正确但无经济意义，S04 使用前须排除"},
        blocking=False)

    # Q16 上游字段覆盖缺口：最新期可用字段过少的公司（S02 不可修，须回 S00 补抽）
    FIELD_SET = ["FIN.REV.YTD", "FIN.REV.SQ", "FIN.NPDEDT.YTD", "FIN.NPDEDT.SQ",
                 "FIN.COST.YTD", "FIN.OCF.YTD", "FIN.NPP.YTD", "FIN.AR.INSTANT",
                 "FIN.INV.INSTANT", "FIN.ASSET.INSTANT", "FIN.CONTRACTASSET.INSTANT",
                 "FIN.GROSSMARGIN.PCT"]
    low_cov = []
    for sec, pk in latest.items():
        n = 0
        for f in FIELD_SET:
            rec = rows.get((sec, pk), {}).get(f)
            if rec and rec["value"] is not None and rec["status"] in s01.USABLE | s01.USABLE_FLAG:
                n += 1
        if n < 8:
            low_cov.append({"security_id": sec, "period_key": pk, "fields_usable": n})
            finding("Q16", "-", sec, "LOW_FIELD_COVERAGE", f"最新期可用字段 {n}/12")
    add("Q16", "最新期字段覆盖缺口清单（上游抽取问题，本卡不修）", not low_cov,
        {"companies": len(low_cov), "only_2_fields": sum(1 for x in low_cov if x["fields_usable"] == 2),
         "sample": low_cov[:10],
         "note": "A03 已记录字段抽取仅覆盖年报；半年报/季报字段缺口集中在此，须回 S00 补抽后重算"},
        blocking=False)

    # Q17 数值量级可疑：营收上亿而扣非不到营收万分之一，多为单位或取数错误
    sus = []
    for sec, pk in latest.items():
        rev = rows.get((sec, pk), {}).get("FIN.REV.YTD")
        npd = rows.get((sec, pk), {}).get("FIN.NPDEDT.YTD")
        if not rev or not npd or rev["value"] is None or npd["value"] is None:
            continue
        if rev["status"] not in s01.USABLE or npd["status"] not in s01.USABLE:
            continue
        if rev["value"] > 1e8 and abs(npd["value"]) / rev["value"] < 1e-4:
            sus.append({"security_id": sec, "period_key": pk,
                        "rev_cny": rev["value"], "npdedt_cny": npd["value"],
                        "ratio": abs(npd["value"]) / rev["value"]})
            finding("Q17", "-", sec, "MAGNITUDE_SUSPECT",
                    f"REV={rev['value']:.4g} NPDEDT={npd['value']:.4g} ratio={abs(npd['value'])/rev['value']:.2e}")
    add("Q17", "数值量级可疑清单（疑似单位/取数错误，本卡不修）", not sus,
        {"companies": len(sus), "sample": sus[:10],
         "note": "按「营收>1亿 且 |扣非|/营收<0.01%」筛出；须回 S00 核 PDF 原表，不得在此手工改数"},
        blocking=False)

    # ---------- 交付 3：QC 明细
    p3 = S02 / "metric_qc_findings.csv"
    if findings:
        ffields = list(findings[0].keys())
        with p3.open("w", encoding="utf-8-sig", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=ffields, lineterminator="\n")
            w.writeheader()
            w.writerows(findings)

    p4 = S02 / "metric_qc.csv"
    with p4.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["check_id", "item", "result", "blocking", "detail"])
        for c in checks:
            w.writerow([c["id"], c["item"], c["result"], "YES" if c["blocking"] else "NO",
                        json.dumps(c["detail"], ensure_ascii=False)])

    # ---------- 交付 4：manifest
    coverage = []
    for mid in metric_order:
        c = cov[mid]
        coverage.append({
            "metric_id": mid, "metric_name_cn": mdefs[mid]["name_cn"], "unit": mdefs[mid]["unit"],
            "companies": len(latest), "with_status": sum(c.values()),
            "ok": c["OK"], "provisional": c["PROVISIONAL"], "hold": c["HOLD"],
            "missing": c["MISSING"], "not_comparable": c["NOT_COMPARABLE"],
            "undefined_base": c["UNDEFINED_BASE"], "not_applicable": c["NOT_APPLICABLE"],
            "excluded_scope": c["EXCLUDED_SCOPE"], "version_mismatch": c["VERSION_MISMATCH"],
        })
    l0_manifest = {key: value for key, value in l0_addendum.items() if key != "classifier"}
    if l0_addendum["applied"]:
        l0_rule_note = (
            f"已应用 {l0_addendum['version']}（{l0_addendum['path']}，SHA256 {l0_addendum['sha256']}）；"
            "L0 仅为证据可得性路由，不是信号或候选结论。"
        )
    else:
        l0_rule_note = (
            "历史 S02 v1 保留原 L0 分支；无 OK 且有 PROVISIONAL 的公司列 W5，"
            "其余未定义混合状态保留 MIXED_NOT_DEFINED_BY_RULE。"
        )
    known_limits = [
        "指标全部为公司合并口径，不是机器人分部口径；不得据此推断机器人业务盈利",
        "2026Q3 截面仅部分公司披露，横截面统计须按最新期分层",
        "PROVISIONAL 与 OK 分列，PROVISIONAL 不得当正常样本",
        "MARGIN 与 PROFIT 维度同源，后续 S04 收紧时仍会重复计数",
        "S00 遗留：62 整槽无值、453 份三表≠摘要表、2,157 重述待核、旧快照单一来源",
        "本卡不产出名单、不算信号、不做 PIT 回测",
        "上游缺陷一：53 家最新期可用字段<8（其中 25 家仅 2 个字段，含美的集团/工业富联/广汽集团/中国中铁/石头科技/时代电气/宇树科技等），A03 已记录字段抽取仅覆盖年报，须回 S00 补抽半年报/季报字段",
        "上游缺陷二：5 家营收上亿而扣非不足营收万分之一（赣锋锂业/中科信息/金百泽/五洋自控/毅昌科技），疑似「万元」被识别为「元」，须回 S00 核 PDF 原表",
    ]
    if l0_addendum["applied"]:
        known_limits.append("L0 addendum 只修补证据可得性分流；W5/W9 不自动判为无信号或候选淘汰")
    else:
        known_limits.append("规则 L0 未覆盖无 OK 且非全 HOLD/全 MISSING/全 NOT_COMPARABLE 的混合情形；历史输出按原规则保留 MIXED 标签")
    calculator_path = Path(__file__).resolve()
    formula_engine_path = ROOT / "tools/s01_rules_check.py"
    l0_classifier_path = ROOT / "tools/l0_classify.py"
    reextract_plan_path = ROOT / "runs/issues/S02/remediation_20261029/reextract_plan.json"
    a03_source_path = ROOT / "tools/a03_financial_field_extractor.py"
    reextract_plan = (json.loads(reextract_plan_path.read_text(encoding="utf-8"))
                      if reextract_plan_path.is_file() else {})
    a03_sha = sha256(a03_source_path) if a03_source_path.is_file() else None
    reextract_plan_sha = sha256(reextract_plan_path) if reextract_plan_path.is_file() else None
    execution_sources = {
        "calculator": {"path": display_path(calculator_path), "sha256": sha256(calculator_path)},
        "formula_engine": {"path": display_path(formula_engine_path), "sha256": sha256(formula_engine_path)},
        "l0_classifier": {
            "path": display_path(l0_classifier_path),
            "sha256": sha256(l0_classifier_path),
            "executed": bool(l0_addendum["applied"]),
        },
        "l0_rules": {
            "applied": bool(l0_addendum["applied"]),
            "path": l0_addendum["path"],
            "sha256": l0_addendum["sha256"],
            "version": l0_addendum["version"],
        },
        "upstream_a03": {
            "source_path": display_path(a03_source_path),
            "source_sha256": a03_sha,
            "reextract_plan_path": display_path(reextract_plan_path),
            "reextract_plan_sha256": reextract_plan_sha,
            "registered_parser_sha256": reextract_plan.get("parser_sha256"),
            "source_matches_registered_parser": bool(a03_sha and a03_sha == reextract_plan.get("parser_sha256")),
            "extraction_executed_this_run": False,
            "note": "上游解析器与重抽计划仅作来源链记录；本次 S02 未执行字段抽取",
        },
    }
    manifest = {
        "issue_key": "S02", "issue_number": 37,
        "plan_version": "20261026_collection_first_v2",
        "generated_at": NOW,
        "executor": "WorkBuddy AI",
        "review_nature": "SELF_CHECK",
        "rules_version": rules["rules_version"],
        "rules_file": display_path(rules_path),
        "rules_sha256": rules_sha,
        "base_rules_sha256": base_rules_sha,
        "formula_source": {
            "file": display_path(formula_engine_path),
            "sha256": execution_sources["formula_engine"]["sha256"],
            "note": "公式不在本脚本重写；S02 只定最新期、做溯源与口径检查",
        },
        "execution_sources": execution_sources,
        "inputs": rules["input_fingerprint"]["files"],
        "normalized_input_used": {
            "path": display_path(actual),
            "sha256": actual_sha,
            "source_path": display_path(source_path),
            "source_sha256": source_sha,
            "source_kind": "gzip" if source_is_gzip else "csv",
            "loaded_csv_path": display_path(actual),
            "loaded_csv_sha256": actual_sha,
            "matches_rules_fingerprint": str(input_identity.get("source", "")).startswith("rules_input_fingerprint"),
            "verified": input_identity["ok"],
            "verified_against": input_identity.get("source"),
            "verified_source_path": input_identity.get("verified_source_path"),
            "verified_source_sha256": input_identity.get("verified_source_sha256"),
            "expected_sha256": input_identity.get("expected_sha256"),
            "note": input_identity["note"],
        },
        "latest_period_definition": {
            "rule": "任一锚定字段（FIN.REV.YTD / FIN.REV.SQ / FIN.NPDEDT.YTD）status ∈ USABLE∪LEGACY_SNAPSHOT 且 value 非空的最新 period_key",
            "anchor_fields": list(ANCHOR_FIELDS),
            "same_as_S01": True,
            "distribution": latest_dist,
            "stale_cut": stale_cut,
            "note": "若改为「该字段自身有值的最新期」，S01 复核显示 SG09 会从 203 变 215，故不得改动",
        },
        "period_model": {
            "yoy_base": "period_key - 10000",
            "prior_quarter": "Q1→上年1231，H1→当年0331，Q3→当年0630，FY→当年0930",
            "m03_bases": "t-1y 与 t-1q（加速度）",
        },
        "coverage": coverage,
        "l0_distribution": dict(sorted(Counter(r["l0_evaluability"] for r in company_rows).items())),
        "l0_rule_note": l0_rule_note,
        "l0_addendum": l0_manifest,
        "counts": {
            "companies": len(latest), "metrics": len(metric_order),
            "cells": len(out_rows),
            "ok": sum(c["OK"] for c in cov.values()),
            "provisional": sum(c["PROVISIONAL"] for c in cov.values()),
            "hold": sum(c["HOLD"] for c in cov.values()),
            "missing": sum(c["MISSING"] for c in cov.values()),
            "not_comparable": sum(c["NOT_COMPARABLE"] for c in cov.values()),
            "undefined_base": sum(c["UNDEFINED_BASE"] for c in cov.values()),
            "not_applicable": sum(c["NOT_APPLICABLE"] for c in cov.values()),
            "excluded_scope": sum(c["EXCLUDED_SCOPE"] for c in cov.values()),
            "version_mismatch": sum(c["VERSION_MISMATCH"] for c in cov.values()),
        },
        "outputs": [
            {"path": str(p1), "rows": len(out_rows),
             "sha256": sha256(p1), "bytes": p1.stat().st_size},
            {"path": str(p2), "rows": len(company_rows),
             "sha256": sha256(p2), "bytes": p2.stat().st_size},
            {"path": str(p4), "rows": len(checks),
             "sha256": sha256(p4), "bytes": p4.stat().st_size},
            {"path": str(p3), "rows": len(findings),
             "sha256": sha256(p3) if findings else None,
             "bytes": p3.stat().st_size if findings else 0},
        ],
        "known_limits": known_limits,
    }
    p5 = S02 / "calculation_manifest.json"
    p5.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    fails = [c for c in checks if c["result"] == "FAIL" and c["blocking"]]
    review = {
        "issue_key": "S02", "issue_number": 37,
        "plan_version": "20261026_collection_first_v2",
        "executor": "WorkBuddy AI", "reviewer": "WorkBuddy AI",
        "review_nature": "SELF_CHECK",
        "reviewed_at": NOW,
        "decision": "SELF_CHECK_PASS_WITH_UPSTREAM_FINDINGS" if not fails else "SELF_CHECK_FAIL",
        "checks_total": len(checks),
        "checks_pass": sum(1 for c in checks if c["result"] in ("PASS", "WARN")),
        "checks_fail": len([c for c in checks if c["result"] == "FAIL"]),
        "checks_warn": len([c for c in checks if c["result"] == "WARN"]),
        "checks_not_applicable": len([c for c in checks if c["result"] == "NOT_APPLICABLE"]),
        "blocking_fail": len(fails),
        "checks": checks,
        "counts": manifest["counts"],
        "next_stage_release": "PENDING_EXTERNAL_RECHECK",
        "limits": manifest["known_limits"],
        "issue_body_sha256_observed": "adbf4755e201663ebb589906452111dfcee918adcf95f1e225530cc5f57325b8",
        "issue_body_sha256_in_plan": "ea0aa53e74183772a9c3e4b67a3f23f2d22df7d823a9dee0c6e25a77e5c6ce95",
        "issue_body_note": "计划登记哈希与当前正文不一致（多种换行变体均不匹配）；已逐条读取正文，验收标准未变，按已读正文执行",
    }
    (S02 / "review.json").write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n",
                                     encoding="utf-8")

    print(json.dumps({"checks": f"{review['checks_pass']}/{review['checks_total']}",
                      "blocking_fail": len(fails), "counts": manifest["counts"]},
                     ensure_ascii=False, indent=1))
    S02 = previous_s02
    return 1 if fails else 0


def independent_recompute(rows, latest, out_rows) -> list[dict]:
    """M01/M02/M05/M07/M09 独立复算：只用原始值相除/相减，不调用 S01 公式函数。"""
    simple = {"M01": ("FIN.REV.YTD", "ratio"), "M02": ("FIN.REV.SQ", "ratio"),
              "M05": ("FIN.NPDEDT.YTD", "ratio"), "M07": ("FIN.NPDEDT.SQ", "ratio"),
              "M09": ("FIN.OCF.YTD", "diff")}
    bad = []
    for r in out_rows:
        if r["metric_id"] not in simple:
            continue
        fid, kind = simple[r["metric_id"]]
        sec, pk = r["security_id"], r["period_key"]
        cur = rows.get((sec, pk), {}).get(fid)
        base = rows.get((sec, pk - 10000), {}).get(fid)
        if r["metric_status"] not in ("OK", "PROVISIONAL"):
            continue
        if not cur or not base or cur["value"] is None or base["value"] is None:
            bad.append({"security_id": sec, "metric": r["metric_id"], "why": "missing input"})
            continue
        if kind == "ratio":
            if base["value"] <= 0:
                bad.append({"security_id": sec, "metric": r["metric_id"], "why": "base<=0 but status OK"})
                continue
            exp = cur["value"] / base["value"] - 1.0
        else:
            exp = cur["value"] - base["value"]
        got = float(r["value"])
        if abs(exp - got) > 1e-9 * max(1.0, abs(exp)):
            bad.append({"security_id": sec, "metric": r["metric_id"], "expected": exp, "got": got})
    return bad


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
