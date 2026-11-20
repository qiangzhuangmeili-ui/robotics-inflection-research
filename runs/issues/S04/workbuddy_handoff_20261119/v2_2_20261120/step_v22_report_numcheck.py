# -*- coding: utf-8 -*-
"""把 report_to_codex_s05_v22.md 里的数字与产物实算逐条比对（prose 漂移守卫）。

任何一处报告数字与产物不一致即 FAIL；报告里每张表都按标签定位后逐格取数，
不靠人工抄写。
"""
import csv
import json
import os
import re
import sys
from collections import Counter
from decimal import Decimal

V2 = os.path.dirname(os.path.abspath(__file__))


def rows(p):
    with open(p, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def main():
    md = open(os.path.join(V2, "report_to_codex_s05_v22.md"), encoding="utf-8").read()
    bad, ok = [], []

    def eq(name, claimed, actual):
        if claimed == actual:
            ok.append(name)
        else:
            bad.append("%s: 报告=%r 实算=%r" % (name, claimed, actual))

    def ints(text):
        return [int(x.replace(",", "")) for x in re.findall(r"[\d,]+", text)]

    def cells(label):
        """取以 label 开头的第一个表格行，返回标签之后的纯数字单元格。"""
        for ln in md.splitlines():
            if ln.startswith(label):
                out = []
                for c in ln.split("|")[2:]:
                    c = c.strip().replace("*", "").replace(",", "")
                    if re.fullmatch(r"\d+", c):
                        out.append(int(c))
                return out
        return []

    def line_after(label):
        """取以 label 开头的第一个表格行（原样）。"""
        for ln in md.splitlines():
            if ln.startswith(label):
                return ln
        return ""

    app = rows(os.path.join(V2, "s05_applicability_v22.csv"))
    elig = rows(os.path.join(V2, "s05_source_eligibility_v22.csv"))
    ss = rows(os.path.join(V2, "s05_rh03_single_sided_v22.csv"))
    bb = rows(os.path.join(V2, "s05_rh03_both_blank_v22.csv"))
    rh04 = rows(os.path.join(V2, "s05_rh04_denominator_v22.csv"))
    rh06 = rows(os.path.join(V2, "s05_rh06_q09_registry_v22.csv"))
    iso = rows(os.path.join(V2, "s05_pending_isolation_v22.csv"))
    trans = rows(os.path.join(V2, "s05_row_transition_v21_v22.csv"))
    q4 = rows(os.path.join(V2, "s05_q4_disposition_match_v22.csv"))
    nonadm = rows(os.path.join(V2, "s05_ca_source_nonadmission_v22.csv"))
    reg = rows(os.path.join(V2, "s05_ca_column_regression_v22.csv"))
    diff = json.load(open(os.path.join(V2, "s05_v21_v22_diff.json"), encoding="utf-8"))
    ct = json.load(open(os.path.join(V2, "s05_input_contract_v22.json"), encoding="utf-8"))
    rv = json.load(open(os.path.join(V2, "s05_v22_review.json"), encoding="utf-8"))

    # --- 文件行数 ---
    eq("eligibility 行数", int(re.search(
        r"s05_source_eligibility_v22\.csv`（([\d,]+) 行）", md).group(1).replace(",", "")), len(elig))
    eq("applicability 行数", int(re.search(
        r"s05_applicability_v22\.csv`（([\d,]+) 行）", md).group(1).replace(",", "")), len(app))
    eq("登记表行数", int(re.search(
        r"s05_ca_source_nonadmission_v22\.csv`（([\d,]+) 行）", md).group(1).replace(",", "")), len(nonadm))
    eq("回归表行数", int(re.search(
        r"s05_ca_column_regression_v22\.csv`（([\d,]+) 行）", md).group(1).replace(",", "")), len(reg))

    # --- RH02 / RH03 对比表 ---
    r2 = diff["rh_by_company"]["RH02"]
    r3 = diff["rh_by_company"]["RH03"]
    eq("RH02 V2.1 行", cells("| V2.1 |"), [120, 31, 127, 278])
    eq("RH02 V2.2 行", cells("| **V2.2 实际** |"), 
       [r2["可判"], r2["不适用"], r2["待核"], sum(r2.values())])
    eq("RH02 预估行", cells("| 你的预估 |"), [118, 31, 129, 278])
    eq("RH03 V2.1 行", cells("| V2.1 | 135"), [135, 125, 17, 1, 278])
    eq("RH03 V2.2 行", cells("| **V2.2 实际** | **133**"),
       [r3["可判"], r3["不适用"], r3["单边缺口"], r3["待核"], sum(r3.values())])
    eq("RH03 预估行", cells("| 你的预估 | 133"), [133, 126, 18, 1, 278])

    # --- 行级表 ---
    u = Counter(r["actual_use_eligibility"] for r in elig)
    pend = sum(v for k, v in u.items() if k.startswith("PENDING"))
    eq("行级 V2.1 行", cells("| V2.1 | 8,021"), [8021, 76, 526, 0, 15, 8638])
    eq("行级 V2.2 行", cells("| **V2.2 实际** | **8,005**"),
       [u["ELIGIBLE_FOR_S05_USE"], u["NOT_APPLICABLE"], u["HOLD_APPLICABILITY_UNKNOWN"],
        u["HOLD_SINGLE_SIDED_GAP"], pend, len(elig)])
    eq("8021-16=8005", 8005, 8021 - diff["row_level_flipped_total"])

    # --- 转移表 ---
    tr = diff["row_level_transition"]
    eq("M11 转移 8", 8, tr["M11|ELIGIBLE_FOR_S05_USE->HOLD_APPLICABILITY_UNKNOWN"])
    eq("M12 转移 8", 8, tr["M12|ELIGIBLE_FOR_S05_USE->HOLD_SINGLE_SIDED_GAP"])
    eq("转移合计 16", 16, diff["row_level_flipped_total"])
    eq("转移表 16 行", 16, len(trans))
    eq("转移只涉三家", 3, len({r["security_id"] for r in trans}))

    # --- 四态表 ---
    seen = 0
    for line in md.splitlines():
        mm = re.match(r"^\|\s*(RH0\d)\s+([^|]+?)\s*\|\s*\**([\d,]+)\**\s*\|\s*\**([\d,]+)\**\s*"
                      r"\|\s*\**([\d,]+)\**\s*\|\s*\**([\d,]+)\**\s*\|\s*([\d,]+)\s*\|", line)
        if not mm:
            continue
        rh = mm.group(1)
        vals = [int(mm.group(i).replace(",", "").replace("*", "")) for i in (3, 4, 5, 6, 7)]
        c = diff["rh_by_company"][rh]
        eq("RH 表 %s" % rh, vals,
           [c.get("可判", 0), c.get("不适用", 0), c.get("单边缺口", 0),
            c.get("待核", 0), sum(c.values())])
        seen += 1
    eq("RH 表行数", 5, seen)

    # --- 合同资产状态 ---
    ca_t = Counter(r["ca_status_t"] for r in app if r["metric_id"] == "M11")
    ca_t1 = Counter(r["ca_basis_t1y"] for r in app if r["metric_id"] == "M12")
    eq("当期 149 有金额", 149, ca_t["HAS_VALUE"])
    eq("当期 127 空白", 127, ca_t["REPORTED_BLANK"])
    eq("当期 2 来源不准入", 2, ca_t["SOURCE_NOT_ADMISSIBLE"])
    eq("上年 135 有金额", 135, ca_t1["HAS_VALUE"])
    eq("上年 141 空白", 141, ca_t1["REPORTED_BLANK"])
    eq("上年 1 不准入", 1, ca_t1["SOURCE_NOT_ADMISSIBLE"])
    eq("上年 1 无记录", 1, ca_t1["NO_RECORD"])

    # --- 明确零 ---
    zeros = [r for r in app if r["metric_id"] == "M11" and r["ca_zero_basis_t"] == "EXPLICIT_ZERO"]
    eq("明确零 13 家", 13, len(zeros))
    eq("报告写 14 条", True, "当期 14 条" in md)
    eq("报告写 13 条", True, "**13 条**" in md)

    # --- 项目制构成 ---
    pm = [r for r in app if r["metric_id"] == "M11" and r["verdict"] == "NOT_APPLICABLE_PROJECT_MODE"]
    only1 = sum(1 for r in pm if Decimal(r["q10_branch1_pct"]) > 5
                and Decimal(r["q10_branch2_pct"]) <= 10)
    only2 = sum(1 for r in pm if Decimal(r["q10_branch1_pct"]) <= 5
                and Decimal(r["q10_branch2_pct"]) > 10)
    both = sum(1 for r in pm if Decimal(r["q10_branch1_pct"]) > 5
               and Decimal(r["q10_branch2_pct"]) > 10)
    eq("项目制 31", 31, len(pm))
    eq("项目制构成 1/19/11", [1, 19, 11], [only1, only2, both])

    # --- 来源完整度 ---
    m11 = [r for r in app if r["metric_id"] == "M11"]
    eq("149 有金额", 149, sum(1 for r in m11 if r["ca_status_t"] == "HAS_VALUE"))
    ca_tbl = {r["security_id"] for r in elig
              if r["metric_id"] == "M12" and r["field_id"] == "FIN.CONTRACTASSET.INSTANT"
              and r["period_key"] == r["anchor_period"]}
    eq("15 个当期 CA 键不在消费表", 15,
       sum(1 for r in m11 if r["ca_status_t"] == "HAS_VALUE" and r["security_id"] not in ca_tbl))

    # --- RH03 ---
    eq("单边缺口 18", 18, len(ss))
    eq("双期无可采用金额 126", 126, len(bb))
    mx = max(Decimal(r["if_zero_filled_signed_pp"]) for r in ss)
    eq("最大正向 +0.819421", Decimal("0.819421"), mx)
    eq("最大正向公司 瑞凌", "SZ:300154",
       [r["security_id"] for r in ss if Decimal(r["if_zero_filled_signed_pp"]) == mx][0])
    db = [r for r in ss if "002901" in r["security_id"]]
    eq("大博 -0.004709", Decimal("-0.004709"),
       Decimal(db[0]["if_zero_filled_signed_pp"]) if db else None)

    # --- RH04 / 父链 / M08 / Q4 / Q09 / 隔离 ---
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

    # --- 登记与回归 ---
    eq("登记 3 格", 3, len(nonadm))
    eq("登记 SHA 全匹配", 3, sum(1 for r in nonadm if r["sha_matches_register"] == "YES"))
    eq("底表未覆盖", 3, sum(1 for r in nonadm if r["base_table_overwritten"] == "NO"))
    eq("回归 6 例", 6, len(reg))
    eq("回归列归属 6", 6, sum(1 for r in reg if r["column_agrees"] == "YES"))
    eq("回归准入 6", 6, sum(1 for r in reg if r["admission_agrees"] == "YES"))
    eq("回归落到输出 6", 6, sum(1 for r in reg if r["rule_applied_to_output"] == "YES"))

    # --- 自检与契约 ---
    eq("自检 39/39", "39/39", rv["checks_passed"])
    eq("报告写 39/39 处数", 3, md.count("39/39"))
    eq("release_S05", False, rv["release_S05"])
    jj = {j["id"]: j["status"] for j in ct["judgments"]}
    eq("J1 否决", "REVOKED_BY_GATE", jj["J1"])
    eq("J2 通过", "PASSED_BY_GATE", jj["J2"])
    eq("J3 通过", "PASSED_BY_GATE", jj["J3"])
    eq("J4 本轮采用", "ADOPTED_BY_THIS_ROUND", jj["J4"])
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
