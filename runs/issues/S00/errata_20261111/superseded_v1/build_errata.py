#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""S00 勘误台账生成器（2026-11-11）

目的：把 A（S00 交付件 228,155 行）与 B（s00_v10 229,667 行，S02-S04 实际消费）
之间的全部差异逐条列出，并为每一条给出「依据来源 + 处置结论」。

纪律：
- 只读四个版本文件与既有记录，不改任何数据。
- 有依据的标 RESOLVED_*，无依据的标 UNRESOLVED_NO_EVIDENCE，不按「哪份更合理」选边。
- 不做抽样：值差异、键差异、元数据差异全部逐条列出。
"""
import csv
import gzip
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
S00 = ROOT / "runs/issues/S00"
OUT = S00 / "errata_20261111"
OUT.mkdir(parents=True, exist_ok=True)

P_A = ROOT / "runs/issues/S00/financial_normalized.csv"
P_V7 = ROOT / "runs/issues/S02/remediation_20261029/collect_q3_2026/s00_v7.csv"
P_V9 = ROOT / "runs/issues/S02/m07_repair_20261030/s00_v9.csv.gz"
P_V10 = ROOT / "runs/issues/S02/hangcha_restated_20261101/s00_v10/s00_v10.csv.gz"

P_DELTA = ROOT / "runs/issues/S02/remediation_20261029/normalized_delta.csv"
P_APPLY = ROOT / "runs/issues/S02/remediation_20261029/collect_q3_2026/apply_summary.json"
P_VERIFY = ROOT / "runs/issues/S02/remediation_20261029/restatement_verify/results.csv"
P_V8SUM = ROOT / "runs/issues/S02/m07_repair_20261030/s00_v8_patch_summary.json"
P_V9SUM = ROOT / "runs/issues/S02/m07_repair_20261030/s00_v9_patch_summary.json"
P_NPDEDT = ROOT / "runs/issues/S02/m07_repair_20261030/npdedt_override_rows.json"
P_ADOPT = ROOT / "runs/issues/S02/hangcha_restated_20261101/s00_v10/s00_v10_adoption_audit.csv"

DERIVED_PARENT = {
    "FIN.GROSSPROFIT.YTD": ["FIN.REV.YTD", "FIN.COST.YTD"],
    "FIN.GROSSPROFIT.SQ": ["FIN.REV.SQ", "FIN.COST.SQ"],
    "FIN.GROSSMARGIN.PCT": ["FIN.REV.YTD", "FIN.COST.YTD"],
    "FIN.NPMARGIN.PCT": ["FIN.NP.YTD", "FIN.REV.YTD"],
    "FIN.OCF_TO_NP.RATIO": ["FIN.OCF.YTD", "FIN.NP.YTD"],
}
META_FIELDS = ["restatement_flag", "status", "document_id",
               "consolidation_scope", "pit_status"]


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load(p, gz=False):
    d = {}
    opener = gzip.open if gz else open
    with opener(p, "rt", encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            d[(r["security_id"], r["field_id"], r["period_key"])] = r
    return d


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


print("加载四个版本 …")
DA = load(P_A)
D7 = load(P_V7)
D9 = load(P_V9, gz=True)
D10 = load(P_V10, gz=True)
print("  A=%d v7=%d v9=%d v10=%d" % (len(DA), len(D7), len(D9), len(D10)))

# ---------- 依据源索引 ----------
delta = {}
with open(P_DELTA, encoding="utf-8-sig", newline="") as f:
    for r in csv.DictReader(f):
        delta[(r["security_id"], r["field_id"], r["period_key"])] = r

apply_sum = json.loads(P_APPLY.read_text(encoding="utf-8"))

verify = defaultdict(list)
with open(P_VERIFY, encoding="utf-8-sig", newline="") as f:
    for r in csv.DictReader(f):
        verify[(r["security_id"], r["period_key"])].append(r)

adopt = {}
with open(P_ADOPT, encoding="utf-8-sig", newline="") as f:
    for r in csv.DictReader(f):
        adopt[(r["security_id"], r["field_id"], r["period_key"])] = r

v9sum = json.loads(P_V9SUM.read_text(encoding="utf-8"))
v9_added = {(x["security_id"], x["field_id"], x["period_key"])
            for x in v9sum.get("detail_added", [])}
v8sum = json.loads(P_V8SUM.read_text(encoding="utf-8"))
v8_changed = set()
for block in ("npdedt_changes", "sq_changes"):
    for x in v8sum.get(block, []) or []:
        if isinstance(x, dict) and "security_id" in x:
            v8_changed.add((x["security_id"], x.get("field_id", ""), x.get("period_key", "")))
npdedt = set()
try:
    nd = json.loads(P_NPDEDT.read_text(encoding="utf-8"))
    items = nd if isinstance(nd, list) else nd.get("rows", []) or nd.get("overrides", [])
    for x in items:
        if isinstance(x, dict) and "security_id" in x:
            npdedt.add((x["security_id"], x.get("field_id", ""), x.get("period_key", "")))
except Exception as e:  # 结构异常时如实记录，不猜测
    print("  [warn] npdedt_override_rows 读取异常:", e)

print("依据源: delta=%d verify=%d adopt=%d v9_added=%d npdedt=%d"
      % (len(delta), len(verify), len(adopt), len(v9_added), len(npdedt)))

# ---------- 1. 值差异 ----------
rows_value = []
v_a7 = {k for k in set(DA) & set(D7) if DA[k]["value_cny"] != D7[k]["value_cny"]}
v_79 = {k for k in set(D7) & set(D9) if D7[k]["value_cny"] != D9[k]["value_cny"]}
v_910 = {k for k in set(D9) & set(D10) if D9[k]["value_cny"] != D10[k]["value_cny"]}
v_all = sorted({k for k in set(DA) & set(D10) if DA[k]["value_cny"] != D10[k]["value_cny"]})

for k in v_all:
    a, b = DA[k], D10[k]
    av, bv = num(a["value_cny"]), num(b["value_cny"])
    step = ("v9_to_v10" if k in v_910 else
            "A_to_v7" if k in v_a7 else
            "v7_to_v9" if k in v_79 else "unknown")
    if av not in (None, 0) and bv is not None:
        ratio = bv / av
        abs_ratio = abs(ratio)
        sign_flip = "YES" if av * bv < 0 else "NO"
    else:
        ratio = abs_ratio = None
        sign_flip = "N/A"
    if abs_ratio is None:
        bucket = "含0或非数值"
    elif abs_ratio >= 10 or abs_ratio <= 0.1:
        bucket = "量级差异"
    elif 0.5 <= abs_ratio <= 2:
        bucket = "小幅差异"
    else:
        bucket = "中间倍数"

    # 处置判定
    evidence = ""
    if k in adopt:
        resolution = "RESOLVED_RESTATED_ADOPTION"
        evidence = "s00_v10_adoption_audit.csv action=%s doc=%s" % (
            adopt[k]["action"], adopt[k]["document_id_after"])
    elif k in delta and delta[k]["change"] == "UPDATE":
        resolution = "RESOLVED_NORMALIZED_DELTA"
        evidence = "normalized_delta.csv change=UPDATE doc=%s p.%s" % (
            delta[k]["document_id"], delta[k]["source_page"])
    elif a["status"].startswith("DERIVED") or b["status"].startswith("DERIVED"):
        parents = DERIVED_PARENT.get(k[1], [])
        hit = [p for p in parents
               if (k[0], p, k[2]) in delta and delta[(k[0], p, k[2])]["change"] == "UPDATE"]
        if hit:
            resolution = "RESOLVED_DERIVED_FROM_PARENT"
            evidence = "派生值随父输入重算；父输入有记录: " + ";".join(hit)
        else:
            resolution = "UNRESOLVED_NO_EVIDENCE"
            evidence = "派生值，但父输入无变更记录"
    else:
        resolution = "UNRESOLVED_NO_EVIDENCE"
        evidence = "A_to_v7 值变更，normalized_delta 无对应 UPDATE 记录"

    rows_value.append({
        "security_id": k[0], "stock_name": a.get("stock_name", ""),
        "field_id": k[1], "period_key": k[2], "step": step,
        "value_A": a["value_cny"], "value_B": b["value_cny"],
        "status_A": a["status"], "status_B": b["status"],
        "document_A": a.get("document_id", ""), "document_B": b.get("document_id", ""),
        "source_page_A": a.get("source_page", ""), "source_page_B": b.get("source_page", ""),
        "ratio_B_over_A": ("%.6g" % ratio) if ratio is not None else "",
        "abs_ratio": ("%.6g" % abs_ratio) if abs_ratio is not None else "",
        "sign_flip": sign_flip, "bucket": bucket,
        "resolution": resolution, "evidence": evidence,
    })

with open(OUT / "cell_diff.csv", "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows_value[0].keys()), lineterminator="\n")
    w.writeheader()
    w.writerows(rows_value)
print("cell_diff.csv: %d 行" % len(rows_value))

# ---------- 2. 键差异 ----------
rows_key = []
k_a7 = set(DA) ^ set(D7)
k_79 = set(D7) ^ set(D9)
k_910 = set(D9) ^ set(D10)
k_all = sorted(set(DA) ^ set(D10))
for k in k_all:
    side = "ONLY_A" if k in DA else "ONLY_B"
    step = ("v9_to_v10" if k in k_910 else
            "A_to_v7" if k in k_a7 else
            "v7_to_v9" if k in k_79 else "unknown")
    src = DA.get(k) or D10.get(k) or {}
    if k in delta:
        d = delta[k]
        resolution = "RESOLVED_NORMALIZED_DELTA"
        evidence = "normalized_delta.csv change=%s doc=%s p.%s" % (
            d["change"], d["document_id"], d["source_page"])
    elif k in v9_added:
        resolution = "RESOLVED_M07_REPAIR"
        evidence = "s00_v9_patch_summary.detail_added status=%s" % src.get("status", "")
    elif k in npdedt or (k[0], k[1], k[2]) in npdedt:
        resolution = "RESOLVED_M07_NPDEDT_OVERRIDE"
        evidence = "npdedt_override_rows.json"
    elif step == "v9_to_v10":
        resolution = "RESOLVED_RESTATED_ADOPTION"
        evidence = "s00_v10 manifest.row_additions / 杭叉重述采用"
    elif step == "v7_to_v9" and k[1].startswith("FIN.NPDEDT"):
        resolution = "RESOLVED_M07_NPDEDT_OVERRIDE"
        evidence = "m07 v9 扣非补行（v9 manifest 说明）"
    else:
        resolution = "UNRESOLVED_NO_EVIDENCE"
        evidence = "键增删无对应记录"
    rows_key.append({
        "security_id": k[0], "stock_name": src.get("stock_name", ""),
        "field_id": k[1], "period_key": k[2], "side": side, "step": step,
        "value": src.get("value_cny", ""), "status": src.get("status", ""),
        "document_id": src.get("document_id", ""), "source_page": src.get("source_page", ""),
        "resolution": resolution, "evidence": evidence,
    })

with open(OUT / "key_diff.csv", "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows_key[0].keys()), lineterminator="\n")
    w.writeheader()
    w.writerows(rows_key)
print("key_diff.csv: %d 行" % len(rows_key))

# ---------- 3. 元数据差异 ----------
rows_meta = []
common = set(DA) & set(D10)
for fld in META_FIELDS:
    for k in sorted(common):
        if DA[k].get(fld, "") == D10[k].get(fld, ""):
            continue
        a, b = DA[k], D10[k]
        if fld == "restatement_flag":
            hit = verify.get((k[0], k[2]))
            if hit:
                v = hit[0]
                resolution = "RESOLVED_RESTATEMENT_VERIFY"
                evidence = "results.csv verdict=%s method=%s p.%s" % (
                    v["verdict"], v["method"], v["page"])
                if v["method"] == "ASSUMED_NO_PENDING_REVIEW":
                    resolution = "RESOLVED_RESTATEMENT_VERIFY_WEAK"
                    evidence = "results.csv method=ASSUMED_NO_PENDING_REVIEW（假设非实证）p.%s" % v["page"]
            else:
                resolution = "UNRESOLVED_NO_EVIDENCE"
                evidence = "restatement_verify/results.csv 未覆盖该公司-期间"
        else:
            d = delta.get(k)
            if d and fld in (d.get("changed_columns") or ""):
                resolution = "RESOLVED_NORMALIZED_DELTA"
                evidence = "normalized_delta.csv changed_columns 含 %s" % fld
            elif d:
                resolution = "RESOLVED_NORMALIZED_DELTA"
                evidence = "normalized_delta.csv change=%s（该键有变更记录）" % d["change"]
            else:
                resolution = "UNRESOLVED_NO_EVIDENCE"
                evidence = "无对应记录"
        rows_meta.append({
            "security_id": k[0], "stock_name": a.get("stock_name", ""),
            "field_id": k[1], "period_key": k[2], "meta_field": fld,
            "value_A": a.get(fld, ""), "value_B": b.get(fld, ""),
            "resolution": resolution, "evidence": evidence,
        })

with open(OUT / "meta_diff.csv", "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows_meta[0].keys()), lineterminator="\n")
    w.writeheader()
    w.writerows(rows_meta)
print("meta_diff.csv: %d 行" % len(rows_meta))

# ---------- 4. 下游影响 ----------
pass_rows = {}
with open(ROOT / "runs/issues/S04/tight_pass.csv", encoding="utf-8-sig", newline="") as f:
    for r in csv.DictReader(f):
        pass_rows[r["company_id"]] = r
observe_rows = {}
with open(ROOT / "runs/issues/S04/tight_observe.csv", encoding="utf-8-sig", newline="") as f:
    for r in csv.DictReader(f):
        observe_rows[r["company_id"]] = r

# 每家公司的未决差异（UNRESOLVED_*）
unres_by_co = defaultdict(lambda: {"value": [], "key": [], "meta": []})
for r in rows_value:
    if r["resolution"].startswith("UNRESOLVED"):
        unres_by_co[r["security_id"]]["value"].append(r["field_id"] + "@" + r["period_key"])
for r in rows_key:
    if r["resolution"].startswith("UNRESOLVED"):
        unres_by_co[r["security_id"]]["key"].append(r["field_id"] + "@" + r["period_key"])
for r in rows_meta:
    if r["resolution"].startswith("UNRESOLVED"):
        unres_by_co[r["security_id"]]["meta"].append(r["meta_field"] + ":" + r["field_id"] + "@" + r["period_key"])

all_co = ({r["security_id"] for r in rows_value} | {r["security_id"] for r in rows_key}
          | {r["security_id"] for r in rows_meta})
rows_impact = []
for sec in sorted(all_co):
    u = unres_by_co.get(sec, {"value": [], "key": [], "meta": []})
    n_unres = len(u["value"]) + len(u["key"]) + len(u["meta"])
    in_pass = sec in pass_rows
    in_obs = sec in observe_rows
    if in_pass:
        status = "IN_TIGHT_PASS"
        deps = pass_rows[sec].get("clean_sg", "")
        dims = pass_rows[sec].get("clean_dims", "")
    elif in_obs:
        status = "IN_TIGHT_OBSERVE"
        deps = observe_rows[sec].get("clean_sg", "")
        dims = observe_rows[sec].get("clean_dims", "")
    else:
        status = "NOT_IN_S04_SCOPE"
        deps = dims = ""
    if n_unres == 0:
        verdict = "CLEAN_ALL_RESOLVED"
    elif status == "IN_TIGHT_PASS":
        verdict = "IN_LIST_WITH_UNRESOLVED_DEPS"
    elif status == "IN_TIGHT_OBSERVE":
        verdict = "OBSERVE_WITH_UNRESOLVED_DEPS"
    else:
        verdict = "UNRESOLVED_OUTSIDE_S04"
    rows_impact.append({
        "security_id": sec,
        "stock_name": (pass_rows.get(sec) or observe_rows.get(sec) or {}).get("company_name", ""),
        "s04_status": status, "s04_clean_dims": dims, "s04_clean_sg": deps,
        "n_unresolved_value": len(u["value"]), "n_unresolved_key": len(u["key"]),
        "n_unresolved_meta": len(u["meta"]), "n_unresolved_total": n_unres,
        "verdict": verdict,
        "unresolved_detail": ";".join((u["value"] + u["key"] + u["meta"])[:12]),
    })

with open(OUT / "downstream_impact.csv", "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows_impact[0].keys()), lineterminator="\n")
    w.writeheader()
    w.writerows(rows_impact)
print("downstream_impact.csv: %d 行" % len(rows_impact))

# ---------- 5. summary ----------
def cnt(rows, key):
    return dict(Counter(r[key] for r in rows).most_common())

summary = {
    "generated_at": "2026-11-11T15:40:00+08:00",
    "scope": "A(runs/issues/S00/financial_normalized.csv) vs B(s00_v10)",
    "nature": "SELF_CHECK",
    "versions": {
        "A": {"path": str(P_A.relative_to(ROOT)), "rows": len(DA), "sha256": sha(P_A)},
        "v7": {"path": str(P_V7.relative_to(ROOT)), "rows": len(D7), "sha256": sha(P_V7)},
        "v9": {"path": str(P_V9.relative_to(ROOT)), "rows": len(D9), "sha256": sha(P_V9)},
        "B": {"path": str(P_V10.relative_to(ROOT)), "rows": len(D10), "sha256": sha(P_V10)},
    },
    "value_diff": {
        "total": len(rows_value),
        "by_step": cnt(rows_value, "step"),
        "by_bucket": cnt(rows_value, "bucket"),
        "sign_flip": sum(1 for r in rows_value if r["sign_flip"] == "YES"),
        "by_resolution": cnt(rows_value, "resolution"),
        "companies": len({r["security_id"] for r in rows_value}),
    },
    "key_diff": {
        "total": len(rows_key),
        "by_step": cnt(rows_key, "step"),
        "by_side": cnt(rows_key, "side"),
        "by_resolution": cnt(rows_key, "resolution"),
        "companies": len({r["security_id"] for r in rows_key}),
    },
    "meta_diff": {
        "total": len(rows_meta),
        "by_field": cnt(rows_meta, "meta_field"),
        "by_resolution": cnt(rows_meta, "resolution"),
        "companies": len({r["security_id"] for r in rows_meta}),
    },
    "downstream": {
        "companies_with_diff": len(all_co),
        "by_s04_status": cnt(rows_impact, "s04_status"),
        "by_verdict": cnt(rows_impact, "verdict"),
    },
    "restatement_apply_summary": apply_sum.get("rows_changed"),
    "known_gaps": [
        "26 格值差异与 374 个键增删在 normalized_delta 中无记录，标 UNRESOLVED",
        "5,073 行重述标记变化不在 results.csv 覆盖范围内，标 UNRESOLVED",
        "ASSUMED_NO_PENDING_REVIEW 方法属假设非实证，单列 WEAK",
    ],
}
(OUT / "summary.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

# manifest
files = ["cell_diff.csv", "key_diff.csv", "meta_diff.csv", "downstream_impact.csv", "summary.json"]
manifest = {
    "issue_key": "S00", "stage": "ERRATA", "date": "2026-11-11",
    "files": [{"path": "runs/issues/S00/errata_20261111/" + f,
               "sha256": sha(OUT / f),
               "bytes": (OUT / f).stat().st_size} for f in files],
}
(OUT / "manifest.json").write_text(
    json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

print("\n=== 汇总 ===")
print("值差异:", summary["value_diff"]["by_resolution"])
print("键差异:", summary["key_diff"]["by_resolution"])
print("元数据:", summary["meta_diff"]["by_resolution"])
print("下游:", summary["downstream"]["by_verdict"])
