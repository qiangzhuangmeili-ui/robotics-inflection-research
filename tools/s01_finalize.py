#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""S01 收口：生成 manifest.json（交付清单 + 逐文件 sha256 + 自检摘要）。"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
S01 = ROOT / "runs/issues/S01"
CST = timezone(timedelta(hours=8))

DELIVERABLES = [
    "screen_rules_v1.json",
    "metric_formulas.md",
    "threshold_rationale.md",
    "metric_coverage_dryrun.csv",
    "self_check.json",
    "handoff.md",
    "review.json",
]
TOOLS = ["tools/s01_rules_check.py"]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    rules = json.loads((S01 / "screen_rules_v1.json").read_text(encoding="utf-8"))
    sc = json.loads((S01 / "self_check.json").read_text(encoding="utf-8"))

    if sc["rules_sha256"] != sha256(S01 / "screen_rules_v1.json"):
        raise SystemExit("规则文件在自检之后被改动，请重跑 tools/s01_rules_check.py")

    outputs = []
    for name in DELIVERABLES:
        p = S01 / name
        if not p.exists():
            continue
        outputs.append({"path": str(p.relative_to(ROOT)).replace("\\", "/"),
                        "bytes": p.stat().st_size, "sha256": sha256(p)})

    manifest = {
        "issue_key": "S01",
        "issue_number": 36,
        "plan_version": rules["plan_version"],
        "rules_version": rules["rules_version"],
        "generated_at": datetime.now(CST).isoformat(timespec="seconds"),
        "executor": "WorkBuddy AI",
        "review_nature": "SELF_CHECK",
        "frozen_at": rules["frozen_at"],
        "purpose": "在任何名单产出前冻结公式、阈值、缺失/亏损/低基数/一次性/模式/版本处理与重进条件",
        "inputs": rules["input_fingerprint"],
        "outputs": outputs,
        "universe": rules["universe"],
        "rules_summary": {
            "metrics": len(rules["metrics"]),
            "signals": len(rules["signals"]),
            "risk_hints": len(rules["risk_hints"]),
            "quality_flags": len(rules["quality_flags"]),
            "decision_layers": [l["id"] for l in rules["decision_layers"]],
            "policies": sorted(rules["policies"]),
        },
        "self_check": {
            "file": "runs/issues/S01/self_check.json",
            "total": sc["checks_total"],
            "pass": sc["checks_pass"],
            "fail": sc["checks_fail"],
            "blocking_fail": sc["blocking_fail"],
        },
        "dryrun": {
            "label": "ANONYMOUS_DRYRUN_NOT_A_RESULT",
            "companies": sc["dryrun"]["companies"],
            "latest_period_distribution": sc["dryrun"]["latest_period_distribution"],
            "L1_counts": sc["dryrun"]["L1_counts"],
            "L2_counts": sc["dryrun"]["L2_counts"],
            "breadth_observation": sc["dryrun"]["breadth_observation"],
            "note": "只验证规则可执行，不产出名单；不得引用为「多少家改善」。",
        },
        "no_quota": rules["no_quota_attestation"],
        "tools": [{"path": t, "sha256": sha256(ROOT / t)} for t in TOOLS],
        "known_limits": [
            "阈值全部为先验假设，未做行业分组校准",
            "干跑显示 SG01∪SG02 覆盖 93%、L2 两维组合覆盖 51%，v1 偏松；按预登记原则未回头调阈值",
            "MARGIN 与 PROFIT 维度同源，L2 存在重复计数，须在 v2 修正",
            "62 个整槽无值公司落 W1，不代表基本面",
            "2026Q3 仅 188 家已披露，当期截面不完整",
        ],
    }

    (S01 / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"outputs": len(outputs), "self_check": manifest["self_check"]},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
