# -*- coding: utf-8 -*-
"""
S08 (#43) Deterministic Builder — accept the metric-screening stage (S00-S07),
freeze the downstream business-verification candidate list, and close S07 F10.

Outputs (all under runs/issues/S08/, pure LF):
  - screen_acceptance.json
  - business_verification_candidates.csv  (1,054 rows)
  - candidate_reuse_map.csv               (80 legacy rows, no auto-promotion)
  - s04_to_s05_bridge_445_to_278.csv      (445 rows)
  - handoff.md
  manifest.json / review.json are produced by step_s08_verify.py.

Set S08_FIXED_NOW for byte-identical replay.
"""
import csv
import hashlib
import io
import json
import os
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
OUT = REPO / "runs" / "issues" / "S08"
NOW = os.environ.get("S08_FIXED_NOW") or datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")

ISSUE_KEY = "S08"
ISSUE_NUMBER = 43
PLAN_VERSION = "20261026_collection_first_v2"
KNOWLEDGE_AS_OF = "2026-10-25"
EXECUTOR = "CodeBuddy"
ORCHESTRATOR = "Antigravity"
REVIEWER_ASSIGNED = "Codex"
DRIVE_ARCHIVE_ID = "1VrpWyQct6xI5PpRdGNs6KFZmubbspYEA"

# Exact, exhaustive list of every Git-tracked file read at runtime.
READ_INPUTS = [
    "runs/issues/S08/release_20261126.json",
    "runs/issues/S08/handoff_from_s07_20261126.md",
    "data/company_master.csv",
    # S01
    "runs/issues/S01/acceptance_20261029.json",
    "runs/issues/S01/screen_rules_v3.json",
    "runs/issues/S01/screen_rules_v4.json",
    # S02
    "runs/issues/S02/acceptance_20261106/review.json",
    "runs/issues/S02/acceptance_20261106/s03_input_contract.json",
    "runs/issues/S02/hangcha_restated_20261101/s02_v10/all_pool_metrics.csv",
    # S03
    "runs/issues/S03/review.json",
    "runs/issues/S03/rerun_20261106/l1_screen_results.csv",
    "runs/issues/S03/rerun_20261106/wide_pass.csv",
    "runs/issues/S03/rerun_20261106/wide_defer.csv",
    "runs/issues/S03/rerun_20261106/wide_unknown.csv",
    # S04
    "runs/issues/S04/codex_ruling_s05_v22_20261120.md",
    "runs/issues/S04/tight_decision_log.csv",
    # S05
    "runs/issues/S05/acceptance_s05_r1_20261121.json",
    "runs/issues/S05/quality_pass.csv",
    "runs/issues/S05/quality_observe.csv",
    "runs/issues/S05/quality_decision_log.csv",
    "runs/issues/S05/quality_flags.csv",
    "runs/issues/S05/observe_pool_preserved_776.csv",
    "runs/issues/S05/rh06_adoption.csv",
    "runs/issues/S05/s05_out_of_valid_range.csv",
    # S06
    "runs/issues/S06/acceptance_s06_r2_20261123.json",
    "runs/issues/S06/early_stage_watch.csv",
    "runs/issues/S06/missing_data_watch.csv",
    "runs/issues/S06/watch_reentry_rules.md",
    # S07
    "runs/issues/S07/acceptance_s07_r3_20261126.json",
    "runs/issues/S07/screen_audit_review.json",
    "runs/issues/S07/screen_audit_findings.md",
    # Legacy reuse sources
    "archive/latest_universe.csv",
    "archive/R1_batch01_parent_reviewed_20261024/classification_reviewed.csv",
    "archive/R1_02A_parent_reviewed_20261024/classification_reviewed.csv",
    "archive/02A_supplement/classification_reviewed.csv",
    "archive/02B/classification_reviewed.csv",
    "archive/early_sample_proposals.csv",
    "packages/B00_SOURCE_01/results/screening.csv",
    "packages/B00_SOURCE_02/results/screening.csv",
    "packages/C00_PILOT_01/results/screening.csv",
    "packages/D00_B00_ADVANCE_01/results/evidence.csv",
    "data/package_index.csv",
    # Legacy 45 conditional-detail package assignments
    "packages/D01_DETAIL_01/assignment.csv",
    "packages/D01_DETAIL_02/assignment.csv",
    "packages/D01_DETAIL_03/assignment.csv",
    "packages/D01_DETAIL_04/assignment.csv",
    "packages/D01_DETAIL_05/assignment.csv",
    "packages/D01_DETAIL_06/assignment.csv",
    "packages/D01_DETAIL_07/assignment.csv",
    "packages/D01_DETAIL_08/assignment.csv",
    "packages/D01_DETAIL_09/assignment.csv",
]

DELIVERABLES = [
    "runs/issues/S08/screen_acceptance.json",
    "runs/issues/S08/business_verification_candidates.csv",
    "runs/issues/S08/candidate_reuse_map.csv",
    "runs/issues/S08/s04_to_s05_bridge_445_to_278.csv",
    "runs/issues/S08/handoff.md",
    "runs/issues/S08/review.json",
    "runs/issues/S08/step_s08_build.py",
    "runs/issues/S08/step_s08_verify.py",
]

ADOPT_PATHS = [
    "archive/R1_batch01_parent_reviewed_20261024/classification_reviewed.csv",
    "archive/R1_02A_parent_reviewed_20261024/classification_reviewed.csv",
    "archive/02A_supplement/classification_reviewed.csv",
    "archive/02B/classification_reviewed.csv",
]
B00_PATHS = [
    "packages/B00_SOURCE_01/results/screening.csv",
    "packages/B00_SOURCE_02/results/screening.csv",
]
C00_PATH = "packages/C00_PILOT_01/results/screening.csv"
D00_PATH = "packages/D00_B00_ADVANCE_01/results/evidence.csv"
EARLY_PATH = "archive/early_sample_proposals.csv"

QUEUE_ORDER = [
    "R00_MAINLINE_VERIFY",
    "OBSERVE_QUALITY_HOLD",
    "OBSERVE_EARLY_AND_MISSING",
    "OBSERVE_EARLY_STAGE_ONLY",
    "OBSERVE_MISSING_DATA_ONLY",
    "NOT_SELECTED_FOR_R00",
]
TIER_ORDER = [
    "TIER_1_EVIDENCED_AND_CLEAN_OR_LOW_RISK",
    "TIER_2_CLEAN_NO_QUALITY_TRIGGER",
    "TIER_3_TRIGGERED_OR_PENDING_QUALITY",
    "NOT_IN_R00_MAINLINE",
]
TIER_LABEL = {
    "TIER_1_EVIDENCED_AND_CLEAN_OR_LOW_RISK": "TIER_1",
    "TIER_2_CLEAN_NO_QUALITY_TRIGGER": "TIER_2",
    "TIER_3_TRIGGERED_OR_PENDING_QUALITY": "TIER_3",
    "NOT_IN_R00_MAINLINE": "NOT_IN_R00_MAINLINE",
}


def load_csv(rel):
    with open(REPO / rel, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def canonical_input_digest(rel):
    raw = (REPO / rel).read_bytes()
    canon = raw.replace(b"\r\n", b"\n")
    return len(canon), hashlib.sha256(canon).hexdigest()


def sha256_exact(path):
    raw = Path(path).read_bytes()
    return len(raw), hashlib.sha256(raw).hexdigest()


def clean(value):
    if value is None:
        return ""
    return str(value).replace("\r\n", " ").replace("\n", " ").replace("\r", " ")


def write_csv(rel, header, rows):
    buf = io.StringIO(newline="")
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    for row in rows:
        w.writerow([clean(row.get(h, "")) for h in header])
    data = buf.getvalue().encode("utf-8")
    assert b"\r\n" not in data, rel
    (REPO / rel).write_bytes(data)


def write_json(rel, obj):
    data = (json.dumps(obj, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    assert b"\r\n" not in data, rel
    (REPO / rel).write_bytes(data)


def split_set(value):
    return {x for x in (value or "").split(";") if x}


def anchor_label(period):
    return {"20260630": "H1", "20260930": "9M", "20260331": "Q1"}.get(period, period or "UNKNOWN")


def main():
    master = load_csv("data/company_master.csv")
    master_by_id = {r["security_id"]: r for r in master}
    master_ids = set(master_by_id)
    if len(master) != 1054 or len(master_ids) != 1054:
        raise SystemExit("company_master is not 1,054 unique primary keys")

    s03 = {r["company_id"]: r for r in load_csv("runs/issues/S03/rerun_20261106/l1_screen_results.csv")}
    wp = {r["company_id"] for r in load_csv("runs/issues/S03/rerun_20261106/wide_pass.csv")}
    wd = {r["company_id"] for r in load_csv("runs/issues/S03/rerun_20261106/wide_defer.csv")}
    wu = {r["company_id"] for r in load_csv("runs/issues/S03/rerun_20261106/wide_unknown.csv")}

    s04 = {r["company_id"]: r for r in load_csv("runs/issues/S04/tight_decision_log.csv")}
    s04_445 = {k for k, r in s04.items() if r["l2_decision"] == "L2_SHORTLIST_CANDIDATE"}

    qp = {r["security_id"]: r for r in load_csv("runs/issues/S05/quality_pass.csv")}
    qo = {r["security_id"]: r for r in load_csv("runs/issues/S05/quality_observe.csv")}
    qdl = {r["security_id"]: r for r in load_csv("runs/issues/S05/quality_decision_log.csv")}
    qf = load_csv("runs/issues/S05/quality_flags.csv")
    ob = {r["security_id"]: r for r in load_csv("runs/issues/S05/observe_pool_preserved_776.csv")}
    rh06 = load_csv("runs/issues/S05/rh06_adoption.csv")
    oor_rows = load_csv("runs/issues/S05/s05_out_of_valid_range.csv")
    oor_ids = {r["security_id"] for r in oor_rows}
    rh06_pending_ids = {r["security_id"] for r in rh06 if r["adoption_status"].startswith("PENDING")}

    early_rows = load_csv("runs/issues/S06/early_stage_watch.csv")
    missing_rows = load_csv("runs/issues/S06/missing_data_watch.csv")
    early = {r["security_id"]: r for r in early_rows}
    missing = {r["security_id"]: r for r in missing_rows}

    # ---------------- legacy sources ----------------
    adopt_by_id = {}
    for p in ADOPT_PATHS:
        for r in load_csv(p):
            adopt_by_id.setdefault(r["security_id"], set()).add(p)
    d45_by_id = {}
    d45_pkgs = []
    for i in range(1, 10):
        pkg = f"D01_DETAIL_{i:02d}"
        d45_pkgs.append(pkg)
        for r in load_csv(f"packages/{pkg}/assignment.csv"):
            d45_by_id.setdefault(r["security_id"], set()).add(pkg)
    early_by_id = {r["security_id"]: r for r in load_csv(EARLY_PATH)}
    b00_by_id = {}
    for p in B00_PATHS:
        for r in load_csv(p):
            b00_by_id.setdefault(r["security_id"], []).append((p, r))
    c00_by_id = {r["security_id"]: r for r in load_csv(C00_PATH)}
    d00_by_id = {}
    for r in load_csv(D00_PATH):
        d00_by_id.setdefault(r["security_id"], []).append(r)

    legacy_union = set(adopt_by_id) | set(d45_by_id) | set(early_by_id) | set(b00_by_id) | set(c00_by_id) | set(d00_by_id)
    excluded_legacy = {}
    for sid, items in b00_by_id.items():
        for _, r in items:
            if r["screening_decision"] == "DEFER":
                excluded_legacy.setdefault(sid, []).append("B00_DEFER_CONCEPT_OR_SCOPE_EXCLUDED")
    for sid, r in c00_by_id.items():
        if r["screening_decision"] == "DEFER":
            excluded_legacy.setdefault(sid, []).append("C00_DEFER_CONCEPT_OR_SCOPE_EXCLUDED")
        if r["robot_exposure_proposal"] in {"CONCEPT_ONLY", "ASSOCIATE_NOT_CONSOLIDATED",
                                            "ASSOCIATE_NOT_CONSOLIDATED"}:
            excluded_legacy.setdefault(sid, []).append("C00_CONCEPT_OR_ASSOCIATE_EXCLUDED")
    for sid in list(excluded_legacy):
        excluded_legacy[sid] = sorted(set(excluded_legacy[sid]))

    # ---------------- helpers ----------------
    def legacy_buckets(sid):
        out = []
        if sid in adopt_by_id:
            out.append("PRIOR_ADOPTED_53")
        if sid in d45_by_id:
            out.append("CONDITIONAL_DETAIL_45")
        if sid in early_by_id:
            out.append("EARLY_SAMPLE_10")
        if sid in b00_by_id:
            out.append("B00_SOURCE")
        if sid in c00_by_id:
            out.append("C00_PILOT")
        if sid in d00_by_id:
            out.append("D00_ADVANCE")
        return out

    def legacy_sources(sid):
        parts = []
        for p in ADOPT_PATHS:
            if sid in adopt_by_id and p in adopt_by_id[sid]:
                parts.append(p)
        for pkg in d45_pkgs:
            if sid in d45_by_id and pkg in d45_by_id[sid]:
                parts.append(f"packages/{pkg}/assignment.csv")
        if sid in early_by_id:
            parts.append(EARLY_PATH)
        for p in B00_PATHS:
            if sid in b00_by_id and any(x[0] == p for x in b00_by_id[sid]):
                parts.append(p)
        if sid in c00_by_id:
            parts.append(C00_PATH)
        if sid in d00_by_id:
            parts.append(D00_PATH)
        return ";".join(dict.fromkeys(parts))

    def legacy_adoption_status(sid):
        parts = []
        if sid in adopt_by_id:
            parts.append("ACCEPTED_WITH_LIMITS")
        if sid in d45_by_id:
            parts.append("PLANNED_CONDITIONAL_PRELIMINARY_ONLY")
        if sid in early_by_id:
            parts.append("PARTIAL_CLAIM_REVIEW_ONLY")
        for _, r in b00_by_id.get(sid, []):
            parts.append(f"B00_{r['screening_decision']}_REVIEW_PENDING")
        if sid in c00_by_id:
            parts.append(f"C00_{c00_by_id[sid]['screening_decision']}_REVIEW_PENDING")
        if sid in d00_by_id:
            parts.append("D00_EVIDENCE_REVIEW_PENDING")
        return ";".join(dict.fromkeys(parts))

    def legacy_limits(sid):
        parts = []
        if sid in adopt_by_id:
            parts.append("旧53家为ACCEPTED_WITH_LIMITS采用事实，仅可复用，不自动提级")
        if sid in d45_by_id:
            parts.append("旧45家仅具进入细筛的初步业务依据，不等于已通过细筛")
        if sid in early_by_id:
            parts.append("10家早期样本仅局部断言已核读，不得外推")
        if sid in b00_by_id:
            parts.append("B00旧提议REVIEW_PENDING，需原文复验")
        if sid in c00_by_id:
            parts.append("C00为粗筛尺度校准，规则已验收但公司结论REVIEW_PENDING")
        if sid in d00_by_id:
            parts.append("D00证据多为REVIEW_PENDING或限定用途，不构成业务采用")
        return ";".join(parts)

    def trigger_list(sid):
        return split_set(qp[sid]["rh_triggered"]) if sid in qp else set()

    def pending_list(sid):
        return split_set(qp[sid]["rh_pending"]) if sid in qp else set()

    def final_queue(sid):
        if sid in qp:
            return "R00_MAINLINE_VERIFY"
        if sid in qo:
            return "OBSERVE_QUALITY_HOLD"
        if sid in early and sid in missing:
            return "OBSERVE_EARLY_AND_MISSING"
        if sid in early:
            return "OBSERVE_EARLY_STAGE_ONLY"
        if sid in missing:
            return "OBSERVE_MISSING_DATA_ONLY"
        return "NOT_SELECTED_FOR_R00"

    def priority_tier(sid, queue):
        if queue != "R00_MAINLINE_VERIFY":
            return "NOT_IN_R00_MAINLINE"
        if sid in legacy_union and sid not in excluded_legacy:
            return "TIER_1_EVIDENCED_AND_CLEAN_OR_LOW_RISK"
        if not trigger_list(sid) and not (pending_list(sid) & {"RH02", "RH03", "RH06"}):
            return "TIER_2_CLEAN_NO_QUALITY_TRIGGER"
        return "TIER_3_TRIGGERED_OR_PENDING_QUALITY"

    def s05_route(sid):
        if sid in qp:
            return "S05_QUALITY_PASS"
        if sid in qo:
            return "S05_QUALITY_HOLD"
        return "OBSERVE_POOL_PRESERVED_776"

    def anchor_period(sid):
        if sid in qp:
            return qp[sid]["anchor_period"]
        if sid in qo:
            return qo[sid]["anchor_period"]
        return ob[sid]["anchor_period"]

    def decision_reason(sid, queue, tier):
        if queue == "R00_MAINLINE_VERIFY":
            dims = qp[sid]["dimension_count_after"]
            trig = qp[sid]["rh_triggered"] or "无"
            pend = qp[sid]["rh_pending"] or "无"
            text = (f"S05 QUALITY_PASS：撤维后{dims}个维度由冻结合格信号支持；"
                    f"RH触发={trig}；RH待核={pend}；进入R00主线核验（{TIER_LABEL[tier]}）")
            if tier == "TIER_1_EVIDENCED_AND_CLEAN_OR_LOW_RISK":
                text += "；历史机器人线索可追溯，优先核验业务与财务归因（复用旧证据不自动提级）"
            elif tier == "TIER_2_CLEAN_NO_QUALITY_TRIGGER":
                text += "；无质量风险触发且无RH02/RH03/RH06待核"
            else:
                text += "；存在质量风险触发或RH02/RH03/RH06待核，核验时同步排查"
            return text
        if queue == "OBSERVE_QUALITY_HOLD":
            return (f"S05 QUALITY_HOLD：{qo[sid]['decision_reason']}；"
                    "冀东装备单独质量观察，不进入R00主线")
        if queue == "OBSERVE_EARLY_AND_MISSING":
            return (f"S06早期储备与缺数据观察交集：early_bucket={early[sid]['watch_bucket']}；"
                    f"missing_category={missing[sid]['missing_data_category']}；不进入R00主线，保留观察")
        if queue == "OBSERVE_EARLY_STAGE_ONLY":
            return (f"S06早期储备观察（{early[sid]['watch_bucket']}）；非主线776；"
                    "不进入R00主线，保留观察")
        if queue == "OBSERVE_MISSING_DATA_ONLY":
            return (f"S06缺数据观察（{missing[sid]['missing_data_category']}）；非主线776；"
                    "不进入R00主线，保留观察")
        d = s04[sid]
        reason = d["decision_reason"] or d["blocking_gap"] or "未达S04收紧门槛"
        return (f"S04未进入S05质量池（{d['l2_decision']}，S03分区{d['l1_partition']}）："
                f"{reason}；且不在S06早期/缺数据观察池；不进入R00")

    def carry_notes(sid, queue):
        parts = [f"锚定期={anchor_label(anchor_period(sid))}({anchor_period(sid)})"]
        if sid.startswith("BJ:"):
            parts.append("BJ市场（F08差异仅描述）")
        if sid in qp:
            if "RH02" in split_set(qp[sid]["rh_not_applicable"]):
                parts.append("RH02项目制豁免(F06)")
        if sid in oor_ids:
            parts.append("越界值保留原值/OK状态(F11)")
        if sid in rh06_pending_ids:
            parts.append("RH06待核(F12)")
        if sid in legacy_union:
            parts.append("历史资产仅复用、不自动提级")
        if sid in ob and ob[sid]["quality_source_state"] == "PENDING_CE_SOURCE":
            parts.append(f"质量来源未知守卫:{ob[sid]['quality_source_pending_metrics']}")
        if sid in s04_445 and sid not in qp and sid not in qo:
            parts.append("S05 HOLD_FOR_DATA，待补数据后按S06重入规则复核")
        if queue.startswith("OBSERVE_") and sid not in ob:
            parts.append("按S06观察池结转，重入需触发条件")
        return "；".join(parts)

    # ---------------- candidate rows ----------------
    candidate_rows = []
    for sid in master_ids:
        queue = final_queue(sid)
        tier = priority_tier(sid, queue)
        row = {
            "security_id": sid,
            "stock_name": master_by_id[sid]["stock_name"],
            "market": sid.split(":")[0],
            "s03_partition": s04[sid]["l1_partition"],
            "s04_baseline_decision": s04[sid]["l2_decision"],
            "s04_to_s05_bridge_status": (
                "ADMITTED_TO_S05_QUALITY_PASS" if sid in qp else
                "ADMITTED_TO_S05_QUALITY_HOLD" if sid in qo else
                "DEFERRED_TO_HOLD_FOR_DATA" if sid in s04_445 else
                "NOT_APPLICABLE_NOT_IN_445_BASELINE"
            ),
            "s05_route": s05_route(sid),
            "s05_anchor_period": anchor_period(sid),
            "s05_trigger_count": (len(trigger_list(sid)) if sid in qp else ""),
            "s05_rh_triggers": (qp[sid]["rh_triggered"] if sid in qp else ""),
            "s05_pending_flags": (
                qp[sid]["rh_pending"] if sid in qp else
                (f"QUALITY_SOURCE_UNKNOWN:{ob[sid]['quality_source_pending_metrics']}"
                 if sid in ob and ob[sid]["quality_source_state"] == "PENDING_CE_SOURCE" else "")
            ),
            "s05_out_of_valid_range_flag": "YES" if sid in oor_ids else "NO",
            "s06_early_bucket": early[sid]["watch_bucket"] if sid in early else "",
            "s06_missing_category": missing[sid]["missing_data_category"] if sid in missing else "",
            "has_legacy_asset": "True" if sid in legacy_union else "False",
            "legacy_sources": legacy_sources(sid),
            "legacy_auto_promoted": "False",
            "final_queue": queue,
            "r00_priority_tier": tier,
            "decision_reason": decision_reason(sid, queue, tier),
            "carry_forward_notes": carry_notes(sid, queue),
        }
        candidate_rows.append(row)

    def candidate_sort_key(r):
        q = QUEUE_ORDER.index(r["final_queue"])
        t = TIER_ORDER.index(r["r00_priority_tier"])
        if r["r00_priority_tier"] == "TIER_2_CLEAN_NO_QUALITY_TRIGGER":
            return (q, t, r["s05_anchor_period"],
                    -int(qp[r["security_id"]]["dimension_count_after"]), r["security_id"])
        return (q, t, "", 0, r["security_id"])

    candidate_rows.sort(key=candidate_sort_key)

    # ---------------- reuse map ----------------
    reuse_rows = []
    for sid in sorted(legacy_union):
        queue = final_queue(sid)
        tier = priority_tier(sid, queue)
        reuse_rows.append({
            "security_id": sid,
            "stock_name": master_by_id[sid]["stock_name"],
            "legacy_bucket": ";".join(legacy_buckets(sid)),
            "legacy_sources": legacy_sources(sid),
            "legacy_adoption_status": legacy_adoption_status(sid),
            "legacy_limits": legacy_limits(sid),
            "s08_final_queue": queue,
            "s08_r00_priority_tier": tier,
            "auto_promoted": "False",
            "reuse_instruction": (
                "R00/观察阶段可复用上述材料作为线索与原文入口；必须按当前S08门槛重新核验，"
                "不得绕过S08或自动提升验收状态（auto_promoted=False）。"
            ),
        })

    # ---------------- 445 -> 278 bridge ----------------
    bridge_rows = []
    for sid in sorted(s04_445):
        if sid in qp:
            dest = "ADMITTED_TO_S05_QUALITY_PASS"
            quality_decision = "QUALITY_PASS"
            quality_reason = qp[sid]["decision_reason"]
            recheck = ""
        elif sid in qo:
            dest = "ADMITTED_TO_S05_QUALITY_HOLD"
            quality_decision = "QUALITY_HOLD"
            quality_reason = qo[sid]["decision_reason"]
            recheck = ""
        else:
            dest = "DEFERRED_TO_HOLD_FOR_DATA"
            quality_decision = "HOLD_FOR_DATA"
            quality_reason = ("S05 未进入278质量池；observe_pool_preserved_776 标记 HOLD_FOR_DATA，"
                              "逐家保留观察")
            recheck = ob[sid]["recheck_status"]
        miss_cat = missing[sid]["missing_data_category"] if sid in missing else ""
        early_bucket = early[sid]["watch_bucket"] if sid in early else ""
        watch_reason = []
        if sid in missing:
            watch_reason.append(f"MISSING:{missing[sid]['watch_reason']}")
        if sid in early:
            watch_reason.append(f"EARLY:{early[sid]['watch_reason']}")
        bridge_rows.append({
            "security_id": sid,
            "stock_name": master_by_id[sid]["stock_name"],
            "s04_l2_decision": s04[sid]["l2_decision"],
            "s04_decision_reason": s04[sid]["decision_reason"],
            "s04_blocking_gap": s04[sid]["blocking_gap"],
            "s04_reentry_condition": s04[sid]["reentry_condition"],
            "s05_destination": dest,
            "s05_quality_decision": quality_decision,
            "s05_anchor_period": anchor_period(sid),
            "s05_decision_reason": quality_reason,
            "observe_pool_recheck_status": recheck,
            "s06_missing_category": miss_cat,
            "s06_early_bucket": early_bucket,
            "s06_watch_reason": "；".join(watch_reason),
            "bridge_basis": (
                "Git-tracked: runs/issues/S04/tight_decision_log.csv + "
                "runs/issues/S05/quality_pass.csv + runs/issues/S05/quality_observe.csv + "
                "runs/issues/S05/observe_pool_preserved_776.csv + "
                "runs/issues/S06/missing_data_watch.csv + runs/issues/S06/early_stage_watch.csv + "
                f"Drive archive {DRIVE_ARCHIVE_ID}"
            ),
            "drive_archive_id": DRIVE_ARCHIVE_ID,
        })

    # ---------------- reconciliation ----------------
    queue_counts = Counter(r["final_queue"] for r in candidate_rows)
    tier_counts = Counter(r["r00_priority_tier"] for r in candidate_rows)
    bridge_counts = Counter(r["s05_destination"] for r in bridge_rows)
    early_ids = set(early)
    missing_ids = set(missing)
    nonmainline_union = (early_ids | missing_ids) - (set(qp) | set(qo))
    zero_trigger_total = sum(1 for sid in qp if not trigger_list(sid))
    zero_trigger_pending = sum(1 for sid in qp if not trigger_list(sid)
                               and (pending_list(sid) & {"RH02", "RH03", "RH06"}))
    zero_tier = Counter(priority_tier(sid, "R00_MAINLINE_VERIFY")
                        for sid in qp if not trigger_list(sid))
    zero_t1 = zero_tier.get("TIER_1_EVIDENCED_AND_CLEAN_OR_LOW_RISK", 0)
    zero_t2 = zero_tier.get("TIER_2_CLEAN_NO_QUALITY_TRIGGER", 0)
    zero_t3 = zero_tier.get("TIER_3_TRIGGERED_OR_PENDING_QUALITY", 0)
    zero_t1_pending = sum(1 for sid in qp if not trigger_list(sid)
                          and priority_tier(sid, "R00_MAINLINE_VERIFY") == "TIER_1_EVIDENCED_AND_CLEAN_OR_LOW_RISK"
                          and (pending_list(sid) & {"RH02", "RH03", "RH06"}))
    rh02_na = sum(1 for r in qdl.values() if "RH02" in split_set(r["rh_not_applicable"]))
    rh06_pending = sum(1 for r in rh06 if r["adoption_status"].startswith("PENDING"))
    bj_universe = sum(1 for sid in master_ids if sid.startswith("BJ:"))
    bj_pass = sum(1 for sid in qp if sid.startswith("BJ:"))
    nonbj_universe = len(master_ids) - bj_universe
    nonbj_pass = len(qp) - bj_pass
    quality_source_unknown = sum(1 for r in ob.values() if r["quality_source_state"] == "PENDING_CE_SOURCE")
    cutoff_isolated = sum(1 for r in ob.values() if r["cutoff_isolated"] == "YES")
    anchor_pending = sum(1 for r in ob.values() if r["anchor_reselection_pending"] == "YES")

    # Dynamic anomaly list; stage_decision is derived from it, never hard-coded.
    anomalies = []
    if len(master) != 1054 or len(master_ids) != 1054:
        anomalies.append("UNIVERSE_NOT_1054_UNIQUE")
    if len(wp) != 777 or len(wd) != 149 or len(wu) != 128 or (wp & wd) or (wp & wu) or (wd & wu):
        anomalies.append("S03_PARTITION_MISMATCH")
    if (wp | wd | wu) != master_ids:
        anomalies.append("S03_UNION_NOT_UNIVERSE")
    if len(s04_445) != 445 or not s04_445 <= wp:
        anomalies.append("S04_BASELINE_NOT_445_IN_WIDE_PASS")
    if len(qp) != 277 or len(qo) != 1 or len(ob) != 776:
        anomalies.append("S05_PARTITION_MISMATCH")
    if (set(qp) | set(qo) | set(ob)) != master_ids or (set(qp) & set(qo)) or (set(qp) & set(ob)) or (set(qo) & set(ob)):
        anomalies.append("S05_UNION_NOT_DISJOINT_UNIVERSE")
    if not (set(qp) | set(qo)) <= s04_445:
        anomalies.append("S05_278_NOT_SUBSET_OF_S04_445")
    deferred = s04_445 - set(qp) - set(qo)
    if len(deferred) != 167 or any(ob[s]["l2_decision"] != "HOLD_FOR_DATA" for s in deferred):
        anomalies.append("S04_TO_S05_DEFERRED_NOT_167_HOLD_FOR_DATA")
    if len(early) != 54 or len(missing) != 379:
        anomalies.append("S06_WATCH_COUNTS_MISMATCH")
    if len(early_ids & missing_ids) != 33 or len(nonmainline_union) != 399:
        anomalies.append("S06_INTERSECTION_OR_UNION_MISMATCH")
    if any(early[s]["s05_mainline_dedup_status"] != "NON_MAINLINE_776" for s in early):
        anomalies.append("S06_EARLY_NOT_NONMAINLINE")
    if len(missing_ids & set(qo)) != 1:
        anomalies.append("S06_MISSING_MAINLINE_NOT_JIDONG_ONLY")
    expected_queues = {
        "R00_MAINLINE_VERIFY": 277,
        "OBSERVE_QUALITY_HOLD": 1,
        "OBSERVE_EARLY_AND_MISSING": 33,
        "OBSERVE_EARLY_STAGE_ONLY": 21,
        "OBSERVE_MISSING_DATA_ONLY": 345,
        "NOT_SELECTED_FOR_R00": 377,
    }
    if len(candidate_rows) != 1054 or sum(queue_counts.values()) != 1054:
        anomalies.append("CANDIDATE_ROW_COUNT_NOT_1054")
    for k, v in expected_queues.items():
        if queue_counts.get(k, 0) != v:
            anomalies.append(f"QUEUE_COUNT_MISMATCH:{k}")
    if set(r["security_id"] for r in candidate_rows) != master_ids:
        anomalies.append("CANDIDATE_KEYS_NOT_UNIVERSE")
    if any(r["final_queue"] == "R00_MAINLINE_VERIFY" for r in candidate_rows
           if r["security_id"] not in qp):
        anomalies.append("R00_CONTAINS_NON_QUALITY_PASS")
    if tier_counts.get("NOT_IN_R00_MAINLINE", 0) != 1054 - 277:
        anomalies.append("TIER_NON_R00_COUNT_MISMATCH")
    if len(bridge_rows) != 445 or bridge_counts.get("ADMITTED_TO_S05_QUALITY_PASS", 0) != 277 \
            or bridge_counts.get("ADMITTED_TO_S05_QUALITY_HOLD", 0) != 1 \
            or bridge_counts.get("DEFERRED_TO_HOLD_FOR_DATA", 0) != 167:
        anomalies.append("BRIDGE_445_TO_278_MISMATCH")
    if any(r["auto_promoted"] != "False" for r in reuse_rows):
        anomalies.append("LEGACY_AUTO_PROMOTION_DETECTED")
    if any(r["legacy_auto_promoted"] != "False" for r in candidate_rows):
        anomalies.append("CANDIDATE_LEGACY_AUTO_PROMOTION_DETECTED")
    if "BJ:920007" in master_ids:
        anomalies.append("EXCLUDED_LEGACY_SECURITY_PRESENT_IN_UNIVERSE")
    release = json.loads((REPO / "runs/issues/S08/release_20261126.json").read_text(encoding="utf-8"))
    if release["guards"]["S00_errata_issue_53"] != "OPEN":
        anomalies.append("ISSUE_53_NOT_OPEN")
    if release["guards"]["jidong_quality_hold"] != "SZ:000856" or "SZ:000856" not in qo:
        anomalies.append("JIDONG_QUALITY_HOLD_MISMATCH")

    stage_decision = "ACCEPTED_WITH_LIMITS" if not anomalies else "NOT_ACCEPTED_PENDING_FIX"

    input_fingerprints = []
    for rel in READ_INPUTS:
        nbytes, digest = canonical_input_digest(rel)
        input_fingerprints.append({"path": rel, "bytes": nbytes, "sha256": digest})

    acceptance = {
        "artifact": "S08_METRIC_STAGE_ACCEPTANCE_AND_R00_CANDIDATE_FREEZE",
        "issue_key": ISSUE_KEY,
        "issue_number": ISSUE_NUMBER,
        "plan_version": PLAN_VERSION,
        "knowledge_as_of": KNOWLEDGE_AS_OF,
        "generated_at": NOW,
        "timezone": "Asia/Shanghai",
        "executor": EXECUTOR,
        "orchestrator": ORCHESTRATOR,
        "review_nature": "SELF_CHECK",
        "reviewer_assigned": REVIEWER_ASSIGNED,
        "stage_decision": stage_decision,
        "stage_decision_basis": {
            "rule": "anomalies 为空 -> ACCEPTED_WITH_LIMITS；存在任一异常 -> NOT_ACCEPTED_PENDING_FIX",
            "anomaly_count": len(anomalies),
            "anomalies": anomalies,
        },
        "stage_versions": {
            "S00": {"status": "ERRATA_53_OPEN", "note": "S00 勘误 #53 原样结转，未闭合"},
            "S01": {"rules": ["v3", "v4"], "acceptance": "runs/issues/S01/acceptance_20261029.json"},
            "S02": {"metrics": "s02_v10", "acceptance": "runs/issues/S02/acceptance_20261106/review.json"},
            "S03": {"round": "rerun_20261106", "review": "runs/issues/S03/review.json"},
            "S04": {"ruling": "v2.2", "review": "runs/issues/S04/codex_ruling_s05_v22_20261120.md"},
            "S05": {"round": "R1", "acceptance": "runs/issues/S05/acceptance_s05_r1_20261121.json"},
            "S06": {"round": "R2", "acceptance": "runs/issues/S06/acceptance_s06_r2_20261123.json"},
            "S07": {"round": "R3", "acceptance": "runs/issues/S07/acceptance_s07_r3_20261126.json"},
        },
        "input_fingerprints": input_fingerprints,
        "reconciliation": {
            "universe": {"primary_keys": len(master_ids), "source": "data/company_master.csv"},
            "S03": {"wide_pass": len(wp), "wide_defer": len(wd), "wide_unknown": len(wu),
                    "sum": len(wp) + len(wd) + len(wu)},
            "S04": {"l2_shortlist_candidate": len(s04_445), "within_wide_pass": len(s04_445 & wp)},
            "S04_to_S05": {"baseline_445": len(s04_445), "frozen_278": len(qp) + len(qo),
                            "deferred_167": len(s04_445 - set(qp) - set(qo))},
            "S05": {"quality_pass": len(qp), "quality_hold": len(qo), "observe_pool_776": len(ob),
                    "sum": len(qp) + len(qo) + len(ob)},
            "S06": {"early_stage_watch": len(early), "missing_data_watch": len(missing),
                    "intersection": len(early_ids & missing_ids),
                    "nonmainline_union": len(nonmainline_union),
                    "missing_mainline_jidong": sorted(missing_ids & (set(qp) | set(qo)))},
            "bridge_445_to_278": {
                "baseline_445": len(bridge_rows),
                "admitted_quality_pass": bridge_counts.get("ADMITTED_TO_S05_QUALITY_PASS", 0),
                "admitted_quality_hold": bridge_counts.get("ADMITTED_TO_S05_QUALITY_HOLD", 0),
                "deferred_hold_for_data": bridge_counts.get("DEFERRED_TO_HOLD_FOR_DATA", 0),
                "sum": sum(bridge_counts.values()),
            },
            "final_queue_partition": {
                "counts": {k: queue_counts.get(k, 0) for k in QUEUE_ORDER},
                "sum": sum(queue_counts.values()),
                "sort_key": ("final_queue 顺序 -> r00_priority_tier 顺序 -> "
                             "TIER_2 内按(锚定期, -撤维后维度数, security_id)，其余按 security_id"),
            },
            "r00_priority_tiers": {
                "counts": {k: tier_counts.get(k, 0) for k in TIER_ORDER},
                "r00_total": sum(v for k, v in tier_counts.items() if k != "NOT_IN_R00_MAINLINE"),
                "zero_trigger_total": zero_trigger_total,
                "zero_trigger_with_rh02_rh03_rh06_pending": zero_trigger_pending,
                "zero_trigger_tier_breakdown": {
                    "TIER_1": zero_t1, "TIER_2": zero_t2, "TIER_3": zero_t3,
                    "TIER_1_with_pending": zero_t1_pending,
                    "TIER_3_pending": zero_t3,
                },
                "note": (f"零触发 {zero_trigger_total} 家中，{zero_trigger_pending} 家存在 RH02/RH03/RH06 待核："
                         f"{zero_t1_pending} 家历史资产进入 TIER_1，{zero_t3} 家进入 TIER_3；"
                         f"另有 {zero_t1 - zero_t1_pending} 家零触发历史资产（无待核）进入 TIER_1，"
                         f"{zero_t2} 家零触发无待核非历史资产进入 TIER_2"),
            },
        },
        "carry_forward_limits": {
            "F05": {"status": "CARRIED_AS_ANCHOR_STRATIFICATION",
                    "detail": "H1 与 9M 锚定期分层解释，禁止跨期合并触发率",
                    "H1_companies": sum(1 for r in list(qp.values()) + list(qo.values()) if r["anchor_period"] == "20260630"),
                    "M9_companies": sum(1 for r in list(qp.values()) + list(qo.values()) if r["anchor_period"] == "20260930")},
            "F06": {"status": "CARRIED_AS_RULE_EXEMPTION",
                    "detail": "RH02 项目制豁免按规则关闭存货周转风险；继续监控 RH01 应收与 RH03 合同资产",
                    "rh02_not_applicable_companies": rh02_na},
            "F07": {"status": "CARRIED_AS_FROZEN_THRESHOLD",
                    "detail": "低基数确认门槛保持冻结，不为凑数调整；保守延迟偏差保留"},
            "F08": {"status": "CARRIED_AS_DESCRIPTIVE_ONLY",
                    "detail": "BJ 与主板通过率差异仅描述，不作披露/结构/基数归因",
                    "bj_universe": bj_universe, "bj_pass": bj_pass,
                    "nonbj_universe": nonbj_universe, "nonbj_pass": nonbj_pass},
            "F09": {"status": "CARRIED_AS_SAMPLE_LIMIT",
                    "detail": "反向漏筛仅 5 家抽样独立重推；36 家强线索非主线公司仅路由汇总，不外推"},
            "F10": {"status": "CLOSED_BY_GIT_REPLAYABLE_BRIDGE",
                    "detail": "445 家 S04 基线逐家映射至 S05 277+1+167，100% 基于 Git 跟踪冻结表",
                    "bridge_file": "runs/issues/S08/s04_to_s05_bridge_445_to_278.csv",
                    "drive_archive_id": DRIVE_ARCHIVE_ID},
            "F11": {"status": "CARRIED_AS_RAW_VALUE_RETENTION",
                    "detail": "越界值保留原值与 OK 状态，冻结路由不改值、不阻断",
                    "out_of_valid_range_cells": len(oor_rows), "companies": len(oor_ids)},
            "F12": {"status": "CARRIED_AS_PENDING_RH06",
                    "detail": "RH06 待核公司继续待核，不因 S08 冻结而视为已解决",
                    "rh06_pending_companies": rh06_pending},
        },
        "guards": {
            "after_cutoff_companies": cutoff_isolated,
            "anchor_reselection_pending": anchor_pending,
            "quality_source_unknown_companies": quality_source_unknown,
            "unadopted_parent_members": release["guards"]["unadopted_parent_members"],
            "jidong_quality_hold": "SZ:000856",
            "S00_errata_issue_53": release["guards"]["S00_errata_issue_53"],
            "no_threshold_tuning": True,
            "no_manual_add_back": True,
            "no_legacy_auto_promotion": True,
        },
        "legacy_reuse": {
            "prior_adopted_53": len(adopt_by_id),
            "conditional_detail_45": len(d45_by_id),
            "early_sample_10": len(early_by_id),
            "b00_source": len(b00_by_id),
            "c00_pilot": len(c00_by_id),
            "d00_advance": len(d00_by_id),
            "union_in_universe": len(legacy_union),
            "auto_promoted": sum(1 for r in reuse_rows if r["auto_promoted"] != "False"),
            "excluded_not_in_universe": [
                {"security_id": "BJ:920007", "stock_name": "酉立智能",
                 "reason": "出现在 R1_batch01 parent-reviewed boundary/evidence/product-line 文件，但不在 1,054 冻结主表",
                 "sources": [
                     "archive/R1_batch01_parent_reviewed_20261024/boundary_reviewed.csv",
                     "archive/R1_batch01_parent_reviewed_20261024/evidence_register.csv",
                     "archive/R1_batch01_parent_reviewed_20261024/parent_corrections.csv",
                     "archive/R1_batch01_parent_reviewed_20261024/product_line_stages.csv",
                 ]},
            ],
        },
        "legacy_sequence_policy": {
            "old_concept_pre_screen_20_pdf_first": "NOT_EXECUTED_EARLY",
            "statement": "旧“概念粗筛 20 家先读 PDF”的顺序不再提前执行；后续 R00 只按本冻结名单分 5 家小包执行。",
            "r00_package_size": 5,
        },
        "release_control": {
            "release_R00": False,
            "release_R02": False,
            "issue_53_touched": False,
            "issue_53_status": "OPEN",
            "S08_completed": True,
        },
        "limits": [
            "本文件为执行方 SELF_CHECK 结论，不等同 Codex 独立验收；业务采用仍须独立复核。",
            "仅完成指标轮总对账与 R00 候选名单冻结，未启动公司业务深研、未做估值、未放行 R00/R02。",
            "TIER_1 仅表示存在可追溯历史线索，复用旧证据不自动提升任何验收状态。",
            "零触发 111 家中 71 家仍有 RH02/RH03/RH06 待核，按规则进入 TIER_3 或 TIER_1，不视为已清洁。",
            "BJ:920007 不在 1,054 冻结主表，已从复用映射剔除并登记。",
        ],
    }

    write_json("runs/issues/S08/screen_acceptance.json", acceptance)

    candidate_header = [
        "security_id", "stock_name", "market", "s03_partition", "s04_baseline_decision",
        "s04_to_s05_bridge_status", "s05_route", "s05_anchor_period", "s05_trigger_count",
        "s05_rh_triggers", "s05_pending_flags", "s05_out_of_valid_range_flag",
        "s06_early_bucket", "s06_missing_category", "has_legacy_asset", "legacy_sources",
        "legacy_auto_promoted", "final_queue", "r00_priority_tier", "decision_reason",
        "carry_forward_notes",
    ]
    write_csv("runs/issues/S08/business_verification_candidates.csv", candidate_header, candidate_rows)

    reuse_header = [
        "security_id", "stock_name", "legacy_bucket", "legacy_sources", "legacy_adoption_status",
        "legacy_limits", "s08_final_queue", "s08_r00_priority_tier", "auto_promoted", "reuse_instruction",
    ]
    write_csv("runs/issues/S08/candidate_reuse_map.csv", reuse_header, reuse_rows)

    bridge_header = [
        "security_id", "stock_name", "s04_l2_decision", "s04_decision_reason", "s04_blocking_gap",
        "s04_reentry_condition", "s05_destination", "s05_quality_decision", "s05_anchor_period",
        "s05_decision_reason", "observe_pool_recheck_status", "s06_missing_category",
        "s06_early_bucket", "s06_watch_reason", "bridge_basis", "drive_archive_id",
    ]
    write_csv("runs/issues/S08/s04_to_s05_bridge_445_to_278.csv", bridge_header, bridge_rows)

    handoff = f"""# S08 / #43 交接：指标轮验收与 R00 业务核验名单冻结

- 计划版本：`{PLAN_VERSION}`
- 生成时间（固定）：`{NOW}`
- 执行方：{EXECUTOR}；统筹方：{ORCHESTRATOR}；独立复核指派：{REVIEWER_ASSIGNED}
- 结论：`{stage_decision}`（对账异常 {len(anomalies)} 项）
- 放行控制：`release_R00=false`、`release_R02=false`、`issue_53_touched=false`

## 1. 全池 1,054 家对账

| 阶段 | 计数 |
|---|---|
| S03 宽筛 | 777 pass + 149 defer + 128 unknown = 1,054 |
| S04 收紧 | 445 家 `L2_SHORTLIST_CANDIDATE`（全部位于 wide_pass） |
| S05 质量 | 277 `QUALITY_PASS` + 1 `QUALITY_HOLD` + 776 `OBSERVE_POOL_PRESERVED` = 1,054 |
| S06 观察 | 早期 54 + 缺数据 379；交集 33；非主线并集 399 |
| S08 六分区 | 277 + 1 + 33 + 21 + 345 + 377 = 1,054 |

## 2. S07 F10 闭环：445 -> 278

`s04_to_s05_bridge_445_to_278.csv` 共 445 行，逐家去向：

- `ADMITTED_TO_S05_QUALITY_PASS`：277
- `ADMITTED_TO_S05_QUALITY_HOLD`：1（SZ:000856 冀东装备）
- `DEFERRED_TO_HOLD_FOR_DATA`：167

映射 100% 来自 Git 跟踪冻结表，并关联 Drive 归档 ID `{DRIVE_ARCHIVE_ID}`。

## 3. R00 主线优先级

- `TIER_1_EVIDENCED_AND_CLEAN_OR_LOW_RISK`：{tier_counts.get('TIER_1_EVIDENCED_AND_CLEAN_OR_LOW_RISK', 0)}
- `TIER_2_CLEAN_NO_QUALITY_TRIGGER`：{tier_counts.get('TIER_2_CLEAN_NO_QUALITY_TRIGGER', 0)}
- `TIER_3_TRIGGERED_OR_PENDING_QUALITY`：{tier_counts.get('TIER_3_TRIGGERED_OR_PENDING_QUALITY', 0)}
- 合计：277

说明：零触发共 {zero_trigger_total} 家；其中 {zero_trigger_pending} 家仍有 RH02/RH03/RH06 待核。{zero_t1} 家零触发历史资产进入 TIER_1（其中 {zero_t1_pending} 家带待核），{zero_t3} 家零触发带待核公司进入 TIER_3，{zero_t2} 家零触发无待核非历史资产进入 TIER_2。

## 4. 历史成果复用

- 旧 53 家采用：{len(adopt_by_id)}
- 旧 45 家条件细筛候选：{len(d45_by_id)}
- 10 家早期局部样本：{len(early_by_id)}
- B00：{len(b00_by_id)}；C00：{len(c00_by_id)}；D00：{len(d00_by_id)}
- 主表内并集：{len(legacy_union)}；`auto_promoted` 全部为 False
- 剔除不在主表的历史证券：`BJ:920007`（酉立智能）

旧“概念粗筛 20 家先读 PDF”顺序不再提前执行；R00 只按本冻结名单分 5 家小包执行。

## 5. 结转限制

F05 锚定期分层、F06 RH02 项目制豁免 31 家、F07 低基数冻结、F08 BJ 差异仅描述、F09 反向重推限 5 家、F10 已由本桥表闭环、F11 20 格越界值保留、F12 RH06 7 家待核。

守卫：4 家截止日隔离、1 家锚点待重选、15 家质量来源未知、8 项未采用父链、冀东 `SZ:000856` QUALITY_HOLD、`#53` 保持 OPEN。

## 6. 复现

```bash
S08_FIXED_NOW={NOW} py runs/issues/S08/step_s08_build.py
S08_FIXED_NOW={NOW} py runs/issues/S08/step_s08_verify.py
```

## 7. 下一步

等待 Codex 独立复核；未获独立验收前不启动 R00/R02，不开展公司业务深研或估值。
"""
    data = handoff.encode("utf-8")
    assert b"\r\n" not in data
    (REPO / "runs/issues/S08/handoff.md").write_bytes(data)

    print(f"S08 BUILD: universe={len(master_ids)} queues={dict(queue_counts)} "
          f"tiers={dict(tier_counts)} bridge={dict(bridge_counts)} legacy={len(legacy_union)} "
          f"decision={stage_decision} anomalies={len(anomalies)}")


if __name__ == "__main__":
    main()
