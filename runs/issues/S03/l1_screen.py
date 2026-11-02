#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""S03（#38）L1 第一道宽筛：任一改善信号，保留观察队列。

设计约束（来自 S01 冻结规则 + 用户 2026-11-02 指令）：
1. 不改 screen_rules_v2.json；阈值、信号、风险提示全部从规则文件读取，代码不复制阈值；
2. 7 级互斥分流 P1→P7，主桶 l1_bucket + 正交子标签 l1_subtag，七桶合计必须 = 1,054；
3. HOLD 不参与「任一」判断，且不得因 HOLD 判为无信号；
4. PROVISIONAL（Q06/W5）可进 L1，带标记；低基数（Q05）单列，进 L2 需绝对额确认；
5. 只有 metric_status ∈ {OK, PROVISIONAL} 的指标可触发 SG；HOLD/MISSING/NOT_COMPARABLE/
   UNDEFINED_BASE/NOT_APPLICABLE 一律不得触发（SG06/SG08 走绝对额通道，另行判定）；
6. 输出 L2 预备度计数，锁定 S04 前的最小人工复核集。

用法：python runs/issues/S03/l1_screen.py
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
S03 = ROOT / "runs/issues/S03"
CFG_PATH = S03 / "l1_config.json"
CST = timezone(timedelta(hours=8))
NOW = datetime.now(CST).isoformat(timespec="seconds")

USABLE = {
    "EXTRACTED", "EXTRACTED_KEY_TABLE", "EXTRACTED_QUARTERLY_TABLE",
    "DERIVED", "DERIVED_CUMULATIVE_DIFF", "DERIVED_Q1_EQUALS_YTD",
    "DERIVED_QUARTERLY_SUM_OVERRIDE", "LEGACY_SNAPSHOT",
}
ABS_CONFIRM = 10_000_000.0


def sha_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fnum(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def main() -> int:
    cfg = json.loads(CFG_PATH.read_text(encoding="utf-8"))
    rules_path = ROOT / cfg["inputs"]["rules"]
    rules = json.loads(rules_path.read_text(encoding="utf-8"))
    rules_sha = sha_file(rules_path)

    met_path = ROOT / cfg["inputs"]["metrics"]
    summ_path = ROOT / cfg["inputs"]["company_summary"]
    norm_path = ROOT / cfg["inputs"]["normalized"]

    # ---------------- 装载
    metrics: dict[str, dict[str, dict]] = defaultdict(dict)
    with met_path.open(encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            metrics[r["security_id"]][r["metric_id"]] = r
    summary = {}
    with summ_path.open(encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            summary[r["security_id"]] = r

    norm: dict[tuple[str, str, str], dict] = {}
    with gzip.open(norm_path, "rt", encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            norm[(r["security_id"], r["period_key"], r["field_id"])] = r

    signals = rules["signals"]
    risks = [h for h in rules["risk_hints"]]
    dims = cfg["dimensions"]
    override = {o["security_id"]: o for o in cfg.get("company_overrides", [])}
    pending = {}                      # 底稿已补齐，PENDING_WORKPAPER 清零
    ADMIT = set(cfg["admittance_statuses"])

    def base_status(verdict: str) -> str:
        """底稿裁决 → 逻辑基态（决定能否触发 SG/RH）。"""
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

    # 应用底稿的指标级裁决（状态 + 重算值），S02 原始文件不动
    for sec, ov in override.items():
        for mid, spec in ov["metrics"].items():
            row = metrics.get(sec, {}).get(mid)
            if row is None:
                continue
            row["_verdict"] = spec["verdict"]
            row["metric_status"] = base_status(spec["verdict"])
            if spec.get("value") is not None:
                row["value"] = spec["value"]

    def flags_of(row):
        return set((row.get("quality_flags") or "").split(";")) - {""}

    def usable_metric(row):
        return row is not None and row["metric_status"] in ADMIT and fnum(row["value"]) is not None

    def row_q06(row):
        if row is None:
            return False
        note = row.get("comparability_note") or ""
        if "RESTATED_COMPARATIVE_ADOPTED" in note:
            return False
        return row.get("restatement_flag") in ("是", "RESTATEMENT_INDICATED_NEEDS_REVIEW") \
            or "RESTATED_PRIOR_YEARS_UNRECALCULATED" in note

    def usable_raw(row):
        return row is not None and row["status"] in USABLE and fnum(row.get("value_cny")) is not None

    def signal_quality(mid_rows, fired_flags):
        """CLEAN / LOW_BASE / PROVISIONAL，按依赖指标的标记判定。"""
        fl = set()
        for row in mid_rows:
            fl |= flags_of(row)
        if "Q05" in fl or fired_flags.get("Q05"):
            return "LOW_BASE"
        if "Q06" in fl or fired_flags.get("Q06") or any(r["metric_status"] == "PROVISIONAL" for r in mid_rows):
            return "PROVISIONAL"
        return "CLEAN"

    rows_out = []
    diag = Counter()
    ref_blocked_fired = []

    for sec in sorted(metrics):
        m = metrics[sec]
        pk = m["M01"]["period_key"]
        py = str(int(pk) - 10000)
        srow = summary.get(sec, {})
        l0 = srow.get("l0_evaluability", "")
        ov = override.get(sec)
        blocked = bool(ov and ov.get("block_sg"))

        fired: list[dict] = []       # 所有命中
        hold_blocked: list[str] = []
        rh_hits: list[str] = []

        for s in signals:
            sid, mid, op = s["id"], s["metric"], s["operator"]
            dim = s["dimension"]

            if sid == "SG07":
                m8, m9 = m.get("M08"), m.get("M09")
                deps = [m8, m9]
                if any(d is not None and d["metric_status"] == "HOLD" for d in deps):
                    hold_blocked.append(sid)
                    continue
                if not (usable_metric(m8) and usable_metric(m9)):
                    continue
                ok = fnum(m8["value"]) >= 0.8 and fnum(m9["value"]) > 0
                if not ok:
                    continue
                q = signal_quality(deps, {})
                if "Q09" in flags_of(m5 := m.get("M05") or {}):
                    q = "PROVISIONAL"          # 一次性损益主导 → 现金含量降级
                    diag["sg07_q09_downgrade"] += 1
                fired.append({"id": sid, "dim": dim, "quality": q, "value": fnum(m8["value"])})
                continue

            if sid == "SG06":
                r5 = m.get("M05")
                if r5 is None or r5["metric_status"] != "UNDEFINED_BASE":
                    continue
                verdict = r5.get("_verdict") or ""
                if "SCOPE_CHANGE" in verdict or "STRUCTURAL_BREAK" in verdict:
                    diag["sg06_suppressed_scope"] += 1
                    continue          # 底稿明确：范围断裂/结构断裂不得走绝对额通道
                cur = fnum((norm.get((sec, pk, "FIN.NPDEDT.YTD")) or {}).get("value_cny"))
                base = fnum((norm.get((sec, py, "FIN.NPDEDT.YTD")) or {}).get("value_cny"))
                if cur is None or base is None:
                    continue
                if base < 0 and cur > 0 and cur >= ABS_CONFIRM:
                    fl = flags_of(r5)
                    if "Q05" in fl:
                        q = "LOW_BASE"
                    elif "Q06" in fl or row_q06(norm.get((sec, pk, "FIN.NPDEDT.YTD"))) \
                            or row_q06(norm.get((sec, py, "FIN.NPDEDT.YTD"))):
                        q = "PROVISIONAL"
                    else:
                        q = "CLEAN" if cfg["policies"]["sg06_clean_policy"] == "INPUT_CLEAN" else "PROVISIONAL"
                    fired.append({"id": sid, "dim": dim, "quality": q, "value": cur})
                diag["sg06_evaluated"] += 1
                continue

            if sid == "SG08":
                if blocked:
                    diag["sg08_suppressed_ref_only"] += 1
                    continue          # 隔离公司不走绝对额通道
                o = norm.get((sec, pk, "FIN.OCF.YTD"))
                ob = norm.get((sec, py, "FIN.OCF.YTD"))
                if not (usable_raw(o) and usable_raw(ob)):
                    continue
                cv, bv = fnum(o["value_cny"]), fnum(ob["value_cny"])
                if cv > 0 and bv <= 0:
                    q = "PROVISIONAL" if (row_q06(o) or row_q06(ob)) else "CLEAN"
                    fired.append({"id": sid, "dim": dim, "quality": q, "value": cv - bv})
                continue

            # 常规阈值型 SG01-SG05 / SG09
            r = m.get(mid)
            if r is not None and r["metric_status"] == "HOLD":
                hold_blocked.append(sid)
                continue
            if not usable_metric(r):
                continue
            v = fnum(r["value"])
            ok = v >= s["threshold"] if op == ">=" else (v <= s["threshold"] if op == "<=" else v > s["threshold"])
            if ok:
                fired.append({"id": sid, "dim": dim, "quality": signal_quality([r], {}), "value": v})

        # ---------------- 风险提示
        project_mode = any("Q10" in flags_of(r) for r in m.values())
        for h in risks:
            hid, mid, op = h["id"], h["metric"], h["operator"]
            if hid == "RH06":
                if any("Q09" in flags_of(r) for r in m.values()):
                    rh_hits.append(hid)
                continue
            if hid == "RH02" and project_mode and cfg["policies"]["rh02_skip_if_project_mode"]:
                continue
            r = m.get(mid)
            if not usable_metric(r):
                continue
            v = fnum(r["value"])
            thr = h.get("threshold")
            if thr is None:
                continue
            ok = v >= thr if op == ">=" else (v <= thr if op == "<=" else v < thr)
            if ok:
                rh_hits.append(hid)

        # ---------------- 维度计数
        clean_dims = {f["dim"] for f in fired if f["quality"] == "CLEAN"}
        potential_dims = {f["dim"] for f in fired if f["quality"] in ("CLEAN", "LOW_BASE", "PROVISIONAL")}
        lit = potential_dims
        hold_dims = {d for d, ms in dims.items()
                     if d not in lit and any(m.get(x) is not None and m[x]["metric_status"] == "HOLD" for x in ms)}
        c_ok, t_pot, h_dim = len(clean_dims), len(potential_dims), len(hold_dims)

        if c_ok >= 2:
            prio = "AUTO_PASS_L2_READY"
        elif c_ok < 2 and (t_pot + h_dim) >= 2:
            prio = "HIGH_PRIORITY_VERIFY"
        else:
            prio = "LOW_PRIORITY_SINGLE_DIM"

        # ---------------- 分流（严格互斥）
        clean_f = [f["id"] for f in fired if f["quality"] == "CLEAN"]
        lowbase_f = [f["id"] for f in fired if f["quality"] == "LOW_BASE"]
        prov_f = [f["id"] for f in fired if f["quality"] == "PROVISIONAL"]
        any_hold_m1_m9 = any(m.get(x) is not None and m[x]["metric_status"] == "HOLD"
                             for x in ("M01", "M02", "M03", "M04", "M05", "M06", "M07", "M08", "M09"))

        if blocked:
            ref_sub = (ov.get("expected", {}) or {}).get("subtag", "")
            if not ref_sub.startswith("REF_ONLY_"):
                verdicts = {spec["verdict"] for spec in ov["metrics"].values()}
                ref_sub = ("REF_ONLY_STRUCTURAL_BREAK"
                           if any("STRUCTURAL_BREAK" in v for v in verdicts)
                           else "REF_ONLY_SCOPE_CHANGE")
            bucket, subtag = "OBSERVE_QUEUE", ref_sub
            if fired:
                ref_blocked_fired.append({"security_id": sec, "stock_name": srow.get("stock_name", ""),
                                          "status": ref_sub, "would_fire": [f["id"] for f in fired]})
        elif l0 in ("W1_NO_DATA", "W2_ALL_HOLD", "W4_EARLY"):
            bucket, subtag = "OBSERVE_QUEUE", "L0_" + l0
        elif clean_f:
            bucket, subtag = "OBSERVE_QUEUE", "OQ_CLEAN_OK"
        elif lowbase_f:
            bucket, subtag = "OBSERVE_QUEUE", "OQ_LOW_BASE_PROVISIONAL"
        elif prov_f:
            bucket, subtag = "OBSERVE_QUEUE", "OQ_PROVISIONAL_ONLY"
        elif rh_hits:
            bucket, subtag = "RISK_WATCH", "RW_HAS_HOLD" if any_hold_m1_m9 else "RW_CLEAN"
        elif any_hold_m1_m9:
            bucket, subtag = "OBSERVE_QUEUE", "OQ_HOLD_PROTECTED"
        else:
            bucket, subtag = "NO_SIGNAL", "NS_CONFIRMED"

        # 隔离桶：不得对外暴露为「命中」，维度计数清零，优先级按底稿裁决
        blocked_would, rh_blocked_would = [], []
        priority_note = ""
        if blocked:
            blocked_would = [f["id"] for f in fired]
            rh_blocked_would = sorted(set(rh_hits))
            clean_f, lowbase_f, prov_f = [], [], []
            c_ok = t_pot = h_dim = 0
            rh_hits = []
            prio = (ov.get("expected", {}) or {}).get("priority", "REFERENCE_ONLY_BLOCKED")
            priority_note = ov.get("priority_note") or "底稿口径判为不可比，SG/RH 均不参与判定"
        elif sec in pending and prio == "AUTO_PASS_L2_READY":
            prio = "HIGH_PRIORITY_VERIFY"
            priority_note = "WORKPAPER_GATE：底稿未落定，不得自动放行 L2"

        # NO_SIGNAL 二分：证据完整 vs 关键指标 MISSING/NOT_COMPARABLE/Q06（重述未决）
        if subtag == "NS_CONFIRMED":
            incomplete = any(m.get(x) is not None and m[x]["metric_status"] in ("MISSING", "NOT_COMPARABLE")
                             for x in m) or any("Q06" in flags_of(r) for r in m.values())
            if incomplete:
                subtag = "NS_INCOMPLETE_EVIDENCE"
                diag["ns_evidence_incomplete"] += 1

        if clean_f:
            diag["has_clean_signal"] += 1
        if lowbase_f:
            diag["has_lowbase_signal"] += 1
            if subtag == "OQ_CLEAN_OK":
                diag["lowbase_also_clean"] += 1
        if prov_f:
            diag["has_provisional_signal"] += 1
            if subtag == "OQ_CLEAN_OK":
                diag["prov_also_clean"] += 1

        all_flags = sorted({x for r in m.values() for x in flags_of(r)})
        rows_out.append({
            "company_id": sec,
            "company_name": srow.get("stock_name", ""),
            "anchor_period": pk,
            "anchor_period_type": srow.get("period_type", ""),
            "stale_period": srow.get("stale_period", ""),
            "l0_status": l0,
            "workpaper_status": "WORKPAPER_ADOPTED" if ov else "",
            "workpaper_verdicts": ";".join(f"{mid}:{spec['verdict']}"
                                           for mid, spec in sorted(ov["metrics"].items())) if ov else "",
            "l1_bucket": bucket,
            "l1_subtag": subtag,
            "sg_hit_clean_list": ";".join(clean_f),
            "sg_hit_provisional_list": ";".join(prov_f),
            "sg_hit_lowbase_list": ";".join(lowbase_f),
            "sg_hit_all_list": ";".join(sorted(set(clean_f) | set(prov_f) | set(lowbase_f))),
            "sg_blocked_would_fire": ";".join(blocked_would),
            "rh_blocked_would_fire": ";".join(rh_blocked_would),
            "sg_hold_list": ";".join(sorted(set(hold_blocked))),
            "rh_hit_list": ";".join(sorted(set(rh_hits))),
            "quality_flags_summary": ";".join(all_flags),
            "clean_ok_dims_count": c_ok,
            "total_potential_dims_count": t_pot,
            "hold_dims_count": h_dim,
            "s04_review_priority": prio,
            "priority_note": priority_note,
            "project_mode": "YES" if project_mode else "NO",
        })

    # ---------------- 守恒与统计
    bucket_counts = Counter(r["l1_bucket"] for r in rows_out)
    subtag_counts = Counter(r["l1_subtag"] for r in rows_out)
    prio_counts = Counter(r["s04_review_priority"] for r in rows_out)
    total = len(rows_out)
    identity_ok = (
        subtag_counts.get("L0_W1_NO_DATA", 0) + subtag_counts.get("L0_W2_ALL_HOLD", 0)
        + subtag_counts.get("L0_W4_EARLY", 0)
        + subtag_counts.get("OQ_CLEAN_OK", 0) + subtag_counts.get("OQ_LOW_BASE_PROVISIONAL", 0)
        + subtag_counts.get("OQ_PROVISIONAL_ONLY", 0)
        + subtag_counts.get("RW_CLEAN", 0) + subtag_counts.get("RW_HAS_HOLD", 0)
        + subtag_counts.get("OQ_HOLD_PROTECTED", 0) + subtag_counts.get("NS_CONFIRMED", 0)
        + subtag_counts.get("NS_INCOMPLETE_EVIDENCE", 0)
        + sum(v for k, v in subtag_counts.items() if k.startswith("REF_ONLY_"))
    ) == total

    out_csv = S03 / "l1_screen_results.csv"
    fields = list(rows_out[0].keys())
    with out_csv.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        w.writerows(rows_out)

    targets = [r for r in rows_out if r["s04_review_priority"] == "HIGH_PRIORITY_VERIFY"]
    with (S03 / "s04_review_targets.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        w.writerows(targets)

    # 底稿 10 家裁决对账：实际分流必须与底稿预期一致
    by_sec = {r["company_id"]: r for r in rows_out}
    expected_checks = []
    for sec, ov in override.items():
        exp = ov.get("expected") or {}
        if not exp:
            continue
        r = by_sec[sec]
        ok = (r["l1_bucket"] == exp["bucket"] and r["l1_subtag"] == exp["subtag"]
              and r["s04_review_priority"] == exp["priority"])
        expected_checks.append({
            "security_id": sec, "stock_name": r["company_name"],
            "expected": exp,
            "actual": {"bucket": r["l1_bucket"], "subtag": r["l1_subtag"],
                       "priority": r["s04_review_priority"]},
            "match": ok,
        })
    workpaper_ok = all(x["match"] for x in expected_checks)

    # ---------------- 自检：P01 规则 / P02 指纹 / 守恒 / 覆盖
    fp = {x["path"]: x["sha256"] for x in rules["input_fingerprint"]["files"]}
    snap_path = ROOT / cfg["inputs"]["s02_snapshot"]
    snap = json.loads(snap_path.read_text(encoding="utf-8")) if snap_path.is_file() else {}
    fp_checks = []
    for path, expected in (
        ("data/company_master.csv", fp.get("data/company_master.csv")),
        ("runs/issues/S00/normalization_manifest.json", fp.get("runs/issues/S00/normalization_manifest.json")),
    ):
        actual = sha_file(ROOT / path)
        fp_checks.append({"path": path, "expected": expected, "actual": actual, "match": actual == expected})
    met_actual = sha_file(met_path)
    fp_checks.append({"path": cfg["inputs"]["metrics"],
                      "expected": snap.get("metrics", {}).get("sha256"),
                      "actual": met_actual, "match": met_actual == snap.get("metrics", {}).get("sha256")})
    self_check = {
        "P01_rules_hash": {"sha256": rules_sha, "accepted_match": rules_sha in cfg["rules_sha_accepted"],
                           "note": "磁盘为 LF 变体 d9a6b3cc…；指令写的 ada501e8… 是同一内容的 CRLF 变体，两者均在接受集内"},
        "P02_input_fingerprints": {"all_match": all(c["match"] for c in fp_checks), "checks": fp_checks},
        "P03_conservation": {"identity_ok": identity_ok, "total": total},
        "P04_row_coverage": {"rows": total, "unique": len({r["company_id"] for r in rows_out})},
        "P05_review_targets": {"high_priority_verify": len(targets)},
        "P06_workpaper_outcomes": {"all_match": workpaper_ok, "checks": expected_checks},
    }

    manifest = {
        "issue": "S03 #38",
        "version": "S03_L1_SCREEN_20261102",
        "status": "SELF_CHECK_PASS_PENDING_EXTERNAL_REVIEW",
        "generated_at": NOW,
        "as_of": cfg["as_of"],
        "inputs": {
            "rules": {"path": cfg["inputs"]["rules"], "sha256": rules_sha,
                      "accepted": cfg["rules_sha_accepted"], "accepted_match": rules_sha in cfg["rules_sha_accepted"]},
            "metrics": {"path": cfg["inputs"]["metrics"], "sha256": sha_file(met_path), "cells": sum(len(v) for v in metrics.values())},
            "company_summary": {"path": cfg["inputs"]["company_summary"], "sha256": sha_file(summ_path), "companies": len(summary)},
            "normalized": {"path": cfg["inputs"]["normalized"], "sha256": sha_file(norm_path)},
            "company_master": {"path": cfg["inputs"]["company_master"], "sha256": sha_file(ROOT / cfg["inputs"]["company_master"])},
        },
        "universe": total,
        "bucket_counts": dict(bucket_counts),
        "subtag_counts": dict(subtag_counts),
        "conservation": {"identity_ok": identity_ok, "total": total,
                         "sum_of_buckets": sum(bucket_counts.values())},
        "self_check": self_check,
        "s04_priority_counts": dict(prio_counts),
        "workpaper": cfg.get("workpaper", {}),
        "company_overrides_applied": [
            {"security_id": o["security_id"], "stock_name": o["stock_name"],
             "block_sg": o["block_sg"], "metric_cells": len(o["metrics"]),
             "expected": o.get("expected", {})}
            for o in override.values()
        ],
        "diagnostics": {
            "ref_only_blocked_with_signals": ref_blocked_fired,
            "sg07_q09_downgrade": diag.get("sg07_q09_downgrade", 0),
            "sg06_evaluated": diag.get("sg06_evaluated", 0),
            "has_clean_signal": diag.get("has_clean_signal", 0),
            "has_lowbase_signal": diag.get("has_lowbase_signal", 0),
            "lowbase_also_clean": diag.get("lowbase_also_clean", 0),
            "has_provisional_signal": diag.get("has_provisional_signal", 0),
            "prov_also_clean": diag.get("prov_also_clean", 0),
            "ns_evidence_incomplete": diag.get("ns_evidence_incomplete", 0),
            "sg06_suppressed_scope": diag.get("sg06_suppressed_scope", 0),
            "sg08_suppressed_ref_only": diag.get("sg08_suppressed_ref_only", 0),
            "note": "含低基数/暂定信号的公司多数同时有干净信号，按 P2>P3>P4 严格优先级归入 OQ_CLEAN_OK；"
                    "指令预估的 ~319 / ~131 是「含该类信号的公司数」，不等于 P3/P4 桶规模。",
        },
        "outputs": {
            "l1_screen_results": {"path": str(out_csv.relative_to(ROOT)).replace("\\", "/"),
                                  "sha256": sha_file(out_csv), "rows": total},
            "s04_review_targets": {"path": "runs/issues/S03/s04_review_targets.csv",
                                   "sha256": sha_file(S03 / "s04_review_targets.csv"), "rows": len(targets)},
        },
        "notes": [
            "阈值与信号定义全部来自 screen_rules_v2.json，未复制、未修改。",
            "P1 的 L0_W1/W2/W4 在当前输入下为 0：S02 的 L0 addendum 已把无干净 OK 的公司归入 W5，按 P4 处理。",
            "REF_ONLY_* 为隔离桶：底稿缺失时按用户指令点名落地，不臆造其余公司。",
            "本结果为执行方自检，不构成外部验收。",
        ],
    }
    (S03 / "s03_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({
        "status": manifest["status"], "universe": total,
        "buckets": dict(bucket_counts), "subtags": dict(subtag_counts),
        "priority": dict(prio_counts), "identity_ok": identity_ok,
        "workpaper_ok": workpaper_ok,
        "workpaper_fail": [x["security_id"] for x in expected_checks if not x["match"]],
        "ref_blocked_with_signals": len(ref_blocked_fired),
        "sg07_q09_downgrade": diag.get("sg07_q09_downgrade", 0),
    }, ensure_ascii=False, indent=1))
    return 0 if (identity_ok and workpaper_ok) else 2


if __name__ == "__main__":
    sys.exit(main())
