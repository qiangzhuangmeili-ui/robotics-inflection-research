#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""重述复核第三轮：用「重要事项」章节的正式勾选项判定。

前两轮漏判的原因：判据找错了位置。
- 附注「十八、其他重要事项」只写一句「详见"重要事项"的…分析说明」，没有勾选；
- 真正的勾选在年报「重要事项」章节（通常在 40–110 页）：
    五、公司对会计政策、会计估计变更或重大会计差错更正原因和影响的分析说明
    （二）公司对重大会计差错更正原因及影响的分析说明   □适用 √不适用

本轮只处理前两轮判为「未找到判据」的文档，扫前 180 页。
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
OUT = VDIR / "round3_results.csv"
INDEX = ROOT / "runs/collection/collection_index.csv"

HEAD = "重大会计差错更正"


def judge(path: Path):
    try:
        reader = PdfReader(str(path))
        n = len(reader.pages)
    except Exception as e:
        return "待核", "", f"PDF_PARSE_ERROR:{str(e)[:50]}", "ERROR"
    for i in range(min(180, n)):
        try:
            t = (reader.pages[i].extract_text() or "").replace(" ", "")
        except Exception:
            continue
        if HEAD not in t or "原因" not in t:
            continue
        # 优先定位「（二）公司对重大会计差错更正原因及影响的分析说明」
        m = re.search(r"[（(]二[)）]?公司对重大会计差错更正原因", t)
        j = m.start() if m else t.find(HEAD)
        seg = t[j:j + 220]
        if re.search(r"[√☑✓✔]\s*不适用", seg):
            return "否", i + 1, seg[:150], "IMPORTANT_MATTER_NA"
        if re.search(r"[√☑✓✔]\s*适用", seg) and "不适用" not in seg:
            return "是", i + 1, seg[:150], "IMPORTANT_MATTER_YES"
        return "待核", i + 1, seg[:150], "IMPORTANT_MATTER_UNCLEAR"
    return "未找到判据", "", "", "NO_IMPORTANT_MATTER"


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
            v, page, ev, m = judge(ROOT / f)
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
