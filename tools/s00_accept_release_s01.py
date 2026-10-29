#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""S00 外部复验通过后，把验收写进状态源并放行 S01（#36）。

只改调度/状态文件，不改任何研究数据、原始输入或他人结果。
幂等：重复执行结果一致。
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

ACCEPTANCE = "runs/issues/S00/acceptance_20261029.json"
ACCEPTANCE_SHA = hashlib.sha256((ROOT / ACCEPTANCE).read_bytes()).hexdigest()


def load(p: str):
    return json.loads((ROOT / p).read_text(encoding="utf-8"))


def dump(p: str, obj) -> None:
    (ROOT / p).write_text(
        json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def update_plan_csv() -> dict:
    path = ROOT / "data/issue_execution_plan.csv"
    raw = path.read_text(encoding="utf-8-sig")
    rows = list(csv.DictReader(io.StringIO(raw)))
    fields = list(rows[0].keys())
    changed = {}
    for row in rows:
        if row["key"] == "S00":
            row["review_record"] = ACCEPTANCE
            changed["S00"] = row["status"]
        if row["key"] == "S01":
            row["status"] = "READY"
            changed["S01"] = "READY"
        if row["key"] == "S02":
            changed["S02"] = row["status"]
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fields, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    path.write_text(buf.getvalue(), encoding="utf-8-sig")
    return changed


def update_plan_json() -> None:
    p = "data/issue_execution_plan.json"
    d = load(p)
    for t in d["tasks"]:
        if t["key"] == "S00":
            t["acceptance"] = {
                "review_nature": "EXTERNAL_INDEPENDENT_RECHECK",
                "reviewer": "Codex",
                "decision": "ACCEPTED_WITH_LIMITS",
                "review_file": ACCEPTANCE,
                "review_file_sha256": ACCEPTANCE_SHA,
                "reviewed_at": "2026-10-29",
                "release_next": "S01",
            }
        elif t["key"] == "S01":
            t["status"] = "READY"
        elif t["key"] == "S02":
            t["status"] = "WAITING_DEPENDENCIES"
            t["blocked_reason"] = "等待 S01 自身验收（S00 教训：自检不等于验收）"
    d["next_recommended_issue"] = 36
    dump(p, d)


def update_project_state() -> None:
    p = "PROJECT_STATE.json"
    d = load(p)
    d["status"] = "S00_ACCEPTED_WITH_LIMITS_S01_READY"
    d["current_gate"] = "S01_READY"
    d["release_S00"] = True
    d["s00_stage"]["decision"] = "ACCEPTED_WITH_LIMITS"
    d["s00_stage"]["acceptance"] = {
        "review_nature": "EXTERNAL_INDEPENDENT_RECHECK",
        "reviewer": "Codex",
        "reviewed_at": "2026-10-29",
        "review_file": ACCEPTANCE,
        "review_file_sha256": ACCEPTANCE_SHA,
        "checks_passed": "7/7 独立只读复算",
        "blockers_closed": "4/4",
        "release_S01": True,
        "release_S02": False,
        "weak_assertions": ["V2-1/V2-2 只比计数", "V3-3 sq_hold>=0 恒真"],
    }
    d["next_recommended_issue"] = "https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/36"
    d["next_issue"] = {
        "key": "S01",
        "number": 36,
        "reason": "S00 外部复验 ACCEPTED_WITH_LIMITS，S01 只登记规则版本，不看个别公司调阈值",
    }
    dump(p, d)


def claim_active_issue() -> None:
    p = "data/active_issue.json"
    d = load(p)
    d["active_issue_number"] = 36
    d["active_issue_key"] = "S01"
    d["executor"] = "WorkBuddy AI"
    d["started_at"] = NOW
    d["status"] = "IN_PROGRESS"
    d["claim_note"] = (
        "S00 经 Codex 独立复验 ACCEPTED_WITH_LIMITS（4 项阻断闭合），本地放行 S01；"
        "本卡只登记规则版本，不产出名单、不按公司调阈值。"
    )
    d["last_completed"] = {
        "issue_number": 35,
        "issue_key": "S00",
        "completed_at": NOW,
        "review_file": ACCEPTANCE,
        "decision": "ACCEPTED_WITH_LIMITS",
        "review_nature": "EXTERNAL_INDEPENDENT_RECHECK",
        "review_round": "REWORK_20261029",
        "acceptance": "7/7 独立复算 + 4/4 阻断关闭",
        "summary": "44,499 派生格 0 违规、64 仲裁格溯源齐、2,037 HOLD 格父键齐、6 槽 131 格更正版采用、交付哈希与 gzip 一致",
    }
    d["next_recommended_issue_number"] = 37
    d["next_recommended_issue_key"] = "S02"
    d["next_recommended_reason"] = "S01 完成自检后，S02 仍须等 S01 外部复验放行（自检不等于验收）。"
    dump(p, d)


def main() -> None:
    changed = update_plan_csv()
    update_plan_json()
    update_project_state()
    claim_active_issue()
    print(json.dumps({"updated": changed, "acceptance_sha256": ACCEPTANCE_SHA,
                      "at": NOW}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
