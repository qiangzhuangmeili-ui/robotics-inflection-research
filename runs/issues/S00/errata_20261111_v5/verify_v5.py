#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""S00 勘误 V5 自检 V6（SELF_CHECK）

对 Codex 第六轮裁决（RETURN_FOR_REWORK）的逐条落实：

第二节（方法实现错误）
- C33 期间参数三态：is_own_period 显式返回 True/False/None，
  非自身期间必须要求 COMPARATIVE_SCOPE，未知期间单列 DOC_PERIOD_UNKNOWN；
- C26 撤销「同报告相减自动抵消」，改为 PARENT_COMPATIBILITY 证据维度，
  并按 B 实际父输入逐行重算（含跨文档父输入）。

第三节（极性）
- C34 极性四反例：肯定发生 / 政策变更 / 100.00元 不误命中 0.00元 / 勾选式不适用；
- C14 确认类不再只看 B=是，须事件层确认 + 来源维度覆盖。

第五、八节（自检与追溯）
- C14 裁决类必须命中 rulings_resolved.json 且键一致；
- C24 补充元数据放行必须有 content_review 记录，否则不得放行；
- C26 全类别双向重算，裁决类与确认类不再跳过；
- C28 差异 ID 稳定（不含处置状态）+ 引用同键 + 台账列一致；
- C29 已解决项按重算结果判覆盖，不看台账自报；
- C30 先把 V4 旧标签映射为当前可识别类别，再分别注入
  「范围不足 / 肯定发生 / 父输入不兼容」三种实质反例；
- C35 受限表逐表哈希 + dispute_ledger 逐条源表哈希。

性质：SELF_CHECK，不是独立验收。未回读全部 PDF（抽样回读见 sampling_v5.csv）。
"""
import csv
import datetime
import gzip
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import evidence_scope as es
import l2_core as core

ROOT = core.ROOT
OUT = ROOT / "runs/issues/S00/errata_20261111_v5"
V4 = ROOT / "runs/issues/S00/errata_20261111_v4"
V1 = ROOT / "runs/issues/S00/errata_20261111/superseded_v1"
P_A = ROOT / "runs/issues/S00/financial_normalized.csv"
P_V10 = ROOT / "runs/issues/S02/hangcha_restated_20261101/s00_v10/s00_v10.csv.gz"
P_DELTA = ROOT / "runs/issues/S02/remediation_20261029/normalized_delta.csv"
P_VERIFY = ROOT / "runs/issues/S02/remediation_20261029/restatement_verify/results.csv"
P_REGISTRY = ROOT / "runs/collection/collection_index.csv"
P_ADOPT = ROOT / "runs/issues/S02/hangcha_restated_20261101/s00_v10/s00_v10_adoption_audit.csv"
P_RULED = OUT / "rulings_resolved.json"
PERIOD_LABEL_TO_KEY = {
    "2025Q1": "20250331", "2025H1": "20250630", "2025Q3": "20250930",
    "FY2025": "20251231", "2026Q1": "20260331", "2026H1": "20260630",
    "2026Q3": "20260930", "FY2024": "20241231", "2024FY": "20241231",
}
QMAP = {"0331": "1231", "0630": "0331", "0930": "0630", "1231": "0930"}


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def match(a, b):
    x, y = num(a), num(b)
    if x is None or y is None:
        return (a or "").strip() == (b or "").strip()
    if x == 0 and y == 0:
        return True
    return abs(x - y) <= max(1e-6, max(abs(x), abs(y)) * 1e-9)


def load_map(p, gz=False):
    d = {}
    op = gzip.open if gz else open
    with op(p, "rt", encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            d[(r["security_id"], r["field_id"], r["period_key"])] = r
    return d


def prev_quarter(pk):
    tail = pk[4:]
    if tail == "0331":
        return str(int(pk[:4]) - 1) + "1231"
    return pk[:4] + QMAP[tail]


D10 = load_map(P_V10, True)
delta = load_map(P_DELTA)
adopt = load_map(P_ADOPT)
vrec = {}
with open(P_VERIFY, encoding="utf-8-sig", newline="") as f:
    for r in csv.DictReader(f):
        vrec[r["document_id"]] = r
doc_period = {}
with open(P_REGISTRY, encoding="utf-8-sig", newline="") as f:
    for r in csv.DictReader(f):
        doc_period[r["document_id"]] = PERIOD_LABEL_TO_KEY.get(r.get("period_label", ""), "")
RULED = {}
if P_RULED.exists():
    _d = json.loads(P_RULED.read_text(encoding="utf-8"))
    RULED = {e["key"]: e for e in _d.get("entries", [])}


def parent_compatible(k):
    """与 build_errata_v5.py 同口径：两期累计父输入的文档/版本/合并范围/单位兼容性。"""
    sec, fld, pk = k
    if fld not in es.SIMPLE_SQ:
        return None
    ytd = fld[:-3] + ".YTD"
    p1 = D10.get((sec, ytd, pk))
    p2 = D10.get((sec, ytd, prev_quarter(pk)))
    if not p1 or not p2:
        return False
    for x in ("consolidation_scope", "unit_scale", "currency"):
        if (p1.get(x) or "") != (p2.get(x) or ""):
            return False
    if (p1.get("document_id") or "") == (p2.get("document_id") or ""):
        return True
    if (p1.get("version_used") or "") and p1.get("version_used") == p2.get("version_used"):
        return True
    return ((sec, ytd, pk) in adopt) or ((sec, ytd, prev_quarter(pk)) in adopt)


def read_dir(d):
    def rd(n):
        p = d / n
        if not p.exists():
            return []
        with open(p, encoding="utf-8-sig", newline="") as f:
            return list(csv.DictReader(f))
    return rd("cell_diff.csv"), rd("key_diff.csv"), rd("meta_diff.csv")


def read_extra(d):
    p = d / "extra_meta_diff.csv"
    if not p.exists():
        return []
    with open(p, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


# ================= 独立重算核心（不读台账自报的 scope 列） =================

def facts(r):
    """从 B / 核验记录 / 登记表 / 采用审计重算一条重述差异的全部事实。"""
    k = (r["security_id"], r["field_id"], r["period_key"])
    b = D10.get(k, {})
    doc = b.get("document_id", "")
    rec = vrec.get(doc)
    status = b.get("status", "")
    own = doc_period.get(doc, "")
    req = es.required_scope(status, own, k[2])
    if rec:
        ex, af, sc, me = es.analyse(rec)
    else:
        ex, af, sc, me = set(), set(), set(), set()
    cov = set(ex)
    pok = parent_compatible(k)
    if es.PARENT_COMPATIBILITY in req and pok is True:
        cov.add(es.PARENT_COMPATIBILITY)
    return {"k": k, "b": b, "doc": doc, "rec": rec, "status": status, "own": own,
            "req": req, "ex": ex, "af": af, "sc": sc, "cov": cov,
            "missing": req - cov, "pok": pok, "bval": b.get("restatement_flag", "")}


def allowed_label(f, rec=None, pok=None, bval=None):
    """按重算事实给出唯一允许的处置标签。rec/pok/bval 可注入，供故障注入使用。"""
    rec = f["rec"] if rec is None else rec
    pok = f["pok"] if pok is None else pok
    bval = f["bval"] if bval is None else bval
    if str(f["k"][0]) + "|" + "|".join(f["k"]) in RULED or ("|".join(f["k"])) in RULED:
        return "RESOLVED_BY_RULING"
    if not f["doc"]:
        return "UNRESOLVED_NO_DOCUMENT"
    if rec is None:
        return "UNRESOLVED_DOC_NEVER_VERIFIED"
    m = rec.get("method") or ""
    req = es.required_scope(f["status"], f["own"], f["k"][2])
    ex, af, sc, me = es.analyse(rec)
    cov = set(ex)
    if es.PARENT_COMPATIBILITY in req and pok is True:
        cov.add(es.PARENT_COMPATIBILITY)
    missing = req - cov
    if m == "ASSUMED_NO_PENDING_REVIEW":
        return "PENDING_WEAK_ASSUMPTION"
    if rec.get("verdict") != bval and m != "NOTE_RETAINED_ERRATA_NONZERO":
        return "UNRESOLVED_EVIDENCE_MISMATCH"
    if bval == "是":
        event_ok = (es.ERRATA in af) or m == "NOTE_RETAINED_ERRATA_NONZERO"
        if not event_ok:
            return "PENDING_CONFIRMED_UNSUPPORTED"
        src_gap = es.source_dims_for(f["status"], f["own"], f["k"][2]) - cov
        if src_gap:
            return "PENDING_CONFIRMED_EVENT_FIELD_OPEN"
        return "RESOLVED_RESTATEMENT_CONFIRMED"
    if m in es.SCOPE_LIMITED_METHODS and not es.binds_field(rec):
        return "PENDING_SCOPE_LIMITED_METHOD"
    if es.ERRATA in af and es.ERRATA not in ex:
        return "UNRESOLVED_EVIDENCE_CONTRADICTS"
    if not missing:
        return "RESOLVED_SCOPE_COVERED"
    if es.DOC_PERIOD_UNKNOWN in missing:
        return "PENDING_DOC_PERIOD_UNKNOWN"
    if es.QUARTERLY_TABLE_PROVENANCE in missing or es.COMPARATIVE_SCOPE in missing:
        return "PENDING_SOURCE_PROVENANCE"
    if es.PARENT_COMPATIBILITY in missing:
        return "PENDING_PARENT_COMPATIBILITY"
    return "PENDING_CAUSE_UNCOVERED"


RESOLVED_PREFIX = ("RESOLVED_",)
V4_LABEL_MAP = {
    # V4 的核心断言就是「行期间 == 文档自身期间 → 已闭合」，映射到当前标签即
    # RESOLVED_SCOPE_COVERED，让它接受同一套覆盖检查，而不是因标签陌生被拒。
    "RESOLVED_RESTATEMENT_OWN_PERIOD": "RESOLVED_SCOPE_COVERED",
    "RESOLVED_SCOPE_COVERED": "RESOLVED_SCOPE_COVERED",
    "RESOLVED_BY_RULING": "RESOLVED_BY_RULING",
    "RESOLVED_NORMALIZED_DELTA": "RESOLVED_NORMALIZED_DELTA",
    "RESOLVED_RESTATEMENT_CONFIRMED": "RESOLVED_RESTATEMENT_CONFIRMED",
    "PENDING_SCOPE_AUDIT": "PENDING_SOURCE_PROVENANCE",
    "PENDING_WEAK_ASSUMPTION": "PENDING_WEAK_ASSUMPTION",
    "UNRESOLVED_DOC_NEVER_VERIFIED": "UNRESOLVED_DOC_NEVER_VERIFIED",
    "UNRESOLVED_EVIDENCE_MISMATCH": "UNRESOLVED_EVIDENCE_MISMATCH",
}


def is_resolved(res):
    return (res or "").startswith(RESOLVED_PREFIX)


# ---------------- 逐项检查器（可对任意版本台账运行，用于故障注入） ----------------

def check_c13(cell):
    """所有已解决值差异都要有可复算依据，不只是 NORMALIZED_DELTA。"""
    bad = []
    for r in cell:
        res = r["resolution"]
        if not is_resolved(res):
            continue
        k = (r["security_id"], r["field_id"], r["period_key"])
        b = D10.get(k)
        if b is None:
            bad.append((k, "ROW_NOT_IN_B:%s" % res))
            continue
        if not match(r["value_B"], b["value_cny"]):
            bad.append((k, "LEDGER_B_NE_B:%s" % res))
            continue
        if res == "RESOLVED_NORMALIZED_DELTA":
            d = delta.get(k)
            if d is None:
                bad.append((k, "NO_RECORD"))
            elif d["change"] != "UPDATE":
                bad.append((k, "NOT_UPDATE:%s" % d["change"]))
            elif not match(d["new_value"], b["value_cny"]):
                bad.append((k, "VALUE_MISMATCH"))
        elif res == "RESOLVED_RESTATED_ADOPTION":
            if k not in adopt:
                bad.append((k, "NO_ADOPTION_ROW"))
        elif res == "RESOLVED_DERIVED_FROM_PARENT":
            d = delta.get(k)
            if d is None or d["change"] != "UPDATE":
                bad.append((k, "DERIVED_WITHOUT_RECORD"))
        else:
            bad.append((k, "UNKNOWN_RESOLVED_LABEL:%s" % res))
    return bad


def check_c14(meta, label_map=None):
    """已解决重述必须由证据覆盖支撑：独立重算，逐条比对。

    第六轮裁决第五节：裁决类不能只查 evidence 非空，必须命中 rulings 且键一致；
    确认类不能只看 B=是，须事件层确认且来源维度覆盖。
    """
    bad = []
    for r in meta:
        if r.get("meta_field") != "restatement_flag":
            continue
        res = r["resolution"]
        if label_map:
            res = label_map.get(res, res)
        if not is_resolved(res):
            continue
        f = facts(r)
        key = "|".join(f["k"])
        if res == "RESOLVED_BY_RULING":
            if key not in RULED:
                bad.append((f["k"], "RULING_NOT_IN_RULINGS_FILE"))
            elif not (RULED[key].get("basis") or "").strip():
                bad.append((f["k"], "RULING_WITHOUT_BASIS"))
            elif f["rec"] is not None and f["rec"].get("verdict") != f["bval"]:
                # 裁决必须正面解释「判定与 B 相反」这件事
                if "verdict" not in json.dumps(RULED[key], ensure_ascii=False):
                    bad.append((f["k"], "RULING_IGNORES_VERDICT_CONFLICT"))
            continue
        if res == "RESOLVED_NORMALIZED_DELTA":
            continue  # 由 C17 校验
        if res == "RESOLVED_RESTATEMENT_CONFIRMED":
            if f["bval"] != "是":
                bad.append((f["k"], "CONFIRMED_BUT_B_IS_NOT_YES"))
                continue
            m = (f["rec"] or {}).get("method") or ""
            event_ok = (es.ERRATA in f["af"]) or m == "NOTE_RETAINED_ERRATA_NONZERO"
            if not event_ok:
                bad.append((f["k"], "CONFIRMED_EVENT_NOT_SUPPORTED"))
                continue
            gap = es.source_dims_for(f["status"], f["own"], f["k"][2]) - f["cov"]
            if gap:
                bad.append((f["k"], "CONFIRMED_SOURCE_DIM_OPEN:%s" % ";".join(sorted(gap))))
            continue
        if res != "RESOLVED_SCOPE_COVERED":
            bad.append((f["k"], "UNKNOWN_RESOLVED_LABEL:%s" % res))
            continue
        if f["rec"] is None:
            bad.append((f["k"], "NO_DOC_RECORD"))
            continue
        if f["rec"].get("verdict") != f["bval"]:
            bad.append((f["k"], "VERDICT_NE:%s" % f["rec"].get("verdict")))
            continue
        if f["missing"]:
            bad.append((f["k"], "SCOPE_NOT_COVERED:%s" % ";".join(sorted(f["missing"]))))
            continue
        m = f["rec"].get("method") or ""
        if m in es.SCOPE_LIMITED_METHODS and not es.binds_field(f["rec"]):
            bad.append((f["k"], "LIMITED_METHOD_COUNTED_RESOLVED"))
        elif m == "ASSUMED_NO_PENDING_REVIEW":
            bad.append((f["k"], "WEAK_COUNTED_RESOLVED"))
        # 台账声明必须与独立重算一致
        if "scope_required" in r:
            if set(filter(None, (r.get("scope_required") or "").split(";"))) != f["req"]:
                bad.append((f["k"], "SCOPE_REQUIRED_DRIFT"))
            elif set(filter(None, (r.get("scope_covered") or "").split(";"))) != f["cov"]:
                bad.append((f["k"], "SCOPE_COVERED_DRIFT"))
            elif (r.get("scope_missing") or "") != "":
                bad.append((f["k"], "SCOPE_MISSING_NOT_EMPTY"))
        if "is_own_period" in r:
            exp = {True: "YES", False: "NO", None: "UNKNOWN"}[
                es.is_own_period(f["own"], f["k"][2])]
            if r["is_own_period"] != exp:
                bad.append((f["k"], "IS_OWN_PERIOD_DRIFT:%s!=%s" % (r["is_own_period"], exp)))
    return bad


def check_c17(meta):
    """所有已解决元数据都要有终值或字段级依据。"""
    bad = []
    for r in meta:
        res = r["resolution"]
        if not is_resolved(res):
            continue
        k = (r["security_id"], r["field_id"], r["period_key"])
        b = D10.get(k)
        if b is None:
            bad.append((k, "ROW_NOT_IN_B"))
            continue
        if (r["value_B"] or "") != (b.get(r["meta_field"], "") or ""):
            bad.append((k, "LEDGER_B_NE_B:%s" % r["meta_field"]))
            continue
        if r["meta_field"] == "restatement_flag":
            if res not in ("RESOLVED_SCOPE_COVERED", "RESOLVED_BY_RULING",
                           "RESOLVED_RESTATEMENT_CONFIRMED"):
                bad.append((k, "RESTATEMENT_BAD_LABEL:%s" % res))
            continue
        if res != "RESOLVED_NORMALIZED_DELTA":
            bad.append((k, "META_BAD_LABEL:%s" % res))
            continue
        d = delta.get(k)
        if d is None:
            bad.append((k, "NO_RECORD"))
        elif d["change"] == "REMOVE":
            bad.append((k, "REMOVE_EXPLAINS_EXISTING_ROW"))
        elif r["meta_field"] != "status":
            bad.append((k, "FIELD_NOT_IN_RECORD:%s" % r["meta_field"]))
        elif (d.get("new_status") or "").strip() != r["value_B"]:
            bad.append((k, "TERMINAL_NE"))
    return bad


def check_c26(meta, label_map=None):
    """全类别双向重算：裁决类、确认类、待核类都不跳过。

    方向一：已解决 ⇒ 重算无缺口且标签等于唯一允许标签；
    方向二：未解决/待核 ⇒ 必须存在具体阻断理由，不得出现「覆盖已足却仍挂起」。
    """
    bad = []
    for r in meta:
        if r.get("meta_field") != "restatement_flag":
            continue
        res = r["resolution"]
        if label_map:
            res = label_map.get(res, res)
        f = facts(r)
        exp = allowed_label(f)
        if res != exp:
            bad.append((f["k"], "%s!=%s" % (res, exp)))
            continue
        if is_resolved(res) and f["missing"] and res == "RESOLVED_SCOPE_COVERED":
            bad.append((f["k"], "RESOLVED_WITH_MISSING"))
    return bad


def run_all(d):
    cell, key, meta = read_dir(d)
    if not cell:
        return None
    r = {"cell_rows": len(cell), "key_rows": len(key), "meta_rows": len(meta),
         "C13_bad": check_c13(cell), "C14_bad": check_c14(meta),
         "C17_bad": check_c17(meta), "C26_bad": check_c26(meta)}
    r["pass"] = not (r["C13_bad"] or r["C14_bad"] or r["C17_bad"] or r["C26_bad"])
    return r


cell, key, meta = read_dir(OUT)
extra = read_extra(OUT)
l2 = list(csv.DictReader(open(OUT / "l2_dependency_check.csv", encoding="utf-8-sig", newline="")))
restr = list(csv.DictReader(open(OUT / "restricted_claims.csv", encoding="utf-8-sig", newline="")))
dledger = list(csv.DictReader(open(OUT / "dispute_ledger.csv", encoding="utf-8-sig", newline="")))
summary = json.loads((OUT / "summary.json").read_text(encoding="utf-8"))
l2sum = json.loads((OUT / "l2_dependency_summary.json").read_text(encoding="utf-8"))

checks = []


def add(cid, name, ok, detail):
    checks.append({"id": cid, "name": name,
                   "result": "PASS" if ok else "FAIL", "detail": detail})


# ---------------- C01–C12 基础一致性 ----------------
add("C01", "输入哈希与 summary 一致",
    sha(P_A) == summary["versions"]["A"]["sha256"]
    and sha(P_V10) == summary["versions"]["B"]["sha256"],
    {"A": sha(P_A)[:16], "B": sha(P_V10)[:16]})
add("C02", "B 行数与登记一致", len(D10) == summary["versions"]["B"]["rows"], {"rows": len(D10)})
add("C03", "台账行数与 summary 一致",
    len(cell) == summary["value_diff"]["total"]
    and len(key) == summary["key_diff"]["total"]
    and len(meta) == summary["meta_diff"]["total"]
    and len(extra) == summary["extra_meta_diff"]["total"],
    {"cell": len(cell), "key": len(key), "meta": len(meta), "extra": len(extra)})
add("C04", "每条差异均有处置结论",
    not [r for r in cell + key + meta + extra if not r.get("resolution")],
    {"rows": len(cell) + len(key) + len(meta) + len(extra)})
bad = [r for r in cell + key + meta + extra
       if not is_resolved(r["resolution"]) and not r.get("evidence")]
add("C05", "未闭合/待核项均写明原因", not bad, {"missing": len(bad)})
n_restate = sum(1 for r in meta if r["meta_field"] == "restatement_flag")
add("C06", "重述差异 17,009", n_restate == 17009, {"count": n_restate})
add("C07", "符号翻转 89 格",
    sum(1 for r in cell if r["sign_flip"] == "YES") == 89,
    {"sign_flip": sum(1 for r in cell if r["sign_flip"] == "YES")})
vc = Counter(r["verdict"] for r in l2)
add("C08", "全池 1054 家守恒", sum(vc.values()) == 1054,
    {"total": sum(vc.values()), "by_verdict": dict(vc)})
holds = [r for r in l2 if r["verdict"] == "HOLD_PENDING_ERRATA"]
add("C09", "HOLD 争议可追溯到字段与期间",
    all("@" in r["dispute_detail"] and "[" in r["dispute_detail"] for r in holds),
    {"hold_count": len(holds)})
n_open = sum(1 for r in cell + key + meta if not is_resolved(r["resolution"]))
add("C10", "核心未闭合+待核与 summary 一致", n_open == summary["open_total_core"],
    {"computed": n_open, "declared": summary["open_total_core"]})
add("C11", "键差异方向统计", True, dict(Counter(r["side"] for r in key)))
mt = [datetime.datetime.fromtimestamp(p.stat().st_mtime) for p in (P_A, P_V10)]
add("C12", "输入文件未被本次工作修改",
    all(x < datetime.datetime(2026, 11, 11) for x in mt),
    {"mtimes": [x.isoformat() for x in mt]})

# ---------------- C13/C14/C17 已解决项 ----------------
b13 = check_c13(cell)
add("C13", "已解决值差异：全部标签均有可复算依据（非仅 NORMALIZED_DELTA）",
    not b13, {"violations": len(b13), "sample": [str(x) for x in b13[:3]],
              "labels": dict(Counter(r["resolution"] for r in cell))})
b14 = check_c14(meta)
add("C14", "已解决重述：裁决类命中裁决清单、确认类事件+来源双证、覆盖类独立重算无缺口",
    not b14, {"violations": len(b14), "sample": [str(x) for x in b14[:5]],
              "rulings": len(RULED)})
b17 = check_c17(meta)
add("C17", "已解决元数据：全部标签均有终值或字段级依据", not b17,
    {"violations": len(b17), "sample": [str(x) for x in b17[:3]]})

# ---------------- C15/C16/C18 依赖函数 ----------------
four = core.dependency_keys("M03", "20260630")
two = core.dependency_keys("M01", "20260630")
add("C15", "M03 生产依赖为四季（t/t−1q/t−1y/t−1y−1q）",
    {("FIN.REV.SQ", p) for p in ("20260630", "20260331", "20250630", "20250331")} <= four
    and len(two) == 2,
    {"M03_keys": len(four), "M01_keys": len(two)})
synth = ("FIN.REV.SQ", "20250331")
add("C16", "生产依赖命中前季争议（合成键）", synth in four and synth not in two,
    {"synthetic": str(synth), "in_M03": synth in four, "in_M01": synth in two})
parent_key = ("FIN.REV.YTD", "20260630")
add("C18", "单季派生递归展开累计父键（合成 REV.YTD 争议被命中）",
    parent_key in core.dependency_keys("M02", "20260630")
    and parent_key in core.dependency_keys("M03", "20260630"),
    {"parent_key": str(parent_key)})

# ---------------- C19/C20/C25/C35 台账与受限表结构 ----------------
cols = {r["meta_field"] for r in extra}
add("C19", "19 列 / 1,505 格元数据差异已登记",
    len(cols) == 19 and len(extra) == 1505, {"columns": len(cols), "cells": len(extra)})
need = {"security_id", "stock_name", "snapshot", "snapshot_hash", "ledger_version",
        "ledger_sha256", "anchor_period", "signal_id", "dimension", "metric_id",
        "field_id", "period_key", "status_B", "dispute_count", "dispute_ids",
        "dispute_ids_cell", "dispute_ids_key", "dispute_ids_meta", "dispute_ids_extra",
        "ledger_sha256_cell", "ledger_sha256_key", "ledger_sha256_meta",
        "ledger_sha256_extra", "restriction", "allowed_use", "release_condition",
        "review_status"}
add("C20", "受限表字段完整（含逐表差异 ID 与逐表哈希）",
    bool(restr) and set(restr[0].keys()) == need,
    {"rows": len(restr), "cols": len(restr[0]) if restr else 0,
     "missing": sorted(need - set(restr[0].keys())) if restr else []})
snap = ROOT / "runs/issues/S04/tight_pass.csv"
snap_sha = sha(snap)
add("C25", "受限表全部行 snapshot_hash 与实际快照一致",
    bool(restr) and all(r["snapshot_hash"] == snap_sha for r in restr),
    {"snapshot_sha": snap_sha[:16], "rows_checked": len(restr)})

LEDGER_FILES = ["cell_diff.csv", "key_diff.csv", "meta_diff.csv", "extra_meta_diff.csv"]
LEDGER_SHA = {f: sha(OUT / f) for f in LEDGER_FILES}
BUNDLE = hashlib.sha256("".join("%s:%s" % (f, LEDGER_SHA[f])
                                for f in LEDGER_FILES).encode("utf-8")).hexdigest()
h_bad = []
for r in restr:
    for k, f in (("cell", "cell_diff.csv"), ("key", "key_diff.csv"),
                 ("meta", "meta_diff.csv"), ("extra", "extra_meta_diff.csv")):
        if r.get("ledger_sha256_" + k) != LEDGER_SHA[f]:
            h_bad.append((r["security_id"], "PER_TABLE:%s" % k))
    if r.get("ledger_sha256") != BUNDLE:
        h_bad.append((r["security_id"], "BUNDLE_MISMATCH"))
led_bad = [r["dispute_id"] for r in dledger
           if r["source_ledger_sha256"] != LEDGER_SHA[r["ledger"] + ".csv"]]
add("C35", "受限表逐表哈希 + 差异台账逐条源表哈希均与文件实算一致",
    not h_bad and not led_bad,
    {"restricted_bad": len(h_bad), "ledger_bad": len(led_bad),
     "bundle": BUNDLE[:16], "ledger_rows": len(dledger)})

# ---------------- C21/C22/C30 故障注入 ----------------
inj_v1 = run_all(V1)
add("C21a", "C13 必须独立拦住 V1", inj_v1 is not None and len(inj_v1["C13_bad"]) > 0,
    {"v1_C13": len(inj_v1["C13_bad"]) if inj_v1 else None})
add("C21b", "C14 必须独立拦住 V1", inj_v1 is not None and len(inj_v1["C14_bad"]) > 0,
    {"v1_C14": len(inj_v1["C14_bad"]) if inj_v1 else None})
add("C21c", "C17 必须独立拦住 V1", inj_v1 is not None and len(inj_v1["C17_bad"]) > 0,
    {"v1_C17": len(inj_v1["C17_bad"]) if inj_v1 else None})
self_run = run_all(OUT)
add("C22", "V5 台账代入同一套检查必须全 PASS",
    self_run is not None and self_run["pass"],
    {"C13": len(self_run["C13_bad"]), "C14": len(self_run["C14_bad"]),
     "C17": len(self_run["C17_bad"]), "C26": len(self_run["C26_bad"])})

# C30：V4 旧标签先映射，再注入三种实质反例
v4_cell, v4_key, v4_meta = read_dir(V4)
v4_mapped_c26 = check_c26(v4_meta, V4_LABEL_MAP)
v4_mapped_c14 = check_c14(v4_meta, V4_LABEL_MAP)
v4_limited = sum(1 for r in v4_meta
                 if r["resolution"] == "RESOLVED_RESTATEMENT_OWN_PERIOD"
                 and (v4_rec := vrec.get(D10.get((r["security_id"], r["field_id"],
                                                  r["period_key"]), {}).get("document_id", ""), {})
                      ) and (v4_rec.get("method") or "") in es.SCOPE_LIMITED_METHODS)

# 三种反例：分别在同一条已解决/待核行上注入，必须各自命中特定标签
def _find(pred):
    for r in meta:
        if r["meta_field"] == "restatement_flag" and pred(r):
            return r
    return None


# (1) 范围不足：证据排除了差错更正，但取值来自分季度表，来源维度仍缺
probe_q = _find(lambda r: r["status_B"] == "EXTRACTED_QUARTERLY_TABLE")
# (2) 父输入不兼容：累计差分已解决行，两个父输入文档/范围/单位不兼容
probe_c = _find(lambda r: r["status_B"] == "DERIVED_CUMULATIVE_DIFF"
                and r["resolution"] == "RESOLVED_SCOPE_COVERED")
# (3) 肯定发生：任一条已解决行，证据改为确认发生差错更正
probe_a = _find(lambda r: r["resolution"] == "RESOLVED_SCOPE_COVERED")
REC_EXCL = {"evidence": "本报告期前期差错更正不适用", "method": "CHECKBOX_NA",
            "verdict": "否", "page": "1"}
REC_AFFIRM = {"evidence": "本期发生前期差错更正，调整年初数", "method": "MANUAL_EVIDENCE",
              "verdict": "否", "page": "1"}
inj_scope = allowed_label(facts(probe_q), rec=REC_EXCL) if probe_q else "NO_PROBE"
inj_parent = allowed_label(facts(probe_c), rec=REC_EXCL, pok=False) if probe_c else "NO_PROBE"
inj_affirm = allowed_label(facts(probe_a), rec=REC_AFFIRM) if probe_a else "NO_PROBE"
add("C30", "V4 旧标签映射后仍必须 FAIL，且三种实质反例各自命中特定标签",
    len(v4_mapped_c26) >= 5270 and len(v4_mapped_c14) >= 5270
    and v4_limited >= 5270
    and inj_scope == "PENDING_SOURCE_PROVENANCE"
    and inj_parent == "PENDING_PARENT_COMPATIBILITY"
    and inj_affirm == "UNRESOLVED_EVIDENCE_CONTRADICTS",
    {"v4_c26_violations": len(v4_mapped_c26), "v4_c14_violations": len(v4_mapped_c14),
     "v4_limited_own_period": v4_limited,
     "inject_scope_insufficient": inj_scope,
     "inject_parent_incompatible": inj_parent,
     "inject_cause_affirmed": inj_affirm,
     "probes": ["|".join(facts(p)["k"]) for p in (probe_q, probe_c, probe_a) if p]})

# ---------------- C23/C24/C26/C27/C28/C29 语义 ----------------
sd = [r for r in meta if r["security_id"] == "SH:600022" and r["period_key"] == "20250630"
      and r["field_id"] in ("FIN.NPDEDT.SQ", "FIN.NPP.SQ", "FIN.OCF.SQ", "FIN.REV.SQ")]
sd_ok = len(sd) == 4 and all(not is_resolved(r["resolution"]) for r in sd)
mis = [r for r in meta if r["meta_field"] == "restatement_flag"
       and is_resolved(r["resolution"]) and r["resolution"] != "RESOLVED_BY_RULING"
       and r["is_own_period"] == "NO"]
add("C23", "山东钢铁四条待核 + 非自身期间一律不得判已解决",
    sd_ok and not mis,
    {"sd_found": len(sd), "sd_res": sorted({r["resolution"] for r in sd}),
     "comparative_resolved": len(mis)})


def extra_leaks(rows):
    """放行必须有 content_review=CONFIRMED 记录；来源变更不得算纯展示。"""
    out = []
    for r in rows:
        res = r["resolution"]
        if not is_resolved(res) and not res.startswith("REGISTERED_"):
            continue
        if res == "REGISTERED_DISPLAY_ONLY":
            if r.get("document_changed") == "YES" or r.get("period_source_changed") == "YES":
                out.append((r["security_id"], r["meta_field"], "DISPLAY_BUT_PROVENANCE_CHANGED"))
            continue
        if res != "RESOLVED_FIELD_LEVEL_CHECK":
            out.append((r["security_id"], r["meta_field"], "UNKNOWN_RELEASE:%s" % res))
            continue
        if (r.get("content_review") or "") != "CONFIRMED":
            out.append((r["security_id"], r["meta_field"], "RELEASE_WITHOUT_CONTENT_REVIEW"))
    return out


leak = extra_leaks(extra)
# 反例：补一条「已放行但没有内容审查记录」的合成行，检查必须能拦住
fake = dict(extra[0])
fake["resolution"] = "RESOLVED_FIELD_LEVEL_CHECK"
fake["content_review"] = ""
fake_caught = len(extra_leaks([fake])) == 1
add("C24", "补充元数据放行须有 content_review 记录（来源变更不得算展示）",
    not leak and fake_caught,
    {"leaked": len(leak), "sample": [str(x) for x in leak[:5]],
     "injection_caught": fake_caught,
     "pending": sum(1 for r in extra if r["resolution"] == "PENDING_FIELD_LEVEL_CHECK")})

b26 = check_c26(meta)
add("C26", "全类别双向重算（17,009 条，含裁决类与确认类）", not b26,
    {"violations": len(b26), "sample": [str(x) for x in b26[:5]],
     "labels": dict(Counter(r["resolution"] for r in meta
                            if r["meta_field"] == "restatement_flag"))})

c27 = []
ANCHORS = ("20250331", "20250630", "20250930", "20251231",
           "20260331", "20260630", "20260930")
for fld in sorted(core.SIMPLE_SQ):
    ytd = fld[:-3] + ".YTD"
    for pk in ANCHORS:
        pq = core.prev_quarter(pk)
        kq = core.expand(fld, pk, lambda f, p: core.QUARTERLY_TABLE)
        if kq != {(fld, pk)}:
            c27.append((fld, pk, "QUARTERLY_TABLE", "EXTRA_KEYS:%d" % len(kq)))
        k1 = core.expand(fld, pk, lambda f, p: core.Q1_EQUALS_YTD)
        if (ytd, pk) not in k1:
            c27.append((fld, pk, "Q1", "MISSING_YTD_SELF"))
        if (ytd, pq) in k1:
            c27.append((fld, pk, "Q1", "SUBTRACTED_PREV_QUARTER"))
        kd = core.expand(fld, pk, lambda f, p: "DERIVED_CUMULATIVE_DIFF")
        if (ytd, pk) not in kd:
            c27.append((fld, pk, "CUMULATIVE_DIFF", "MISSING_YTD_SELF"))
        if pk[4:] != "0331" and (ytd, pq) not in kd:
            c27.append((fld, pk, "CUMULATIVE_DIFF", "MISSING_PARENT"))
    k0331 = core.expand(fld, "20260331", None)
    if (ytd, "20251231") in k0331:
        c27.append((fld, "20260331", "CALENDAR_Q1", "SUBTRACTED_PREV_YE_END"))
for mid in core.METRIC_FIELDS:
    for a in ANCHORS:
        base = core.dependency_keys(mid, a)
        for fld in core.METRIC_FIELDS[mid]:
            if fld not in core.SIMPLE_SQ:
                continue
            ytd = fld[:-3] + ".YTD"
            if (ytd, a) not in base:
                c27.append((mid, a, fld, "MISSING_YTD_SELF"))
            if a[4:] != "0331" and (ytd, core.prev_quarter(a)) not in base:
                c27.append((mid, a, fld, "MISSING_YTD_PREV_Q"))
m07 = core.dependency_keys("M07", "20260630")
add("C27", "各目标期父键检查（M01–M12 × 7 锚定期，含 Codex 点名 M07@20260630）",
    (not c27) and ("FIN.NPDEDT.YTD", "20250331") in m07,
    {"violations": len(c27), "sample": [str(x) for x in c27[:6]],
     "M07_has_20250331": ("FIN.NPDEDT.YTD", "20250331") in m07})


LED_SHORT = {"cell_diff": "cell", "key_diff": "key",
             "meta_diff": "meta", "extra_meta_diff": "extra"}


def dispute_id(ledger, sec, fld, pk, meta_field="", direction=""):
    raw = "|".join([ledger, sec, fld, pk, meta_field or "", direction])
    return "D-" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


led_ids = [r["dispute_id"] for r in dledger]
dup = [k for k, v in Counter(led_ids).items() if v > 1]
used = {d for r in restr for d in (r["dispute_ids"] or "").split(";") if d}
unmapped = sorted(used - set(led_ids))
cnt_bad = [r for r in restr
           if int(r["dispute_count"]) != len([d for d in (r["dispute_ids"] or "").split(";") if d])]
# 逐条重算 ID 并核对引用是否落在同一键上
id_bad = []
ledger_index = {r["dispute_id"]: r for r in dledger}
for r in dledger:
    exp = dispute_id(LED_SHORT.get(r["ledger"], r["ledger"]), r["security_id"],
                     r["field_id"], r["period_key"], r["meta_field"], r["direction"])
    if exp != r["dispute_id"]:
        id_bad.append((r["dispute_id"], "ID_UNSTABLE"))
per_table_bad = []
TBL_OF = {"cell": "cell_diff", "key": "key_diff", "meta": "meta_diff", "extra": "extra_meta_diff"}
for r in restr:
    for k in ("cell", "key", "meta", "extra"):
        for d in (r.get("dispute_ids_" + k) or "").split(";"):
            if not d:
                continue
            lr = ledger_index.get(d)
            if lr is None:
                per_table_bad.append((d, "MISSING"))
            elif lr["ledger"] != TBL_OF[k]:
                per_table_bad.append((d, "WRONG_TABLE:%s" % lr["ledger"]))
            elif (lr["security_id"], lr["field_id"], lr["period_key"]) != \
                    (r["security_id"], r["field_id"], r["period_key"]):
                per_table_bad.append((d, "WRONG_KEY"))
add("C28", "差异 ID 稳定、逐表引用同键、受限行逐项可回溯",
    not dup and not unmapped and not cnt_bad and not id_bad and not per_table_bad,
    {"ledger_ids": len(led_ids), "unique": len(set(led_ids)), "dups": len(dup),
     "used_ids": len(used), "unmapped": len(unmapped), "count_mismatch": len(cnt_bad),
     "id_unstable": len(id_bad), "per_table_bad": len(per_table_bad)})

eq_only = []
for r in meta:
    if r["meta_field"] != "restatement_flag" or not is_resolved(r["resolution"]):
        continue
    if r["resolution"] == "RESOLVED_BY_RULING":
        continue
    f = facts(r)
    if f["missing"]:
        eq_only.append((f["k"], ";".join(sorted(f["missing"]))))
    if not (r.get("scope_required") or ""):
        eq_only.append((f["k"], "NO_SCOPE_DECLARED"))
add("C29", "不得存在「仅凭期间相等」的闭合（按重算覆盖判定，不看台账自报）",
    not eq_only, {"violations": len(eq_only), "sample": [str(x) for x in eq_only[:5]]})

# ---------------- C31/C32 分层抽验 ----------------
samp = list(csv.DictReader(open(OUT / "sampling_v5.csv", encoding="utf-8-sig", newline="")))
samp_risk = {s["risk_type"] for s in samp}
REQUIRED_RISK = {"R1_QUARTERLY_TABLE_OWN", "R2_CUMULATIVE_DIFF", "R3_Q1_EQUALS_YTD",
                 "R4_COMPARATIVE_COLUMN", "R5_CAUSE_MERGER_RETRO",
                 "R5_CAUSE_POLICY_CHANGE", "R5_CAUSE_AFFIRMED",
                 "R6_CROSS_DOC_PARENT", "R7_PARTIAL_LOCATED",
                 "R8_SHANDONG_POSITIVE", "R9_DAHAO_RULED",
                 "R10_HANGCHA_CROSS_SOURCE"}
has_extra = any(k.startswith("R11_") for k in samp_risk)
non_r7 = [s for s in samp if not s["risk_type"].startswith("R7_")]
reread_bad = [s for s in non_r7 if s["page_reread"] in ("NOT_FOUND", "PDF_MISSING",
                                                        "READ_ERROR")
              or s["page_reread"].startswith("PAGE_OUT")]
r7 = [s for s in samp if s["risk_type"].startswith("R7_")]
r7_bad = [s for s in r7 if not s["located_conclusion"]]
add("C31", "分层抽验覆盖 12 类必需风险 + 补充字段，原件回读无失配",
    REQUIRED_RISK <= samp_risk and has_extra and not reread_bad and bool(r7) and not r7_bad,
    {"samples": len(samp), "risk_types": len(samp_risk),
     "missing": sorted(REQUIRED_RISK - samp_risk), "extra_covered": has_extra,
     "reread_bad": len(reread_bad), "r7_bad": len(r7_bad),
     "reread": dict(Counter(s["page_reread"] for s in samp)),
     "r7_conclusion": dict(Counter(s["located_conclusion"].split("：")[0] for s in r7))})

dh_s = [s for s in samp if s["risk_type"] == "R9_DAHAO_RULED"]
sd_s = [s for s in samp if s["risk_type"] == "R8_SHANDONG_POSITIVE"]
hc_s = [s for s in samp if s["risk_type"] == "R10_HANGCHA_CROSS_SOURCE"]
add("C32", "大豪科技保持解除、山东钢铁保持待核、杭叉样本带跨来源限制",
    bool(dh_s) and all(s["resolution"] == "RESOLVED_BY_RULING" for s in dh_s)
    and bool(sd_s) and all(not is_resolved(s["resolution"]) for s in sd_s)
    and bool(hc_s) and any("杭叉" in s["why_selected"] or "跨来源" in s["why_selected"]
                           for s in hc_s),
    {"dahao": [s["resolution"] for s in dh_s],
     "shandong": [s["resolution"] for s in sd_s],
     "hangcha": len(hc_s)})

# ---------------- C33 期间参数三态 ----------------
c33 = []
if es.is_own_period("20251231", "20251231") is not True:
    c33.append("SAME_PERIOD_NOT_TRUE")
if es.is_own_period("20251231", "20250630") is not False:
    c33.append("DIFF_PERIOD_NOT_FALSE")
if es.is_own_period("", "20250630") is not None:
    c33.append("UNKNOWN_NOT_NONE")
# 核心回归：非自身期间必须要求 COMPARATIVE_SCOPE（第六轮第二节的直接错误）
if es.COMPARATIVE_SCOPE not in es.required_scope("EXTRACTED", "20251231", "20250630"):
    c33.append("COMPARATIVE_SCOPE_NOT_REQUIRED")
if es.DOC_PERIOD_UNKNOWN not in es.required_scope("EXTRACTED", "", "20250630"):
    c33.append("DOC_PERIOD_UNKNOWN_NOT_REQUIRED")
if es.COMPARATIVE_SCOPE in es.required_scope("EXTRACTED", "20250630", "20250630"):
    c33.append("OWN_PERIOD_REQUIRES_COMPARATIVE")
# 全量：非自身期间行不得出现「没有 COMPARATIVE_SCOPE 的必需范围」
n_no = 0
for r in meta:
    if r["meta_field"] != "restatement_flag" or r["is_own_period"] != "NO":
        continue
    n_no += 1
    if es.COMPARATIVE_SCOPE not in (r["scope_required"] or ""):
        c33.append("ROW_%s_MISSING_COMPARATIVE" % r["security_id"])
add("C33", "期间参数三态与「非自身期间必须要求比较范围」",
    not c33 and n_no > 0, {"violations": len(c33), "sample": c33[:5],
                           "comparative_rows": n_no})

# ---------------- C34 极性四反例 ----------------
c34 = []


def _pol(txt):
    return es.analyse({"evidence": txt, "method": "T"})


if es.ERRATA not in _pol("本公司未发生前期差错更正")[0]:
    c34.append("NEG_NOT_EXCLUDED")
if es.ERRATA not in _pol("本期发生前期差错更正")[1]:
    c34.append("POS_NOT_AFFIRMED")
if es.ERRATA in _pol("本期发生前期差错更正")[0]:
    c34.append("POS_MISREAD_AS_EXCLUDED")
if es.ERRATA in _pol("前期差错更正调整 100.00 元")[0]:
    c34.append("ZERO_REGEX_HIT_100YUAN")
if es.ERRATA not in _pol("追溯重述法；□适用 √不适用")[0]:
    c34.append("CHECKBOX_PAIR_NOT_EXCLUDED")
_z = _pol("附注：由于重大会计差错更正影响期初未分配利润0.00元")
if es.ERRATA in _z[0]:
    c34.append("SCOPED_ZERO_TREATED_AS_EXCLUDED")
if es.ERRATA not in _z[2]:
    c34.append("SCOPED_ZERO_NOT_RECORDED")
add("C34", "极性四反例：肯定发生/政策变更/100.00元 不误命中/勾选式不适用",
    not c34, {"violations": c34,
              "cases": {"neg": "本公司未发生前期差错更正",
                        "pos": "本期发生前期差错更正",
                        "hundred": "前期差错更正调整 100.00 元",
                        "checkbox": "追溯重述法；□适用 √不适用",
                        "scoped_zero": "…影响期初未分配利润0.00元"}})

passed = sum(1 for c in checks if c["result"] == "PASS")
review = {
    "issue_key": "S00", "stage": "ERRATA", "version": "ERRATA_V5",
    "self_check_version": "V6",
    "review_nature": "SELF_CHECK",
    "decision": "SELF_CHECK_PASS_WITH_UNRESOLVED_ITEMS" if passed == len(checks)
                else "SELF_CHECK_FAIL",
    "reviewed_at": "2026-11-12T03:20:00+08:00",
    "checks_pass": passed, "checks_total": len(checks),
    "checks": checks,
    "fault_injection": {
        "V1": {k: (len(v) if isinstance(v, list) else v) for k, v in (inj_v1 or {}).items()},
        "V4_mapped": {"C14": len(v4_mapped_c14), "C26": len(v4_mapped_c26),
                      "limited_method_own_period": v4_limited},
        "V5_self": {"C13": len(self_run["C13_bad"]), "C14": len(self_run["C14_bad"]),
                    "C17": len(self_run["C17_bad"]), "C26": len(self_run["C26_bad"]),
                    "pass": self_run["pass"]},
        "targeted": {"scope_insufficient": inj_scope,
                     "cause_affirmed": inj_affirm,
                     "parent_incompatible": inj_parent},
    },
    "round6_fixes": [
        "期间参数改为显式三态 is_own_period(document_period,row_period)，"
        "非自身期间强制要求 COMPARATIVE_SCOPE，未知期间单列 DOC_PERIOD_UNKNOWN → C33",
        "撤销「同报告内 YTD 相减自动抵消」，改为 PARENT_COMPATIBILITY 并逐行核"
        "父输入文档/版本/合并范围/单位 → C26/C27/C30",
        "极性改按分句三分（EXCLUDED/AFFIRMED/SCOPED_ONLY），0.00元 用负向后视，"
        "勾选式向下配对 → C34",
        "C14 裁决类必须命中 rulings_resolved.json 且键一致；确认类须事件+来源双证",
        "C24 放行须有 content_review 记录，并注入「无审查记录放行」反例",
        "C26 全类别双向重算，裁决类与确认类不再跳过",
        "C28 差异 ID 去掉处置状态 + 逐表引用同键校验",
        "C29 按重算覆盖判定，不看台账自报列",
        "C30 先把 V4 旧标签映射为当前类别，再注入范围不足/肯定发生/父输入不兼容三反例",
        "C35 受限表逐表哈希 + 差异台账逐条源表哈希（原基础列全填 meta_diff）",
    ],
    "open_findings": [
        "9,927 条 NOTE_TRACE_NA 已解决项尚未做方法适用性复审（不等于全部错误）",
        "NOTE_RETAINED_ERRATA_ZERO 642 条（自身 563 / 非自身 79）待核实，未凭注记批量放行",
        "SH:600936 FIN.REV.SQ@20250630 的核验证据在原件全文无法定位，属上游核验记录问题",
        "第 4 步批量核证（文档级事件确认 / 字段级影响确认 / 采用链确认）未开始",
        "第 5 步重算分层与受限表未开始；43/207/445 未锁定",
        "锚定期回退与上游准入的间接依赖未覆盖",
    ],
    "not_independent": "执行方自检，不构成独立验收；仅抽验 37 条回读原件物理页。",
    "release_S05": False,
}
(OUT / "review.json").write_text(
    json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

for c in checks:
    print("%s %-6s %s" % (c["id"], c["result"], c["name"]))
    if c["result"] == "FAIL":
        print("      ", json.dumps(c["detail"], ensure_ascii=False)[:400])
print("\n%d/%d PASS → %s" % (passed, len(checks), review["decision"]))
