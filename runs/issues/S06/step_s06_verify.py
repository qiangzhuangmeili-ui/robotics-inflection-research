# -*- coding: utf-8 -*-
"""
S06 (#41) Independent Self-Check, Manifest & Review Generator.
Verifies all S06 deliverables against frozen S01/S02/S05 inputs and
writes runs/issues/S06/manifest.json and runs/issues/S06/review.json.
"""
import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
OUT = REPO / "runs" / "issues" / "S06"
NOW = datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_csv(rel: str):
    with open(REPO / rel, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def main():
    checks = []

    def rec(cid, name, passed, detail):
        checks.append({
            "id": cid,
            "name": name,
            "result": "PASS" if passed else "FAIL",
            "detail": detail,
        })

    # Load frozen baselines
    master = {r["security_id"]: r for r in load_csv("data/company_master.csv")}
    s05_pass = {r["security_id"]: r for r in load_csv("runs/issues/S05/quality_pass.csv")}
    s05_obs = {r["security_id"]: r for r in load_csv("runs/issues/S05/quality_observe.csv")}
    s05_776 = {r["security_id"]: r for r in load_csv("runs/issues/S05/observe_pool_preserved_776.csv")}
    s05_278 = set(s05_pass) | set(s05_obs)

    s02_path = "runs/issues/S02/hangcha_restated_20261101/s02_v10/all_pool_metrics.csv"
    s02_sha = sha256_file(REPO / s02_path)
    rec("C01", "S02 all_pool_metrics.csv SHA-256 与放行记录一致",
        s02_sha == "3091b0bb82a3e3114d7f338595c40d82c842ce47aa8802b141a6ce8ec2232953",
        f"actual={s02_sha}")

    rec("C02", "全池 1,054 主键守恒 (277+1+776=1,054 且互斥)",
        len(master) == 1054 and len(s05_pass) == 277 and len(s05_obs) == 1 and len(s05_776) == 776
        and not (set(s05_pass) & set(s05_obs))
        and not (s05_278 & set(s05_776))
        and (s05_278 | set(s05_776)) == set(master),
        f"master={len(master)}, pass={len(s05_pass)}, obs={len(s05_obs)}, 776={len(s05_776)}")

    # Load S06 CSV deliverables
    early = load_csv("runs/issues/S06/early_stage_watch.csv")
    missing = load_csv("runs/issues/S06/missing_data_watch.csv")
    early_sids = [r["security_id"] for r in early]
    missing_sids = [r["security_id"] for r in missing]

    rec("C03", "early_stage_watch.csv 主键唯一且全部属于冻结 1,054 主表",
        len(early_sids) == len(set(early_sids)) and set(early_sids).issubset(set(master)),
        f"rows={len(early)}, unique={len(set(early_sids))}")

    rec("C04", "early_stage_watch.csv 与 S05 278 主线 0 重叠（严格去重）",
        len(set(early_sids) & s05_278) == 0 and set(early_sids).issubset(set(s05_776)),
        f"overlap_278={len(set(early_sids) & s05_278)}")

    rec("C05", "missing_data_watch.csv 主键唯一且全部属于冻结 1,054 主表",
        len(missing_sids) == len(set(missing_sids)) and set(missing_sids).issubset(set(master)),
        f"rows={len(missing)}, unique={len(set(missing_sids))}")

    rec("C06", "missing_data_watch.csv 与 S05 277 quality_pass 0 重叠；仅含 1 家 S05_OBSERVE 结转并显式标注",
        len(set(missing_sids) & set(s05_pass)) == 0
        and (set(missing_sids) & set(s05_obs)) == {"SZ:000856"}
        and sum(1 for r in missing if r["mainline_dedup_status"] == "MAINLINE_S05_OBSERVE_CARRYOVER_DO_NOT_DOUBLE_COUNT") == 1,
        f"overlap_pass={len(set(missing_sids) & set(s05_pass))}, overlap_obs={sorted(set(missing_sids) & set(s05_obs))}")

    # Verify guards preserved in missing_data_watch.csv
    cut_rows = [r for r in missing if r["cutoff_isolated"] == "YES"]
    anc_rows = [r for r in missing if r["anchor_reselection_pending"] == "YES"]
    ce_rows = [r for r in missing if r["quality_source_state"] == "PENDING_CE_SOURCE"]
    hfd_rows = [r for r in missing if r["s04_l2_decision"] == "HOLD_FOR_DATA"]
    rec("C07", "4 家截止日后隔离守卫完整保留",
        {r["security_id"] for r in cut_rows} == {"SH:603448", "SH:688836", "SZ:301348", "SZ:301699"},
        f"cutoff_ids={sorted(r['security_id'] for r in cut_rows)}")

    rec("C08", "1 家锚点待重选守卫完整保留",
        {r["security_id"] for r in anc_rows} == {"SZ:002083"},
        f"anchor_ids={sorted(r['security_id'] for r in anc_rows)}")

    rec("C09", "15 家质量来源未知守卫完整保留",
        len(ce_rows) == 15,
        f"pending_ce_source={len(ce_rows)}")

    rec("C10", "328 家 S04 HOLD_FOR_DATA 完整保留",
        len(hfd_rows) == 328,
        f"hold_for_data={len(hfd_rows)}")

    # Verify zero concept-only reviewed exclusions leaked into early_stage_watch
    excluded_6 = {"BJ:920198", "BJ:920263", "BJ:920002", "SH:600699", "SH:603466", "SH:688327"}
    rec("C11", "6 家已核查概念/意向/证据不足公司与 1 家主表外公司未混入 early_stage_watch",
        len(set(early_sids) & (excluded_6 | {"BJ:920007"})) == 0,
        f"leaked={sorted(set(early_sids) & (excluded_6 | {'BJ:920007'}))}")

    # Verify every row has non-empty reason, source, reentry, and UNKNOWN (no 0-fill) for aux leading indicators
    early_fields_ok = all(
        r["watch_reason"].strip() and r["document_id_or_url"].strip() and r["reentry_trigger_conditions"].strip()
        and r["contract_liability_aux_status"] == "UNKNOWN"
        and r["order_backlog_aux_status"] == "UNKNOWN"
        and r["aux_method_version"] == "S06_AUX_LEAD_V1"
        for r in early
    )
    rec("C12", "early_stage_watch 每行具备观察理由、来源定位、重进条件且辅助观察缺披露记 UNKNOWN 不填零",
        early_fields_ok,
        f"checked={len(early)} rows")

    missing_fields_ok = all(
        r["watch_reason"].strip() and r["source_locator"].strip() and r["reentry_trigger_conditions"].strip()
        for r in missing
    )
    rec("C13", "missing_data_watch 每行具备观察理由、来源定位与可验证重进条件",
        missing_fields_ok,
        f"checked={len(missing)} rows")

    # Verify every evidence_id in early_stage_watch resolves in authoritative source registers
    known_eids = set()
    for rel in [
        "archive/R1_batch01_parent_reviewed_20261024/evidence_register.csv",
        "archive/R1_02A_parent_reviewed_20261024/evidence_register_reviewed.csv",
        "archive/02A_supplement/evidence_register_reviewed.csv",
        "archive/02B/evidence_register_reviewed.csv",
        "archive/early_sample_evidence.csv",
        "packages/C00_PILOT_01/results/evidence.csv",
    ]:
        for r in load_csv(rel):
            known_eids.add(r["evidence_id"].strip())

    unresolved_eids = []
    for r in early:
        for eid in r["evidence_ids"].split(";"):
            eid = eid.strip()
            if eid and eid not in known_eids:
                unresolved_eids.append((r["security_id"], eid))
    rec("C14", "early_stage_watch 所有 evidence_id 均可在权威源登记表解析",
        len(unresolved_eids) == 0,
        f"unresolved={unresolved_eids}")

    # Verify in_early_stage_watch cross-flag exactness
    marked_in_early = {r["security_id"] for r in missing if r["in_early_stage_watch"] == "YES"}
    actual_overlap = set(early_sids) & set(missing_sids)
    rec("C15", "两表交集标记 in_early_stage_watch 与实际主键交集完全一致",
        marked_in_early == actual_overlap,
        f"overlap={len(actual_overlap)}")

    # Verify prose numbers in watch_reentry_rules.md and handoff.md
    rules_txt = (OUT / "watch_reentry_rules.md").read_text(encoding="utf-8")
    handoff_txt = (OUT / "handoff.md").read_text(encoding="utf-8")
    prose_ok = (
        f"**{len(early)} 家**" in rules_txt
        and f"**{len(missing)} 家**" in rules_txt
        and "S06_AUX_LEAD_V1" in rules_txt
        and "METHOD_20261107_LEADING_INDICATORS" in rules_txt
        and f"**{len(early)} 家**" in handoff_txt
        and f"**{len(missing)} 家**" in handoff_txt
        and "SELF_CHECK" in handoff_txt
    )
    rec("C16", "watch_reentry_rules.md 与 handoff.md 核心计数与口径版本和 CSV 实算一致",
        prose_ok,
        f"early={len(early)}, missing={len(missing)}")

    # Verify all checks passed
    passed_cnt = sum(1 for c in checks if c["result"] == "PASS")
    all_pass = (passed_cnt == len(checks))

    # ------------------------------------------------------------------
    # Write review.json (SELF_CHECK)
    # ------------------------------------------------------------------
    early_bucket_cnt = Counter(r["watch_bucket"] for r in early)
    missing_cat_cnt = Counter(r["missing_data_category"] for r in missing)
    non_mainline_missing = sum(1 for r in missing if r["mainline_dedup_status"] == "NON_MAINLINE_776")

    review_obj = {
        "artifact": "S06_SELF_CHECK_REVIEW",
        "issue_key": "S06",
        "issue_number": 41,
        "plan_version": "20261026_collection_first_v2",
        "knowledge_as_of": "2026-10-25",
        "executor": "Antigravity",
        "reviewer_assigned": "Codex",
        "review_nature": "SELF_CHECK",
        "independent_review_complete": False,
        "reviewed_at": NOW,
        "decision": "SELF_CHECK_PASS_WITH_LIMITS" if all_pass else "SELF_CHECK_FAIL",
        "release_basis": {
            "release_file": "runs/issues/S06/release_20261122.json",
            "handoff_file": "runs/issues/S06/handoff_from_s05_20261122.md",
            "method_decision": "data/methodology_decision_20261107.json",
            "aux_method_version": "S06_AUX_LEAD_V1",
        },
        "counts": {
            "universe": 1054,
            "s05_mainline_pass": 277,
            "s05_mainline_observe": 1,
            "s05_carryover_776": 776,
            "early_stage_watch_total": len(early),
            "early_stage_by_bucket": dict(early_bucket_cnt),
            "missing_data_watch_total": len(missing),
            "missing_data_non_mainline_776": non_mainline_missing,
            "missing_data_mainline_observe_carryover": len(missing) - non_mainline_missing,
            "missing_data_by_category": dict(missing_cat_cnt),
            "overlap_early_and_missing": len(actual_overlap),
            "union_non_mainline_watch": len(set(early_sids) | {r["security_id"] for r in missing if r["mainline_dedup_status"] == "NON_MAINLINE_776"}),
            "overlap_with_s05_quality_pass": 0,
            "overlap_early_with_s05_278": 0,
            "reviewed_concept_or_insufficient_excluded": len(excluded_6),
        },
        "guards_preserved": {
            "after_cutoff_companies": 4,
            "anchor_reselection_pending": 1,
            "quality_source_unknown_companies": 15,
            "unadopted_parent_members": 8,
            "s05_quality_observe_jidong": 1,
            "s00_errata_issue_53": "OPEN",
            "historical_44_231_378": "NON_AUTHORITATIVE_HISTORY",
        },
        "checks_summary": f"{passed_cnt}/{len(checks)} PASS",
        "checks": checks,
        "limits": [
            "执行方自检（SELF_CHECK）不等同独立验收，须由 Codex 独立复核后决定是否验收与放行 S07。",
            "仅复用已有可追溯证据（archive 53 家旧采用附限制、10 家早期样本局部断言、B00/C00/D00）与 S02/S05 冻结快照，未扩大全池采集或逐家企业深研。",
            "合同负债不在 P04/S00 冻结标准化字段内，且无全池结构化在手订单台账；非主线观察行在 S06_AUX_LEAD_V1 中统一记 UNKNOWN，不填 0、不据此淘汰。",
            "观察名单不是买入推荐、投资候选或已商业化认定，不得跳过 S07/S08 进入估值。",
            "S00 勘误 #53 与 8 项未采用父链提议、15 家质量来源未知、4 家截止日后隔离、1 家锚点待重选及 S05 专门待核均原样结转，本次未闭合 #53。",
        ],
        "release_S07": False,
        "release_S08": False,
        "issue_53_touched": False,
    }
    (OUT / "review.json").write_text(json.dumps(review_obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # ------------------------------------------------------------------
    # Write manifest.json (hashes of inputs + deliverables + root digest)
    # ------------------------------------------------------------------
    input_paths = [
        "runs/issues/S06/release_20261122.json",
        "runs/issues/S06/handoff_from_s05_20261122.md",
        "runs/issues/S01/acceptance_20261029.json",
        "runs/issues/S02/acceptance_20261106/review.json",
        "runs/issues/S02/acceptance_20261106/s03_input_contract.json",
        "runs/issues/S02/hangcha_restated_20261101/s02_v10/all_pool_metrics.csv",
        "runs/issues/S05/acceptance_s05_r1_20261121.json",
        "runs/issues/S05/quality_pass.csv",
        "runs/issues/S05/quality_observe.csv",
        "runs/issues/S05/observe_pool_preserved_776.csv",
        "data/company_master.csv",
        "data/methodology_decision_20261107.json",
    ]
    deliverable_paths = [
        "runs/issues/S06/early_stage_watch.csv",
        "runs/issues/S06/missing_data_watch.csv",
        "runs/issues/S06/watch_reentry_rules.md",
        "runs/issues/S06/handoff.md",
        "runs/issues/S06/review.json",
        "runs/issues/S06/step_s06_build.py",
        "runs/issues/S06/step_s06_verify.py",
    ]

    inputs_meta = [
        {"path": p, "bytes": (REPO / p).stat().st_size, "sha256": sha256_file(REPO / p)}
        for p in input_paths
    ]
    deliv_meta = [
        {"path": p, "bytes": (REPO / p).stat().st_size, "sha256": sha256_file(REPO / p)}
        for p in deliverable_paths
    ]
    root_digest_src = "\n".join(f"{d['path']}:{d['sha256']}" for d in sorted(deliv_meta, key=lambda x: x["path"]))
    root_digest = hashlib.sha256(root_digest_src.encode("utf-8")).hexdigest()

    manifest_obj = {
        "artifact": "S06_DELIVERY_MANIFEST",
        "issue_key": "S06",
        "issue_number": 41,
        "plan_version": "20261026_collection_first_v2",
        "knowledge_as_of": "2026-10-25",
        "aux_method_version": "S06_AUX_LEAD_V1",
        "executor": "Antigravity",
        "review_nature": "SELF_CHECK",
        "generated_at": NOW,
        "manifest_root_digest": root_digest,
        "deliverable_count": len(deliv_meta),
        "inputs": inputs_meta,
        "deliverables": deliv_meta,
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest_obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"SELF_CHECK: {passed_cnt}/{len(checks)} PASS | root_digest={root_digest}")
    if not all_pass:
        for c in checks:
            if c["result"] != "PASS":
                print("  FAIL:", c)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
