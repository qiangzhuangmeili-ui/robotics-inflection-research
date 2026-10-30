#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""重述复核第五轮：改用 pymupdf 提取文本（对勾选符号的还原优于 pypdf）。"""
from __future__ import annotations
import csv, re
from collections import Counter
from pathlib import Path
import pymupdf

ROOT = Path(__file__).resolve().parents[1]
VDIR = ROOT / "runs/issues/S02/remediation_20261029/restatement_verify"
SRC = VDIR / "results_final2.csv"
OUT = VDIR / "round5_results.csv"
INDEX = ROOT / "runs/collection/collection_index.csv"
RE2 = re.compile(r"重大会计差错更正原因及影响.{0,8}?分析说明(.{0,80})")
RE1 = re.compile(r"会计政策、会计估计变更原因及影响.{0,8}?分析说明(.{0,60})")

def judge(path):
    try:
        doc = pymupdf.open(str(path))
    except Exception as e:
        return "待核", "", "", f"OPEN_ERROR:{str(e)[:40]}", ""
    for i in range(min(180, len(doc))):
        try:
            t = re.sub(r"\s+", "", doc[i].get_text())
        except Exception:
            continue
        m2 = RE2.search(t)
        if not m2:
            continue
        seg2 = m2.group(1)
        m1 = RE1.search(t)
        seg1 = m1.group(1)[:40] if m1 else ""
        doc.close()
        if re.search(r"[√☑✓✔]\s*不适用", seg2):
            return "否", i + 1, seg2[:60], "ERRATA_NA", seg1
        if re.search(r"[√☑✔✓]\s*适用", seg2) and "不适用" not in seg2:
            return "是", i + 1, seg2[:60], "ERRATA_YES", seg1
        return "待核", i + 1, seg2[:60], "ERRATA_UNCLEAR", seg1
    doc.close()
    return "未找到判据", "", "", "NO_SECTION", ""

def main():
    idx = {}
    for r in csv.DictReader(open(INDEX, encoding="utf-8-sig", newline="")):
        if r["document_id"]:
            idx[r["document_id"]] = r.get("local_file", "")
    rows = [r for r in csv.DictReader(SRC.open(encoding="utf-8-sig", newline=""))
            if r["verdict"] in ("待核", "未找到判据")]
    print("targets", len(rows), flush=True)
    out = []
    for k, r in enumerate(rows, 1):
        f = idx.get(r["document_id"], "")
        if not f or not Path(f).exists():
            out.append((r["document_id"], "未找到判据", "", "", "NO_FILE", "")); continue
        try:
            v, page, ev, m, ev1 = judge(ROOT / f)
        except Exception as e:
            v, page, ev, m, ev1 = "待核", "", "", f"ERR:{str(e)[:40]}", ""
        out.append((r["document_id"], v, page, ev, m, ev1))
        if k % 20 == 0:
            print(" ", k, "/", len(rows), Counter(x[1] for x in out), flush=True)
    with OUT.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["document_id", "verdict", "page", "evidence_errata", "method", "evidence_policy_change"])
        for x in out: w.writerow(x)
    print("done", Counter(x[1] for x in out), flush=True)

if __name__ == "__main__":
    main()
