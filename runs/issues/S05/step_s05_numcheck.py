#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""S05 说明文档数字校验：把 handoff.md 里的每个关键数字与产物实算比对。

存在的理由：JSON/CSV 一致而说明文档漂移，是任何结构检查都抓不到的失败模式。
"""

from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
V22 = REPO / "runs/issues/S04/workbuddy_handoff_20261119/v2_2_20261120"

METRICS = ("M04", "M08", "M10", "M11", "M12")
RH = ("RH01", "RH02", "RH03", "RH04", "RH05")


def read(p):
    with open(p, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def ints(text):
    """抽取纯数字单元格（去掉表格竖线、加粗、千分位）。"""
    out = []
    for cell in text.split("|"):
        c = cell.strip().replace("*", "").replace(",", "").strip()
        if re.fullmatch(r"-?\d+", c):
            out.append(int(c))
    return out


def find_row(md, label):
    for line in md.splitlines():
        if line.strip().startswith("|") and label in line:
            return line
    return ""


results = []


def check(name, ok, detail=""):
    results.append({"name": name, "pass": bool(ok), "detail": str(detail)})


def main():
    md = (HERE / "handoff.md").read_text(encoding="utf-8")
    decision = read(HERE / "quality_decision_log.csv")
    passed = read(HERE / "quality_pass.csv")
    observe = read(HERE / "quality_observe.csv")
    flags = read(HERE / "quality_flags.csv")
    preserved = read(HERE / "observe_pool_preserved_776.csv")
    source = read(HERE / "source_eligibility.csv")
    oor = read(HERE / "s05_out_of_valid_range.csv")
    pending = read(V22 / "s05_pending_isolation_v22.csv")
    contract = json.load(open(HERE / "input_contract.json", encoding="utf-8"))
    selfcheck = json.load(open(HERE / "s05_self_check.json", encoding="utf-8"))

    st = {m: Counter(r[f"{m.lower()}_status"] for r in decision) for m in METRICS}

    # ---- 一、结论
    check("N01 278 家主键", len(decision) == 278, len(decision))
    check("N02 277 通过", len(passed) == 277, len(passed))
    check("N03 1 观察", len(observe) == 1, len(observe))
    n_no_rh = sum(1 for r in passed if not (r["rh_triggered"] or ""))
    n_pending = sum(1 for r in passed if r["rh_pending"])
    check("N04 166 家至少一条已触发风险提示", len(passed) - n_no_rh == 166, len(passed) - n_no_rh)
    check("N05 148 家带待核项", n_pending == 148, n_pending)
    check("N06 正文写了 166 / 148 / 111",
          "166 家至少带一条已触发的风险提示" in md and "148 家带待核项" in md
          and "111 家无已触发提示" in md, "")

    # ---- 三、五指标表
    expect = {
        "M04": (st["M04"]["OK"], 0,
                st["M04"]["HOLD_DECISIVE_CELL_PENDING"] + st["M04"]["UNKNOWN_INPUT_MISSING"], 278),
        "M08": (st["M08"]["OK"],
                st["M08"]["NOT_APPLICABLE_NEGATIVE_DENOMINATOR"] + st["M08"]["NOT_APPLICABLE_ZERO_BASE_FLOOR"],
                st["M08"]["UNKNOWN_INPUT_MISSING"], 278),
        "M10": (st["M10"]["OK"], 0, st["M10"]["UNKNOWN_INPUT_MISSING"], 278),
        "M11": (st["M11"]["OK"], st["M11"]["NOT_APPLICABLE_PROJECT_MODE"],
                st["M11"]["UNKNOWN_CA_BLANK"] + st["M11"]["UNKNOWN_CA_SOURCE_NOT_ADMISSIBLE"], 278),
        "M12": (st["M12"]["OK"], st["M12"]["BOTH_BLANK_NO_USABLE_AMOUNT"],
                st["M12"]["SINGLE_SIDED_GAP"] + st["M12"]["UNKNOWN_INPUT_UNREADABLE"], 278),
    }
    for m, exp in expect.items():
        row = find_row(md, f"| {m} ")
        got = tuple(ints(row))
        check(f"N07 {m} 表行数字与实算一致", got == exp, f"文中 {got} vs 实算 {exp}")
    check("N08 M08 36 家不适用 = 35 负分母 + 1 零基数",
          st["M08"]["NOT_APPLICABLE_NEGATIVE_DENOMINATOR"] == 35
          and st["M08"]["NOT_APPLICABLE_ZERO_BASE_FLOOR"] == 1, "")
    check("N09 M11 31 家不适用全部为项目制",
          st["M11"]["NOT_APPLICABLE_PROJECT_MODE"] == 31, st["M11"]["NOT_APPLICABLE_PROJECT_MODE"])

    # ---- 四、RH 表
    rh_exp = {
        "RH01": (sum(1 for r in decision if "RH01" in (r["rh_triggered"] or "").split(";")),
                 sum(1 for r in decision if "RH01" in (r["rh_pending"] or "").split(";")),
                 sum(1 for r in decision if "RH01" in (r["rh_not_applicable"] or "").split(";"))),
        "RH02": (sum(1 for r in decision if "RH02" in (r["rh_triggered"] or "").split(";")),
                 sum(1 for r in decision if "RH02" in (r["rh_pending"] or "").split(";")),
                 sum(1 for r in decision if "RH02" in (r["rh_not_applicable"] or "").split(";"))),
        "RH03": (sum(1 for r in decision if "RH03" in (r["rh_triggered"] or "").split(";")),
                 sum(1 for r in decision if "RH03" in (r["rh_pending"] or "").split(";")),
                 sum(1 for r in decision if "RH03" in (r["rh_not_applicable"] or "").split(";"))),
        "RH04": (sum(1 for r in decision if "RH04" in (r["rh_triggered"] or "").split(";")),
                 sum(1 for r in decision if "RH04" in (r["rh_pending"] or "").split(";")),
                 sum(1 for r in decision if "RH04" in (r["rh_not_applicable"] or "").split(";"))),
        "RH05": (sum(1 for r in decision if "RH05" in (r["rh_triggered"] or "").split(";")),
                 sum(1 for r in decision if "RH05" in (r["rh_pending"] or "").split(";")),
                 sum(1 for r in decision if "RH05" in (r["rh_not_applicable"] or "").split(";"))),
        "RH06": (sum(1 for r in decision if "RH06" in (r["rh_triggered"] or "").split(";")),
                 sum(1 for r in decision if "RH06" in (r["rh_pending"] or "").split(";")),
                 sum(1 for r in decision if "RH06" in (r["rh_not_applicable"] or "").split(";"))),
    }
    for k, exp in rh_exp.items():
        row = find_row(md, f"| {k} ")
        got = tuple(ints(row))
        check(f"N10 {k} 表行数字与实算一致", got == exp, f"文中 {got} vs 实算 {exp}")

    # ---- 五、Q 标记
    q_actual = {f"Q{i:02d}": sum(1 for r in decision if f"Q{i:02d}" in (r["quality_flags"] or "").split(";"))
                for i in range(1, 13)}
    m = re.search(r"Q01 (\d+) 家、Q02 (\d+) 家、Q03 (\d+) 家、Q04 (\d+) 家、Q05 (\d+) 家、Q06 (\d+) 家、"
                  r"Q07 (\d+) 家、Q08 (\d+) 家、Q09 (\d+) 家、Q10 (\d+) 家、Q11 (\d+) 家、Q12 (\d+) 家", md)
    got_q = [int(x) for x in m.groups()] if m else []
    exp_q = [q_actual[f"Q{i:02d}"] for i in range(1, 13)]
    check("N11 Q01–Q12 十二个数字与实算一致", got_q == exp_q, f"文中 {got_q} vs 实算 {exp_q}")
    rh06 = read(HERE / "rh06_adoption.csv")
    rh06_triggered = sum(1 for r in rh06 if r["adoption_status"] == "QUALIFIED_TRIGGERED")
    check("N12 Q09 = 37 = RH06 有资格已触发（数据触发 38，差 1 为待核）",
          q_actual["Q09"] == 37 == rh06_triggered
          and sum(1 for r in rh06 if r["data_trigger"] == "YES") == 38, q_actual["Q09"])
    ad = Counter(r["adoption_status"] for r in rh06)
    check("N12b RH06 四类状态 37 / 234 / 1 / 6",
          ad.get("QUALIFIED_TRIGGERED") == 37 and ad.get("QUALIFIED_NOT_TRIGGERED") == 234
          and ad.get("PENDING_EXISTING_HINT") == 1 and ad.get("PENDING_INPUT_GAP") == 6, dict(ad))
    check("N12c 正文的 RH06 四类数字与实算一致",
          "| 有资格已触发 | 37 |" in md and "| 有资格未达阈值 | 234 |" in md
          and "| 既有提示待核 | 1 |" in md and "| 缺来源 | 6 |" in md, "")
    check("N12d RH06 待核 7 家且逐家登记",
          sum(1 for r in rh06 if r["adopted"] == "NO") == 7
          and sum(1 for r in rh06 if r["gap_type"] == "MISSING_NPP") == 2
          and sum(1 for r in rh06 if r["gap_type"] == "OPEN_DISPUTE") == 5, "")
    check("N12e 五洋自控 RH06 既有提示待核 + 争议号",
          any(r["security_id"] == "SZ:300420" and r["adoption_status"] == "PENDING_EXISTING_HINT"
              and "D-6863cfbe7055" in r["open_dispute_ids"] for r in rh06), "")
    anc = Counter(r["anchor_period"] for r in decision)
    check("N12f 锚定期间 200×20260630 + 78×20260930 与文中一致",
          anc.get("20260630") == 200 and anc.get("20260930") == 78
          and "200 家锚 `20260630`" in md and "78 家锚 `20260930`" in md, dict(anc))
    check("N13 Q06/Q07/Q11/Q12 均为 0",
          all(q_actual[k] == 0 for k in ("Q06", "Q07", "Q11", "Q12")),
          {k: q_actual[k] for k in ("Q06", "Q07", "Q11", "Q12")})

    # ---- 六、三格与待核
    check("N14 待核 15 行 / 13 格 / 5 家",
          len(pending) == 15
          and len({(r["security_id"], r["field_id"], r["period_key"]) for r in pending}) == 13
          and len({r["security_id"] for r in pending}) == 5, "")
    check("N15 正文写了 15 行、13 个唯一格、5 家",
          "15 行、13 个唯一格、5 家" in md, "")
    check("N16 只有冀东装备绑定 blocked_signal_ids",
          [r["security_id"] for r in pending if r["blocked_signal_ids"]] == ["SZ:000856"], "")
    ss = read(V22 / "s05_rh03_single_sided_v22.csv")
    check("N17 单边缺口 18 家", len(ss) == 18, len(ss))
    check("N18 18 家即使填零也不触发 RH03",
          not [r for r in ss if r["would_trigger_rh03_if_zero_filled"] == "YES"], "")

    # ---- 七、证据链
    adopted = sum(1 for r in source if r["adopted"] == "YES")
    not_adopted = sum(1 for r in source if r["adopted"] == "NO")
    via = sum(1 for r in source if r["page_evidence_mode"] == "VIA_PARENT")
    check("N19 来源资格 6076 行", len(source) == 6076, len(source))
    check("N20 采用 5444 / 未采用 632", adopted == 5444 and not_adopted == 632,
          f"{adopted}/{not_adopted}")
    check("N21 未采用 632 = 534+76+9+8+5", 534 + 76 + 9 + 8 + 5 == not_adopted, not_adopted)
    by_use = Counter(r["actual_use_eligibility"] for r in source if r["adopted"] == "NO")
    check("N22 未采用分项与文中一致",
          by_use.get("HOLD_APPLICABILITY_UNKNOWN") == 534
          and by_use.get("NOT_APPLICABLE") == 76
          and by_use.get("PENDING_MISSING_INPUT") == 9
          and by_use.get("HOLD_SINGLE_SIDED_GAP") == 8
          and by_use.get("PENDING_OPEN_DISPUTE") == 5, dict(by_use))
    check("N23 毛利率父键 851 行", via == 851, via)
    check("N24 毛利率行 852 = 851 父键 + 1 缺失",
          sum(1 for r in source if r["field_id"] == "FIN.GROSSMARGIN.PCT") == 852, "")

    # ---- 八、限制
    check("N25 超范围 20 个", len(oor) == 20, len(oor))
    check("N26 超范围分布 M08 15 / M10 4 / M12 1",
          Counter(r["metric_id"] for r in oor) == Counter({"M08": 15, "M10": 4, "M12": 1}),
          dict(Counter(r["metric_id"] for r in oor)))
    nchuan = [r for r in oor if r["stock_name"] == "*ST纳川" and r["metric_id"] == "M10"]
    check("N27 *ST纳川 M10 = -769.564487",
          nchuan and Decimal(nchuan[0]["value"]) == Decimal("-769.564487"),
          nchuan[0]["value"] if nchuan else "")
    nchuan12 = [r for r in oor if r["stock_name"] == "*ST纳川" and r["metric_id"] == "M12"]
    check("N28 *ST纳川 M12 = -158.156651",
          nchuan12 and Decimal(nchuan12[0]["value"]) == Decimal("-158.156651"),
          nchuan12[0]["value"] if nchuan12 else "")

    # ---- 十、交付物
    rows = {
        "quality_flags.csv": len(flags), "quality_decision_log.csv": len(decision),
        "quality_pass.csv": len(passed), "quality_observe.csv": len(observe),
        "rh06_adoption.csv": len(rh06),
        "observe_pool_preserved_776.csv": len(preserved),
        "source_eligibility.csv": len(source), "s05_out_of_valid_range.csv": len(oor),
    }
    m2 = re.search(r"`quality_flags.csv`（([\d,]+) 行）、`quality_decision_log.csv`（([\d,]+) 行）、"
                   r"`quality_pass.csv`（([\d,]+) 行）、`quality_observe.csv`（([\d,]+) 行）、"
                   r"`rh06_adoption.csv`（([\d,]+) 行）、"
                   r"`observe_pool_preserved_776.csv`（([\d,]+) 行）、`source_eligibility.csv`（([\d,]+) 行）、"
                   r"`s05_out_of_valid_range.csv`（([\d,]+) 行）", md)
    got_rows = [int(x.replace(",", "")) for x in m2.groups()] if m2 else []
    exp_rows = [rows[k] for k in ("quality_flags.csv", "quality_decision_log.csv", "quality_pass.csv",
                                  "quality_observe.csv", "rh06_adoption.csv",
                                  "observe_pool_preserved_776.csv",
                                  "source_eligibility.csv", "s05_out_of_valid_range.csv")]
    check("N29 交付物行数与实算一致", got_rows == exp_rows, f"文中 {got_rows} vs 实算 {exp_rows}")
    frac = f"{selfcheck['checks_passed']}/{selfcheck['checks_total']}"
    check("N30 自检全项通过", selfcheck["checks_passed"] == selfcheck["checks_total"],
          f"{frac}")
    check("N31 正文写的自检分数与自检文件一致", f"（{frac}）" in md, frac)

    # ---- 776 携带
    check("N32 776 家原样携带", len(preserved) == 776, len(preserved))
    check("N33 4 家时间隔离 / 1 家锚点待核 / 15 家来源待核",
          sum(1 for r in preserved if r["cutoff_isolated"] == "YES") == 4
          and sum(1 for r in preserved if r["anchor_reselection_pending"] == "YES") == 1
          and sum(1 for r in preserved if r["quality_source_state"] == "PENDING_CE_SOURCE") == 15, "")

    # ---- 合同与本文一致性
    check("N34 合同 decision 计数与名单行数一致",
          contract["measured"]["decision"].get("QUALITY_PASS") == len(passed)
          and contract["measured"]["decision"].get("QUALITY_HOLD") == len(observe), "")

    out = {
        "artifact": "S05_PROSE_NUMBER_CHECK",
        "checks_passed": sum(1 for r in results if r["pass"]),
        "checks_total": len(results),
        "verdict": "NUMCHECK_PASS" if all(r["pass"] for r in results) else "NUMCHECK_FAIL",
        "results": results,
    }
    with open(HERE / "s05_prose_numcheck.json", "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"{out['checks_passed']}/{out['checks_total']} {out['verdict']}")
    for r in results:
        if not r["pass"]:
            print("FAIL", r["name"], "|", r["detail"])
    return 0 if out["verdict"] == "NUMCHECK_PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
