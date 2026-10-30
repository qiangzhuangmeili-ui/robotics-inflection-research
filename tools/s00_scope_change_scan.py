#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""扫描「同一控制下企业合并」导致的追溯调整。

背景：北投科技（600936）2025 年完成同一控制下企业合并，比较期数据全部追溯调整，
但年报「重大会计差错更正」勾选「不适用」——因为这不是差错更正。
按关键词判「无重述」会把这类公司误判为干净，而它们的同比其实不可比。

本脚本只做识别与清单，不改数据。判定：
- 出现「同一控制下企业合并」且上下文含本期/报告期内/完成等时点词 → 标记 SCOPE_CHANGE_TRACE
- 仅出现在会计政策章节模板 → 忽略
"""
from __future__ import annotations

import csv
import re
from collections import Counter
from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
VDIR = ROOT / "runs/issues/S02/remediation_20261029/restatement_verify"
OUT = VDIR / "scope_change_scan.csv"
INDEX = ROOT / "runs/collection/collection_index.csv"

KEY = "同一控制下企业合并"
NOW_WORDS = re.compile(r"本期|报告期内|本年|2025年|2026年|完成|取得|置换|收购")


def main() -> int:
    idx = {}
    with INDEX.open(encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            if r["document_id"]:
                idx[r["document_id"]] = r.get("local_file", "")
    # 只扫已判「否」的文档（判「是」的已经保护）
    rows = [r for r in csv.DictReader((VDIR / "results.csv").open(encoding="utf-8-sig", newline=""))
            if r["verdict"] == "否"]
    print("targets", len(rows), flush=True)

    out = []
    for k, r in enumerate(rows, 1):
        f = idx.get(r["document_id"], "")
        if not f or not Path(f).exists():
            continue
        try:
            reader = PdfReader(str(f))
        except Exception:
            continue
        hit = None
        for i in range(min(140, len(reader.pages))):
            try:
                t = (reader.pages[i].extract_text() or "").replace(" ", "")
            except Exception:
                continue
            if KEY not in t:
                continue
            j = t.find(KEY)
            seg = t[max(0, j - 60):j + 200]
            if NOW_WORDS.search(seg):
                hit = (i + 1, seg)
                break
        if hit:
            out.append({
                "security_id": r["security_id"], "stock_name": r["stock_name"],
                "period_label": r["period_label"], "document_id": r["document_id"],
                "local_file": f, "page": hit[0], "evidence": hit[1][:200],
            })
        if k % 100 == 0:
            print(" ", k, "/", len(rows), "hits", len(out), flush=True)

    with OUT.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["security_id", "stock_name", "period_label",
                                           "document_id", "local_file", "page", "evidence"],
                           lineterminator="\n")
        w.writeheader()
        w.writerows(out)
    print("done hits", len(out), "companies", len({x["security_id"] for x in out}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
