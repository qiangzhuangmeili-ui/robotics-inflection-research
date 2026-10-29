#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""S02 修复版接手上账：登记 v2 输入/输出、L0 addendum，S03 仍锁。

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

REMED = "runs/issues/S02/remediation_20261029"
REVIEW = f"{REMED}/review_workbuddy.md"
V2_MANIFEST = f"{REMED}/s02_recheck/calculation_manifest.json"


def load(p: str):
    return json.loads((ROOT / p).read_text(encoding="utf-8"))


def dump(p: str, obj) -> None:
    (ROOT / p).write_text(
        json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def sha256(p: str) -> str:
    h = hashlib.sha256()
    with (ROOT / p).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def update_plan_csv() -> dict:
    path = ROOT / "data/issue_execution_plan.csv"
    rows = list(csv.DictReader(io.StringIO(path.read_text(encoding="utf-8-sig"))))
    fields = list(rows[0].keys())
    changed = {}
    for row in rows:
        if row["key"] == "S02":
            row["status"] = "SELF_CHECK_PASS_REPAIR_V2"
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


def update_plan_json(man: dict) -> None:
    p = "data/issue_execution_plan.json"
    d = load(p)
    for t in d["tasks"]:
        if t["key"] == "S02":
            t["status"] = "SELF_CHECK_PASS_REPAIR_V2"
            t["review"]["repair"] = {
                "review_file": REVIEW,
                "review_file_sha256": sha256(REVIEW),
                "review_nature": "REPAIR_ACCEPTANCE_REVIEW",
                "received_at": NOW,
                "baseline_commit": "547508d",
                "package_manifest": f"{REMED}/manifest.json",
                "package_files_verified": 433,
                "v2_input": f"{REMED}/s00/financial_normalized.csv",
                "v2_input_sha256": man["normalized_input_used"]["sha256"],
                "v2_output_dir": f"{REMED}/s02/",
                "independent_recheck_dir": f"{REMED}/s02_recheck/",
                "independent_recheck_diff_cells": 0,
                "cells_changed_vs_v1": 398,
                "companies_changed_vs_v1": 46,
                "l0_addendum": "S01_SCREEN_RULES_V2_L0_ADDENDUM_20261029",
                "l0_distribution": man["l0_distribution"],
                "pending_external_recheck": True,
            }
        elif t["key"] == "S03":
            t["status"] = "WAITING_DEPENDENCIES"
            t["blocked_reason"] = (
                "等 S02 修复版（v2）外部复核放行；开工须用 remediation_20261029/s00 输入 + "
                "L0 addendum，21 家待核须显式保留为观察/待核，PROVISIONAL/HOLD 不计入干净维度"
            )
    d["next_recommended_issue"] = 37
    dump(p, d)


def update_project_state(man: dict) -> None:
    p = "PROJECT_STATE.json"
    d = load(p)
    d["status"] = "S02_REPAIR_V2_APPLIED_AWAITING_EXTERNAL_RECHECK"
    d["current_gate"] = "S02_REPAIR_V2_EXTERNAL_RECHECK"
    d["s02_repair_stage"] = {
        "issue": "S02 / #37",
        "received_at": NOW,
        "baseline_commit": "547508d",
        "package": f"{REMED}/",
        "package_files_verified": "433/433",
        "review_file": REVIEW,
        "review_file_sha256": sha256(REVIEW),
        "review_nature": "REPAIR_ACCEPTANCE_REVIEW",
        "decision": "REPAIR_APPLIED_PENDING_EXTERNAL_RECHECK",
        "what_changed": [
            "重抽 59 家 360 份报告：整数金额、脚注混入、跨页单位、百分比错列",
            "标准化表 228,155 → 229,032 行；指标层 398 格 / 46 家变化",
            "53 家：32 家恢复≥8 字段，21 家保留待核（不得当无改善）",
            "L0 补 addendum：EVALUABLE 664 / W5 387 / W9 3，125,970 向量穷举",
        ],
        "independent_verification": {
            "cells_recomputed": 12648,
            "diff_vs_package_s02": 0,
            "counts_match": True,
            "l0_match": True,
            "cases_checked": ["美的集团 M05=-25.31%", "传智教育 M06=16.36pp",
                              "复星医药 M05=0.19", "石头科技 全 PROVISIONAL",
                              "赣锋锂业 M06=19.26pp"],
            "q17_magnitude_suspects_before": 5,
            "q17_magnitude_suspects_after": 0,
        },
        "not_independently_verified": [
            "19 条原页预期未逐条回读 PDF",
            "360 份源 PDF 的 SHA256 未逐个复算",
            "a03 采集器 158 行改动只做方向审查",
        ],
        "release_S03": False,
        "release_note": "S03 须等修复版外部复核；本次只是执行方接手复核",
    }
    d["current_valid_versions"] = {
        "S00_data": {
            "v1_frozen": "runs/issues/S00/financial_normalized.csv.gz",
            "v2_repair": f"{REMED}/s00/financial_normalized.csv",
            "v2_sha256": man["normalized_input_used"]["sha256"],
            "use_for_S03": "v2_repair",
        },
        "S02_metrics": {
            "v1": "runs/issues/S02/all_pool_metrics.csv",
            "v2_repair": f"{REMED}/s02/all_pool_metrics.csv",
            "recheck": f"{REMED}/s02_recheck/all_pool_metrics.csv",
            "use_for_S03": "v2_repair",
        },
        "rules": {
            "base": "S01_SCREEN_RULES_V2",
            "addendum": "S01_SCREEN_RULES_V2_L0_ADDENDUM_20261029",
            "note": "只加 L0 分支，未改指标公式与信号阈值",
        },
    }
    d["s02_stage"]["status"] = "SELF_CHECK_PASS_REPAIR_V2"
    d["s02_stage"]["repair_applied"] = True
    d["s02_stage"]["release_S03"] = False
    dump(p, d)


def update_active_issue() -> None:
    p = "data/active_issue.json"
    d = load(p)
    d["status"] = "REPAIR_V2_APPLIED_AWAITING_EXTERNAL_RECHECK"
    d["claim_note"] = (
        "已接手修复包：433/433 文件校验通过，用包内 s00 独立重算 12,648 格与包内 s02 输出 0 差异，"
        "状态分布与 L0 分布逐项一致；S03 仍锁，等外部复核。"
    )
    d["last_completed"] = {
        "issue_number": 37,
        "issue_key": "S02",
        "completed_at": NOW,
        "review_file": REVIEW,
        "decision": "REPAIR_APPLIED_PENDING_EXTERNAL_RECHECK",
        "review_nature": "REPAIR_ACCEPTANCE_REVIEW",
        "acceptance": "433/433 包校验 + 12,648 格独立重算 0 差异 + L0 664/387/3 一致",
        "summary": "修复版接管为 S02 v2；21 家待核保留；S03 未放行",
    }
    d["next_recommended_issue_number"] = 37
    d["next_recommended_issue_key"] = "S02"
    d["next_recommended_reason"] = (
        "等 S02 修复版外部复核；复核通过后 S03 须用 v2 输入 + L0 addendum 开工"
    )
    dump(p, d)


def main() -> None:
    man = load(V2_MANIFEST)
    changed = update_plan_csv()
    update_plan_json(man)
    update_project_state(man)
    update_active_issue()
    print(json.dumps({"updated": changed, "at": NOW,
                      "v2_input_sha256": man["normalized_input_used"]["sha256"]},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
