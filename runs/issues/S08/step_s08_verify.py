# -*- coding: utf-8 -*-
"""
S08 (#43) Independent Self-Check, Manifest & Review Generator.

Every count, partition, tier, 445->278 mapping and legacy-reuse rule is
independently recomputed from the frozen upstream CSVs; no builder boolean is
trusted. Writes:
  - runs/issues/S08/review.json   (SELF_CHECK, executor CodeBuddy)
  - runs/issues/S08/manifest.json (CANONICAL_LF_BYTES inputs / EXACT_BYTES_LF deliverables)

Run after step_s08_build.py with the same S08_FIXED_NOW for byte-identical replay.
"""
import csv
import hashlib
import io
import json
import os
import subprocess
import sys
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

READ_INPUTS = [
    "runs/issues/S08/release_20261126.json",
    "runs/issues/S08/handoff_from_s07_20261126.md",
    "data/company_master.csv",
    "runs/issues/S01/acceptance_20261029.json",
    "runs/issues/S01/screen_rules_v3.json",
    "runs/issues/S01/screen_rules_v4.json",
    "runs/issues/S02/acceptance_20261106/review.json",
    "runs/issues/S02/acceptance_20261106/s03_input_contract.json",
    "runs/issues/S02/hangcha_restated_20261101/s02_v10/all_pool_metrics.csv",
    "runs/issues/S03/review.json",
    "runs/issues/S03/rerun_20261106/l1_screen_results.csv",
    "runs/issues/S03/rerun_20261106/wide_pass.csv",
    "runs/issues/S03/rerun_20261106/wide_defer.csv",
    "runs/issues/S03/rerun_20261106/wide_unknown.csv",
    "runs/issues/S04/codex_ruling_s05_v22_20261120.md",
    "runs/issues/S04/tight_decision_log.csv",
    "runs/issues/S05/acceptance_s05_r1_20261121.json",
    "runs/issues/S05/quality_pass.csv",
    "runs/issues/S05/quality_observe.csv",
    "runs/issues/S05/quality_decision_log.csv",
    "runs/issues/S05/quality_flags.csv",
    "runs/issues/S05/observe_pool_preserved_776.csv",
    "runs/issues/S05/rh06_adoption.csv",
    "runs/issues/S05/s05_out_of_valid_range.csv",
    "runs/issues/S06/acceptance_s06_r2_20261123.json",
    "runs/issues/S06/early_stage_watch.csv",
    "runs/issues/S06/missing_data_watch.csv",
    "runs/issues/S06/watch_reentry_rules.md",
    "runs/issues/S07/acceptance_s07_r3_20261126.json",
    "runs/issues/S07/screen_audit_review.json",
    "runs/issues/S07/screen_audit_findings.md",
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
EXPECTED_QUEUES = {
    "R00_MAINLINE_VERIFY": 277,
    "OBSERVE_QUALITY_HOLD": 1,
    "OBSERVE_EARLY_AND_MISSING": 33,
    "OBSERVE_EARLY_STAGE_ONLY": 21,
    "OBSERVE_MISSING_DATA_ONLY": 345,
    "NOT_SELECTED_FOR_R00": 377,
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


def split_set(value):
    return {x for x in (value or "").split(";") if x}


def anchor_label(period):
    return {"20260630": "H1", "20260930": "9M", "20260331": "Q1"}.get(period, period or "UNKNOWN")


def is_git_tracked(rel):
    try:
        r = subprocess.run(["git", "-C", str(REPO), "ls-files", "--error-unmatch", rel],
                           capture_output=True, text=True)
        return r.returncode == 0
    except Exception:
        return False


def main():
    checks = []

    def rec(cid, name, passed, detail):
        checks.append({"id": cid, "name": name,
                       "result": "PASS" if passed else "FAIL", "detail": detail})

    # ---------------- load raw frozen data ----------------
    master = load_csv("data/company_master.csv")
    master_ids = [r["security_id"] for r in master]
    master_set = set(master_ids)
    master_by_id = {r["security_id"]: r for r in master}

    wp = {r["company_id"] for r in load_csv("runs/issues/S03/rerun_20261106/wide_pass.csv")}
    wd = {r["company_id"] for r in load_csv("runs/issues/S03/rerun_20261106/wide_defer.csv")}
    wu = {r["company_id"] for r in load_csv("runs/issues/S03/rerun_20261106/wide_unknown.csv")}
    s04 = {r["company_id"]: r for r in load_csv("runs/issues/S04/tight_decision_log.csv")}
    s04_445 = {k for k, r in s04.items() if r["l2_decision"] == "L2_SHORTLIST_CANDIDATE"}

    qp = {r["security_id"]: r for r in load_csv("runs/issues/S05/quality_pass.csv")}
    qo = {r["security_id"]: r for r in load_csv("runs/issues/S05/quality_observe.csv")}
    qdl = {r["security_id"]: r for r in load_csv("runs/issues/S05/quality_decision_log.csv")}
    ob = {r["security_id"]: r for r in load_csv("runs/issues/S05/observe_pool_preserved_776.csv")}
    rh06 = load_csv("runs/issues/S05/rh06_adoption.csv")
    oor_rows = load_csv("runs/issues/S05/s05_out_of_valid_range.csv")
    oor_ids = {r["security_id"] for r in oor_rows}
    rh06_pending_ids = {r["security_id"] for r in rh06 if r["adoption_status"].startswith("PENDING")}

    early = {r["security_id"]: r for r in load_csv("runs/issues/S06/early_stage_watch.csv")}
    missing = {r["security_id"]: r for r in load_csv("runs/issues/S06/missing_data_watch.csv")}

    # ---------------- legacy recomputation ----------------
    adopt = set()
    for p in [
        "archive/R1_batch01_parent_reviewed_20261024/classification_reviewed.csv",
        "archive/R1_02A_parent_reviewed_20261024/classification_reviewed.csv",
        "archive/02A_supplement/classification_reviewed.csv",
        "archive/02B/classification_reviewed.csv",
    ]:
        adopt |= {r["security_id"] for r in load_csv(p)}
    d45 = set()
    d45_pkg_by_id = {}
    for i in range(1, 10):
        pkg = f"D01_DETAIL_{i:02d}"
        ids = {r["security_id"] for r in load_csv(f"packages/{pkg}/assignment.csv")}
        d45 |= ids
        for sid in ids:
            d45_pkg_by_id.setdefault(sid, set()).add(pkg)
    early_legacy = {r["security_id"] for r in load_csv("archive/early_sample_proposals.csv")}
    b00_rows = []
    for p in ["packages/B00_SOURCE_01/results/screening.csv",
              "packages/B00_SOURCE_02/results/screening.csv"]:
        b00_rows.extend((p, r) for r in load_csv(p))
    b00 = {r["security_id"] for _, r in b00_rows}
    c00_rows = {r["security_id"]: r for r in load_csv("packages/C00_PILOT_01/results/screening.csv")}
    c00 = set(c00_rows)
    d00 = {r["security_id"] for r in load_csv("packages/D00_B00_ADVANCE_01/results/evidence.csv")}
    legacy = adopt | d45 | early_legacy | b00 | c00 | d00

    excluded = set()
    for _, r in b00_rows:
        if r["screening_decision"] == "DEFER":
            excluded.add(r["security_id"])
    for sid, r in c00_rows.items():
        if r["screening_decision"] == "DEFER":
            excluded.add(sid)
        if r["robot_exposure_proposal"] in {"CONCEPT_ONLY", "ASSOCIATE_NOT_CONSOLIDATED"}:
            excluded.add(sid)

    # ---------------- independent expected routing ----------------
    def trig(sid):
        return split_set(qp[sid]["rh_triggered"]) if sid in qp else set()

    def pend(sid):
        return split_set(qp[sid]["rh_pending"]) if sid in qp else set()

    def expected_queue(sid):
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

    def expected_tier(sid):
        q = expected_queue(sid)
        if q != "R00_MAINLINE_VERIFY":
            return "NOT_IN_R00_MAINLINE"
        if sid in legacy and sid not in excluded:
            return "TIER_1_EVIDENCED_AND_CLEAN_OR_LOW_RISK"
        if not trig(sid) and not (pend(sid) & {"RH02", "RH03", "RH06"}):
            return "TIER_2_CLEAN_NO_QUALITY_TRIGGER"
        return "TIER_3_TRIGGERED_OR_PENDING_QUALITY"

    expected = {sid: (expected_queue(sid), expected_tier(sid)) for sid in master_set}

    # ---------------- read deliverables ----------------
    cand_path = REPO / "runs/issues/S08/business_verification_candidates.csv"
    reuse_path = REPO / "runs/issues/S08/candidate_reuse_map.csv"
    bridge_path = REPO / "runs/issues/S08/s04_to_s05_bridge_445_to_278.csv"
    acc_path = REPO / "runs/issues/S08/screen_acceptance.json"
    for p in (cand_path, reuse_path, bridge_path, acc_path):
        if not p.exists():
            raise SystemExit(f"missing deliverable: {p}")
    candidates = load_csv("runs/issues/S08/business_verification_candidates.csv")
    reuse = load_csv("runs/issues/S08/candidate_reuse_map.csv")
    bridge = load_csv("runs/issues/S08/s04_to_s05_bridge_445_to_278.csv")
    acceptance = json.loads(acc_path.read_text(encoding="utf-8"))
    release = json.loads((REPO / "runs/issues/S08/release_20261126.json").read_text(encoding="utf-8"))

    # C01 input fingerprints
    fp_bad = []
    fps = {x["path"]: x for x in acceptance.get("input_fingerprints", [])}
    for rel in READ_INPUTS:
        if not (REPO / rel).exists():
            fp_bad.append(f"MISSING:{rel}")
            continue
        nb, sh = canonical_input_digest(rel)
        if rel not in fps or fps[rel]["bytes"] != nb or fps[rel]["sha256"] != sh:
            fp_bad.append(rel)
    rec("C01", "全部运行时输入存在，且 screen_acceptance 的 CANONICAL_LF_BYTES 指纹可逐份重算一致",
        not fp_bad and len(fps) == len(READ_INPUTS),
        f"inputs={len(READ_INPUTS)}, fingerprints={len(fps)}, bad={fp_bad}")

    # C02 universe & S03
    c02 = (len(master_ids) == 1054 and len(master_set) == 1054
           and len(wp) == 777 and len(wd) == 149 and len(wu) == 128
           and not (wp & wd) and not (wp & wu) and not (wd & wu)
           and (wp | wd | wu) == master_set)
    rec("C02", "1,054 家主键唯一；S03 宽筛 777+149+128 互斥且并集等于全池",
        c02, f"universe={len(master_ids)}, unique={len(master_set)}, "
             f"pass={len(wp)}, defer={len(wd)}, unknown={len(wu)}, union={len(wp | wd | wu)}")

    # C03 S04 baseline
    c03 = len(s04_445) == 445 and s04_445 <= wp
    rec("C03", "S04 基线 L2_SHORTLIST_CANDIDATE 严格 445 家且全部来自 wide_pass",
        c03, f"baseline={len(s04_445)}, outside_wide_pass={len(s04_445 - wp)}")

    # C04 S05 partition
    c04 = (len(qp) == 277 and len(qo) == 1 and len(ob) == 776
           and not (set(qp) & set(qo)) and not (set(qp) & set(ob)) and not (set(qo) & set(ob))
           and (set(qp) | set(qo) | set(ob)) == master_set
           and (set(qp) | set(qo)) <= s04_445)
    rec("C04", "S05 277+1+776 互斥且并集等于全池；278 质量池为 S04 445 的子集",
        c04, f"pass={len(qp)}, hold={len(qo)}, observe={len(ob)}, "
             f"union={len(set(qp) | set(qo) | set(ob))}, 278_subset={len((set(qp) | set(qo)) - s04_445) == 0}")

    # C05 S06 reconciliation
    nonmainline_union = (set(early) | set(missing)) - (set(qp) | set(qo))
    c05 = (len(early) == 54 and len(missing) == 379
           and len(set(early) & set(missing)) == 33
           and len(nonmainline_union) == 399
           and all(r["s05_mainline_dedup_status"] == "NON_MAINLINE_776" for r in early.values())
           and set(missing) & (set(qp) | set(qo)) == {"SZ:000856"})
    rec("C05", "S06 早期 54 / 缺数据 379 / 交集 33 / 非主线并集 399；唯一主线缺数据为冀东",
        c05, f"early={len(early)}, missing={len(missing)}, "
             f"inter={len(set(early) & set(missing))}, nonmainline_union={len(nonmainline_union)}, "
             f"mainline_missing={sorted(set(missing) & (set(qp) | set(qo)))}")

    # C06 final queue
    cand_ids = [r["security_id"] for r in candidates]
    queue_bad = [r["security_id"] for r in candidates
                 if (r["final_queue"], r["r00_priority_tier"]) != expected[r["security_id"]]]
    qcount = Counter(r["final_queue"] for r in candidates)
    c06 = (len(candidates) == 1054 and len(set(cand_ids)) == 1054
           and set(cand_ids) == master_set and not queue_bad
           and all(qcount.get(k, 0) == v for k, v in EXPECTED_QUEUES.items())
           and sum(qcount.values()) == 1054)
    rec("C06", "六分区逐家重算一致、互斥且合计严格 1,054（277/1/33/21/345/377）",
        c06, f"rows={len(candidates)}, unique={len(set(cand_ids))}, bad={len(queue_bad)}, counts={dict(qcount)}")

    # C07 tiers
    tcount = Counter(r["r00_priority_tier"] for r in candidates)
    r00 = [r for r in candidates if r["final_queue"] == "R00_MAINLINE_VERIFY"]
    tier_bad = [r["security_id"] for r in candidates
                if r["r00_priority_tier"] != expected[r["security_id"]][1]]
    c07 = (len(r00) == 277 and not tier_bad
           and set(r["security_id"] for r in r00) == set(qp)
           and tcount.get("NOT_IN_R00_MAINLINE", 0) == 777
           and sum(v for k, v in tcount.items() if k != "NOT_IN_R00_MAINLINE") == 277)
    rec("C07", "R00 优先级逐家重算一致；277 家分层合计 277，非 R00 全为 NOT_IN_R00_MAINLINE",
        c07, f"r00={len(r00)}, bad={len(tier_bad)}, tiers={dict(tcount)}")

    # C08 bridge
    bridge_ids = [r["security_id"] for r in bridge]
    bcount = Counter(r["s05_destination"] for r in bridge)
    bridge_bad = []
    for r in bridge:
        sid = r["security_id"]
        if sid not in s04_445:
            bridge_bad.append(f"{sid}:NOT_IN_445")
            continue
        if sid in qp:
            exp = "ADMITTED_TO_S05_QUALITY_PASS"
        elif sid in qo:
            exp = "ADMITTED_TO_S05_QUALITY_HOLD"
        else:
            exp = "DEFERRED_TO_HOLD_FOR_DATA"
        if r["s05_destination"] != exp:
            bridge_bad.append(f"{sid}:{r['s05_destination']}!={exp}")
    c08 = (len(bridge) == 445 and len(set(bridge_ids)) == 445
           and set(bridge_ids) == s04_445 and not bridge_bad
           and bcount.get("ADMITTED_TO_S05_QUALITY_PASS", 0) == 277
           and bcount.get("ADMITTED_TO_S05_QUALITY_HOLD", 0) == 1
           and bcount.get("DEFERRED_TO_HOLD_FOR_DATA", 0) == 167)
    rec("C08", "445→278 桥表逐家重算一致：277 通过 + 1 质量观察 + 167 转 HOLD_FOR_DATA",
        c08, f"rows={len(bridge)}, unique={len(set(bridge_ids))}, bad={bridge_bad}, counts={dict(bcount)}")

    # C09 reuse map
    reuse_ids = [r["security_id"] for r in reuse]
    reuse_bad = []
    for r in reuse:
        sid = r["security_id"]
        if sid not in legacy:
            reuse_bad.append(f"{sid}:NOT_LEGACY")
            continue
        if r["auto_promoted"] != "False":
            reuse_bad.append(f"{sid}:AUTO_PROMOTED")
        if r["s08_final_queue"] != expected[sid][0] or r["s08_r00_priority_tier"] != expected[sid][1]:
            reuse_bad.append(f"{sid}:QUEUE_TIER_MISMATCH")
        buckets = set(r["legacy_bucket"].split(";"))
        exp_buckets = set()
        if sid in adopt:
            exp_buckets.add("PRIOR_ADOPTED_53")
        if sid in d45:
            exp_buckets.add("CONDITIONAL_DETAIL_45")
        if sid in early_legacy:
            exp_buckets.add("EARLY_SAMPLE_10")
        if sid in b00:
            exp_buckets.add("B00_SOURCE")
        if sid in c00:
            exp_buckets.add("C00_PILOT")
        if sid in d00:
            exp_buckets.add("D00_ADVANCE")
        if buckets != exp_buckets:
            reuse_bad.append(f"{sid}:BUCKET")
    c09 = (len(reuse) == 80 and len(set(reuse_ids)) == 80
           and set(reuse_ids) == legacy and not reuse_bad
           and len(adopt) == 53 and len(d45) == 45 and len(early_legacy) == 10
           and len(b00) == 7 and len(c00) == 10 and len(d00) == 2)
    rec("C09", "历史复用映射 80 家逐家桶位/队列/优先级重算一致，auto_promoted 全为 False",
        c09, f"rows={len(reuse)}, unique={len(set(reuse_ids))}, bad={reuse_bad[:10]}, "
             f"53={len(adopt)}, 45={len(d45)}, 10={len(early_legacy)}, "
             f"b00={len(b00)}, c00={len(c00)}, d00={len(d00)}")

    # C10 no auto promotion / exclusion
    promoted = ([r["security_id"] for r in candidates if r["legacy_auto_promoted"] != "False"]
                + [r["security_id"] for r in reuse if r["auto_promoted"] != "False"])
    excl_record = acceptance.get("legacy_reuse", {}).get("excluded_not_in_universe", [])
    c10 = (not promoted and "BJ:920007" not in master_set
           and any(x.get("security_id") == "BJ:920007" for x in excl_record))
    rec("C10", "无历史资产自动提级；BJ:920007 已从复用映射剔除并在验收文件登记",
        c10, f"promoted={promoted}, excluded_recorded="
             f"{[x.get('security_id') for x in excl_record]}")

    # C11 carry-forward numbers
    h1 = sum(1 for r in list(qp.values()) + list(qo.values()) if r["anchor_period"] == "20260630")
    m9 = sum(1 for r in list(qp.values()) + list(qo.values()) if r["anchor_period"] == "20260930")
    rh02_na = sum(1 for r in qdl.values() if "RH02" in split_set(r["rh_not_applicable"]))
    rh06_pending = sum(1 for r in rh06 if r["adoption_status"].startswith("PENDING"))
    bj_u = sum(1 for s in master_set if s.startswith("BJ:"))
    bj_p = sum(1 for s in qp if s.startswith("BJ:"))
    cf = acceptance.get("carry_forward_limits", {})
    c11 = (cf["F05"]["H1_companies"] == h1 == 200
           and cf["F05"]["M9_companies"] == m9 == 78
           and cf["F06"]["rh02_not_applicable_companies"] == rh02_na == 31
           and cf["F11"]["out_of_valid_range_cells"] == len(oor_rows) == 20
           and cf["F11"]["companies"] == len(oor_ids) == 19
           and cf["F12"]["rh06_pending_companies"] == rh06_pending == 7
           and cf["F08"]["bj_universe"] == bj_u == 62
           and cf["F08"]["bj_pass"] == bj_p == 25
           and cf["F08"]["nonbj_universe"] == len(master_set) - bj_u == 992
           and cf["F08"]["nonbj_pass"] == len(qp) - bj_p == 252)
    rec("C11", "F05–F12 结转数值独立重算一致（H1 200/9M 78、RH02 31、越界 20 格/19 家、RH06 7、BJ 25/62）",
        c11, f"H1={h1}, 9M={m9}, rh02_na={rh02_na}, oor={len(oor_rows)}/{len(oor_ids)}, "
             f"rh06_pending={rh06_pending}, BJ={bj_p}/{bj_u}, nonBJ={len(qp)-bj_p}/{len(master_set)-bj_u}")

    # C12 guards
    cutoff = sum(1 for r in ob.values() if r["cutoff_isolated"] == "YES")
    anchor = sum(1 for r in ob.values() if r["anchor_reselection_pending"] == "YES")
    qsu = sum(1 for r in ob.values() if r["quality_source_state"] == "PENDING_CE_SOURCE")
    g = acceptance.get("guards", {})
    c12 = (cutoff == 4 and anchor == 1 and qsu == 15
           and "SZ:000856" in qo and g.get("jidong_quality_hold") == "SZ:000856"
           and g.get("S00_errata_issue_53") == "OPEN"
           and g.get("unadopted_parent_members") == release["guards"]["unadopted_parent_members"] == 8)
    rec("C12", "继承守卫完整：4 截止日隔离、1 锚点待重选、15 质量来源未知、8 未采用父链、冀东 HOLD、#53 OPEN",
        c12, f"cutoff={cutoff}, anchor={anchor}, qsu={qsu}, jidong={'SZ:000856' in qo}, "
             f"unadopted={g.get('unadopted_parent_members')}, issue53={g.get('S00_errata_issue_53')}")

    # C13 inputs Git-tracked or archive-verified
    missing_inputs = [p for p in READ_INPUTS if not (REPO / p).exists()]
    has_git = (REPO / ".git").exists()
    if has_git:
        untracked = [p for p in READ_INPUTS if not is_git_tracked(p)]
        c13 = (not missing_inputs and not untracked and len(READ_INPUTS) == len(set(READ_INPUTS)))
        c13_detail = f"git_index_check=ENFORCED, inputs={len(READ_INPUTS)}, missing={missing_inputs}, untracked={untracked}"
    else:
        expected_sha = {x["path"]: x["sha256"] for x in acceptance.get("input_fingerprints", [])}
        man = OUT / "manifest.json"
        if man.exists():
            try:
                for item in json.loads(man.read_text(encoding="utf-8")).get("inputs", []):
                    expected_sha[item["path"]] = item["sha256"]
            except Exception:
                pass
        uncovered = [p for p in READ_INPUTS if p not in expected_sha]
        sha_bad = []
        for p in READ_INPUTS:
            if p in expected_sha:
                _, got = canonical_input_digest(p)
                if got != expected_sha[p]:
                    sha_bad.append(p)
        c13 = (not missing_inputs and not sha_bad and not uncovered)
        c13_detail = (f"git_index_check=SKIPPED_NO_GIT_DIR_VERIFIED_BY_MANIFEST, inputs={len(READ_INPUTS)}, "
                      f"missing={missing_inputs}, sha_mismatch={sha_bad}, uncovered={uncovered}")
    rec("C13", "全部运行时输入存在且 100% 位于 Git 跟踪树内（无 .git 归档按冻结 SHA 兜底）",
        c13, c13_detail)

    # C14 pure LF
    crlf = [p for p in DELIVERABLES if (REPO / p).exists() and b"\r\n" in (REPO / p).read_bytes()]
    existing = [p for p in DELIVERABLES if (REPO / p).exists()]
    # review.json is written by this verifier after the checks; it is covered by C20.
    rec("C14", "全部已生成的 S08 交付物为纯 LF 换行（review.json 由 C20 复核）",
        len(existing) >= len(DELIVERABLES) - 1 and not crlf,
        f"existing={len(existing)}/{len(DELIVERABLES)}, crlf={crlf}")

    # C15 dynamic stage decision
    anomalies = []
    if len(master_ids) != 1054 or len(master_set) != 1054:
        anomalies.append("UNIVERSE_NOT_1054_UNIQUE")
    if len(wp) != 777 or len(wd) != 149 or len(wu) != 128 or (wp & wd) or (wp & wu) or (wd & wu):
        anomalies.append("S03_PARTITION_MISMATCH")
    if (wp | wd | wu) != master_set:
        anomalies.append("S03_UNION_NOT_UNIVERSE")
    if len(s04_445) != 445 or not s04_445 <= wp:
        anomalies.append("S04_BASELINE_NOT_445_IN_WIDE_PASS")
    if len(qp) != 277 or len(qo) != 1 or len(ob) != 776:
        anomalies.append("S05_PARTITION_MISMATCH")
    if (set(qp) | set(qo) | set(ob)) != master_set or (set(qp) & set(qo)) or (set(qp) & set(ob)) or (set(qo) & set(ob)):
        anomalies.append("S05_UNION_NOT_DISJOINT_UNIVERSE")
    if not (set(qp) | set(qo)) <= s04_445:
        anomalies.append("S05_278_NOT_SUBSET_OF_S04_445")
    deferred = s04_445 - set(qp) - set(qo)
    if len(deferred) != 167 or any(ob[s]["l2_decision"] != "HOLD_FOR_DATA" for s in deferred):
        anomalies.append("S04_TO_S05_DEFERRED_NOT_167_HOLD_FOR_DATA")
    if len(early) != 54 or len(missing) != 379:
        anomalies.append("S06_WATCH_COUNTS_MISMATCH")
    if len(set(early) & set(missing)) != 33 or len(nonmainline_union) != 399:
        anomalies.append("S06_INTERSECTION_OR_UNION_MISMATCH")
    if any(r["s05_mainline_dedup_status"] != "NON_MAINLINE_776" for r in early.values()):
        anomalies.append("S06_EARLY_NOT_NONMAINLINE")
    if len(set(missing) & set(qo)) != 1:
        anomalies.append("S06_MISSING_MAINLINE_NOT_JIDONG_ONLY")
    if len(candidates) != 1054 or sum(qcount.values()) != 1054:
        anomalies.append("CANDIDATE_ROW_COUNT_NOT_1054")
    for k, v in EXPECTED_QUEUES.items():
        if qcount.get(k, 0) != v:
            anomalies.append(f"QUEUE_COUNT_MISMATCH:{k}")
    if set(cand_ids) != master_set:
        anomalies.append("CANDIDATE_KEYS_NOT_UNIVERSE")
    if any(r["final_queue"] == "R00_MAINLINE_VERIFY" for r in candidates if r["security_id"] not in qp):
        anomalies.append("R00_CONTAINS_NON_QUALITY_PASS")
    if tcount.get("NOT_IN_R00_MAINLINE", 0) != 777:
        anomalies.append("TIER_NON_R00_COUNT_MISMATCH")
    if (len(bridge) != 445 or bcount.get("ADMITTED_TO_S05_QUALITY_PASS", 0) != 277
            or bcount.get("ADMITTED_TO_S05_QUALITY_HOLD", 0) != 1
            or bcount.get("DEFERRED_TO_HOLD_FOR_DATA", 0) != 167):
        anomalies.append("BRIDGE_445_TO_278_MISMATCH")
    if any(r["auto_promoted"] != "False" for r in reuse) or any(r["legacy_auto_promoted"] != "False" for r in candidates):
        anomalies.append("LEGACY_AUTO_PROMOTION_DETECTED")
    if "BJ:920007" in master_set:
        anomalies.append("EXCLUDED_LEGACY_SECURITY_PRESENT_IN_UNIVERSE")
    if release["guards"]["S00_errata_issue_53"] != "OPEN":
        anomalies.append("ISSUE_53_NOT_OPEN")
    if release["guards"]["jidong_quality_hold"] != "SZ:000856" or "SZ:000856" not in qo:
        anomalies.append("JIDONG_QUALITY_HOLD_MISMATCH")

    expected_decision = "ACCEPTED_WITH_LIMITS" if not anomalies else "NOT_ACCEPTED_PENDING_FIX"
    c15 = (acceptance.get("stage_decision") == expected_decision
           and acceptance.get("stage_decision_basis", {}).get("anomalies") == anomalies)
    rec("C15", "stage_decision 由实际对账异常清单动态推导，与独立重算的异常清单一致",
        c15, f"expected={expected_decision}, actual={acceptance.get('stage_decision')}, "
             f"anomalies={anomalies}")

    # C16 release control
    rc = acceptance.get("release_control", {})
    c16 = (rc.get("release_R00") is False and rc.get("release_R02") is False
           and rc.get("issue_53_touched") is False and rc.get("issue_53_status") == "OPEN")
    rec("C16", "release_R00=false、release_R02=false、issue_53_touched=false、#53 保持 OPEN",
        c16, f"release_control={rc}")

    # C17 candidate schema / reasons / notes
    required_cols = {
        "security_id", "stock_name", "market", "s03_partition", "s04_baseline_decision",
        "s04_to_s05_bridge_status", "s05_route", "s05_anchor_period", "s05_trigger_count",
        "s05_rh_triggers", "s05_pending_flags", "s05_out_of_valid_range_flag",
        "s06_early_bucket", "s06_missing_category", "has_legacy_asset", "legacy_sources",
        "legacy_auto_promoted", "final_queue", "r00_priority_tier", "decision_reason",
        "carry_forward_notes",
    }
    schema_bad = [r["security_id"] for r in candidates
                  if not required_cols <= set(r.keys()) or not r["decision_reason"] or not r["carry_forward_notes"]]
    token_bad = []
    for r in candidates:
        sid = r["security_id"]
        q = r["final_queue"]
        reason = r["decision_reason"]
        notes = r["carry_forward_notes"]
        if q == "R00_MAINLINE_VERIFY" and "S05 QUALITY_PASS" not in reason:
            token_bad.append(f"{sid}:REASON")
        if q == "OBSERVE_QUALITY_HOLD" and "S05 QUALITY_HOLD" not in reason:
            token_bad.append(f"{sid}:REASON")
        if q == "OBSERVE_EARLY_AND_MISSING" and "交集" not in reason:
            token_bad.append(f"{sid}:REASON")
        if q == "OBSERVE_EARLY_STAGE_ONLY" and "S06早期储备观察" not in reason:
            token_bad.append(f"{sid}:REASON")
        if q == "OBSERVE_MISSING_DATA_ONLY" and "S06缺数据观察" not in reason:
            token_bad.append(f"{sid}:REASON")
        if q == "NOT_SELECTED_FOR_R00" and s04[sid]["l2_decision"] not in reason:
            token_bad.append(f"{sid}:REASON")
        if anchor_label(r["s05_anchor_period"]) not in notes:
            token_bad.append(f"{sid}:ANCHOR")
        if sid.startswith("BJ:") and "BJ" not in notes:
            token_bad.append(f"{sid}:BJ")
        if sid in qp and "RH02" in split_set(qp[sid]["rh_not_applicable"]) and "F06" not in notes:
            token_bad.append(f"{sid}:F06")
        if sid in oor_ids and "F11" not in notes:
            token_bad.append(f"{sid}:F11")
        if sid in rh06_pending_ids and "F12" not in notes:
            token_bad.append(f"{sid}:F12")
        if sid in legacy and "不自动提级" not in notes:
            token_bad.append(f"{sid}:LEGACY")
        if sid in s04_445 and sid not in qp and sid not in qo and "HOLD_FOR_DATA" not in notes:
            token_bad.append(f"{sid}:HOLD")
    c17 = not schema_bad and not token_bad
    rec("C17", "候选表 21 列完整、理由非空且逐家包含队列/锚定/BJ/F06/F11/F12/复用/HOLD 必要标记",
        c17, f"schema_bad={schema_bad[:5]}, token_bad={token_bad[:10]}")

    # C18 bridge schema / basis
    bridge_required = {
        "security_id", "stock_name", "s04_l2_decision", "s04_decision_reason", "s04_blocking_gap",
        "s04_reentry_condition", "s05_destination", "s05_quality_decision", "s05_anchor_period",
        "s05_decision_reason", "observe_pool_recheck_status", "s06_missing_category",
        "s06_early_bucket", "s06_watch_reason", "bridge_basis", "drive_archive_id",
    }
    bridge_schema_bad = [r["security_id"] for r in bridge
                         if not bridge_required <= set(r.keys()) or not r["s05_decision_reason"]]
    basis_bad = [r["security_id"] for r in bridge
                 if DRIVE_ARCHIVE_ID not in r["bridge_basis"] or r["drive_archive_id"] != DRIVE_ARCHIVE_ID]
    deferred_bad = [r["security_id"] for r in bridge
                    if r["s05_destination"] == "DEFERRED_TO_HOLD_FOR_DATA"
                    and r["observe_pool_recheck_status"] != "CARRIED_FORWARD_UNCHANGED"]
    c18 = not bridge_schema_bad and not basis_bad and not deferred_bad
    rec("C18", "桥表字段完整、理由非空、100% 关联 Drive 归档 ID，167 家均标记 CARRIED_FORWARD_UNCHANGED",
        c18, f"schema_bad={bridge_schema_bad[:5]}, basis_bad={basis_bad[:5]}, deferred_bad={deferred_bad[:5]}")

    # C19 legacy sequence policy
    lsp = acceptance.get("legacy_sequence_policy", {})
    c19 = (lsp.get("old_concept_pre_screen_20_pdf_first") == "NOT_EXECUTED_EARLY"
           and lsp.get("r00_package_size") == 5
           and "5 家小包" in lsp.get("statement", "")
           and "不再提前执行" in lsp.get("statement", ""))
    rec("C19", "显式声明旧“概念粗筛 20 家先读 PDF”不再提前执行，R00 只按 5 家小包执行",
        c19, f"policy={lsp}")

    # C21 acceptance structure
    sv = acceptance.get("stage_versions", {})
    rec_struct = acceptance.get("reconciliation", {})
    c21 = (set(sv.keys()) >= {"S01", "S02", "S03", "S04", "S05", "S06", "S07"}
           and rec_struct.get("universe", {}).get("primary_keys") == 1054
           and rec_struct.get("S03", {}).get("sum") == 1054
           and rec_struct.get("S04_to_S05", {}).get("baseline_445") == 445
           and rec_struct.get("S04_to_S05", {}).get("frozen_278") == 278
           and rec_struct.get("S04_to_S05", {}).get("deferred_167") == 167
           and rec_struct.get("S05", {}).get("sum") == 1054
           and rec_struct.get("final_queue_partition", {}).get("sum") == 1054
           and rec_struct.get("bridge_445_to_278", {}).get("sum") == 445
           and len(acceptance.get("input_fingerprints", [])) == len(READ_INPUTS))
    rec("C21", "验收文件完整记录阶段版本、输入指纹与各阶段 1,054/445 守恒",
        c21, f"stage_versions={sorted(sv.keys())}, fingerprints={len(acceptance.get('input_fingerprints', []))}, "
             f"s03_sum={rec_struct.get('S03', {}).get('sum')}, s05_sum={rec_struct.get('S05', {}).get('sum')}, "
             f"queue_sum={rec_struct.get('final_queue_partition', {}).get('sum')}, "
             f"bridge_sum={rec_struct.get('bridge_445_to_278', {}).get('sum')}")

    # C22 ordering / duplicates
    def cand_sort_key(sid):
        q, t = expected[sid]
        qi, ti = QUEUE_ORDER.index(q), TIER_ORDER.index(t)
        if t == "TIER_2_CLEAN_NO_QUALITY_TRIGGER":
            return (qi, ti, qp[sid]["anchor_period"], -int(qp[sid]["dimension_count_after"]), sid)
        return (qi, ti, "", 0, sid)

    exp_cand_order = sorted(cand_ids, key=cand_sort_key)
    c22 = (cand_ids == exp_cand_order
           and [r["security_id"] for r in bridge] == sorted(bridge_ids)
           and [r["security_id"] for r in reuse] == sorted(reuse_ids)
           and len(set(bridge_ids)) == len(bridge_ids)
           and len(set(reuse_ids)) == len(reuse_ids))
    rec("C22", "三张交付表按固定排序键排列且主键无重复",
        c22, f"cand_order_ok={cand_ids == exp_cand_order}, "
             f"bridge_sorted={[r['security_id'] for r in bridge] == sorted(bridge_ids)}, "
             f"reuse_sorted={[r['security_id'] for r in reuse] == sorted(reuse_ids)}")

    # C23 zero-trigger tier breakdown reconciliation
    zt = acceptance.get("reconciliation", {}).get("r00_priority_tiers", {})
    z_ids = [sid for sid in qp if not trig(sid)]
    z_tier = Counter(expected_tier(sid) for sid in z_ids)
    z_pending = [sid for sid in z_ids if pend(sid) & {"RH02", "RH03", "RH06"}]
    z_t1_pending = sum(1 for sid in z_pending if expected_tier(sid) == "TIER_1_EVIDENCED_AND_CLEAN_OR_LOW_RISK")
    breakdown = zt.get("zero_trigger_tier_breakdown", {})
    c23 = (zt.get("zero_trigger_total") == len(z_ids) == 111
           and zt.get("zero_trigger_with_rh02_rh03_rh06_pending") == len(z_pending)
           and breakdown.get("TIER_1") == z_tier.get("TIER_1_EVIDENCED_AND_CLEAN_OR_LOW_RISK", 0)
           and breakdown.get("TIER_2") == z_tier.get("TIER_2_CLEAN_NO_QUALITY_TRIGGER", 0)
           and breakdown.get("TIER_3") == z_tier.get("TIER_3_TRIGGERED_OR_PENDING_QUALITY", 0)
           and breakdown.get("TIER_1_with_pending") == z_t1_pending
           and breakdown.get("TIER_3_pending") == z_tier.get("TIER_3_TRIGGERED_OR_PENDING_QUALITY", 0)
           and sum(breakdown.get(k, 0) for k in ("TIER_1", "TIER_2", "TIER_3")) == len(z_ids))
    rec("C23", "零触发 111 家的 TIER 分解与待核归属独立重算一致",
        c23, f"zero={len(z_ids)}, pending={len(z_pending)}, breakdown={breakdown}, "
             f"recomputed={dict(z_tier)}")

    passed_cnt = sum(1 for c in checks if c["result"] == "PASS")
    all_pass = passed_cnt == len(checks)

    review_obj = {
        "artifact": "S08_SELF_CHECK_REVIEW",
        "issue_key": ISSUE_KEY,
        "issue_number": ISSUE_NUMBER,
        "plan_version": PLAN_VERSION,
        "reviewed_on": "2026-11-26",
        "timezone": "Asia/Shanghai",
        "review_nature": "SELF_CHECK",
        "executor": EXECUTOR,
        "orchestrator": ORCHESTRATOR,
        "reviewer_assigned": REVIEWER_ASSIGNED,
        "review_method": (
            "独立重算 S03/S04/S05/S06 分区、1,054 六分区、277 家 R00 优先级、"
            "445→278 逐家映射、80 家历史复用桶位与非提级规则；不信任构建器布尔值。"
        ),
        "decision": "SELF_CHECK_PASS_WITH_LIMITS" if all_pass else "SELF_CHECK_FAIL",
        "checks_summary": f"{passed_cnt}/{len(checks)} PASS",
        "checks": checks,
        "limits": [
            "执行方自检（SELF_CHECK）不等同独立验收；须由 Codex 独立复核后决定是否验收。",
            "仅完成指标轮总对账与 R00 候选冻结，未启动业务深研、未估值、未放行 R00/R02。",
            "历史 53/45/10/B00/C00/D00 仅复用线索与原文入口，不自动提升验收状态。",
            "零触发 111 家中 71 家仍有 RH02/RH03/RH06 待核，按规则进入 TIER_3 或 TIER_1。",
            "BJ:920007 不在 1,054 冻结主表，已从复用映射剔除并登记。",
        ],
        "release_R00": False,
        "release_R02": False,
        "issue_53_touched": False,
    }
    (OUT / "review.json").write_bytes((json.dumps(review_obj, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))

    # ---------------- manifest ----------------
    inputs_meta = []
    for rel in READ_INPUTS:
        nb, sh = canonical_input_digest(rel)
        inputs_meta.append({"path": rel, "bytes": nb, "sha256": sh})
    deliv_meta = []
    for rel in DELIVERABLES:
        nb, sh = sha256_exact(REPO / rel)
        if b"\r\n" in (REPO / rel).read_bytes():
            raise SystemExit(f"CRLF in deliverable {rel}")
        deliv_meta.append({"path": rel, "bytes": nb, "sha256": sh})

    root_src = "\n".join(f"{d['path']}:{d['sha256']}" for d in sorted(deliv_meta, key=lambda x: x["path"]))
    root_digest = hashlib.sha256(root_src.encode("utf-8")).hexdigest()
    manifest_obj = {
        "artifact": "S08_DELIVERY_MANIFEST",
        "issue_key": ISSUE_KEY,
        "issue_number": ISSUE_NUMBER,
        "plan_version": PLAN_VERSION,
        "knowledge_as_of": KNOWLEDGE_AS_OF,
        "executor": EXECUTOR,
        "orchestrator": ORCHESTRATOR,
        "review_nature": "SELF_CHECK",
        "generated_at": NOW,
        "input_hash_basis": "CANONICAL_LF_BYTES",
        "input_hash_basis_note": "全部文本输入按 CRLF->LF 规范化后计算字节数与 SHA-256。",
        "deliverable_hash_basis": "EXACT_BYTES_LF",
        "replay_note": (
            "在干净 Git checkout 内以 S08_FIXED_NOW=<generated_at> 顺序运行 "
            "step_s08_build.py 与 step_s08_verify.py；C13 用 git ls-files 验证输入全部被跟踪。"
            "无 .git 的纯归档目录下 C13 自动改用冻结 SHA-256 清单核对，"
            "标注 git_index_check=SKIPPED_NO_GIT_DIR_VERIFIED_BY_MANIFEST。"
        ),
        "manifest_root_digest": root_digest,
        "input_count": len(inputs_meta),
        "deliverable_count": len(deliv_meta),
        "inputs": inputs_meta,
        "deliverables": deliv_meta,
    }
    (OUT / "manifest.json").write_bytes((json.dumps(manifest_obj, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))

    # C20 manifest self-consistency (after manifest exists)
    m = json.loads((OUT / "manifest.json").read_text(encoding="utf-8"))
    recomputed_root = hashlib.sha256(
        "\n".join(f"{d['path']}:{d['sha256']}" for d in sorted(m["deliverables"], key=lambda x: x["path"])).encode("utf-8")
    ).hexdigest()
    deliv_bad = []
    for d in m["deliverables"]:
        nb, sh = sha256_exact(REPO / d["path"])
        if nb != d["bytes"] or sh != d["sha256"]:
            deliv_bad.append(d["path"])
    crlf_all = [p for p in DELIVERABLES if b"\r\n" in (REPO / p).read_bytes()]
    c20 = (m["manifest_root_digest"] == recomputed_root
           and m["input_hash_basis"] == "CANONICAL_LF_BYTES"
           and m["deliverable_hash_basis"] == "EXACT_BYTES_LF"
           and m["input_count"] == len(READ_INPUTS)
           and m["deliverable_count"] == len(DELIVERABLES)
           and not deliv_bad and not crlf_all)
    checks.append({"id": "C20",
                   "name": "manifest 根摘要、输入/交付数量与逐份交付哈希自洽且全部交付为纯 LF",
                   "result": "PASS" if c20 else "FAIL",
                   "detail": f"root_match={m['manifest_root_digest'] == recomputed_root}, "
                             f"inputs={m['input_count']}, deliverables={m['deliverable_count']}, "
                             f"bad={deliv_bad}, crlf={crlf_all}"})

    passed_cnt = sum(1 for c in checks if c["result"] == "PASS")
    all_pass = passed_cnt == len(checks)

    # finalize review with C20
    review_obj["checks"] = checks
    review_obj["checks_summary"] = f"{passed_cnt}/{len(checks)} PASS"
    review_obj["decision"] = "SELF_CHECK_PASS_WITH_LIMITS" if all_pass else "SELF_CHECK_FAIL"
    (OUT / "review.json").write_bytes((json.dumps(review_obj, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))

    # refresh review hash and root, then final manifest
    for d in manifest_obj["deliverables"]:
        if d["path"] == "runs/issues/S08/review.json":
            d["bytes"], d["sha256"] = sha256_exact(OUT / "review.json")
    final_root = hashlib.sha256(
        "\n".join(f"{d['path']}:{d['sha256']}" for d in sorted(manifest_obj["deliverables"], key=lambda x: x["path"])).encode("utf-8")
    ).hexdigest()
    manifest_obj["manifest_root_digest"] = final_root
    manifest_obj["self_check"] = {
        "checks_total": len(checks),
        "checks_passed": passed_cnt,
        "deliverables_verified": not deliv_bad,
        "pure_lf": not crlf_all,
    }
    (OUT / "manifest.json").write_bytes((json.dumps(manifest_obj, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))

    # verify final manifest is self-consistent after review refresh
    final_manifest = json.loads((OUT / "manifest.json").read_text(encoding="utf-8"))
    final_root_check = hashlib.sha256(
        "\n".join(f"{d['path']}:{d['sha256']}" for d in sorted(final_manifest["deliverables"], key=lambda x: x["path"])).encode("utf-8")
    ).hexdigest()
    final_ok = (final_root_check == final_manifest["manifest_root_digest"]
                and all(sha256_exact(REPO / d["path"])[1] == d["sha256"] for d in final_manifest["deliverables"]))

    print(f"S08 SELF_CHECK: {passed_cnt}/{len(checks)} PASS | inputs={len(inputs_meta)} | "
          f"deliverables={len(deliv_meta)} | root={final_root} | final_manifest_ok={final_ok}")
    if not all_pass or not final_ok:
        for c in checks:
            if c["result"] != "PASS":
                print("  FAIL:", c)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
