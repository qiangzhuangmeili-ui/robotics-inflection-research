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
_old = lambda clause, st, window=10: False  # noqa: E731  ＝「关闭新主语判据」

# 第十二轮 A 项：复核指出上一轮汇报「新判据在真实证据上从未触发」与插桩不符
# （调用 88 次、判真 44 次）。这句话当时没有计数支撑，属无据断言。
# 现在把调用次数与判真次数直接打进输出，报告只引用数字，不再自行描述。
_STAT = {"calls": 0, "true": 0, "true_nonzero": 0}
_NONZERO = []          # 判真且非零的那几条：逐条留证，供复核抽查
_HEADS = {}            # 中心语分布：存量证据里判据到底看到了什么


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


def run_counted():
    """与 run(_orig) 等价，只是给当前判据挂计数器。"""
    def _wrapped(clause, st, window=10):
        v = _orig(clause, st, window)
        _STAT["calls"] += 1
        _h = es._head_noun(clause, st)
        _HEADS[_h] = _HEADS.get(_h, 0) + 1
        if v:
            _STAT["true"] += 1
            # 判真且该位置金额非零：这才是「拦下来会改变结论」的情形
            _hit = [x for x in es._amounts(clause) if x[0] == st]
            if _hit and abs(_hit[0][2]) > 0:
                _STAT["true_nonzero"] += 1
                if len(_NONZERO) < 10:
                    _NONZERO.append({"amount": _hit[0][2],
                                     "head_noun": es._head_noun(clause, st),
                                     "clause": clause[:160]})
        return v
    return run(_wrapped)


cur = run_counted()
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
    "new_subject_calls": _STAT["calls"],
    "new_subject_true": _STAT["true"],
    "new_subject_true_nonzero": _STAT["true_nonzero"],
    "nonzero_cases": _NONZERO,
    "head_nouns": dict(sorted(_HEADS.items(), key=lambda kv: -kv[1])[:20]),
    "note": ("A/B 对照：old = 关闭新主语判据（_new_subject 恒 False），"
             "new = 当前中心语判据。clause_changed 统计分句归属是否变化，"
             "polarity_changed 统计 excluded/affirmed/scoped/mentioned/conflict 是否变化。"
             "判据确实被调用（new_subject_calls）也确实判真（new_subject_true），"
             "其中判真且该位置金额非零的有 new_subject_true_nonzero 条。"
             "结论只能说「对存量证据的极性结果无影响」，不能说「判据从未触发」；"
             "判据是否承重由 C34 的 38 条反例证明，不由本回放证明。"),
    "changed_samples": samples,
}
(OUT / "replay_polarity_v5.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
print(json.dumps({k: v for k, v in summary.items() if k != "changed_samples"},
                 ensure_ascii=False))
