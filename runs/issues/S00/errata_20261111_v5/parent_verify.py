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
        names = METRIC_ALIASES.get(key[1]) or METRIC_ALIASES.get(
            key[1][:-3] + ".YTD" if key[1].endswith(".SQ") else key[1])
        if names and not any(n in q for n in names):
            continue
        if not any(tok in q for tok in _period_tokens(key[2])):
            continue
        ok.add(dim)
    return ok


def _col_norm(s):
    return re.sub(r"[\s*_]", "", s or "")


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


def column_of_amount(words, value, x_tol=3.0, y_tol=4.0):
    """按词坐标找该金额**所在列**的期间列头（第十一轮 B 项）。

    只按文字先后顺序取「金额前最后一个期间词」会把「上年同期」错认成
    本期金额的栏目——列头在文字流里往往排在行标签之前，与金额的物理列无关。
    这里改为：金额词 → 取其 x 中心 → 在上方找**同一 x 区间**、**非数值**、
    最近的一行词，拼成列头。
    返回 (column_text, amount_text)；找不到返回 (None, amount_text|None)。
    """
    target = _num_of(value)
    if target is None:
        return None, None
    cands = []
    for x0, y0, x1, y1, tx in words:
        v = _num_of(tx)
        if v is not None and abs(v - target) < 0.01:
            cands.append((x0, y0, x1, y1, tx))
    if not cands:
        return None, None
    cands.sort(key=lambda c: (c[1], c[0]))
    ax0, ay0, ax1, ay1, atxt = cands[0]
    cx = (ax0 + ax1) / 2.0
    above = []
    for x0, y0, x1, y1, tx in words:
        if y1 > ay0 - 0.5:
            continue
        if _num_of(tx) is not None:
            continue
        if x1 < cx - x_tol or x0 > cx + x_tol:
            continue
        above.append((y0, x0, tx))
    if not above:
        return None, atxt
    above.sort(key=lambda a: -a[0])
    top = above[0][0]
    line = sorted([a for a in above if abs(a[0] - top) <= y_tol], key=lambda a: a[1])
    return "".join(a[2] for a in line), atxt


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
        # 挡不住「金额在本期列、登记写上期列」。`col_of` 由调用方按原件词坐标提供。
        if col_of is not None:
            actual_col = col_of((ent.get("%s_doc" % side) or "").strip(),
                                (ent.get("%s_page" % side) or "").strip(),
                                exp.get("value"))
            if not actual_col:
                return "PARENT_COLUMN_UNRESOLVED"
            if _col_norm(col) not in _col_norm(actual_col):
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
