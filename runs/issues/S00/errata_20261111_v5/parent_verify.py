#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""父输入兼容性 / 来源维度的唯一依据：核证登记表（生产与自检共用）。

第八轮裁决 C 项明确否掉两条自动判据：
- **同文档不能自动证明兼容**——同一报告可能含调整前后列或混合来源；
- **上游「双否」不能直接证明兼容**——三协电机已证明 verdict 可能与原文相反，
  它只能作为待核线索。
同时澄清：正常同口径累计数相减，**不要求两期调整额相等**；只有主张
「调整影响相互抵消」时才须证明调整额相等。

第九轮裁决 C 项又指出：只比对「父终值」不够——登记里把父文档换成无关文档、
把父期间和口径写错、审查人填 `x`、日期留空，仍能返回 VERIFIED。因此把
登记记录绑定到**实际父输入**（doc/period/value/口径三元组/版本）。

第十轮裁决 B 项继续指出四处「只验形式」：

1. **单位折算键名错误**。`_expect()` 提供 `unit_scale`，`gap()` 却读
   `expect[side].get("unit")`，实际恒回退 1 倍——真实原件
   `187,875.40 万元 = 1,878,754,000 元` 会被正确引文拒绝，反之 1 倍口径的
   错误引文会被放行。V10 统一改读 `unit_scale`，并限定金额字段只接受
   `1/1000/10000` 三档。
2. **栏目与版本只验形式**。`p1_column` 任意非空即过、`adjust_version` 只验枚举
   与两父相等。V10 要求：栏目必须是**期间列头**且出现在引文中；版本必须等于
   该父实际采用的 `version_used` 归类（ORIGINAL / RESTATED），并在引文里有
   对应标记（重述后 / 无调整后列）。
3. **引文含同一个数字不证明是目标指标和目标期间**。V10 要求引文同时含
   **指标名 + 期间列头 + 父数**，三者缺一不可。
4. **生产引文源仍是上游摘要**。V10 的 `evidence_of(doc, page)` 必须回读
   **登记页**原件（生产侧由 `_pdf_page` 提供），不再是 `results.csv.evidence`。

第十轮裁决 E 项：来源维度登记还须核对 `source_page`，引文须绑定具体表格／
期间列头／目标行列，不能只靠「全文命中 + 含年份」——`Ltd.年度报告——2025——`
这类封面片段曾同时取得 `COMPARATIVE_SCOPE` 与 `QUARTERLY_TABLE_PROVENANCE`。
"""
import csv
import datetime
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

import evidence_scope as es

# ---------------- 父输入核证登记表 ----------------
COLS = ["security_id", "field_id", "period_key", "ytd_field",
        "p1_period", "p2_period", "p1_doc", "p2_doc",
        "p1_value", "p2_value", "p1_page", "p2_page",
        "p1_quote", "p2_quote",
        "p1_column", "p2_column", "p1_adjust_version", "p2_adjust_version",
        "consolidation_scope", "unit_scale", "currency", "scope_basis",
        "version_basis", "conclusion", "review_role", "reviewer", "reviewed_at"]

# 调整前后版本：登记只能声明这两类，且必须等于该父实际 version_used 的归类。
# 第十轮裁决 B2：不再允许 SAME_VERSION 作为免证标签——「两父同版本」由实际
# version_used 相等直接判定，不需要登记者另立名目。
ADJUST_VERSIONS = {"ORIGINAL", "RESTATED"}
REVIEW_ROLES = {"INDEPENDENT_REVIEW", "SELF_CHECK"}
REVIEWER_PLACEHOLDERS = {"", "x", "xx", "xxx", "-", "--", "n/a", "na",
                         "none", "null", "test", "tbd", "todo", "self", "me"}
# 金额字段允许的折算倍数（s00 的 unit_scale 实际取值：1 / 1000 / 10000，
# 另有 pct / times 用于比率字段——那些不参与父输入相减）
AMOUNT_UNITS = {"1", "1000", "10000"}
_AMOUNT_TOKEN = re.compile(r"(?<![\d.,])-?\d[\d,]*(?:\.\d+)?")
_MIN_QUOTE = 12
_MIN_BASIS = 20

# 指标名：引文必须点出目标指标（目标行），否则「同数不同指标」无法区分
METRIC_ALIASES = {
    "FIN.REV.YTD": ("营业收入", "营业总收入"),
    "FIN.COST.YTD": ("营业成本", "营业总成本"),
    "FIN.NPDEDT.YTD": ("扣除非经常性损益", "扣非"),
    "FIN.NPP.YTD": ("归属于上市公司股东的净利润", "归属于母公司股东的净利润",
                    "归母净利润"),
    "FIN.OCF.YTD": ("经营活动产生的现金流量净额", "经营活动现金流量净额"),
}
# 版本标记：重述版必须在引文里出现「调整后/重述后/更正后」之一；
# 原版必须在引文里不出现这些标记（否则引的其实是调整后列）
_VER_MARK_RESTATED = ("调整后", "重述后", "更正后", "调整后金额")
_VER_MARK_FORBIDDEN_ORIGINAL = ("调整后", "重述后", "更正后")
# 期间列头须含年份或这些相对列名之一
_PERIOD_COL = re.compile(r"\d{4}|本期|上期|本年|上年|年末|期末|年初|期初|"
                         r"本报告期|上年同期|本年年初")
# 来源维度的关键词：引文必须点出该维度的实际证据载体
DIM_MARKERS = {
    es.QUARTERLY_TABLE_PROVENANCE: ("分季度", "季度主要财务数据", "第一季度",
                                    "第二季度", "第三季度", "第四季度"),
    es.COMPARATIVE_SCOPE: ("比较", "上年同期", "上年年末", "上期", "期初",
                           "调整前", "重述前"),
}


def _nz(s):
    return re.sub(r"\s+", "", s or "")


def _reviewer_ok(ent):
    r = (ent.get("reviewer") or "").strip()
    return len(r) >= 2 and r.lower() not in REVIEWER_PLACEHOLDERS


def _role_ok(ent):
    return (ent.get("review_role") or "").strip() in REVIEW_ROLES


def _date_ok(s):
    s = (s or "").strip()
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        return False
    try:
        datetime.date(int(s[:4]), int(s[5:7]), int(s[8:10]))
    except ValueError:
        return False
    return True


def _page_ok(s):
    """物理页码必须是正整数（第十轮 E 项：`source_page` 未被核对）。"""
    s = (s or "").strip()
    return bool(re.match(r"^[1-9]\d{0,3}$", s))


def ver_class(v):
    """把 s00 的 version_used 归到登记可声明的一类。未知值返回 None（阻断）。"""
    v = (v or "").strip().upper()
    if v == "ORIGINAL":
        return "ORIGINAL"
    if v.startswith("RESTATED") or v.startswith("CORRECTED"):
        return "RESTATED"
    return None


def _num_in_quote(quote, value, unit_scale="1", exact=None):
    """引文里是否出现该父数本身（按 unit_scale 折算）。

    第九轮 C 项：只比父终值字段，登记可以把引文换成无关文档的通用标题片段。
    这里要求引文里真的写出这个数，`DOC-…` 之类的标题片段无法满足。
    第十轮 B1：`unit_scale` 必须是实际倍数（1/1000/10000），键名不得再写成
    `unit`——否则 187,875.40 万元永远对不上 1,878,754,000 元。

    第二十轮裁决 3：上一版的「第三级」允许把 token 在**任意数字位**切开，
    只要前半段等于父数、后半段够长就算命中。独立实测：
    `_num_in_quote("营业收入100999999", "100")` 返回 True，
    `_num_in_quote("营业收入100.00", "999", exact="100.00")` 也返回 True——
    后者更严重：`exact` 命中了，却**没有回头核对这个金额词本身的数值**。
    现在：

    ① 给了 `exact`（调用方已按词坐标定位到金额词）时，必须**同时**满足
       「该词文本出现在引文里」**且**「该词数值 × unit_scale == 目标值」；
       粘连只能靠这条值核对兜住，不靠切数字位。
    ② 没给 `exact` 时，只做严格的 token 全等，**取消任意数字位切分**。
       切不开就判不命中（→ 待核），方向安全。
    """
    if isinstance(exact, (tuple, list)):
        exact = exact[2] if len(exact) > 2 else None
    tgt = _dec(value)
    if tgt is None:
        return False
    mlt = _dec(unit_scale or "1")
    if mlt is None or mlt <= 0:
        mlt = Decimal(1)
    if exact and _nz(exact):
        ex = _dec(exact)
        if ex is None:
            return False
        if not _same_amount(ex * mlt, tgt):
            return False          # 金额词的值与目标不符，文本命中也不算
        return _nz(exact) in _nz(quote)
    for m in _AMOUNT_TOKEN.finditer(quote or ""):
        v = _dec(m.group(0).replace(",", ""))
        if v is not None and _same_amount(v * mlt, tgt):
            return True
    return False


def load(path):
    """返回 {(security_id, field_id, period_key): 记录}。"""
    idx = {}
    p = Path(path)
    if not p.exists():
        return idx
    with open(p, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            idx[(r.get("security_id", ""), r.get("field_id", ""),
                 r.get("period_key", ""))] = r
    return idx


# ---------------- 来源维度核证登记表 ----------------
SCOPE_COLS = ["security_id", "field_id", "period_key", "dimension",
              "target_field", "target_period",
              "document_id", "source_page", "evidence_quote",
              "conclusion", "review_role", "reviewer", "reviewed_at"]


def load_scope(path):
    """来源维度核证登记表：{(sec, fld, pk): [记录, ...]}。"""
    idx = {}
    p = Path(path)
    if not p.exists():
        return idx
    with open(p, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            idx.setdefault((r.get("security_id", ""), r.get("field_id", ""),
                            r.get("period_key", "")), []).append(r)
    return idx


_PERIOD_TOKENS = {
    "0331": ("第一季度", "一季度", "3月31日", "1-3月", "1月至3月", "本期第一季度"),
    "0630": ("半年度", "上半年", "6月30日", "1-6月", "1月至6月", "第二季度"),
    "0930": ("第三季度", "三季度", "9月30日", "1-9月", "1月至9月"),
    "1231": ("年度", "12月31日", "全年", "1-12月", "1月至12月"),
}


def _period_tokens(pk):
    """该期间键对应的「具体期间」表述（第十一轮 E 项）。"""
    tail = (pk or "")[4:]
    return _PERIOD_TOKENS.get(tail, ())


# 第十二轮 E 项：三项词语同时出现 ≠ 三者属于同一证据关系。
_MAX_DIM_SPAN = 160                       # 指标名—期间—载体三者的最大字符跨度
_RE_FOOTNOTE = re.compile(r"注\s*[:：]|附注|脚注|见附表|附表见|页脚|见附录|详见")


def dim_window_ok(q, key, dim):
    """引文是否把「目标指标名 + 该行具体期间 + 维度载体」绑在同一个窗口内。

    第十二轮实测的两个绕过：
      - `2025年上半年营业收入` + `甲`×501 + `比较`：三词都在，但相隔 500 字；
      - `2025年上半年营业收入100.00元。……页脚注释：分季度见附表`：载体词来自页脚。
    因此除「三词同现」外还要求：三者跨度 ≤ `_MAX_DIM_SPAN`，且载体词所在句子
    不是注释/页脚（`注：`/`附注`/`见附表`/`详见`…）。
    """
    names = METRIC_ALIASES.get(key[1]) or METRIC_ALIASES.get(
        key[1][:-3] + ".YTD" if key[1].endswith(".SQ") else key[1])
    ptoks = _period_tokens(key[2])
    markers = DIM_MARKERS.get(dim, ())
    if not names or not ptoks or not markers:
        return False
    ni = [q.find(n) for n in names if q.find(n) >= 0]
    if not ni:
        return False
    ti = [q.find(t) for t in ptoks if q.find(t) >= 0]
    if not ti:
        return False
    mi = [(q.find(m), m) for m in markers if q.find(m) >= 0]
    if not mi:
        return False
    best = None
    for i in ni:
        for j in ti:
            for k, m in mi:
                span = max(i, j, k + len(m)) - min(i, j, k)
                if best is None or span < best[0]:
                    best = (span, k, m)
    if best is None or best[0] > _MAX_DIM_SPAN:
        return False
    _span, k, m = best
    # 载体词所在句子不得是注释/页脚
    cut = max(q.rfind(s, 0, k) for s in "。；;") if any(s in q[:k] for s in "。；;") else -1
    seg = q[cut + 1:k + len(m)]
    if _RE_FOOTNOTE.search(seg):
        return False
    return True


def scope_dims(entries, key, evidence_of, expect_doc=None):
    """该行已获结构化核证的来源维度。

    第九轮 E 项三条收紧：
    1. 维度只接受 `COMPARATIVE_SCOPE` / `QUARTERLY_TABLE_PROVENANCE`；
       `PARENT_COMPATIBILITY` 必须走 `parent_verifications.csv`，不能被顶替。
    2. `target_field` / `target_period` 必须等于目标键本身（不能拿别的行作依据）。
    3. `document_id` 必须等于该行实际供给文档（不能拿无关文档的通用引文）。

    第十轮 E 项追加两条：
    4. `source_page` 必须是正整数，且引文必须能在**该物理页**原文中定位
       （原实现只查全文，`Ltd.年度报告——2025——` 这类封面片段即可通过）。
    5. 引文必须点出该维度自己的证据载体：分季度表来源须含「分季度／季度主要
       财务数据／第 N 季度」，比较范围须含「比较／上年同期／期初／调整前」等。
       仅「文档标题 + 年份」不构成来源核证。
    """
    ok = set()
    for e in entries.get(key, []):
        dim = (e.get("dimension") or "").strip()
        if dim not in es.SCOPE_REGISTRABLE:
            continue
        if (e.get("conclusion") or "").strip() != "CONFIRMED":
            continue
        if not _reviewer_ok(e) or not _role_ok(e) or not _date_ok(e.get("reviewed_at")):
            continue
        if (e.get("target_field") or "").strip() != key[1]:
            continue
        if (e.get("target_period") or "").strip() != key[2]:
            continue
        doc = (e.get("document_id") or "").strip()
        if expect_doc is not None and doc != (expect_doc or "").strip():
            continue
        page = (e.get("source_page") or "").strip()
        if not _page_ok(page):
            continue
        q = _nz(e.get("evidence_quote"))
        if len(q) < _MIN_QUOTE:
            continue
        if q not in _nz(evidence_of(doc, page)):
            continue
        if key[2][:4] not in q:
            continue
        if not any(mk in q for mk in DIM_MARKERS.get(dim, ())):
            continue
        # 第十一轮 E 项：维度词 + 年份仍不构成「实质关系」。
        # `经营计划2025年，公司成功登陆……报告期初比较` 这类经营叙述曾取得比较范围，
        # 但它没有点出目标指标、也没有点出该行的具体期间，证明不了这个维度。
        # 第十二轮：窗口/距离/页脚规则下沉到这里——`_dim_window()` 只约束自检侧
        # 构造记录，外部登记记录走 `scope_dims()`，两处口径必须同一套。
        if not dim_window_ok(q, key, dim):
            continue
        ok.add(dim)
    return ok


def _col_norm(s):
    return re.sub(r"[\s*_]", "", s or "")


# 期间列头的**语义类**（第十二轮 B 项）：只做子串比对时，「登记：本期发生额」
# 与「实际：本期数」会被判不一致（正确登记被拒），而「登记：本期」与
# 「实际：上年同期」反而可能靠子串蒙过。改为先归到期间类，再比类。
# 第十三轮 B 项：语义类过宽会把不同列互认——
# 「上年同期」（去年同期）与「上期」（紧邻上一期间）不是同一列；
# 「本年累计」（年初至报告期末）与「本期数」（单季/本报告期）也不是同一列。
# 故拆成 6 类，跨类一律不互认；同类内仍靠归一化子串兜住措辞差异。
# 顺序有意义：先匹配更具体的（上年累计/累计/年初至期末），再匹配宽的「本期」。
# 第十九轮 D2：`PRIOR_YEAR_YTD` 必须排在 `CURRENT_YTD` **之前**——
# `上年年初至报告期末` 同时含「年初至报告期末」，先判 CURRENT_YTD 会把它归成
# 「本期累计」，于是「本期累计」与「上年累计」互认。
_COL_CLASSES = [
    ("PRIOR_YEAR_YTD", r"上年年初至报告期末|上年同期累计|上年累计"),
    ("CURRENT_YTD", r"年初至报告期末|年初至本报告期末|本年累计|本期累计|本年数|"
                    r"本报告期末累计|累计数"),
    ("PRIOR_YEAR_SAME", r"上年同期|上年同期数|上年同期金额|同期数|比较期|上年同期发生额"),
    ("PRIOR_PERIOD", r"上期|上期数|上期发生额|上期金额|上一期"),
    ("YEAR_OPEN", r"年初|期初|上年年末|上年度末|年初数"),
    ("PERIOD_END", r"期末|期末数|年末|年末数"),
    ("CURRENT", r"本期|本期数|本期发生额|本期金额|本报告期|报告期"),
]


def _col_class(s):
    t = _col_norm(s)
    for name, pat in _COL_CLASSES:
        if re.search(pat, t):
            return name
    return None


# 第十五轮 B 项：`_date_span` 原来只认「年+月区间」「年+月+日」「年+月」，于是
# `2026年上半年`、`2026Q2`、`1-6月`（不带年）全部解析成 None，退回语义类被判等价。
# 解析不出来**不等于可以按语义类证明等价**——那正是 Codex 指出的漏网路径。
_RE_SPAN_RANGE = re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*[—–−－~～至\-]\s*(\d{1,2})\s*月")
_RE_SPAN_RANGE_NY = re.compile(r"(?<!\d)(\d{1,2})\s*[—–−－~～至\-]\s*(\d{1,2})\s*月")
_RE_SPAN_HALF = re.compile(r"(?:(\d{4})\s*年)?\s*(?:上半年|半年度|H1)")
_RE_SPAN_HALF2 = re.compile(r"(?:(\d{4})\s*年)?\s*(?:下半年|H2)")
_RE_SPAN_QUARTER = re.compile(r"(?:(\d{4})\s*年)?\s*(?:第)?\s*[Qq]([1-4])")
# 第二十轮裁决 2：`2025年度` / `2026年度` 原先都归成 `||累计`，绝对年份丢失，
# 于是两个不同会计年度的年度列可以互认。年度 = 1–12 月，必须解出年份。
_RE_SPAN_YEAR = re.compile(r"(\d{4})\s*年\s*(?:度|全年|报表)")
_RE_SPAN_QCN = re.compile(r"(?:(\d{4})\s*年)?\s*第?([一二三四1-4])\s*季度")
_RE_SPAN_POINT = re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日")
_RE_SPAN_MONTH = re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月")
# 「写着期间但解析不了」的线索词：出现这些词却解不出区间 → 不得按语义类放行
_RE_PERIOD_HINT = re.compile(r"\d{4}\s*年|\d{1,2}\s*月|季度|[Qq][1-4]|上半年|下半年|半年度|"r"年初|年末|期末|期初|本期|上期|同期|累计")


def _loose_year(t):
    """列头里没有「年」字时，退一步找 4 位年份（`2026Q2` 这种写法）。"""
    m = re.search(r"(?<!\d)(20\d{2})(?!\d)", t)
    return int(m.group(1)) if m else None


def _date_span(label):
    """列头里写明的期间区间；没写就返回 None。

    第十四轮 B 项：语义类只能说明「这是本期 / 上年同期」，说明不了「哪一段」。
    列头自己写着 `本期金额（2026年1—6月）` 与 `本报告期金额（2026年4—6月）`，
    归到同一类就互认，是把 6 个月与 3 个月当成同一列。区间写得出来就必须比区间。

    第十五轮 B 项：各种写法**先归一到同一个坐标系**再比，否则
    `2026年上半年` 与 `2026年1-6月` 明明同段却因为标签不同被判不等价（假阴性）。
    归一规则：上半年→1–6 月、下半年→7–12 月、Qn→3n-2..3n 月；
    没有年份的写法用 `R0` 与带年份的 `R` 区分（年份不确定就不能认同一列）。
    """
    t = _col_norm(label)
    m = _RE_SPAN_RANGE.search(t)
    if m:
        return ("R", int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = _RE_SPAN_HALF.search(t)
    if m:
        y = int(m.group(1)) if m.group(1) else _loose_year(t)
        return ("R", y, 1, 6) if y else ("R0", 1, 6)
    m = _RE_SPAN_HALF2.search(t)
    if m:
        y = int(m.group(1)) if m.group(1) else _loose_year(t)
        return ("R", y, 7, 12) if y else ("R0", 7, 12)
    m = _RE_SPAN_YEAR.search(t)
    if m:
        return ("R", int(m.group(1)), 1, 12)
    m = _RE_SPAN_QUARTER.search(t)
    if m:
        y = int(m.group(1)) if m.group(1) else _loose_year(t)
        q = int(m.group(2))
        return ("R", y, 3 * q - 2, 3 * q) if y else ("R0", 3 * q - 2, 3 * q)
    m = _RE_SPAN_QCN.search(t)
    if m:
        y = int(m.group(1)) if m.group(1) else _loose_year(t)
        q = "一二三四".find(m.group(2))
        q = (q + 1) if q >= 0 else int(m.group(2))
        return ("R", y, 3 * q - 2, 3 * q) if y else ("R0", 3 * q - 2, 3 * q)
    m = _RE_SPAN_POINT.search(t)
    if m:
        return ("P", int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = _RE_SPAN_MONTH.search(t)
    if m:
        return ("M", int(m.group(1)), int(m.group(2)))
    m = _RE_SPAN_RANGE_NY.search(t)
    if m:
        return ("R0", int(m.group(1)), int(m.group(2)))
    return None


def cols_equivalent(registered, actual):
    """登记列头与实际列头是否指同一列。

    第二十轮裁决 2：上一版在「两侧都解出区间」时**直接** `return sa == sb`，
    跳过了相对年份，于是
    `cols_equivalent("上年同期（1-6月）", "本报告期（1-6月）")` 返回 True，
    `cols_equivalent("上期（2026年1-6月）", "本期（2026年1-6月）")` 也返回 True——
    区间相同就把「上年/上期」和「本期」当成同一列。

    现在的顺序（任一维度冲突即拒绝，不再有「先返回」的短路）：

    ① 区间：两侧都写了且不同 → 不等价；
    ② 相对年：两侧都写了且不同 → 不等价（上年/上期/本期 互不认）；
    ③ 累计属性：两侧都写了且不同 → 不等价；
    ④ 区间两侧都有且相等（相对年、累计均不冲突）→ 等价；
    ⑤ 一侧有区间、另一侧写着期间线索却解不出 → 不等价（未知不得当已知）；
    ⑥ 否则比期间类；
    ⑦ 最后才退回归一化子串。
    """
    pa, pb = _canon_parts(registered), _canon_parts(actual)
    if pa[1] and pb[1] and pa[1] != pb[1]:
        return False
    if pa[0] and pb[0] and pa[0] != pb[0]:
        return False
    if pa[2] and pb[2] and pa[2] != pb[2]:
        return False
    if pa[1] and pb[1]:
        return True
    if pa[1] or pb[1]:
        # 一侧解出了区间，另一侧写着期间线索却解不出：**无法确认，按不等价处理**。
        # 不能把「我解析不了」翻译成「可以按语义类证明等价」——那是把未知当已知。
        other = actual if pa[1] else registered
        if _RE_PERIOD_HINT.search(_col_norm(other)):
            return False
    a, b = _col_class(registered), _col_class(actual)
    if a and b:
        return a == b
    na, nb = _col_norm(registered), _col_norm(actual)
    return bool(na) and bool(nb) and (na in nb or nb in na)


def _dec(txt):
    """把「57,296,869.60」解析成 Decimal；不是数值返回 None。

    第十九轮 D3：原实现走 float，`abs(v - target) < 0.01` 这种容差会把
    「目标 100.009、页面只有 100.00」判成命中。金额一律用十进制，比较按
    **分位逐位相等**（`_same_amount`），不设浮点容差。
    """
    if txt is None:
        return None
    s = re.sub(r"[,\s元]", "", str(txt))
    if not s or not re.match(r"^-?\d+(\.\d+)?$", s):
        return None
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


_CENT = Decimal("0.01")


def _has_subcent(d):
    """金额是否带「分」以下的非零尾数（如 100.004）。

    第二十轮裁决 3：`quantize(0.01)` 会把 100.004 舍成 100.00 再判相等，
    于是「页面 100.00、登记 100.004」也能命中。财务报表金额最小单位是分，
    出现分位以下的非零尾数说明这个数不是报表原样，按**待核**处理。
    """
    if d is None:
        return False
    try:
        return d != d.quantize(_CENT)
    except (InvalidOperation, ValueError):
        return True


def _same_amount(a, b):
    """两个金额是否**逐位相等**。

    第二十轮裁决 3：上一版写的是「各自 quantize 到分再比」，那**不是**逐位相等——
    `100.004` 与 `100.00` 会被舍成同一个数。现在直接比 Decimal 数值：
    `1.0 == 1.00` 为真（数值相等），`100.004 == 100.00` 为假。
    """
    if a is None or b is None:
        return False
    try:
        return a == b
    except (InvalidOperation, ValueError):
        return False


def _num_of(txt):
    """兼容旧签名：返回 Decimal（旧调用方只做 `is not None` 判断）。"""
    return _dec(txt)


def amount_pattern(value):
    """把 684956197.48 变成能匹配 `684,956,197.48` / `684956197.48` 的正则。

    第十九轮 D3：原实现用 `"%f" % float(value)`（float 会掉精度，长金额直接错位），
    正则也没有数字边界——`1100.00` 里能匹配出 `100.00`。这里改用 Decimal 生成，
    并强制左右边界：左边不得紧邻数字/逗号/小数点，右边不得紧邻数字。
    """
    d = _dec(value)
    if d is None:
        return None
    s = format(d.normalize(), "f")
    neg = s.startswith("-")
    if neg:
        s = s[1:]
    if "." in s:
        ip, fp = s.split(".")
    else:
        ip, fp = s, ""
    grp = "{:,}".format(int(ip)) if ip.isdigit() else ip
    body = re.escape(grp) + (r"\." + re.escape(fp) if fp else "")
    loose = r",?".join(re.escape(ch) for ch in ip) + (r"\." + re.escape(fp) if fp else "")
    return re.compile(r"(?<![\d.,])(?:%s|%s)(?!\d)" % (body, loose))


def page_words(pdf_path, page):
    """返回原件该物理页的词坐标 [(x0, y0, x1, y1, text)]；不可用返回 []。"""
    try:
        n = int(str(page).strip())
    except (TypeError, ValueError):
        return []
    if n < 1 or not pdf_path:
        return []
    try:
        import pymupdf
        d = pymupdf.open(str(pdf_path))
        if n > d.page_count:
            d.close()
            return []
        ws = d[n - 1].get_text("words")
        d.close()
        return [(w[0], w[1], w[2], w[3], w[4]) for w in ws]
    except Exception:
        return []


def rows_of_words(words, y_tol=4.0):
    """按 y 聚成行：返回 [(y0, [(x0, x1, text), …])]，按 y 升序。"""
    rows = []
    for x0, y0, _x1, _y1, tx in sorted(words, key=lambda w: (w[1], w[0])):
        if rows and abs(y0 - rows[-1][0]) <= y_tol:
            rows[-1][1].append((x0, _x1, tx))
        else:
            rows.append([y0, [(x0, _x1, tx)]])
    return [(y, sorted(cells)) for y, cells in rows]


def column_of_amount_ex(words, value, label=None, x_tol=3.0, y_tol=4.0):
    """返回 (column_text, amount_text, status)。

    status ∈ {OK, NO_WORDS, NO_AMOUNT, AMBIGUOUS, NO_COLUMN}

    第十二轮 B 项两条修正：

    1. **必须绑定目标行**。同一页常有多笔相同金额（合计行与明细行、上年与本期），
       原实现按 y 取第一笔，会把「上年同期」列头配给本期金额。现在用 `label`
       （该行指标别名）限定「只有与指标名同一行的金额才是目标金额」；同页出现
       多笔且无法唯一绑定时返回 `AMBIGUOUS`，交回人工，不猜。
    2. **扫描页/无文本层** 返回 `NO_WORDS`，由调用方记为「待回读/OCR」，
       不能表述成「原件不可解」——技术取词失败与原件本身不可读是两件事。
    """
    if not words:
        return None, None, "NO_WORDS"
    target = _num_of(value)
    if target is None:
        return None, None, "NO_AMOUNT"
    rows = rows_of_words(words, y_tol)
    cands = []
    for ri, (_y, cells) in enumerate(rows):
        for x0, x1, tx in cells:
            v = _dec(tx)
            if v is not None and _same_amount(v, target):
                cands.append((ri, x0, x1, tx))
    if not cands:
        return None, None, "NO_AMOUNT"
    if label:
        want = [label] if isinstance(label, str) else [x for x in label if x]
        hit = []
        for ri, x0, x1, tx in cands:
            row_txt = "".join(c[2] for c in rows[ri][1])
            if any(w in row_txt for w in want):
                hit.append((ri, x0, x1, tx))
        if len(hit) > 1:
            return None, hit[0][3], "AMBIGUOUS"
        if hit:
            cands = hit
        elif len(cands) > 1:
            return None, cands[0][3], "AMBIGUOUS"
    elif len(cands) > 1:
        return None, cands[0][3], "AMBIGUOUS"
    ri, ax0, ax1, atxt = cands[0]
    cx = (ax0 + ax1) / 2.0
    above = []
    for rj in range(ri):
        for x0, x1, tx in rows[rj][1]:
            if _num_of(tx) is not None:
                continue
            if x1 < cx - x_tol or x0 > cx + x_tol:
                continue
            above.append((rj, x0, tx))
    if not above:
        return None, atxt, "NO_COLUMN"
    rj = max(a[0] for a in above)
    line = sorted([a for a in above if a[0] == rj], key=lambda a: a[1])
    return "".join(a[2] for a in line), atxt, "OK"


def column_of_amount(words, value, label=None, x_tol=3.0, y_tol=4.0):
    """兼容旧签名：只返回 (column_text, amount_text)。"""
    col, amt, _st = column_of_amount_ex(words, value, label=label,
                                        x_tol=x_tol, y_tol=y_tol)
    return col, amt


# 第十八轮接受后自查（F33）：`column_of_amount_ex()` 用「金额中心点 ±3pt」去套表头，
# 而财务报表的数字是**右对齐**、表头文字通常**居中**——两者根本不是同一个坐标系。
# 实测 87 条父输入缺口涉及的 174 个真实页面上，97 页因此取不到表头（NO_COLUMN），
# 另有 52 页取到的是页眉标题（`…年半年度报告`）。
# 同时 `if _num_of(tx) is not None: continue` 把表头里的**年份**当金额丢掉了
# （`2026` + `年半年度` → 只剩 `年半年度`），而 `_PERIOD_COL` 要求栏目含四位年份，
# 于是「2026年半年度」这种栏目**无论怎么正确登记都过不了**。
# 本函数改用报表排版的稳定特征定列：**同一列的数字右边界相同**。
_COL_PERIOD_HINT = re.compile(r"\d{4}|本期|上期|上年|本年|年末|期末|年初|期初|"
                              r"报告期|季度|半年|月")
# 页眉/标题行不是表头：它们同样含「2026」「年半年度」，但那是文档标题不是列名。
# 不加这条排除，取到的「栏目」会变成「…股份有限公司2026年半年度报告」。
_TITLE_ROW = re.compile(r"股份有限公司|年度报告|半年度报告|季度报告|单位[:：]|"
                        r"合并资产负债表|合并利润表|合并现金流量表|合并所有者权益变动表|"
                        r"合并股东权益变动表|母公司资产负债表|母公司利润表|"
                        r"母公司现金流量表|母公司所有者权益变动表|"
                        r"资产负债表|利润表|现金流量表|所有者权益变动表|股东权益变动表|"
                        r"财务报表附注|报表附注")
# 表头词与金额跨度的重叠判定：金额左侧留 8pt（表头通常比数字宽、且居中偏左），
# 右侧留 edge_tol。
# 第十九轮 D1：原值 20pt 比这更松，直接把左邻列的表头拉进来，再把两列列名拼成
# `2025年半年度2026年半年度` 后择一——等于**允许把邻列表头认成本列**。
# 现在先按「词并成单元格、单元格跨行成列」还原列结构，多列候选一律报歧义，
# 不再靠这个 padding 去凑覆盖率，故收回 8pt。
_BAND_PAD_LEFT = 8.0
_HDR_MERGE_GAP = 50.0          # 表头跨行合并的最大行距（pt）
_CELL_WORD_GAP = 6.0           # 同一表头单元格内相邻词的允许间隙（pt）
_CELL_X_TOL = 3.0              # 跨行表头视为同一列的横向容差（pt）
_EDGE_TOL = 4.0                # 数字右边界聚类容差（pt）


def _amount_bounds(rows, ri, ax0, ax1):
    """金额所在列的左右边界：与**同一行**左右相邻数字的中点（无相邻则 ±inf）。

    第二十一轮裁决 1 的根因：`_compatible()` 只能证明「两段语义互补」，不能证明
    「两段属于同一列」。短表头 `本报告期` 与右邻列 `（4-6月）` 语义互补、间隙
    只有 4pt，于是被并成一列——生产与旁证都把第一列认成 `本报告期（4-6月）`。

    裁决给的口径是「按**相邻列边界**约束」，并明确否掉「金额宽度 + N pt」这类
    未校准的阈值。所以这里只用报表最硬的一条几何事实：**同一行的数字是分列的**，
    取「本列数字与左右相邻数字的中点」作为边界。表头片段中心越界即判为邻列。

    只取金额**那一行**的数字，不取整页列格：整页列格会被脚注编号、页码切碎
    （实测 6 个真实列被切成 12 个簇），据此切区反而把同列断词判成两列。
    """
    lefts, rights = [], []
    for x0, x1, tx in rows[ri][1]:
        if _dec(tx) is None:
            continue
        if x1 <= ax0 - 0.5:
            lefts.append(x1)
        elif x0 >= ax1 + 0.5:
            rights.append(x0)
    left = (max(lefts) + ax0) / 2.0 if lefts else float("-inf")
    right = (min(rights) + ax1) / 2.0 if rights else float("inf")
    return left, right


def _header_cells(rows, hdr_rows, gap=_CELL_WORD_GAP, bounds=None):
    """把每个表头行的词按横向间隙并成**单元格**：[(y, x0, x1, text)]。

    表格里 `2026年` 与 `半年度` 常是两个词，中间只隔 1–2pt；而邻列的两个词
    之间隔着列间距（通常 >20pt）。先并单元格，才能把「同一列的断词」与
    「不同列的相邻列名」分开。

    只靠间隙不够：紧排的表里两列列名也可能只隔 3–5pt。因此再加一条**语义**
    保护——用 `_compatible()` 判「这两段是不是同一列的不同维度」。

    第二十轮裁决 1：上一版用的是「两侧 canon 都非空就不并」，**过严**——
    同一列横排的 `本报告期` 与 `（1-6月）` 两段 canon 都非空，被拆成两个单元格，
    于是一个列变成两个候选，判成 `AMBIGUOUS`（正确登记被拒）。
    正确的判据不是「完整不完整」，而是「**有没有互相冲突的维度**」：
    `本报告期`(本期,-,-) 与 `（1-6月）`(-,R0-1-6,累计) 互补，照并；
    `2025年半年度` 与 `2026年半年度` 区间冲突，不并。

    第二十一轮裁决 1：语义互补只是**必要**条件，不是充分条件。给了 `bounds`
    （`_amount_bounds` 的左右边界）时还要求两段**在同一侧**——`本报告期` 与
    右邻列的 `（4-6月）` 语义互补、间隙 4pt，但后者的中心已越出本列右边界。
    """
    out = []
    for rj in hdr_rows:
        y, cells = rows[rj]
        cur = None
        for x0, x1, tx in sorted(cells, key=lambda c: c[0]):
            joinable = (cur is not None and x0 - cur[1] <= gap
                        and _compatible(cur[2], tx))
            if joinable and bounds:
                left, right = bounds
                c1 = (cur[0] + cur[1]) / 2.0
                c2 = (x0 + x1) / 2.0
                if (c1 < left) != (c2 < left) or (c1 > right) != (c2 > right):
                    joinable = False
            if joinable:
                cur[1] = max(cur[1], x1)
                cur[2] += tx
            else:
                if cur is not None:
                    out.append((y, cur[0], cur[1], cur[2]))
                cur = [x0, x1, tx]
        if cur is not None:
            out.append((y, cur[0], cur[1], cur[2]))
    return out


def _chain_cells(cells, x_tol=_CELL_X_TOL):
    """把跨行的表头单元格按横向邻近并成「列」：[(x0, x1, text)]。

    **同一行的两个单元格永不合并**——它们本来就是两列。跨行合并只在横向
    重叠（或间隙 ≤ x_tol）时进行，即「`本报告期` 在上、`（1－6月）` 在下」。

    第二十轮裁决 1：上一版只按几何合并，于是「x[100,130]、y=70 的
    `2025年半年度`」与「y=80 的 `2026年半年度`」被并成一个候选，文本拼成
    `2025年半年度2026年半年度`，`_date_span` 取第一个匹配 → 返回 `OK`。
    现在合并前先过 `_compatible()`：区间/相对年/累计任一维度冲突就不并，
    于是它们成为两个候选，调用方据「期间列候选 >1」判 `AMBIGUOUS`。
    """
    groups = []
    for y, x0, x1, tx in sorted(cells, key=lambda c: (c[0], c[1])):
        placed = False
        for g in groups:
            if g["last_y"] == y:          # 同一行已有单元格，必是另一列
                continue
            if min(g["x1"], x1) - max(g["x0"], x0) < -x_tol:
                continue
            if not _compatible("".join(t for _y, _x, t in g["parts"]), tx):
                continue                  # 期间冲突：不是同一列
            g["x0"] = min(g["x0"], x0)
            g["x1"] = max(g["x1"], x1)
            g["parts"].append((y, x0, tx))
            g["last_y"] = y
            placed = True
            break
        if not placed:
            groups.append({"x0": x0, "x1": x1, "last_y": y,
                           "parts": [(y, x0, tx)]})
    out = []
    for g in groups:
        text = "".join(t for _y, _x, t in sorted(g["parts"], key=lambda p: (p[0], p[1])))
        out.append((g["x0"], g["x1"], text))
    return out


def _label_band(rows, ri, max_rows=2, max_dy=40.0):
    """指标名的取词带：金额行本身 + 紧邻的**无数字**行（上/下各至多 2 行）。

    财务报表里的指标名经常换行：`归属于上市公司股东的扣除非经常性` 在金额行，
    `损益的净利润` 在下一行；也有反过来的（金额行只有数字，指标名在上一行）。
    只取「金额行文本」会让这些行被判成「指标行未命中」，而回退接受又不允许
    （第十九轮 D3）。折中办法是把换行拼回来，但**只在紧邻行没有数字时**才拼——
    有数字的行是另一条记录，拼进来就是换行串行。
    """
    parts = ["".join(c[2] for c in rows[ri][1])]
    y0 = rows[ri][0]
    j = ri - 1
    while j >= 0 and ri - j <= max_rows:
        y, cells = rows[j]
        if y0 - y > max_dy or any(_dec(c[2]) is not None for c in cells):
            break
        parts.append("".join(c[2] for c in cells))
        j -= 1
    j = ri + 1
    while j < len(rows) and j - ri <= max_rows:
        y, cells = rows[j]
        if y - y0 > max_dy or any(_dec(c[2]) is not None for c in cells):
            break
        parts.append("".join(c[2] for c in cells))
        j += 1
    return "".join(parts)


def column_of_amount_aligned(words, value, label=None, y_tol=4.0, edge_tol=4.0):
    """兼容签名：只要 (column_text, amount_text, status)。"""
    col, amt, st, _w = column_of_amount_aligned_ex(
        words, value, label=label, y_tol=y_tol, edge_tol=edge_tol)
    return col, amt, st


def column_of_amount_aligned_ex(words, value, label=None, y_tol=4.0, edge_tol=4.0):
    """按「金额自身的横向跨度」取表头，再取该列文字。

    返回 (column_text, amount_text, status, amount_word)，status 取值与
    `column_of_amount_ex()` 一致，另加 `NO_HEADER_ROW`（找不到表头行）与
    `NO_LABEL_ROW`（指标行未命中）。

    `amount_word` 是命中金额的**那个词** `(x0, y0, x1, y1, text)`，供调用方按
    词坐标定位引文——第十九轮 D3 之后不再用正则去页面文本里捞金额：把空白去掉
    以后 `684,956,197.48` 会和后一个数粘成 `684,956,197.48585,346,923.80`，
    任何「数字边界」写法都会在这里误判。

    与 `column_of_amount_ex()` 的区别只有三点，都不放松判据：

    1. **定列用跨度重叠而不是中心点 ±3pt**。财务报表的数字右对齐、表头居中，
       两者不是同一坐标系：短数字（`0.00`）的中心会落到右邻列的表头上，长数字
       的中心会落到列外。实测 174 个真实页面里 97 页因此取不到表头。
    2. **表头行里的年份词保留**（F33）。原实现 `if _num_of(tx) is not None: continue`
       把 `2026` 当金额丢掉，`2026年半年度` 只剩 `年半年度`，而 `_PERIOD_COL`
       要求栏目含四位年份——正确登记也过不了。
    3. **不设垂直距离上限**，改为排除页眉/标题行。财务报表一页可跨几百 pt，
       设上限会把表头挡在门外（实测 64/174 页因此判 NO_HEADER_ROW）。

    指标行绑定、金额唯一性、扫描页处理全部沿用原口径。
    """
    if not words:
        return None, None, "NO_WORDS", None
    target = _num_of(value)
    if target is None:
        return None, None, "NO_AMOUNT", None
    # 第二十轮裁决 3：分位以下还有非零尾数（如 100.004）的「金额」不是报表原样，
    # 一律待核，不参与匹配——否则它会和页面上的 100.00 被舍成同一个数。
    if _has_subcent(target):
        return None, None, "AMOUNT_PRECISION_INVALID", None
    rows = rows_of_words(words, y_tol)
    cands = []
    for ri, (_y, cells) in enumerate(rows):
        for x0, x1, tx in cells:
            v = _dec(tx)
            if v is not None and _same_amount(v, target):
                cands.append((ri, x0, x1, tx))
    if not cands:
        return None, None, "NO_AMOUNT", None
    if label:
        want = [label] if isinstance(label, str) else [x for x in label if x]
        hit = []
        for ri, x0, x1, tx in cands:
            if any(w in _label_band(rows, ri) for w in want):
                hit.append((ri, x0, x1, tx))
        if not hit:
            # 第十九轮 D3：指标行未命中**不得回退接受**。原实现在「页面只有一个
            # 候选金额」时继续往下走，于是「目标营业收入 100.009、页面只有营业成本
            # 100.00」也能返回 OK——金额对不上、指标也不对，两处都靠回退蒙过。
            return None, cands[0][3], "NO_LABEL_ROW", cands[0]
        # 合计行与明细行同值（`一、营业总收入` 与 `其中：营业收入` 都是这个数）不算
        # 歧义：本函数要定的是**列**，两行只要指向同一列，列就是确定的。
        # 只有同一数值出现在**不同列**时才是真歧义。
        spans = {(round(x0), round(x1)) for _ri, x0, x1, _tx in hit}
        if len(spans) > 1:
            return None, hit[0][3], "AMBIGUOUS", hit[0]
        cands = hit
    elif len(cands) > 1:
        return None, cands[0][3], "AMBIGUOUS", cands[0]
    ri, ax0, ax1, atxt = cands[0]

    # 表头行：金额行上方、含期间词、至少两个单元格、且不是页眉/标题的最近一行。
    #
    # 第二十轮裁决 5：上一版遇到标题行**跳过继续往上找**，于是「上方一张有期间
    # 表头的表 + 下方另一张无表头表」时，会把上面那张表的表头套到下面那张表的
    # 金额上（两条路径都返回 OK）。现在标题行是**表格边界**：向上扫到标题行就停，
    # 表头必须落在「本表标题 → 金额行」之间；扫不过去就记 `TABLE_BOUNDARY_UNPROVEN`
    # 留待核，不再跨表借表头。
    hdr = None
    blocked_by_title = False
    for rj in range(ri - 1, -1, -1):
        cells = rows[rj][1]
        row_txt = "".join(c[2] for c in cells)
        if _TITLE_ROW.search(row_txt):
            blocked_by_title = True
            break
        if len(cells) < 2:
            continue
        if not any(_COL_PERIOD_HINT.search(c[2]) for c in cells):
            continue
        hdr = rj
        break
    if hdr is None:
        return (None, atxt,
                "TABLE_BOUNDARY_UNPROVEN" if blocked_by_title else "NO_HEADER_ROW",
                (ax0, ax1, atxt))

    # 表头可能跨两三行：`本报告期` 在一行、`（1－6月）` 在下一行，只取最近一行会
    # 拿到半截列名（`（1－6月）` 不含「本期」也无年份，`_PERIOD_COL` 判不过）。
    # 向上把相邻的表头行一起收进来，仍要求它们是表头形状（≥2 单元格、非标题）。
    hdr_rows = [hdr]
    for rj in range(hdr - 1, -1, -1):
        if rows[hdr_rows[-1]][0] - rows[rj][0] > _HDR_MERGE_GAP:
            break
        cells = rows[rj][1]
        if len(cells) < 2:
            break
        if _TITLE_ROW.search("".join(c[2] for c in cells)):
            break
        hdr_rows.append(rj)

    # 表头里取「横向跨度与金额跨度重叠」的**列**。这里**不跳过数字词**——年份
    # 正是表头的一部分（F33）；金额词本就不该出现在表头行。
    #
    # 第十九轮 D1：原实现把所有重叠的表头词**直接拼起来**再交给 `canon_column`
    # 择一。左邻列的表头一旦落进 20pt 的 padding 就会被拼进去，`2025年半年度`
    # 排在前面，归一后就成了「本列 = 2025年半年度」——邻列表头被认成本列。
    # 现在先还原列结构，再按「几个期间列候选」决定：≥2 个一律报歧义。
    lo, hi = ax0 - _BAND_PAD_LEFT, ax1 + edge_tol
    # 第二十一轮裁决 1：用「同一行左右相邻数字的中点」作列边界，
    # 表头片段中心越界即判为邻列，不得并进本列。
    bounds = _amount_bounds(rows, ri, ax0, ax1)
    chains = _chain_cells(_header_cells(rows, hdr_rows, bounds=bounds))
    hit = [c for c in chains if c[1] > lo and c[0] < hi]
    aw = (ax0, ax1, atxt)
    if not hit:
        return None, atxt, "NO_COLUMN", aw
    period_hit = [c for c in hit if _COL_PERIOD_HINT.search(_nz(c[2]))]
    if len(period_hit) > 1:
        # 多个期间列同时与金额跨度重叠：不允许拼接后择一，交回人工/换页。
        return None, atxt, "AMBIGUOUS", aw
    if period_hit:
        return period_hit[0][2], atxt, "OK", aw
    if len(hit) == 1:
        return hit[0][2], atxt, "OK", aw
    return None, atxt, "NO_COLUMN", aw


_RE_YEAR_ABS = re.compile(r"(?<!\d)(?:19|20)\d{2}(?!\d)")
# 相对年：**先判上年/上期，再判本期**。顺序不能反：`上年年初至报告期末` 里同时
# 含「年初」与「上年」，先判本期就会把它归成「本期」——正是第十九轮 D2 的第 4 例。
_RE_REL_PRIOR_YEAR = re.compile(r"上年|去年同期|上年度|上年年末")
_RE_REL_PRIOR = re.compile(r"上期|上一期")
_RE_REL_CUR = re.compile(r"本期|本报告期|报告期|本年|年初至|本季度|当月")
# 累计属性：从年初起算的口径。`1-6月`/`1-9月`/`1-12月`/上半年/年度 都是累计；
# `4-6月` 这种单季不是。这一项决定「本期累计」与「本季度」不能互认。
_RE_CUM = re.compile(r"年初至|累计|自年初|上半年|半年度|年度|全年|"
                     r"(?<!\d)1\s*[—–−－~～至\-]\s*(?:3|6|9|12)\s*月")


def _canon_parts(text):
    """把表头拆成三个**互相独立**的维度：(相对年, 区间, 累计属性)。

    第二十轮裁决 1/2 的根因就在这里：上一版只有一个字符串键，
    「`本报告期` + `（1-6月）`」与「`2025年半年度` + `2026年半年度`」在字符串层面
    长得一样（都是两段），但前者是**互补片段**（一段给相对年、一段给区间），
    后者是**两个完整但互相冲突的期间**。只有拆成维度才分得清。
    """
    t = _col_norm(text)
    if not t:
        return ("", "", "")
    span = _date_span(t)
    rel = ""
    if _RE_REL_PRIOR_YEAR.search(t):
        rel = "上年"
    elif _RE_REL_PRIOR.search(t):
        rel = "上期"
    elif _RE_REL_CUR.search(t):
        rel = "本期"
    cum = "累计" if _RE_CUM.search(t) else ""
    sp = ""
    if span:
        sp = "%s-%s" % (span[0], "-".join(str(x) for x in span[1:]))
    return (rel, sp, cum)


def _compatible(a, b):
    """两段表头能否并成**同一列**：任一维度两侧都写了、且写得不一样，就是冲突。

    - `本报告期`(本期,-,-) 与 `（1-6月）`(-,R0-1-6,累计)：无冲突维度 → 可并
    - `2025年半年度`(-,R-2025-1-6,累计) 与 `2026年半年度`(-,R-2026-1-6,累计)：
      区间两侧都写了且不同 → 冲突，不可并（第二十轮裁决 1 的复现用例）
    """
    pa, pb = _canon_parts(a), _canon_parts(b)
    for x, y in zip(pa, pb):
        if x and y and x != y:
            return False
    return True


def _no_extra_semantics(registered, actual):
    """**同侧**列身份：登记名不得断言实际列尚未证明的语义。

    第二十一轮裁决 2：`cols_equivalent()` 对「一侧有分量、另一侧为空」判等价，
    这条对「跨文档名称兼容」是对的（p1 写 `2026年半年度`、p2 写 `本报告期`
    本来就是两份文档的不同写法），但对**同一侧**的列身份是漏洞：

        目标金额实际表头 `本报告期`，邻列表头 `本报告期（1-6月）`；
        把登记列名写成邻列的长名称 → 取列得 `本报告期`、`cols_equivalent` 为真、
        `gap()` 返回 `None`、`check_c41` 零违例。

    长名称确实在同页连续出现，但属于邻列。所以同侧必须单向：登记的每个
    「已写」分量，实际列也必须写出来。反向（实际比登记更详细）允许——实际列
    带了额外写法不影响它是不是同一列。
    """
    pr, pa = _canon_parts(registered), _canon_parts(actual)
    for r, a in zip(pr, pa):
        if r and not a:
            return False
    return True


def canon_column(text):
    """把表头文字归一成**保留期间语义的结构化键**，供两侧用同一把尺子比较。

    第十九轮 D2 否掉了旧实现（取最长年份段/最长期间词）：它把
    `本期金额（2026年1-6月）` 与 `（2026年4-6月）` 都压成 `2026年`，
    把 `上年年初至报告期末` 压成 `年初至报告期末`——那不是写法归一，是把
    必须保留的**起止区间与相对年份语义删掉**，于是 6 个月与 3 个月可以互认。

    键的格式：`相对年|区间|累计`，例如

    - `本期金额（2026年1-6月）` → `本期|R-2026-1-6|累计`
    - `本期金额（2026年4-6月）` → `本期|R-2026-4-6|`
    - `本报告期（1－6月）`      → `本期|R0-1-6|累计`
    - `上年年初至报告期末`      → `上年||累计`
    - `本报告期`                → `本期||`

    三段全空说明这个表头**没有任何期间语义**，返回空串——不能当列名。
    """
    rel, sp, cum = _canon_parts(text)
    if not sp and not rel and not cum:
        return ""
    return "%s|%s|%s" % (rel, sp, cum)


# 表头里带期间语义的片段（用于把原文里的连续列名切出来）
_COL_TOKEN = re.compile(
    r"(?<!\d)(?:19|20)\d{2}\s*年(?:半年度|年度|第[一二三四1-4]季度|上半年|下半年)?"
    r"|(?<!\d)\d{1,2}\s*[—–−－~～至\-]\s*\d{1,2}\s*月"
    r"|（[^（）]{0,28}）|\([^()]{0,28}\)"
    r"|年初至本?报告期末|本报告期末|本报告期|上年同期金额|上年同期|上年年末|上年度末"
    r"|本期发生额|本期金额|本期数|本期|上期发生额|上期金额|上期数|上期"
    r"|报告期|期末数|期末|年末数|年末|年初数|年初|期初数|期初"
    r"|第[一二三四1-4]季度|上半年|下半年|半年度|年度|全年|累计"
    r"|[Qq][1-4]")


def clean_column_text(text):
    """把表头串收敛成**原文里连续的一段**，且不丢期间语义。

    取「第一个期间片段 → 最后一个期间片段」的连续区间，因此结果仍是原文的
    子串（登记表要能在引文/原件里定位），但不会把整行表头（含邻列、含「附注」）
    都吞进来。没有期间片段则返回空串。
    """
    t = _nz(text)
    if not t:
        return ""
    ms = list(_COL_TOKEN.finditer(t))
    if not ms:
        return ""
    return t[ms[0].start():ms[-1].end()]


def registrable_column(header, page_txt):
    """从表头串里取出**在正文中连续出现、且语义与整段一致**的列名。

    第十九轮 D2：登记值必须同时满足两条——①是原件里的连续片段（否则引文里
    找不到它）；②`canon_column` 与整段表头**完全相同**（否则等于用一个更短的、
    丢了区间或相对年份的名字去登记）。两条都满足才返回。
    """
    want = canon_column(header)
    if not want:
        return ""
    cands = [clean_column_text(header)]
    cands += [m.group(0) for m in _COL_TOKEN.finditer(_nz(header))]
    for c in cands:
        if c and c in (page_txt or "") and canon_column(c) == want:
            return c
    return ""


def gap(ent, expect, evidence_of, col_of=None):
    """返回该记录不足以证明兼容的原因；None 表示依据充分。

    `expect` = {"field": 指标ID, "p1": {...}, "p2": {...}}，每侧含
    doc / period / value / consolidation_scope / unit_scale / currency /
    adjust_version，取自 B 的实际父输入。
    `evidence_of(doc_id, page)` 返回该文档**该物理页**的原文（可为空串）。
    """
    if ent is None:
        return "NO_VERIFICATION_RECORD"
    if (ent.get("conclusion") or "").strip() != "COMPATIBLE":
        return "VERIFICATION_NOT_COMPATIBLE"
    if not _reviewer_ok(ent):
        return "VERIFICATION_WITHOUT_REVIEWER"
    if not _role_ok(ent):
        return "VERIFICATION_WITHOUT_ROLE"
    if not _date_ok(ent.get("reviewed_at")):
        return "VERIFICATION_WITHOUT_DATE"

    # 绑定实际父输入：文档 / 期间 / 终值 / 栏目 / 页码 / 版本
    aw_of = {}
    for side in ("p1", "p2"):
        exp = expect[side]
        if (ent.get("%s_doc" % side) or "").strip() != (exp.get("doc") or "").strip():
            return "PARENT_DOC_MISMATCH"
        if (ent.get("%s_period" % side) or "").strip() != (exp.get("period") or "").strip():
            return "PARENT_PERIOD_MISMATCH"
        if (ent.get("%s_value" % side) or "").strip() != (exp.get("value") or "").strip():
            return "PARENT_VALUE_MISMATCH"
        col = _nz(ent.get("%s_column" % side))
        if not col:
            return "PARENT_COLUMN_EMPTY"
        if len(col) < 2:
            return "PARENT_COLUMN_TOO_SHORT"
        # 第十九轮 D2：改用 `canon_column` 判「是不是期间列名」。它要求表头带
        # 年份/区间/相对年/累计属性之一，比 `_PERIOD_COL` 的裸子串更严——
        # `_PERIOD_COL` 里「月」一个字的线索就能过。
        if not canon_column(col):
            return "PARENT_COLUMN_NOT_PERIOD"
        if not _page_ok(ent.get("%s_page" % side)):
            return "PARENT_PAGE_INVALID"
        # 栏目必须真是该金额所在列（第十一轮 B 项）：只验「列头出现在引文里」
        # 挡不住「金额在本期列、登记写上期列」。`col_of` 由调用方按原件词坐标提供，
        # 返回 (column_text, status)。第十二轮再收紧：绑定目标行、期间类比对、
        # 扫描页记「待回读」而不是「原件不可解」。
        if col_of is not None:
            res = col_of((ent.get("%s_doc" % side) or "").strip(),
                         (ent.get("%s_page" % side) or "").strip(),
                         exp.get("value"),
                         METRIC_ALIASES.get((expect.get("field") or "").strip()))
            actual_col, st = res[0], res[1]
            aw_of[side] = res[2] if len(res) > 2 else None
            if st == "NO_WORDS":
                return "PARENT_COLUMN_NEEDS_REREAD"
            if st == "AMBIGUOUS":
                return "PARENT_COLUMN_AMBIGUOUS"
            if st == "AMOUNT_PRECISION_INVALID":
                return "PARENT_AMOUNT_PRECISION_INVALID"
            if st == "TABLE_BOUNDARY_UNPROVEN":
                return "PARENT_TABLE_BOUNDARY_UNPROVEN"
            if not actual_col:
                return "PARENT_COLUMN_UNRESOLVED"
            if not cols_equivalent(col, actual_col):
                return "PARENT_COLUMN_MISMATCH"
            # 第二十一轮裁决 2：等价只证明「可以互认」，不证明「就是这个列」。
            # 同侧登记不得凭空增加实际列没有的区间/年份/累计语义。
            if not _no_extra_semantics(col, actual_col):
                return "PARENT_COLUMN_SEMANTICS_UNPROVEN"
        ver = (ent.get("%s_adjust_version" % side) or "").strip()
        if ver not in ADJUST_VERSIONS:
            return "PARENT_ADJUST_VERSION_INVALID"
        actual = ver_class(exp.get("adjust_version"))
        if actual is None:
            return "PARENT_ACTUAL_VERSION_UNKNOWN"
        if ver != actual:
            return "PARENT_ADJUST_VERSION_MISMATCH"

    # 两父必须取自同一调整版本基础
    v1 = (ent.get("p1_adjust_version") or "").strip()
    v2 = (ent.get("p2_adjust_version") or "").strip()
    if v1 != v2:
        return "PARENT_ADJUST_VERSION_INCONSISTENT"
    if ver_class(expect["p1"].get("adjust_version")) != \
            ver_class(expect["p2"].get("adjust_version")):
        return "PARENT_ACTUAL_VERSION_INCONSISTENT"

    # 口径：非空 + 与实际父输入一致 + 有依据
    for f in ("consolidation_scope", "unit_scale", "currency"):
        v = (ent.get(f) or "").strip()
        if not v:
            return "SCOPE_FIELD_EMPTY"
        if v != (expect["p1"].get(f) or "").strip():
            return "SCOPE_MISMATCH_WITH_PARENT"
    if (ent.get("unit_scale") or "").strip() not in AMOUNT_UNITS:
        return "SCOPE_UNIT_NOT_AMOUNT"
    if len(_nz(ent.get("scope_basis"))) < _MIN_BASIS:
        return "SCOPE_BASIS_MISSING"

    names = METRIC_ALIASES.get((expect.get("field") or "").strip())
    # 引文：够长、在该页可定位、含目标指标 + 期间列头 + 父数 + 版本标记
    for side, fq, fd, fp in (("p1", "p1_quote", "p1_doc", "p1_page"),
                             ("p2", "p2_quote", "p2_doc", "p2_page")):
        q = _nz(ent.get(fq))
        if len(q) < _MIN_QUOTE:
            return "PARENT_QUOTE_TOO_SHORT"
        doc = (ent.get(fd) or "").strip()
        src = _nz(evidence_of(doc, (ent.get(fp) or "").strip()))
        if not src:
            return "PARENT_SOURCE_UNAVAILABLE"
        if q not in src:
            return "PARENT_QUOTE_NOT_LOCATED"
        if names and not any(n in q for n in names):
            return "PARENT_QUOTE_WITHOUT_TARGET_METRIC"
        if _nz(ent.get("%s_column" % side)) not in q:
            return "PARENT_COLUMN_NOT_IN_QUOTE"
        if (ent.get("%s_adjust_version" % side) or "").strip() == "RESTATED":
            if not any(mk in q for mk in _VER_MARK_RESTATED):
                return "PARENT_QUOTE_WITHOUT_VERSION_MARK"
        else:
            if any(mk in q for mk in _VER_MARK_FORBIDDEN_ORIGINAL):
                return "PARENT_QUOTE_VERSION_CONFLICT"
        if not _num_in_quote(ent.get(fq), expect[side].get("value"),
                             expect[side].get("unit_scale"),
                             exact=aw_of.get(side)):
            return "PARENT_QUOTE_WITHOUT_PARENT_VALUE"
    return None
