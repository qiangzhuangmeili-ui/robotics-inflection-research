#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""第 4 步批次 B：父输入核证的**证据扫描**（只读，不做放行判定）。

Codex 第十八轮裁决：下一批优先父输入，`parent_verifications.csv` 的 27 列可沿用，
但「引文须实际支持指定行、期间表头及数值」「单纯填满列不能替代核证；不满足时保留待核」。

本脚本只做一件事：对「HOLD 中仅缺 PARENT_COMPATIBILITY」的每一条待核行，
把它两个实际累计父数在原件里的**可定位证据**找出来，写 `step4_parent_scan.csv`：
登记页、表头、行标签、引文、以及取不到时的确切原因。是否登记为 COMPATIBLE
由 `step4_apply_parents.py` 决定，且只在两侧证据都完整时写。

两个关键口径（对应 F33 与「续页无表头」）：

1. **表头取词按金额跨度重叠**，不是中心点。数字右对齐、表头居中，中心点对齐会
   把短数字配到右邻列的表头上（实测 97/174 页取不到表头）。
2. **登记页 = 证据所在页**。s00 的 `source_page` 常常是报表续页，该页没有表头，
   无法证明「这个数是本期列」；此时在同一文档内找「该数值与期间表头同页出现」的
   那一页（多为「主要会计数据」表）。两处数值必须逐位相等——不相等就不登记。
"""
import csv
import gzip
import io
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import evidence_scope as es          # noqa: E402
import l2_core as core               # noqa: E402
import parent_verify as pv           # noqa: E402

ROOT = core.ROOT
OUT = HERE
ORIG = Path("D:/StockResearchLab/IndustryInflectionLab/robotics_data/collection/originals")
P_V10 = ROOT / "runs/issues/S02/hangcha_restated_20261101/s00_v10/s00_v10.csv.gz"
SCAN_PAGES = 40                      # 摘要表都在前 40 页；超过这个范围不再盲搜
_NUM_IN_TEXT = None


def load_v10():
    idx = {}
    with gzip.open(P_V10, "rt", encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            idx[(r["security_id"], r["field_id"], r["period_key"])] = r
    return idx


def _pdf(sec, doc):
    return next((p for p in (ORIG / sec.split(":")[-1]).rglob(doc + ".pdf")), None)


def _num_pattern(value):
    """兼容旧签名：金额正则统一由 `parent_verify.amount_pattern()` 生成。

    第十九轮 D3：原实现 `("%f" % float(value))` 会掉精度，且正则没有数字边界
    （`1100.00` 里能抠出 `100.00`）。现在只有一处实现，生产与自检共用。
    """
    return pv.amount_pattern(value)


def find_evidence(sec, doc, value, field, prefer_page):
    """在文档内找「数值 + 期间表头」同页出现的位置。返回 dict。"""
    pdf = _pdf(sec, doc)
    if pdf is None:
        return {"status": "NO_ORIGINAL"}
    aliases = pv.METRIC_ALIASES.get(field)
    try:
        import pymupdf
        n = pymupdf.open(str(pdf)).page_count
    except Exception:
        return {"status": "OPEN_FAIL"}
    order = [str(prefer_page)] + [str(p) for p in range(1, min(n, SCAN_PAGES) + 1)
                                  if str(p) != str(prefer_page)]
    tried = []
    for pg in order:
        words = pv.page_words(pdf, pg)
        col, _amt, st, aw = pv.column_of_amount_aligned_ex(
            words, value, label=aliases)
        if st != "OK":
            tried.append("%s:%s" % (pg, st))
            continue
        page_txt, offs = _page_text(words)
        col_reg = pv.registrable_column(col, page_txt)
        if not col_reg:
            tried.append("%s:COLUMN_NOT_CONTIGUOUS(%s)" % (pg, col))
            continue
        quote = _quote(page_txt, offs, aw, col_reg, aliases)
        if not quote:
            tried.append("%s:QUOTE_UNBUILDABLE(%s)" % (pg, col_reg))
            continue
        return {"status": "OK", "page": pg, "column_raw": col, "column": col_reg,
                "quote": quote, "page_txt_len": len(page_txt), "tried": tried}
    return {"status": "NOT_FOUND", "tried": tried[:6]}


_VER_FORBID = ("调整后", "重述后", "更正后")


def _page_text(words):
    """把词流拼成「无空白正文」并记下每个词的字符区间。

    第十九轮 D3：不再用正则去正文里捞金额。去掉空白以后
    `684,956,197.48` 会和后一个数粘成 `684,956,197.48585,346,923.80`，
    任何「数字边界」写法在这里都会误判（要么漏，要么把两个数当一个）。
    改成**按词坐标定位**：命中金额是哪一个词，由取列函数直接给出。
    """
    parts, offs, pos = [], [], 0
    for x0, _y0, x1, _y1, tx in words:
        t = re.sub(r"\s+", "", tx)
        offs.append((pos, pos + len(t), (round(x0, 2), round(x1, 2), tx)))
        parts.append(t)
        pos += len(t)
    return "".join(parts), offs


def _quote(page_txt, offs, amt_word, column, aliases):
    """构造「表头 + 指标行 + 数值」同段的引文；含版本禁用词则放弃。

    金额位置来自词坐标（`amt_word` = 取列函数返回的 `(x0, x1, text)`），
    指标名必须命中，**不得回退**（第十九轮 D3）。
    """
    if not amt_word:
        return ""
    key = (round(amt_word[0], 2), round(amt_word[1], 2), amt_word[2])
    idx = next((i for i, (_a, _b, k) in enumerate(offs) if k == key), None)
    if idx is None:
        return ""
    a, b = offs[idx][0], offs[idx][1]
    col_pos = page_txt.find(column)
    if col_pos >= 0:
        a = min(a, col_pos)
        b = max(b, col_pos + len(column))
    seg = page_txt[a:b]
    if any(w in seg for w in _VER_FORBID):
        return ""
    if aliases and not any(al in seg for al in aliases):
        # 指标名可能在数值之前更远处，向前扩一段（仍须是连续原文）
        seg2 = page_txt[max(0, a - 60):b]
        if not (any(al in seg2 for al in aliases)
                and not any(w in seg2 for w in _VER_FORBID)):
            return ""
        seg = seg2
    if len(pv._nz(seg)) < pv._MIN_QUOTE:
        return ""
    return seg


def targets(meta, hold, v10):
    """待核行 = 「HOLD 中仅缺父输入」的 + **上一轮已登记、本轮须重验**的。

    第十九轮裁决：「修复后重验全部 70 条」。只扫「还缺父输入」的行会让已登记的
    70 条自动消失——那不是重验，是把待验对象换掉了。所以把登记表里的键并进来，
    用新方法重推一遍；推不出来的由 `step4_apply_parents.py` 撤下。
    """
    keep = set()
    p_pv = OUT / "parent_verifications.csv"
    if p_pv.exists():
        for r in csv.DictReader(io.open(p_pv, encoding="utf-8-sig", newline="")):
            keep.add((r["security_id"], r["field_id"], r["period_key"]))
    out = []
    seen = set()
    for r in meta:
        sec, fld, pk = r["security_id"], r["field_id"], r["period_key"]
        if (sec, fld, pk) in seen:
            # meta_diff 里同一键可能出现在多行（同一差异的多个来源），去重：
            # 登记表以 (security_id, field_id, period_key) 为唯一键，重复写会让
            # 「登记行数」与「实际生效条数」不一致。
            continue
        in_scope = (sec in hold and r["scope_missing"] == "PARENT_COMPATIBILITY")
        if not in_scope and (sec, fld, pk) not in keep:
            continue
        seen.add((sec, fld, pk))
        ytd = fld[:-3] + ".YTD"
        p2pk = core.prev_quarter(pk)
        b1, b2 = v10.get((sec, ytd, pk)), v10.get((sec, ytd, p2pk))
        if not b1 or not b2:
            continue
        out.append({"security_id": sec, "stock_name": r["stock_name"],
                    "field_id": fld, "period_key": pk, "ytd_field": ytd,
                    "p1_period": pk, "p2_period": p2pk,
                    "p1_doc": b1["document_id"], "p1_page": b1["source_page"],
                    "p1_value": b1["value_cny"], "p1_unit": b1["unit_scale"],
                    "p1_scope": b1["consolidation_scope"], "p1_cur": b1["currency"],
                    "p1_ver": b1["version_used"],
                    "p2_doc": b2["document_id"], "p2_page": b2["source_page"],
                    "p2_value": b2["value_cny"], "p2_unit": b2["unit_scale"],
                    "p2_scope": b2["consolidation_scope"], "p2_cur": b2["currency"],
                    "p2_ver": b2["version_used"]})
    return out


def main():
    meta = list(csv.DictReader(io.open(OUT / "meta_diff.csv", encoding="utf-8-sig", newline="")))
    hold = {r["security_id"] for r in
            csv.DictReader(io.open(OUT / "l2_dependency_check.csv",
                                   encoding="utf-8-sig", newline=""))
            if r["verdict"] == "HOLD_PENDING_ERRATA"}
    v10 = load_v10()
    tg = targets(meta, hold, v10)
    rows = []
    for t in tg:
        r1 = find_evidence(t["security_id"], t["p1_doc"], t["p1_value"],
                           t["ytd_field"], t["p1_page"])
        r2 = find_evidence(t["security_id"], t["p2_doc"], t["p2_value"],
                           t["ytd_field"], t["p2_page"])
        ok = r1["status"] == "OK" and r2["status"] == "OK"
        rows.append(dict(t,
                         p1_evidence_page=r1.get("page", ""),
                         p1_column=r1.get("column", ""),
                         p1_quote=r1.get("quote", ""),
                         p1_status=r1["status"],
                         p1_note=";".join(r1.get("tried", [])[:3]),
                         p2_evidence_page=r2.get("page", ""),
                         p2_column=r2.get("column", ""),
                         p2_quote=r2.get("quote", ""),
                         p2_status=r2["status"],
                         p2_note=";".join(r2.get("tried", [])[:3]),
                         verdict="EVIDENCE_OK" if ok else "BLOCKED"))
    cols = list(rows[0].keys())
    with io.open(OUT / "step4_parent_scan.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    from collections import Counter
    print("targets", len(rows))
    print("verdict", Counter(r["verdict"] for r in rows).most_common())
    print("p1", Counter(r["p1_status"] for r in rows).most_common())
    print("p2", Counter(r["p2_status"] for r in rows).most_common())


if __name__ == "__main__":
    main()
