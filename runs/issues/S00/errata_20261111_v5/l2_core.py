#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""L2 依赖核心 V5（供 check_l2_v5.py 与 verify_v5.py 共用）

演进：
- v3：field_periods() 只追加期间，父键从未展开（Codex 第四轮指出）。
- v4：field_keys() 按字段递归，但「每个目标单季期间」仍未展开其实际累计父输入，
      且对直接取自分季度表的行也强加累计依赖（Codex 第五轮指出）。
- v5：展开改为「读实际行状态」——

  * EXTRACTED_QUARTERLY_TABLE → 直接取自分季度表，不依赖累计父输入；
  * DERIVED_Q1_EQUALS_YTD 或 Q1 期间 → SQ == YTD，只加本期累计，不减上年年末；
  * DERIVED_CUMULATIVE_DIFF 等 → 加 YTD(t) 与 YTD(t−1q)；
  * 状态未知（未传 status_of）→ 保守取并集，供自检与故障注入使用。

  status_of(field_id, period_key) -> status 字符串，由调用方按公司注入。
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]

METRIC_FIELDS = {
    "M01": ["FIN.REV.YTD"], "M02": ["FIN.REV.SQ"], "M03": ["FIN.REV.SQ"],
    "M04": ["FIN.GROSSMARGIN.PCT", "FIN.REV.YTD", "FIN.COST.YTD"],
    "M05": ["FIN.NPDEDT.YTD"], "M06": ["FIN.NPDEDT.YTD", "FIN.REV.YTD"],
    "M07": ["FIN.NPDEDT.SQ"], "M08": ["FIN.OCF.YTD", "FIN.NPP.YTD"],
    "M09": ["FIN.OCF.YTD"], "M10": ["FIN.AR.INSTANT", "FIN.REV.YTD"],
    "M11": ["FIN.INV.INSTANT", "FIN.COST.YTD"], "M12": ["FIN.CONTRACTASSET.INSTANT", "FIN.REV.YTD"],
}

# 派生字段 -> 直接父字段
PARENT = {
    "FIN.REV.SQ": ["FIN.REV.YTD"],
    "FIN.COST.SQ": ["FIN.COST.YTD"],
    "FIN.NPDEDT.SQ": ["FIN.NPDEDT.YTD"],
    "FIN.NPP.SQ": ["FIN.NPP.YTD"],
    "FIN.OCF.SQ": ["FIN.OCF.YTD"],
    "FIN.GROSSPROFIT.SQ": ["FIN.REV.SQ", "FIN.COST.SQ"],
    "FIN.GROSSPROFIT.YTD": ["FIN.REV.YTD", "FIN.COST.YTD"],
    "FIN.GROSSMARGIN.PCT": ["FIN.REV.YTD", "FIN.COST.YTD"],
    "FIN.NPMARGIN.PCT": ["FIN.NP.YTD", "FIN.REV.YTD"],
    "FIN.OCF_TO_NP.RATIO": ["FIN.OCF.YTD", "FIN.NP.YTD"],
}

# 父输入就是同名字段累计值的单季字段
SIMPLE_SQ = {"FIN.REV.SQ", "FIN.COST.SQ", "FIN.NPDEDT.SQ",
             "FIN.NPP.SQ", "FIN.OCF.SQ"}

Q1_EQUALS_YTD = "DERIVED_Q1_EQUALS_YTD"
QUARTERLY_TABLE = "EXTRACTED_QUARTERLY_TABLE"

# 需要前季的指标（单季加速度）
NEEDS_PREV_Q = {"M03"}
QMAP = {"0331": "1231", "0630": "0331", "0930": "0630", "1231": "0930"}


def prev_year(pk):
    return str(int(pk[:4]) - 1) + pk[4:]


def prev_quarter(pk):
    tail = pk[4:]
    if tail == "0331":
        return str(int(pk[:4]) - 1) + "1231"
    return pk[:4] + QMAP[tail]


def periods_for(mid, anchor):
    if mid in NEEDS_PREV_Q:
        q = prev_quarter(anchor)
        return {anchor, q, prev_year(anchor), prev_year(q)}
    return {anchor, prev_year(anchor)}


def _status(status_of, fld, pk):
    if status_of is None:
        return ""
    try:
        return status_of(fld, pk) or ""
    except TypeError:
        return status_of((fld, pk)) or ""


def expand(fld, pk, status_of=None, _seen=None):
    """把 (field, period) 展开为它实际依赖的键集合（含自身）。"""
    if _seen is None:
        _seen = set()
    if (fld, pk) in _seen:
        return set()
    _seen.add((fld, pk))
    out = {(fld, pk)}
    st = _status(status_of, fld, pk)

    if fld in SIMPLE_SQ:
        base = fld[:-3]            # "FIN.REV.SQ" -> "FIN.REV"
        ytd = base + ".YTD"
        if st == QUARTERLY_TABLE:
            # 直接取自分季度表：既非累计差分，也不存在父输入
            return out
        if pk[4:] == "0331" or st == Q1_EQUALS_YTD:
            # Q1 单季即本期累计，不减上年年末
            out |= expand(ytd, pk, status_of, _seen)
        else:
            # 累计差分（或状态未知的保守取法）
            out |= expand(ytd, pk, status_of, _seen)
            out |= expand(ytd, prev_quarter(pk), status_of, _seen)
        return out

    for par in PARENT.get(fld, []):
        out |= expand(par, pk, status_of, _seen)
    return out


def dependency_keys(mid, anchor, status_of=None):
    """返回 {(field_id, period_key)}。

    status_of(field_id, period_key) -> status；不传则按并集保守展开。
    """
    out = set()
    for fld in METRIC_FIELDS.get(mid, []):
        for pk in periods_for(mid, anchor):
            out |= expand(fld, pk, status_of)
    return out


def load_rules(path=None):
    p = path or (ROOT / "runs/issues/S01/screen_rules_v2.json")
    d = json.loads(Path(p).read_text(encoding="utf-8"))
    return ({s["id"]: s["metric"] for s in d["signals"]},
            {s["id"]: s["dimension"] for s in d["signals"]})


def status_of_for(rows, security_id):
    """返回该公司的 status_of 闭包。rows 为 {(sid,field,period): status}。"""
    def f(fld, pk):
        return rows.get((security_id, fld, pk), "")
    return f
