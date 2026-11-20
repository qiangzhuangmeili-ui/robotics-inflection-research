#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""S05 V2.2 自检：25 项结构守恒 + 13 项反例。

按 2026-11-20 第三次门审裁决（codex_ruling_s05_v21_20261120.md）的验收要求：
三格来源不准入登记、Q10/RH03 共用来源资格、四例+一正例回归、
RH02 118/31/129 与 RH03 133/126/18/1 的实算回填。

每项都从实际输出或规则函数重推，能 FAIL；不引用 step_v22_build.py 的中间变量。
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
from s05_ca_source_rule import (  # noqa: E402
    q10_eval, Q10_ASSET_PCT, Q10_REV_PCT, NON_ADMISSIBLE_CA,
    ca_source_admissible, classify_amount_column)

UNIT = os.path.abspath(os.path.join(HERE, ".."))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", "..", "..", ".."))

FD = os.path.join(REPO, "runs", "issues", "S04", "completion_20261114", "final_delivery_20261116")
QUAL = os.path.join(REPO, "runs", "issues", "S04", "completion_20261114", "qualification_v3_20261115")
COLL = os.path.join(REPO, "runs", "collection", "collection_index.csv")

APP = os.path.join(HERE, "s05_applicability_v22.csv")
ELIG = os.path.join(HERE, "s05_source_eligibility_v22.csv")
QU = os.path.join(HERE, "s05_q10_unknown_v22.csv")
TRANS = os.path.join(HERE, "s05_row_transition_v21_v22.csv")
SS = os.path.join(HERE, "s05_rh03_single_sided_v22.csv")
BB = os.path.join(HERE, "s05_rh03_both_blank_v22.csv")
RH04 = os.path.join(HERE, "s05_rh04_denominator_v22.csv")
RH06 = os.path.join(HERE, "s05_rh06_q09_registry_v22.csv")
ISO = os.path.join(HERE, "s05_pending_isolation_v22.csv")
Q4M = os.path.join(HERE, "s05_q4_disposition_match_v22.csv")
NONADM = os.path.join(HERE, "s05_ca_source_nonadmission_v22.csv")
REG = os.path.join(HERE, "s05_ca_column_regression_v22.csv")
DIFF = os.path.join(HERE, "s05_v21_v22_diff.json")
CONTRACT = os.path.join(HERE, "s05_input_contract_v22.json")

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
    trans = rows(TRANS)
    ss = rows(SS)
    bb = rows(BB)
    rh04 = rows(RH04)
    rh06 = rows(RH06)
    iso = rows(ISO)
    q4 = rows(Q4M)
    nonadm = rows(NONADM)
    reg = rows(REG)
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
    check("V3", "RH02 = 118 可判 / 31 项目制不适用 / 129 待核（与裁决复算一致）",
          (r2.get("可判"), r2.get("不适用"), r2.get("待核")) == (118, 31, 129), r2)
    v_rh02 = Counter(r["verdict"] for r in app if r["metric_id"] == "M11")
    unk = sum(v for k, v in v_rh02.items() if k.startswith("UNKNOWN_CA"))
    check("V3b", "RH02 判定明细 = 118 APPLICABLE + 31 项目制 + 129 未知（127 空白 + 2 来源不准入）",
          v_rh02.get("APPLICABLE") == 118
          and v_rh02.get("NOT_APPLICABLE_PROJECT_MODE") == 31
          and unk == 129
          and v_rh02.get("UNKNOWN_CA_BLANK") == 127
          and v_rh02.get("UNKNOWN_CA_SOURCE_NOT_ADMISSIBLE") == 2,
          dict(v_rh02))

    # ---------- V4 行级四类守恒 ----------
    u = Counter(r["actual_use_eligibility"] for r in elig)
    check("V4", "8,638 行 = 8,005 可用 + 76 不适用 + 534 适用性待核 + 15 逐格待核",
          len(elig) == 8638 and u["ELIGIBLE_FOR_S05_USE"] == 8005 and u["NOT_APPLICABLE"] == 76
          and u["HOLD_APPLICABILITY_UNKNOWN"] == 534
          and sum(v for k, v in u.items() if k.startswith("PENDING")) == 15,
          dict(u))

    # ---------- V5 行级转移 ----------
    tr = diff["row_level_transition"]
    m11_flip = tr.get("M11|ELIGIBLE_FOR_S05_USE->HOLD_APPLICABILITY_UNKNOWN", 0)
    m12_flip = tr.get("M12|ELIGIBLE_FOR_S05_USE->HOLD_SINGLE_SIDED_GAP", 0)
    check("V5", "V2.1→V2.2 转移 = 8 行 M11 + 8 行 M12（合计 16，与 8,021-8,005 相符）",
          m11_flip == 8 and m12_flip == 8 and diff["row_level_flipped_total"] == 16
          and 8021 - 16 == u["ELIGIBLE_FOR_S05_USE"],
          {"m11": m11_flip, "m12": m12_flip, "total": diff["row_level_flipped_total"]})

    # ---------- V6 转移表只落在三家公司 ----------
    tcomp = {r["security_id"] for r in trans}
    check("V6", "行级转移 16 行仅涉卓翼/银宝/胜蓝三家，不扩散到其他公司",
          len(trans) == 16 and tcomp == {"SZ:002369", "SZ:002786", "SZ:300843"}
          and sum(1 for r in trans if r["metric_id"] == "M11") == 8
          and sum(1 for r in trans if r["metric_id"] == "M12") == 8,
          {"rows": len(trans), "companies": sorted(tcomp)})

    # ---------- V7 空白/不准入不计算 ----------
    bad_pct = [(r["security_id"], r["ca_basis_t"]) for r in app
               if r["metric_id"] == "M11" and r["ca_basis_t"] != "HAS_VALUE"
               and (r["q10_branch1_pct"] or r["q10_branch2_pct"])]
    check("V7", "合同资产无金额或来源不准入的公司不得出现任何 Q10 比值（不补零、不计算）",
          not bad_pct, {"violations": bad_pct[:5], "count": len(bad_pct)})

    # ---------- V8 明确零（13 条期末栏零值保留）----------
    zeros = [r for r in app if r["metric_id"] == "M11" and r["ca_zero_basis_t"] == "EXPLICIT_ZERO"]
    zero_ok = all(r["q10_branch1_pct"] == "0" and r["q10_branch2_pct"] == "0"
                  and r["q10_verdict"] == "NON_PROJECT" and r["verdict"] == "APPLICABLE"
                  and r["ca_page_t"] for r in zeros)
    check("V8", "原文期末栏明确零可采用：两支均 0%、Q10 非项目制、RH02 适用，共 13 家（原 14 减卓翼 1）",
          len(zeros) == 13 and zero_ok,
          {"count": len(zeros), "all_zero_non_project_applicable": zero_ok})

    # ---------- V9 决策输入来源 ----------
    m11 = [r for r in app if r["metric_id"] == "M11"]
    ca_with_val = [r for r in m11 if r["ca_status_t"] == "HAS_VALUE"]
    asset_pos = [r for r in m11 if r["asset_status_t"] == "HAS_VALUE"
                 and Decimal(r["asset_value_t"]) > 0]
    asset_ok_all = all(r["asset_status_t"] == "HAS_VALUE" and Decimal(r["asset_value_t"]) > 0
                       and r["asset_doc_t"] and r["asset_page_t"] for r in ca_with_val)
    missing_doc = [r["security_id"] for r in m11
                   if not r["ca_doc_t"] or not r["asset_doc_t"] or not r["rev_doc_t"]]
    missing_page = [r["security_id"] for r in ca_with_val if not r["ca_page_t"]]
    ca_in_table_t = {r["security_id"] for r in elig
                     if r["metric_id"] == "M12" and r["field_id"] == "FIN.CONTRACTASSET.INSTANT"
                     and r["period_key"] == r["anchor_period"]}
    ca_not_in_table = [r["security_id"] for r in ca_with_val if r["security_id"] not in ca_in_table_t]
    check("V9", "决策输入来源齐备：278×3 键均有文档；278 个资产键正分母；149 个可用合同资产键有页，15 个补入适用性表",
          not missing_doc and not missing_page and len(ca_with_val) == 149
          and len(asset_pos) == 278 and asset_ok_all and len(ca_not_in_table) == 15,
          {"missing_doc": len(missing_doc), "missing_page": len(missing_page),
           "ca_with_value": len(ca_with_val), "asset_positive": len(asset_pos),
           "asset_ok_for_all": asset_ok_all,
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
    r3 = diff["rh_by_company"]["RH03"]
    check("V11", "RH03 = 133 可判 / 126 双期无可采用金额 / 18 单边缺口 / 1 待核；反事实有向",
          len(ss) == 18 and len(bb) == 126
          and (r3.get("可判"), r3.get("不适用"), r3.get("单边缺口"), r3.get("待核")) == (133, 126, 18, 1)
          and all(x < 5 for x in pos)
          and mx == Decimal("0.819421") and bool(ruiling) and bool(dabo)
          and Decimal(dabo[0]["if_zero_filled_signed_pp"]) == Decimal("-0.004709"),
          {"single_sided": len(ss), "both_blank": len(bb), "max_positive_pp": str(mx),
           "dabo": dabo[0]["if_zero_filled_signed_pp"] if dabo else None})

    # ---------- V12 两侧可定位 ----------
    bb_missing = [r["security_id"] for r in bb if not r["t_ca_doc"] or not r["t1y_ca_doc"]]
    ss_missing = [r["security_id"] for r in ss if not r["t_ca_doc"] or not r["t1y_ca_doc"]]
    check("V12", "RH03 两侧抽取记录分别落到实际文档（126 双期无可采用金额 + 18 单边缺口）",
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
    check("V20", "契约：release_S05=false；J1 否决、J2/J3 通过、J4 本轮采用；两个分支指针分别记录",
          contract["release_S05"] is False
          and jj.get("J1") == "REVOKED_BY_GATE"
          and jj.get("J2") == "PASSED_BY_GATE" and jj.get("J3") == "PASSED_BY_GATE"
          and jj.get("J4") == "ADOPTED_BY_THIS_ROUND"
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

    # ---------- V23 来源不准入登记表 ----------
    coll_sha = {}
    for r in rows(COLL):
        if r.get("document_id"):
            coll_sha.setdefault(r["document_id"], r.get("sha256", ""))
    sha_ok = all(r["document_sha256"] == coll_sha.get(r["document_id"], "")
                 for r in nonadm)
    check("V23", "登记表 3 格：文档 SHA-256 与 collection_index 一致、底表未覆盖、四元组键齐备",
          len(nonadm) == 3 and sha_ok
          and all(r["base_table_overwritten"] == "NO" for r in nonadm)
          and all(r["gate_applied"] == "YES" for r in nonadm)
          and all(r["b_value_raw"] for r in nonadm)
          and len({(r["security_id"], r["field_id"], r["period_key"],
                    r["document_sha256"]) for r in nonadm}) == 3,
          {"rows": len(nonadm), "sha_ok": sha_ok,
           "defects": [r["defect_class"] for r in nonadm]})

    # ---------- V24 列归属回归 ----------
    check("V24", "回归 6 例（四类 + 一正例 + 并排两期）：列归属 6/6、准入 6/6、规则落到输出 6/6",
          len(reg) == 6
          and all(r["column_agrees"] == "YES" for r in reg)
          and all(r["admission_agrees"] == "YES" for r in reg)
          and all(r["rule_applied_to_output"] == "YES" for r in reg),
          {"cases": len(reg),
           "column_agrees": sum(1 for r in reg if r["column_agrees"] == "YES"),
           "rule_applied": sum(1 for r in reg if r["rule_applied_to_output"] == "YES")})

    # ---------- V25 三格判定与裁决一致 ----------
    a = {(r["security_id"], r["metric_id"]): r for r in app}
    zy11 = a[("SZ:002369", "M11")]["verdict"]
    zy12 = a[("SZ:002369", "M12")]["verdict"]
    yb11 = a[("SZ:002786", "M11")]["verdict"]
    yb12 = a[("SZ:002786", "M12")]["verdict"]
    sl11 = a[("SZ:300843", "M11")]["verdict"]
    sl12 = a[("SZ:300843", "M12")]["verdict"]
    check("V25", "三格后果：卓翼 Q10 未知+RH03 双期无可采用金额；银宝 Q10 未知+RH03 单边；胜蓝当期保留、基期转单边",
          zy11 == "UNKNOWN_CA_SOURCE_NOT_ADMISSIBLE"
          and zy12 == "BOTH_BLANK_NO_USABLE_AMOUNT"
          and yb11 == "UNKNOWN_CA_SOURCE_NOT_ADMISSIBLE"
          and yb12 == "SINGLE_SIDED_GAP"
          and sl11 == "APPLICABLE" and sl12 == "SINGLE_SIDED_GAP",
          {"zhuoyi": [zy11, zy12], "yinbao": [yb11, yb12], "shenglan": [sl11, sl12]})

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

    # CE9–CE13：来源资格门槛本身
    blocked = []
    for rec in NON_ADMISSIBLE_CA:
        ok, hit = ca_source_admissible(rec["security_id"], rec["field_id"],
                                       rec["period_key"], rec["document_sha256"])
        blocked.append(not ok and hit is not None)
    check("CE9", "三格按四元组命中登记表 → 来源不准入", all(blocked) and len(blocked) == 3,
          {"blocked": blocked})

    rec0 = NON_ADMISSIBLE_CA[0]
    ok_other, _ = ca_source_admissible(rec0["security_id"], rec0["field_id"],
                                       rec0["period_key"], "0" * 64)
    ok_period, _ = ca_source_admissible(rec0["security_id"], rec0["field_id"],
                                        "20250630", rec0["document_sha256"])
    check("CE10", "换 SHA 或换期间即不再命中（登记是版本与期间绑定的，不泛化）",
          ok_other is True and ok_period is True,
          {"other_sha": ok_other, "other_period": ok_period})

    check("CE11", "列归属判定：期末空期初零/期初非零 → BEGIN；期末栏零 → END；并排左列 → END",
          classify_amount_column(510, 274, 435) == "BEGIN"
          and classify_amount_column(480, 285, 446) == "BEGIN"
          and classify_amount_column(523, 285, 446) == "BEGIN"
          and classify_amount_column(357, 280, 440) == "END"
          and classify_amount_column(170, 167, 245) == "END"
          and classify_amount_column(182, 180, 247) == "END",
          {"end_zero": classify_amount_column(357, 280, 440),
           "opening": classify_amount_column(510, 274, 435)})

    r = q10_eval("SOURCE_NOT_ADMISSIBLE", None, "HAS_VALUE", D("1e9"), "HAS_VALUE", D("1e9"))
    check("CE12", "来源不准入 → UNKNOWN_CA_SOURCE_NOT_ADMISSIBLE，两支都不出数",
          r["verdict"] == "UNKNOWN_CA_SOURCE_NOT_ADMISSIBLE"
          and r["branch1_pct"] == "" and r["branch2_pct"] == ""
          and r["b1_status"] == "CA_NOT_USABLE", r)

    sl = a[("SZ:300843", "M11")]
    slz = a[("SZ:300843", "M12")]
    check("CE13", "胜蓝当期期末栏 0.00 保留：Q10 判非项目制、RH03 当期侧仍是可采值，只有基期被撤销",
          sl["q10_verdict"] == "NON_PROJECT" and sl["q10_branch1_pct"] == "0"
          and sl["ca_basis_t"] == "HAS_VALUE"
          and slz["ca_basis_t"] == "HAS_VALUE"
          and slz["ca_basis_t1y"] == "SOURCE_NOT_ADMISSIBLE",
          {"q10": sl["q10_verdict"], "t": slz["ca_basis_t"], "t1y": slz["ca_basis_t1y"]})

    ok = all(c["pass"] for c in CHECKS)
    review = {
        "artifact": "S05_V22_SELF_CHECK",
        "generated_at": now,
        "plan_version": "20261026_collection_first_v2",
        "ruling": "runs/issues/S04/codex_ruling_s05_v21_20261120.md",
        "author": "WorkBuddy AI",
        "review_nature": "SELF_CHECK",
        "decision": "SELF_CHECK_PASS_WITH_LIMITS" if ok else "SELF_CHECK_FAIL",
        "checks": CHECKS,
        "checks_passed": "%d/%d" % (sum(1 for c in CHECKS if c["pass"]), len(CHECKS)),
        "blocking_failures": [c["id"] for c in CHECKS if not c["pass"]],
        "release_S05": False,
        "release_note": "自检不等同独立复核；V2.2 须经门审明确 release_S05 后才可开工。",
        "limits": [
            "本轮只回读三格原页（卓翼 p39、银宝 p38、胜蓝 p50/p47），其余 127 家空白原页未核。",
            "胜蓝的错表结论依赖页标题识别（母公司 vs 合并），未逐行比对两张表全部科目。",
            "RH02 待核 129 家的合同资产金额仍未取得，只做隔离与依据补齐。",
            "四会富仕 SZ:300852 同时缺上一期存货/营业成本，RH02 仍需另补两格。",
            "冀东装备 SZ:000856 的 SG09 合并口径仍 UNKNOWN，S05 归观察，S04 资格不动。",
        ],
    }
    with open(os.path.join(HERE, "s05_v22_review.json"), "w",
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
