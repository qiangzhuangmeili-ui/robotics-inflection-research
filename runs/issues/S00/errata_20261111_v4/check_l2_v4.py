#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""S00 勘误 V4 → 全池影响判定（1054 家）

对 Codex 第四轮裁决的落实：
- 依赖改为调用 l2_core.dependency_keys：单季字段递归展开累计父键，不再只加期间；
- 补充元数据（extra_meta_diff）接入下游争议传播，不再被忽略；
- 名单外分层改用「争议键是否落在任一候选指标的完整依赖内」；
- 受限表补 snapshot_hash，dispute_id 绑定差异类型与元数据字段。
"""
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

import l2_core as core

ROOT = core.ROOT
OUT = ROOT / "runs/issues/S00/errata_20261111_v4"
SNAPSHOT = ROOT / "runs/issues/S04/tight_pass.csv"
SNAPSHOT_SHA = hashlib.sha256(SNAPSHOT.read_bytes()).hexdigest()

SG_METRIC, SG_DIM = core.load_rules(ROOT / "runs/issues/S01/screen_rules_v2.json")
ALARM = ("HOLD", "MISMATCH", "PROVISIONAL", "CONFLICT", "MISSING", "ABSENT", "UNDEFINED")
EXTRA_CLASSES = {"AFFECTS_VALUE", "AFFECTS_QUALIFICATION", "AFFECTS_TIMING_OR_PROVENANCE"}


def is_open(res):
    return res.startswith("UNRESOLVED") or res.startswith("PENDING")


def is_alarm(v):
    return any(a in (v or "").upper() for a in ALARM)


disputes = defaultdict(list)
with open(OUT / "cell_diff.csv", encoding="utf-8-sig", newline="") as f:
    for r in csv.DictReader(f):
        if is_open(r["resolution"]):
            disputes[(r["security_id"], r["field_id"], r["period_key"])].append(
                "VALUE:%s" % r["resolution"])
with open(OUT / "key_diff.csv", encoding="utf-8-sig", newline="") as f:
    for r in csv.DictReader(f):
        if is_open(r["resolution"]):
            k = (r["security_id"], r["field_id"], r["period_key"])
            tag = "ADD_UNBACKED" if r["resolution"].endswith("UNBACKED_ADDITION") else "KEY:%s" % r["resolution"]
            disputes[k].append(tag)
with open(OUT / "meta_diff.csv", encoding="utf-8-sig", newline="") as f:
    for r in csv.DictReader(f):
        if not is_open(r["resolution"]):
            continue
        k = (r["security_id"], r["field_id"], r["period_key"])
        if r["meta_field"] == "restatement_flag":
            disputes[k].append("RESTATEMENT:%s" % r["resolution"].replace("UNRESOLVED_", "").replace("PENDING_", ""))
        elif is_alarm(r["value_A"]) and not is_alarm(r["value_B"]):
            disputes[k].append("RELEASE")
        else:
            disputes[k].append("META:%s:%s" % (r["meta_field"], r["resolution"].replace("UNRESOLVED_", "")))

extra_by_key = defaultdict(list)
with open(OUT / "extra_meta_diff.csv", encoding="utf-8-sig", newline="") as f:
    for r in csv.DictReader(f):
        if r["class"] not in EXTRA_CLASSES or not is_open(r["resolution"]):
            continue
        k = (r["security_id"], r["field_id"], r["period_key"])
        disputes[k].append("EXTRA:%s:%s" % (r["meta_field"], r["class"]))
        extra_by_key[k].append((r["meta_field"], r["class"]))

print("争议键:", len(disputes), "其中含补充元数据:", len(extra_by_key))

universe = {}
for part in ("wide_pass", "wide_defer", "wide_unknown"):
    with open(ROOT / f"runs/issues/S03/rerun_20261106/{part}.csv",
              encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            universe[r["company_id"]] = {"name": r.get("company_name", ""),
                                         "anchor": r.get("anchor_period", ""),
                                         "partition": part}

pass_rows = {}
with open(SNAPSHOT, encoding="utf-8-sig", newline="") as f:
    for r in csv.DictReader(f):
        pass_rows[r["company_id"]] = r

rows, restricted = [], []
for sec in sorted(universe):
    anchor = universe[sec]["anchor"]
    p = pass_rows.get(sec)
    if p:
        sgs = [x for x in (p.get("qualified_sg") or "").split(";") if x]
        ok_dims, hit_dims, detail = set(), set(), []
        for sg in sgs:
            mid = SG_METRIC.get(sg, "")
            hits = []
            for fld, pk in sorted(core.dependency_keys(mid, anchor)):
                if (sec, fld, pk) in disputes:
                    gap = "/".join(sorted(set(disputes[(sec, fld, pk)])))
                    hits.append("%s@%s[%s]" % (fld, pk, gap))
                    restricted.append({
                        "security_id": sec, "stock_name": universe[sec]["name"],
                        "snapshot": "runs/issues/S04/tight_pass.csv",
                        "snapshot_hash": SNAPSHOT_SHA,
                        "anchor_period": anchor,
                        "signal_id": sg, "dimension": SG_DIM.get(sg, ""),
                        "metric_id": mid,
                        "field_id": fld, "period_key": pk,
                        "dispute_id": "%s|%s|%s|%s" % (
                            sec, fld, pk, "|".join(sorted(set(disputes[(sec, fld, pk)])))),
                        "evidence_gap": gap,
                        "restriction": "该结论不得作为 S05 有效输入或名单验收依据",
                        "allowed_use": "历史复现；不作为入选/漏筛判定依据",
                        "release_condition": "争议字段取得可复核依据并经独立验收",
                        "review_status": "PENDING",
                    })
            if hits:
                hit_dims.add(SG_DIM.get(sg, ""))
                detail.append("%s=%s" % (sg, "|".join(hits)))
            else:
                ok_dims.add(SG_DIM.get(sg, ""))
        if not hit_dims:
            verdict = "NOT_AFFECTED"
        elif len(ok_dims) >= 2:
            verdict = "STILL_PASSES_WITHOUT"
        else:
            verdict = "HOLD_PENDING_ERRATA"
        rows.append({
            "security_id": sec, "stock_name": universe[sec]["name"],
            "in_s04_pass": "YES", "anchor_period": anchor,
            "qualified_sg": p.get("qualified_sg", ""),
            "qualified_dims": p.get("qualified_dims", ""),
            "n_dims_undisputed": len(ok_dims),
            "disputed_dims": ";".join(sorted(x for x in hit_dims if x)),
            "dispute_detail": ";".join(detail),
            "verdict": verdict,
        })
    else:
        linked = unlinked = 0
        for k in disputes:
            if k[0] != sec:
                continue
            fld, pk = k[1], k[2]
            hit = False
            for mid in core.METRIC_FIELDS:
                if (fld, pk) in core.dependency_keys(mid, anchor):
                    hit = True
                    break
            if hit:
                linked += 1
            else:
                unlinked += 1
        if linked:
            verdict = "R2_MAY_CHANGE"
        elif unlinked:
            verdict = "R3_PENDING"
        else:
            verdict = "R1_NO_LINK"
        rows.append({
            "security_id": sec, "stock_name": universe[sec]["name"],
            "in_s04_pass": "NO", "anchor_period": anchor,
            "qualified_sg": "", "qualified_dims": "",
            "n_dims_undisputed": 0, "disputed_dims": "",
            "dispute_detail": "linked=%d unlinked=%d" % (linked, unlinked),
            "verdict": verdict,
        })

with open(OUT / "l2_dependency_check.csv", "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()), lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
with open(OUT / "restricted_claims.csv", "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(restricted[0].keys()), lineterminator="\n")
    w.writeheader()
    w.writerows(restricted)

c = Counter(r["verdict"] for r in rows)
print("全池 %d 家:" % len(rows), dict(c))
print("受限声明行:", len(restricted))
print("\nHOLD:")
for r in rows:
    if r["verdict"] == "HOLD_PENDING_ERRATA":
        print("  %-11s %-8s %-16s %s" % (r["security_id"], r["stock_name"],
                                         r["disputed_dims"], r["dispute_detail"][:80]))

summary = {
    "scope": "全池 1054 家 vs S00 V4 未闭合/待核差异（含 19 列补充元数据）",
    "generated_at": "2026-11-11T23:55:00+08:00",
    "nature": "SELF_CHECK",
    "snapshot": {"path": "runs/issues/S04/tight_pass.csv", "sha256": SNAPSHOT_SHA,
                 "companies": len(pass_rows)},
    "dependency": {
        "engine": "runs/issues/S00/errata_20261111_v4/l2_core.py:dependency_keys",
        "period_rule": {"M03": "t, t-1q, t-1y, t-1y-1q", "others": "t, t-1y"},
        "parent_rule": "单季字段递归展开累计父键 YTD(t)、YTD(t-1q)，直到无父字段",
        "extra_meta_included": True,
    },
    "verdicts": dict(c),
    "hold_list": [{"security_id": r["security_id"], "stock_name": r["stock_name"],
                   "disputed_dims": r["disputed_dims"], "detail": r["dispute_detail"]}
                  for r in rows if r["verdict"] == "HOLD_PENDING_ERRATA"],
    "still_passes": [r["security_id"] for r in rows if r["verdict"] == "STILL_PASSES_WITHOUT"],
    "restricted_claim_rows": len(restricted),
    "note": ("未闭合含 PENDING_*（待核不计已闭合）；未回读原文；"
             "未覆盖锚定期回退与上游准入的间接依赖。SELF_CHECK。"),
}
(OUT / "l2_dependency_summary.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("\n已写 l2_dependency_check.csv / restricted_claims.csv / l2_dependency_summary.json")
