#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 S05 输入合同 input_contract.json（数字全部从产物派生，不手写）。"""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
V22 = REPO / "runs/issues/S04/workbuddy_handoff_20261119/v2_2_20261120"
REVIEWED = REPO / "runs/issues/S04/completion_20261114/final_delivery_20261116/reviewed_view"
RULES = REPO / "runs/issues/S01/screen_rules_v3_provenance_20261114.json"
FROZEN_B = REPO / "runs/issues/S02/hangcha_restated_20261101/s00_v10/s00_v10.csv.gz"
RELEASE = REPO / "runs/issues/S05/release_20261120.json"

METRICS = ("M04", "M08", "M10", "M11", "M12")


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def read(p: Path):
    with open(p, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def main():
    decision = read(HERE / "quality_decision_log.csv")
    flags = read(HERE / "quality_flags.csv")
    passed = read(HERE / "quality_pass.csv")
    observe = read(HERE / "quality_observe.csv")
    preserved = read(HERE / "observe_pool_preserved_776.csv")
    source = read(HERE / "source_eligibility.csv")
    oor = read(HERE / "s05_out_of_valid_range.csv")
    pending = read(V22 / "s05_pending_isolation_v22.csv")
    nonadmit = read(V22 / "s05_ca_source_nonadmission_v22.csv")
    rules = json.load(open(RULES, encoding="utf-8"))
    rel = json.load(open(RELEASE, encoding="utf-8"))

    rh_rules = {h["id"]: {"metric": h["metric"], "operator": h["operator"],
                          "threshold": h["threshold"], "unit": h["unit"]} for h in rules["risk_hints"]}

    st = {m: Counter(r[f"{m.lower()}_status"] for r in decision) for m in METRICS}

    contract = {
        "contract_id": "S05_EXECUTION_CONTRACT_20261120",
        "artifact": "S05_INPUT_CONTRACT",
        "issue": "S05 / #40",
        "executor": "WorkBuddy AI",
        "plan_version": "20261026_collection_first_v2",
        "review_nature": "SELF_CHECK",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "release_basis": {
            "path": "runs/issues/S05/release_20261120.json",
            "decision": rel["decision"],
            "release_S05": rel["release_S05"],
            "recorded_at": rel["recorded_at"],
            "sha256": sha256(RELEASE),
        },
        "scope": {
            "primary_pool": len(decision),
            "pool_basis": "S04 冻结交付 tight_pass 的精确主键集合，不增补、不替换、不重排",
            "metrics": list(METRICS),
            "additional_inputs": [
                "冻结有效信号的 L3 依赖（15 行待核消费行）",
                "低基数与绝对额通道的来源依赖",
                "适用性证据（V2.2 适用性表）",
                "既有 RH06/Q09 提示（可追溯，不重算口径）",
            ],
            "not_consumed": [
                "M01/M02/M03/M05/M06/M07/M09 的指标值（仅取其待核隔离记录）",
                "776 家观察池的指标值（原样携带，不重算）",
                "全池重抽、全池精读、企业深研",
            ],
            "observe_pool_preserved": len(preserved),
        },
        "inputs": [
            {"role": "冻结 B（期间与财务原始值）", "path": str(FROZEN_B.relative_to(REPO)),
             "sha256": sha256(FROZEN_B)},
            {"role": "278 家主键", "path": "runs/issues/S04/completion_20261114/final_delivery_20261116/reviewed_view/tight_pass.csv",
             "sha256": sha256(REVIEWED / "tight_pass.csv")},
            {"role": "776 家观察入口", "path": "runs/issues/S04/completion_20261114/final_delivery_20261116/reviewed_view/tight_observe.csv",
             "sha256": sha256(REVIEWED / "tight_observe.csv")},
            {"role": "冻结规则", "path": str(RULES.relative_to(REPO)), "sha256": sha256(RULES)},
            {"role": "V2.2 适用性", "path": "runs/issues/S04/workbuddy_handoff_20261119/v2_2_20261120/s05_applicability_v22.csv",
             "sha256": sha256(V22 / "s05_applicability_v22.csv")},
            {"role": "V2.2 来源资格", "path": "runs/issues/S04/workbuddy_handoff_20261119/v2_2_20261120/s05_source_eligibility_v22.csv",
             "sha256": sha256(V22 / "s05_source_eligibility_v22.csv")},
            {"role": "V2.2 待核隔离", "path": "runs/issues/S04/workbuddy_handoff_20261119/v2_2_20261120/s05_pending_isolation_v22.csv",
             "sha256": sha256(V22 / "s05_pending_isolation_v22.csv")},
            {"role": "V2.2 三格不准入", "path": "runs/issues/S04/workbuddy_handoff_20261119/v2_2_20261120/s05_ca_source_nonadmission_v22.csv",
             "sha256": sha256(V22 / "s05_ca_source_nonadmission_v22.csv")},
            {"role": "V2.2 规则模块（阈值唯一来源）", "path": "runs/issues/S04/workbuddy_handoff_20261119/v2_2_20261120/s05_ca_source_rule.py",
             "sha256": sha256(V22 / "s05_ca_source_rule.py")},
        ],
        "rules_applied": {
            "M04": {"formula": "GM(t) - GM(t-1y)", "unit": "pp",
                    "gm_source": "优先 FIN.GROSSMARGIN.PCT；缺失时 (REV-COST)/REV*100",
                    "evidence": "派生值无自身页码，按父键 REV+COST 追溯（VIA_PARENT）"},
            "M08": {"formula": "OCF.YTD(t)/NPP.YTD(t)", "unit": "ratio",
                    "only_period": "t", "negative_denominator": "NPP<=0 不适用",
                    "zero_base_floor": "0<NPP<100 万元 不适用"},
            "M10": {"formula": "AR(t)/REV(t)*days(t) - AR(t-1y)/REV(t-1y)*days(t-1y)",
                    "unit": "days", "method": "期末余额法"},
            "M11": {"formula": "INV(t)/COST(t)*days(t) - INV(t-1y)/COST(t-1y)*days(t-1y)",
                    "unit": "days", "project_mode": "Q10 成立则不判本指标"},
            "M12": {"formula": "CA(t)/REV(t)*100 - CA(t-1y)/REV(t-1y)*100", "unit": "pp",
                    "ca_source_requirement": "期间 + 合并资产负债表 + 合同资产行 + 期末列，四者同时绑定"},
            "days_in_period": "period_end - period_start + 1，取自 B，不按 365 硬编码",
            "rh_thresholds": rh_rules,
            "rh_threshold_source": "screen_rules_v3_provenance_20261114.json / risk_hints（唯一来源）",
            "q10_thresholds": {
                "asset_pct_gt": 5, "rev_pct_gt": 10, "logic": "两支 OR，各自独立成立",
                "source": "s05_ca_source_rule.py（Q10_ASSET_PCT / Q10_REV_PCT）",
            },
            "zero_base_floor_cny": 1000000,
            "zero_base_floor_source": "s05_ca_source_rule.py（ZERO_BASE_FLOOR）",
        },
        "status_vocabulary": {
            "OK": "可判且有值",
            "NOT_APPLICABLE_PROJECT_MODE": "Q10 成立，按项目制不判存货天数",
            "NOT_APPLICABLE_NEGATIVE_DENOMINATOR": "分母 <= 0",
            "NOT_APPLICABLE_ZERO_BASE_FLOOR": "|分母| < 100 万元",
            "HOLD_DECISIVE_CELL_PENDING": "决定性格存在未闭合输入/争议",
            "UNKNOWN_INPUT_MISSING": "必需输入行缺失",
            "UNKNOWN_INPUT_UNREADABLE": "抽取待核",
            "UNKNOWN_CA_BLANK": "合同资产在报表内但无金额，不补零",
            "UNKNOWN_CA_SOURCE_NOT_ADMISSIBLE": "合同资产取数经原页复核不成立，来源不准入",
            "BOTH_BLANK_NO_USABLE_AMOUNT": "双期无可采用金额（覆盖状态，不代表零值或无风险）",
            "SINGLE_SIDED_GAP": "单边有值，不填零、不判变动",
        },
        "rh_status_vocabulary": {
            "TRIGGERED": "达阈值", "NOT_TRIGGERED": "未达阈值",
            "NOT_APPLICABLE": "按规则不适用（项目制 / 双期无可采用金额 / 负分母 / 零基数）",
            "PENDING_HOLD": "待核（含来源不准入）",
            "PENDING_APPLICABILITY": "待核（适用性未定）",
            "PENDING_SINGLE_SIDED": "单边缺口，不判变动",
        },
        "ca_source_nonadmission": [
            {
                "security_id": r["security_id"], "stock_name": r["stock_name"],
                "field_id": r["field_id"], "period_key": r["period_key"],
                "document_id": r["document_id"], "document_sha256": r["document_sha256"],
                "defect_class": r["defect_class"], "b_value_raw": r["b_value_raw"],
                "s05_effect": r["s05_effect"],
            }
            for r in nonadmit
        ],
        "pending_isolation": {
            "rows": len(pending),
            "unique_cells": len({(r["security_id"], r["field_id"], r["period_key"]) for r in pending}),
            "companies": len({r["security_id"] for r in pending}),
            "company_list": sorted({r["stock_name"] for r in pending}),
            "blocking_signals": sorted({s for r in pending
                                        for s in (r["blocked_signal_ids"] or "").split(";") if s}),
        },
        "measured": {
            "decision": dict(Counter(r["decision"] for r in decision)),
            "metric_status": {m: dict(st[m]) for m in METRICS},
            "rh_triggered": {k: sum(1 for r in decision if k in (r["rh_triggered"] or "").split(";"))
                             for k in ("RH01", "RH02", "RH03", "RH04", "RH05", "RH06")},
            "rh_pending": {k: sum(1 for r in decision if k in (r["rh_pending"] or "").split(";"))
                           for k in ("RH01", "RH02", "RH03", "RH04", "RH05")},
            "rh_not_applicable": {k: sum(1 for r in decision if k in (r["rh_not_applicable"] or "").split(";"))
                                  for k in ("RH01", "RH02", "RH03", "RH04", "RH05")},
            "quality_flags": {f"Q{i:02d}": sum(1 for r in decision if f"Q{i:02d}" in (r["quality_flags"] or "").split(";"))
                              for i in range(1, 13)},
            "source_eligibility_rows": len(source),
            "source_adopted": sum(1 for r in source if r["adopted"] == "YES"),
            "source_not_adopted": sum(1 for r in source if r["adopted"] == "NO"),
            "via_parent_rows": sum(1 for r in source if r["page_evidence_mode"] == "VIA_PARENT"),
            "out_of_valid_range": len(oor),
        },
        "preserved_guards": {
            "cutoff_isolated": sum(1 for r in preserved if r["cutoff_isolated"] == "YES"),
            "anchor_reselection_pending": sum(1 for r in preserved if r["anchor_reselection_pending"] == "YES"),
            "quality_source_unknown": sum(1 for r in preserved if r["quality_source_state"] == "PENDING_CE_SOURCE"),
            "held_parent_members": rel["guards"]["held_parent_members"],
            "nonadmitted_CA_keys": rel["guards"]["nonadmitted_CA_keys"],
            "note": "776 家观察入口原样携带，本轮不重算、不改写；上述计数为携带时的原值核对",
        },
        "outputs": [
            {"file": "quality_flags.csv", "rows": len(flags), "sha256": sha256(HERE / "quality_flags.csv")},
            {"file": "quality_pass.csv", "rows": len(passed), "sha256": sha256(HERE / "quality_pass.csv")},
            {"file": "quality_observe.csv", "rows": len(observe), "sha256": sha256(HERE / "quality_observe.csv")},
            {"file": "quality_decision_log.csv", "rows": len(decision), "sha256": sha256(HERE / "quality_decision_log.csv")},
            {"file": "source_eligibility.csv", "rows": len(source), "sha256": sha256(HERE / "source_eligibility.csv")},
            {"file": "observe_pool_preserved_776.csv", "rows": len(preserved), "sha256": sha256(HERE / "observe_pool_preserved_776.csv")},
            {"file": "s05_out_of_valid_range.csv", "rows": len(oor), "sha256": sha256(HERE / "s05_out_of_valid_range.csv")},
        ],
        "downstream": {
            "S05_completed": True,
            "S06_released_by_this_record": False,
            "S07_released": False,
            "S08_released": False,
            "note": "本轮只完成 #40 的质量检查并交 Codex 复核实际质量结果；不释放后续阶段。",
        },
    }

    with open(HERE / "input_contract.json", "w", encoding="utf-8", newline="\n") as f:
        json.dump(contract, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(json.dumps(contract["measured"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
