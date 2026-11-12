# -*- coding: utf-8 -*-
"""第十五轮 B 项：期间解析扩写 + 「无法确认不得按语义类放行」。"""
import io
import sys

P = "parent_verify.py"
s = io.open(P, encoding="utf-8", newline="").read()
NL = "\n"  # 该文件是 LF


def rep(old, new, tag):
    global s
    if s.count(old) != 1:
        print("FAIL %s count=%d" % (tag, s.count(old)))
        sys.exit(1)
    s = s.replace(old, new, 1)


# 1) 正则扩写：半年 / 季度 / 不带年的月区间 / 月末时点
rep(
    '_RE_SPAN_RANGE = re.compile(r"(\\d{4})\\s*年\\s*(\\d{1,2})\\s*[—\\-~～至]\\s*(\\d{1,2})\\s*月")' + NL +
    '_RE_SPAN_POINT = re.compile(r"(\\d{4})\\s*年\\s*(\\d{1,2})\\s*月\\s*(\\d{1,2})\\s*日")' + NL +
    '_RE_SPAN_MONTH = re.compile(r"(\\d{4})\\s*年\\s*(\\d{1,2})\\s*月")',
    '# 第十五轮 B 项：`_date_span` 原来只认「年+月区间」「年+月+日」「年+月」，'
    '于是\n'
    '# `2026年上半年`、`2026Q2`、`1-6月`（不带年）全部解析成 None，退回语义类被判等价。\n'
    '# 解析不出来**不等于可以按语义类证明等价**——那正是 Codex 指出的漏网路径。\n'
    '_RE_SPAN_RANGE = re.compile(r"(\\d{4})\\s*年\\s*(\\d{1,2})\\s*[—\\-~～至]\\s*(\\d{1,2})\\s*月")\n'
    '_RE_SPAN_RANGE_NY = re.compile(r"(?<!\\d)(\\d{1,2})\\s*[—\\-~～至]\\s*(\\d{1,2})\\s*月")\n'
    '_RE_SPAN_HALF = re.compile(r"(?:(\\d{4})\\s*年)?\\s*(?:上半年|半年度|H1)")\n'
    '_RE_SPAN_HALF2 = re.compile(r"(?:(\\d{4})\\s*年)?\\s*(?:下半年|H2)")\n'
    '_RE_SPAN_QUARTER = re.compile(r"(?:(\\d{4})\\s*年)?\\s*(?:第)?\\s*[Qq]([1-4])")\n'
    '_RE_SPAN_QCN = re.compile(r"(?:(\\d{4})\\s*年)?\\s*第?([一二三四1-4])\\s*季度")\n'
    '_RE_SPAN_POINT = re.compile(r"(\\d{4})\\s*年\\s*(\\d{1,2})\\s*月\\s*(\\d{1,2})\\s*日")\n'
    '_RE_SPAN_MONTH = re.compile(r"(\\d{4})\\s*年\\s*(\\d{1,2})\\s*月")\n'
    '# 「写着期间但解析不了」的线索词：出现这些词却解不出区间 → 不得按语义类放行\n'
    '_RE_PERIOD_HINT = re.compile(r"\\d{4}\\s*年|\\d{1,2}\\s*月|季度|[Qq][1-4]|上半年|下半年|半年度|"'
    'r"年初|年末|期末|期初|本期|上期|同期|累计")',
    "P1")

# 2) _date_span 扩写
rep(
    '    t = _col_norm(label)' + NL +
    '    m = _RE_SPAN_RANGE.search(t)' + NL +
    '    if m:' + NL +
    '        return ("R", int(m.group(1)), int(m.group(2)), int(m.group(3)))' + NL +
    '    m = _RE_SPAN_POINT.search(t)' + NL +
    '    if m:' + NL +
    '        return ("P", int(m.group(1)), int(m.group(2)), int(m.group(3)))' + NL +
    '    m = _RE_SPAN_MONTH.search(t)' + NL +
    '    if m:' + NL +
    '        return ("M", int(m.group(1)), int(m.group(2)))' + NL +
    '    return None',
    '    t = _col_norm(label)' + NL +
    '    m = _RE_SPAN_RANGE.search(t)' + NL +
    '    if m:' + NL +
    '        return ("R", int(m.group(1)), int(m.group(2)), int(m.group(3)))' + NL +
    '    m = _RE_SPAN_HALF.search(t)' + NL +
    '    if m:' + NL +
    '        return ("H1", int(m.group(1)) if m.group(1) else None)' + NL +
    '    m = _RE_SPAN_HALF2.search(t)' + NL +
    '    if m:' + NL +
    '        return ("H2", int(m.group(1)) if m.group(1) else None)' + NL +
    '    m = _RE_SPAN_QUARTER.search(t)' + NL +
    '    if m:' + NL +
    '        return ("Q", int(m.group(1)) if m.group(1) else None, int(m.group(2)))' + NL +
    '    m = _RE_SPAN_QCN.search(t)' + NL +
    '    if m:' + NL +
    '        q = "一二三四".find(m.group(2))' + NL +
    '        return ("Q", int(m.group(1)) if m.group(1) else None,' + NL +
    '                (q + 1) if q >= 0 else int(m.group(2)))' + NL +
    '    m = _RE_SPAN_POINT.search(t)' + NL +
    '    if m:' + NL +
    '        return ("P", int(m.group(1)), int(m.group(2)), int(m.group(3)))' + NL +
    '    m = _RE_SPAN_MONTH.search(t)' + NL +
    '    if m:' + NL +
    '        return ("M", int(m.group(1)), int(m.group(2)))' + NL +
    '    m = _RE_SPAN_RANGE_NY.search(t)' + NL +
    '    if m:' + NL +
    '        return ("R0", int(m.group(1)), int(m.group(2)))' + NL +
    '    return None',
    "P2")

# 3) cols_equivalent：一侧能解析、另一侧写着期间却解析不了 → 不得放行
rep(
    '    sa, sb = _date_span(registered), _date_span(actual)' + NL +
    '    if sa and sb:' + NL +
    '        return sa == sb',
    '    sa, sb = _date_span(registered), _date_span(actual)' + NL +
    '    if sa and sb:' + NL +
    '        return sa == sb' + NL +
    '    if sa or sb:' + NL +
    '        # 一侧解出了区间，另一侧写着期间线索却解不出：**无法确认，按不等价处理**。' + NL +
    '        # 不能把「我解析不了」翻译成「可以按语义类证明等价」——那是把未知当已知。' + NL +
    '        other = actual if sa else registered' + NL +
    '        if _RE_PERIOD_HINT.search(_col_norm(other)):' + NL +
    '            return False',
    "P3")

io.open(P, "w", encoding="utf-8", newline="").write(s)
print("ok")
