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
    """把 684956197.48 变成能匹配 `684,956,197.48` / `684956197.48` 的正则。"""
    s = ("%f" % float(value)).rstrip("0").rstrip(".")
    if "." in s:
        ip, fp = s.split(".")
    else:
        ip, fp = s, ""
    grp = ""
    for i, ch in enumerate(reversed(ip)):
        grp = ch + grp
        if i % 3 == 2 and i != len(ip) - 1:
            grp = "," + grp
    body = re.escape(grp) + (r"\." + re.escape(fp) if fp else "")
    loose = r",?".join(re.escape(x) for x in ip) + (r"\." + re.escape(fp) if fp else "")
    return re.compile("(?:%s|%s)" % (body, loose))


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
        col, _amt, st = pv.column_of_amount_aligned(words, value, label=aliases)
        if st != "OK":
            tried.append("%s:%s" % (pg, st))
            continue
        if not pv._PERIOD_COL.search(pv._nz(col)):
            tried.append("%s:COLUMN_NOT_PERIOD(%s)" % (pg, col))
            continue
        page_txt = re.sub(r"\s+", "", "".join(w[4] for w in words))
        col_reg = _registrable_column(col, page_txt)
        if not col_reg:
            tried.append("%s:COLUMN_NOT_CONTIGUOUS(%s)" % (pg, col))
            continue
        quote = _quote(page_txt, col_reg, value, aliases)
        if not quote:
            tried.append("%s:QUOTE_UNBUILDABLE(%s)" % (pg, col_reg))
            continue
        return {"status": "OK", "page": pg, "column_raw": col, "column": col_reg,
                "quote": quote, "page_txt_len": len(page_txt), "tried": tried}
    return {"status": "NOT_FOUND", "tried": tried[:6]}


def _registrable_column(col, page_txt):
    """从表头串里取出**在正文中连续出现**的规范列名。

    表头行里同一列的文字可能横跨多行（`本报告期` + `（1－6月）`），也可能因取词
    窗口把邻列年份带进来（`2026年半年度2025`）。登记值必须是原文里连续的一段，
    否则引文里根本找不到它；同时必须与 `_col_of` 归一到同一把尺子（`canon_column`）。
    """
    c = pv.canon_column(col)
    if c and c in page_txt:
        return c
    return ""


_VER_FORBID = ("调整后", "重述后", "更正后")


def _quote(page_txt, column, value, aliases):
    """构造「表头 + 指标行 + 数值」同段的引文；含版本禁用词则换一处或放弃。"""
    pat = _num_pattern(value)
    hits = [m for m in pat.finditer(page_txt)]
    if not hits:
        return ""
    col_pos = page_txt.find(column)
    for m in hits:
        a = min(col_pos, m.start()) if col_pos >= 0 else m.start()
        b = max(col_pos + len(column), m.end()) if col_pos >= 0 else m.end()
        seg = page_txt[a:b]
        if any(w in seg for w in _VER_FORBID):
            continue
        if aliases and not any(al in seg for al in aliases):
            # 指标名可能在数值之前更远处，向前扩一段（仍须是连续原文）
            seg2 = page_txt[max(0, a - 60):b]
            if any(al in seg2 for al in aliases) and not any(w in seg2 for w in _VER_FORBID):
                seg = seg2
            else:
                continue
        if len(pv._nz(seg)) < pv._MIN_QUOTE:
            continue
        return seg
    return ""


def targets(meta, hold, v10):
    out = []
    for r in meta:
        if r["security_id"] not in hold or r["scope_missing"] != "PARENT_COMPATIBILITY":
            continue
        sec, fld, pk = r["security_id"], r["field_id"], r["period_key"]
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
