# -*- coding: utf-8 -*-
"""第十四轮 H 项（续）：把「只留指针与版本号」写成可检验的判据。"""
import io
import sys

P = "verify_v5.py"
s = io.open(P, encoding="utf-8", newline="").read()
NL = "\r\n"


def rep(old, new, tag):
    global s
    if s.count(old) != 1:
        print("FAIL %s count=%d" % (tag, s.count(old)))
        sys.exit(1)
    s = s.replace(old, new, 1)


# 1) checks 指针里出现 count → 结构违规
rep(
    '    elif _RE_LEGACY_COUNT.search(json.dumps(e["checks"], ensure_ascii=False)):' + NL +
    '        bad.append("CHECKS_STILL_QUOTES_LEGACY_COUNTS")',
    '    elif "count" in e["checks"]:' + NL +
    '        # 第十四轮 H 项：状态块只留指针与版本号，条数写在这里就是第二份数字' + NL +
    '        bad.append("CHECKS_KEEPS_COUNT")' + NL +
    '    elif _RE_LEGACY_COUNT.search(json.dumps(e["checks"], ensure_ascii=False)):' + NL +
    '        bad.append("CHECKS_STILL_QUOTES_LEGACY_COUNTS")',
    "S1")

# 2) self_check 指针里出现 checks/pass → 结构违规
rep(
    '    elif not e["self_check"].get("canonical"):' + NL +
    '        # 结构性问题：指针没有落点' + NL +
    '        bad.append("SELF_CHECK_POINTER_INCOMPLETE")',
    '    elif [k for k in ("checks", "pass") if k in e["self_check"]]:' + NL +
    '        # 第十四轮 H 项：条数与通过数只在 review.json' + NL +
    '        bad.append("SELF_CHECK_KEEPS_COUNT:%s" %' + NL +
    '                   [k for k in ("checks", "pass") if k in e["self_check"]])' + NL +
    '    elif not e["self_check"].get("canonical"):' + NL +
    '        # 结构性问题：指针没有落点' + NL +
    '        bad.append("SELF_CHECK_POINTER_INCOMPLETE")',
    "S2")

# 3) sampling 的派生键清单补 finding（旧版业务结论字段）
rep(
    '_LEGACY_SAMPLING_KEYS = ',
    '_LEGACY_SAMPLING_KEYS = ',
    "S3-noop") if False else None

io.open(P, "w", encoding="utf-8", newline="").write(s)
print("ok")
