# -*- coding: utf-8 -*-
"""第十四轮 H 项：状态文件只留指针与版本号，不再复述任何计数。"""
import io
import sys

P = "verify_v5.py"
s = io.open(P, encoding="utf-8", newline="").read()
NL = "\r\n"
n_ok = 0


def rep(old, new, tag):
    global s, n_ok
    if s.count(old) != 1:
        print("FAIL %s count=%d" % (tag, s.count(old)))
        sys.exit(1)
    s = s.replace(old, new, 1)
    n_ok += 1


# ---- H-1: _sc 去掉 checks/pass ----
rep(
    '    _sc = {"version": SELF_CHECK_VERSION, "checks": total_n, "pass": passed_n,' + NL +
    '           "canonical": "%s/review.json#checks" % STATUS_REL,' + NL +
    '           "detail": "%s/review.json" % STATUS_REL,' + NL +
    '           "note": "计数由 verify_v5.py 写出；逐项结果与注入明细只在 review.json。"}',
    '    # 第十四轮 H 项：状态块**只留指针与版本号**。' + NL +
    '    # 旧版还写了 checks=41 / pass=41，这两个数字和 review.json 的' + NL +
    '    # checks_total / checks_pass 是同一件事，两处存储就是两份可以漂移的数字。' + NL +
    '    _sc = {"version": SELF_CHECK_VERSION,' + NL +
    '           "canonical": "%s/review.json#checks" % STATUS_REL,' + NL +
    '           "detail": "%s/review.json" % STATUS_REL,' + NL +
    '           "note": "状态文件不复述任何计数；条数、逐项结果与注入明细只在 review.json。"}',
    "H1")

# ---- H-2: e["checks"] 去掉 count ----
rep(
    '    e["checks"] = {"canonical": "%s/review.json#checks" % STATUS_REL,' + NL +
    '                   "count": total_n,' + NL +
    '                   "note": "检查项名称/结果/明细一律不在状态文件复述；旧版曾在此写死反例数、"',
    '    e["checks"] = {"canonical": "%s/review.json#checks" % STATUS_REL,' + NL +
    '                   "note": "检查项名称/结果/明细/条数一律不在状态文件复述；旧版曾在此写死反例数、"',
    "H2")

# ---- H-3: sampling 去掉 finding ----
rep(
    '                "keys_diff；状态文件只留定位器版本与指针，杜绝第二份数字漂移。",' + NL +
    '        "finding": "SH:600936 FIN.REV.SQ@20250630 的核验证据未定位到，"' + NL +
    '                   "属上游核验记录异常，未放行",' + NL +
    '    }',
    '                "keys_diff；状态文件只留定位器版本与指针，杜绝第二份数字漂移。"' + NL +
    '        # 第十四轮 H 项：去掉业务结论字段（finding）。' + NL +
    '        # 状态文件不是报告，它只该告诉读者「去哪里看」；' + NL +
    '        # 把具体样本结论写在这里，下一轮又会变成一处需要手改的字。' + NL +
    '    }',
    "H3")

# ---- H-4: claim_note 去计数 ----
rep(
    '        "S00 勘误 V5 自检 %s（%d/%d PASS）。逐项结果、注入明细与限制见 "' + NL +
    '        "%s/review.json 与 REPORT.md；此处不复述条数/环数/种数，避免与 review.json 漂移。"' + NL +
    '        "第 4 步批量核证与第 5 步重算分层未做；44/231/378 未冻结；"' + NL +
    '        "S04 第二轮与 S05 不放行。"' + NL +
    '        % (SELF_CHECK_VERSION, passed_n, total_n, STATUS_REL))',
    '        "S00 勘误 V5 自检 %s 通过；条数与逐项结果只在 "' + NL +
    '        "%s/review.json，此处不复述。"' + NL +
    '        "第 4 步批量核证与第 5 步重算分层未做；锚定期回退与上游准入未冻结；"' + NL +
    '        "S04 第二轮与 S05 不放行。"' + NL +
    '        % (SELF_CHECK_VERSION, STATUS_REL))',
    "H4")

io.open(P, "w", encoding="utf-8", newline="").write(s)
print("patched %d blocks" % n_ok)
