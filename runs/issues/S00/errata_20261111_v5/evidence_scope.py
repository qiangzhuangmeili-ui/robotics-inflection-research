#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""证据覆盖模型（V5 新增，生产与自检共用）

Codex 第五轮裁决第二节：

> 「期间相等只说明日期对应，不能证明核验记录覆盖了该字段、表格、调整原因及派生输入。」
> 「更合适的判据是：实际证据是否覆盖该断言。」

因此本模块把「按方法名整体认可/否决」换成两个独立计算：

1. coverage_of(rec)  —— 从证据正文抽出它实际排除了哪些调整原因
                       （ERRATA / MERGER_RETRO / POLICY_CHANGE / QUANTIFIED）；
2. required_scope(...) —— 该行要成立「未被重述」，按取值来源必须覆盖哪些原因。

只有 coverage ⊇ required 才可闭合；差集写进 scope_missing 供逐项复核。
方法名只用于两处：标注结构性强度（SCOPE_LIMITED_METHODS 强制待核）和分组抽验。
"""
import re

# ---- 调整原因（断言维度） ----
ERRATA = "ERRATA"                    # 会计差错更正
MERGER_RETRO = "MERGER_RETRO"        # 同一控制下企业合并追溯调整
POLICY_CHANGE = "POLICY_CHANGE"      # 会计政策变更追溯调整
# ---- 来源维度（NA 类证据天然不涉及） ----
QUARTERLY_TABLE_PROVENANCE = "QUARTERLY_TABLE_PROVENANCE"  # 分季度表自身来源与采用链
COMPARATIVE_SCOPE = "COMPARATIVE_SCOPE"                    # 比较列取值的追溯范围

CAUSES = [ERRATA, MERGER_RETRO, POLICY_CHANGE]

# 证据正文里出现即视为该原因已被排除
_RE_ERRATA = re.compile(r"追溯重述|差错更正|前期差错")
_RE_MERGER = re.compile(r"同一控制|合并范围")
_RE_POLICY = re.compile(r"会计政策")
_RE_QUANT = re.compile(r"0\.00\s*元|影响期初未分配利润\s*0")

# 结构性受限方法：判据只覆盖「重大会计差错更正」这一节，且不绑定字段/表格/行列。
# Codex 第五轮明确要求这 5,270 条不得继续整体计作已证据闭合。
SCOPE_LIMITED_METHODS = {"IMPORTANT_MATTER_NA", "NOTE_RETAINED_ERRATA_ZERO"}

# 方法结构性强度：仅用于分组抽验与排序，不单独决定闭合
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

# 单季字段：父输入就是同名字段的累计值
SIMPLE_SQ = {"FIN.REV.SQ", "FIN.COST.SQ", "FIN.NPDEDT.SQ",
             "FIN.NPP.SQ", "FIN.OCF.SQ"}
# 由累计差分得到的取值状态
CUMULATIVE_DIFF_STATUSES = {"DERIVED_CUMULATIVE_DIFF", "DERIVED_Q1_EQUALS_YTD",
                            "DERIVED_QUARTERLY_SUM_OVERRIDE"}
# 直接取自分季度表
QUARTERLY_TABLE_STATUS = "EXTRACTED_QUARTERLY_TABLE"


def coverage_of(rec):
    """证据正文实际排除了哪些调整原因。返回 set。"""
    txt = (rec.get("evidence") or "") if isinstance(rec, dict) else str(rec or "")
    cov = set()
    if _RE_ERRATA.search(txt):
        cov.add(ERRATA)
    if _RE_MERGER.search(txt):
        cov.add(MERGER_RETRO)
    if _RE_POLICY.search(txt):
        cov.add(POLICY_CHANGE)
    if _RE_QUANT.search(txt):
        cov.add("QUANTIFIED")
    return cov


def binds_field(rec):
    """证据是否绑定到具体字段/表格/行列（NA 类均为否）。"""
    txt = (rec.get("evidence") or "") if isinstance(rec, dict) else str(rec or "")
    if (rec.get("method") or "") == "MANUAL_EVIDENCE":
        return True
    return bool(re.search(r"第\s*\d+\s*[行列表]|附注[一二三四五六七八九十]|\d{3,}\s*元", txt))


def required_scope(status, own_period):
    """该行要断言「未被重述」，按取值来源必须覆盖哪些维度。

    注意：派生/差分行的「父输入是否可信」不在本函数内判断——那属于依赖引擎
    （l2_core.dependency_keys + 父键闭合检查）的职责。若在此处追加 MERGER_RETRO，
    会把「同一份报告内 YTD 相减」也判成证据不足，属于 Codex 第五轮警告的过度传播。
    """
    if not own_period:
        # 比较列 / 分季度表供给的其它期间：任何追溯调整都会改写比较数
        return {ERRATA, MERGER_RETRO, COMPARATIVE_SCOPE}
    if status == QUARTERLY_TABLE_STATUS:
        # 分季度表是独立来源，NA 类证据不涉及该表本身
        return {ERRATA, QUARTERLY_TABLE_PROVENANCE}
    # 主表直接提取 / 累计差分 / 一般派生：证据只须排除差错更正；
    # 差分链的可信度由父键闭合检查单独承担。
    return {ERRATA}


def judge(rec, doc, status, own_period, row_period, ruled=None, bval=""):
    """返回 (resolution, scope_required, scope_covered, scope_missing, evidence_note)。"""
    if ruled:
        return ("RESOLVED_BY_RULING", "", "", "",
                "独立复核已裁决解除：%s" % str(ruled.get("basis", ""))[:90])

    if not doc:
        return ("UNRESOLVED_NO_DOCUMENT", "", "", "",
                "B 该行无 document_id，无法定位供给文档")
    if rec is None:
        return ("UNRESOLVED_DOC_NEVER_VERIFIED", "", "", "",
                "供给文档 %s 不在 1,007 份核验清单内" % doc[:20])

    method = rec.get("method") or ""
    req = required_scope(status, own_period)
    cov = coverage_of(rec)
    missing = req - cov
    req_s = ";".join(sorted(req))
    cov_s = ";".join(sorted(cov))
    mis_s = ";".join(sorted(missing))

    if method == "ASSUMED_NO_PENDING_REVIEW":
        return ("PENDING_WEAK_ASSUMPTION", req_s, cov_s, mis_s,
                "方法为假设（未查原文）p.%s" % rec.get("page"))

    if method == "NOTE_RETAINED_ERRATA_NONZERO":
        # 明确披露非零差错更正。B 说「是」则证据支持 B；B 说「否」才构成冲突。
        if bval == "是":
            return ("RESOLVED_RESTATEMENT_CONFIRMED", req_s, cov_s, mis_s,
                    "证据披露非零前期差错更正且 B=是，判定一致（p.%s）" % rec.get("page"))
        return ("UNRESOLVED_EVIDENCE_CONTRADICTS", req_s, cov_s, mis_s,
                "证据披露存在非零前期差错更正（p.%s），与 B=%s 冲突，须回读定性"
                % (rec.get("page"), bval or "空"))

    if method in SCOPE_LIMITED_METHODS and not binds_field(rec):
        return ("PENDING_SCOPE_LIMITED_METHOD", req_s, cov_s, mis_s,
                "方法 %s 仅覆盖「重大会计差错更正」一节，未绑定字段/表格/行列（p.%s）；"
                "已排除=%s，仍缺=%s" % (method, rec.get("page"), cov_s or "无", mis_s or "无"))

    if not missing:
        return ("RESOLVED_SCOPE_COVERED", req_s, cov_s, "",
                "证据覆盖该行所需全部维度；method=%s p.%s；own_period=%s"
                % (method, rec.get("page"), own_period or "否"))

    # 覆盖不足：区分是「来源维度」缺（分季度表/比较列）还是「原因维度」缺
    if QUARTERLY_TABLE_PROVENANCE in missing or COMPARATIVE_SCOPE in missing:
        label = "PENDING_SOURCE_PROVENANCE"
        why = ("取值来源为%s，NA 类证据不涉及该表/该比较列本身"
               % ("分季度表" if QUARTERLY_TABLE_PROVENANCE in missing else "比较列"))
    else:
        label = "PENDING_CAUSE_UNCOVERED"
        why = "证据未覆盖 %s（%s 仅涉及其余原因）" % (mis_s, method)
    return (label, req_s, cov_s, mis_s,
            "%s；own_period=%s row_period=%s p.%s"
            % (why, own_period or "否", row_period, rec.get("page")))


def group_key(method, cov, status, own_period):
    """同质分组键：方法 × 覆盖签名 × 取值来源 × 是否自身期间。"""
    return "|".join([method or "NONE", "+".join(sorted(cov)) or "NONE",
                     status or "NONE", "OWN" if own_period else "COMPARATIVE"])
