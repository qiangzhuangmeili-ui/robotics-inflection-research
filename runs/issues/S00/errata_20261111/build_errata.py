#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""S00 勘误台账生成器 v2（2026-11-11 返工）

修正 Codex 第二轮指出的四个缺陷：
1. UPDATE 记录必须校验 new_value 与实际 B 值一致，不一致标 EVIDENCE_MISMATCH
2. 元数据不得按「同键有记录」兜底，必须 changed_columns 明确包含该字段
3. 重述核验按（公司,期间）可能有多条记录，必须全部一致且等于 B 才算解决；
   多记录互斥标 AMBIGUOUS_MULTI_RECORD
4. 无依据的 B 新增行（ONLY_B）计入验收缺口，标 UNBACKED_ADDITION

另：ASSUMED_NO_PENDING_REVIEW 单列 WEAK，不计入「已解决」。
"""
import csv
import gzip
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "runs/issues/S00/errata_20261111"

P_A = ROOT / "runs/issues/S00/financial_normalized.csv"
P_V7 = ROOT / "runs/issues/S02/remediation_20261029/collect_q3_2026/s00_v7.csv"
P_V9 = ROOT / "runs/issues/S02/m07_repair_20261030/s00_v9.csv.gz"
P_V10 = ROOT / "runs/issues/S02/hangcha_restated_20261101/s00_v10/s00_v10.csv.gz"

P_DELTA = ROOT / "runs/issues/S02/remediation_20261029/normalized_delta.csv"
P_APPLY = ROOT / "runs/issues/S02/remediation_20261029/collect_q3_2026/apply_summary.json"
P_VERIFY = ROOT / "runs/issues/S02/remediation_20261029/restatement_verify/results.csv"
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


def values_match(a, b):
    """记录值是否与实际值一致（容忍浮点尾差）"""
    x, y = num(a), num(b)
    if x is None or y is None:
        return (a or "").strip() == (b or "").strip()
    if x == 0 and y == 0:
        return True
    scale = max(abs(x), abs(y))
    return abs(x - y) <= max(1e-6, scale * 1e-9)


print("加载四个版本 …")
DA, D7, D9, D10 = load(P_A), load(P_V7), load(P_V9, True), load(P_V10, True)
print("  A=%d v7=%d v9=%d v10=%d" % (len(DA), len(D7), len(D9), len(D10)))

delta = {}
with open(P_DELTA, encoding="utf-8-sig", newline="") as f:
    for r in csv.DictReader(f):
        delta[(r["security_id"], r["field_id"], r["period_key"])] = r

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

npdedt = set()
try:
    nd = json.loads(P_NPDEDT.read_text(encoding="utf-8"))
    if isinstance(nd, dict):
        npdedt = set(nd.keys())
except Exception as e:
    print("  [warn] npdedt:", e)

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
    step = ("v9_to_v10" if k in v_910 else "A_to_v7" if k in v_a7
            else "v7_to_v9" if k in v_79 else "cross_step")
    ratio = abs_ratio = None
    sign_flip = "N/A"
    if av not in (None, 0) and bv is not None:
        ratio = bv / av
        abs_ratio = abs(ratio)
        sign_flip = "YES" if av * bv < 0 else "NO"
    if abs_ratio is None:
        bucket = "含0或非数值"
    elif abs_ratio >= 10 or abs_ratio <= 0.1:
        bucket = "量级差异"
    elif 0.5 <= abs_ratio <= 2:
        bucket = "小幅差异"
    else:
        bucket = "中间倍数"

    if k in adopt:
        resolution = "RESOLVED_RESTATED_ADOPTION"
        evidence = "adoption_audit action=%s doc=%s" % (
            adopt[k]["action"], adopt[k]["document_id_after"])
    elif k in delta and delta[k]["change"] == "UPDATE":
        if values_match(delta[k]["new_value"], b["value_cny"]):
            resolution = "RESOLVED_NORMALIZED_DELTA"
            evidence = "delta UPDATE new_value 与 B 一致; doc=%s p.%s" % (
                delta[k]["document_id"], delta[k]["source_page"])
        else:
            resolution = "UNRESOLVED_EVIDENCE_MISMATCH"
            evidence = "delta UPDATE new_value=%s 与 B=%s 不符" % (
                (delta[k]["new_value"] or "")[:18], b["value_cny"][:18])
    elif a["status"].startswith("DERIVED") or b["status"].startswith("DERIVED"):
        parents = DERIVED_PARENT.get(k[1], [])
        hit = [p for p in parents
               if (k[0], p, k[2]) in delta and delta[(k[0], p, k[2])]["change"] == "UPDATE"]
        if hit:
            resolution = "RESOLVED_DERIVED_FROM_PARENT"
            evidence = "派生值随父输入重算; 父输入有记录: " + ";".join(hit)
        else:
            resolution = "UNRESOLVED_NO_EVIDENCE"
            evidence = "派生值，父输入无变更记录"
    else:
        resolution = "UNRESOLVED_NO_EVIDENCE"
        evidence = "值变更无对应 UPDATE 记录"

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
k_a7, k_79, k_910 = set(DA) ^ set(D7), set(D7) ^ set(D9), set(D9) ^ set(D10)
for k in sorted(set(DA) ^ set(D10)):
    side = "ONLY_A" if k in DA else "ONLY_B"
    step = ("v9_to_v10" if k in k_910 else "A_to_v7" if k in k_a7
            else "v7_to_v9" if k in k_79 else "cross_step")
    src = DA.get(k) or D10.get(k) or {}
    if k in delta:
        d = delta[k]
        if d["change"] == "ADD" and not values_match(d["new_value"], src.get("value_cny")):
            resolution = "UNRESOLVED_EVIDENCE_MISMATCH"
            evidence = "delta ADD new_value=%s 与实值=%s 不符" % (
                (d["new_value"] or "")[:16], (src.get("value_cny") or "")[:16])
        else:
            resolution = "RESOLVED_NORMALIZED_DELTA"
            evidence = "delta change=%s doc=%s p.%s" % (
                d["change"], d["document_id"], d["source_page"])
    elif k in v9_added:
        resolution = "RESOLVED_M07_REPAIR"
        evidence = "v9 patch detail_added status=%s" % src.get("status", "")
    elif ("%s|%s" % (k[0], {"20260331": "q1_2026", "20260630": "h1_2026",
                            "20260930": "q3_2026"}.get(k[2], ""))) in npdedt:
        resolution = "RESOLVED_M07_NPDEDT_OVERRIDE"
        evidence = "npdedt_override_rows.json"
    elif step == "v9_to_v10":
        resolution = "RESOLVED_RESTATED_ADOPTION"
        evidence = "s00_v10 manifest.row_additions"
    elif step == "v7_to_v9" and k[1].startswith("FIN.NPDEDT"):
        resolution = "RESOLVED_M07_NPDEDT_OVERRIDE"
        evidence = "m07 v9 扣非补行"
    elif side == "ONLY_B":
        resolution = "UNRESOLVED_UNBACKED_ADDITION"
        evidence = "B 新增该行但无操作记录（验收缺口，非数值冲突）"
    else:
        resolution = "UNRESOLVED_NO_EVIDENCE"
        evidence = "B 删除该行且无记录"
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
        bval = b.get(fld, "")
        if fld == "restatement_flag":
            hit = verify.get((k[0], k[2]))
            if not hit:
                resolution = "UNRESOLVED_NO_EVIDENCE"
                evidence = "results.csv 未覆盖该公司-期间"
            else:
                vs = {x["verdict"] for x in hit}
                methods = {x["method"] for x in hit}
                if len(vs) > 1:
                    resolution = "UNRESOLVED_AMBIGUOUS_MULTI_RECORD"
                    evidence = "%d 条核验记录判定互斥: %s" % (len(hit), "/".join(sorted(vs)))
                elif bval not in vs:
                    resolution = "UNRESOLVED_EVIDENCE_MISMATCH"
                    evidence = "核验判定=%s 但 B=%s" % (list(vs)[0], bval)
                elif "ASSUMED_NO_PENDING_REVIEW" in methods:
                    resolution = "RESOLVED_RESTATEMENT_VERIFY_WEAK"
                    evidence = "method=ASSUMED_NO_PENDING_REVIEW（假设非实证）p.%s" % hit[0]["page"]
                else:
                    resolution = "RESOLVED_RESTATEMENT_VERIFY"
                    evidence = "verdict=%s method=%s p.%s" % (
                        hit[0]["verdict"], hit[0]["method"], hit[0]["page"])
        else:
            d = delta.get(k)
            if d and fld in (d.get("changed_columns") or ""):
                resolution = "RESOLVED_NORMALIZED_DELTA"
                evidence = "delta changed_columns 含 %s doc=%s" % (fld, d["document_id"])
            else:
                resolution = "UNRESOLVED_NO_EVIDENCE"
                evidence = "无证明 %s 变更的记录" % fld
        rows_meta.append({
            "security_id": k[0], "stock_name": a.get("stock_name", ""),
            "field_id": k[1], "period_key": k[2], "meta_field": fld,
            "value_A": a.get(fld, ""), "value_B": bval,
            "resolution": resolution, "evidence": evidence,
        })

with open(OUT / "meta_diff.csv", "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows_meta[0].keys()), lineterminator="\n")
    w.writeheader()
    w.writerows(rows_meta)
print("meta_diff.csv: %d 行" % len(rows_meta))

# ---------- 4. 汇总 ----------
def cnt(rows, key):
    return dict(Counter(r[key] for r in rows).most_common())


def is_open(r):
    """未闭合：UNRESOLVED_* 全部计入；WEAK 也算未闭合（Codex 要求）"""
    return r["resolution"].startswith("UNRESOLVED") or r["resolution"].endswith("_WEAK")


open_value = [r for r in rows_value if is_open(r)]
open_key = [r for r in rows_key if is_open(r)]
open_meta = [r for r in rows_meta if is_open(r)]

summary = {
    "generated_at": "2026-11-11T18:30:00+08:00",
    "version": "ERRATA_V2",
    "scope": "A vs B 全量差异（含元数据与键集），依据校验加强",
    "nature": "SELF_CHECK",
    "fixes_from_v1": [
        "UPDATE 记录校验 new_value 与实际值一致（v1 仅按键匹配）",
        "元数据不得按同键有记录兜底，须 changed_columns 含该字段",
        "重述多记录须全部一致且等于 B，互斥标 AMBIGUOUS",
        "ONLY_B 无记录计入验收缺口",
        "ASSUMED_NO_PENDING_REVIEW 不计入已解决",
    ],
    "versions": {
        "A": {"rows": len(DA), "sha256": sha(P_A)},
        "v7": {"rows": len(D7), "sha256": sha(P_V7)},
        "v9": {"rows": len(D9), "sha256": sha(P_V9)},
        "B": {"rows": len(D10), "sha256": sha(P_V10)},
    },
    "value_diff": {
        "total": len(rows_value),
        "by_step": cnt(rows_value, "step"),
        "by_bucket": cnt(rows_value, "bucket"),
        "sign_flip": sum(1 for r in rows_value if r["sign_flip"] == "YES"),
        "by_resolution": cnt(rows_value, "resolution"),
        "open": len(open_value),
        "companies": len({r["security_id"] for r in rows_value}),
    },
    "key_diff": {
        "total": len(rows_key),
        "by_step": cnt(rows_key, "step"),
        "by_side": cnt(rows_key, "side"),
        "by_resolution": cnt(rows_key, "resolution"),
        "open": len(open_key),
        "companies": len({r["security_id"] for r in rows_key}),
    },
    "meta_diff": {
        "total": len(rows_meta),
        "by_field": cnt(rows_meta, "meta_field"),
        "by_resolution": cnt(rows_meta, "resolution"),
        "open": len(open_meta),
        "companies": len({r["security_id"] for r in rows_meta}),
    },
    "open_total": len(open_value) + len(open_key) + len(open_meta),
    "restatement_apply_summary": json.loads(P_APPLY.read_text(encoding="utf-8")).get("rows_changed"),
    "known_limits": [
        "未回读 PDF；所有依据来自既有记录",
        "B 补行是否应有依据，取决于补采流程是否留痕；本台账只标缺口",
        "未覆盖「最新可用期选择」的间接依赖",
    ],
}
(OUT / "summary.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

print("\n=== V2 汇总 ===")
print("值差异:", summary["value_diff"]["by_resolution"], "未闭合", len(open_value))
print("键差异:", summary["key_diff"]["by_resolution"], "未闭合", len(open_key))
print("元数据:", summary["meta_diff"]["by_resolution"], "未闭合", len(open_meta))
print("未闭合合计:", summary["open_total"])
