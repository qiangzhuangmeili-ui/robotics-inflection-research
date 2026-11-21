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
    rh06 = read(HERE / "rh06_adoption.csv")
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
                           for k in ("RH01", "RH02", "RH03", "RH04", "RH05", "RH06")},
            "rh06_adoption": dict(Counter(r["adoption_status"] for r in rh06)),
            "rh06_data_trigger": sum(1 for r in rh06 if r["data_trigger"] == "YES"),
            "anchor_period": dict(Counter(r["anchor_period"] for r in decision)),
            "stale_period_flag": dict(Counter(r["stale_period_flag"] for r in decision)),
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
            "维度级 provisional_dimensions 会同维度兄弟信号连坐（冀东装备 CASH 的 SG07 为 PROVISIONAL_ONLY，但存活信号 SG08 为 QUALIFIED_ABSOLUTE_CHANNEL），不能读成存活信号是临时值；本轮改为按存活信号自身状态判维度并输出 dimension_basis。",
            "l3_gate_result 只覆盖本轮五个指标；SG08 使用的 M09 来源沿用 S04 已核依赖，不在本轮重核范围。",
            "RH06 待核 7 家（既有提示 1 + 缺归母 2 + 扣非争议 4）继续隔离，不清零、不推定。",
        ],
        "codex_review_20261121": {
            "path": "runs/issues/S05/codex_review_s05_20261121.md",
            "verdict": "核心名单切分与五指标复算通过；RH06 定向返修后再验收",
            "items_fixed": [
                "冀东装备理由删除“CASH 在 S04 是 PROVISIONAL”的错误表述，改为只依据维度不足；新增 dimension_basis",
                "四家带待核通过显式标注 pass_scope = S05_QUALITY_GATE_ONLY",
                "20 个超 valid_range 值保留登记、不自动阻断，作为抽查入口",
                "卓翼 M11（当期来源不准入）与 M12（双期无可采用金额）两个子标签并存，不回改 V2.2",
                "RH06 改为逐公司采用台账 rh06_adoption.csv，四类状态，7 家待核逐家登记",
                "RH06 报告数字按实算改为 37 触发 / 234 未达阈值 / 7 待核；Q09 同步 37",
                "RH 触发改为按冻结算子分派（RH05 为 <=）并新增边界核验",
                "“全部为最新期”改为沿用冻结 Q11 标记，锚定期间分列 200×20260630 + 78×20260930",
            ],
            "still_open": "Codex 需复核本轮指纹与差额（RH06 采用台账、两处表述、RH05 边界）。",
        },
        "open_questions_for_codex": [
            "RH06 采用台账的四类划分与 7 家待核是否接受。",
            "RH05 改为按 <= 分派后，274 个可判 M04 中无等于 -2 的值，故触发数不变，是否认可该边界处理。",
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
