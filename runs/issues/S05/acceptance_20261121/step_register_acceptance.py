#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 S05 R1 验收结论与交付版本登记到在线控制文件，并释放 #40 执行占用。

纪律：
  * 所有数字从 acceptance_s05_r1_20261121.json 与交付产物派生，不手写。
  * 登记前先校验验收记录指向的版本 = 当前 HEAD 与磁盘清单，不一致即中止。
  * 不释放 S06/S07/S08；不改 #53 既有结论；不改冻结阈值/B/旧验收。
  * 不修改 manifest.json（它是验收指纹，改一个字节即作废本次验收）。
"""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent          # runs/issues/S05/acceptance_20261121
S05 = HERE.parent                                # runs/issues/S05
REPO = HERE.parents[3]
ACCEPT = S05 / "acceptance_s05_r1_20261121.json"


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def head_commit() -> str:
    return subprocess.check_output(["git", "-C", str(REPO), "rev-parse", "HEAD"]).decode().strip()


def main() -> int:
    acc = json.loads(ACCEPT.read_text(encoding="utf-8"))
    man = json.loads((S05 / "manifest.json").read_text(encoding="utf-8"))
    rv = acc["reviewed_version"]

    # ---- 前置校验：验收对象必须就是磁盘上这一版
    problems = []
    if head_commit() != rv["commit"]:
        problems.append(f"HEAD {head_commit()[:12]} != 验收提交 {rv['commit'][:12]}")
    if sha256(S05 / "manifest.json") != rv["manifest_sha256"]:
        problems.append("manifest.json SHA-256 与验收记录不符")
    if man["root_digest"] != rv["manifest_root_digest"]:
        problems.append("manifest root_digest 与验收记录不符")
    if problems:
        print("ABORT:", "；".join(problems))
        return 1
    print("前置校验通过：HEAD / manifest sha / root_digest 三者与验收记录一致")

    now = datetime.now().astimezone().isoformat(timespec="seconds")

    # ---- 1) data/active_issue.json
    ai_path = REPO / "data/active_issue.json"
    ai = json.loads(ai_path.read_text(encoding="utf-8"))
    prev = {
        "active_issue_number": ai.get("active_issue_number"),
        "active_issue_key": ai.get("active_issue_key"),
        "executor": ai.get("executor"),
        "status": ai.get("status"),
    }
    ai["active_issue_number"] = None
    ai["active_issue_key"] = None
    ai["executor"] = None
    ai["status"] = "S05_ACCEPTED_WITH_LIMITS_RELEASED"
    ai["released_at"] = now
    ai["release_note"] = (
        "S05 已由 Codex 独立复核为 ACCEPTED_WITH_LIMITS；#40 执行占用已释放。"
        "S06/S07/S08 未放行，需新增明确 release 记录后再派工。"
    )
    ai["s05_acceptance"] = {
        "issue_key": acc["issue_key"],
        "issue_number": acc["issue_number"],
        "decision": acc["decision"],
        "S05_completed": acc["S05_completed"],
        "reviewer": acc["reviewer"],
        "reviewed_on": acc["reviewed_on"],
        "review_file": "runs/issues/S05/acceptance_s05_r1_20261121.json",
        "review_round": rv["round"],
        "reviewed_commit": rv["commit"],
        "manifest_root_digest": rv["manifest_root_digest"],
        "manifest_sha256": rv["manifest_sha256"],
        "primary_pool": acc["verified"]["primary_decision_keys"],
        "quality_pass": acc["verified"]["quality_pass"],
        "quality_observe": acc["verified"]["quality_observe"],
        "rh06": {
            "triggered": acc["RH06"]["triggered"],
            "not_triggered_with_qualified_inputs": acc["RH06"]["not_triggered_with_qualified_inputs"],
            "pending": acc["RH06"]["pending"],
            "Q09_total": acc["RH06"]["Q09_total"],
        },
        "limits": acc["limits"],
        "release_S06": False,
        "release_S07": False,
        "release_S08": False,
        "issue_53_touched": False,
    }
    ai["last_completed"] = {
        "issue_key": acc["issue_key"],
        "issue_number": acc["issue_number"],
        "decision": acc["decision"],
        "review_file": "runs/issues/S05/acceptance_s05_r1_20261121.json",
        "reviewer": acc["reviewer"],
        "reviewed_commit": rv["commit"],
        "manifest_root_digest": rv["manifest_root_digest"],
        "coverage": acc["verified"]["primary_decision_keys"],
    }
    ai["next_recommended_issue_number"] = None
    ai["next_recommended_issue_key"] = None
    ai["next_recommended_reason"] = (
        "S05 已验收。S06 未放行（release_S06=false），等新增明确 release 记录后再推荐派工。"
    )
    ai["s05_claim"]["lease_released_at"] = now
    ai["s05_claim"]["lease_release_basis"] = "runs/issues/S05/acceptance_s05_r1_20261121.json"
    ai["updated_at"] = now
    ai_path.write_text(json.dumps(ai, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8", newline="\n")

    # ---- 2) data/issue_execution_plan.csv
    csv_path = REPO / "data/issue_execution_plan.csv"
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
        fields = list(rows[0].keys())
    hit = 0
    for r in rows:
        if r["key"] == "S05":
            r["status"] = acc["decision"]
            r["review_record"] = "runs/issues/S05/acceptance_s05_r1_20261121.json"
            hit += 1
    assert hit == 1, hit
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow(r)

    # ---- 3) data/issue_execution_plan.json
    pj_path = REPO / "data/issue_execution_plan.json"
    pj = json.loads(pj_path.read_text(encoding="utf-8"))
    hit = 0
    for t in pj["tasks"]:
        if t.get("key") == "S05":
            t["status"] = acc["decision"]
            t["review_record"] = "runs/issues/S05/acceptance_s05_r1_20261121.json"
            t["accepted_at"] = now
            t["accepted_commit"] = rv["commit"]
            t["manifest_root_digest"] = rv["manifest_root_digest"]
            hit += 1
    assert hit == 1, hit
    pj["next_recommended_issue"] = None
    pj_path.write_text(json.dumps(pj, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8", newline="\n")

    # ---- 4) PROJECT_STATE.json
    ps_path = REPO / "PROJECT_STATE.json"
    ps = json.loads(ps_path.read_text(encoding="utf-8"))
    gate = "S05_ACCEPTED_WITH_LIMITS_S06_LOCKED"
    ps["status"] = gate
    ps["current_gate"] = gate
    ps["issue_plan"]["current_gate"] = gate
    ps["issue_plan"]["next_recommended_issue"] = None
    ps["issue_plan"]["last_completed_issue"] = {
        "issue_key": acc["issue_key"],
        "issue_number": acc["issue_number"],
        "decision": acc["decision"],
        "review_file": "runs/issues/S05/acceptance_s05_r1_20261121.json",
        "reviewer": acc["reviewer"],
        "reviewed_commit": rv["commit"],
        "manifest_root_digest": rv["manifest_root_digest"],
        "coverage": acc["verified"]["primary_decision_keys"],
    }
    ps["next_recommended_issue"] = None
    ps["release_S06"] = False
    ps["release_S07"] = False
    ps["release_S08"] = False
    ps["s05_stage"] = {
        "issue_key": acc["issue_key"],
        "issue_number": acc["issue_number"],
        "plan_version": acc["plan_version"],
        "executor": "WorkBuddy AI",
        "reviewer": acc["reviewer"],
        "review_method": acc["review_method"],
        "review_nature": "INDEPENDENT_REVIEW",
        "reviewed_at": acc["reviewed_on"],
        "decision": acc["decision"],
        "review_file": "runs/issues/S05/acceptance_s05_r1_20261121.json",
        "reviewed_commit": rv["commit"],
        "manifest_root_digest": rv["manifest_root_digest"],
        "manifest_files": acc["verified"]["manifest_files"],
        "counts": {
            "primary_pool": acc["verified"]["primary_decision_keys"],
            "quality_pass": acc["verified"]["quality_pass"],
            "quality_observe": acc["verified"]["quality_observe"],
        },
        "rh06": acc["RH06"],
        "actual_output_directory": "runs/issues/S05",
        "allows_next_stage": False,
        "release_S06": False,
        "release_S07": False,
        "release_S08": False,
        "limitations": acc["limits"],
        "prior_review": rv["prior_review"],
    }
    ps_path.write_text(json.dumps(ps, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8", newline="\n")

    print(json.dumps({
        "active_issue": {
            "before": prev,
            "after": {
                "active_issue_number": ai["active_issue_number"],
                "active_issue_key": ai["active_issue_key"],
                "executor": ai["executor"],
                "status": ai["status"],
            },
        },
        "plan_csv": "S05 -> " + acc["decision"],
        "plan_json": "S05 -> " + acc["decision"],
        "project_state_gate": gate,
        "release_S06_08": [False, False, False],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
