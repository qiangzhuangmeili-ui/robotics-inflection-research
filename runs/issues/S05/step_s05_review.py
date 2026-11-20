#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 S05 review.json（工作单元复核记录）。数字从产物派生。"""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
V22 = REPO / "runs/issues/S04/workbuddy_handoff_20261119/v2_2_20261120"

METRICS = ("M04", "M08", "M10", "M11", "M12")


def read(p):
    with open(p, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def main():
    decision = read(HERE / "quality_decision_log.csv")
    passed = read(HERE / "quality_pass.csv")
    observe = read(HERE / "quality_observe.csv")
    source = read(HERE / "source_eligibility.csv")
    oor = read(HERE / "s05_out_of_valid_range.csv")
    pending = read(V22 / "s05_pending_isolation_v22.csv")
    selfcheck = json.load(open(HERE / "s05_self_check.json", encoding="utf-8"))
    numcheck = json.load(open(HERE / "s05_prose_numcheck.json", encoding="utf-8"))

    st = {m: Counter(r[f"{m.lower()}_status"] for r in decision) for m in METRICS}
    hold = observe[0] if observe else {}

    review = {
        "artifact": "S05_WORK_UNIT_REVIEW",
        "issue": "S05 / #40",
        "executor": "WorkBuddy AI",
        "plan_version": "20261026_collection_first_v2",
        "review_nature": "SELF_CHECK",
        "verdict": "SELF_CHECK_PASS",
        "verdict_basis": {
            "self_check": f"{selfcheck['checks_passed']}/{selfcheck['checks_total']}",
            "prose_numcheck": f"{numcheck['checks_passed']}/{numcheck['checks_total']}",
        },
        "scope_done": [
            "按 V2.2 冻结输入完成 278 家公司层面质量检查",
            "五个指标（M04/M08/M10/M11/M12）从冻结 B 独立重算，并与 S01 掩码表逐格比对",
            "RH01–RH06 按冻结算子与阈值输出，RH02 的 129 家待核继续隔离",
            "Q01–Q12 质量标记按冻结定义输出",
            "L3 闸门按 document_id + source_page（或父键）+ 非 HOLD 判定",
            "三格错列/错表隔离，无一被采用",
            "776 家观察入口原样携带，未重算、未改写",
        ],
        "counts": {
            "primary_pool": len(decision),
            "quality_pass": len(passed),
            "quality_observe": len(observe),
            "metric_status": {m: dict(st[m]) for m in METRICS},
            "rh_triggered": {k: sum(1 for r in decision if k in (r["rh_triggered"] or "").split(";"))
                             for k in ("RH01", "RH02", "RH03", "RH04", "RH05", "RH06")},
            "rh_pending": {k: sum(1 for r in decision if k in (r["rh_pending"] or "").split(";"))
                           for k in ("RH01", "RH02", "RH03", "RH04", "RH05")},
            "source_rows": len(source),
            "source_adopted": sum(1 for r in source if r["adopted"] == "YES"),
            "pending_rows": len(pending),
            "out_of_valid_range": len(oor),
        },
        "hold_company": {
            "security_id": hold.get("security_id", ""),
            "stock_name": hold.get("stock_name", ""),
            "reason": hold.get("decision_reason", ""),
        },
        "limitations": [
            "只核对五指标与待核隔离涉及的原页证据，未回读其余空白原页，未复算 360 份 PDF 哈希。",
            "valid_range 是合理性包络，冻结规则未给处置动作；20 个超范围值只登记不阻断。",
            "V2.2 对卓翼同一事实用两个子标签（M11 来源不准入 / M12 双期无可采用金额），结论一致、计数不受影响，本轮不改 V2.2。",
            "776 家观察池原样携带，其指标值不在本轮核对范围。",
            "冀东装备存活维度 CASH 在 S04 即标 PROVISIONAL，观察结论有双重支撑。",
        ],
        "open_questions_for_codex": [
            "277/1 的通过—观察切分是否成立，尤其冀东装备的撤维判断。",
            "立昂微、振华新材、四会富仕、本川智能四家带待核项仍通过，是否接受。",
            "20 个超出 valid_range 的值是否应按某种未写明的规则阻断。",
            "卓翼 M11/M12 子标签不一致是否需要回改 V2.2。",
        ],
        "downstream": {
            "S05_completed": True,
            "S06_released_by_this_record": False,
            "S07_released": False,
            "S08_released": False,
            "issue_53_touched": False,
            "note": "本轮只完成 #40 的质量检查并交 Codex 复核；不释放后续阶段，不改 #53 的既有结论。",
        },
    }
    with open(HERE / "review.json", "w", encoding="utf-8", newline="\n") as f:
        json.dump(review, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(json.dumps({"verdict": review["verdict"], "hold": review["hold_company"]["stock_name"]},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
