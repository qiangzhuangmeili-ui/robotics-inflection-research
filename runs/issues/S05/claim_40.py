# -*- coding: utf-8 -*-
"""按放行记录领取 #40（S05），登记执行者与时间，并同步控制文件。"""
import hashlib
import io
import json
import os
from datetime import datetime, timedelta, timezone

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "..", "..", ".."))
ONLINE = os.path.join(os.path.expanduser("~"), "AppData", "Local", "Temp", "s05claim")
now = datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def sha_txt(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


# 领取前在线版本的哈希（用下载的原始字节）
rel_sha = sha(os.path.join(ONLINE, "release_20261120.json"))
hand_sha = sha(os.path.join(ONLINE, "handoff_from_s04_20261120.md"))
plan_csv_sha = sha(os.path.join(ONLINE, "data_issue_execution_plan.csv"))
plan_json_sha = sha(os.path.join(ONLINE, "data_issue_execution_plan.json"))
state_sha = sha(os.path.join(ONLINE, "PROJECT_STATE.json"))

# ---------- 1) active_issue.json ----------
p = os.path.join(REPO, "data", "active_issue.json")
d = json.load(io.open(p, encoding="utf-8"))
d["active_issue_number"] = 40
d["active_issue_key"] = "S05"
d["executor"] = "WorkBuddy AI"
d["started_at"] = now
d["status"] = "IN_PROGRESS"
d["claim_note"] = ("按 S05 放行记录单卡领取 #40。领取前在线 active_issue 无执行者（blob 82ef676b），"
                   "V2.2 五份冻结指纹与冻结 B 逐项匹配，控制文件已同步在线权威版本。")
d["s05_claim"] = {
    "claimed_at": now,
    "issue_number": 40,
    "issue_key": "S05",
    "executor": "WorkBuddy AI",
    "review_nature": "SELF_CHECK",
    "single_card": True,
    "claim_basis": {
        "online_active_issue_blob_sha_before_claim":
            "82ef676b4be8e2439f2f78e15ed977f07d991990",
        "online_main_ref_at_claim": "a308fab19c17ea0184df0d730f2a5723760f2ef4",
        "release_record": "runs/issues/S05/release_20261120.json",
        "release_record_sha256": rel_sha,
        "handoff_file": "runs/issues/S05/handoff_from_s04_20261120.md",
        "handoff_sha256": hand_sha,
        "technical_review": "runs/issues/S04/codex_ruling_s05_v22_20261120.md",
        "technical_review_decision": "ACCEPTED_WITH_LIMITS_FOR_FROZEN_S05_INPUT",
        "worktree_commit": "dae485f06cf88d167a7bc5a6d4105914db5068a3",
        "worktree_branch": "s04/l2-tightening-20261108",
        "input_contract_id": "S05_INPUT_CONTRACT_20261120_V22",
        "frozen_B": "runs/issues/S02/hangcha_restated_20261101/s00_v10/s00_v10.csv.gz",
        "frozen_B_sha256":
            "fc312c52ace51feb37593c08cb8077c8a47012a7a239ef639d0fe8b745fe2025",
        "verified_files_sha256": {
            "manifest.json":
                "98b835b77721b81392d56428ea0b7be726e3344ac199429893035d424528e54e",
            "s05_input_contract_v22.json":
                "bb796b1ced9990a4d47e1be7bc7f6e64cdbd9ca1fa94e1242a22cd86d04f7532",
            "s05_applicability_v22.csv":
                "ad06003d9503b74f4a828fe245e892c96e552080f0daf190f6492ea892205268",
            "s05_source_eligibility_v22.csv":
                "129dbe9de4e3e9955f034c0874addeae17eb2d3e236ad162d0fd2a7f59b6b0e3",
            "s05_ca_source_nonadmission_v22.csv":
                "6177055309bc869a90ac02aefb336e83702448c3fd2a2842f46f82a39101ec1c",
        },
        "verified_files_result": "5/5 MATCH；冻结 B 亦 MATCH",
        "control_files_sha256_at_claim": {
            "data/issue_execution_plan.csv": plan_csv_sha,
            "data/issue_execution_plan.json": plan_json_sha,
            "PROJECT_STATE.json": state_sha,
        },
        "note": "控制文件哈希取领取前在线版本；领取后按本次提交更新。",
    },
    "scope": {
        "universe": 1054,
        "primary_candidates": 278,
        "observe_or_guard_only": 776,
        "knowledge_as_of": "2026-10-25",
        "metrics": ["M04", "M08", "M10", "M11", "M12"],
        "output_directory": "runs/issues/S05/",
        "deliverables": ["quality_flags.csv", "quality_pass.csv", "quality_observe.csv",
                         "quality_decision_log.csv", "source_eligibility.csv",
                         "input_contract.json", "manifest.json", "handoff.md", "review.json"],
    },
    "guards_inherited_from_release": {
        "rh02": {"evaluable": 118, "project_mode_not_applicable": 31, "hold": 129},
        "rh03": {"evaluable": 133, "both_periods_no_usable_amount": 126,
                 "single_sided_gap": 18, "unreadable_or_missing": 1},
        "existing_pending_consumer_rows": 15,
        "existing_pending_unique_cells": 13,
        "nonadmitted_CA_keys": 3,
        "cutoff_guard": 4,
        "anchor_hold": 1,
        "quality_source_unknown_observe_companies": 15,
        "held_parent_members": 8,
        "jidong": ("M07/SG09 blocked for consolidation scope UNKNOWN; "
                   "remaining CASH only; route to quality_observe"),
    },
    "prior_lease": {"issue_number": 53, "issue_key": "S00_ERRATA_REVIEW",
                    "executor": "Codex", "state": "RELEASED",
                    "issue_state": "OPEN", "residual_errata_open": True},
}
d["s53_breakpoint_at_s05_claim"] = {
    "issue_number": 53,
    "issue_key": "S00_ERRATA_REVIEW",
    "issue_state": "OPEN",
    "lease": "RELEASED_TO_S05",
    "registered_at": now,
    "online_blob_sha_at_registration": "82ef676b4be8e2439f2f78e15ed977f07d991990",
    "prior_controller_blob_sha": "a8195c81d4ff2aab630c08bc843ef043eaf4350d",
    "checkpoint_file": "runs/issues/S05/release_20261120.json",
    "residual_scope": ("全池 S00 勘误保持开放：8 项未采用父链提议、15 家质量来源未知、"
                       "44/231/378 未冻结集合均保留；本次不关闭 #53、不改其残余结论。"),
}
d["updated_at"] = now
io.open(p, "w", encoding="utf-8", newline="\n").write(
    json.dumps(d, ensure_ascii=False, indent=2) + "\n")

# ---------- 2) 计划 CSV：只改 S05 行 ----------
p = os.path.join(REPO, "data", "issue_execution_plan.csv")
raw = io.open(p, encoding="utf-8-sig", newline="").read()
lines = raw.splitlines(True)
hit = 0
for i, ln in enumerate(lines):
    if ",S05,40," in ln and ",READY," in ln:
        lines[i] = ln.replace(",READY,", ",IN_PROGRESS,", 1)
        hit += 1
assert hit == 1, hit
io.open(p, "w", encoding="utf-8-sig", newline="").write("".join(lines))

# ---------- 3) 计划 JSON ----------
p = os.path.join(REPO, "data", "issue_execution_plan.json")
d = json.load(io.open(p, encoding="utf-8"))
for t in d["tasks"]:
    if t.get("key") == "S05":
        t["status"] = "IN_PROGRESS"
        t["claim_record"] = "data/active_issue.json#s05_claim"
        t["claimed_at"] = now
        t["executor"] = "WorkBuddy AI"
io.open(p, "w", encoding="utf-8", newline="\n").write(
    json.dumps(d, ensure_ascii=False, indent=2) + "\n")

# ---------- 4) PROJECT_STATE ----------
p = os.path.join(REPO, "PROJECT_STATE.json")
raw = io.open(p, encoding="utf-8", newline="").read()
pairs = [
    ('"current_gate": "S05_RELEASED_READY_FOR_CLAIM"', '"current_gate": "S05_IN_PROGRESS"'),
    ('"status": "S03_SELF_CHECK_PASS_WITH_LIMITS_S04_READY"',
     '"status": "S04_ACCEPTED_WITH_LIMITS_S05_IN_PROGRESS"'),
]
for a, b in pairs:
    assert a in raw, a
    raw = raw.replace(a, b, 1)
io.open(p, "w", encoding="utf-8", newline="").write(raw)

print(json.dumps({"claimed_at": now, "release_sha": rel_sha, "handoff_sha": hand_sha,
                  "plan_csv_sha_before": plan_csv_sha,
                  "plan_json_sha_before": plan_json_sha,
                  "state_sha_before": state_sha}, ensure_ascii=False, indent=1))
