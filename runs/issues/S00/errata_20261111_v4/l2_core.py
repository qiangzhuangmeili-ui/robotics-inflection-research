#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""L2 依赖核心（供 check_l2_v4.py 与 verify_v4.py 共用）

Codex 第四轮指出：v3 的 field_periods() 只给同一字段追加期间，从未把
FIN.REV.SQ 换成 FIN.REV.YTD 父键，所谓「累计父输入展开」并未实现。
本模块把期间规则与父键展开放在一处，生产代码与自检都调用它，
避免「自检另写一套、删掉生产逻辑也能 PASS」。
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

# 派生字段 -> 直接父字段（单季由累计差分得到；毛利率/毛利额由营收与成本得到）
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


def field_keys(fld, periods, _seen=None):
    """字段级递归展开：同期间内把派生字段替换为其父字段，直到无父字段。

    注意递归单位是「字段」不是「指标」。v3 的实现在这里把字段名当指标名去查
    METRIC_FIELDS，结果父键永远为空——C18 的合成争议检查就是为了拦住它。
    """
    if _seen is None:
        _seen = set()
    out = set()
    for pk in periods:
        if (fld, pk) in _seen:
            continue
        _seen.add((fld, pk))
        out.add((fld, pk))
        for par in PARENT.get(fld, []):
            out |= field_keys(par, {pk}, _seen)
    return out


def dependency_keys(mid, anchor, _seen=None):
    """返回 {(field_id, period_key)}，含递归父键。

    - 期间：M03 取四季，其余取 t 与 t−1y；
    - 单季字段追加「本期累计 + 前季累计」（SQ(t)=YTD(t)−YTD(t−1q)）；
    - 每个字段再按 PARENT 递归展开父字段。
    """
    out = set()
    for fld in METRIC_FIELDS.get(mid, []):
        pers = set(periods_for(mid, anchor))
        if fld in PARENT and fld.endswith(".SQ"):
            pers |= {anchor, prev_quarter(anchor)}
        out |= field_keys(fld, pers, _seen)
    return out


def load_rules(path=None):
    p = path or (ROOT / "runs/issues/S01/screen_rules_v2.json")
    d = json.loads(Path(p).read_text(encoding="utf-8"))
    return ({s["id"]: s["metric"] for s in d["signals"]},
            {s["id"]: s["dimension"] for s in d["signals"]})
