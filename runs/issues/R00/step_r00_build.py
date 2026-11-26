#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R00 / #44 / #57 + #58 构建：R00_BATCH_01 与 R00_BATCH_02 共 10 家 TIER_1 公司业务核验统一汇总。

只读取 Git 跟踪树内的 15 份输入，不联网、不修改任何上游冻结文件。
全部产物写入 runs/issues/R00/，统一 UTF-8 无 BOM + 纯 LF。

产物
----
business_batch_dispatch.csv      10 家固定派包（5 家 #57 + 5 家 #58，两批互斥）
business_review_register.csv     10 家结构化业务核验总表（8×H1 + 2×9M，含口径未知项）
batch01_evidence_quotes.csv      Batch 01 五家逐字短引文与物理页码（87 行）
batch02_evidence_quotes.csv      Batch 02 五家逐字短引文与物理页码（73 行）
child_issue_manifest.json        子卡 #57 / #58 清单与互斥校验
manifest.json                    输入与交付 sha256、根摘要、固定时间戳
handoff.md                       面向独立复核方 Codex 的交接
review.json                      SELF_CHECK（decision 由实测 anomalies 动态推导）

复现
----
    R00_FIXED_NOW=2026-11-26T22:25:00+08:00 py runs/issues/R00/step_r00_build.py
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - 环境已实测 PyYAML 6.0.3
    sys.stderr.write("ERROR: 需要 PyYAML（已实测 py -c \"import yaml\" 通过）；"
                     "请在离线环境安装后重跑，勿改用正则近似解析 YAML。\n")
    raise SystemExit(2)

REPO = Path(__file__).resolve().parents[3]
OUT = REPO / "runs/issues/R00"

NOW = os.environ.get("R00_FIXED_NOW") or "2026-11-26T22:25:00+08:00"
TODAY = NOW[:10]
CUTOFF = "2026-10-25"

PLAN_VERSION = "20261026_collection_first_v2"
ISSUE_KEY = "R00"
ISSUE_NUMBER = 44

IN_S08_CAND = "runs/issues/S08/business_verification_candidates.csv"
IN_S08_REUSE = "runs/issues/S08/candidate_reuse_map.csv"
IN_S08_ACC = "runs/issues/S08/acceptance_s08_20261126.json"
IN_R02_ACC = "runs/issues/R02/acceptance_r02_20261126.json"
IN_S05_FLAGS = "runs/issues/S05/quality_flags.csv"
IN_S05_LOG = "runs/issues/S05/quality_decision_log.csv"
IN_RELEASE = "runs/issues/R00/release_20261126.json"
IN_AI1_YAML = "runs/issues/R00/inputs_batch01/ai1_300607_002747_business_review.yaml"
IN_AI1_MD = "runs/issues/R00/inputs_batch01/ai1_300607_002747_evidence_notes.md"
IN_AI1_MANIFEST = "runs/issues/R00/inputs_batch01/ai1_manifest.json"
IN_AI2_YAML = "runs/issues/R00/inputs_batch01/ai2_002472_002979_business_review.yaml"
IN_CB_JSON = "runs/issues/R00/inputs_batch01/codebuddy_920593_draft.json"
IN_CB_MD = "runs/issues/R00/inputs_batch01/codebuddy_920593_draft.md"
IN_RELEASE_B2 = "runs/issues/R00/release_batch02_20261126.json"
IN_B2_YAML = "runs/issues/R00/inputs_batch02/batch02_5companies_business_review.yaml"

INPUTS = [IN_S08_CAND, IN_S08_REUSE, IN_S08_ACC, IN_R02_ACC, IN_S05_FLAGS, IN_S05_LOG,
          IN_RELEASE, IN_AI1_YAML, IN_AI1_MD, IN_AI1_MANIFEST, IN_AI2_YAML,
          IN_CB_JSON, IN_CB_MD, IN_RELEASE_B2, IN_B2_YAML]

OUT_DISPATCH = "business_batch_dispatch.csv"
OUT_REGISTER = "business_review_register.csv"
OUT_QUOTES_B1 = "batch01_evidence_quotes.csv"
OUT_QUOTES_B2 = "batch02_evidence_quotes.csv"
OUT_CHILD = "child_issue_manifest.json"
OUT_MANIFEST = "manifest.json"
OUT_HANDOFF = "handoff.md"
OUT_REVIEW = "review.json"

DELIVERABLES = [OUT_DISPATCH, OUT_REGISTER, OUT_QUOTES_B1, OUT_QUOTES_B2, OUT_CHILD, OUT_HANDOFF]
SCRIPTS = ["step_r00_build.py", "step_r00_verify.py"]
MANIFEST_DELIVERABLES = DELIVERABLES + SCRIPTS

DISPATCH_FIELDS = [
    "batch_id", "child_issue_number", "security_id", "stock_name", "topic",
    "s08_priority_tier", "anchor_period", "s05_rh_triggers", "s05_pending_flags",
    "has_legacy_asset", "legacy_sources", "legacy_auto_promoted",
    "assigned_executor", "batch_status",
]

REGISTER_FIELDS = [
    "security_id", "stock_name", "batch_id", "child_issue_number", "anchor_period",
    "knowledge_as_of", "sources_verified_count", "consolidated_robotics_entities",
    "non_consolidated_entities_excluded", "robot_exposure_verdict",
    "commercial_stage_verdict", "robot_revenue_separately_disclosed",
    "fy2025_total_rev_cny", "fy2025_robot_related_line", "anchor_total_rev_cny",
    "anchor_robot_related_line", "s05_alert_check_summary", "evidence_quote_count",
    "key_unknowns_and_limits", "one_sentence_summary", "source_executor",
    "review_nature", "independent_review_status",
]

QUOTE_FIELDS = ["security_id", "stock_name", "source_executor", "doc_id",
                "physical_page", "topic", "verbatim_quote"]

EXECUTOR_LINE = {
    "external_ai_1": "T02 整机与集成线",
    "external_ai_2": "T01 核心零部件线",
    "codebuddy": "T01 核心零部件 + 资料摸底 + 汇总建表与自检",
    "external_ai_batch02": "T01 核心零部件 + T02 整机与集成（Batch 02 外部 AI 统一执行）",
}

# 口径提示：凡混合/未单列口径，必须在表内明示，禁止等同纯机器人收入
MIXED_CAVEAT = "｜口径提示：混合或未单列口径，非纯机器人本体收入，不得以公司总收入替代机器人收入"

ROBOT_SEPARATELY = {
    "SZ:300607": "PARTIAL_FY2025_BODY_ONLY",
    "SZ:002747": "NO",
    "SZ:002472": "NO",
    "SZ:002979": "NO",
    "BJ:920593": "NO",
    "BJ:920510": "NO",
    "BJ:920491": "PARTIAL_FY2025_TEXT_ONLY",
    "SH:688003": "PARTIAL_FY2025_SEGMENT_MIXED",
    "SZ:002698": "YES",
    "BJ:920578": "PARTIAL_SYSTEM_INTEGRATION_LINE",
}

ALERT_KEY = {"RH02": "rh02_check", "RH04": "rh04_check",
             "RH05": "rh05_check", "RH06": "rh06_check"}

# 9M 锚定公司（其余 8 家一律 H1）
NINE_MONTH = {"SZ:002979", "SH:688003"}
ANCHOR_H1 = "20260630"
ANCHOR_9M = "20260930"


# ---------------------------------------------------------------- 基础工具

def read_csv(rel):
    with open(REPO / rel, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def read_json(rel):
    return json.loads((REPO / rel).read_text(encoding="utf-8"))


def sha256_exact(path: Path):
    raw = path.read_bytes()
    return len(raw), hashlib.sha256(raw).hexdigest()


def canon_bytes(path: Path):
    return path.read_bytes().replace(b"\r\n", b"\n")


def money(v):
    """归一为不带千分位、保留两位小数的金额字符串；无值返回空串。"""
    if v is None or v == "":
        return ""
    if isinstance(v, (int, float)):
        return "%.2f" % float(v)
    m = re.search(r"-?\d[\d,]*\.?\d*", str(v))
    if not m:
        return ""
    t = m.group(0).replace(",", "")
    return "%.2f" % float(t)


def pages_of(text):
    """从原文核验描述中抽取 1-based 物理页码（支持「第N页」与「pN」两种写法）。"""
    out = []
    for m in re.finditer(r"第\s*(\d+)\s*页", text or ""):
        p = int(m.group(1))
        if p not in out:
            out.append(p)
    for m in re.finditer(r"(?<![A-Za-z0-9])p(\d+)(?![0-9])", text or ""):
        p = int(m.group(1))
        if p not in out:
            out.append(p)
    return out


def clip(text, n=240):
    t = re.sub(r"\s+", " ", (text or "").strip())
    return t if len(t) <= n else t[: n - 1] + "…"


# ---------------------------------------------------------------- 载入输入

cand = {r["security_id"]: r for r in read_csv(IN_S08_CAND)}
reuse = {r["security_id"]: r for r in read_csv(IN_S08_REUSE)}
s05_flags = read_csv(IN_S05_FLAGS)
s05_log = {r["security_id"]: r for r in read_csv(IN_S05_LOG)}
accept_s08 = read_json(IN_S08_ACC)
accept_r02 = read_json(IN_R02_ACC)
release = read_json(IN_RELEASE)
release_b2 = read_json(IN_RELEASE_B2)

ai1_doc = yaml.safe_load((REPO / IN_AI1_YAML).read_text(encoding="utf-8"))
ai1_companies = [c["company"] for c in ai1_doc["companies"]]

ai2_companies = []
for doc in yaml.safe_load_all((REPO / IN_AI2_YAML).read_text(encoding="utf-8")):
    if isinstance(doc, dict) and "company" in doc:
        ai2_companies.append(doc["company"])

cb = read_json(IN_CB_JSON)

b2_doc = yaml.safe_load((REPO / IN_B2_YAML).read_text(encoding="utf-8"))
b2_companies = [w["company"] for w in b2_doc["companies"]]

# ---- 两批子卡规格统一为同一结构
B1_SPEC = release["child_issues"][0]
assert B1_SPEC["batch_id"] == "R00_BATCH_01" and B1_SPEC["issue_number"] == 57
assert release_b2["batch_id"] == "R00_BATCH_02" and release_b2["child_issue_number"] == 58
B2_SPEC = {
    "batch_id": release_b2["batch_id"],
    "issue_number": release_b2["child_issue_number"],
    "url": release_b2["child_issue_url"],
    "title": "R00_BATCH_02｜后期业务核验第02批：固定5家TIER_1核心公司",
    "companies": [{"security_id": c["security_id"], "stock_name": c["stock_name"],
                   "topic": c["topic"], "anchor_period": c["anchor_period"],
                   "s05_triggers": c["s05_triggers"], "s05_pending": c["s05_pending"],
                   "assigned_to": c["assigned_to"]} for c in release_b2["companies"]],
}

BATCHES = [
    {"batch_id": "R00_BATCH_01", "spec": B1_SPEC},
    {"batch_id": "R00_BATCH_02", "spec": B2_SPEC},
]

BATCH_ORDER = {b["batch_id"]: [c["security_id"] for c in b["spec"]["companies"]] for b in BATCHES}
ASSIGNED = {}
TOPIC = {}
SID_BATCH = {}
SID_CHILD = {}
for b in BATCHES:
    for c in b["spec"]["companies"]:
        ASSIGNED[c["security_id"]] = c["assigned_to"]
        TOPIC[c["security_id"]] = c["topic"]
        SID_BATCH[c["security_id"]] = b["batch_id"]
        SID_CHILD[c["security_id"]] = b["spec"]["issue_number"]

ORDER = BATCH_ORDER["R00_BATCH_01"] + BATCH_ORDER["R00_BATCH_02"]

S05_ANCHOR = {}
S05_FLAGS_OF = {}
for r in s05_flags:
    S05_ANCHOR.setdefault(r["security_id"], r["anchor_period"])
    S05_FLAGS_OF.setdefault(r["security_id"], set()).add(r["rh"])

TIER1 = {s for s, r in cand.items() if r["r00_priority_tier"].startswith("TIER_1")}


# ---------------------------------------------------------------- 归一化

def base_rec(sid, name, knowledge_as_of, sources, entities, lines, fy_total, fy_robot,
             anchor_total, anchor_robot, alerts, exposure, stage, summary, quotes,
             unknowns, excluded, anchor_label):
    return {
        "sid": sid, "name": name, "knowledge_as_of": knowledge_as_of,
        "sources": sources, "entities": entities, "lines": lines,
        "fy_total": fy_total, "fy_robot": fy_robot,
        "anchor_total": anchor_total, "anchor_robot": anchor_robot,
        "alerts": alerts, "exposure": exposure, "stage": stage, "summary": summary,
        "quotes": quotes, "unknowns": unknowns, "excluded": excluded,
        "anchor_label": anchor_label,
    }


def norm_ai1(c):
    rb = c["revenue_breakdown"]
    return base_rec(
        c["security_id"], c["stock_name"], c["knowledge_as_of"],
        [{"doc_id": s["doc_id"], "report_name": s["report_name"],
          "disclosure_date": s["disclosure_date"], "read_status": s["read_status"]}
         for s in c["sources_actually_read"]],
        [{"name": e["entity_name"], "status": e["consolidation_status"],
          "role": e["role_in_robotics"]} for e in c["consolidated_entities"]],
        [{"name": p["line_name"], "stage": p["commercial_stage"],
          "ref": p["evidence_ref"]} for p in c["product_lines"]],
        money(rb["fy2025_total_rev_cny"]), rb["fy2025_robot_related_line"],
        money(rb["h1_2026_total_rev_cny"]), rb["h1_2026_robot_related_line"],
        dict(c["s05_alert_investigation"]),
        c["business_verdict"]["robot_exposure"],
        c["business_verdict"]["overall_commercial_stage"],
        c["business_verdict"]["one_sentence_summary"],
        [{"doc_id": q["doc_id"], "page": int(q["physical_page"]),
          "topic": q["topic"], "quote": q["verbatim_quote"]}
         for q in c["evidence_quotes"]],
        list(c["unknowns_and_limits"]), [], "2026H1")


def norm_ai2(c):
    rb = c["revenue_breakdown"]
    return base_rec(
        c["security_id"], c["stock_name"], c["knowledge_as_of"],
        [{"doc_id": s["doc_id"], "report_name": s["report_name"],
          "disclosure_date": s["disclosure_date"], "read_status": s["read_status"]}
         for s in c["sources_actually_read"]],
        [{"name": e["entity_name"], "status": e["consolidation_status"],
          "role": e["role_in_robotics"]} for e in c["consolidated_entities"]],
        [{"name": p["line_name"], "stage": p["commercial_stage"],
          "ref": p["evidence_ref"]} for p in c["product_lines"]],
        money(rb["fy2025_total_rev_cny"]), rb["fy2025_robot_related_line"],
        money(rb["anchor_total_rev_cny"]), rb["anchor_robot_related_line"],
        dict(c["s05_alert_investigation"]),
        c["business_verdict"]["robot_exposure"],
        c["business_verdict"]["overall_commercial_stage"],
        c["business_verdict"]["one_sentence_summary"],
        [{"doc_id": q["doc_id"], "page": int(q["physical_page"]),
          "topic": q["topic"], "quote": q["verbatim_quote"]}
         for q in c["evidence_quotes"]],
        list(c["unknowns_and_limits"]), [], rb.get("anchor_period", ""))


def norm_b2(c):
    """Batch 02 五家：与 ai1 同构，但锚定期可为 2026Q1-Q3（天准）。"""
    rb = c["revenue_breakdown"]
    return base_rec(
        c["security_id"], c["stock_name"], c["knowledge_as_of"],
        [{"doc_id": s["doc_id"], "report_name": s["report_name"],
          "disclosure_date": s["disclosure_date"], "read_status": s["read_status"]}
         for s in c["sources_actually_read"]],
        [{"name": e["entity_name"], "status": e["consolidation_status"],
          "role": e["role_in_robotics"]} for e in c["consolidated_entities"]],
        [{"name": p["line_name"], "stage": p["commercial_stage"],
          "ref": p["evidence_ref"]} for p in c["product_lines"]],
        money(rb["fy2025_total_rev_cny"]), rb["fy2025_robot_related_line"],
        money(rb["anchor_total_rev_cny"]), rb["anchor_robot_related_line"],
        dict(c["s05_alert_investigation"]),
        c["business_verdict"]["robot_exposure"],
        c["business_verdict"]["overall_commercial_stage"],
        c["business_verdict"]["one_sentence_summary"],
        [{"doc_id": q["doc_id"], "page": int(q["physical_page"]),
          "topic": q["topic"], "quote": q["verbatim_quote"]}
         for q in c["evidence_quotes"]],
        list(c["unknowns_and_limits"]), [], rb.get("anchor_period", ""))


def norm_cb(d):
    rb = d["revenue_breakdown"]
    ca = d["s05_alert_check"]["contract_asset"]
    rh02_text = " ".join(str(v) for v in ca.values() if not isinstance(v, bool))
    ents = [{"name": s["name"], "status": "CONSOLIDATED(持股%s)" % s["holding"],
             "role": s.get("business", "")} for s in d["consolidated_entities"]["subsidiaries_10"]]
    excluded = ["%s（%s）" % (e["name"], e["type"])
                for e in d["consolidated_entities"]["equity_participations_not_consolidated"]]
    return base_rec(
        d["security_id"], d["stock_name"], d["knowledge_as_of"],
        [{"doc_id": s["document_id"], "report_name": s["title"],
          "disclosure_date": s["disclosure_date"],
          "read_status": "TEXT_LAYER_VERIFIED"} for s in d["sources_read"]],
        ents,
        [{"name": p["product"], "stage": p["robot_stage"],
          "ref": clip(p["disclosed_application"], 160)} for p in d["product_lines"]],
        money(rb["fy2025"]["total_revenue_cny"]),
        "NO_SEPARATE_ROBOT_REVENUE_LINE（机器人相关收入并入“直流电机及组件”，未单列）",
        money(rb["h1_2026"]["total_revenue_cny"]),
        ("NO_SEPARATE_ROBOT_REVENUE_LINE（2026H1 分产品不再拆“减速电机及驱控”，"
         "机器人收入不可量化）"),
        {"rh04_check": "NA", "rh05_check": "NA", "rh06_check": "NA", "rh02_check": rh02_text},
        d["robot_exposure_verdict"]["verdict"],
        d["commercial_stage_verdict"]["overall"],
        d["commercial_stage_verdict"]["summary"],
        [{"doc_id": q["document_id"], "page": int(q["page"]),
          "topic": q["claim"],
          "quote": q["quote"] + ("｜附注数据（非逐字）：" + q["data_excerpt"]
                                 if q.get("data_excerpt") else "")}
         for q in d["evidence_quotes"]],
        list(d["limits_and_unknowns"]), excluded, d["anchor_period"])


RECS = {}
for c in ai1_companies + ai2_companies:
    r = norm_ai1(c) if "h1_2026_total_rev_cny" in c.get("revenue_breakdown", {}) else norm_ai2(c)
    RECS[r["sid"]] = r
RECS[cb["security_id"]] = norm_cb(cb)
for c in b2_companies:
    r = norm_b2(c)
    RECS[r["sid"]] = r

assert set(RECS) == set(ORDER), "输入公司集合与 #57+#58 固定名单不一致"


# ---------------------------------------------------------------- 派生字段

def ent_status(s):
    """把来源的并表状态归一为“并表(持股x%)”，避免括号嵌套。"""
    if "CONSOLIDATED" not in s:
        return s
    m = re.search(r"持股([\d.]+%)", s)
    return "并表，持股%s" % m.group(1) if m else "并表"


def is_excluded_entity(status, role):
    """参股/未并表/非股权项目一律不计入并表口径。"""
    if "EQUITY_METHOD" in status or "不并表" in status or "NOT_CONSOLIDATED" in status or "PROPOSED_INVESTMENT" in status or "拟投资" in status:
        return True
    return any(k in role for k in ("未并表", "尚未并表", "无并表主体", "非股权主体"))


def consolidated_text(rec):
    keep, drop = [], []
    for e in rec["entities"]:
        if is_excluded_entity(e["status"], e["role"]):
            drop.append("%s（%s）" % (e["name"], clip(e["role"], 150)))
        else:
            keep.append("%s（%s）" % (e["name"], ent_status(e["status"])))
    return "; ".join(keep), drop


def excerpt(text, head=400, tail=200):
    """保留核验要点：长文取首段 + 尾段，避免截断关键数字。"""
    t = re.sub(r"\s+", " ", (text or "").strip())
    if len(t) <= head + tail:
        return t
    return t[:head] + "……" + t[-tail:]


def alert_summary(rec, triggers, pending):
    flags = [f for f in triggers if f] + [f for f in pending if f]
    if not flags:
        return "NO_S05_ALERT_TRIGGERED_OR_PENDING（0 触发 0 待核；RH02 项目制豁免 F06）"
    parts = []
    for f in flags:
        text = rec["alerts"].get(ALERT_KEY[f], "")
        pages = pages_of(text)
        if f in triggers:
            ok = ("成立" in text) or ("触发" in text)
            status = "TRIGGERED_CONFIRMED_BY_ORIGINAL" if ok else "TRIGGERED_STILL_OPEN"
        else:
            ok = ("已核实" in text) or ("CONFIRMED_BY_ORIGINAL" in text)
            status = "PENDING_RESOLVED_REAL_BLANK" if ok else "PENDING_STILL_OPEN"
        parts.append("%s:%s(物理页%s)｜核验要点：%s" % (
            f, status, "/".join(str(p) for p in pages) or "NA", excerpt(text)))
    return "; ".join(parts)


def dispatch_rows():
    rows = []
    for sid in ORDER:
        c = cand[sid]
        rows.append({
            "batch_id": SID_BATCH[sid],
            "child_issue_number": str(SID_CHILD[sid]),
            "security_id": sid,
            "stock_name": c["stock_name"],
            "topic": TOPIC[sid],
            "s08_priority_tier": c["r00_priority_tier"],
            "anchor_period": c["s05_anchor_period"],
            "s05_rh_triggers": c["s05_rh_triggers"],
            "s05_pending_flags": c["s05_pending_flags"],
            "has_legacy_asset": c["has_legacy_asset"],
            "legacy_sources": c["legacy_sources"],
            "legacy_auto_promoted": c["legacy_auto_promoted"],
            "assigned_executor": ASSIGNED[sid],
            "batch_status": "SUBMITTED_FOR_INDEPENDENT_REVIEW",
        })
    return rows


def register_rows():
    rows = []
    for sid in ORDER:
        c = cand[sid]
        rec = RECS[sid]
        cons, dropped = consolidated_text(rec)
        if rec["excluded"]:
            dropped = dropped + rec["excluded"]
        triggers = [x for x in c["s05_rh_triggers"].split(";") if x]
        pending = [x for x in c["s05_pending_flags"].split(";") if x]
        rows.append({
            "security_id": sid,
            "stock_name": c["stock_name"],
            "batch_id": SID_BATCH[sid],
            "child_issue_number": str(SID_CHILD[sid]),
            "anchor_period": c["s05_anchor_period"],
            "knowledge_as_of": rec["knowledge_as_of"],
            "sources_verified_count": len(rec["sources"]),
            "consolidated_robotics_entities": cons,
            "non_consolidated_entities_excluded": "; ".join(dropped) if dropped else "NONE_DISCLOSED",
            "robot_exposure_verdict": rec["exposure"],
            "commercial_stage_verdict": rec["stage"],
            "robot_revenue_separately_disclosed": ROBOT_SEPARATELY[sid],
            "fy2025_total_rev_cny": rec["fy_total"],
            "fy2025_robot_related_line": rec["fy_robot"],
            "anchor_total_rev_cny": rec["anchor_total"],
            "anchor_robot_related_line": rec["anchor_robot"] + MIXED_CAVEAT,
            "s05_alert_check_summary": alert_summary(rec, triggers, pending),
            "evidence_quote_count": len(rec["quotes"]),
            "key_unknowns_and_limits": " | ".join(rec["unknowns"]),
            "one_sentence_summary": rec["summary"],
            "source_executor": ASSIGNED[sid],
            "review_nature": "SELF_CHECK",
            "independent_review_status": "PENDING_CODEX_INDEPENDENT_REVIEW",
        })
    return rows


def quote_rows(batch_id):
    rows = []
    for sid in BATCH_ORDER[batch_id]:
        rec = RECS[sid]
        for q in rec["quotes"]:
            rows.append({
                "security_id": sid,
                "stock_name": rec["name"],
                "source_executor": ASSIGNED[sid],
                "doc_id": q["doc_id"],
                "physical_page": q["page"],
                "topic": q["topic"],
                "verbatim_quote": q["quote"],
            })
    return rows


# ---------------------------------------------------------------- 写出工具

def write_csv(path: Path, fields, rows):
    buf = io.StringIO(newline="")
    w = csv.DictWriter(buf, fieldnames=fields, lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow({k: r[k] for k in fields})
    path.write_bytes(buf.getvalue().encode("utf-8"))


def write_json(path: Path, obj):
    path.write_bytes((json.dumps(obj, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


def input_meta():
    meta = []
    for rel in INPUTS:
        b = canon_bytes(REPO / rel)
        meta.append({"path": rel, "bytes": len(b), "sha256": hashlib.sha256(b).hexdigest()})
    return meta


def build_manifest(anomaly_count):
    deliv = []
    for name in MANIFEST_DELIVERABLES:
        n, s = sha256_exact(OUT / name)
        deliv.append({"path": "runs/issues/R00/" + name, "bytes": n, "sha256": s})
    root = hashlib.sha256(
        "\n".join("%s:%s" % (d["path"], d["sha256"])
                  for d in sorted(deliv, key=lambda x: x["path"])).encode("utf-8")
    ).hexdigest()
    return {
        "artifact": "R00_DELIVERY_MANIFEST",
        "issue_key": ISSUE_KEY,
        "issue_number": ISSUE_NUMBER,
        "child_issue_numbers": [b["spec"]["issue_number"] for b in BATCHES],
        "batch_ids": [b["batch_id"] for b in BATCHES],
        "plan_version": PLAN_VERSION,
        "knowledge_as_of": CUTOFF,
        "executor": "CodeBuddy",
        "orchestrator": "Antigravity",
        "review_nature": "SELF_CHECK",
        "fixed_now": NOW,
        "input_hash_basis": "CANONICAL_LF_BYTES",
        "input_hash_basis_note": "文本输入按 CRLF->LF 规范化后计算字节数与 SHA-256。",
        "deliverable_hash_basis": "EXACT_BYTES_LF",
        "root_digest_basis": ("按交付物 path 排序后以 'path:sha256' 以 \\n 连接再取 SHA-256；"
                              "不含 manifest.json 与 review.json 自身，避免循环依赖。"),
        "replay_note": "离线运行 step_r00_build.py 与 step_r00_verify.py；R00_FIXED_NOW 固定时间戳。",
        "manifest_root_digest": root,
        "input_count": len(INPUTS),
        "deliverable_count": len(deliv),
        "company_count": len(ORDER),
        "inputs": input_meta(),
        "deliverables": deliv,
        "anomaly_count": anomaly_count,
    }


# ---------------------------------------------------------------- 子卡清单

def child_manifest():
    children = []
    for b in BATCHES:
        spec = b["spec"]
        comps = []
        for sid in BATCH_ORDER[b["batch_id"]]:
            c = cand[sid]
            comps.append({
                "security_id": sid,
                "stock_name": c["stock_name"],
                "topic": TOPIC[sid],
                "anchor_period": c["s05_anchor_period"],
                "s08_priority_tier": c["r00_priority_tier"],
                "s05_rh_triggers": [x for x in c["s05_rh_triggers"].split(";") if x],
                "s05_pending_flags": [x for x in c["s05_pending_flags"].split(";") if x],
                "has_legacy_asset": c["has_legacy_asset"] == "True",
                "legacy_sources": c["legacy_sources"],
                "legacy_auto_promoted": c["legacy_auto_promoted"] == "True",
                "assigned_executor": ASSIGNED[sid],
                "executor_line": EXECUTOR_LINE[ASSIGNED[sid]],
                "source_file": {"external_ai_1": IN_AI1_YAML, "external_ai_2": IN_AI2_YAML,
                                "codebuddy": IN_CB_JSON,
                                "external_ai_batch02": IN_B2_YAML}[ASSIGNED[sid]],
                "evidence_quote_count": len(RECS[sid]["quotes"]),
                "sources_verified_count": len(RECS[sid]["sources"]),
            })
        lines = {}
        for ex in sorted({ASSIGNED[s] for s in BATCH_ORDER[b["batch_id"]]}):
            lines[ex] = {
                "line": EXECUTOR_LINE[ex],
                "companies": [s for s in BATCH_ORDER[b["batch_id"]] if ASSIGNED[s] == ex],
                "input_files": [p for p in
                                ([IN_AI1_YAML, IN_AI1_MD, IN_AI1_MANIFEST] if ex == "external_ai_1" else [])
                                + ([IN_AI2_YAML] if ex == "external_ai_2" else [])
                                + ([IN_CB_JSON, IN_CB_MD] if ex == "codebuddy" else [])
                                + ([IN_B2_YAML] if ex == "external_ai_batch02" else [])],
            }
        children.append({
            "issue_number": spec["issue_number"],
            "issue_key": b["batch_id"],
            "url": spec["url"],
            "title": spec["title"],
            "batch_size": len(BATCH_ORDER[b["batch_id"]]),
            "fixed_no_substitution": True,
            "companies": comps,
            "executor_lines": lines,
        })

    b1 = set(BATCH_ORDER["R00_BATCH_01"])
    b2 = set(BATCH_ORDER["R00_BATCH_02"])
    overlap = sorted(b1 & b2)
    return {
        "artifact": "R00_CHILD_ISSUE_MANIFEST",
        "parent_issue": {"issue_number": ISSUE_NUMBER, "issue_key": ISSUE_KEY,
                         "release_files": [IN_RELEASE, IN_RELEASE_B2]},
        "plan_version": PLAN_VERSION,
        "knowledge_as_of": CUTOFF,
        "fixed_now": NOW,
        "child_issue_count": len(children),
        "total_companies": len(ORDER),
        "mutual_exclusion": {
            "batches": ["R00_BATCH_01", "R00_BATCH_02"],
            "batch01_companies": sorted(b1),
            "batch02_companies": sorted(b2),
            "overlap": overlap,
            "verified_zero_overlap": not overlap,
            "union_equals_s08_tier1_subset": set(ORDER) <= TIER1,
        },
        "children": children,
        "inputs": input_meta(),
        "deliverables": [
            {"path": "runs/issues/R00/" + n, "role": r} for n, r in [
                (OUT_DISPATCH, "10 家固定派包（两批互斥）"),
                (OUT_REGISTER, "10 家结构化业务核验总表（8×H1 + 2×9M）"),
                (OUT_QUOTES_B1, "Batch 01 逐字短引文与物理页码"),
                (OUT_QUOTES_B2, "Batch 02 逐字短引文与物理页码"),
                (OUT_CHILD, "本文件：两子卡清单与互斥校验"),
                (OUT_MANIFEST, "输入/交付哈希与根摘要"),
                (OUT_HANDOFF, "独立复核交接"),
                (OUT_REVIEW, "SELF_CHECK 自检结果"),
                ("step_r00_build.py", "可复现构建脚本"),
                ("step_r00_verify.py", "独立校验脚本"),
            ]
        ],
        "guards": {
            "knowledge_as_of": CUTOFF,
            "max_companies_per_batch": 5,
            "fixed_batch_no_substitution": True,
            "batches_mutually_exclusive": not overlap,
            "legacy_auto_promoted": False,
            "unknown_or_hold_on_gap": True,
            "company_total_revenue_neq_robot_revenue": True,
            "no_cross_period_merge_h1_vs_9m": True,
            "S00_errata_issue_53": "OPEN",
            "R01_released": False,
            "R03_released": False,
            "R04_started": False,
        },
        "review": {"review_nature": "SELF_CHECK", "independent_reviewer": "Codex",
                   "independent_review_status": "PENDING",
                   "note": "执行方自检不等于独立复核；业务结论最终采用仍需 Codex 原文复核。"},
    }


# ---------------------------------------------------------------- handoff

FOCUS = {
    "SZ:300607": [
        "DOC ID 冲突：GitHub `document_registry.csv` 登记 2025 年报为 `DOC-82DD061D1A766CCA`，"
        "用户清单另列 `DOC-8AA65D8C6F87227B`；官方 PDF URL 相同，未擅自合并，需二进制哈希与登记 ID 对齐。",
        "2026H1 的 707,279,751.48 元是“工业机器人及自动化应用系统”合并口径，"
        "本体与自动化系统金额未完整拆分；不得写成纯机器人本体收入。",
        "“小拓”仅客户场景小批量验证，“星仔”为样机级，X5 平台无收入披露；"
        "H1 签单 6,800 台/出货 5,500 台为工业机器人整体口径，非人形机器人。",
    ],
    "SZ:002747": [
        "RH04：H1 经营现金流 44,527,240.04 元 / 归母净利 161,325,506.86 元 = 0.276；"
        "应收增加、应付净减少与合同负债下降共同压低现金流，存货去化部分抵消。",
        "RH06：H1 非经常性损益净额 91,153,843.97 元，占归母净利约 56.50%，"
        "其中公允价值变动收益 99,504,389.61 元；扣非由负转正但 2025H1 为负基数。",
        "酷卓时间线：2026-06-30 仅持股 13.95% 参股不并表；2026-09-08 交割完成公告后间接 100% 并表。"
        "不得把酷卓 2026 年 1—4 月收入倒算进埃斯顿 H1 合并收入。",
    ],
    "SZ:002472": [
        "环动科技（持股 61.29%）已并表，但单体收入/净利润未披露（2025 年报 p26 主要子公司表未列），"
        "RV 减速器盈利能力留 HOLD。",
        "分拆上市仅披露 2024-11-25 受理及“尚在进行中”，未见上市委审议/注册/中止正式披露，进度留 HOLD。",
        "“减速器及其他”795,052,336.68 元（FY2025）/440,341,985.30 元（H1）含非机器人减速器，"
        "不可整体视作机器人收入。",
    ],
    "SZ:002979": [
        "9M 锚定（20260930），严禁与 6 家 H1 公司跨期混比；三季报披露日 2026-10-22 在截止日内。",
        "RH04：9M 经营现金流 -51,525,866.57 元，归母净利 299,184,569.06 元，比值 -0.172；"
        "Q3 单季经营现金流 -94,892,155.76 元（约 -9,489 万元），单季恶化需持续跟踪。",
        "三季报 p2 资产负债表变动表增减率与同行金额无法复算（存货标 +33.22% 实为 +49.75%、"
        "应收票据标 +40.49% 实为 +68.03%、应收款项融资标 +69.70% 实为 +230.02%），本表不采用该增减率。",
    ],
    "BJ:920593": [
        "年报“该单项业务收入增长 687.23%”无绝对额，且与附注“减速电机及驱控”行同比 +127.72% 不一致，"
        "口径冲突留未知，不反推、不补零。",
        "机器人收入并入“直流电机及组件”，H1 分产品不再拆“减速电机及驱控”，机器人金额彻底不可量化。",
        "5 家参股/联营（脉塔、锚点、联融域、华传智感、中科灵犀 5%）一律不并表、不折算收入。",
    ],
    "BJ:920510": [
        "谐波减速器已量产并向意优机器人小批量交付，但 2025 年报与 2026 半年报分产品表均只有"
        "“产品收入/加工收入”两行，谐波金额无法单独称重；2025 年对意优机器人客户销售额 1,234.21 万元（占 5.89%）仅保留为客户销售额事实，无交易级品类拆分，谐波及机器人收入留未知。",
        "北京唯实深蓝 51% 收购截至 2026-06-30 未并表（p19“合并范围是否发生变化 √否”），"
        "已付预付并购款（其他非流动资产 +8,040.13 万元）并新增并购贷 5,623.81 万元，并表时点与对价留 HOLD。",
        "RH02 为真实空白：2025 年报 p70 与 2026 半年报 p39 合同资产行均为“-”，"
        "存货周转加快（H1 约 115.8 天），未见积压；但 2025 年全年亏损 -1,554.92 万元。",
        "披露日差异：清单列 2026-08-13，CNINFO 静态路径为 2026-08-14，正文仅见公告编号，未擅自改期。",
    ],
    "BJ:920491": [
        "“应用于机器人的传感器全年营业收入超过 1.1 亿元”为 2025 年报 p21 文本口径而非表格科目，"
        "未拆分服务/工业/人形，只能作机器人相关收入的上限近似；不可外推至 2026H1。",
        "RH05 触发且已查清：2026H1 综合毛利率 32.89%（-2.53pct），传感器 34.84%（-2.43pct）；"
        "官方三因（服务机器人降价传导、贵金属涨价、美元贬值汇兑损失），执行器与技术服务同步下滑佐证普遍性。",
        "电子皮肤主体奥感微为参股联营（权益法、不并表），2026H1 收入仅 12,648.14 元、净亏 315.95 万元；"
        "持股比例原文未列，留 HOLD，不得并表或折算。",
        "RH02 为真实空白：2025 年报 p87 与 2026 半年报 p37 合同资产行均无金额，属连续期间一贯无合同资产。",
    ],
    "SH:688003": [
        "9M 锚定（20260930）：三季报 2026-10-23 披露，在截止日内；严禁与 8 家 H1 公司跨期混比。",
        "“具身智能方案”FY2025 为 1.78 亿元、2026H1 具身大脑 1.58 亿元（+141.60%），"
        "但同一科目混入无人物流车/Robotaxi/重卡/清扫车 L4 域控，纯人形部分不可得。",
        "RH06 触发且已查清：9M 扣非 2,147.36 万元仅占归母 6,645.60 万元的 32.31%，"
        "非经常性损益 4,498.24 万元占 67.69%；Q3 归母 -3,202.66 万元而扣非 +1,113.14 万元，"
        "单季炒股浮亏 -4,489.10 万元，主业扣非仍为正。",
        "RH02 触发：三季报 p7 存货 20.83 亿元较年初 +75.01%，合同资产 7,324.74 万元（+40.03%，非空白）；"
        "三季报未解释存货再增原因，原因项留 UNKNOWN。",
        "天准星智注册资本半年报内部不一致（21,678.01 万元 vs 26,178.01 万元），不采用作规模判断。",
    ],
    "SZ:002698": [
        "“机器人+”单列但盘子极小：FY2025 仅 0.33 亿元（占 1.17%，同比 -91.53%，公司归因无电石智能工厂收入"
        "且炉前作业机器人收入下滑）；2026H1 增至 0.48 亿元（+125.84%）但毛利率降至 14.87%（-3.71pct）。",
        "与哈工大合作的人形机器人关键技术及原理样机产业化研发项目 2026H1 已明确终止后续工作，"
        "2 台样机未达合同指标，4 项发明专利为共有申请权且变更登记在办理中，处置与减值未披露。",
        "思哲睿（13.43%，医疗手术机器人，权益法参股不并表）；灵博（2026-08 公告拟增资 2,000 万元、拟持股 12%，截至 H1 尚未出资、尚未参股，属拟投资未交割事项，交割及会计处理待核），"
        "均不构成本期并表或损益影响。",
        "RH05 触发且已查清：FY2025 工业服务毛利率 23.97%（-5.65pct），官方原因为定价与结算水平、"
        "成本负面波动；2026H1 已修复至 27.80%（+2.78pct），但“机器人+”自身毛利成为新拖累。",
        "页码偏移：两份 PDF 印刷页码均为物理页 -1（物理 p29 印“28”），本表 physical_page 按物理页给出。",
    ],
    "BJ:920578": [
        "占营收 85% 的“机器人自动化生产线”是系统集成项目制收入，本体以发那科外购为主"
        "（2025 年前五大供应商含上海发那科 802.57 万元、占 8.63%），未拆分本体/集成，不可视为纯本体收入。",
        "RH04 触发且已查清：2026H1 经营现金流 166.87 万元 / 归母净利 1,006.26 万元 = 0.166（同比 -94.52%）；"
        "官方仅给“上年同期超 3,000 万元大额验收款”高基数原因，未解释本期回款本身。",
        "合同负债 2,433.60 万元、较年初 -34.59%，公司称“新合同订单增长小于订单转入收入幅度”，"
        "即在手订单被消耗；应收票据 +38.07% 说明回款以票据为主。",
        "2025 年亏损（归母 -214.63 万元）转 2026H1 扭亏，主要靠毛利率 +5.59pct；"
        "非经常性损益 309.09 万元占归母 30.7%，扭亏质量部分依赖政府补助。",
    ],
}


def build_handoff(rows):
    L = []
    A = L.append
    A("# R00 / #44 · R00_BATCH_01（#57）+ R00_BATCH_02（#58）交接：十家业务核验汇总")
    A("")
    A("- 计划版本：`%s`；知识截止日：`%s`；生成时间：`%s`（Asia/Shanghai）" % (PLAN_VERSION, CUTOFF, NOW))
    A("- 执行方：CodeBuddy（汇总建表与自检）；统筹方：Antigravity")
    A("- 业务执行：外部 AI-1（拓斯达/埃斯顿）、外部 AI-2（双环传动/雷赛智能）、本机 CodeBuddy（鼎智科技）、"
      "外部 AI Batch 02（丰光精密/奥迪威/天准科技/博实股份/巨能股份）")
    A("- 复核方：Codex（`gpt-6.2-sol low`，用户授权 `--sandbox danger-full-access`；遇业务真伪硬争议升 `high`）")
    A("- 本文件性质：`SELF_CHECK`。执行方自检不等于独立复核；`R01_released=false`、`R03_released=false`、"
      "`#53` 保持 `OPEN`，未做估值、未给买卖建议。")
    A("")
    A("## 1. 复现命令")
    A("")
    A("```bash")
    A("R00_FIXED_NOW=%s py runs/issues/R00/step_r00_build.py" % NOW)
    A("R00_FIXED_NOW=%s py runs/issues/R00/step_r00_verify.py" % NOW)
    A("py runs/issues/R00/step_r00_verify.py --negative-test   # 活体负例篡改，期望退出码 1")
    A("```")
    A("")
    A("构建脚本仅读取 15 份 Git 跟踪输入，全程离线；两次构建逐字节一致（纯 LF、UTF-8 无 BOM）。")
    A("")
    A("## 2. 两批固定名单与互斥")
    A("")
    A("| 子卡 | 批次 | 家数 | 名单 |")
    A("| --- | --- | --- | --- |")
    for b in BATCHES:
        ids = BATCH_ORDER[b["batch_id"]]
        A("| #%d | `%s` | %d | %s |" % (
            b["spec"]["issue_number"], b["batch_id"], len(ids),
            "、".join("%s（%s）" % (cand[s]["stock_name"], s) for s in ids)))
    A("")
    A("两批交集为空（零重复），10 家全部落在 S08 冻结 `TIER_1` 主线候选内；锚定期严格分层："
      "8 家 H1（`20260630`）+ 2 家 9M（`20260930`：雷赛智能、天准科技）。")
    A("")
    A("## 3. 十家核心结论")
    A("")
    A("| 证券 | 名称 | 批次 | 锚定期 | 机器人暴露 | 商业化阶段 | 机器人收入单列 | 证据引文 |")
    A("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for r in rows:
        A("| `%s` | %s | %s | %s | `%s` | `%s` | `%s` | %s 条 |" % (
            r["security_id"], r["stock_name"], r["batch_id"], r["anchor_period"],
            r["robot_exposure_verdict"], r["commercial_stage_verdict"],
            r["robot_revenue_separately_disclosed"], r["evidence_quote_count"]))
    A("")
    for r in rows:
        A("### %s（%s）" % (r["stock_name"], r["security_id"]))
        A("")
        A("- 一句话结论：%s" % r["one_sentence_summary"])
        A("- FY2025 总收入 %s 元；机器人相关线：%s" % (r["fy2025_total_rev_cny"], clip(r["fy2025_robot_related_line"], 300)))
        A("- 锚定期（%s）总收入 %s 元；机器人相关线：%s" % (
            r["anchor_period"], r["anchor_total_rev_cny"], clip(r["anchor_robot_related_line"], 300)))
        A("- S05 质量项：%s" % r["s05_alert_check_summary"])
        A("")
    A("## 4. 待独立复核重点")
    A("")
    for sid in ORDER:
        A("**%s（%s）**" % (RECS[sid]["name"], sid))
        A("")
        for f in FOCUS[sid]:
            A("- %s" % f)
        A("")
    A("## 5. 关键限制条款")
    A("")
    A("1. **公司总收入 != 机器人收入**。十家中仅博实股份在分产品表单列“机器人+”，"
      "但该科目含电石智能工厂整线与高温特种作业机器人，且 FY2025 仅占 1.17%；其余九家的机器人相关收入均并入更大类目，金额不可单独验证。")
    A("2. **混合大类不得当作纯机器人收入**。“工业机器人及自动化应用系统”“减速器及其他”“伺服系统类”"
      "“直流电机及组件”“产品收入”“传感器”“具身智能方案”“机器人自动化生产线”均含非机器人部分。")
    A("3. **参股不并表**。埃斯顿酷卓（2026-06-30 仅 13.95%）、鼎智科技 5 家参股、丰光精密唯实深蓝（尚未并表）、"
      "奥迪威奥感微（权益法）、天准科技矽行（权益法）、博实股份思哲睿（权益法）与灵博（2026-08拟增资未交割、H1尚未参股，交割及会计处理待核）一律不并表、不折算收入。")
    A("4. **H1 与 9M 严格分层**。雷赛智能、天准科技为 9M（20260930）锚定，禁止与 8 家 H1 公司跨期混比；"
      "天准三季报未拆分部，其机器人结论以 2026H1 为依据并明确标注期间。")
    A("5. **未知保持未知**。缺失不补零、不按增速反推金额、不以订单/样机替代已实现收入；"
      "无法核实处记 `UNKNOWN`/`HOLD`。")
    A("6. **历史资产仅复用**。十家 `legacy_sources` 均只作线索与原文入口，`legacy_auto_promoted=false`，"
      "不因旧底稿自动提级。")
    A("7. **知识截止日 2026-10-25**。未采用该日之后披露的任何报告或公告；"
      "八家 H1 锚定公司未混入 2026 三季报。")
    A("8. **原件归档未完成**。本轮仅完成官方原文关键页读取与物理页码核验；"
      "PDF 二进制 SHA-256 与 Google Drive 回读归档验收仍待补。")
    A("9. **页码口径**。博实股份两份 PDF 印刷页码为物理页 -1；本表 `physical_page` 一律为 PDF 物理页（1-based）。")
    A("")
    A("## 6. 交付物")
    A("")
    A("| 文件 | 说明 |")
    A("| --- | --- |")
    A("| `business_batch_dispatch.csv` | 10 家固定派包（%d 行，两批互斥） |" % len(rows))
    A("| `business_review_register.csv` | 10 家结构化业务核验总表（%d 行） |" % len(rows))
    A("| `batch01_evidence_quotes.csv` | Batch 01 逐字短引文与物理页码（%d 行） |"
      % len(quote_rows("R00_BATCH_01")))
    A("| `batch02_evidence_quotes.csv` | Batch 02 逐字短引文与物理页码（%d 行） |"
      % len(quote_rows("R00_BATCH_02")))
    A("| `child_issue_manifest.json` | 子卡 #57 / #58 清单、三线映射与互斥校验 |")
    A("| `manifest.json` | 输入/交付哈希与根摘要 |")
    A("| `review.json` | SELF_CHECK（decision 由 anomalies 推导） |")
    A("| `step_r00_build.py` / `step_r00_verify.py` | 离线构建 / 独立校验 |")
    A("")
    A("## 7. 断点与下一步")
    A("")
    A("- 两批共 10 家业务核验已汇总，等待 Codex 独立复核；未执行 `git commit`，由统筹方统一提交推送。")
    A("- 未放行 R01（财务归因）、未启动 R03（拐点研判）与 R04（估值），未触碰 `#53`。")
    A("- 复核若发现口径问题，按当前 issue 范围修改并重跑构建+校验，不手工改交付表。")
    A("")
    return "\n".join(L)


# ---------------------------------------------------------------- 自检

def build_checks(disp, reg, quotes_b1, quotes_b2, manifest):
    checks, anomalies = [], []
    quotes = quotes_b1 + quotes_b2

    def add(cid, name, ok, detail):
        checks.append({"id": cid, "name": name,
                       "result": "PASS" if ok else "FAIL", "detail": detail})
        if not ok:
            anomalies.append("%s %s: %s" % (cid, name, detail))

    # C01 固定名单与两批互斥
    b1_ids = [c["security_id"] for c in B1_SPEC["companies"]]
    b2_ids = [c["security_id"] for c in B2_SPEC["companies"]]
    reg_ids = [r["security_id"] for r in reg]
    c01 = (reg_ids == ORDER and set(reg_ids) == set(ORDER) and len(set(reg_ids)) == 10
           and set(reg_ids) <= TIER1
           and not (set(b1_ids) & set(b2_ids))
           and all(r["batch_id"] == SID_BATCH[r["security_id"]] for r in reg)
           and all(r["child_issue_number"] == str(SID_CHILD[r["security_id"]]) for r in reg))
    add("C01", "10 家 = #57 五家 + #58 五家，两批互斥零重复且全属 S08 TIER_1", c01,
        "reg=%s b1=%s b2=%s overlap=%s all_tier1=%s" % (
            reg_ids, b1_ids, b2_ids, sorted(set(b1_ids) & set(b2_ids)), set(reg_ids) <= TIER1))

    # C02 知识截止日
    late_src, q3_outside = [], []
    for sid, rec in RECS.items():
        if rec["knowledge_as_of"] != CUTOFF:
            late_src.append("%s:knowledge_as_of=%s" % (sid, rec["knowledge_as_of"]))
        for s in rec["sources"]:
            if s["disclosure_date"] > CUTOFF:
                late_src.append("%s:%s@%s" % (sid, s["doc_id"], s["disclosure_date"]))
            if ("三季" in s["report_name"] or "第三季度" in s["report_name"]) and sid not in NINE_MONTH:
                q3_outside.append("%s:%s" % (sid, s["doc_id"]))
    c02 = not late_src and not q3_outside
    add("C02", "knowledge_as_of=2026-10-25、披露日<=截止日、8 家非 9M 公司不混入三季报", c02,
        "late=%s q3_outside=%s" % (late_src[:3], q3_outside))

    # C03 锚定期分离
    anchors = {r["security_id"]: r["anchor_period"] for r in reg}
    exp_anchor = {s: cand[s]["s05_anchor_period"] for s in ORDER}
    c03 = (anchors == exp_anchor
           and sum(1 for v in anchors.values() if v == ANCHOR_H1) == 8
           and sum(1 for v in anchors.values() if v == ANCHOR_9M) == 2
           and {s for s, v in anchors.items() if v == ANCHOR_9M} == NINE_MONTH
           and all(S05_ANCHOR.get(s) == exp_anchor[s] for s in ORDER))
    add("C03", "锚定期 8×H1 + 2×9M（雷赛、天准）与 S08/S05 一致", c03,
        "anchors=%s s05_anchor=%s" % (anchors, {s: S05_ANCHOR.get(s) for s in ORDER}))

    # C04 历史复用边界
    bad_legacy = []
    for r in reg:
        s = r["security_id"]
        if not reuse[s]["legacy_sources"] or not r["security_id"]:
            bad_legacy.append(s + ":no_legacy_sources")
        if reuse[s]["auto_promoted"] != "False" or cand[s]["legacy_auto_promoted"] != "False":
            bad_legacy.append(s + ":auto_promoted")
    for r in disp:
        if r["legacy_auto_promoted"] != "False" or not r["legacy_sources"]:
            bad_legacy.append(r["security_id"] + ":dispatch")
    c04 = not bad_legacy
    add("C04", "十家均保留 legacy_sources 且 legacy_auto_promoted=False", c04,
        "bad=%s" % bad_legacy)

    # C05 质量项排查完备性
    miss = []
    q_by_sid = {}
    for q in quotes:
        q_by_sid.setdefault(q["security_id"], set()).add(int(q["physical_page"]))
    reg_of = {r["security_id"]: r for r in reg}
    for sid in ORDER:
        triggers = [x for x in cand[sid]["s05_rh_triggers"].split(";") if x]
        pending = [x for x in cand[sid]["s05_pending_flags"].split(";") if x]
        summ = reg_of[sid]["s05_alert_check_summary"]
        for f in triggers + pending:
            if f not in summ:
                miss.append("%s:%s:not_in_summary" % (sid, f))
                continue
            pages = set(pages_of(RECS[sid]["alerts"].get(ALERT_KEY[f], "")))
            if not (pages & q_by_sid.get(sid, set())):
                miss.append("%s:%s:no_page_quote" % (sid, f))
        if (triggers or pending) and ("物理页" not in summ or "NA" == summ.split("物理页")[-1][:2]):
            miss.append(sid + ":no_page_ref")
    expect_flags = {s: (cand[s]["s05_rh_triggers"], cand[s]["s05_pending_flags"]) for s in ORDER}
    need = {"SZ:002747": ("RH04;RH06", ""), "SZ:002979": ("RH04", "RH02"),
            "SZ:002472": ("", "RH02"), "BJ:920593": ("", "RH02"),
            "BJ:920510": ("", "RH02"), "BJ:920491": ("RH05", "RH02"),
            "SH:688003": ("RH02;RH06", ""), "SZ:002698": ("RH05", ""),
            "BJ:920578": ("RH04", "")}
    c05 = not miss and all(expect_flags[k] == v for k, v in need.items())
    add("C05", "全部 S05 触发/待核项（含 Batch 02 的 RH02/RH04/RH05/RH06）均有原文页码引文", c05,
        "miss=%s flags=%s" % (miss, expect_flags))

    # C06 口径防污染
    contam = []
    for r in reg:
        sid = r["security_id"]
        if not r["key_unknowns_and_limits"].strip():
            contam.append(sid + ":no_unknowns")
        if "非纯机器人" not in r["anchor_robot_related_line"]:
            contam.append(sid + ":no_caveat")
        if r["anchor_robot_related_line"].strip() == r["anchor_total_rev_cny"].strip():
            contam.append(sid + ":total_as_robot")
        if not r["anchor_robot_related_line"].strip():
            contam.append(sid + ":empty_robot_line")
    # 参股不得并表
    def col(sid, field):
        return reg_of[sid][field]
    if "酷卓" in col("SZ:002747", "consolidated_robotics_entities"):
        contam.append("SZ:002747:kuzhuo_in_consolidated")
    if "酷卓" not in col("SZ:002747", "non_consolidated_entities_excluded"):
        contam.append("SZ:002747:kuzhuo_not_excluded")
    for n in ("中科灵犀", "脉塔", "锚点", "联融域", "华传智感"):
        if n in col("BJ:920593", "consolidated_robotics_entities"):
            contam.append("BJ:920593:%s_in_consolidated" % n)
        if n not in col("BJ:920593", "non_consolidated_entities_excluded"):
            contam.append("BJ:920593:%s_not_excluded" % n)
    for sid, names in {
        "BJ:920510": ("唯实深蓝",),
        "BJ:920491": ("奥感微",),
        "SH:688003": ("矽行",),
        "SZ:002698": ("思哲睿", "灵博"),
    }.items():
        for n in names:
            if n in col(sid, "consolidated_robotics_entities"):
                contam.append("%s:%s_in_consolidated" % (sid, n))
            if n not in col(sid, "non_consolidated_entities_excluded"):
                contam.append("%s:%s_not_excluded" % (sid, n))
    c06 = not contam
    add("C06", "未知项齐备、混合口径明示、参股不并表（酷卓/鼎智/唯实深蓝/奥感微/矽行/思哲睿/灵博）", c06,
        "contam=%s" % contam)

    # C07 引文完整性
    per = {s: sum(1 for q in quotes if q["security_id"] == s) for s in ORDER}
    bad_q = [q for q in quotes if int(q["physical_page"]) <= 0 or not q["verbatim_quote"].strip()
             or not q["doc_id"].strip()]
    c07 = (all(v >= 10 for v in per.values()) and not bad_q
           and len(quotes_b1) == sum(len(RECS[s]["quotes"]) for s in BATCH_ORDER["R00_BATCH_01"])
           and len(quotes_b2) == sum(len(RECS[s]["quotes"]) for s in BATCH_ORDER["R00_BATCH_02"])
           and len(quotes) == sum(len(RECS[s]["quotes"]) for s in ORDER))
    add("C07", "引文表覆盖 10 家、每家>=10 条、页码 1-based>0 且逐字非空", c07,
        "per_company=%s b1=%d b2=%d bad=%d" % (per, len(quotes_b1), len(quotes_b2), len(bad_q)))

    # C08 manifest 与 LF
    inp_bad = []
    for d in manifest["inputs"]:
        b = canon_bytes(REPO / d["path"])
        if len(b) != d["bytes"] or hashlib.sha256(b).hexdigest() != d["sha256"]:
            inp_bad.append(d["path"])
    del_bad = []
    for d in manifest["deliverables"]:
        n, s = sha256_exact(REPO / d["path"])
        if n != d["bytes"] or s != d["sha256"]:
            del_bad.append(d["path"])
    root = hashlib.sha256(
        "\n".join("%s:%s" % (d["path"], d["sha256"])
                  for d in sorted(manifest["deliverables"], key=lambda x: x["path"])).encode("utf-8")
    ).hexdigest()
    crlf = [f for f in DELIVERABLES + SCRIPTS if b"\r\n" in (OUT / f).read_bytes()]
    bom = [f for f in DELIVERABLES + SCRIPTS if (OUT / f).read_bytes().startswith(b"\xef\xbb\xbf")]
    c08 = (not inp_bad and not del_bad and root == manifest["manifest_root_digest"]
           and not crlf and not bom
           and manifest["input_count"] == len(INPUTS)
           and manifest["deliverable_count"] == len(MANIFEST_DELIVERABLES))
    add("C08", "manifest 输入/交付哈希与根摘要精确匹配，全部纯 LF 无 BOM", c08,
        "input_bad=%s deliv_bad=%s root=%s crlf=%s bom=%s" % (
            inp_bad[:3], del_bad[:3], root == manifest["manifest_root_digest"], crlf, bom))

    # C09 自检性质与越权
    c09 = (release["decision"] == "APPROVED_TO_START_R00_WITH_LIMITS"
           and release_b2["decision"] == "APPROVED_TO_START_R00_BATCH_02_WITH_LIMITS"
           and release["guards"]["R01_released"] is False
           and release["guards"]["R03_released"] is False
           and release["guards"]["S00_errata_issue_53"] == "OPEN"
           and accept_s08["decision"] == "ACCEPTED_WITH_LIMITS"
           and accept_r02["decision"] == "ACCEPTED_WITH_LIMITS"
           and accept_s08["online_control"]["issue_53_touched"] is False
           and accept_r02["online_control"]["issue_53_touched"] is False)
    add("C09", "放行边界：SELF_CHECK 不冒充独立复核，不越权放行 R01/R03，不触碰 #53", c09,
        "release=%s/%s r01=%s r03=%s issue53=%s" % (
            release["decision"], release_b2["decision"], release["guards"]["R01_released"],
            release["guards"]["R03_released"], release["guards"]["S00_errata_issue_53"]))

    # C10 输入位置
    missing = [p for p in INPUTS if not (REPO / p).exists()]
    escaped = [p for p in INPUTS if p.startswith("/") or ".." in Path(p).parts]
    add("C10", "15 份输入存在且位于 Git 工作树内，无越界路径", not missing and not escaped,
        "inputs=%d missing=%s escaped=%s" % (len(INPUTS), missing, escaped))

    return checks, anomalies


# ---------------------------------------------------------------- main

def main():
    OUT.mkdir(parents=True, exist_ok=True)

    disp = dispatch_rows()
    reg = register_rows()
    q1 = quote_rows("R00_BATCH_01")
    q2 = quote_rows("R00_BATCH_02")

    write_csv(OUT / OUT_DISPATCH, DISPATCH_FIELDS, disp)
    write_csv(OUT / OUT_REGISTER, REGISTER_FIELDS, reg)
    write_csv(OUT / OUT_QUOTES_B1, QUOTE_FIELDS, q1)
    write_csv(OUT / OUT_QUOTES_B2, QUOTE_FIELDS, q2)
    write_json(OUT / OUT_CHILD, child_manifest())
    (OUT / OUT_HANDOFF).write_bytes(build_handoff(reg).encode("utf-8"))

    manifest = build_manifest(0)
    checks, anomalies = build_checks(disp, reg, q1, q2, manifest)

    review = {
        "artifact": "R00_SELF_CHECK_REVIEW",
        "issue_key": ISSUE_KEY,
        "issue_number": ISSUE_NUMBER,
        "child_issue_numbers": [b["spec"]["issue_number"] for b in BATCHES],
        "batch_ids": [b["batch_id"] for b in BATCHES],
        "plan_version": PLAN_VERSION,
        "reviewed_on": TODAY,
        "timezone": "Asia/Shanghai",
        "review_nature": "SELF_CHECK",
        "executor": "CodeBuddy",
        "orchestrator": "Antigravity",
        "reviewer_assigned": "Codex",
        "review_method": ("从原始 Git 跟踪输入独立重算两批名单/互斥性/锚定期/披露日/历史复用/质量项排查/"
                          "引文页码/哈希与口径不变量，逐项比对交付物；不信任构建器布尔值。"),
        "decision_rule": ("anomalies 为空 -> SELF_CHECK_PASS_WITH_LIMITS；"
                          "任一阻塞异常 -> NOT_ACCEPTED_PENDING_FIX"),
        "anomalies": anomalies,
        "decision": "SELF_CHECK_PASS_WITH_LIMITS" if not anomalies else "NOT_ACCEPTED_PENDING_FIX",
        "checks_summary": "%d/%d PASS" % (sum(1 for c in checks if c["result"] == "PASS"), len(checks)),
        "checks": checks,
        "counts": {
            "companies": len(reg),
            "batches": len(BATCHES),
            "batch01_companies": len(BATCH_ORDER["R00_BATCH_01"]),
            "batch02_companies": len(BATCH_ORDER["R00_BATCH_02"]),
            "dispatch_rows": len(disp),
            "register_rows": len(reg),
            "evidence_quote_rows": len(q1) + len(q2),
            "batch01_evidence_quote_rows": len(q1),
            "batch02_evidence_quote_rows": len(q2),
            "quotes_per_company": {s: sum(1 for q in q1 + q2 if q["security_id"] == s)
                                   for s in ORDER},
            "h1_anchor": sum(1 for r in reg if r["anchor_period"] == ANCHOR_H1),
            "m9_anchor": sum(1 for r in reg if r["anchor_period"] == ANCHOR_9M),
        },
        "R01_released": False,
        "R03_released": False,
        "R04_started": False,
        "issue_53_touched": False,
        "issue_53_status": "OPEN",
        "delivery_complete": not anomalies,
        "independent_review_required": True,
        "independent_review_status": "PENDING_CODEX_INDEPENDENT_REVIEW",
        "known_limits_ref": "runs/issues/R00/business_review_register.csv#key_unknowns_and_limits",
    }
    write_json(OUT / OUT_REVIEW, review)

    manifest = build_manifest(len(anomalies))
    write_json(OUT / OUT_MANIFEST, manifest)

    print("R00 build done @", NOW)
    print("dispatch", len(disp), "register", len(reg), "quotes", len(q1), "+", len(q2))
    print("checks", review["checks_summary"], "decision", review["decision"])
    print("manifest_root_digest", manifest["manifest_root_digest"])
    for c in checks:
        if c["result"] != "PASS":
            print("  FAIL", c["id"], c["detail"])
    return 0 if not anomalies else 1


if __name__ == "__main__":
    sys.exit(main())
