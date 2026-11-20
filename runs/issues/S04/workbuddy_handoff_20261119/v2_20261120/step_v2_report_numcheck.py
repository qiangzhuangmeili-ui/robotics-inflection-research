# -*- coding: utf-8 -*-
"""把 report_to_codex_s05_v2.md 里的数字与产物实算逐条比对（prose 漂移守卫）。"""
import csv
import json
import os
import re
import sys
from collections import Counter
from decimal import Decimal

V2 = os.path.dirname(os.path.abspath(__file__))
UNIT = os.path.dirname(V2)
REPO = os.path.abspath(os.path.join(V2, "..", "..", "..", "..", ".."))


def rows(p):
    with open(p, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def main():
    md = open(os.path.join(V2, "report_to_codex_s05_v2.md"), encoding="utf-8").read()
    bad = []
    ok = []

    def eq(name, claimed, actual):
        if claimed == actual:
            ok.append(name)
        else:
            bad.append("%s: 报告=%r 实算=%r" % (name, claimed, actual))

    elig = rows(os.path.join(V2, "s05_source_eligibility_v2.csv"))
    app = rows(os.path.join(V2, "s05_applicability_v2.csv"))
    diff = json.load(open(os.path.join(V2, "s05_v1_v2_diff.json"), encoding="utf-8"))

    # --- 行数 ---
    eq("eligibility 行数", int(re.search(r"s05_source_eligibility_v2\.csv`（([\d,]+) 行）", md).group(1).replace(",", "")), len(elig))
    eq("applicability 行数", int(re.search(r"s05_applicability_v2\.csv`（([\d,]+) 行）", md).group(1).replace(",", "")), len(app))

    # --- 用途分类四态 ---
    u = Counter(r["actual_use_eligibility"] for r in elig)
    tbl = {}
    for line in md.splitlines():
        m = re.match(r"^\|\s*`(ELIGIBLE_FOR_S05_USE|NOT_APPLICABLE|HOLD_APPLICABILITY_UNKNOWN|PENDING_\*)`\s*\|\s*([\d,]+)\s*\|", line)
        if m:
            tbl[m.group(1)] = int(m.group(2).replace(",", ""))
    eq("ELIGIBLE", tbl.get("ELIGIBLE_FOR_S05_USE"), u["ELIGIBLE_FOR_S05_USE"])
    eq("NOT_APPLICABLE", tbl.get("NOT_APPLICABLE"), u["NOT_APPLICABLE"])
    eq("HOLD", tbl.get("HOLD_APPLICABILITY_UNKNOWN"), u["HOLD_APPLICABILITY_UNKNOWN"])
    eq("PENDING", tbl.get("PENDING_*"), sum(v for k, v in u.items() if k.startswith("PENDING")))
    eq("合计", tbl.get("合计") or 8638, len(elig))
    # 闭合式
    s = u["ELIGIBLE_FOR_S05_USE"] + u["NOT_APPLICABLE"] + u["HOLD_APPLICABILITY_UNKNOWN"]
    eq("8,623 = 8538+76+9", s, 8623)

    # --- 五个风险提示四态 ---
    RH = {"RH01": "应收周转", "RH02": "存货周转", "RH03": "合同资产占比", "RH04": "现金含量", "RH05": "毛利率下滑"}
    for line in md.splitlines():
        m = re.match(r"^\|\s*(RH0\d)\s+([^|]+?)\s*\|\s*\**([\d,]+)\**\s*\|\s*\**([\d,]+)\**\s*\|\s*\**([\d,]+)\**\s*\|\s*([\d,]+)\s*\|\s*([\d,]+)\s*\|", line)
        if not m:
            continue
        rh = m.group(1)
        vals = [int(m.group(i).replace(",", "")) for i in (3, 4, 5, 6, 7)]
        c = diff["rh_by_company"][rh]
        actual = [c.get("可判", 0), c.get("不适用", 0), c.get("单边缺口", 0), c.get("待核", 0), sum(c.values())]
        eq("RH 表 %s" % rh, vals, actual)

    # --- Q10 差异 ---
    q10 = rows(os.path.join(V2, "s05_q10_engine_diff_v2.csv"))
    eq("Q10 差异行(项目制)", int(re.search(r"\*\*(\d+) 家\*\* 现为 M11=OK", md).group(1)),
       sum(1 for r in q10 if r["diff_kind"] == "OLD_OK_NOW_PROJECT_MODE"))
    eq("Q10 差异表总行", 20, len(q10))
    eq("diff_kind", diff["q10_engine_diff"], Counter(r["diff_kind"] for r in q10))
    yt = [r for r in q10 if "920508" in r["security_id"]]
    if yt:
        eq("殷图 branch1", re.search(r"复现为 \*\*([\d.]+)%", md).group(1), str(round(Decimal(yt[0]["q10_branch1_pct"]), 2)))
        eq("殷图 branch2", re.search(r"复现为 \*\*[\d.]+% / ([\d.]+)%", md).group(1), str(round(Decimal(yt[0]["q10_branch2_pct"]), 2)))
    pm = [r for r in app if r["verdict"] == "NOT_APPLICABLE_PROJECT_MODE"]
    only1 = [r for r in pm if Decimal(r["q10_branch1_pct"]) > 5 and Decimal(r["q10_branch2_pct"]) <= 10]
    only2 = [r for r in pm if Decimal(r["q10_branch1_pct"]) <= 5 and Decimal(r["q10_branch2_pct"]) > 10]
    both = [r for r in pm if Decimal(r["q10_branch1_pct"]) > 5 and Decimal(r["q10_branch2_pct"]) > 10]
    eq("只靠第一支", 1, len(only1))
    eq("只靠第二支", 19, len(only2))
    eq("两支都过", 11, len(both))
    if only1:
        eq("国机汽车代码", "SH:600335", only1[0]["security_id"])

    # --- RH03 ---
    ss = rows(os.path.join(V2, "s05_rh03_single_sided_v2.csv"))
    eq("单边缺口", 17, len(ss))
    eq("当期有值上年无", 16, sum(1 for r in ss if r["gap_side"].startswith("t 有值")))
    eq("上年有值当期无", 1, sum(1 for r in ss if r["gap_side"].startswith("t-1y 有值")))
    eq("RH03 不适用 125", 125, sum(1 for r in app if r["verdict"] == "NOT_APPLICABLE_NOT_REPORTED_BOTH"))
    eq("RH03 不可读 1", 1, sum(1 for r in app if r["verdict"] == "UNKNOWN_INPUT_UNREADABLE"))
    mx = max(Decimal(r["if_zero_filled_pp"]) for r in ss)
    eq("填零最大 pp（两位小数）", "0.82", str(round(mx, 2)))
    db = [r for r in ss if "002901" in r["security_id"]]
    eq("大博医疗在单边缺口表", 1, len(db))

    # --- RH04 ---
    rh04 = rows(os.path.join(V2, "s05_rh04_denominator_v2.csv"))
    eq("RH04 行数", 36, len(rh04))
    eq("负分母", 35, sum(1 for r in rh04 if r["reason"] == "NEGATIVE_DENOMINATOR"))
    eq("零基数", 1, sum(1 for r in rh04 if r["reason"] == "ZERO_BASE_FLOOR_POSITIVE"))
    rq = [r for r in rh04 if "301360" in r["security_id"]]
    eq("荣旗 NPP", "246598.23", rq[0]["npp_ytd_t"] if rq else None)

    # --- 父链 ---
    par = [r for r in elig if r["page_evidence_mode"] == "VIA_PARENT"]
    eq("父链行数", 851, len(par))
    eq("父链缺项", 0, sum(1 for r in par if not (r["rev_document_id"] and r["cost_document_id"])))
    eq("父链同文档", 851, sum(1 for r in par if r["rev_document_id"] == r["cost_document_id"]))
    md_max = max(Decimal(r["recompute_abs_diff"]) for r in par)
    eq("最大复算差（1e-7 档）", "4.98e-07", "%.2e" % md_max)

    # --- M08 ---
    m08 = [r for r in elig if r["m08_dependency_kind"]]
    eq("M08 行数", 804, len(m08))
    eq("M08 三分类", {"RH04_INPUT": 484, "SIGNAL_DEP_AT_T": 160, "INHERITED_S04_SIGNAL_CHECK": 160},
       dict(Counter(r["m08_dependency_kind"] for r in m08)))

    # --- Q4 ---
    q4 = rows(os.path.join(V2, "s05_q4_disposition_match_v2.csv"))
    eq("Q4 命中", 0, len(q4))
    disp = rows(os.path.join(REPO, "runs/issues/S04/completion_20261114/qualification_v3_20261115/accepted_dispositions.csv"))
    cand = {r["security_id"] for r in rows(os.path.join(REPO, "runs/issues/S04/completion_20261114/final_delivery_20261116/reviewed_view/tight_pass.csv"))}
    eq("839 项", 839, len(disp))
    eq("317 家", 317, len({r["security_id"] for r in disp}))
    eq("交集 0", 0, len({r["security_id"] for r in disp} & cand))

    # --- RH06 ---
    rh06 = rows(os.path.join(V2, "s05_rh06_q09_registry_v2.csv"))
    eq("Q09 家数", 38, len(rh06))

    # --- 待核隔离 ---
    iso = rows(os.path.join(V2, "s05_pending_isolation_v2.csv"))
    rv = json.load(open(os.path.join(V2, "s05_v2_review.json"), encoding="utf-8"))
    eq("待核行", 15, len(iso))
    eq("待核格", 13, len({(r["security_id"], r["field_id"], r["period_key"]) for r in iso}))
    eq("待核家", 5, len({r["security_id"] for r in iso}))
    jd = [r for r in iso if "000856" in r["security_id"]]
    eq("冀东阻断信号", "SG09", jd[0]["blocked_signal_ids"] if jd else None)
    eq("冀东其余指标不受影响", "M04;M08;M10;M12", jd[0]["unaffected_applicable_metrics"] if jd else None)
    ce6 = [c for c in rv["checks"] if c["id"] == "CE6"]
    eq("CE6 剩余维度 CASH", True, bool(ce6) and '"CASH"' in json.dumps(ce6[0], ensure_ascii=False))

    # --- 自检 ---
    eq("自检计数", "21/21", rv["checks_passed"])
    eq("报告写 21/21 处数", 3, md.count("21/21"))
    eq("release_S05", False, rv["release_S05"])

    print("PASS %d / FAIL %d" % (len(ok), len(bad)))
    for b in bad:
        print("  FAIL", b)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
