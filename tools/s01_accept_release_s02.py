#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""S01 外部复验通过后，把验收写进状态源并把 S02 置为 READY（#37）。

只改调度/状态文件，不改任何研究数据、原始输入或他人结果。
幂等：重复执行结果一致（时间戳字段除外）。
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

ACCEPTANCE = "runs/issues/S01/acceptance_20261029.json"
ACCEPTANCE_SHA = hashlib.sha256((ROOT / ACCEPTANCE).read_bytes()).hexdigest()
S02_SCOPE = "METRIC_CALCULATION_AND_DEFINITION_QC_ONLY"


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
        if row["key"] == "S01":
            row["status"] = "ACCEPTED_WITH_LIMITS"
            row["review_record"] = ACCEPTANCE
            changed["S01"] = row["status"]
        elif row["key"] == "S02":
            row["status"] = "READY"
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
        if t["key"] == "S01":
            t["status"] = "ACCEPTED_WITH_LIMITS"
            t["acceptance"] = {
                "review_nature": "EXTERNAL_INDEPENDENT_RECHECK",
                "reviewer": "Codex",
                "recorded_by": "WorkBuddy AI",
                "decision": "ACCEPTED_WITH_LIMITS",
                "review_file": ACCEPTANCE,
                "review_file_sha256": ACCEPTANCE_SHA,
                "reviewed_at": "2026-10-29",
                "release_next": "S02",
                "release_scope": S02_SCOPE,
                "rules_version": "S01_SCREEN_RULES_V2",
            }
        elif t["key"] == "S02":
            t["status"] = "READY"
            t.pop("blocked_reason", None)
            t["release"] = {
                "from_issue": "S01",
                "decision": "ACCEPTED_WITH_LIMITS",
                "release_file": ACCEPTANCE,
                "scope": S02_SCOPE,
                "rules_version_required": "S01_SCREEN_RULES_V2",
                "rules_sha256_required":
                    "ada501e8bcd276ce670a4799c730a81cdf2f9dc70c244f9255485b00168c6a85",
                "must_not": "S03 名单筛选 / 业务深研 / 估值",
            }
    d["next_recommended_issue"] = 37
    dump(p, d)


def update_project_state() -> None:
    p = "PROJECT_STATE.json"
    d = load(p)
    d["status"] = "S01_ACCEPTED_WITH_LIMITS_S02_READY"
    d["current_gate"] = "S02_READY"
    d["release_S00"] = True
    d["s01_stage"]["decision"] = "ACCEPTED_WITH_LIMITS"
    d["s01_stage"]["review_nature"] = "EXTERNAL_INDEPENDENT_RECHECK"
    d["s01_stage"]["acceptance"] = {
        "reviewer": "Codex",
        "recorded_by": "WorkBuddy AI",
        "reviewed_at": "2026-10-29",
        "review_file": ACCEPTANCE,
        "review_file_sha256": ACCEPTANCE_SHA,
        "checks_passed": "6/6（含独立重算 SG09=203、C16 故障注入、v1→v2 差异白名单）",
        "commit": "80745cdc4e3f521b14b1ad7d716d05497914ea4d",
        "release_S02": True,
        "release_S02_scope": S02_SCOPE,
        "weak_assertions": [
            "SIGNAL_DEPS 仍硬编码在代码、规则文件未登记依赖字段",
            "D04 的 clean_dims 兜底按干净计入辅助统计",
            "最新可用期锚定定义敏感（203 vs 215）",
        ],
    }
    d["s01_stage"]["release_S02"] = True
    d["s01_stage"]["release_note"] = "S02 仅放行指标计算与口径检查，S03 及以后仍锁"
    d["s02_stage"] = {
        "issue": "S02 / #37",
        "status": "READY",
        "rules_version_required": "S01_SCREEN_RULES_V2",
        "rules_sha256": "ada501e8bcd276ce670a4799c730a81cdf2f9dc70c244f9255485b00168c6a85",
        "scope": S02_SCOPE,
        "must_output": [
            "all_pool_metrics.csv（逐格 metric_status / quality_flags / 期间 / 来源）",
            "metric_qc.csv",
            "calculation_manifest.json（输入指纹 + 最新可用期定义 + 规则版本）",
        ],
        "must_not": "把 PROVISIONAL 混入 OK；进入 S03 名单筛选、业务深研或估值",
        "started": False,
    }
    d["next_recommended_issue"] = \
        "https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/37"
    d["next_issue"] = {
        "key": "S02",
        "number": 37,
        "reason": "S01 外部复验 ACCEPTED_WITH_LIMITS，放行全池指标计算与口径检查",
    }
    dump(p, d)


def claim_active_issue() -> None:
    p = "data/active_issue.json"
    d = load(p)
    d["active_issue_number"] = 37
    d["active_issue_key"] = "S02"
    d["executor"] = "WorkBuddy AI"
    d["started_at"] = None
    d["status"] = "READY_NOT_STARTED"
    d["claim_note"] = (
        "S01 经 Codex 独立复验 ACCEPTED_WITH_LIMITS（SG09 依赖与传播、23 项测试、"
        "匿名重算 280/659、规则与交付哈希均通过），本地放行 S02；"
        "S02 只做指标计算与口径检查，须用冻结 v2，S03 名单筛选仍锁。"
    )
    d["last_completed"] = {
        "issue_number": 36,
        "issue_key": "S01",
        "completed_at": NOW,
        "review_file": ACCEPTANCE,
        "decision": "ACCEPTED_WITH_LIMITS",
        "review_nature": "EXTERNAL_INDEPENDENT_RECHECK",
        "review_round": "REWORK_R4_AFTER_CODEX_ACCEPTANCE_80745cd",
        "acceptance": "6/6 独立核实 + 23/23 合成测试 + 28/28 校验",
        "summary": "SIGNAL_DEPS 补 SG09→M07、未登记返回 None、新增 C16；L2=280、SG01∪SG02=659；"
                   "规则 v2 冻结未改，S02 放行指标计算",
    }
    d["next_recommended_issue_number"] = 37
    d["next_recommended_issue_key"] = "S02"
    d["next_recommended_reason"] = (
        "S01 已验收放行；S02 须用 v2 逐格输出 OK/PROVISIONAL/HOLD 与来源，"
        "不得直接进 S03。"
    )
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
