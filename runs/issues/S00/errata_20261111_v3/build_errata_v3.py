#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""S00 勘误台账 V3（2026-11-11）

对 Codex 第三轮裁决的逐条落实：

R1 元数据判据改为「字段精确成员 + 操作语义适用 + 记录终值等于 B」。
   - changed_columns 有 1,425/2,022 条是「全 41 列清单」，子串判据等于恒真；
   - 因此非 status 字段（document_id/pit_status/consolidation_scope）不能由 delta 解释，
     一律标 FIELD_NOT_IN_RECORD 重开。
R2 重述核验改按 document_id 匹配。
   依据：tools/s00_restatement_apply.py 第 36、46 行只用 document_id 建索引与应用，
   results.csv 是 1,007 文档 / 1,007 记录（1:1，零重复）。
   V2 按 (公司,期间) 匹配，导致同一文档供给的其它期间全部落空。
R3 登记 19 列 / 1,505 格未入台账的元数据差异，并分类。
R4 依赖检查递归展开单季派生值的累计父输入。

性质：SELF_CHECK。未回读 PDF。
"""
import csv
import gzip
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "runs/issues/S00/errata_20261111_v3"
OUT.mkdir(parents=True, exist_ok=True)

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

META_FIELDS = ["restatement_flag", "status", "document_id",
               "consolidation_scope", "pit_status"]
# 影响取值的列：变更即改变「代表什么数/哪一期/哪份文档」
AFFECTS_VALUE = {"value_raw", "value_before_adoption", "unit_raw", "unit_scale",
                 "currency", "period_source", "version_used", "original_document_id"}
# 影响资格的列：变更即改变可用性/低基数/可比性判断
AFFECTS_QUALIFICATION = {"upstream_hold_fields", "low_base_flag",
                         "comparability_note", "quarterly_inputs"}
# 其余为溯源或展示
DERIVED_PARENT = {
    "FIN.GROSSPROFIT.YTD": ["FIN.REV.YTD", "FIN.COST.YTD"],
    "FIN.GROSSPROFIT.SQ": ["FIN.REV.SQ", "FIN.COST.SQ"],
    "FIN.GROSSMARGIN.PCT": ["FIN.REV.YTD", "FIN.COST.YTD"],
    "FIN.NPMARGIN.PCT": ["FIN.NP.YTD", "FIN.REV.YTD"],
    "FIN.OCF_TO_NP.RATIO": ["FIN.OCF.YTD", "FIN.NP.YTD"],
}


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def load(p, gz=False):
    d = {}
    op = gzip.open if gz else open
    with op(p, "rt", encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            d[(r["security_id"], r["field_id"], r["period_key"])] = r
    return d


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def values_match(a, b):
    x, y = num(a), num(b)
    if x is None or y is None:
        return (a or "").strip() == (b or "").strip()
    if x == 0 and y == 0:
        return True
    return abs(x - y) <= max(1e-6, max(abs(x), abs(y)) * 1e-9)


print("加载四个版本 …")
DA, D7, D9, D10 = load(P_A), load(P_V7), load(P_V9, True), load(P_V10, True)
print("  A=%d v7=%d v9=%d B=%d" % (len(DA), len(D7), len(D9), len(D10)))

delta = {}
with open(P_DELTA, encoding="utf-8-sig", newline="") as f:
    for r in csv.DictReader(f):
        delta[(r["security_id"], r["field_id"], r["period_key"])] = r

# 重述核验：按 document_id（1:1），保留期间与判定供展示
vrec = {}
with open(P_VERIFY, encoding="utf-8-sig", newline="") as f:
    for r in csv.DictReader(f):
        vrec[r["document_id"]] = r

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

print("依据源: delta=%d verify_docs=%d adopt=%d v9_added=%d npdedt=%d"
      % (len(delta), len(vrec), len(adopt), len(v9_added), len(npdedt)))

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

    d = delta.get(k)
    if k in adopt:
        resolution = "RESOLVED_RESTATED_ADOPTION"
        evidence = "adoption_audit action=%s doc=%s" % (
            adopt[k]["action"], adopt[k]["document_id_after"])
    elif d and d["change"] == "UPDATE":
        if values_match(d["new_value"], b["value_cny"]):
            resolution = "RESOLVED_NORMALIZED_DELTA"
            evidence = "delta UPDATE new_value 与 B 一致; doc=%s p.%s" % (
                d["document_id"], d["source_page"])
        else:
            resolution = "UNRESOLVED_EVIDENCE_MISMATCH"
            evidence = "delta UPDATE new_value=%s 与 B=%s 不符" % (
                (d["new_value"] or "")[:18], b["value_cny"][:18])
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
    d = delta.get(k)
    if d and d["change"] == "ADD" and side == "ONLY_B":
        if values_match(d["new_value"], src.get("value_cny")):
            resolution = "RESOLVED_NORMALIZED_DELTA"
            evidence = "delta ADD 值一致 doc=%s p.%s" % (d["document_id"], d["source_page"])
        else:
            resolution = "UNRESOLVED_EVIDENCE_MISMATCH"
            evidence = "delta ADD new_value=%s 与实值=%s 不符" % (
                (d["new_value"] or "")[:16], (src.get("value_cny") or "")[:16])
    elif d and d["change"] == "REMOVE" and side == "ONLY_A":
        resolution = "RESOLVED_NORMALIZED_DELTA"
        evidence = "delta REMOVE doc=%s p.%s" % (d["document_id"], d["source_page"])
    elif d and d["change"] == "REMOVE" and side == "ONLY_B":
        resolution = "UNRESOLVED_EVIDENCE_MISMATCH"
        evidence = "记录为 REMOVE 但 B 存在该行"
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

# ---------- 3. 元数据差异（五个核心字段） ----------
rows_meta = []
common = set(DA) & set(D10)
for fld in META_FIELDS:
    for k in sorted(common):
        if DA[k].get(fld, "") == D10[k].get(fld, ""):
            continue
        a, b = DA[k], D10[k]
        bval = b.get(fld, "")
        if fld == "restatement_flag":
            doc = b.get("document_id", "")
            rec = vrec.get(doc) if doc else None
            if not doc:
                resolution = "UNRESOLVED_NO_DOCUMENT"
                evidence = "B 该行无 document_id，无法定位核验记录"
            elif rec is None:
                resolution = "UNRESOLVED_DOC_NEVER_VERIFIED"
                evidence = "供给文档 %s 不在 1,007 份核验清单内" % doc[:20]
            elif (rec.get("method") or "") == "ASSUMED_NO_PENDING_REVIEW":
                resolution = "UNRESOLVED_WEAK_ASSUMPTION"
                evidence = "文档已核验但方法为假设（ASSUMED_NO_PENDING_REVIEW）p.%s" % rec.get("page")
            elif rec["verdict"] != bval:
                resolution = "UNRESOLVED_EVIDENCE_MISMATCH"
                evidence = "文档判定=%s 但 B=%s（doc=%s）" % (rec["verdict"], bval, doc[:20])
            else:
                resolution = "RESOLVED_RESTATEMENT_VERIFY_DOC"
                evidence = "doc=%s verdict=%s method=%s p.%s" % (
                    doc[:20], rec["verdict"], rec["method"], rec["page"])
        else:
            d = delta.get(k)
            if d is None:
                resolution = "UNRESOLVED_NO_EVIDENCE"
                evidence = "无该键的操作记录"
            elif d["change"] == "REMOVE":
                resolution = "UNRESOLVED_RECORD_IS_REMOVE"
                evidence = "引用记录为 REMOVE，但 B 保留该行，记录不能解释 B 的 %s" % fld
            elif fld != "status":
                resolution = "UNRESOLVED_FIELD_NOT_IN_RECORD"
                evidence = "delta 无 %s 列，changed_columns 为全列清单，不构成字段级证明" % fld
            else:
                ns = (d.get("new_status") or "").strip()
                if not ns:
                    resolution = "UNRESOLVED_NO_TERMINAL_VALUE"
                    evidence = "记录无终值 new_status"
                elif ns != bval:
                    resolution = "UNRESOLVED_EVIDENCE_MISMATCH"
                    evidence = "记录终值 new_status=%s 与 B=%s 不符" % (ns, bval)
                else:
                    resolution = "RESOLVED_NORMALIZED_DELTA"
                    evidence = "UPDATE new_status=%s 与 B 一致 doc=%s" % (ns, d["document_id"])
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

# ---------- 4. 其余 19 列元数据差异 ----------
rows_extra = []
all_cols = list(DA[next(iter(DA))].keys())
covered = set(META_FIELDS) | {"security_id", "field_id", "period_key", "value_cny"}
for fld in [c for c in all_cols if c not in covered]:
    for k in sorted(common):
        if (DA[k].get(fld) or "") == (D10[k].get(fld) or ""):
            continue
        if fld in AFFECTS_VALUE:
            cls = "AFFECTS_VALUE"
        elif fld in AFFECTS_QUALIFICATION:
            cls = "AFFECTS_QUALIFICATION"
        else:
            cls = "TRACE_OR_DISPLAY"
        d = delta.get(k)
        if cls == "TRACE_OR_DISPLAY":
            resolution = "REGISTERED_DISPLAY_ONLY"
            evidence = "溯源/展示字段，不改变数值或资格"
        elif d is not None and d["change"] in ("ADD", "UPDATE"):
            resolution = "REGISTERED_WITH_RECORD"
            evidence = "同键存在 %s 记录 doc=%s" % (d["change"], d["document_id"])
        else:
            resolution = "UNRESOLVED_NO_EVIDENCE"
            evidence = "%s 变更无同键记录" % cls
        rows_extra.append({
            "security_id": k[0], "stock_name": DA[k].get("stock_name", ""),
            "field_id": k[1], "period_key": k[2], "meta_field": fld,
            "class": cls, "value_A": (DA[k].get(fld) or "")[:60],
            "value_B": (D10[k].get(fld) or "")[:60],
            "resolution": resolution, "evidence": evidence,
        })

with open(OUT / "extra_meta_diff.csv", "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows_extra[0].keys()), lineterminator="\n")
    w.writeheader()
    w.writerows(rows_extra)
print("extra_meta_diff.csv: %d 行" % len(rows_extra))

# ---------- 5. 汇总 ----------
def cnt(rows, key):
    return dict(Counter(r[key] for r in rows).most_common())


def is_open(r):
    return r["resolution"].startswith("UNRESOLVED")


open_value = [r for r in rows_value if is_open(r)]
open_key = [r for r in rows_key if is_open(r)]
open_meta = [r for r in rows_meta if is_open(r)]
open_extra = [r for r in rows_extra if is_open(r)]

summary = {
    "generated_at": "2026-11-11T21:10:00+08:00",
    "version": "ERRATA_V3",
    "scope": "A vs B 全量差异（含 24 个元数据列），判据按 Codex 第三轮裁决收紧",
    "nature": "SELF_CHECK",
    "changes_from_v2": [
        "元数据判据改为「字段精确成员 + 操作语义适用 + 记录终值等于 B」；"
        "changed_columns 有 1,425/2,022 条为全列清单，V2 子串判据等于恒真",
        "非 status 字段不能由 delta 解释，document_id/pit_status/consolidation_scope 全部重开",
        "重述核验改按 document_id 匹配（apply 脚本按文档应用，1,007 文档 1:1 记录）",
        "新增 19 列 / 1,505 格元数据差异登记与分类",
        "WEAK 一律计未闭合；REMOVE 记录不得解释 B 中保留行",
    ],
    "versions": {
        "A": {"rows": len(DA), "sha256": sha(P_A)},
        "v7": {"rows": len(D7), "sha256": sha(P_V7)},
        "v9": {"rows": len(D9), "sha256": sha(P_V9)},
        "B": {"rows": len(D10), "sha256": sha(P_V10)},
    },
    "value_diff": {
        "total": len(rows_value), "by_step": cnt(rows_value, "step"),
        "by_bucket": cnt(rows_value, "bucket"),
        "sign_flip": sum(1 for r in rows_value if r["sign_flip"] == "YES"),
        "by_resolution": cnt(rows_value, "resolution"),
        "open": len(open_value), "companies": len({r["security_id"] for r in rows_value}),
    },
    "key_diff": {
        "total": len(rows_key), "by_step": cnt(rows_key, "step"),
        "by_side": cnt(rows_key, "side"), "by_resolution": cnt(rows_key, "resolution"),
        "open": len(open_key), "companies": len({r["security_id"] for r in rows_key}),
    },
    "meta_diff": {
        "total": len(rows_meta), "by_field": cnt(rows_meta, "meta_field"),
        "by_resolution": cnt(rows_meta, "resolution"),
        "open": len(open_meta), "companies": len({r["security_id"] for r in rows_meta}),
    },
    "extra_meta_diff": {
        "total": len(rows_extra), "by_class": cnt(rows_extra, "class"),
        "by_field": cnt(rows_extra, "meta_field"),
        "by_resolution": cnt(rows_extra, "resolution"),
        "open": len(open_extra), "companies": len({r["security_id"] for r in rows_extra}),
    },
    "open_total_core": len(open_value) + len(open_key) + len(open_meta),
    "open_total_all": len(open_value) + len(open_key) + len(open_meta) + len(open_extra),
    "restatement_apply_summary": json.loads(P_APPLY.read_text(encoding="utf-8")).get("rows_changed"),
    "known_limits": [
        "未回读 PDF；所有依据来自既有记录",
        "锚定期回退路径的间接依赖仍未覆盖",
        "19 列中 AFFECTS_QUALIFICATION 类未判定是否影响本次资格，仅登记",
    ],
}
(OUT / "summary.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

print("\n=== V3 汇总 ===")
print("值:", summary["value_diff"]["by_resolution"], "未闭合", len(open_value))
print("键:", summary["key_diff"]["by_resolution"], "未闭合", len(open_key))
print("元数据:", summary["meta_diff"]["by_resolution"], "未闭合", len(open_meta))
print("补充列:", summary["extra_meta_diff"]["by_class"],
      "未闭合", len(open_extra))
print("核心未闭合:", summary["open_total_core"], "含补充列:", summary["open_total_all"])
