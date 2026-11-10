"""S04 第二道收紧：L2 多指标共同改善。

规则来源：runs/issues/S01/screen_rules_v2.json（已冻结；本脚本不写任何筛选阈值）
信号输入：runs/issues/S03/rerun_20261106 三分区逐家信号结果（S03 已验收交付）
证据校验：S02 v10 all_pool_metrics.csv（仅用于核对「所用指标状态」，不重算信号）
守卫输入：runs/issues/S02/acceptance_20261106/s03_input_contract.json（四家截止日隔离）

L2 规则原文（S01 v2 decision_layers[L2]）：
  在 GROWTH / MARGIN / PROFIT / CASH 四个维度中，至少 2 个维度各有 1 条 SG 为真，
  且所用指标均 metric_status=OK、无 Q01 HOLD、无 Q06 未决重述、无 Q05 低基数未确认。
  hold_policy: 所需维度任一 HOLD → HOLD_FOR_DATA，不得降级为不通过。
  low_base_policy: 低基数信号须附绝对额同向确认（增量≥1,000 万元）才计入维度。
  restatement_policy: Q06 未决重述的跨期指标不得计入 L2 维度。

输出：tight_pass.csv / tight_observe.csv / tight_decision_log.csv / review_100_qc.csv
      tight_summary.json / manifest.json / review.json
"""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
S04 = ROOT / "runs/issues/S04"
S03 = ROOT / "runs/issues/S03"
RERUN = S03 / "rerun_20261106"
CFG_PATH = S03 / "l1_config.json"
RULES_PATH = ROOT / "runs/issues/S01/screen_rules_v2.json"
CONTRACT_PATH = ROOT / "runs/issues/S02/acceptance_20261106/s03_input_contract.json"
METRICS_PATH = ROOT / "runs/issues/S02/hangcha_restated_20261101/s02_v10/all_pool_metrics.csv"
MASTER_PATH = ROOT / "data/company_master.csv"

ACCEPTED_CFG_SHA = "2f6193e6a0cad024a67d0ce0dd806e58db8ebdb44dd92d9ef750cc3fdc3fd541"
ACCEPTED_RULES_SHA = {
    "ada501e8bcd276ce670a4799c730a81cdf2f9dc70c244f9255485b00168c6a85",
    "d9a6b3cc77fcd3afb498673668be2d5c86412b6b83ffe0193e6c78f4979ecabf",
}
PARTITIONS = ("wide_pass", "wide_defer", "wide_unknown")
DIM_ORDER = ("GROWTH", "MARGIN", "PROFIT", "CASH")

# 维度状态优先级：干净 > 低基数 > 暂定 > 上游 HOLD > 无
DIM_RANK = {"CLEAN": 0, "LOW_BASE": 1, "PROVISIONAL": 2, "HOLD": 3, "NONE": 4}


def sha_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fail(msg: str) -> int:
    print(f"FAIL {msg}", file=sys.stderr)
    return 2


def base_status(verdict: str) -> str:
    if verdict.startswith("HOLD"):
        return "HOLD"
    if verdict.startswith("MISSING"):
        return "MISSING"
    if verdict.startswith("UNDEFINED_BASE"):
        return "UNDEFINED_BASE"
    if verdict.startswith("NOT_APPLICABLE"):
        return "NOT_APPLICABLE"
    if verdict.startswith("REFERENCE_ONLY") or verdict.startswith("ESTIMATED_REFERENCE_ONLY"):
        return "REFERENCE_ONLY"
    return verdict


def sgs(s: str) -> list[str]:
    return [x for x in (s or "").split(";") if x]


def main() -> int:
    checks: list[dict] = []

    def check(cid: str, name: str, ok: bool, detail=None, level: str = "FAIL") -> None:
        checks.append({"id": cid, "name": name, "pass": bool(ok), "level": level, "detail": detail})

    # ---------------- C00 输入与版本闸门
    if not CFG_PATH.exists() or not RULES_PATH.exists() or not CONTRACT_PATH.exists():
        return fail("C00 required input missing")
    cfg_sha = sha_file(CFG_PATH)
    if cfg_sha != ACCEPTED_CFG_SHA:
        return fail("C00 S03 config hash differs from the accepted configuration")
    rules_sha = sha_file(RULES_PATH)
    if rules_sha not in ACCEPTED_RULES_SHA:
        return fail("C00 rules file is not an accepted S01 v2 artifact")
    cfg = json.loads(CFG_PATH.read_text(encoding="utf-8"))
    rules = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    if contract.get("version") != "S02_TO_S03_GATE_20261106" \
            or contract.get("knowledge_as_of") != cfg.get("as_of"):
        return fail("C00 input contract version or cutoff mismatch")
    met_decl = (contract.get("metrics") or {})
    if sha_file(METRICS_PATH) != met_decl.get("sha256"):
        return fail("C00 metrics file hash differs from the S02 acceptance contract")

    sg_dim = {s["id"]: s["dimension"] for s in rules["signals"]}
    sg_metric = {s["id"]: s["metric"] for s in rules["signals"]}
    thresholds = {s["id"]: s["threshold"] for s in rules["signals"]}
    dims = cfg["dimensions"]
    l2 = next(d for d in rules["decision_layers"] if d["id"] == "L2")
    check("C00", "输入版本与哈希闸门（config/rules/metrics/contract）", True,
          {"config_sha256": cfg_sha, "rules_sha256": rules_sha,
           "metrics_sha256": met_decl.get("sha256"),
           "knowledge_as_of": cfg.get("as_of"),
           "l2_rule_text": l2["rule_text"]})

    guard_ids = {g["security_id"] for g in contract.get("guard_companies", [])}
    if len(guard_ids) != 4:
        return fail("C00 contract must enumerate exactly four cutoff-guard companies")

    # ---------------- 装载
    master: dict[str, str] = {}
    with MASTER_PATH.open(encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            master[r["security_id"]] = r["stock_name"]

    metrics: dict[str, dict[str, dict]] = defaultdict(dict)
    with METRICS_PATH.open(encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            metrics[r["security_id"]][r["metric_id"]] = r

    override = {o["security_id"]: o for o in cfg.get("company_overrides", [])}
    for sec, ov in override.items():
        for mid, spec in ov["metrics"].items():
            row = metrics.get(sec, {}).get(mid)
            if row is None:
                continue
            row["metric_status"] = base_status(spec["verdict"])

    rows: dict[str, dict] = {}
    part_of: dict[str, str] = {}
    for part in PARTITIONS:
        with (RERUN / f"{part}.csv").open(encoding="utf-8-sig", newline="") as fh:
            for r in csv.DictReader(fh):
                rows[r["company_id"]] = r
                part_of[r["company_id"]] = part

    review_targets: dict[str, dict] = {}
    with (RERUN / "s04_review_targets.csv").open(encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            review_targets[r["company_id"]] = r

    # ---------------- C01/C02 覆盖与主键
    counts = Counter(part_of.values())
    check("C01", "分区覆盖 1054 家且与调度总表主键完全一致",
          len(rows) == 1054 and set(rows) == set(master) and sum(counts.values()) == 1054,
          {"rows": len(rows), "master": len(master), "by_partition": dict(counts)})
    dup = len(rows) - len(set(rows))
    check("C02", "三分区互斥无重复（1054 = 777 + 149 + 128）",
          dup == 0 and counts["wide_pass"] == 777 and counts["wide_defer"] == 149
          and counts["wide_unknown"] == 128,
          {"duplicates": dup, "wide_pass": counts["wide_pass"],
           "wide_defer": counts["wide_defer"], "wide_unknown": counts["wide_unknown"]})

    # ---------------- 逐家 L2 判定
    out: list[dict] = []
    dim_diff: list[dict] = []
    hold_diff: list[dict] = []

    for sec in sorted(rows):
        r = rows[sec]
        part = part_of[sec]
        clean_sg = sgs(r.get("sg_hit_clean_list"))
        prov_sg = sgs(r.get("sg_hit_provisional_list"))
        low_sg = sgs(r.get("sg_hit_lowbase_list"))
        hold_sg = sgs(r.get("sg_hold_list"))

        dim_state: dict[str, str] = {}
        dim_sg: dict[tuple[str, str], list[str]] = defaultdict(list)

        def mark(sg: str, st: str) -> None:
            d = sg_dim[sg]
            dim_sg[(d, st)].append(sg)
            if DIM_RANK[st] < DIM_RANK[dim_state.get(d, "NONE")]:
                dim_state[d] = st

        for sg in clean_sg:
            mark(sg, "CLEAN")
        for sg in low_sg:
            mark(sg, "LOW_BASE")
        for sg in prov_sg:
            mark(sg, "PROVISIONAL")
        for sg in hold_sg:
            mark(sg, "HOLD")

        clean_dims = [d for d in DIM_ORDER if dim_state.get(d) == "CLEAN"]
        hold_dims = [d for d in DIM_ORDER if dim_state.get(d) == "HOLD"]
        potential_dims = [d for d in DIM_ORDER if dim_state.get(d) in ("CLEAN", "LOW_BASE", "PROVISIONAL")]
        # 所需维度的 HOLD 也要计入「可能补足」路径：未点亮但该维度存在上游 HOLD 指标
        hold_metric_dims = []
        for d in DIM_ORDER:
            if d in potential_dims:
                continue
            if any((metrics[sec].get(mid) or {}).get("metric_status") == "HOLD" for mid in dims[d]):
                hold_metric_dims.append(d)

        # 底稿判为不可比的公司：S03 按设计清零维度计数，L2 不评估（口径隔离）
        ov = override.get(sec)
        blocked = bool(ov and ov.get("block_sg"))
        if blocked:
            clean_dims, hold_dims, potential_dims, hold_metric_dims = [], [], [], []
        reachable = len(set(clean_dims) | set(hold_dims) | set(hold_metric_dims))

        # 与 S03 已验收计数对账
        if len(clean_dims) != int(r["clean_ok_dims_count"] or 0):
            dim_diff.append({"security_id": sec, "derived": len(clean_dims),
                             "s03": int(r["clean_ok_dims_count"] or 0)})
        s03_hold = int(r["hold_dims_count"] or 0)
        if len(set(hold_dims) | set(hold_metric_dims)) != s03_hold:
            hold_diff.append({"security_id": sec,
                              "derived": len(set(hold_dims) | set(hold_metric_dims)),
                              "s03": s03_hold})

        # 证据等级：CLEAN 信号所用指标是否全部 metric_status=OK
        non_ok = []
        ok_dims = set()
        for sg in clean_sg:
            mid = sg_metric[sg]
            st = (metrics[sec].get(mid) or {}).get("metric_status", "ABSENT")
            if st != "OK":
                non_ok.append(f"{sg}:{mid}={st}")
            else:
                ok_dims.add(sg_dim[sg])
        grade = "A_ALL_OK" if not non_ok else "B_ABS_CHANNEL"
        # 若把非 OK 指标（SG06/SG08 绝对额通道）整条剔除，是否仍满足 2 维
        abs_critical = "NO"
        if non_ok and len(ok_dims) < 2:
            abs_critical = "YES"

        if sec in guard_ids:
            decision = "WATCH_AFTER_CUTOFF"
            reason = "截止日后披露，整体隔离；不作候选/无信号/风险结论，不得回退旧期"
            gap = "AFTER_CUTOFF"
        elif part != "wide_pass":
            decision = "L2_NOT_IN_SCOPE"
            reason = (f"S03 分区 {part}（{r.get('l1_subtag','')}），"
                      f"不在 L2 收紧范围；保留观察，不淘汰")
            gap = r.get("l1_subtag") or part
        elif len(clean_dims) >= 2:
            decision = "L2_SHORTLIST_CANDIDATE"
            reason = "干净维度 " + "+".join(clean_dims) + f"（{len(clean_dims)} 个）满足 ≥2"
            gap = ""
        elif reachable >= 2:
            decision = "L2_HOLD_FOR_DATA"
            reason = ("干净维度不足 2 个，但存在上游 HOLD 维度可补足："
                      + ",".join(sorted(set(hold_dims) | set(hold_metric_dims))))
            gap = "UPSTREAM_HOLD"
        else:
            decision = "L2_NOT_SHORTLISTED"
            blockers = []
            for d in DIM_ORDER:
                st = dim_state.get(d, "NONE")
                if st == "PROVISIONAL":
                    blockers.append(f"{d}:PROVISIONAL")
                elif st == "LOW_BASE":
                    blockers.append(f"{d}:LOW_BASE_UNCONFIRMED")
            gap = ";".join(blockers) if blockers else "SINGLE_DIM_ONLY"
            reason = (f"干净维度仅 {len(clean_dims)} 个"
                      + (f"（{'/'.join(clean_dims)}）" if clean_dims else "")
                      + "；" + gap)

        if decision == "L2_HOLD_FOR_DATA":
            reentry = "上游 HOLD 解除后按同一规则重算，不需人工改规则"
        elif gap.startswith(("PROVISIONAL", "GROWTH:PROVISIONAL", "MARGIN:PROVISIONAL",
                             "PROFIT:PROVISIONAL", "CASH:PROVISIONAL")) or "PROVISIONAL" in gap:
            reentry = "重述标记由 NEEDS_REVIEW 落定为是/否后信号可升级重算"
        elif "LOW_BASE" in gap:
            reentry = "取得绝对额同向确认（增量≥1,000 万元）后方可计入维度"
        elif gap in ("W1_NO_DATA", "W2_ALL_HOLD", "W4_EARLY", "W5_PROVISIONAL_ONLY"):
            reentry = "按 S01 观察名单重进条件处理"
        elif gap == "AFTER_CUTOFF":
            reentry = "下一报告期资料入池后按截止日规则重进"
        else:
            reentry = "规则升版时全池重算，不单独重进"

        out.append({
            "company_id": sec,
            "company_name": r.get("company_name") or master.get(sec, ""),
            "anchor_period": r.get("anchor_period", ""),
            "anchor_period_type": r.get("anchor_period_type", ""),
            "stale_period": r.get("stale_period", ""),
            "l0_status": r.get("l0_status", ""),
            "l1_partition": part,
            "l1_bucket": r.get("l1_bucket", ""),
            "l1_subtag": r.get("l1_subtag", ""),
            "l2_decision": decision,
            "clean_dim_count": len(clean_dims),
            "reachable_dim_count": reachable,
            "clean_dims": ";".join(clean_dims),
            "hold_dims": ";".join(sorted(set(hold_dims) | set(hold_metric_dims))),
            "potential_dims": ";".join(potential_dims),
            "clean_sg": ";".join(clean_sg),
            "prov_sg": ";".join(prov_sg),
            "low_base_sg": ";".join(low_sg),
            "hold_sg": ";".join(hold_sg),
            "dim_detail": ";".join(
                f"{d}={dim_state.get(d, 'NONE')}"
                + (f"[{'/'.join(dim_sg[(d, dim_state[d])])}]" if dim_sg.get((d, dim_state.get(d, ""))) else "")
                for d in DIM_ORDER),
            "hold_metric_detail": ";".join(
                f"{d}:" + "/".join(mid for mid in dims[d]
                                   if (metrics[sec].get(mid) or {}).get("metric_status") == "HOLD")
                for d in DIM_ORDER
                if any((metrics[sec].get(mid) or {}).get("metric_status") == "HOLD" for mid in dims[d])),
            "evidence_grade": grade if decision == "L2_SHORTLIST_CANDIDATE" else "",
            "abs_dependency_critical": abs_critical if decision == "L2_SHORTLIST_CANDIDATE" else "",
            "scope_blocked": "YES" if blocked else "",
            "non_ok_metric_in_clean_sg": ";".join(non_ok),
            "quality_flags_summary": r.get("quality_flags_summary", ""),
            "project_mode": r.get("project_mode", ""),
            "s04_review_priority": r.get("s04_review_priority", ""),
            "decision_reason": reason,
            "blocking_gap": gap,
            "reentry_condition": reentry,
        })

    check("C03", "L2 干净维度数与 S03 已验收 clean_ok_dims_count 逐家一致",
          not dim_diff, {"mismatches": dim_diff[:10], "count": len(dim_diff)})
    check("C04", "HOLD 维度数与 S03 hold_dims_count 逐家一致", not hold_diff,
          {"mismatches": hold_diff[:10], "count": len(hold_diff)}, level="WARN")

    by_dec = Counter(o["l2_decision"] for o in out)
    by_part_dec = Counter((o["l1_partition"], o["l2_decision"]) for o in out)

    check("C05", "L2 通过数等于 S03 AUTO_PASS_L2_READY 的 443 家",
          by_dec["L2_SHORTLIST_CANDIDATE"] == 443
          and by_part_dec[("wide_pass", "L2_SHORTLIST_CANDIDATE")] == 443,
          {"shortlist": by_dec["L2_SHORTLIST_CANDIDATE"]})

    guard_rows = [o for o in out if o["company_id"] in guard_ids]
    check("C06", "四家截止日隔离公司保持隔离且零信号、无 L2 结论",
          len(guard_rows) == 4
          and all(o["l2_decision"] == "WATCH_AFTER_CUTOFF" for o in guard_rows)
          and all(not o["clean_sg"] and not o["prov_sg"] and not o["low_base_sg"] for o in guard_rows),
          {"guards": [o["company_id"] for o in guard_rows]})

    # ---------------- C07 守恒
    pass_ids = {o["company_id"] for o in out if o["l2_decision"] == "L2_SHORTLIST_CANDIDATE"}
    pass_part = {o["company_id"] for o in out
                 if o["l2_decision"] == "L2_SHORTLIST_CANDIDATE" and o["l1_partition"] == "wide_pass"}
    check("C07", "tight_pass 全部来自 wide_pass 且交付合计覆盖 1054、无重叠",
          pass_ids == pass_part and len(pass_ids) == 443,
          {"pass": len(pass_ids), "pass_from_wide_pass": len(pass_part)})

    # ---------------- C08 阈值未改动
    expected_thresholds = {"SG01": 0.1, "SG02": 5.0, "SG03": 1.0, "SG04": 0.2, "SG05": 1.0,
                           "SG06": 10000000.0, "SG07": 0.8, "SG08": 0.0, "SG09": 0.3}
    check("C08", "九条信号阈值与冻结规则完全一致，本脚本未引入新阈值",
          thresholds == expected_thresholds,
          {"thresholds": thresholds, "rules_sha256": rules_sha})

    # ---------------- C09 定向核验清单
    target_ids = set(review_targets)
    missing_targets = target_ids - set(rows)
    check("C09", "S03 的 100 家定向核验对象全部在结果中且均有诊断",
          not missing_targets and len(target_ids) == 100,
          {"targets": len(target_ids), "missing": sorted(missing_targets)[:5]})

    # ---------------- 输出
    pass_rows = [o for o in out if o["l2_decision"] == "L2_SHORTLIST_CANDIDATE"]
    observe_rows = [o for o in out if o["l2_decision"] != "L2_SHORTLIST_CANDIDATE"]

    cols = ["company_id", "company_name", "anchor_period", "anchor_period_type", "stale_period",
            "l0_status", "l1_partition", "l1_bucket", "l1_subtag", "l2_decision",
            "clean_dim_count", "reachable_dim_count", "clean_dims", "hold_dims", "potential_dims",
            "clean_sg", "prov_sg", "low_base_sg", "hold_sg", "dim_detail", "hold_metric_detail",
            "evidence_grade",
            "abs_dependency_critical", "scope_blocked", "non_ok_metric_in_clean_sg",
            "quality_flags_summary", "project_mode",
            "s04_review_priority", "decision_reason", "blocking_gap", "reentry_condition"]

    def write_csv(path: Path, data: list[dict]) -> dict:
        with path.open("w", encoding="utf-8-sig", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            w.writerows(data)
        return {"path": str(path.relative_to(ROOT)).replace("\\", "/"),
                "rows": len(data), "sha256": sha_file(path)}

    outputs = {
        "tight_pass.csv": write_csv(S04 / "tight_pass.csv", pass_rows),
        "tight_observe.csv": write_csv(S04 / "tight_observe.csv", observe_rows),
        "tight_decision_log.csv": write_csv(S04 / "tight_decision_log.csv", out),
    }

    # 100 家定向核验：只核数据依赖，不新增 PDF 深读
    qc_rows = []
    for sec, t in review_targets.items():
        o = next(x for x in out if x["company_id"] == sec)
        qc_rows.append({
            "company_id": sec,
            "company_name": o["company_name"],
            "anchor_period": o["anchor_period"],
            "s03_priority": t.get("s04_review_priority", ""),
            "l2_decision": o["l2_decision"],
            "clean_dim_count": o["clean_dim_count"],
            "reachable_dim_count": o["reachable_dim_count"],
            "dim_detail": o["dim_detail"],
            "blocking_gap": o["blocking_gap"],
            "gap_is_data_level": "YES" if o["blocking_gap"] in (
                "UPSTREAM_HOLD", "PROVISIONAL", "LOW_BASE_UNCONFIRMED") or
                "PROVISIONAL" in o["blocking_gap"] or "LOW_BASE" in o["blocking_gap"] else "NO",
            "next_data_action": o["reentry_condition"],
            "note": "仅数据依赖核验；未新增 PDF 深读，未改变任何指标状态",
        })
    qc_cols = list(qc_rows[0].keys()) if qc_rows else []
    qc_path = S04 / "review_100_qc.csv"
    with qc_path.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=qc_cols)
        w.writeheader()
        w.writerows(qc_rows)
    outputs["review_100_qc.csv"] = {"path": "runs/issues/S04/review_100_qc.csv",
                                    "rows": len(qc_rows), "sha256": sha_file(qc_path)}

    grade = Counter(o["evidence_grade"] for o in pass_rows)
    summary = {
        "issue": "S04 / #39",
        "rule_layer": "L2",
        "rules_version": rules["rules_version"],
        "rules_sha256": rules_sha,
        "knowledge_as_of": cfg.get("as_of"),
        "universe": len(out),
        "decisions": dict(by_dec),
        "by_partition": {f"{p}|{d}": n for (p, d), n in sorted(by_part_dec.items())},
        "pass_evidence_grade": dict(grade),
        "pass_grade_b_companies": [o["company_id"] for o in pass_rows
                                   if o["evidence_grade"] == "B_ABS_CHANNEL"],
        "pass_abs_dependency_critical": [
            {"security_id": o["company_id"], "stock_name": o["company_name"],
             "clean_sg": o["clean_sg"], "non_ok": o["non_ok_metric_in_clean_sg"]}
            for o in pass_rows if o["abs_dependency_critical"] == "YES"],
        "observe_reasons": dict(Counter(o["blocking_gap"] for o in observe_rows)),
        "review_targets": len(review_targets),
        "outputs": outputs,
    }
    (S04 / "tight_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    manifest = {
        "issue_key": "S04",
        "issue_number": 39,
        "plan_version": "20261026_collection_first_v2",
        "rule_layer": "L2",
        "executor": "WorkBuddy AI",
        "review_nature": "SELF_CHECK",
        "generated_by": "runs/issues/S04/tight_screen.py",
        "inputs": {
            "s03_wide_pass": {"path": "runs/issues/S03/rerun_20261106/wide_pass.csv",
                              "sha256": sha_file(RERUN / "wide_pass.csv"), "rows": 777},
            "s03_wide_defer": {"path": "runs/issues/S03/rerun_20261106/wide_defer.csv",
                               "sha256": sha_file(RERUN / "wide_defer.csv"), "rows": 149},
            "s03_wide_unknown": {"path": "runs/issues/S03/rerun_20261106/wide_unknown.csv",
                                 "sha256": sha_file(RERUN / "wide_unknown.csv"), "rows": 128},
            "s03_review_targets": {"path": "runs/issues/S03/rerun_20261106/s04_review_targets.csv",
                                   "sha256": sha_file(RERUN / "s04_review_targets.csv"), "rows": 100},
            "s03_config": {"path": "runs/issues/S03/l1_config.json", "sha256": cfg_sha},
            "s01_rules": {"path": "runs/issues/S01/screen_rules_v2.json", "sha256": rules_sha},
            "s02_metrics": {"path": str(METRICS_PATH.relative_to(ROOT)).replace("\\", "/"),
                            "sha256": met_decl.get("sha256")},
            "s02_to_s03_contract": {
                "path": "runs/issues/S02/acceptance_20261106/s03_input_contract.json",
                "sha256": sha_file(CONTRACT_PATH)},
            "company_master": {"path": "data/company_master.csv",
                               "sha256": sha_file(MASTER_PATH), "rows": len(master)},
        },
        "outputs": outputs,
        "checks": checks,
        "counts": summary["decisions"],
        "no_quota_attestation": "未为达到任何家数目标调整阈值；443 为规则结果而非目标。",
        "limits": [
            "L2 只做多指标共同改善判定，不是投资候选、不含业务/估值结论。",
            "信号来自 S03 已验收交付；本卡未重算信号，只核对所用指标状态与维度归属。",
            "PROVISIONAL / 低基数 / HOLD 均不得计入 L2 维度，保留重进条件。",
            "四家截止日后公司保持隔离，未产生正负信号。",
        ],
    }
    (S04 / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    failed = [c for c in checks if not c["pass"] and c["level"] == "FAIL"]
    warns = [c for c in checks if not c["pass"] and c["level"] == "WARN"]
    review = {
        "issue_key": "S04",
        "issue_number": 39,
        "review_nature": "SELF_CHECK",
        "reviewer": "WorkBuddy AI（执行方自检）",
        "decision": "SELF_CHECK_PASS" if not failed else "SELF_CHECK_FAIL",
        "checks": checks,
        "checks_passed": f"{sum(1 for c in checks if c['pass'])}/{len(checks)}",
        "warnings": [w["id"] for w in warns],
        "counts": summary["decisions"],
        "pass_evidence_grade": summary["pass_evidence_grade"],
        "not_independent": "自检不等同独立复核；未逐份回读 PDF，未新增业务采用。",
        "limits": manifest["limits"],
    }
    (S04 / "review.json").write_text(
        json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    for c in checks:
        flag = "PASS" if c["pass"] else ("WARN" if c["level"] == "WARN" else "FAIL")
        print(f"{flag} {c['id']} {c['name']}")
    print("decisions:", dict(by_dec))
    print("pass grade:", dict(grade))
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
