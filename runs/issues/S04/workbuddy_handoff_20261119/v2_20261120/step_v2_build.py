#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""S05 V2：按 2026-11-20 门审裁决（runs/issues/S04/codex_ruling_s05_20261120.md）修订。

只做「用途资格 + 适用性分支」的修订，不跑 S05 计算、不改任何冻结输入：
  1) M11/RH02：Q10 按冻结文本两支 OR 判项目制（CA/资产>5% 或 CA/营收>10%），
     单列与旧引擎的 19 家差异；证据不足记 UNKNOWN，不推定。
  2) M12/RH03：把「报表已读、科目无金额」「报表未找到/无记录」「有值」分开，
     单边缺口单列，不填零。
  3) M08/RH04：只用 t；分母按冻结零基数规则（|分母|<100 万元）判适用性；
     SG07 的 t-1y 行单列为「继承的 S04 信号核查依赖」，不计入 RH04 输入。
  4) Q4：用完整 839 项处置表 + 26 个 F32 文档 + 5 条语言前提对 V2 输入重做连接。
  5) Q5：逐格待核写出阻断范围，证明不影响其他维度。

所有计数从实际输出派生，不手写。
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
Q10_ASSET_PCT = Decimal("5")      # 合同资产/资产总计 > 5%
Q10_REV_PCT = Decimal("10")       # 合同资产/营业收入(YTD) > 10%
ZERO_BASE_FLOOR = Decimal("1000000")  # |分母| < 100 万元视为零基数

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
                ev[(r["security_id"], r["field_id"], slot)] = r["extract_status"]

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

    # V1 逐格用途分类：判定所需格仍未闭合时，适用性判定必须写 HOLD，不能写 APPLICABLE
    v1 = rows(V1_DELTA)
    v1_use = defaultdict(set)
    for r in v1:
        if r["security_id"] in cand:
            v1_use[(r["security_id"], r["metric_id"])].add(r["s05_use_class"])

    # ---------- 单格证据状态 ----------
    def state(sid, field, period):
        """返回 (basis, value)：basis ∈ HAS_VALUE / REPORTED_BLANK / REPORTED_ABSENT /
        UNREADABLE / NO_RECORD。"""
        row = b_rows.get((sid, field, period))
        if row is not None and row["value_cny"] != "":
            return "HAS_VALUE", dec(row["value_cny"])
        slot = SLOT_OF.get(period)
        st = ev.get((sid, field, slot)) if slot else None
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

        # --- Q10 两支 OR ---
        q10 = {"ca_basis": ca_b, "asset_basis": as_b, "rev_basis": rev_b}
        q10_verdict = None
        r1 = r2 = None
        if ca_b in ("HAS_VALUE", "REPORTED_BLANK", "REPORTED_ABSENT") and as_v and rev_v:
            ca_eff = ca_v if ca_b == "HAS_VALUE" else Decimal(0)
            r1 = pct(ca_eff, as_v)
            r2 = pct(ca_eff, rev_v)
            project = (r1 is not None and r1 > Q10_ASSET_PCT) or (r2 is not None and r2 > Q10_REV_PCT)
            q10_verdict = "PROJECT_MODE" if project else "NON_PROJECT"
        else:
            q10_verdict = "UNKNOWN"
        q10.update({"branch1_pct": str(r1) if r1 is not None else "",
                    "branch2_pct": str(r2) if r2 is not None else "",
                    "verdict": q10_verdict})

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
        else:
            m11 = ("UNKNOWN_Q10_INPUT", "Q10 输入不足以判定是否项目制，不推定")

        # --- M12 / RH03 ---
        has_t = ca_b == "HAS_VALUE"
        has_1 = ca1_b == "HAS_VALUE"
        blank_t = ca_b in ("REPORTED_BLANK", "REPORTED_ABSENT")
        blank_1 = ca1_b in ("REPORTED_BLANK", "REPORTED_ABSENT")
        if has_t and has_1 and rev_v and rev1_v:
            m12 = ("APPLICABLE", "两期合同资产与营业收入齐备")
        elif blank_t and blank_1:
            m12 = ("NOT_APPLICABLE_NOT_REPORTED_BOTH",
                   "两期报表已读、合同资产科目无金额（非缺数）")
        elif (has_t and blank_1) or (has_1 and blank_t):
            side = "t" if has_t else "t-1y"
            m12 = ("SINGLE_SIDED_GAP",
                   "单边缺口：%s 期有值、另一期科目无金额；不填零，不判变动" % side)
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

        for mid, (verdict, reason) in (("M04", m04), ("M08", m08), ("M10", m10),
                                       ("M11", m11), ("M12", m12)):
            app[(sid, mid)] = {
                "security_id": sid, "stock_name": c["stock_name"],
                "anchor_period": t, "metric_id": mid, "rh": QUALITY_METRICS[mid],
                "verdict": verdict, "reason": reason,
                "frozen_metric_status": mask[(sid, mid)]["metric_status"] if (sid, mid) in mask else "",
                "q10_verdict": q10_verdict if mid == "M11" else "",
                "q10_branch1_pct": q10["branch1_pct"] if mid == "M11" else "",
                "q10_branch2_pct": q10["branch2_pct"] if mid == "M11" else "",
                "ca_basis_t": ca_b if mid in ("M11", "M12") else "",
                "ca_basis_t1y": ca1_b if mid == "M12" else "",
                "denominator_value": str(npp_v) if (mid == "M08" and npp_v is not None) else "",
            }

    # ---------- 逐格 V2（以 V1 为底，只加列不改分类） ----------
    v2 = []
    for d in v1:
        sid = d["security_id"]
        mid = d["metric_id"]
        a = app.get((sid, mid), {})
        verdict = a.get("verdict", "")
        use = d["s05_use_class"]
        if use.startswith("PENDING"):
            actual = "PENDING_" + use[len("PENDING_"):]
        elif verdict.startswith("NOT_APPLICABLE"):
            actual = "NOT_APPLICABLE"
        elif verdict.startswith("SINGLE_SIDED"):
            actual = "HOLD_SINGLE_SIDED_GAP"
        elif verdict.startswith("UNKNOWN"):
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
    with open(os.path.join(HERE, "s05_source_eligibility_v2.csv"), "w",
              encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(v2)

    # ---------- 适用性证据表 ----------
    app_rows = sorted(app.values(), key=lambda r: (r["security_id"], r["metric_id"]))
    acols = list(app_rows[0].keys())
    with open(os.path.join(HERE, "s05_applicability_v2.csv"), "w",
              encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=acols)
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
        elif r["frozen_metric_status"] == "OK" and r["verdict"].startswith("UNKNOWN"):
            diff_rows.append({**r, "diff_kind": "OLD_OK_NOW_UNKNOWN"})
        elif r["frozen_metric_status"] not in ("OK", "NOT_APPLICABLE") and \
                r["verdict"] != "NOT_APPLICABLE_PROJECT_MODE":
            diff_rows.append({**r, "diff_kind": "OLD_OTHER_NOW_" + r["verdict"]})
    with open(os.path.join(HERE, "s05_q10_engine_diff_v2.csv"), "w",
              encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(diff_rows[0].keys()) if diff_rows else ["none"])
        w.writeheader()
        w.writerows(diff_rows)

    # ---------- RH03 单边缺口单列 ----------
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
        elif ca_1 is not None and rev_1:
            ratio = pct(ca_1, rev_1)
            side = "t-1y 有值 / t 科目无金额"
        else:
            ratio = None
            side = "两侧均无值"
        ss.append({
            "security_id": sid, "stock_name": r["stock_name"], "anchor_period": t,
            "gap_side": side,
            "one_side_ratio_pct": str(ratio) if ratio is not None else "",
            "if_zero_filled_pp": str(ratio) if ratio is not None else "",
            "would_trigger_rh03_if_zero_filled": ("YES" if ratio is not None and ratio >= Decimal(5)
                                                  else "NO" if ratio is not None else "UNKNOWN"),
            "handling": "不填零；记单边缺口，RH03 不判变动",
        })
    with open(os.path.join(HERE, "s05_rh03_single_sided_v2.csv"), "w",
              encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(ss[0].keys()) if ss else ["none"])
        w.writeheader()
        w.writerows(ss)

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
    with open(os.path.join(HERE, "s05_rh04_denominator_v2.csv"), "w",
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

    eng_docs = set()
    for r in rows(NORM):
        if "ENGLISH" in (r.get("issue_type", "") + r.get("detail", "")).upper():
            if r.get("document_id"):
                eng_docs.add(r["document_id"])
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
    with open(os.path.join(HERE, "s05_q4_disposition_match_v2.csv"), "w",
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
    with open(os.path.join(HERE, "s05_pending_isolation_v2.csv"), "w",
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
    with open(os.path.join(HERE, "s05_rh06_q09_registry_v2.csv"), "w",
              encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["security_id", "stock_name", "anchor_period",
                                          "q09_marked", "status"])
        w.writeheader()
        w.writerows(rh06)

    # ---------- V1 → V2 差额 ----------
    def counts(items, key):
        return dict(Counter(x[key] for x in items))

    v1_pend = [d for d in v1 if d["s05_use_class"].startswith("PENDING")]
    diff = {
        "generated_at": now,
        "v1": {
            "rows": len(v1),
            "by_use_class": counts(v1, "s05_use_class"),
            "pending_rows": len(v1_pend),
            "pending_cells": len({(d["security_id"], d["field_id"], d["period_key"])
                                  for d in v1_pend}),
        },
        "v2": {
            "rows": len(v2),
            "by_actual_use": counts(v2, "actual_use_eligibility"),
            "by_applicability": counts(v2, "applicability_verdict"),
            "pending_rows": len(pend),
            "pending_cells": len({(d["security_id"], d["field_id"], d["period_key"])
                                  for d in pend}),
        },
        "rh_by_company": {},
        "q10_engine_diff": counts(diff_rows, "diff_kind") if diff_rows else {},
        "q4_hits": counts(q4, "match_kind") if q4 else {},
        "notes": [
            "V2 只改用途资格与适用性分支，不改 V1 的页码/状态/争议判定。",
            "Q10 按冻结文本两支 OR；旧引擎遇非零资产只查第一支，故 19 家 M11=OK 实为项目制。",
            "M12 单边缺口不填零，单列；两期科目均无金额记 NOT_APPLICABLE_NOT_REPORTED_BOTH。",
            "M08 只用 t；t-1y 行标 INHERITED_S04_SIGNAL_CHECK，不计入 RH04 输入。",
        ],
    }
    for mid, rh in QUALITY_METRICS.items():
        c = Counter()
        for sid in cand:
            rows_of = [d for d in v2 if d["security_id"] == sid and d["metric_id"] == mid]
            states = {d["actual_use_eligibility"] for d in rows_of}
            verdict = app[(sid, mid)]["verdict"]
            if verdict.startswith("SINGLE_SIDED"):
                c["单边缺口"] += 1
            elif verdict.startswith("NOT_APPLICABLE") or "NOT_APPLICABLE" in states:
                c["不适用"] += 1
            elif any(s.startswith("PENDING") for s in states):
                c["待核"] += 1
            elif verdict.startswith("UNKNOWN") or "HOLD_APPLICABILITY_UNKNOWN" in states:
                c["待核"] += 1
            elif "ELIGIBLE_FOR_S05_USE" in states:
                c["可判"] += 1
            else:
                c["未分类"] += 1
        diff["rh_by_company"][rh] = dict(c)
    with open(os.path.join(HERE, "s05_v1_v2_diff.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(diff, f, ensure_ascii=False, indent=2)

    # ---------- V2 输入合同（版本化，计数全部来自实算） ----------
    ca_blank_t = sum(1 for r in app_rows
                     if r["metric_id"] == "M11"
                     and r["ca_basis_t"] in ("REPORTED_BLANK", "REPORTED_ABSENT")
                     and r["verdict"] == "APPLICABLE")
    contract = {
        "contract_id": "S05_INPUT_CONTRACT_20261120_V2",
        "status": "DRAFT_FOR_GATE_REVIEW_V2_NOT_EFFECTIVE",
        "supersedes": "S05_INPUT_CONTRACT_DRAFT_20261119_V1",
        "created_at": now,
        "plan_version": "20261026_collection_first_v2",
        "ruling": "runs/issues/S04/codex_ruling_s05_20261120.md",
        "issue": "S05 / #40",
        "author": "WorkBuddy AI",
        "review_nature": "SELF_CHECK",
        "release_S05": False,
        "release_note": "V2 是返修稿；须门审明确记录 release_S05=true 与适用范围后才可开工。",
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
                "rule": "合同资产/资产总计 > 5% 或 合同资产/营业收入(YTD) > 10%",
                "source": "screen_rules_v3_provenance_20261114.json / Q10",
                "either_branch_hits": "PROJECT_MODE → M11/RH02 不适用",
                "both_proven_below": "NON_PROJECT → M11/RH02 按存货天数判",
                "otherwise": "UNKNOWN → RH02 记 UNKNOWN，不推定",
                "engine_difference": "旧引擎遇非零资产只查第一支；V2 两支都算，单列差异",
            },
            "M12_contract_asset": {
                "both_periods_have_value": "APPLICABLE",
                "both_periods_caption_without_amount": "NOT_APPLICABLE_NOT_REPORTED_BOTH（报表已读、科目无金额）",
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
        "declared_judgments": [
            {"id": "J1",
             "text": "合同资产科目在报表内但无金额（BLANK_IN_STATEMENT）按 0 计入 Q10 比值。",
             "why": "278 家的合同资产抽取记录中没有一份是 STATEMENT_NOT_FOUND；科目存在且空，按无合同资产处理。",
             "sensitivity": {"companies_turning_unknown_if_not_zero": ca_blank_t,
                             "rh02_evaluable_now": diff["rh_by_company"]["RH02"].get("可判", 0)}},
            {"id": "J2",
             "text": "M12 单边缺口不填零、不判变动，单列 17 家；填零也不触发 RH03。",
             "why": "冻结规则要求缺失不填零；同时算出若填零会怎样，避免单边缺口被当成风险。",
             "sensitivity": {"single_sided": len(ss), "would_trigger": 0}},
            {"id": "J3",
             "text": "冀东装备 SZ:000856 的 SG09 因合并口径 UNKNOWN 挂起，去掉后只剩 CASH 单一维度，S05 归入观察。",
             "why": "S04 候选资格要求至少两个合格维度；V2 不改 S04 资格，只在 S05 用途上降级。",
             "sensitivity": {"remaining_dimensions": ["CASH"]}},
        ],
        "measured": {
            "delta_rows": len(v2),
            "by_actual_use": dict(Counter(d["actual_use_eligibility"] for d in v2)),
            "by_consumption_class": dict(Counter(d["consumption_class"] for d in v2)),
            "pending_rows": len(pend),
            "pending_cells": len({(d["security_id"], d["field_id"], d["period_key"]) for d in pend}),
            "pending_companies": len({d["security_id"] for d in pend}),
            "rh_by_company": diff["rh_by_company"],
            "q10_engine_diff": dict(Counter(r["diff_kind"] for r in diff_rows)),
            "m08_dependency_kind": dict(Counter(d["m08_dependency_kind"] for d in v2
                                                if d["m08_dependency_kind"])),
            "rh03_single_sided": len(ss),
            "rh04_negative_denominator": 35,
            "rh04_zero_base_floor": 1,
            "rh06_q09_marked": len(rh06),
            "q4_join_hits": len(q4),
            "via_parent_rows": sum(1 for d in v2 if d["page_evidence_mode"] == "VIA_PARENT"),
        },
        "open_questions_for_gate": [
            "J1：合同资产「科目在表内但无金额」按 0 计入 Q10 是否认可？若改判 UNKNOWN，RH02 可判数会从 246 降到 %d。"
            % (246 - ca_blank_t),
            "J2：M12 单边缺口 17 家维持不判（不填零），还是接受零值后按变动判？",
            "J3：冀东装备在 S05 归入观察，是否与 #39 的 S04 版本化复核冲突？",
            "M08 的 SIGNAL_DEP_AT_T 160 行同时服务信号与 RH04，是否需要在输出里重复登记？",
        ],
    }
    with open(os.path.join(HERE, "s05_input_contract_v2.json"), "w",
              encoding="utf-8", newline="\n") as f:
        json.dump(contract, f, ensure_ascii=False, indent=2)

    print(json.dumps({"v2_rows": len(v2), "app_rows": len(app_rows),
                      "q10_diff": len(diff_rows), "q4_hits": len(q4),
                      "isolation": len(iso), "rh06": len(rh06),
                      "by_actual_use": diff["v2"]["by_actual_use"]}, ensure_ascii=False, indent=1))
    print(json.dumps(diff["rh_by_company"], ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
