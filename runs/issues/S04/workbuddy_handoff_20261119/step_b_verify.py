#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""步骤B自检：对已生成的 S05 差额表做独立复算，不修改任何输入。

检查项全部可从输入重推，不引用 step_b_build.py 的中间变量。
"""
import csv
import gzip
import hashlib
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
FD = os.path.join(REPO, "runs", "issues", "S04", "completion_20261114", "final_delivery_20261116")
QUAL = os.path.join(REPO, "runs", "issues", "S04", "completion_20261114", "qualification_v3_20261115")
S00 = os.path.join(REPO, "runs", "issues", "S02", "hangcha_restated_20261101", "s00_v10", "s00_v10.csv.gz")
MASK = os.path.join(REPO, "runs/issues/S00/completion_20261114/remaining_scope_review_20261115",
                    "classification_v2/CE_admission_projection/execution",
                    "all_pool_metrics_source_aware_mask.csv")
DELTA = os.path.join(HERE, "s05_source_eligibility_delta.csv")
TARGET = os.path.join(HERE, "s05_target_assignment.csv")
CARRY = os.path.join(HERE, "carryover_register.csv")
CONTRACT = os.path.join(HERE, "s05_input_contract_draft.json")
QUEUE = os.path.join(HERE, "bounded_source_verification_queue.csv")

HOLD = {"EXTRACTED_XCHECK_MISMATCH", "DERIVED_HOLD_UPSTREAM", "DERIVED_Q1_HOLD_UPSTREAM"}
USABLE = {"EXTRACTED", "EXTRACTED_KEY_TABLE", "EXTRACTED_QUARTERLY_TABLE", "DERIVED",
          "DERIVED_CUMULATIVE_DIFF", "DERIVED_Q1_EQUALS_YTD", "DERIVED_QUARTERLY_SUM_OVERRIDE",
          "LEGACY_SNAPSHOT"}
CHECKS = []


def check(cid, name, ok, detail=None):
    CHECKS.append({"id": cid, "name": name, "pass": bool(ok), "detail": detail})
    return bool(ok)


def rows(p):
    with open(p, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def main():
    now = datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")
    delta = rows(DELTA)
    target = rows(TARGET)
    carry = rows(CARRY)
    queue = rows(QUEUE)
    contract = json.load(open(CONTRACT, encoding="utf-8"))
    pass_rows = rows(os.path.join(FD, "reviewed_view", "tight_pass.csv"))
    cand = {r["security_id"]: r for r in pass_rows}
    log_rows = rows(os.path.join(FD, "reviewed_view", "tight_decision_log.csv"))
    dep_rows = rows(os.path.join(QUAL, "signal_dependency_members.csv"))

    # ---- 重建 S00 与争议（独立于构建脚本） ----
    s00 = {}
    with gzip.open(S00, "rt", encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            if r["security_id"] in cand:
                s00[(r["security_id"], r["field_id"], r["period_key"])] = r
    open_disp = defaultdict(set)
    for r in rows(os.path.join(QUAL, "dispute_member_map.csv")):
        if r["open_at_replay"] == "YES":
            open_disp[(r["security_id"], r["field_id"], r["period_key"])].add(r["dispute_id"])
    acc_disp = defaultdict(set)
    for r in rows(os.path.join(QUAL, "accepted_dispositions.csv")):
        acc_disp[(r["security_id"], r["field_id"], r["period_key"])].add(r["dispute_id"])

    # ---- B1 信号依赖行数与 S04 生效依赖一致 ----
    dep_eff_keys = {(r["security_id"], r["field_id"], r["period_key"])
                    for r in dep_rows if r["security_id"] in cand
                    and r["signal_effective_status"].startswith("QUALIFIED")}
    sig_delta = [d for d in delta if d["consumption_class"] == "SIGNAL_L3"]
    check("B1a", "SIGNAL_L3 行数等于 S04 生效依赖行数 3738", len(sig_delta) == 3738,
          {"delta": len(sig_delta), "expected": 3738})
    missing_keys = [(d["security_id"], d["field_id"], d["period_key"]) for d in sig_delta
                    if (d["security_id"], d["field_id"], d["period_key"]) not in dep_eff_keys]
    check("B1b", "SIGNAL_L3 每行都能在 S04 生效依赖表中找到对应成员", not missing_keys,
          {"missing": len(missing_keys), "sample": missing_keys[:5]})

    # ---- B2 信号依赖行无开放争议（与 peer 一致） ----
    sig_open = [d for d in sig_delta if d["open_dispute_ids"]]
    check("B2", "SIGNAL_L3 无开放争议（与 peer 记录的 0 一致）", not sig_open,
          {"rows_with_dispute": len(sig_open)})

    # ---- B3 每行状态自洽 ----
    bad = []
    for d in delta:
        row = s00.get((d["security_id"], d["field_id"], d["period_key"]))
        if d["s05_use_class"] == "ELIGIBLE_FOR_S05":
            if row is None:
                bad.append((d["security_id"], d["field_id"], d["period_key"], "NO_ROW"))
                continue
            if row["status"] not in USABLE:
                bad.append((d["security_id"], d["field_id"], d["period_key"], "STATUS_" + row["status"]))
            if not row["document_id"]:
                bad.append((d["security_id"], d["field_id"], d["period_key"], "NO_DOC"))
            if not row["source_page"] and d["page_evidence_mode"] != "VIA_PARENT":
                bad.append((d["security_id"], d["field_id"], d["period_key"], "NO_PAGE"))
            if row["consolidation_scope"] != "CONSOLIDATED":
                bad.append((d["security_id"], d["field_id"], d["period_key"], "SCOPE"))
            if row["restatement_flag"] == "RESTATEMENT_INDICATED_NEEDS_REVIEW":
                bad.append((d["security_id"], d["field_id"], d["period_key"], "Q06"))
            un = open_disp[(d["security_id"], d["field_id"], d["period_key"])] - \
                acc_disp[(d["security_id"], d["field_id"], d["period_key"])]
            if un:
                bad.append((d["security_id"], d["field_id"], d["period_key"], "OPEN_DISPUTE"))
    check("B3", "标为 ELIGIBLE_FOR_S05 的每行都能独立复核为可用", not bad,
          {"violations": len(bad), "sample": bad[:5]})

    # ---- B4 VIA_PARENT 的父键页码独立复核 ----
    bad_parents = []
    for d in delta:
        if d["page_evidence_mode"] != "VIA_PARENT":
            continue
        parents = [p for p in d["page_evidence_parents"].split(";") if p]
        if not parents:
            bad_parents.append((d["security_id"], d["field_id"], d["period_key"], "NO_PARENT"))
            continue
        for p in parents:
            f2, p2 = p.split("@")
            r2 = s00.get((d["security_id"], f2, p2))
            if r2 is None or not r2["source_page"]:
                bad_parents.append((d["security_id"], f2, p2, "PARENT_NO_PAGE"))
    check("B4", "派生值经父键追溯的页码全部存在", not bad_parents,
          {"violations": len(bad_parents), "sample": bad_parents[:5]})

    # ---- B5 目标分配守恒 ----
    role = Counter(r["s05_role"] for r in target)
    check("B5a", "目标分配 1054 行且主键唯一",
          len(target) == 1054 and len({r["security_id"] for r in target}) == 1054,
          {"rows": len(target), "unique": len({r["security_id"] for r in target})})
    check("B5b", "主检查池 278 家且与 tight_pass 完全一致",
          role["PRIMARY_CHECK_POOL"] == 278 and
          {r["security_id"] for r in target if r["s05_role"] == "PRIMARY_CHECK_POOL"} == set(cand),
          {"primary": role["PRIMARY_CHECK_POOL"]})
    check("B5c", "各角色之和等于 1054", sum(role.values()) == 1054, dict(role))

    # ---- B6 结转登记齐全 ----
    ctype = Counter(r["carryover_type"] for r in carry)
    expect = {"CE_QUALITY_SOURCE_PENDING": 15, "HELD_PARENT_PROPOSAL_UNADOPTED": 8,
              "HCC_NPP_DISPUTE_OPEN": 1, "HCC_LIWIN_HOLD": 1,
              "ANCHOR_RESELECTION_PENDING": 1, "CUTOFF_AFTER_20261025": 4,
              "PROJECT_MODE_UNKNOWN": 3}
    check("B6", "结转登记七类齐全且计数一致", ctype == expect,
          {"observed": dict(ctype), "expected": expect})

    # ---- B7 质量指标裁决计数自洽 ----
    qcells = [d for d in delta if d["consumption_class"] == "QUALITY_RH"]
    per_metric = Counter(d["metric_id"] for d in qcells)
    measured = contract["measured"]
    check("B7a", "质量指标裁决总数 = 278 × 5", measured["quality_metric_verdicts"] == 1390,
          {"verdicts": measured["quality_metric_verdicts"]})
    check("B7b", "质量依赖行按指标计数与差额表自洽（行口径）",
          sum(per_metric.values()) == len(qcells),
          {"rows": len(qcells), "by_metric": dict(per_metric)})
    tot = sum(measured["quality_metric_by_s05_class"].values())
    check("B7c", "质量指标三分类之和 = 1390", tot == 1390, {"sum": tot})

    # ---- B8 冻结输入未被改动 ----
    fps = {
        "runs/issues/S04/completion_20261114/final_peer_review_20261116/peer_review.json":
            "ab249f1806e1997fb0f938b216aaeb17def7f460b03a08b694acafd7d2e7c924",
        "runs/issues/S00/completion_20261114/formal_gate_review_20261115/review.json":
            "d906efffa47321b68dec8e847c15122ca87cde17667cad59e75360396b42d2d1",
        "runs/issues/S04/completion_20261114/qualification_v3_20261115/manifest.json":
            "2be3081c47a634e960709bb16e9bf2327e109057bfbfd5509e5ce8fb27785144",
        "runs/issues/S02/hangcha_restated_20261101/s00_v10/s00_v10.csv.gz":
            "fc312c52ace51feb37593c08cb8077c8a47012a7a239ef639d0fe8b745fe2025",
        "runs/issues/S01/screen_rules_v3.json":
            "6c474d1fc58ea6d484a428e8203792e3c0cf427756413860b85e17c16b1e4d45",
    }
    bad_fp = [k for k, v in fps.items() if sha(os.path.join(REPO, k.replace("/", os.sep))) != v]
    check("B8", "冻结输入（peer/来源补充/资格manifest/B/v3规则）指纹未变", not bad_fp,
          {"bad": bad_fp})

    # ---- B9 差额表无重复键 ----
    keys = Counter((d["security_id"], d["consumption_class"], d["metric_id"],
                    d["field_id"], d["period_key"]) for d in delta)
    dup = {k: v for k, v in keys.items() if v > 1}
    check("B9", "差额表无重复 (公司, 消费类, 指标, 字段, 期间) 键", not dup,
          {"duplicates": len(dup), "sample": list(dup)[:5]})

    # ---- B10 指标算术抽查（M08 / M10，Decimal） ----
    def dec(x):
        return Decimal(x) if x not in (None, "") else None

    def days(pk):
        row = next((r for r in s00.values() if r["period_key"] == pk and r["period_start"]
                    and r["period_end"]), None)
        if not row:
            return None
        d1 = date.fromisoformat(row["period_start"])
        d2 = date.fromisoformat(row["period_end"])
        return Decimal((d2 - d1).days + 1)

    mask = {}
    for r in rows(MASK):
        if r["security_id"] in cand:
            mask[(r["security_id"], r["metric_id"])] = r
    checked, mismatch = 0, []
    for sid in list(cand)[:60]:
        anchor = cand[sid]["anchor_period"]
        # M08 = OCF.YTD(t) / NPP.YTD(t)
        a = s00.get((sid, "FIN.OCF.YTD", anchor))
        b = s00.get((sid, "FIN.NPP.YTD", anchor))
        m = mask.get((sid, "M08"))
        if a and b and m and m["metric_status"] == "OK":
            npv = dec(b["value_cny"])
            if npv and npv > 0:
                calc = dec(a["value_cny"]) / npv
                got = dec(m["value"])
                if got is not None:
                    checked += 1
                    if abs(calc - got) > Decimal("0.000001"):
                        mismatch.append((sid, "M08", str(calc), str(got)))
        # M10 = AR(t)/REV(t)*days(t) - same at t-1y
        ar = s00.get((sid, "FIN.AR.INSTANT", anchor))
        rev = s00.get((sid, "FIN.REV.YTD", anchor))
        m10 = mask.get((sid, "M10"))
        if ar and rev and m10 and m10["metric_status"] == "OK" and m10["base_period_key"]:
            dd = days(anchor)
            if dd:
                cur = dec(ar["value_cny"]) / dec(rev["value_cny"]) * dd
                ar0 = s00.get((sid, "FIN.AR.INSTANT", m10["base_period_key"]))
                rev0 = s00.get((sid, "FIN.REV.YTD", m10["base_period_key"]))
                dd0 = days(m10["base_period_key"])
                if ar0 and rev0 and dd0:
                    base = dec(ar0["value_cny"]) / dec(rev0["value_cny"]) * dd0
                    calc = cur - base
                    got = dec(m10["value"])
                    if got is not None:
                        checked += 1
                        if abs(calc - got) > Decimal("0.01"):
                            mismatch.append((sid, "M10", str(calc), str(got)))
    check("B10", "M08/M10 算术抽查与指标表一致（Decimal）", not mismatch,
          {"checked": checked, "mismatch": mismatch[:5]})

    # ---- B11 队列与待核格一一对应；行与格的口径必须分开核 ----
    pend_rows = [d for d in delta if d["s05_use_class"].startswith("PENDING")]
    pend_keys = {(d["security_id"], d["field_id"], d["period_key"], d["s05_use_class"])
                 for d in pend_rows}
    q_keys = {(r["security_id"], r["field_id"], r["period_key"], r["s05_use_class"]) for r in queue}
    check("B11a", "有界核证队列与待核格一一对应", pend_keys == q_keys,
          {"pending_cells": len(pend_keys), "queue": len(q_keys)})

    per_cell = Counter((d["security_id"], d["field_id"], d["period_key"]) for d in pend_rows)
    multi = {k: v for k, v in per_cell.items() if v > 1}
    check("B11b", "待核行 = 待核格 + 双消费者重复行；可判行 + 待核行 = 8,638",
          len(pend_rows) == len(pend_keys) + sum(v - 1 for v in multi.values()) == 15
          and len(pend_keys) == 13
          and sum(1 for d in delta if d["s05_use_class"] == "ELIGIBLE_FOR_S05") + len(pend_rows)
          == len(delta) == 8638,
          {"pending_rows": len(pend_rows), "pending_cells": len(pend_keys),
           "multi_consumer_cells": {"%s|%s|%s" % k: v for k, v in multi.items()},
           "eligible_rows": sum(1 for d in delta if d["s05_use_class"] == "ELIGIBLE_FOR_S05")})

    # ---- B12 合同 measured 块与差额表实算逐项相等（防 JSON 与 CSV 漂移） ----
    m = contract["measured"]
    got = {
        "delta_rows": len(delta),
        "by_consumption_class": dict(Counter(d["consumption_class"] for d in delta)),
        "by_use_class": dict(Counter(d["s05_use_class"] for d in delta)),
        "by_page_evidence_mode": dict(Counter(d["page_evidence_mode"] for d in delta)),
        "companies_with_any_pending_consumed_cell": len({d["security_id"] for d in pend_rows}),
        "bounded_verification_queue_rows": len(queue),
    }
    drift = {k: {"contract": m.get(k), "recomputed": v}
             for k, v in got.items() if m.get(k) != v}
    check("B12", "输入合同的 measured 计数与差额表实算逐项相等", not drift, {"drift": drift})

    # ---- B13 两份说明文档的表格数字与实算一致（防 prose 与数据漂移） ----
    def cell_counts(consumption):
        sub = [d for d in delta if d["consumption_class"] == consumption]
        return (len(sub), sum(1 for d in sub if d["s05_use_class"] == "ELIGIBLE_FOR_S05"),
                sum(1 for d in sub if d["s05_use_class"].startswith("PENDING")))

    expect_tbl = {
        "SIGNAL_L3": cell_counts("SIGNAL_L3"),
        "QUALITY_RH": cell_counts("QUALITY_RH"),
        "LOW_BASE_CONFIRM": cell_counts("LOW_BASE_CONFIRM"),
        "TOTAL": (len(delta), sum(1 for d in delta if d["s05_use_class"] == "ELIGIBLE_FOR_S05"),
                  len(pend_rows)),
    }
    hint_ready = m.get("risk_hints_ready_by_company", {})
    hint_block = m.get("risk_hints_blocked_by_company", {})
    pat = re.compile(r"^\|\s*([^|]+?)\s*\|\s*([\d,]+)\s*\|\s*([\d,]+)\s*\|\s*([\d,]+)\s*\|")
    label_map = [("信号 L3", "SIGNAL_L3"), ("质量指标依赖", "QUALITY_RH"),
                 ("低基数", "LOW_BASE_CONFIRM"), ("合计", "TOTAL")]
    prose_bad, prose_seen = [], Counter()
    for doc in ("S05_GATE_PACKET.md", "handoff.md"):
        p = os.path.join(HERE, doc)
        if not os.path.exists(p):
            prose_bad.append((doc, "MISSING"))
            continue
        for line in open(p, encoding="utf-8"):
            hit = pat.match(line.strip().replace("*", ""))
            if not hit:
                continue
            label = hit.group(1).strip()
            nums = tuple(int(hit.group(i).replace(",", "")) for i in (2, 3, 4))
            for prefix, key in label_map:
                if label.startswith(prefix):
                    prose_seen[key] += 1
                    if nums != expect_tbl[key]:
                        prose_bad.append((doc, label, nums, expect_tbl[key]))
                    break
            else:
                mm = re.match(r"^RH0(\d)", label)
                if mm:
                    hint = "RH0" + mm.group(1)
                    if (nums[0], nums[2]) != (hint_ready.get(hint), hint_block.get(hint, 0)):
                        prose_bad.append((doc, label, nums,
                                          (hint_ready.get(hint), hint_block.get(hint, 0))))
    check("B13", "两份说明文档的资格表/风险表数字与实算一致",
          not prose_bad and prose_seen["TOTAL"] == 2 and prose_seen["SIGNAL_L3"] == 2,
          {"violations": prose_bad, "table_rows_seen": dict(prose_seen)})

    ok = all(c["pass"] for c in CHECKS)
    out = {
        "artifact": "S05_STEP_B_SELF_CHECK",
        "generated_at": now,
        "plan_version": "20261026_collection_first_v2",
        "author": "WorkBuddy AI",
        "review_nature": "SELF_CHECK",
        "decision": "SELF_CHECK_PASS_WITH_LIMITS" if ok else "SELF_CHECK_FAIL",
        "checks": CHECKS,
        "checks_passed": "%d/%d" % (sum(1 for c in CHECKS if c["pass"]), len(CHECKS)),
        "blocking_failures": [c["id"] for c in CHECKS if not c["pass"]],
        "release_S05": False,
        "release_note": "自检不等同独立复核；S05 正式运行须新增明确 release_S05 记录。",
        "limits": [
            "未回读 PDF 原文；ELIGIBLE_FOR_S05 只表示结构化证据链齐备。",
            "S04 的 M08 依赖按 {t, t-1y} 冻结展开；S05 侧按公式取 t，差异已在合同登记并提交门审。",
            "差额表只覆盖 278 家拟消费字段，不是全池来源验收。",
            "851 行派生毛利率按父键页码追溯（VIA_PARENT）：若门审要求派生值自身页码，M04 全线 HOLD、RH05 归零，且 148 家的 M04 信号依赖同时失效。",
            "待核按行计 15、按格计 13：四会富仕 SZ:300852 的 FIN.REV.YTD / FIN.COST.YTD@20250930 各被两个指标共用，引用时必须点明口径。",
        ],
    }
    with open(os.path.join(HERE, "review.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(json.dumps({"checks_passed": out["checks_passed"], "decision": out["decision"],
                      "blocking": out["blocking_failures"]}, ensure_ascii=False))
    for c in CHECKS:
        if not c["pass"]:
            print("FAIL", c["id"], c["name"], json.dumps(c["detail"], ensure_ascii=False)[:400])
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
