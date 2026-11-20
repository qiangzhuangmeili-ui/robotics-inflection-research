# -*- coding: utf-8 -*-
"""S05 的合同资产来源资格与 Q10 项目制判定规则（单一事实来源）。

2026-11-20 第三轮门审（V2.1 裁决）后修订：
1. Q10 与 RH03 共用同一份「合同资产来源资格」结论。采用金额必须同时绑定
   指定期间 + 合并资产负债表 + 合同资产行 + **期末列**；页码、`0.00` 字符或
   B 的 CONSOLIDATED 标签独自不足。
2. 回读原页确认的三格来源不准入，按「公司 + 字段 + 期间 + 文档 SHA-256」登记；
   保留 B 原值与修订证据，不在冻结底表直接覆盖。
3. 空白（BLANK_IN_STATEMENT / NOT_IN_STATEMENT）、缺记录、不可读、来源不准入
   一律不采用，不得补零；只有 B 中确有金额（含原文期末栏明确写 0.00）可采用。
4. 两支 OR 独立成立：一支分母不可用，不妨碍另一支独立确立 PROJECT_MODE。
   只有两支都算出且都未达门槛才判 NON_PROJECT。

阈值取自 screen_rules_v3_provenance_20261114.json / Q10 与 negative_zero_base。
任何脚本不得另写一份阈值——本模块是唯一来源。
"""
from decimal import Decimal

Q10_ASSET_PCT = Decimal("5")          # 合同资产/资产总计 > 5%
Q10_REV_PCT = Decimal("10")           # 合同资产/营业收入(YTD) > 10%
ZERO_BASE_FLOOR = Decimal("1000000")  # |分母| < 100 万元视为零基数

# 唯一可采用合同资产金额的状态：B 里确有金额且来源资格通过（含期末栏明确零）
CA_USABLE_BASES = ("HAS_VALUE",)

# 合同资产「无可采用金额」的状态集合（用于 RH03 双期/单边路由）
CA_NO_USABLE_BASES = ("REPORTED_BLANK", "REPORTED_ABSENT",
                      "UNREADABLE", "NO_RECORD", "EXTRACTED_NOT_IN_B",
                      "SOURCE_NOT_ADMISSIBLE")

# ---------------------------------------------------------------------------
# 来源不准入登记（只列本轮回读原页确认的三格；其余空白格不在此表）
# 键 = (security_id, field_id, period_key, document_sha256)
# ---------------------------------------------------------------------------
NON_ADMISSIBLE_CA = [
    {
        "security_id": "SZ:002369", "stock_name": "卓翼科技",
        "field_id": "FIN.CONTRACTASSET.INSTANT",
        "period_key": "20260630", "period_label": "2026H1",
        "document_id": "DOC-CED1573B6156692D",
        "document_sha256": "d24cc5016e88761fa99810b0024b8f84fdd3dfd42286c22a22e6eac2fa964e6d",
        "b_value_cny": "0", "b_value_raw": "0.00", "b_source_page": 39,
        "b_scope_tag": "CONSOLIDATED", "b_version": "ORIGINAL",
        "defect_class": "PERIOD_END_BLANK_VALUE_IN_OPENING",
        "authority_table": "合并资产负债表", "authority_page": 39,
        "header_end_x": 274, "header_begin_x": 435,
        "value_x": 510, "column_of_b_value": "BEGIN",
        "period_end_column_blank": "YES",
        "corroboration": ("同一行期末栏无任何数字；0.00 的 x=510 已越过期初表头 x=435，"
                          "落在期初栏。上年同期 B 无合同资产记录，无法与本期期初对账。"),
        "observation": "物理第39页合并资产负债表：合同资产行期末栏空白，0.00 位于期初栏。",
        "s05_effect": "Q10 置 UNKNOWN；RH02 待核；RH03 当期值撤销，与同期空白合为双期无可采用金额。",
    },
    {
        "security_id": "SZ:002786", "stock_name": "银宝山新",
        "field_id": "FIN.CONTRACTASSET.INSTANT",
        "period_key": "20260630", "period_label": "2026H1",
        "document_id": "DOC-F1CA96F4BB5E007E",
        "document_sha256": "b8da02460ad86e2fc9f8b46305f3679f5713c5bc1667b7e331a41d0dd0a81a57",
        "b_value_cny": "40000000", "b_value_raw": "40,000,000.00", "b_source_page": 38,
        "b_scope_tag": "CONSOLIDATED", "b_version": "ORIGINAL",
        "defect_class": "PERIOD_END_BLANK_VALUE_IN_OPENING",
        "authority_table": "合并资产负债表", "authority_page": 38,
        "header_end_x": 285, "header_begin_x": 446,
        "value_x": 480, "column_of_b_value": "BEGIN",
        "period_end_column_blank": "YES",
        "corroboration": ("期初栏 40,000,000.00 与上年同期（2025H1，DOC-27AE4650A28842AA "
                          "物理第34页）期末栏 40,000,000.00 相等，印证该数确为期初余额。"),
        "observation": "物理第38页合并资产负债表：合同资产行期末栏空白，4,000 万元位于期初栏。",
        "s05_effect": "Q10 置 UNKNOWN；RH02 待核；RH03 转单边缺口（上年同期期末栏有值且可用）。",
    },
    {
        "security_id": "SZ:300843", "stock_name": "胜蓝股份",
        "field_id": "FIN.CONTRACTASSET.INSTANT",
        "period_key": "20250630", "period_label": "2025H1",
        "document_id": "DOC-8CCAA8F91C8043AF",
        "document_sha256": "6ecb1a27d7954e04cd3a2d500aade29d346e4a515756da3da6bb66a90c12d55f",
        "b_value_cny": "0", "b_value_raw": "0.00", "b_source_page": 50,
        "b_scope_tag": "CONSOLIDATED", "b_version": "ORIGINAL",
        "defect_class": "WRONG_TABLE_AND_WRONG_COLUMN",
        "authority_table": "合并资产负债表", "authority_page": 47,
        "header_end_x": 285, "header_begin_x": 446,
        "value_x": 523, "column_of_b_value": "BEGIN",
        "period_end_column_blank": "YES",
        "corroboration": ("B 取数页（物理第50页）标题为「2、母公司资产负债表」，非合并表；"
                          "该页 0.00 的 x=523 越过期初表头 x=446，属母公司表期初栏。"
                          "合并资产负债表在物理第47页，合同资产行期末栏无数字。"),
        "observation": ("两步：①B 标注 CONSOLIDATED，但取数页实为母公司资产负债表且 0.00 在期初栏；"
                        "②合并资产负债表（物理第47页）合同资产期末栏空白。"),
        "s05_effect": "RH03 基期值撤销，转单边缺口；当期（2026H1 期末栏明确 0.00）与当期 Q10 判定保留。",
    },
]

NON_ADMISSIBLE_INDEX = {
    (r["security_id"], r["field_id"], r["period_key"], r["document_sha256"]): r
    for r in NON_ADMISSIBLE_CA
}


def classify_amount_column(value_x, header_end_x, header_begin_x, tol=6.0):
    """按表头 x 坐标判定数字落在哪一列。

    END    → 期末栏（value_x 落在 [header_end_x - tol, header_begin_x - tol)）
    BEGIN  → 期初栏（value_x >= header_begin_x - tol）
    LEFT   → 两列以左（行标签区，不应出现金额）
    """
    if value_x >= header_begin_x - tol:
        return "BEGIN"
    if value_x >= header_end_x - tol:
        return "END"
    return "LEFT"


def ca_source_admissible(security_id, field_id, period_key, document_sha256):
    """返回 (admissible, record)。

    只对登记表中的「公司+字段+期间+文档 SHA-256」四元组生效：文档重新采集
    导致 SHA 变化时，本登记不再自动适用，须重新回读原页确认。
    """
    rec = NON_ADMISSIBLE_INDEX.get(
        (security_id, field_id, period_key, document_sha256))
    return (rec is None), rec


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
        if ca_basis == "SOURCE_NOT_ADMISSIBLE":
            verdict = "UNKNOWN_CA_SOURCE_NOT_ADMISSIBLE"
            reason = "合同资产取数经原页复核不成立（错列/错表），来源不准入，不补零、不推定"
        elif ca_basis == "REPORTED_BLANK":
            verdict = "UNKNOWN_CA_BLANK"
            reason = "合同资产当期状态为 REPORTED_BLANK，无原文金额，按 J1 保留未知，不补零、不推定"
        else:
            verdict = "UNKNOWN_CA_NOT_USABLE"
            reason = "合同资产当期状态为 %s，无原文金额，保留未知，不补零、不推定" % ca_basis
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
