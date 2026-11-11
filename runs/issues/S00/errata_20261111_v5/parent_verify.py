#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""父输入兼容性的唯一依据：核证登记表（生产与自检共用）。

第八轮裁决 C 项明确否掉两条自动判据：
- **同文档不能自动证明兼容**——同一报告可能含调整前后列或混合来源；
- **上游「双否」不能直接证明兼容**——三协电机已证明 verdict 可能与原文相反，
  它只能作为待核线索。
同时澄清：正常同口径累计数相减，**不要求两期调整额相等**；只有主张
「调整影响相互抵消」时才须证明调整额相等。

因此本模块只做一件事：给定一条登记记录，判断它是否构成充分依据。
没有任何自动分支能替代它——登记表为空时，全部累计差分都停在待核。
"""
import csv
import re
from pathlib import Path

COLS = ["security_id", "field_id", "period_key", "ytd_field",
        "p1_period", "p2_period", "p1_doc", "p2_doc",
        "p1_value", "p2_value", "p1_page", "p2_page",
        "p1_quote", "p2_quote",
        "consolidation_scope", "unit_scale", "currency",
        "conclusion", "reviewer", "reviewed_at"]


def _nz(s):
    return re.sub(r"\s+", "", s or "")


def load(path):
    """返回 {(security_id, field_id, period_key): 记录}。"""
    idx = {}
    p = Path(path)
    if not p.exists():
        return idx
    with open(p, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            idx[(r.get("security_id", ""), r.get("field_id", ""),
                 r.get("period_key", ""))] = r
    return idx


SCOPE_COLS = ["security_id", "field_id", "period_key", "dimension",
              "document_id", "source_page", "evidence_quote",
              "conclusion", "reviewer", "reviewed_at"]


def load_scope(path):
    """来源维度核证登记表：{(sec, fld, pk): [记录, ...]}。"""
    idx = {}
    p = Path(path)
    if not p.exists():
        return idx
    with open(p, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            idx.setdefault((r.get("security_id", ""), r.get("field_id", ""),
                            r.get("period_key", "")), []).append(r)
    return idx


def scope_dims(entries, key, evidence_of):
    """该行已获结构化核证的来源维度（COMPARATIVE_SCOPE / QUARTERLY_TABLE_PROVENANCE）。

    必须同时满足：结论 CONFIRMED、有审查人、引文 ≥12 字且能在所引文档原文中定位。
    不满足的记录一律不计入——「文档里提到过」不构成来源核证。
    """
    ok = set()
    for e in entries.get(key, []):
        if (e.get("conclusion") or "").strip() != "CONFIRMED":
            continue
        if not (e.get("reviewer") or "").strip():
            continue
        q = _nz(e.get("evidence_quote"))
        if len(q) < 12:
            continue
        if q not in _nz(evidence_of((e.get("document_id") or "").strip())):
            continue
        ok.add((e.get("dimension") or "").strip())
    return ok


def gap(ent, p1_value, p2_value, evidence_of):
    """返回该记录不足以证明兼容的原因；None 表示依据充分。

    evidence_of(doc_id) 返回该文档可用原文（可为空字符串）。
    """
    if ent is None:
        return "NO_VERIFICATION_RECORD"
    if (ent.get("conclusion") or "").strip() != "COMPATIBLE":
        return "VERIFICATION_NOT_COMPATIBLE"
    if not (ent.get("reviewer") or "").strip():
        return "VERIFICATION_WITHOUT_REVIEWER"
    if not (ent.get("reviewed_at") or "").strip():
        return "VERIFICATION_WITHOUT_DATE"
    for f, v in (("p1_value", p1_value), ("p2_value", p2_value)):
        if (ent.get(f) or "").strip() != (v or "").strip():
            return "PARENT_VALUE_MISMATCH"
    for f in ("consolidation_scope", "unit_scale", "currency"):
        if not (ent.get(f) or "").strip():
            return "SCOPE_FIELD_EMPTY"
    for fq, fd in (("p1_quote", "p1_doc"), ("p2_quote", "p2_doc")):
        q = _nz(ent.get(fq))
        d = (ent.get(fd) or "").strip()
        if len(q) < 12:
            return "PARENT_QUOTE_TOO_SHORT"
        src = _nz(evidence_of(d))
        if not src:
            return "PARENT_SOURCE_UNAVAILABLE"
        if q not in src:
            return "PARENT_QUOTE_NOT_LOCATED"
    return None
