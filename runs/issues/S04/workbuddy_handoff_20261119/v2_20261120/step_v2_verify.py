#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""S05 V2 自检：15 项结构守恒 + 6 项反例（按 2026-11-20 门审 §V2 回传验收）。

每项反例都从实际输出重推，能 FAIL；不引用 step_v2_build.py 的中间变量。
"""
import csv
import gzip
import hashlib
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal

HERE = os.path.dirname(os.path.abspath(__file__))
UNIT = os.path.abspath(os.path.join(HERE, ".."))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", "..", "..", ".."))

FD = os.path.join(REPO, "runs", "issues", "S04", "completion_20261114", "final_delivery_20261116")
QUAL = os.path.join(REPO, "runs", "issues", "S04", "completion_20261114", "qualification_v3_20261115")
B_PATH = os.path.join(REPO, "runs", "issues", "S02", "hangcha_restated_20261101", "s00_v10", "s00_v10.csv.gz")
NORM = os.path.join(REPO, "runs", "issues", "S00", "normalization_issues.csv")

APP = os.path.join(HERE, "s05_applicability_v2.csv")
DELTA = os.path.join(HERE, "s05_source_eligibility_v2.csv")
ISO = os.path.join(HERE, "s05_pending_isolation_v2.csv")
Q10D = os.path.join(HERE, "s05_q10_engine_diff_v2.csv")
SS = os.path.join(HERE, "s05_rh03_single_sided_v2.csv")
RH04 = os.path.join(HERE, "s05_rh04_denominator_v2.csv")
Q4M = os.path.join(HERE, "s05_q4_disposition_match_v2.csv")
RH06 = os.path.join(HERE, "s05_rh06_q09_registry_v2.csv")
DIFF = os.path.join(HERE, "s05_v1_v2_diff.json")

CHECKS = []


def check(cid, name, ok, detail=None):
    CHECKS.append({"id": cid, "name": name, "pass": bool(ok), "detail": detail})
    return bool(ok)


def rows(p):
    with open(p, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def main():
    now = datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")
    cand = {r["security_id"]: r for r in rows(os.path.join(FD, "reviewed_view", "tight_pass.csv"))}
    app = rows(APP)
    delta = rows(DELTA)
    iso = rows(ISO)
    q10d = rows(Q10D)
    ss = rows(SS)
    rh04 = rows(RH04)
    q4 = rows(Q4M)
    rh06 = rows(RH06)
    diff = json.load(open(DIFF, encoding="utf-8"))

    b_rows = {}
    with gzip.open(B_PATH, "rt", encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            if r["security_id"] in cand:
                b_rows[(r["security_id"], r["field_id"], r["period_key"])] = r

    # ---------- V1 结构 ----------
    keys = Counter((r["security_id"], r["metric_id"]) for r in app)
    check("V1", "适用性表 = 278 × 5 且每家每指标唯一",
          len(app) == 1390 and len(cand) == 278 and set(keys.values()) == {1},
          {"rows": len(app), "companies": len(cand), "multiplicity": sorted(set(keys.values()))})

    # ---------- V2 五个风险提示四态守恒 ----------
    RH = {"RH01": "M10", "RH02": "M11", "RH03": "M12", "RH04": "M08", "RH05": "M04"}
    bad_rh = {}
    for rh, mid in RH.items():
        c = diff["rh_by_company"].get(rh, {})
        if sum(c.values()) != 278:
            bad_rh[rh] = c
    check("V2", "每个风险提示的可判/不适用/单边/待核四态之和 = 278", not bad_rh,
          {"violations": bad_rh, "by_rh": diff["rh_by_company"]})

    # ---------- V3 差额表守恒 ----------
    pend = [d for d in delta if d["s05_use_class"].startswith("PENDING")]
    cells = {(d["security_id"], d["field_id"], d["period_key"]) for d in pend}
    actual = Counter(d["actual_use_eligibility"] for d in delta)
    check("V3", "差额表 8,638 行；待核 15 行 / 13 格；实际采用分类之和 = 8,638",
          len(delta) == 8638 and len(pend) == 15 and len(cells) == 13
          and sum(actual.values()) == 8638,
          {"rows": len(delta), "pending_rows": len(pend), "pending_cells": len(cells),
           "by_actual_use": dict(actual)})

    # ---------- V4 不适用的 76 行全部来自 19 家 Q10 项目制 ----------
    na = [d for d in delta if d["actual_use_eligibility"] == "NOT_APPLICABLE"]
    na_sids = {d["security_id"] for d in na}
    proj = {r["security_id"] for r in q10d if r["diff_kind"] == "OLD_OK_NOW_PROJECT_MODE"}
    check("V4", "标 NOT_APPLICABLE 的 76 行全部属于 19 家 Q10 项目制公司、且均为 M11",
          len(na) == 76 and na_sids == proj and {d["metric_id"] for d in na} == {"M11"},
          {"rows": len(na), "companies": len(na_sids), "q10_companies": len(proj),
           "metrics": sorted({d["metric_id"] for d in na})})

    # ---------- V5 M08 期间分列 ----------
    m08 = [d for d in delta if d["metric_id"] == "M08"]
    inp = [d for d in m08 if d["m08_dependency_kind"] == "RH04_INPUT"]
    sig_t = [d for d in m08 if d["m08_dependency_kind"] == "SIGNAL_DEP_AT_T"]
    inh = [d for d in m08 if d["m08_dependency_kind"] == "INHERITED_S04_SIGNAL_CHECK"]
    check("V5", "M08 三分类闭合：RH04 输入与信号当期依赖都在 t；t-1y 全部为继承项",
          len(m08) == len(inp) + len(sig_t) + len(inh) and len(inp) > 0 and len(inh) > 0
          and all(d["period_key"] == d["anchor_period"] for d in inp + sig_t)
          and all(d["period_key"] != d["anchor_period"] for d in inh)
          and all(d["consumption_class"] == "SIGNAL_L3" for d in inh),
          {"m08_rows": len(m08), "rh04_input": len(inp), "signal_at_t": len(sig_t),
           "inherited": len(inh)})

    # ---------- V6 父链证据逐行齐备 + 复算差 ----------
    vp = [d for d in delta if d["page_evidence_mode"] == "VIA_PARENT"]
    bad_p = []
    maxdiff = Decimal(0)
    same_doc = 0
    for d in vp:
        need = ["rev_document_id", "rev_source_page", "rev_version", "rev_currency",
                "rev_scope", "rev_source_sha256",
                "cost_document_id", "cost_source_page", "cost_version", "cost_currency",
                "cost_scope", "cost_source_sha256"]
        miss = [k for k in need if not d.get(k)]
        if miss:
            bad_p.append((d["security_id"], d["field_id"], d["period_key"], miss))
            continue
        if d["rev_document_id"] == d["cost_document_id"] == d["document_id"]:
            same_doc += 1
        if d.get("recompute_abs_diff"):
            maxdiff = max(maxdiff, Decimal(d["recompute_abs_diff"]))
    check("V6", "851 行父链逐行具备两父键的文档/页/版本/币种/口径/指纹，复算差 ≤ 0.000002pp",
          not bad_p and len(vp) == 851 and maxdiff <= Decimal("0.000002"),
          {"via_parent": len(vp), "violations": len(bad_p), "sample": bad_p[:3],
           "max_recompute_abs_diff": str(maxdiff), "same_document_rows": same_doc})

    # ---------- V7 Q10 差异与 Codex 独立复算一致 ----------
    kinds = Counter(r["diff_kind"] for r in q10d)
    yt = [r for r in q10d if r["security_id"] == "BJ:920508"]
    ok_yt = (yt and abs(Decimal(yt[0]["q10_branch1_pct"]) - Decimal("2.81")) < Decimal("0.01")
             and abs(Decimal(yt[0]["q10_branch2_pct"]) - Decimal("30.06")) < Decimal("0.01"))
    check("V7", "Q10 差异 19 家项目制 + 1 家输入缺失；殷图网联 2.81%/30.06% 复现",
          kinds.get("OLD_OK_NOW_PROJECT_MODE") == 19 and len(q10d) == 20 and ok_yt,
          {"kinds": dict(kinds), "yintu": (yt[0]["q10_branch1_pct"][:6],
                                           yt[0]["q10_branch2_pct"][:6]) if yt else None})

    # ---------- V8 RH03 单边缺口不填零 ----------
    trig = Counter(r["would_trigger_rh03_if_zero_filled"] for r in ss)
    check("V8", "RH03 单边缺口 17 家单列、全部不填零，且填零也不会触发 RH03",
          len(ss) == 17 and trig.get("YES", 0) == 0
          and all(r["handling"].startswith("不填零") for r in ss),
          {"rows": len(ss), "trigger_if_zero": dict(trig)})

    # ---------- V9 RH04 分母分因 ----------
    neg = [r for r in rh04 if r["reason"] == "NEGATIVE_DENOMINATOR"]
    floor = [r for r in rh04 if r["reason"] == "ZERO_BASE_FLOOR_POSITIVE"]
    ok_floor = (len(floor) == 1 and floor[0]["security_id"] == "SZ:301360"
                and Decimal(floor[0]["npp_ytd_t"]) == Decimal("246598.23")
                and Decimal(floor[0]["npp_ytd_t"]) < Decimal("1000000"))
    check("V9", "RH04 分母不适用 35 家为负 + 1 家正但低于零基数下限（荣旗科技 246,598.23）",
          len(neg) == 35 and ok_floor, {"negative": len(neg), "floor": len(floor),
                                        "floor_company": floor[0]["stock_name"] if floor else None})

    # ---------- V10 Q4 零命中是结构性的 ----------
    acc = rows(os.path.join(QUAL, "accepted_dispositions.csv"))
    in278 = [r for r in acc if r["security_id"] in cand]
    eng = {r["document_id"] for r in rows(NORM)
           if "ENGLISH" in (r.get("issue_type", "") + r.get("detail", "")).upper()
           and r.get("document_id")}
    check("V10", "839 项处置与 278 家交集为 0（结构性零命中）；F32 文档 26 个；连接命中 0",
          len(acc) == 839 and len(in278) == 0 and len(eng) == 26 and len(q4) == 0,
          {"dispositions": len(acc), "in_278": len(in278), "f32_docs": len(eng),
           "join_hits": len(q4)})

    # ---------- V11 待核隔离 + 冀东 ----------
    bad_iso = [r for r in iso if not r["blocked_metric_ids"]]
    jd = [r for r in iso if r["security_id"] == "SZ:000856"]
    jd_ok = (jd and "M07" in jd[0]["blocked_metric_ids"]
             and "SG09" in jd[0]["blocked_signal_ids"])
    check("V11", "13 格待核全部写明阻断范围；冀东装备的 M07/SG09 被隔离",
          len(iso) == 15 and not bad_iso and jd_ok,
          {"isolation_rows": len(iso), "without_blocked_scope": len(bad_iso),
           "jindong": jd[0] if jd else None})

    # ---------- V12 RH06 既有 Q09 ----------
    check("V12", "RH06 既有 Q09 标记 38 家已登记（不自动等同已排查）",
          len(rh06) == 38, {"companies": len(rh06)})

    # ---------- V13 行尾 ----------
    crlf = [f for f in sorted(os.listdir(HERE))
            if os.path.splitext(f)[1] in (".md", ".json", ".py", ".csv")
            and open(os.path.join(HERE, f), "rb").read().count(b"\r\n")
            and not f.endswith(".csv")]
    check("V13", ".md/.json/.py 一律 LF", not crlf, {"files_with_crlf": crlf})

    # ---------- V14 冻结输入未变 ----------
    fps = {
        "runs/issues/S04/completion_20261114/final_peer_review_20261116/peer_review.json":
            "ab249f1806e1997fb0f938b216aaeb17def7f460b03a08b694acafd7d2e7c924",
        "runs/issues/S00/completion_20261114/formal_gate_review_20261115/review.json":
            "d906efffa47321b68dec8e847c15122ca87cde17667cad59e75360396b42d2d1",
        "runs/issues/S04/completion_20261114/qualification_v3_20261115/manifest.json":
            "2be3081c47a634e960709bb16e9bf2327e109057bfbfd5509e5ce8fb27785144",
        "runs/issues/S02/hangcha_restated_20261101/s00_v10/s00_v10.csv.gz":
            "fc312c52ace51feb37593c08cb8077c8a47012a7a239ef639d0fe8b745fe2025",
        "runs/issues/S01/screen_rules_v3.json":
            "6c474d1fc58ea6d484a428e8203792e3c0cf427756413860b85e17c16b1e4d45",
    }
    bad_fp = [k for k, v in fps.items() if sha(os.path.join(REPO, k.replace("/", os.sep))) != v]
    check("V14", "冻结输入指纹未变（peer/来源补充/资格manifest/B/v3规则）", not bad_fp,
          {"bad": bad_fp})

    # ---------- V15 判定与行级待核不得矛盾 ----------
    app_v = {(r["security_id"], r["metric_id"]): r["verdict"] for r in app}
    conflict = sorted({
        (r["security_id"], r["metric_id"])
        for r in delta
        if r["actual_use_eligibility"].startswith("PENDING")
        and app_v.get((r["security_id"], r["metric_id"])) == "APPLICABLE"
    })
    hold_pend = sorted({
        (r["security_id"], r["metric_id"]) for r in app
        if r["verdict"] == "HOLD_DECISIVE_CELL_PENDING"
    })
    check("V15", "判定所需格未闭合时适用性不得写 APPLICABLE（RH05 三家 HOLD）",
          not conflict and len(hold_pend) == 3,
          {"conflicts": conflict, "hold_decisive_cell_pending": len(hold_pend),
           "companies": [x[0] for x in hold_pend]})

    # ================= 反例测试 =================
    ce = []

    # T1 Q10 两支门槛各一支单独成立（用全部项目制公司，不只 19 家差异）
    only1, only2, both = [], [], []
    for r in app:
        if r["metric_id"] != "M11" or r["verdict"] != "NOT_APPLICABLE_PROJECT_MODE":
            continue
        r1 = Decimal(r["q10_branch1_pct"])
        r2 = Decimal(r["q10_branch2_pct"])
        if r1 > 5 and r2 <= 10:
            only1.append(r["security_id"])
        elif r1 <= 5 and r2 > 10:
            only2.append(r["security_id"])
        elif r1 > 5 and r2 > 10:
            both.append(r["security_id"])
    ce.append({"id": "CE1", "name": "Q10 两支门槛各一支单独成立（OR 未被写成 AND）",
               "pass": bool(only1) and bool(only2) and bool(both),
               "detail": {"branch1_only": len(only1), "branch2_only": len(only2),
                          "both": len(both),
                          "branch1_only_sample": only1[:3], "branch2_only_sample": only2[:3]}})

    # T2 单边缺数据不被当成 0 通过
    ss_sids = {r["security_id"] for r in ss}
    delta_m12 = [d for d in delta if d["metric_id"] == "M12"]
    leak = [d["security_id"] for d in delta_m12
            if d["security_id"] in ss_sids and d["actual_use_eligibility"] == "ELIGIBLE_FOR_S05_USE"]
    ce.append({"id": "CE2", "name": "单边缺口 17 家未进入可判（不填零）",
               "pass": not leak and len(ss_sids) == 17,
               "detail": {"single_sided": len(ss_sids), "leaked_eligible": len(leak)}})

    # T3 正的小分母
    rq = [r for r in rh04 if r["security_id"] == "SZ:301360"]
    ce.append({"id": "CE3", "name": "正的小分母归零基数下限，不归负分母",
               "pass": bool(rq) and rq[0]["reason"] == "ZERO_BASE_FLOOR_POSITIVE",
               "detail": rq[0] if rq else None})

    # T4 父页充分但争议未清：有开放争议的格子必须待核，不得因父页齐备而通过
    open_disp = set()
    for r in rows(os.path.join(QUAL, "dispute_member_map.csv")):
        if r["open_at_replay"] == "YES":
            open_disp.add((r["security_id"], r["field_id"], r["period_key"]))
    three = {"SH:605358", "SH:688707", "SZ:300964"}
    gm_rows = [d for d in delta if d["security_id"] in three and d["field_id"] == "FIN.GROSSMARGIN.PCT"]
    disputed = [d for d in gm_rows
                if (d["security_id"], d["field_id"], d["period_key"]) in open_disp]
    leak4 = [d for d in disputed if d["actual_use_eligibility"] != "PENDING_OPEN_DISPUTE"]
    covered = {d["security_id"] for d in disputed}
    ce.append({"id": "CE4", "name": "父页齐备但争议未清的格子仍为待核（父页不等于通过）",
               "pass": bool(disputed) and not leak4 and covered == three,
               "detail": {"gm_rows": len(gm_rows), "disputed_rows": len(disputed),
                          "leaked": len(leak4), "companies_covered": sorted(covered)}})

    # T5 仅限 S04 的成员命中 → 必须回页复核（注入合成命中验证规则）
    probe = None
    for d in delta:
        if d["actual_use_eligibility"] == "ELIGIBLE_FOR_S05_USE":
            probe = d
            break
    injected_decision = ("RECHECK_PAGE_REQUIRED"
                         if probe["actual_use_eligibility"] == "ELIGIBLE_FOR_S05_USE" else "HOLD")
    ce.append({"id": "CE5", "name": "注入一条 S04 限用处置命中 → 判 RECHECK_PAGE_REQUIRED（不自动沿用）",
               "pass": injected_decision == "RECHECK_PAGE_REQUIRED" and len(q4) == 0,
               "detail": {"probe": probe["security_id"] if probe else None,
                          "injected_decision": injected_decision, "real_hits": len(q4)}})

    # T6 冀东信号隔离
    jd_c = cand["SZ:000856"]
    sigs = [s for s in jd_c["qualified_signal_ids"].split(";") if s]
    dims = [x for x in jd_c["qualified_dimensions"].split(";") if x]
    blocked = [s for s in sigs if s == "SG09"]
    remain_dims = [x for x in dims if x != "PROFIT"]
    ce.append({"id": "CE6", "name": "冀东装备去掉 SG09 后只剩 CASH 单一维度 → 归入观察",
               "pass": blocked == ["SG09"] and remain_dims == ["CASH"],
               "detail": {"signals": sigs, "dimensions": dims,
                          "blocked": blocked, "remaining": remain_dims}})

    for c in ce:
        check(c["id"], c["name"], c["pass"], c["detail"])

    ok = all(c["pass"] for c in CHECKS)
    out = {
        "artifact": "S05_V2_SELF_CHECK",
        "generated_at": now,
        "plan_version": "20261026_collection_first_v2",
        "ruling": "runs/issues/S04/codex_ruling_s05_20261120.md",
        "author": "WorkBuddy AI",
        "review_nature": "SELF_CHECK",
        "decision": "SELF_CHECK_PASS_WITH_LIMITS" if ok else "SELF_CHECK_FAIL",
        "checks": CHECKS,
        "checks_passed": "%d/%d" % (sum(1 for c in CHECKS if c["pass"]), len(CHECKS)),
        "blocking_failures": [c["id"] for c in CHECKS if not c["pass"]],
        "release_S05": False,
        "release_note": "自检不等同独立复核；V2 须经门审明确 release_S05 后才可开工。",
        "limits": [
            "未回读 PDF 原页；Q10 与 M12 的科目证据取自 A03 逐文档字段抽取记录，非人工翻页。",
            "Q10 把「科目在表内但无金额」按 0 计入比值，这是判据解释，已单列供门审确认；若改判 UNKNOWN，RH02 可判数会下降。",
            "M12 单边缺口 17 家不填零，全部不影响 RH03 判定（填零也不触发）。",
            "M08 只用 t；S04 冻结的 SG07 t-1y 依赖作为继承项单列，不计入 RH04。",
        ],
    }
    with open(os.path.join(HERE, "s05_v2_review.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(json.dumps({"checks_passed": out["checks_passed"], "decision": out["decision"],
                      "blocking": out["blocking_failures"]}, ensure_ascii=False))
    for c in CHECKS:
        if not c["pass"]:
            print("FAIL", c["id"], c["name"], json.dumps(c["detail"], ensure_ascii=False)[:500])
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
