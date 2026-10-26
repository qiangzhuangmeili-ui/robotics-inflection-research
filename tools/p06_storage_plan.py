#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
P06 生成器：容量估算 / 归档路由 / 传输回执 schema + 可复算自检。

只读输入，只写 runs/issues/P06/ 下的交付。
不下载、不上传、不改 data/document_registry.csv、不改任何原始输入。

用法：
    python tools/p06_storage_plan.py            # 生成三份交付 + self_check.json
    python tools/p06_storage_plan.py --check    # 只跑自检（交付须已存在）
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "runs" / "issues" / "P06"
TZ_CN = timezone(timedelta(hours=8))

PLAN_VERSION = "20261026_collection_first_v2"
ISSUE_NUMBER = 17
ISSUE_KEY = "P06"
SCHEMA_VERSION = "STORAGE_PLAN_V1"
RECEIPT_SCHEMA_VERSION = "TRANSFER_RECEIPT_V1"

GIB = 1024 ** 3
MIB = 1024 ** 2

# ---------------------------------------------------------------- 基础工具


def now_cn() -> str:
    return datetime.now(TZ_CN).isoformat(timespec="seconds")


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_csv(path: Path) -> list[dict]:
    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def read_json(path: Path):
    with open(path, "r", encoding="utf-8-sig") as fh:
        return json.load(fh)


def rel(path: Path) -> str:
    return path.relative_to(REPO).as_posix()


def input_fingerprint(paths: list[Path]) -> list[dict]:
    out = []
    for p in paths:
        if not p.exists():
            out.append({"path": rel(p), "exists": False, "sha256": None, "bytes": None})
            continue
        out.append({
            "path": rel(p),
            "exists": True,
            "bytes": p.stat().st_size,
            "sha256": sha256_file(p),
        })
    return out


def pct(values: list[int], q: float) -> int:
    """线性插值分位数，n=1 时返回该值。"""
    if not values:
        raise ValueError("empty sample")
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    pos = (len(s) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(s) - 1)
    frac = pos - lo
    return int(round(s[lo] + (s[hi] - s[lo]) * frac))


# ---------------------------------------------------------------- 输入装载


def load_inputs() -> dict:
    scope = read_json(REPO / "runs/issues/P00/collection_scope.json")
    collector = read_json(REPO / "runs/issues/P05/collector_config.json")
    company_master = read_csv(REPO / "data/company_master.csv")
    registry = read_csv(REPO / "data/document_registry.csv")
    drive_folders = read_csv(REPO / "data/drive_folders.csv")
    transfer_plan = read_csv(REPO / "data/pdf_transfer_plan.csv")
    batch_index = read_csv(REPO / "data/intake_batch_index.csv")
    queue = read_csv(REPO / "data/intake_company_queue.csv")
    assets = read_csv(REPO / "runs/issues/P02/existing_assets.csv")
    p05_index = read_csv(REPO / "runs/issues/P05/collection_index.csv")
    return {
        "scope": scope,
        "collector": collector,
        "company_master": company_master,
        "registry": registry,
        "drive_folders": drive_folders,
        "transfer_plan": transfer_plan,
        "batch_index": batch_index,
        "queue": queue,
        "assets": assets,
        "p05_index": p05_index,
    }


# ---------------------------------------------------------------- 容量测算


def build_samples(inp: dict) -> dict:
    """按内容哈希去重的实测字节样本，区分年报/半年报/摘要/招股书。"""
    classes = {
        "ANNUAL_REPORT": [],
        "ANNUAL_REPORT_SUMMARY": [],
        "SEMI_ANNUAL_REPORT": [],
        "PROSPECTUS": [],
        "QUARTERLY_REPORT": [],
    }
    seen: dict[str, str] = {}

    def add(cls: str, size: int, sha: str, origin: str):
        if cls not in classes:
            return
        key = sha or f"{origin}:{size}"
        if key in seen:
            return
        seen[key] = cls
        classes[cls].append(size)

    for row in inp["assets"]:
        cls = (row.get("document_type") or "").strip()
        raw = (row.get("size_bytes") or "").strip()
        if not raw.isdigit() or cls not in classes:
            continue
        add(cls, int(raw), (row.get("sha256_actual") or "").strip(), row.get("asset_id", ""))

    for row in inp["p05_index"]:
        raw = (row.get("bytes") or "").strip()
        if not raw.isdigit():
            continue
        rt = (row.get("report_type") or "").strip()
        cls = {
            "ANNUAL_REPORT": "ANNUAL_REPORT",
            "SEMI_ANNUAL_REPORT": "SEMI_ANNUAL_REPORT",
            "QUARTERLY_REPORT": "QUARTERLY_REPORT",
        }.get(rt)
        if cls:
            add(cls, int(raw), (row.get("sha256") or "").strip(), row.get("document_id", ""))

    stats = {}
    for cls, vals in classes.items():
        if not vals:
            stats[cls] = {"n": 0, "status": "UNMEASURED"}
            continue
        stats[cls] = {
            "n": len(vals),
            "status": "MEASURED",
            "min_bytes": min(vals),
            "p25_bytes": pct(vals, 0.25),
            "median_bytes": int(statistics.median(vals)),
            "mean_bytes": int(round(statistics.fmean(vals))),
            "p75_bytes": pct(vals, 0.75),
            "max_bytes": max(vals),
            "sum_bytes": sum(vals),
            "sources": "P02 existing_assets(size_bytes) + P05 collection_index(bytes)，按内容哈希去重",
        }
    return stats


def build_planned_slots(inp: dict) -> tuple[list[dict], dict]:
    scope = inp["scope"]
    companies = len(inp["company_master"])
    core = [s for s in scope["report_slots"] if s.get("core_slot")]
    quarterly = scope["quarterly_slots"]
    q_applicable = [s for s in quarterly if s.get("as_of_cutoff_status") == "APPLICABLE"]
    q_not_yet = [s for s in quarterly if s.get("as_of_cutoff_status") != "APPLICABLE"]

    rows = []
    for s in core + quarterly:
        applicable = s.get("core_slot") or s.get("as_of_cutoff_status") == "APPLICABLE"
        rows.append({
            "slot_id": s["slot_id"],
            "report_type": s["report_type"],
            "period_label": s["period_label"],
            "core_slot": bool(s.get("core_slot")),
            "required_form": s.get("required_form", "FULL_PDF"),
            "statutory_deadline": s.get("statutory_deadline"),
            "counted_in_capacity": bool(applicable),
            "not_counted_reason": None if applicable else "NOT_YET_DISCLOSED_AT_CUTOFF",
            "companies": companies,
            "attempt_upper_bound": companies if applicable else 0,
        })

    summary = {
        "companies": companies,
        "core_slots": len(core),
        "quarterly_slots_applicable": len(q_applicable),
        "quarterly_slots_not_yet_disclosed": len(q_not_yet),
        "core_attempt_upper_bound": companies * len(core),
        "quarterly_attempt_upper_bound": companies * len(q_applicable),
        "total_attempt_upper_bound": companies * (len(core) + len(q_applicable)),
        "upper_bound_meaning": "数学上界，不是应有文件数；listing_date 1054/1054 UNKNOWN，无法扣除上市前不适用、未披露与修订合并，实际数必低于此值且当前不可知。",
        "p00_cross_check": {
            "p00_core_slot_upper_bound": scope["capacity_rule"]["core_slot_upper_bound"],
            "recomputed": companies * len(core),
            "match": scope["capacity_rule"]["core_slot_upper_bound"] == companies * len(core),
        },
    }
    return rows, summary


def build_envelope(inp: dict, planned_rows: list[dict], samples: dict) -> dict:
    per_slot = []
    totals = {"low_bytes": 0, "mid_bytes": 0, "high_bytes": 0}
    unmeasured = []
    for row in planned_rows:
        slot = row["slot_id"]
        if not row["counted_in_capacity"]:
            per_slot.append({**row, "unit_bytes_median": None, "envelope_status": "NOT_COUNTED_NOT_YET_DISCLOSED"})
            continue
        cls = "ANNUAL_REPORT" if slot.startswith("annual") else (
            "SEMI_ANNUAL_REPORT" if slot.startswith("h1") else "QUARTERLY_REPORT")
        st = samples[cls]
        if st["status"] != "MEASURED":
            unmeasured.append(slot)
            per_slot.append({
                **row,
                "unit_bytes_median": None,
                "envelope_status": "UNMEASURED_UNIT_BYTES",
                "reason": "该类报告无实测字节样本；按 P00 capacity_rule 不得用经验带宽替代，故容量留空。",
            })
            continue
        low = row["attempt_upper_bound"] * st["p25_bytes"]
        mid = row["attempt_upper_bound"] * st["median_bytes"]
        high = row["attempt_upper_bound"] * st["p75_bytes"]
        totals["low_bytes"] += low
        totals["mid_bytes"] += mid
        totals["high_bytes"] += high
        per_slot.append({
            **row,
            "unit_bytes_median": st["median_bytes"],
            "unit_bytes_p25": st["p25_bytes"],
            "unit_bytes_p75": st["p75_bytes"],
            "unit_sample_n": st["n"],
            "envelope_low_bytes": low,
            "envelope_mid_bytes": mid,
            "envelope_high_bytes": high,
            "envelope_status": "ESTIMATE_NOT_FACT",
        })

    return {
        "per_slot": per_slot,
        "totals": {
            "low_bytes": totals["low_bytes"],
            "mid_bytes": totals["mid_bytes"],
            "high_bytes": totals["high_bytes"],
            "low_gib": round(totals["low_bytes"] / GIB, 2),
            "mid_gib": round(totals["mid_bytes"] / GIB, 2),
            "high_gib": round(totals["high_bytes"] / GIB, 2),
            "excluded_slots": unmeasured,
            "excluded_note": "季度 PDF 无实测样本，未计入合计；其字节数保持 UNMEASURED，不得填估计值。",
        },
    }


def build_actual_bytes(inp: dict) -> dict:
    sizes = [int(r["size_bytes"]) for r in inp["assets"] if (r.get("size_bytes") or "").strip().isdigit()]
    pdf_classes = {"ANNUAL_REPORT", "ANNUAL_REPORT_SUMMARY", "SEMI_ANNUAL_REPORT", "PROSPECTUS",
                   "SUSTAINABILITY_REPORT", "LISTING_DISCLOSURE", "CONTRACT_ANNOUNCEMENT", "TENDER_NOTICE"}
    pdf_sizes = [int(r["size_bytes"]) for r in inp["assets"]
                 if (r.get("size_bytes") or "").strip().isdigit() and (r.get("document_type") or "") in pdf_classes]
    p05_sizes = [int(r["bytes"]) for r in inp["p05_index"] if (r.get("bytes") or "").strip().isdigit()]
    return {
        "measured_asset_rows": len(sizes),
        "measured_asset_bytes": sum(sizes),
        "measured_asset_mib": round(sum(sizes) / MIB, 2),
        "pdf_asset_rows": len(pdf_sizes),
        "pdf_asset_bytes": sum(pdf_sizes),
        "pdf_asset_mib": round(sum(pdf_sizes) / MIB, 2),
        "pdf_class_scope": sorted(pdf_classes),
        "p05_live_files": len(p05_sizes),
        "p05_live_bytes": sum(p05_sizes),
        "p05_live_mib": round(sum(p05_sizes) / MIB, 2),
        "note": "实际字节只统计已取得二进制的文件；未取得二进制的登记行不计入，也不按文件名推测大小。measured_asset_* 含文本快照/研究包等非 PDF 资产，pdf_asset_* 才是原件口径。",
    }


# ---------------------------------------------------------------- Drive 目录核实


DRIVE_ROOT_ID = "1v8RYlfohKcrGrulwCFq3fZSnGdjFxUYQ"


def probe_drive() -> dict:
    """无凭据探测，只记录真实结果，不做任何上传/读取尝试。"""
    targets = [
        ("root_folder", f"https://drive.google.com/drive/folders/{DRIVE_ROOT_ID}"),
        ("file_view", "https://drive.google.com/file/d/1oREDQ9KYl3FKaOOW5As-XhpFy-DBefL1/view"),
        ("api_v3_files_get", f"https://www.googleapis.com/drive/v3/files/{DRIVE_ROOT_ID}?fields=id,name"),
    ]
    results = []
    for name, url in targets:
        rec = {"probe": name, "url": url, "at_utc": now_utc()}
        req = urllib.request.Request(url, method="GET", headers={"User-Agent": "Mozilla/5.0 (P06 storage plan probe)"})
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                rec.update({"http_status": resp.status, "final_url": resp.geturl(), "reachable": True})
        except urllib.error.HTTPError as exc:
            rec.update({"http_status": exc.code, "final_url": exc.headers.get("Location"), "reachable": False})
        except Exception as exc:  # noqa: BLE001
            rec.update({"http_status": None, "error": f"{type(exc).__name__}: {exc}", "reachable": False})
        results.append(rec)

    codes = {r["probe"]: r["http_status"] for r in results}
    blocked = codes.get("api_v3_files_get") in (401, 403) or codes.get("root_folder") in (302, 401, 403)
    return {
        "probed_at_utc": now_utc(),
        "probes": results,
        "verdict": "DRIVE_API_NOT_CONNECTED" if blocked else "DRIVE_REACHABLE_UNVERIFIED",
        "capability": {
            "list_folder": False,
            "read_metadata": False,
            "upload": False,
            "download_binary": False,
            "quota_read": False,
        } if blocked else {
            "list_folder": True,
            "read_metadata": True,
            "upload": None,
            "download_binary": None,
            "quota_read": None,
        },
        "impact": "本会话无法列举/读取/上传 Drive：五个分类目录只能按用户快照与 PROJECT_STATE 记为 RECORDED_NOT_REVERIFIED；Drive 配额 UNKNOWN；新文件 archive_status 最高只能到 UPLOADED_UNVERIFIED（需真实上传回读才可 VERIFIED）。",
        "not_done": "未尝试登录、未要求公开分享、未扩大任何权限。",
    }


def build_drive_layout(inp: dict, probe: dict) -> dict:
    rows = inp["drive_folders"]
    wanted = {
        "PROJECT_ROOT": "根目录",
        "01_原始资料": "01_原始资料",
        "02_批次交接": "02_批次交接",
        "03_历史版本": "03_历史版本",
        "04_财务与数据导出": "04_财务与数据导出",
        "05_行业资料": "05_行业资料",
    }
    folders = []
    for row in rows:
        name = (row.get("folder_name") or "").strip()
        ftype = (row.get("folder_type") or "").strip()
        role = "PROJECT_ROOT" if ftype == "PROJECT_ROOT" else name
        if role not in wanted:
            continue
        fid = (row.get("folder_id") or "").strip()
        furl = (row.get("folder_url") or "").strip()
        folders.append({
            "role": role,
            "folder_name": name,
            "folder_id": fid,
            "folder_url": furl,
            "parent_id": (row.get("parent_id") or "").strip(),
            "contents": (row.get("contents") or "").strip(),
            "snapshot_status": (row.get("status") or "").strip(),
            "reverify_status": "RECORDED_NOT_REVERIFIED",
            "reverify_blocker": probe["verdict"],
            "id_is_not_url": bool(fid) and not fid.startswith("http") and "/folders/" not in fid,
            "url_contains_id": bool(fid) and fid in furl,
        })
    found_roles = {f["role"] for f in folders}
    return {
        "root_folder_id": DRIVE_ROOT_ID,
        "root_folder_url": f"https://drive.google.com/drive/folders/{DRIVE_ROOT_ID}",
        "folders": folders,
        "missing_roles": [k for k in wanted if k not in found_roles],
        "verification": probe,
        "id_rule": "folder_id 只放 33 位左右的不透明 ID（^[A-Za-z0-9_-]{20,}$）；folder_url 只放 https://drive.google.com/drive/folders/<id>。两者不得互换，更不得把目录 URL 写进 drive_file_id。",
        "file_id_rule": "文件回执里 drive.file_id 必须是上传回读返回的文件 ID，file_url 必须是 https://drive.google.com/file/d/<file_id>；从目录页复制的链接一律视为未验证。",
    }


# ---------------------------------------------------------------- 容量守卫


def build_capacity_guard(envelope: dict, actual: dict) -> dict:
    repo_drive = Path(os.path.abspath(REPO)).anchor or "C:\\"
    usage = shutil.disk_usage(repo_drive)
    alt_usage = shutil.disk_usage("D:\\")
    reserve = 6 * GIB
    soft = 10 * GIB
    rolling_max = 8 * GIB
    usable = min(rolling_max, max(0, usage.free - reserve))
    mid = envelope["totals"]["mid_bytes"]
    return {
        "measured_at": now_cn(),
        "cache_drive": repo_drive,
        "cache_drive_total_bytes": usage.total,
        "cache_drive_free_bytes": usage.free,
        "cache_drive_free_gib": round(usage.free / GIB, 2),
        "cache_drive_used_pct": round(100 * usage.used / usage.total, 1),
        "alternate_drive": "D:\\",
        "alternate_free_gib": round(alt_usage.free / GIB, 2),
        "reserve_bytes": reserve,
        "soft_watermark_free_bytes": soft,
        "hard_stop_free_bytes": reserve,
        "rolling_cache_max_bytes": rolling_max,
        "usable_cache_bytes_now": usable,
        "usable_cache_gib_now": round(usable / GIB, 2),
        "core_envelope_mid_bytes": mid,
        "core_envelope_mid_gib": round(mid / GIB, 2),
        "envelope_exceeds_rolling_cache": mid > usable,
        "conclusion": (
            "核心槽估算中位 {} GiB 已超过本机允许的单轮缓存上限 {} GiB，"
            "因此禁止“全池一次性下载完再归档”：必须按批（M00_xx）滚动缓存、批内归档回读后再清理。"
        ).format(round(mid / GIB, 2), round(usable / GIB, 2)),
        "breach_actions": [
            "free_bytes < hard_stop_free_bytes → 立即停止新下载（不停止已完成文件的归档回读）",
            "写 checkpoint：已下载未归档清单、下一家/下一槽游标、已占用字节",
            "按 priority_order 记录“哪些低优先级槽被推迟”，不得静默截断",
            "保留本地原件，不因空间不足删除唯一副本",
            "切换 cache_root 到 alternate_drive 需显式配置并留痕，不自动改路径",
        ],
        "watermark_basis": "reserve 6 GiB 为系统与其他工作预留；soft 10 GiB 触发提前归档；rolling 8 GiB 为单轮缓存硬上限。",
    }


# ---------------------------------------------------------------- 规则块


def build_registration_order() -> dict:
    return {
        "principle": "先查重 → 再取件 → 再归档回读 → 最后登记；登记永远写在事实之后，不写预测。",
        "steps": [
            {"step": 1, "action": "查台账与登记表", "detail": "按 (security_id, slot_id) 查 runs/issues/P05 台账与 data/document_registry.csv；命中同 sha256 且本地文件存在 → SKIPPED_ALREADY_HAVE，不发 HTTP。", "writes": []},
            {"step": 2, "action": "查 Drive", "detail": "有 Drive 权限时按文件名+父目录列目录比对；本会话无权限 → 记 RECORDED_NOT_REVERIFIED，不得声称“Drive 里没有”。", "writes": []},
            {"step": 3, "action": "分配 document_id", "detail": "IDENTITY_V1：DOC- + sha256(security_id|issuer_scope|document_type|period_key|revision_no)[:16].upper()，下载前分配，修订版换 revision_no。", "writes": []},
            {"step": 4, "action": "取件到本地缓存", "detail": "写 .part → 校验 Content-Length/魔数/可开 → 改名；失败保留 .part 供续传。", "writes": ["local_cache"]},
            {"step": 5, "action": "算哈希与页数", "detail": "对本地二进制算 SHA-256、页数、首屏身份要素；哈希只能来自实际文件。", "writes": ["receipt.download"]},
            {"step": 6, "action": "上传 Drive 目标目录", "detail": "按 archive_routing.csv 路由到 01—05 目录下的公司/报告期子目录；文件名保留原名。", "writes": ["receipt.drive.file_id"]},
            {"step": 7, "action": "回读确认", "detail": "重新列目录/取元数据：name、size、mimeType、parents 含目标目录 ID；缺任一项 archive_status 只能 UPLOADED_UNVERIFIED。", "writes": ["receipt.drive.readback", "archive_status"]},
            {"step": 8, "action": "写回执", "detail": "按 transfer_receipt_schema.json 落一条回执；schema 校验不通过视为未完成。", "writes": ["receipt"]},
            {"step": 9, "action": "更新登记表", "detail": "只回填实际取得的 drive_file_id/drive_url/sha256/page_count/archive_status/access_check_status；不确定留 UNKNOWN。", "writes": ["data/document_registry.csv"]},
            {"step": 10, "action": "最后清理缓存", "detail": "满足 cleanup_rules 全部条件才删本地副本；任一不满足则保留。", "writes": []},
        ],
        "ordering_rule": "第 9 步（登记）必须晚于第 7 步（回读）；先写 ID 后上传属于禁止行为。",
    }


def build_dedupe_rules() -> dict:
    return {
        "identity_key": "sha256（内容指纹）优先于文件名、URL、大小",
        "same_content_rule": "同一 sha256 在本次运行内只算一份；多槽命中记 DUPLICATE_SAME_CONTENT，保留首个来源，不重复计数、不重复上传。",
        "registry_reuse_rule": "data/document_registry.csv 已有同 security_id + period_covered + sha256 且本地文件存在 → 复用原 document_id 与 Drive ID。",
        "duplicate_folder_rule": "Drive 目录清单里 920418(2025年度)、920207(2026H1)、920491(IR) 各存在 3 个同名文件夹（P02 记录）。归档前必须指定唯一 canonical 目录；另两个只作历史位置记录，不得当成 3 份文件。",
        "summary_vs_full_rule": "标题含“摘要”的另记 document_type=ANNUAL_REPORT_SUMMARY，不与全文共用槽位完成数。",
        "revision_rule": "更正/修订/补充版另建 document_id（revision_no+1），旧版保留并在 supersedes_document_id 关联，不覆盖。",
        "entity_rule": "更名/借壳/北交所旧代码（如 835207→920207）按 security_id 归并，历史代码记入 limitations，不拆成两家公司。",
        "non_dedupe_rule": "同一公司的年度报告与半年度报告、全文与摘要、原文与转录稿均视为不同文件。",
    }


def build_cleanup_rules() -> dict:
    return {
        "principle": "只有“云端已确认 + 索引已回填”才允许删本地；本地是唯一副本时永不删除。",
        "preconditions_all_required": [
            "receipt.drive.file_id 非空且匹配 ^[A-Za-z0-9_-]{20,}$",
            "receipt.drive.readback.listed == true 且 parents_contains_target_folder_id == true",
            "archive_status == VERIFIED",
            "receipt.download.sha256 与回读文件大小/内容一致（不一致则重传）",
            "data/document_registry.csv 已回填该 document_id 的 drive_file_id 与 archive_status",
            "本地文件已不在 .part 状态且无同名待续传任务",
        ],
        "never_cleanup_when": [
            "archive_status ∈ {NOT_UPLOADED, UPLOADED_UNVERIFIED, SOURCE_UNAVAILABLE, ACCESS_BLOCKED}",
            "该 sha256 在本地是唯一副本（无 Drive ID、无第二份本地路径）",
            "文件属于 03_历史版本 关联的旧版/修订前版本",
            "receipt.verification.nature == SELF_CHECK 且尚未完成任一必填回读字段",
        ],
        "order": "先删重复副本（同 sha256 多路径），再删已 VERIFIED 的缓存副本；每次删除写日志（路径、sha256、依据回执 ID）。",
        "revision_retention": "原版与修订版同时保留在 03_历史版本，不做“以新替旧”的删除。",
    }


def build_priority(envelope: dict) -> list[dict]:
    return [
        {"rank": "P0", "target": "annual_2025", "why": "最新完整年度，指标宽筛主依据", "deferrable": False},
        {"rank": "P1", "target": "h1_2026", "why": "最新中期，判断拐点方向的核心窗口", "deferrable": False},
        {"rank": "P2", "target": "annual_2024,h1_2025", "why": "同比与基数必需", "deferrable": False},
        {"rank": "P3", "target": "annual_2023,h1_2024", "why": "三年趋势与更早基数；容量紧张时最后取", "deferrable": True},
        {"rank": "P4", "target": "keyword_original_announcements", "why": "仅关键词命中的公告原件，用于后期业务核验", "deferrable": True},
        {"rank": "P5", "target": "quarterly_report_pdf", "why": "季度先取结构化财务，PDF 默认关闭；仅在需要单季原文时按需取", "deferrable": True},
    ]


def build_blockers(inp: dict, probe: dict, guard: dict, samples: dict) -> list[dict]:
    reg = inp["registry"]
    return [
        {
            "id": "BLK-01",
            "blocker": "Drive API 未连接（无凭据）",
            "evidence": f"folder 302→accounts.google.com；file 401；api/v3 403（{probe['probed_at_utc']}）",
            "impact": "五个分类目录无法列举核实、Drive 配额未知、新文件无法真实上传与回读",
            "consequence": "目录状态只能 RECORDED_NOT_REVERIFIED；archive_status 无法达到 VERIFIED；配额不足无法事前判断",
            "next_action": "P07 首个上传前先做一次列目录+上传+回读三步探测；仍无权限则记 ACCESS_BLOCKED 并把归档环节留给具备权限的会话",
            "stop_rule": "不得因无权限就删除本地原件，也不得把目录 URL 当文件 ID 填表",
        },
        {
            "id": "BLK-02",
            "blocker": "Drive 配额 UNKNOWN",
            "evidence": "无 API 凭据，about.storageQuota 不可读",
            "impact": "无法判断核心槽估算量能否装下",
            "consequence": "上传中断时只能按 receipt 逐份登记，不能声称已全部归档",
            "next_action": "P07 上传首份后立即读 about.storageQuota；不足则按 priority_order 降级并保留本地",
            "stop_rule": "配额不足时停止上传，不删唯一原件",
        },
        {
            "id": "BLK-03",
            "blocker": "本机缓存盘余量偏紧",
            "evidence": f"{guard['cache_drive']} 剩余 {guard['cache_drive_free_gib']} GiB（已用 {guard['cache_drive_used_pct']}%）；核心槽估算中位 {guard['core_envelope_mid_gib']} GiB",
            "impact": "无法一次性容纳全池原件",
            "consequence": "必须滚动缓存；空间不足时按 priority_order 断点，不静默截断",
            "next_action": "M00 每批结束后强制归档+回读+清理；必要时把 cache_root 显式切到 D:\\（余 {} GiB）".format(guard["alternate_free_gib"]),
            "stop_rule": "free < 6 GiB 立即停止新下载",
        },
        {
            "id": "BLK-04",
            "blocker": "listing_date 1054/1054 UNKNOWN",
            "evidence": "P00 not_applicable_decision_table；P04 复核确认",
            "impact": "计划槽 11594 个尝试上界无法扣除上市前不适用部分",
            "consequence": "文件数只能给上界，不能给“应有份数”",
            "next_action": "P05 待办：取交易所上市日期回填后重算分母",
            "stop_rule": "未知不得按不适用处理，也不得当作缺件",
        },
        {
            "id": "BLK-05",
            "blocker": "季度报告字节数无实测样本",
            "evidence": f"QUARTERLY_REPORT n={samples['QUARTERLY_REPORT']['n']}；P05 季度 PDF 开关未实跑",
            "impact": "季度 PDF 容量无法估算",
            "consequence": "容量表中季度 PDF 记 UNMEASURED，不给数字",
            "next_action": "P07 校准含 1 个季度槽实跑后回填中位数",
            "stop_rule": "不得用年报字节数代替季度字节数",
        },
        {
            "id": "BLK-06",
            "blocker": "登记表存在非枚举历史状态值",
            "evidence": "archive_status 出现 L1_SOURCE_INDEX_ONLY(3)、UPLOADED_AND_TEXT_READ(3)；access_check_status 出现 WEB_PAGE_READ_NOT_DRIVE_ARCHIVED(5)、DRIVE_TEXT_EXTRACTION_OK(3)、OFFICIAL_PAGE_WEB_VERIFIED(1)、WEB_TEXT_READ_IDENTITY_CORRECTED(1)",
            "impact": "清理条件与回执状态无法直接机读比对",
            "consequence": "本卡只给归一化映射（PROPOSED_NOT_APPLIED），不改登记表",
            "next_action": "P01 迁移落地时按 legacy_status_normalization 表一次性归一，保留原值列",
            "stop_rule": "不得为对齐枚举而覆盖历史值",
        },
    ]


def build_legacy_normalization(inp: dict) -> dict:
    reg = inp["registry"]
    archive_counts: dict[str, int] = {}
    access_counts: dict[str, int] = {}
    for row in reg:
        archive_counts[(row.get("archive_status") or "").strip()] = archive_counts.get((row.get("archive_status") or "").strip(), 0) + 1
        access_counts[(row.get("access_check_status") or "").strip()] = access_counts.get((row.get("access_check_status") or "").strip(), 0) + 1

    archive_map = {
        "NOT_UPLOADED": ("NOT_UPLOADED", "枚举内，原值保留"),
        "UPLOADED_UNVERIFIED": ("UPLOADED_UNVERIFIED", "枚举内，原值保留"),
        "VERIFIED": ("VERIFIED", "枚举内，原值保留"),
        "NOT_REQUIRED_REFERENCE_ONLY": ("NOT_REQUIRED_REFERENCE_ONLY", "枚举内，原值保留"),
        "L1_SOURCE_INDEX_ONLY": ("NOT_UPLOADED", "仅来源索引、无二进制；映射后须在 limitations 保留 L1 事实"),
        "UPLOADED_AND_TEXT_READ": ("UPLOADED_UNVERIFIED", "有文本读取但缺回读记录，不得直接判 VERIFIED"),
    }
    access_map = {
        "NOT_CHECKED": ("NOT_CHECKED", "枚举内"),
        "AI_READ_CONFIRMED": ("AI_READ_CONFIRMED", "枚举内"),
        "OWNER_ONLY_CHECKED": ("OWNER_ONLY_CHECKED", "枚举内"),
        "ACCESS_BLOCKED": ("ACCESS_BLOCKED", "枚举内"),
        "WEB_PAGE_READ_NOT_DRIVE_ARCHIVED": ("AI_READ_CONFIRMED", "网页全文已读；归档状态独立保持 NOT_UPLOADED（五轴分离）"),
        "OFFICIAL_PAGE_WEB_VERIFIED": ("AI_READ_CONFIRMED", "官方页面已读；归档状态独立"),
        "WEB_TEXT_READ_IDENTITY_CORRECTED": ("AI_READ_CONFIRMED", "网页全文已读且身份已更正；归档状态独立"),
        "DRIVE_TEXT_EXTRACTION_OK": ("AI_READ_CONFIRMED", "Drive 文本已抽出并读；物理页复核属 evidence_status，不并入 access"),
    }
    rows = []
    for value, count in sorted(archive_counts.items()):
        mapped, note = archive_map.get(value, ("UNMAPPED_REQUIRES_REVIEW", "未覆盖的历史值，迁移时须人工裁决"))
        rows.append({"field": "archive_status", "legacy_value": value, "rows": count, "in_v11_enum": value in {"NOT_UPLOADED", "UPLOADED_UNVERIFIED", "VERIFIED", "NOT_REQUIRED_REFERENCE_ONLY", "SOURCE_UNAVAILABLE"}, "mapped_to": mapped, "note": note})
    for value, count in sorted(access_counts.items()):
        mapped, note = access_map.get(value, ("UNMAPPED_REQUIRES_REVIEW", "未覆盖的历史值，迁移时须人工裁决"))
        rows.append({"field": "access_check_status", "legacy_value": value, "rows": count, "in_v11_enum": value in {"NOT_CHECKED", "OWNER_ONLY_CHECKED", "AI_READ_CONFIRMED", "ACCESS_BLOCKED"}, "mapped_to": mapped, "note": note})
    return {
        "status": "PROPOSED_NOT_APPLIED",
        "why_not_applied": "P01 迁移方案未执行，登记表仍为 23 列；本卡不修改原始输入。",
        "rows": rows,
        "unmapped": [r for r in rows if r["mapped_to"] == "UNMAPPED_REQUIRES_REVIEW"],
    }


# ---------------------------------------------------------------- 归档路由


ROUTING_ROWS = [
    # route_id, doc_class, period_scope, condition, cache_subdir, drive_path, folder_role,
    # status_after_upload, status_after_readback, access_default, receipt, evidence, blocker, notes
    ("R01", "ANNUAL_REPORT", "FY2023|FY2024|FY2025", "核心槽全文，标题不含摘要/更正", "{security_id}/{slot_id}/", "01_原始资料/{stock_code}_{stock_name}/{YYYY}年度/", "01_原始资料", "UPLOADED_UNVERIFIED", "VERIFIED", "NOT_CHECKED", "REQUIRED", "L2", "01_原始资料目录不可用→ACCESS_BLOCKED，不降级到其他目录", "文件名保留原名；同目录允许多份不同报告期"),
    ("R02", "SEMI_ANNUAL_REPORT", "2024H1|2025H1|2026H1", "核心槽全文", "{security_id}/{slot_id}/", "01_原始资料/{stock_code}_{stock_name}/{YYYY}H1/", "01_原始资料", "UPLOADED_UNVERIFIED", "VERIFIED", "NOT_CHECKED", "REQUIRED", "L2", "同上", "半年度报告与同年度年报不同目录"),
    ("R03", "QUARTERLY_REPORT", "2024Q1—2026Q3", "仅在结构化财务缺项或需单季原文时取", "{security_id}/{slot_id}/", "01_原始资料/{stock_code}_{stock_name}/{YYYY}Q{n}/", "01_原始资料", "UPLOADED_UNVERIFIED", "VERIFIED", "NOT_CHECKED", "REQUIRED", "L2", "同上", "默认关闭；取件前须在台账记触发原因"),
    ("R04", "ANNUAL_REPORT_SUMMARY", "FY2023—FY2025", "只找到摘要、全文缺失", "{security_id}/{slot_id}_summary/", "01_原始资料/{stock_code}_{stock_name}/{YYYY}年度/", "01_原始资料", "UPLOADED_UNVERIFIED", "VERIFIED", "NOT_CHECKED", "REQUIRED", "L2", "同上", "文件名单列“摘要”；不得计入核心槽完成数"),
    ("R05", "PROSPECTUS", "上市前期间", "slot_status=NOT_APPLICABLE_PRE_LISTING 时替代", "{security_id}/prospectus/", "01_原始资料/{stock_code}_{stock_name}/招股说明书/", "01_原始资料", "UPLOADED_UNVERIFIED", "VERIFIED", "NOT_CHECKED", "REQUIRED", "L2", "同上", "document_type=PROSPECTUS，不得冒充年报"),
    ("R06", "REVISION_OR_CORRECTION", "任意", "标题含更正/修订/补充，revision_no>=1", "{security_id}/{slot_id}_rev{n}/", "03_历史版本/{stock_code}_{stock_name}/{period_key}/", "03_历史版本", "UPLOADED_UNVERIFIED", "VERIFIED", "NOT_CHECKED", "REQUIRED", "L2", "03_历史版本不可用→停止上传并保留本地", "旧版留在原目录不回移；supersedes_document_id 指向旧版"),
    ("R07", "CONTRACT_ANNOUNCEMENT", "研究截止日前两年", "关键词命中（机器人/人形/减速器/执行器/丝杠/灵巧手/伺服/关节模组等）", "{security_id}/announcements/{YYYYMMDD}/", "01_原始资料/{stock_code}_{stock_name}/公告_{YYYYMMDD}/", "01_原始资料", "UPLOADED_UNVERIFIED", "VERIFIED", "NOT_CHECKED", "REQUIRED", "L2", "同上", "关键词只用于取件排序，不作业务证据"),
    ("R08", "ANNOUNCEMENT_ORIGINAL", "研究截止日前两年", "人工补件或定向核验要求", "{security_id}/announcements/{YYYYMMDD}/", "01_原始资料/{stock_code}_{stock_name}/公告_{YYYYMMDD}/", "01_原始资料", "UPLOADED_UNVERIFIED", "VERIFIED", "NOT_CHECKED", "REQUIRED", "L2", "同上", "与 R07 同目录，按公告日期分子目录"),
    ("R09", "FINANCIAL_EXPORT", "2021—2026H1", "结构化财务导出（快照/接口导出）", "financial/", "04_财务与数据导出/{YYYYMMDD}_{内容描述}/", "04_财务与数据导出", "UPLOADED_UNVERIFIED", "VERIFIED", "NOT_CHECKED", "REQUIRED", "L2", "目录不可用→保留本机并在登记表记 NOT_UPLOADED", "导出件须带抓取日与口径说明；不得覆盖官方 PDF"),
    ("R10", "INDUSTRY_MATERIAL", "不限", "跨公司行业报告/政策/标准", "industry/", "05_行业资料/{类别}/{YYYYMMDD}_{标题}/", "05_行业资料", "UPLOADED_UNVERIFIED", "VERIFIED", "NOT_CHECKED", "REQUIRED", "L2", "同上", "不得把行业资料当作公司收入证据"),
    ("R11", "BATCH_HANDOFF_ZIP", "按批次", "批次交接包（ZIP/大表）", "handoff/", "02_批次交接/{package_id}/", "02_批次交接", "UPLOADED_UNVERIFIED", "VERIFIED", "NOT_CHECKED", "REQUIRED", "L2", "同上", "ZIP 永不入库 GitHub；只登记 manifest 与哈希"),
    ("R12", "INDEX_ONLY_L1", "全池", "仅来源索引、未取二进制", "无", "无（不上传）", "NONE", "NOT_UPLOADED", "NOT_APPLICABLE", "NOT_CHECKED", "NOT_REQUIRED", "L1", "不适用", "L1 只写 URL/标题/日期到登记表；不得伪造 Drive ID"),
    ("R13", "BLOCKED_NO_ARCHIVE", "任意", "无权限/配额不足/源站不可用", "保留本地", "无（不上传）", "NONE", "SOURCE_UNAVAILABLE", "NOT_APPLICABLE", "ACCESS_BLOCKED", "REQUIRED", "L2", "不适用", "必须写尝试入口、错误码、下一步；不得据此判定公司无业务"),
]


def write_archive_routing(path: Path) -> None:
    header = ["route_id", "doc_class", "period_scope", "route_condition", "local_cache_path_template",
              "drive_folder_path_template", "drive_parent_role", "archive_status_after_upload",
              "archive_status_after_readback", "access_check_status_default", "receipt_required",
              "evidence_level", "blocker_if_folder_missing", "notes"]
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        for row in ROUTING_ROWS:
            w.writerow(list(row))


# ---------------------------------------------------------------- 回执 schema


def build_receipt_schema() -> dict:
    slot_ids = ["annual_2023", "annual_2024", "annual_2025", "h1_2024", "h1_2025", "h1_2026",
                "q1_2024", "q3_2024", "q1_2025", "q3_2025", "q1_2026", "q3_2026",
                "announcement_ir_index", "keyword_original", "batch_handoff", "financial_export", "industry_material"]
    return {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "$id": "runs/issues/P06/transfer_receipt_schema.json",
        "title": "P06 传输回执 TRANSFER_RECEIPT_V1",
        "description": "一次“本地缓存 → Drive 归档 → 回读确认”的完整证据记录。归档成功不等于 AI 已读全文；两者分字段记录。",
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "type": "object",
        "additionalProperties": False,
        "required": ["receipt_id", "schema_version", "document_id", "security_id", "slot_id", "doc_class",
                     "revision_no", "source", "download", "local_cache", "drive", "archive_status",
                     "access_check_status", "evidence", "verification", "created_at_utc"],
        "properties": {
            "receipt_id": {"type": "string", "pattern": "^RCP-[0-9A-F]{12}$"},
            "schema_version": {"const": RECEIPT_SCHEMA_VERSION},
            "document_id": {"type": "string", "pattern": "^DOC-[0-9A-F]{16}$"},
            "security_id": {"type": "string", "pattern": "^(SH|SZ|BJ):[0-9]{6}$"},
            "slot_id": {"type": "string", "enum": slot_ids},
            "doc_class": {"type": "string", "enum": ["ANNUAL_REPORT", "ANNUAL_REPORT_SUMMARY", "SEMI_ANNUAL_REPORT",
                                                     "QUARTERLY_REPORT", "PROSPECTUS", "CONTRACT_ANNOUNCEMENT",
                                                     "ANNOUNCEMENT_ORIGINAL", "FINANCIAL_EXPORT", "INDUSTRY_MATERIAL",
                                                     "BATCH_HANDOFF_ZIP"]},
            "revision_no": {"type": "integer", "minimum": 0},
            "supersedes_document_id": {"type": ["string", "null"], "pattern": "^DOC-[0-9A-F]{16}$"},
            "source": {
                "type": "object",
                "additionalProperties": False,
                "required": ["primary_url", "source_kind", "http_status"],
                "properties": {
                    "primary_url": {"type": "string", "pattern": "^https?://"},
                    "source_kind": {"type": "string", "enum": ["CNINFO_OFFICIAL", "EXCHANGE_OFFICIAL", "ISSUER_OFFICIAL",
                                                               "USER_UPLOAD", "MIRROR_SECONDARY"]},
                    "http_status": {"type": "integer", "minimum": 100, "maximum": 599},
                    "disclosed_on": {"type": ["string", "null"], "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"},
                    "identity_method": {"type": "string", "enum": ["BODY_PHRASE", "TITLE_PLUS_YEAR_IN_BODY",
                                                                   "FIRST_PAGE_VISUAL", "NOT_VERIFIED"]},
                    "official_provenance": {"type": "string", "enum": ["VERIFIED", "PENDING", "NOT_APPLICABLE"]}
                }
            },
            "download": {
                "type": "object",
                "additionalProperties": False,
                "required": ["attempted", "bytes_received", "sha256", "downloaded_at_utc"],
                "properties": {
                    "attempted": {"type": "boolean"},
                    "bytes_received": {"type": "integer", "minimum": 0},
                    "sha256": {"type": ["string", "null"], "pattern": "^[0-9a-f]{64}$"},
                    "content_length_matches": {"type": "boolean"},
                    "page_count": {"type": ["integer", "null"], "minimum": 1},
                    "downloaded_at_utc": {"type": "string", "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}T"},
                    "partial_suffix_used": {"type": "boolean"}
                }
            },
            "local_cache": {
                "type": "object",
                "additionalProperties": False,
                "required": ["cache_root", "relative_path", "exists"],
                "properties": {
                    "cache_root": {"type": "string", "pattern": "^(sources/|[A-Za-z]:[\\\\/])"},
                    "relative_path": {"type": "string", "pattern": "\\.(pdf|zip|xlsx|csv|json)$"},
                    "exists": {"type": "boolean"},
                    "keep_until": {"type": "string", "enum": ["ARCHIVE_VERIFIED", "ALWAYS_KEEP", "MANUAL_REVIEW"]}
                }
            },
            "drive": {
                "type": "object",
                "additionalProperties": False,
                "required": ["target_folder_path", "target_folder_id", "upload_attempted"],
                "properties": {
                    "target_folder_path": {"type": "string", "pattern": "^(01_原始资料|02_批次交接|03_历史版本|04_财务与数据导出|05_行业资料)/"},
                    "target_folder_id": {"type": "string", "pattern": "^[A-Za-z0-9_-]{20,}$"},
                    "file_id": {"type": ["string", "null"], "pattern": "^[A-Za-z0-9_-]{20,}$"},
                    "file_url": {"type": ["string", "null"], "pattern": "^https://drive\\.google\\.com/file/d/[A-Za-z0-9_-]{20,}/?$"},
                    "upload_attempted": {"type": "boolean"},
                    "upload_result": {"type": "string", "enum": ["SUCCESS", "FAILED", "SKIPPED_NO_PERMISSION", "NOT_TRIED"]},
                    "readback": {
                        "type": ["object", "null"],
                        "additionalProperties": False,
                        "required": ["listed", "readback_at_utc"],
                        "properties": {
                            "listed": {"type": "boolean"},
                            "name": {"type": ["string", "null"]},
                            "mime_type": {"type": ["string", "null"]},
                            "size_bytes": {"type": ["integer", "null"], "minimum": 0},
                            "parents_contains_target_folder_id": {"type": "boolean"},
                            "readback_at_utc": {"type": "string", "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}T"}
                        }
                    }
                }
            },
            "archive_status": {"type": "string", "enum": ["NOT_UPLOADED", "UPLOADED_UNVERIFIED", "VERIFIED",
                                                          "NOT_REQUIRED_REFERENCE_ONLY", "SOURCE_UNAVAILABLE"]},
            "access_check_status": {"type": "string", "enum": ["NOT_CHECKED", "OWNER_ONLY_CHECKED", "AI_READ_CONFIRMED", "ACCESS_BLOCKED"]},
            "evidence": {
                "type": "object",
                "additionalProperties": False,
                "required": ["level"],
                "properties": {
                    "level": {"type": "string", "enum": ["L1", "L2", "L3"]},
                    "page_quote": {
                        "type": ["object", "null"],
                        "additionalProperties": False,
                        "required": ["page", "quote", "quote_located"],
                        "properties": {
                            "page": {"type": "integer", "minimum": 1},
                            "quote": {"type": "string"},
                            "quote_located": {"type": "boolean"},
                            "scope": {"type": "string", "enum": ["CONSOLIDATED", "PARENT_ONLY", "UNKNOWN"]}
                        }
                    }
                }
            },
            "failure": {
                "type": ["object", "null"],
                "additionalProperties": False,
                "required": ["code", "attempts", "next_action"],
                "properties": {
                    "code": {"type": "string", "enum": ["HTTP_ERROR", "TIMEOUT", "QUOTA_EXCEEDED", "NO_PERMISSION",
                                                         "IDENTITY_MISMATCH", "PARTIAL_CONTENT", "DISK_FULL",
                                                         "SCHEMA_INVALID", "SOURCE_UNAVAILABLE"]},
                    "http_status": {"type": ["integer", "null"], "minimum": 100, "maximum": 599},
                    "message": {"type": "string"},
                    "attempts": {"type": "integer", "minimum": 0},
                    "next_action": {"type": "string", "enum": ["RETRY_LATER", "MANUAL_REVIEW", "RESOLVE_LISTING_DATE",
                                                                "REQUEST_PERMISSION", "FREE_SPACE", "STOP_AND_KEEP_LOCAL"]}
                }
            },
            "verification": {
                "type": "object",
                "additionalProperties": False,
                "required": ["nature", "checks", "verified_by", "verified_at_utc"],
                "properties": {
                    "nature": {"type": "string", "enum": ["SELF_CHECK", "INDEPENDENT"]},
                    "checks": {"type": "array", "items": {"type": "string", "enum": [
                        "MAGIC_HEADER", "SIZE_FLOOR", "PDF_OPENABLE", "PAGE_COUNT_FLOOR", "ISSUER_MATCH",
                        "PERIOD_MATCH", "FORM_FULL_TEXT", "CONTENT_LENGTH", "SHA256", "DRIVE_READBACK",
                        "PARENTS_MATCH", "PAGE_QUOTE_LOCATED"]}},
                    "verified_by": {"type": "string"},
                    "verified_at_utc": {"type": "string", "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}T"}
                }
            },
            "created_at_utc": {"type": "string", "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}T"}
        },
        "allOf": [
            {
                "if": {"properties": {"archive_status": {"const": "VERIFIED"}}, "required": ["archive_status"]},
                "then": {
                    "required": ["drive"],
                    "properties": {"drive": {
                        "required": ["file_id", "file_url", "readback", "upload_result"],
                        "properties": {
                            "file_id": {"type": "string", "pattern": "^[A-Za-z0-9_-]{20,}$"},
                            "file_url": {"type": "string", "pattern": "^https://drive\\.google\\.com/file/d/[A-Za-z0-9_-]{20,}/?$"},
                            "readback": {"type": "object", "required": ["listed", "parents_contains_target_folder_id"],
                                         "properties": {"listed": {"const": True}, "parents_contains_target_folder_id": {"const": True}}}
                        }
                    }}
                }
            },
            {
                "if": {"properties": {"access_check_status": {"const": "AI_READ_CONFIRMED"}}, "required": ["access_check_status"]},
                "then": {"properties": {"evidence": {
                    "required": ["page_quote"],
                    "properties": {"page_quote": {"type": "object", "required": ["quote_located"],
                                                  "properties": {"quote_located": {"const": True}}}}
                }}}
            },
            {
                "if": {"properties": {"doc_class": {"enum": ["ANNUAL_REPORT", "SEMI_ANNUAL_REPORT", "QUARTERLY_REPORT", "PROSPECTUS"]}},
                       "required": ["doc_class"]},
                "then": {"properties": {"evidence": {"properties": {"level": {"enum": ["L2", "L3"]}}}}}
            },
            {
                "if": {"properties": {"archive_status": {"enum": ["NOT_UPLOADED", "SOURCE_UNAVAILABLE"]}}, "required": ["archive_status"]},
                "then": {"required": ["failure"]}
            }
        ],
        "x_invariants": [
            {"id": "INV-01", "rule": "archive_status=VERIFIED 必须同时具备 file_id、file_url、readback.listed=true、parents_contains_target_folder_id=true，缺一不可。"},
            {"id": "INV-02", "rule": "access_check_status=AI_READ_CONFIRMED 必须有 evidence.page_quote.quote_located=true；归档成功不能替代读全文。"},
            {"id": "INV-03", "rule": "drive.target_folder_id 与 drive.file_id 必须是 Drive 不透明 ID；禁止出现 http、drive.google.com、/folders/。"},
            {"id": "INV-04", "rule": "drive.file_url 只能是 https://drive.google.com/file/d/<file_id>；目录链接不得填入。"},
            {"id": "INV-05", "rule": "archive_status ∈ {NOT_UPLOADED, SOURCE_UNAVAILABLE} 必须带 failure 块说明原因与下一步。"},
            {"id": "INV-06", "rule": "download.sha256 只能来自实际取得的二进制；未取得时置 null，不得编造。"},
            {"id": "INV-07", "rule": "revision_no>0 时必须填 supersedes_document_id，且旧版记录不得删除或覆盖。"},
            {"id": "INV-08", "rule": "verification.nature=SELF_CHECK 的记录不得在业务采用环节当作独立验收。"},
            {"id": "INV-09", "rule": "download.attempted=false 时 archive_status 不得为 VERIFIED，且 upload_result=NOT_TRIED。"},
            {"id": "INV-10", "rule": "同一 document_id 的 receipt 可多次生成（重试），但只有 archive_status=VERIFIED 的那条可驱动缓存清理。"}
        ],
        "x_forbidden_patterns": {
            "drive_file_id_must_not_contain": ["http", "drive.google.com", "/folders/", "usp=drivesdk"],
            "drive_target_folder_id_must_not_contain": ["http", "drive.google.com", "/file/d/"],
            "note": "目录 URL / 分享链接里的 usp= 参数都不是 ID，必须先解析出裸 ID 再填。"
        },
        "x_examples": {
            "valid_verified_receipt": {
                "receipt_id": "RCP-0000000000A1",
                "schema_version": RECEIPT_SCHEMA_VERSION,
                "document_id": "DOC-42A96A84780EB94B",
                "security_id": "BJ:920207",
                "slot_id": "annual_2025",
                "doc_class": "ANNUAL_REPORT",
                "revision_no": 0,
                "supersedes_document_id": None,
                "source": {
                    "primary_url": "https://static.cninfo.com.cn/finalpage/2026-04-27/1225221058.PDF",
                    "source_kind": "CNINFO_OFFICIAL",
                    "http_status": 200,
                    "disclosed_on": "2026-04-26",
                    "identity_method": "TITLE_PLUS_YEAR_IN_BODY",
                    "official_provenance": "VERIFIED"
                },
                "download": {
                    "attempted": True,
                    "bytes_received": 3110800,
                    "sha256": "86eed5c4be4c1e1be67cce9bae452b8ec503be089d6a5bcf60bb04a542849e27",
                    "content_length_matches": True,
                    "page_count": 178,
                    "downloaded_at_utc": "2026-10-26T08:41:48Z",
                    "partial_suffix_used": True
                },
                "local_cache": {
                    "cache_root": "sources/p06_cache/",
                    "relative_path": "BJ_920207/annual_2025/DOC-42A96A84780EB94B.pdf",
                    "exists": True,
                    "keep_until": "ARCHIVE_VERIFIED"
                },
                "drive": {
                    "target_folder_path": "01_原始资料/920207_众诚科技/2025年度/",
                    "target_folder_id": "1PPX55Sl9ZNhT6JaG-SUm1OByanYu6o6t",
                    "file_id": None,
                    "file_url": None,
                    "upload_attempted": False,
                    "upload_result": "NOT_TRIED",
                    "readback": None
                },
                "archive_status": "NOT_UPLOADED",
                "access_check_status": "NOT_CHECKED",
                "evidence": {"level": "L2", "page_quote": None},
                "failure": {
                    "code": "NO_PERMISSION",
                    "http_status": 403,
                    "message": "本会话无 Drive API 凭据：folder 302、file 401、api/v3 403",
                    "attempts": 1,
                    "next_action": "REQUEST_PERMISSION"
                },
                "verification": {
                    "nature": "SELF_CHECK",
                    "checks": ["MAGIC_HEADER", "SIZE_FLOOR", "PDF_OPENABLE", "PAGE_COUNT_FLOOR", "ISSUER_MATCH",
                               "PERIOD_MATCH", "FORM_FULL_TEXT", "CONTENT_LENGTH", "SHA256"],
                    "verified_by": "WorkBuddy AI",
                    "verified_at_utc": "2026-10-26T08:41:48Z"
                },
                "created_at_utc": "2026-10-26T08:41:48Z"
            }
        }
    }


# ---------------------------------------------------------------- 迷你校验器

_SUPPORTED = {"type", "required", "properties", "pattern", "enum", "const", "minimum", "maximum",
              "items", "allOf", "if", "then", "additionalProperties", "description", "title", "$schema", "$id"}


class SchemaError(AssertionError):
    pass


def _type_ok(value, t) -> bool:
    types = t if isinstance(t, list) else [t]
    py = {"object": dict, "array": list, "string": str, "integer": int, "number": (int, float), "boolean": bool, "null": type(None)}
    for name in types:
        if name == "integer" and isinstance(value, bool):
            continue
        if name == "number" and isinstance(value, bool):
            continue
        if isinstance(value, py[name]):
            return True
    return False


def validate(instance, schema, path="$", errors=None) -> list[str]:
    if errors is None:
        errors = []
    if "type" in schema and not _type_ok(instance, schema["type"]):
        errors.append(f"{path}: type 期望 {schema['type']}，实得 {type(instance).__name__}")
        return errors
    if "const" in schema and instance != schema["const"]:
        errors.append(f"{path}: const 期望 {schema['const']!r}，实得 {instance!r}")
    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{path}: 不在枚举内 {instance!r}")
    if "pattern" in schema and isinstance(instance, str):
        if not re.search(schema["pattern"], instance):
            errors.append(f"{path}: 不匹配 pattern {schema['pattern']} → {instance!r}")
    if "minimum" in schema and isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if instance < schema["minimum"]:
            errors.append(f"{path}: 小于 minimum {schema['minimum']}")
    if "maximum" in schema and isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if instance > schema["maximum"]:
            errors.append(f"{path}: 大于 maximum {schema['maximum']}")
    if isinstance(instance, dict):
        for key in schema.get("required", []):
            if key not in instance:
                errors.append(f"{path}: 缺必填字段 {key}")
        props = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            extra = set(instance) - set(props)
            if extra:
                errors.append(f"{path}: 出现未定义字段 {sorted(extra)}")
        for key, sub in props.items():
            if key in instance:
                validate(instance[key], sub, f"{path}.{key}", errors)
    if isinstance(instance, list) and "items" in schema:
        for i, item in enumerate(instance):
            validate(item, schema["items"], f"{path}[{i}]", errors)
    for sub in schema.get("allOf", []):
        if "if" in sub:
            cond_errs = validate(instance, sub["if"], path)
            if not cond_errs:
                validate(instance, sub.get("then", {}), path, errors)
        else:
            validate(instance, sub, path, errors)
    return errors


def receipt_invariant_checks(receipt: dict) -> list[str]:
    errs = []
    folder_url_bits = ["http", "drive.google.com", "/folders/", "usp=drivesdk"]
    for field in ("target_folder_id", "file_id"):
        val = (receipt.get("drive") or {}).get(field)
        if isinstance(val, str):
            for bit in folder_url_bits:
                if bit in val:
                    errs.append(f"INV-03: drive.{field} 含 {bit} → {val}")
    return errs


# ---------------------------------------------------------------- 主构建


def build_all() -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    inp = load_inputs()

    inputs_used = [
        REPO / "PROJECT_STATE.json",
        REPO / "data/company_master.csv",
        REPO / "data/document_registry.csv",
        REPO / "data/drive_folders.csv",
        REPO / "data/intake_company_queue.csv",
        REPO / "data/intake_batch_index.csv",
        REPO / "data/pdf_transfer_plan.csv",
        REPO / "runs/issues/P00/collection_scope.json",
        REPO / "runs/issues/P02/existing_assets.csv",
        REPO / "runs/issues/P05/collector_config.json",
        REPO / "runs/issues/P05/collection_index.csv",
    ]

    planned_rows, planned_summary = build_planned_slots(inp)
    samples = build_samples(inp)
    envelope = build_envelope(inp, planned_rows, samples)
    actual = build_actual_bytes(inp)
    probe = probe_drive()
    drive_layout = build_drive_layout(inp, probe)
    guard = build_capacity_guard(envelope, actual)

    reg = inp["registry"]
    archive_counts: dict[str, int] = {}
    access_counts: dict[str, int] = {}
    for row in reg:
        a = (row.get("archive_status") or "").strip()
        b = (row.get("access_check_status") or "").strip()
        archive_counts[a] = archive_counts.get(a, 0) + 1
        access_counts[b] = access_counts.get(b, 0) + 1
    local_paths = [r["local_file"].strip() for r in reg if (r.get("local_file") or "").strip()]
    local_exists = sum(1 for p in local_paths if Path(p).exists())

    actually_found = {
        "documents_registered": len(reg),
        "unique_document_id": len({r["document_id"] for r in reg if r.get("document_id")}),
        "unique_content_sha256": len({r["sha256"] for r in reg if r.get("sha256")}),
        "drive_file_id_present": sum(1 for r in reg if (r.get("drive_file_id") or "").strip()),
        "local_file_recorded": len(local_paths),
        "local_file_exists_now": local_exists,
        "archive_status_counts": archive_counts,
        "access_check_status_counts": access_counts,
        "archived_verified": archive_counts.get("VERIFIED", 0),
        "uploaded_unverified": archive_counts.get("UPLOADED_UNVERIFIED", 0),
        "not_uploaded": archive_counts.get("NOT_UPLOADED", 0) + archive_counts.get("L1_SOURCE_INDEX_ONLY", 0),
        "ai_read_confirmed": access_counts.get("AI_READ_CONFIRMED", 0),
        "business_accepted_independent": 0,
        "source": "data/document_registry.csv（只读）",
        "note": "“已发现”是文件层面计数，不等于已核读、更不等于已业务验收；四项不得合并成单一完成率。",
    }

    storage_plan = {
        "plan_version": PLAN_VERSION,
        "issue_number": ISSUE_NUMBER,
        "issue_key": ISSUE_KEY,
        "storage_plan_version": SCHEMA_VERSION,
        "generated_at": now_cn(),
        "generated_at_utc": now_utc(),
        "executor": "WorkBuddy AI",
        "review_nature": "SELF_CHECK",
        "scope_statement": "只定容量口径、目录路由、归档与交接规则；本卡不下载、不上传、不改登记表、不做业务判断、不估值。",
        "inputs": input_fingerprint(inputs_used),
        "capacity": {
            "method": "总容量 = Σ(各槽实际尝试数 × 该槽单位文件字节中位数)（P00 capacity_rule.estimation_method）",
            "status": "PRE_CALIBRATION_ESTIMATE_NOT_FACT",
            "p00_rule_compliance": "P00 规定 P07 实测前 pre_calibration_state=UNMEASURED、不对外给单一“总 GB 事实值”。本卡只给可复算的区间与样本量，并显式标 ESTIMATE_NOT_FACT；P07 校准后重算。",
            "tiers": {
                "planned_slots": planned_summary,
                "actually_found": actually_found,
                "actual_bytes": actual,
            },
            "unit_bytes_samples": samples,
            "envelope": envelope,
            "publishing_rule": "任何对外引用必须带“估算（ESTIMATE_NOT_FACT）+ 样本量 n + 区间”，不得写成“需要 X GB”的既成事实。",
        },
        "local_cache": {
            "cache_root_default": "sources/p06_cache/",
            "raw_response_root": "sources/p06_raw/",
            "layout": "sources/p06_cache/{security_id}/{slot_id}/{document_id}.pdf（下载中为 .pdf.part）",
            "git_policy": "sources/** 已被 .gitignore 排除；缓存目录永不入库，只入库回执与索引。",
            "rolling_window": True,
            "flush_after": "每个采集批次（M00_xx）结束",
            "capacity_guard": guard,
            "priority_order": build_priority(envelope),
        },
        "drive_layout": drive_layout,
        "registration_order": build_registration_order(),
        "dedupe_rules": build_dedupe_rules(),
        "cleanup_rules": build_cleanup_rules(),
        "legacy_status_normalization": build_legacy_normalization(inp),
        "blockers": build_blockers(inp, probe, guard, samples),
        "invariants": [
            {"id": "S-01", "rule": "GitHub 不提交 PDF/ZIP/XLSX/原始大表；只提交规则、索引、回执、短引文与哈希。", "check": "git ls-files 二进制扩展名计数=0"},
            {"id": "S-02", "rule": "目录 URL 不得写入 drive_file_id；目录 ID 只进 drive.target_folder_id。", "check": "登记表与回执双向扫描"},
            {"id": "S-03", "rule": "归档成功 ≠ AI 已读全文：archive_status 与 access_check_status 分字段、分证据。", "check": "INV-02 回执校验"},
            {"id": "S-04", "rule": "容量不足时写断点与优先级，不静默截断、不改名单凑数。", "check": "breach_actions + priority_order"},
            {"id": "S-05", "rule": "唯一原件不删；修订版另存另 ID，旧版保留。", "check": "cleanup_rules.never_cleanup_when"},
            {"id": "S-06", "rule": "缺失不等于 0，未尝试不等于缺件；NOT_TRIED 不计完成。", "check": "状态口径沿用 P00"},
            {"id": "S-07", "rule": "哈希只能来自实际二进制；未计算留空。", "check": "INV-06"},
            {"id": "S-08", "rule": "本卡不修改原始输入：document_registry / company_master / intake 队列保持原字节。", "check": "git diff --stat 空"},
        ],
        "handoff_to_p07": [
            "上传首个文件前做三步探测：列目录 → 上传 → 回读；任一步失败即记 ACCESS_BLOCKED，不进批量。",
            "用 10 家校准实测 annual/h1/quarterly 三类字节中位数，回填 capacity.unit_bytes_samples 并把 status 改为 CALIBRATED。",
            "校准中至少跑 1 个季度槽，补齐 QUARTERLY_REPORT 的 UNMEASURED。",
            "校准期间保持滚动缓存：单轮不超过 8 GiB，批次结束即归档回读清理。",
            "首个 VERIFIED 回执落库后，再放开 M00_01。",
        ],
        "out_of_scope": [
            "不下载全池、不上传文件、不改登记表",
            "不判定任何公司是否披露（属采集卡）",
            "不做业务结论、拐点判断、估值",
        ],
    }

    plan_path = OUT / "storage_plan.json"
    with open(plan_path, "w", encoding="utf-8") as fh:
        json.dump(storage_plan, fh, ensure_ascii=False, indent=2)

    routing_path = OUT / "archive_routing.csv"
    write_archive_routing(routing_path)

    schema = build_receipt_schema()
    schema_path = OUT / "transfer_receipt_schema.json"
    with open(schema_path, "w", encoding="utf-8") as fh:
        json.dump(schema, fh, ensure_ascii=False, indent=2)

    return {"storage_plan": storage_plan, "schema": schema, "paths": {
        "storage_plan": plan_path, "archive_routing": routing_path, "schema": schema_path}}


# ---------------------------------------------------------------- 自检


def run_self_check(built: dict) -> dict:
    plan = built["storage_plan"]
    schema = built["schema"]
    checks = []

    def add(cid, item, expected, actual, ok, method):
        checks.append({"id": cid, "item": item, "expected": expected, "actual": actual,
                       "result": "PASS" if ok else "FAIL", "method": method})

    # SC1 入库无二进制
    out = subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True, text=True, encoding="utf-8")
    tracked = out.stdout.splitlines()
    bin_ext = re.compile(r"\.(pdf|zip|xlsx|xls|docx|pptx|png|jpg|jpeg)$", re.I)
    bin_hits = [p for p in tracked if bin_ext.search(p)]
    add("SC1", "GitHub 跟踪文件里没有 PDF/ZIP/大表",
        "二进制扩展名计数=0", f"跟踪 {len(tracked)} 个文件，二进制 {len(bin_hits)} 个：{bin_hits[:5]}",
        len(bin_hits) == 0, "git ls-files + 扩展名正则")

    # SC2 本次交付自身体量与类型
    sizes = {rel(p): p.stat().st_size for p in built["paths"].values()}
    big = {k: v for k, v in sizes.items() if v > 512 * 1024}
    add("SC2", "P06 交付本身是小型文本",
        "单文件 ≤ 512 KiB", f"最大 {max(sizes.values())} B；超限 {big}", not big, "stat")

    # SC3 登记表文件 ID 格式与目录 URL 混入
    reg = read_csv(REPO / "data/document_registry.csv")
    id_pat = re.compile(r"^[A-Za-z0-9_-]{20,}$")
    bad_id = [r["document_id"] for r in reg if (r.get("drive_file_id") or "").strip() and not id_pat.match(r["drive_file_id"].strip())]
    url_in_id = [r["document_id"] for r in reg if any(b in (r.get("drive_file_id") or "") for b in ("http", "/folders/", "drive.google.com"))]
    add("SC3", "登记表没有把目录 URL 填进文件 ID",
        "格式违规=0 且 URL 混入=0", f"格式违规 {len(bad_id)}；URL 混入 {len(url_in_id)}",
        not bad_id and not url_in_id, "逐行正则 + 子串扫描")

    # SC4 回执 schema：正例通过、三个反例被拒
    good = schema["x_examples"]["valid_verified_receipt"]
    errs_good = validate(good, schema) + receipt_invariant_checks(good)

    import copy
    neg = {}
    n1 = copy.deepcopy(good)
    n1["drive"]["target_folder_id"] = "https://drive.google.com/drive/folders/1uC1sk5q7PKMZMLPLt-xIxOj2nPk4z0Ne"
    neg["folder_url_in_folder_id"] = (validate(n1, schema) + receipt_invariant_checks(n1))

    n2 = copy.deepcopy(good)
    n2["archive_status"] = "VERIFIED"
    neg["verified_without_readback"] = validate(n2, schema)

    n3 = copy.deepcopy(good)
    n3["access_check_status"] = "AI_READ_CONFIRMED"
    neg["read_confirmed_without_page_quote"] = validate(n3, schema)

    n4 = copy.deepcopy(good)
    n4["download"]["sha256"] = "NOT_COMPUTED"
    neg["fake_hash"] = validate(n4, schema)

    rejected = {k: bool(v) for k, v in neg.items()}
    add("SC4", "回执 schema 能拒收四类错误回执",
        "正例 0 错；反例 4/4 被拒",
        f"正例错 {len(errs_good)} 条；反例 {rejected}；正例错误明细 {errs_good[:2]}",
        not errs_good and all(rejected.values()), "自实现 draft-07 子集校验器（type/required/pattern/enum/const/min/max/allOf/if-then/additionalProperties）+ 4 条不变量")

    # SC5 容量可复算
    inp = load_inputs()
    planned_rows, planned_summary = build_planned_slots(inp)
    samples = build_samples(inp)
    env2 = build_envelope(inp, planned_rows, samples)
    same = (env2["totals"]["mid_bytes"] == plan["capacity"]["envelope"]["totals"]["mid_bytes"]
            and planned_summary["total_attempt_upper_bound"] == plan["capacity"]["tiers"]["planned_slots"]["total_attempt_upper_bound"])
    add("SC5", "容量数字可复算（重跑同结果）",
        "重算 mid 与上界一致",
        f"mid {env2['totals']['mid_bytes']} vs {plan['capacity']['envelope']['totals']['mid_bytes']}；上界 {planned_summary['total_attempt_upper_bound']}",
        same, "重新装载输入并重算")

    # SC6 P00 容量规则遵守：不把估算当事实、季度留空
    q_status = samples["QUARTERLY_REPORT"]["status"]
    q_envelope_null = all(r.get("envelope_status") != "ESTIMATE_NOT_FACT" for r in plan["capacity"]["envelope"]["per_slot"] if r["slot_id"].startswith("q"))
    add("SC6", "不把未实测类别写成事实",
        "status=PRE_CALIBRATION_ESTIMATE_NOT_FACT 且季度不填估算",
        f"status={plan['capacity']['status']}；季度样本={q_status}；季度无估算={q_envelope_null}",
        plan["capacity"]["status"] == "PRE_CALIBRATION_ESTIMATE_NOT_FACT" and q_status == "UNMEASURED" and q_envelope_null,
        "字段核对")

    # SC7 五个分类目录 + 根目录齐备，且 ID 不是 URL
    roles = {f["role"] for f in plan["drive_layout"]["folders"]}
    need = {"PROJECT_ROOT", "01_原始资料", "02_批次交接", "03_历史版本", "04_财务与数据导出", "05_行业资料"}
    all_ids_ok = all(f["id_is_not_url"] for f in plan["drive_layout"]["folders"])
    add("SC7", "Drive 根目录与 01—05 分类目录登记齐备，ID 与 URL 分离",
        "6 个角色齐备、ID 均非 URL",
        f"缺 {sorted(need - roles)}；ID 全部非 URL={all_ids_ok}",
        roles == need and all_ids_ok, "读 data/drive_folders.csv + 正则")

    # SC8 路由表覆盖 schema 的 doc_class
    rows = read_csv(OUT / "archive_routing.csv")
    routed = {r["doc_class"] for r in rows}
    classes = set(schema["properties"]["doc_class"]["enum"])
    missing = classes - routed
    add("SC8", "每个文档类别都有归档路由",
        "doc_class 全覆盖",
        f"schema {len(classes)} 类；未覆盖 {sorted(missing)}",
        not missing, "集合比对")

    # SC9 原始输入未被改动
    diff = subprocess.run(["git", "diff", "--stat", "--", "data/document_registry.csv", "data/company_master.csv",
                           "data/intake_company_queue.csv", "data/intake_batch_index.csv"],
                          cwd=REPO, capture_output=True, text=True, encoding="utf-8")
    add("SC9", "本卡没有改动原始输入",
        "四个输入文件 diff 为空",
        (diff.stdout.strip() or "空"),
        diff.stdout.strip() == "", "git diff --stat")

    # SC10 优先级与断点规则存在且覆盖核心槽
    prio = {p["target"] for p in plan["local_cache"]["priority_order"]}
    covered = all(any(s in t for t in prio) for s in ["annual_2025", "h1_2026", "annual_2024"])
    add("SC10", "容量不足时有优先级与断点记录，不静默截断",
        "P0—P5 覆盖核心槽且 breach_actions 非空",
        f"优先级 {sorted(prio)}；breach 动作 {len(plan['local_cache']['capacity_guard']['breach_actions'])} 条",
        covered and len(plan["local_cache"]["capacity_guard"]["breach_actions"]) >= 4,
        "字段核对")

    # SC11 路由表状态值合法且上传/回读两态分离
    allowed = {"NOT_UPLOADED", "UPLOADED_UNVERIFIED", "VERIFIED", "NOT_REQUIRED_REFERENCE_ONLY",
               "SOURCE_UNAVAILABLE", "NOT_APPLICABLE"}
    bad_status = [r["route_id"] for r in rows
                  if r["archive_status_after_upload"] not in allowed or r["archive_status_after_readback"] not in allowed]
    same_state = [r["route_id"] for r in rows
                  if r["archive_status_after_upload"] == "UPLOADED_UNVERIFIED" and r["archive_status_after_readback"] != "VERIFIED"]
    add("SC11", "路由表把“上传后”与“回读后”两态分开且取值合法",
        "状态值全部在枚举内、上传态与回读态不混写",
        f"非法值 {bad_status}；上传后未升级为 VERIFIED 的 {same_state}",
        not bad_status and not same_state, "逐行枚举比对")

    passed = sum(1 for c in checks if c["result"] == "PASS")
    report = {
        "issue_key": ISSUE_KEY,
        "issue_number": ISSUE_NUMBER,
        "generated_at": now_cn(),
        "review_nature": "SELF_CHECK",
        "method": "可复算脚本 tools/p06_storage_plan.py；输入只读，输出仅 runs/issues/P06/",
        "checks": checks,
        "summary": {"total": len(checks), "pass": passed, "fail": len(checks) - passed},
        "validator_coverage": sorted(_SUPPORTED),
        "not_covered": [
            "未做真实上传与回读（无 Drive 权限）",
            "未实测季度报告字节数",
            "未做独立审计（执行者与自检者为同一 AI）",
        ],
    }
    with open(OUT / "self_check.json", "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    return report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只跑自检")
    ap.add_argument("--validate-receipt", metavar="PATH", help="按 transfer_receipt_schema.json 校验一份回执")
    args = ap.parse_args()

    if args.validate_receipt:
        schema = read_json(OUT / "transfer_receipt_schema.json")
        inst = read_json(Path(args.validate_receipt))
        errs = validate(inst, schema) + receipt_invariant_checks(inst)
        if errs:
            print(f"[P06] 回执不合格：{len(errs)} 条")
            for e in errs:
                print("  -", e)
            return 1
        print("[P06] 回执合格")
        return 0

    if args.check:
        plan = read_json(OUT / "storage_plan.json")
        schema = read_json(OUT / "transfer_receipt_schema.json")
        built = {"storage_plan": plan, "schema": schema,
                 "paths": {"storage_plan": OUT / "storage_plan.json",
                           "archive_routing": OUT / "archive_routing.csv",
                           "schema": OUT / "transfer_receipt_schema.json"}}
    else:
        built = build_all()

    report = run_self_check(built)
    s = report["summary"]
    print(f"[P06] self-check {s['pass']}/{s['total']} PASS")
    for c in report["checks"]:
        if c["result"] != "PASS":
            print(f"  FAIL {c['id']}: {c['actual']}")
    return 0 if s["fail"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
