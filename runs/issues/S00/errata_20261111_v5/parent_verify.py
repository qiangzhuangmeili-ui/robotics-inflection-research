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
_AMOUNT_TOKEN = re.compile(r"-?\d[\d,]*(?:\.\d+)?")
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


def _num_in_quote(quote, value, unit_scale="1"):
    """引文里是否出现该父数本身（按 unit_scale 折算）。

    第九轮 C 项：只比父终值字段，登记可以把引文换成无关文档的通用标题片段。
    这里要求引文里真的写出这个数，`DOC-…` 之类的标题片段无法满足。
    第十轮 B1：`unit_scale` 必须是实际倍数（1/1000/10000），键名不得再写成
    `unit`——否则 187,875.40 万元永远对不上 1,878,754,000 元。
    """
    try:
        target = float(value)
    except (TypeError, ValueError):
        return False
    try:
        mult = float(unit_scale or "1")
    except (TypeError, ValueError):
        mult = 1.0
    if mult <= 0:
        mult = 1.0
    for m in _AMOUNT_TOKEN.finditer(quote or ""):
        raw = m.group(0).replace(",", "")
        try:
            v = float(raw)
        except ValueError:
            continue
        if abs(v * mult - target) <= max(0.05, abs(target) * 1e-9):
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
# 顺序有意义：先匹配更具体的（累计/年初至期末），再匹配宽的「本期」。
_COL_CLASSES = [
    ("CURRENT_YTD", r"年初至报告期末|年初至本报告期末|本年累计|本期累计|本年数|"
                    r"本报告期末累计|累计数"),
    ("PRIOR_YEAR_YTD", r"上年年初至报告期末|上年同期累计|上年累计"),
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
_RE_SPAN_RANGE = re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*[—\-~～至]\s*(\d{1,2})\s*月")
_RE_SPAN_RANGE_NY = re.compile(r"(?<!\d)(\d{1,2})\s*[—\-~～至]\s*(\d{1,2})\s*月")
_RE_SPAN_HALF = re.compile(r"(?:(\d{4})\s*年)?\s*(?:上半年|半年度|H1)")
_RE_SPAN_HALF2 = re.compile(r"(?:(\d{4})\s*年)?\s*(?:下半年|H2)")
_RE_SPAN_QUARTER = re.compile(r"(?:(\d{4})\s*年)?\s*(?:第)?\s*[Qq]([1-4])")
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

    判定顺序（第十四轮 B 项把「区间」提到「语义类」之前）：
    ① 两侧都写明了期间区间 → **区间必须相同**（`本期金额（1—6月）` 与
       `本报告期金额（4—6月）` 不是同一列，语义类相同也不认）；
    ② 否则两侧都能归到期间类 → **必须同类**（跨类一律不认，不再退回子串，
       否则「上年同期」与「上期」会靠共同后缀蒙过）；
    ③ 只有至少一侧归不到类时，才退回归一化子串比对。
    """
    sa, sb = _date_span(registered), _date_span(actual)
    if sa and sb:
        return sa == sb
    if sa or sb:
        # 一侧解出了区间，另一侧写着期间线索却解不出：**无法确认，按不等价处理**。
        # 不能把「我解析不了」翻译成「可以按语义类证明等价」——那是把未知当已知。
        other = actual if sa else registered
        if _RE_PERIOD_HINT.search(_col_norm(other)):
            return False
    a, b = _col_class(registered), _col_class(actual)
    if a and b:
        return a == b
    na, nb = _col_norm(registered), _col_norm(actual)
    return bool(na) and bool(nb) and (na in nb or nb in na)


def _num_of(txt):
    """把「57,296,869.60」这类词解析成数值；不是数值返回 None。"""
    s = re.sub(r"[,\s元]", "", txt or "")
    if not s or not re.match(r"^-?\d+(\.\d+)?$", s):
        return None
    try:
        return float(s)
    except ValueError:
        return None


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
            v = _num_of(tx)
            if v is not None and abs(v - target) < 0.01:
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
_TITLE_ROW = re.compile(r"股份有限公司|年度报告|半年度报告|季度报告|单位[:：]")
# 表头词与金额跨度的重叠判定：金额左侧留 20pt（表头通常比数字宽、且居中偏左），
# 右侧留 edge_tol。放宽左侧会把左邻列的列名拉进来（如「上年同期」），
# 收窄则会漏掉居中表头的左半部分。
_BAND_PAD_LEFT = 20.0
_HDR_MERGE_GAP = 50.0          # 表头跨行合并的最大行距（pt）


def column_of_amount_aligned(words, value, label=None, y_tol=4.0, edge_tol=4.0):
    """按「金额自身的横向跨度」取表头，再取该列文字。

    返回 (column_text, amount_text, status)，status 取值与
    `column_of_amount_ex()` 一致，另加 `NO_HEADER_ROW`（找不到表头行）。

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
        return None, None, "NO_WORDS"
    target = _num_of(value)
    if target is None:
        return None, None, "NO_AMOUNT"
    rows = rows_of_words(words, y_tol)
    cands = []
    for ri, (_y, cells) in enumerate(rows):
        for x0, x1, tx in cells:
            v = _num_of(tx)
            if v is not None and abs(v - target) < 0.01:
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

    # 表头行：金额行上方、含期间词、至少两个单元格、且不是页眉/标题的最近一行
    hdr = None
    for rj in range(ri - 1, -1, -1):
        cells = rows[rj][1]
        if len(cells) < 2:
            continue
        row_txt = "".join(c[2] for c in cells)
        if _TITLE_ROW.search(row_txt):
            continue
        if not any(_COL_PERIOD_HINT.search(c[2]) for c in cells):
            continue
        hdr = rj
        break
    if hdr is None:
        return None, atxt, "NO_HEADER_ROW"

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

    # 表头行里取「横向跨度与金额跨度重叠」的词。这里**不跳过数字词**——年份正是
    # 表头的一部分（F33）；金额词本就不该出现在表头行。
    lo, hi = ax0 - _BAND_PAD_LEFT, ax1 + edge_tol
    picked = []
    for rj in reversed(hdr_rows):          # 从上到下
        for x0, x1, tx in rows[rj][1]:
            if x1 > lo and x0 < hi:
                picked.append((rows[rj][0], x0, tx))
    if not picked:
        return None, atxt, "NO_COLUMN"
    col = "".join(t for _y, _x, t in sorted(picked, key=lambda p: (p[0], p[1])))
    return col, atxt, "OK"


_YEAR_PERIOD = re.compile(r"(?:19|20)\d{2}年(?:半年度|年度|第一季度|第三季度|上半年|下半年)?")
_PERIOD_WORDS = ("年初至报告期末", "本报告期末", "上年同期金额", "上年同期",
                 "本报告期", "本期发生额", "本期金额", "本期数", "本期",
                 "上期发生额", "上期金额", "上期数", "上期", "报告期",
                 "上年年末", "上年度末", "年初数", "期末数", "年末数",
                 "期初数", "年初", "期末", "年末")


def canon_column(text):
    """把表头文字归一成**一个列名**，供登记侧与实际侧用同一把尺子比较。

    表头行里同一列的文字可能横跨多行（`本报告期` + `（1－6月）`），也可能因取词
    窗口把邻列年份带进来（`2026年半年度2025`）。归一规则：
    ① 有「年份+期间」的，取最长的那一段（`2026年半年度`）；
    ② 否则取出现的最长期间词（`本报告期` / `本期数` / `年初至报告期末` …）；
    ③ 都没有则返回空串——**没有期间语义的表头不能当列名**。
    """
    t = _nz(text)
    if not t:
        return ""
    ys = _YEAR_PERIOD.findall(t)
    if ys:
        return max(ys, key=len)
    hits = [w for w in _PERIOD_WORDS if w in t]
    if hits:
        return max(hits, key=len)
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
        if not _PERIOD_COL.search(col):
            return "PARENT_COLUMN_NOT_PERIOD"
        if not _page_ok(ent.get("%s_page" % side)):
            return "PARENT_PAGE_INVALID"
        # 栏目必须真是该金额所在列（第十一轮 B 项）：只验「列头出现在引文里」
        # 挡不住「金额在本期列、登记写上期列」。`col_of` 由调用方按原件词坐标提供，
        # 返回 (column_text, status)。第十二轮再收紧：绑定目标行、期间类比对、
        # 扫描页记「待回读」而不是「原件不可解」。
        if col_of is not None:
            actual_col, st = col_of((ent.get("%s_doc" % side) or "").strip(),
                                    (ent.get("%s_page" % side) or "").strip(),
                                    exp.get("value"),
                                    METRIC_ALIASES.get((expect.get("field") or "").strip()))
            if st == "NO_WORDS":
                return "PARENT_COLUMN_NEEDS_REREAD"
            if st == "AMBIGUOUS":
                return "PARENT_COLUMN_AMBIGUOUS"
            if not actual_col:
                return "PARENT_COLUMN_UNRESOLVED"
            if not cols_equivalent(col, actual_col):
                return "PARENT_COLUMN_MISMATCH"
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
                             expect[side].get("unit_scale")):
            return "PARENT_QUOTE_WITHOUT_PARENT_VALUE"
    return None
