# -*- coding: utf-8 -*-
"""S05 的 Q10 项目制判定规则（单一事实来源）。

2026-11-20 门审 J1 否决后修订：
- 合同资产空白（BLANK_IN_STATEMENT）、未列示（NOT_IN_STATEMENT）、缺记录、不可读
  一律不采用，**不得补零**；只有 B 中确有的金额（含原文明确写 0.00）可采用。
- 两支 OR 独立成立：一支分母不可用，不妨碍另一支独立确立 PROJECT_MODE。
- 只有两支都算出且都未达门槛才判 NON_PROJECT。

阈值取自 screen_rules_v3_provenance_20261114.json / Q10 与 negative_zero_base。
任何脚本不得另写一份阈值——本模块是唯一来源。
"""
from decimal import Decimal

Q10_ASSET_PCT = Decimal("5")          # 合同资产/资产总计 > 5%
Q10_REV_PCT = Decimal("10")           # 合同资产/营业收入(YTD) > 10%
ZERO_BASE_FLOOR = Decimal("1000000")  # |分母| < 100 万元视为零基数

# 唯一可采用合同资产金额的状态：B 里确有金额（含原文明确零）
CA_USABLE_BASES = ("HAS_VALUE",)


def ratio_pct(num, den):
    """占比百分数；分母缺失或非正时返回 None（不计算、不推定）。"""
    if num is None or den is None:
        return None
    if den <= 0:
        return None
    return (num / den) * Decimal(100)


def q10_eval(ca_basis, ca_v, asset_basis, asset_v, rev_basis, rev_v,
             asset_ok=True, rev_ok=True):
    """判定 Q10 是否项目制。

    ca_basis / asset_basis / rev_basis 为单格证据状态；asset_ok / rev_ok 表示该分母
    是否通过文档、期间、版本、单位、合并口径与来源资格检查。
    返回 dict：verdict / branch1_pct / branch2_pct / b1_status / b2_status / reason。
    """
    ca_ok = ca_basis in CA_USABLE_BASES and ca_v is not None
    b1 = None
    b2 = None
    if ca_ok and asset_basis in CA_USABLE_BASES and asset_ok:
        b1 = ratio_pct(ca_v, asset_v)
    if ca_ok and rev_basis in CA_USABLE_BASES and rev_ok:
        b2 = ratio_pct(ca_v, rev_v)

    h1 = b1 is not None and b1 > Q10_ASSET_PCT
    h2 = b2 is not None and b2 > Q10_REV_PCT

    if h1 or h2:
        verdict = "PROJECT_MODE"
        hit = []
        if h1:
            hit.append("资产支 %s%% > %s%%" % (_fmt(b1), Q10_ASSET_PCT))
        if h2:
            hit.append("营收支 %s%% > %s%%" % (_fmt(b2), Q10_REV_PCT))
        reason = "项目制：" + "；".join(hit)
    elif b1 is not None and b2 is not None:
        verdict = "NON_PROJECT"
        reason = "两支均有证据且未达门槛（资产支 %s%% ≤ %s%%，营收支 %s%% ≤ %s%%）" % (
            _fmt(b1), Q10_ASSET_PCT, _fmt(b2), Q10_REV_PCT)
    elif not ca_ok:
        verdict = "UNKNOWN_CA_BLANK" if ca_basis == "REPORTED_BLANK" else "UNKNOWN_CA_NOT_USABLE"
        reason = ("合同资产当期状态为 %s，无原文金额，按 J1 保留未知，不补零、不推定" % ca_basis)
    else:
        verdict = "UNKNOWN_DENOMINATOR"
        reason = "合同资产有金额，但两支分母均不可用（%s / %s），无法判定" % (
            asset_basis if not asset_ok else "OK", rev_basis if not rev_ok else "OK")

    return {
        "verdict": verdict,
        "branch1_pct": _dec_str(b1),
        "branch2_pct": _dec_str(b2),
        "b1_status": _branch_status(ca_ok, asset_basis, asset_v, asset_ok, b1),
        "b2_status": _branch_status(ca_ok, rev_basis, rev_v, rev_ok, b2),
        "reason": reason,
    }


def _dec_str(x):
    """不用科学计数法：0 → '0'，其余保留完整精度。"""
    if x is None:
        return ""
    if x == 0:
        return "0"
    return format(x, "f")


def _fmt(x):
    return ("%.4f" % x).rstrip("0").rstrip(".")


def _branch_status(ca_ok, den_basis, den_v, den_ok, computed):
    if not ca_ok:
        return "CA_NOT_USABLE"
    if den_basis not in CA_USABLE_BASES:
        return "DENOMINATOR_%s" % den_basis
    if not den_ok:
        return "DENOMINATOR_SOURCE_INELIGIBLE"
    if den_v is None or den_v <= 0:
        return "DENOMINATOR_NON_POSITIVE"
    return "COMPUTED" if computed is not None else "NOT_COMPUTED"
