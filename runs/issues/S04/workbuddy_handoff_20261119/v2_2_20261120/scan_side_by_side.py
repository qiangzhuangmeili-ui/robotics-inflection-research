# -*- coding: utf-8 -*-
"""在 278 家受限候选实际消费的合同资产原页中，定位「资产与负债左右并排」版式。

判据：同一物理页上「期末余额/期末数」表头出现 >= 2 次，说明资产列与负债列
各自带一组期末/期初表头。用于回归第四例（并排版式不得取错列）。

只读，输出 scan_side_by_side.json。
"""
import csv
import json
import os
import sys
from collections import defaultdict

import pymupdf

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", "..", ".."))
REPO = os.path.join(ROOT, "runs", "issues", "S04", "workbuddy_handoff_20261119")
ORIG = os.path.join(ROOT, "sources", "collection", "originals")

HEAD_KEYS = ("期末余额", "期末数")


def load_pages():
    """从 V2.1 适用性表取 278 家的合同资产页（t 与 t-1y）。"""
    want = defaultdict(set)   # doc -> set(page)
    meta = []
    p = os.path.join(REPO, "v2_1_20261120", "s05_applicability_v21.csv")
    with open(p, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            if row["metric_id"] != "M12":
                continue
            for suf in ("t", "t1y"):
                doc = row.get("ca_doc_" + suf, "")
                pg = row.get("ca_page_" + suf, "")
                if doc and pg:
                    try:
                        want[doc].add(int(float(pg)))
                    except ValueError:
                        pass
            meta.append((row["security_id"], row["stock_name"], row["anchor_period"]))
    return want, meta


def doc_dir(doc):
    """document_id -> 本地 PDF 路径（用 collection_index）。"""
    p = os.path.join(ROOT, "runs", "collection", "collection_index.csv")
    with open(p, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            if row["document_id"] == doc:
                return os.path.join(ROOT, row["local_file"]) if row["local_file"] else ""
    return ""


def scan():
    want, _ = load_pages()
    hits, missing, scanned = [], [], 0
    for doc, pages in sorted(want.items()):
        path = doc_dir(doc)
        if not path or not os.path.exists(path):
            missing.append(doc)
            continue
        try:
            pdf = pymupdf.open(path)
        except Exception as e:      # noqa: BLE001
            missing.append("%s(%s)" % (doc, e))
            continue
        for pno in sorted(pages):
            if pno - 1 >= pdf.page_count:
                continue
            page = pdf[pno - 1]
            words = page.get_text("words")
            heads = [w for w in words if any(k in w[4] for k in HEAD_KEYS)]
            scanned += 1
            if len(heads) >= 2:
                xs = sorted(round(w[0]) for w in heads)
                ca = [w for w in words if w[4].startswith("合同资产")]
                hits.append({
                    "document_id": doc,
                    "physical_page": pno,
                    "header_count": len(heads),
                    "header_x": xs,
                    "ca_row_present": bool(ca),
                    "ca_x": [round(w[0]) for w in ca],
                })
        pdf.close()
    out = {"scanned_pages": scanned, "docs": len(want),
           "side_by_side_pages": len(hits), "hits": hits,
           "missing_docs": missing}
    with open(os.path.join(HERE, "scan_side_by_side.json"), "w",
              encoding="utf-8", newline="\n") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("扫描页数", scanned, "文档", len(want), "并排页", len(hits),
          "缺原件", len(missing))
    for h in hits[:20]:
        print("  ", h["document_id"], "p%d" % h["physical_page"],
              "表头x", h["header_x"], "合同资产行", h["ca_row_present"])


if __name__ == "__main__":
    scan()
