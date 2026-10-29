#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""S02 收口：写入自检结论与交付，S03 仍锁（等 S02 外部复核 + 两项前置）。

只改调度/状态文件，不改研究数据、原始输入或他人结果。
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CST = timezone(timedelta(hours=8))
NOW = datetime.now(CST).isoformat(timespec="seconds")
REVIEW = "runs/issues/S02/review.json"
MANIFEST = "runs/issues/S02/calculation_manifest.json"


def load(p: str):
    return json.loads((ROOT / p).read_text(encoding="utf-8"))


def dump(p: str, obj) -> None:
    (ROOT / p).write_text(
        json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def update_plan_csv() -> dict:
    path = ROOT / "data/issue_execution_plan.csv"
    rows = list(csv.DictReader(io.StringIO(path.read_text(encoding="utf-8-sig"))))
    fields = list(rows[0].keys())
    changed = {}
    for row in rows:
        if row["key"] == "S02":
            row["status"] = "SELF_CHECK_PASS"
            row["review_record"] = REVIEW
            changed["S02"] = row["status"]
        elif row["key"] == "S03":
            changed["S03"] = row["status"]
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fields, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    path.write_text(buf.getvalue(), encoding="utf-8-sig")
    return changed


def update_plan_json() -> None:
    p = "data/issue_execution_plan.json"
    d = load(p)
    man = load(MANIFEST)
    for t in d["tasks"]:
        if t["key"] == "S02":
            t["status"] = "SELF_CHECK_PASS"
            t["review"] = {
                "review_nature": "SELF_CHECK",
                "decision": "SELF_CHECK_PASS_WITH_UPSTREAM_FINDINGS",
                "review_file": REVIEW,
                "reviewed_at": NOW,
                "checks": "21 项：18 PASS + 3 WARN，阻断 0",
                "cells": man["counts"]["cells"],
                "next_stage_release": "PENDING_EXTERNAL_RECHECK",
                "upstream_findings": [
                    "Q16 字段覆盖缺口 53 家（25 家仅 2 字段）",
                    "Q17 数值量级可疑 5 家（疑似万元/元单位错）",
                ],
            }
        elif t["key"] == "S03":
            t["status"] = "WAITING_DEPENDENCIES"
            t["blocked_reason"] = (
                "等 S02 外部复核放行；另需先补 L0 混合分支（377 家 W5 / 17 家 MIXED）"
                "与回 S00 补抽 53 家半年报/季报字段"
            )
    d["next_recommended_issue"] = 37
    dump(p, d)


def update_project_state() -> None:
    p = "PROJECT_STATE.json"
    d = load(p)
    man = load(MANIFEST)
    d["status"] = "S02_SELF_CHECK_PASS_AWAITING_EXTERNAL_RECHECK"
    d["current_gate"] = "S02_SELF_CHECK"
    d["s02_stage"].update({
        "status": "SELF_CHECK_PASS",
        "decision": "SELF_CHECK_PASS_WITH_UPSTREAM_FINDINGS",
        "completed_at": NOW,
        "review_nature": "SELF_CHECK",
        "review_file": REVIEW,
        "checks": "21 项：18 PASS + 3 WARN，阻断 0",
        "cells": man["counts"]["cells"],
        "counts": man["counts"],
        "l0_distribution": man["l0_distribution"],
        "outputs": man["outputs"],
        "upstream_findings": [
            {"id": "Q16", "companies": 53, "note": "最新期可用字段<8，25 家仅 2 字段；A03 已知半年报/季报字段未跑"},
            {"id": "Q17", "companies": 5, "note": "营收上亿而扣非不足万分之一，疑似万元/元单位错"},
        ],
        "rule_gap": "L0 未覆盖无 OK 的混合情形；377 家按 W5 单列、17 家记 MIXED，S03 前须补分支",
        "release_S03": False,
        "release_note": "自检不等于验收；S03 另需补 L0 分支与上游字段",
        "started": True,
    })
    d["next_recommended_issue"] = \
        "https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/37"
    d["next_issue"] = {
        "key": "S02", "number": 37,
        "reason": "S02 自检完成，等外部复核；复核通过后再评估 S03 前置",
    }
    dump(p, d)


def update_active_issue() -> None:
    p = "data/active_issue.json"
    d = load(p)
    man = load(MANIFEST)
    d["status"] = "SELF_CHECK_PASS_AWAITING_EXTERNAL_RECHECK"
    d["completed_at"] = NOW
    d["claim_note"] = (
        "S02 自检完成：12,648 格全覆盖，21 项检查 18 PASS + 3 WARN、阻断 0；"
        "两个上游缺陷（53 家字段缺口、5 家单位可疑）与 L0 规则缺口已记录，等外部复核。"
    )
    d["last_completed"] = {
        "issue_number": 37,
        "issue_key": "S02",
        "completed_at": NOW,
        "review_file": REVIEW,
        "decision": "SELF_CHECK_PASS_WITH_UPSTREAM_FINDINGS",
        "review_nature": "SELF_CHECK",
        "acceptance": "12,648 格全覆盖；21 项 18 PASS + 3 WARN，阻断 0",
        "summary": "用 v2 计算 1054×12 指标，逐格出 status/flags/期间/来源；"
                   "OK 6,092 / PROVISIONAL 4,158；与 S01 干跑逐项一致",
    }
    d["next_recommended_issue_number"] = 37
    d["next_recommended_issue_key"] = "S02"
    d["next_recommended_reason"] = (
        "S02 等外部复核；S03 另需补 L0 混合分支并回 S00 补抽 53 家字段，未完成前不开 S03"
    )
    dump(p, d)


def main() -> None:
    changed = update_plan_csv()
    update_plan_json()
    update_project_state()
    update_active_issue()
    print(json.dumps({"updated": changed, "at": NOW}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
