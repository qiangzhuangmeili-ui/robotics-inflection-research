#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""第十九轮 D1/D2/D3 反例的回归测试（不写任何交付物）。

D1：邻列表头不得被认成本列（多列候选必须报歧义）。
D2：canon_column 必须保留年份/起止区间/本期-上年-上期/累计属性。
D3：金额必须逐位相等，指标行未命中不得回退。
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import parent_verify as pv          # noqa: E402

FAIL = []


def ck(name, cond, extra=""):
    print("%-46s %s %s" % (name, "PASS" if cond else "FAIL", extra))
    if not cond:
        FAIL.append(name)


def W(x0, y0, x1, y1, t):
    return (x0, y0, x1, y1, t)


# ---------------- D1：邻列表头 ----------------
def d1():
    # ① Codex 第十九轮 D1 原反例：左列 2025年半年度 x[70,90]、本列 2026年半年度
    #    x[100,130]、金额 100.00 x[100,110]。**不得把左列表头拼进来择一**。
    words = [
        W(0, 100, 40, 110, "营业收入"),
        W(70, 80, 90, 90, "2025年半年度"),
        W(100, 80, 130, 90, "2026年半年度"),
        W(100, 100, 110, 110, "100.00"),
        W(140, 100, 150, 110, "200.00"),
        W(0, 60, 200, 70, "单位：元"),
    ]
    col, _amt, st = pv.column_of_amount_aligned(words, "100.00", label=("营业收入",))
    ck("D1 邻列表头不得被认成本列",
       st == "OK" and "2025" not in col and pv.canon_column(col) == "|R-2026-1-6|累计",
       "st=%s col=%r" % (st, col))

    # ② 两个期间列**同时**与金额跨度重叠（左列 x1 落进 padding）：必须报歧义，
    #    不允许「拼起来再择一」。
    words1b = [
        W(0, 100, 40, 110, "营业收入"),
        W(80, 80, 95, 90, "2025年半年度"),
        W(100, 80, 130, 90, "2026年半年度"),
        W(100, 100, 110, 110, "100.00"),
        W(140, 100, 150, 110, "200.00"),
        W(0, 60, 200, 70, "单位：元"),
    ]
    col, _amt, st = pv.column_of_amount_aligned(words1b, "100.00", label=("营业收入",))
    ck("D1 多列候选必须报歧义", st == "AMBIGUOUS", "st=%s col=%r" % (st, col))

    # ③ 同一列的断词（2026年 + 半年度，间隙 1pt）仍须合并成一列
    words2 = [
        W(0, 100, 40, 110, "营业收入"),
        W(70, 80, 90, 90, "2025年半年度"),
        W(100, 80, 112, 90, "2026年"),
        W(113, 80, 130, 90, "半年度"),
        W(100, 100, 110, 110, "100.00"),
        W(140, 100, 150, 110, "200.00"),
        W(0, 60, 200, 70, "单位：元"),
    ]
    col, _amt, st = pv.column_of_amount_aligned(words2, "100.00", label=("营业收入",))
    ck("D1 同列断词仍合并", st == "OK" and pv.canon_column(col) == "|R-2026-1-6|累计",
       "st=%s col=%r" % (st, col))

    # ④ 表头跨两行（本报告期 / （1－6月））仍须成一列
    words3 = [
        W(0, 100, 40, 110, "营业收入"),
        W(60, 70, 90, 80, "项目"),
        W(100, 70, 130, 80, "本报告期"),
        W(100, 88, 130, 98, "（1－6月）"),
        W(140, 70, 170, 80, "上年同期"),
        W(140, 88, 170, 98, "（1－6月）"),
        W(100, 100, 110, 110, "100.00"),
        W(140, 100, 150, 110, "200.00"),
        W(0, 60, 200, 66, "单位：元"),
    ]
    col, _amt, st = pv.column_of_amount_aligned(words3, "100.00", label=("营业收入",))
    ck("D1 跨行表头成一列", st == "OK" and pv.canon_column(col) == "本期|R0-1-6|累计",
       "st=%s col=%r" % (st, col))


# ---------------- D2：canon 语义 ----------------
def d2():
    cases = [
        ("本期金额（2026年1-6月）", "本期|R-2026-1-6|累计"),
        ("本期金额（2026年4-6月）", "本期|R-2026-4-6|"),
        ("本报告期（1－6月）", "本期|R0-1-6|累计"),
        ("本报告期（4－6月）", "本期|R0-4-6|"),
        ("上年年初至报告期末", "上年||累计"),
        ("年初至报告期末", "本期||累计"),
        ("本报告期", "本期||"),
        ("2026年半年度", "|R-2026-1-6|累计"),
    ]
    for t, want in cases:
        got = pv.canon_column(t)
        ck("D2 canon %s" % t, got == want, "got=%r want=%r" % (got, want))
    pairs = [("本期金额（2026年1-6月）", "本期金额（2026年4-6月）"),
             ("本报告期（1－6月）", "本报告期（4－6月）"),
             ("上年年初至报告期末", "年初至报告期末"),
             ("上年同期", "上期")]
    for a, b in pairs:
        ck("D2 不等价 %s ≠ %s" % (a, b), not pv.cols_equivalent(a, b))
    same = [("本期数", "本报告期"), ("本年累计", "年初至报告期末"),
            ("2026年半年度", "2026年1-6月"), ("上年同期", "上年同期金额")]
    for a, b in same:
        ck("D2 仍等价 %s = %s" % (a, b), pv.cols_equivalent(a, b))
    # 登记值必须是原文连续片段且语义不缩水
    pg = "营业收入100.00本期金额（2026年1-6月）"
    ck("D2 registrable 保留区间", pv.registrable_column("本期金额（2026年1-6月）", pg)
       == "本期金额（2026年1-6月）")
    ck("D2 registrable 拒缩水",
       pv.registrable_column("本期金额（2026年1-6月）", "本期100.00") == "")


# ---------------- D3：金额精确 / 指标行 ----------------
def d3():
    words = [
        W(0, 100, 40, 110, "营业成本"),
        W(100, 80, 130, 90, "2026年半年度"),
        W(100, 100, 110, 110, "100.00"),
        W(0, 60, 200, 70, "单位：元"),
    ]
    col, _amt, st = pv.column_of_amount_aligned(words, "100.009", label=("营业收入",))
    ck("D3 100.009 不得匹配 100.00", st == "NO_AMOUNT", "st=%s col=%r" % (st, col))
    col, _amt, st = pv.column_of_amount_aligned(words, "100.00", label=("营业收入",))
    ck("D3 指标行未命中不得回退", st == "NO_LABEL_ROW", "st=%s col=%r" % (st, col))
    ck("D3 引文数值逐位相等",
       not pv._num_in_quote("营业收入100.00元", "100.009")
       and pv._num_in_quote("营业收入100.00元", "100.00"))
    pat = pv.amount_pattern("100.00")
    ck("D3 正则数字边界", (not pat.search("1100.00")) and bool(pat.search("100.00")))
    pat2 = pv.amount_pattern("684956197.48")
    ck("D3 正则长金额", bool(pat2.search("684,956,197.48"))
       and bool(pat2.search("684956197.48")))


d1()
d2()
d3()
print("-" * 60)
print("FAIL %d" % len(FAIL), FAIL)
sys.exit(1 if FAIL else 0)
