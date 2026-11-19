#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""步骤B：拟定 S05 用途合同与来源采用差额（只读派生，不跑 S05）。

只核「拟实际消费」的字段：
  1) 278 受限候选已生效信号的 L3 依赖行（document_id + source_page + 非 HOLD）
  2) S05 质量检查要用的 5 个指标：M04(RH05) / M08(RH04) / M10(RH01) / M11(RH02) / M12(RH03)
  3) 低基数同口径绝对额确认行（只对 QUALIFIED_LOW_BASE_CONFIRMED 的信号）

不做：全池重新抽取、全池精读、企业深研、S05 正式计算、放行判断。
所有计数从实际输出派生，不手写。
"""
import csv
import gzip
import hashlib
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "runs", "issues", "S00", "errata_20261111_v5"))
import l2_core  # noqa: E402

FD = os.path.join(REPO, "runs", "issues", "S04", "completion_20261114", "final_delivery_20261116")
QUAL = os.path.join(REPO, "runs", "issues", "S04", "completion_20261114", "qualification_v3_20261115")
S00 = os.path.join(REPO, "runs", "issues", "S02", "hangcha_restated_20261101", "s00_v10", "s00_v10.csv.gz")
MASK = os.path.join(REPO, "runs/issues/S00/completion_20261114/remaining_scope_review_20261115",
                    "classification_v2/CE_admission_projection/execution",
                    "all_pool_metrics_source_aware_mask.csv")
COLL = os.path.join(REPO, "runs", "collection", "collection_index.csv")
RULES = os.path.join(REPO, "runs/issues/S01/screen_rules_v3_provenance_20261114.json")

HOLD = {"EXTRACTED_XCHECK_MISMATCH", "DERIVED_HOLD_UPSTREAM", "DERIVED_Q1_HOLD_UPSTREAM"}
QUALITY_METRICS = {"M10": "RH01", "M11": "RH02", "M12": "RH03", "M08": "RH04", "M04": "RH05"}
LOW_BASE_FIELDS = {"SG01": "FIN.REV.YTD", "SG04": "FIN.NPDEDT.YTD", "SG06": "FIN.NPDEDT.YTD",
                   "SG08": "FIN.OCF.YTD", "SG09": "FIN.NPDEDT.SQ"}

# 期间口径按冻结指标公式的 offset 直接登记（screen_rules_v3 metrics.fields），
# 不再一律套用 l2_core.periods_for 的 {t, t-1y}：
#   M08 = OCF.YTD(t)/NPP.YTD(t)，公式只需 t。
# S04 冻结资格复算用的是 l2_core 的 {t, t-1y} 展开（signal_dependency_members 里
# SG07 确实带 20250630 两行），属既有冻结口径；本轮不修改 S04，只在 S05 侧按公式
# 取期间，并把差异登记到合同与门审问题里。
METRIC_PERIODS = {
    "M01": ("t", "t-1y"), "M02": ("t", "t-4q"), "M03": ("t", "t-1q", "t-4q", "t-5q"),
    "M04": ("t", "t-1y"), "M05": ("t", "t-1y"), "M06": ("t", "t-1y"), "M07": ("t", "t-4q"),
    "M08": ("t",), "M09": ("t", "t-1y"), "M10": ("t", "t-1y"), "M11": ("t", "t-1y"),
    "M12": ("t", "t-1y"),
}


def rows(p):
    with open(p, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def main():
    now = datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")
    out = HERE

    pass_rows = rows(os.path.join(FD, "reviewed_view", "tight_pass.csv"))
    observe_rows = rows(os.path.join(FD, "reviewed_view", "tight_observe.csv"))
    log_rows = rows(os.path.join(FD, "reviewed_view", "tight_decision_log.csv"))
    dep_rows = rows(os.path.join(QUAL, "signal_dependency_members.csv"))
    reason_rows = rows(os.path.join(QUAL, "signal_reason_map.csv"))
    dispute_rows = rows(os.path.join(QUAL, "dispute_member_map.csv"))
    accepted_rows = rows(os.path.join(QUAL, "accepted_dispositions.csv"))
    mask_rows = rows(MASK)

    cand = {r["security_id"]: r for r in pass_rows}

    s00 = {}
    with gzip.open(S00, "rt", encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            if r["security_id"] in cand:
                s00[(r["security_id"], r["field_id"], r["period_key"])] = r

    coll = {}
    for r in rows(COLL):
        coll.setdefault(r["document_id"], r)

    open_disputes = defaultdict(list)
    for r in dispute_rows:
        if r["open_at_replay"] == "YES":
            open_disputes[(r["security_id"], r["field_id"], r["period_key"])].append(
                (r["dispute_id"], r["ledger"], r["meta_field"]))
    accepted = defaultdict(list)
    for r in accepted_rows:
        accepted[(r["security_id"], r["field_id"], r["period_key"])].append(r["dispute_id"])

    mstat = {}
    for r in mask_rows:
        if r["security_id"] in cand:
            mstat[(r["security_id"], r["metric_id"])] = r

    def status_of(sid):
        def f(fld, pk):
            row = s00.get((sid, fld, pk))
            return row["status"] if row else ""
        return f

    def offset_period(anchor, off):
        if off == "t":
            return anchor
        if off == "t-1y":
            return l2_core.prev_year(anchor)
        if off == "t-4q":
            return l2_core.prev_year(anchor)
        if off == "t-1q":
            return l2_core.prev_quarter(anchor)
        if off == "t-5q":
            return l2_core.prev_year(l2_core.prev_quarter(anchor))
        raise ValueError(off)

    def deps_formula(metric, anchor, st):
        """按冻结指标公式的 offset 取期间，再按 l2_core.expand 展开派生父键。"""
        out = set()
        for fld in l2_core.METRIC_FIELDS[metric]:
            for off in METRIC_PERIODS[metric]:
                out |= l2_core.expand(fld, offset_period(anchor, off), st)
        return out

    delta = []

    def resolve_page_evidence(sid, field, pk):
        """返回 (mode, parents_missing, parents)。
        DIRECT     : 行自身有 source_page。
        VIA_PARENT : 派生值无自身页码，但实际父键行都有页码（派生字段经父键追溯）。
        NONE       : 两者都不成立。
        """
        row = s00.get((sid, field, pk))
        if row is None:
            return "NONE", [], []
        if row["source_page"]:
            return "DIRECT", [], []
        if row["status"].startswith("DERIVED"):
            st = status_of(sid)
            keys = sorted(l2_core.expand(field, pk, st) - {(field, pk)})
            missing = []
            for (f2, p2) in keys:
                r2 = s00.get((sid, f2, p2))
                if r2 is None or not r2["source_page"]:
                    missing.append("%s@%s" % (f2, p2))
            parents = ["%s@%s" % k for k in keys]
            if keys and not missing:
                return "VIA_PARENT", [], parents
            return "NONE", missing, parents
        return "NONE", [], []

    def judge_cell(sid, metric, field, pk, role, consumption):
        """唯一的单格判定入口：三类消费共用，避免同一判据散落在多个调用点。"""
        row = s00.get((sid, field, pk))
        od = open_disputes.get((sid, field, pk), [])
        acc = accepted.get((sid, field, pk), [])
        od_ids = [d[0] for d in od]
        unresolved = [d for d in od_ids if d not in acc]
        mode, parents_missing, parents = resolve_page_evidence(sid, field, pk)
        if row is None:
            cls, reason = "PENDING_MISSING_INPUT", "S00 无该行（不填 0、不当恶化）"
        elif row["status"] in HOLD:
            cls, reason = "PENDING_HOLD_STATUS", "输入行 status 属 hold，不得参与改善/恶化判断"
        elif mode == "NONE":
            cls = "PENDING_NO_PAGE_EVIDENCE"
            reason = ("缺 source_page 且父键页码不全: " + ";".join(parents_missing[:4])
                      if parents_missing else "缺 document_id 或 source_page")
        elif not row["document_id"]:
            cls, reason = "PENDING_NO_PAGE_EVIDENCE", "缺 document_id"
        elif row["consolidation_scope"] != "CONSOLIDATED":
            cls, reason = "PENDING_SCOPE_NOT_CONSOLIDATED", "非合并口径，不得混比"
        elif row["restatement_flag"] == "RESTATEMENT_INDICATED_NEEDS_REVIEW":
            cls, reason = "PENDING_Q06_RESTATEMENT", "Q06 未决重述，跨期指标不可用"
        elif unresolved:
            cls, reason = "PENDING_OPEN_DISPUTE", "存在未采用处置的开放争议"
        elif od_ids:
            cls = "S04_ONLY_REQUIRES_S05_RECHECK"
            reason = "该格仅凭 839 项精确处置/语言前提用于 S04，S05 质量采用需回页复核"
        else:
            cls, reason = "ELIGIBLE_FOR_S05", ""
        l3_ok = "YES" if (row is not None and row["document_id"] and row["status"] not in HOLD
                          and mode in ("DIRECT", "VIA_PARENT")) else "NO"
        c = coll.get(row["document_id"], {}) if row else {}
        delta.append({
            "security_id": sid,
            "stock_name": cand[sid]["stock_name"],
            "anchor_period": cand[sid]["anchor_period"],
            "anchor_period_type": cand[sid]["anchor_period_type"],
            "pool_role": "PRIMARY_CHECK_POOL_LIMITED_CANDIDATE",
            "consumption_class": consumption,
            "metric_id": metric,
            "field_id": field,
            "period_key": pk,
            "period_role": role,
            "value_cny": row["value_cny"] if row else "",
            "actual_status": row["status"] if row else "ROW_ABSENT",
            "document_id": row["document_id"] if row else "",
            "source_page": row["source_page"] if row else "",
            "page_evidence_mode": mode,
            "page_evidence_parents": ";".join(parents),
            "collection_slot": c.get("slot_id", ""),
            "collection_sha256": c.get("sha256", ""),
            "consolidation_scope": row["consolidation_scope"] if row else "",
            "currency": row["currency"] if row else "",
            "restatement_flag": row["restatement_flag"] if row else "",
            "q06_flag": "YES" if (row and row["restatement_flag"] == "RESTATEMENT_INDICATED_NEEDS_REVIEW") else "NO",
            "open_dispute_ids": ";".join(od_ids),
            "accepted_disposition_ids": ";".join(acc),
            "l3_evidence_ok": l3_ok,
            "s05_use_class": cls,
            "blocking_reason": reason,
        })
        return cls

    # ---------- 1) 信号 L3 依赖（278 家已生效信号） ----------
    for r in dep_rows:
        sid = r["security_id"]
        if sid not in cand or not r["signal_effective_status"].startswith("QUALIFIED"):
            continue
        judge_cell(sid, r["metric_id"], r["field_id"], r["period_key"], "SIGNAL_DEP", "SIGNAL_L3")

    # ---------- 2) 质量检查指标依赖（M04/M08/M10/M11/M12） ----------
    quality_metric_verdict = {}
    for sid, crow in cand.items():
        anchor = crow["anchor_period"]
        st = status_of(sid)
        for metric, rh in QUALITY_METRICS.items():
            mrow = mstat.get((sid, metric))
            mstatus = mrow["metric_status"] if mrow else "MISSING"
            if mstatus == "NOT_APPLICABLE":
                quality_metric_verdict[(sid, metric)] = {
                    "metric_status": mstatus, "risk_hint": rh,
                    "l3": "L3_NOT_APPLICABLE", "s05": "NOT_APPLICABLE_METRIC",
                    "cells": 0, "blocking": "经济事实/模式不适用，不填 0、不当无风险",
                }
                continue
            keys = sorted(deps_formula(metric, anchor, st))
            cls_list = []
            for (field, pk) in keys:
                role = "t" if pk == anchor else ("t-1y" if pk == l2_core.prev_year(anchor) else "other")
                cls_list.append(judge_cell(sid, metric, field, pk, role, "QUALITY_RH"))
            n = len(cls_list)
            if n == 0:
                verdict = "PENDING_MISSING_INPUT"
            elif all(c == "ELIGIBLE_FOR_S05" for c in cls_list):
                verdict = "ELIGIBLE_FOR_S05"
            elif any(c.startswith("PENDING") for c in cls_list):
                verdict = "PENDING"
            else:
                verdict = "S04_ONLY_REQUIRES_S05_RECHECK"
            cells = [d for d in delta if d["security_id"] == sid and d["metric_id"] == metric
                     and d["consumption_class"] == "QUALITY_RH"]
            quality_metric_verdict[(sid, metric)] = {
                "metric_status": mstatus, "risk_hint": rh,
                "l3": "L3_QUALITY_PASS" if all(d["l3_evidence_ok"] == "YES" for d in cells) else "L3_QUALITY_HOLD",
                "s05": verdict, "cells": n,
                "blocking": "" if verdict == "ELIGIBLE_FOR_S05" else ";".join(
                    sorted({d["s05_use_class"] for d in cells if d["s05_use_class"] != "ELIGIBLE_FOR_S05"})),
            }

    # ---------- 3) 低基数同口径绝对额确认行 ----------
    lb_rows = 0
    for r in reason_rows:
        sid = r["security_id"]
        if sid not in cand or r["effective_signal"] != "YES":
            continue
        if r["effective_status"] != "QUALIFIED_LOW_BASE_CONFIRMED":
            continue
        detail = json.loads(r["low_base_detail_json"] or "{}")
        field = detail.get("field") or LOW_BASE_FIELDS.get(r["signal_id"], "")
        if not field:
            continue
        anchor = cand[sid]["anchor_period"]
        if detail.get("basis") == "SQ":
            pks = [anchor, l2_core.prev_quarter(l2_core.prev_quarter(l2_core.prev_quarter(
                l2_core.prev_quarter(anchor))))]
        else:
            pks = [anchor, l2_core.prev_year(anchor)]
        for pk in pks:
            judge_cell(sid, r["metric_id"], field, pk,
                       "t" if pk == anchor else "t-1y", "LOW_BASE_CONFIRM")
            lb_rows += 1

    # ---------- 写 delta ----------
    delta.sort(key=lambda d: (d["security_id"], d["consumption_class"], d["metric_id"],
                              d["field_id"], d["period_key"]))
    dcols = list(delta[0].keys())
    with open(os.path.join(out, "s05_source_eligibility_delta.csv"), "w",
              encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=dcols)
        w.writeheader()
        for d in delta:
            w.writerow(d)

    # ---------- 目标分配 ----------
    guards = {}
    for r in log_rows:
        sid = r["security_id"]
        g = []
        if r["cutoff_isolated"].upper() == "YES":
            g.append("CUTOFF_AFTER_20261025")
        if r["anchor_reselection_pending"].upper() == "YES":
            g.append("ANCHOR_RESELECTION_PENDING")
        if r["project_mode_source_unknown"].upper() == "YES":
            g.append("PROJECT_MODE_UNKNOWN")
        if r["quality_source_state"] == "PENDING_CE_SOURCE":
            g.append("CE_QUALITY_SOURCE_PENDING")
        if sid in ("SH:688320", "SH:688518"):
            g.append("HCC_LIWIN_HOLD")
        if g:
            guards[sid] = g
    with open(os.path.join(out, "s05_target_assignment.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["security_id", "stock_name", "l2_decision", "anchor_period",
                    "s05_role", "guard_flags", "reentry_or_note"])
        for r in log_rows:
            sid = r["security_id"]
            if sid in cand:
                role = "PRIMARY_CHECK_POOL"
                note = "278 受限候选；S05 质量检查拟在此池内执行，不代表业务或投资候选"
            elif r["l2_decision"] == "HOLD_FOR_DATA":
                role, note = "OBSERVE_HOLD_FOR_DATA", "缺数据/待核；不因 S05 被淘汰，补齐后重进"
            elif r["l2_decision"] == "NOT_SHORTLISTED":
                role, note = "OBSERVE_NOT_SHORTLISTED", "当前未入选；S07 偏差检查样本，不在 S05 主池"
            elif r["l2_decision"] == "L2_NOT_IN_SCOPE":
                role, note = "OBSERVE_OUT_OF_SCOPE", "不在本次 L2 范围；不解释为质量差"
            elif r["l2_decision"] == "WATCH_AFTER_CUTOFF":
                role, note = "GUARD_CUTOFF_ISOLATED", "截止日后披露；仅增量版本重进，不用早期报告回退"
            elif r["l2_decision"] == "PENDING_ANCHOR_RESELECTION":
                role, note = "GUARD_ANCHOR_PENDING", "锚点待重选；版本化定锚与受影响链重算前隔离"
            else:
                role, note = "UNKNOWN_ROLE", ""
            w.writerow([sid, r["stock_name"], r["l2_decision"], r["anchor_period"],
                        role, ";".join(guards.get(sid, [])), note])

    # ---------- 结转登记 ----------
    carry = []
    for sid in ["SZ:000801", "SZ:000967", "SZ:000988", "SZ:001208", "SZ:001311", "SZ:002035",
                "SZ:002171", "SZ:002245", "SZ:002284", "SZ:002530", "SZ:002705", "SZ:002765",
                "SZ:002801", "SZ:300611", "SZ:301584"]:
        carry.append([sid, "CE_QUALITY_SOURCE_PENDING", "15家质量来源未知之一",
                      "M10/M11/M12 质量值不得用于 S05；RH01/RH02/RH03 记 UNKNOWN",
                      "独立原页核证 48 条源引用边后解除；不得按公司广播"])
    for ntn, member in [("NTN-cc7ef7c13603f88f39ae", "SH:688800|FIN.OCF.SQ|20250630"),
                        ("NTN-8537b4150e72f0731029", "SH:688800|FIN.OCF.YTD|20250630"),
                        ("NTN-d5eed7612dbcc43fc1d2", "SH:688800|FIN.OCF.YTD|20260630"),
                        ("NTN-475938521289726f8126", "SH:600939|FIN.GROSSMARGIN.PCT|20250630"),
                        ("NTN-319659864c5b8c7f57b1", "SH:600939|FIN.GROSSMARGIN.PCT|20260630"),
                        ("NTN-6015198c1920296046a8", "SH:601717|FIN.GROSSMARGIN.PCT|20250630"),
                        ("NTN-0e7a33418221fa6b96d6", "SH:601717|FIN.GROSSMARGIN.PCT|20260630"),
                        ("NTN-fbb13c8ee722e1ee5121", "SH:603350|FIN.OCF.SQ|20260630")]:
        carry.append([member.split("|")[0], "HELD_PARENT_PROPOSAL_UNADOPTED", ntn + " → " + member,
                      "仅 SELF_CHECK 准备，未采用、非有效；不得计入任何维度或质量结论",
                      "独立父期/版本/范围兼容核证并采用后才解除"])
    carry.append(["SH:688320", "HCC_NPP_DISPUTE_OPEN", "D-a3a9ea277080",
                  "UPDATE 终态 EXTRACTED_XCHECK_MISMATCH 与 B 的 EXTRACTED 不符；SG07 仍阻断",
                  "争议闭合后重算该信号；不得称 B 仍为 Xcheck 或全公司警告全清"])
    carry.append(["SH:688518", "HCC_LIWIN_HOLD", "联赢激光仍 HOLD_FOR_DATA，0 有效信号、9 条待核",
                  "已有精确更正不得扩成全公司清洁", "残余重述/比较/父链争议闭合后重进"])
    carry.append(["SZ:002083", "ANCHOR_RESELECTION_PENDING", "孚日股份锚点待重选",
                  "无版本化定锚与受影响链重算前保持隔离", "定锚版本化 + 受影响链重算"])
    for sid, name in [("SH:603448", "天博智能"), ("SH:688836", "宇树科技"),
                      ("SZ:301348", "蓝箭电子"), ("SZ:301699", "洛轴股份")]:
        carry.append([sid, "CUTOFF_AFTER_20261025", name + " 截止日后披露",
                      "保持 WATCH_AFTER_CUTOFF，不用早期报告回退规避时间隔离",
                      "增量版本按新披露期重进"])
    for sid, name in [("SZ:000988", "华工科技"), ("SZ:001208", "华菱线缆"), ("SZ:002530", "金财互联")]:
        carry.append([sid, "PROJECT_MODE_UNKNOWN", name + " 项目模式 UNKNOWN",
                      "RH02 消失只表示来源待核，不证明无存货风险；不得默认非项目制",
                      "合同资产/资产或营收比例的证据补齐后判定模式"])
    with open(os.path.join(out, "carryover_register.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["security_id", "carryover_type", "item", "effect_on_s05", "release_condition"])
        for c in carry:
            w.writerow(c)

    # ---------- 有界核证队列 ----------
    q = []
    seen = set()
    for d in delta:
        if not d["s05_use_class"].startswith("PENDING"):
            continue
        key = (d["security_id"], d["field_id"], d["period_key"], d["s05_use_class"])
        if key in seen:
            continue
        seen.add(key)
        q.append([d["security_id"], d["stock_name"], d["metric_id"], d["consumption_class"],
                  d["field_id"], d["period_key"], d["document_id"], d["source_page"],
                  d["actual_status"], d["s05_use_class"], d["blocking_reason"]])
    with open(os.path.join(out, "bounded_source_verification_queue.csv"), "w",
              encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["security_id", "stock_name", "metric_id", "consumption_class", "field_id",
                    "period_key", "document_id", "source_page", "actual_status",
                    "s05_use_class", "blocking_reason"])
        for r in q:
            w.writerow(r)

    # ---------- 计数（全部从输出派生） ----------
    cls_counter = Counter(d["s05_use_class"] for d in delta)
    cons_counter = Counter(d["consumption_class"] for d in delta)
    page_counter = Counter(d["page_evidence_mode"] for d in delta)
    per_company_blocked = Counter(d["security_id"] for d in delta
                                  if d["s05_use_class"].startswith("PENDING"))
    quality_verdict_counter = Counter(v["s05"] for v in quality_metric_verdict.values())
    l3_counter = Counter(v["l3"] for v in quality_metric_verdict.values())
    rh_ready = Counter()
    rh_blocked = Counter()
    for (sid, metric), v in quality_metric_verdict.items():
        if v["s05"] == "ELIGIBLE_FOR_S05":
            rh_ready[v["risk_hint"]] += 1
        elif v["s05"] == "PENDING":
            rh_blocked[v["risk_hint"]] += 1

    contract = {
        "contract_id": "S05_INPUT_CONTRACT_DRAFT_20261119_V1",
        "status": "DRAFT_FOR_GATE_REVIEW_NOT_EFFECTIVE",
        "created_at": now,
        "plan_version": "20261026_collection_first_v2",
        "issue": "S05 / #40",
        "author": "WorkBuddy AI",
        "review_nature": "SELF_CHECK",
        "release_S05": False,
        "release_note": "本文件是待门审草案；S05 正式运行须由独立复核写出明确 release_S05 记录，自检/归档/issue 关闭均不替代。",
        "basis": {
            "s04_formal_review": "runs/issues/S04/completion_20261114/final_delivery_20261116/review.json",
            "s04_peer_review": "runs/issues/S04/completion_20261114/final_peer_review_20261116/peer_review.json",
            "s00_source_supplement": "runs/issues/S00/completion_20261114/formal_gate_review_20261115/review.json",
            "qualification_contract": "runs/issues/S04/completion_20261114/qualification_v3_20261115/scope_contract.json",
            "governing_rule": "runs/issues/S00/errata_20261111_v5/codex_ruling_round5.md §9 Q2",
            "rules_version": "S01_SCREEN_RULES_V3_PROVENANCE_20261114",
            "rules_sha256": sha256_file(RULES),
            "knowledge_as_of": "2026-10-25",
            "authoritative_B": "runs/issues/S02/hangcha_restated_20261101/s00_v10/s00_v10.csv.gz",
            "authoritative_B_sha256": sha256_file(S00),
            "methodology_decision": "METHOD_20261107_LEADING_INDICATORS",
        },
        "pools": {
            "primary_check_pool": {
                "definition": "S04 冻结交付 tight_pass 的 278 家 SHORTLIST_CANDIDATE_LIMITED",
                "companies": len(cand),
                "role": "S05 质量检查拟执行池",
                "not_implied": "不是机器人业务确认、不是投资候选、不等于全部字段合格",
            },
            "observe_only": {
                "definition": "tight_observe 776 家",
                "companies": len(observe_rows),
                "sub_pools": dict(Counter(r["l2_decision"] for r in observe_rows)),
                "role": "保留观察与追踪入口；不因 S05 被淘汰；不增补进主池",
            },
            "hard_guards": {
                "cutoff_after_20261025": 4,
                "anchor_reselection_pending": 1,
                "project_mode_unknown": 3,
                "ce_quality_source_pending": 15,
                "hcc_liwin_hold": 2,
                "held_parent_proposals_unadopted": 8,
            },
        },
        "consumption_model": {
            "note": "只核拟实际消费字段；不重启全池抽取/精读/企业深研。",
            "classes": {
                "SIGNAL_L3": "278 家已生效信号的依赖行（L3 证据闸门）",
                "QUALITY_RH": "S05 风险提示所用指标依赖行：M10→RH01、M11→RH02、M12→RH03、M08→RH04、M04→RH05",
                "LOW_BASE_CONFIRM": "低基数同口径绝对额确认行（仅 QUALIFIED_LOW_BASE_CONFIRMED 信号）",
            },
            "not_consumed_in_s05": [
                "合同负债 / 在手订单 / 在建工程（按 METHOD_20261107 留在 S06 与筛后核验）",
                "Q09 一次性损益的新判定（本轮只登记既有标记，不新判）",
                "任何机器人业务、订单、客户、估值字段",
            ],
        },
        "eligibility_rules": {
            "L3_frozen_rule": "所用每个指标须有 document_id + source_page + 非 HOLD 状态；否则 QUALITY_HOLD。本草案不改该规则。",
            "page_evidence": "派生值无自身页码时，按实际父键行页码追溯（VIA_PARENT）；父键页码不全则仍判 PENDING_NO_PAGE_EVIDENCE。",
            "s05_use_classes": {
                "ELIGIBLE_FOR_S05": "行存在、status 属 usable、页码证据齐备（自身或父键）、合并口径、无 Q06、无开放争议",
                "S04_ONLY_REQUIRES_S05_RECHECK": "该格仅凭 839 项精确处置或 5 条语言前提用于 S04；S05 质量采用需回页复核",
                "PENDING_MISSING_INPUT": "S00 无该行；不填 0、不当恶化",
                "PENDING_HOLD_STATUS": "输入行 status 属 hold；不参与改善/恶化",
                "PENDING_NO_PAGE_EVIDENCE": "缺 document_id 或 source_page，且父键页码不全",
                "PENDING_SCOPE_NOT_CONSOLIDATED": "非合并口径，不得混比",
                "PENDING_Q06_RESTATEMENT": "Q06 未决重述，跨期指标不可用",
                "PENDING_OPEN_DISPUTE": "存在未采用处置的开放争议",
                "NOT_APPLICABLE_METRIC": "经济事实/模式不适用（如项目制不看存货天数），不填 0、不当无风险",
            },
            "no_threshold_or_cutoff_change": True,
        },
        "routing": {
            "missing": "MISSING，不填 0，不当恶化，进观察与追踪入口",
            "not_applicable": "保留 NA 并注明依据（项目制/经济事实），不当作已通过",
            "project_mode_unknown": "不默认非项目制；RH02 记 UNKNOWN，不当作无风险",
            "scope_change": "SCOPE_CHANGE / STRUCTURAL_BREAK 不得计入，路由待核",
            "low_base": "仅按 low_base_confirmation 同口径绝对额同向确认（增量 ≥1,000 万元）；无映射信号记 NO_CONFIRM_RULE",
            "stale_period": "标 STALE_PERIOD，横截面分层，同比结论不受影响",
            "unknown_is_not_zero": True,
        },
        "measured": {
            "delta_rows": len(delta),
            "by_consumption_class": dict(cons_counter),
            "by_use_class": dict(cls_counter),
            "by_page_evidence_mode": dict(page_counter),
            "quality_metric_verdicts": len(quality_metric_verdict),
            "quality_metric_by_s05_class": dict(quality_verdict_counter),
            "quality_metric_by_l3": dict(l3_counter),
            "risk_hints_ready_by_company": dict(rh_ready),
            "risk_hints_blocked_by_company": dict(rh_blocked),
            "companies_with_any_pending_consumed_cell": len(per_company_blocked),
            "bounded_verification_queue_rows": len(q),
            "low_base_confirmation_rows": lb_rows,
        },
        "outputs": {
            "target_assignment": "s05_target_assignment.csv",
            "source_eligibility_delta": "s05_source_eligibility_delta.csv",
            "carryover_register": "carryover_register.csv",
            "bounded_verification_queue": "bounded_source_verification_queue.csv",
        },
        "open_questions_for_gate": [
            "是否允许 #40 在本草案输入合同下开工？允许的名单、字段与输出范围是什么？",
            "仅限 S04 采用的来源（839 精确处置 / 5 条语言前提）对 S05 有哪些额外核证要求？哪些值只能 QUALITY_HOLD？",
            "非消费争议是否继续按 Q2 有界挂账？哪些实际消费争议必须先核证？",
            "#53 继续开放的残余范围如何与后续 #40 执行占用分开？",
        ],
        "limits": [
            "本草案是自检产物，不是独立验收，也不是 S05 放行。",
            "未回读 PDF 原文；ELIGIBLE_FOR_S05 只表示结构化证据链齐备，不等于逐页复核。",
            "278 家为财务信号受限候选，不判断机器人业务，也不是投资名单。",
            "未改冻结阈值、截止日、B、S01 v3 规则或任何旧验收状态。",
        ],
    }
    with open(os.path.join(out, "s05_input_contract_draft.json"), "w", encoding="utf-8") as f:
        json.dump(contract, f, ensure_ascii=False, indent=2)

    print(json.dumps({
        "delta_rows": len(delta),
        "by_consumption_class": dict(cons_counter),
        "by_use_class": dict(cls_counter),
        "by_page_mode": dict(page_counter),
        "quality_by_s05": dict(quality_verdict_counter),
        "quality_by_l3": dict(l3_counter),
        "rh_ready": dict(rh_ready),
        "rh_blocked": dict(rh_blocked),
        "companies_with_pending": len(per_company_blocked),
        "queue_rows": len(q),
        "low_base_rows": lb_rows,
    }, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
