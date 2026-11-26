# -*- coding: utf-8 -*-
"""
S07 (#42) Independent Self-Check, Manifest & Review Generator.

Verifies every S07 deliverable against the frozen S01/S02/S03/S04/S05/S06 inputs,
enforces pure-LF deliverables, checks that all runtime inputs are Git-tracked,
recomputes the manifest root digest, and writes:
  - runs/issues/S07/review.json   (SELF_CHECK, executor CodeBuddy)
  - runs/issues/S07/manifest.json (CANONICAL_LF_BYTES inputs / EXACT_BYTES_LF deliverables)

Run after step_s07_build.py with the same S07_FIXED_NOW for byte-identical replay.
"""
import csv
import hashlib
import json
import os
import subprocess
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
OUT = REPO / "runs" / "issues" / "S07"
NOW = os.environ.get("S07_FIXED_NOW") or datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")

sys.path.insert(0, str(OUT))
from step_s07_build import (  # noqa: E402
    EXECUTOR,
    FLOAT_TOL,
    ISSUE_KEY,
    ISSUE_NUMBER,
    KNOWLEDGE_AS_OF,
    ORCHESTRATOR,
    PLAN_VERSION,
    READ_INPUTS,
    RELEASE_SHA,
    REVIEWER_ASSIGNED,
    STRATUM_ORDER,
    canonical_input_digest,
    sha256_exact,
)


def load_csv(rel: str):
    with open(REPO / rel, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def is_git_tracked(rel: str) -> bool:
    try:
        r = subprocess.run(["git", "-C", str(REPO), "ls-files", "--error-unmatch", rel],
                           capture_output=True, text=True)
        return r.returncode == 0
    except Exception:
        return False


def main():
    checks = []

    def rec(cid, name, passed, detail):
        checks.append({"id": cid, "name": name, "result": "PASS" if passed else "FAIL", "detail": detail})

    # ---------------- load frozen baselines ----------------
    master = load_csv("data/company_master.csv")
    master_ids = {r["security_id"] for r in master}
    s05_pass = load_csv("runs/issues/S05/quality_pass.csv")
    s05_obs = load_csv("runs/issues/S05/quality_observe.csv")
    s05_776 = load_csv("runs/issues/S05/observe_pool_preserved_776.csv")
    pass_ids = {r["security_id"] for r in s05_pass}
    obs_ids = {r["security_id"] for r in s05_obs}
    pool_ids = {r["security_id"] for r in s05_776}
    s05_278 = pass_ids | obs_ids
    s06_missing = load_csv("runs/issues/S06/missing_data_watch.csv")
    s06_early = load_csv("runs/issues/S06/early_stage_watch.csv")
    oor = load_csv("runs/issues/S05/s05_out_of_valid_range.csv")
    wp = {r["company_id"] for r in load_csv("runs/issues/S03/rerun_20261106/wide_pass.csv")}
    wd = {r["company_id"] for r in load_csv("runs/issues/S03/rerun_20261106/wide_defer.csv")}
    wu = {r["company_id"] for r in load_csv("runs/issues/S03/rerun_20261106/wide_unknown.csv")}
    release = json.loads((REPO / "runs/issues/S07/release_20261126.json").read_text(encoding="utf-8"))

    # ---------------- C01 input hashes ----------------
    hash_fail = []
    for rel, exp in RELEASE_SHA.items():
        _, got = canonical_input_digest(rel)
        if got != exp:
            hash_fail.append((rel, got, exp))
    rec("C01", "18 份冻结输入按 CANONICAL_LF_BYTES（gzip 用 EXACT_BYTES）重算 SHA-256 与放行记录一致",
        not hash_fail, f"checked={len(RELEASE_SHA)}, mismatches={hash_fail}")

    # ---------------- C02 universe conservation ----------------
    partition_ok = (len(wp) == 777 and len(wd) == 149 and len(wu) == 128
                    and not (wp & wd) and not (wp & wu) and not (wd & wu)
                    and (wp | wd | wu) == master_ids)
    rec("C02", "全池 1,054 主键守恒 (277+1+776=1,054 且互斥) 且 S03 777+149+128 分区完整互斥",
        len(master) == 1054 and len(pass_ids) == 277 and len(obs_ids) == 1 and len(pool_ids) == 776
        and not (pass_ids & obs_ids) and not (s05_278 & pool_ids) and (s05_278 | pool_ids) == master_ids
        and partition_ok,
        f"master={len(master)}, pass={len(pass_ids)}, obs={len(obs_ids)}, 776={len(pool_ids)}, "
        f"wide=({len(wp)},{len(wd)},{len(wu)})")

    # ---------------- C03 sample integrity ----------------
    sample = load_csv("runs/issues/S07/screen_audit_sample.csv")
    sids = [r["security_id"] for r in sample]
    rec("C03", "抽样清单主键唯一、全部属于 1,054 主表、样本量在 50–65 家",
        len(sids) == len(set(sids)) and set(sids).issubset(master_ids) and 50 <= len(sids) <= 65,
        f"rows={len(sids)}, unique={len(set(sids))}")

    # ---------------- C04 six strata covered ----------------
    sc = Counter(r["primary_stratum"] for r in sample)
    rec("C04", "六个分层均有主样本覆盖",
        all(sc.get(s, 0) > 0 for s in STRATUM_ORDER),
        f"counts={dict(sc)}")

    # ---------------- C05 slot quotas ----------------
    audit_review = json.loads((OUT / "screen_audit_review.json").read_text(encoding="utf-8"))
    slots = audit_review["sampling"]["slots"]
    slot_ok = all(s["filled"] <= s["quota"] for s in slots) and sum(s["filled"] for s in slots) == len(sample)
    rec("C05", "每个子槽实取不超过配额，子槽合计等于样本量",
        slot_ok, f"slots={len(slots)}, filled_sum={sum(s['filled'] for s in slots)}, rows={len(sample)}")

    # ---------------- C06 recomputation consistency ----------------
    non_exact = [r["security_id"] for r in sample if r["recompute_consistency"] != "EXACT"]
    bad_counts = [r["security_id"] for r in sample
                  if int(r["metrics_compared"]) != 12
                  or int(r["metrics_status_match"]) != 12
                  or int(r["metrics_value_match"]) != 12]
    max_diff = max(float(r["recompute_max_abs_diff"]) for r in sample)
    anchor_bad = [r["security_id"] for r in sample if r["latest_period_check"] != "MATCH"]
    rec("C06", "全部样本 12 项指标状态与数值逐格复算一致、锚定期间独立推导一致",
        not non_exact and not bad_counts and max_diff <= FLOAT_TOL and not anchor_bad,
        f"non_exact={non_exact}, bad_counts={bad_counts}, max_diff={max_diff:.3e}, anchor_bad={anchor_bad}")

    # ---------------- C07 S03 route ----------------
    s03_mis = [r["security_id"] for r in sample if r["s03_route_check"] == "MISMATCH"]
    s03_override = sum(1 for r in sample if r["s03_route_check"] == "FROZEN_OVERRIDE")
    s03_ok = sum(1 for r in sample if r["s03_route_check"] == "CONSISTENT")
    rec("C07", "S03 L1 bucket/subtag 由复算指标重放：0 不一致（底稿/截止日覆盖单列）",
        not s03_mis and s03_ok + s03_override == len(sample),
        f"consistent={s03_ok}, override={s03_override}, mismatch={s03_mis}")

    # ---------------- C08 S04 boundary ----------------
    s04_mis = [r["security_id"] for r in sample if r["s04_route_check"] == "MISMATCH"]
    rec("C08", "S04 维度计数/候选判定内部一致", not s04_mis, f"mismatch={s04_mis}")

    # ---------------- C09 S05/S06 route ----------------
    s05_mis = [r["security_id"] for r in sample if r["s05_route_check"] == "MISMATCH"]
    s06_mis = [r["security_id"] for r in sample if r["s06_route_check"] == "MISMATCH"]
    rec("C09", "S05 RH 阈值与越界复核、S06 五项计数复核均无差异",
        not s05_mis and not s06_mis, f"s05_mismatch={s05_mis}, s06_mismatch={s06_mis}")

    # ---------------- C10 reverse omission ----------------
    rev = [r for r in sample if r["primary_stratum"] == "REVERSE_OMISSION"]
    rev_bad = [r["security_id"] for r in rev if not r["omission_verdict"].startswith("RULE_CONSISTENT")]
    rev_in_main = [r["security_id"] for r in rev if r["security_id"] in pass_ids]
    rec("C10", "反向漏筛样本全部为规则性排除/待核，且无一家被手工加入 S05 277 主线",
        not rev_bad and not rev_in_main,
        f"reverse_rows={len(rev)}, non_rule={rev_bad}, in_mainline={rev_in_main}")

    # ---------------- C11 guards ----------------
    cut = sum(1 for r in s06_missing if r["cutoff_isolated"] == "YES")
    anc = sum(1 for r in s06_missing if r["anchor_reselection_pending"] == "YES")
    ce = sum(1 for r in s06_missing if r["quality_source_state"] == "PENDING_CE_SOURCE")
    jid = "SZ:000856" in obs_ids
    rec("C11", "继承守卫完整：4 家截止日隔离、1 家锚点待重选、15 家质量来源未知、冀东 QUALITY_HOLD、#53 OPEN",
        cut == 4 and anc == 1 and ce == 15 and jid and release["guards"]["S00_errata_issue_53"] == "OPEN",
        f"cutoff={cut}, anchor={anc}, ce={ce}, jidong={jid}, issue53={release['guards']['S00_errata_issue_53']}")

    # ---------------- C12 pure LF ----------------
    deliverables = [
        "runs/issues/S07/screen_audit_sample.csv",
        "runs/issues/S07/screen_audit_findings.md",
        "runs/issues/S07/screen_audit_review.json",
        "runs/issues/S07/handoff.md",
        "runs/issues/S07/review.json",
        "runs/issues/S07/step_s07_build.py",
        "runs/issues/S07/step_s07_verify.py",
    ]
    existing = [p for p in deliverables if (REPO / p).exists()]
    crlf = [p for p in existing if b"\r\n" in (REPO / p).read_bytes()]
    rec("C12", "已生成的 S07 交付物均为纯 LF 换行（review.json 由 C20 复核）",
        len(existing) >= 6 and not crlf, f"existing={len(existing)}, crlf_files={crlf}")

    # ---------------- C13 inputs Git-tracked ----------------
    missing_inputs = [p for p in READ_INPUTS if not (REPO / p).exists()]
    untracked = [p for p in READ_INPUTS if not is_git_tracked(p)]
    rec("C13", "全部运行时输入存在且 100% 位于 Git 跟踪文件树内",
        not missing_inputs and not untracked and len(READ_INPUTS) == len(set(READ_INPUTS)),
        f"inputs={len(READ_INPUTS)}, missing={missing_inputs}, untracked={untracked}")

    # ---------------- C14 required sub-feature coverage ----------------
    slot_ids = {r["selection_slot"] for r in sample}
    need_slots = {
        "B01_S03_MIN_2DIM", "B02_S03_MIN_1DIM", "B03_S03_DEFER_RISK",
        "B04_S04_MIN2_PASS", "B05_S04_ONE_DIM_FAIL", "B06_S04_ABS_SG06",
        "B07_S04_LOWBASE_CONFIRMED", "B09_RH06_TRIGGER", "B10_OUT_OF_VALID_RANGE",
        "B08_RH_TRIGGERED_NEAR",
        "J01_BJ_PASS_H1", "J02_BJ_PASS_9M", "J03_BJ_S04_CAND_NOT_PASS",
        "J04_BJ_RISK_OR_NO_SIGNAL", "J05_BJ_MISSING_WATCH",
        "L01_LOSS_M05_UNDEFINED", "L02_M07_UNDEFINED_BASE", "L03_LOWBASE_PROVISIONAL",
        "L04_LOWBASE_CONFIRMED_EXTRA", "M01_AFTER_CUTOFF", "M02_ANCHOR_PENDING",
        "M03_QUALITY_HOLD_JIDONG", "M04_QUALITY_SOURCE_UNKNOWN",
        "M05_HOLD_AND_QUALITY_UNKNOWN", "M06_S04_HOLD_FOR_DATA", "M07_S02_HOLD_OR_MISSING",
        "E01_EARLY_RD", "E02_EARLY_PILOT", "E03_EVIDENCED_UNKNOWN", "E04_COMMERCIAL_RESERVE",
        "R01_NOT_IN_SCOPE", "R02_HOLD_FOR_DATA", "R03_NOT_SHORTLISTED",
    }
    missing_slots = sorted(need_slots - slot_ids)
    rh_slots = {f"B08_{rh}_NEAR" for rh in ("RH01", "RH02", "RH03", "RH04", "RH05")}
    missing_rh = sorted(rh_slots - slot_ids)
    rec("C14", "全部边界/市场/低基数/缺数据/早期/反向子槽均有代表（含 RH01–RH05 临界）",
        not missing_slots and not missing_rh,
        f"missing_slots={missing_slots}, missing_rh={missing_rh}")

    # ---------------- C15 missing categories & early buckets ----------------
    miss_cats = {r["missing_data_category"] for r in s06_missing}
    early_buckets = {r["watch_bucket"] for r in s06_early}
    sample_cats = {r["s06_missing_category"] for r in sample if r["s06_missing_category"]}
    sample_buckets = {r["s06_early_bucket"] for r in sample if r["s06_early_bucket"]}
    rec("C15", "S06 缺失观察 7 类与早期储备 4 桶在样本中全部覆盖",
        miss_cats == sample_cats and early_buckets == sample_buckets,
        f"missing_categories={sorted(sample_cats)}, early_buckets={sorted(sample_buckets)}")

    # ---------------- C16 out-of-range representatives ----------------
    oor_pairs = {(r["security_id"], r["metric_id"]) for r in oor}
    sample_oor = []
    for r in sample:
        if "OUT_OF_VALID_RANGE" not in r["boundary_attributes"]:
            continue
        for m in ("M08", "M10", "M12"):
            if f"{m}=" in r["boundary_attributes"]:
                sample_oor.append((r["security_id"], m))
    sample_oor = [p for p in sample_oor if p in oor_pairs]
    rec("C16", "越界样本确实来自 s05_out_of_valid_range.csv 且覆盖 M08/M10/M12",
        len(sample_oor) >= 3 and {m for _, m in sample_oor} >= {"M08", "M10", "M12"},
        f"pairs={sample_oor}")

    # ---------------- C17 findings/review counts ----------------
    findings_txt = (OUT / "screen_audit_findings.md").read_text(encoding="utf-8")
    handoff_txt = (OUT / "handoff.md").read_text(encoding="utf-8")
    counts_ok = (
        f"**{len(sample)} 家**" in findings_txt
        and f"**{len(sample)} 家**" in handoff_txt
        and f"共 **{len(s06_missing)} 家**" in findings_txt
        and f"| BOUNDARY_PASS_FAIL | {sc.get('BOUNDARY_PASS_FAIL', 0)} |" in findings_txt
    )
    rec("C17", "报告/交接中的样本量与 S06 观察总数与 CSV 实算一致",
        counts_ok, f"sample={len(sample)}, missing={len(s06_missing)}")

    # ---------------- C18 structured review grading ----------------
    gr = audit_review.get("grading", {})
    rec("C18", "结构化审计结论无 SYSTEMIC_BLOCKER、无需回退 S00/S01、不释放 S08",
        gr.get("systemic_blocker") is False
        and gr.get("requires_s00_s01_rollback") is False
        and audit_review.get("release_S08") is False
        and audit_review.get("issue_53_touched") is False,
        f"grading={gr}")

    # ---------------- C19 upstream zero mutation ----------------
    rec("C19", "冻结输入哈希零漂移（C01 已逐份核验），S07 未改写任何上游文件",
        not hash_fail and not missing_inputs,
        f"hash_mismatches={len(hash_fail)}, missing_inputs={len(missing_inputs)}")

    passed_cnt = sum(1 for c in checks if c["result"] == "PASS")
    all_pass = passed_cnt == len(checks)

    # ---------------- write review.json ----------------
    review_obj = {
        "artifact": "S07_SELF_CHECK_REVIEW",
        "issue_key": ISSUE_KEY,
        "issue_number": ISSUE_NUMBER,
        "plan_version": PLAN_VERSION,
        "knowledge_as_of": KNOWLEDGE_AS_OF,
        "executor": EXECUTOR,
        "orchestrator": ORCHESTRATOR,
        "reviewer_assigned": REVIEWER_ASSIGNED,
        "review_nature": "SELF_CHECK",
        "independent_review_complete": False,
        "reviewed_at": NOW,
        "decision": "SELF_CHECK_PASS_WITH_LIMITS" if all_pass else "SELF_CHECK_FAIL",
        "counts": {
            "universe": len(master),
            "s05_mainline_pass": len(pass_ids),
            "s05_mainline_observe": len(obs_ids),
            "s05_carryover_776": len(pool_ids),
            "sample_total": len(sample),
            "sample_by_stratum": {s: sc.get(s, 0) for s in STRATUM_ORDER},
            "metrics_cells_recomputed": sum(int(r["metrics_compared"]) for r in sample),
            "missing_data_watch": len(s06_missing),
            "early_stage_watch": len(s06_early),
            "reverse_omission_sample": len(rev),
        },
        "checks_summary": f"{passed_cnt}/{len(checks)} PASS",
        "checks": checks,
        "limits": [
            "执行方自检（SELF_CHECK）不等同独立验收；须由 Codex 独立复核后决定是否验收与放行 S08。",
            "仅做小样本规则与计算审计，未重研全池、未逐家深读公告、未调整冻结阈值、未手工加回公司。",
            "S04 复核版 tight_pass（278）未纳入 Git 跟踪，445→278 的逐家映射不可在干净树内完全重放；登记为 F10 结转 S08。",
            "20 格越界值在冻结规则中无处置动作（F11），只登记、不阻断、不改值。",
            "S00 勘误 #53 与既有守卫原样结转，本次未闭合 #53。",
        ],
        "release_S08": False,
        "issue_53_touched": False,
    }
    (OUT / "review.json").write_bytes((json.dumps(review_obj, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))

    # ---------------- write manifest.json ----------------
    inputs_meta = []
    for p in READ_INPUTS:
        nbytes, digest = canonical_input_digest(p)
        inputs_meta.append({"path": p, "bytes": nbytes, "sha256": digest})

    deliv_meta = []
    for p in deliverables:
        nbytes, digest = sha256_exact(REPO / p)
        assert b"\r\n" not in (REPO / p).read_bytes(), f"CRLF detected in deliverable {p}"
        deliv_meta.append({"path": p, "bytes": nbytes, "sha256": digest})

    root_src = "\n".join(f"{d['path']}:{d['sha256']}" for d in sorted(deliv_meta, key=lambda x: x["path"]))
    root_digest = hashlib.sha256(root_src.encode("utf-8")).hexdigest()

    manifest_obj = {
        "artifact": "S07_DELIVERY_MANIFEST",
        "issue_key": ISSUE_KEY,
        "issue_number": ISSUE_NUMBER,
        "plan_version": PLAN_VERSION,
        "knowledge_as_of": KNOWLEDGE_AS_OF,
        "executor": EXECUTOR,
        "orchestrator": ORCHESTRATOR,
        "review_nature": "SELF_CHECK",
        "generated_at": NOW,
        "input_hash_basis": "CANONICAL_LF_BYTES",
        "input_hash_basis_note": (
            "28 份文本输入统一按 CRLF->LF 规范化后计算字节数与 SHA-256；"
            "s00_v10.csv.gz 为二进制 gzip，按 EXACT_BYTES 计算（bytes=5907837, sha256=fc312c52...），"
            "与 S02 calculation_manifest 的输入指纹一致。"
        ),
        "deliverable_hash_basis": "EXACT_BYTES_LF",
        "replay_note": (
            "在任意干净提交树内以 S07_FIXED_NOW=<generated_at> 顺序运行 "
            "step_s07_build.py 与 step_s07_verify.py，可逐字节复现全部交付、review.json 与 manifest.json。"
        ),
        "manifest_root_digest": root_digest,
        "input_count": len(inputs_meta),
        "deliverable_count": len(deliv_meta),
        "inputs": inputs_meta,
        "deliverables": deliv_meta,
    }
    (OUT / "manifest.json").write_bytes((json.dumps(manifest_obj, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))

    # ---------------- C20 manifest self-consistency ----------------
    m = json.loads((OUT / "manifest.json").read_text(encoding="utf-8"))
    recomputed_root = hashlib.sha256(
        "\n".join(f"{d['path']}:{d['sha256']}" for d in sorted(m["deliverables"], key=lambda x: x["path"])).encode("utf-8")
    ).hexdigest()
    deliv_hash_bad = []
    for d in m["deliverables"]:
        nb, sh = sha256_exact(REPO / d["path"])
        if nb != d["bytes"] or sh != d["sha256"]:
            deliv_hash_bad.append(d["path"])
    c20 = (m["manifest_root_digest"] == recomputed_root
           and m["input_hash_basis"] == "CANONICAL_LF_BYTES"
           and m["deliverable_hash_basis"] == "EXACT_BYTES_LF"
           and m["input_count"] == len(READ_INPUTS)
           and m["deliverable_count"] == len(deliverables)
           and not deliv_hash_bad)
    crlf_all = [p for p in deliverables if b"\r\n" in (REPO / p).read_bytes()]
    c20 = c20 and not crlf_all
    checks.append({"id": "C20", "name": "manifest 根摘要、输入/交付数量与逐份交付哈希自洽且全部交付为纯 LF",
                   "result": "PASS" if c20 else "FAIL",
                   "detail": f"root_match={m['manifest_root_digest'] == recomputed_root}, "
                             f"inputs={m['input_count']}, deliverables={m['deliverable_count']}, "
                             f"bad={deliv_hash_bad}, crlf={crlf_all}"})

    passed_cnt = sum(1 for c in checks if c["result"] == "PASS")
    all_pass = passed_cnt == len(checks)

    # rewrite review.json so checks_summary includes C20
    review_obj["checks"] = checks
    review_obj["checks_summary"] = f"{passed_cnt}/{len(checks)} PASS"
    review_obj["decision"] = "SELF_CHECK_PASS_WITH_LIMITS" if all_pass else "SELF_CHECK_FAIL"
    (OUT / "review.json").write_bytes((json.dumps(review_obj, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))

    # review.json changed after manifest -> refresh manifest deliverable hash and root
    for d in manifest_obj["deliverables"]:
        if d["path"] == "runs/issues/S07/review.json":
            d["bytes"], d["sha256"] = sha256_exact(OUT / "review.json")
    root_src = "\n".join(f"{d['path']}:{d['sha256']}" for d in sorted(manifest_obj["deliverables"], key=lambda x: x["path"]))
    manifest_obj["manifest_root_digest"] = hashlib.sha256(root_src.encode("utf-8")).hexdigest()
    manifest_obj["self_check"] = {
        "checks_total": len(checks),
        "checks_passed": passed_cnt,
        "manifest_root_digest_verified": c20,
        "deliverables_verified": not deliv_hash_bad,
    }
    (OUT / "manifest.json").write_bytes((json.dumps(manifest_obj, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))

    print(f"S07 SELF_CHECK: {passed_cnt}/{len(checks)} PASS | inputs={len(inputs_meta)} | "
          f"deliverables={len(deliv_meta)} | root={manifest_obj['manifest_root_digest']}")
    if not all_pass:
        for c in checks:
            if c["result"] != "PASS":
                print("  FAIL:", c)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
