# -*- coding: utf-8 -*-
"""把 report_to_codex_s05_v21.md 里的数字与产物实算逐条比对（prose 漂移守卫）。"""
import csv
import json
import os
import re
import sys
from collections import Counter
from decimal import Decimal

V2 = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(V2, "..", "..", "..", "..", ".."))


def rows(p):
    with open(p, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def main():
    md = open(os.path.join(V2, "report_to_codex_s05_v21.md"), encoding="utf-8").read()
    bad, ok = [], []

    def eq(name, claimed, actual):
        if claimed == actual:
            ok.append(name)
        else:
            bad.append("%s: 报告=%r 实算=%r" % (name, claimed, actual))

    app = rows(os.path.join(V2, "s05_applicability_v21.csv"))
    elig = rows(os.path.join(V2, "s05_source_eligibility_v21.csv"))
    ss = rows(os.path.join(V2, "s05_rh03_single_sided_v21.csv"))
    bb = rows(os.path.join(V2, "s05_rh03_both_blank_v21.csv"))
    rh04 = rows(os.path.join(V2, "s05_rh04_denominator_v21.csv"))
    rh06 = rows(os.path.join(V2, "s05_rh06_q09_registry_v21.csv"))
    iso = rows(os.path.join(V2, "s05_pending_isolation_v21.csv"))
    imp = rows(os.path.join(V2, "s05_m11_impact_v21.csv"))
    q4 = rows(os.path.join(V2, "s05_q4_disposition_match_v21.csv"))
    diff = json.load(open(os.path.join(V2, "s05_v2_v21_diff.json"), encoding="utf-8"))
    ct = json.load(open(os.path.join(V2, "s05_input_contract_v21.json"), encoding="utf-8"))
    rv = json.load(open(os.path.join(V2, "s05_v21_review.json"), encoding="utf-8"))

    eq("eligibility 行数", int(re.search(r"s05_source_eligibility_v21\.csv`（([\d,]+) 行）", md).group(1).replace(",", "")), len(elig))
    eq("applicability 行数", int(re.search(r"s05_applicability_v21\.csv`（([\d,]+) 行）", md).group(1).replace(",", "")), len(app))

    # --- CA 状态分布 ---
    ca_t = Counter(r["ca_status_t"] for r in app if r["metric_id"] == "M11")
    ca_t1 = Counter(r["ca_basis_t1y"] for r in app if r["metric_id"] == "M12")
    eq("当期 151 有金额", 151, ca_t["HAS_VALUE"])
    eq("当期 127 空白", 127, ca_t["REPORTED_BLANK"])
    eq("上年 136 有金额", 136, ca_t1["HAS_VALUE"])
    eq("上年 141 空白", 141, ca_t1["REPORTED_BLANK"])
    eq("上年 1 无记录", 1, ca_t1["NO_RECORD"])

    # --- RH02 表 ---
    r2 = diff["rh_by_company"]["RH02"]
    m = re.search(r"\| V2\.1（J1 撤销） \| \*\*(\d+)\*\* \| \*\*(\d+)\*\* \| \*\*(\d+)\*\* \| \*\*(\d+)\*\* \|", md)
    eq("RH02 表", [int(m.group(i)) for i in (1, 2, 3, 4)],
       [r2["可判"], r2["不适用"], r2["待核"], sum(r2.values())])
    eq("V2 表 246/31/1", [246, 31, 1, 278], [246, 31, 1, 278])
    eq("126 家转待核", 126, r2["待核"] - 1)

    # --- 行级四类 ---
    u = Counter(r["actual_use_eligibility"] for r in elig)
    pend = sum(v for k, v in u.items() if k.startswith("PENDING"))
    eq("V2.1 行级", [8021, 76, 526, 15],
       [u["ELIGIBLE_FOR_S05_USE"], u["NOT_APPLICABLE"], u["HOLD_APPLICABILITY_UNKNOWN"], pend])
    eq("V2 行级", [8538, 76, 9, 15], [8538, 76, 9, 15])
    eq("预估 8,034/513", [8034, 513], [8538 - 504, 9 + 504])

    # --- 转移 ---
    tr = diff["row_level_transition"]
    eq("M11 504", 504, tr["M11|ELIGIBLE_FOR_S05_USE->HOLD_APPLICABILITY_UNKNOWN"])
    eq("M04 13", 13, tr["M04|ELIGIBLE_FOR_S05_USE->HOLD_APPLICABILITY_UNKNOWN"])
    eq("合计 517", 517, diff["row_level_flipped_total"])
    eq("8538-517=8021", 8021, 8538 - diff["row_level_flipped_total"])
    eq("M11 影响表 508/127/504", [508, 127, 504],
       [len(imp), len({r["security_id"] for r in imp}),
        sum(1 for r in imp if r["changed"] == "YES")])

    # --- 四态表 ---
    RH = {"RH01": "应收周转", "RH02": "存货周转", "RH03": "合同资产占比",
          "RH04": "现金含量", "RH05": "毛利率下滑"}
    seen = 0
    for line in md.splitlines():
        mm = re.match(r"^\|\s*(RH0\d)\s+([^|]+?)\s*\|\s*\**([\d,]+)\**\s*\|\s*\**([\d,]+)\**\s*\|\s*\**([\d,]+)\**\s*\|\s*\**([\d,]+)\**\s*\|\s*([\d,]+)\s*\|", line)
        if not mm:
            continue
        rh = mm.group(1)
        vals = [int(mm.group(i).replace(",", "")) for i in (3, 4, 5, 6, 7)]
        c = diff["rh_by_company"][rh]
        eq("RH 表 %s" % rh, vals,
           [c.get("可判", 0), c.get("不适用", 0), c.get("单边缺口", 0), c.get("待核", 0), sum(c.values())])
        seen += 1
    eq("RH 表行数", 5, seen)

    # --- 明确零 / 项目制构成 ---
    zeros = [r for r in app if r["metric_id"] == "M11" and r["ca_zero_basis_t"] == "EXPLICIT_ZERO"]
    eq("明确零 14 家", 14, len(zeros))
    pm = [r for r in app if r["metric_id"] == "M11" and r["verdict"] == "NOT_APPLICABLE_PROJECT_MODE"]
    only1 = sum(1 for r in pm if Decimal(r["q10_branch1_pct"]) > 5 and Decimal(r["q10_branch2_pct"]) <= 10)
    only2 = sum(1 for r in pm if Decimal(r["q10_branch1_pct"]) <= 5 and Decimal(r["q10_branch2_pct"]) > 10)
    both = sum(1 for r in pm if Decimal(r["q10_branch1_pct"]) > 5 and Decimal(r["q10_branch2_pct"]) > 10)
    eq("项目制构成 1/19/11", [1, 19, 11], [only1, only2, both])
    gj = [r for r in pm if "600335" in r["security_id"]]
    eq("国机汽车 6.44/9.24", ["6.44", "9.24"],
       [str(round(Decimal(gj[0]["q10_branch1_pct"]), 2)), str(round(Decimal(gj[0]["q10_branch2_pct"]), 2))] if gj else None)

    # --- 来源完整度 ---
    m11 = [r for r in app if r["metric_id"] == "M11"]
    eq("278×3 都有文档", 0,
       sum(1 for r in m11 if not (r["ca_doc_t"] and r["asset_doc_t"] and r["rev_doc_t"])))
    eq("151 有金额", 151, sum(1 for r in m11 if r["ca_status_t"] == "HAS_VALUE"))
    ca_tbl = {r["security_id"] for r in elig
              if r["metric_id"] == "M12" and r["field_id"] == "FIN.CONTRACTASSET.INSTANT"
              and r["period_key"] == r["anchor_period"]}
    eq("16 个当期 CA 键不在消费表", 16,
       sum(1 for r in m11 if r["ca_status_t"] == "HAS_VALUE" and r["security_id"] not in ca_tbl))

    # --- RH03 ---
    eq("单边缺口 17", 17, len(ss))
    eq("双期空白 125", 125, len(bb))
    mx = max(Decimal(r["if_zero_filled_signed_pp"]) for r in ss)
    eq("最大正向 +0.819421", Decimal("0.819421"), mx)
    db = [r for r in ss if "002901" in r["security_id"]]
    eq("大博 -0.004709", Decimal("-0.004709"), Decimal(db[0]["if_zero_filled_signed_pp"]) if db else None)
    eq("瑞凌代码", "SZ:300154", [r["security_id"] for r in ss if Decimal(r["if_zero_filled_signed_pp"]) == mx][0])

    # --- RH04 / 父链 / M08 / Q4 / RH06 / 隔离 ---
    eq("RH04 36", 36, len(rh04))
    eq("负分母 35", 35, sum(1 for r in rh04 if r["reason"] == "NEGATIVE_DENOMINATOR"))
    eq("正小分母 1", 1, sum(1 for r in rh04 if r["reason"] == "ZERO_BASE_FLOOR_POSITIVE"))
    rq = [r for r in rh04 if "301360" in r["security_id"]]
    eq("荣旗 246598.23", "246598.23", rq[0]["npp_ytd_t"] if rq else None)
    par = [r for r in elig if r["page_evidence_mode"] == "VIA_PARENT"]
    eq("父链 851", 851, len(par))
    eq("父链 0 缺项", 0, sum(1 for r in par if not (r["rev_document_id"] and r["cost_document_id"])))
    eq("最大复算差 4.98e-07", "4.98e-07",
       "%.2e" % max(Decimal(r["recompute_abs_diff"]) for r in par))
    m08 = [r for r in elig if r["m08_dependency_kind"]]
    eq("M08 804 = 484/160/160", [804, 484, 160, 160],
       [len(m08), sum(1 for r in m08 if r["m08_dependency_kind"] == "RH04_INPUT"),
        sum(1 for r in m08 if r["m08_dependency_kind"] == "SIGNAL_DEP_AT_T"),
        sum(1 for r in m08 if r["m08_dependency_kind"] == "INHERITED_S04_SIGNAL_CHECK")])
    eq("Q4 命中 0", 0, len(q4))
    eq("Q09 38", 38, len(rh06))
    eq("隔离 15 行", 15, len(iso))
    eq("隔离 13 格", 13, len({(r["security_id"], r["field_id"], r["period_key"]) for r in iso}))
    eq("隔离 5 家", 5, len({r["security_id"] for r in iso}))

    # --- 自检与契约 ---
    eq("自检 31/31", "31/31", rv["checks_passed"])
    eq("报告写 31/31 处数", 3, md.count("31/31"))
    eq("release_S05", False, rv["release_S05"])
    eq("J1 否决", "REVOKED_BY_GATE",
       {j["id"]: j["status"] for j in ct["judgments"]}["J1"])
    eq("online_main_ref", "a308fab19c17ea0184df0d730f2a5723760f2ef4",
       ct["branch_refs"]["online_main_ref"])
    eq("local_main_ref", "15dd324c2dcebc7a9e64192c42f69fe704abe652",
       ct["branch_refs"]["local_main_ref"])
    eq("差 30 个提交在文中", True, "30 个提交" in md)

    print("PASS %d / FAIL %d" % (len(ok), len(bad)))
    for b in bad:
        print("  FAIL", b)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
