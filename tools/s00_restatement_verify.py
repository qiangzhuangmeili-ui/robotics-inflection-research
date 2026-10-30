#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""S00 重述标记复核：把 RESTATEMENT_INDICATED_NEEDS_REVIEW 逐份回原文核实。

背景：S00 的重述标记用附注关键词判定，只认有限几种否定式；实测发现两类假阳性——
1) 合并所有者权益变动表的固定行项目「加：会计政策变更 / 前期差错更正 / 其他」；
2) 附注章节标题「会计政策变更、会计估计变更和前期差错更正」。
真正可判的判据是附注里的勾选：
    (1).追溯重述法   □适用 √不适用      → 无重述
    或正文「本期未发生采用追溯重述法的前期会计差错更正事项」 → 无重述
    √适用                              → 发生了重述

输出：每份文档一条结论（是 / 否 / 待核 / 未找到判据），不修改任何原始数据。

用法：
    python tools/s00_restatement_verify.py [--limit N]
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs/issues/S02/remediation_20261029/restatement_verify"
NORMALIZED = ROOT / "runs/issues/S02/remediation_20261029/collect_q3_2026/s00_v6.csv"
INDEX = ROOT / "runs/collection/collection_index.csv"
CST = timezone(timedelta(hours=8))
NOW = datetime.now(CST).isoformat(timespec="seconds")

USABLE = {"EXTRACTED", "EXTRACTED_KEY_TABLE", "EXTRACTED_QUARTERLY_TABLE", "DERIVED",
          "DERIVED_CUMULATIVE_DIFF", "DERIVED_Q1_EQUALS_YTD",
          "DERIVED_QUARTERLY_SUM_OVERRIDE", "LEGACY_SNAPSHOT"}
ANCHOR = ("FIN.REV.YTD", "FIN.REV.SQ", "FIN.NPDEDT.YTD")
PENDING = "RESTATEMENT_INDICATED_NEEDS_REVIEW"


def load_targets():
    """最新期 + 上年同期里标了待核的文档（这些直接决定当期指标是否 PROVISIONAL）。"""
    rows = {}
    with NORMALIZED.open(encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            rows.setdefault(r["security_id"], []).append(r)
    latest = {}
    for sec, rs in rows.items():
        for r in rs:
            if r["field_id"] in ANCHOR and r["status"] in USABLE and r["value_cny"]:
                pk = int(r["period_key"])
                if sec not in latest or pk > latest[sec]:
                    latest[sec] = pk
    targets = {}
    for sec, rs in rows.items():
        pk = latest.get(sec)
        if not pk:
            continue
        for r in rs:
            if int(r["period_key"]) not in (pk, pk - 10000):
                continue
            if r["restatement_flag"] != PENDING or not r["document_id"]:
                continue
            targets.setdefault(r["document_id"], {
                "security_id": sec, "stock_name": r["stock_name"],
                "period_key": r["period_key"], "period_label": r["period_label"],
            })
    return targets


def load_paths():
    idx = {}
    with INDEX.open(encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            if r["document_id"]:
                idx[r["document_id"]] = r.get("local_file", "")
    return idx


def _verdict_from_segment(seg: str):
    """从「追溯重述法 …」后续片段判定。"""
    s = seg.replace(" ", "")
    if re.search(r"[√☑✓✔]\s*不适用", s):
        return "否", "NOTE_TRACE_NA"
    if re.search(r"本期未发生|未发生采用|无前期差错更正|不存在前期差错更正", s):
        return "否", "NOTE_TRACE_NOT_OCCURRED"
    if re.search(r"[√☑✓✔]\s*适用", s) and "不适用" not in s:
        return "是", "NOTE_TRACE_YES"
    if re.search(r"调增|调减|重述后|更正后|调整后金额", s):
        return "是", "NOTE_TRACE_AMOUNT"
    return "待核", "NOTE_TRACE_UNCLEAR"


def judge(path: Path):
    try:
        reader = PdfReader(str(path))
    except Exception as e:                     # 文件损坏
        return "待核", None, f"PDF_PARSE_ERROR:{e}", "ERROR"
    n = len(reader.pages)

    # 1) 附注「追溯重述法」勾选（年报/半年报的稳定位置，从后往前扫）
    for i in range(n - 1, max(n - 60, -1), -1):
        try:
            t = (reader.pages[i].extract_text() or "").replace(" ", "")
        except Exception:
            continue
        if "追溯重述法" in t:
            j = t.find("追溯重述法")
            v, m = _verdict_from_segment(t[j:j + 220])
            return v, i + 1, t[j:j + 160], m

    # 2) 首部勾选项（深市/北交所格式：公司是否需追溯调整或重述以前年度会计数据 □是 √否）
    for i in range(min(60, n)):
        try:
            t = (reader.pages[i].extract_text() or "").replace(" ", "")
        except Exception:
            continue
        if "追溯调整" in t and "重述" in t:
            j = t.find("追溯调整")
            seg = t[j:j + 160]
            if re.search(r"[√☑✓✔]\s*否", seg):
                return "否", i + 1, seg, "CHECKBOX_NO"
            if re.search(r"[√☑✓✔]\s*是", seg):
                return "是", i + 1, seg, "CHECKBOX_YES"
            if "不适用" in seg:
                return "否", i + 1, seg, "CHECKBOX_NA"
            return "待核", i + 1, seg, "CHECKBOX_UNCLEAR"
    return "未找到判据", None, None, "NO_RULE_FOUND"


def _work(job):
    did, meta, f = job
    if not f or not Path(f).exists():
        return {**meta, "document_id": did, "verdict": "未找到判据",
                "page": "", "evidence": "LOCAL_FILE_MISSING", "method": "NO_FILE"}
    verdict, page, ev, method = judge(ROOT / f)
    return {**meta, "document_id": did, "verdict": verdict,
            "page": page or "", "evidence": (ev or "")[:160], "method": method}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args(argv)

    targets = load_targets()
    idx = load_paths()
    OUT.mkdir(parents=True, exist_ok=True)
    items = sorted(targets.items())
    if args.limit:
        items = items[:args.limit]
    print(f"targets={len(items)}")

    jobs = [(did, meta, idx.get(did, "")) for did, meta in items]
    results = []
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        for k, r in enumerate(ex.map(_work, jobs, chunksize=4), 1):
            results.append(r)
            if k % 100 == 0:
                print(f"  {k}/{len(items)} {Counter(x['verdict'] for x in results)}", flush=True)

    out = OUT / "results.csv"
    fields = ["security_id", "stock_name", "period_key", "period_label",
              "document_id", "verdict", "page", "method", "evidence"]
    with out.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        for r in results:
            w.writerow({k: r.get(k, "") for k in fields})

    c = Counter(r["verdict"] for r in results)
    summary = {
        "generated_at": NOW,
        "targets": len(items),
        "verdicts": dict(c),
        "by_method": dict(Counter(r["method"] for r in results)),
        "note": "否=原文明确无重述；是=原文明确发生重述；待核=有勾选但读不出；未找到判据=格式无此章节或文件缺失",
        "not_a_data_change": True,
    }
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
                                      encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
