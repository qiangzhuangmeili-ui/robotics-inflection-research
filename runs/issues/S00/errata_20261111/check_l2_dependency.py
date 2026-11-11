#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""S00 勘误 → S04 名单依赖判定（v2，区分「B 补行」与「真争议」）

修正 v1 的逻辑错误：把 ONLY_B 键差异一律当争议，导致 2 家假警报。
A 里没有该行、B 补上，不构成「两版冲突」；真正需要解释的是：
  1. 值差异（A 有值、B 有值、两者不同）
  2. 状态解除（A 为 HOLD / 勾稽不符 / PROVISIONAL，B 变为正常）
  3. A 有行、B 删除（B 少了数据）
  4. 重述标记变化且无核验依据
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
ALARM = ("HOLD", "MISMATCH", "PROVISIONAL", "CONFLICT", "MISSING", "ABSENT", "UNDEFINED")

rules = json.loads((ROOT / "runs/issues/S01/screen_rules_v2.json").read_text(encoding="utf-8"))
SG_METRIC = {s["id"]: s["metric"] for s in rules["signals"]}
SG_DIM = {s["id"]: s["dimension"] for s in rules["signals"]}


def is_alarm(v):
    return any(a in (v or "").upper() for a in ALARM)


disputes = defaultdict(list)
fills = defaultdict(int)

with open(OUT / "cell_diff.csv", encoding="utf-8-sig", newline="") as f:
    for r in csv.DictReader(f):
        if r["resolution"].startswith("UNRESOLVED"):
            disputes[(r["security_id"], r["field_id"], r["period_key"])].append(
                ("DISPUTED_VALUE", "A=%s B=%s 符号翻=%s" % (
                    r["value_A"][:16], r["value_B"][:16], r["sign_flip"])))

with open(OUT / "key_diff.csv", encoding="utf-8-sig", newline="") as f:
    for r in csv.DictReader(f):
        k = (r["security_id"], r["field_id"], r["period_key"])
        if r["side"] == "ONLY_B":
            fills[k] += 1
        elif r["resolution"].startswith("UNRESOLVED"):
            disputes[k].append(("DISPUTED_DROP", "A 有行、B 无"))

with open(OUT / "meta_diff.csv", encoding="utf-8-sig", newline="") as f:
    for r in csv.DictReader(f):
        if not r["resolution"].startswith("UNRESOLVED"):
            continue
        k = (r["security_id"], r["field_id"], r["period_key"])
        if r["meta_field"] == "restatement_flag":
            disputes[k].append(("DISPUTED_RESTATEMENT",
                                "A=%s B=%s" % (r["value_A"][:20], r["value_B"][:8])))
        elif is_alarm(r["value_A"]) and not is_alarm(r["value_B"]):
            disputes[k].append(("DISPUTED_RELEASE",
                                "A=%s B=%s" % (r["value_A"][:24], r["value_B"][:16])))

print("争议键:", len(disputes), " B 补行键:", len(fills))


def prev_year(pk):
    return str(int(pk[:4]) - 1) + pk[4:]


rows = []
with open(ROOT / "runs/issues/S04/tight_pass.csv", encoding="utf-8-sig", newline="") as f:
    for r in csv.DictReader(f):
        sec = r["company_id"]
        anchor = r.get("anchor_period", "")
        sgs = [x for x in (r.get("qualified_sg") or "").split(";") if x]
        periods = {anchor, prev_year(anchor)} if anchor else set()
        ok_dims, hit_dims = set(), set()
        detail = []
        for sg in sgs:
            mid = SG_METRIC.get(sg, "")
            hits = []
            for fld in METRIC_FIELDS.get(mid, []):
                for pk in periods:
                    for kind, d in disputes.get((sec, fld, pk), []):
                        hits.append("%s@%s[%s]" % (fld, pk, kind))
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
            "security_id": sec, "stock_name": r.get("company_name", ""),
            "anchor_period": anchor, "qualified_sg": r.get("qualified_sg", ""),
            "qualified_dims": r.get("qualified_dims", ""),
            "n_dims_total": len({SG_DIM.get(s, "") for s in sgs}),
            "n_dims_undisputed": len(ok_dims),
            "disputed_dims": ";".join(sorted(x for x in hit_dims if x)),
            "dispute_detail": ";".join(detail),
            "verdict": verdict,
        })

with open(OUT / "l2_dependency_check.csv", "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()), lineterminator="\n")
    w.writeheader()
    w.writerows(rows)

c = Counter(r["verdict"] for r in rows)
print("445 家判定:", dict(c))
for r in rows:
    if r["verdict"] != "NOT_AFFECTED":
        print("  %-11s %-8s %-20s 争议维度=%-22s %s" % (
            r["security_id"], r["stock_name"], r["verdict"],
            r["disputed_dims"], r["dispute_detail"][:110]))

summary = {
    "scope": "S04 tight_pass 445 家 vs S00 真争议差异",
    "generated_at": "2026-11-11T16:05:00+08:00",
    "nature": "SELF_CHECK",
    "logic": {
        "DISPUTED_VALUE": "值差异无依据",
        "DISPUTED_RELEASE": "A 为告警态、B 解除告警，无依据",
        "DISPUTED_DROP": "A 有行、B 删除，无依据",
        "DISPUTED_RESTATEMENT": "重述标记变化不在核验范围",
        "B_ONLY_FILL": "B 补行，不计争议",
    },
    "verdicts": dict(c),
    "hold_list": [{"security_id": r["security_id"], "stock_name": r["stock_name"],
                   "disputed_dims": r["disputed_dims"],
                   "detail": r["dispute_detail"]}
                  for r in rows if r["verdict"] == "HOLD_PENDING_ERRATA"],
    "note": ("仅检查当期与上年同期的直接依赖；未覆盖最新可用期选择等间接依赖，"
             "未回读原文。SELF_CHECK，不替代独立复核。"),
}
(OUT / "l2_dependency_summary.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("\n已更新 l2_dependency_check.csv / l2_dependency_summary.json")
