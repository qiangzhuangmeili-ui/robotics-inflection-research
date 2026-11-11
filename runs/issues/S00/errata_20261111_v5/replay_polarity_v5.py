#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""极性 A/B 回放：新增「结构性新主语」判据对存量证据有无影响（第十一轮 A 项）。

做法：把 `evidence_scope._new_subject` 临时换成恒 False（＝第十轮行为），
对 1,007 份核验证据各跑一遍 `analyse`，与当前判据的结果逐条比对：

- 分句变化：`_clauses()` 的输出（新判据不参与分句，应为 0）
- 极性变化：`excluded / affirmed / scoped / mentioned` 四集合（应只在裁决点名的那类句子上变）

输出 `replay_polarity_v5.json`，由 C34 读取并纳入 PASS 条件。
复现顺序：`sampling_v5.py` 之后、`verify_v5.py` 之前。
"""
import csv
import json
import sys
from pathlib import Path

import evidence_scope as es

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "runs/issues/S00/errata_20261111_v5"
P_VERIFY = ROOT / "runs/issues/S02/remediation_20261029/restatement_verify/results.csv"

rows = list(csv.DictReader(P_VERIFY.open(encoding="utf-8-sig", newline="")))

_orig = es._new_subject
_old = lambda clause, st, window=10: False  # noqa: E731  ＝第十轮行为


def run(new_subject):
    es._new_subject = new_subject
    try:
        out = []
        for r in rows:
            txt = r.get("evidence") or ""
            a = es.analyse({"evidence": txt})
            out.append((tuple(es._clauses(txt)),
                        frozenset(a.excluded), frozenset(a.affirmed),
                        frozenset(a.scoped), frozenset(a.mentioned),
                        frozenset(a.conflict)))
        return out
    finally:
        es._new_subject = _orig


cur = run(_orig)
old = run(_old)

clause_changed, polarity_changed, samples = 0, 0, []
for r, a, b in zip(rows, cur, old):
    if a[0] != b[0]:
        clause_changed += 1
    if a[1:] != b[1:]:
        polarity_changed += 1
        if len(samples) < 5:
            samples.append({
                "security_id": r["security_id"], "document_id": r["document_id"],
                "evidence": (r.get("evidence") or "")[:160],
                "old": {"excluded": sorted(b[1]), "affirmed": sorted(b[2]),
                        "scoped": sorted(b[3])},
                "new": {"excluded": sorted(a[1]), "affirmed": sorted(a[2]),
                        "scoped": sorted(a[3])},
            })

summary = {
    "documents": len(rows),
    "clause_changed": clause_changed,
    "polarity_changed": polarity_changed,
    "note": ("A/B 对照：old = 第十轮判据（_new_subject 恒 False），"
             "new = 第十一轮判据（结构性新主语）。分句逻辑本轮未改，故 clause_changed 应为 0。"),
    "changed_samples": samples,
}
(OUT / "replay_polarity_v5.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
print(json.dumps({k: v for k, v in summary.items() if k != "changed_samples"},
                 ensure_ascii=False))
