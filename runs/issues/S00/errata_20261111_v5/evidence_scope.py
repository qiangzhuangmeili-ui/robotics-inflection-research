#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""证据覆盖模型 V6（生产与自检共用）

第六轮裁决的三处修正：

1. **期间参数**（第二节）：`required_scope` 之前用 `if not own_period` 判断是否非自身期间，
   但调用方传的是文档期间字符串（如 "20251231"），非空恒真——1,240 条非自身期间记录
   从未要求 COMPARATIVE_SCOPE。V6 改为显式接收 `document_period` 与 `row_period`，
   内部计算 `is_own`，未知期间单列。

2. **极性**（第三节）：之前「出现即视为排除」。V6 按分句判断极性，区分
   `EXCLUDED`（明确不适用/未发生）、`AFFIRMED`（确认发生/非零金额）、
   `SCOPED_ONLY`（只对特定项目给出金额，不覆盖本字段）。
   `0.00元` 用负向后视避免命中 `100.00元` 的尾部。

3. **累计差分**（第二节）：撤销「同报告内相减自动抵消」的理由。差分是否抵消取决于
   两期调整额是否相等，不能由「同一报告」推出。改为要求 `PARENT_COMPATIBILITY`：
   两个父输入的文档/版本/合并范围/单位必须兼容，由调用方按 B 实际行计算后传入。
"""
import re

ERRATA = "ERRATA"
MERGER_RETRO = "MERGER_RETRO"
POLICY_CHANGE = "POLICY_CHANGE"
QUARTERLY_TABLE_PROVENANCE = "QUARTERLY_TABLE_PROVENANCE"
COMPARATIVE_SCOPE = "COMPARATIVE_SCOPE"
PARENT_COMPATIBILITY = "PARENT_COMPATIBILITY"
DOC_PERIOD_UNKNOWN = "DOC_PERIOD_UNKNOWN"

CAUSES = [ERRATA, MERGER_RETRO, POLICY_CHANGE]
SOURCE_DIMS = [QUARTERLY_TABLE_PROVENANCE, COMPARATIVE_SCOPE, PARENT_COMPATIBILITY]

_RE_ERRATA = re.compile(r"追溯重述|差错更正|前期差错")
_RE_MERGER = re.compile(r"同一控制|合并范围")
_RE_POLICY = re.compile(r"会计政策")
# 否定：明确不适用 / 未发生 / 无
_RE_NEG = re.compile(r"不适用|未发生|未采用|未涉及|不存在|未进行|无需|没有发生|无重大|无前期|均无|☑否|√否|□否")
# 肯定：确认发生 / 已采用 / 已调整
_RE_POS = re.compile(r"发生|存在|采用|已调整|追溯调整|已重述")
# 金额：负向后视，避免 100.00元 命中 0.00元
_RE_ZERO = re.compile(r"(?<![\d.])0\.00\s*元")
_RE_AMOUNT = re.compile(r"-?\d[\d,]*\.\d{2}\s*元")
# 只对特定项目给出结论（不覆盖本字段）
_RE_SCOPED_ITEM = re.compile(r"期初未分配利润|未分配利润|所有者权益|盈余公积|净资产")

SCOPE_LIMITED_METHODS = {"IMPORTANT_MATTER_NA", "NOTE_RETAINED_ERRATA_ZERO"}
METHOD_STRENGTH = {
    "IMPORTANT_MATTER_NA": "SCOPE_LIMITED",
    "NOTE_RETAINED_ERRATA_ZERO": "SCOPE_LIMITED_QUANTIFIED",
    "NOTE_TRACE_NA": "BOILERPLATE_CHECKBOX",
    "CHECKBOX_NA": "BOILERPLATE_CHECKBOX",
    "CHECKBOX_NO": "BOILERPLATE_CHECKBOX",
    "SUPP_NEG": "NARRATIVE_NEGATIVE",
    "NOTE_TRACE_NOT_OCCURRED": "NARRATIVE_NEGATIVE",
    "NOTE_RETAINED_ERRATA_NONZERO": "POSITIVE_NONZERO",
    "MANUAL_EVIDENCE": "FIELD_LEVEL_MANUAL",
    "ASSUMED_NO_PENDING_REVIEW": "ASSUMPTION",
}

SIMPLE_SQ = {"FIN.REV.SQ", "FIN.COST.SQ", "FIN.NPDEDT.SQ",
             "FIN.NPP.SQ", "FIN.OCF.SQ"}
CUMULATIVE_DIFF_STATUSES = {"DERIVED_CUMULATIVE_DIFF", "DERIVED_Q1_EQUALS_YTD",
                            "DERIVED_QUARTERLY_SUM_OVERRIDE"}
QUARTERLY_TABLE_STATUS = "EXTRACTED_QUARTERLY_TABLE"

_CLAUSE_SPLIT = re.compile(r"[；;。\n]")
# 勾选式取值行：以 □/√/☑ 开头、只含 适用/不适用/是/否
_RE_CHECKBOX_VALUE = re.compile(r"^[□√☑\s]*(适用|不适用|是|否)")


def _clauses(txt):
    return [c for c in _CLAUSE_SPLIT.split(txt or "") if c.strip()]


def analyse(rec):
    """按分句判断极性。

    返回 (excluded, affirmed, scoped_only, mentioned)
    - excluded: 明确排除该原因（否定词与原因同句）
    - affirmed: 确认该原因发生（肯定词或非零金额同句）
    - scoped_only: 只对特定项目给结论（如期初未分配利润 0.00 元），不覆盖本字段
    - mentioned: 仅提及，无极性
    """
    txt = (rec.get("evidence") or "") if isinstance(rec, dict) else str(rec or "")
    excluded, affirmed, scoped_only, mentioned = set(), set(), set(), set()
    cls = _clauses(txt)
    for idx, c in enumerate(cls):
        has = {}
        if _RE_ERRATA.search(c):
            has[ERRATA] = True
        if _RE_MERGER.search(c):
            has[MERGER_RETRO] = True
        if _RE_POLICY.search(c):
            has[POLICY_CHANGE] = True
        if not has:
            continue
        neg = bool(_RE_NEG.search(c))
        # 勾选式版面：标签在一句、取值在下一句（"追溯重述法" + "□适用√不适用"）。
        # 仅当标签句很短且不含金额时才向下配对，避免把后续章节的「不适用」串进来。
        if not neg and len(c.strip()) <= 40 and not _RE_AMOUNT.search(c) and idx + 1 < len(cls):
            nxt = cls[idx + 1].strip()
            if len(nxt) <= 12 and _RE_CHECKBOX_VALUE.match(nxt) and _RE_NEG.search(nxt):
                neg = True
        zero = bool(_RE_ZERO.search(c))
        amt = bool(_RE_AMOUNT.search(c)) and not zero
        pos = bool(_RE_POS.search(c))
        scoped = bool(_RE_SCOPED_ITEM.search(c))
        for cause in has:
            mentioned.add(cause)
            if neg:
                excluded.add(cause)
            elif scoped and (zero or amt):
                # 只给了某个权益项目的金额，不能据此排除本字段
                scoped_only.add(cause)
            elif amt:
                affirmed.add(cause)
            elif pos:
                affirmed.add(cause)
    return excluded, affirmed, scoped_only, mentioned


def coverage_of(rec):
    """兼容旧接口：只返回明确排除的原因集合。"""
    return analyse(rec)[0]


def binds_field(rec):
    """证据是否绑定到具体字段/表格/行列（NA 类均为否）。"""
    txt = (rec.get("evidence") or "") if isinstance(rec, dict) else str(rec or "")
    if (rec.get("method") or "") == "MANUAL_EVIDENCE":
        return True
    return bool(re.search(r"第\s*\d+\s*[行列表]|附注[一二三四五六七八九十]|\d{3,}\s*元", txt))


def is_own_period(document_period, row_period):
    """显式判断，不再用字符串真值。未知文档期间返回 None。"""
    if not document_period:
        return None
    return document_period == row_period


def required_scope(status, document_period, row_period):
    """该行要断言「未被重述」，按取值来源必须覆盖哪些维度。"""
    own = is_own_period(document_period, row_period)
    if own is None:
        return {ERRATA, MERGER_RETRO, COMPARATIVE_SCOPE, DOC_PERIOD_UNKNOWN}
    if own is False:
        # 比较列 / 分季度表供给别的期间：任何追溯调整都会改写比较数
        return {ERRATA, MERGER_RETRO, COMPARATIVE_SCOPE}
    if status == QUARTERLY_TABLE_STATUS:
        return {ERRATA, QUARTERLY_TABLE_PROVENANCE}
    if status in CUMULATIVE_DIFF_STATUSES:
        # 单季 = YTD(t) − YTD(t−1q)，两个父输入的文档/版本/合并范围/单位须兼容
        return {ERRATA, PARENT_COMPATIBILITY}
    return {ERRATA}


def source_dims_for(status, document_period, row_period):
    """只看来源维度的缺口，用于「B=是」的确认类断言。"""
    req = required_scope(status, document_period, row_period)
    return {d for d in req if d in SOURCE_DIMS or d == DOC_PERIOD_UNKNOWN}


def judge(rec, doc, status, document_period, row_period, ruled=None, bval="",
          parent_ok=None):
    """返回 dict：resolution / scope_required / scope_covered / scope_missing / evidence_note / polarity。"""
    def out(res, req=(), cov=(), mis=(), note="", pol="", lvl=""):
        return {"resolution": res,
                "scope_level": lvl,
                "scope_required": ";".join(sorted(req)),
                "scope_covered": ";".join(sorted(cov)),
                "scope_missing": ";".join(sorted(mis)),
                "evidence_note": note, "polarity": pol}

    req = required_scope(status, document_period, row_period)

    if ruled:
        # 裁决解除不等于「范围已证成」：必需范围照常登记，覆盖留空，
        # 供 C33 检验「非自身期间必须要求比较范围」，也避免把裁决当成覆盖证据。
        return out("RESOLVED_BY_RULING", req, (), req, lvl="RULED",
                   note="独立复核已裁决解除：%s" % str(ruled.get("basis", ""))[:90])
    if not doc:
        return out("UNRESOLVED_NO_DOCUMENT", req, (), req, lvl="NO_DOC",
                   note="B 该行无 document_id，无法定位供给文档")
    if rec is None:
        return out("UNRESOLVED_DOC_NEVER_VERIFIED", req, (), req, lvl="NO_VERIFY",
                   note="供给文档 %s 不在 1,007 份核验清单内" % doc[:20])

    method = rec.get("method") or ""
    excluded, affirmed, scoped_only, mentioned = analyse(rec)
    # 来源维度只有调用方能证成；证据文本不覆盖
    covered = set(excluded)
    if PARENT_COMPATIBILITY in req and parent_ok is True:
        covered.add(PARENT_COMPATIBILITY)
    missing = req - covered
    level = "FIELD" if binds_field(rec) else "SECTION"
    pol = "excluded=%s|affirmed=%s|scoped=%s" % (
        ",".join(sorted(excluded)) or "-", ",".join(sorted(affirmed)) or "-",
        ",".join(sorted(scoped_only)) or "-")

    if method == "ASSUMED_NO_PENDING_REVIEW":
        return out("PENDING_WEAK_ASSUMPTION", req, covered, missing,
                   "方法为假设（未查原文）p.%s" % rec.get("page"), pol, level)

    # B=是：断言方向相反，要证的是「确实发生过」
    if bval == "是":
        event_ok = (ERRATA in affirmed) or method == "NOTE_RETAINED_ERRATA_NONZERO"
        src_gap = source_dims_for(status, document_period, row_period) - covered
        if not event_ok:
            return out("PENDING_CONFIRMED_UNSUPPORTED", req, covered, missing,
                       "B=是 但证据未确认发生过差错更正 p.%s" % rec.get("page"), pol, level)
        if src_gap:
            return out("PENDING_CONFIRMED_EVENT_FIELD_OPEN", req, covered, src_gap,
                       "事件已确认，但来源维度未核：%s（p.%s）"
                       % (";".join(sorted(src_gap)), rec.get("page")), pol, level)
        return out("RESOLVED_RESTATEMENT_CONFIRMED", req, covered, (),
                   "证据确认发生更正且来源维度已覆盖（p.%s）" % rec.get("page"), pol, level)

    if method in SCOPE_LIMITED_METHODS and not binds_field(rec):
        return out("PENDING_SCOPE_LIMITED_METHOD", req, covered, missing,
                   "方法 %s 仅覆盖「重大会计差错更正」一节，未绑定字段/表格/行列（p.%s）；"
                   "已排除=%s，仍缺=%s" % (method, rec.get("page"),
                                          ",".join(sorted(excluded)) or "无",
                                          ";".join(sorted(missing)) or "无"), pol, level)

    if ERRATA in affirmed and ERRATA not in excluded:
        return out("UNRESOLVED_EVIDENCE_CONTRADICTS", req, covered, missing,
                   "证据确认存在差错更正（p.%s），与 B=%s 冲突" % (rec.get("page"), bval or "空"), pol, level)

    if not missing:
        return out("RESOLVED_SCOPE_COVERED", req, covered, (),
                   "证据覆盖该行所需全部维度；method=%s p.%s scope_level=%s"
                   % (method, rec.get("page"), level), pol, level)

    if DOC_PERIOD_UNKNOWN in missing:
        label, why = "PENDING_DOC_PERIOD_UNKNOWN", "文档期间未知，无法判定是否自身期间"
    elif QUARTERLY_TABLE_PROVENANCE in missing:
        label, why = "PENDING_SOURCE_PROVENANCE", "取值来源为分季度表，NA 类证据不涉及该表"
    elif COMPARATIVE_SCOPE in missing:
        label, why = "PENDING_SOURCE_PROVENANCE", "取值来自比较列，未核比较范围"
    elif PARENT_COMPATIBILITY in missing:
        label, why = "PENDING_PARENT_COMPATIBILITY", "累计差分父输入未证兼容"
    else:
        label, why = "PENDING_CAUSE_UNCOVERED", "证据未覆盖 %s" % ";".join(sorted(missing))
    return out(label, req, covered, missing,
               "%s；method=%s p.%s scope_level=%s" % (why, method, rec.get("page"), level),
               pol, level)


def group_key(method, excluded, affirmed, status, is_own):
    return "|".join([method or "NONE",
                     "+".join(sorted(excluded)) or "NONE",
                     ("AFF:" + "+".join(sorted(affirmed))) if affirmed else "NOAFF",
                     status or "NONE",
                     "OWN" if is_own else ("COMPARATIVE" if is_own is False else "UNKNOWN")])
