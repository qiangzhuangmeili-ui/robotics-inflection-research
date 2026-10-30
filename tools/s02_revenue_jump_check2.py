#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""35 家营收异动核查（第二版）：只看「营业收入变动原因说明」，不看会计政策模板。"""
from __future__ import annotations
import csv, re
from collections import Counter
from pathlib import Path
import pymupdf

ROOT = Path(__file__).resolve().parents[1]
WL = ROOT / "runs/issues/S02/remediation_20261029/restatement_verify/revenue_jump_watchlist.csv"
OUT = ROOT / "runs/issues/S02/remediation_20261029/restatement_verify/revenue_jump_check.csv"
NORM = ROOT / "runs/issues/S02/remediation_20261029/collect_q3_2026/s00_v7.csv"
INDEX = ROOT / "runs/collection/collection_index.csv"

# 并表信号：动作词 + 主体
SCOPE = re.compile(r"(合并范围|并表|置入|收购|取得.{0,8}控制权|同一控制下.{0,6}合并|非同一控制下.{0,6}合并)")
# 排除：会计政策模板
TPL = ("会计处理", "会计政策", "分为同一控制", "采用权益结合法", "购买日对作为", "净利润为", "加：会计政策变更", "期初至合并日")


def main():
    idx = {}
    for r in csv.DictReader(open(INDEX, encoding="utf-8-sig", newline="")):
        if r["document_id"]:
            idx[r["document_id"]] = r.get("local_file", "")
    latest, doc = {}, {}
    for r in csv.DictReader(open(NORM, encoding="utf-8-sig", newline="")):
        if r["field_id"] in ("FIN.REV.YTD", "FIN.REV.SQ") and r["value_cny"] and r["document_id"]:
            pk = int(r["period_key"])
            if r["security_id"] not in latest or pk > latest[r["security_id"]]:
                latest[r["security_id"]] = pk
                doc[r["security_id"]] = r["document_id"]

    rows = list(csv.DictReader(open(WL, encoding="utf-8-sig", newline="")))
    out = []
    for k, w in enumerate(rows, 1):
        sid = w["security_id"]
        f = idx.get(doc.get(sid, ""), "")
        verdict, page, ev = "未见并表说明", "", ""
        if f and Path(f).exists():
            try:
                d = pymupdf.open(f)
                for i in range(min(60, len(d))):
                    t = re.sub(r"\s+", "", d[i].get_text() or "")
                    # 定位「营业收入」变动原因段落
                    for m in re.finditer(r"营业收入", t):
                        seg = t[max(0, m.start() - 20):m.start() + 220]
                        if not re.search(r"变动|增加|减少|增长|同比|原因", seg):
                            continue
                        if any(x in seg for x in TPL):
                            continue
                        ms = SCOPE.search(seg)
                        if ms:
                            verdict = "并表导致"
                            page, ev = i + 1, seg[:170]
                            break
                    if verdict == "并表导致":
                        break
                d.close()
            except Exception as e:
                verdict, ev = "解析失败", str(e)[:50]
        out.append({**w, "verdict": verdict, "page": page, "evidence": ev})
        if k % 10 == 0:
            print(" ", k, "/", len(rows), Counter(x["verdict"] for x in out), flush=True)

    fields = list(rows[0].keys()) + ["verdict", "page", "evidence"]
    with OUT.open("w", encoding="utf-8-sig", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        wr.writeheader()
        for x in out:
            wr.writerow({k: x.get(k, "") for k in fields})
    print("done", Counter(x["verdict"] for x in out), flush=True)


if __name__ == "__main__":
    main()
