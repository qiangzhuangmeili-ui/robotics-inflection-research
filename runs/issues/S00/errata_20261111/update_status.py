#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""更新 S00 勘误与 S04 等待状态到 active_issue.json 与执行计划表。"""
import csv
import io
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]

# ---- manifest 路径分隔符修正
mp = ROOT / "runs/issues/S00/errata_20261111/manifest.json"
m = json.loads(mp.read_text(encoding="utf-8"))
for x in m["files"]:
    x["path"] = x["path"].replace("\\", "/")
mp.write_text(json.dumps(m, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("manifest paths fixed:", m["files"][0]["path"])

# ---- active_issue.json
ap = ROOT / "data/active_issue.json"
a = json.loads(ap.read_text(encoding="utf-8"))

a["s00_errata"] = {
    "stage": "ERRATA",
    "issue_key": "S00",
    "directory": "runs/issues/S00/errata_20261111/",
    "supersession": "runs/issues/S00/supersession.json",
    "executor": "WorkBuddy AI",
    "review_nature": "SELF_CHECK",
    "decision": "SELF_CHECK_PASS_WITH_UNRESOLVED_ITEMS",
    "reviewed_at": "2026-11-11T16:20:00+08:00",
    "trigger": "发现 A(S00 交付件) 与 B(s00_v10) 并存且数值冲突；Codex 裁决要求补做限定范围的 S00 勘误验收",
    "authoritative_input": {
        "path": "runs/issues/S02/hangcha_restated_20261101/s00_v10/s00_v10.csv.gz",
        "sha256": "fc312c52ace51feb37593c08cb8077c8a47012a7a239ef639d0fe8b745fe2025",
    },
    "superseded_input": {
        "path": "runs/issues/S00/financial_normalized.csv",
        "sha256": "a1f27f1ceacfba10d709101d24b819e8bf6a86dfdd546aa1c56ac53825ff1fc6",
        "status": "SUPERSEDED_DO_NOT_CONSUME",
    },
    "lineage": "A(228,155) → v7(229,393) → v9(229,666) → B(229,667)",
    "diff_totals": {
        "value": 240, "key": 2056, "meta": 17728,
        "resolved": 14324, "unresolved": 5700,
        "value_unresolved": 28, "key_unresolved": 374, "meta_unresolved": 5298,
        "sign_flip": 89,
    },
    "downstream": {
        "companies_with_diff": 419,
        "in_s04_list_with_diff": 175,
        "l2_not_affected": 443,
        "l2_hold_pending_errata": 2,
        "hold_list": ["SH:688320 禾川科技", "SH:688518 联赢激光"],
    },
    "checks": "12/12 PASS",
    "reproducible": True,
    "limits": [
        "未回读 PDF、未修改任何数据文件",
        "5,700 条未解决项未做原文核验",
        "未覆盖最新可用期选择等间接依赖",
        "自检不等同独立验收",
    ],
    "report": "runs/issues/S00/errata_20261111/REPORT.md",
    "handoff": "runs/issues/S00/errata_20261111/handoff.md",
}

a["status"] = "S00_ERRATA_SELF_CHECK_PASS_WITH_UNRESOLVED_ITEMS"
a["claim_note"] = ("S00 勘误台账完成：20,024 条差异逐条定性，14,324 有依据、5,700 未解决；"
                   "445 家中 443 家 L2 结论不受影响，禾川科技/联赢激光待勘误闭合。"
                   "S04 第二轮复核与 S00 补充验收均未完成，S05 不放行")
a["next_recommended_issue_key"] = "S00_ERRATA_REVIEW"
a["next_recommended_issue_number"] = 35
a["next_recommended_reason"] = (
    "按 Codex 裁决顺序：先完成 S00 勘误的独立补充验收（重点 2 家 HOLD、475 行弱依据、"
    "5,073 行未覆盖重述），再完成 S04 第二轮外部复核；S05 保持 WAITING_DEPENDENCIES")

if "s04_stage" in a:
    a["s04_stage"]["waiting_reason"] = (
        "S00 勘误发现 2 家名单内公司（禾川科技 SH:688320、联赢激光 SH:688518）的 L2 通过"
        "依赖无依据的告警解除，须待勘误闭合后重新确认；其余 443 家结论不受未解决差异影响")
    a["s04_stage"]["s00_errata_ref"] = "runs/issues/S00/errata_20261111/"
    a["s04_stage"]["release_S05"] = False

ap.write_text(json.dumps(a, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("active_issue.json updated")

# ---- 计划表 csv
cp = ROOT / "data/issue_execution_plan.csv"
raw = cp.read_text(encoding="utf-8-sig")
rows = list(csv.DictReader(io.StringIO(raw)))
cols = list(rows[0].keys())
found = False
for r in rows:
    if r["key"] == "S00":
        r["status"] = "ERRATA_SELF_CHECK_PASS_WITH_UNRESOLVED_ITEMS"
        r["review_record"] = "runs/issues/S00/errata_20261111/review.json"
        found = True
buf = io.StringIO()
w = csv.DictWriter(buf, fieldnames=cols, lineterminator="\n")
w.writeheader()
w.writerows(rows)
cp.write_text("\ufeff" + buf.getvalue(), encoding="utf-8")
print("plan csv updated, S00 found:", found)
for r in rows:
    if r["key"] in ("S00", "S04", "S05"):
        print(" ", r["key"], r["status"])

# ---- 计划 json
jp = ROOT / "data/issue_execution_plan.json"
d = json.loads(jp.read_text(encoding="utf-8"))
for t in d["tasks"]:
    if t["key"] == "S00":
        t["status"] = "ERRATA_SELF_CHECK_PASS_WITH_UNRESOLVED_ITEMS"
        t["review_record"] = "runs/issues/S00/errata_20261111/review.json"
        t["errata_ref"] = "runs/issues/S00/errata_20261111/"
d["next_recommended_issue"] = 35
jp.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("plan json updated")
