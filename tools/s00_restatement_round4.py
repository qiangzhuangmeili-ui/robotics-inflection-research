#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""重述复核第四轮：只看「（二）重大会计差错更正」那一项，不被「（一）会计政策变更」干扰。

发现的问题：年报「重要事项」章节有两项紧邻：
    （一）公司对会计政策、会计估计变更原因及影响的分析说明   √适用 □不适用
    （二）公司对重大会计差错更正原因及影响的分析说明         □适用 √不适用
多数公司（一）是「√适用」——因为每年都有新准则解释（如标准仓单交易、准则解释第19号），
这不是差错更正。前几轮脚本把（一）的勾选当成了（二），导致大量「待核」。

本轮严格定位（二），并把（一）的勾选单独记录，供人工区分。
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
OUT = VDIR / "round4_results.csv"
INDEX = ROOT / "runs/collection/collection_index.csv"

RE2 = re.compile(r"[（(]二[)）]?\s*公司对重大会计差错更正原因及影响的分析说明(.{0,80})")
RE1 = re.compile(r"[（(]一[)）]?\s*公司对会计政策、会计估计变更原因及影响的分析说明(.{0,80})")


def judge(path: Path):
    try:
        reader = PdfReader(str(path))
        n = len(reader.pages)
    except Exception as e:
        return "待核", "", "", f"PDF_PARSE_ERROR:{str(e)[:40]}", "ERROR"
    for i in range(min(180, n)):
        try:
            t = re.sub(r"\s+", "", reader.pages[i].extract_text() or "")
        except Exception:
            continue
        m2 = RE2.search(t)
        if not m2:
            continue
        seg2 = m2.group(1)
        m1 = RE1.search(t)
        seg1 = m1.group(1)[:40] if m1 else ""
        if re.search(r"[√☑✓✔]\s*不适用", seg2):
            return "否", i + 1, seg2[:60], "ERRATA_NA", seg1
        if re.search(r"[√☑✔✓]\s*适用", seg2) and "不适用" not in seg2:
            return "是", i + 1, seg2[:60], "ERRATA_YES", seg1
        return "待核", i + 1, seg2[:60], "ERRATA_UNCLEAR", seg1
    return "未找到判据", "", "", "NO_SECTION", ""


def main() -> int:
    idx = {}
    with INDEX.open(encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            if r["document_id"]:
                idx[r["document_id"]] = r.get("local_file", "")
    rows = [r for r in csv.DictReader(SRC.open(encoding="utf-8-sig", newline=""))
            if r["verdict"] in ("待核", "未找到判据")]
    print("targets", len(rows), flush=True)

    out = []
    for k, r in enumerate(rows, 1):
        did = r["document_id"]
        f = idx.get(did, "")
        if not f or not Path(f).exists():
            out.append((did, "未找到判据", "", "", "NO_FILE", ""))
            continue
        try:
            v, page, ev, m, ev1 = judge(ROOT / f)
        except Exception as e:
            v, page, ev, m, ev1 = "待核", "", "", f"ERROR:{str(e)[:40]}", ""
        out.append((did, v, page, ev, m, ev1))
        if k % 20 == 0:
            print(" ", k, "/", len(rows), Counter(x[1] for x in out), flush=True)

    with OUT.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["document_id", "verdict", "page", "evidence_errata", "method", "evidence_policy_change"])
        for x in out:
            w.writerow(x)
    print("done", Counter(x[1] for x in out), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
