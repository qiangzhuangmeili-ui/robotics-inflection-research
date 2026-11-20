#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""S05 公司层面质量检查构建（#40 / S05，冻结输入 V2.2）。

范围：278 家受限候选（S04 tight_pass 精确主键集合），五个指标
M04 / M08 / M10 / M11 / M12，外加冻结有效信号的 L3 依赖与低基数来源依赖。

纪律：
  * 阈值不在此声明。Q10 两支门槛与零基数下限从
    runs/issues/S04/workbuddy_handoff_20261119/v2_2_20261120/s05_ca_source_rule.py 导入；
    RH01-RH06 门槛从冻结规则文件 screen_rules_v3_provenance_20261114.json 读取。
  * days_in_period 由 B 的 period_start/period_end 求得，不按 365 硬编码。
  * 合同资产采用值必须同时绑定 期间 + 合并资产负债表 + 合同资产行 + 期末列；
    三格错列/错表由 s05_ca_source_rule.NON_ADMISSIBLE_INDEX 隔离，不补零、不推定。
  * 不新增派工、不改冻结阈值、不改 B、不改旧验收。
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
import sys
from collections import Counter, defaultdict
from datetime import date, datetime
from decimal import Decimal, getcontext
from pathlib import Path

getcontext().prec = 34

# ---------------------------------------------------------------- 路径

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
V22 = REPO / "runs/issues/S04/workbuddy_handoff_20261119/v2_2_20261120"
REVIEWED = REPO / "runs/issues/S04/completion_20261114/final_delivery_20261116/reviewed_view"
RULES_PATH = REPO / "runs/issues/S01/screen_rules_v3_provenance_20261114.json"
FROZEN_B = REPO / "runs/issues/S02/hangcha_restated_20261101/s00_v10/s00_v10.csv.gz"
RELEASE = REPO / "runs/issues/S05/release_20261120.json"

sys.path.insert(0, str(V22))
from s05_ca_source_rule import (  # noqa: E402
    CA_NO_USABLE_BASES,
    CA_USABLE_BASES,
    NON_ADMISSIBLE_CA,
    NON_ADMISSIBLE_INDEX,
    Q10_ASSET_PCT,
    Q10_REV_PCT,
    ZERO_BASE_FLOOR,
)

# ---------------------------------------------------------------- 常量

D = Decimal
ZERO = D("0")
HUNDRED = D("100")

METRICS = ("M04", "M08", "M10", "M11", "M12")
METRIC_RH = {"M04": "RH05", "M08": "RH04", "M10": "RH01", "M11": "RH02", "M12": "RH03"}
METRIC_UNIT = {"M04": "pp", "M08": "ratio", "M10": "days", "M11": "days", "M12": "pp"}

SIGNAL_DIMENSION = {
    "SG01": "GROWTH", "SG02": "GROWTH", "SG03": "MARGIN",
    "SG04": "PROFIT", "SG05": "PROFIT", "SG06": "PROFIT",
    "SG07": "CASH", "SG08": "CASH", "SG09": "PROFIT",
}
SIGNAL_METRIC = {
    "SG01": "M01", "SG02": "M03", "SG03": "M04", "SG04": "M05",
    "SG05": "M06", "SG06": "M05", "SG07": "M08", "SG08": "M09", "SG09": "M07",
}

# 判定 -> (metric_status, 质量标记)
VERDICT_STATUS = {
    "APPLICABLE": "OK",
    "NOT_APPLICABLE_PROJECT_MODE": "NOT_APPLICABLE_PROJECT_MODE",
    "NOT_APPLICABLE_NEGATIVE_DENOMINATOR": "NOT_APPLICABLE_NEGATIVE_DENOMINATOR",
    "NOT_APPLICABLE_ZERO_BASE_FLOOR": "NOT_APPLICABLE_ZERO_BASE_FLOOR",
    "HOLD_DECISIVE_CELL_PENDING": "HOLD_DECISIVE_CELL_PENDING",
    "UNKNOWN_INPUT_MISSING": "UNKNOWN_INPUT_MISSING",
    "UNKNOWN_INPUT_UNREADABLE": "UNKNOWN_INPUT_UNREADABLE",
    "UNKNOWN_CA_BLANK": "UNKNOWN_CA_BLANK",
    "UNKNOWN_CA_SOURCE_NOT_ADMISSIBLE": "UNKNOWN_CA_SOURCE_NOT_ADMISSIBLE",
    "BOTH_BLANK_NO_USABLE_AMOUNT": "BOTH_BLANK_NO_USABLE_AMOUNT",
    "SINGLE_SIDED_GAP": "SINGLE_SIDED_GAP",
}

# metric_status -> 质量标记集合
STATUS_FLAGS = {
    "OK": (),
    "NOT_APPLICABLE_PROJECT_MODE": (),
    "NOT_APPLICABLE_NEGATIVE_DENOMINATOR": ("Q03",),
    "NOT_APPLICABLE_ZERO_BASE_FLOOR": ("Q04",),
    "HOLD_DECISIVE_CELL_PENDING": ("Q01",),
    "UNKNOWN_INPUT_MISSING": ("Q02",),
    "UNKNOWN_INPUT_UNREADABLE": ("Q02",),
    "UNKNOWN_CA_BLANK": ("Q02",),
    "UNKNOWN_CA_SOURCE_NOT_ADMISSIBLE": ("Q01",),
    "BOTH_BLANK_NO_USABLE_AMOUNT": ("Q02",),
    "SINGLE_SIDED_GAP": ("Q02",),
}

HOLD_STATUSES = {
    "HOLD_DECISIVE_CELL_PENDING",
    "UNKNOWN_CA_SOURCE_NOT_ADMISSIBLE",
}
PENDING_STATUSES = {
    "UNKNOWN_INPUT_MISSING",
    "UNKNOWN_INPUT_UNREADABLE",
    "UNKNOWN_CA_BLANK",
    "BOTH_BLANK_NO_USABLE_AMOUNT",
    "SINGLE_SIDED_GAP",
}
USABLE_B = {
    "EXTRACTED", "EXTRACTED_KEY_TABLE", "EXTRACTED_QUARTERLY_TABLE",
    "DERIVED", "DERIVED_CUMULATIVE_DIFF", "DERIVED_Q1_EQUALS_YTD",
    "DERIVED_QUARTERLY_SUM_OVERRIDE", "LEGACY_SNAPSHOT",
}
HOLD_B = {"EXTRACTED_XCHECK_MISMATCH", "DERIVED_HOLD_UPSTREAM", "DERIVED_Q1_HOLD_UPSTREAM"}


# ---------------------------------------------------------------- 工具

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_csv(path: Path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def dec(text, default=None):
    if text is None:
        return default
    s = str(text).strip().replace(",", "")
    if s == "" or s.lower() in {"nan", "none", "null"}:
        return default
    try:
        return D(s)
    except Exception:
        return default


def q(value, places="0.000001"):
    if value is None:
        return ""
    return str(value.quantize(D(places)))


def load_rules():
    with open(RULES_PATH, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------- B 索引

NEEDED_FIELDS = {
    "FIN.REV.YTD", "FIN.COST.YTD", "FIN.AR.INSTANT", "FIN.INV.INSTANT",
    "FIN.NPP.YTD", "FIN.NPDEDT.YTD", "FIN.OCF.YTD",
    "FIN.CONTRACTASSET.INSTANT", "FIN.ASSET.INSTANT", "FIN.GROSSMARGIN.PCT",
}


def build_b_index(targets):
    """targets: set of (security_id, period_key). 返回 {(sid,field,period): row}。"""
    index = {}
    with gzip.open(FROZEN_B, "rt", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            key = (row["security_id"], row["period_key"])
            if key not in targets:
                continue
            if row["field_id"] not in NEEDED_FIELDS:
                continue
            index[(row["security_id"], row["field_id"], row["period_key"])] = row
    return index


def days_between(row):
    if not row:
        return None
    ps, pe = row.get("period_start"), row.get("period_end")
    if not ps or not pe:
        return None
    try:
        return (date.fromisoformat(pe) - date.fromisoformat(ps)).days + 1
    except Exception:
        return None


def cell(index, sid, field, period):
    return index.get((sid, field, period))


def cell_value(index, sid, field, period):
    row = cell(index, sid, field, period)
    if not row:
        return None, None
    return dec(row.get("value_cny")), row


# ---------------------------------------------------------------- 主流程

def main():
    rules = load_rules()
    rh_rules = {h["id"]: h for h in rules["risk_hints"]}
    low_base_threshold = D(str(rules["low_base_confirmation"]["threshold_cny"]))
    # Q05 门槛来自冻结 quality_flags Q05 定义（基期营收<5,000 万 或 |基期扣非|<1,000 万）
    Q05_REV_FLOOR = D("50000000")
    Q05_NPDEDT_FLOOR = low_base_threshold

    pool = read_csv(REVIEWED / "tight_pass.csv")
    observe_pool = read_csv(REVIEWED / "tight_observe.csv")
    applicability = read_csv(V22 / "s05_applicability_v22.csv")
    eligibility = read_csv(V22 / "s05_source_eligibility_v22.csv")
    pending = read_csv(V22 / "s05_pending_isolation_v22.csv")
    nonadmit = read_csv(V22 / "s05_ca_source_nonadmission_v22.csv")
    both_blank = read_csv(V22 / "s05_rh03_both_blank_v22.csv")
    single_sided = read_csv(V22 / "s05_rh03_single_sided_v22.csv")
    q10_unknown = read_csv(V22 / "s05_q10_unknown_v22.csv")

    assert len(pool) == 278, len(pool)
    assert len(observe_pool) == 776, len(observe_pool)

    # --- 索引
    app = {(r["security_id"], r["metric_id"]): r for r in applicability}
    assert len(app) == 278 * 5, len(app)

    elig = defaultdict(list)
    for r in eligibility:
        elig[(r["security_id"], r["metric_id"])].append(r)

    pend_by_company = defaultdict(list)
    for r in pending:
        pend_by_company[r["security_id"]].append(r)

    nonadmit_keys = {(r["security_id"], r["field_id"], r["period_key"]) for r in nonadmit}
    both_blank_set = {r["security_id"] for r in both_blank}
    single_sided_map = {r["security_id"]: r for r in single_sided}
    q10_unknown_map = {r["security_id"]: r for r in q10_unknown}

    # --- B 索引
    targets = set()
    for r in pool:
        sid, ap = r["security_id"], r["anchor_period"]
        targets.add((sid, ap))
        targets.add((sid, str(int(ap) - 10000)))
    b_index = build_b_index(targets)

    # --- 逐公司
    flag_rows = []
    decision_rows = []
    source_rows = []
    oor_rows = []
    dim_after = {}
    checks = []

    for r in pool:
        sid = r["security_id"]
        name = r["stock_name"]
        ap = r["anchor_period"]
        ap1 = str(int(ap) - 10000)

        days_t = days_between(cell(b_index, sid, "FIN.REV.YTD", ap))
        days_t1 = days_between(cell(b_index, sid, "FIN.REV.YTD", ap1))
        if days_t is None:
            # 回退：用任一存在的行取期间长度
            for f in NEEDED_FIELDS:
                days_t = days_between(cell(b_index, sid, f, ap))
                if days_t is not None:
                    break
        if days_t1 is None:
            for f in NEEDED_FIELDS:
                days_t1 = days_between(cell(b_index, sid, f, ap1))
                if days_t1 is not None:
                    break

        # 基础量
        rev_t, rev_t_row = cell_value(b_index, sid, "FIN.REV.YTD", ap)
        rev_1, rev_1_row = cell_value(b_index, sid, "FIN.REV.YTD", ap1)
        cost_t, cost_t_row = cell_value(b_index, sid, "FIN.COST.YTD", ap)
        cost_1, cost_1_row = cell_value(b_index, sid, "FIN.COST.YTD", ap1)
        ar_t, ar_t_row = cell_value(b_index, sid, "FIN.AR.INSTANT", ap)
        ar_1, ar_1_row = cell_value(b_index, sid, "FIN.AR.INSTANT", ap1)
        inv_t, inv_t_row = cell_value(b_index, sid, "FIN.INV.INSTANT", ap)
        inv_1, inv_1_row = cell_value(b_index, sid, "FIN.INV.INSTANT", ap1)
        npp_t, npp_t_row = cell_value(b_index, sid, "FIN.NPP.YTD", ap)
        npd_t, npd_t_row = cell_value(b_index, sid, "FIN.NPDEDT.YTD", ap)
        npd_1, npd_1_row = cell_value(b_index, sid, "FIN.NPDEDT.YTD", ap1)
        ocf_t, ocf_t_row = cell_value(b_index, sid, "FIN.OCF.YTD", ap)
        ca_t, ca_t_row = cell_value(b_index, sid, "FIN.CONTRACTASSET.INSTANT", ap)
        ca_1, ca_1_row = cell_value(b_index, sid, "FIN.CONTRACTASSET.INSTANT", ap1)
        gm_t, gm_t_row = cell_value(b_index, sid, "FIN.GROSSMARGIN.PCT", ap)
        gm_1, gm_1_row = cell_value(b_index, sid, "FIN.GROSSMARGIN.PCT", ap1)
        asset_t, asset_t_row = cell_value(b_index, sid, "FIN.ASSET.INSTANT", ap)

        # 合同资产来源准入：三格错列/错表一律不采用
        ca_t_admissible = True
        ca_1_admissible = True
        for row in (ca_t_row, ca_1_row):
            if row is None:
                continue
            key = (sid, "FIN.CONTRACTASSET.INSTANT", row["period_key"])
            if key in nonadmit_keys:
                sha = (row.get("document_id") or "")
                rec = NON_ADMISSIBLE_INDEX.get(
                    (sid, "FIN.CONTRACTASSET.INSTANT", row["period_key"], sha)
                )
                if rec is not None or key in nonadmit_keys:
                    if row["period_key"] == ap:
                        ca_t_admissible = False
                    else:
                        ca_1_admissible = False

        # --- 五个指标
        metric = {}
        for mid in METRICS:
            a = app.get((sid, mid))
            verdict = a["verdict"] if a else "UNKNOWN_INPUT_MISSING"
            status = VERDICT_STATUS.get(verdict, "UNKNOWN_INPUT_MISSING")
            value = None
            note = a["reason"] if a else "适用性行缺失"

            if status == "OK":
                if mid == "M04":
                    g_t = gm_t if gm_t is not None else (
                        (rev_t - cost_t) / rev_t * HUNDRED if rev_t and cost_t is not None and rev_t > 0 else None
                    )
                    g_1 = gm_1 if gm_1 is not None else (
                        (rev_1 - cost_1) / rev_1 * HUNDRED if rev_1 and cost_1 is not None and rev_1 > 0 else None
                    )
                    if g_t is None or g_1 is None:
                        status = "UNKNOWN_INPUT_MISSING"
                    else:
                        value = g_t - g_1
                elif mid == "M08":
                    if ocf_t is None or npp_t is None:
                        status = "UNKNOWN_INPUT_MISSING"
                    elif npp_t <= ZERO:
                        status = "NOT_APPLICABLE_NEGATIVE_DENOMINATOR"
                    elif abs(npp_t) < ZERO_BASE_FLOOR:
                        status = "NOT_APPLICABLE_ZERO_BASE_FLOOR"
                    else:
                        value = ocf_t / npp_t
                elif mid == "M10":
                    if None in (ar_t, ar_1, rev_t, rev_1) or days_t is None or days_t1 is None:
                        status = "UNKNOWN_INPUT_MISSING"
                    elif rev_t <= ZERO or rev_1 <= ZERO:
                        status = "NOT_APPLICABLE_NEGATIVE_DENOMINATOR"
                    elif abs(rev_t) < ZERO_BASE_FLOOR or abs(rev_1) < ZERO_BASE_FLOOR:
                        status = "NOT_APPLICABLE_ZERO_BASE_FLOOR"
                    else:
                        value = (ar_t / rev_t * D(days_t)) - (ar_1 / rev_1 * D(days_t1))
                elif mid == "M11":
                    if None in (inv_t, inv_1, cost_t, cost_1) or days_t is None or days_t1 is None:
                        status = "UNKNOWN_INPUT_MISSING"
                    elif cost_t <= ZERO or cost_1 <= ZERO:
                        status = "NOT_APPLICABLE_NEGATIVE_DENOMINATOR"
                    elif abs(cost_t) < ZERO_BASE_FLOOR or abs(cost_1) < ZERO_BASE_FLOOR:
                        status = "NOT_APPLICABLE_ZERO_BASE_FLOOR"
                    else:
                        value = (inv_t / cost_t * D(days_t)) - (inv_1 / cost_1 * D(days_t1))
                elif mid == "M12":
                    if not ca_t_admissible or not ca_1_admissible:
                        status = "UNKNOWN_CA_SOURCE_NOT_ADMISSIBLE"
                    elif None in (ca_t, ca_1, rev_t, rev_1):
                        status = "UNKNOWN_INPUT_MISSING"
                    elif rev_t <= ZERO or rev_1 <= ZERO:
                        status = "NOT_APPLICABLE_NEGATIVE_DENOMINATOR"
                    elif abs(rev_t) < ZERO_BASE_FLOOR or abs(rev_1) < ZERO_BASE_FLOOR:
                        status = "NOT_APPLICABLE_ZERO_BASE_FLOOR"
                    else:
                        value = (ca_t / rev_t * HUNDRED) - (ca_1 / rev_1 * HUNDRED)

            # 证据链
            cells = elig.get((sid, mid), [])
            l3 = "YES" if cells and all(c["l3_evidence_ok"] == "YES" for c in cells) else ("NO" if cells else "NO_INPUT")
            modes = {c["page_evidence_mode"] for c in cells}
            mode = "DIRECT" if modes == {"DIRECT"} else ("VIA_PARENT" if "VIA_PARENT" in modes else (sorted(modes)[0] if modes else "NONE"))
            docs = sorted({c["document_id"] for c in cells if c["document_id"]})
            pages = sorted({c["source_page"] for c in cells if c["source_page"]})
            parents = sorted({c["page_evidence_parents"] for c in cells if c["page_evidence_parents"]})
            parent_pages = sorted(
                {p for c in cells for p in (c["rev_source_page"], c["cost_source_page"]) if p}
            )
            use_classes = sorted({c["actual_use_eligibility"] for c in cells if c["actual_use_eligibility"]})

            # 质量标记
            flags = set(STATUS_FLAGS.get(status, ()))
            if status == "OK":
                if value is not None and mid == "M04" and rev_t is not None and rev_1 is not None:
                    if abs(rev_1) < Q05_REV_FLOOR:
                        flags.add("Q05")
            # 低基数（公司级，另算）
            metric[mid] = {
                "status": status,
                "value": value,
                "note": note,
                "l3": l3,
                "mode": mode,
                "docs": docs,
                "pages": pages,
                "parents": parents,
                "parent_pages": parent_pages,
                "use_classes": use_classes,
                "cells": cells,
                "flags": flags,
            }

            # 来源资格行
            for c in cells:
                adopted = c["actual_use_eligibility"] == "ELIGIBLE_FOR_S05_USE"
                source_rows.append({
                    "security_id": sid,
                    "stock_name": name,
                    "anchor_period": ap,
                    "metric_id": mid,
                    "field_id": c["field_id"],
                    "period_key": c["period_key"],
                    "period_role": c["period_role"],
                    "value_cny": c["value_cny"],
                    "actual_status": c["actual_status"],
                    "document_id": c["document_id"],
                    "source_page": c["source_page"],
                    "page_evidence_mode": c["page_evidence_mode"],
                    "page_evidence_parents": c["page_evidence_parents"],
                    "parent_document_id": ";".join(
                        sorted({x for x in (c["rev_document_id"], c["cost_document_id"]) if x})
                    ),
                    "parent_source_page": ";".join(
                        sorted({x for x in (c["rev_source_page"], c["cost_source_page"]) if x})
                    ),
                    "consolidation_scope": c["consolidation_scope"],
                    "currency": c["currency"],
                    "restatement_flag": c["restatement_flag"],
                    "l3_evidence_ok": c["l3_evidence_ok"],
                    "actual_use_eligibility": c["actual_use_eligibility"],
                    "adopted": "YES" if adopted else "NO",
                    "adoption_reason": "" if adopted else c["blocking_reason"] or c["actual_use_eligibility"],
                })

        # --- 公司级质量标记
        qflags = set()
        for mid in METRICS:
            qflags |= metric[mid]["flags"]
        # Q06 重述
        if any(c["restatement_flag"] == "RESTATEMENT_INDICATED_NEEDS_REVIEW"
               for mid in METRICS for c in metric[mid]["cells"]):
            qflags.add("Q06")
        # Q07 旧快照
        if any(c["actual_status"] == "LEGACY_SNAPSHOT"
               for mid in METRICS for c in metric[mid]["cells"]):
            qflags.add("Q07")
        # Q08 上市前 / 无上年同期
        pre_listing = any(
            (row or {}).get("is_pre_listing") == "YES"
            for row in (rev_1_row, cost_1_row, ar_1_row)
        )
        if pre_listing or rev_1 is None:
            qflags.add("Q08")
        # Q09 一次性损益主导
        one_off = False
        if npp_t is not None and npd_t is not None:
            denom = max(abs(npp_t), D("1"))
            if abs(npp_t - npd_t) / denom > D("0.5"):
                one_off = True
                qflags.add("Q09")
        # Q10 项目制
        q10v = (app.get((sid, "M11")) or {}).get("q10_verdict", "")
        if q10v == "PROJECT_MODE":
            qflags.add("Q10")
        # Q11 陈旧期
        if r.get("stale_period") == "YES":
            qflags.add("Q11")
        # Q12 非合并口径
        if any(c["consolidation_scope"] not in ("CONSOLIDATED", "")
               for mid in METRICS for c in metric[mid]["cells"]):
            qflags.add("Q12")
        # 低基数（基期营收<5,000 万 或 |基期扣非|<1,000 万）
        if rev_1 is not None and abs(rev_1) < Q05_REV_FLOOR:
            qflags.add("Q05")
        if npd_1 is not None and abs(npd_1) < Q05_NPDEDT_FLOOR:
            qflags.add("Q05")

        # --- RH 判定（状态族由 V2.2 冻结映射给出：可判 / 不适用 / 单边缺口 / 待核）
        rh_out = {}
        for mid in METRICS:
            h = rh_rules[METRIC_RH[mid]]
            st = metric[mid]["status"]
            val = metric[mid]["value"]
            family = (app.get((sid, mid)) or {}).get("state_family", "")
            if family == "可判" and st == "OK" and val is not None:
                op, thr = h["operator"], D(str(h["threshold"]))
                hit = (val >= thr) if op == ">=" else (val < thr)
                rh_out[METRIC_RH[mid]] = "TRIGGERED" if hit else "NOT_TRIGGERED"
            elif family == "不适用":
                rh_out[METRIC_RH[mid]] = "NOT_APPLICABLE"
            elif family == "单边缺口":
                rh_out[METRIC_RH[mid]] = "PENDING_SINGLE_SIDED"
            elif st in HOLD_STATUSES:
                rh_out[METRIC_RH[mid]] = "PENDING_HOLD"
            elif family == "待核" or st in PENDING_STATUSES:
                rh_out[METRIC_RH[mid]] = "PENDING_APPLICABILITY"
            else:
                rh_out[METRIC_RH[mid]] = "NOT_APPLICABLE"
        rh_out["RH06"] = "TRIGGERED" if one_off else "NOT_TRIGGERED"

        # --- 维度存活：待核隔离里明确 blocked_signal_ids 的才撤信号
        qualified = [s for s in (r.get("qualified_signal_ids") or "").split(";") if s]
        withdrawn = set()
        for p in pend_by_company.get(sid, []):
            for s in (p.get("blocked_signal_ids") or "").split(";"):
                if s:
                    withdrawn.add(s)
        surviving = [s for s in qualified if s not in withdrawn]
        dims_before = {SIGNAL_DIMENSION[s] for s in qualified}
        dims_after = {SIGNAL_DIMENSION[s] for s in surviving}
        dim_after[sid] = len(dims_after)

        # --- L3 闸门：仅对"决定性"指标（存活信号所用指标）施加
        decisive_metrics = {SIGNAL_METRIC[s] for s in surviving}
        l3_fail = []
        for mid in METRICS:
            if mid in decisive_metrics and metric[mid]["l3"] != "YES":
                l3_fail.append(mid)
        # 五指标外的决定性指标（M01/M03/M05/M06/M07/M09）只看待核隔离
        extra_block = [
            p for p in pend_by_company.get(sid, [])
            if any(s in withdrawn for s in (p.get("blocked_signal_ids") or "").split(";") if s)
        ]

        if len(dims_after) >= 2 and not l3_fail:
            decision = "QUALITY_PASS"
            reason = (
                f"撤维后仍有 {len(dims_after)} 个维度（{';'.join(sorted(dims_after))}）"
                "由冻结合格信号支持，决定性指标证据链完整"
            )
        else:
            decision = "QUALITY_HOLD"
            bits = []
            if len(dims_after) < 2:
                bits.append(
                    f"撤维后仅剩 {len(dims_after)} 个维度（{';'.join(sorted(dims_after)) or '无'}）"
                )
                if withdrawn:
                    bits.append("撤下信号 " + ";".join(sorted(withdrawn)))
            if l3_fail:
                bits.append("决定性指标缺证据 " + ";".join(l3_fail))
            prov_dims = {x for x in (r.get("provisional_dimensions") or "").split(";") if x}
            if dims_after and dims_after <= prov_dims:
                bits.append("存活维度在 S04 即标 PROVISIONAL（" + ";".join(sorted(dims_after)) + "）")
            reason = "；".join(bits)

        # --- 超冻结 valid_range 的观测（冻结文件未给处置规则，只登记不阻断）
        vr = {"M04": (D("-100"), D("100")), "M08": (D("-10"), D("10")),
              "M10": (D("-365"), D("3650")), "M11": (D("-365"), D("3650")), "M12": (D("-100"), D("500"))}
        observations = []
        for mid in METRICS:
            v = metric[mid]["value"]
            if v is None:
                continue
            lo, hi = vr[mid]
            if v < lo or v > hi:
                observations.append(f"OUT_OF_VALID_RANGE:{mid}")
                oor_rows.append({
                    "security_id": sid,
                    "stock_name": name,
                    "anchor_period": ap,
                    "metric_id": mid,
                    "value": q(v),
                    "valid_range": f"[{lo}, {hi}]",
                    "metric_status": metric[mid]["status"],
                    "note": "冻结规则未给 valid_range 处置动作；只登记，不阻断、不改值",
                })

        decision_rows.append({
            "security_id": sid,
            "stock_name": name,
            "anchor_period": ap,
            "pool_role": "PRIMARY_CHECK_POOL",
            "qualified_signal_ids": r.get("qualified_signal_ids", ""),
            "qualified_dimensions": r.get("qualified_dimensions", ""),
            "dimension_count_before": len(dims_before),
            "withdrawn_signals": ";".join(sorted(withdrawn)),
            "dimension_count_after": len(dims_after),
            "surviving_dimensions": ";".join(sorted(dims_after)),
            "s04_provisional_dimensions": r.get("provisional_dimensions", ""),
            "s04_upstream_hold_dimensions": r.get("upstream_hold_dimensions", ""),
            "m04_status": metric["M04"]["status"],
            "m08_status": metric["M08"]["status"],
            "m10_status": metric["M10"]["status"],
            "m11_status": metric["M11"]["status"],
            "m12_status": metric["M12"]["status"],
            "m04_value": q(metric["M04"]["value"]),
            "m08_value": q(metric["M08"]["value"]),
            "m10_value": q(metric["M10"]["value"]),
            "m11_value": q(metric["M11"]["value"]),
            "m12_value": q(metric["M12"]["value"]),
            "quality_flags": ";".join(sorted(qflags)),
            "s05_observations": ";".join(observations),
            "rh_triggered": ";".join(k for k, v in sorted(rh_out.items()) if v == "TRIGGERED"),
            "rh_pending": ";".join(k for k, v in sorted(rh_out.items()) if v.startswith("PENDING")),
            "rh_not_applicable": ";".join(k for k, v in sorted(rh_out.items()) if v == "NOT_APPLICABLE"),
            "l3_gate_result": "EVIDENCE_OK" if not l3_fail else "EVIDENCE_HOLD",
            "decision": decision,
            "decision_reason": reason,
            "s04_l2_decision": r.get("l2_decision", ""),
            "limitations": r.get("limitations", ""),
            "q10_verdict": q10v,
            "one_off": "YES" if one_off else "NO",
        })

        for mid in METRICS:
            m = metric[mid]
            flag_rows.append({
                "security_id": sid,
                "stock_name": name,
                "anchor_period": ap,
                "metric_id": mid,
                "rh": METRIC_RH[mid],
                "applicability_verdict": (app.get((sid, mid)) or {}).get("verdict", ""),
                "state_family": (app.get((sid, mid)) or {}).get("state_family", ""),
                "metric_status": m["status"],
                "metric_value": q(m["value"]),
                "metric_unit": METRIC_UNIT[mid],
                "quality_flags": ";".join(sorted(m["flags"])),
                "rh_status": rh_out[METRIC_RH[mid]],
                "l3_evidence_ok": m["l3"],
                "page_evidence_mode": m["mode"],
                "evidence_document_ids": ";".join(m["docs"]),
                "evidence_pages": ";".join(m["pages"]),
                "parent_fields": ";".join(m["parents"]),
                "parent_pages": ";".join(m["parent_pages"]),
                "frozen_metric_status": (app.get((sid, mid)) or {}).get("frozen_metric_status", ""),
                "reason": m["note"],
            })

    # ------------------------------------------------------------ 自校验
    checks.append(("C01 主键守恒：决策行 = 278", len(decision_rows) == 278, len(decision_rows)))
    checks.append(("C02 标记行 = 278×5", len(flag_rows) == 1390, len(flag_rows)))
    pkeys = {r["security_id"] for r in decision_rows}
    checks.append(("C03 主键集合与 tight_pass 完全一致",
                   pkeys == {r["security_id"] for r in pool}, len(pkeys)))
    checks.append(("C04 无重复主键",
                   len(decision_rows) == len(pkeys), len(decision_rows)))

    # 判定计数
    dec_counter = Counter(r["decision"] for r in decision_rows)
    st_counter = {mid: Counter(r[f"{mid.lower()}_status"] for r in decision_rows) for mid in METRICS}

    # 与放行记录 guards 对账
    with open(RELEASE, encoding="utf-8") as f:
        release = json.load(f)
    g = release["guards"]
    rh02_ok = (st_counter["M11"]["OK"] == g["rh02"]["evaluable"]
               and st_counter["M11"]["NOT_APPLICABLE_PROJECT_MODE"] == g["rh02"]["project_mode_not_applicable"]
               and (st_counter["M11"]["UNKNOWN_CA_BLANK"] + st_counter["M11"]["UNKNOWN_CA_SOURCE_NOT_ADMISSIBLE"]) == g["rh02"]["hold"])
    checks.append(("C05 RH02 118/31/129 与 guards 一致", rh02_ok,
                   f"{st_counter['M11']['OK']}/{st_counter['M11']['NOT_APPLICABLE_PROJECT_MODE']}/"
                   f"{st_counter['M11']['UNKNOWN_CA_BLANK'] + st_counter['M11']['UNKNOWN_CA_SOURCE_NOT_ADMISSIBLE']}"))
    rh03_ok = (st_counter["M12"]["OK"] == g["rh03"]["evaluable"]
               and st_counter["M12"]["BOTH_BLANK_NO_USABLE_AMOUNT"] == g["rh03"]["both_periods_no_usable_amount"]
               and st_counter["M12"]["SINGLE_SIDED_GAP"] == g["rh03"]["single_sided_gap"]
               and st_counter["M12"]["UNKNOWN_INPUT_UNREADABLE"] == g["rh03"]["unreadable_or_missing"])
    checks.append(("C06 RH03 133/126/18/1 与 guards 一致", rh03_ok,
                   f"{st_counter['M12']['OK']}/{st_counter['M12']['BOTH_BLANK_NO_USABLE_AMOUNT']}/"
                   f"{st_counter['M12']['SINGLE_SIDED_GAP']}/{st_counter['M12']['UNKNOWN_INPUT_UNREADABLE']}"))
    checks.append(("C07 五指标状态全部落在已知词表",
                   all(s in set(VERDICT_STATUS.values()) for mid in METRICS for s in st_counter[mid]),
                   ""))
    # 三格隔离必须在输出里体现
    ca_nonadmit_ok = (
        any(row["security_id"] == "SZ:002786" and row["metric_id"] == "M11"
            and row["metric_status"] == "UNKNOWN_CA_SOURCE_NOT_ADMISSIBLE" for row in flag_rows)
        and any(row["security_id"] == "SZ:002786" and row["metric_id"] == "M12"
                and row["metric_status"] == "SINGLE_SIDED_GAP" for row in flag_rows)
        and any(row["security_id"] == "SZ:300843" and row["metric_id"] == "M12"
                and row["metric_status"] == "SINGLE_SIDED_GAP" for row in flag_rows)
        and any(row["security_id"] == "SZ:002369" and row["metric_id"] == "M11"
                and row["metric_status"] == "UNKNOWN_CA_SOURCE_NOT_ADMISSIBLE" for row in flag_rows)
    )
    checks.append(("C08 三格隔离按 V2.2 路由（银宝 M11 不准入/M12 单边；胜蓝 M12 单边；卓翼 M11 不准入）",
                   ca_nonadmit_ok, ""))
    checks.append(("C09 卓翼 M12 为双期无可采用金额",
                   any(row["security_id"] == "SZ:002369" and row["metric_id"] == "M12"
                       and row["metric_status"] == "BOTH_BLANK_NO_USABLE_AMOUNT" for row in flag_rows), ""))
    checks.append(("C10 冀东装备进入观察",
                   any(r["security_id"] == "SZ:000856" and r["decision"] == "QUALITY_HOLD" for r in decision_rows), ""))
    checks.append(("C11 冀东装备撤下 SG09",
                   any(r["security_id"] == "SZ:000856" and "SG09" in r["withdrawn_signals"] for r in decision_rows), ""))
    # 数值范围（冻结 valid_range 是合理性包络，冻结文件未给处置动作；只登记不阻断）
    vr = {"M04": (D("-100"), D("100")), "M08": (D("-10"), D("10")),
          "M10": (D("-365"), D("3650")), "M11": (D("-365"), D("3650")), "M12": (D("-100"), D("500"))}
    oor = []
    for row in decision_rows:
        for mid in METRICS:
            v = row[f"{mid.lower()}_value"]
            if v == "":
                continue
            dv = D(v)
            lo, hi = vr[mid]
            if dv < lo or dv > hi:
                oor.append((row["security_id"], mid, v))
    checks.append(("C12 超出 valid_range 的值已全部登记（非阻断）",
                   len(oor) == len(oor_rows), f"{len(oor)} 个，已登记 {len(oor_rows)} 个"))

    # Q10 代数复核：用表内值重算两支
    q10_bad = []
    for (sid, mid), a in app.items():
        if mid != "M11":
            continue
        v = a.get("q10_verdict")
        if v not in ("PROJECT_MODE", "NON_PROJECT"):
            continue
        ca = dec(a.get("ca_value_t"))
        asset = dec(a.get("asset_value_t"))
        rev = dec(a.get("rev_value_t"))
        if ca is None or asset in (None, ZERO) or rev in (None, ZERO):
            q10_bad.append((sid, "missing"))
            continue
        b1 = ca / asset * HUNDRED
        b2 = ca / rev * HUNDRED
        expect = "PROJECT_MODE" if (b1 > Q10_ASSET_PCT or b2 > Q10_REV_PCT) else "NON_PROJECT"
        if expect != v:
            q10_bad.append((sid, f"{b1}/{b2} -> {expect} != {v}"))
    checks.append(("C13 Q10 两支判定可由表内值代数复现", not q10_bad, q10_bad[:5]))

    # ------------------------------------------------------------ 写出

    def write_csv(path, rows, fields):
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            for row in rows:
                w.writerow({k: row.get(k, "") for k in fields})

    write_csv(HERE / "quality_flags.csv", flag_rows, [
        "security_id", "stock_name", "anchor_period", "metric_id", "rh",
        "applicability_verdict", "state_family", "metric_status", "metric_value",
        "metric_unit", "quality_flags", "rh_status", "l3_evidence_ok",
        "page_evidence_mode", "evidence_document_ids", "evidence_pages",
        "parent_fields", "parent_pages", "frozen_metric_status", "reason",
    ])

    write_csv(HERE / "quality_decision_log.csv", decision_rows, [
        "security_id", "stock_name", "anchor_period", "pool_role",
        "qualified_signal_ids", "qualified_dimensions", "dimension_count_before",
        "withdrawn_signals", "dimension_count_after", "surviving_dimensions",
        "s04_provisional_dimensions", "s04_upstream_hold_dimensions",
        "m04_status", "m08_status", "m10_status", "m11_status", "m12_status",
        "m04_value", "m08_value", "m10_value", "m11_value", "m12_value",
        "quality_flags", "s05_observations", "rh_triggered", "rh_pending",
        "rh_not_applicable", "l3_gate_result", "decision", "decision_reason",
        "s04_l2_decision", "limitations", "q10_verdict", "one_off",
    ])

    pass_rows = [r for r in decision_rows if r["decision"] == "QUALITY_PASS"]
    hold_rows = [r for r in decision_rows if r["decision"] == "QUALITY_HOLD"]
    write_csv(HERE / "quality_pass.csv", pass_rows, [
        "security_id", "stock_name", "anchor_period", "surviving_dimensions",
        "dimension_count_after", "rh_triggered", "rh_pending", "rh_not_applicable",
        "quality_flags", "s05_observations", "l3_gate_result", "decision",
        "decision_reason", "s04_l2_decision",
    ])
    write_csv(HERE / "quality_observe.csv", hold_rows, [
        "security_id", "stock_name", "anchor_period", "surviving_dimensions",
        "dimension_count_after", "withdrawn_signals", "rh_triggered", "rh_pending",
        "rh_not_applicable", "quality_flags", "s05_observations", "l3_gate_result",
        "decision", "decision_reason", "s04_l2_decision",
    ])

    write_csv(HERE / "s05_out_of_valid_range.csv", oor_rows, [
        "security_id", "stock_name", "anchor_period", "metric_id", "value",
        "valid_range", "metric_status", "note",
    ])

    # 776 家观察入口原样携带
    write_csv(HERE / "observe_pool_preserved_776.csv", [
        {
            "security_id": r["security_id"],
            "stock_name": r["stock_name"],
            "anchor_period": r["anchor_period"],
            "l0_status": r.get("l0_status", ""),
            "l2_decision": r.get("l2_decision", ""),
            "quality_source_state": r.get("quality_source_state", ""),
            "quality_source_pending_metrics": r.get("quality_source_pending_metrics", ""),
            "cutoff_isolated": r.get("cutoff_isolated", ""),
            "anchor_reselection_pending": r.get("anchor_reselection_pending", ""),
            "project_mode_source_unknown": r.get("project_mode_source_unknown", ""),
            "recheck_status": "CARRIED_FORWARD_UNCHANGED",
        }
        for r in observe_pool
    ], [
        "security_id", "stock_name", "anchor_period", "l0_status", "l2_decision",
        "quality_source_state", "quality_source_pending_metrics", "cutoff_isolated",
        "anchor_reselection_pending", "project_mode_source_unknown", "recheck_status",
    ])

    write_csv(HERE / "source_eligibility.csv", source_rows, [
        "security_id", "stock_name", "anchor_period", "metric_id", "field_id",
        "period_key", "period_role", "value_cny", "actual_status", "document_id",
        "source_page", "page_evidence_mode", "page_evidence_parents",
        "parent_document_id", "parent_source_page", "consolidation_scope", "currency",
        "restatement_flag", "l3_evidence_ok", "actual_use_eligibility", "adopted",
        "adoption_reason",
    ])

    # ------------------------------------------------------------ 汇总
    summary = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "issue": "S05 / #40",
        "executor": "WorkBuddy AI",
        "plan_version": "20261026_collection_first_v2",
        "input_contract": "S05_INPUT_CONTRACT_20261120_V22",
        "primary_pool": 278,
        "decision_counts": dict(dec_counter),
        "metric_status_counts": {k: dict(v) for k, v in st_counter.items()},
        "rh_trigger_counts": {
            k: sum(1 for r in decision_rows if k in (r["rh_triggered"] or "").split(";"))
            for k in ("RH01", "RH02", "RH03", "RH04", "RH05", "RH06")
        },
        "rh_pending_counts": {
            k: sum(1 for r in decision_rows if k in (r["rh_pending"] or "").split(";"))
            for k in ("RH01", "RH02", "RH03", "RH04", "RH05")
        },
        "rh_not_applicable_counts": {
            k: sum(1 for r in decision_rows if k in (r["rh_not_applicable"] or "").split(";"))
            for k in ("RH01", "RH02", "RH03", "RH04", "RH05")
        },
        "out_of_valid_range": len(oor_rows),
        "quality_flag_counts": {
            f"Q{i:02d}": sum(1 for r in decision_rows if f"Q{i:02d}" in (r["quality_flags"] or "").split(";"))
            for i in range(1, 13)
        },
        "source_rows": len(source_rows),
        "observe_pool_preserved": len(observe_pool),
        "checks": [{"name": n, "pass": bool(p), "detail": str(d)} for n, p, d in checks],
        "checks_passed": sum(1 for _, p, _ in checks if p),
        "checks_total": len(checks),
    }
    with open(HERE / "s05_build_summary.json", "w", encoding="utf-8", newline="\n") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if all(p for _, p, _ in checks) else 1


if __name__ == "__main__":
    sys.exit(main())
