#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""证据覆盖模型 V7（生产与自检共用）

第七轮裁决的三处修正：

1. **必需范围取并集**（A 项）：V6 在非自身/未知期间分支直接 `return`，把 status 本来要求的
   来源维度（`QUARTERLY_TABLE_PROVENANCE` / `PARENT_COMPATIBILITY`）覆盖掉了。
   非自身期间的分季度表行因此只要求比较范围、不要求季度表来源核验；非自身期间的累计差分
   行也不再要求父输入兼容。V7 改为 `期间要求 ∪ 取值来源要求`，两者互不替代。

2. **极性判定重写**（B 项）：V6 仍是「出现否定词即排除」，三个反例可误放行：
   - `前期差错更正\n√适用□不适用` —— 看到「不适用」就排除，未识别 √ 打在「适用」上；
   - `本期发生前期差错更正，但会计政策变更不适用` —— 否定词绑到了全句所有原因；
   - `未发生前期差错更正。本期发生前期差错更正100.00元` —— 同时肯定与否定，未判冲突。
   V7 按「否定就近绑定单个原因」+「勾选符号识别实际取值」+「肯定/否定冲突单列」重写。
   另：非零权益影响同时记「事件已确认」与「影响范围仅限特定项目」，不再只记后者。

3. **父输入兼容性**（C 项）：见 `build_errata_v5.py:parent_compatible`。
"""
import re
from collections import namedtuple

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
_CAUSE_RE = {ERRATA: _RE_ERRATA, MERGER_RETRO: _RE_MERGER, POLICY_CHANGE: _RE_POLICY}

# 否定：按「就近绑定」处理，不再整句广播。裸「无」也纳入，但绑定半径收紧到 8 字，
# 避免「无商誉减值……本期发生差错更正」这类跨主题误绑（误绑方向是待核，不会误放行）。
_NEG_TOKENS = ["不适用", "未发生", "未采用", "未涉及", "不存在", "未进行",
               "无需", "没有发生", "无重大", "无前期", "均无", "未", "无"]
_NEG_SHORT = {"未", "无"}
_NEG_RADIUS = 14
_NEG_RADIUS_SHORT = 8
# 金额绑定半径：金额常在「对期初未分配利润影响 X 元」之后，离原因词较远
_AMOUNT_RADIUS = 24
# 肯定：确认发生 / 已采用 / 已调整
# 肯定词：必须是谓词，不能是原因短语本身。
# 「追溯重述」「追溯调整」多为小节标题（「追溯重述法的前期会计差错更正事项。」），
# 列进来会把跨页截断的标题当成「确认发生」。
_POS_TOKENS = ["已调整", "已重述", "已采用", "发生", "存在", "采用",
               "调整年初", "调整期初", "调整了"]
# 肯定词左侧若出现这些字，说明它其实在否定短语里（未发生 / 没有发生 / 不存在）
_POS_SUPPRESS = "未没无不非"

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
# 只有「两个累计父输入相减」的派生值才需要父输入兼容性。
# Q1 单季 = Q1 累计，只有一个父输入，套两期相减是错的（第七轮 C 项）。
CUMULATIVE_DIFF_STATUSES = {"DERIVED_CUMULATIVE_DIFF", "DERIVED_QUARTERLY_SUM_OVERRIDE"}
Q1_EQUALS_YTD_STATUS = "DERIVED_Q1_EQUALS_YTD"
QUARTERLY_TABLE_STATUS = "EXTRACTED_QUARTERLY_TABLE"


def is_q1(row_period):
    return (row_period or "")[4:] == "0331"

_CLAUSE_SPLIT = re.compile(r"[；;。\n]")
# 勾选式取值：□/√/☑ + 适用/不适用/是/否
_RE_CHECKBOX_PAIR = re.compile(r"([□√☑■✔●○])\s*(不适用|适用|是|否)")
_CHECKED_MARKS = set("√☑■✔●")
_RE_CHECKBOX_VALUE = re.compile(r"^[□√☑■✔●○\s]*(不适用|适用|是|否)\s*$")
# 纯标题/标签行：只说明「这一节在讲什么」，本身不断言发生或未发生
_RE_LABEL = re.compile(r"^(追溯重述法|未来适用法|追溯调整法|会计政策变更|"
                       r"会计估计变更|前期差错更正|前期差错|差错更正)$")

Polarity = namedtuple("Polarity",
                      "excluded affirmed scoped mentioned conflict")


def _clauses(txt):
    return [c for c in _CLAUSE_SPLIT.split(txt or "") if c.strip()]


def checkbox_value(txt):
    """返回被勾选的那一项（适用/不适用/是/否）；无法唯一判定返回 None。

    必须看符号，不能看文字：`□适用√不适用` 与 `√适用□不适用` 都含「不适用」。
    """
    pairs = _RE_CHECKBOX_PAIR.findall(txt or "")
    if not pairs:
        return None
    checked = [v for m, v in pairs if m in _CHECKED_MARKS]
    if len(checked) == 1:
        return checked[0]
    return None


def _cause_spans(clause):
    spans = []
    for cause, rx in _CAUSE_RE.items():
        for m in rx.finditer(clause):
            spans.append((m.start(), m.end(), cause))
    spans.sort()
    return spans


def _nearest(spans, pos, limit=None):
    """离 pos 最近的原因（按区间距离）；超出 limit 视为未绑定。"""
    best, bestd = None, None
    for s, e, cause in spans:
        d = 0 if s <= pos < e else min(abs(pos - s), abs(pos - e))
        if bestd is None or d < bestd:
            best, bestd = cause, d
    if limit is not None and bestd is not None and bestd > limit:
        return None
    return best


def _neg_positions(clause):
    out = []
    for tok in _NEG_TOKENS:
        for m in re.finditer(re.escape(tok), clause):
            out.append((m.start(), m.end(), tok))
    return out


def _mask(clause):
    """把专有名词遮成等长占位符，避免「未分配利润」里的「未」被当否定词。

    等长替换保证位置索引与原文一致。
    """
    out = list(clause)
    for m in _RE_SCOPED_ITEM.finditer(clause):
        for i in range(m.start(), m.end()):
            out[i] = "□"
    return "".join(out)


def _pos_positions(clause):
    out = []
    for tok in _POS_TOKENS:
        for m in re.finditer(re.escape(tok), clause):
            st = m.start()
            # 「未发生」「没有发生」「不存在」里的「发生/存在」不算肯定
            if st > 0 and clause[st - 1] in _POS_SUPPRESS:
                continue
            out.append((st, m.end()))
    return out


def analyse(rec):
    """按分句 + 就近绑定判极性。

    返回 Polarity(excluded, affirmed, scoped, mentioned, conflict)：
    - excluded：该原因被明确排除（否定词就近绑到它）
    - affirmed：该原因被确认发生（肯定词或非零金额）
    - scoped：只对特定权益项目给出金额，不能证明本字段受影响
    - mentioned：仅出现原因词
    - conflict：同一原因同时被肯定与否定（必须待核，不得解除）
    """
    txt = (rec.get("evidence") or "") if isinstance(rec, dict) else str(rec or "")
    excluded, affirmed, scoped, mentioned = set(), set(), set(), set()
    cls = _clauses(txt)

    for idx, raw in enumerate(cls):
        c = raw.strip()
        spans = _cause_spans(c)
        if not spans:
            continue
        causes = {s[2] for s in spans}
        mentioned |= causes

        # 1) 同句勾选：先看符号定实际取值（`√适用□不适用` 与 `□适用√不适用` 文字相同）
        val = checkbox_value(c)
        if val is not None:
            if val in ("不适用", "否"):
                excluded |= causes
            else:
                affirmed |= causes
            continue

        # 2) 勾选式版面：短标签句 + 下一句纯取值。
        #    必须先于「肯定词绑定」，否则「追溯重述法」这个标签词本身会被当成肯定。
        if len(c) <= 40 and not _RE_AMOUNT.search(c) and idx + 1 < len(cls):
            nxt = cls[idx + 1].strip()
            nv = checkbox_value(nxt) if (len(nxt) <= 16 and not _cause_spans(nxt)) else None
            if nv is not None:
                if nv in ("不适用", "否"):
                    excluded |= causes
                else:
                    affirmed |= causes
                continue

        # 3) 纯标签行（如「追溯重述法」小标题）不断言任何事，只记提及。
        #    否则标签里的「追溯重述」会被当成肯定，与下一句「未发生」构成假冲突。
        if _RE_LABEL.match(c):
            continue

        # 4) 否定就近绑定：每个否定词只作用于离它最近的那一个原因。
        #    单原因分句直接绑——长句「本期未发生采用未来适用法的前期会计差错更正事项」
        #    的否定词离原因词 15 字，按半径会漏掉，反而把「采用」当肯定。
        #    先遮罩专有名词——「期初未分配利润」里的「未」不是否定词。
        scan = _mask(c)
        single = len(causes) == 1
        only = next(iter(causes))
        neg_c = set()
        for st, en, tok in _neg_positions(scan):
            if single:
                neg_c.add(only)
                break
            radius = _NEG_RADIUS_SHORT if tok in _NEG_SHORT else _NEG_RADIUS
            tgt = _nearest(spans, st if st else en, limit=radius)
            if tgt:
                neg_c.add(tgt)

        # 5) 肯定就近绑定（同一分句内已被否定的原因不再肯定）
        pos_c = set()
        for st, en in _pos_positions(scan):
            if single:
                tgt = only
            else:
                tgt = _nearest(spans, st, limit=_NEG_RADIUS)
            if tgt and tgt not in neg_c:
                pos_c.add(tgt)

        excluded |= neg_c
        affirmed |= pos_c

        # 5) 金额：非零确认事件；权益项目金额同时记「影响仅限该项目」
        zero = bool(_RE_ZERO.search(c))
        nonzero = bool(_RE_AMOUNT.search(c)) and not zero
        if (zero or nonzero) and _RE_SCOPED_ITEM.search(c):
            tgt = _nearest(spans, c.find("元"), limit=_AMOUNT_RADIUS)
            if tgt:
                scoped.add(tgt)
                if nonzero and tgt not in neg_c:
                    affirmed.add(tgt)
        elif nonzero:
            tgt = _nearest(spans, c.find("元"), limit=_AMOUNT_RADIUS)
            if tgt and tgt not in neg_c:
                affirmed.add(tgt)

    conflict = excluded & affirmed
    return Polarity(excluded, affirmed, scoped, mentioned, conflict)


def coverage_of(rec):
    """兼容旧接口：只返回明确排除的原因集合。"""
    return analyse(rec).excluded


def polarity_str(p):
    return "excluded=%s|affirmed=%s|scoped=%s|conflict=%s" % (
        ",".join(sorted(p.excluded)) or "-", ",".join(sorted(p.affirmed)) or "-",
        ",".join(sorted(p.scoped)) or "-", ",".join(sorted(p.conflict)) or "-")


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


def period_scope(document_period, row_period):
    """只看「期间」带来的要求。"""
    own = is_own_period(document_period, row_period)
    if own is None:
        return {ERRATA, MERGER_RETRO, COMPARATIVE_SCOPE, DOC_PERIOD_UNKNOWN}
    if own is False:
        # 比较列 / 分季度表供给别的期间：任何追溯调整都会改写比较数
        return {ERRATA, MERGER_RETRO, COMPARATIVE_SCOPE}
    return {ERRATA}


def source_scope(status, row_period=""):
    """只看「取值来源」带来的要求。

    第七轮 C 项：Q1 单季等于 Q1 累计，只有一个父输入，不套两期相减，
    因此 Q1 不要求 PARENT_COMPATIBILITY（它要证的是「这个唯一父输入未被重述」，
    已由 ERRATA 维度覆盖）。
    """
    if status == QUARTERLY_TABLE_STATUS:
        return {QUARTERLY_TABLE_PROVENANCE}
    if status in CUMULATIVE_DIFF_STATUSES and not is_q1(row_period):
        return {PARENT_COMPATIBILITY}
    return set()


def required_scope(status, document_period, row_period):
    """该行要断言「未被重述」，必须覆盖哪些维度。

    第七轮 A 项：期间要求与来源要求**取并集**。V6 在非自身期间分支直接返回，
    把 QUARTERLY_TABLE_PROVENANCE / PARENT_COMPATIBILITY 覆盖掉了。
    """
    return period_scope(document_period, row_period) | source_scope(status, row_period)


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
        # 裁决解除不等于「范围已证成」：必需范围照常登记，覆盖留空。
        return out("RESOLVED_BY_RULING", req, (), req, lvl="RULED",
                   note="独立复核已裁决解除：%s" % str(ruled.get("basis", ""))[:90])
    if not doc:
        return out("UNRESOLVED_NO_DOCUMENT", req, (), req, lvl="NO_DOC",
                   note="B 该行无 document_id，无法定位供给文档")
    if rec is None:
        return out("UNRESOLVED_DOC_NEVER_VERIFIED", req, (), req, lvl="NO_VERIFY",
                   note="供给文档 %s 不在 1,007 份核验清单内" % doc[:20])

    method = rec.get("method") or ""
    p = analyse(rec)
    covered = set(p.excluded)
    if PARENT_COMPATIBILITY in req and parent_ok is True:
        covered.add(PARENT_COMPATIBILITY)
    missing = req - covered
    level = "FIELD" if binds_field(rec) else "SECTION"
    pol = polarity_str(p)

    # 同一原因既被肯定又被否定：冲突必须待核，不能按任一侧解除。
    # 但只有「本行必须排除的原因」冲突才阻断——POLICY_CHANGE 不是必需维度，
    # 它自相矛盾不影响「未被差错更正」这条断言（152 条误阻断即由此而来）。
    blocking = p.conflict & (req & set(CAUSES))
    if blocking:
        return out("UNRESOLVED_POLARITY_CONFLICT", req, covered, missing,
                   "证据同时肯定与否定 %s（p.%s），须回读原页判实际勾选/金额"
                   % (",".join(sorted(blocking)), rec.get("page")), pol, level)

    if method == "ASSUMED_NO_PENDING_REVIEW":
        return out("PENDING_WEAK_ASSUMPTION", req, covered, missing,
                   "方法为假设（未查原文）p.%s" % rec.get("page"), pol, level)

    # B=是：断言方向相反，要证的是「确实发生过」
    if bval == "是":
        # 第七轮 D 项：不再用方法名兜底，事件确认必须来自原文极性
        event_ok = ERRATA in p.affirmed
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
                                          ",".join(sorted(p.excluded)) or "无",
                                          ";".join(sorted(missing)) or "无"), pol, level)

    # 事件已确认但影响只落在特定权益项目：事件与字段影响分开记
    if ERRATA in p.affirmed and ERRATA in p.scoped:
        return out("PENDING_EVENT_CONFIRMED_SCOPE_LIMITED", req, covered, missing,
                   "证据确认发生差错更正，但只给出权益项目影响金额（p.%s），"
                   "不能证明本字段受影响；仍缺=%s"
                   % (rec.get("page"), ";".join(sorted(missing)) or "无"), pol, level)

    if ERRATA in p.affirmed:
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
