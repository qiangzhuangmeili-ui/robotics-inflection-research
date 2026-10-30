#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""核查 35 家营收同比异常公司：增长是并表带来的还是内生的。"""
from __future__ import annotations
import csv, re
from collections import Counter, defaultdict
from pathlib import Path
import pymupdf

ROOT = Path(__file__).resolve().parents[1]
WL = ROOT / "runs/issues/S02/remediation_20261029/restatement_verify/revenue_jump_watchlist.csv"
OUT = ROOT / "runs/issues/S02/remediation_20261029/restatement_verify/revenue_jump_check.csv"
NORM = ROOT / "runs/issues/S02/remediation_20261029/collect_q3_2026/s00_v7.csv"
INDEX = ROOT / "runs/collection/collection_index.csv"

PATTERNS = [
    ("SCOPE_SAME", re.compile(r"同一控制下(?:的)?企业合并")),
    ("SCOPE_DIFF", re.compile(r"非同一控制下(?:的)?企业合并")),
    ("SCOPE_CHANGE", re.compile(r"合并范围(?:发生)?变更")),
    ("PURCHASE_DATE", re.compile(r"购买日")),
]
TEMPLATE = ("会计处理方法", "非经常性损益", "净利润为：0元", "净利润为:0元", "期初至合并日的当期净损益")


def main():
    idx = {}
    for r in csv.DictReader(open(INDEX, encoding="utf-8-sig", newline="")):
        if r["document_id"]:
            idx[r["document_id"]] = r.get("local_file", "")
    # 每家最新期文档
    latest = {}
    doc = {}
    for r in csv.DictReader(open(NORM, encoding="utf-8-sig", newline="")):
        if r["field_id"] in ("FIN.REV.YTD", "FIN.REV.SQ", "FIN.NPDEDT.YTD") and r["value_cny"] and r["document_id"]:
            pk = int(r["period_key"])
            if r["security_id"] not in latest or pk > latest[r["security_id"]]:
                latest[r["security_id"]] = pk
                doc[r["security_id"]] = r["document_id"]

    rows = list(csv.DictReader(open(WL, encoding="utf-8-sig", newline="")))
    out = []
    for k, w in enumerate(rows, 1):
        sid = w["security_id"]
        did = doc.get(sid, "")
        f = idx.get(did, "")
        verdict, page, ev = "无法判断", "", ""
        if f and Path(f).exists():
            try:
                d = pymupdf.open(f)
                hits = defaultdict(list)
                for i in range(min(120, len(d))):
                    t = re.sub(r"\s+", "", d[i].get_text() or "")
                    for tag, pat in PATTERNS:
                        for m in pat.finditer(t):
                            seg = t[max(0, m.start() - 40):m.start() + 120]
                            if any(x in seg for x in TEMPLATE):
                                continue
                            hits[tag].append((i + 1, seg))
                            break
                    if len(hits.get("SCOPE_SAME", [])) + len(hits.get("SCOPE_DIFF", [])) >= 2:
                        break
                d.close()
                if hits.get("SCOPE_SAME") or hits.get("SCOPE_DIFF"):
                    pg, seg = (hits.get("SCOPE_SAME") or hits.get("SCOPE_DIFF"))[0]
                    verdict = "疑似并表"
                    page, ev = pg, seg[:150]
                elif hits.get("SCOPE_CHANGE"):
                    pg, seg = hits["SCOPE_CHANGE"][0]
                    verdict = "有范围变更表述"
                    page, ev = pg, seg[:150]
                else:
                    verdict = "未见并表"
            except Exception as e:
                verdict, ev = "解析失败", str(e)[:60]
        out.append({**w, "document_id": did, "verdict": verdict, "page": page, "evidence": ev})
        if k % 10 == 0:
            print(" ", k, "/", len(rows), Counter(x["verdict"] for x in out), flush=True)

    fields = list(rows[0].keys()) + ["document_id", "verdict", "page", "evidence"]
    with OUT.open("w", encoding="utf-8-sig", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        wr.writeheader()
        for x in out:
            wr.writerow({k: x.get(k, "") for k in fields})
    print("done", Counter(x["verdict"] for x in out), flush=True)


if __name__ == "__main__":
    main()
