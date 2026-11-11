#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""父输入兼容性 / 来源维度的唯一依据：核证登记表（生产与自检共用）。

第八轮裁决 C 项明确否掉两条自动判据：
- **同文档不能自动证明兼容**——同一报告可能含调整前后列或混合来源；
- **上游「双否」不能直接证明兼容**——三协电机已证明 verdict 可能与原文相反，
  它只能作为待核线索。
同时澄清：正常同口径累计数相减，**不要求两期调整额相等**；只有主张
「调整影响相互抵消」时才须证明调整额相等。

第九轮裁决 C 项又指出：只比对「父终值」不够——登记里把父文档换成无关文档、
把父期间和口径写错、审查人填 `x`、日期留空，仍能返回 VERIFIED。因此本轮把
登记记录绑定到**实际父输入**：

- `p1_doc`/`p2_doc` 必须等于该行两个父键实际采用的 document_id；
- `p1_period`/`p2_period` 必须等于实际父期间；
- `p1_value`/`p2_value` 必须等于实际父终值，且**引文里必须出现该父数**
  （按 unit_scale 折算比对，杜绝「引用通用标题片段」）；
- 必须登记取值栏目、调整前后版本，且两父版本一致；
- 口径三元组不仅要非空，还要与实际父输入一致，并给出 `scope_basis`。

第九轮裁决 E 项同时限定：来源登记只能供给 `COMPARATIVE_SCOPE` /
`QUARTERLY_TABLE_PROVENANCE`，**不得顶替父输入核证**；且引文必须绑定目标键、
目标期间与该行实际供给文档。
"""
import csv
import datetime
import re
from pathlib import Path

import evidence_scope as es

# ---------------- 父输入核证登记表 ----------------
COLS = ["security_id", "field_id", "period_key", "ytd_field",
        "p1_period", "p2_period", "p1_doc", "p2_doc",
        "p1_value", "p2_value", "p1_page", "p2_page",
        "p1_quote", "p2_quote",
        "p1_column", "p2_column", "p1_adjust_version", "p2_adjust_version",
        "consolidation_scope", "unit_scale", "currency", "scope_basis",
        "conclusion", "review_role", "reviewer", "reviewed_at"]

# 调整前后版本：两父必须取自同一版本基础
ADJUST_VERSIONS = {"ORIGINAL", "RESTATED", "SAME_VERSION"}
REVIEW_ROLES = {"INDEPENDENT_REVIEW", "SELF_CHECK"}
REVIEWER_PLACEHOLDERS = {"", "x", "xx", "xxx", "-", "--", "n/a", "na",
                         "none", "null", "test", "tbd", "todo", "self", "me"}
_AMOUNT_TOKEN = re.compile(r"-?\d[\d,]*(?:\.\d+)?")
_MIN_QUOTE = 12
_MIN_BASIS = 20


def _nz(s):
    return re.sub(r"\s+", "", s or "")


def _reviewer_ok(ent):
    r = (ent.get("reviewer") or "").strip()
    return len(r) >= 2 and r.lower() not in REVIEWER_PLACEHOLDERS


def _role_ok(ent):
    return (ent.get("review_role") or "").strip() in REVIEW_ROLES


def _date_ok(s):
    s = (s or "").strip()
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        return False
    try:
        datetime.date(int(s[:4]), int(s[5:7]), int(s[8:10]))
    except ValueError:
        return False
    return True


def _num_in_quote(quote, value, unit_scale="1"):
    """引文里是否出现该父数本身（按 unit_scale 折算）。

    第九轮 C 项：只比父终值字段，登记可以把引文换成无关文档的通用标题片段。
    这里要求引文里真的写出这个数，`DOC-…` 之类的标题片段无法满足。
    """
    try:
        target = float(value)
    except (TypeError, ValueError):
        return False
    try:
        mult = float(unit_scale or "1")
    except (TypeError, ValueError):
        mult = 1.0
    if mult <= 0:
        mult = 1.0
    for m in _AMOUNT_TOKEN.finditer(quote or ""):
        raw = m.group(0).replace(",", "")
        try:
            v = float(raw)
        except ValueError:
            continue
        if abs(v * mult - target) <= max(0.05, abs(target) * 1e-9):
            return True
    return False


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


# ---------------- 来源维度核证登记表 ----------------
SCOPE_COLS = ["security_id", "field_id", "period_key", "dimension",
              "target_field", "target_period",
              "document_id", "source_page", "evidence_quote",
              "conclusion", "review_role", "reviewer", "reviewed_at"]


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


def scope_dims(entries, key, evidence_of, expect_doc=None):
    """该行已获结构化核证的来源维度。

    第九轮 E 项四条收紧：
    1. 维度只接受 `COMPARATIVE_SCOPE` / `QUARTERLY_TABLE_PROVENANCE`；
       `PARENT_COMPATIBILITY` 必须走 `parent_verifications.csv`，不能被顶替。
    2. `target_field` / `target_period` 必须等于目标键本身（不能拿别的行作依据）。
    3. `document_id` 必须等于该行实际供给文档（不能拿无关文档的通用引文）。
    4. 引文 ≥12 字、能在该文档原文中定位，且**含该行期间年份**——通用摘录不算来源核证。
    """
    ok = set()
    for e in entries.get(key, []):
        dim = (e.get("dimension") or "").strip()
        if dim not in es.SCOPE_REGISTRABLE:
            continue
        if (e.get("conclusion") or "").strip() != "CONFIRMED":
            continue
        if not _reviewer_ok(e) or not _role_ok(e) or not _date_ok(e.get("reviewed_at")):
            continue
        if (e.get("target_field") or "").strip() != key[1]:
            continue
        if (e.get("target_period") or "").strip() != key[2]:
            continue
        doc = (e.get("document_id") or "").strip()
        if expect_doc is not None and doc != (expect_doc or "").strip():
            continue
        q = _nz(e.get("evidence_quote"))
        if len(q) < _MIN_QUOTE:
            continue
        if q not in _nz(evidence_of(doc)):
            continue
        if key[2][:4] not in q:
            continue
        ok.add(dim)
    return ok


def gap(ent, expect, evidence_of):
    """返回该记录不足以证明兼容的原因；None 表示依据充分。

    `expect` = {"p1": {...}, "p2": {...}}，每侧含 doc / period / value /
    scope / unit / cur，取自 B 的实际父输入。
    `evidence_of(doc_id)` 返回该文档可用原文（可为空字符串）。
    """
    if ent is None:
        return "NO_VERIFICATION_RECORD"
    if (ent.get("conclusion") or "").strip() != "COMPATIBLE":
        return "VERIFICATION_NOT_COMPATIBLE"
    if not _reviewer_ok(ent):
        return "VERIFICATION_WITHOUT_REVIEWER"
    if not _role_ok(ent):
        return "VERIFICATION_WITHOUT_ROLE"
    if not _date_ok(ent.get("reviewed_at")):
        return "VERIFICATION_WITHOUT_DATE"

    # 绑定实际父输入：文档 / 期间 / 终值
    for side in ("p1", "p2"):
        exp = expect[side]
        if (ent.get("%s_doc" % side) or "").strip() != (exp.get("doc") or "").strip():
            return "PARENT_DOC_MISMATCH"
        if (ent.get("%s_period" % side) or "").strip() != (exp.get("period") or "").strip():
            return "PARENT_PERIOD_MISMATCH"
        if (ent.get("%s_value" % side) or "").strip() != (exp.get("value") or "").strip():
            return "PARENT_VALUE_MISMATCH"
        if not (ent.get("%s_column" % side) or "").strip():
            return "PARENT_COLUMN_EMPTY"
        ver = (ent.get("%s_adjust_version" % side) or "").strip()
        if ver not in ADJUST_VERSIONS:
            return "PARENT_ADJUST_VERSION_INVALID"

    # 两父必须取自同一调整版本基础
    v1 = (ent.get("p1_adjust_version") or "").strip()
    v2 = (ent.get("p2_adjust_version") or "").strip()
    if v1 != v2:
        return "PARENT_ADJUST_VERSION_INCONSISTENT"

    # 口径：非空 + 与实际父输入一致 + 有依据
    for f in ("consolidation_scope", "unit_scale", "currency"):
        v = (ent.get(f) or "").strip()
        if not v:
            return "SCOPE_FIELD_EMPTY"
        if v != (expect["p1"].get(f) or "").strip():
            return "SCOPE_MISMATCH_WITH_PARENT"
    if len(_nz(ent.get("scope_basis"))) < _MIN_BASIS:
        return "SCOPE_BASIS_MISSING"

    # 引文：够长、可定位、且含该父数
    for side, fq, fd in (("p1", "p1_quote", "p1_doc"), ("p2", "p2_quote", "p2_doc")):
        q = _nz(ent.get(fq))
        if len(q) < _MIN_QUOTE:
            return "PARENT_QUOTE_TOO_SHORT"
        src = _nz(evidence_of((ent.get(fd) or "").strip()))
        if not src:
            return "PARENT_SOURCE_UNAVAILABLE"
        if q not in src:
            return "PARENT_QUOTE_NOT_LOCATED"
        if not _num_in_quote(ent.get(fq), expect[side].get("value"),
                             expect[side].get("unit")):
            return "PARENT_QUOTE_WITHOUT_PARENT_VALUE"
    return None
