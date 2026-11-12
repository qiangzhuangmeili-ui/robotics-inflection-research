#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""第 4 步批次 B：父输入登记的**独立列身份旁证**（只读）。

Codex 第十九轮裁决：「是否还需独立旁证？**需要**。至少以不调用该取列函数的
单元格边界解析或原页目视核读，证明『指标行 × 完整期间列 × 金额』的交点。」

本脚本**不调用** `parent_verify.column_of_amount_aligned()`，改用另一套几何：
**数字右边界格 + 中点分列**。思路与取列函数完全不同：

- 取列函数：从金额的**横向跨度**出发，去找与之重叠的表头词（自下而上）。
- 本脚本：先把整页所有**数字的右边界**聚类成列格（财务报表数字右对齐，同一列
  的右边界几乎相同），再用相邻右边界的中点切出每一列的可视范围，最后按**表头词
  的中心**落进哪一列来判断列身份（自左而右）。

两条路都通过，才认为「这个金额确实位于这个期间列」。任一路判不出来或两者
不一致，该条退出登记表、保留待核。

输出 `step4_column_witness.csv`：逐条、逐侧的独立判定结果与两侧列名。
"""
import csv
import io
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import parent_verify as pv          # noqa: E402

OUT = HERE
ORIG = Path("D:/StockResearchLab/IndustryInflectionLab/robotics_data/collection/originals")
Y_TOL = 4.0
EDGE_TOL = 1.5          # 右边界聚类容差（pt）
_HEADER_HINT = pv._COL_PERIOD_HINT
_TITLE = pv._TITLE_ROW


def _pdf(sec, doc):
    return next((p for p in (ORIG / sec.split(":")[-1]).rglob(doc + ".pdf")), None)


def _dec(txt):
    s = (txt or "").strip().replace(",", "")
    if not s or not s.replace(".", "").replace("-", "").isdigit():
        return None
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def _rows(words, tol=Y_TOL):
    """独立实现的行聚类：[(y, [(x0, x1, text)])]，按 y 升序。"""
    rows = []
    for x0, y0, x1, _y1, tx in sorted(words, key=lambda w: (round(w[1], 1), w[0])):
        if rows and abs(y0 - rows[-1][0]) <= tol:
            rows[-1][1].append((x0, x1, tx))
        else:
            rows.append([y0, [(x0, x1, tx)]])
    return [(y, sorted(c)) for y, c in rows]


def _column_grid(rows, skip_ys):
    """整页数字的右边界格：[(右边界, 该列最左数字的左边界, 词数)]。

    财务报表的数字右对齐，同一列的数字右边界几乎相同。右边界相同的数字里
    最靠左的那个，就是这一列数字实际占到的左边界——列的可视范围由此确定，
    不需要假设列宽。
    """
    items = []
    for y, cells in rows:
        if any(abs(y - s) <= Y_TOL for s in skip_ys):
            continue
        for x0, x1, tx in cells:
            if _dec(tx) is not None:
                items.append((x1, x0))
    items.sort()
    grid = []
    for x1, x0 in items:
        if grid and x1 - grid[-1][0] <= EDGE_TOL:
            grid[-1][0] = max(grid[-1][0], x1)
            grid[-1][1] = min(grid[-1][1], x0)
            grid[-1][2] += 1
        else:
            grid.append([x1, x0, 1])
    return grid


def _column_span(grid, x1):
    """金额右边界落在哪一列，以及该列的可视横向范围。"""
    if not grid:
        return None, None
    idx = min(range(len(grid)), key=lambda i: abs(grid[i][0] - x1))
    if abs(grid[idx][0] - x1) > EDGE_TOL * 2:
        return None, None
    left = grid[idx][1] - 12.0
    right = grid[idx][0] + 6.0
    return idx, (left, right)


def _band(rows, ri, max_rows=2, max_dy=40.0):
    """指标名取词带：金额行 + 紧邻的无数字行（指标名换行时拼回来）。"""
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


def _header_rows(rows, amt_ri):
    """金额行上方最近的一行「≥2 格 + 含期间词 + 非页眉标题」，可再向上并一行。"""
    hdr = None
    for rj in range(amt_ri - 1, -1, -1):
        _y, cells = rows[rj]
        if len(cells) < 2:
            continue
        txt = "".join(c[2] for c in cells)
        if _TITLE.search(txt):
            continue
        if not any(_HEADER_HINT.search(c[2]) for c in cells):
            continue
        hdr = rj
        break
    if hdr is None:
        return []
    out = [hdr]
    for rj in range(hdr - 1, -1, -1):
        if rows[out[-1]][0] - rows[rj][0] > 50.0:
            break
        _y, cells = rows[rj]
        if len(cells) < 2 or _TITLE.search("".join(c[2] for c in cells)):
            break
        out.append(rj)
        break
    return out


def witness(pdf, page, value, aliases):
    """返回 dict(status, column, amount, why)。不调用 column_of_amount_aligned。"""
    words = pv.page_words(pdf, page)
    if not words:
        return {"status": "NO_WORDS"}
    rows = _rows(words)
    target = pv._dec(value)
    if target is None:
        return {"status": "NO_AMOUNT"}
    # 1) 找「指标名 + 金额」同一行（指标名允许换行，拼紧邻无数字行）
    hits = []
    for ri, (_y, cells) in enumerate(rows):
        if aliases and not any(a in _band(rows, ri) for a in aliases):
            continue
        for x0, x1, tx in cells:
            v = _dec(tx)
            if v is not None and pv._same_amount(v, target):
                hits.append((ri, x0, x1, tx))
    if not hits:
        return {"status": "NO_AMOUNT_ROW"}
    # 合计行/明细行同值不算歧义：要定的是列，只要落在同一列就唯一
    spans = {(round(h[2], 1)) for h in hits}
    if len(spans) > 1:
        return {"status": "AMBIGUOUS", "why": "same_row_cols=%d" % len(spans)}
    ri, ax0, ax1, atxt = hits[0]
    # 2) 独立列格：整页数字右边界
    hdr = _header_rows(rows, ri)
    if not hdr:
        return {"status": "NO_HEADER_ROW"}
    edges = _column_grid(rows, [rows[j][0] for j in hdr])
    idx, span = _column_span(edges, ax1)
    if span is None:
        return {"status": "NO_COLUMN_GRID", "why": "grid=%d" % len(edges)}
    # 3) 该列的表头文字：先把表头行的词按间隙并成单元格，再按单元格**中心**
    #    落进列范围（`2026` + `年第一季度` 是一个单元格的两个词，只取到后半个
    #    会丢掉年份，`cols_equivalent` 会判成不同列）。
    parts = []
    for j in hdr:
        cells = sorted(rows[j][1], key=lambda c: c[0])
        cur = None
        merged = []
        for x0, x1, tx in cells:
            if cur is not None and x0 - cur[1] <= 6.0:
                cur[1] = max(cur[1], x1)
                cur[2] += tx
            else:
                if cur is not None:
                    merged.append(cur)
                cur = [x0, x1, tx]
        if cur is not None:
            merged.append(cur)
        for x0, x1, tx in merged:
            c = (x0 + x1) / 2.0
            if span[0] < c <= span[1]:
                parts.append((rows[j][0], x0, tx))
    if not parts:
        return {"status": "NO_COLUMN_TEXT", "why": "span=%.1f-%.1f" % span}
    col = "".join(t for _y, _x, t in sorted(parts, key=lambda p: (p[0], p[1])))
    if not pv.canon_column(col):
        return {"status": "COLUMN_NOT_PERIOD", "column": col}
    return {"status": "OK", "column": col, "amount": atxt,
            "grid_col": idx, "grid_n": len(edges)}


def main():
    rows = list(csv.DictReader(io.open(OUT / "step4_parent_scan.csv",
                                      encoding="utf-8-sig", newline="")))
    out = []
    for r in rows:
        if r["verdict"] != "EVIDENCE_OK":
            continue
        rec = {"security_id": r["security_id"], "field_id": r["field_id"],
               "period_key": r["period_key"]}
        ok = True
        for side in ("p1", "p2"):
            doc = r[side + "_doc"]
            pg = r[side + "_evidence_page"]
            reg = r[side + "_column"]
            pdf = _pdf(r["security_id"], doc)
            if pdf is None:
                w = {"status": "NO_ORIGINAL"}
            else:
                w = witness(pdf, pg, r[side + "_value"],
                            pv.METRIC_ALIASES.get(r["ytd_field"]))
            wc = w.get("column") or ""
            same = bool(wc) and pv.cols_equivalent(reg, wc)
            rec["%s_registered" % side] = reg
            rec["%s_witness" % side] = wc
            rec["%s_witness_status" % side] = w["status"] + (
                "" if w["status"] != "OK" else (":AGREE" if same else ":DISAGREE"))
            if not same:
                ok = False
        rec["verdict"] = "WITNESS_OK" if ok else "WITNESS_FAIL"
        out.append(rec)
    cols = list(out[0].keys()) if out else []
    with io.open(OUT / "step4_column_witness.csv", "w",
                 encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(out)
    from collections import Counter
    print("rows", len(out))
    print("verdict", Counter(r["verdict"] for r in out).most_common())
    print("p1", Counter(r["p1_witness_status"] for r in out).most_common())
    print("p2", Counter(r["p2_witness_status"] for r in out).most_common())


if __name__ == "__main__":
    main()
