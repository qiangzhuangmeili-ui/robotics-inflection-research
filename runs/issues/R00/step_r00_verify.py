#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R00 / #44 / #57 独立校验（完全离线，不信任构建器布尔值）。

从原始 Git 跟踪输入从零重算，独立校验交付表与 manifest.json / review.json。

校验内容
--------
V01 固定 5 家名单与 release_20261126.json、S08 冻结 TIER_1 100% 一致（零增删零换人）
V02 knowledge_as_of=2026-10-25，全部引用披露日 <= 截止日，非 9M 公司不混入三季报
V03 锚定期严格分离（4 家 H1 20260630 + 1 家 9M 20260930 雷赛），与 S08/S05 对齐
V04 历史复用边界：五家保留 legacy_sources，legacy_auto_promoted=False
V05 质量预警排查完备：埃斯顿 RH04+RH06、雷赛 RH04+RH02、双环 RH02、鼎智 RH02 均有原文页码引文
V06 口径防污染：未知项齐备、混合口径明示、参股不并表（酷卓 / 鼎智五家参股）
V07 逐字短引文与物理页码完整（5 家、每家 >= 10 条、1-based page > 0、doc 属于已读来源）
V08 manifest.json 全部输入/输出 sha256 与根摘要精确匹配，全部纯 LF 无 BOM
V09 review.json 性质为 SELF_CHECK，decision 与实测一致，不越权放行 R01/R03，不触碰 #53
V10 固定时间戳连续两次构建逐字节一致且与仓库交付同步
V11 活体负例篡改测试（--negative-test）：3 个独立篡改场景，均须退出码 1

用法
----
    R00_FIXED_NOW=2026-11-26T19:20:00+08:00 py runs/issues/R00/step_r00_verify.py
    py runs/issues/R00/step_r00_verify.py --negative-test
    py runs/issues/R00/step_r00_verify.py --root <临时树> --skip-replay
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
NOW = os.environ.get("R00_FIXED_NOW") or "2026-11-26T19:20:00+08:00"
CUTOFF = "2026-10-25"
BATCH_ID = "R00_BATCH_01"
CHILD_ISSUE = 57

INPUTS = [
    "runs/issues/S08/business_verification_candidates.csv",
    "runs/issues/S08/candidate_reuse_map.csv",
    "runs/issues/S08/acceptance_s08_20261126.json",
    "runs/issues/R02/acceptance_r02_20261126.json",
    "runs/issues/S05/quality_flags.csv",
    "runs/issues/S05/quality_decision_log.csv",
    "runs/issues/R00/release_20261126.json",
    "runs/issues/R00/inputs_batch01/ai1_300607_002747_business_review.yaml",
    "runs/issues/R00/inputs_batch01/ai1_300607_002747_evidence_notes.md",
    "runs/issues/R00/inputs_batch01/ai1_manifest.json",
    "runs/issues/R00/inputs_batch01/ai2_002472_002979_business_review.yaml",
    "runs/issues/R00/inputs_batch01/codebuddy_920593_draft.json",
    "runs/issues/R00/inputs_batch01/codebuddy_920593_draft.md",
]

DELIVERABLES = ["business_batch_dispatch.csv", "business_review_register.csv",
                "batch01_evidence_quotes.csv", "child_issue_manifest.json", "handoff.md"]
SCRIPTS = ["step_r00_build.py", "step_r00_verify.py"]
MANIFEST_DELIVERABLES = DELIVERABLES + SCRIPTS
ALL_OUT = DELIVERABLES + ["review.json", "manifest.json"]

ALERT_KEY = {"RH04": "rh04_check", "RH06": "rh06_check", "RH02": "rh02_check"}
STATUS_TOKENS = ("TRIGGERED_CONFIRMED_BY_ORIGINAL", "PENDING_RESOLVED_REAL_BLANK")


# ------------------------------------------------------------ 独立读取

def rd_csv(p):
    with open(p, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def rd_json(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def exact_sha(p):
    b = p.read_bytes()
    return len(b), hashlib.sha256(b).hexdigest()


def canon_sha(p):
    b = p.read_bytes().replace(b"\r\n", b"\n")
    return len(b), hashlib.sha256(b).hexdigest()


def pages_in(text):
    out = []
    for m in re.finditer(r"物理页([\d/]+)", text or ""):
        out.extend(int(x) for x in m.group(1).split("/") if x)
    for m in re.finditer(r"第\s*(\d+)\s*页", text or ""):
        out.append(int(m.group(1)))
    for m in re.finditer(r"(?<![A-Za-z0-9])p(\d+)(?![0-9])", text or ""):
        out.append(int(m.group(1)))
    seen, res = set(), []
    for p in out:
        if p not in seen:
            seen.add(p)
            res.append(p)
    return res


def segment_of(summary, flag):
    """取 summary 中以 flag 开头、到下一个 RHxx: 之前的片段（不依赖分隔符）。"""
    i = summary.find(flag + ":")
    if i < 0:
        return ""
    ends = [summary.find(g + ":", i + 1) for g in
            ("RH01", "RH02", "RH03", "RH04", "RH05", "RH06", "RH07")]
    ends = [e for e in ends if e > 0]
    return summary[i:min(ends)] if ends else summary[i:]


def money(v):
    if v is None or v == "":
        return ""
    if isinstance(v, (int, float)):
        return "%.2f" % float(v)
    m = re.search(r"-?\d[\d,]*\.?\d*", str(v))
    if not m:
        return ""
    return "%.2f" % float(m.group(0).replace(",", ""))


class Ctx:
    """独立上下文：只读原始输入与交付物。"""

    def __init__(self, root: Path):
        self.root = root
        r = root
        self.cand = {x["security_id"]: x for x in rd_csv(r / INPUTS[0])}
        self.reuse = {x["security_id"]: x for x in rd_csv(r / INPUTS[1])}
        self.acc_s08 = rd_json(r / INPUTS[2])
        self.acc_r02 = rd_json(r / INPUTS[3])
        self.flags = rd_csv(r / INPUTS[4])
        self.log = {x["security_id"]: x for x in rd_csv(r / INPUTS[5])}
        self.release = rd_json(r / INPUTS[6])
        self.ai1_manifest = rd_json(r / INPUTS[9])
        self.cb = rd_json(r / INPUTS[11])

        ai1 = yaml.safe_load((r / INPUTS[7]).read_text(encoding="utf-8"))
        self.ai1 = {c["company"]["security_id"]: c["company"] for c in ai1["companies"]}
        self.ai2 = {}
        for doc in yaml.safe_load_all((r / INPUTS[10]).read_text(encoding="utf-8")):
            if isinstance(doc, dict) and "company" in doc:
                self.ai2[doc["company"]["security_id"]] = doc["company"]

        self.dispatch = rd_csv(r / "runs/issues/R00/business_batch_dispatch.csv")
        self.register = rd_csv(r / "runs/issues/R00/business_review_register.csv")
        self.quotes = rd_csv(r / "runs/issues/R00/batch01_evidence_quotes.csv")
        self.child = rd_json(r / "runs/issues/R00/child_issue_manifest.json")
        self.review = rd_json(r / "runs/issues/R00/review.json")
        self.manifest = rd_json(r / "runs/issues/R00/manifest.json")
        self.handoff = (r / "runs/issues/R00/handoff.md").read_text(encoding="utf-8")

        self.spec = self.release["child_issues"][0]
        self.order = [c["security_id"] for c in self.spec["companies"]]
        self.assigned = {c["security_id"]: c["assigned_to"] for c in self.spec["companies"]}
        self.tier1 = {s for s, x in self.cand.items()
                      if x["r00_priority_tier"].startswith("TIER_1")}
        self.anchor_s05 = {}
        for x in self.flags:
            self.anchor_s05.setdefault(x["security_id"], x["anchor_period"])

    # ---- 原始输入归一化（独立实现）
    def sources(self, sid):
        if sid in self.ai1:
            return [{"doc_id": s["doc_id"], "name": s["report_name"],
                     "date": s["disclosure_date"]} for s in self.ai1[sid]["sources_actually_read"]]
        if sid in self.ai2:
            return [{"doc_id": s["doc_id"], "name": s["report_name"],
                     "date": s["disclosure_date"]} for s in self.ai2[sid]["sources_actually_read"]]
        return [{"doc_id": s["document_id"], "name": s["title"],
                 "date": s["disclosure_date"]} for s in self.cb["sources_read"]]

    def raw_quotes(self, sid):
        if sid in self.ai1:
            return [(q["doc_id"], int(q["physical_page"]), q["verbatim_quote"])
                    for q in self.ai1[sid]["evidence_quotes"]]
        if sid in self.ai2:
            return [(q["doc_id"], int(q["physical_page"]), q["verbatim_quote"])
                    for q in self.ai2[sid]["evidence_quotes"]]
        return [(q["document_id"], int(q["page"]), q["quote"],
                 q.get("data_excerpt", "")) for q in self.cb["evidence_quotes"]]

    def alerts(self, sid):
        if sid in self.ai1:
            return dict(self.ai1[sid]["s05_alert_investigation"])
        if sid in self.ai2:
            return dict(self.ai2[sid]["s05_alert_investigation"])
        ca = self.cb["s05_alert_check"]["contract_asset"]
        return {"rh02_check": " ".join(str(v) for v in ca.values())}

    def entities(self, sid):
        """-> (consolidated names, excluded names)"""
        cons, exc = [], []
        if sid in self.ai1 or sid in self.ai2:
            src = (self.ai1.get(sid) or self.ai2.get(sid))["consolidated_entities"]
            for e in src:
                if "未并表" in e["role_in_robotics"] or "NOT_CONSOLIDATED" in e["consolidation_status"]:
                    exc.append(e["entity_name"])
                else:
                    cons.append(e["entity_name"])
        else:
            ce = self.cb["consolidated_entities"]
            cons = [s["name"] for s in ce["subsidiaries_10"]]
            exc = [p["name"] for p in ce["equity_participations_not_consolidated"]]
        return cons, exc

    def fy_total(self, sid):
        if sid in self.ai1:
            return money(self.ai1[sid]["revenue_breakdown"]["fy2025_total_rev_cny"])
        if sid in self.ai2:
            return money(self.ai2[sid]["revenue_breakdown"]["fy2025_total_rev_cny"])
        return money(self.cb["revenue_breakdown"]["fy2025"]["total_revenue_cny"])

    def anchor_total(self, sid):
        if sid in self.ai1:
            return money(self.ai1[sid]["revenue_breakdown"]["h1_2026_total_rev_cny"])
        if sid in self.ai2:
            return money(self.ai2[sid]["revenue_breakdown"]["anchor_total_rev_cny"])
        return money(self.cb["revenue_breakdown"]["h1_2026"]["total_revenue_cny"])

    def knowledge_as_of(self, sid):
        if sid in self.ai1:
            return self.ai1[sid]["knowledge_as_of"]
        if sid in self.ai2:
            return self.ai2[sid]["knowledge_as_of"]
        return self.cb["knowledge_as_of"]

    def input_anchor_hint(self, sid):
        """输入自报锚定期（用于与 S08 交叉核对）。"""
        if sid in self.ai1:
            return self.ai1[sid].get("knowledge_as_of") and "H1"
        if sid in self.ai2:
            return self.ai2[sid]["revenue_breakdown"].get("anchor_period", "")
        return self.cb["anchor_period"]


# ------------------------------------------------------------ 校验主体

def run_checks(ctx: Ctx, replay_res=None):
    checks, bad = [], []

    def add(cid, name, ok, detail):
        checks.append({"id": cid, "name": name, "result": "PASS" if ok else "FAIL", "detail": detail})
        if not ok:
            bad.append("%s %s: %s" % (cid, name, detail))

    reg_ids = [r["security_id"] for r in ctx.register]
    dis_ids = [r["security_id"] for r in ctx.dispatch]
    rel_ids = ctx.order

    # V01 固定名单
    name_ok = all(r["stock_name"] == ctx.cand[r["security_id"]]["stock_name"] for r in ctx.register)
    topic_ok = all(d["topic"] == next(c["topic"] for c in ctx.spec["companies"]
                                      if c["security_id"] == d["security_id"]) for d in ctx.dispatch)
    v01 = (reg_ids == rel_ids and dis_ids == rel_ids and len(set(rel_ids)) == 5
           and set(reg_ids) <= ctx.tier1 and name_ok and topic_ok
           and all(d["child_issue_number"] == str(CHILD_ISSUE) for d in ctx.dispatch))
    add("V01", "固定 5 家名单与 release/#57/S08 TIER_1 零增删零换人", v01,
        "release=%s register=%s dispatch=%s all_tier1=%s name_ok=%s topic_ok=%s" % (
            rel_ids, reg_ids, dis_ids, set(reg_ids) <= ctx.tier1, name_ok, topic_ok))

    # V02 知识截止日
    late, q3_bad, kas_bad, cnt_bad = [], [], [], []
    for r in ctx.register:
        sid = r["security_id"]
        if r["knowledge_as_of"] != CUTOFF:
            kas_bad.append("%s=%s" % (sid, r["knowledge_as_of"]))
        if ctx.knowledge_as_of(sid) != CUTOFF:
            kas_bad.append("%s:input=%s" % (sid, ctx.knowledge_as_of(sid)))
        srcs = ctx.sources(sid)
        if int(r["sources_verified_count"]) != len(srcs):
            cnt_bad.append("%s:%s!=%d" % (sid, r["sources_verified_count"], len(srcs)))
        for s in srcs:
            if s["date"] > CUTOFF:
                late.append("%s:%s@%s" % (sid, s["doc_id"], s["date"]))
            if ("三季" in s["name"] or "第三季度" in s["name"]) and sid != "SZ:002979":
                q3_bad.append("%s:%s" % (sid, s["doc_id"]))
    add("V02", "knowledge_as_of=2026-10-25、披露日<=截止日、非 9M 公司不混入三季报", 
        not late and not q3_bad and not kas_bad and not cnt_bad,
        "late=%s q3=%s kas=%s src_count=%s" % (late[:3], q3_bad, kas_bad, cnt_bad))

    # V03 锚定期分离
    reg_anchor = {r["security_id"]: r["anchor_period"] for r in ctx.register}
    dis_anchor = {r["security_id"]: r["anchor_period"] for r in ctx.dispatch}
    s08_anchor = {s: ctx.cand[s]["s05_anchor_period"] for s in ctx.order}
    hint_bad = []
    for sid in ctx.order:
        h = ctx.input_anchor_hint(sid)
        if sid == "SZ:002979" and h not in ("2026Q1-Q3", "20260930"):
            hint_bad.append("%s:input_hint=%s" % (sid, h))
        if sid != "SZ:002979" and h in ("2026Q1-Q3", "20260930"):
            hint_bad.append("%s:input_hint=%s" % (sid, h))
    v03 = (reg_anchor == dis_anchor == s08_anchor
           and all(ctx.anchor_s05.get(s) == s08_anchor[s] for s in ctx.order)
           and sum(1 for v in reg_anchor.values() if v == "20260630") == 4
           and sum(1 for v in reg_anchor.values() if v == "20260930") == 1
           and reg_anchor.get("SZ:002979") == "20260930"
           and not hint_bad)
    add("V03", "锚定期 4×H1(20260630)+1×9M(20260930 雷赛) 与 S08/S05/原始输入一致", v03,
        "register=%s dispatch=%s s08=%s s05=%s hint_bad=%s" % (
            reg_anchor, dis_anchor, s08_anchor,
            {s: ctx.anchor_s05.get(s) for s in ctx.order}, hint_bad))

    # V04 历史复用边界
    legacy_bad = []
    for sid in ctx.order:
        ru = ctx.reuse.get(sid)
        if not ru or not ru["legacy_sources"].strip():
            legacy_bad.append(sid + ":reuse_missing")
            continue
        if ru["auto_promoted"] != "False" or ctx.cand[sid]["legacy_auto_promoted"] != "False":
            legacy_bad.append(sid + ":auto_promoted")
        d = next(x for x in ctx.dispatch if x["security_id"] == sid)
        if d["legacy_sources"] != ctx.cand[sid]["legacy_sources"]:
            legacy_bad.append(sid + ":dispatch_legacy_mismatch")
        if d["legacy_auto_promoted"] != "False":
            legacy_bad.append(sid + ":dispatch_auto_promoted")
    add("V04", "五家均保留 legacy_sources 复用映射且 legacy_auto_promoted=False", not legacy_bad,
        "bad=%s" % legacy_bad)

    # V05 质量项排查完备
    miss = []
    qpages = {}
    for q in ctx.quotes:
        qpages.setdefault(q["security_id"], set()).add(int(q["physical_page"]))
    for sid in ctx.order:
        r = next(x for x in ctx.register if x["security_id"] == sid)
        summ = r["s05_alert_check_summary"]
        triggers = [x for x in ctx.cand[sid]["s05_rh_triggers"].split(";") if x]
        pending = [x for x in ctx.cand[sid]["s05_pending_flags"].split(";") if x]
        if triggers or pending:
            for f in triggers + pending:
                if f not in summ:
                    miss.append("%s:%s:absent" % (sid, f))
                    continue
                seg = segment_of(summ, f)
                if not any(t in seg for t in STATUS_TOKENS):
                    miss.append("%s:%s:no_status" % (sid, f))
                cited = set(pages_in(seg))
                if not cited:
                    miss.append("%s:%s:no_page" % (sid, f))
                elif not (cited & qpages.get(sid, set())):
                    miss.append("%s:%s:no_quote_on_cited_page" % (sid, f))
            # 原文核验记录必须存在
            if not any(str(v).strip() and str(v) != "NA"
                       for k, v in ctx.alerts(sid).items() if k in ALERT_KEY.values()):
                miss.append(sid + ":no_original_check_text")
    # 必须覆盖的四类组合（从 S08 重算，不读交付表）
    combos = {s: (ctx.cand[s]["s05_rh_triggers"], ctx.cand[s]["s05_pending_flags"]) for s in ctx.order}
    need = {"SZ:002747": ("RH04;RH06", ""), "SZ:002979": ("RH04", "RH02"),
            "SZ:002472": ("", "RH02"), "BJ:920593": ("", "RH02")}
    combo_ok = all(combos[k] == v for k, v in need.items())
    add("V05", "埃斯顿 RH04+RH06、雷赛 RH04+RH02、双环/鼎智 RH02 均有原文页码引文", 
        not miss and combo_ok, "miss=%s combos=%s" % (miss, combos))

    # V06 口径防污染
    contam = []
    for r in ctx.register:
        sid = r["security_id"]
        cons, exc = ctx.entities(sid)
        if not r["key_unknowns_and_limits"].strip():
            contam.append(sid + ":no_unknowns")
        if "非纯机器人" not in r["anchor_robot_related_line"]:
            contam.append(sid + ":no_mixed_caveat")
        if r["anchor_robot_related_line"].strip() == r["anchor_total_rev_cny"].strip():
            contam.append(sid + ":total_as_robot")
        if r["fy2025_total_rev_cny"] != ctx.fy_total(sid):
            contam.append("%s:fy_total(%s!=%s)" % (sid, r["fy2025_total_rev_cny"], ctx.fy_total(sid)))
        if r["anchor_total_rev_cny"] != ctx.anchor_total(sid):
            contam.append("%s:anchor_total(%s!=%s)" % (sid, r["anchor_total_rev_cny"], ctx.anchor_total(sid)))
        for n in cons:
            if n not in r["consolidated_robotics_entities"]:
                contam.append("%s:consolidated_missing:%s" % (sid, n))
        for n in exc:
            if n in r["consolidated_robotics_entities"]:
                contam.append("%s:participated_in_consolidated:%s" % (sid, n))
            if n not in r["non_consolidated_entities_excluded"]:
                contam.append("%s:excluded_missing:%s" % (sid, n))
    add("V06", "未知项齐备、混合口径明示、参股不并表、金额与原始输入一致", not contam,
        "contam=%s" % contam[:6])

    # V07 引文完整
    per, qbad, docbad = {}, [], []
    for sid in ctx.order:
        rows = [q for q in ctx.quotes if q["security_id"] == sid]
        per[sid] = len(rows)
        src_ids = {s["doc_id"] for s in ctx.sources(sid)}
        raw = ctx.raw_quotes(sid)
        for q in rows:
            if int(q["physical_page"]) <= 0 or not q["verbatim_quote"].strip() or not q["doc_id"].strip():
                qbad.append("%s:%s" % (sid, q["doc_id"]))
            if q["doc_id"] not in src_ids:
                docbad.append("%s:%s" % (sid, q["doc_id"]))
        # 条数与逐字对应
        if len(rows) != len(raw):
            qbad.append("%s:count(%d!=%d)" % (sid, len(rows), len(raw)))
            continue
        for q, rq in zip(rows, raw):
            doc, page, quote = rq[0], rq[1], rq[2]
            if q["doc_id"] != doc or int(q["physical_page"]) != page:
                qbad.append("%s:doc/page_mismatch" % sid)
                continue
            if not q["verbatim_quote"].startswith(quote):
                qbad.append("%s:quote_not_verbatim" % sid)
            if len(rq) == 4 and rq[3] and rq[3] not in q["verbatim_quote"]:
                qbad.append("%s:excerpt_missing" % sid)
    v07 = all(v >= 10 for v in per.values()) and not qbad and not docbad \
        and len(ctx.quotes) == sum(per.values())
    add("V07", "引文表覆盖 5 家、每家>=10 条、页码 1-based>0、逐字可回溯且 doc 属于已读来源",
        v07, "per=%s rows=%d qbad=%s docbad=%s" % (per, len(ctx.quotes), qbad[:4], docbad[:3]))

    # V08 manifest
    inp_bad, del_bad = [], []
    for d in ctx.manifest["inputs"]:
        n, s = canon_sha(ctx.root / d["path"])
        if n != d["bytes"] or s != d["sha256"]:
            inp_bad.append(d["path"])
    for d in ctx.manifest["deliverables"]:
        n, s = exact_sha(ctx.root / d["path"])
        if n != d["bytes"] or s != d["sha256"]:
            del_bad.append(d["path"])
    root = hashlib.sha256(
        "\n".join("%s:%s" % (d["path"], d["sha256"])
                  for d in sorted(ctx.manifest["deliverables"], key=lambda x: x["path"])).encode("utf-8")
    ).hexdigest()
    crlf = [f for f in DELIVERABLES + SCRIPTS if b"\r\n" in (ctx.root / "runs/issues/R00" / f).read_bytes()]
    bom = [f for f in DELIVERABLES + SCRIPTS
           if (ctx.root / "runs/issues/R00" / f).read_bytes().startswith(b"\xef\xbb\xbf")]
    manifest_ids = {d["path"] for d in ctx.manifest["deliverables"]}
    expect_ids = {"runs/issues/R00/" + f for f in MANIFEST_DELIVERABLES}
    add("V08", "manifest 输入/交付 sha256 与根摘要精确匹配，全部纯 LF 无 BOM",
        not inp_bad and not del_bad and root == ctx.manifest["manifest_root_digest"]
        and not crlf and not bom and manifest_ids == expect_ids
        and ctx.manifest["input_count"] == len(INPUTS)
        and ctx.manifest["deliverable_count"] == len(MANIFEST_DELIVERABLES)
        and ctx.manifest["fixed_now"] == NOW,
        "input_bad=%d deliv_bad=%d root_match=%s crlf=%s bom=%s ids_ok=%s fixed_now=%s" % (
            len(inp_bad), len(del_bad), root == ctx.manifest["manifest_root_digest"],
            crlf, bom, manifest_ids == expect_ids, ctx.manifest["fixed_now"]))

    # V09 review 性质与越权
    replay_ok = True if replay_res is None else replay_res[0]
    derived = "SELF_CHECK_PASS_WITH_LIMITS" if (not bad and not ctx.review["anomalies"] and replay_ok) \
        else "NOT_ACCEPTED_PENDING_FIX"
    rev = ctx.review
    v09 = (rev["review_nature"] == "SELF_CHECK" and rev["decision"] == derived
           and replay_ok
           and rev["R01_released"] is False and rev["R03_released"] is False
           and rev["R04_started"] is False and rev["issue_53_touched"] is False
           and rev["issue_53_status"] == "OPEN"
           and rev["independent_review_status"] == "PENDING_CODEX_INDEPENDENT_REVIEW"
           and ctx.release["guards"]["R01_released"] is False
           and ctx.release["guards"]["R03_released"] is False
           and ctx.release["guards"]["S00_errata_issue_53"] == "OPEN"
           and "SELF_CHECK" in ctx.handoff and "R01_released=false" in ctx.handoff)
    add("V09", "review/handoff 性质为 SELF_CHECK，不越权放行 R01/R03，不触碰 #53", v09,
        "review=%s derived=%s nature=%s r01=%s r03=%s issue53=%s replay_ok=%s" % (
            rev["decision"], derived, rev["review_nature"], rev["R01_released"],
            rev["R03_released"], rev["issue_53_status"], replay_ok))

    if replay_res is not None:
        ok, detail = replay_res
        checks.append({"id": "V11", "name": "固定时间戳连续两次构建逐字节一致且与仓库交付同步",
                       "result": "PASS" if ok else "FAIL", "detail": detail})
        if not ok:
            bad.append("V11 逐字节复现失败: " + detail)

    # 交付表结构
    v10 = (len(ctx.dispatch) == 5 and len(ctx.register) == 5
           and len(ctx.child["companies"]) == 5 and ctx.child["batch_size"] == 5
           and ctx.child["fixed_no_substitution"] is True
           and ctx.child["issue_number"] == CHILD_ISSUE
           and [c["security_id"] for c in ctx.child["companies"]] == ctx.order
           and all(c["legacy_auto_promoted"] is False for c in ctx.child["companies"]))
    add("V10", "dispatch/register 各 5 行，child_issue_manifest 固定名单与复用边界一致", v10,
        "dispatch=%d register=%d child=%d" % (len(ctx.dispatch), len(ctx.register),
                                              len(ctx.child["companies"])))
    return checks, bad


# ------------------------------------------------------------ 复现与负例

COPY = INPUTS + ["runs/issues/R00/" + s for s in SCRIPTS] + \
       ["runs/issues/R00/" + f for f in ALL_OUT]


def make_tree(dst: Path, root: Path):
    for rel in COPY:
        src = root / rel
        if not src.exists():
            continue
        tgt = dst / rel
        tgt.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, tgt)


def replay(root: Path):
    tmp = Path(tempfile.mkdtemp(prefix="r00_replay_"))
    try:
        make_tree(tmp, root)
        env = dict(os.environ, R00_FIXED_NOW=NOW)
        snaps = []
        for _ in range(2):
            p = subprocess.run([sys.executable, "runs/issues/R00/step_r00_build.py"],
                               cwd=str(tmp), env=env, capture_output=True, text=True)
            if p.returncode != 0:
                return False, "build rc=%d %s" % (p.returncode, (p.stdout + p.stderr)[-400:])
            snaps.append({f: exact_sha(tmp / "runs/issues/R00" / f)[1] for f in ALL_OUT})
        same = snaps[0] == snaps[1]
        repo = {f: exact_sha(root / "runs/issues/R00" / f)[1] for f in ALL_OUT}
        in_sync = repo == snaps[1]
        return same and in_sync, "twice_identical=%s repo_in_sync=%s" % (same, in_sync)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _tamper_disclosure_date(tmp: Path):
    p = tmp / INPUTS[10]
    txt = p.read_text(encoding="utf-8")
    new = txt.replace('disclosure_date: "2026-04-23"', 'disclosure_date: "2026-10-26"', 1)
    assert new != txt, "tamper target not found"
    p.write_bytes(new.encode("utf-8"))


def _tamper_auto_promoted(tmp: Path):
    p = tmp / INPUTS[0]
    rows = rd_csv(p)
    fields = list(rows[0].keys())
    hit = False
    for r in rows:
        if r["security_id"] == "BJ:920593" and not hit:
            r["legacy_auto_promoted"] = "True"
            hit = True
    assert hit, "tamper target not found"
    buf = []
    import io as _io
    s = _io.StringIO(newline="")
    w = csv.DictWriter(s, fieldnames=fields, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    p.write_bytes(s.getvalue().encode("utf-8"))


def _tamper_quote_page(tmp: Path):
    p = tmp / "runs/issues/R00/batch01_evidence_quotes.csv"
    rows = rd_csv(p)
    fields = list(rows[0].keys())
    rows[0]["physical_page"] = "0"
    import io as _io
    s = _io.StringIO(newline="")
    w = csv.DictWriter(s, fieldnames=fields, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    p.write_bytes(s.getvalue().encode("utf-8"))


def negative_test(root: Path):
    cases = [
        ("disclosure_date_2026-10-26", _tamper_disclosure_date, "V02"),
        ("legacy_auto_promoted=True", _tamper_auto_promoted, "V04"),
        ("physical_page=0", _tamper_quote_page, "V07"),
    ]
    results = []
    ok_all = True
    for name, fn, expect in cases:
        tmp = Path(tempfile.mkdtemp(prefix="r00_neg_"))
        try:
            make_tree(tmp, root)
            fn(tmp)
            p = subprocess.run([sys.executable, "runs/issues/R00/step_r00_verify.py",
                                "--root", str(tmp), "--skip-replay"],
                               cwd=str(tmp), env=dict(os.environ, R00_FIXED_NOW=NOW),
                               capture_output=True, text=True)
            detected = (p.returncode == 1 and ("[FAIL] " + expect) in p.stdout)
            results.append("%s->rc=%d,%s=%s" % (name, p.returncode, expect,
                                                "BLOCKED" if detected else "MISSED"))
            ok_all = ok_all and detected
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    return ok_all, "; ".join(results)


# ------------------------------------------------------------ main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(REPO))
    ap.add_argument("--skip-replay", action="store_true")
    ap.add_argument("--negative-test", action="store_true")
    args = ap.parse_args()
    root = Path(args.root).resolve()

    if args.negative_test:
        ok, detail = negative_test(root)
        print("NEGATIVE_TEST", "PASS" if ok else "FAIL", detail)
        return 0 if ok else 1

    ctx = Ctx(root)
    replay_res = None if args.skip_replay else replay(root)
    checks, bad = run_checks(ctx, replay_res)

    passed = sum(1 for c in checks if c["result"] == "PASS")
    print("R00 verify @", NOW, "root=", root)
    for c in checks:
        print("  [%s] %s %s" % (c["result"], c["id"], c["name"]))
        if c["result"] != "PASS":
            print("        ", c["detail"])
    print("checks %d/%d PASS, anomalies=%d" % (passed, len(checks), len(bad)))
    for b in bad:
        print("  ANOMALY", b)
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
