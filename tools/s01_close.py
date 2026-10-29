#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""S01 收口：更新调度状态。S02 保持 WAITING_DEPENDENCIES，等 S01 外部复验。"""
from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CST = timezone(timedelta(hours=8))
NOW = datetime.now(CST).isoformat(timespec="seconds")
REVIEW = "runs/issues/S01/review.json"


def load(p):
    return json.loads((ROOT / p).read_text(encoding="utf-8"))


def dump(p, obj):
    (ROOT / p).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    # 1) CSV
    path = ROOT / "data/issue_execution_plan.csv"
    rows = list(csv.DictReader(io.StringIO(path.read_text(encoding="utf-8-sig"))))
    fields = list(rows[0].keys())
    for r in rows:
        if r["key"] == "S01":
            r["status"] = "SELF_CHECK_PASS"
        if r["key"] == "S02":
            r["status"] = "WAITING_DEPENDENCIES"
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fields, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    path.write_text(buf.getvalue(), encoding="utf-8-sig")

    # 2) plan json
    p = "data/issue_execution_plan.json"
    d = load(p)
    for t in d["tasks"]:
        if t["key"] == "S01":
            t["status"] = "SELF_CHECK_PASS"
            t["review"] = {"review_nature": "SELF_CHECK", "decision": "SELF_CHECK_PASS",
                           "review_file": REVIEW, "reviewed_at": "2026-10-29",
                           "next_stage_release": "PENDING_EXTERNAL_RECHECK"}
        if t["key"] == "S02":
            t["status"] = "WAITING_DEPENDENCIES"
            t["blocked_reason"] = "等待 S01 外部复验放行（自检不等于验收）"
    d["next_recommended_issue"] = 37
    dump(p, d)

    # 3) PROJECT_STATE
    p = "PROJECT_STATE.json"
    d = load(p)
    d["status"] = "S01_SELF_CHECK_PASS_AWAITING_EXTERNAL_RECHECK"
    d["current_gate"] = "S01_SELF_CHECK"
    d["s01_stage"] = {
        "issue": "S01 / #36",
        "decision": "SELF_CHECK_PASS",
        "review_nature": "SELF_CHECK",
        "completed_at": NOW,
        "rules_version": "S01_SCREEN_RULES_V1",
        "frozen_at": "2026-10-29T10:25:57+08:00",
        "rules_file": "runs/issues/S01/screen_rules_v1.json",
        "metrics": 12,
        "signals": 9,
        "risk_hints": 6,
        "quality_flags": 12,
        "decision_layers": ["L0", "L1", "L2", "L3"],
        "machine_checks": "20/20 PASS",
        "dryrun_companies": 1054,
        "dryrun_latest_period": {"20251231": 4, "20260331": 5, "20260630": 863, "20260930": 182},
        "dryrun_L1": {"OBSERVE_QUEUE": 892, "RISK_WATCH": 111, "NO_SIGNAL": 51},
        "dryrun_L2": {"SHORTLIST_CANDIDATE": 542, "NOT_SHORTLISTED": 512},
        "known_limits": [
            "SG01∪SG02 覆盖 93%、L2 覆盖 51%，v1 阈值偏松",
            "MARGIN 与 PROFIT 维度同源，L2 重复计数",
            "按预登记原则未回头调阈值，修正留到 S04 前 v2"
        ],
        "release_S02": False,
        "release_note": "S02 等外部复验后放行；自检不等于验收",
    }
    d["next_recommended_issue"] = "https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/37"
    d["next_issue"] = {"key": "S02", "number": 37,
                       "reason": "S01 规则已冻结并自检通过，S02 待外部复验后放行",
                       "blocked_until": "S01_EXTERNAL_ACCEPTANCE"}
    dump(p, d)

    # 4) active_issue
    p = "data/active_issue.json"
    d = load(p)
    d["active_issue_number"] = None
    d["active_issue_key"] = None
    d["executor"] = "WorkBuddy AI"
    d["status"] = "IDLE_S01_SELF_CHECK_PASS_AWAITING_EXTERNAL_RECHECK"
    d["claim_note"] = "S01 规则已冻结并自检 20/20；S02 未启动，等外部复验。"
    d["last_completed"] = {
        "issue_number": 36,
        "issue_key": "S01",
        "completed_at": NOW,
        "review_file": REVIEW,
        "decision": "SELF_CHECK_PASS",
        "review_nature": "SELF_CHECK",
        "acceptance": "2/2 验收项自检通过，20/20 机器校验",
        "summary": "12 指标 + 9 信号 + 6 提示 + 4 层判定冻结；输入指纹登记；匿名干跑 1054 家证明可执行、未出名单",
    }
    d["next_recommended_issue_number"] = 37
    d["next_recommended_issue_key"] = "S02"
    d["next_recommended_reason"] = "S01 自检通过但未验收；S02 须等外部复验放行后执行"
    dump(p, d)

    print(json.dumps({"status": "S01_SELF_CHECK_PASS", "release_S02": False, "at": NOW},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
