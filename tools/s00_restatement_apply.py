#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把重述复核结论应用到标准化表：只改 restatement_flag，不动数值。

输入：restatement_verify/results.csv（verdict: 是 / 否 / 待核 / 未找到判据）
输出：s00_v7.csv（新版本）+ apply_summary.json

规则：
- verdict=否 → restatement_flag 改「否」（原文明确无重述，去掉 Q06）
- verdict=是 → 改「是」（原文明确发生重述，保留 Q06）
- 待核 / 未找到判据 → 保持 RESTATEMENT_INDICATED_NEEDS_REVIEW（不猜）
- 只改 results.csv 覆盖到的 document_id，其余原样
"""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "runs/issues/S02/remediation_20261029/collect_q3_2026/s00_v6.csv"
VERIFY = ROOT / "runs/issues/S02/remediation_20261029/restatement_verify/results.csv"
OUT_DIR = ROOT / "runs/issues/S02/remediation_20261029/collect_q3_2026"
OUT = OUT_DIR / "s00_v7.csv"
CST = timezone(timedelta(hours=8))
NOW = datetime.now(CST).isoformat(timespec="seconds")


def main() -> int:
    verdict = {}
    with VERIFY.open(encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            verdict[r["document_id"]] = r["verdict"]

    changed = Counter()
    per_doc = defaultdict(int)
    with BASE.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        cols = reader.fieldnames
        rows = list(reader)

    for r in rows:
        v = verdict.get(r["document_id"])
        if v == "否" and r["restatement_flag"] == "RESTATEMENT_INDICATED_NEEDS_REVIEW":
            r["restatement_flag"] = "否"
            changed["NEEDS_REVIEW->否"] += 1
            per_doc[r["document_id"]] += 1
        elif v == "是" and r["restatement_flag"] == "RESTATEMENT_INDICATED_NEEDS_REVIEW":
            r["restatement_flag"] = "是"
            changed["NEEDS_REVIEW->是"] += 1
            per_doc[r["document_id"]] += 1

    with OUT.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)

    sha = hashlib.sha256(OUT.read_bytes()).hexdigest()
    summary = {
        "generated_at": NOW,
        "base": BASE.as_posix(),
        "output": OUT.as_posix(),
        "rows": len(rows),
        "sha256": sha,
        "verdict_source": VERIFY.as_posix(),
        "verdict_counts": dict(Counter(verdict.values())),
        "rows_changed": dict(changed),
        "documents_changed": len(per_doc),
        "only_restatement_flag_changed": True,
        "not_applied": "待核 / 未找到判据 保持 NEEDS_REVIEW，不猜",
    }
    (OUT_DIR / "apply_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
