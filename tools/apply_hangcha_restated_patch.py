#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Apply Hangcha's same-control restated comparative values to a new S00 version,
then rerun the frozen S02 calculation against that exact input fingerprint.

This script never overwrites the v9 source or the frozen S01 rule JSON.
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import shutil
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATCH_PATH = ROOT / "runs/issues/S00/restated_comparative_adoptions/hangcha_603298_2025H1.json"
BASE = ROOT / "runs/issues/S02/m07_repair_20261030/s00_v9.csv.gz"
BASE_MANIFEST = ROOT / "runs/issues/S02/m07_repair_20261030/s00_v9_manifest.json"
BASE_RULES = ROOT / "runs/issues/S02/m07_repair_20261030/rules_recalculation_inputs_v9.json"
COMPANY_MASTER = ROOT / "data/company_master.csv"
S01_RULES = ROOT / "runs/issues/S01/screen_rules_v2.json"
S02_SCRIPT = ROOT / "tools/s02_calculate.py"

OUT_ROOT = ROOT / "runs/issues/S02/hangcha_restated_20261031"
S00_DIR = OUT_ROOT / "s00_v10"
S02_DIR = OUT_ROOT / "s02_v10"
OUT_GZ = S00_DIR / "s00_v10.csv.gz"
OUT_MANIFEST = S00_DIR / "s00_v10_manifest.json"
OUT_AUDIT = S00_DIR / "s00_v10_adoption_audit.csv"
OUT_RULES = OUT_ROOT / "rules_recalculation_inputs_v10.json"
OUT_HANGCHA = OUT_ROOT / "hangcha_metrics.csv"
OUT_VALIDATION = OUT_ROOT / "hangcha_validation.json"

CST = timezone(timedelta(hours=8))
NOW = datetime.now(CST).isoformat(timespec="seconds")
AS_OF = "2026-10-25"
SEC = "SH:603298"
CODE = "603298"
NAME = "杭叉集团"
ADOPTED_MARKER = "RESTATED_COMPARATIVE_ADOPTED_SAME_CONTROL"

YTD_FIELDS = (
    "FIN.REV.YTD", "FIN.COST.YTD", "FIN.NP.YTD",
    "FIN.NPP.YTD", "FIN.NPDEDT.YTD", "FIN.OCF.YTD",
)
DERIVED_YTD_FIELDS = (
    "FIN.GROSSPROFIT.YTD", "FIN.GROSSMARGIN.PCT",
    "FIN.NPMARGIN.PCT", "FIN.OCF_TO_NP.RATIO",
)
SQ_FIELDS = ("FIN.REV.SQ", "FIN.NPP.SQ", "FIN.NPDEDT.SQ", "FIN.OCF.SQ")


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def dec(value: str | Decimal) -> Decimal:
    return Decimal(str(value))


def money(value: Decimal) -> str:
    return f"{value:,.2f}"


def marker_note(row: dict) -> None:
    old = [x for x in (row.get("comparability_note") or "").split("|") if x]
    drop = {
        "RESTATED_PRIOR_YEARS_UNRECALCULATED",
        "RESTATEMENT_UNRESOLVED",
        ADOPTED_MARKER,
    }
    keep = [x for x in old if x not in drop]
    keep.append(ADOPTED_MARKER)
    row["comparability_note"] = "|".join(dict.fromkeys(keep))
    row["restatement_flag"] = "是"


def set_adopted_metadata(row: dict, reason: str, version: str | None = None) -> None:
    marker_note(row)
    row["adoption_reason"] = reason
    if version:
        row["version_used"] = version
    row["as_of"] = AS_OF
    row["currency"] = "CNY"
    row["consolidation_scope"] = "CONSOLIDATED"


def make_audit(row: dict, old_value: str, old_doc: str, action: str, reason: str) -> dict:
    return {
        "security_id": SEC,
        "stock_code": CODE,
        "stock_name": NAME,
        "period_key": row["period_key"],
        "period_type": row["period_type"],
        "period_basis": row["period_basis"],
        "field_id": row["field_id"],
        "action": action,
        "value_before": old_value,
        "value_after": row["value_cny"],
        "status_before": row.get("_status_before", row["status"]),
        "status_after": row["status"],
        "document_id_before": old_doc,
        "document_id_after": row["document_id"],
        "original_document_id": row.get("original_document_id", ""),
        "source_page_after": row.get("source_page", ""),
        "published_on_after": row.get("published_on", ""),
        "version_used_after": row.get("version_used", ""),
        "comparability_note_after": row.get("comparability_note", ""),
        "reason": reason,
    }


def main() -> int:
    for p in (PATCH_PATH, BASE, BASE_MANIFEST, BASE_RULES, COMPANY_MASTER, S01_RULES, S02_SCRIPT):
        if not p.is_file():
            raise FileNotFoundError(p)

    patch = json.loads(PATCH_PATH.read_text(encoding="utf-8"))
    base_manifest = json.loads(BASE_MANIFEST.read_text(encoding="utf-8"))
    if patch["security_id"] != SEC or patch["stock_code"] != CODE:
        raise ValueError("patch security identity mismatch")
    if sha_file(BASE) != base_manifest["sha256"]:
        raise ValueError("S00 v9 compressed SHA does not match its manifest")
    if base_manifest["rows"] != 229666:
        raise ValueError(f"unexpected S00 v9 row count: {base_manifest['rows']}")

    source_docs = patch["source_documents"]
    for key in ("q1_2026", "h1_2026", "q1_2025", "h1_2025", "annual_2025"):
        d = source_docs[key]
        if len(d["sha256"]) != 64 or not d["document_id"] or not d["published_on"]:
            raise ValueError(f"source document metadata incomplete: {key}")
        if d["published_on"] > AS_OF:
            raise ValueError(f"source is later than frozen as_of: {key}")

    with gzip.open(BASE, "rt", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        fieldnames = reader.fieldnames
        rows = list(reader)
    if not fieldnames or len(rows) != base_manifest["rows"]:
        raise ValueError("S00 v9 CSV row count/header mismatch")

    index: dict[tuple[str, str, str, str], dict] = {}
    for row in rows:
        k = (row["security_id"], row["period_key"], row["period_basis"], row["field_id"])
        if k in index:
            raise ValueError(f"duplicate normalized key: {k}")
        index[k] = row

    audit: list[dict] = []

    def get(period_key: str, basis: str, field_id: str) -> dict:
        k = (SEC, str(period_key), basis, field_id)
        if k not in index:
            raise KeyError(f"normalized row missing: {k}")
        return index[k]

    def adopt_direct_ytd(item: dict) -> None:
        row = get(item["period_key"], "YTD_CUMULATIVE", item["field_id"])
        expected_doc = item["expected_current_document_id"]
        if row["document_id"] != expected_doc:
            raise ValueError(
                f"original document guard failed for {item['field_id']} {item['period_key']}: "
                f"{row['document_id']} != {expected_doc}"
            )
        source = source_docs[item["source_key"]]
        old_value, old_doc = row["value_cny"], row["document_id"]
        old_status = row["status"]
        if old_value == "":
            raise ValueError(f"cannot adopt over empty value: {item['field_id']} {item['period_key']}")
        row["_status_before"] = old_status
        row["value_before_adoption"] = old_value
        row["value_cny"] = str(item["value"])
        row["value_raw"] = money(dec(item["value"]))
        row["unit_raw"] = item["unit"]
        row["unit_scale"] = "1"
        row["status"] = item["status"]
        row["status_reason"] = "RESTATED_COMPARATIVE_VALUE_ADOPTED_FROM_OFFICIAL_REPORT"
        row["source_kind"] = "PDF_STATEMENT"
        row["document_id"] = source["document_id"]
        row["slot_id"] = source["slot_id"]
        row["source_page"] = str(item["source_page"])
        row["evidence_label"] = item["field_name_cn"]
        row["published_on"] = source["published_on"]
        row["pit_status"] = "PIT_OK"
        row["version_used"] = "RESTATED_COMPARATIVE"
        row["original_document_id"] = old_doc
        row["quarterly_inputs"] = ""
        reason = (
            f'{source["document_id"]} {source["title"]} p.{item["source_page"]}; '
            f'采用同一控制下合并追溯调整后的 {item["period_label"]} 比较值；'
            f'原始来源 {old_doc} 保留于 original_document_id'
        )
        set_adopted_metadata(row, reason, "RESTATED_COMPARATIVE")
        audit.append(make_audit(row, old_value, old_doc, "ADOPT_RESTATED_YTD", reason))
        row.pop("_status_before", None)

    for item in patch["ytd_adoptions"]:
        adopt_direct_ytd(item)

    # 2025Q1：报告比较表的 Q1 累计值即单季值。与 2025 年报原始分季值逐项对账后，
    # 将同值来源更新为 2026Q1 官方报告的调整后比较列。
    q1_source = source_docs["q1_2026"]
    for item in patch["q1_single_quarter_checks"]:
        row = get("20250331", "SINGLE_QUARTER", item["field_id"])
        old_value, old_doc = row["value_cny"], row["document_id"]
        if old_value == "" or abs(dec(old_value) - dec(item["value"])) > Decimal("0.01"):
            raise ValueError(
                f'2025Q1 single-quarter cross-check failed {item["field_id"]}: '
                f'{old_value} vs {item["value"]}'
            )
        row["_status_before"] = row["status"]
        row["value_before_adoption"] = old_value
        row["value_cny"] = str(item["value"])
        row["value_raw"] = money(dec(item["value"]))
        row["unit_raw"] = "元"
        row["unit_scale"] = "1"
        row["status"] = "DERIVED_Q1_EQUALS_YTD"
        row["status_reason"] = "2026Q1官方报告调整后比较值；Q1累计即单季"
        row["source_kind"] = "PDF_STATEMENT"
        row["document_id"] = q1_source["document_id"]
        row["slot_id"] = q1_source["slot_id"]
        row["source_page"] = str(q1_source["key_table_page"])
        row["evidence_label"] = "2025Q1调整后比较值（Q1累计即单季）"
        row["published_on"] = q1_source["published_on"]
        row["pit_status"] = "PIT_OK"
        row["version_used"] = "RESTATED_COMPARATIVE"
        row["original_document_id"] = old_doc
        reason = (
            f'{q1_source["document_id"]} p.{q1_source["key_table_page"]}; '
            "2025Q1调整后比较值与原2025年报分季表同值，更新来源链，不改变数值"
        )
        set_adopted_metadata(row, reason, "RESTATED_COMPARATIVE")
        audit.append(make_audit(row, old_value, old_doc, "ADOPT_RESTATED_Q1_SAME_VALUE", reason))
        row.pop("_status_before", None)

    # 2025Q2：用同一控制追溯口径下的 H1 累计值减 Q1 累计值。
    q1_values = {
        "FIN.REV.SQ": "4455524706.04",
        "FIN.NPP.SQ": "431975966.52",
        "FIN.NPDEDT.SQ": "419311660.58",
        "FIN.OCF.SQ": "198826564.31",
    }
    h1_values = {
        "FIN.REV.SQ": "9296138420.08",
        "FIN.NPP.SQ": "1115391633.83",
        "FIN.NPDEDT.SQ": "1091573107.27",
        "FIN.OCF.SQ": "347414148.08",
    }
    h1_source = source_docs["h1_2026"]
    q2_bridge = []
    for item in patch["q2_single_quarter"]:
        row = get("20250630", "SINGLE_QUARTER", item["field_id"])
        old_value, old_doc = row["value_cny"], row["document_id"]
        if old_value == "" or dec(old_value) != dec(item["previous_value"]):
            raise ValueError(
                f'2025Q2 original-value guard failed {item["field_id"]}: '
                f'{old_value} != {item["previous_value"]}'
            )
        bridge_value = dec(h1_values[item["field_id"]]) - dec(q1_values[item["field_id"]])
        if item["adopt"]:
            if bridge_value != dec(item["expected_value"]):
                raise ValueError(f'Q2 bridge mismatch for {item["field_id"]}: {bridge_value}')
            row["_status_before"] = row["status"]
            row["value_before_adoption"] = old_value
            row["value_cny"] = str(item["expected_value"])
            row["value_raw"] = ""
            row["unit_raw"] = "元"
            row["unit_scale"] = "1"
            row["status"] = "DERIVED_CUMULATIVE_DIFF"
            row["status_reason"] = "同一控制追溯调整口径：2025H1调整后比较值−2025Q1调整后比较值"
            row["source_kind"] = "DERIVED_DIFF"
            row["document_id"] = h1_source["document_id"]
            row["slot_id"] = h1_source["slot_id"]
            row["source_page"] = str(h1_source["key_table_page"])
            row["evidence_label"] = "2025H1调整后比较值−2025Q1调整后比较值"
            row["published_on"] = h1_source["published_on"]
            row["pit_status"] = "PIT_OK"
            row["version_used"] = "RESTATED_COMPARATIVE_BRIDGE"
            row["original_document_id"] = old_doc
            q1_source = source_docs["q1_2026"]
            inputs = (
                f'2025Q1_adj={q1_values[item["field_id"]]} '
                f'({q1_source["document_id"]} p.{q1_source["key_table_page"]}); '
                f'2025H1_adj={h1_values[item["field_id"]]} '
                f'({h1_source["document_id"]} p.{h1_source["key_table_page"]}); '
                f'Q2=H1-Q1={item["expected_value"]}'
            )
            row["quarterly_inputs"] = inputs
            reason = (
                f'同一控制下合并追溯比较桥接；{inputs}；'
                f'原2025年报分季值 {old_value} 仅保留于 value_before_adoption'
            )
            set_adopted_metadata(row, reason, "RESTATED_COMPARATIVE_BRIDGE")
            audit.append(make_audit(row, old_value, old_doc, "ADOPT_RESTATED_Q2_BRIDGE", reason))
            row.pop("_status_before", None)
            q2_bridge.append({
                "field_id": item["field_id"],
                "q1_adjusted": q1_values[item["field_id"]],
                "h1_adjusted": h1_values[item["field_id"]],
                "q2_adjusted": str(bridge_value),
                "original_q2": old_value,
                "adopted": True,
            })
        else:
            if abs(bridge_value - dec(item["expected_bridge_value"])) > Decimal("0.01"):
                raise ValueError(f'Q2 OCF bridge check failed: {bridge_value}')
            if abs(dec(old_value) - bridge_value) > Decimal("0.01"):
                raise ValueError(f'Q2 OCF original-vs-bridge exceeds 0.01: {old_value} vs {bridge_value}')
            reason = (
                f"不采纳：2025H1−2025Q1桥接={bridge_value}，原2025年报Q2={old_value}，"
                "差异仅0.01元，按尾数舍入差异留痕，保留原官方分季值"
            )
            audit.append(make_audit(row, old_value, old_doc, "KEEP_ORIGINAL_Q2_ROUNDING", reason))
            q2_bridge.append({
                "field_id": item["field_id"],
                "q1_adjusted": q1_values[item["field_id"]],
                "h1_adjusted": h1_values[item["field_id"]],
                "q2_adjusted_bridge": str(bridge_value),
                "original_q2": old_value,
                "adopted": False,
                "reason": reason,
            })

    # 对 H1/Q1 的派生利润率和现金含量字段重新计算，不能沿用旧版本派生值。
    def recalc_derived(period_key: str, source_key: str) -> None:
        source = source_docs[source_key]
        rev = dec(get(period_key, "YTD_CUMULATIVE", "FIN.REV.YTD")["value_cny"])
        cost = dec(get(period_key, "YTD_CUMULATIVE", "FIN.COST.YTD")["value_cny"])
        npp = dec(get(period_key, "YTD_CUMULATIVE", "FIN.NPP.YTD")["value_cny"])
        ocf = dec(get(period_key, "YTD_CUMULATIVE", "FIN.OCF.YTD")["value_cny"])
        derived = {
            "FIN.GROSSPROFIT.YTD": (rev - cost).quantize(Decimal("0.01")), 
            "FIN.GROSSMARGIN.PCT": ((rev - cost) / rev * Decimal(100)).quantize(Decimal("0.000001")),
            "FIN.NPMARGIN.PCT": (npp / rev * Decimal(100)).quantize(Decimal("0.000001")),
            "FIN.OCF_TO_NP.RATIO": (ocf / npp).quantize(Decimal("0.000001")) if npp > 0 else None,
        }
        meta = {
            "FIN.GROSSPROFIT.YTD": ("元", "1", "DERIVED_REV_MINUS_COST", "REV−COST"),
            "FIN.GROSSMARGIN.PCT": ("%", "pct", "DERIVED_GP_DIV_REV", "GP/REV"),
            "FIN.NPMARGIN.PCT": ("%", "pct", "DERIVED_NPP_DIV_REV", "NPP/REV"),
            "FIN.OCF_TO_NP.RATIO": ("倍", "times", "DERIVED_OCF_DIV_NPP", "OCF/NPP"),
        }
        for fid, value in derived.items():
            if value is None:
                continue
            row = get(period_key, "YTD_CUMULATIVE", fid)
            old_value, old_doc = row["value_cny"], row["document_id"]
            row["_status_before"] = row["status"]
            row["value_before_adoption"] = old_value
            row["value_cny"] = str(value)
            row["value_raw"] = ""
            row["unit_raw"], row["unit_scale"], row["source_kind"], row["evidence_label"] = meta[fid]
            row["status"] = "DERIVED"
            row["status_reason"] = "基于已采用的追溯调整后累计字段重新派生"
            row["document_id"] = source["document_id"]
            row["slot_id"] = source["slot_id"]
            row["source_page"] = ""
            row["published_on"] = source["published_on"]
            row["pit_status"] = "PIT_OK"
            row["version_used"] = "RESTATED_COMPARATIVE"
            row["original_document_id"] = old_doc
            reason = (
                f'重新派生：{fid}，使用 {source["document_id"]} 的追溯调整后比较字段；'
                "公式沿用 S00 derive_ratios"
            )
            set_adopted_metadata(row, reason, "RESTATED_COMPARATIVE")
            audit.append(make_audit(row, old_value, old_doc, "RECALCULATE_DERIVED_YTD", reason))
            row.pop("_status_before", None)

    recalc_derived("20250331", "q1_2026")
    recalc_derived("20250630", "h1_2026")

    # 当前期输入不改数值；只登记这些字段与已采用的同口径比较基数配对。
    def mark_current(period_key: str, basis: str, fields: tuple[str, ...], reason: str) -> None:
        for fid in fields:
            row = get(period_key, basis, fid)
            old_value, old_doc, old_status = row["value_cny"], row["document_id"], row["status"]
            if old_value == "":
                raise ValueError(f"current comparison input missing: {period_key} {fid}")
            set_adopted_metadata(row, reason)
            audit.append(make_audit(row, old_value, old_doc, "MARK_CURRENT_COMPARABILITY_ADOPTED", reason))

    current_reason = (
        "当前期与同一控制下合并追溯调整后的上年同期比较基数配对；"
        "当前期金额未修改，字段级比较口径已核验"
    )
    for pk in ("20260331", "20260630"):
        mark_current(pk, "YTD_CUMULATIVE", YTD_FIELDS, current_reason)
        mark_current(pk, "YTD_CUMULATIVE", DERIVED_YTD_FIELDS, current_reason)
        mark_current(pk, "SINGLE_QUARTER", SQ_FIELDS, current_reason)

    # 输出新 S00 版本；源 v9 保持不动。
    S00_DIR.mkdir(parents=True, exist_ok=True)
    csv_buf = io.StringIO(newline="")
    writer = csv.DictWriter(csv_buf, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        row.pop("_status_before", None)
        writer.writerow(row)
    csv_payload = csv_buf.getvalue().encode("utf-8-sig")
    gz_payload = gzip.compress(csv_payload, compresslevel=9, mtime=0)
    OUT_GZ.write_bytes(gz_payload)
    payload_sha = sha_bytes(csv_payload)
    compressed_sha = sha_bytes(gz_payload)

    audit_fields = [
        "security_id", "stock_code", "stock_name", "period_key", "period_type",
        "period_basis", "field_id", "action", "value_before", "value_after",
        "status_before", "status_after", "document_id_before", "document_id_after",
        "original_document_id", "source_page_after", "published_on_after",
        "version_used_after", "comparability_note_after", "reason",
    ]
    audit_buf = io.StringIO(newline="")
    aw = csv.DictWriter(audit_buf, fieldnames=audit_fields, lineterminator="\n")
    aw.writeheader()
    for a in audit:
        aw.writerow(a)
    audit_bytes = audit_buf.getvalue().encode("utf-8-sig")
    OUT_AUDIT.write_bytes(audit_bytes)

    # 核对 Q2 桥接中成本、净利润等辅助字段，且确认 OCF 0.01 元差异未被强行改写。
    bridge_checks = {
        "FIN.COST.Q2_DERIVED_CHECK": str(
            dec(patch["expected_q2_adjusted"]["FIN.COST.YTD"])
        ),
        "FIN.NP.Q2_DERIVED_CHECK": str(
            dec(patch["expected_q2_adjusted"]["FIN.NP.YTD"])
        ),
    }
    for field_id, ytd_field in (
        ("FIN.COST.Q2_DERIVED_CHECK", "FIN.COST.YTD"),
        ("FIN.NP.Q2_DERIVED_CHECK", "FIN.NP.YTD"),
    ):
        q1 = dec(get("20250331", "YTD_CUMULATIVE", ytd_field)["value_cny"])
        h1 = dec(get("20250630", "YTD_CUMULATIVE", ytd_field)["value_cny"])
        if h1 - q1 != dec(bridge_checks[field_id]):
            raise ValueError(f"auxiliary Q2 bridge check failed: {field_id}")

    s00_manifest = {
        "version": "S00_HANGCHA_RESTATED_COMPARATIVE_V10_20261031",
        "status": "CANDIDATE_PENDING_S02_SELF_CHECK_AND_EXTERNAL_REVIEW",
        "generated_at": NOW,
        "as_of": AS_OF,
        "security_id": SEC,
        "stock_code": CODE,
        "stock_name": NAME,
        "built_from": str(BASE.relative_to(ROOT)).replace("\\", "/"),
        "built_from_sha256": sha_file(BASE),
        "patch_spec": str(PATCH_PATH.relative_to(ROOT)).replace("\\", "/"),
        "patch_spec_sha256": sha_file(PATCH_PATH),
        "rows": len(rows),
        "csv_payload_bytes": len(csv_payload),
        "csv_payload_sha256": payload_sha,
        "gzip_bytes": len(gz_payload),
        "gzip_sha256": compressed_sha,
        "audit_path": str(OUT_AUDIT.relative_to(ROOT)).replace("\\", "/"),
        "audit_sha256": sha_file(OUT_AUDIT),
        "audit_rows": len(audit),
        "adoption_counts": dict(Counter(a["action"] for a in audit)),
        "source_documents": source_docs,
        "q2_bridge": q2_bridge,
        "auxiliary_q2_bridge_checks": bridge_checks,
        "rules_note": "指标公式与阈值沿用冻结 S01 v2；仅修正字段级追溯比较基数与 Q06 已采用标记。",
        "known_limits": [
            "2025-06-30 追溯调整后应收账款、存货、合同资产比较余额未取得；M10/M11/M12 不得据原始余额冒充同口径。",
            "2025Q2 OCF 桥接值与 2025 年报原始分季值相差 0.01 元；保留原值，不强行采用桥接尾数。",
            "本次只修复杭叉集团（603298），不扩大到其他公司。",
        ],
    }
    OUT_MANIFEST.write_text(json.dumps(s00_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # 为新输入建立独立规则输入指纹；冻结科学规则核心内容不变。
    rules = json.loads(BASE_RULES.read_text(encoding="utf-8"))
    company_sha = sha_file(COMPANY_MASTER)
    company_bytes = COMPANY_MASTER.stat().st_size
    manifest_sha = sha_file(OUT_MANIFEST)
    manifest_bytes = OUT_MANIFEST.stat().st_size
    rules["input_version"] = "S00_HANGCHA_RESTATED_COMPARATIVE_V10_20261031"
    rules["input_fingerprint"] = {
        "files": [
            {
                "path": str(OUT_GZ.relative_to(ROOT)).replace("\\", "/"),
                "sha256": compressed_sha,
                "bytes": len(gz_payload),
            },
            {
                "path": str(OUT_MANIFEST.relative_to(ROOT)).replace("\\", "/"),
                "sha256": manifest_sha,
                "bytes": manifest_bytes,
            },
            {
                "path": "data/company_master.csv",
                "sha256": company_sha,
                "bytes": company_bytes,
            },
        ],
        "note": (
            "S00 v10 定向版本：在 S00 v9 上只采用杭叉集团（603298）同一控制下企业合并的"
            "官方追溯比较基数；其余 1053 家及其他字段保持不变。科学规则核心与冻结 S01 v2 一致。"
        ),
    }
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    OUT_RULES.write_text(json.dumps(rules, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # 用新输入 + 新指纹 + 冻结 S01 规则运行全池 S02。
    cmd = [
        sys.executable, str(S02_SCRIPT),
        "--normalized", str(OUT_GZ),
        "--out-dir", str(S02_DIR),
        "--rules", str(OUT_RULES),
        "--normalized-sha256", payload_sha,
    ]
    completed = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
    (OUT_ROOT / "s02_stdout.log").write_text(completed.stdout, encoding="utf-8")
    (OUT_ROOT / "s02_stderr.log").write_text(completed.stderr, encoding="utf-8")
    if completed.returncode != 0:
        raise RuntimeError(
            f"S02 exited {completed.returncode}; inspect {OUT_ROOT / 's02_stderr.log'}\n"
            + completed.stdout[-6000:] + "\n" + completed.stderr[-6000:]
        )

    review_path = S02_DIR / "review.json"
    metrics_path = S02_DIR / "all_pool_metrics.csv"
    company_path = S02_DIR / "company_metric_summary.csv"
    if not review_path.is_file() or not metrics_path.is_file() or not company_path.is_file():
        raise FileNotFoundError("S02 output set incomplete")
    review = json.loads(review_path.read_text(encoding="utf-8"))
    if review.get("blocking_fail", 0) != 0:
        raise RuntimeError(f"S02 has blocking failures: {review.get('blocking_fail')}")

    hangcha_metrics = []
    with metrics_path.open(encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            if r["stock_code"] == CODE:
                hangcha_metrics.append(r)
    if len(hangcha_metrics) != 12:
        raise RuntimeError(f"Hangcha S02 metric count is not 12: {len(hangcha_metrics)}")
    with OUT_HANGCHA.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(hangcha_metrics[0].keys()), lineterminator="\n")
        w.writeheader()
        w.writerows(hangcha_metrics)

    expected = {k: dec(v) for k, v in patch["metrics_expected"].items()}
    tolerance = {
        "M01": Decimal("0.00000002"),
        "M02": Decimal("0.00000002"),
        "M03": Decimal("0.000002"),
        "M04": Decimal("0.000002"),
        "M05": Decimal("0.00000002"),
        "M06": Decimal("0.000002"),
        "M07": Decimal("0.00000002"),
        "M08": Decimal("0.00000002"),
        "M09": Decimal("0.02"),
    }
    by_metric = {r["metric_id"]: r for r in hangcha_metrics}
    checks = []
    for mid, target in expected.items():
        r = by_metric[mid]
        actual = dec(r["value"])
        no_q06 = "Q06" not in (r["quality_flags"] or "").split(";")
        status_ok = r["metric_status"] == "OK"
        value_ok = abs(actual - target) <= tolerance[mid]
        checks.append({
            "metric_id": mid,
            "expected_value": str(target),
            "actual_value": r["value"],
            "expected_status": "OK",
            "actual_status": r["metric_status"],
            "quality_flags": r["quality_flags"],
            "value_pass": value_ok,
            "status_pass": status_ok,
            "q06_absent": no_q06,
            "source_refs": r["source_refs"],
        })
        if not (value_ok and status_ok and no_q06):
            raise RuntimeError(f"Hangcha metric validation failed: {mid}: {checks[-1]}")

    # M10-M12 remain outside the clean comparable set because the 2025H1 restated
    # balance-sheet bases are unavailable. They must not become ordinary OK.
    balance_limits = {}
    for mid in ("M10", "M11", "M12"):
        r = by_metric[mid]
        balance_limits[mid] = {
            "status": r["metric_status"],
            "quality_flags": r["quality_flags"],
            "value": r["value"],
            "not_promoted_to_ok": r["metric_status"] != "OK",
        }
        if r["metric_status"] == "OK":
            raise RuntimeError(f"{mid} unexpectedly became OK without restated balance base")

    company_row = None
    with company_path.open(encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            if r["stock_code"] == CODE:
                company_row = r
                break
    if company_row is None:
        raise RuntimeError("Hangcha missing from company_metric_summary.csv")

    validation = {
        "status": "SELF_CHECK_PASS_CANDIDATE_PENDING_EXTERNAL_REVIEW",
        "generated_at": NOW,
        "security_id": SEC,
        "stock_code": CODE,
        "stock_name": NAME,
        "s00_manifest": str(OUT_MANIFEST.relative_to(ROOT)).replace("\\", "/"),
        "s00_gzip_sha256": compressed_sha,
        "s00_payload_sha256": payload_sha,
        "s00_audit_rows": len(audit),
        "s02_review_decision": review.get("decision"),
        "s02_checks": {
            "total": review.get("checks_total"),
            "pass": review.get("checks_pass"),
            "fail": review.get("checks_fail"),
            "warnings": review.get("checks_warn"),
            "blocking_fail": review.get("blocking_fail"),
        },
        "hangcha_company_summary": company_row,
        "metric_checks": checks,
        "balance_sheet_limits": balance_limits,
        "s01_implementation_revision": "R5_RESTATED_COMPARATIVE_ADOPTION_20261031",
        "scope": "only Hangcha 603298 changed; other company rows preserved",
        "next_step": "独立复核 S00 v10 采纳审计与 S02 输出；未外部复核前不更新 PROJECT_STATE 当前有效版本、不放行 S03。",
    }
    OUT_VALIDATION.write_text(json.dumps(validation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # 删除 S02 的临时解压缓存；其 SHA 已写入 calculation_manifest。
    cache = S02_DIR / ".input_cache"
    if cache.exists():
        shutil.rmtree(cache)

    print(json.dumps({
        "status": validation["status"],
        "s00_rows": len(rows),
        "s00_gzip_sha256": compressed_sha,
        "audit_rows": len(audit),
        "s02_review_decision": review.get("decision"),
        "s02_checks": validation["s02_checks"],
        "hangcha_company_summary": company_row,
        "metrics": [
            {k: r[k] for k in ("metric_id", "value", "metric_status", "quality_flags")}
            for r in hangcha_metrics
        ],
        "balance_sheet_limits": balance_limits,
        "output_root": str(OUT_ROOT.relative_to(ROOT)).replace("\\", "/"),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
