#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""A00｜汇总 11 批覆盖率，核对全池和全部资料槽。

只读既有输入（名单、checkpoint、collection_index、财务快照、登记表、上市日期侧表），
不改任何原始输入；产出 A00 的三份交付。

用法：
    python tools/a00_reconcile.py --check     # 只算不写，打印摘要
    python tools/a00_reconcile.py --run       # 写 runs/issues/A00/ 三份交付
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "runs", "issues", "A00")

BATCHES = [f"M00_{i:02d}" for i in range(1, 12)]
SLOTS = ["annual_2023", "annual_2024", "annual_2025",
         "h1_2024", "h1_2025", "h1_2026", "q1_2026"]
SNAPSHOT = os.path.join(os.path.dirname(ROOT),
                        "collection_run_20261026", "raw", "既有候选池财务快照.csv")

VERIFIED = "COLLECTED_IDENTITY_VERIFIED"
PENDING = "COLLECTED_PENDING_IDENTITY"
FAILED = "SOURCE_FAILED"
NOT_TRIED = "NOT_TRIED"
NA = "NOT_APPLICABLE_PRE_LISTING"
NOT_DISCLOSED = "NOT_YET_DISCLOSED"


def rp(*p):
    return os.path.join(ROOT, *p)


def read_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path, rows, fields):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------- 名单核对
def check_roster():
    master = read_csv(rp("data", "company_master.csv"))
    queue = read_csv(rp("data", "intake_company_queue.csv"))
    index = read_csv(rp("data", "intake_batch_index.csv"))

    master_ids = [r["security_id"] for r in master]
    master_set = set(master_ids)

    assignments = {}
    seen = defaultdict(list)          # security_id -> [batch...]
    per_batch = {}
    for b in BATCHES:
        path = rp("intake_batches", b, "assignment.csv")
        rows = read_csv(path)
        ids = [r["security_id"] for r in rows]
        dup_in_file = [k for k, v in Counter(ids).items() if v > 1]
        bad_batch = [r["security_id"] for r in rows if r["batch_id"] != b]
        for i in ids:
            seen[i].append(b)
        assignments[b] = ids
        per_batch[b] = {
            "assignment_rows": len(rows),
            "unique_ids": len(set(ids)),
            "duplicates_within_file": dup_in_file,
            "batch_id_mismatch_rows": len(bad_batch),
            "codes": len({r["stock_code"] for r in rows}),
        }

    union = set(seen)
    cross_dup = {k: v for k, v in seen.items() if len(v) > 1}

    # 队列与名单一致性
    q_ids = {r["security_id"] for r in queue}
    q_map = {r["security_id"]: r["batch_id"] for r in queue}
    q_mismatch = [i for i, bs in seen.items() if q_map.get(i) not in bs]

    # 批次索引
    idx_counts = {r["batch_id"]: int(r["company_count"]) for r in index}

    return {
        "master_rows": len(master),
        "master_unique_ids": len(master_set),
        "master_unique_codes": len({r["stock_code"] for r in master}),
        "queue_rows": len(queue),
        "queue_unique_ids": len(q_ids),
        "index_batches": len(index),
        "index_total_companies": sum(idx_counts.values()),
        "index_counts": idx_counts,
        "assignment_total_rows": sum(len(v) for v in assignments.values()),
        "assignment_unique_ids": len(union),
        "per_batch": per_batch,
        "cross_batch_duplicates": cross_dup,
        "missing_vs_master": sorted(master_set - union),
        "extra_vs_master": sorted(union - master_set),
        "missing_vs_queue": sorted(q_ids - union),
        "extra_vs_queue": sorted(union - q_ids),
        "queue_batch_mismatch": q_mismatch,
        "master_dup_ids": [k for k, v in Counter(master_ids).items() if v > 1],
        "batch_counts_match_index": all(
            per_batch[b]["assignment_rows"] == idx_counts.get(b) for b in BATCHES),
    }


# ---------------------------------------------------------------- 槽位核对
def load_checkpoints():
    cdir = rp("runs", "collection", "checkpoint")
    out = {}
    for fn in sorted(os.listdir(cdir)):
        if not fn.endswith(".json"):
            continue
        with open(os.path.join(cdir, fn), encoding="utf-8") as f:
            d = json.load(f)
        out[d["security_id"]] = d
    return out


def slot_status_of(cp_slots):
    """从 checkpoint 取 7 槽状态；缺槽记 MISSING_SLOT。"""
    res = {}
    for s in SLOTS:
        rec = cp_slots.get(s)
        res[s] = (rec or {}).get("status", "MISSING_SLOT")
    return res


def check_slots(roster, cps, index_rows):
    companies = read_csv(rp("data", "company_master.csv"))
    listing = {r["security_id"]: r for r in read_csv(rp("data", "company_listing_dates.csv"))}
    batch_of = {}
    for b in BATCHES:
        for r in read_csv(rp("intake_batches", b, "assignment.csv")):
            batch_of[r["security_id"]] = b

    idx = defaultdict(dict)
    for r in index_rows:
        idx[r["security_id"]][r["slot_id"]] = r

    # 原件存在性
    local_ok = local_missing = 0
    missing_detail = []
    bytes_total = 0

    pool_rows = []
    for c in companies:
        sid = c["security_id"]
        cp = cps.get(sid, {}).get("slots", {})
        st = slot_status_of(cp)
        cnt = Counter(st.values())

        present = miss = 0
        row_bytes = 0
        for s in SLOTS:
            rec = cp.get(s) or {}
            doc = rec.get("document") or {}
            lf = doc.get("local_file")
            if rec.get("status") in (VERIFIED, PENDING) and lf:
                p = rp(lf.replace("/", os.sep))
                if os.path.exists(p):
                    present += 1
                    try:
                        row_bytes += os.path.getsize(p)
                    except OSError:
                        pass
                else:
                    miss += 1
                    missing_detail.append({"security_id": sid, "slot_id": s, "local_file": lf})
        local_ok += present
        local_missing += miss
        bytes_total += row_bytes

        verified = cnt.get(VERIFIED, 0)
        pending = cnt.get(PENDING, 0)
        failed = cnt.get(FAILED, 0)
        nottried = cnt.get(NOT_TRIED, 0)
        na = cnt.get(NA, 0)
        nd = cnt.get(NOT_DISCLOSED, 0)
        applicable = len(SLOTS) - na - nd

        pool_rows.append({
            "batch_id": batch_of.get(sid, ""),
            "security_id": sid,
            "stock_code": c["stock_code"],
            "stock_name": c["stock_name"],
            "exchange": c["exchange"],
            "sw_l1": c["sw_l1"],
            "listing_date": listing.get(sid, {}).get("listing_date", ""),
            "listing_date_status": listing.get(sid, {}).get("listing_date_status", "UNKNOWN"),
            "slots_total": len(SLOTS),
            "obtained_verified": verified,
            "pending_identity": pending,
            "source_failed": failed,
            "not_tried": nottried,
            "na_prelisting": na,
            "not_yet_disclosed": nd,
            "missing_slot": cnt.get("MISSING_SLOT", 0),
            "applicable_slots": applicable,
            "obtained_rate_applicable": round(verified / applicable, 4) if applicable else "",
            "obtained_incl_pending": verified + pending,
            "pending_slots": "|".join(s for s in SLOTS if st[s] == PENDING),
            "failed_slots": "|".join(s for s in SLOTS if st[s] == FAILED),
            "not_tried_slots": "|".join(s for s in SLOTS if st[s] == NOT_TRIED),
            "na_slots": "|".join(s for s in SLOTS if st[s] == NA),
            "local_files_present": present,
            "local_files_missing": miss,
            "local_bytes": row_bytes,
            "legacy_data_status": c["data_status"],
            "legacy_listing_date_field": c["listing_date"],
        })

    # checkpoint vs collection_index 交叉核对
    diffs = []
    for sid, cp in cps.items():
        st = slot_status_of(cp.get("slots", {}))
        for s in SLOTS:
            ir = idx.get(sid, {}).get(s)
            if ir is None:
                diffs.append({"security_id": sid, "slot_id": s, "issue": "INDEX_ROW_MISSING"})
            elif ir["status"] != st[s]:
                diffs.append({"security_id": sid, "slot_id": s, "issue": "STATUS_DIFF",
                              "checkpoint": st[s], "index": ir["status"]})

    # 索引里存在但 checkpoint 里没有的公司/槽
    extra_index = sorted({r["security_id"] for r in index_rows} - set(cps))

    return {
        "companies_with_checkpoint": len(cps),
        "companies_missing_checkpoint": sorted(
            {r["security_id"] for r in companies} - set(cps)),
        "index_companies_not_in_checkpoint": extra_index,
        "index_rows": len(index_rows),
        "checkpoint_slots": sum(len(c.get("slots", {})) for c in cps.values()),
        "status_counts": dict(Counter(
            v for c in cps.values() for v in slot_status_of(c.get("slots", {})).values())),
        "checkpoint_index_status_diffs": diffs[:200],
        "checkpoint_index_diff_count": len(diffs),
        "local_files_present": local_ok,
        "local_files_missing": local_missing,
        "local_missing_detail": missing_detail[:100],
        "local_bytes": bytes_total,
        "pool_rows": pool_rows,
    }


# ---------------------------------------------------------------- 字段覆盖
FIELD_MAP = [
    # (canonical_field_id, 中文名, 快照列前缀/None, 判定, 说明)
    ("FIN.REV.YTD", "营业收入（合并，年初至今）", "revenue_cny_", "COVERED",
     "2021—2025 年报 + 2026H1"),
    ("FIN.REV.SQ", "营业收入（合并，单季度）", None, "ABSENT",
     "旧快照无单季营收列；须由年报「分季度主要财务数据」表取"),
    ("FIN.COST.YTD", "营业成本（合并，年初至今）", None, "ABSENT",
     "旧快照无营业成本，毛利率为直接给出值"),
    ("FIN.GROSSPROFIT.YTD", "毛利额（派生）", None, "BLOCKED_BY_RULE",
     "缺营业成本；P04 禁止用毛利率反推，故不可计算"),
    ("FIN.GROSSMARGIN.PCT", "毛利率（%）", "gross_margin_pct_", "COVERED",
     "百分数数值（23.28=23.28%），非小数"),
    ("FIN.NP.YTD", "净利润（合并，累计）", None, "ABSENT", "只有归母口径"),
    ("FIN.NPP.YTD", "归母净利润（累计）", "net_profit_parent_cny_", "COVERED", "2021—2025 + 2026H1"),
    ("FIN.NPP.SQ", "归母净利润（单季度）", None, "ABSENT", "无单季序列"),
    ("FIN.NPDEDT.YTD", "扣非归母净利润（累计）", "deducted_np_parent_cny_", "COVERED",
     "22 期累计，覆盖 2021Q1—2026H1"),
    ("FIN.NPDEDT.SQ", "扣非归母净利润（单季度）", None, "ABSENT",
     "结构化接口无此字段，须回官方 PDF 分季度表"),
    ("FIN.OCF.YTD", "经营活动现金流净额（累计）", None, "ABSENT",
     "旧快照无经营现金流，P04 列为 P00 必需"),
    ("FIN.OCF.SQ", "经营活动现金流净额（单季度）", None, "ABSENT", "同上，且无单季"),
    ("FIN.AR.INSTANT", "应收账款（时点）", None, "ABSENT", "旧快照无应收"),
    ("FIN.NR.INSTANT", "应收票据（时点）", None, "ABSENT", "旧快照无应收票据"),
    ("FIN.CONTRACTASSET.INSTANT", "合同资产（时点）", None, "ABSENT", "旧快照无合同资产"),
    ("FIN.INV.INSTANT", "存货（时点）", None, "ABSENT", "旧快照无存货"),
    ("FIN.ASSET.INSTANT", "资产总计（时点）", None, "ABSENT", "旧快照无资产负债表科目"),
    ("FIN.PERIOD.START", "报告期起始日", None, "DERIVED_FROM_COLUMN",
     "可由列名期间推导（2021→2021-01-01 等）"),
    ("FIN.PERIOD.END", "报告期结束日", None, "DERIVED_FROM_COLUMN", "可由列名期间推导"),
    ("FIN.PUBLISHED_ON", "实际披露日", None, "PARTIAL_NEW",
     "旧快照无；本轮采集已为 7172 槽取得巨潮 published_on，但尚未回写财务表"),
    ("FIN.COLLECTED_AT", "取件日", None, "COVERED", "快照 2026-10-26 生成；本轮原件 2026-10-26/27"),
    ("FIN.AS_OF", "研究截止日", None, "COVERED", "knowledge_as_of=2026-10-25（P00 冻结）"),
    ("FIN.CURRENCY", "币种", None, "ASSUMED_NOT_ROW_SOURCED",
     "4/4 抽样 PDF 表头「币种：人民币」；快照逐行未带币种列"),
    ("FIN.UNIT_SCALE", "金额单位与量纲", None, "ASSUMED_NOT_ROW_SOURCED",
     "4/4 抽样 PDF 表头「单位：元」；快照逐行未带单位列"),
    ("FIN.CONSOLIDATION_SCOPE", "合并范围", None, "ASSUMED_NOT_ROW_SOURCED",
     "按合并口径定义取数，逐行未标注"),
    ("FIN.AUDIT_STATUS", "审计状态", None, "ABSENT", "快照无审计意见列"),
    ("FIN.RESTATEMENT", "重述/版本标记", None, "ABSENT", "快照无重述标记，跨期比较有风险"),
    ("FIN.STATUS", "数据状态码", "data_status", "COVERED", "company_master.data_status 有值"),
    ("FIN.LISTING_DATE", "上市日期", None, "COVERED_NEW",
     "侧表 data/company_listing_dates.csv 已 1054/1054 回填（不改 company_master）"),
    ("FIN.YOY.PCT", "同比增速（派生）", None, "PARTIAL",
     "2022—2025 同比可算；2026H1 同比因缺 2025H1 基数不可算"),
    ("FIN.NPMARGIN.PCT", "归母净利率（派生）", None, "DERIVABLE", "营收与归母均有，可派生"),
    ("FIN.OCF_TO_NP.RATIO", "经营现金流/归母净利", None, "BLOCKED_BY_INPUT", "缺经营现金流"),
    ("FIN.PPCHG.PP", "比率变动（百分点）", None, "DERIVABLE", "毛利率序列齐全，可算 pp 变动"),
]


def check_fields(pool_rows):
    snap = read_csv(SNAPSHOT)
    header = list(snap[0].keys())
    n = len(snap)

    rows = []
    for fid, name, prefix, verdict, note in FIELD_MAP:
        cols = [h for h in header if prefix and h.startswith(prefix)] if prefix else []
        if cols:
            non_null = sum(1 for r in snap for c in cols if (r.get(c) or "").strip() not in ("", "NULL", "NA"))
            expected = n * len(cols)
            cov = round(non_null / expected * 100, 2) if expected else ""
            period_note = f"{len(cols)} 列：{cols[0]} … {cols[-1]}" if len(cols) > 1 else cols[0]
        else:
            non_null, expected, cov, period_note = 0, 0, "", ""
        rows.append({
            "field_id": fid,
            "name_cn": name,
            "verdict": verdict,
            "snapshot_columns": "|".join(cols),
            "column_count": len(cols),
            "expected_cells": expected,
            "non_null_cells": non_null,
            "coverage_pct": cov,
            "period_note": period_note,
            "note": note,
            "p00_required": "YES" if fid in (
                "FIN.REV.YTD", "FIN.REV.SQ", "FIN.COST.YTD", "FIN.NPP.YTD",
                "FIN.NPDEDT.YTD", "FIN.NPDEDT.SQ", "FIN.OCF.YTD", "FIN.AR.INSTANT",
                "FIN.CONTRACTASSET.INSTANT", "FIN.INV.INSTANT", "FIN.PERIOD.START",
                "FIN.PERIOD.END", "FIN.PUBLISHED_ON", "FIN.COLLECTED_AT", "FIN.AS_OF",
                "FIN.CURRENCY", "FIN.UNIT_SCALE", "FIN.CONSOLIDATION_SCOPE",
                "FIN.RESTATEMENT", "FIN.STATUS", "FIN.LISTING_DATE") else "NO",
        })

    # 快照列级覆盖（逐列）
    col_rows = []
    for c in header:
        non_null = sum(1 for r in snap if (r.get(c) or "").strip() not in ("", "NULL", "NA"))
        col_rows.append({
            "field_id": "",
            "name_cn": c,
            "verdict": "SNAPSHOT_COLUMN",
            "snapshot_columns": c,
            "column_count": 1,
            "expected_cells": n,
            "non_null_cells": non_null,
            "coverage_pct": round(non_null / n * 100, 2),
            "period_note": "",
            "note": "",
            "p00_required": "",
        })

    # 市场覆盖
    mkt = Counter(r["exchange"] for r in pool_rows)
    legacy = Counter(r["legacy_data_status"] for r in pool_rows)
    return rows, col_rows, {
        "snapshot_rows": n,
        "snapshot_columns": len(header),
        "snapshot_sha256": sha256_file(SNAPSHOT),
        "market_company_counts": dict(mkt),
        "legacy_data_status_counts": dict(legacy),
    }


# ---------------------------------------------------------------- 完整性交叉核
def check_integrity(cps):
    cfg_path = rp("runs", "issues", "P07", "collection_config_v1.json")
    with open(cfg_path, encoding="utf-8") as f:
        cfg = json.load(f)
    slotmeta = {s["slot_id"]: s for s in cfg["slots"]}
    listing = {r["security_id"]: r for r in read_csv(rp("data", "company_listing_dates.csv"))}
    period_end = {s["slot_id"]: s["period_end"] for s in cfg["slots"]}

    type_mis, period_mis = [], []
    sha_map, doc_map = defaultdict(set), defaultdict(set)
    no_val, reval_bad, firstpass_only = [], [], []
    na_violation, na_companies = [], set()
    not_tried_markets = Counter()

    for sid, d in cps.items():
        for s, rec in d.get("slots", {}).items():
            st = rec.get("status")
            doc = rec.get("document") or {}
            val = (rec.get("validation") or {}).get("checks") or {}
            fp = doc.get("identity_checks") or {}

            if st in (VERIFIED, PENDING):
                if rec.get("report_type") != slotmeta[s]["report_type"]:
                    type_mis.append({"security_id": sid, "slot_id": s})
                if rec.get("period_label") != slotmeta[s]["period_label"]:
                    period_mis.append({"security_id": sid, "slot_id": s})
                if not val:
                    no_val.append({"security_id": sid, "slot_id": s})
                else:
                    vbad = [k for k, v in val.items() if v.get("result") != "PASS"]
                    if vbad:
                        reval_bad.append({"security_id": sid, "slot_id": s,
                                          "status": st, "failed": vbad})
                fbad = [k for k, v in fp.items() if v.get("result") != "PASS"]
                vbad2 = [k for k, v in val.items() if v.get("result") != "PASS"]
                if fbad and not vbad2:
                    firstpass_only.append({"security_id": sid, "slot_id": s,
                                           "first_pass_unknown": fbad})
                if doc.get("sha256"):
                    sha_map[doc["sha256"]].add(sid)
                if doc.get("document_id"):
                    doc_map[doc["document_id"]].add(sid)

            if st == NA:
                na_companies.add(sid)
                L = listing.get(sid, {}).get("listing_date", "")
                if not L or L <= period_end[s]:
                    na_violation.append({"security_id": sid, "slot_id": s,
                                         "listing_date": L, "period_end": period_end[s]})
            if st == NOT_TRIED:
                not_tried_markets[sid.split(":")[0]] += 1

    return {
        "slot_report_type_mismatch": len(type_mis),
        "slot_period_label_mismatch": len(period_mis),
        "slots_without_revalidation_record": len(no_val),
        "revalidation_non_pass": len(reval_bad),
        "revalidation_non_pass_detail": reval_bad,
        "revalidation_non_pass_all_pending": all(x["status"] == PENDING for x in reval_bad),
        "first_pass_unknown_but_revalidated_pass": len(firstpass_only),
        "first_pass_unknown_detail": firstpass_only,
        "first_pass_note": "document.identity_checks 保留首次下载时的结果，未随 P07 复检覆盖；"
                           "权威结论取 validation.checks。属记账不一致，非文件问题。",
        "sha256_shared_across_companies": {k: sorted(v) for k, v in sha_map.items() if len(v) > 1},
        "document_id_shared_across_companies": {k: sorted(v) for k, v in doc_map.items() if len(v) > 1},
        "distinct_sha256": len(sha_map),
        "distinct_document_id": len(doc_map),
        "na_prelisting_slots": sum(1 for d in cps.values() for r in d.get("slots", {}).values()
                                   if r.get("status") == NA),
        "na_prelisting_companies": len(na_companies),
        "na_violating_listing_date_rule": na_violation,
        "not_tried_by_market": dict(not_tried_markets),
        "not_tried_all_bj": set(not_tried_markets) == {"BJ"},
    }


# ---------------------------------------------------------------- 主流程
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--run", action="store_true")
    a = ap.parse_args()
    if not (a.check or a.run):
        ap.error("need --check or --run")

    roster = check_roster()
    roster["verdict"] = "PASS" if (
        roster["master_unique_ids"] == 1054
        and roster["assignment_unique_ids"] == 1054
        and not roster["cross_batch_duplicates"]
        and not roster["missing_vs_master"]
        and not roster["extra_vs_master"]
        and not roster["missing_vs_queue"]
        and not roster["extra_vs_queue"]
        and not roster["queue_batch_mismatch"]
        and roster["batch_counts_match_index"]
    ) else "FAIL"
    index_rows = read_csv(rp("runs", "collection", "collection_index.csv"))
    cps = load_checkpoints()
    slots = check_slots(roster, cps, index_rows)
    pool_rows = slots.pop("pool_rows")
    integrity = check_integrity(cps)
    fields, col_rows, field_meta = check_fields(pool_rows)

    # 汇总
    cnt = slots["status_counts"]
    total = sum(cnt.values())
    verified, pending = cnt.get(VERIFIED, 0), cnt.get(PENDING, 0)
    failed, nottried = cnt.get(FAILED, 0), cnt.get(NOT_TRIED, 0)
    na, nd = cnt.get(NA, 0), cnt.get(NOT_DISCLOSED, 0)
    applicable = total - na - nd

    by_batch = {}
    for b in BATCHES:
        sub = [r for r in pool_rows if r["batch_id"] == b]
        c = Counter()
        for r in sub:
            c["total"] += r["slots_total"]
            c[VERIFIED] += r["obtained_verified"]
            c[PENDING] += r["pending_identity"]
            c[FAILED] += r["source_failed"]
            c[NOT_TRIED] += r["not_tried"]
            c[NA] += r["na_prelisting"]
            c[NOT_DISCLOSED] += r["not_yet_disclosed"]
        app = c["total"] - c[NA] - c[NOT_DISCLOSED]
        by_batch[b] = {
            "companies": len(sub),
            "slots": c["total"],
            "verified": c[VERIFIED],
            "pending_identity": c[PENDING],
            "source_failed": c[FAILED],
            "not_tried": c[NOT_TRIED],
            "na_prelisting": c[NA],
            "not_yet_disclosed": c[NOT_DISCLOSED],
            "applicable": app,
            "obtained": c[VERIFIED],
            "obtained_rate_applicable": round(c[VERIFIED] / app, 4) if app else None,
            "bytes": sum(r["local_bytes"] for r in sub),
        }

    by_market = {}
    for m in ("SZ", "SH", "BJ"):
        sub = [r for r in pool_rows if r["exchange"] == m]
        by_market[m] = {
            "companies": len(sub),
            "slots": sum(r["slots_total"] for r in sub),
            "verified": sum(r["obtained_verified"] for r in sub),
            "pending_identity": sum(r["pending_identity"] for r in sub),
            "source_failed": sum(r["source_failed"] for r in sub),
            "not_tried": sum(r["not_tried"] for r in sub),
            "na_prelisting": sum(r["na_prelisting"] for r in sub),
        }

    # 四类清单
    pending_list = [{"security_id": r["security_id"], "stock_code": r["stock_code"],
                     "stock_name": r["stock_name"], "batch_id": r["batch_id"],
                     "slots": r["pending_slots"]} for r in pool_rows if r["pending_identity"]]
    failed_list = [{"security_id": r["security_id"], "stock_code": r["stock_code"],
                    "stock_name": r["stock_name"], "batch_id": r["batch_id"],
                    "slots": r["failed_slots"]} for r in pool_rows if r["source_failed"]]
    nottried_list = [{"security_id": r["security_id"], "stock_code": r["stock_code"],
                      "stock_name": r["stock_name"], "batch_id": r["batch_id"],
                      "slots": r["not_tried_slots"], "count": r["not_tried"]}
                     for r in pool_rows if r["not_tried"]]
    na_list = [{"security_id": r["security_id"], "stock_code": r["stock_code"],
                "stock_name": r["stock_name"], "listing_date": r["listing_date"],
                "slots": r["na_slots"]} for r in pool_rows if r["na_prelisting"]]

    full_slot_companies = sum(1 for r in pool_rows
                              if r["obtained_verified"] + r["pending_identity"] == r["slots_total"])
    applicable_fully_verified = sum(1 for r in pool_rows
                                    if r["applicable_slots"] > 0
                                    and r["obtained_verified"] == r["applicable_slots"])
    applicable_fully_obtained = sum(1 for r in pool_rows
                                    if r["applicable_slots"] > 0
                                    and r["obtained_verified"] + r["pending_identity"] == r["applicable_slots"])
    real_gap_companies = [r["security_id"] for r in pool_rows
                          if r["obtained_verified"] + r["pending_identity"] < r["applicable_slots"]]
    zero_applicable = [r["security_id"] for r in pool_rows if r["applicable_slots"] == 0]

    recon = {
        "issue": "A00",
        "issue_number": 30,
        "plan_version": "20261026_collection_first_v2",
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "knowledge_as_of": "2026-10-25",
        "scope": "全池 1054 家 × 7 资料槽 = 7378 槽；只做覆盖与完整性聚合，不按投资价值筛选",
        "roster": {
            "master_rows": roster["master_rows"],
            "master_unique_ids": roster["master_unique_ids"],
            "master_unique_codes": roster["master_unique_codes"],
            "assignment_total_rows": roster["assignment_total_rows"],
            "assignment_unique_ids": roster["assignment_unique_ids"],
            "queue_rows": roster["queue_rows"],
            "index_batches": roster["index_batches"],
            "index_total_companies": roster["index_total_companies"],
            "cross_batch_duplicates": roster["cross_batch_duplicates"],
            "missing_vs_master": roster["missing_vs_master"],
            "extra_vs_master": roster["extra_vs_master"],
            "missing_vs_queue": roster["missing_vs_queue"],
            "extra_vs_queue": roster["extra_vs_queue"],
            "queue_batch_mismatch": roster["queue_batch_mismatch"],
            "master_dup_ids": roster["master_dup_ids"],
            "batch_counts_match_index": roster["batch_counts_match_index"],
            "per_batch": roster["per_batch"],
            "verdict": roster["verdict"],
        },
        "slots": {
            "total": total,
            "expected_total": 1054 * 7,
            "applicable": applicable,
            "verified": verified,
            "pending_identity": pending,
            "source_failed": failed,
            "not_tried": nottried,
            "na_prelisting": na,
            "not_yet_disclosed": nd,
            "missing_slot": cnt.get("MISSING_SLOT", 0),
            "obtained_rate_applicable": round(verified / applicable, 4) if applicable else None,
            "obtained_incl_pending_rate": round((verified + pending) / applicable, 4) if applicable else None,
            "obtained_rate_total": round(verified / total, 4) if total else None,
            "obtained_incl_pending": verified + pending,
            "companies_with_checkpoint": slots["companies_with_checkpoint"],
            "companies_missing_checkpoint": slots["companies_missing_checkpoint"],
            "index_rows": slots["index_rows"],
            "checkpoint_slots": slots["checkpoint_slots"],
            "checkpoint_index_diff_count": slots["checkpoint_index_diff_count"],
            "checkpoint_index_status_diffs": slots["checkpoint_index_status_diffs"],
            "local_files_present": slots["local_files_present"],
            "local_files_missing": slots["local_files_missing"],
            "local_missing_detail": slots["local_missing_detail"],
            "local_bytes": slots["local_bytes"],
            "local_gib": round(slots["local_bytes"] / 1024 ** 3, 2),
            "full_slot_companies": full_slot_companies,
            "applicable_fully_verified_companies": applicable_fully_verified,
            "applicable_fully_obtained_companies": applicable_fully_obtained,
            "real_gap_companies": real_gap_companies,
            "real_gap_company_count": len(real_gap_companies),
            "zero_applicable_companies": zero_applicable,
            "zero_applicable_count": len(zero_applicable),
        },
        "by_batch": by_batch,
        "by_market": by_market,
        "integrity": integrity,
        "gaps": {
            "pending_identity": pending_list,
            "source_failed": failed_list,
            "not_tried": nottried_list,
            "na_prelisting_count": len(na_list),
            "na_prelisting": na_list,
        },
        "fields": {
            "snapshot_rows": field_meta["snapshot_rows"],
            "snapshot_columns": field_meta["snapshot_columns"],
            "snapshot_sha256": field_meta["snapshot_sha256"],
            "market_company_counts": field_meta["market_company_counts"],
            "legacy_data_status_counts": field_meta["legacy_data_status_counts"],
            "p00_required_missing": [r["field_id"] for r in fields
                                     if r["p00_required"] == "YES"
                                     and r["verdict"] in ("ABSENT", "BLOCKED_BY_INPUT", "BLOCKED_BY_RULE")],
            "verdict_counts": dict(Counter(r["verdict"] for r in fields)),
        },
        "archive": {
            "drive_status": "ACCESS_BLOCKED_IN_CURRENT_SESSION",
            "note": "P07 归档 65 份由 Codex 完成并有回执；本会话无 Drive 连接器，未做任何上传/回读，归档态不得写 VERIFIED",
        },
        "acceptance": {
            "A1_batches_checkable_1054_no_dup": None,
            "A2_not_tried_kept_incomplete": nottried > 0,
        },
        "global_source_failures": [
            {"type": "SIZE_LIMIT", "slots": failed,
             "detail": "transport.max_download_bytes=80MB 挡住 301622 英思特 annual_2025（87.3MB），非发行人未披露"},
            {"type": "NEEQ_PLATFORM_GAP", "slots": nottried,
             "detail": "北交所 65 槽落在股转挂牌期，需 8xxxxx 代码映射；平台不同不等于不适用"},
        ],
    }
    recon["acceptance"]["A1_batches_checkable_1054_no_dup"] = roster["verdict"] == "PASS"

    print("== roster ==", json.dumps({k: v for k, v in recon["roster"].items()
                                      if k not in ("per_batch",)}, ensure_ascii=False)[:800])
    print("== slots ==", verified, pending, failed, nottried, na, "total", total, "applicable", applicable)
    print("== local ==", slots["local_files_present"], "present /", slots["local_files_missing"],
          "missing /", recon["slots"]["local_gib"], "GiB")
    print("== diffs ==", slots["checkpoint_index_diff_count"])
    print("== integrity ==", json.dumps({k: v for k, v in integrity.items()
                                         if k not in ("first_pass_unknown_detail",
                                                      "revalidation_non_pass_detail")},
                                        ensure_ascii=False)[:900])
    print("== fields ==", recon["fields"]["verdict_counts"])
    print("== p00 missing ==", recon["fields"]["p00_required_missing"])

    if a.check:
        return

    os.makedirs(OUT, exist_ok=True)
    write_csv(os.path.join(OUT, "all_pool_coverage.csv"), pool_rows,
              ["batch_id", "security_id", "stock_code", "stock_name", "exchange", "sw_l1",
               "listing_date", "listing_date_status", "slots_total", "obtained_verified",
               "pending_identity", "source_failed", "not_tried", "na_prelisting",
               "not_yet_disclosed", "missing_slot", "applicable_slots",
               "obtained_rate_applicable", "obtained_incl_pending", "pending_slots",
               "failed_slots", "not_tried_slots", "na_slots", "local_files_present",
               "local_files_missing", "local_bytes", "legacy_data_status",
               "legacy_listing_date_field"])
    write_csv(os.path.join(OUT, "all_field_coverage.csv"), fields + col_rows,
              ["field_id", "name_cn", "verdict", "snapshot_columns", "column_count",
               "expected_cells", "non_null_cells", "coverage_pct", "period_note",
               "note", "p00_required"])
    with open(os.path.join(OUT, "coverage_reconciliation.json"), "w", encoding="utf-8") as f:
        json.dump(recon, f, ensure_ascii=False, indent=2)
    print("written to", OUT)


if __name__ == "__main__":
    sys.exit(main())
