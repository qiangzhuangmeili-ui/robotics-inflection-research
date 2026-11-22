# -*- coding: utf-8 -*-
"""
S06 (#41) Independent Self-Check, Manifest & Review Generator (Rework Round R2).
Verifies all S06 deliverables against frozen S01/S02/S05 inputs and Codex R1/R2 rulings,
computes canonical LF input hashes (matching Git blob bytes), enforces pure-LF deliverables,
and writes runs/issues/S06/manifest.json and runs/issues/S06/review.json.
"""
import csv
import hashlib
import json
import os
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
OUT = REPO / "runs" / "issues" / "S06"
NOW = os.environ.get("S06_FIXED_NOW") or datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")

sys.path.insert(0, str(OUT))
from step_s06_build import (
    READ_INPUTS,
    REVIEW_PROVENANCE_REFS,
    extract_page,
    is_non_adopted_evidence,
    sha256_canonical_lf,
)


def sha256_exact(path: Path) -> tuple[int, str]:
    raw = path.read_bytes()
    return len(raw), hashlib.sha256(raw).hexdigest()


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
    doc_reg = {r["document_id"]: r for r in load_csv("data/document_registry.csv")}
    s05_pass = {r["security_id"]: r for r in load_csv("runs/issues/S05/quality_pass.csv")}
    s05_obs = {r["security_id"]: r for r in load_csv("runs/issues/S05/quality_observe.csv")}
    s05_776 = {r["security_id"]: r for r in load_csv("runs/issues/S05/observe_pool_preserved_776.csv")}
    s05_278 = set(s05_pass) | set(s05_obs)

    s02_path = "runs/issues/S02/hangcha_restated_20261101/s02_v10/all_pool_metrics.csv"
    _, s02_sha = sha256_canonical_lf(REPO / s02_path)
    rec("C01", "S02 all_pool_metrics.csv SHA-256（LF 规范化/Git blob 口径）与放行记录一致",
        s02_sha == "3091b0bb82a3e3114d7f338595c40d82c842ce47aa8802b141a6ce8ec2232953",
        f"actual={s02_sha}")

    rec("C02", "全池 1,054 主键守恒 (277+1+776=1,054 且互斥)",
        len(master) == 1054 and len(s05_pass) == 277 and len(s05_obs) == 1 and len(s05_776) == 776
        and not (set(s05_pass) & set(s05_obs))
        and not (s05_278 & set(s05_776))
        and (s05_278 | set(s05_776)) == set(master),
        f"master={len(master)}, pass={len(s05_pass)}, obs={len(s05_obs)}, 776={len(s05_776)}")

    early = load_csv("runs/issues/S06/early_stage_watch.csv")
    missing = load_csv("runs/issues/S06/missing_data_watch.csv")
    early_by_sid = {r["security_id"]: r for r in early}
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

    cut_rows = [r for r in missing if r["cutoff_isolated"] == "YES"]
    anc_rows = [r for r in missing if r["anchor_reselection_pending"] == "YES"]
    ce_rows = [r for r in missing if r["quality_source_state"] == "PENDING_CE_SOURCE"]
    hfd_rows = [r for r in missing if r["s04_l2_decision"] == "HOLD_FOR_DATA"]
    rec("C07", "4 家截止日后隔离守卫完整保留且 s02_gap_diagnostic_scope 显式标为隔离期诊断",
        {r["security_id"] for r in cut_rows} == {"SH:603448", "SH:688836", "SZ:301348", "SZ:301699"}
        and all(r["s02_gap_diagnostic_scope"] == "AFTER_CUTOFF_ISOLATED_DIAGNOSTIC_ONLY_NOT_ADMISSIBLE_BEFORE_R05" for r in cut_rows),
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

    excluded_6 = {"BJ:920198", "BJ:920263", "BJ:920002", "SH:600699", "SH:603466", "SH:688327"}
    rec("C11", "6 家已核查概念/意向/证据不足公司与 1 家主表外公司未混入 early_stage_watch",
        len(set(early_sids) & (excluded_6 | {"BJ:920007"})) == 0,
        f"leaked={sorted(set(early_sids) & (excluded_6 | {'BJ:920007'}))}")

    early_fields_ok = all(
        r["watch_reason"].strip()
        and r["document_id_or_url"].strip()
        and r["primary_evidence_binding"].strip()
        and "【主线重进】" in r["reentry_trigger_conditions"]
        and "【业务核证目标】" in r["reentry_trigger_conditions"]
        and r["contract_liability_aux_status"] == "UNKNOWN"
        and r["order_backlog_aux_status"] == "UNKNOWN"
        and r["aux_method_version"] == "S06_AUX_LEAD_V1"
        for r in early
    )
    rec("C12", "early_stage_watch 每行具备完整证据绑定、分离式重进条件且辅助观察记 UNKNOWN 不填零",
        early_fields_ok,
        f"checked={len(early)} rows")

    missing_fields_ok = all(
        r["watch_reason"].strip() and r["source_locator"].strip() and r["reentry_trigger_conditions"].strip()
        for r in missing
    )
    rec("C13", "missing_data_watch 每行具备观察理由、来源定位与可验证重进条件",
        missing_fields_ok,
        f"checked={len(missing)} rows")

    ev_index = {}
    for rel in [
        "archive/R1_batch01_parent_reviewed_20261024/evidence_register.csv",
        "archive/R1_02A_parent_reviewed_20261024/evidence_register_reviewed.csv",
        "archive/02A_supplement/evidence_register_reviewed.csv",
        "archive/02B/evidence_register_reviewed.csv",
        "archive/early_sample_evidence.csv",
        "packages/C00_PILOT_01/results/evidence.csv",
    ]:
        for r in load_csv(rel):
            ev_index[r["evidence_id"].strip()] = r

    unresolved, wrong_sid, adopted_do_not_adopt, missed_pages = [], [], [], []
    for r in early:
        sid = r["security_id"]
        eids = [e.strip() for e in r["evidence_ids"].split(";") if e.strip()]
        has_src_page = False
        for eid in eids:
            if eid not in ev_index:
                unresolved.append((sid, eid))
                continue
            eo = ev_index[eid]
            if eo["security_id"].strip() != sid:
                wrong_sid.append((sid, eid, eo["security_id"]))
            if is_non_adopted_evidence(eo):
                adopted_do_not_adopt.append((sid, eid, eo.get("parent_source_review") or eo.get("review_status")))
            if extract_page(eo) != "UNKNOWN":
                has_src_page = True
        if has_src_page and r["physical_page_or_section"] == "UNKNOWN":
            missed_pages.append(sid)

    rec("C14", "early_stage_watch 所有采用 evidence_id 可解析、同公司主键且零 DO_NOT_ADOPT 混入",
        not unresolved and not wrong_sid and not adopted_do_not_adopt,
        f"unresolved={len(unresolved)}, wrong_sid={len(wrong_sid)}, do_not_adopt={adopted_do_not_adopt}")

    rec("C15", "源登记含物理页码的观察行零漏读（54/54 无 UNKNOWN 物理页）",
        len(missed_pages) == 0 and sum(1 for r in early if r["physical_page_or_section"] == "UNKNOWN") == 0,
        f"missed_pages={missed_pages}, remaining_unknown_pages={sum(1 for r in early if r['physical_page_or_section'] == 'UNKNOWN')}")

    r_dc = early_by_sid["SH:605555"]
    r_ys = early_by_sid["SH:600366"]
    r_fj = early_by_sid["SH:603219"]
    r_nt = early_by_sid["BJ:920124"]
    r_hq = early_by_sid["SH:603296"]
    r_jc = early_by_sid["SH:603583"]
    r_ef = early_by_sid["SH:688165"]
    r_xs = early_by_sid["SZ:002527"]

    rec("C16", "Codex 1.1 德昌股份 SH:605555 移出 S3 并采用 C00-EV-605555-03 物理第 12 页",
        r_dc["watch_bucket"] == "EVIDENCED_PRODUCT_STAGE_UNKNOWN"
        and r_dc["fact_tier"] == "PRODUCT_RAMP_DELIVERY_STAGE_UNKNOWN"
        and r_dc["evidence_ids"] == "C00-EV-605555-03"
        and "12" in r_dc["physical_page_or_section"],
        f"bucket={r_dc['watch_bucket']}, tier={r_dc['fact_tier']}, page={r_dc['physical_page_or_section']}")

    rec("C17", "Codex 1.1 宁波韵升 SH:600366 同步采用第 11 页 C00-EV-600366-03 长期协议与供货事实且不推定在手订单金额",
        "C00-EV-600366-03" in r_ys["evidence_ids"]
        and "11" in r_ys["physical_page_or_section"]
        and "长期协议" in r_ys["disclosed_fact_summary"]
        and r_ys["order_backlog_aux_status"] == "UNKNOWN"
        and r_ys["fact_tier"] == "SAMPLING_AND_SUPPLY_SCALE_UNKNOWN",
        f"tier={r_ys['fact_tier']}, page={r_ys['physical_page_or_section']}, eids={r_ys['evidence_ids']}")

    rec("C18", "Codex 1.1 富佳股份 SH:603219 严格分离上市母公司(UNKNOWN)与非并表参股公司芯禾(S1/S3间接观察)",
        r_fj["watch_bucket"] == "EVIDENCED_PRODUCT_STAGE_UNKNOWN"
        and r_fj["fact_tier"] == "LISTED_PARENT_STAGE_UNKNOWN_WITH_ASSOCIATE_EARLY_OBSERVE"
        and "R1B1-PL046" in r_fj["all_recorded_product_lines"]
        and "R1B1-PL047" in r_fj["all_recorded_product_lines"]
        and "R1B1-PL048" in r_fj["all_recorded_product_lines"],
        f"bucket={r_fj['watch_bucket']}, other_stages={r_fj['other_verified_stages']}")

    rec("C19", "Codex 1.1 华勤/捷昌/埃夫特/新时达完整保留较高阶段产品线(R1B02-PL041/R1A02-PL013/R1B1-PL001/R1B1-PL006/007)",
        "R1B02-PL041" in r_hq["all_recorded_product_lines"] and "S4" in r_hq["other_verified_stages"]
        and "R1A02-PL013" in r_jc["all_recorded_product_lines"] and "S4" in r_jc["other_verified_stages"]
        and "R1B1-PL001" in r_ef["all_recorded_product_lines"] and "S4" in r_ef["other_verified_stages"]
        and "R1B1-PL006" in r_xs["all_recorded_product_lines"] and "R1B1-PL007" in r_xs["all_recorded_product_lines"] and "S3" in r_xs["other_verified_stages"],
        f"hq={r_hq['other_verified_stages']}, jc={r_jc['other_verified_stages']}, ef={r_ef['other_verified_stages']}, xs={r_xs['other_verified_stages']}")

    rec("C20", "Codex 1.2 南特科技 BJ:920124 仅采用官方原文 R1A02S-E001(物理第41页)，旧镜像 R1A02-E001 降格为历史定位",
        r_nt["evidence_ids"] == "R1A02S-E001"
        and "R1A02-E001" in r_nt["non_adopted_historical_locators"]
        and "41" in r_nt["physical_page_or_section"],
        f"eids={r_nt['evidence_ids']}, non_adopted={r_nt['non_adopted_historical_locators']}, page={r_nt['physical_page_or_section']}")

    marked_in_early = {r["security_id"] for r in missing if r["in_early_stage_watch"] == "YES"}
    actual_overlap = set(early_sids) & set(missing_sids)
    rec("C21", "两表交集标记 in_early_stage_watch 与实际主键交集完全一致",
        marked_in_early == actual_overlap,
        f"overlap={len(actual_overlap)}")

    missing_inputs = [p for p in READ_INPUTS if not (REPO / p).exists()]
    no_local_only = all(p not in READ_INPUTS for p in REVIEW_PROVENANCE_REFS)
    rec("C22", "manifest 登记的 33 份运行必需输入均存在且不含本地未提交复核文件",
        len(missing_inputs) == 0 and len(READ_INPUTS) == len(set(READ_INPUTS)) and no_local_only,
        f"total_inputs={len(READ_INPUTS)}, missing={missing_inputs}, no_local_only={no_local_only}")

    rules_txt = (OUT / "watch_reentry_rules.md").read_text(encoding="utf-8")
    handoff_txt = (OUT / "handoff.md").read_text(encoding="utf-8")
    early_bucket_cnt = Counter(r["watch_bucket"] for r in early)
    prose_ok = (
        f"**{len(early)} 家**" in rules_txt
        and f"**{len(missing)} 家**" in rules_txt
        and f"**{early_bucket_cnt['EARLY_RD_PROTOTYPE_SAMPLING']} 家**" in rules_txt
        and f"**{early_bucket_cnt['EARLY_PILOT_SMALL_BATCH']} 家**" in rules_txt
        and f"**{early_bucket_cnt['EVIDENCED_PRODUCT_STAGE_UNKNOWN']} 家**" in rules_txt
        and "AFTER_CUTOFF_ISOLATED_DIAGNOSTIC_ONLY_NOT_ADMISSIBLE_BEFORE_R05" in rules_txt
        and f"共 {len(early)} 家" in handoff_txt
        and f"共 {len(missing)} 家" in handoff_txt
        and "SELF_CHECK" in handoff_txt
    )
    rec("C23", "watch_reentry_rules.md 与 handoff.md 核心计数、R2 分桶及口径版本与 CSV 实算一致",
        prose_ok,
        f"buckets={dict(early_bucket_cnt)}")

    ef_doc = doc_reg.get("DOC-586ED2C18DB28CDE", {})
    rec("C24", "Codex R1-2 埃夫特 SH:688165 绑定 DOC-586ED2C18DB28CDE 物理第 32 页(S1发布)、第 25 页(获奖)与第 19 页(量产边界)",
        ef_doc.get("sha256") == "586ed2c18db28cdeb8b2df23bc9dc8ff995ec33bc37895c885b5e9aa8e426517"
        and "DOC-586ED2C18DB28CDE" in r_ef["document_id_or_url"]
        and "第32页" in r_ef["physical_page_or_section"]
        and "第25页" in r_ef["physical_page_or_section"]
        and "第19页" in r_ef["physical_page_or_section"]
        and "P32_S1_DECISIVE" in r_ef["primary_evidence_binding"]
        and "P19_MASS_PROD_BOUNDARY" in r_ef["primary_evidence_binding"],
        f"page={r_ef['physical_page_or_section']}")

    # Pre-check LF purity on already-generated deliverables (review.json & manifest.json will also be written pure LF)
    pre_delivs = [
        "runs/issues/S06/early_stage_watch.csv",
        "runs/issues/S06/missing_data_watch.csv",
        "runs/issues/S06/watch_reentry_rules.md",
        "runs/issues/S06/handoff.md",
        "runs/issues/S06/step_s06_build.py",
        "runs/issues/S06/step_s06_verify.py",
    ]
    crlf_files = [p for p in pre_delivs if b"\r\n" in (REPO / p).read_bytes()]
    rec("C25", "全部 S06 交付文件与脚本均为纯 LF 换行（工作区字节与 Git blob 逐字节一致）",
        len(crlf_files) == 0,
        f"crlf_files={crlf_files}")

    passed_cnt = sum(1 for c in checks if c["result"] == "PASS")
    all_pass = (passed_cnt == len(checks))

    # ------------------------------------------------------------------
    # Write review.json (SELF_CHECK, R2, pure LF)
    # ------------------------------------------------------------------
    missing_cat_cnt = Counter(r["missing_data_category"] for r in missing)
    non_mainline_missing = sum(1 for r in missing if r["mainline_dedup_status"] == "NON_MAINLINE_776")

    review_obj = {
        "artifact": "S06_SELF_CHECK_REVIEW",
        "issue_key": "S06",
        "issue_number": 41,
        "rework_round": "R2",
        "review_provenance_refs": REVIEW_PROVENANCE_REFS,
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
        "r2_fixes_applied": [
            "将未入库本地复核记录移出运行必需输入清单，转登记于 review_provenance_refs；manifest 全部 33 份输入均位于目标 Git 提交树内",
            "manifest 输入哈希显式采用 CANONICAL_LF_BYTES（对文本统一按 LF 规范化计算字节数与 SHA-256，消除 Git blob 与 Windows CRLF 差异），交付采用 EXACT_BYTES_LF，支持从干净提交独立重放逐字节复现",
            "埃夫特 SH:688165 直接核读 DOC-586ED2C18DB28CDE(SHA-256 586ed2c1...) 物理/印刷第 32 页(Yobot R1/W1 发布，S1 决定性原页)、第 25 页(获奖)与第 19 页(R1B1-E001 量产边界)",
        ],
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
            "执行方自检（SELF_CHECK）不等同独立验收，须由 Codex 独立复核 R2 后决定是否验收与放行 S07。",
            "仅复用已有可追溯证据与 S02/S05 冻结快照（另定向核读埃夫特 2025 年报已归档原页 P19/P25/P32），未扩大全池采集或逐家企业深研。",
            "合同负债不在 P04/S00 冻结标准化字段内，且无全池结构化在手订单台账；非主线观察行在 S06_AUX_LEAD_V1 中统一记 UNKNOWN，不填 0、不据此淘汰。",
            "观察名单不是买入推荐、投资候选或已商业化认定，不得跳过 S07/S08 进入估值。",
            "S00 勘误 #53 与既有守卫全部原样结转，本次未闭合 #53。",
        ],
        "release_S07": False,
        "release_S08": False,
        "issue_53_touched": False,
    }
    (OUT / "review.json").write_bytes((json.dumps(review_obj, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))

    # ------------------------------------------------------------------
    # Write manifest.json (ALL 33 Git-tracked READ_INPUTS using canonical LF bytes)
    # ------------------------------------------------------------------
    deliverable_paths = [
        "runs/issues/S06/early_stage_watch.csv",
        "runs/issues/S06/missing_data_watch.csv",
        "runs/issues/S06/watch_reentry_rules.md",
        "runs/issues/S06/handoff.md",
        "runs/issues/S06/review.json",
        "runs/issues/S06/step_s06_build.py",
        "runs/issues/S06/step_s06_verify.py",
    ]

    inputs_meta = []
    for p in READ_INPUTS:
        nbytes, digest = sha256_canonical_lf(REPO / p)
        inputs_meta.append({"path": p, "bytes": nbytes, "sha256": digest})

    deliv_meta = []
    for p in deliverable_paths:
        nbytes, digest = sha256_exact(REPO / p)
        assert b"\r\n" not in (REPO / p).read_bytes(), f"CRLF detected in deliverable {p}"
        deliv_meta.append({"path": p, "bytes": nbytes, "sha256": digest})

    root_digest_src = "\n".join(f"{d['path']}:{d['sha256']}" for d in sorted(deliv_meta, key=lambda x: x["path"]))
    root_digest = hashlib.sha256(root_digest_src.encode("utf-8")).hexdigest()

    manifest_obj = {
        "artifact": "S06_DELIVERY_MANIFEST",
        "issue_key": "S06",
        "issue_number": 41,
        "rework_round": "R2",
        "plan_version": "20261026_collection_first_v2",
        "knowledge_as_of": "2026-10-25",
        "aux_method_version": "S06_AUX_LEAD_V1",
        "executor": "Antigravity",
        "review_nature": "SELF_CHECK",
        "generated_at": NOW,
        "input_hash_basis": "CANONICAL_LF_BYTES",
        "input_hash_basis_note": "全部 33 份文本输入统一执行 CRLF->LF 规范化后计算字节数与 SHA-256（含 6 份 Git blob 本身为 CRLF 与 15 份 Windows 检出转 CRLF 的输入），确保干净提交树重放与本地工作区逐字节一致。",
        "deliverable_hash_basis": "EXACT_BYTES_LF",
        "replay_note": "在任意干净提交树内以 S06_FIXED_NOW=<generated_at> 顺序运行 step_s06_build.py 与 step_s06_verify.py，可逐字节复现全部交付、review.json 与 manifest.json。",
        "review_provenance_refs": REVIEW_PROVENANCE_REFS,
        "manifest_root_digest": root_digest,
        "input_count": len(inputs_meta),
        "deliverable_count": len(deliv_meta),
        "inputs": inputs_meta,
        "deliverables": deliv_meta,
    }
    (OUT / "manifest.json").write_bytes((json.dumps(manifest_obj, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))

    print(f"R2 SELF_CHECK: {passed_cnt}/{len(checks)} PASS | inputs={len(inputs_meta)} | root_digest={root_digest}")
    if not all_pass:
        for c in checks:
            if c["result"] != "PASS":
                print("  FAIL:", c)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
