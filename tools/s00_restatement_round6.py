#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""重述复核第六轮：用附注「未分配利润」的调整明细判定（会计准则强制披露，最可靠）。

原文格式（每份年报都有）：
    调整期初未分配利润明细：
    1、由于《企业会计准则》及其相关新规定进行追溯调整，影响期初未分配利润 X 元。
    2、由于会计政策变更，影响期初未分配利润 X 元。
    3、由于重大会计差错更正，影响期初未分配利润 X 元。
    4、由于同一控制导致的合并范围变更，影响期初未分配利润 X 元。

X=0 → 未发生；X≠0 → 发生且金额明确。这比「重要事项」章节的勾选更稳（不受格式差异影响），
同时能识别北投科技那类「同一控制下企业合并」的追溯调整。
"""
from __future__ import annotations
import csv, re
from collections import Counter
from pathlib import Path
import pymupdf

ROOT = Path(__file__).resolve().parents[1]
VDIR = ROOT / "runs/issues/S02/remediation_20261029/restatement_verify"
SRC = VDIR / "results_final2.csv"
OUT = VDIR / "round6_results.csv"
INDEX = ROOT / "runs/collection/collection_index.csv"

NUM = r"([-−]?[\d,]+(?:\.\d+)?)"
RE_ERRATA = re.compile(r"由于重大会计差错更正[，,]?影响期初未分配利润" + NUM + "元")
RE_SCOPE = re.compile(r"由于同一控制导致的合并范围变更[，,]?影响期初未分配利润" + NUM + "元")


def amt(s: str) -> float:
    return float(s.replace(",", "").replace("−", "-"))


def judge(path):
    try:
        doc = pymupdf.open(str(path))
    except Exception as e:
        return "待核", "", "", f"OPEN_ERROR:{str(e)[:40]}", ""
    for i in range(len(doc)):
        try:
            t = re.sub(r"\s+", "", doc[i].get_text())
        except Exception:
            continue
        m = RE_ERRATA.search(t)
        if not m:
            continue
        errata = amt(m.group(1))
        ms = RE_SCOPE.search(t)
        scope = amt(ms.group(1)) if ms else None
        doc.close()
        ev = f"附注：由于重大会计差错更正影响期初未分配利润{errata:,.2f}元"
        if scope is not None:
            ev += f"；同一控制合并范围变更{scope:,.2f}元"
        if abs(errata) > 0.005:
            return "是", i + 1, ev, "NOTE_RETAINED_ERRATA_NONZERO", (ms.group(0)[:60] if ms else "")
        return "否", i + 1, ev, "NOTE_RETAINED_ERRATA_ZERO", (ms.group(0)[:60] if ms else "")
    doc.close()
    return "未找到判据", "", "", "NO_NOTE", ""


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
        w.writerow(["document_id", "verdict", "page", "evidence_errata", "method", "evidence_scope_change"])
        for x in out: w.writerow(x)
    print("done", Counter(x[1] for x in out), flush=True)

if __name__ == "__main__":
    main()
