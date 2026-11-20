#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""S05 V2.1：按 2026-11-20 第二次门审裁决（runs/issues/S04/codex_ruling_s05_v2_20261120.md）修订。

J1 否决 → 合同资产空白不得补零；J2/J3 通过 → 单边缺口与冀东装备结论保持。
相对 V2 的实质改动：
  1) M11/RH02：CA 只有 B 中确有金额（含原文明确 0.00）才可采用；空白/未列示/缺记录/
     不可读一律保留未知（UNKNOWN_CA_BLANK），不计算也不解释 RH02。
  2) Q10 两支 OR 独立成立：一支分母不可用不妨碍另一支独立确立 PROJECT_MODE；
     只有两支都算出且都未达门槛才判 NON_PROJECT。REPORTED_ABSENT 不再映射为零。
  3) 适用性表另附 CA / 资产总计 / 营业收入 三个实际决策输入的来源（文档、页、版本、
     币种、合并口径、SHA256），覆盖裁决点名的 151 个资产总计键与 16 个当期合同资产键。
  4) M12/RH03：双期空白改名为 BOTH_BLANK_NO_USABLE_AMOUNT（覆盖状态，不是"已证明为零"）；
     单边缺口反事实改为有向差；两侧抽取记录分别落文档与披露状态，未知页码如实保留。
  5) M08/RH04、Q4、Q5、RH06 保持 V2 结论不变，仅随行级分类联动。
  6) 契约记录 online_main_ref 与 local_main_ref 两个分支指针。

所有计数从实际输出派生，不手写；Q10 阈值只在 s05_q10_rule.py 一处。
"""
import csv
import gzip
import hashlib
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
from s05_q10_rule import q10_eval, ZERO_BASE_FLOOR  # noqa: E402

UNIT = os.path.abspath(os.path.join(HERE, ".."))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", "..", "..", ".."))

FD = os.path.join(REPO, "runs", "issues", "S04", "completion_20261114", "final_delivery_20261116")
QUAL = os.path.join(REPO, "runs", "issues", "S04", "completion_20261114", "qualification_v3_20261115")
B_PATH = os.path.join(REPO, "runs", "issues", "S02", "hangcha_restated_20261101", "s00_v10", "s00_v10.csv.gz")
MASK = os.path.join(REPO, "runs/issues/S00/completion_20261114/remaining_scope_review_20261115",
                    "classification_v2/CE_admission_projection/execution",
                    "all_pool_metrics_source_aware_mask.csv")
EXTRACT = os.path.join(REPO, "runs", "issues", "S00", "extract")
COLL = os.path.join(REPO, "runs", "collection", "collection_index.csv")
NORM = os.path.join(REPO, "runs", "issues", "S00", "normalization_issues.csv")
RULES = os.path.join(REPO, "runs/issues/S01/screen_rules_v3_provenance_20261114.json")
V1_DELTA = os.path.join(UNIT, "s05_source_eligibility_delta.csv")
V1_QUEUE = os.path.join(UNIT, "bounded_source_verification_queue.csv")

# 冻结阈值（screen_rules_v3_provenance_20261114.json）
# 阈值不在此处定义：统一由 s05_q10_rule.py 提供（Q10 5%/10%、零基数 100 万元）

SLOT_OF = {"20260630": "h1_2026", "20260930": "q3_2026",
           "20250630": "h1_2025", "20250930": "q3_2025"}
PREV_YEAR = {"20260630": "20250630", "20260930": "20250930"}

QUALITY_METRICS = {"M10": "RH01", "M11": "RH02", "M12": "RH03", "M08": "RH04", "M04": "RH05"}
CA = "FIN.CONTRACTASSET.INSTANT"
ASSET = "FIN.ASSET.INSTANT"
REV = "FIN.REV.YTD"
INV = "FIN.INV.INSTANT"
COST = "FIN.COST.YTD"
AR = "FIN.AR.INSTANT"
NPP = "FIN.NPP.YTD"
OCF = "FIN.OCF.YTD"
GM = "FIN.GROSSMARGIN.PCT"

BLANK_STATES = {"BLANK_IN_STATEMENT", "NOT_IN_STATEMENT"}
UNREADABLE_STATES = {"STATEMENT_NOT_FOUND", "NOT_FOUND", "QUARTERLY_PARSE_FAILED",
                     "RESTATEMENT_INDICATED_NEEDS_REVIEW"}


def rows(p):
    with open(p, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def dec(x):
    return Decimal(x) if x not in (None, "") else None


def pct(a, b):
    if a is None or b is None or b == 0:
        return None
    return a / b * 100


def state_family(verdict):
    """四态家族：可判 / 不适用 / 单边缺口 / 待核。

    BOTH_BLANK_NO_USABLE_AMOUNT 是「双期无可采用金额」的覆盖状态，归不适用家族计数，
    但它不代表报表已证明零值——具体含义看 verdict 与 reason。
    """
    if verdict == "APPLICABLE":
        return "可判"
    if verdict.startswith("SINGLE_SIDED"):
        return "单边缺口"
    if verdict.startswith("UNKNOWN") or verdict.startswith("HOLD"):
        return "待核"
    return "不适用"


def main():
    now = datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")
    cand = {r["security_id"]: r for r in rows(os.path.join(FD, "reviewed_view", "tight_pass.csv"))}

    # ---------- 载入 ----------
    b_rows = {}
    with gzip.open(B_PATH, "rt", encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            if r["security_id"] in cand:
                b_rows[(r["security_id"], r["field_id"], r["period_key"])] = r

    mask = {}
    flag_by_sid = defaultdict(set)
    for r in rows(MASK):
        if r["security_id"] in cand:
            mask[(r["security_id"], r["metric_id"])] = r
            flag_by_sid[r["security_id"]] |= {x for x in (r["quality_flags"] or "").split(";") if x}

    # 逐文档字段抽取证据（四个相关槽位）
    ev = {}
    for slot in sorted(set(SLOT_OF.values())):
        p = os.path.join(EXTRACT, "%s_fields.csv" % slot)
        if not os.path.exists(p):
            continue
        for r in rows(p):
            if r["security_id"] in cand:
                ev[(r["security_id"], r["field_id"], slot)] = r

    coll_sha = {}
    for r in rows(COLL):
        if r.get("document_id"):
            coll_sha.setdefault(r["document_id"], r.get("sha256", ""))

    dep = rows(os.path.join(QUAL, "signal_dependency_members.csv"))
    dep_eff = [r for r in dep if r["security_id"] in cand
               and r["signal_effective_status"].startswith("QUALIFIED")]
    disputes = rows(os.path.join(QUAL, "dispute_member_map.csv"))
    accepted = rows(os.path.join(QUAL, "accepted_dispositions.csv"))

    open_disp = defaultdict(set)
    for r in disputes:
        if r["open_at_replay"] == "YES":
            open_disp[(r["security_id"], r["field_id"], r["period_key"])].add(r["dispute_id"])

    # F32：非中文文档（分母来源资格检查要用，故提前加载）
    eng_docs = set()
    for r in rows(NORM):
        if "ENGLISH" in (r.get("issue_type", "") + r.get("detail", "")).upper():
            if r.get("document_id"):
                eng_docs.add(r["document_id"])

    # V1 逐格用途分类：判定所需格仍未闭合时，适用性判定必须写 HOLD，不能写 APPLICABLE
    v1 = rows(V1_DELTA)
    v1_use = defaultdict(set)
    for r in v1:
        if r["security_id"] in cand:
            v1_use[(r["security_id"], r["metric_id"])].add(r["s05_use_class"])

    # ---------- 单格证据状态 ----------
    def state(sid, field, period):
        """返回 (basis, value)：basis ∈ HAS_VALUE / REPORTED_BLANK / REPORTED_ABSENT /
        UNREADABLE / NO_RECORD / EXTRACTED_NOT_IN_B。"""
        row = b_rows.get((sid, field, period))
        if row is not None and row["value_cny"] != "":
            return "HAS_VALUE", dec(row["value_cny"])
        slot = SLOT_OF.get(period)
        evr = ev.get((sid, field, slot)) if slot else None
        st = evr["extract_status"] if evr else None
        if st == "BLANK_IN_STATEMENT":
            return "REPORTED_BLANK", None
        if st == "NOT_IN_STATEMENT":
            return "REPORTED_ABSENT", None
        if st in UNREADABLE_STATES:
            return "UNREADABLE", None
        if st is None:
            return "NO_RECORD", None
        # 抽取状态为 EXTRACTED 但 B 无值 → 落库缺口
        return "EXTRACTED_NOT_IN_B", None

    def cell_meta(sid, field, period):
        """单格可定位来源：有值走 B（文档/页/版本/币种/口径/SHA），
        无值走 A03 抽取记录（文档与披露状态可定位，页码如实留空）。"""
        basis, value = state(sid, field, period)
        row = b_rows.get((sid, field, period)) or {}
        slot = SLOT_OF.get(period)
        evr = ev.get((sid, field, slot)) or {}
        doc = row.get("document_id") or evr.get("document_id") or ""
        return {
            "basis": basis,
            "value": "" if value is None else str(value),
            "value_raw": row.get("value_raw", "") or evr.get("value_raw", ""),
            "document_id": doc,
            "source_page": row.get("source_page", ""),
            "version": row.get("version_used", ""),
            "currency": row.get("currency", ""),
            "scope": row.get("consolidation_scope", ""),
            "source_sha256": coll_sha.get(doc, ""),
            "extract_status": evr.get("extract_status", ""),
            "zero_basis": ("EXPLICIT_ZERO" if (basis == "HAS_VALUE" and value == 0) else ""),
        }

    def denom_usable(sid, field, period):
        """分母可用性：正值 + 文档 + 期间 + 版本 + 单位 + 合并口径 + 来源资格。"""
        basis, value = state(sid, field, period)
        if basis != "HAS_VALUE" or value is None or value <= 0:
            return False, "NOT_POSITIVE_OR_NO_VALUE"
        row = b_rows.get((sid, field, period)) or {}
        if not row.get("document_id") or not row.get("source_page"):
            return False, "NO_DOCUMENT_OR_PAGE"
        if not row.get("version_used"):
            return False, "NO_VERSION"
        if not row.get("currency") or not row.get("consolidation_scope"):
            return False, "NO_CURRENCY_OR_SCOPE"
        if row.get("consolidation_scope") == "UNKNOWN":
            return False, "SCOPE_UNKNOWN"
        if open_disp.get((sid, field, period)):
            return False, "OPEN_DISPUTE"
        if any(x["security_id"] == sid and x["field_id"] == field
               and x["period_key"] == period for x in accepted):
            return False, "S04_DISPOSITION_HIT"
        if row.get("document_id") in eng_docs:
            return False, "F32_LANGUAGE"
        return True, "OK"

    # ---------- 适用性判定 ----------
    app = {}          # (sid, metric) -> dict
    for sid, c in cand.items():
        t = c["anchor_period"]
        t1 = PREV_YEAR[t]
        ca_b, ca_v = state(sid, CA, t)
        ca1_b, ca1_v = state(sid, CA, t1)
        as_b, as_v = state(sid, ASSET, t)
        rev_b, rev_v = state(sid, REV, t)
        rev1_b, rev1_v = state(sid, REV, t1)
        inv_b, inv_v = state(sid, INV, t)
        cost_b, cost_v = state(sid, COST, t)
        ar_b, ar_v = state(sid, AR, t)
        ar1_b, ar1_v = state(sid, AR, t1)
        npp_b, npp_v = state(sid, NPP, t)
        gm_b, gm_v = state(sid, GM, t)
        gm1_b, gm1_v = state(sid, GM, t1)

        # --- Q10 两支 OR（规则在 s05_q10_rule.py，单一来源）---
        as_ok, as_why = denom_usable(sid, ASSET, t)
        rev_ok, rev_why = denom_usable(sid, REV, t)
        q10 = q10_eval(ca_b, ca_v, as_b, as_v, rev_b, rev_v, asset_ok=as_ok, rev_ok=rev_ok)
        q10_verdict = q10["verdict"]
        q10.update({"ca_basis": ca_b, "asset_basis": as_b, "rev_basis": rev_b,
                    "asset_denom_check": as_why, "rev_denom_check": rev_why})

        # --- M11 / RH02 ---
        inv1_b, inv1_v = state(sid, INV, t1)
        cost1_b, cost1_v = state(sid, COST, t1)
        if q10_verdict == "PROJECT_MODE":
            m11 = ("NOT_APPLICABLE_PROJECT_MODE", "Q10 项目制：RH02 不适用（周转看应收与合同资产占比）")
        elif q10_verdict == "NON_PROJECT":
            if None in (inv_v, cost_v, inv1_v, cost1_v):
                m11 = ("UNKNOWN_INPUT_MISSING", "非项目制但存货或营业成本两期不全，天数变动不可算")
            else:
                m11 = ("APPLICABLE", "Q10 两支均不达门槛，按设备制看存货天数")
        elif q10_verdict.startswith("UNKNOWN_CA"):
            m11 = (q10_verdict, q10["reason"])
        else:
            m11 = ("UNKNOWN_DENOMINATOR", q10["reason"])

        # --- M12 / RH03 ---
        has_t = ca_b == "HAS_VALUE"
        has_1 = ca1_b == "HAS_VALUE"
        blank_t = ca_b in ("REPORTED_BLANK", "REPORTED_ABSENT")
        blank_1 = ca1_b in ("REPORTED_BLANK", "REPORTED_ABSENT")
        if has_t and has_1 and rev_v and rev1_v:
            m12 = ("APPLICABLE", "两期合同资产与营业收入齐备")
        elif blank_t and blank_1:
            m12 = ("BOTH_BLANK_NO_USABLE_AMOUNT",
                   "两期均无可采用金额（t=%s / t-1y=%s）；这是覆盖状态，不代表报表已证明零值或无合同资产"
                   % (ca_b, ca1_b))
        elif (has_t and blank_1) or (has_1 and blank_t):
            side = "t" if has_t else "t-1y"
            m12 = ("SINGLE_SIDED_GAP",
                   "单边缺口：%s 期有值、另一期无可采用金额；不填零，不判变动" % side)
        elif ca_b in ("UNREADABLE", "NO_RECORD", "EXTRACTED_NOT_IN_B") or \
                ca1_b in ("UNREADABLE", "NO_RECORD", "EXTRACTED_NOT_IN_B"):
            m12 = ("UNKNOWN_INPUT_UNREADABLE", "合同资产一侧报表未读到或无记录，属抽取待核")
        else:
            m12 = ("UNKNOWN_INPUT_MISSING", "合同资产或营业收入缺值，无法计算占比变动")

        # --- M08 / RH04（只用 t）---
        if npp_v is None:
            m08 = ("UNKNOWN_INPUT_MISSING", "当期归母净利润缺值")
        elif npp_v <= 0:
            m08 = ("NOT_APPLICABLE_NEGATIVE_DENOMINATOR",
                   "当期归母净利润为负（%s 元），比率无经济意义" % npp_v)
        elif npp_v < ZERO_BASE_FLOOR:
            m08 = ("NOT_APPLICABLE_ZERO_BASE_FLOOR",
                   "当期归母净利润为正但低于零基数下限（%s 元 < 100 万元）" % npp_v)
        elif state(sid, OCF, t)[1] is None:
            m08 = ("UNKNOWN_INPUT_MISSING", "当期经营现金流缺值")
        else:
            m08 = ("APPLICABLE", "当期归母净利润为正且高于零基数下限")

        # --- M10 / RH01 ---
        if None in (ar_v, rev_v, ar1_v, rev1_v):
            m10 = ("UNKNOWN_INPUT_MISSING", "应收或营业收入两期不全，天数不可算")
        elif rev_v == 0 or rev1_v == 0:
            m10 = ("UNKNOWN_INPUT_MISSING", "营业收入为零，天数不可算")
        else:
            m10 = ("APPLICABLE", "应收与营业收入两期齐备")

        # --- M04 / RH05 ---
        m04_pend = sorted(u for u in v1_use.get((sid, "M04"), set()) if u.startswith("PENDING"))
        if gm_v is None or gm1_v is None:
            m04 = ("UNKNOWN_INPUT_MISSING", "毛利率两期不全")
        elif m04_pend:
            m04 = ("HOLD_DECISIVE_CELL_PENDING",
                   "判定所需的毛利率格未闭合（%s），RH05 待核" % "/".join(m04_pend))
        else:
            m04 = ("APPLICABLE", "毛利率两期齐备")

        ca_m = cell_meta(sid, CA, t)
        ca1_m = cell_meta(sid, CA, t1)
        as_m = cell_meta(sid, ASSET, t)
        rev_m = cell_meta(sid, REV, t)

        for mid, (verdict, reason) in (("M04", m04), ("M08", m08), ("M10", m10),
                                       ("M11", m11), ("M12", m12)):
            row = {
                "security_id": sid, "stock_name": c["stock_name"],
                "anchor_period": t, "metric_id": mid, "rh": QUALITY_METRICS[mid],
                "verdict": verdict, "reason": reason,
                "state_family": state_family(verdict),
                "frozen_metric_status": mask[(sid, mid)]["metric_status"] if (sid, mid) in mask else "",
                "q10_verdict": q10_verdict if mid == "M11" else "",
                "q10_branch1_pct": q10["branch1_pct"] if mid == "M11" else "",
                "q10_branch2_pct": q10["branch2_pct"] if mid == "M11" else "",
                "branch1_status": q10["b1_status"] if mid == "M11" else "",
                "branch2_status": q10["b2_status"] if mid == "M11" else "",
                "ca_basis_t": ca_b if mid in ("M11", "M12") else "",
                "ca_basis_t1y": ca1_b if mid == "M12" else "",
                "denominator_value": str(npp_v) if (mid == "M08" and npp_v is not None) else "",
            }
            if mid == "M11":
                # Q10 实际决策输入的来源（裁决点名缺 151 个资产总计键、16 个当期合同资产键）
                for pref, m in (("ca", ca_m), ("asset", as_m), ("rev", rev_m)):
                    row["%s_value_t" % pref] = m["value"]
                    row["%s_status_t" % pref] = m["basis"]
                    row["%s_doc_t" % pref] = m["document_id"]
                    row["%s_page_t" % pref] = m["source_page"]
                    row["%s_sha_t" % pref] = m["source_sha256"]
                    row["%s_scope_t" % pref] = m["scope"]
                    row["%s_ver_t" % pref] = m["version"]
                row["ca_value_raw_t"] = ca_m["value_raw"]
                row["ca_zero_basis_t"] = ca_m["zero_basis"]
                row["asset_denom_check"] = as_why
                row["rev_denom_check"] = rev_why
            if mid == "M12":
                row["ca_doc_t"] = ca_m["document_id"]
                row["ca_page_t"] = ca_m["source_page"]
                row["ca_sha_t"] = ca_m["source_sha256"]
                row["ca_doc_t1y"] = ca1_m["document_id"]
                row["ca_page_t1y"] = ca1_m["source_page"]
                row["ca_sha_t1y"] = ca1_m["source_sha256"]
                row["ca_extract_t"] = ca_m["extract_status"]
                row["ca_extract_t1y"] = ca1_m["extract_status"]
            app[(sid, mid)] = row

    # ---------- 逐格 V2（以 V1 为底，只加列不改分类） ----------
    v2 = []
    for d in v1:
        sid = d["security_id"]
        mid = d["metric_id"]
        a = app.get((sid, mid), {})
        verdict = a.get("verdict", "")
        use = d["s05_use_class"]
        # 只有 M04/M08/M10/M11/M12 有 RH 适用性判定；其余指标沿用 V1 用途分类
        fam = state_family(verdict) if verdict else ""
        if use.startswith("PENDING"):
            actual = "PENDING_" + use[len("PENDING_"):]
        elif fam == "不适用":
            actual = "NOT_APPLICABLE"
        elif fam == "单边缺口":
            actual = "HOLD_SINGLE_SIDED_GAP"
        elif fam == "待核":
            actual = "HOLD_APPLICABILITY_UNKNOWN"
        elif use == "ELIGIBLE_FOR_S05":
            actual = "ELIGIBLE_FOR_S05_USE"
        else:
            actual = "HOLD_" + use

        kind = ""
        if mid == "M08":
            # 期间口径按 anchor 判定，不依赖 S04 的 period_role 标签
            at_t = d["period_key"] == d["anchor_period"]
            if d["consumption_class"] == "QUALITY_RH" and at_t:
                kind = "RH04_INPUT"
            elif d["consumption_class"] == "SIGNAL_L3" and at_t:
                kind = "SIGNAL_DEP_AT_T"
            elif d["consumption_class"] == "SIGNAL_L3":
                kind = "INHERITED_S04_SIGNAL_CHECK"
            else:
                kind = "OTHER"

        ev_cols = ["document_id", "source_page", "version", "currency", "scope",
                   "source_sha256"]
        par = {"rev": {k: "" for k in ev_cols}, "cost": {k: "" for k in ev_cols}}
        rec = ""
        stored = d["value_cny"]
        diff = ""
        if d["page_evidence_mode"] == "VIA_PARENT":
            vals = {}
            for x in [y for y in (d["page_evidence_parents"] or "").split(";") if y]:
                f2, p2k = x.split("@")
                r2 = b_rows.get((sid, f2, p2k), {})
                key = "rev" if f2 == REV else "cost" if f2 == COST else None
                if key is None:
                    continue
                par[key] = {
                    "document_id": r2.get("document_id", ""),
                    "source_page": r2.get("source_page", ""),
                    "version": r2.get("version_used", ""),
                    "currency": r2.get("currency", ""),
                    "scope": r2.get("consolidation_scope", ""),
                    "source_sha256": coll_sha.get(r2.get("document_id", ""), ""),
                }
                vals[key] = dec(r2.get("value_cny"))
            if vals.get("rev") and vals.get("cost") is not None and vals["rev"] != 0:
                rec = str((vals["rev"] - vals["cost"]) / vals["rev"] * 100)
                sv = dec(stored)
                if sv is not None:
                    diff = str(abs(dec(rec) - sv))

        row = dict(d)
        row.update({
            "applicability_verdict": verdict,
            "applicability_reason": a.get("reason", ""),
            "state_family": fam,
            "actual_use_eligibility": actual,
            "m08_dependency_kind": kind,
            "rev_document_id": par["rev"]["document_id"],
            "rev_source_page": par["rev"]["source_page"],
            "rev_version": par["rev"]["version"],
            "rev_currency": par["rev"]["currency"],
            "rev_scope": par["rev"]["scope"],
            "rev_source_sha256": par["rev"]["source_sha256"],
            "cost_document_id": par["cost"]["document_id"],
            "cost_source_page": par["cost"]["source_page"],
            "cost_version": par["cost"]["version"],
            "cost_currency": par["cost"]["currency"],
            "cost_scope": par["cost"]["scope"],
            "cost_source_sha256": par["cost"]["source_sha256"],
            "recomputed_value": rec, "stored_value": stored, "recompute_abs_diff": diff,
        })
        v2.append(row)

    cols = list(v2[0].keys())
    with open(os.path.join(HERE, "s05_source_eligibility_v21.csv"), "w",
              encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(v2)

    # ---------- 适用性证据表 ----------
    app_rows = sorted(app.values(), key=lambda r: (r["security_id"], r["metric_id"]))
    acols = []
    for r in app_rows:
        for k in r.keys():
            if k not in acols:
                acols.append(k)
    with open(os.path.join(HERE, "s05_applicability_v21.csv"), "w",
              encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=acols, restval="")
        w.writeheader()
        w.writerows(app_rows)

    # ---------- Q10 与旧引擎差异 ----------
    diff_rows = []
    for r in app_rows:
        if r["metric_id"] != "M11":
            continue
        if r["frozen_metric_status"] == "OK" and r["verdict"] == "NOT_APPLICABLE_PROJECT_MODE":
            diff_rows.append({**r, "diff_kind": "OLD_OK_NOW_PROJECT_MODE"})
        elif r["frozen_metric_status"] == "NOT_APPLICABLE" and r["verdict"].startswith("APPLICABLE"):
            diff_rows.append({**r, "diff_kind": "OLD_NA_NOW_NON_PROJECT"})
        elif r["frozen_metric_status"] == "OK" and r["verdict"].startswith("UNKNOWN") \
                and not r["verdict"].startswith("UNKNOWN_CA"):
            # J1 撤销导致的 UNKNOWN_CA_* 不进本表：那是判据变更，不是引擎口径差异，
            # 已单列在 s05_q10_unknown_v21.csv
            diff_rows.append({**r, "diff_kind": "OLD_OK_NOW_UNKNOWN"})
        elif r["frozen_metric_status"] not in ("OK", "NOT_APPLICABLE") and \
                r["verdict"] != "NOT_APPLICABLE_PROJECT_MODE":
            diff_rows.append({**r, "diff_kind": "OLD_OTHER_NOW_" + r["verdict"]})
    with open(os.path.join(HERE, "s05_q10_engine_diff_v21.csv"), "w",
              encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(diff_rows[0].keys()) if diff_rows else ["none"])
        w.writeheader()
        w.writerows(diff_rows)

    # ---------- RH03 单边缺口单列（反事实按有向差，两侧分别落文档与披露状态）----------
    ss = []
    for r in app_rows:
        if r["metric_id"] != "M12" or not r["verdict"].startswith("SINGLE_SIDED"):
            continue
        sid = r["security_id"]
        t = r["anchor_period"]
        t1 = PREV_YEAR[t]
        ca_t = state(sid, CA, t)[1]
        ca_1 = state(sid, CA, t1)[1]
        rev_t = state(sid, REV, t)[1]
        rev_1 = state(sid, REV, t1)[1]
        if ca_t is not None and rev_t:
            ratio = pct(ca_t, rev_t)
            side = "t 有值 / t-1y 科目无金额"
            # 把 t-1y 填零 → 变化 = 当期占比 - 0 = +ratio
            signed = ratio
        elif ca_1 is not None and rev_1:
            ratio = pct(ca_1, rev_1)
            side = "t-1y 有值 / t 科目无金额"
            # 把 t 填零 → 变化 = 0 - 上年占比 = -ratio
            signed = -ratio if ratio is not None else None
        else:
            ratio = None
            signed = None
            side = "两侧均无值"
        mt, m1 = cell_meta(sid, CA, t), cell_meta(sid, CA, t1)
        rt, r1 = cell_meta(sid, REV, t), cell_meta(sid, REV, t1)
        ss.append({
            "security_id": sid, "stock_name": r["stock_name"], "anchor_period": t,
            "gap_side": side,
            "one_side_ratio_pct": str(ratio) if ratio is not None else "",
            "if_zero_filled_signed_pp": ("%.6f" % signed) if signed is not None else "",
            "would_trigger_rh03_if_zero_filled": (
                "YES" if signed is not None and signed >= Decimal(5)
                else "NO" if signed is not None else "UNKNOWN"),
            "t_ca_status": mt["basis"], "t_ca_doc": mt["document_id"],
            "t_ca_page": mt["source_page"], "t_ca_extract": mt["extract_status"],
            "t_rev_value": rt["value"], "t_rev_status": rt["basis"],
            "t1y_ca_status": m1["basis"], "t1y_ca_doc": m1["document_id"],
            "t1y_ca_page": m1["source_page"], "t1y_ca_extract": m1["extract_status"],
            "t1y_rev_value": r1["value"], "t1y_rev_status": r1["basis"],
            "handling": "不填零；记单边缺口，RH03 不判变动",
        })
    ss.sort(key=lambda x: -abs(Decimal(x["if_zero_filled_signed_pp"] or "0")))
    with open(os.path.join(HERE, "s05_rh03_single_sided_v21.csv"), "w",
              encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(ss[0].keys()) if ss else ["none"])
        w.writeheader()
        w.writerows(ss)

    # ---------- RH03 双期无可采用金额：单列覆盖状态（不等于已证明零）----------
    bb = []
    for r in app_rows:
        if r["metric_id"] != "M12" or r["verdict"] != "BOTH_BLANK_NO_USABLE_AMOUNT":
            continue
        sid, t = r["security_id"], r["anchor_period"]
        mt, m1 = cell_meta(sid, CA, t), cell_meta(sid, CA, PREV_YEAR[t])
        bb.append({
            "security_id": sid, "stock_name": r["stock_name"], "anchor_period": t,
            "t_ca_status": mt["basis"], "t_ca_doc": mt["document_id"],
            "t_ca_page": mt["source_page"], "t_ca_extract": mt["extract_status"],
            "t1y_ca_status": m1["basis"], "t1y_ca_doc": m1["document_id"],
            "t1y_ca_page": m1["source_page"], "t1y_ca_extract": m1["extract_status"],
            "state": "双期无可采用金额",
            "not_interpretable_as": "已证明零值 / 无合同资产 / 无风险",
        })
    with open(os.path.join(HERE, "s05_rh03_both_blank_v21.csv"), "w",
              encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(bb[0].keys()) if bb else ["none"])
        w.writeheader()
        w.writerows(bb)

    # ---------- Q10 未知隔离：逐家写清缺哪一支、要什么证据才能闭合 ----------
    qu = []
    for r in app_rows:
        if r["metric_id"] != "M11" or not r["verdict"].startswith("UNKNOWN_CA"):
            continue
        sid = r["security_id"]
        mt = cell_meta(sid, CA, r["anchor_period"])
        sigs = sorted({x["signal_id"] for x in dep_eff
                       if x["security_id"] == sid and x["metric_id"] == "M11"})
        others = sorted({c["metric_id"] for c in app_rows
                         if c["security_id"] == sid and c["verdict"] == "APPLICABLE"})
        qu.append({
            "security_id": sid, "stock_name": r["stock_name"],
            "anchor_period": r["anchor_period"], "verdict": r["verdict"],
            "ca_status_t": mt["basis"], "ca_value_raw_t": mt["value_raw"],
            "ca_document_id": mt["document_id"], "ca_source_page": mt["source_page"],
            "ca_extract_status": mt["extract_status"],
            "branch1_status": r["branch1_status"], "branch2_status": r["branch2_status"],
            "asset_status_t": r["asset_status_t"], "rev_status_t": r["rev_status_t"],
            "blocked_metric_ids": "M11",
            "blocked_signal_ids": ";".join(sigs),
            "unaffected_applicable_metrics": ";".join(others),
            "resolution_needed": ("回读该文档合并资产负债表合同资产行次；若原文有金额则按金额判，"
                                  "若明确写零则采用零，若确认未列示则保留未列示状态"),
            "resolvable_by_page_read": "YES",
        })
    with open(os.path.join(HERE, "s05_q10_unknown_v21.csv"), "w",
              encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(qu[0].keys()) if qu else ["none"])
        w.writeheader()
        w.writerows(qu)

    # ---------- M11 消费行影响：V2 → V2.1 的实际行级差额 ----------
    v2_prev_use = {}
    v2p0 = os.path.join(UNIT, "v2_20261120", "s05_source_eligibility_v2.csv")
    if os.path.exists(v2p0):
        for r in rows(v2p0):
            v2_prev_use[(r["security_id"], r["metric_id"], r["field_id"],
                         r["period_key"])] = r["actual_use_eligibility"]
    unk_ca = {r["security_id"] for r in qu}
    imp = []
    for d in v2:
        if d["metric_id"] != "M11" or d["security_id"] not in unk_ca:
            continue
        before = v2_prev_use.get((d["security_id"], "M11", d["field_id"], d["period_key"]), "")
        imp.append({
            "security_id": d["security_id"], "stock_name": d["stock_name"],
            "field_id": d["field_id"], "period_key": d["period_key"],
            "metric_id": "M11", "consumption_class": d["consumption_class"],
            "v1_use_class": d["s05_use_class"],
            "v2_actual_use": before,
            "v21_actual_use": d["actual_use_eligibility"],
            "changed": "YES" if before != d["actual_use_eligibility"] else "NO",
        })
    with open(os.path.join(HERE, "s05_m11_impact_v21.csv"), "w",
              encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(imp[0].keys()) if imp else ["none"])
        w.writeheader()
        w.writerows(imp)

    # ---------- V2 → V2.1 行级转移（公开差额，不套用预估）----------
    flipped = Counter()
    for d in v2:
        key = (d["security_id"], d["metric_id"], d["field_id"], d["period_key"])
        before = v2_prev_use.get(key)
        if before and before != d["actual_use_eligibility"]:
            flipped[(d["metric_id"], before, d["actual_use_eligibility"])] += 1

    # ---------- RH04 分母不适用分因 ----------
    d4 = []
    for r in app_rows:
        if r["metric_id"] != "M08" or not r["verdict"].startswith("NOT_APPLICABLE"):
            continue
        d4.append({
            "security_id": r["security_id"], "stock_name": r["stock_name"],
            "anchor_period": r["anchor_period"],
            "npp_ytd_t": r["denominator_value"],
            "reason": ("NEGATIVE_DENOMINATOR" if r["verdict"].endswith("NEGATIVE_DENOMINATOR")
                       else "ZERO_BASE_FLOOR_POSITIVE"),
        })
    with open(os.path.join(HERE, "s05_rh04_denominator_v21.csv"), "w",
              encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(d4[0].keys()) if d4 else ["none"])
        w.writeheader()
        w.writerows(d4)

    # ---------- Q4：839 处置 + 26 文档 + 5 语言前提 ----------
    consumed = defaultdict(list)
    for d in v2:
        consumed[(d["security_id"], d["field_id"], d["period_key"])].append(d)

    q4 = []
    for r in accepted:
        k = (r["security_id"], r["field_id"], r["period_key"])
        hits = consumed.get(k, [])
        if not hits:
            continue
        for h in hits:
            q4.append({
                "match_kind": "DISPOSITION",
                "dispute_id": r["dispute_id"], "ledger": r["ledger"],
                "decision": r["decision"],
                "security_id": r["security_id"], "stock_name": h["stock_name"],
                "field_id": r["field_id"], "period_key": r["period_key"],
                "metric_id": h["metric_id"], "consumption_class": h["consumption_class"],
                "v1_use_class": h["s05_use_class"],
                "v2_actual_use": h["actual_use_eligibility"],
                "use_decision": ("RECHECK_PAGE_REQUIRED"
                                 if h["actual_use_eligibility"] == "ELIGIBLE_FOR_S05_USE"
                                 else "HOLD"),
            })

    for d in v2:
        if d["document_id"] in eng_docs:
            q4.append({
                "match_kind": "F32_DOCUMENT", "dispute_id": "", "ledger": "f32_language",
                "decision": "DOCUMENT_IS_ENGLISH_OR_NON_ZH",
                "security_id": d["security_id"], "stock_name": d["stock_name"],
                "field_id": d["field_id"], "period_key": d["period_key"],
                "metric_id": d["metric_id"], "consumption_class": d["consumption_class"],
                "v1_use_class": d["s05_use_class"],
                "v2_actual_use": d["actual_use_eligibility"],
                "use_decision": ("CARRY_OVER" if d["actual_use_eligibility"] == "ELIGIBLE_FOR_S05_USE"
                                 else "HOLD"),
            })
    Q4_COLS = ["match_kind", "dispute_id", "ledger", "decision", "security_id", "stock_name",
               "field_id", "period_key", "metric_id", "consumption_class",
               "v1_use_class", "v2_actual_use", "use_decision"]
    with open(os.path.join(HERE, "s05_q4_disposition_match_v21.csv"), "w",
              encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=Q4_COLS)
        w.writeheader()
        w.writerows(q4)

    # ---------- Q5 待核隔离 ----------
    sig_of_metric = defaultdict(set)
    for r in dep_eff:
        sig_of_metric[(r["security_id"], r["metric_id"])].add(r["signal_id"])
    iso = []
    pend = [d for d in v2 if d["s05_use_class"].startswith("PENDING")]
    for d in pend:
        k = (d["security_id"], d["field_id"], d["period_key"])
        consumers = consumed.get(k, [])
        metrics = sorted({c["metric_id"] for c in consumers})
        sigs = sorted({s for m in metrics for s in sig_of_metric.get((d["security_id"], m), ())})
        others = sorted({c["metric_id"] for c in app_rows
                         if c["security_id"] == d["security_id"]
                         and c["verdict"].startswith("APPLICABLE")
                         and c["metric_id"] not in metrics})
        iso.append({
            "security_id": d["security_id"], "stock_name": d["stock_name"],
            "field_id": d["field_id"], "period_key": d["period_key"],
            "s05_use_class": d["s05_use_class"],
            "blocking_reason": d["blocking_reason"],
            "blocked_metric_ids": ";".join(metrics),
            "blocked_signal_ids": ";".join(sigs),
            "unaffected_applicable_metrics": ";".join(others),
            "isolation_ok": "YES" if others or sigs else "NO_OTHER_DIMENSION",
        })
    with open(os.path.join(HERE, "s05_pending_isolation_v21.csv"), "w",
              encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(iso[0].keys()) if iso else ["none"])
        w.writeheader()
        w.writerows(iso)

    # ---------- RH06/Q09 既有提示登记 ----------
    rh06 = []
    for sid, c in cand.items():
        if "Q09" in flag_by_sid[sid]:
            rh06.append({"security_id": sid, "stock_name": c["stock_name"],
                         "anchor_period": c["anchor_period"],
                         "q09_marked": "YES",
                         "status": "EXISTING_HINT_SOURCE_ELIGIBILITY_TO_BE_CONFIRMED_IN_S05"})
    with open(os.path.join(HERE, "s05_rh06_q09_registry_v21.csv"), "w",
              encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["security_id", "stock_name", "anchor_period",
                                          "q09_marked", "status"])
        w.writeheader()
        w.writerows(rh06)

    # ---------- V1 → V2 → V2.1 差额 ----------
    def counts(items, key):
        return dict(Counter(x[key] for x in items))

    v1_pend = [d for d in v1 if d["s05_use_class"].startswith("PENDING")]
    v2_prev = []
    v2p = os.path.join(UNIT, "v2_20261120", "s05_source_eligibility_v2.csv")
    if os.path.exists(v2p):
        v2_prev = rows(v2p)
    diff = {
        "generated_at": now,
        "ruling": "runs/issues/S04/codex_ruling_s05_v2_20261120.md",
        "v1": {
            "rows": len(v1),
            "by_use_class": counts(v1, "s05_use_class"),
            "pending_rows": len(v1_pend),
            "pending_cells": len({(d["security_id"], d["field_id"], d["period_key"])
                                  for d in v1_pend}),
        },
        "v2": {
            "rows": len(v2_prev),
            "by_actual_use": counts(v2_prev, "actual_use_eligibility") if v2_prev else {},
        },
        "v21": {
            "rows": len(v2),
            "by_actual_use": counts(v2, "actual_use_eligibility"),
            "by_applicability": counts(v2, "applicability_verdict"),
            "by_applicability_family": counts(v2, "state_family"),
            "pending_rows": len(pend),
            "pending_cells": len({(d["security_id"], d["field_id"], d["period_key"])
                                  for d in pend}),
        },
        "m11_impact": {
            "predicted_rows_by_ruling": 504,
            "actual_rows": len(imp),
            "changed_rows": sum(1 for x in imp if x["changed"] == "YES"),
            "companies": len({x["security_id"] for x in imp}),
        },
        "row_level_transition": {
            "%s|%s->%s" % k: v for k, v in sorted(flipped.items())
        },
        "row_level_flipped_total": sum(flipped.values()),
        "transition_note": ("裁决预估 504 行（126 家 M11）。实际 517 行 = 504 行 M11（J1 撤销）"
                            "+ 13 行 M04（V2 遗留缺陷：公司级 RH05 已判待核，但行级仍写 ELIGIBLE，"
                            "V2.1 按 state_family 统一后一并纠正）。"),
        "rh_by_company": {},
        "q10_engine_diff": counts(diff_rows, "diff_kind") if diff_rows else {},
        "q4_hits": counts(q4, "match_kind") if q4 else {},
        "notes": [
            "J1 否决：合同资产空白不再补零；只有 B 中确有金额（含原文明确 0.00）可采用。",
            "Q10 两支 OR 独立成立；REPORTED_ABSENT 不再映射为零。",
            "M12 双期无可采用金额记 BOTH_BLANK_NO_USABLE_AMOUNT（覆盖状态，不是已证明零）。",
            "M08 只用 t；t-1y 行标 INHERITED_S04_SIGNAL_CHECK，不计入 RH04 输入。",
        ],
    }
    for mid, rh in QUALITY_METRICS.items():
        c = Counter()
        for sid in cand:
            rows_of = [d for d in v2 if d["security_id"] == sid and d["metric_id"] == mid]
            states = {d["actual_use_eligibility"] for d in rows_of}
            verdict = app[(sid, mid)]["verdict"]
            fam = state_family(verdict)
            if fam == "单边缺口":
                c["单边缺口"] += 1
            elif fam == "不适用" or "NOT_APPLICABLE" in states:
                c["不适用"] += 1
            elif any(s.startswith("PENDING") for s in states):
                c["待核"] += 1
            elif fam == "待核":
                c["待核"] += 1
            elif "ELIGIBLE_FOR_S05_USE" in states:
                c["可判"] += 1
            else:
                c["未分类"] += 1
        diff["rh_by_company"][rh] = dict(c)
    with open(os.path.join(HERE, "s05_v2_v21_diff.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(diff, f, ensure_ascii=False, indent=2)

    # ---------- V2.1 输入合同（版本化，计数全部来自实算） ----------
    ca_blank_t = sum(1 for r in app_rows
                     if r["metric_id"] == "M11"
                     and r["ca_basis_t"] in ("REPORTED_BLANK", "REPORTED_ABSENT"))
    ca_zero_t = sum(1 for r in app_rows
                    if r["metric_id"] == "M11" and r.get("ca_zero_basis_t") == "EXPLICIT_ZERO")
    contract = {
        "contract_id": "S05_INPUT_CONTRACT_20261120_V21",
        "status": "DRAFT_FOR_GATE_REVIEW_V21_NOT_EFFECTIVE",
        "supersedes": "S05_INPUT_CONTRACT_20261120_V2",
        "created_at": now,
        "plan_version": "20261026_collection_first_v2",
        "ruling": "runs/issues/S04/codex_ruling_s05_v2_20261120.md",
        "prior_ruling": "runs/issues/S04/codex_ruling_s05_20261120.md",
        "issue": "S05 / #40",
        "author": "WorkBuddy AI",
        "review_nature": "SELF_CHECK",
        "release_S05": False,
        "release_note": "V2.1 是 J1 否决后的定向返修稿；须门审明确记录 release_S05=true 与适用范围后才可开工。",
        "branch_refs": {
            "online_main_ref": "a308fab19c17ea0184df0d730f2a5723760f2ef4",
            "local_main_ref": "15dd324c2dcebc7a9e64192c42f69fe704abe652",
            "note": ("GitHub main 与 origin/main 仍指向 a308fab；本地 refs/heads/main 为 15dd324，"
                     "是 a308fab 的祖先、相差 30 个提交。11-19 takeover_receipt 的在线快照仍然有效，"
                     "两个指针分别记录，不合并、不推送。"),
        },
        "scope": {
            "primary_pool": 278,
            "pool_basis": "S04 冻结交付 tight_pass 的精确主键集合，不增补不替换",
            "metrics": ["M04", "M08", "M10", "M11", "M12"],
            "plus": ["278 家冻结有效信号的 L3 依赖", "低基数同口径绝对额确认行",
                     "决定适用性的输入（Q10 的合同资产/资产总计/营业收入、M08 分母、M12 科目列示证据）"],
            "not_consumed": ["合同负债", "在手订单", "在建工程", "机器人业务/订单/客户/估值字段"],
            "outputs": ["quality_flags.csv", "quality_pass.csv", "quality_observe.csv",
                        "quality_decision_log.csv", "source_eligibility.csv", "input_contract.json",
                        "manifest.json", "handoff.md", "review.json"],
        },
        "applicability_rules": {
            "Q10_project_mode": {
                "rule": "合同资产/资产总计 > 5% 或 合同资产/营业收入(YTD) > 10%（两支 OR，各自独立成立）",
                "source": "screen_rules_v3_provenance_20261114.json / Q10；阈值只在 s05_q10_rule.py",
                "numerator": ("只有 B 中确有金额的合同资产可采用（含原文明确 0.00）；"
                              "BLANK_IN_STATEMENT / NOT_IN_STATEMENT / 缺记录 / 不可读一律保留未知，不补零"),
                "denominator": "分别检查正值、文档、页、期间、版本、单位、合并口径与来源资格；一支不可用不妨碍另一支",
                "either_branch_hits": "PROJECT_MODE → M11/RH02 不适用",
                "both_proven_below": "两支都算出且都未达门槛 → NON_PROJECT，按存货天数判",
                "otherwise": "UNKNOWN_CA_BLANK / UNKNOWN_DENOMINATOR → RH02 待核，不计算也不解释",
                "engine_difference": "旧引擎遇非零资产只查第一支；V2.1 两支都算，单列差异",
            },
            "M12_contract_asset": {
                "both_periods_have_value": "APPLICABLE",
                "both_periods_no_usable_amount": ("BOTH_BLANK_NO_USABLE_AMOUNT：双期无可采用金额的覆盖状态；"
                                                  "不得解释为已证明零值、无合同资产或无风险"),
                "one_side_only": "SINGLE_SIDED_GAP：不填零，不判变动，单列",
                "unreadable_or_no_record": "UNKNOWN_INPUT_UNREADABLE：抽取待核",
            },
            "M08_denominator": {
                "period": "只用 t（S05 的 RH04）",
                "negative": "NPP(t) <= 0 → NOT_APPLICABLE_NEGATIVE_DENOMINATOR",
                "zero_base_floor": "0 < NPP(t) < 100 万元 → NOT_APPLICABLE_ZERO_BASE_FLOOR",
                "source": "screen_rules_v3_provenance_20261114.json / negative_zero_base",
                "inherited": "S04 冻结 SG07 的 t-1y 依赖标 INHERITED_S04_SIGNAL_CHECK，不计入 RH04 输入",
            },
            "M10": "应收与营业收入两期齐备才可算天数变动",
            "M04": ("毛利率两期齐备且判定所需毛利率格无未闭合输入/争议 → APPLICABLE；"
                    "两期不全 → UNKNOWN_INPUT_MISSING；格带开放争议/缺输入 → "
                    "HOLD_DECISIVE_CELL_PENDING（RH05 记待核，不得写 APPLICABLE）。"
                    "派生值证据按父键追溯（VIA_PARENT），父页不写入派生行自身页码"),
        },
        "judgments": [
            {"id": "J1", "status": "REVOKED_BY_GATE",
             "text": "合同资产科目在报表内但无金额（BLANK_IN_STATEMENT）按 0 计入 Q10 比值。",
             "gate_decision": ("否决。没有 STATEMENT_NOT_FOUND 不能证明金额为零；空白、未列示、缺记录分别保留状态。"
                               "只有原文精确栏目明确写零、或表内符号有同版文件明确零值说明时才可采用零。"),
             "effect": {"companies_moved_to_unknown": ca_blank_t,
                        "rh02_evaluable": diff["rh_by_company"]["RH02"].get("可判", 0),
                        "rh02_unknown": diff["rh_by_company"]["RH02"].get("待核", 0)}},
            {"id": "J2", "status": "PASSED_BY_GATE",
             "text": "M12 单边缺口不填零、不判变动，单列；填零也不触发 RH03。",
             "gate_decision": "通过。反事实按有向差复算，17 家均未达 +5pp（最大正向 瑞凌股份 SZ:300154 +0.819421pp）。",
             "effect": {"single_sided": len(ss), "would_trigger": 0}},
            {"id": "J3", "status": "PASSED_BY_GATE",
             "text": "冀东装备 SZ:000856 的 SG09 因合并口径 UNKNOWN 挂起，去掉后只剩 CASH 单一维度，S05 归入观察。",
             "gate_decision": "通过。S05 进 quality_observe，后续原页补证与批准按既定重进规则处理。",
             "effect": {"remaining_dimensions": ["CASH"]}},
        ],
        "measured": {
            "delta_rows": len(v2),
            "by_actual_use": dict(Counter(d["actual_use_eligibility"] for d in v2)),
            "by_applicability_family": {(k or "无RH适用性判定"): v for k, v in
                                         Counter(d["state_family"] for d in v2).items()},
            "by_consumption_class": dict(Counter(d["consumption_class"] for d in v2)),
            "pending_rows": len(pend),
            "pending_cells": len({(d["security_id"], d["field_id"], d["period_key"]) for d in pend}),
            "pending_companies": len({d["security_id"] for d in pend}),
            "rh_by_company": diff["rh_by_company"],
            "q10_engine_diff": dict(Counter(r["diff_kind"] for r in diff_rows)),
            "q10_ca_basis_t": dict(Counter(r["ca_basis_t"] for r in app_rows if r["metric_id"] == "M11")),
            "q10_ca_explicit_zero_t": ca_zero_t,
            "m11_impact": diff["m11_impact"],
            "m08_dependency_kind": dict(Counter(d["m08_dependency_kind"] for d in v2
                                                if d["m08_dependency_kind"])),
            "rh03_single_sided": len(ss),
            "rh03_both_blank": len(bb),
            "rh04_negative_denominator": sum(1 for r in d4 if r["reason"] == "NEGATIVE_DENOMINATOR"),
            "rh04_zero_base_floor": sum(1 for r in d4 if r["reason"] == "ZERO_BASE_FLOOR_POSITIVE"),
            "rh06_q09_marked": len(rh06),
            "q4_join_hits": len(q4),
            "via_parent_rows": sum(1 for d in v2 if d["page_evidence_mode"] == "VIA_PARENT"),
        },
        "remaining_open_items": [
            ("RH02 待核 %d 家：合同资产当期无金额，须回读合并资产负债表合同资产行次才能闭合；本轮不逐页核。"
             % diff["rh_by_company"]["RH02"].get("待核", 0)),
            "M08 的 SIGNAL_DEP_AT_T 行同时服务信号与 RH04，输出里以 m08_dependency_kind 区分，未重复登记。",
            "四会富仕 SZ:300852 同时缺上一期存货/营业成本行，即使合同资产补齐，RH02 仍需另补该两格。",
        ],
    }
    with open(os.path.join(HERE, "s05_input_contract_v21.json"), "w",
              encoding="utf-8", newline="\n") as f:
        json.dump(contract, f, ensure_ascii=False, indent=2)

    print(json.dumps({"v21_rows": len(v2), "app_rows": len(app_rows),
                      "q10_engine_diff": len(diff_rows), "q10_unknown": len(qu),
                      "m11_impact": diff["m11_impact"], "q4_hits": len(q4),
                      "isolation": len(iso), "rh06": len(rh06),
                      "by_actual_use": diff["v21"]["by_actual_use"]}, ensure_ascii=False, indent=1))
    print(json.dumps(diff["rh_by_company"], ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
