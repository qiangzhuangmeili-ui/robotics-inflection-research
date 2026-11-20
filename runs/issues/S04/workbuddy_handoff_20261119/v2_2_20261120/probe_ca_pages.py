# -*- coding: utf-8 -*-
"""回读三处合同资产原页，输出「合同资产」行及其右侧数字的 x 坐标，
并与「期末余额 / 期初余额」表头的 x 坐标比对，用于判定金额落在哪一列。

只读原页，不写任何数据文件；结论另存 JSON 供登记表引用。
用法: python probe_ca_pages.py
"""
import json
import os
import sys

import pymupdf

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", "..", ".."))
ORIG = os.path.join(ROOT, "sources", "collection", "originals")

TARGETS = [
    # (标签, 股票目录, 期目录, 文档, 物理页列表)
    ("卓翼科技 2026H1", "002369", "h1_2026", "DOC-CED1573B6156692D", [38, 39, 40]),
    ("银宝山新 2026H1", "002786", "h1_2026", "DOC-F1CA96F4BB5E007E", [37, 38, 39]),
    ("胜蓝股份 2025H1", "300843", "h1_2025", "DOC-8CCAA8F91C8043AF", [46, 47, 48, 49, 50]),
    ("胜蓝股份 2026H1", "300843", "h1_2026", "DOC-8F60D69D8B150CD1", [44, 45, 46]),
]

KEYS = ("合同资产", "期末余额", "期初余额", "期末数", "期初数",
        "母公司资产负债表", "合并资产负债表")


def line_groups(words, tol=3.0):
    """按 y 中心聚成行。"""
    ws = sorted(words, key=lambda w: (round(w[1], 1), w[0]))
    out, cur, cy = [], [], None
    for x0, y0, x1, y1, txt, *_ in ws:
        yc = (y0 + y1) / 2.0
        if cy is None or abs(yc - cy) <= tol:
            cur.append((x0, x1, txt))
            cy = yc if cy is None else (cy + yc) / 2.0
        else:
            out.append((cy, cur))
            cur, cy = [(x0, x1, txt)], yc
    if cur:
        out.append((cy, cur))
    return out


def probe():
    report = []
    for label, code, per, doc, pages in TARGETS:
        path = os.path.join(ORIG, code, per, doc + ".pdf")
        if not os.path.exists(path):
            report.append({"label": label, "error": "PDF 不存在: " + path})
            continue
        pdf = pymupdf.open(path)
        entry = {"label": label, "document_id": doc, "pdf_pages": pdf.page_count,
                 "pages": []}
        for pno in pages:
            if pno - 1 >= pdf.page_count:
                continue
            page = pdf[pno - 1]
            words = page.get_text("words")
            lines = line_groups(words)
            keep = []
            for yc, toks in lines:
                text = "".join(t[2] for t in toks)
                if not any(k in text for k in KEYS):
                    continue
                keep.append({"y": round(yc, 1),
                             "tokens": [{"x0": round(t[0], 1), "x1": round(t[1], 1),
                                         "t": t[2]} for t in toks]})
            entry["pages"].append({"physical_page": pno, "lines": keep})
        pdf.close()
        report.append(entry)
    with open(os.path.join(HERE, "probe_ca_pages.json"), "w",
              encoding="utf-8", newline="\n") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    for e in report:
        print("=" * 78)
        print(e["label"], e.get("document_id"), "总页", e.get("pdf_pages"))
        for p in e.get("pages", []):
            print("  -- 物理第 %d 页 --" % p["physical_page"])
            for ln in p["lines"]:
                seg = " | ".join("%s@%.0f" % (t["t"], t["x0"]) for t in ln["tokens"])
                print("     y=%.0f  %s" % (ln["y"], seg))


if __name__ == "__main__":
    probe()
