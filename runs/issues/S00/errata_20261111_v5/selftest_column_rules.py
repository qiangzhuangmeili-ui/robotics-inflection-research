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
    # 第二十轮裁决 3：分位以下有非零尾数的目标值直接判 AMOUNT_PRECISION_INVALID
    # （比笼统的 NO_AMOUNT 更明确），两者都表示「不得命中」。
    ck("D3 100.009 不得匹配 100.00", st in ("NO_AMOUNT", "AMOUNT_PRECISION_INVALID"),
       "st=%s col=%r" % (st, col))
    ck("D3 100.004 不得匹配 100.00", not pv._same_amount(pv._dec("100.004"), pv._dec("100.00")),
       "_same_amount 退化成 quantize 就会把两者判成相等")
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


# ---------------- D4：第二十轮裁决的六项 ----------------
def d4():
    # ① 同列**横排**的互补片段（本报告期 + （1-6月））不得被拆成两列。
    #    裁决原文：上一版「两侧 canon 都非空就不并」过严。
    words = [
        W(0, 100, 40, 110, "营业收入"),
        W(100, 70, 130, 80, "本报告期"),
        W(131, 70, 165, 80, "（1-6月）"),
        W(200, 70, 230, 80, "上年同期"),
        W(231, 70, 265, 80, "（1-6月）"),
        W(100, 100, 110, 110, "100.00"),
        W(200, 100, 210, 110, "200.00"),
        W(0, 60, 300, 66, "单位：元"),
    ]
    col, _amt, st = pv.column_of_amount_aligned(words, "100.00", label=("营业收入",))
    ck("D4 横排互补片段成一列", st == "OK" and pv.canon_column(col) == "本期|R0-1-6|累计",
       "st=%s col=%r" % (st, col))

    # ② 列链内出现**互相冲突的完整期间**必须报歧义。
    #    裁决原文复现：x[100,130] y=70 的 2025年半年度 与 y=80 的 2026年半年度
    #    被并成一个候选，文本拼成 `2025年半年度2026年半年度` 后返回 OK。
    words2 = [
        W(0, 100, 40, 110, "营业收入"),
        W(100, 70, 130, 80, "2025年半年度"),
        W(200, 70, 230, 80, "2024年半年度"),
        W(100, 80, 130, 90, "2026年半年度"),
        W(200, 80, 230, 90, "2025年半年度"),
        W(100, 100, 110, 110, "100.00"),
        W(200, 100, 210, 110, "200.00"),
        W(0, 60, 300, 66, "单位：元"),
    ]
    col, _amt, st = pv.column_of_amount_aligned(words2, "100.00", label=("营业收入",))
    ck("D4 列链冲突期间报歧义", st == "AMBIGUOUS", "st=%s col=%r" % (st, col))

    # ③ 表格边界：上方一张有表头的表 + 标题行 + 下方一张无表头的表，
    #    金额在下方 —— 不得把上面那张表的表头借下来。
    words3 = [
        W(0, 60, 300, 66, "单位：元"),
        W(0, 70, 40, 80, "营业收入"),
        W(100, 70, 130, 80, "2026年半年度"),
        W(100, 80, 110, 90, "999.00"),
        W(0, 120, 200, 130, "合并现金流量表"),
        W(0, 140, 40, 150, "经营活动产生的现金流量净额"),
        W(100, 140, 110, 150, "100.00"),
    ]
    col, _amt, st = pv.column_of_amount_aligned(words3, "100.00",
                                              label=("经营活动产生的现金流量净额",))
    ck("D4 不得跨表借表头", st == "TABLE_BOUNDARY_UNPROVEN", "st=%s col=%r" % (st, col))

    # ④ 生产等价判定必须保留相对年
    for a, b in [("上年同期（1-6月）", "本报告期（1-6月）"),
                 ("上期（2026年1-6月）", "本期（2026年1-6月）")]:
        ck("D4 相对年冲突 %s ≠ %s" % (a, b), not pv.cols_equivalent(a, b))
    # ⑤ 年度列必须解出年份
    ck("D4 年度保留年份", pv.canon_column("2025年度") != pv.canon_column("2026年度"),
       "got=%r/%r" % (pv.canon_column("2025年度"), pv.canon_column("2026年度")))
    ck("D4 年度=1-12月", pv.cols_equivalent("2026年度", "2026年1-12月"),
       "got=%r" % (pv.canon_column("2026年度"),))
    # ⑥ 引文验证：exact 命中后必须回头核对金额词自身的值；取消任意数字位切分
    ck("D4 exact 须核对数值",
       not pv._num_in_quote("营业收入100.00", "999", exact="100.00"))
    ck("D4 取消任意数字位切分",
       not pv._num_in_quote("营业收入100999999", "100"))
    ck("D4 exact 正确时命中",
       pv._num_in_quote("营业收入100.00", "100", exact="100.00"))


# ---------------- D5：第二十一轮裁决的四项 ----------------
def d5():
    # ① 裁决 1 原反例：两列数字 + 语义互补但分属两列的表头片段。
    #    上一版把第一列认成 `本报告期（4-6月）`；现在第一列只能是 `本报告期`。
    words = [
        W(0, 90, 40, 100, "营业收入"),
        W(100, 70, 130, 80, "本报告期"),
        W(134, 70, 165, 80, "（4-6月）"),
        W(100, 90, 130, 100, "100.00"),
        W(140, 90, 170, 100, "200.00"),
        W(0, 60, 200, 66, "单位：元"),
    ]
    col, _amt, st = pv.column_of_amount_aligned(words, "100.00", label=("营业收入",))
    ck("D5 邻列互补片段不得并进本列",
       st == "OK" and col == "本报告期",
       "st=%s col=%r（上一版是 本报告期（4-6月））" % (st, col))

    # ② 裁决 2：同侧登记不得增加实际列没有的区间/年份/累计语义
    ck("D5 同侧不得增加区间",
       not pv._no_extra_semantics("本报告期（1-6月）", "本报告期"))
    ck("D5 实际更详细时允许",
       pv._no_extra_semantics("本报告期", "本报告期（1-6月）"))
    ck("D5 同侧完全一致时允许",
       pv._no_extra_semantics("2026年半年度", "2026年半年度"))
    ck("D5 同侧不得增加相对年",
       not pv._no_extra_semantics("上年同期", "（1-6月）"))

    # ③ 裁决 3：旁证横向合并前必须拦冲突（上一版并成
    #    `2025年半年度2026年半年度` 仍返回 OK）
    import step4_column_witness as cw
    INF = float("inf")
    rows = [(70, [(100.0, 113.0, "2025年半年度"),
                  (114.0, 130.0, "2026年半年度")])]
    merged = cw._merge_header_cells(rows, 0, None)
    ck("D5 旁证横向冲突不得并成一格",
       len(merged) == 2 and all("2025" not in t or "2026" not in t
                                for cell in merged for t in ["".join(cell[2])]),
       "merged=%r" % (merged,))
    # 互补片段仍须合并（真实同列断词的正例）
    rows2 = [(70, [(100.0, 130.0, "本报告期"),
                   (131.0, 165.0, "（1－6月）")])]
    merged2 = cw._merge_header_cells(rows2, 0, (-INF, 155.0))
    ck("D5 旁证互补片段仍合并",
       len(merged2) == 1 and "".join(merged2[0][2]) == "本报告期（1－6月）",
       "merged=%r" % (merged2,))
    # 跨列互补片段不得合并（相邻数字中点给出列边界：金额 [100,130]、右邻 [140,170]）
    rows3 = [(70, [(100.0, 130.0, "本报告期"),
                   (134.0, 165.0, "（4-6月）")])]
    merged3 = cw._merge_header_cells(rows3, 0, (-INF, 135.0))
    ck("D5 旁证跨列片段不得合并",
       len(merged3) == 2, "merged=%r" % (merged3,))
    # 列边界由同一行相邻数字给出（不是拍阈值）：100.00 [100,130] 与 200.00 [140,170]
    b = pv._amount_bounds([(90, [(100.0, 130.0, "100.00"), (140.0, 170.0, "200.00")])],
                          0, 100.0, 130.0)
    ck("D5 列边界取相邻数字中点", b == (-INF, 135.0), "bounds=%r" % (b,))
    # 纵向冲突（同一列上下两行）仍须报歧义
    rows4 = [(70, [(100.0, 130.0, "2025年半年度")]),
             (80, [(100.0, 130.0, "2026年半年度")])]
    m4a = cw._merge_header_cells(rows4, 0, None)
    m4b = cw._merge_header_cells(rows4, 1, None)
    ck("D5 旁证纵向两两检查能发现冲突",
       not pv._compatible(m4a[0][2][0], m4b[0][2][0]))

    # ④ 裁决 2 的完整链：登记写成邻列长名称、实际列只有 `本报告期`
    #    → 必须穿不过 `gap()`（上一版返回 None）
    def _side(doc, per, val):
        return {"doc": doc, "period": per, "value": val,
                "consolidation_scope": "CONSOLIDATED", "unit_scale": "1",
                "currency": "CNY", "adjust_version": "ORIGINAL"}
    ent = {"conclusion": "COMPATIBLE", "reviewer": "WorkBuddy-Agent",
           "review_role": "SELF_CHECK", "reviewed_at": "2026-11-12",
           "consolidation_scope": "CONSOLIDATED", "unit_scale": "1",
           "currency": "CNY", "scope_basis": "合并范围：合并报表；单位：元；币种：人民币；"
                                             "期间：20260630 与 20260331 两期均为合并口径。",
           "p1_doc": "DOC-A", "p1_period": "20260630", "p1_value": "100.00",
           "p1_page": "1", "p1_adjust_version": "ORIGINAL",
           "p2_doc": "DOC-B", "p2_period": "20260331", "p2_value": "50.00",
           "p2_page": "1", "p2_adjust_version": "ORIGINAL"}
    expect = {"field": "FIN.REV.SQ", "p1": _side("DOC-A", "20260630", "100.00"),
              "p2": _side("DOC-B", "20260331", "50.00")}

    def _mk(col):
        e = dict(ent)
        e["p1_column"] = col
        e["p2_column"] = "本报告期"
        return e

    def _col_of(_doc, _page, _val, _names):
        return ("本报告期", "OK", None)      # 实际列只有 `本报告期`

    r1 = pv.gap(_mk("本报告期（1-6月）"), expect, lambda d, p: "", _col_of)
    ck("D5 登记凭空加区间须被 gap 拒绝",
       r1 == "PARENT_COLUMN_SEMANTICS_UNPROVEN", "gap=%r" % (r1,))
    r2 = pv.gap(_mk("本报告期"), expect, lambda d, p: "", _col_of)
    ck("D5 登记与实际一致时 gap 不报此项",
       r2 != "PARENT_COLUMN_SEMANTICS_UNPROVEN", "gap=%r" % (r2,))


def d6():
    """第二十二轮裁决 1、2：列归属必须贯穿跨行合并；边界未知不得当成无约束。"""
    INF = float("inf")

    # ① `_attribution` 三态：越界可证明是邻列 / 边界未知且不相交是待核 /
    #    边界未知但相交是 OK。三态分开，才不会把「证明不了」当成「证明不是」。
    ck("D6 越界判为邻列（OTHER）",
       pv._attribution(134, 165, (-INF, 135.0), (100, 130), True) == "OTHER")
    ck("D6 边界未知且不相交判待核（UNPROVEN）",
       pv._attribution(134, 165, (-INF, INF), (100, 130), True) == "UNPROVEN")
    ck("D6 边界未知但相交判 OK",
       pv._attribution(105, 128, (-INF, INF), (100, 130), True) == "OK")

    # ② 裁决 1 原样反例：两段期间片段在**不同行**、右邻有 200.00（右边界 135）。
    #    上一版跨行合并只看「跨度重叠 + 语义兼容」，拼成 `本报告期（4-6月）`。
    w1 = [
        W(0, 90, 45, 100, "营业收入"),
        W(0, 60, 40, 66, "项目"), W(100, 60, 138, 66, "本报告期"),
        W(0, 70, 40, 76, "项目"), W(134, 70, 165, 76, "（4-6月）"),
        W(100, 90, 130, 100, "100.00"),
        W(140, 90, 170, 100, "200.00"),
        W(0, 50, 40, 56, "单位：元"),
    ]
    col, _amt, st = pv.column_of_amount_aligned(w1, "100.00", label=("营业收入",))
    ck("D6 跨行合并不得绕过列边界",
       st == "OK" and col == "本报告期",
       "st=%s col=%r（上一版是 本报告期（4-6月））" % (st, col))

    # ③ 裁决 2 负例：删掉右邻 200.00，边界退化为 (-inf, inf)。
    #    上一版把 `（4-6月）` 又并回 `本报告期`（生产与旁证都返回 OK）。
    w2 = [
        W(0, 90, 45, 100, "营业收入"),
        W(100, 70, 130, 76, "本报告期"),
        W(134, 70, 165, 76, "（4-6月）"),
        W(100, 90, 130, 100, "100.00"),
        W(0, 50, 40, 56, "单位：元"),
    ]
    col2, _amt2, st2 = pv.column_of_amount_aligned(w2, "100.00", label=("营业收入",))
    ck("D6 无邻数字时不得把邻列片段并回本列",
       st2 == "COLUMN_ATTRIBUTION_UNPROVEN",
       "st=%s col=%r（上一版是 OK / 本报告期（4-6月））" % (st2, col2))

    # ④ 正例 A：真实同列换行（两段都落在金额跨度内），边界已知时照并。
    w3 = [
        W(0, 90, 45, 100, "营业收入"),
        W(0, 60, 40, 66, "项目"), W(100, 60, 130, 66, "本报告期"),
        W(0, 70, 40, 76, "项目"), W(102, 70, 135, 76, "（1-6月）"),
        W(100, 90, 130, 100, "100.00"),
        W(140, 90, 170, 100, "200.00"),
        W(0, 50, 40, 56, "单位：元"),
    ]
    col3, _amt3, st3 = pv.column_of_amount_aligned(w3, "100.00", label=("营业收入",))
    ck("D6 真实同列换行仍须并成一列",
       st3 == "OK" and col3 == "本报告期（1-6月）", "st=%s col=%r" % (st3, col3))

    # ⑤ 正例 B：单数字行 + 只有一个表头片段——不得因为「没有邻数字」判待核
    #    （裁决 2 明确要求「不要求所有单数字行一律待核」）。
    w4 = [
        W(0, 90, 45, 100, "营业收入"),
        W(0, 70, 40, 76, "项目"), W(100, 70, 160, 76, "2026年半年度"),
        W(100, 90, 130, 100, "100.00"),
        W(0, 50, 40, 56, "单位：元"),
    ]
    col4, _amt4, st4 = pv.column_of_amount_aligned(w4, "100.00", label=("营业收入",))
    ck("D6 单数字行单片段不得判待核",
       st4 == "OK" and col4 == "2026年半年度", "st=%s col=%r" % (st4, col4))

    # ⑥ 正例 C：单数字行 + 换行片段，但与金额跨度相交 → 归属可证，照并。
    w5 = [
        W(0, 90, 45, 100, "营业收入"),
        W(0, 60, 40, 66, "项目"), W(100, 60, 132, 66, "本报告期"),
        W(0, 70, 40, 76, "项目"), W(105, 70, 128, 76, "（1-6月）"),
        W(100, 90, 130, 100, "100.00"),
        W(0, 50, 40, 56, "单位：元"),
    ]
    col5, _amt5, st5 = pv.column_of_amount_aligned(w5, "100.00", label=("营业收入",))
    ck("D6 单数字行相交片段仍须合并",
       st5 == "OK" and col5 == "本报告期（1-6月）", "st=%s col=%r" % (st5, col5))

    # ⑦ 旁证同一负例：横向合并前就要挡住，并留下 drop 记录。
    import step4_column_witness as cw
    rows = [(70, [(100.0, 130.0, "本报告期"), (134.0, 165.0, "（4-6月）")])]
    drops = []
    m = cw._merge_header_cells(rows, 0, (-INF, INF), (100.0, 130.0), drops)
    ck("D6 旁证无邻数字时不得并回本列",
       len(m) == 2 and len(drops) == 1 and drops[0][4] == "（4-6月）",
       "merged=%r drops=%r" % (m, drops))
    # 旁证正例：同一行两段都落在金额跨度内 → 照并
    rows2 = [(70, [(100.0, 130.0, "本报告期"), (120.0, 160.0, "（1-6月）")])]
    d2 = []
    m2 = cw._merge_header_cells(rows2, 0, (-INF, INF), (100.0, 130.0), d2)
    ck("D6 旁证相交片段仍合并",
       len(m2) == 1 and not d2, "merged=%r drops=%r" % (m2, d2))
    # 旁证：越界（OTHER）不记 drop——邻列表头是常态，不该整列待核
    rows3 = [(70, [(100.0, 130.0, "本报告期"), (134.0, 165.0, "（4-6月）")])]
    d3 = []
    m3 = cw._merge_header_cells(rows3, 0, (-INF, 135.0), (100.0, 130.0), d3)
    ck("D6 旁证越界片段不记待核",
       len(m3) == 2 and not d3, "merged=%r drops=%r" % (m3, d3))


def d7():
    """第二十三轮裁决 1–3：归属检查必须覆盖首片段、既有组与最终候选。"""
    INF = float("inf")

    # ① 裁决 1：**首片段**越界（金额左邻列的 （4-6月）），后一段合法片段不得把它带进来。
    #    左边界 = (90 + 100) / 2 = 95；（4-6月）中心 80.5 < 95 → OTHER。
    w1 = [
        W(0, 90, 45, 100, "营业收入"),
        W(65, 70, 96, 76, "（4-6月）"), W(100, 70, 138, 76, "本报告期"),
        W(60, 90, 90, 100, "200.00"), W(100, 90, 130, 100, "100.00"),
        W(0, 50, 40, 56, "单位：元"),
    ]
    col, _a, st = pv.column_of_amount_aligned(w1, "100.00", label=("营业收入",))
    ck("D7 首片段越界不得被后一段带进本列",
       st == "OK" and col == "本报告期",
       "st=%s col=%r（上一版是 （4-6月）本报告期）" % (st, col))

    # ② 裁决 2：**既有组**首片段与金额跨度不相交，边界未知时不得拼。
    #    上一版建组时用 need_core=False 记为 OK，合并时只重判新片段。
    w2 = [
        W(0, 90, 45, 100, "营业收入"),
        W(0, 60, 40, 66, "项目"), W(132, 60, 165, 66, "本报告期"),
        W(0, 70, 40, 76, "项目"), W(100, 70, 130, 76, "（4-6月）"),
        W(100, 90, 130, 100, "100.00"),
        W(0, 50, 40, 56, "单位：元"),
    ]
    col2, _a2, st2 = pv.column_of_amount_aligned(w2, "100.00", label=("营业收入",))
    ck("D7 既有组首片段也要按 need_core 重判",
       st2 == "COLUMN_ATTRIBUTION_UNPROVEN",
       "st=%s col=%r（上一版是 OK / 本报告期（4-6月））" % (st2, col2))

    # ③ 裁决 2 的左右倒序：无左邻数字、首片段在左侧 [65,96] → 同样不得拼
    w3 = [
        W(0, 90, 45, 100, "营业收入"),
        W(0, 60, 40, 66, "项目"), W(65, 60, 98, 66, "（4-6月）"),
        W(0, 70, 40, 76, "项目"), W(100, 70, 130, 76, "本报告期"),
        W(100, 90, 130, 100, "100.00"),
        W(0, 50, 40, 56, "单位：元"),
    ]
    col3, _a3, st3 = pv.column_of_amount_aligned(w3, "100.00", label=("营业收入",))
    ck("D7 左右倒序同样不得拼",
       st3 == "COLUMN_ATTRIBUTION_UNPROVEN",
       "st=%s col=%r" % (st3, col3))

    # ④ 裁决 3：**最终候选**不得放行已知越界的链。
    #    左边界 95，表头中心 87.5 → OTHER；上一版只按跨度重叠筛 → 返回 OK。
    w4 = [
        W(0, 90, 45, 100, "营业收入"),
        W(0, 70, 40, 76, "项目"), W(65, 70, 110, 76, "2026年半年度"),
        W(60, 90, 90, 100, "200.00"), W(100, 90, 130, 100, "100.00"),
        W(0, 50, 40, 56, "单位：元"),
    ]
    col4, _a4, st4 = pv.column_of_amount_aligned(w4, "100.00", label=("营业收入",))
    ck("D7 最终候选须过滤越界链",
       st4 == "NO_COLUMN", "st=%s col=%r（上一版是 OK / 2026年半年度）" % (st4, col4))

    # ⑤ 旁证同两条：首片段越界不得并；越界格子不得进候选
    import step4_column_witness as cw
    rows5 = [(70, [(65.0, 96.0, "（4-6月）"), (100.0, 138.0, "本报告期")])]
    d5 = []
    m5 = cw._merge_header_cells(rows5, 0, (95.0, INF), (100.0, 130.0), d5)
    ck("D7 旁证首片段越界不得并",
       len(m5) == 2 and [c[3] for c in m5] == ["OTHER", "OK"],
       "merged=%r" % (m5,))
    ck("D7 旁证格子带归属供候选过滤",
       all(len(c) == 4 for c in m5), "merged=%r" % (m5,))


d1()
d2()
d3()
d4()
d5()
d6()
d7()
print("-" * 60)
print("FAIL %d" % len(FAIL), FAIL)
sys.exit(1 if FAIL else 0)
