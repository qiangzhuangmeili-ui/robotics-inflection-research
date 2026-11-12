# -*- coding: utf-8 -*-
"""第十四轮：把 A/B/C/H 四处的返工写进 review.json 的变更说明。"""
import io
import sys

P = "verify_v5.py"
s = io.open(P, encoding="utf-8", newline="").read()
NL = "\r\n"

anchor = '    "open_findings": ['
if s.count(anchor) != 1:
    print("FAIL anchor")
    sys.exit(1)

block = (
    '    "round14_fixes": [' + NL +
    '        "A｜影响动词改**分句级窗口** `_effect_win()`：它不再套 `span=24`。'
    '第十三轮虽已把动词从剥完的中心语挪到未剥离窗口，但窗口仍限 24 字——'
    '「调减与以前年度销售折让及客户往来余额差异相关的应收账款100.00元」动词距金额 27 字，'
    '被截掉后判成新主语，非零调整直接丢掉。影响动词是分句属性，不是金额的局部修饰语；'
    '中心语仍用 24 字窗口（那里要的正是紧邻名词）→ C34 增至 45 条反例（㉗）",' + NL +
    '        "B｜栏目改「区间优先」：新增 `_date_span()`，列头自己写明期间（1—6月 / 4—6月 / '
    '6月30日 / 12月31日）时**先比区间**，区间不同即不同列，语义类相同也不认。'
    '语义类只能说明「本期 / 上年同期」，说明不了「哪一段」。'
    '「本报告期 / 本期金额」从同义断言里撤掉（没有区间时那是惯例不是事实），'
    '改为异义表里的区间用例 → C37 断言 3 同义 + 8 异义",' + NL +
    '        "C｜SELF_PAGE 同行判据的两处失效：① 调用点先对整页 `_nz`，换行被删光，'
    '「页眉合计 100.00 / 营业收入 200.00」两行拼成一行，同行限制当场失效——'
    '改为传原始页文本，归一化下沉到函数内逐行做；② 金额用裸子串匹配，'
    '`100.00 in "营业收入 1100.00"` 为真——新增 `_amt_in_text()` 边界判据。'
    '直测从 3 条扩到 7 条，全部按实际调用形式（原始页文本）跑",' + NL +
    '        "H｜状态块**只留指针与版本号**：去掉 `checks.count` / `self_check.checks` / '
    '`self_check.pass` / `sampling.finding` / claim_note 里的 `%d/%d`。'
    '新增 `CHECKS_KEEPS_COUNT` / `SELF_CHECK_KEEPS_COUNT` 两条判据，'
    '并把「把条数写回状态文件」做成注入（`checks_count` / `self_check_count`），'
    'C39 注入由 3 条增至 5 条，`all_caught: true`",' + NL +
    '    ],' + NL +
    anchor
)
s = s.replace(anchor, block, 1)
io.open(P, "w", encoding="utf-8", newline="").write(s)
print("ok")
