#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""S00 勘误 → 影响判定 v2（全池 1054 家）

修正 Codex 第二轮指出的依赖期间缺陷：
- SG02 使用 M03（单季营收加速度）= M02(t) − M02(t−1q)，
  依赖 {t, t−1q, t−1y, t−1y−1q} 四个季度，v1 只查了两个。
- WEAK 依据（ASSUMED_NO_PENDING_REVIEW）与 UNBACKED_ADDITION 均计入争议。

判定分级（445 家名单内）：
- NOT_AFFECTED            所有依赖信号未触及争议
- STILL_PASSES_WITHOUT    部分信号争议，但剔除后仍 ≥2 维度成立
- HOLD_PENDING_ERRATA     剩余可支撑维度 <2

名单外公司另标 POTENTIAL_MISS_RISK（有争议但未入选，供后续核原文）。
"""
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "runs/issues/S00/errata_20261111"

METRIC_FIELDS = {
    "M01": ["FIN.REV.YTD"], "M02": ["FIN.REV.SQ"], "M03": ["FIN.REV.SQ"],
    "M04": ["FIN.GROSSMARGIN.PCT", "FIN.REV.YTD", "FIN.COST.YTD"],
    "M05": ["FIN.NPDEDT.YTD"], "M06": ["FIN.NPDEDT.YTD", "FIN.REV.YTD"],
    "M07": ["FIN.NPDEDT.SQ"], "M08": ["FIN.OCF.YTD", "FIN.NPP.YTD"],
    "M09": ["FIN.OCF.YTD"], "M10": ["FIN.AR.INSTANT", "FIN.REV.YTD"],
    "M11": ["FIN.INV.INSTANT", "FIN.COST.YTD"],
    "M12": ["FIN.CONTRACTASSET.INSTANT", "FIN.REV.YTD"],
}
# 需要前季的指标（加速度类）
NEEDS_PREV_Q = {"M03"}
ALARM = ("HOLD", "MISMATCH", "PROVISIONAL", "CONFLICT", "MISSING", "ABSENT", "UNDEFINED")

rules = json.loads((ROOT / "runs/issues/S01/screen_rules_v2.json").read_text(encoding="utf-8"))
SG_METRIC = {s["id"]: s["metric"] for s in rules["signals"]}
SG_DIM = {s["id"]: s["dimension"] for s in rules["signals"]}


def prev_year(pk):
    return str(int(pk[:4]) - 1) + pk[4:]


QMAP = {"0331": "1231", "0630": "0331", "0930": "0630", "1231": "0930"}


def prev_quarter(pk):
    tail = pk[4:]
    if tail == "0331":
        return str(int(pk[:4]) - 1) + "1231"
    return pk[:4] + QMAP[tail]


def periods_for(mid, anchor):
    if mid in NEEDS_PREV_Q:
        q = prev_quarter(anchor)
        return {anchor, q, prev_year(anchor), prev_year(q)}
    return {anchor, prev_year(anchor)}


def is_open(res):
    return res.startswith("UNRESOLVED") or res.endswith("_WEAK")


def is_alarm(v):
    return any(a in (v or "").upper() for a in ALARM)


disputes = defaultdict(list)
fills = defaultdict(int)

with open(OUT / "cell_diff.csv", encoding="utf-8-sig", newline="") as f:
    for r in csv.DictReader(f):
        if is_open(r["resolution"]):
            disputes[(r["security_id"], r["field_id"], r["period_key"])].append(
                "VALUE:%s" % r["resolution"])

with open(OUT / "key_diff.csv", encoding="utf-8-sig", newline="") as f:
    for r in csv.DictReader(f):
        k = (r["security_id"], r["field_id"], r["period_key"])
        if r["resolution"] == "UNRESOLVED_UNBACKED_ADDITION":
            disputes[k].append("ADD_UNBACKED")
        elif is_open(r["resolution"]):
            disputes[k].append("KEY:%s" % r["resolution"])

with open(OUT / "meta_diff.csv", encoding="utf-8-sig", newline="") as f:
    for r in csv.DictReader(f):
        if not is_open(r["resolution"]):
            continue
        k = (r["security_id"], r["field_id"], r["period_key"])
        if r["meta_field"] == "restatement_flag":
            disputes[k].append("RESTATEMENT")
        elif is_alarm(r["value_A"]) and not is_alarm(r["value_B"]):
            disputes[k].append("RELEASE")
        else:
            disputes[k].append("META:%s" % r["meta_field"])

print("争议键:", len(disputes))

# 全池：从 S03 三分区取公司与锚定期
universe = {}
for part in ("wide_pass", "wide_defer", "wide_unknown"):
    with open(ROOT / f"runs/issues/S03/rerun_20261106/{part}.csv",
              encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            universe[r["company_id"]] = {
                "name": r.get("company_name", ""),
                "anchor": r.get("anchor_period", ""),
                "partition": part,
            }

pass_rows = {}
with open(ROOT / "runs/issues/S04/tight_pass.csv", encoding="utf-8-sig", newline="") as f:
    for r in csv.DictReader(f):
        pass_rows[r["company_id"]] = r

rows = []
for sec in sorted(universe):
    anchor = universe[sec]["anchor"]
    p = pass_rows.get(sec)
    if p:
        sgs = [x for x in (p.get("qualified_sg") or "").split(";") if x]
        ok_dims, hit_dims, detail = set(), set(), []
        for sg in sgs:
            mid = SG_METRIC.get(sg, "")
            hits = []
            for fld in METRIC_FIELDS.get(mid, []):
                for pk in sorted(periods_for(mid, anchor)):
                    if (sec, fld, pk) in disputes:
                        hits.append("%s@%s[%s]" % (
                            fld, pk, "/".join(sorted(set(disputes[(sec, fld, pk)])))))
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
        # 名单外：只要有争议依赖就标潜在漏筛风险
        n = sum(1 for k in disputes if k[0] == sec)
        rows.append({
            "security_id": sec, "stock_name": universe[sec]["name"],
            "in_s04_pass": "NO", "anchor_period": anchor,
            "qualified_sg": "", "qualified_dims": "",
            "n_dims_undisputed": 0, "disputed_dims": "",
            "dispute_detail": "%d 个争议键" % n if n else "",
            "verdict": "POTENTIAL_MISS_RISK" if n else "OUT_OF_LIST_CLEAN",
        })

with open(OUT / "l2_dependency_check.csv", "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()), lineterminator="\n")
    w.writeheader()
    w.writerows(rows)

c = Counter(r["verdict"] for r in rows)
print("全池 %d 家判定:" % len(rows), dict(c))
print("\nHOLD 明细:")
for r in rows:
    if r["verdict"] == "HOLD_PENDING_ERRATA":
        print("  %-11s %-8s dims=%-8s 争议维度=%-20s %s" % (
            r["security_id"], r["stock_name"], r["qualified_dims"],
            r["disputed_dims"], r["dispute_detail"][:120]))

summary = {
    "scope": "全池 1054 家 vs S00 未闭合差异（含 WEAK 与无依据新增）",
    "generated_at": "2026-11-11T18:40:00+08:00",
    "nature": "SELF_CHECK",
    "period_rule": {
        "M03": "t, t-1q, t-1y, t-1y-1q（加速度需四季）",
        "others": "t, t-1y",
    },
    "verdicts": dict(c),
    "hold_list": [{"security_id": r["security_id"], "stock_name": r["stock_name"],
                   "disputed_dims": r["disputed_dims"], "detail": r["dispute_detail"]}
                  for r in rows if r["verdict"] == "HOLD_PENDING_ERRATA"],
    "still_passes_count": c.get("STILL_PASSES_WITHOUT", 0),
    "potential_miss_count": c.get("POTENTIAL_MISS_RISK", 0),
    "note": ("争议判定含 UNRESOLVED_* 与 WEAK、UNBACKED_ADDITION；"
             "未回读原文，未覆盖锚定期回退路径的间接依赖。SELF_CHECK。"),
}
(OUT / "l2_dependency_summary.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("\n已写 l2_dependency_check.csv / l2_dependency_summary.json")
