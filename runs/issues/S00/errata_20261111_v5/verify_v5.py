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
- C37 父输入兼容性只认核证登记表并绑定实际父输入；C38 来源维度只认两类登记；
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

# 裁决的**适用范围**清单：独立于登记条目维护（第十一轮 D 项）。
# 登记条目里的 `key` / `ruled_key` 都是自报字段，两处一起改写就能把裁决扩用到
# 同公司的其他字段或期间；只有与这份清单（section → 允许的键）比对才挡得住。
P_RULING_SCOPE = OUT / "ruling_scope.csv"
RULING_SCOPE = {}
if P_RULING_SCOPE.exists():
    with P_RULING_SCOPE.open(encoding="utf-8-sig", newline="") as _f:
        for _r in csv.DictReader(_f):
            RULING_SCOPE.setdefault((_r.get("ruling_section") or "").strip(), set()).add(
                (_r.get("allowed_key") or "").strip())

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


# 正式裁决表的行：`| Q2 大豪科技改判 | **接受该具体争议解除。** … |`
_RE_RULING_ROW = re.compile(r"^\|\s*(Q\d+)\s+([^|]+?)\s*\|(.*)\|\s*$")
# 裁决结论里的否定表述：出现即不得作为「解除」依据（第十一轮）
_RE_NEG_VERDICT = re.compile(r"不代表|不予|不成立|驳回|撤销|否决|取消|除外|不构成|不予以|不适用")


def _ruling_rows(lines):
    """从裁决文件解析「正式裁决表」：{`Q2 大豪科技改判`: 结论单元格文本}。

    第十轮 D 项：原实现只要求三个自填字符串出现在**任意一行**，于是把三项都填成
    「大豪科技」、引用第 88 行的文档登记说明（`collection_index.csv:8428 将该文档
    登记为大豪科技 2025 年年度报告`）也能通过——那一行没有裁决任何争议。
    现在引文必须落在裁决表的一行上，且裁决项标题必须点名该键。
    """
    rows = {}
    for ln in lines:
        m = _RE_RULING_ROW.match(ln.strip())
        if m:
            rows[(m.group(1) + " " + m.group(2)).strip()] = m.group(3)
    return rows


def ruling_gap(ent):
    """返回裁决依据不成立的原因；None 表示成立（第十轮 D 项）。"""
    lines = _ruling_text(ent)
    if lines is None:
        return "RULING_FILE_MISSING"
    quote = (ent.get("ruling_quote") or "").strip()
    if len(quote) < _RULING_QUOTE_MIN:
        return "RULING_QUOTE_TOO_SHORT"
    try:
        ln = int(ent.get("ruling_line") or 0)
    except (TypeError, ValueError):
        return "RULING_LINE_INVALID"
    if not (1 <= ln <= len(lines)) or quote not in lines[ln - 1]:
        return "RULING_QUOTE_NOT_AT_LINE"
    if quote not in "\n".join(lines):
        return "RULING_QUOTE_NOT_IN_FILE"

    line = lines[ln - 1].strip()
    m = _RE_RULING_ROW.match(line)
    if not m:
        return "RULING_LINE_NOT_A_RULING_ROW"
    item_title = (m.group(1) + " " + m.group(2)).strip()
    concl = m.group(3)

    section = (ent.get("ruling_section") or "").strip()
    verdict = (ent.get("ruling_verdict") or "").strip()
    pat = (ent.get("ruling_key_pattern") or "").strip()
    if len(section) < 4 or len(verdict) < 4 or len(pat) < 4:
        return "RULING_FIELD_TOO_SHORT"
    # 裁决只解除它裁定的那一个键：`ruled_key` 必须与待判键三元组完全一致。
    # （第十一轮复核中断前暴露：原实现只在 check_c14 里比对 ruled_key，单独调 ruling_gap
    #   时同一公司的其他字段也能过——判据本身必须自带绑定，不能靠调用方代劳。）
    ruled_key = (ent.get("ruled_key") or "").strip()
    if not ruled_key:
        return "RULING_RULED_KEY_MISSING"
    if ruled_key != (ent.get("key") or "").strip():
        return "RULING_KEY_MISMATCH"
    # 裁决条目必须是该行的裁决项名，结论必须来自该行结论单元格
    if section != item_title:
        return "RULING_SECTION_MISMATCH"
    # 与独立维护的「裁决条目 → 允许键」清单比对：自报的 key/ruled_key 一起改写也没用
    _scope = RULING_SCOPE.get(section)
    if not _scope:
        return "RULING_SCOPE_NOT_LISTED"
    if (ent.get("key") or "").strip() not in _scope:
        return "RULING_KEY_NOT_IN_SCOPE"
    # 结论单元格须**以裁决结论开头**，且裁决结论不得是否定表述。
    # （第十一轮复核中断前暴露：原实现只查「verdict 是结论单元格的子串」，
    #   于是从同一格末尾截出「不代表全公司验收」也能通过。）
    concl_n = re.sub(r"[*_\s]", "", concl)
    verdict_n = re.sub(r"[*_\s]", "", verdict)
    if _RE_NEG_VERDICT.search(verdict_n):
        return "RULING_VERDICT_NEGATED"
    if not concl_n.startswith(verdict_n):
        return "RULING_VERDICT_NOT_IN_ROW"
    # 裁决项标题必须点名该键：通用条目（如「Q1 document_id 匹配」）不得用于解除单键
    if pat not in item_title:
        return "RULING_ITEM_DOES_NOT_NAME_KEY"

    # 识别信息必须真是本键：证券代码 / 简称 / 该键文档 ID，不能是通用词
    sec = (ent.get("key") or "").split("|")[0]
    code = sec.split(":")[-1]
    idents = {sec, code, (ent.get("stock_name") or "").strip()}
    idents = {x for x in idents if x}
    if pat not in idents and not re.match(r"^DOC-[0-9A-F]{16}$", pat):
        return "RULING_KEY_PATTERN_NOT_THIS_KEY"

    idents = [t for t in (ent.get("stock_name"), ent.get("key", "").split("|")[0]) if t]
    for m2 in re.finditer(r"DOC-[0-9A-F]{16}", " ".join(
            str(ent.get(k) or "") for k in ("basis", "conflict_explanation"))):
        idents.append(m2.group(0))
    for fld in ("basis", "conflict_explanation"):
        txt = (ent.get(fld) or "").strip()
        if len(txt) < _MIN_BASIS:
            return "RULING_BASIS_TOO_SHORT"
        if not any(t and t in txt for t in idents):
            return "RULING_BASIS_NOT_KEY_SPECIFIC"
    return None


def ruling_content_ok(ent):
    """裁决依据不能是占位文字，且必须**确实裁决该键**（详见 `ruling_gap`）。"""
    return ruling_gap(ent) is None


def _parent_basis(kp):
    r = D10.get(kp)
    if not r:
        return None
    return {"doc": (r.get("document_id") or "").strip(),
            "period": kp[2],
            "scope": (r.get("consolidation_scope") or "").strip(),
            "unit": (r.get("unit_scale") or "").strip(),
            "cur": (r.get("currency") or "").strip(),
            "ver": (r.get("version_used") or "").strip(),
            "val": (r.get("value_cny") or "").strip()}


def _expect(k1, k2, b1, b2):
    """核证登记必须逐项对应的实际父输入（第九轮 C 项 / 第十轮 B 项）。

    第十轮 B2：新增 `adjust_version`——登记声明的调整前后版本必须等于该父
    实际采用的 `version_used` 归类，不能只验枚举与两父相等。
    """
    return {"field": k1[1],
            "p1": {"doc": b1["doc"], "period": k1[2], "value": b1["val"],
                   "consolidation_scope": b1["scope"], "unit_scale": b1["unit"],
                   "currency": b1["cur"], "adjust_version": b1["ver"]},
            "p2": {"doc": b2["doc"], "period": k2[2], "value": b2["val"],
                   "consolidation_scope": b2["scope"], "unit_scale": b2["unit"],
                   "currency": b2["cur"], "adjust_version": b2["ver"]}}


def _doc_verdict(doc):
    return ((vrec.get(doc) or {}).get("verdict") or "").strip()


def parent_compatible(k, entries=None, ev_of=None, col_of=None):
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
    src = ev_of or (lambda d, p: _pdf_ev(sec, d, p))
    if isinstance(src, dict):
        _m = src
        src = lambda d, p: _m.get((d, str(p)), "")
    return pv.gap(reg.get(k), _expect(k1, k2, b1, b2), src, col_of=col_of) is None


def pdf_file(sec, doc):
    """原件路径（第十一轮 B 项：按坐标核对栏目需要词坐标，不能再只读文本）。"""
    code = (sec or "").split(":")[-1]
    for p in (ORIG / code).rglob(doc + ".pdf"):
        return p
    return None


def _col_of(sec):
    """按词坐标取「该金额所在列」的期间列头（第十一轮 B 项）。"""
    def f(doc, page, value):
        pdf = pdf_file(sec, doc)
        if pdf is None:
            return None
        words = pv.page_words(pdf, page)
        if not words:
            return None
        col, _amt = pv.column_of_amount(words, value)
        return col
    return f


def _pdf_ev(sec, doc, page):
    """原件指定物理页文本（第十轮 B3 项：引文必须落在登记页上）。"""
    try:
        n = int(str(page).strip())
    except (TypeError, ValueError):
        return ""
    pages = pdf_pages(sec, doc) or []
    return pages[n - 1] if 1 <= n <= len(pages) else ""


def parent_gap(k, entries=None, col_of=None):
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
    g = pv.gap(reg.get(k), _expect(k1, k2, b1, b2),
               lambda d, p: _pdf_ev(sec, d, p), col_of=col_of)
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
    """临时替换裁决登记条目，返回 (台账是否拦下该键, ruling_gap 的具体原因, 台账原因)。

    第十轮 G 项：只断言布尔会把「拦在别处」也算成通过，必须同时断言拒绝原因。
    第十一轮 G 项：台账侧原来写死「必须是 RULING_WITHOUT_LOCATED_QUOTE」，
    但 `key`+`ruled_key` 一起改写时台账先报 `RULING_KEY_MISMATCH`——那同样是拦下了，
    错的是断言。改为「该键被台账判为不合规」+ 单独比对 `ruling_gap` 的拒绝原因。
    """
    k = "SH:603025|FIN.REV.SQ|20250331"
    if k not in RULED:
        return False, "NO_RULED_ENTRY", []
    saved = RULED[k]
    ent = dict(saved)
    mut(ent)
    RULED[k] = ent
    try:
        got = check_c14(meta)
        why = ruling_gap(ent)
    finally:
        RULED[k] = saved
    kt = tuple(k.split("|"))
    hit = [x[1] for x in got if x[0] == kt]
    return bool(hit), why, hit


def _ph(e):
    e["basis"] = "x"
    e["conflict_explanation"] = "x"


def _wl(e):
    e["ruling_line"] = int(e.get("ruling_line") or 1) - 1


def _unrelated(e):
    """第九轮 D 项实测绕过：引文换成裁决文件第 3 行「建议存档名…」，行号也改成 3。

    该行确实逐字存在、行号也正确，但完全没有裁决这个键。
    """
    e["ruling_line"] = 3
    e["ruling_quote"] = "建议存档名：`codex_ruling_round4.md`"


def _registry_note(e):
    """第十轮 D 项实测绕过：三项都填「大豪科技」，引第 88 行的文档登记说明。

    该行确实出现「大豪科技」且行号正确，但它是文档登记说明，没有裁决任何争议。
    """
    e["ruling_line"] = 88
    e["ruling_quote"] = "`runs/collection/collection_index.csv:8428` 将该文档登记为大豪科技"
    e["ruling_section"] = "大豪科技"
    e["ruling_key_pattern"] = "大豪科技"
    e["ruling_verdict"] = "大豪科技"


def _wrong_key(e):
    """引文与行号都对，但识别信息指向别的公司（不是本键）。"""
    e["ruling_key_pattern"] = "SH:600022"


def _no_section(e):
    """引文与行号都对，但裁决条目名不在该行（无法证明该段裁决的就是本键）。"""
    e["ruling_section"] = "Q9 杭叉跨来源限制"


def _generic_item(e):
    """把引文换到正式裁决表里的**通用**条目（Q1 document_id 匹配），并声称它解除本键。

    注意拦截顺序：`Q1 document_id 匹配` 不在 `ruling_scope.csv` 里，所以先撞
    `RULING_SCOPE_NOT_LISTED`；「裁决项标题没点名该键」这一道由
    `key_pattern_other_company` 单独覆盖（那一项的 section 是已登记条目）。
    """
    e["ruling_line"] = 235
    e["ruling_quote"] = "| Q1 document_id 匹配 | **用于定位文档和解释历史回填成立；用于自动解除所有期间争议不成立。**"
    e["ruling_section"] = "Q1 document_id 匹配"
    e["ruling_verdict"] = "用于定位文档和解释历史回填成立"
    e["ruling_key_pattern"] = "大豪科技"


def _field_other(e):
    """第十一轮暴露：裁决只裁定 `FIN.REV.SQ`，但把键换成同一公司的其他字段也能过。

    裁决解除的粒度是「这一个键」，不是「这家公司」。`ruled_key` 必须精确相等。
    """
    e["key"] = "SH:603025|FIN.NPDEDT.SQ|20250331"


def _neg_verdict(e):
    """第十一轮暴露：从结论单元格末尾截出否定表述「不代表全公司验收」当作裁决结论。"""
    e["ruling_verdict"] = "不代表全公司验收"


def _both_rewritten(e):
    """第十一轮 D 项实测绕过：把 `key` 和 `ruled_key` **一起**改成同一公司的其他字段。

    `ruled_key == key` 因此仍然成立、裁决项标题也仍点名「大豪科技」，
    只有与独立维护的 `ruling_scope.csv` 比对才能拦住。
    """
    e["key"] = "SH:603025|FIN.NPDEDT.SQ|20250331"
    e["ruled_key"] = "SH:603025|FIN.NPDEDT.SQ|20250331"


# 一张表管住「注入名 → 改法 → 预期拒绝原因」；键集合与预期原因集合同源，不会漏登
_C14_MUTS = [
    ("placeholder_basis", _ph, "RULING_BASIS_TOO_SHORT"),
    ("wrong_line", _wl, "RULING_QUOTE_NOT_AT_LINE"),
    ("unrelated_quote", _unrelated, "RULING_LINE_NOT_A_RULING_ROW"),
    ("registry_note", _registry_note, "RULING_LINE_NOT_A_RULING_ROW"),
    ("key_pattern_other_company", _wrong_key, "RULING_ITEM_DOES_NOT_NAME_KEY"),
    ("section_not_on_line", _no_section, "RULING_SECTION_MISMATCH"),
    ("generic_ruling_item", _generic_item, "RULING_SCOPE_NOT_LISTED"),
    ("field_other_same_company", _field_other, "RULING_KEY_MISMATCH"),
    ("both_key_and_ruled_rewritten", _both_rewritten, "RULING_KEY_NOT_IN_SCOPE"),
    ("negative_verdict_substring", _neg_verdict, "RULING_VERDICT_NEGATED"),
]
c14_inj = {}
for _n, _mut, _exp in _C14_MUTS:
    _c, _w, _hit = _with_ruling(_mut)
    c14_inj[_n] = {"caught": _c, "reason": _w, "expect": _exp,
                   "ledger_reasons": _hit}
c14_reason_mismatch = {n: d["reason"] for n, d in c14_inj.items()
                       if d["reason"] != d["expect"]}
c14_not_caught = [n for n, d in c14_inj.items() if not d["caught"]]

# 正例：未改动的既有裁决必须继续成立（证明门槛可满足）
c14_control_ok = ("SH:603025|FIN.REV.SQ|20250331" in RULED
                  and ruling_gap(RULED["SH:603025|FIN.REV.SQ|20250331"]) is None)

add("C14", "已解决重述：裁决类须绑定**正式裁决表条目**+适用键+裁决结论"
           "（引文所在行必须是裁决表行，裁决项标题须点名该键，`ruled_key` 须与待判键完全一致，"
           "且该键须在独立维护的 `ruling_scope.csv` 适用范围内，"
           "结论单元格须以裁决结论开头且不得是否定表述），"
           "确认类事件+来源双证，覆盖类独立重算无缺口",
    not b14 and c14_control_ok and not c14_not_caught and not c14_reason_mismatch,
    {"violations": len(b14), "sample": [str(x) for x in b14[:5]],
     "rulings": len(RULED),
     "control_accepted": c14_control_ok,
     "injections": c14_inj,
     "injection_count": len(c14_inj),
     "not_caught": c14_not_caught,
     "reason_mismatch": c14_reason_mismatch,
     "ruling_scope_rows": sum(len(v) for v in RULING_SCOPE.values())})
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


ORIG = Path("D:/StockResearchLab/IndustryInflectionLab/robotics_data/collection/originals")
_PDF_CACHE = {}


def pdf_pages(sec, doc):
    """回读原件物理页文本（按 document_id 缓存）。不可用时返回 None。

    第九轮 D 项：C24 原来的定位源是 `results.csv.evidence`——那是上游核验记录里
    的摘录，不是原件；拿它自证「引文可定位」等于用同一来源自证。改为回读 PDF。
    """
    key = (sec, doc)
    if key in _PDF_CACHE:
        return _PDF_CACHE[key]
    pages = None
    code = (sec or "").split(":")[-1]
    pdf = None
    for p in (ORIG / code).rglob(doc + ".pdf"):
        pdf = p
        break
    if pdf is not None:
        try:
            import pymupdf
            d = pymupdf.open(str(pdf))
            pages = [_nz(d[i].get_text()) for i in range(d.page_count)]
            d.close()
        except Exception:
            pages = None
    _PDF_CACHE[key] = pages
    return pages


_RE_NUM_CLEAN = re.compile(r"[,\s]")
# 原文单位字样 → 折算倍数（第十轮 C 项：单位必须由固定映射核，不能自述）
UNIT_MAP = {"元": "1", "千元": "1000", "万元": "10000", "百万元": "1000000",
            "亿元": "100000000"}
_RE_DATE_CN = re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日")
_RE_DATE_ISO = re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})")


def _as_num(s):
    """去千分位后转 float。

    第十轮 C 项：原 `float(v)` 无法解析 `5,667,075,612.52`，直接抛错落入文本分支，
    于是「自述里同时写出上年数与本期数」即可过关。必须先去掉千分位逗号。
    """
    t = _RE_NUM_CLEAN.sub("", (s or "").strip())
    if not t:
        return None
    try:
        return float(t)
    except ValueError:
        return None


def _as_date(s):
    """把 `2026年4月23日` / `2026-04-23` 归一为 `YYYY-MM-DD`；不可解析返回 None。"""
    s = (s or "").strip()
    for rx in (_RE_DATE_ISO, _RE_DATE_CN):
        m = rx.search(s)
        if m:
            return "%04d-%02d-%02d" % (int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return None


# 每个 meta_field 的核证方式（第十轮 C/D 项）。
# 规则只认「原文事实 / 固定映射 / 登记页自证」，`judgement_basis` 一律不再作为
# 证据——它只能解释映射，不能替代映射所需的证据。
FIELD_RULES = {
    "value_raw": ("NUM", "原文印刷金额按单位折算后须等于 value_raw"),
    "value_before_adoption": ("NUM", "采用前金额须等于原文印刷值"),
    "unit_scale": ("UNIT", "原文单位字样经固定映射后须等于该倍数"),
    "unit_raw": ("LITERAL", "原文单位字样须逐字出现在片段中"),
    "currency": ("LITERAL", "币种字样须逐字出现在片段中"),
    "evidence_label": ("LITERAL", "指标名须逐字出现在片段中"),
    "published_on": ("DATE", "原文披露日期须等于 published_on"),
    "source_page": ("SELF_PAGE", "登记页须等于 source_page（即审查者实际读到的那一页）"),
}
# 未定义可核验映射规则的字段：一律不得由内容审查放行（须留在待核）。
# 这些值都是内部枚举/派生状态，PDF 里没有对应字面，也没有可回放的采用日志，
# 让 `judgement_basis` 自述就等于让登记者自己举证——第十轮 C 项明确否掉。
# 文本字段的「自带标签」正则：值必须跟在它自己的标签后面
_LITERAL_LABEL = {
    "unit_raw": r"单位\s*[:：]?\s*(?:人民币)?\s*%s",
    "currency": r"(?:币种|货币|记账本位币)\s*[:：]?\s*%s",
}


RULE_UNDEFINED_FIELDS = sorted({
    "period_source", "slot_id", "source_kind", "status_reason",
    "upstream_hold_fields", "low_base_flag", "quarterly_inputs",
    "comparability_note", "version_used", "adoption_reason",
    "original_document_id",
})


def _field_support(kind, printed, value_b, unit, frag, ent):
    """按字段规则判「原文事实是否支撑该字段终值」。返回 (ok, 拒绝原因)。"""
    if kind == "NUM":
        p = _as_num(printed)
        t = _as_num(value_b)
        if t is None:
            return False, "REVIEW_VALUE_NOT_NUMERIC"
        if p is None:
            return False, "REVIEW_PRINTED_VALUE_NOT_NUMERIC"
        try:
            mult = float(unit or "1")
        except (TypeError, ValueError):
            mult = 1.0
        if mult <= 0:
            mult = 1.0
        if abs(p * mult - t) <= max(0.05, 0.5 * mult, abs(t) * 1e-9):
            return True, None
        return False, "REVIEW_PRINTED_VALUE_NOT_SUPPORT_VALUE"
    if kind == "UNIT":
        u = UNIT_MAP.get(_nz(printed))
        if u is None:
            return False, "REVIEW_UNIT_TEXT_UNMAPPED"
        if u != (value_b or "").strip():
            return False, "REVIEW_UNIT_MAPPING_MISMATCH"
        return True, None
    if kind == "DATE":
        d = _as_date(printed)
        if d is None:
            return False, "REVIEW_PRINTED_DATE_UNPARSED"
        if d != _as_date(value_b):
            return False, "REVIEW_PRINTED_DATE_MISMATCH"
        return True, None
    if kind == "LITERAL":
        v = (value_b or "").strip()
        if not v:
            return False, "REVIEW_VALUE_EMPTY"
        if _nz(v) not in _nz(frag):
            return False, "REVIEW_PRINTED_VALUE_NOT_IN_FRAGMENT"
        # 第十一轮 C 项：字面出现 ≠ 它是该字段的值。年份 2025 在页面上到处都是，
        # 不能因此证明它是单位/币种/证据标签。文本字段须**带自己的标签**出现。
        fld = (ent.get("meta_field") or "").strip()
        pat = _LITERAL_LABEL.get(fld)
        if pat is not None:
            if not re.search(pat % re.escape(v), frag):
                return False, "REVIEW_LITERAL_NOT_BOUND_TO_FIELD"
            return True, None
        if fld == "evidence_label":
            # 行/列标签必须与紧随其后的金额相邻（20 字内出现数字），
            # 证明它是这个数的标签，而不是页面别处出现的同名字样。
            if not re.search(re.escape(v) + r"[^\d]{0,20}?[−-]?\d[\d,]*\.?\d*", frag):
                return False, "REVIEW_LITERAL_NOT_BOUND_TO_FIELD"
            return True, None
        return False, "REVIEW_FIELD_RULE_UNDEFINED"
    if kind == "SELF_PAGE":
        if (value_b or "").strip() != (ent.get("original_page") or "").strip():
            return False, "REVIEW_SOURCE_PAGE_NE_REGISTERED_PAGE"
        return True, None
    return False, "REVIEW_FIELD_RULE_UNDEFINED"


def _supports(printed, value, unit="1", basis=""):
    """兼容旧接口：数值型按单位折算比对，文本型逐字包含。

    `basis` 已**不再**参与判定（第十轮 C 项）：自述不能替代证据。
    """
    p = _as_num(printed)
    t = _as_num(value)
    if p is not None and t is not None:
        try:
            mult = float(unit or "1")
        except (TypeError, ValueError):
            mult = 1.0
        return abs(p * mult - t) <= max(0.05, 0.5 * mult, abs(t) * 1e-9)
    v = (value or "").strip()
    if not v or not (printed or "").strip():
        return False
    return _nz(v) in _nz(printed) or _nz(printed) in _nz(v)


def review_gap(r):
    """放行一条补充元数据差异所缺的东西；None 表示审查记录齐备。

    第九轮 D 项在第八轮基础上再补五道：
    - `reviewed_at` 必须是真实日期，`review_role` 必须显式标注（自检也要标）；
    - `reviewer` 不得是 `x` 之类占位；
    - `original_page` + `original_fragment` 必须能在**原件该页**逐字命中
      （不再接受 `results.csv.evidence` 自证）；
    - `original_value_text` 必须是该字段在原文里印出来的字面值，且出现在片段中；
    - `judgement_basis` ≥40 字、点名该字段与终值。

    第十轮 C/D 项再补三道：
    - 登记记录必须属于该键（`REVIEW_KEY_MISMATCH`），不再靠「缺文档」偶然拦截；
    - 印刷值 → 终值的支撑关系改按**字段规则**判定（`FIELD_RULES`），
      `judgement_basis` 不再作为证据（原文本分支让自述同时写出两个数即可过关）；
    - 没有可核验映射规则的字段一律 `REVIEW_FIELD_RULE_UNDEFINED`，留在待核。
    """
    ent = REVIEWS.get((r["security_id"], r["field_id"], r["period_key"], r["meta_field"]))
    if ent is None:
        return "RELEASE_WITHOUT_CONTENT_REVIEW"
    if (r.get("content_review_ref") or "").strip() != review_key(r):
        return "LEDGER_NOT_LINKED_TO_REVIEW"
    # 第十轮 G 项：登记记录本身必须属于该键（原实现没有这一道，`period_key`
    # 被换成别的期间时只能靠「缺文档」偶然拦住，属错误归因）。
    for _f in ("security_id", "field_id", "period_key", "meta_field"):
        if (ent.get(_f) or "").strip() != (r.get(_f) or "").strip():
            return "REVIEW_KEY_MISMATCH"
    if (ent.get("value_B") or "").strip() != (r.get("value_B") or "").strip():
        return "REVIEW_VALUE_MISMATCH"
    if (ent.get("conclusion") or "").strip() not in ALLOWED_CONCLUSIONS:
        return "REVIEW_WITHOUT_CONCLUSION"
    if not pv._reviewer_ok(ent):
        return "REVIEW_WITHOUT_REVIEWER"
    if (ent.get("review_role") or "").strip() not in pv.REVIEW_ROLES:
        return "REVIEW_ROLE_UNMARKED"
    if not pv._date_ok(ent.get("reviewed_at")):
        return "REVIEW_WITHOUT_DATE"
    b = D10.get((r["security_id"], r["field_id"], r["period_key"])) or {}
    doc = (b.get("document_id") or "").strip()
    if not doc or (ent.get("document_id") or "").strip() != doc:
        return "REVIEW_DOCUMENT_MISMATCH"

    # 针对该字段的判断依据
    basis = _nz(ent.get("judgement_basis"))
    if len(basis) < 40:
        return "REVIEW_BASIS_TOO_SHORT"
    if _nz(r["meta_field"]) not in basis or _nz(r.get("value_B")) not in basis:
        return "REVIEW_BASIS_NOT_FIELD_SPECIFIC"

    printed = (ent.get("original_value_text") or "").strip()
    if not printed:
        return "REVIEW_WITHOUT_ORIGINAL_VALUE"

    # 原件定位：必须在 PDF 该页逐字命中
    try:
        pg = int(ent.get("original_page") or 0)
    except (TypeError, ValueError):
        pg = 0
    if pg <= 0:
        return "REVIEW_WITHOUT_ORIGINAL_PAGE"
    frag = _nz(ent.get("original_fragment"))
    if len(frag) < 20:
        return "REVIEW_FRAGMENT_TOO_SHORT"
    pages = pdf_pages(r["security_id"], doc)
    if pages is None:
        return "REVIEW_ORIGINAL_UNAVAILABLE"
    if pg > len(pages):
        return "REVIEW_ORIGINAL_PAGE_OUT_OF_RANGE"
    if frag not in pages[pg - 1]:
        return "REVIEW_FRAGMENT_NOT_IN_ORIGINAL_PAGE"
    if _nz(printed) not in frag:
        return "REVIEW_PRINTED_VALUE_NOT_IN_FRAGMENT"

    # 终值支持：印刷值必须按**字段规则**支撑该字段终值
    if (ent.get("value_in_quote") or "").strip() != (r.get("value_B") or "").strip():
        return "REVIEW_VALUE_NOT_DECLARED"
    rule = FIELD_RULES.get(r["meta_field"])
    if rule is None:
        return "REVIEW_FIELD_RULE_UNDEFINED"
    if rule[0] == "SELF_PAGE":
        # 第十一轮 C 项：两个**自报**页码相等不算证据。改为独立定位——
        # 该行金额在原件里最早出现的页，才是「审查者实际读到的那一页」。
        amt = _nz(_fmt_parent(b.get("value_cny") or "", b.get("unit_scale") or "1"))
        if not amt:
            return "REVIEW_SOURCE_PAGE_UNVERIFIABLE"
        first = None
        for _i, _pt in enumerate(pages, 1):
            if amt in _nz(_pt):
                first = _i
                break
        if first is None:
            return "REVIEW_SOURCE_PAGE_NOT_LOCATED"
        if pg != first:
            return "REVIEW_SOURCE_PAGE_NOT_FIRST_OCCURRENCE"
    ok, why = _field_support(rule[0], printed, r.get("value_B"),
                             b.get("unit_scale", "1"), frag, ent)
    if not ok:
        return why

    # 引文仍保留（用于台账展示），但已不再作为唯一依据
    q = _nz(ent.get("evidence_quote"))
    if len(q) < 12:
        return "REVIEW_QUOTE_TOO_SHORT"
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


def _leak_of(rows):
    """走 `extra_leaks` 全链，返回 (是否恰好拦 1 条, **实际**拒绝原因)。

    第十一轮 G 项：`no_review` / `unbound_digest` 原先把原因字符串直接写进结果
    元组，断言的是「我以为拦在哪」，不是「实际拦在哪」。改为从 `extra_leaks`
    的返回里取第三条元素。
    """
    lk = extra_leaks(rows)
    if len(lk) == 1:
        return True, lk[0][2]
    if not lk:
        return False, "NOT_CAUGHT"
    return False, "MULTI_LEAK:%d" % len(lk)


def _leak_with(rel, ent):
    """在**指定**审查记录下跑一遍 `extra_leaks`，返回 (是否恰好拦 1 条, 实际原因)。

    `no_review` / `unbound_digest` 要分别检验「根本没有记录」和「记录在但没绑定」，
    所以得显式决定 REGISTRY 里有没有这条记录——不能指望调用点残留状态。
    """
    k = (rel["security_id"], rel["field_id"], rel["period_key"], rel["meta_field"])
    saved = REVIEWS.get(k)
    if ent is None:
        REVIEWS.pop(k, None)
    else:
        REVIEWS[k] = ent
    try:
        return _leak_of([rel])
    finally:
        if saved is None:
            REVIEWS.pop(k, None)
        else:
            REVIEWS[k] = saved


def _inj(rel, base, **over):
    """从完整正例复制，只改一个条件，返回 (是否被拦, 具体拒绝原因)。

    第十轮 G 项：原 `_with_review()` 默认建立的记录缺文档、缺原件，错页/样板/终值
    未声明等测试先被 `REVIEW_DOCUMENT_MISMATCH` 拦住，PASS 并未验证所声称的门槛。
    现在一律以完整正例为基线，每次只改一个条件，并断言预期拒绝原因。
    """
    k = (rel["security_id"], rel["field_id"], rel["period_key"], rel["meta_field"])
    saved = REVIEWS.get(k)
    ent = dict(base)
    ent.update(over)
    REVIEWS[k] = ent
    try:
        why = review_gap(rel)
    finally:
        if saved is None:
            REVIEWS.pop(k, None)
        else:
            REVIEWS[k] = saved
    return why is not None, why


def _genuine_review(row):
    """按**字段规则**构造一条真实可核的审查记录（正例对照用）。

    第十轮 C 项：只取「有明确字段规则 + 原件里确实印着该事实」的行。
    NUM 按单位折算找印刷值；UNIT 走固定映射；DATE 归一化日期；LITERAL 逐字命中；
    SELF_PAGE 要求页码与该页一致。
    """
    k = (row["security_id"], row["field_id"], row["period_key"])
    b = D10.get(k) or {}
    doc = (b.get("document_id") or "").strip()
    v = (row.get("value_B") or "").strip()
    rule = FIELD_RULES.get(row["meta_field"])
    if not doc or not v or rule is None:
        return None
    unit = (b.get("unit_scale") or "1").strip()
    pages = pdf_pages(row["security_id"], doc)
    if not pages:
        return None
    kind = rule[0]
    for pi, t in enumerate(pages):
        printed, pos = None, -1
        if kind == "NUM":
            tgt = _as_num(v)
            if tgt is None:
                return None
            # 优先用与 value_B 完全一致的字面串：页内相邻单元格会粘连成
            # `5,667,075,612.526,303,...`，纯数值扫描会取到假精度
            if v in t:
                printed, pos = v, t.index(v)
            try:
                mult = float(unit or "1")
            except (TypeError, ValueError):
                mult = 1.0
            if mult <= 0:
                mult = 1.0
            for m in re.finditer(r"-?\d[\d,]*(?:\.\d+)?", t):
                p = _as_num(m.group(0))
                if p is None:
                    continue
                if abs(p * mult - tgt) <= max(0.05, 0.5 * mult, abs(tgt) * 1e-9):
                    printed, pos = m.group(0), m.start()
                    break
        elif kind == "UNIT":
            for txt, sc in UNIT_MAP.items():
                if sc == v and txt in t:
                    printed, pos = txt, t.index(txt)
                    break
        elif kind == "DATE":
            d = _as_date(v)
            if d:
                y, mo, da = d.split("-")
                for pat in ("%s年%d月%d日" % (y, int(mo), int(da)), d):
                    if pat in t:
                        printed, pos = pat, t.index(pat)
                        break
        elif kind == "LITERAL":
            if v in t:
                printed, pos = v, t.index(v)
        elif kind == "SELF_PAGE":
            if v in t and v == str(pi + 1):
                printed, pos = v, t.index(v)
        if printed is None:
            continue
        frag = t[max(0, pos - 24):pos + len(printed) + 24]
        if len(frag) < 20:
            continue
        return {"security_id": row["security_id"], "field_id": row["field_id"],
                "period_key": row["period_key"], "meta_field": row["meta_field"],
                "value_B": v, "document_id": doc, "source_page": str(pi + 1),
                "evidence_quote": frag[:20], "original_page": str(pi + 1),
                "original_fragment": frag, "original_value_text": printed,
                "value_in_quote": v,
                "judgement_basis": ("核对 %s 字段终值 %s：原件 p.%d 印出 %s，按字段规则"
                                    "%s 判定与 B 的 %s 一致，不构成实质差异"
                                    % (row["meta_field"], v, pi + 1, printed,
                                       kind, v)),
                "conclusion": "CONFIRMED_EXPLAINED",
                "review_role": "SELF_CHECK", "reviewer": "self-check-agent",
                "reviewed_at": "2026-11-12"}
    return None


_CTRL = None
for _r in extra:
    if _r["meta_field"] not in FIELD_RULES:
        continue
    _g = _genuine_review(_r)
    if _g is not None:
        _CTRL = (_r, _g)
        break

# 单位折算直测：第十轮 B1/C 项——`unit` / `unit_scale` 键名与千分位解析
unit_path_ok = (_field_support("NUM", "187,875.40", "1878754000", "10000", "", {})[0]
                and not _field_support("NUM", "187875.40", "1878754000", "1", "", {})[0]
                and pv._num_in_quote("187,875.40", "1878754000", "10000"))

inj = {}
ctrl_row, ctrl_ent, ctrl_ok = None, None, None
c24_reason = ""
if _CTRL is None:
    c24_reason = "NO_GENUINE_CONTROL_ROW"
else:
    ctrl_row, ctrl_ent = _CTRL
    _rel = dict(ctrl_row)
    _rel["resolution"] = "RESOLVED_FIELD_LEVEL_CHECK"
    _rel["content_review_ref"] = review_key(_rel)
    _k = (ctrl_row["security_id"], ctrl_row["field_id"],
          ctrl_row["period_key"], ctrl_row["meta_field"])
    _saved = REVIEWS.get(_k)
    REVIEWS[_k] = ctrl_ent
    try:
        ctrl_ok = review_gap(_rel) is None
    finally:
        if _saved is None:
            REVIEWS.pop(_k, None)
        else:
            REVIEWS[_k] = _saved

    _pk = _rel["period_key"]
    _alt = "20250930" if _pk != "20250930" else "20251231"
    _pg0 = int(ctrl_ent["original_page"])
    _other_pg = 1 if _pg0 != 1 else 2
    _pages = pdf_pages(ctrl_row["security_id"], ctrl_ent["document_id"]) or []
    _ptxt = _pages[_pg0 - 1] if 0 <= _pg0 - 1 < len(_pages) else ""
    _pv = ctrl_ent["original_value_text"]
    _boiler = ""
    for _i in range(0, max(1, len(_ptxt) - 40), 8):
        _w = _ptxt[_i:_i + 40]
        if len(_w) >= 20 and _pv not in _w:
            _boiler = _w
            break
    _other_amt, _other_frag = None, None
    if FIELD_RULES.get(ctrl_row["meta_field"], ("",))[0] == "NUM":
        _pv_num = _as_num(_pv)
        for _m in re.finditer(r"-?\d[\d,]*\.\d{2}", _ptxt):
            _cand = _m.group(0)
            # 必须换成一个**数值不同**的数：同一数的不同写法（有无千分位）不构成绕过
            if _cand != _pv and _as_num(_cand) not in (_pv_num, _as_num(ctrl_row["value_B"])):
                _other_amt = _cand
                _other_frag = _ptxt[max(0, _m.start() - 24):_m.end() + 24]
                break

    inj["no_review"] = _leak_with(dict(_rel, content_review_ref=""), None)
    inj["unbound_digest"] = _leak_with(
        dict(_rel, content_review_ref="CR-000000000000"), ctrl_ent)
    inj["wrong_period_key"] = _inj(_rel, ctrl_ent, period_key=_alt)
    inj["document_mismatch"] = _inj(_rel, ctrl_ent, document_id="")
    inj["placeholder_reviewer"] = _inj(_rel, ctrl_ent, reviewer="x")
    inj["no_date"] = _inj(_rel, ctrl_ent, reviewed_at="")
    inj["role_unmarked"] = _inj(_rel, ctrl_ent, review_role="")
    inj["conclusion_invalid"] = _inj(_rel, ctrl_ent, conclusion="PENDING")
    inj["fragment_wrong_page"] = _inj(_rel, ctrl_ent, original_page=str(_other_pg))
    # 条件型注入：构造不出对照物时记 `caught=None`，由 `not_exercised` 单列，
    # 不再用「(True, 占位原因)」蒙混成通过（第十一轮 G 项）
    inj["fragment_boilerplate"] = (_inj(_rel, ctrl_ent, original_fragment=_boiler)
                                   if _boiler else (None, "SKIP_NO_BOILERPLATE"))
    inj["value_not_declared"] = _inj(_rel, ctrl_ent, value_in_quote="0.00")
    inj["basis_placeholder"] = _inj(
        _rel, ctrl_ent, judgement_basis="已核对，无问题，可以放行，不必再查")
    inj["same_page_other_amount"] = (
        _inj(_rel, ctrl_ent, original_value_text=_other_amt,
             original_fragment=_other_frag) if _other_amt
        else (None, "SKIP_NO_SECOND_AMOUNT"))

# 第十轮 C 项实测绕过：枚举字段用封面年份映射出内部枚举名
_enum_row = {"security_id": "SH:600444", "field_id": "FIN.COST.YTD",
             "period_key": "20251231", "meta_field": "period_source",
             "value_B": "LEGACY_SNAPSHOT", "class": "VALUE",
             "resolution": "PENDING_FIELD_LEVEL_CHECK"}
_enum_row["content_review_ref"] = review_key(_enum_row)
_enum_caught = None
_b = D10.get(("SH:600444", "FIN.COST.YTD", "20251231")) or {}
if (_b.get("document_id") or "").strip():
    _enum_ent = {"security_id": "SH:600444", "field_id": "FIN.COST.YTD",
                 "period_key": "20251231", "meta_field": "period_source",
                 "value_B": "LEGACY_SNAPSHOT", "conclusion": "CONFIRMED_EXPLAINED",
                 "review_role": "SELF_CHECK", "reviewer": "self-check-agent",
                 "reviewed_at": "2026-11-12", "original_value_text": "2025",
                 "value_in_quote": "LEGACY_SNAPSHOT",
                 "document_id": _b["document_id"].strip(),
                 "judgement_basis": ("period_source 字段终值 LEGACY_SNAPSHOT：封面年份 "
                                     "2025 映射为旧快照来源，属内部枚举，PDF 无枚举字面")}
    for _pi, _t in enumerate(pdf_pages("SH:600444", _b["document_id"].strip()) or []):
        if "2025" in _t:
            _pos = _t.index("2025")
            _enum_ent["original_page"] = str(_pi + 1)
            _enum_ent["source_page"] = str(_pi + 1)
            _enum_ent["original_fragment"] = _t[max(0, _pos - 24):_pos + 28]
            if len(_enum_ent["original_fragment"]) >= 20:
                _enum_caught = _inj(_enum_row, _enum_ent)
            break

# 逐项断言「预期拒绝原因」（第十轮 G 项：不能只看布尔，要看拦在哪一道）
# 第十一轮 G 项：本表与 `inj` 的键集合必须**严格相等**，缺项/多项都算失败
EXPECT_REASON = {
    "no_review": "RELEASE_WITHOUT_CONTENT_REVIEW",
    "unbound_digest": "LEDGER_NOT_LINKED_TO_REVIEW",
    "wrong_period_key": "REVIEW_KEY_MISMATCH",
    "document_mismatch": "REVIEW_DOCUMENT_MISMATCH",
    "placeholder_reviewer": "REVIEW_WITHOUT_REVIEWER",
    "no_date": "REVIEW_WITHOUT_DATE",
    "role_unmarked": "REVIEW_ROLE_UNMARKED",
    "conclusion_invalid": "REVIEW_WITHOUT_CONCLUSION",
    "fragment_wrong_page": "REVIEW_FRAGMENT_NOT_IN_ORIGINAL_PAGE",
    "fragment_boilerplate": "REVIEW_PRINTED_VALUE_NOT_IN_FRAGMENT",
    "value_not_declared": "REVIEW_VALUE_NOT_DECLARED",
    "basis_placeholder": "REVIEW_BASIS_TOO_SHORT",
    # 同页异数：数值字段须拦在「印刷值不支持终值」，文本字段拦在「印刷值不在片段中」
    "same_page_other_amount": ("REVIEW_PRINTED_VALUE_NOT_SUPPORT_VALUE",
                               "REVIEW_PRINTED_VALUE_NOT_IN_FRAGMENT"),
}
inj_keys, expect_keys = set(inj), set(EXPECT_REASON)
key_gap = sorted(expect_keys - inj_keys)     # 登记了预期原因，却没有对应注入
key_extra = sorted(inj_keys - expect_keys)   # 有注入，却没登记预期原因（拼错/漏登）
reason_mismatch, not_exercised = {}, {}
for _k in sorted(inj_keys & expect_keys):
    _caught, _why = inj[_k]
    if _caught is None:                      # 条件型注入没构造出对照物
        not_exercised[_k] = _why
        continue
    if not _caught:
        reason_mismatch[_k] = "NOT_CAUGHT"
        continue
    _exp = EXPECT_REASON[_k]
    if _why not in (_exp if isinstance(_exp, tuple) else (_exp,)):
        reason_mismatch[_k] = _why

# 枚举注入：PASS 条件必须包含「拦在 REVIEW_FIELD_RULE_UNDEFINED」这一具体原因
enum_reason = _enum_caught[1] if _enum_caught else "NO_ENUM_CONTROL"
enum_ok = bool(_enum_caught) and _enum_caught[0] and enum_reason == "REVIEW_FIELD_RULE_UNDEFINED"

add("C24", "补充元数据放行须有外部审查登记表记录：键+终值+原件页定位+印刷值+字段级映射规则；"
           "审查角色显式标注（自检亦须标注）；无规则字段一律待核",
    not leak and ctrl_ok and unit_path_ok and not reason_mismatch
    and not key_gap and not key_extra and not not_exercised
    and all(v[0] for v in inj.values() if v[0] is not None) and enum_ok,
    {"leaked": len(leak), "sample": [str(x) for x in leak[:5]],
     "reason": c24_reason,
     "control_key": ("|".join([ctrl_row["security_id"], ctrl_row["field_id"],
                               ctrl_row["period_key"], ctrl_row["meta_field"]])
                     if ctrl_row else ""),
     "control_accepted": ctrl_ok,
     "unit_path_ok": unit_path_ok,
     "injections": {k: {"caught": v[0], "reason": v[1]} for k, v in inj.items()},
     "injection_keys_equal_expect": (not key_gap and not key_extra),
     "expect_reason_keys": len(expect_keys),
     "key_gap": key_gap,
     "key_extra": key_extra,
     "reason_mismatch": reason_mismatch,
     "not_exercised": not_exercised,
     "injection_enum_rule_undefined": enum_reason,
     "injection_enum_ok": enum_ok,
     "review_register_rows": len(REVIEWS),
     "rule_undefined_fields": RULE_UNDEFINED_FIELDS,
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

# 第十一轮 A 项：新增「结构性新主语」判据必须做 A/B 回放，证明对存量零影响。
# 回放由 `replay_polarity_v5.py` 生成（reproduce 顺序：sampling_v5 → replay_polarity_v5 → verify_v5）。
_p_replay = OUT / "replay_polarity_v5.json"
_replay = (json.loads(_p_replay.read_text(encoding="utf-8"))
           if _p_replay.exists() else None)
if _replay is None:
    c34.append("REPLAY_MISSING")
elif (_replay.get("documents") != 1007 or _replay.get("clause_changed") != 0
      or _replay.get("polarity_changed") != 0):
    c34.append("REPLAY_CHANGED_EXISTING_EVIDENCE")

add("C34", "极性回归：%d 条反例（含第八轮裁决表五条原文用例 + 三协电机真实版面）"
           "；1,007 份存量证据 A/B 回放须分句与极性均零变化" % len(pc.CASES),
    not c34, {"violations": c34,
              "case_count": len(pc.CASES),
              "case_failures": _pc_bad,
              "replay_ab": (_replay or "MISSING"),
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
def _fmt_parent(v, unit):
    """按 unit_scale 还原「原文印刷值」：value_cny / 单位倍数。"""
    try:
        mult = float(unit or "1") or 1.0
        return "{:,.2f}".format(float(v) / mult)
    except (TypeError, ValueError):
        return str(v)


_GENERIC_QUOTE = "本报告期与上期数据均按同一合并范围列示口径一致可比无需调整"


def _parent_sides(k):
    """返回 (k1, k2, b1, b2)；不满足可核证前提时返回 None。"""
    if not es.SIMPLE_SQ.__contains__(k[1]) or es.is_q1(k[2]):
        return None
    ytd = k[1][:-3] + ".YTD"
    k1, k2 = (k[0], ytd, k[2]), (k[0], ytd, prev_quarter(k[2]))
    b1, b2 = _parent_basis(k1), _parent_basis(k2)
    if not b1 or not b2:
        return None
    if not (b1["scope"] and b1["unit"] and b1["cur"]):
        return None
    if (b1["scope"], b1["unit"], b1["cur"]) != (b2["scope"], b2["unit"], b2["cur"]):
        return None
    if b1["unit"] not in pv.AMOUNT_UNITS:
        return None
    if (pv.ver_class(b1["ver"]) is None
            or pv.ver_class(b1["ver"]) != pv.ver_class(b2["ver"])):
        return None
    return k1, k2, b1, b2


def _inject_parent_chain():
    """挑一条口径一致的真实累计差分键，用合成原文源验证判定链。

    生产路径改为回读原件登记页；这里只替换「原文源」以便把判定链逐环拆开验证，
    不改变任何判定规则。第十轮 B 项后，登记记录还必须绑定：期间列头（须出现在
    引文里）、物理页码（引文须落在该页）、目标指标名、调整版本（须等于该父实际
    version_used 的归类）、以及引文中的父数。
    """
    for k in diff_keys:
        sides = _parent_sides(k)
        if sides is None:
            continue
        k1, k2, b1, b2 = sides
        metric = (pv.METRIC_ALIASES.get(k1[1]) or ("",))[0]
        if not metric:
            continue
        ver = pv.ver_class(b1["ver"])
        mark = "调整后" if ver == "RESTATED" else ""
        q1 = "合并利润表%s%s%s元本期累计数%s口径列示" % (
            mark, metric, _fmt_parent(b1["val"], b1["unit"]), b1["scope"])
        q2 = "合并利润表%s%s%s元上期累计数%s口径列示" % (
            mark, metric, _fmt_parent(b2["val"], b2["unit"]), b2["scope"])
        ent = {"security_id": k[0], "field_id": k[1], "period_key": k[2],
               "ytd_field": k1[1],
               "p1_doc": b1["doc"], "p2_doc": b2["doc"],
               "p1_period": k1[2], "p2_period": k2[2],
               "p1_value": b1["val"], "p2_value": b2["val"],
               "p1_page": "1", "p2_page": "1",
               "p1_quote": q1, "p2_quote": q2,
               "p1_column": "本期累计数", "p2_column": "上期累计数",
               "p1_adjust_version": ver, "p2_adjust_version": ver,
               "consolidation_scope": b1["scope"], "unit_scale": b1["unit"],
               "currency": b1["cur"],
               "scope_basis": "两期均取合并利润表同一合并范围、同一币种、同一单位列示的累计数",
               "conclusion": "COMPATIBLE", "review_role": "SELF_CHECK",
               "reviewer": "injection", "reviewed_at": "2026-11-11"}
        src = {(b1["doc"], "1"): q1 + "…" + q2 + "…" + _GENERIC_QUOTE,
               (b2["doc"], "1"): q1 + "…" + q2 + "…" + _GENERIC_QUOTE}
        return k, ent, src
    return None, None, None


def _real_parent_case():
    """真实原件阳性对照：两个父数都确实印在原件对应页上，登记即可判 YES。

    第十轮 B 项：原注入链只用合成原文源，不能证明「生产路径（回读原件）可用」。
    引文取「期间列头 → 目标行金额」的连续片段，使指标名、期间列头、父数三者
    同时落在引文内（这正是第十轮 B2 要求的绑定方式）。
    """
    for k in diff_keys:
        sides = _parent_sides(k)
        if sides is None:
            continue
        k1, k2, b1, b2 = sides
        metric = (pv.METRIC_ALIASES.get(k1[1]) or ("",))[0]
        if not metric:
            continue
        ver = pv.ver_class(b1["ver"])
        pages1 = pdf_pages(k[0], b1["doc"]) or []
        pages2 = pdf_pages(k[0], b2["doc"]) or []
        if not pages1 or not pages2:
            continue

        def _loc(pages, b):
            """第十一轮 B 项：栏目按**词坐标**取，不再取「金额前最后一个期间词」。

            Codex 实测：`BJ:920289` p.10 的 57,296,869.60 在「本期」列，旧实现
            因文字流里「上年同期」排在金额之前，把栏目写成上年同期——真实阳性
            本身就是错列反例。
            """
            want = _fmt_parent(b["val"], b["unit"])
            pdf = pdf_file(k[0], b["doc"])
            if pdf is None:
                return None
            for pi, t in enumerate(pages, 1):
                if want not in t:
                    continue
                words = pv.page_words(pdf, pi)
                col, _amt = pv.column_of_amount(words, b["val"])
                if not col or not pv._PERIOD_COL.search(col):
                    continue
                j = t.find(want)
                hidx = t.rfind(col, 0, j)
                if hidx < 0:
                    hidx = max(0, j - 60)
                lo = hidx
                if ver == "ORIGINAL":
                    for bad in ("调整后", "重述后", "更正后"):
                        k2i = t.rfind(bad, hidx, j)
                        if k2i >= 0:
                            lo = max(lo, k2i + len(bad))
                w = t[lo:j + len(want) + 12]
                if len(w) < 20 or metric not in w or want not in w:
                    continue
                return str(pi), w, col
            return None

        l1, l2 = _loc(pages1, b1), _loc(pages2, b2)
        if not l1 or not l2:
            continue
        ent = {"security_id": k[0], "field_id": k[1], "period_key": k[2],
               "ytd_field": k1[1],
               "p1_doc": b1["doc"], "p2_doc": b2["doc"],
               "p1_period": k1[2], "p2_period": k2[2],
               "p1_value": b1["val"], "p2_value": b2["val"],
               "p1_page": l1[0], "p2_page": l2[0],
               "p1_quote": l1[1], "p2_quote": l2[1],
               "p1_column": l1[2], "p2_column": l2[2],
               "p1_adjust_version": ver, "p2_adjust_version": ver,
               "consolidation_scope": b1["scope"], "unit_scale": b1["unit"],
               "currency": b1["cur"],
               "scope_basis": "两期均取合并利润表同一合并范围、同一币种、同一单位列示的累计数",
               "conclusion": "COMPATIBLE", "review_role": "SELF_CHECK",
               "reviewer": "self-check-agent", "reviewed_at": "2026-11-12"}
        return k, ent
    return None, None


def _pgap(k, ent, src, col_of=None):
    """直接取 gap() 的拒绝原因（第十轮 G 项：断言拦在哪一道）。"""
    sides = _parent_sides(k)
    if sides is None:
        return "PRECONDITION"
    k1, k2, b1, b2 = sides
    if isinstance(src, dict):
        _m = src
        src = lambda d, p: _m.get((d, str(p)), "")
    return pv.gap(ent, _expect(k1, k2, b1, b2), src, col_of=col_of)


_pk, _pent, _psrc = _inject_parent_chain()
_real_k, _real_ent = _real_parent_case()
# 单位路径直测（第十轮 B1 项）：1 / 1000 / 10000 三档都要正确折算
unit_paths_ok = (
    pv._num_in_quote("187,875.40", "1878754000", "10000")
    and pv._num_in_quote("1,878,754.00", "1878754000", "1000")
    and pv._num_in_quote("1,878,754,000.00", "1878754000", "1")
    and not pv._num_in_quote("187,875.40", "1878754000", "1")
    and not pv._num_in_quote("187,875.40", "1878754000", "1000")
)
if _pk is None:
    c37.append("NO_INJECTABLE_PARENT_CASE")
    chain, c37_reason = {}, {}
else:
    chain, c37_reason = {}, {}
    chain["with_record"] = parent_compatible(_pk, {_pk: _pent}, _psrc) is True
    chain["no_record"] = parent_compatible(_pk, {}, _psrc) is False

    EXPECT = [
        ("wrong_conclusion", {"conclusion": "NOT_COMPATIBLE"},
         "VERIFICATION_NOT_COMPATIBLE"),
        ("value_mismatch", {"p1_value": "0"}, "PARENT_VALUE_MISMATCH"),
        ("quote_not_located", {"p1_quote": "此引文在原文中并不存在用于测试定位失败"},
         "PARENT_QUOTE_NOT_LOCATED"),
        ("empty_scope", {"unit_scale": ""}, "SCOPE_FIELD_EMPTY"),
        ("no_reviewer", {"reviewer": ""}, "VERIFICATION_WITHOUT_REVIEWER"),
        ("p2_quote_missing", {"p2_quote": ""}, "PARENT_QUOTE_TOO_SHORT"),
        ("doc_mismatch", {"p1_doc": "DOC-01140151955D939E"}, "PARENT_DOC_MISMATCH"),
        ("p2_doc_mismatch", {"p2_doc": "DOC-01140151955D939E"}, "PARENT_DOC_MISMATCH"),
        ("period_mismatch", {"p1_period": "20250331"}, "PARENT_PERIOD_MISMATCH"),
        ("column_empty", {"p1_column": ""}, "PARENT_COLUMN_EMPTY"),
        # 第十轮 B2 项：栏目必须是期间列头，且须出现在引文里
        ("column_not_period", {"p1_column": "营业收入"}, "PARENT_COLUMN_NOT_PERIOD"),
        ("column_not_in_quote", {"p1_column": "2024年12月31日"},
         "PARENT_COLUMN_NOT_IN_QUOTE"),
        ("page_invalid", {"p1_page": ""}, "PARENT_PAGE_INVALID"),
        ("quote_on_wrong_page", {"p1_page": "7"}, "PARENT_SOURCE_UNAVAILABLE"),
        ("adjust_version_invalid", {"p1_adjust_version": "MIXED"},
         "PARENT_ADJUST_VERSION_INVALID"),
        ("adjust_version_mismatch",
         {"p1_adjust_version": "RESTATED" if _pent["p1_adjust_version"] == "ORIGINAL"
          else "ORIGINAL"}, "PARENT_ADJUST_VERSION_MISMATCH"),
        # 两父声明不同版本时，先被「该侧声明 != 该侧实际归类」拦住；
        # 声明一致性的检查只在两侧都能对上实际版本时才可达（此时必然一致）。
        ("adjust_version_other_side", {"p2_adjust_version": "RESTATED"
                                       if _pent["p1_adjust_version"] == "ORIGINAL"
                                       else "ORIGINAL"},
         "PARENT_ADJUST_VERSION_MISMATCH"),
        ("scope_mismatch", {"consolidation_scope": "PARENT_ONLY"},
         "SCOPE_MISMATCH_WITH_PARENT"),
        ("scope_basis_missing", {"scope_basis": "一致"}, "SCOPE_BASIS_MISSING"),
        ("reviewer_placeholder", {"reviewer": "x"}, "VERIFICATION_WITHOUT_REVIEWER"),
        ("no_date", {"reviewed_at": ""}, "VERIFICATION_WITHOUT_DATE"),
        ("role_unmarked", {"review_role": ""}, "VERIFICATION_WITHOUT_ROLE"),
        ("quote_without_parent_value", {"p1_quote": _GENERIC_QUOTE},
         "PARENT_QUOTE_WITHOUT_TARGET_METRIC"),
        # 同数异义：引文含该父数，但点的是另一个指标 → 必须拒
    ]
    # 同数异义需要专属原文源：改过的引文不在原合成源里，否则会先被「引文不可定位」拦住
    _q_other = _pent["p1_quote"].replace(
        (pv.METRIC_ALIASES.get(_pent["ytd_field"]) or ("",))[0], "营业成本")
    _src_other = dict(_psrc)
    _src_other[(_pent["p1_doc"], "1")] = _q_other + "…" + _pent["p2_quote"]
    _e = dict(_pent)
    _e["p1_quote"] = _q_other
    chain["quote_other_metric"] = parent_compatible(_pk, {_pk: _e}, _src_other) is False
    c37_reason["quote_other_metric"] = _pgap(_pk, _e, _src_other)
    if chain["quote_other_metric"] and             c37_reason["quote_other_metric"] != "PARENT_QUOTE_WITHOUT_TARGET_METRIC":
        c37_reason["_mismatch_quote_other_metric"] = "PARENT_QUOTE_WITHOUT_TARGET_METRIC"
    for name, over, want in EXPECT:
        e = dict(_pent)
        e.update(over)
        chain[name] = parent_compatible(_pk, {_pk: e}, _psrc) is False
        got = _pgap(_pk, e, _psrc)
        c37_reason[name] = got
        if chain[name] and got != want:
            c37_reason["_mismatch_" + name] = want
    # 版本标记：原版引文里出现「调整后」必须拒（引的其实是调整后列）
    if _pent["p1_adjust_version"] == "ORIGINAL":
        e = dict(_pent)
        e["p1_quote"] = "调整后" + e["p1_quote"]
        chain["original_quote_with_restated_mark"] = \
            parent_compatible(_pk, {_pk: e}, _psrc) is False
        c37_reason["original_quote_with_restated_mark"] = _pgap(_pk, e, _psrc)
    else:
        e = dict(_pent)
        e["p1_quote"] = e["p1_quote"].replace("调整后", "")
        chain["restated_quote_without_mark"] = \
            parent_compatible(_pk, {_pk: e}, _psrc) is False
        c37_reason["restated_quote_without_mark"] = _pgap(_pk, e, _psrc)
    if not all(chain.values()):
        c37.append("VERIFICATION_CHAIN_BROKEN:%s" % {k: v for k, v in chain.items() if not v})
    if any(k.startswith("_mismatch_") for k in c37_reason):
        c37.append("REASON_MISMATCH:%s"
                   % {k: v for k, v in c37_reason.items() if k.startswith("_mismatch_")})

# 真实原件阳性（生产路径）：登记即判 YES，且依据是回读的物理页
real_ok = None
real_col_neg = None
real_col_unres = None
if _real_k is not None:
    _rcol = _col_of(_real_k[0])
    # 生产路径：登记即判 YES，且栏目由**词坐标**核对
    real_ok = parent_compatible(_real_k, {_real_k: _real_ent}, col_of=_rcol) is True
    if not real_ok:
        c37.append("REAL_ORIGINAL_POSITIVE_REJECTED:%s"
                   % _pgap(_real_k, _real_ent,
                           lambda d, p: _pdf_ev(_real_k[0], d, p), col_of=_rcol))
    # 第十一轮 B 项负例：坐标解析出的是**另一列**，登记却写本列 → 必须拒
    _other = "上年同期" if "上年同期" not in (_real_ent.get("p1_column") or "") else "本期"
    real_col_neg = _pgap(_real_k, _real_ent, None,
                         col_of=lambda d, p, v: _other)
    chain["real_wrong_column"] = real_col_neg == "PARENT_COLUMN_MISMATCH"
    if not chain["real_wrong_column"]:
        c37.append("REAL_WRONG_COLUMN_NOT_REJECTED:%s" % real_col_neg)
    # 坐标取不到列头 → 不得当作「栏目成立」
    real_col_unres = _pgap(_real_k, _real_ent, None, col_of=lambda d, p, v: None)
    chain["real_column_unresolved"] = real_col_unres == "PARENT_COLUMN_UNRESOLVED"
    if not chain["real_column_unresolved"]:
        c37.append("REAL_COLUMN_UNRESOLVED_NOT_REJECTED:%s" % real_col_unres)
else:
    c37.append("NO_REAL_ORIGINAL_CASE")
if not unit_paths_ok:
    c37.append("UNIT_PATH_BROKEN")


reopened = sum(1 for r in meta if r["meta_field"] == "restatement_flag"
               and r["resolution"] == "PENDING_PARENT_COMPATIBILITY")
if reopened < 1000:
    c37.append("REOPENED_PARENT_COMPAT_TOO_FEW:%d" % reopened)
add("C37", "父输入兼容性只认核证登记表：撤去真实依据后必须变 NO，跨文档已解除项重开；"
           "栏目须为期间列头且在引文中、页码须为登记页、版本须等于实际 version_used 归类",
    not c37,
    {"violations": c37, "auto_passes": len(auto_pass),
     "empty_scope_passes": len(empty_scope_pass),
     "verification_chain": chain,
     "reject_reasons": c37_reason,
     "unit_paths_ok": unit_paths_ok,
     "real_original_positive": (real_ok if _real_k is not None else "NO_CASE"),
     "real_original_key": ("|".join(_real_k) if _real_k else ""),
     "real_original_columns": ({"p1": _real_ent.get("p1_column"),
                                "p2": _real_ent.get("p2_column")} if _real_k else {}),
     "real_wrong_column_reason": real_col_neg,
     "real_column_unresolved_reason": real_col_unres,
     "register_rows": len(PARENT_VERIFS),
     "reopened_pending": reopened,
     "cumulative_diff_rows": len(diff_keys)})

# ---------------- C38 judge 的结构化核证入口（比较范围 / 季度表来源）----------------
# 第八轮 C 项：judge() 原先把这两个维度当成「证据里提到过就算覆盖」，
# 现在只接受核证登记表供给，且撤去登记后必须退回待核。
def _dim_window(pages, k, dim):
    """「目标指标名 + 具体期间表述 + 维度载体」同页窗口（第十一轮 E 项）。

    Codex 实测：`_find_dim` 找到的真实 COMPARATIVE_SCOPE 阳性是
    「经营计划2025年，公司成功登陆北京证券交易所……报告期初比较」——一段经营叙述，
    既没点出目标指标，也没点出该行的具体期间，证明不了 2025H1 单季扣非数的比较范围。
    现在要求三者同页，且窗口内出现该行年份。
    """
    names = pv.METRIC_ALIASES.get(k[1]) or pv.METRIC_ALIASES.get(
        k[1][:-3] + ".YTD" if k[1].endswith(".SQ") else k[1])
    if not names:
        return None
    nm = names[0]
    ptoks = pv._period_tokens(k[2])
    if not ptoks:
        return None
    yr = k[2][:4]
    for pi, tx in enumerate(pages, 1):
        ni = tx.find(nm)
        if ni < 0:
            continue
        # 期间表述取**离指标名最近**的一处，并纳入窗口——下游 `scope_dims` 要求
        # 引文本身含指标名与该行期间，窗口不含期间就会被判成「未覆盖」。
        best = None
        for tok in ptoks:
            j = tx.find(tok)
            while j >= 0:
                if abs(j - ni) <= 300 and (best is None or abs(j - ni) < abs(best[0] - ni)):
                    best = (j, tok)
                j = tx.find(tok, j + 1)
        if best is None:
            continue
        for mk in pv.DIM_MARKERS.get(dim, ()):
            mi = tx.find(mk, max(0, ni - 300), ni + 300)
            if mi < 0:
                continue
            lo = max(0, min(ni, mi, best[0]) - 10)
            hi = min(len(tx), max(ni, mi, best[0] + len(best[1])) + 40)
            w = tx[lo:hi]
            if len(w) >= 20 and yr in w:
                return str(pi), w
    return None


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
    if not doc or len(_nz((vrec.get(doc) or {}).get("evidence", ""))) < 12:
        continue
    _need0 = [d for d in (r["scope_missing"] or "").split(";") if d in es.SCOPE_REGISTRABLE]
    if not _need0:
        continue
    _pgs = pdf_pages(k[0], doc) or []
    if not _pgs:
        continue
    if all(_dim_window(_pgs, k, d) for d in _need0):
        _cand = (r, k, doc)
        break

if _cand is None:
    c38.append("NO_SOURCE_PROVENANCE_CASE")
    c38_detail = {}
else:
    r, k, doc = _cand
    _need = [d for d in (r["scope_missing"] or "").split(";") if d in es.SCOPE_REGISTRABLE]
    # 证据源改为**原件该页**：第九轮 E 项要求核对证据与目标键、期间、表格来源的关系，
    # 拿 results.csv.evidence 自证等于用同一来源自证；第十轮 E 项进一步要求核对
    # `source_page`，引文必须落在登记页上，且须点出该维度自己的证据载体。
    _pages = pdf_pages(k[0], doc) or []
    _yr = k[2][:4]

    def _ev(d, p):
        try:
            n = int(str(p).strip())
        except (TypeError, ValueError):
            return ""
        _ps = pdf_pages(k[0], d) or []
        return _ps[n - 1] if 1 <= n <= len(_ps) else ""

    def _find_dim(dim):
        return _dim_window(_pages, k, dim)

    _found = {d: _find_dim(d) for d in _need}
    if any(v is None for v in _found.values()):
        c38.append("NO_DIM_EVIDENCE_ON_ORIGINAL:%s"
                   % [d for d, v in _found.items() if v is None])
        c38_detail = {"key": "|".join(k), "found": {d: bool(v) for d, v in _found.items()}}
        _need = []
        recs, good = [], set()
        base = {"dimension": _need[0] if _need else ""}
        bad_concl = bad_quote = bad_reviewer = bad_role = bad_date = set()
        bad_other_doc = bad_dim = bad_target = bad_year = set()
        bad_page = bad_marker = set()
        j_no = j_yes = j_dim = {"resolution": "PENDING_SOURCE_PROVENANCE",
                                "scope_missing": ""}
    else:
        def _rec(dim, **over):
            # 未在原件检出的维度（如故意写成 PARENT_COMPATIBILITY）沿用首维的页与引文，
            # 以便单独检验「维度白名单」这一道，而不是被「引文不匹配」提前拦住。
            pg, q = _found.get(dim) or _found[_need[0]]
            e = {"security_id": k[0], "field_id": k[1], "period_key": k[2],
                 "dimension": dim, "target_field": k[1], "target_period": k[2],
                 "document_id": doc, "source_page": pg, "evidence_quote": q,
                 "conclusion": "CONFIRMED", "review_role": "SELF_CHECK",
                 "reviewer": "injection", "reviewed_at": "2026-11-12"}
            e.update(over)
            return e

        recs = [_rec(d) for d in _need]
        base = recs[0]
        _bd = base["dimension"]
        good = pv.scope_dims({k: recs}, k, _ev, expect_doc=doc)
        bad_concl = pv.scope_dims({k: [_rec(_bd, conclusion="PENDING")]}, k, _ev,
                                  expect_doc=doc)
        bad_quote = pv.scope_dims(
            {k: [_rec(_bd, evidence_quote="不存在的引文用于测试")]}, k, _ev,
            expect_doc=doc)
        bad_reviewer = pv.scope_dims({k: [_rec(_bd, reviewer="")]}, k, _ev,
                                     expect_doc=doc)
        bad_role = pv.scope_dims({k: [_rec(_bd, review_role="")]}, k, _ev,
                                 expect_doc=doc)
        bad_date = pv.scope_dims({k: [_rec(_bd, reviewed_at="")]}, k, _ev,
                                 expect_doc=doc)
        # 绕过①：用无关文档的通用引文登记季度表来源
        bad_other_doc = pv.scope_dims(
            {k: [_rec(_bd, document_id="DOC-01140151955D939E")]}, k, _ev,
            expect_doc=doc)
        # 绕过②：维度写成 PARENT_COMPATIBILITY，试图顶替父输入核证
        bad_dim = pv.scope_dims({k: [_rec(es.PARENT_COMPATIBILITY)]}, k, _ev,
                                expect_doc=doc)
        # 绕过③：目标字段/期间不是本键
        bad_target = pv.scope_dims(
            {k: [_rec(_bd, target_period="19991231")]}, k, _ev, expect_doc=doc)
        # 绕过④：引文虽长但通篇不含该行期间年份
        bad_year = pv.scope_dims(
            {k: [_rec(_bd, evidence_quote="季度表格数据来源已在附注中列示")]}, k, _ev,
            expect_doc=doc)
        # 绕过⑤（第十轮 E 项实测）：页码不核对——引文在别页，登记页写成第 1 页
        _pg = str(base["source_page"])
        _wrong_pg = "1" if _pg != "1" else "2"
        bad_page = pv.scope_dims({k: [_rec(_bd, source_page=_wrong_pg)]}, k, _ev,
                                 expect_doc=doc)
        # 绕过⑥（第十轮 E 项实测）：只有文档标题 + 年份，没有该维度的证据载体
        _title_q = None
        for t in _pages:
            yi = t.find(_yr)
            if yi < 0:
                continue
            w = t[max(0, yi - 24):yi + 20]
            if len(w) >= 12 and not any(
                    mk in w for mk in pv.DIM_MARKERS.get(_bd, ())):
                _title_q = w
                break
        bad_marker = (pv.scope_dims({k: [_rec(_bd, evidence_quote=_title_q)]}, k, _ev,
                                    expect_doc=doc) if _title_q else set())
        # 绕过⑦：页码非法
        bad_page2 = pv.scope_dims({k: [_rec(_bd, source_page="0")]}, k, _ev,
                                  expect_doc=doc)

        st = D10.get(k, {}).get("status", "")
        own = doc_period.get(doc, "")
        j_no = es.judge(vrec.get(doc), doc, st, own, k[2], bval="否", scope_ok=set(),
                        parent_ok=False)
        j_yes = es.judge(vrec.get(doc), doc, st, own, k[2], bval="否", scope_ok=good,
                         parent_ok=False)
        # 绕过②的直接检验：父输入未核时，来源登记不得把它补上
        j_dim = es.judge(vrec.get(doc), doc, st, own, k[2], bval="否",
                         scope_ok={es.PARENT_COMPATIBILITY}, parent_ok=False)
        c38_detail = {
            "key": "|".join(k),
            "without_record": j_no["resolution"],
            "with_record": j_yes["resolution"],
            "with_parent_dim_only": j_dim["resolution"],
            "dims_from_record": sorted(good),
            "dims_required": _need,
            "evidence_pages": {d: v[0] for d, v in _found.items()},
            "rejected_wrong_conclusion": not bad_concl,
            "rejected_unlocatable_quote": not bad_quote,
            "rejected_no_reviewer": not bad_reviewer,
            "rejected_role_unmarked": not bad_role,
            "rejected_no_date": not bad_date,
            "rejected_other_document": not bad_other_doc,
            "rejected_parent_dimension": not bad_dim,
            "rejected_wrong_target": not bad_target,
            "rejected_quote_without_year": not bad_year,
            "rejected_quote_on_wrong_page": not bad_page,
            "rejected_quote_without_dim_marker": not bad_marker,
            "rejected_page_invalid": not bad_page2,
        }
        if not set(_need) <= good:
            c38.append("VALID_RECORD_NOT_ACCEPTED:%s" % sorted(_need))
        if (bad_concl or bad_quote or bad_reviewer or bad_role or bad_date
                or bad_other_doc or bad_dim or bad_target or bad_year
                or bad_page or bad_marker or bad_page2):
            c38.append("INVALID_RECORD_ACCEPTED")
        if j_no["resolution"] != "PENDING_SOURCE_PROVENANCE":
            c38.append("PENDING_NOT_RESTORED_WITHOUT_RECORD:%s" % j_no["resolution"])
        if j_yes["resolution"] == "PENDING_SOURCE_PROVENANCE":
            c38.append("RECORD_DID_NOT_COVER_DIMENSION")
        if set(_need) & set((j_yes["scope_missing"] or "").split(";")):
            c38.append("DIMENSION_STILL_MISSING_WITH_RECORD")
        if not j_dim["resolution"].startswith("PENDING"):
            c38.append("PARENT_DIM_BYPASSED:%s" % j_dim["resolution"])

add("C38", "来源维度只接受比较范围/季度表来源两类登记，且须绑定目标键、期间与实际供给文档；"
           "父输入兼容不得由来源登记顶替",
    not c38,
    {"violations": c38, "detail": c38_detail,
     "register_rows": len(_sv),
     "pending_source_provenance": sum(
         1 for r in meta if r["meta_field"] == "restatement_flag"
         and r["resolution"] == "PENDING_SOURCE_PROVENANCE")})

passed = sum(1 for c in checks if c["result"] == "PASS")
review = {
    "issue_key": "S00", "stage": "ERRATA", "version": "ERRATA_V5",
    "self_check_version": "V11",
    "review_nature": "SELF_CHECK",
    "decision": "SELF_CHECK_PASS_WITH_UNRESOLVED_ITEMS" if passed == len(checks)
                else "SELF_CHECK_FAIL",
    "reviewed_at": "2026-11-12T23:40:00+08:00",
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
    "round10_fixes": [
        "极性 A 项五条新绕过全修：单符号跨行（√ 独占一行）合并、含符号的原因标签仍作主语行、"
        "「适用」与「某原因未勾」并存判歧义、无关报表项目金额不再承接为主语肯定、"
        "单原因分句金额直绑（不再受 24 字半径限制）→ C34 增至 30 条反例；"
        "回放 1,007 份证据分句变化 0 / 极性变化 0",
        "父输入单位折算键名修正：gap() 原读 expect[side]['unit']，_expect() 给的是 unit_scale，"
        "折算恒为 1 倍（187,875.40 万元 = 1,878,754,000 元 会被拒）→ 统一改读 unit_scale，"
        "并限定金额字段只接受 1/1000/10000 三档",
        "父输入栏目与版本改为可核：栏目须为期间列头且出现在引文中；调整版本须等于该父实际 "
        "version_used 的归类（ORIGINAL / RESTATED），且引文须有对应标记（重述后 / 无调整后列）",
        "父输入引文源改为回读原件登记页（_pdf_page），不再用 results.csv.evidence 上游摘录；"
        "C37 注入链（第十一轮扩到 29 环）+ 真实原件阳性 + 单位三档 + 错误栏目 + 同数异义负例，"
        "并逐项断言拒绝原因",
        "C24 数值解析修正：先去掉千分位逗号再比较；同页上年数冒充本期终值不再过关；"
        "并新增登记记录必须属于该键（REVIEW_KEY_MISMATCH）",
        "C24 枚举字段不再由自述承担举证：改为字段规则表 FIELD_RULES（NUM/UNIT/DATE/LITERAL/SELF_PAGE），"
        "11 个无规则字段一律 REVIEW_FIELD_RULE_UNDEFINED 留待核",
        "C24 故障注入改为以完整正例为基线、每次只改一个条件，并断言具体拒绝原因（13 种 + 枚举 1 种）",
        "C14 绑定正式裁决表条目：引文所在行必须是裁决表行（| Qn … |），裁决项标题必须点名该键，"
        "结论须来自该行结论单元格 → 「三项都填大豪科技 + 引第 88 行登记说明」不再通过",
        "C38 来源维度核对 source_page 并绑定维度证据载体：引文须落在登记页，且须含分季度/比较/上年同期等"
        "该维度自己的关键词；封面片段「Ltd.年度报告——2025——」不再同时取得两个维度",
        "R6 改为按词坐标确认目标行与目标列：金额所在行的左侧标签须含目标指标（支持换行标签回退），"
        "列头取金额 x 区间正上方最近的期间列头，单位绑定该表表头并做固定映射对照，"
        "调整前后取原件列头附近标记；三条样本 p1/p2 均 LOCATED_OK",
    ],
    "interrupt_fixes_round11": [
        "C14 裁决只解除它裁定的那一个键：`ruling_gap()` 新增 `ruled_key` 必须与待判键三元组"
        "完全相等（`RULING_RULED_KEY_MISSING` / `RULING_KEY_MISMATCH`）。此前只在 `check_c14` 里比对，"
        "单独调判据时同一公司的其他字段也能过——判据必须自带绑定，不能靠调用方代劳",
        "C14 结论不得用否定表述：`ruling_verdict` 须与结论单元格去掉强调符后**前缀匹配**"
        "（`RULING_VERDICT_NOT_IN_ROW`），且不得含否定词（`RULING_VERDICT_NEGATED`）。"
        "此前只查子串，从同一格末尾截出「不代表全公司验收」即可通过",
    ],
    "round11_fixes": [
        "A｜极性「结构性新主语」：金额左侧紧跟片段以名词收尾（且不含受影响权益项目、"
        "不是动词/量词/标点收尾）即判为新主语，不再承接前一分句的原因。"
        "「前期差错更正对期初未分配利润影响0.00元，其中营业总收入100.00元」"
        "不再把 100.00 判成 ERRATA 肯定 → C34 增至 33 条反例（新增 ⑭ 词表外/词表内项目切换、"
        "⑮ 权益项目续写守护）",
        "B｜父输入栏目改按**词坐标**核实：金额词 → x 中心 → 同 x 区间上方最近的非数值词 = 实际列头，"
        "与登记的 p1_column/p2_column 归一化后比对；取不到列头记 PARENT_COLUMN_UNRESOLVED。"
        "BJ:920289 的「上年同期」冒充「本期」不再过关；C37 新增 2 条真实负例（错列 / 列头不可解）",
        "C｜C24 文本字段改按**标签**绑定：unit_raw 须见「单位：」、currency 须见「币种/货币/记账本位币」，"
        "且 evidence_label 须与紧随其后的金额相邻（20 字内出现数字），不再拿片段里的「2025」蒙过；"
        "SELF_PAGE 改为**独立定位**——该行金额在原件里最早出现的页，而不是比对两个自报页码",
        "D｜C14 裁决适用范围独立维护：新增 ruling_scope.csv（section → allowed_key），"
        "裁决必须同时满足「ruled_key 精确等于待判键」与「该键在登记范围内」"
        "（RULING_KEY_NOT_IN_SCOPE）；`key` 与 `ruled_key` 一起改写不再能借用原裁决",
        "E｜C38 维度证据要求「目标指标名 + 该行具体期间表述 + 维度载体」同页同窗口，"
        "窗口须含该行年份；经营计划叙述「报告期初比较」不再算 COMPARATIVE_SCOPE 覆盖",
        "F｜R6 词坐标：断行标签向上回看 3 行逐行拼接，直到出现目标指标名；"
        "调整前后标记只取与金额 x 区间重叠的词，页内别列的「调整前」不再串味；"
        "600053 断行误判改判为已定位",
        "G｜C24 注入键集合与预期原因集合**严格相等**（key_gap / key_extra 均为 0 才算过）；"
        "no_review / unbound_digest 改为从 extra_leaks 捕获实际拒绝原因，不再写死字符串；"
        "fragment_wrong_page 纳入预期原因表；条件型注入构造不出对照物时记 not_exercised 并判失败，"
        "不再用「(True, 占位原因)」蒙混；枚举注入把 REVIEW_FIELD_RULE_UNDEFINED 纳入 PASS 条件；"
        "C14 注入同样改为一张表管住「注入名→改法→预期原因」，10 种逐项比对",
        "H（维护意见）｜同一份自检摘要不再维护两处：active_issue.json 顶层 self_check 降为指针，"
        "canonical 指向 s00_errata.self_check，避免明细两处漂移",
        "新增 sampling_keys_diff.csv：抽样键集相对上一交付版（V10）的增加/删除/保留逐键留痕，"
        "带样本 ID、原因、定位器版本与前后来源哈希；基线冻结在 sampling_keys_baseline.csv",
    ],
    "open_findings": [
        "NOTE_TRACE_NA 总量 9,954 条 / 631 份文档；其中已解除 8,655 条 / 630 份，剩余 1,299 条 / 1 份仍待核。第 4 步须按「文档版本+具体栏目+实际选项组+覆盖期间」核共同事实再映射成员键，已解除的 8,655 条同样复审",
        "NOTE_RETAINED_ERRATA_ZERO 642 条（自身 563 / 非自身 79）待核实，未凭注记批量放行",
        "SH:600936 FIN.REV.SQ@20250630 的核验证据在原件全文无法定位，属上游核验记录问题",
        "第 4 步批量核证（文档级事件确认 / 字段级影响确认 / 采用链确认）未开始",
        "第 5 步重算分层与受限表未开始；44/231/378 未锁定",
        "锚定期回退与上游准入的间接依赖未覆盖",
    ],
    "not_independent": "执行方自检，不构成独立验收；仅抽验 37 行 / 20 类 / 27 键回读原件物理页（见 sampling_v5.json 的 samples / risk_types / unique_keys）。",
    "release_S05": False,
}
(OUT / "review.json").write_text(
    json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

for c in checks:
    print("%s %-6s %s" % (c["id"], c["result"], c["name"]))
    if c["result"] == "FAIL":
        print("      ", json.dumps(c["detail"], ensure_ascii=False)[:400])
print("\n%d/%d PASS → %s" % (passed, len(checks), review["decision"]))
