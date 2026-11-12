# -*- coding: utf-8 -*-
"""第十五轮 H 项：顶层 claim_note 也是状态文件的一部分，必须与 s00_errata 同源。"""
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


# 1) write_status：claim_note 只生成一次，顶层与 s00_errata 共用
rep(
    '    e["claim_note"] = (' + NL +
    '        "S00 勘误 V5 自检 %s 通过；条数与逐项结果只在 "' + NL +
    '        "%s/review.json，此处不复述。"' + NL +
    '        "第 4 步批量核证与第 5 步重算分层未做；锚定期回退与上游准入未冻结；"' + NL +
    '        "S04 第二轮与 S05 不放行。"' + NL +
    '        % (SELF_CHECK_VERSION, STATUS_REL))',
    '    # 第十五轮 H 项：顶层 claim_note 也是状态文件的一部分。' + NL +
    '    # 上一版只写 e["claim_note"]，顶层留着 V10 的长文（「40/40 PASS」「30 条反例」），' + NL +
    '    # 于是「状态文件不复述计数」只做到一半。现在只生成一次，两处共用同一字符串。' + NL +
    '    _claim = (' + NL +
    '        "S00 勘误 V5 自检 %s 通过；条数与逐项结果只在 "' + NL +
    '        "%s/review.json，此处不复述。"' + NL +
    '        "第 4 步批量核证与第 5 步重算分层未做；锚定期回退与上游准入未冻结；"' + NL +
    '        "S04 第二轮与 S05 不放行。"' + NL +
    '        % (SELF_CHECK_VERSION, STATUS_REL))' + NL +
    '    e["claim_note"] = _claim' + NL +
    '    st["claim_note"] = _claim',
    "H1")

# 2) status_problems：顶层 claim_note 必须与 s00_errata 同源且无计数
rep(
    '    if ("AWAITING_RECHECK_%d" % RECHECK_ROUND) not in (st.get("status") or ""):',
    '    # 第十五轮 H 项：顶层 claim_note 单独受检——它是上一版漏掉的那一处。' + NL +
    '    _cn = st.get("claim_note") or ""' + NL +
    '    if not _cn:' + NL +
    '        bad.append("TOP_CLAIM_NOTE_MISSING")' + NL +
    '    elif re.search(r"\\d+\\s*/\\s*\\d+\\s*PASS", _cn) or _RE_LEGACY_COUNT.search(_cn):' + NL +
    '        bad.append("TOP_CLAIM_NOTE_KEEPS_COUNT")' + NL +
    '    elif _cn != (e.get("claim_note") or ""):' + NL +
    '        bad.append("TOP_CLAIM_NOTE_DIVERGES")' + NL +
    '    if ("AWAITING_RECHECK_%d" % RECHECK_ROUND) not in (st.get("status") or ""):',
    "H2")

# 3) C39 注入：把旧顶层 claim_note 放回去
rep(
    '_inj5["s00_errata"]["self_check"]["pass"] = len(checks)' + NL +
    '_inj_count_self = status_problems(_inj5)',
    '_inj5["s00_errata"]["self_check"]["pass"] = len(checks)' + NL +
    '_inj_count_self = status_problems(_inj5)' + NL +
    '_inj6 = json.loads(json.dumps(_post_state))' + NL +
    '_inj6["claim_note"] = ("S00 勘误 V5（自检 V10，40/40 PASS）：C34 增至 30 条反例…")' + NL +
    '_inj_claim_note = status_problems(_inj6)',
    "H3")

rep(
    '           and bool(_inj_count_checks) and bool(_inj_count_self))',
    '           and bool(_inj_count_checks) and bool(_inj_count_self)' + NL +
    '           and bool(_inj_claim_note))',
    "H4")

rep(
    '                   "self_check_count": _inj_count_self,',
    '                   "self_check_count": _inj_count_self,' + NL +
    '                   "top_claim_note": _inj_claim_note,',
    "H5")

io.open(P, "w", encoding="utf-8", newline="").write(s)
print("ok")
