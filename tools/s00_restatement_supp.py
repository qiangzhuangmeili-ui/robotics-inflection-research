#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""重述复核补充判据：对「未找到判据」的文档再找一次。

第一轮只认附注「追溯重述法」勾选；年报若无该章节会漏判。
本轮全文（末 120 页）找「前期差错更正 / 追溯重述」，排除两类假阳性：
  1) 合并所有者权益变动表的固定行「加：会计政策变更 / 前期差错更正 / 其他」
  2) 章节标题「会计政策变更、会计估计变更和前期差错更正」

单进程 + 逐份异常保护（多进程在个别大 PDF 上会 BrokenProcessPool）。
"""
from __future__ import annotations

import csv
import re
from collections import Counter
from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
VDIR = ROOT / "runs/issues/S02/remediation_20261029/restatement_verify"
SRC = VDIR / "results.csv"
OUT = VDIR / "supp_results.csv"
INDEX = ROOT / "runs/collection/collection_index.csv"

NEG = re.compile(r"无前期差错更正|不存在前期差错更正|未发生前期差错更正|无重大前期差错更正"
                 r"|无会计差错更正|本期无|本期未发生|不适用")
POS = re.compile(r"调增|调减|重述后|更正后|已更正|进行了更正|追溯重述了|追溯重述法适用")


def judge(doc_id: str, path: Path):
    try:
        reader = PdfReader(str(path))
        n = len(reader.pages)
    except Exception as e:
        return "待核", "", f"PDF_PARSE_ERROR:{str(e)[:50]}", "ERROR"
    for i in range(max(n - 120, 0), n):
        try:
            t = (reader.pages[i].extract_text() or "").replace(" ", "")
        except Exception:
            continue
        for kw in ("前期差错更正", "追溯重述"):
            if kw not in t:
                continue
            j = t.find(kw)
            while j >= 0:
                before = t[max(0, j - 10):j]
                after = t[j + len(kw):j + len(kw) + 140]
                j = t.find(kw, j + 1)
                if before.endswith("加：") or before.endswith("加:"):
                    continue                       # 权益变动表行项目
                if after[:1] in ("和", "及", "、", "与"):
                    continue                       # 章节标题
                if NEG.search(after):
                    return "否", i + 1, (t[max(0, j - 60):j + 100])[:150], "SUPP_NEG"
                if POS.search(after):
                    return "是", i + 1, (t[max(0, j - 60):j + 100])[:150], "SUPP_POS"
    return "未找到判据", "", "", "SUPP_NONE"


def main() -> int:
    idx = {}
    with INDEX.open(encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            if r["document_id"]:
                idx[r["document_id"]] = r.get("local_file", "")
    rows = [r for r in csv.DictReader(SRC.open(encoding="utf-8-sig", newline=""))
            if r["verdict"] == "未找到判据"]
    print("targets", len(rows), flush=True)

    out = []
    for k, r in enumerate(rows, 1):
        did = r["document_id"]
        f = idx.get(did, "")
        if not f or not Path(f).exists():
            out.append((did, "未找到判据", "", "NO_FILE", "LOCAL_FILE_MISSING"))
            continue
        try:
            v, page, ev, m = judge(did, ROOT / f)
        except Exception as e:
            v, page, ev, m = "待核", "", f"ERROR:{str(e)[:50]}", "ERROR"
        out.append((did, v, page, m, ev))
        if k % 40 == 0:
            print(" ", k, "/", len(rows), Counter(x[1] for x in out), flush=True)

    with OUT.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["document_id", "verdict", "page", "method", "evidence"])
        for x in out:
            w.writerow(x)
    print("done", Counter(x[1] for x in out), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
