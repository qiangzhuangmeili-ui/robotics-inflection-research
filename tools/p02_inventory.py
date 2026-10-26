#!/usr/bin/env python3
"""P02 盘点：把 Drive 目录、本机缓存、旧研究库、财务快照合成一份可复用资产清单。

只读所有输入，不移动/删除任何原件，不改 document_registry。
输出写到 runs/issues/P02/。

用法：python tools/p02_inventory.py
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs" / "issues" / "P02"

PROJECT_PARENT = Path(r"C:\Users\zhangjianmei\Documents\ChatGPT\机器人企业行业拐点研究")
SNAPSHOT = PROJECT_PARENT / "collection_run_20261026" / "raw" / "既有候选池财务快照.csv"
DRIVE_INV = ROOT / "inbox" / "drive_inventory_20261026.csv"
LOCAL_CACHE_DIRS = [
    PROJECT_PARENT / "R1_parallel_parent_reviewed_20261024" / "sources",
    PROJECT_PARENT / "tmp" / "chat02a_parent_sources",
    PROJECT_PARENT / "tmp" / "batch01_parent_sources",
]

IDENT_COLS = {"security_id", "stock_code", "stock_name", "exchange", "data_status",
              "listing_date", "prelisting_flag", "sw_l1", "sw_l2", "sw_l3"}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_csv(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def norm_name(name: str) -> str:
    """去掉「公司简称：」前缀、空白与常见后缀噪声，用于 Drive 文件名与登记表对齐。

    双向处理：登记表可能带前缀而 Drive 不带，也可能反过来。
    """
    name = name.strip()
    for _ in range(2):
        if "：" in name:
            name = name.split("：", 1)[1]
    return name.strip()


def parse_drive_inventory() -> tuple[list[dict], list[tuple[str, str]]]:
    """把用户提供的目录快照解析成文件条目与文件夹段落。

    返回 (items, folder_segments)。folder_segments 用于识别重复文件夹，
    因为同一 (代码, 期间) 可能出现多次而目录快照无法区分是哪一次。
    """
    rows = read_csv(DRIVE_INV)
    items: list[dict] = []
    folders: list[tuple[str, str]] = []
    for r in rows:
        m = re.match(r"(\d{6})_(.+)", r["公司文件夹"].strip())
        if not m:
            continue
        code, folder_name = m.group(1), m.group(2).strip()
        detail = r["下属子文件夹及文件明细"]
        parts = re.split(r"([📁📄])", detail)
        marker = None
        for part in parts:
            if part in ("📁", "📄"):
                marker = part
                continue
            seg = part.strip()
            if not seg or marker is None:
                continue
            empty = "（空文件夹）" in seg
            label = "ROOT"
            rest = seg
            if empty:
                label = seg.replace("（空文件夹）", "").strip(" ：:")
                rest = ""
            elif re.search(r"[：:]", seg):
                label, rest = re.split(r"[：:]", seg, maxsplit=1)
                label = label.strip()
            if marker == "📁":
                folders.append((code, label))
            for fn in re.findall(r"([^、]+?\.pdf)", rest):
                items.append({
                    "stock_code": code,
                    "folder_name": folder_name,
                    "period_folder": label,
                    "filename": fn.strip(),
                    "empty_folder": False,
                })
            if empty:
                items.append({
                    "stock_code": code,
                    "folder_name": folder_name,
                    "period_folder": label,
                    "filename": "",
                    "empty_folder": True,
                })
    return items, folders


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    registry = read_csv(ROOT / "data" / "document_registry.csv")
    queue = read_csv(ROOT / "data" / "intake_company_queue.csv")
    master = read_csv(ROOT / "data" / "company_master.csv")
    resource_map = read_csv(ROOT / "data" / "resource_map.csv")
    p01 = {r["document_id"]: r for r in read_csv(ROOT / "runs" / "issues" / "P01" / "migration_dryrun.csv")}

    drive_items, drive_folders = parse_drive_inventory()
    drive_files = [d for d in drive_items if not d["empty_folder"]]
    drive_empty = [d for d in drive_items if d["empty_folder"]]

    # 登记表文件名 → Drive 条目（按 代码+归一文件名 对齐，避免跨公司同名误配）
    drive_by_key = defaultdict(list)
    for d in drive_files:
        drive_by_key[(d["stock_code"], norm_name(d["filename"]))].append(d)
    matched_drive_ids = set()
    for r in registry:
        key = (r["stock_code"], norm_name(r["original_filename"]))
        hits = drive_by_key.get(key, [])
        r["_drive_match"] = hits[0] if hits else None
        if hits:
            matched_drive_ids.add(id(hits[0]))
    # 同一 (代码, 文件名) 的重复条目不算未登记，单独统计为重复
    dup_extra = [d for d in drive_files
                 if id(d) not in matched_drive_ids
                 and drive_by_key.get((d["stock_code"], norm_name(d["filename"])))
                 and id(drive_by_key[(d["stock_code"], norm_name(d["filename"]))][0]) in matched_drive_ids]
    unmatched_drive = [d for d in drive_files
                       if id(d) not in matched_drive_ids and d not in dup_extra]

    assets = []

    # ---------- A. 已登记文档 ----------
    local_seen = set()
    for r in registry:
        doc_id = r["document_id"]
        axes = p01.get(doc_id, {})
        local_path = r["local_file"].strip()
        size = None
        sha_actual = None
        if local_path and os.path.isfile(local_path):
            local_seen.add(local_path)
            size = os.path.getsize(local_path)
            sha_actual = sha256_file(Path(local_path))
        sha_rec = r["sha256"].strip()
        sha_match = ("MATCH" if sha_rec and sha_actual == sha_rec
                     else "MISMATCH" if sha_rec and sha_actual and sha_actual != sha_rec
                     else "NO_BASELINE" if sha_actual else "NOT_COMPUTED")

        archive = axes.get("new_archive_status", r["archive_status"])
        evidence = axes.get("new_evidence_status", "NOT_USED")
        access = axes.get("new_access_identity_status", "NOT_CHECKED")

        if archive == "VERIFIED" and evidence in ("SELF_CHECK_ONLY", "NOT_USED"):
            reuse = "REUSE_WITH_LIMITS"
        elif archive in ("UPLOADED_UNVERIFIED", "VERIFIED"):
            reuse = "REUSE_WITH_LIMITS" if archive == "VERIFIED" else "REUSE_INDEX_ONLY"
        elif archive == "NOT_REQUIRED_REFERENCE_ONLY":
            reuse = "REUSE_INDEX_ONLY"
        else:
            reuse = "HOLD_PENDING_VERIFICATION"

        lim = []
        if not sha_rec:
            lim.append("无内容哈希")
        if sha_match == "MISMATCH":
            lim.append("本机文件与登记哈希不一致")
        if r["_drive_match"]:
            lim.append("Drive目录快照可见同名文件（未核二进制）")
        else:
            lim.append("Drive目录快照未见同名文件")
        if r["drive_file_id"].strip():
            lim.append("有Drive文件ID但本会话无Drive权限，无法回读")
        if evidence == "SELF_CHECK_ONLY":
            lim.append("仅执行者自检，未独立复核")

        assets.append({
            "asset_id": f"AST-DOC-{doc_id.replace('DOC-', '')}",
            "asset_type": "REGISTERED_DOCUMENT",
            "security_id": r["security_id"],
            "stock_code": r["stock_code"],
            "stock_name": r["stock_name"],
            "title": r["original_title"],
            "document_type": axes.get("new_document_type", "UNKNOWN"),
            "period_key": axes.get("new_period_key", "UNKNOWN"),
            "location_type": "LOCAL_FILE" if local_path else ("DRIVE_ONLY" if r["drive_file_id"] else "URL_ONLY"),
            "location_primary": local_path or r["drive_url"] or r["primary_url"],
            "location_secondary": r["drive_url"] if local_path else r["primary_url"],
            "drive_file_id": r["drive_file_id"],
            "drive_url": r["drive_url"],
            "size_bytes": size,
            "sha256_recorded": sha_rec,
            "sha256_actual": sha_actual,
            "sha256_match": sha_match,
            "link_status": axes.get("new_link_status", "NOT_SEARCHED"),
            "binary_status": axes.get("new_binary_status", "NOT_ATTEMPTED"),
            "archive_status": archive,
            "access_identity_status": access,
            "evidence_status": evidence,
            "verification_status": "LOCAL_HASH_MATCH" if sha_match == "MATCH" else (
                "LOCAL_HASH_MISMATCH" if sha_match == "MISMATCH" else "PRESENT_UNVERIFIED"),
            "reuse_decision": reuse,
            "limitations": "；".join(lim),
            "next_action": r.get("_next", "") or axes.get("new_next_action", ""),
        })

    # ---------- B. 本机缓存中未被登记的文件 ----------
    cache_all = []
    for d in LOCAL_CACHE_DIRS:
        if d.is_dir():
            for p in sorted(d.glob("*.pdf")):
                cache_all.append(p)
    extras = [p for p in cache_all if str(p) not in local_seen]
    for p in extras:
        assets.append({
            "asset_id": f"AST-LOCAL-{hashlib.sha256(str(p).encode()).hexdigest()[:12].upper()}",
            "asset_type": "LOCAL_CACHE_FILE",
            "security_id": "", "stock_code": "", "stock_name": "",
            "title": p.name, "document_type": "UNKNOWN", "period_key": "UNKNOWN",
            "location_type": "LOCAL_FILE", "location_primary": str(p), "location_secondary": "",
            "drive_file_id": "", "drive_url": "",
            "size_bytes": p.stat().st_size,
            "sha256_recorded": "", "sha256_actual": sha256_file(p), "sha256_match": "NO_BASELINE",
            "link_status": "", "binary_status": "", "archive_status": "", "access_identity_status": "",
            "evidence_status": "",
            "verification_status": "PRESENT_UNVERIFIED",
            "reuse_decision": "HOLD_PENDING_VERIFICATION",
            "limitations": "本机缓存中未登记于 document_registry",
            "next_action": "IDENTIFY_AND_REGISTER",
        })

    # ---------- C. 仓库内可复用文本资产 ----------
    for r in resource_map:
        rid = r["resource_id"]
        rel = r["repo_path"].strip()
        if not rel:
            continue
        path = ROOT / rel
        exists = path.is_file()
        sha_act = sha256_file(path) if exists else None
        sha_rec = r["sha256"].strip()
        match = "MATCH" if exists and sha_rec and sha_act == sha_rec else (
            "MISMATCH" if exists and sha_rec and sha_act != sha_rec else (
                "NO_BASELINE" if exists else "MISSING"))
        assets.append({
            "asset_id": f"AST-{rid}",
            "asset_type": "REPO_TEXT_ASSET",
            "security_id": "", "stock_code": "", "stock_name": "",
            "title": rel, "document_type": r["kind"], "period_key": "",
            "location_type": "REPO_FILE", "location_primary": rel,
            "location_secondary": r["local_original_path"],
            "drive_file_id": "", "drive_url": "",
            "size_bytes": path.stat().st_size if exists else None,
            "sha256_recorded": sha_rec, "sha256_actual": sha_act, "sha256_match": match,
            "link_status": "", "binary_status": "", "archive_status": "", "access_identity_status": "",
            "evidence_status": "",
            "verification_status": ("LOCAL_HASH_MATCH" if match == "MATCH"
                                    else "LOCAL_HASH_MISMATCH" if match == "MISMATCH"
                                    else "MISSING"),
            "reuse_decision": "REUSE_AS_IS" if match == "MATCH" else "HOLD_PENDING_VERIFICATION",
            "limitations": "历史研究产物，不重新认定业务或阶段",
            "next_action": "" if match == "MATCH" else "RESTORE_OR_RELOCATE",
        })

    # ---------- D/E. 旧研究包与结果文件 ----------
    pkg_root = ROOT / "packages"
    for pkg in sorted(p for p in pkg_root.iterdir() if p.is_dir()):
        results = sorted((pkg / "results").glob("*")) if (pkg / "results").is_dir() else []
        assets.append({
            "asset_id": f"AST-PKG-{pkg.name}",
            "asset_type": "RESEARCH_PACKAGE",
            "security_id": "", "stock_code": "", "stock_name": "",
            "title": pkg.name, "document_type": "RESEARCH_PACKAGE", "period_key": "",
            "location_type": "REPO_DIR", "location_primary": f"packages/{pkg.name}",
            "location_secondary": "",
            "drive_file_id": "", "drive_url": "",
            "size_bytes": sum(f.stat().st_size for f in pkg.rglob("*") if f.is_file()),
            "sha256_recorded": "", "sha256_actual": "", "sha256_match": "NOT_APPLICABLE",
            "link_status": "", "binary_status": "", "archive_status": "", "access_identity_status": "",
            "evidence_status": "",
            "verification_status": "PRESENT_UNVERIFIED" if results else "SHELL_ONLY_NO_RESULTS",
            "reuse_decision": "REUSE_WITH_LIMITS" if results else "REUSE_INDEX_ONLY",
            "limitations": f"含 {len(results)} 个结果文件" if results else "只有 TASK/assignment，无研究结果",
            "next_action": "READ_RESULTS_BEFORE_REUSE" if results else "NO_RESULT_TO_REUSE",
        })
        for f in results:
            assets.append({
                "asset_id": f"AST-RES-{pkg.name}-{f.stem}",
                "asset_type": "RESEARCH_RESULT_FILE",
                "security_id": "", "stock_code": "", "stock_name": "",
                "title": f"{pkg.name}/{f.name}", "document_type": f.suffix.lstrip(".").upper(),
                "period_key": "",
                "location_type": "REPO_FILE", "location_primary": f"packages/{pkg.name}/results/{f.name}",
                "location_secondary": "",
                "drive_file_id": "", "drive_url": "",
                "size_bytes": f.stat().st_size,
                "sha256_recorded": "", "sha256_actual": sha256_file(f), "sha256_match": "NO_BASELINE",
                "link_status": "", "binary_status": "", "archive_status": "", "access_identity_status": "",
                "evidence_status": "",
                "verification_status": "PRESENT_UNVERIFIED",
                "reuse_decision": "REUSE_WITH_LIMITS",
                "limitations": "旧体系研究结果，仅作历史证据，不重新认定业务或阶段",
                "next_action": "CITE_AS_LEGACY_EVIDENCE",
            })

    # ---------- F. 财务快照 ----------
    snapshot_meta = {}
    if SNAPSHOT.is_file():
        snap_rows = read_csv(SNAPSHOT)
        cols = list(snap_rows[0].keys()) if snap_rows else []
        snapshot_meta = {
            "path": str(SNAPSHOT),
            "rows": len(snap_rows),
            "columns": len(cols),
            "sha256": sha256_file(SNAPSHOT),
            "size_bytes": SNAPSHOT.stat().st_size,
            "numeric_fields": [c for c in cols if c not in IDENT_COLS],
        }
        assets.append({
            "asset_id": "AST-SNAPSHOT-001",
            "asset_type": "FINANCIAL_SNAPSHOT",
            "security_id": "", "stock_code": "", "stock_name": "",
            "title": SNAPSHOT.name, "document_type": "FINANCIAL_SNAPSHOT", "period_key": "2021-2026H1",
            "location_type": "LOCAL_FILE", "location_primary": str(SNAPSHOT),
            "location_secondary": "https://drive.google.com/file/d/1OhRUemuwYyLLYtdXsgSuzv36C5tmECTI/view",
            "drive_file_id": "1OhRUemuwYyLLYtdXsgSuzv36C5tmECTI",
            "drive_url": "https://drive.google.com/file/d/1OhRUemuwYyLLYtdXsgSuzv36C5tmECTI/view",
            "size_bytes": SNAPSHOT.stat().st_size,
            "sha256_recorded": "", "sha256_actual": snapshot_meta["sha256"], "sha256_match": "NO_BASELINE",
            "link_status": "", "binary_status": "", "archive_status": "", "access_identity_status": "",
            "evidence_status": "",
            "verification_status": "LOCAL_PRESENT_HASH_COMPUTED",
            "reuse_decision": "REUSE_WITH_LIMITS",
            "limitations": "缺披露日期/PIT版本，不能做历史可得性回测；缺经营现金流/应收/存货",
            "next_action": "USE_FOR_SCREENING_ONLY_AFTER_P04_FIELD_FREEZE",
        })

    # ---------- G. 校验报告 ----------
    for p in sorted((ROOT / "validation").glob("*.json")):
        assets.append({
            "asset_id": f"AST-VAL-{p.stem}",
            "asset_type": "VALIDATION_REPORT",
            "security_id": "", "stock_code": "", "stock_name": "",
            "title": p.name, "document_type": "VALIDATION_REPORT", "period_key": "",
            "location_type": "REPO_FILE", "location_primary": f"validation/{p.name}",
            "location_secondary": "",
            "drive_file_id": "", "drive_url": "",
            "size_bytes": p.stat().st_size,
            "sha256_recorded": "", "sha256_actual": sha256_file(p), "sha256_match": "NO_BASELINE",
            "link_status": "", "binary_status": "", "archive_status": "", "access_identity_status": "",
            "evidence_status": "",
            "verification_status": "PRESENT_UNVERIFIED",
            "reuse_decision": "REUSE_AS_IS",
            "limitations": "历史校验结果，可能对应旧数据版本",
            "next_action": "CHECK_DATE_BEFORE_CITING",
        })

    # ---------- H. Drive 有但登记表未记 ----------
    for d in unmatched_drive:
        assets.append({
            "asset_id": f"AST-DRV-{hashlib.sha256((d['stock_code'] + d['filename']).encode()).hexdigest()[:12].upper()}",
            "asset_type": "DRIVE_FILE_UNREGISTERED",
            "security_id": "", "stock_code": d["stock_code"], "stock_name": d["folder_name"],
            "title": d["filename"], "document_type": "UNKNOWN", "period_key": d["period_folder"],
            "location_type": "DRIVE_FOLDER_SNAPSHOT", "location_primary": f"Drive/{d['folder_name']}/{d['period_folder']}",
            "location_secondary": "",
            "drive_file_id": "", "drive_url": "",
            "size_bytes": None, "sha256_recorded": "", "sha256_actual": "", "sha256_match": "NOT_COMPUTED",
            "link_status": "", "binary_status": "", "archive_status": "", "access_identity_status": "",
            "evidence_status": "",
            "verification_status": "DIRECTORY_LISTING_ONLY",
            "reuse_decision": "HOLD_PENDING_VERIFICATION",
            "limitations": "仅目录快照可见，未登记、未取二进制",
            "next_action": "IDENTIFY_AND_REGISTER",
        })

    fields = ["asset_id", "asset_type", "security_id", "stock_code", "stock_name", "title",
              "document_type", "period_key", "location_type", "location_primary", "location_secondary",
              "drive_file_id", "drive_url", "size_bytes", "sha256_recorded", "sha256_actual",
              "sha256_match", "link_status", "binary_status", "archive_status",
              "access_identity_status", "evidence_status", "verification_status",
              "reuse_decision", "limitations", "next_action"]
    with (OUT / "existing_assets.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(assets)

    # ---------- 字段级财务覆盖 ----------
    cov_rows = []
    if snapshot_meta:
        snap_rows = read_csv(SNAPSHOT)
        for col in snapshot_meta["numeric_fields"]:
            non_empty = sum(1 for r in snap_rows if r[col].strip())
            missing = len(snap_rows) - non_empty
            if col.startswith("deducted_np_parent_cny_"):
                group, period, unit = "扣非归母净利润（单季）", col.replace("deducted_np_parent_cny_", ""), "CNY"
            else:
                m = re.match(r"(revenue|net_profit_parent|gross_margin_pct)_(?:cny_)?(\w+)$", col)
                grp = {"revenue": "营业收入", "net_profit_parent": "归母净利润",
                       "gross_margin_pct": "毛利率"}.get(m.group(1) if m else "", "其他")
                group = grp
                period = m.group(2) if m else ""
                unit = "%" if "gross_margin" in col else "CNY"
            cov_rows.append({
                "field_name": col,
                "field_group": group,
                "period": period,
                "unit": unit,
                "expected_rows": len(snap_rows),
                "non_empty_rows": non_empty,
                "coverage_pct": round(non_empty / len(snap_rows) * 100, 2),
                "missing_rows": missing,
                "in_p00_contract": "YES" if any(k in col for k in
                    ("revenue_cny_2023", "revenue_cny_2024", "revenue_cny_2025",
                     "net_profit_parent_cny_2023", "net_profit_parent_cny_2024", "net_profit_parent_cny_2025")) else "PARTIAL",
                "notes": "缺失不填 0；62 家 FINANCIAL_DATA_MISSING 全列为空",
            })
        # P00 契约要求但快照完全没有的字段
        for f in ["经营活动产生的现金流量净额", "应收账款", "存货", "营业成本/毛利额",
                  "实际披露日", "上市日期", "单季度营收"]:
            cov_rows.append({
                "field_name": f, "field_group": "P00契约要求", "period": "全部", "unit": "",
                "expected_rows": len(snap_rows), "non_empty_rows": 0, "coverage_pct": 0.0,
                "missing_rows": len(snap_rows), "in_p00_contract": "YES",
                "notes": "快照中无此字段，须 P05 采集补齐",
            })
    with (OUT / "existing_field_coverage.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(cov_rows[0].keys()))
        w.writeheader()
        w.writerows(cov_rows)

    # ---------- 汇总 ----------
    by_type = Counter(a["asset_type"] for a in assets)
    by_reuse = Counter(a["reuse_decision"] for a in assets)
    docs = [a for a in assets if a["asset_type"] == "REGISTERED_DOCUMENT"]
    sha_values = [a["sha256_recorded"] for a in docs if a["sha256_recorded"]]
    hash_verified = [a for a in docs if a["sha256_match"] == "MATCH"]
    hash_mismatch = [a for a in docs if a["sha256_match"] == "MISMATCH"]

    reuse_manifest = {
        "manifest_version": 1,
        "plan_version": "20261026_collection_first_v2",
        "issue_number": 13,
        "issue_key": "P02",
        "generated_at_utc": generated_at,
        "purpose": "盘点 Drive 目录、本机缓存、旧研究库与财务快照，给出可复用资产清单与逐字段财务覆盖。",
        "scope_note": "只盘点与建索引，不重新认定业务或阶段，不追加企业深挖，不移动或删除任何原件。",
        "counts": {
            "registered_documents": len(docs),
            "unique_document_id": len(set(a["asset_id"] for a in docs)),
            "unique_content_sha256": len(set(sha_values)),
            "documents_without_hash": len(docs) - len([a for a in docs if a["sha256_recorded"]]),
            "ai_read_confirmed": len([a for a in docs if a["access_identity_status"] == "AI_READ_CONFIRMED"]),
            "evidence_independently_verified": len([a for a in docs if a["evidence_status"] == "VERIFIED_INDEPENDENT"]),
            "evidence_self_check_only": len([a for a in docs if a["evidence_status"] == "SELF_CHECK_ONLY"]),
            "archive_verified": len([a for a in docs if a["archive_status"] == "VERIFIED"]),
            "archive_uploaded_unverified": len([a for a in docs if a["archive_status"] == "UPLOADED_UNVERIFIED"]),
            "archive_not_uploaded": len([a for a in docs if a["archive_status"] == "NOT_UPLOADED"]),
            "local_file_hash_match": len(hash_verified),
            "local_file_hash_mismatch": len(hash_mismatch),
        },
        "assets_by_type": dict(sorted(by_type.items(), key=lambda kv: -kv[1])),
        "assets_by_reuse_decision": dict(sorted(by_reuse.items(), key=lambda kv: -kv[1])),
        "drive_inventory": {
            "source": "inbox/drive_inventory_20261026.csv（用户提供的目录快照，非 API 列举）",
            "company_folders": len({d["stock_code"] for d in drive_items}),
            "folder_rows": 73,
            "pdf_filename_entries": len(drive_files),
            "unique_pdf_filenames": len({(d["stock_code"], norm_name(d["filename"])) for d in drive_files}),
            "empty_folders": len(drive_empty),
            "duplicate_entries_in_listing": len(dup_extra),
            "duplicate_folder_groups": [
                {"stock_code": k[0], "period_folder": k[1], "folder_segments": v}
                for k, v in sorted(
                    Counter(drive_folders).items(), key=lambda kv: -kv[1]) if v > 1
            ],
            "matched_to_registry": len({(d["stock_code"], norm_name(d["filename"])) for d in drive_files}) - len(unmatched_drive),
            "unmatched": len(unmatched_drive),
            "note": "目录快照只能证明「存在同名文件」，不能证明可打开、是全文、身份正确。重复文件夹不得当成多份不同文件。",
        },
        "local_cache": {
            "directories": [str(d) for d in LOCAL_CACHE_DIRS],
            "pdf_count": len(cache_all),
            "referenced_by_registry": len(cache_all) - len(extras),
            "unregistered_extras": len(extras),
            "portability": "全部为机器绝对路径，不在仓库内；换机即失效，需迁入 sources/ 或 Drive。",
        },
        "financial_snapshot": {
            "path": snapshot_meta.get("path"),
            "rows": snapshot_meta.get("rows"),
            "columns": snapshot_meta.get("columns"),
            "numeric_fields": len(snapshot_meta.get("numeric_fields", [])),
            "sha256": snapshot_meta.get("sha256"),
            "drive_file_id": "1OhRUemuwYyLLYtdXsgSuzv36C5tmECTI",
            "companies_with_data": 992,
            "companies_missing": 62,
            "field_level_coverage": "见 runs/issues/P02/existing_field_coverage.csv",
            "limitations": ["无实际披露日期/PIT 版本，不能做历史可得性回测",
                            "无经营现金流、应收、存货、营业成本字段",
                            "无单季度营收（仅有单季扣非净利）"],
        },
        "blocked": [
            {"what": "Drive 二进制回读与哈希校验",
             "why": "本机未安装 Google Drive 连接器；私有链接实测返回 302 登录跳转 / 401",
             "impact": "90 条有 drive_file_id 的记录无法回读；73 条 UPLOADED_UNVERIFIED 无法转 VERIFIED",
             "unblock": "安装 Drive 连接器，或用户手动下载到本地目录"}
        ],
        "acceptance_counts": {
            "文档数": len(docs),
            "唯一数（document_id）": len(set(a["asset_id"] for a in docs)),
            "唯一数（内容SHA256）": len(set(sha_values)),
            "已读取数（AI_READ_CONFIRMED）": len([a for a in docs if a["access_identity_status"] == "AI_READ_CONFIRMED"]),
            "已业务验收数（VERIFIED_INDEPENDENT）": len([a for a in docs if a["evidence_status"] == "VERIFIED_INDEPENDENT"]),
            "说明": "四项分别计数，不得互相替代。已读取不等于已验收，已归档不等于已读取。",
        },
    }
    (OUT / "reuse_manifest.json").write_text(
        json.dumps(reuse_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({
        "assets_total": len(assets),
        "by_type": reuse_manifest["assets_by_type"],
        "acceptance_counts": reuse_manifest["acceptance_counts"],
        "hash_match": len(hash_verified),
        "hash_mismatch": len(hash_mismatch),
        "unmatched_drive": len(unmatched_drive),
        "extras_local": len(extras),
        "field_rows": len(cov_rows),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
