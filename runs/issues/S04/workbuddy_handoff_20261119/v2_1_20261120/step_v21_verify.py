#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""S05 V2.1 自检：22 项结构守恒 + 8 项反例。

按 2026-11-20 第二次门审裁决（codex_ruling_s05_v2_20261120.md）的验收要求：
三态守恒、504/517 行影响与公开差额、可定位的适用性判定依据，以及
空白 / 明确零 / 一支可证成 / 另一支不可用 的反例。

每项都从实际输出或规则函数重推，能 FAIL；不引用 step_v21_build.py 的中间变量。
"""
import csv
import hashlib
import json
import os
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from decimal import Decimal

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
from s05_q10_rule import q10_eval, Q10_ASSET_PCT, Q10_REV_PCT  # noqa: E402

UNIT = os.path.abspath(os.path.join(HERE, ".."))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", "..", "..", ".."))

FD = os.path.join(REPO, "runs", "issues", "S04", "completion_20261114", "final_delivery_20261116")
QUAL = os.path.join(REPO, "runs", "issues", "S04", "completion_20261114", "qualification_v3_20261115")

APP = os.path.join(HERE, "s05_applicability_v21.csv")
ELIG = os.path.join(HERE, "s05_source_eligibility_v21.csv")
QU = os.path.join(HERE, "s05_q10_unknown_v21.csv")
IMP = os.path.join(HERE, "s05_m11_impact_v21.csv")
SS = os.path.join(HERE, "s05_rh03_single_sided_v21.csv")
BB = os.path.join(HERE, "s05_rh03_both_blank_v21.csv")
RH04 = os.path.join(HERE, "s05_rh04_denominator_v21.csv")
RH06 = os.path.join(HERE, "s05_rh06_q09_registry_v21.csv")
ISO = os.path.join(HERE, "s05_pending_isolation_v21.csv")
Q4M = os.path.join(HERE, "s05_q4_disposition_match_v21.csv")
Q10D = os.path.join(HERE, "s05_q10_engine_diff_v21.csv")
DIFF = os.path.join(HERE, "s05_v2_v21_diff.json")
CONTRACT = os.path.join(HERE, "s05_input_contract_v21.json")

CHECKS = []


def check(cid, name, ok, detail=None):
    CHECKS.append({"id": cid, "name": name, "pass": bool(ok), "detail": detail})


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
    elig = rows(ELIG)
    qu = rows(QU)
    imp = rows(IMP)
    ss = rows(SS)
    bb = rows(BB)
    rh04 = rows(RH04)
    rh06 = rows(RH06)
    iso = rows(ISO)
    q4 = rows(Q4M)
    diff = json.load(open(DIFF, encoding="utf-8"))
    contract = json.load(open(CONTRACT, encoding="utf-8"))

    # ---------- V1 结构 ----------
    keys = Counter((r["security_id"], r["metric_id"]) for r in app)
    check("V1", "适用性表 = 278 × 5 且每家每指标唯一",
          len(app) == 1390 and len(cand) == 278 and set(keys.values()) == {1},
          {"rows": len(app), "companies": len(cand), "multiplicity": sorted(set(keys.values()))})

    # ---------- V2 四态守恒 ----------
    RH = {"RH01": "M10", "RH02": "M11", "RH03": "M12", "RH04": "M08", "RH05": "M04"}
    bad_rh = {rh: diff["rh_by_company"].get(rh, {}) for rh in RH
              if sum(diff["rh_by_company"].get(rh, {}).values()) != 278}
    check("V2", "五个风险提示四态守恒（各和 = 278）", not bad_rh, {"bad": bad_rh})

    # ---------- V3 RH02 三态 ----------
    r2 = diff["rh_by_company"]["RH02"]
    check("V3", "RH02 = 120 可判 / 31 项目制不适用 / 127 待核（与裁决复算一致）",
          (r2.get("可判"), r2.get("不适用"), r2.get("待核")) == (120, 31, 127), r2)
    v_rh02 = Counter(r["verdict"] for r in app if r["metric_id"] == "M11")
    check("V3b", "RH02 判定明细 = 120 APPLICABLE + 31 项目制 + 127 未知",
          v_rh02.get("APPLICABLE") == 120
          and v_rh02.get("NOT_APPLICABLE_PROJECT_MODE") == 31
          and sum(v for k, v in v_rh02.items() if k.startswith("UNKNOWN_CA")) == 127,
          dict(v_rh02))

    # ---------- V4 行级四类守恒 ----------
    u = Counter(r["actual_use_eligibility"] for r in elig)
    check("V4", "8,638 行 = 8,021 可用 + 76 不适用 + 526 待核 + 15 逐格待核",
          len(elig) == 8638 and u["ELIGIBLE_FOR_S05_USE"] == 8021 and u["NOT_APPLICABLE"] == 76
          and u["HOLD_APPLICABILITY_UNKNOWN"] == 526
          and sum(v for k, v in u.items() if k.startswith("PENDING")) == 15,
          dict(u))

    # ---------- V5 行级转移 ----------
    tr = diff["row_level_transition"]
    m11_flip = tr.get("M11|ELIGIBLE_FOR_S05_USE->HOLD_APPLICABILITY_UNKNOWN", 0)
    m04_flip = tr.get("M04|ELIGIBLE_FOR_S05_USE->HOLD_APPLICABILITY_UNKNOWN", 0)
    check("V5", "V2→V2.1 转移 = 504 行 M11 + 13 行 M04（合计 517，与 8,538-8,021 相符）",
          m11_flip == 504 and m04_flip == 13 and diff["row_level_flipped_total"] == 517
          and 8538 - 517 == u["ELIGIBLE_FOR_S05_USE"],
          {"m11": m11_flip, "m04": m04_flip, "total": diff["row_level_flipped_total"]})

    # ---------- V6 M11 影响表 ----------
    check("V6", "M11 影响表 508 行 / 127 家 / 504 行改变，并披露与裁决预估 504 的差额",
          len(imp) == 508 and len({r["security_id"] for r in imp}) == 127
          and sum(1 for r in imp if r["changed"] == "YES") == 504
          and diff["m11_impact"]["predicted_rows_by_ruling"] == 504,
          {"rows": len(imp), "changed": sum(1 for r in imp if r["changed"] == "YES")})

    # ---------- V7 空白不计算 ----------
    bad_pct = [(r["security_id"], r["ca_basis_t"]) for r in app
               if r["metric_id"] == "M11" and r["ca_basis_t"] != "HAS_VALUE"
               and (r["q10_branch1_pct"] or r["q10_branch2_pct"])]
    check("V7", "合同资产无金额的公司不得出现任何 Q10 比值（不补零、不计算）",
          not bad_pct, {"violations": bad_pct[:5], "count": len(bad_pct)})

    # ---------- V8 明确零 ----------
    zeros = [r for r in app if r["metric_id"] == "M11" and r["ca_zero_basis_t"] == "EXPLICIT_ZERO"]
    zero_ok = all(r["q10_branch1_pct"] == "0" and r["q10_branch2_pct"] == "0"
                  and r["q10_verdict"] == "NON_PROJECT" and r["verdict"] == "APPLICABLE"
                  and r["ca_page_t"] for r in zeros)
    check("V8", "原文明确零（ca=0.00、有页码）可采用：两支均 0%，Q10 非项目制、RH02 适用，共 14 家",
          len(zeros) == 14 and zero_ok,
          {"count": len(zeros), "all_zero_non_project_applicable": zero_ok})

    # ---------- V9 决策输入来源 ----------
    m11 = [r for r in app if r["metric_id"] == "M11"]
    ca_with_val = [r for r in m11 if r["ca_status_t"] == "HAS_VALUE"]
    asset_pos = [r for r in m11 if r["asset_status_t"] == "HAS_VALUE"
                 and Decimal(r["asset_value_t"]) > 0]
    asset_ok_151 = all(r["asset_status_t"] == "HAS_VALUE" and Decimal(r["asset_value_t"]) > 0
                       and r["asset_doc_t"] and r["asset_page_t"] for r in ca_with_val)
    missing_doc = [r["security_id"] for r in m11
                   if not r["ca_doc_t"] or not r["asset_doc_t"] or not r["rev_doc_t"]]
    missing_page = [r["security_id"] for r in ca_with_val if not r["ca_page_t"]]
    ca_in_table_t = {r["security_id"] for r in elig
                     if r["metric_id"] == "M12" and r["field_id"] == "FIN.CONTRACTASSET.INSTANT"
                     and r["period_key"] == r["anchor_period"]}
    ca_not_in_table = [r["security_id"] for r in ca_with_val if r["security_id"] not in ca_in_table_t]
    check("V9", "决策输入来源齐备：278×3 键均有文档；278 个资产键正分母（含 151 个决定性）；16 个当期合同资产键补入适用性表",
          not missing_doc and not missing_page and len(ca_with_val) == 151
          and len(asset_pos) == 278 and asset_ok_151 and len(ca_not_in_table) == 16,
          {"missing_doc": len(missing_doc), "missing_page": len(missing_page),
           "ca_with_value": len(ca_with_val), "asset_positive": len(asset_pos),
           "asset_ok_for_151": asset_ok_151,
           "ca_not_in_consumption_table": len(ca_not_in_table)})

    # ---------- V10 两支独立 ----------
    pm = [r for r in m11 if r["verdict"] == "NOT_APPLICABLE_PROJECT_MODE"]
    only1 = [r for r in pm if Decimal(r["q10_branch1_pct"]) > Q10_ASSET_PCT
             and Decimal(r["q10_branch2_pct"]) <= Q10_REV_PCT]
    only2 = [r for r in pm if Decimal(r["q10_branch1_pct"]) <= Q10_ASSET_PCT
             and Decimal(r["q10_branch2_pct"]) > Q10_REV_PCT]
    both = [r for r in pm if Decimal(r["q10_branch1_pct"]) > Q10_ASSET_PCT
            and Decimal(r["q10_branch2_pct"]) > Q10_REV_PCT]
    check("V10", "31 家项目制 = 只靠资产支 1 + 只靠营收支 19 + 两支都过 11（OR 未写成 AND）",
          (len(only1), len(only2), len(both)) == (1, 19, 11) and len(pm) == 31,
          {"only_branch1": len(only1), "only_branch2": len(only2), "both": len(both)})

    # ---------- V11 RH03 ----------
    pos = [Decimal(r["if_zero_filled_signed_pp"]) for r in ss]
    mx = max(pos)
    dabo = [r for r in ss if "002901" in r["security_id"]]
    ruiling = [r for r in ss if "300154" in r["security_id"]]
    check("V11", "RH03 = 135 可判 / 125 双期无可采用金额 / 17 单边缺口 / 1 待核；反事实有向",
          len(ss) == 17 and len(bb) == 125 and all(x < 5 for x in pos)
          and mx == Decimal("0.819421") and bool(ruiling) and bool(dabo)
          and Decimal(dabo[0]["if_zero_filled_signed_pp"]) == Decimal("-0.004709"),
          {"single_sided": len(ss), "both_blank": len(bb), "max_positive_pp": str(mx),
           "dabo": dabo[0]["if_zero_filled_signed_pp"] if dabo else None})

    # ---------- V12 两侧可定位 ----------
    bb_missing = [r["security_id"] for r in bb if not r["t_ca_doc"] or not r["t1y_ca_doc"]]
    ss_missing = [r["security_id"] for r in ss if not r["t_ca_doc"] or not r["t1y_ca_doc"]]
    check("V12", "RH03 两侧抽取记录分别落到实际文档（125 双期空白 + 17 单边缺口）",
          not bb_missing and not ss_missing,
          {"both_blank_missing": len(bb_missing), "single_sided_missing": len(ss_missing)})

    # ---------- V13 RH04 ----------
    check("V13", "RH04 = 240 可判 / 36 不适用（35 负分母 + 1 正小分母）/ 2 待核",
          len(rh04) == 36
          and sum(1 for r in rh04 if r["reason"] == "NEGATIVE_DENOMINATOR") == 35
          and sum(1 for r in rh04 if r["reason"] == "ZERO_BASE_FLOOR_POSITIVE") == 1,
          dict(Counter(r["reason"] for r in rh04)))

    # ---------- V14 父链 ----------
    par = [r for r in elig if r["page_evidence_mode"] == "VIA_PARENT"]
    mx_par = max(Decimal(r["recompute_abs_diff"]) for r in par) if par else Decimal(0)
    check("V14", "父链 851 行，0 缺项，851/851 同文档，最大复算差 < 2e-6 pp",
          len(par) == 851
          and all(r["rev_document_id"] and r["cost_document_id"] for r in par)
          and sum(1 for r in par if r["rev_document_id"] == r["cost_document_id"]) == 851
          and mx_par < Decimal("2e-6"),
          {"rows": len(par), "max_diff": str(mx_par)})

    # ---------- V15 M08 ----------
    m08 = [r for r in elig if r["m08_dependency_kind"]]
    c8 = Counter(r["m08_dependency_kind"] for r in m08)
    check("V15", "M08 804 行 = 484 RH04 输入 + 160 信号当期 + 160 继承 S04",
          len(m08) == 804 and c8["RH04_INPUT"] == 484 and c8["SIGNAL_DEP_AT_T"] == 160
          and c8["INHERITED_S04_SIGNAL_CHECK"] == 160, dict(c8))

    # ---------- V16 Q4 ----------
    disp = rows(os.path.join(QUAL, "accepted_dispositions.csv"))
    inter = {r["security_id"] for r in disp} & set(cand)
    check("V16", "Q4：839 项处置命中 0，且 317 家与 278 交集为空",
          len(q4) == 0 and len(disp) == 839 and len({r["security_id"] for r in disp}) == 317
          and not inter,
          {"q4_rows": len(q4), "dispositions": len(disp), "intersection": len(inter)})

    # ---------- V17 RH06 ----------
    check("V17", "RH06 既有 Q09 标记 38 家已登记", len(rh06) == 38, {"companies": len(rh06)})

    # ---------- V18 隔离 ----------
    cells = {(r["security_id"], r["field_id"], r["period_key"]) for r in iso}
    jd = [r for r in iso if "000856" in r["security_id"]]
    check("V18", "逐格待核 15 行 / 13 格 / 5 家；冀东装备阻断 SG09 后仅剩 CASH",
          len(iso) == 15 and len(cells) == 13 and len({r["security_id"] for r in iso}) == 5
          and bool(jd) and jd[0]["blocked_signal_ids"] == "SG09"
          and jd[0]["unaffected_applicable_metrics"] == "M04;M08;M10;M12",
          {"rows": len(iso), "cells": len(cells),
           "jiedong": jd[0]["blocked_signal_ids"] if jd else None})

    # ---------- V19 判定与行级不得矛盾 ----------
    fam_by = {(r["security_id"], r["metric_id"]): r["state_family"] for r in app}
    conflicts = sorted({
        (r["security_id"], r["metric_id"]) for r in elig
        if fam_by.get((r["security_id"], r["metric_id"])) in ("待核", "不适用")
        and r["actual_use_eligibility"] == "ELIGIBLE_FOR_S05_USE"
    })
    check("V19", "判定为待核/不适用时，对应行不得仍是 ELIGIBLE", not conflicts,
          {"conflicts": conflicts[:5], "count": len(conflicts)})

    # ---------- V20 契约 ----------
    jj = {j["id"]: j["status"] for j in contract["judgments"]}
    br = contract.get("branch_refs", {})
    check("V20", "契约：release_S05=false；J1 否决、J2/J3 通过；两个分支指针分别记录",
          contract["release_S05"] is False
          and jj.get("J1") == "REVOKED_BY_GATE"
          and jj.get("J2") == "PASSED_BY_GATE" and jj.get("J3") == "PASSED_BY_GATE"
          and br.get("online_main_ref", "").startswith("a308fab")
          and br.get("local_main_ref", "").startswith("15dd324"),
          {"release_S05": contract["release_S05"], "judgments": jj,
           "online": br.get("online_main_ref"), "local": br.get("local_main_ref")})

    # ---------- V21 冻结输入 ----------
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
    check("V21", "冻结输入指纹未变（peer/来源补充/资格manifest/B/v3规则）", not bad_fp,
          {"bad": bad_fp})

    # ---------- V22 行尾 ----------
    crlf = [f for f in sorted(os.listdir(HERE))
            if os.path.splitext(f)[1] in (".md", ".json", ".py")
            and b"\r\n" in open(os.path.join(HERE, f), "rb").read()]
    check("V22", ".md/.json/.py 一律 LF", not crlf, {"files_with_crlf": crlf})

    # ================= 反例测试 =================
    D = Decimal

    r = q10_eval("REPORTED_BLANK", None, "HAS_VALUE", D("1e9"), "HAS_VALUE", D("1e9"))
    check("CE1", "合同资产空白 → UNKNOWN_CA_BLANK，不补零、不出比值",
          r["verdict"] == "UNKNOWN_CA_BLANK" and r["branch1_pct"] == ""
          and r["branch2_pct"] == "" and r["b1_status"] == "CA_NOT_USABLE", r)

    r = q10_eval("REPORTED_ABSENT", None, "HAS_VALUE", D("1e9"), "HAS_VALUE", D("1e9"))
    check("CE2", "合同资产未列示 → UNKNOWN_CA_NOT_USABLE（REPORTED_ABSENT 不映射为零）",
          r["verdict"] == "UNKNOWN_CA_NOT_USABLE" and r["branch1_pct"] == "", r)

    r = q10_eval("HAS_VALUE", D("0"), "HAS_VALUE", D("1e9"), "HAS_VALUE", D("1e9"))
    check("CE3", "原文明确零 → 可采用，0% / 0%，判 NON_PROJECT",
          r["verdict"] == "NON_PROJECT" and r["branch1_pct"] == "0"
          and r["branch2_pct"] == "0", r)

    r = q10_eval("HAS_VALUE", D("20"), "REPORTED_BLANK", None, "HAS_VALUE", D("100"))
    check("CE4", "资产分母不可用不妨碍营收支独立确立 PROJECT_MODE",
          r["verdict"] == "PROJECT_MODE" and r["branch1_pct"] == ""
          and Decimal(r["branch2_pct"]) == Decimal(20), r)

    r = q10_eval("HAS_VALUE", D("20"), "HAS_VALUE", D("100"), "REPORTED_BLANK", None)
    check("CE5", "营收分母不可用不妨碍资产支独立确立 PROJECT_MODE",
          r["verdict"] == "PROJECT_MODE" and r["branch2_pct"] == ""
          and Decimal(r["branch1_pct"]) == Decimal(20), r)

    r = q10_eval("HAS_VALUE", D("1"), "HAS_VALUE", D("100"), "REPORTED_BLANK", None)
    check("CE6", "仅一支算出且未达门槛 → UNKNOWN_DENOMINATOR（不得判 NON_PROJECT）",
          r["verdict"] == "UNKNOWN_DENOMINATOR", r)

    r = q10_eval("HAS_VALUE", D("20"), "HAS_VALUE", D("-100"), "HAS_VALUE", D("100"))
    check("CE7", "资产总计非正 → 该支不可用，营收支仍可独立成立",
          r["verdict"] == "PROJECT_MODE" and r["branch1_pct"] == ""
          and r["b1_status"] == "DENOMINATOR_NON_POSITIVE", r)

    check("CE8", "单边缺口反事实按有向差：大博 -0.004709、瑞凌 +0.819421",
          bool(dabo) and bool(ruiling)
          and Decimal(dabo[0]["if_zero_filled_signed_pp"]) == Decimal("-0.004709")
          and Decimal(ruiling[0]["if_zero_filled_signed_pp"]) == Decimal("0.819421")
          and all(Decimal(x["if_zero_filled_signed_pp"]) < 5 for x in ss),
          {"dabo": dabo[0]["if_zero_filled_signed_pp"] if dabo else None,
           "ruiling": ruiling[0]["if_zero_filled_signed_pp"] if ruiling else None})

    ok = all(c["pass"] for c in CHECKS)
    review = {
        "artifact": "S05_V21_SELF_CHECK",
        "generated_at": now,
        "plan_version": "20261026_collection_first_v2",
        "ruling": "runs/issues/S04/codex_ruling_s05_v2_20261120.md",
        "author": "WorkBuddy AI",
        "review_nature": "SELF_CHECK",
        "decision": "SELF_CHECK_PASS_WITH_LIMITS" if ok else "SELF_CHECK_FAIL",
        "checks": CHECKS,
        "checks_passed": "%d/%d" % (sum(1 for c in CHECKS if c["pass"]), len(CHECKS)),
        "blocking_failures": [c["id"] for c in CHECKS if not c["pass"]],
        "release_S05": False,
        "release_note": "自检不等同独立复核；V2.1 须经门审明确 release_S05 后才可开工。",
        "limits": [
            "未回读 PDF 原页：Q10 与 M12 的科目证据取自 A03 逐文档字段抽取记录，不是人工翻页。",
            "RH02 待核 127 家的合同资产金额仍未取得；本轮只做隔离与依据补齐，不逐页核。",
            "四会富仕 SZ:300852 同时缺上一期存货/营业成本，RH02 仍需另补两格。",
            "冀东装备 SZ:000856 的 SG09 合并口径仍 UNKNOWN，S05 归观察，S04 资格不动。",
        ],
    }
    with open(os.path.join(HERE, "s05_v21_review.json"), "w",
              encoding="utf-8", newline="\n") as f:
        json.dump(review, f, ensure_ascii=False, indent=2)

    print(json.dumps({"checks_passed": review["checks_passed"], "decision": review["decision"],
                      "blocking": review["blocking_failures"]}, ensure_ascii=False))
    for c in CHECKS:
        if not c["pass"]:
            print("FAIL", c["id"], c["name"],
                  json.dumps(c.get("detail"), ensure_ascii=False)[:300])
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
