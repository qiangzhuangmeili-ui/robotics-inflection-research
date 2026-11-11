#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""S00 勘误 V3 → 全池影响判定（1054 家）

对 Codex 第三轮 Q4/Q2 的落实：
- 依赖期间：M03 需 t、t−1q、t−1y、t−1y−1q 四季；
- 单季派生值递归展开累计父输入：FIN.*.SQ 依赖同期间与前一季度的 FIN.*.YTD；
- 名单外公司不再一律标 POTENTIAL_MISS_RISK，改为三层：
  R1_NO_LINK        争议键不属于任何候选信号/期间
  R2_MAY_CHANGE     争议键落在候选信号依赖内，须核证重算
  R3_PENDING        争议键存在但依赖关系无法判定
- 另出受限名单 restricted_claims.csv（Codex Q1 字段）
"""
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "runs/issues/S00/errata_20261111_v3"

METRIC_FIELDS = {
    "M01": ["FIN.REV.YTD"], "M02": ["FIN.REV.SQ"], "M03": ["FIN.REV.SQ"],
    "M04": ["FIN.GROSSMARGIN.PCT", "FIN.REV.YTD", "FIN.COST.YTD"],
    "M05": ["FIN.NPDEDT.YTD"], "M06": ["FIN.NPDEDT.YTD", "FIN.REV.YTD"],
    "M07": ["FIN.NPDEDT.SQ"], "M08": ["FIN.OCF.YTD", "FIN.NPP.YTD"],
    "M09": ["FIN.OCF.YTD"], "M10": ["FIN.AR.INSTANT", "FIN.REV.YTD"],
    "M11": ["FIN.INV.INSTANT", "FIN.COST.YTD"], "M12": ["FIN.CONTRACTASSET.INSTANT", "FIN.REV.YTD"],
}
# 单季字段 -> 累计父字段（SQ(t) = YTD(t) − YTD(t−1q)，Q1 累计即单季）
SQ_PARENT = {
    "FIN.REV.SQ": "FIN.REV.YTD", "FIN.COST.SQ": "FIN.COST.YTD",
    "FIN.NPDEDT.SQ": "FIN.NPDEDT.YTD", "FIN.NPP.SQ": "FIN.NPP.YTD",
    "FIN.OCF.SQ": "FIN.OCF.YTD", "FIN.GROSSPROFIT.SQ": "FIN.GROSSPROFIT.YTD",
}
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


def field_periods(fld, mid, anchor):
    """字段级期间集合；单季字段追加累计父输入（t 与 t−1q）"""
    base = periods_for(mid, anchor)
    if fld in SQ_PARENT:
        extra = {anchor, prev_quarter(anchor)}
        return base | extra
    return base


def is_open(res):
    return res.startswith("UNRESOLVED")


def is_alarm(v):
    return any(a in (v or "").upper() for a in ALARM)


# ---------- 争议键 ----------
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
            disputes[k].append("RESTATEMENT:%s" % r["resolution"].replace("UNRESOLVED_", ""))
        elif is_alarm(r["value_A"]) and not is_alarm(r["value_B"]):
            disputes[k].append("RELEASE")
        else:
            disputes[k].append("META:%s" % r["meta_field"])

print("争议键:", len(disputes))

# ---------- 全池 ----------
universe = {}
for part in ("wide_pass", "wide_defer", "wide_unknown"):
    with open(ROOT / f"runs/issues/S03/rerun_20261106/{part}.csv",
              encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            universe[r["company_id"]] = {"name": r.get("company_name", ""),
                                         "anchor": r.get("anchor_period", ""),
                                         "partition": part}

pass_rows = {}
with open(ROOT / "runs/issues/S04/tight_pass.csv", encoding="utf-8-sig", newline="") as f:
    for r in csv.DictReader(f):
        pass_rows[r["company_id"]] = r

rows = []
restricted = []
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
                for pk in sorted(field_periods(fld, mid, anchor)):
                    if (sec, fld, pk) in disputes:
                        hits.append("%s@%s[%s]" % (
                            fld, pk, "/".join(sorted(set(disputes[(sec, fld, pk)])))))
                        restricted.append({
                            "security_id": sec, "stock_name": universe[sec]["name"],
                            "snapshot": "tight_pass.csv@445", "anchor_period": anchor,
                            "signal_id": sg, "dimension": SG_DIM.get(sg, ""),
                            "field_id": fld, "period_key": pk,
                            "dispute_id": "%s|%s|%s" % (sec, fld, pk),
                            "evidence_gap": "/".join(sorted(set(disputes[(sec, fld, pk)]))),
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
        # 名单外：判定争议键是否落在任一候选信号的依赖内
        mid_by_field = defaultdict(set)
        for mid, flds in METRIC_FIELDS.items():
            for fld in flds:
                mid_by_field[fld].add(mid)
        linked, unlinked = 0, 0
        for k in disputes:
            if k[0] != sec:
                continue
            fld, pk = k[1], k[2]
            mids = mid_by_field.get(fld, set())
            if not mids:
                unlinked += 1
                continue
            hit = False
            for mid in mids:
                if pk in field_periods(fld, mid, anchor):
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
        print("  %-11s %-8s 争议维度=%-16s %s" % (
            r["security_id"], r["stock_name"], r["disputed_dims"], r["dispute_detail"][:90]))

summary = {
    "scope": "全池 1054 家 vs S00 V3 未闭合差异",
    "generated_at": "2026-11-11T21:20:00+08:00",
    "nature": "SELF_CHECK",
    "period_rule": {
        "M03": "t, t-1q, t-1y, t-1y-1q（加速度需四季）",
        "SQ_FIELDS": "追加累计父输入 YTD(t) 与 YTD(t-1q)",
        "others": "t, t-1y",
    },
    "verdicts": dict(c),
    "hold_list": [{"security_id": r["security_id"], "stock_name": r["stock_name"],
                   "disputed_dims": r["disputed_dims"], "detail": r["dispute_detail"]}
                  for r in rows if r["verdict"] == "HOLD_PENDING_ERRATA"],
    "still_passes": [r["security_id"] for r in rows if r["verdict"] == "STILL_PASSES_WITHOUT"],
    "restricted_claim_rows": len(restricted),
    "note": ("争议含 UNRESOLVED_*；WEAK 计未闭合。未回读原文，未覆盖锚定期回退的间接依赖。SELF_CHECK。"),
}
(OUT / "l2_dependency_summary.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("\n已写 l2_dependency_check.csv / restricted_claims.csv / l2_dependency_summary.json")
