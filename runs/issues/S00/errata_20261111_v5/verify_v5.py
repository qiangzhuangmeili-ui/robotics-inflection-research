#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""S00 勘误 V5 自检 V8（SELF_CHECK）

对 Codex 第六轮裁决（RETURN_FOR_REWORK）的逐条落实：

第二节（方法实现错误）
- C33 期间参数三态：is_own_period 显式返回 True/False/None，
  非自身期间必须要求 COMPARATIVE_SCOPE，未知期间单列 DOC_PERIOD_UNKNOWN；
- C26 撤销「同报告相减自动抵消」，改为 PARENT_COMPATIBILITY 证据维度，
  并按 B 实际父输入逐行重算（含跨文档父输入）。

第三节（极性）
- C34 极性回归 17 条反例（polarity_cases.py，生产与自检共用）；
- C37 父输入兼容性只认核证登记表；C38 来源维度只认核证登记表；
- C14 确认类不再只看 B=是，须事件层确认 + 来源维度覆盖。

第五、八节（自检与追溯）
- C14 裁决类必须命中 rulings_resolved.json 且键一致；
- C24 补充元数据放行必须命中 content_reviews.csv 登记记录（完整键含期间+终值+引文可定位）；
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
import meta_classes as mc
import parent_verify as pv
import polarity_cases as pc

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

# 父输入兼容性核证登记表：唯一的 YES 来源
PARENT_VERIFS = pv.load(OUT / "parent_verifications.csv")


def ruling_file_ok(ent):
    """裁决必须绑定真实裁决文件：路径存在、sha256 与登记一致。

    第七轮 E 项：原先只检查裁决 JSON 里出现过 "verdict" 字样，写任何占位文字都能过。
    """
    rf = (ent.get("ruling_file") or "").strip()
    want = (ent.get("ruling_file_sha256") or "").strip()
    if not rf or not want:
        return False
    p = (ROOT / rf) if not Path(rf).is_absolute() else Path(rf)
    if not p.exists():
        return False
    return hashlib.sha256(p.read_bytes()).hexdigest() == want


# 裁决依据里必须出现「可核对的识别信息」，否则「x」「见裁决」这类占位文字也能过
_MIN_BASIS = 40
_RULING_QUOTE_MIN = 20


def _ruling_text(ent):
    rf = (ent.get("ruling_file") or "").strip()
    if not rf:
        return None
    p = (ROOT / rf) if not Path(rf).is_absolute() else Path(rf)
    if not p.exists():
        return None
    return p.read_text(encoding="utf-8", errors="replace").split("\n")


def ruling_content_ok(ent):
    """第八轮 E 项：裁决依据不能是占位文字，必须落到裁决文件的具体段落。

    三条同时成立才算通过：
    1. `ruling_quote` 非空且 ≥20 字，并**逐字出现在裁决文件中**；
    2. `ruling_line` 指向的行确实包含该片段（行号不能编）；
    3. `basis` 与 `conflict_explanation` 各自 ≥40 字，且至少包含一个识别信息
       （证券代码 / 文档 ID / 公司简称），把「x」「见裁决」挡掉。
    """
    lines = _ruling_text(ent)
    if lines is None:
        return False
    quote = (ent.get("ruling_quote") or "").strip()
    if len(quote) < _RULING_QUOTE_MIN:
        return False
    try:
        ln = int(ent.get("ruling_line") or 0)
    except (TypeError, ValueError):
        return False
    if not (1 <= ln <= len(lines)) or quote not in lines[ln - 1]:
        return False
    if quote not in "\n".join(lines):
        return False
    idents = [t for t in (ent.get("stock_name"), ent.get("key", "").split("|")[0]) if t]
    for m in re.finditer(r"DOC-[0-9A-F]{16}", " ".join(
            str(ent.get(k) or "") for k in ("basis", "conflict_explanation"))):
        idents.append(m.group(0))
    for fld in ("basis", "conflict_explanation"):
        txt = (ent.get(fld) or "").strip()
        if len(txt) < _MIN_BASIS:
            return False
        if not any(t and t in txt for t in idents):
            return False
    return True


def _parent_basis(kp):
    r = D10.get(kp)
    if not r:
        return None
    return {"doc": (r.get("document_id") or "").strip(),
            "scope": (r.get("consolidation_scope") or "").strip(),
            "unit": (r.get("unit_scale") or "").strip(),
            "cur": (r.get("currency") or "").strip(),
            "ver": (r.get("version_used") or "").strip(),
            "val": (r.get("value_cny") or "").strip()}


def _doc_verdict(doc):
    return ((vrec.get(doc) or {}).get("verdict") or "").strip()


def parent_compatible(k, entries=None, ev_of=None):
    """父输入兼容性：**只认核证登记表**，不存在任何自动放行分支（第八轮 C 项）。

    Codex 第八轮明确否掉两条自动判据：同文档不能自动证明兼容（同一报告可能含
    调整前后列或混合来源）；上游「双否」不能直接证明兼容（三协电机已证明 verdict
    可能与原文相反）。故本函数只做两件事：先卡口径三元组非空且一致（必要条件），
    再要求登记表给出两个实际累计父数、原文引文与审查结论（充分条件）。
    """
    sec, fld, pk = k
    if fld not in es.SIMPLE_SQ:
        return None
    if es.is_q1(pk):
        return None
    ytd = fld[:-3] + ".YTD"
    k1, k2 = (sec, ytd, pk), (sec, ytd, prev_quarter(pk))
    b1, b2 = _parent_basis(k1), _parent_basis(k2)
    if not b1 or not b2:
        return False
    for f in ("scope", "unit", "cur"):
        if not b1[f] or b1[f] != b2[f]:
            return False
    reg = PARENT_VERIFS if entries is None else entries
    src = ev_of or (lambda d: (vrec.get(d) or {}).get("evidence", ""))
    if isinstance(src, dict):
        _m = src
        src = lambda d: _m.get(d, "")
    return pv.gap(reg.get(k), b1["val"], b2["val"], src) is None


def parent_gap(k, entries=None):
    """返回兼容性判定依据（供台账展示）：VERIFIED 或具体缺口原因。"""
    sec, fld, pk = k
    if fld not in es.SIMPLE_SQ or es.is_q1(pk):
        return "NA"
    ytd = fld[:-3] + ".YTD"
    k1, k2 = (sec, ytd, pk), (sec, ytd, prev_quarter(pk))
    b1, b2 = _parent_basis(k1), _parent_basis(k2)
    if not b1 or not b2:
        return "PARENT_MISSING"
    for f in ("scope", "unit", "cur"):
        if not b1[f] or b1[f] != b2[f]:
            return "SCOPE_UNIT_CURRENCY_MISMATCH"
    reg = PARENT_VERIFS if entries is None else entries
    g = pv.gap(reg.get(k), b1["val"], b2["val"],
               lambda d: (vrec.get(d) or {}).get("evidence", ""))
    return "VERIFIED" if g is None else g


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
        _p = es.analyse(rec)
        ex, af, sc, me = _p.excluded, _p.affirmed, _p.scoped, _p.mentioned
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
    """按重算事实给出唯一允许的处置标签。rec/pok/bval 可注入，供故障注入使用。

    分支顺序与 `build_errata_v5.py` 的「裁决 → 判定相反 → judge」严格一致，
    否则重算与生产会因顺序差异产生假违例。
    """
    rec = f["rec"] if rec is None else rec
    pok = f["pok"] if pok is None else pok
    bval = f["bval"] if bval is None else bval
    if ("|".join(f["k"])) in RULED:
        return "RESOLVED_BY_RULING"
    if not f["doc"]:
        return "UNRESOLVED_NO_DOCUMENT"
    if rec is None:
        return "UNRESOLVED_DOC_NEVER_VERIFIED"
    m = rec.get("method") or ""
    if rec.get("verdict") != bval and m != "NOTE_RETAINED_ERRATA_NONZERO":
        return "UNRESOLVED_EVIDENCE_MISMATCH"
    req = es.required_scope(f["status"], f["own"], f["k"][2])
    _p = es.analyse(rec)
    ex, af, sc, me = _p.excluded, _p.affirmed, _p.scoped, _p.mentioned
    cov = set(ex)
    if es.PARENT_COMPATIBILITY in req and pok is True:
        cov.add(es.PARENT_COMPATIBILITY)
    missing = req - cov
    if _p.conflict & (req & set(es.CAUSES)):
        return "UNRESOLVED_POLARITY_CONFLICT"
    if m == "ASSUMED_NO_PENDING_REVIEW":
        return "PENDING_WEAK_ASSUMPTION"
    if bval == "是":
        # 第七轮 D 项：事件确认只认原文极性，不用方法名兜底
        if es.ERRATA not in af:
            return "PENDING_CONFIRMED_UNSUPPORTED"
        src_gap = es.source_dims_for(f["status"], f["own"], f["k"][2]) - cov
        if src_gap:
            return "PENDING_CONFIRMED_EVENT_FIELD_OPEN"
        return "RESOLVED_RESTATEMENT_CONFIRMED"
    if m in es.SCOPE_LIMITED_METHODS and not es.binds_field(rec):
        return "PENDING_SCOPE_LIMITED_METHOD"
    if es.ERRATA in af and es.ERRATA in sc:
        return "PENDING_EVENT_CONFIRMED_SCOPE_LIMITED"
    if es.ERRATA in af:
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
            ent = RULED.get(key)
            if ent is None:
                bad.append((f["k"], "RULING_NOT_IN_RULINGS_FILE"))
            elif (ent.get("ruled_key") or "") != key:
                bad.append((f["k"], "RULING_KEY_MISMATCH"))
            elif not (ent.get("basis") or "").strip():
                bad.append((f["k"], "RULING_WITHOUT_BASIS"))
            elif not ruling_file_ok(ent):
                bad.append((f["k"], "RULING_FILE_UNBOUND_OR_SHA_DRIFT"))
            elif not ruling_content_ok(ent):
                # 第八轮 E 项：basis/conflict_explanation 写 "x" 也能过 → 必须落到裁决原文
                bad.append((f["k"], "RULING_WITHOUT_LOCATED_QUOTE"))
            elif not (ent.get("conflict_explanation") or "").strip():
                bad.append((f["k"], "RULING_WITHOUT_CONFLICT_EXPLANATION"))
            continue
        if res == "RESOLVED_NORMALIZED_DELTA":
            continue  # 由 C17 校验
        if res == "RESOLVED_RESTATEMENT_CONFIRMED":
            if f["bval"] != "是":
                bad.append((f["k"], "CONFIRMED_BUT_B_IS_NOT_YES"))
                continue
            # 第七轮 D 项：事件确认只认原文极性，方法名不能当原文证明
            if es.ERRATA not in f["af"]:
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
def _with_ruling(mut):
    """临时替换裁决登记条目，跑一次 check_c14，再还原（用于故障注入）。"""
    k = "SH:603025|FIN.REV.SQ|20250331"
    if k not in RULED:
        return False
    saved = RULED[k]
    ent = dict(saved)
    mut(ent)
    RULED[k] = ent
    try:
        got = check_c14(meta)
    finally:
        RULED[k] = saved
    return any(x[1] == "RULING_WITHOUT_LOCATED_QUOTE" for x in got)


def _ph(e):
    e["basis"] = "x"
    e["conflict_explanation"] = "x"


def _wl(e):
    e["ruling_line"] = int(e.get("ruling_line") or 1) - 1


c14_placeholder_caught = _with_ruling(_ph)
c14_wrongline_caught = _with_ruling(_wl)

add("C14", "已解决重述：裁决类命中裁决清单且依据落到裁决原文行、确认类事件+来源双证、覆盖类独立重算无缺口",
    not b14 and c14_placeholder_caught and c14_wrongline_caught,
    {"violations": len(b14), "sample": [str(x) for x in b14[:5]],
     "rulings": len(RULED),
     "injection_placeholder_basis": c14_placeholder_caught,
     "injection_wrong_ruling_line": c14_wrongline_caught})
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
# (2) 父输入不兼容：累计差分自身期间行（req 只含 ERRATA+PARENT_COMPATIBILITY，
#     否则比较范围会抢先命中 PENDING_SOURCE_PROVENANCE）。第七轮 C 项后跨文档
#     行已全部重开，不能再要求「已解决行」作探针。
probe_c = _find(lambda r: r["status_B"] == "DERIVED_CUMULATIVE_DIFF"
                and r["is_own_period"] == "YES")
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


P_REVIEWS = OUT / "content_reviews.csv"


def load_reviews():
    """内容审查登记表：真正的审查记录，不是可由公开公式算出的摘要。

    第八轮 E 项：原 `review_ref` 是 sha1(键|字段|终值) 的公开摘要，任何人不做审查
    也能算出来填进台账；且摘要遗漏 period_key，同一证券同一字段跨期间会互相顶替。
    """
    idx = {}
    if not P_REVIEWS.exists():
        return idx
    with open(P_REVIEWS, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            k = (r.get("security_id", ""), r.get("field_id", ""),
                 r.get("period_key", ""), r.get("meta_field", ""))
            idx[k] = r
    return idx


REVIEWS = load_reviews()
ALLOWED_CONCLUSIONS = {"CONFIRMED_EXPLAINED", "CONFIRMED_NOT_SUBSTANTIVE"}


def _nz(s):
    return re.sub(r"\s+", "", s or "")


def review_key(r):
    return "|".join([r["security_id"], r["field_id"], r["period_key"], r["meta_field"]])


def review_gap(r):
    """放行一条补充元数据差异所缺的东西；None 表示审查记录齐备。"""
    ent = REVIEWS.get((r["security_id"], r["field_id"], r["period_key"], r["meta_field"]))
    if ent is None:
        return "RELEASE_WITHOUT_CONTENT_REVIEW"
    if (r.get("content_review_ref") or "").strip() != review_key(r):
        return "LEDGER_NOT_LINKED_TO_REVIEW"
    if (ent.get("value_B") or "").strip() != (r.get("value_B") or "").strip():
        return "REVIEW_VALUE_MISMATCH"
    if (ent.get("conclusion") or "").strip() not in ALLOWED_CONCLUSIONS:
        return "REVIEW_WITHOUT_CONCLUSION"
    if not (ent.get("reviewer") or "").strip():
        return "REVIEW_WITHOUT_REVIEWER"
    b = D10.get((r["security_id"], r["field_id"], r["period_key"])) or {}
    doc = (b.get("document_id") or "").strip()
    if not doc or (ent.get("document_id") or "").strip() != doc:
        return "REVIEW_DOCUMENT_MISMATCH"
    q = _nz(ent.get("evidence_quote"))
    if len(q) < 12:
        return "REVIEW_QUOTE_TOO_SHORT"
    src = _nz((vrec.get(doc) or {}).get("evidence"))
    if not src or q not in src:
        return "REVIEW_QUOTE_NOT_LOCATED"
    return None


def extra_leaks(rows):
    """放行必须有与「同键同字段同期间同终值」绑定的真实审查记录。

    第七轮 E 项：原先只读台账自报的 class 列，把 value_raw / source_page 标成
    REGISTERED_DISPLAY_ONLY 就能免审查。现在分类由字段名锁定，自报 class 只能被核对。
    第八轮 E 项：审查记录改为外部登记表，并回读该文档原文核验引文可定位。
    """
    out = []
    for r in rows:
        mf = r["meta_field"]
        exp = mc.expected_class(mf)
        got = r.get("class") or ""
        if got != exp:
            out.append((r["security_id"], mf, "MISCLASSIFIED:%s!=%s" % (got, exp)))
            continue
        res = r["resolution"]
        if res == "REGISTERED_DISPLAY_ONLY":
            if exp != "DISPLAY_ONLY":
                out.append((r["security_id"], mf, "DISPLAY_ONLY_FOR_SUBSTANTIVE_FIELD"))
            elif r.get("document_changed") == "YES" or r.get("period_source_changed") == "YES":
                out.append((r["security_id"], mf, "DISPLAY_BUT_PROVENANCE_CHANGED"))
            continue
        if res != "RESOLVED_FIELD_LEVEL_CHECK":
            if is_resolved(res) or res.startswith("REGISTERED_"):
                out.append((r["security_id"], mf, "UNKNOWN_RELEASE:%s" % res))
            continue
        gap = review_gap(r)
        if gap:
            out.append((r["security_id"], mf, gap))
    return out


leak = extra_leaks(extra)
# 反例一：补一条「已放行但没有内容审查记录」的合成行
fake = dict(extra[0])
fake["resolution"] = "RESOLVED_FIELD_LEVEL_CHECK"
fake["content_review"] = ""
fake["content_review_ref"] = ""
fake_caught = len(extra_leaks([fake])) == 1
# 反例二（第七轮 Codex 实际用过的绕过路径）：把实质字段改标成展示字段
fake2 = dict(next(r for r in extra if mc.is_substantive(r["meta_field"])))
fake2["class"] = "DISPLAY_ONLY"
fake2["resolution"] = "REGISTERED_DISPLAY_ONLY"
fake2["document_changed"] = "NO"
fake2["period_source_changed"] = "NO"
fake2_caught = len(extra_leaks([fake2])) == 1
# 反例三（第八轮 E 项）：审查记录存在但没绑定到该键
fake3 = dict(fake)
fake3["content_review"] = "CONFIRMED"
fake3["content_review_ref"] = "CR-000000000000"
fake3_caught = len(extra_leaks([fake3])) == 1


def _with_review(row, **over):
    """临时注入一条审查记录，跑一次 extra_leaks，再还原（故障注入用）。"""
    k = (row["security_id"], row["field_id"], row["period_key"], row["meta_field"])
    saved = REVIEWS.get(k)
    ent = {"security_id": row["security_id"], "field_id": row["field_id"],
           "period_key": row["period_key"], "meta_field": row["meta_field"],
           "value_B": row.get("value_B", ""), "document_id": "",
           "evidence_quote": "", "conclusion": "CONFIRMED_EXPLAINED",
           "reviewer": "injection", "reviewed_at": "2026-11-11"}
    ent.update(over)
    REVIEWS[k] = ent
    try:
        got = extra_leaks([row])
    finally:
        if saved is None:
            REVIEWS.pop(k, None)
        else:
            REVIEWS[k] = saved
    return got


_rel = dict(fake)
_rel["content_review_ref"] = review_key(_rel)
# 反例四：摘要式伪造（只填一个可算出来的 ref，没有真实登记）→ 必须拦住
fake4_caught = len(_with_review(_rel, document_id="", evidence_quote="")) == 1
# 反例五：登记表里把 period_key 换成别的期间（第七轮摘要遗漏 period_key 的绕过）
_pk = _rel["period_key"]
_alt = "20250930" if _pk != "20250930" else "20251231"
fake5_caught = len(_with_review(_rel, period_key=_alt, evidence_quote="x" * 20)) == 1
# 反例六：引文在原文里找不到
fake6_caught = len(_with_review(_rel, evidence_quote="此处原文并不存在的一段话用以测试定位失败")) == 1
add("C24", "补充元数据放行须有外部审查登记表记录：完整键（含期间）+终值+原文引文可定位",
    not leak and fake_caught and fake2_caught and fake3_caught
    and fake4_caught and fake5_caught and fake6_caught,
    {"leaked": len(leak), "sample": [str(x) for x in leak[:5]],
     "injection_no_review": fake_caught,
     "injection_misclassified_as_display": fake2_caught,
     "injection_unbound_digest": fake3_caught,
     "injection_digest_only_no_register": fake4_caught,
     "injection_wrong_period_key": fake5_caught,
     "injection_quote_not_located": fake6_caught,
     "review_register_rows": len(REVIEWS),
     "pending": sum(1 for r in extra if r["resolution"] == "PENDING_FIELD_LEVEL_CHECK")})

b26 = check_c26(meta)
add("C26", "全类别双向重算（17,009 条，含裁决类与确认类）；独立于台账自报字段，但与生产同源", not b26,
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
# 第七轮 E 项：不能只查「引用存在且同键」，必须从源差异表独立重建预期引用集合做集合相等。
# 否则删掉一条受限声明的逐表 ID 和总列表同一 ID、再同步减小 dispute_count，仍能通过。
exp_tbl = defaultdict(set)
for r in dledger:
    exp_tbl[(r["security_id"], r["field_id"], r["period_key"], r["ledger"])].add(r["dispute_id"])
seteq_bad = []
for r in restr:
    k = (r["security_id"], r["field_id"], r["period_key"])
    total = {x for x in (r["dispute_ids"] or "").split(";") if x}
    union = set()
    for short, full in TBL_OF.items():
        act = {x for x in (r.get("dispute_ids_" + short) or "").split(";") if x}
        union |= act
        exp = exp_tbl.get(k + (full,), set())
        if act != exp:
            seteq_bad.append((k, short, "act=%d exp=%d" % (len(act), len(exp))))
    if total != union:
        seteq_bad.append((k, "TOTAL_NE_UNION", "%d!=%d" % (len(total), len(union))))
add("C28", "差异 ID 稳定、逐表引用同键、受限行引用集合与源差异表重建结果相等",
    not dup and not unmapped and not cnt_bad and not id_bad and not per_table_bad and not seteq_bad,
    {"ledger_ids": len(led_ids), "unique": len(set(led_ids)), "dups": len(dup),
     "used_ids": len(used), "unmapped": len(unmapped), "count_mismatch": len(cnt_bad),
     "id_unstable": len(id_bad), "per_table_bad": len(per_table_bad),
     "set_equality_bad": len(seteq_bad), "set_equality_sample": [str(x) for x in seteq_bad[:5]]})

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
add("C29", "不得存在「仅凭期间相等」的闭合（按重算覆盖判定，不看台账自报；与 C26 同源）",
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
# 第七轮 F 项：原先只要求 located_conclusion 非空，写「NOT_FOUND」也算通过。
# 现在必须声明 locate_status，且「风险已发现」与「核证通过」分开计数。
r7_bad = [s for s in r7
          if (s.get("locate_status") or "") not in ("VERIFIED", "WEAK", "NOT_LOCATED")]
r7_verified = [s for s in r7 if s.get("locate_status") == "VERIFIED"]
r7_status = Counter(s.get("locate_status") for s in r7)
add("C31", "分层抽验覆盖 12 类必需风险 + 补充字段；原文定位须区分已核与未定位",
    REQUIRED_RISK <= samp_risk and has_extra and not reread_bad and bool(r7)
    and not r7_bad and len(r7_verified) >= 1,
    {"samples": len(samp), "risk_types": len(samp_risk),
     "unique_keys": len({(s["security_id"], s["field_id"], s["period_key"],
                          s["meta_field"]) for s in samp}),
     "missing": sorted(REQUIRED_RISK - samp_risk), "extra_covered": has_extra,
     "reread_bad": len(reread_bad), "r7_undeclared": len(r7_bad),
     "r7_verified": len(r7_verified), "r7_status": dict(r7_status),
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

# 第七轮 B 项：Codex 在内存复现的三个误放行，必须逐个被拦住
_cb_aff = _pol("前期差错更正\n√适用□不适用")
if es.ERRATA not in _cb_aff[1] or es.ERRATA in _cb_aff[0]:
    c34.append("CHECKBOX_CHECKED_APPLICABLE_MISREAD")
_cb_neg = _pol("前期差错更正\n□适用√不适用")
if es.ERRATA not in _cb_neg[0] or es.ERRATA in _cb_neg[1]:
    c34.append("CHECKBOX_CHECKED_NA_MISREAD")
_bind = _pol("本期发生前期差错更正，但会计政策变更不适用")
if es.ERRATA not in _bind[1] or es.POLICY_CHANGE not in _bind[0]:
    c34.append("NEGATION_BROADCAST_TO_ALL_CAUSES")
if es.ERRATA in _bind[0]:
    c34.append("ERRATA_EXCLUDED_BY_POLICY_NEGATION")
_confl = _pol("未发生前期差错更正。本期发生前期差错更正100.00元")
if es.ERRATA not in _confl[4]:
    c34.append("CONFLICT_NOT_DETECTED")
# 事件与影响分离：非零权益影响必须同时记「事件已确认」与「仅限该项目」
_scoped_pos = _pol("差错更正对期初未分配利润影响100.00元")
if es.ERRATA not in _scoped_pos[1] or es.ERRATA not in _scoped_pos[2]:
    c34.append("EVENT_AND_SCOPE_NOT_SEPARATED")
# 标签行不得被当成肯定
_lbl = _pol("追溯重述法\n本期未发生采用追溯重述法的前期会计差错更正事项。")
if es.ERRATA in _lbl[1] or es.ERRATA not in _lbl[0]:
    c34.append("LABEL_LINE_TREATED_AS_AFFIRM")
# 冲突只在该原因属于本行必需维度时才阻断
_judge_pol = es.judge({"evidence": "本期发生前期差错更正，但会计政策变更不适用。"
                                   "本报告期无会计政策变更。", "method": "T", "verdict": "否",
                       "page": "1"}, "DOC-X", "EXTRACTED", "20250630", "20250630", bval="否")
if _judge_pol["resolution"] == "UNRESOLVED_POLARITY_CONFLICT":
    c34.append("POLICY_CONFLICT_BLOCKS_ERRATA_ASSERTION")

_pc_bad = pc.check_all()
c34.extend("POLARITY_CASE:%s" % b["case"] for b in _pc_bad)
add("C34", "极性回归：%d 条反例（含第八轮裁决表五条原文用例 + 三协电机真实版面）" % len(pc.CASES),
    not c34, {"violations": c34,
              "case_count": len(pc.CASES),
              "case_failures": _pc_bad,
              "cases": {"neg": "本公司未发生前期差错更正",
                        "pos": "本期发生前期差错更正",
                        "hundred": "前期差错更正调整 100.00 元",
                        "checkbox_na": "追溯重述法；□适用 √不适用",
                        "checkbox_applicable": "前期差错更正\\n√适用□不适用",
                        "negation_binding": "本期发生前期差错更正，但会计政策变更不适用",
                        "conflict": "未发生前期差错更正。本期发生前期差错更正100.00元",
                        "event_vs_scope": "差错更正对期初未分配利润影响100.00元",
                        "label_line": "追溯重述法（小标题）",
                        "scoped_zero": "…影响期初未分配利润0.00元",
                        "sanxie_option_row": "□会计政策变更 √会计差错更正 □其他原因 □不适用",
                        "postfix_layout": "前期差错更正适用√不适用□",
                        "thousand_sep": "…影响期初未分配利润-160,517.06元"}})

# ---------------- C36 必需范围 = 期间要求 ∪ 来源要求 ----------------
c36 = []
if es.QUARTERLY_TABLE_PROVENANCE not in es.required_scope(
        "EXTRACTED_QUARTERLY_TABLE", "20251231", "20250630"):
    c36.append("NON_OWN_QUARTERLY_TABLE_LOST_PROVENANCE")
if es.COMPARATIVE_SCOPE not in es.required_scope(
        "EXTRACTED_QUARTERLY_TABLE", "20251231", "20250630"):
    c36.append("NON_OWN_LOST_COMPARATIVE_SCOPE")
if es.PARENT_COMPATIBILITY not in es.required_scope(
        "DERIVED_CUMULATIVE_DIFF", "20251231", "20250630"):
    c36.append("NON_OWN_CUMULATIVE_LOST_PARENT_COMPAT")
if es.PARENT_COMPATIBILITY in es.required_scope(
        "DERIVED_CUMULATIVE_DIFF", "20250630", "20250331"):
    c36.append("Q1_STILL_REQUIRES_TWO_PARENT_DIFF")
miss36 = []
for r in meta:
    if r["meta_field"] != "restatement_flag" or r["is_own_period"] != "NO":
        continue
    k = (r["security_id"], r["field_id"], r["period_key"])
    st = D10.get(k, {}).get("status", "")
    if st != "EXTRACTED_QUARTERLY_TABLE":
        continue
    req = es.required_scope(st, r["own_period"], r["period_key"])
    if not {es.COMPARATIVE_SCOPE, es.QUARTERLY_TABLE_PROVENANCE} <= req:
        miss36.append(str(k))
add("C36", "必需范围取并集：非自身期间的分季度表/累计差分不得丢失来源维度",
    not c36 and not miss36,
    {"violations": c36, "row_violations": len(miss36), "sample": miss36[:5],
     "comparative_quarterly_table_rows": sum(
         1 for r in meta if r["meta_field"] == "restatement_flag"
         and r["is_own_period"] == "NO"
         and D10.get((r["security_id"], r["field_id"], r["period_key"]), {}).get("status") == "EXTRACTED_QUARTERLY_TABLE")})

# ---------------- C37 父输入兼容性：只认核证登记表 ----------------
c37 = []
diff_keys = [(r["security_id"], r["field_id"], r["period_key"]) for r in meta
             if r["meta_field"] == "restatement_flag"
             and D10.get((r["security_id"], r["field_id"], r["period_key"]), {}).get("status")
             == "DERIVED_CUMULATIVE_DIFF"]

# 1) 没有登记记录却判 YES → 仍是自动捷径
auto_pass = [str(k) for k in diff_keys if parent_compatible(k) is True]
if auto_pass:
    c37.append("COMPATIBLE_WITHOUT_VERIFICATION_RECORD:%d" % len(auto_pass))

# 2) 口径字段为空不得当作「已确认一致」
empty_scope_pass = []
for k in diff_keys:
    if not es.SIMPLE_SQ.__contains__(k[1]) or es.is_q1(k[2]):
        continue
    ytd = k[1][:-3] + ".YTD"
    b1 = _parent_basis((k[0], ytd, k[2]))
    b2 = _parent_basis((k[0], ytd, prev_quarter(k[2])))
    if not b1 or not b2:
        continue
    if (not b1["scope"] or not b1["unit"] or not b1["cur"]) and parent_compatible(k) is True:
        empty_scope_pass.append(str(k))
if empty_scope_pass:
    c37.append("EMPTY_SCOPE_FIELD_TREATED_AS_EQUAL")


# 3) 第八轮 C 项指定的检验方式：**撤去真实兼容依据后是否仍通过**。
#    不能把所有「跨文档、同版本且兼容」都判成捷径——那样将来会误拦合法核证。
#    做法：找一条口径一致、可登记的真实累计差分键，先造一条满足 gap() 的登记
#    记录（引文取自该文档原文），确认判 YES；再逐项撤去依据，确认逐项变 NO。
def _inject_parent_chain():
    """挑一条口径一致的真实累计差分键，用合成原文源验证判定链。

    生产路径仍读 vrec 原文；这里只替换「原文源」以便把判定链逐环拆开验证，
    不改变任何判定规则。
    """
    for k in diff_keys:
        if not es.SIMPLE_SQ.__contains__(k[1]) or es.is_q1(k[2]):
            continue
        ytd = k[1][:-3] + ".YTD"
        b1 = _parent_basis((k[0], ytd, k[2]))
        b2 = _parent_basis((k[0], ytd, prev_quarter(k[2])))
        if not b1 or not b2:
            continue
        if not (b1["scope"] and b1["unit"] and b1["cur"]):
            continue
        if (b1["scope"], b1["unit"], b1["cur"]) != (b2["scope"], b2["unit"], b2["cur"]):
            continue
        q1 = "母公司本期累计数已在报表主表逐行列出"
        q2 = "上期累计数已在可比期间报表中逐行列示"
        ent = {"security_id": k[0], "field_id": k[1], "period_key": k[2],
               "ytd_field": ytd, "p1_doc": b1["doc"], "p2_doc": b2["doc"],
               "p1_value": b1["val"], "p2_value": b2["val"],
               "p1_quote": q1, "p2_quote": q2,
               "consolidation_scope": b1["scope"], "unit_scale": b1["unit"],
               "currency": b1["cur"], "conclusion": "COMPATIBLE",
               "reviewer": "injection", "reviewed_at": "2026-11-11"}
        src = {b1["doc"]: q1 + "…" + q2, b2["doc"]: q2}
        return k, ent, src
    return None, None, None


_pk, _pent, _psrc = _inject_parent_chain()
if _pk is None:
    c37.append("NO_INJECTABLE_PARENT_CASE")
    chain = {}
else:
    chain = {}
    chain["with_record"] = parent_compatible(_pk, {_pk: _pent}, _psrc) is True
    chain["no_record"] = parent_compatible(_pk, {}, _psrc) is False
    e = dict(_pent); e["conclusion"] = "NOT_COMPATIBLE"
    chain["wrong_conclusion"] = parent_compatible(_pk, {_pk: e}, _psrc) is False
    e = dict(_pent); e["p1_value"] = "0"
    chain["value_mismatch"] = parent_compatible(_pk, {_pk: e}, _psrc) is False
    e = dict(_pent); e["p1_quote"] = "此引文在原文中并不存在用于测试定位失败"
    chain["quote_not_located"] = parent_compatible(_pk, {_pk: e}, _psrc) is False
    e = dict(_pent); e["unit_scale"] = ""
    chain["empty_scope"] = parent_compatible(_pk, {_pk: e}, _psrc) is False
    e = dict(_pent); e["reviewer"] = ""
    chain["no_reviewer"] = parent_compatible(_pk, {_pk: e}, _psrc) is False
    e = dict(_pent); e["p2_quote"] = ""
    chain["p2_quote_missing"] = parent_compatible(_pk, {_pk: e}, _psrc) is False
    if not all(chain.values()):
        c37.append("VERIFICATION_CHAIN_BROKEN:%s" % chain)

reopened = sum(1 for r in meta if r["meta_field"] == "restatement_flag"
               and r["resolution"] == "PENDING_PARENT_COMPATIBILITY")
if reopened < 1000:
    c37.append("REOPENED_PARENT_COMPAT_TOO_FEW:%d" % reopened)
add("C37", "父输入兼容性只认核证登记表：撤去真实依据后必须变 NO，跨文档已解除项重开",
    not c37,
    {"violations": c37, "auto_passes": len(auto_pass),
     "empty_scope_passes": len(empty_scope_pass),
     "verification_chain": chain,
     "register_rows": len(PARENT_VERIFS),
     "reopened_pending": reopened,
     "cumulative_diff_rows": len(diff_keys)})

# ---------------- C38 judge 的结构化核证入口（比较范围 / 季度表来源）----------------
# 第八轮 C 项：judge() 原先把这两个维度当成「证据里提到过就算覆盖」，
# 现在只接受核证登记表供给，且撤去登记后必须退回待核。
c38 = []
_sv = pv.load_scope(OUT / "scope_verifications.csv")
_cand = None
for r in meta:
    if r["meta_field"] != "restatement_flag":
        continue
    if r["resolution"] != "PENDING_SOURCE_PROVENANCE":
        continue
    if "QUARTERLY_TABLE_PROVENANCE" not in (r["scope_missing"] or ""):
        continue
    k = (r["security_id"], r["field_id"], r["period_key"])
    doc = D10.get(k, {}).get("document_id", "")
    if doc and len(_nz((vrec.get(doc) or {}).get("evidence", ""))) >= 12:
        _cand = (r, k, doc)
        break

if _cand is None:
    c38.append("NO_SOURCE_PROVENANCE_CASE")
    c38_detail = {}
else:
    r, k, doc = _cand
    quote = _nz((vrec.get(doc) or {}).get("evidence", ""))[:20]
    _need = [d for d in (r["scope_missing"] or "").split(";") if d in es.SOURCE_DIMS]
    recs = [{"security_id": k[0], "field_id": k[1], "period_key": k[2],
             "dimension": d, "document_id": doc,
             "source_page": (vrec.get(doc) or {}).get("page", ""),
             "evidence_quote": quote, "conclusion": "CONFIRMED",
             "reviewer": "injection", "reviewed_at": "2026-11-11"} for d in _need]
    base = recs[0]
    ev = lambda d: (vrec.get(d) or {}).get("evidence", "")
    good = pv.scope_dims({k: recs}, k, ev)
    bad_concl = pv.scope_dims({k: [dict(base, conclusion="PENDING")]}, k, ev)
    bad_quote = pv.scope_dims({k: [dict(base, evidence_quote="不存在的引文用于测试")]}, k, ev)
    bad_reviewer = pv.scope_dims({k: [dict(base, reviewer="")]}, k, ev)

    st = D10.get(k, {}).get("status", "")
    own = doc_period.get(doc, "")
    j_no = es.judge(vrec.get(doc), doc, st, own, k[2], bval="否", scope_ok=set())
    j_yes = es.judge(vrec.get(doc), doc, st, own, k[2], bval="否", scope_ok=good)
    c38_detail = {
        "key": "|".join(k),
        "without_record": j_no["resolution"],
        "with_record": j_yes["resolution"],
        "dims_from_record": sorted(good),
        "dims_required": _need,
        "rejected_wrong_conclusion": not bad_concl,
        "rejected_unlocatable_quote": not bad_quote,
        "rejected_no_reviewer": not bad_reviewer,
    }
    if not set(_need) <= good:
        c38.append("VALID_RECORD_NOT_ACCEPTED")
    if bad_concl or bad_quote or bad_reviewer:
        c38.append("INVALID_RECORD_ACCEPTED")
    if j_no["resolution"] != "PENDING_SOURCE_PROVENANCE":
        c38.append("PENDING_NOT_RESTORED_WITHOUT_RECORD:%s" % j_no["resolution"])
    if j_yes["resolution"] == "PENDING_SOURCE_PROVENANCE":
        c38.append("RECORD_DID_NOT_COVER_DIMENSION")
    if set(_need) & set((j_yes["scope_missing"] or "").split(";")):
        c38.append("DIMENSION_STILL_MISSING_WITH_RECORD")
add("C38", "来源维度（比较范围/季度表来源）只能由核证登记表覆盖，撤去后必须退回待核",
    not c38,
    {"violations": c38, "detail": c38_detail,
     "register_rows": len(_sv),
     "pending_source_provenance": sum(
         1 for r in meta if r["meta_field"] == "restatement_flag"
         and r["resolution"] == "PENDING_SOURCE_PROVENANCE")})

passed = sum(1 for c in checks if c["result"] == "PASS")
review = {
    "issue_key": "S00", "stage": "ERRATA", "version": "ERRATA_V5",
    "self_check_version": "V8",
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
    "round8_fixes": [
        "极性按版面整体求解：两种版面（符号在前/符号在后）各自解一遍，取能自洽（标签不重复）者；"
        "三协电机 p.135 的四选项行由「判 conflict 并放行」改为 affirmed=ERRATA / excluded=POLICY_CHANGE → C34",
        "分句不再按半角逗号无条件切分（-160,517.06元 曾被切成两段，丢失 8 条事件确认）",
        "勾选组主语遇标题换题即断开，不再跨「（四）审批程序及其他说明」误绑上一节的差错更正",
        "「采用」作为肯定谓词时须检查是否被前面的否定词管辖（本期未发生采用追溯重述法的前期差错更正事项）",
        "父输入兼容性只认 parent_verifications.csv：撤销「同文档」与「上游双否」两条自动判据，"
        "YES 4→0；C37 改为「撤去真实兼容依据后必须变 NO」的注入链",
        "C24 改绑 content_reviews.csv（完整键含 period_key + 终值 + 引文可在原文定位），"
        "并注入六种绕过：无记录 / 改标展示 / 仅填可算摘要 / 换期间 / 引文不可定位 / 终值不符",
        "C14 须回读裁决文件核对 ruling_quote 与 ruling_line，且 basis 与 conflict_explanation "
        "各自 ≥40 字并含识别信息（写 x 不再通过）",
        "R6 交付两父输入各自的取值/状态/原件定位/命中片段；R7 措辞改「原文片段已定位」并保存 located_fragment",
        "新增 C38：比较范围 / 季度表来源只能由 scope_verifications.csv 覆盖，撤去后退回待核",
        "上游 verdict 与原文极性相反的行逐条登记 evidence_conflicts.csv，并给出该文档在 B 中的传播范围",
    ],
    "open_findings": [
        "9,954 条 NOTE_TRACE_NA 已解决项尚未做方法适用性复审（631 份文档，已解除 8,655 条 / 630 份；不等于全部错误）",
        "NOTE_RETAINED_ERRATA_ZERO 642 条（自身 563 / 非自身 79）待核实，未凭注记批量放行",
        "SH:600936 FIN.REV.SQ@20250630 的核验证据在原件全文无法定位，属上游核验记录问题",
        "第 4 步批量核证（文档级事件确认 / 字段级影响确认 / 采用链确认）未开始",
        "第 5 步重算分层与受限表未开始；44/231/378 未锁定",
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
