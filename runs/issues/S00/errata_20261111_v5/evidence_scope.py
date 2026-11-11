#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""证据覆盖模型 V8（生产与自检共用）

第十轮裁决 A 项的四处修正（V8）：

1. **单符号跨行必须合并**（`_clauses`）：`前期差错更正\\n√\\n不适用` 里 `√` 独占
   一行，原阈值 `marks >= 2` 不合并，`√` 单独解不出选项 → 判歧义 → 同时肯定与
   排除。V8 追加「组内存在纯符号碎片即合并」，但**仍不合并含标签的碎片**
   （`会计政策变更` / `会计差错更正` 两行本应各自成立）。

2. **主语行可带符号**（`_is_cause_label`）：`前期差错更正□` 的符号是下一行选项组
   被换行挤过来的，原实现因「含符号」拒绝认作主语行，导致主语被并进组内选项、
   `√` 认领主语、解出「排除 ERRATA」并静默放行。V8 改为「剥掉符号与编号后
   恰好等于一个原因词」即为主语行。

3. **「适用」与「某原因未勾」并存即歧义**（`option_group`）：同一组里勾了「适用」
   又排除了具体原因，两种读法互斥，不能按任一读法放行。

4. **金额绑定不得跨主题承接**（`_bind_amount`）：`未发生前期差错更正，营业收入
   100.00元` 曾把无关收入金额承接为事件肯定；`_AMOUNT_RADIUS` 也不足以覆盖
   `……经董事会和监事会审核后确认为100.00元` 这类长句。V8 改为：本分句只有一个
   原因且未出现其他报表项目词时，金额直接绑该原因（不受半径限制）；无原因词的
   分句仅在「续写/权益项目/金额起句」且未出现其他报表项目词时才承接上一主语。

第七轮裁决的三处修正：

1. **必需范围取并集**（A 项）：V6 在非自身/未知期间分支直接 `return`，把 status 本来要求的
   来源维度（`QUARTERLY_TABLE_PROVENANCE` / `PARENT_COMPATIBILITY`）覆盖掉了。
   非自身期间的分季度表行因此只要求比较范围、不要求季度表来源核验；非自身期间的累计差分
   行也不再要求父输入兼容。V7 改为 `期间要求 ∪ 取值来源要求`，两者互不替代。

2. **极性判定重写**（B 项）：V6 仍是「出现否定词即排除」，三个反例可误放行：
   - `前期差错更正\n√适用□不适用` —— 看到「不适用」就排除，未识别 √ 打在「适用」上；
   - `本期发生前期差错更正，但会计政策变更不适用` —— 否定词绑到了全句所有原因；
   - `未发生前期差错更正。本期发生前期差错更正100.00元` —— 同时肯定与否定，未判冲突。
   V7 按「否定就近绑定单个原因」+「勾选符号识别实际取值」+「肯定/否定冲突单列」重写。
   另：非零权益影响同时记「事件已确认」与「影响范围仅限特定项目」，不再只记后者。

3. **父输入兼容性**（C 项）：见 `build_errata_v5.py:parent_compatible`。
"""
import re
from collections import namedtuple

ERRATA = "ERRATA"
MERGER_RETRO = "MERGER_RETRO"
POLICY_CHANGE = "POLICY_CHANGE"
QUARTERLY_TABLE_PROVENANCE = "QUARTERLY_TABLE_PROVENANCE"
COMPARATIVE_SCOPE = "COMPARATIVE_SCOPE"
PARENT_COMPATIBILITY = "PARENT_COMPATIBILITY"
DOC_PERIOD_UNKNOWN = "DOC_PERIOD_UNKNOWN"

CAUSES = [ERRATA, MERGER_RETRO, POLICY_CHANGE]
SOURCE_DIMS = [QUARTERLY_TABLE_PROVENANCE, COMPARATIVE_SCOPE, PARENT_COMPATIBILITY]
# 允许由 scope_verifications.csv 结构化供给的来源维度（不含父输入核证）
SCOPE_REGISTRABLE = {QUARTERLY_TABLE_PROVENANCE, COMPARATIVE_SCOPE}

_RE_ERRATA = re.compile(r"追溯重述|差错更正|前期差错")
_RE_MERGER = re.compile(r"同一控制|合并范围")
_RE_POLICY = re.compile(r"会计政策")
_CAUSE_RE = {ERRATA: _RE_ERRATA, MERGER_RETRO: _RE_MERGER, POLICY_CHANGE: _RE_POLICY}

# 否定：按「就近绑定」处理，不再整句广播。裸「无」也纳入，但绑定半径收紧到 8 字，
# 避免「无商誉减值……本期发生差错更正」这类跨主题误绑（误绑方向是待核，不会误放行）。
_NEG_TOKENS = ["不适用", "未发生", "未采用", "未涉及", "不存在", "未进行",
               "无需", "没有发生", "无前期", "均无", "未", "无"]
# 「无重大影响」「无实质性影响」是在说重要性，不是在说没发生，不能当否定
_RE_MATERIALITY = re.compile(r"^(重大影响|实质性影响|影响|重大)")
_NEG_SHORT = {"未", "无"}
_NEG_RADIUS = 14
_NEG_RADIUS_SHORT = 8
# 金额绑定半径：金额常在「对期初未分配利润影响 X 元」之后，离原因词较远。
# 第十轮裁决 A 项：半径只是「跨主题」的粗略近似，不能单独承担语义绑定——
# 长句（`……经重新核算并经董事会和监事会审核后确认为100.00元`）会超出半径而
# 丢失明确影响金额。V8 增加「单原因分句直接绑定」与「报表项目词切换即断开」。
_AMOUNT_RADIUS = 24
# 续写标志：无原因词的分句以这些词起句，视为上一分句主语的延续
_RE_CONTINUE = re.compile(
    r"^\s*(?:[-−]?\d|对|其中|该|上述|前述|其|本期|本年|调整|影响|累计|经|确认|"
    r"金额|差额|净额|合计|期初未分配利润|未分配利润|所有者权益|盈余公积|净资产)")
# 报表项目切换：出现与本原因无关的项目词，不得再承接上一分句的原因
# 注意：`所有者权益合计` 属受影响的权益项目（`_RE_SCOPED_ITEM`），不是「另一个项目」，
# 放在这里会让「对所有者权益合计影响100.00元」丢失 scoped，故已剔除。
_RE_OTHER_ITEM = re.compile(
    r"营业收入|营业成本|营业利润|利润总额|净利润|总资产|负债|研发投入|"
    r"现金流量净额|每股收益|毛利率")

# 第十一轮 A 项：**不得靠扩充项目词表**判断「这句换了主语」。
# 判据改为看金额左侧紧跟的片段：
#   - 片段里有权益项目（期初未分配利润/净资产…）→ 该金额是原因的宾语，属续写；
#   - 片段以动词/功能词收尾（为/是/达/影响/确认/金额/元…）→ 属续写；
#   - 否则片段里的名词性成分就是**新主语**，不得承接上一分句的原因。
# 反例：`前期差错更正对期初未分配利润影响0.00元，其中营业总收入100.00元`
#   第二分句金额左侧是「其中营业总收入」，以名词收尾 → 新主语 → 不肯定 ERRATA。
_RE_VERB_TAIL = re.compile(
    r"(?:为|是|达|计|影响|确认|调整|重述|发生|存在|采用|金额|差额|净额|合计|"
    r"元|及|和|与|的|，|,|：|:|\d)$")
_RE_TAIL_FILLER = re.compile(
    r"其中|该|上述|前述|其|本期|本年|年初|累计|经|对|的|元|"
    r"[\s，,。；;：:\d\-−+.]")


def _new_subject(clause, st, window=10):
    """金额左侧紧跟片段是否构成**新主语**（第十一轮 A 项）。"""
    tail = clause[max(0, st - window):st]
    if not tail:
        return False
    if _RE_SCOPED_ITEM.search(tail):
        return False
    if _RE_VERB_TAIL.search(tail):
        return False
    return len(_RE_TAIL_FILLER.sub("", tail)) >= 2
# 肯定：确认发生 / 已采用 / 已调整
# 肯定词：必须是谓词，不能是原因短语本身。
# 「追溯重述」「追溯调整」多为小节标题（「追溯重述法的前期会计差错更正事项。」），
# 列进来会把跨页截断的标题当成「确认发生」。
_POS_TOKENS = ["已调整", "已重述", "已采用", "发生", "存在", "采用",
               "调整年初", "调整期初", "调整了"]
# 肯定词左侧若出现这些字，说明它其实在否定短语里（未发生 / 没有发生 / 不存在）
_POS_SUPPRESS = "未没无不非"

# 金额：负向后视，避免 100.00元 命中 0.00元
_RE_ZERO = re.compile(r"(?<![\d.])0\.00\s*元")
_RE_AMOUNT = re.compile(r"-?\d[\d,]*\.\d{2}\s*元")
# 只对特定项目给出结论（不覆盖本字段）
_RE_SCOPED_ITEM = re.compile(r"期初未分配利润|未分配利润|所有者权益|盈余公积|净资产")

SCOPE_LIMITED_METHODS = {"IMPORTANT_MATTER_NA", "NOTE_RETAINED_ERRATA_ZERO"}
METHOD_STRENGTH = {
    "IMPORTANT_MATTER_NA": "SCOPE_LIMITED",
    "NOTE_RETAINED_ERRATA_ZERO": "SCOPE_LIMITED_QUANTIFIED",
    "NOTE_TRACE_NA": "BOILERPLATE_CHECKBOX",
    "CHECKBOX_NA": "BOILERPLATE_CHECKBOX",
    "CHECKBOX_NO": "BOILERPLATE_CHECKBOX",
    "SUPP_NEG": "NARRATIVE_NEGATIVE",
    "NOTE_TRACE_NOT_OCCURRED": "NARRATIVE_NEGATIVE",
    "NOTE_RETAINED_ERRATA_NONZERO": "POSITIVE_NONZERO",
    "MANUAL_EVIDENCE": "FIELD_LEVEL_MANUAL",
    "ASSUMED_NO_PENDING_REVIEW": "ASSUMPTION",
}

SIMPLE_SQ = {"FIN.REV.SQ", "FIN.COST.SQ", "FIN.NPDEDT.SQ",
             "FIN.NPP.SQ", "FIN.OCF.SQ"}
# 只有「两个累计父输入相减」的派生值才需要父输入兼容性。
# Q1 单季 = Q1 累计，只有一个父输入，套两期相减是错的（第七轮 C 项）。
CUMULATIVE_DIFF_STATUSES = {"DERIVED_CUMULATIVE_DIFF", "DERIVED_QUARTERLY_SUM_OVERRIDE"}
Q1_EQUALS_YTD_STATUS = "DERIVED_Q1_EQUALS_YTD"
QUARTERLY_TABLE_STATUS = "EXTRACTED_QUARTERLY_TABLE"


def is_q1(row_period):
    return (row_period or "")[4:] == "0331"

# 分句：全角逗号一律切；半角逗号只在不是千分位时切
# （`-160,517.06元` 曾被切成两段，8 条事件确认因此丢失）
_CLAUSE_SPLIT = re.compile(r"[；;。，\n]|(?<!\d),(?!\d)")
# 勾选式取值：□/√/☑ + 适用/不适用/是/否
_RE_CHECKBOX_PAIR = re.compile(r"([□√☑■✔●○])\s*(不适用|适用|是|否)")
_CHECKED_MARKS = set("√☑■✔●")
_RE_CHECKBOX_VALUE = re.compile(r"^[□√☑■✔●○\s]*(不适用|适用|是|否)\s*$")
# 纯标题/标签行：只说明「这一节在讲什么」，本身不断言发生或未发生
_RE_LABEL = re.compile(r"^(追溯重述法|未来适用法|追溯调整法|会计政策变更|"
                       r"会计估计变更|前期差错更正|前期差错|差错更正)$")

Polarity = namedtuple("Polarity",
                      "excluded affirmed scoped mentioned conflict")


def _is_option_fragment(seg):
    """该片段是否只由勾选符号 + 选项标签 + 空白组成（选项组的碎片）。

    第九轮裁决 B 项：原 PDF 里每个 `□` 后插入换行时，选项组被 `_CLAUSE_SPLIT`
    切碎成 `□` / `会计政策变更 √` / `会计差错更正 □` …，每片各自还能解出一个
    自洽但**反向**的取值（√ 绑到前一片的标签上）。必须先把碎片拼回完整选项组。
    """
    s = _RE_MARK.sub("", seg or "")
    for lab, _c in _OPT_LABELS:
        s = s.replace(lab, "")
    return re.sub(r"[\s\u3000]", "", s) == ""


def _is_pure_mark(seg):
    """该片段是否只有一个勾选符号（`√` / `□`），不含任何标签文字。"""
    return bool(_RE_MARK.search(seg or "")) and \
        re.sub(r"[\s\u3000]", "", _RE_MARK.sub("", seg or "")) == ""


_RE_HEADING_PREFIX = re.compile(
    r"^(?:[（(][一二三四五六七八九十]+[）)]|[一二三四五六七八九十]+、|"
    r"\d+\s*[、.．]|注\s*\d+\s*[、.：:]?)")
# 纯原因标签的全集（整串匹配）。不能用 _cause_spans 的区间覆盖来判：
# `前期差错更正` 里 `前期差错`(0-4) 与 `差错更正`(2-6) 是重叠的，finditer 只取
# 前者，区间并集覆盖不到整串。
_RE_CAUSE_ONLY = re.compile(
    r"^(?:追溯重述法?|未来适用法|追溯调整法|会计政策变更|会计估计变更|"
    r"前期差错更正|前期差错|会计差错更正|差错更正|"
    r"同一控制下企业合并|合并范围变更)$")


def _is_cause_label(seg):
    """纯原因标签（`前期差错更正` / `会计政策变更` …）：勾选组的主语行，不属于组内选项。

    第十轮裁决 A 项：`前期差错更正□` 这类「原因词 + 符号」同样是主语行——那个符号
    是下一行选项组被换行挤过来的。原实现要求「不含任何符号」，于是把主语并进了
    组内选项，`√` 反过来认领主语、解出「排除 ERRATA」并静默放行。
    V8 改为：剥掉勾选符号、空白、小节编号后，恰好是一个原因词即为主语行。
    """
    s = re.sub(r"[\s\u3000]", "", _RE_MARK.sub("", seg or ""))
    m = _RE_HEADING_PREFIX.match(s)
    if m:
        s = s[m.end():]
    return bool(s) and bool(_RE_CAUSE_ONLY.match(s))


def _clauses(txt):
    """分句，但**不切开选项组**：连续碎片在含 ≥2 个符号、或含纯符号碎片时先拼回一组。

    第十轮裁决 A 项：`前期差错更正\\n√\\n不适用` 的 `√` 独占一行，原阈值
    `marks >= 2` 不合并，`√` 单独解不出选项 → 判歧义 → 同时肯定与排除（假冲突）。
    V8 追加「组内有纯符号碎片即合并」。仍**不**合并「符号 + 标签」的碎片：
    `会计政策变更` / `会计差错更正` 两行本应各自成立。

    主语行必须留在组外：`前期差错更正\\n√适用□不适用` 若把标题并进组，符号左侧
    也能解出一套自洽取值（√ 认领「前期差错更正」），会与右侧解冲突而假判歧义。
    """
    raw = [c for c in _CLAUSE_SPLIT.split(txt or "") if c.strip()]
    out, buf = [], []

    def flush():
        if not buf:
            return
        head = buf[0]
        if len(buf) > 1 and _is_cause_label(head):
            out.append(head.strip())
            buf[:] = buf[1:]
        marks = sum(len(_RE_MARK.findall(x)) for x in buf)
        if len(buf) > 1 and (marks >= 2 or any(_is_pure_mark(x) for x in buf)):
            out.append(" ".join(x.strip() for x in buf))
        else:
            out.extend(buf)
        buf[:] = []

    for c in raw:
        if not _is_option_fragment(c):
            flush()
            out.append(c)
            continue
        # 组内已出现符号后又来一个纯原因标签：这是下一组的主语，必须先断开。
        # 只认「不带符号」的纯标签——`会计差错更正 □` 属于符号与标签交替的选项链
        # （`□ 会计政策变更 √ 会计差错更正 □ …`），必须留在组内。
        if _is_cause_label(c) and not _RE_MARK.search(c) and \
                any(_RE_MARK.search(x) for x in buf):
            flush()
        buf.append(c)
    flush()
    return out


def checkbox_value(txt):
    """返回被勾选的那一项（适用/不适用/是/否）；无法唯一判定返回 None。

    必须看符号，不能看文字：`□适用√不适用` 与 `√适用□不适用` 都含「不适用」。
    """
    pairs = _RE_CHECKBOX_PAIR.findall(txt or "")
    if not pairs:
        return None
    checked = [v for m, v in pairs if m in _CHECKED_MARKS]
    if len(checked) == 1:
        return checked[0]
    return None


def _cause_spans(clause):
    spans = []
    for cause, rx in _CAUSE_RE.items():
        for m in rx.finditer(clause):
            spans.append((m.start(), m.end(), cause))
    spans.sort()
    return spans


def _nearest(spans, pos, limit=None):
    """离 pos 最近的原因（按区间距离）；超出 limit 视为未绑定。"""
    best, bestd = None, None
    for s, e, cause in spans:
        d = 0 if s <= pos < e else min(abs(pos - s), abs(pos - e))
        if bestd is None or d < bestd:
            best, bestd = cause, d
    if limit is not None and bestd is not None and bestd > limit:
        return None
    return best


def _neg_positions(clause):
    out = []
    for tok in _NEG_TOKENS:
        for m in re.finditer(re.escape(tok), clause):
            out.append((m.start(), m.end(), tok))
    return out


def _mask(clause):
    """把专有名词遮成等长占位符，避免「未分配利润」里的「未」被当否定词。

    等长替换保证位置索引与原文一致。
    """
    out = list(clause)
    for m in _RE_SCOPED_ITEM.finditer(clause):
        for i in range(m.start(), m.end()):
            out[i] = "□"
    return "".join(out)


def _pos_positions(clause, negs=(), spans=()):
    """肯定谓词位置。

    除「前一字是否定字」外，还要处理跨词否定：`本期未发生采用追溯重述法的
    前期会计差错更正事项` 里的「采用」被「未发生」管辖，不能算肯定——否则与
    否定撞成假冲突（第八轮 618 条误冲突的根因）。判据：该肯定之前存在否定词，
    且否定词与该肯定之间没有再出现别的原因词（出现则说明否定只管前半句）。
    """
    out = []
    for tok in _POS_TOKENS:
        for m in re.finditer(re.escape(tok), clause):
            st = m.start()
            # 「未发生」「没有发生」「不存在」里的「发生/存在」不算肯定
            if st > 0 and clause[st - 1] in _POS_SUPPRESS:
                continue
            if any(ne <= st and not any(ns < cs < st for cs, _ce, _c in spans)
                   for ns, ne, _t in negs):
                continue
            out.append((st, m.end()))
    return out


# 小节标题：`（二）`/`一、`/`2、`/`注1：` 等，用来判「勾选组的主语是否换了」
_RE_HEADING = re.compile(r"^(?:[（(][一二三四五六七八九十]+[）)]|"
                         r"[一二三四五六七八九十]+、|\d+\s*[、.．]|"
                         r"注\s*\d+\s*[、.：:]?)")


_OPT_LABELS = [
    ("不适用", "NA"), ("适用", "YES"), ("是", "YES"), ("否", "NA"),
    ("会计政策变更", "POLICY_CHANGE"), ("会计差错更正", "ERRATA"),
    ("前期差错更正", "ERRATA"), ("差错更正", "ERRATA"),
    ("其他原因", "OTHER"), ("同一控制下企业合并", "MERGER_RETRO"),
    ("合并范围变更", "MERGER_RETRO"), ("未来适用法", "FUTURE"),
    ("追溯重述法", "RETRO"),
]
_MARK_CHARS = "\u25a1\u221a\u2611\u25a0\u2714\u25cf\u25cb"
_RE_MARK = re.compile(r"[%s]" % _MARK_CHARS)
CANON = {ERRATA: "ERRATA", MERGER_RETRO: "MERGER_RETRO", POLICY_CHANGE: "POLICY_CHANGE"}


def _label_at(text, at_start):
    """在 text 的开头/结尾匹配一个选项标签，返回 (canon, 长度)。"""
    best = None
    for lab, canon in _OPT_LABELS:
        if at_start:
            if text.startswith(lab) and (best is None or len(lab) > best[1]):
                best = (canon, len(lab))
        else:
            if text.endswith(lab) and (best is None or len(lab) > best[1]):
                best = (canon, len(lab))
    return best


def _solve_layout(clause, marks, layout):
    """按单一版面假设解出每个符号的取值。

    layout="after"：符号在标签前（`√适用 □不适用`），取符号右侧的标签；
    layout="before"：符号在标签后（`适用√ 不适用□`），取符号左侧的标签。
    选中侧无标签时回退到另一侧（混排版面）；两侧都无标签、或解出的标签重复
    （同一选项被两个符号认领）时，该版面假设不成立，返回 None。
    """
    out = []
    for m in marks:
        before = clause[:m.start()].rstrip()
        after = clause[m.end():].lstrip()
        primary, fallback = ((after, True), (before, False)) if layout == "after" \
            else ((before, False), (after, True))
        lab = _label_at(primary[0], at_start=primary[1])
        if lab is None:
            lab = _label_at(fallback[0], at_start=fallback[1])
        if lab is None:
            return None
        out.append((m.group(0) in _CHECKED_MARKS, lab[0]))
    labels = [x[1] for x in out]
    if len(set(labels)) != len(labels):
        return None
    return out


def option_group(clause):
    """解析勾选式选项组，返回 (checked, unchecked, ambiguous)。

    必须按符号位置判实际取值：`□适用√不适用` 与 `√适用□不适用` 文字完全相同。
    两种版面都要支持——符号在标签前（常见）与符号在标签后（`适用√不适用□`）。

    第八轮返工：V7 逐符号同时看左右两侧，把「左侧是上一个选项」当成歧义，
    于是任何正常选项行（`□会计政策变更 √会计差错更正 □其他原因 □不适用`）
    都判成 conflict，三协电机 15 条重述差异被误放行。现改为**版面整体求解**：
    两种版面各自解一遍，取能自洽（标签互不重复）的那一种；两种都自洽且结论
    不同才算真歧义。
    """
    marks = list(_RE_MARK.finditer(clause))
    if not marks:
        return set(), set(), False
    sol_after = _solve_layout(clause, marks, "after")
    sol_before = _solve_layout(clause, marks, "before")
    if sol_after is not None and sol_before is not None and sol_after != sol_before:
        return set(), set(), True
    chosen = sol_after if sol_after is not None else sol_before
    if chosen is None:
        return set(), set(), True
    checked = {lab for chk, lab in chosen if chk}
    unchecked = {lab for chk, lab in chosen if not chk}
    # 第十轮裁决 A 项：同一组里勾了「适用」又排除了某个具体原因，两种读法互斥
    # （「本节适用」 vs 「不是这个原因」），不能按任一读法放行，须回原页。
    if "YES" in checked and (unchecked & {CANON[c] for c in CAUSES}):
        return set(), set(), True
    return checked, unchecked, False


def _amounts(c):
    """分句内全部金额（按出现位置）。零值与非零值必须分开记，不能整句归一。"""
    out = []
    for m in _RE_AMOUNT.finditer(c):
        try:
            v = float(re.sub(r"[,\s元]", "", m.group(0)))
        except ValueError:
            continue
        out.append((m.start(), m.end(), v))
    return out


def _bind_amount(c, spans, prev_causes, scoped, affirmed, excluded, neg_c, single=None):
    """金额句绑定：本句原因 → 单原因直绑 → 承接上一分句的原因（主语延续）。

    第九轮裁决 B 项两处修正：

    1. **逐个金额判定**。原 `nonzero = bool(_RE_AMOUNT.search(c)) and not zero`
       让同一分句里的零值把非零值一起压掉——`对期初未分配利润影响0.00元及对
       净资产影响100.00元` 因此只剩 scoped、丢失事件肯定。
    2. **已有 excluded 不得压掉后续非零金额的肯定**。勾选「√不适用」与金额
       「净资产影响100.00元」并存时，必须留下 `conflict` 交回原页待核，
       而不是静默按勾选放行（原 `t not in excluded` 条件即此绕过）。

    第十轮裁决 A 项两处修正：

    3. **单原因分句不再受字符半径限制**。`前期差错更正对期初未分配利润影响经
       重新核算并经董事会和监事会审核后确认为100.00元` 的金额距原因词 40 余字，
       半径 24 直接丢弃，导致「明确影响金额」既无 affirmed 也无 scoped。
    4. **不得跨主题承接主语**。`未发生前期差错更正，营业收入100.00元` 曾把无关
       收入金额承接为 ERRATA 的事件肯定，造出假冲突。V8 要求：本分句出现其他
       报表项目词即断开；无原因词的分句还须以续写词/权益项目/金额起句。
    5. **不得只靠项目词表**（第十一轮 A 项）。`…影响0.00元，其中营业总收入100.00元`
       里的「营业总收入」不在词表内，于是 100.00 元被承接成 ERRATA 肯定。
       现改为结构判据 `_new_subject()`：金额左侧紧跟片段以名词收尾即为新主语。
    """
    amounts = _amounts(c)
    if not amounts:
        return
    has_item = bool(_RE_SCOPED_ITEM.search(c))
    other_item = bool(_RE_OTHER_ITEM.search(c))
    continue_ok = bool(_RE_CONTINUE.match(c)) or has_item or ("影响" in c)
    for st, _en, v in amounts:
        tgt = _nearest(spans, st, limit=_AMOUNT_RADIUS) if spans else None
        new_subj = _new_subject(c, st)
        targets = set()
        if tgt:
            targets = {tgt}
        elif single and not other_item and not new_subj:
            targets = {single}
        elif prev_causes and continue_ok and not other_item and not new_subj:
            targets = set(prev_causes)
        if not targets:
            continue
        nonzero = abs(v) > 0
        for t in targets:
            if has_item:
                scoped.add(t)
            if nonzero and t not in neg_c:
                affirmed.add(t)


def analyse(rec):
    """按分句 + 选项组 + 就近绑定判极性。

    第七轮、第八轮两次返工的要点：
    - 勾选式选项组按符号判取值，支持「符号在前」与「符号在后」两种版面；歧义时记冲突。
    - 勾选结果只作用于本选项组，不能广播到整句后跳过其余叙述（三协电机误放行的根因）。
    - 「无重大影响」是重要性表述，不是否定。
    - 金额句在无原因词时承接上一分句的原因，避免「影响0.00元，对净资产影响100.00元」丢失非零事件。
    """
    txt = (rec.get("evidence") or "") if isinstance(rec, dict) else str(rec or "")
    excluded, affirmed, scoped, mentioned = set(), set(), set(), set()
    cls = _clauses(txt)
    prev_causes = set()

    for raw in cls:
        c = raw.strip()
        spans = _cause_spans(c)
        causes = {s[2] for s in spans}
        if causes:
            mentioned |= causes

        # 0) 选项组：符号决定取值，且只作用于本组原因
        chk, unchk, ambig = option_group(c)
        if chk or unchk or ambig:
            # 勾选行常与原因标题分行（`前期差错更正\n√适用□不适用`）：
            # 本句无原因词时承接上一分句的主语，不能因「本句没提原因」而丢弃勾选结果。
            tgt = causes or prev_causes
            if ambig:
                for cs in tgt:
                    excluded.add(cs)
                    affirmed.add(cs)
            else:
                explicit = {CANON[cs] for cs in tgt}
                for cs in tgt:
                    lab = CANON[cs]
                    if lab in chk:
                        affirmed.add(cs)
                    elif lab in unchk:
                        excluded.add(cs)
                # 组内只有「适用/不适用」而无具体原因标签：作用到本组主语
                if "YES" in chk and not (explicit & chk):
                    for cs in tgt:
                        if CANON[cs] not in unchk:
                            affirmed.add(cs)
                if "NA" in chk:
                    for cs in tgt:
                        if CANON[cs] not in chk:
                            excluded.add(cs)
            if causes:
                _bind_amount(c, spans, prev_causes, scoped, affirmed, excluded, set(),
                             single=next(iter(causes)) if len(causes) == 1 else None)
                prev_causes = causes
            continue

        if not causes:
            # 标题行：主语换到别的话题（`（四）审批程序及其他说明`），
            # 后续勾选组不得再绑到上一个差错更正标题上。
            if _RE_HEADING.match(c):
                prev_causes = set()
                continue
            # 主语承接：本句无原因词，但带金额 → 绑到上一分句的原因
            if prev_causes:
                _bind_amount(c, [], prev_causes, scoped, affirmed, excluded, set())
            continue

        # 纯标签行（小标题）不断言
        if _RE_LABEL.match(c):
            prev_causes = causes
            continue

        scan = _mask(c)
        single = len(causes) == 1
        only = next(iter(causes))
        negs = _neg_positions(scan)
        neg_c = set()
        for st, en, tok in negs:
            if tok in _NEG_SHORT and _RE_MATERIALITY.match(scan[en:en + 6]):
                continue
            if single:
                neg_c.add(only)
                continue
            radius = _NEG_RADIUS_SHORT if tok in _NEG_SHORT else _NEG_RADIUS
            tgt = _nearest(spans, st if st else en, limit=radius)
            if tgt:
                neg_c.add(tgt)

        pos_c = set()
        for st, en in _pos_positions(scan, negs, spans):
            tgt = only if single else _nearest(spans, st, limit=_NEG_RADIUS)
            if tgt:
                pos_c.add(tgt)

        if single and neg_c and pos_c:
            excluded.add(only)
            affirmed.add(only)
        else:
            excluded |= neg_c
            affirmed |= pos_c

        _bind_amount(c, spans, prev_causes, scoped, affirmed, excluded, neg_c,
                     single=only if single else None)
        prev_causes = causes

    conflict = excluded & affirmed
    return Polarity(excluded, affirmed, scoped, mentioned, conflict)


def coverage_of(rec):
    """兼容旧接口：只返回明确排除的原因集合。"""
    return analyse(rec).excluded


def polarity_str(p):
    return "excluded=%s|affirmed=%s|scoped=%s|conflict=%s" % (
        ",".join(sorted(p.excluded)) or "-", ",".join(sorted(p.affirmed)) or "-",
        ",".join(sorted(p.scoped)) or "-", ",".join(sorted(p.conflict)) or "-")


def binds_field(rec):
    """证据是否绑定到具体字段/表格/行列（NA 类均为否）。"""
    txt = (rec.get("evidence") or "") if isinstance(rec, dict) else str(rec or "")
    if (rec.get("method") or "") == "MANUAL_EVIDENCE":
        return True
    return bool(re.search(r"第\s*\d+\s*[行列表]|附注[一二三四五六七八九十]|\d{3,}\s*元", txt))


def is_own_period(document_period, row_period):
    """显式判断，不再用字符串真值。未知文档期间返回 None。"""
    if not document_period:
        return None
    return document_period == row_period


def period_scope(document_period, row_period):
    """只看「期间」带来的要求。"""
    own = is_own_period(document_period, row_period)
    if own is None:
        return {ERRATA, MERGER_RETRO, COMPARATIVE_SCOPE, DOC_PERIOD_UNKNOWN}
    if own is False:
        # 比较列 / 分季度表供给别的期间：任何追溯调整都会改写比较数
        return {ERRATA, MERGER_RETRO, COMPARATIVE_SCOPE}
    return {ERRATA}


def source_scope(status, row_period=""):
    """只看「取值来源」带来的要求。

    第七轮 C 项：Q1 单季等于 Q1 累计，只有一个父输入，不套两期相减，
    因此 Q1 不要求 PARENT_COMPATIBILITY（它要证的是「这个唯一父输入未被重述」，
    已由 ERRATA 维度覆盖）。
    """
    if status == QUARTERLY_TABLE_STATUS:
        return {QUARTERLY_TABLE_PROVENANCE}
    if status in CUMULATIVE_DIFF_STATUSES and not is_q1(row_period):
        return {PARENT_COMPATIBILITY}
    return set()


def required_scope(status, document_period, row_period):
    """该行要断言「未被重述」，必须覆盖哪些维度。

    第七轮 A 项：期间要求与来源要求**取并集**。V6 在非自身期间分支直接返回，
    把 QUARTERLY_TABLE_PROVENANCE / PARENT_COMPATIBILITY 覆盖掉了。
    """
    return period_scope(document_period, row_period) | source_scope(status, row_period)


def source_dims_for(status, document_period, row_period):
    """只看来源维度的缺口，用于「B=是」的确认类断言。"""
    req = required_scope(status, document_period, row_period)
    return {d for d in req if d in SOURCE_DIMS or d == DOC_PERIOD_UNKNOWN}


def judge(rec, doc, status, document_period, row_period, ruled=None, bval="",
          parent_ok=None, scope_ok=None):
    """返回 dict：resolution / scope_required / scope_covered / scope_missing / evidence_note / polarity。

    `scope_ok`：该行已取得结构化核证记录的来源维度集合（比较范围 / 季度表来源）。
    第八轮 C 项：这些维度不能靠「文档里提到过」自动覆盖，只能由核证登记表供给；
    未传或为空即视为未核，仍留在 scope_missing。
    """
    def out(res, req=(), cov=(), mis=(), note="", pol="", lvl=""):
        return {"resolution": res,
                "scope_level": lvl,
                "scope_required": ";".join(sorted(req)),
                "scope_covered": ";".join(sorted(cov)),
                "scope_missing": ";".join(sorted(mis)),
                "evidence_note": note, "polarity": pol}

    req = required_scope(status, document_period, row_period)

    if ruled:
        # 裁决解除不等于「范围已证成」：必需范围照常登记，覆盖留空。
        return out("RESOLVED_BY_RULING", req, (), req, lvl="RULED",
                   note="独立复核已裁决解除：%s" % str(ruled.get("basis", ""))[:90])
    if not doc:
        return out("UNRESOLVED_NO_DOCUMENT", req, (), req, lvl="NO_DOC",
                   note="B 该行无 document_id，无法定位供给文档")
    if rec is None:
        return out("UNRESOLVED_DOC_NEVER_VERIFIED", req, (), req, lvl="NO_VERIFY",
                   note="供给文档 %s 不在 1,007 份核验清单内" % doc[:20])

    method = rec.get("method") or ""
    p = analyse(rec)
    covered = set(p.excluded)
    if PARENT_COMPATIBILITY in req and parent_ok is True:
        covered.add(PARENT_COMPATIBILITY)
    if scope_ok:
        # 第九轮裁决 E 项：结构化核证只能供给「比较范围 / 分季度表来源」两类来源
        # 维度；PARENT_COMPATIBILITY 必须走 parent_verifications.csv，不能被来源
        # 登记顶替（否则 parent_ok=False 的行仍可解除）。
        covered |= (set(scope_ok) & SCOPE_REGISTRABLE) & req
    missing = req - covered
    level = "FIELD" if binds_field(rec) else "SECTION"
    pol = polarity_str(p)

    # 同一原因既被肯定又被否定：冲突必须待核，不能按任一侧解除。
    # 但只有「本行必须排除的原因」冲突才阻断——POLICY_CHANGE 不是必需维度，
    # 它自相矛盾不影响「未被差错更正」这条断言（152 条误阻断即由此而来）。
    blocking = p.conflict & (req & set(CAUSES))
    if blocking:
        return out("UNRESOLVED_POLARITY_CONFLICT", req, covered, missing,
                   "证据同时肯定与否定 %s（p.%s），须回读原页判实际勾选/金额"
                   % (",".join(sorted(blocking)), rec.get("page")), pol, level)

    if method == "ASSUMED_NO_PENDING_REVIEW":
        return out("PENDING_WEAK_ASSUMPTION", req, covered, missing,
                   "方法为假设（未查原文）p.%s" % rec.get("page"), pol, level)

    # B=是：断言方向相反，要证的是「确实发生过」
    if bval == "是":
        # 第七轮 D 项：不再用方法名兜底，事件确认必须来自原文极性
        event_ok = ERRATA in p.affirmed
        src_gap = source_dims_for(status, document_period, row_period) - covered
        if not event_ok:
            return out("PENDING_CONFIRMED_UNSUPPORTED", req, covered, missing,
                       "B=是 但证据未确认发生过差错更正 p.%s" % rec.get("page"), pol, level)
        if src_gap:
            return out("PENDING_CONFIRMED_EVENT_FIELD_OPEN", req, covered, src_gap,
                       "事件已确认，但来源维度未核：%s（p.%s）"
                       % (";".join(sorted(src_gap)), rec.get("page")), pol, level)
        return out("RESOLVED_RESTATEMENT_CONFIRMED", req, covered, (),
                   "证据确认发生更正且来源维度已覆盖（p.%s）" % rec.get("page"), pol, level)

    if method in SCOPE_LIMITED_METHODS and not binds_field(rec):
        return out("PENDING_SCOPE_LIMITED_METHOD", req, covered, missing,
                   "方法 %s 仅覆盖「重大会计差错更正」一节，未绑定字段/表格/行列（p.%s）；"
                   "已排除=%s，仍缺=%s" % (method, rec.get("page"),
                                          ",".join(sorted(p.excluded)) or "无",
                                          ";".join(sorted(missing)) or "无"), pol, level)

    # 事件已确认但影响只落在特定权益项目：事件与字段影响分开记
    if ERRATA in p.affirmed and ERRATA in p.scoped:
        return out("PENDING_EVENT_CONFIRMED_SCOPE_LIMITED", req, covered, missing,
                   "证据确认发生差错更正，但只给出权益项目影响金额（p.%s），"
                   "不能证明本字段受影响；仍缺=%s"
                   % (rec.get("page"), ";".join(sorted(missing)) or "无"), pol, level)

    if ERRATA in p.affirmed:
        return out("UNRESOLVED_EVIDENCE_CONTRADICTS", req, covered, missing,
                   "证据确认存在差错更正（p.%s），与 B=%s 冲突" % (rec.get("page"), bval or "空"), pol, level)

    if not missing:
        return out("RESOLVED_SCOPE_COVERED", req, covered, (),
                   "证据覆盖该行所需全部维度；method=%s p.%s scope_level=%s"
                   % (method, rec.get("page"), level), pol, level)

    if DOC_PERIOD_UNKNOWN in missing:
        label, why = "PENDING_DOC_PERIOD_UNKNOWN", "文档期间未知，无法判定是否自身期间"
    elif QUARTERLY_TABLE_PROVENANCE in missing:
        label, why = "PENDING_SOURCE_PROVENANCE", "取值来源为分季度表，NA 类证据不涉及该表"
    elif COMPARATIVE_SCOPE in missing:
        label, why = "PENDING_SOURCE_PROVENANCE", "取值来自比较列，未核比较范围"
    elif PARENT_COMPATIBILITY in missing:
        label, why = "PENDING_PARENT_COMPATIBILITY", "累计差分父输入未证兼容"
    else:
        label, why = "PENDING_CAUSE_UNCOVERED", "证据未覆盖 %s" % ";".join(sorted(missing))
    return out(label, req, covered, missing,
               "%s；method=%s p.%s scope_level=%s" % (why, method, rec.get("page"), level),
               pol, level)


def group_key(method, excluded, affirmed, status, is_own):
    return "|".join([method or "NONE",
                     "+".join(sorted(excluded)) or "NONE",
                     ("AFF:" + "+".join(sorted(affirmed))) if affirmed else "NOAFF",
                     status or "NONE",
                     "OWN" if is_own else ("COMPARATIVE" if is_own is False else "UNKNOWN")])
