#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""S00 勘误台账 V5（2026-11-11）

对 Codex 第五轮裁决的逐条落实：

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

import evidence_scope as es

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "runs/issues/S00/errata_20261111_v5"
OUT.mkdir(parents=True, exist_ok=True)

P_REGISTRY = ROOT / "runs/collection/collection_index.csv"
PERIOD_LABEL_TO_KEY = {
    "2025Q1": "20250331", "2025H1": "20250630", "2025Q3": "20250930",
    "FY2025": "20251231", "2026Q1": "20260331", "2026H1": "20260630",
    "2026Q3": "20260930", "FY2024": "20241231", "2024FY": "20241231",
}
# 方法适用范围与覆盖判据统一由 evidence_scope 提供：
# 不再用「行期间 == 文档自身期间」充当闭合充分条件。

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
# 影响时点/来源性质/版本采用：Codex 第四轮指出不能一律归为展示
AFFECTS_TIMING_OR_PROVENANCE = {"published_on", "source_kind", "adoption_reason"}
# Codex 第五轮：232 格整体归展示不成立。四类字段各有明确作用，必须逐项核。
AFFECTS_TRACE_LOCATION = {"source_page"}          # 证据定位（同方股份 61→137）
AFFECTS_ADOPTION_EXPLANATION = {"evidence_label"}  # 采用解释（国机通用新增仲裁标签）
AFFECTS_PROVENANCE = {"slot_id"}                   # 供给槽位（q1_2025→annual_2025）
AFFECTS_QUALIFICATION_REASON = {"status_reason"}   # 资格理由
# 其余为溯源或展示（V5 起该桶为空，保留以便回归）
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

# 文档自身期间：用于区分「报告披露自身期间」与「供给比较列/分季度表」
doc_period = {}
with open(P_REGISTRY, encoding="utf-8-sig", newline="") as f:
    for r in csv.DictReader(f):
        doc_period[r["document_id"]] = PERIOD_LABEL_TO_KEY.get(r.get("period_label", ""), "")

# 已由独立复核裁决解除的具体争议：不得按新判据重新挂起
P_RULED = OUT / "rulings_resolved.json"
RULED = {}
if P_RULED.exists():
    _d = json.loads(P_RULED.read_text(encoding="utf-8"))
    RULED = {e["key"]: e for e in _d.get("entries", [])}
    print("已裁决解除项:", len(RULED))

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

QMAP = {"0331": "1231", "0630": "0331", "0930": "0630", "1231": "0930"}


def prev_quarter(pk):
    tail = pk[4:]
    if tail == "0331":
        return str(int(pk[:4]) - 1) + "1231"
    return pk[:4] + QMAP[tail]


def parent_compatible(k):
    """累计差分行的两个累计父输入是否兼容（文档/版本/合并范围/单位）。

    第六轮裁决：不能以「同一报告内相减自动抵消」豁免。只有两期调整额相等才抵消，
    而相等无法由同一报告推出；跨文档情形（本期 H1 与上期 Q1 来自不同公告）更须核。
    """
    sec, fld, pk = k
    if fld not in es.SIMPLE_SQ:
        return None
    ytd = fld[:-3] + ".YTD"
    p1 = D10.get((sec, ytd, pk))
    p2 = D10.get((sec, ytd, prev_quarter(pk)))
    if not p1 or not p2:
        return False
    for x in ("consolidation_scope", "unit_scale", "currency"):
        if (p1.get(x) or "") != (p2.get(x) or ""):
            return False
    if (p1.get("document_id") or "") == (p2.get("document_id") or ""):
        return True
    if (p1.get("version_used") or "") and p1.get("version_used") == p2.get("version_used"):
        return True
    return ((sec, ytd, pk) in adopt) or ((sec, ytd, prev_quarter(pk)) in adopt)


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
        scope_req = scope_cov = scope_mis = grp = polarity = ""
        if fld == "restatement_flag":
            doc = b.get("document_id", "")
            rec = vrec.get(doc) if doc else None
            own = doc_period.get(doc, "") if doc else ""
            rk = "%s|%s|%s" % (k[0], k[1], k[2])
            status_b = b.get("status", "")
            pok = parent_compatible(k)
            # 判据：证据实际覆盖该行断言。document_period 与 row_period 分开传，
            # 由 evidence_scope 内部判定 is_own，不再用字符串真值。
            if rk in RULED:
                r = es.judge(rec, doc, status_b, own, k[2], ruled=RULED[rk],
                             bval=bval, parent_ok=pok)
            elif rec is not None and rec["verdict"] != bval and (rec.get("method") or "") != "NOTE_RETAINED_ERRATA_NONZERO":
                # 判定与 B 相反：先登记该行按来源应有的必需范围，处置停在未闭合。
                _req = es.required_scope(status_b, own, k[2])
                r = {"resolution": "UNRESOLVED_EVIDENCE_MISMATCH",
                     "scope_level": "CONFLICT",
                     "scope_required": ";".join(sorted(_req)),
                     "scope_covered": "", "scope_missing": ";".join(sorted(_req)),
                     "polarity": "",
                     "evidence_note": ("文档判定=%s 但 B=%s（doc=%s）；须先判旧判据范围是否不足，"
                                       "不能直接认定 B 错" % (rec["verdict"], bval, doc[:20]))}
            else:
                r = es.judge(rec, doc, status_b, own, k[2], bval=bval, parent_ok=pok)
            resolution = r["resolution"]
            scope_req, scope_cov = r["scope_required"], r["scope_covered"]
            scope_mis, evidence = r["scope_missing"], r["evidence_note"]
            polarity = r["polarity"]
            if rec is not None:
                _ex, _af, _sc, _me = es.analyse(rec)
                grp = es.group_key(rec.get("method"), _ex, _af, status_b,
                                   es.is_own_period(own, k[2]))
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
            "status_B": D10[k].get("status", ""),
            "document_id": D10[k].get("document_id", ""),
            "document_period": doc_period.get(D10[k].get("document_id", ""), ""),
            "own_period": doc_period.get(D10[k].get("document_id", ""), ""),
            "is_own_period": {True: "YES", False: "NO", None: "UNKNOWN"}[
                es.is_own_period(doc_period.get(D10[k].get("document_id", ""), ""), k[2])],
            "parent_compatible": {True: "YES", False: "NO", None: "NA"}[parent_compatible(k)],
            "polarity": polarity,
            "evidence_group": grp,
            "scope_required": scope_req, "scope_covered": scope_cov,
            "scope_missing": scope_mis,
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
        elif fld in AFFECTS_TIMING_OR_PROVENANCE:
            cls = "AFFECTS_TIMING_OR_PROVENANCE"
        elif fld in AFFECTS_TRACE_LOCATION:
            cls = "AFFECTS_TRACE_LOCATION"
        elif fld in AFFECTS_ADOPTION_EXPLANATION:
            cls = "AFFECTS_ADOPTION_EXPLANATION"
        elif fld in AFFECTS_PROVENANCE:
            cls = "AFFECTS_PROVENANCE"
        elif fld in AFFECTS_QUALIFICATION_REASON:
            cls = "AFFECTS_QUALIFICATION_REASON"
        else:
            cls = "TRACE_OR_DISPLAY"
        d = delta.get(k)
        if cls == "TRACE_OR_DISPLAY":
            resolution = "REGISTERED_DISPLAY_ONLY"
            evidence = "溯源/展示字段，不改变数值、资格、时点或版本采用"
        else:
            # Codex 第四轮：不得以「同键存在 ADD/UPDATE」自动免责，
            # 必须核记录是否含该字段、操作是否解释该字段、终值是否相等。
            resolution = "PENDING_FIELD_LEVEL_CHECK"
            if d is None:
                evidence = "%s 变更无同键记录" % cls
            else:
                evidence = ("同键存在 %s 记录 doc=%s，但未证明该记录含此字段且终值相等"
                            % (d["change"], d["document_id"]))
        rows_extra.append({
            "security_id": k[0], "stock_name": DA[k].get("stock_name", ""),
            "field_id": k[1], "period_key": k[2], "meta_field": fld,
            "class": cls, "value_A": DA[k].get(fld) or "",
            "value_B": D10[k].get(fld) or "",
            "same_key_record": (d["change"] if d else "NONE"),
            "document_changed": ("YES" if (DA[k].get("document_id") or "") != (D10[k].get("document_id") or "") else "NO"),
            "period_source_changed": ("YES" if (DA[k].get("period_source") or "") != (D10[k].get("period_source") or "") else "NO"),
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
    """未闭合：UNRESOLVED_* 与 PENDING_* 都计入（待核不是已闭合）"""
    return r["resolution"].startswith("UNRESOLVED") or r["resolution"].startswith("PENDING")


open_value = [r for r in rows_value if is_open(r)]
open_key = [r for r in rows_key if is_open(r)]
open_meta = [r for r in rows_meta if is_open(r)]
open_extra = [r for r in rows_extra if is_open(r)]

# 证据分组：同质分组供逐组复核，避免「按方法名整体认可/否决」
meta_rs = [r for r in rows_meta if r["meta_field"] == "restatement_flag"]
grp_cnt = Counter(r["evidence_group"] for r in meta_rs)
grp_rows = defaultdict(list)
for r in meta_rs:
    grp_rows[r["evidence_group"]].append(r)
groups = []
for g, n in grp_cnt.most_common():
    rs = grp_rows[g]
    groups.append({
        "group": g, "rows": n,
        "documents": len({r["document_id"] for r in rs}),
        "companies": len({r["security_id"] for r in rs}),
        "by_resolution": dict(Counter(r["resolution"] for r in rs).most_common()),
    })

summary = {
    "generated_at": "2026-11-12T00:40:00+08:00",
    "version": "ERRATA_V5",
    "scope": "A vs B 全量差异（含 24 个元数据列）；闭合判据改为证据覆盖断言",
    "nature": "SELF_CHECK",
    "changes_from_v4": [
        "取消「行期间 == 文档自身期间即闭合」：新增 evidence_scope.py，"
        "按证据正文实际排除的调整原因（ERRATA / MERGER_RETRO / POLICY_CHANGE）"
        "与按取值来源确定的必需范围求差集，差集写入 scope_missing",
        "IMPORTANT_MATTER_NA、NOTE_RETAINED_ERRATA_ZERO 两类结构性受限方法"
        "不再自动闭合，5,270 条转入 PENDING_SCOPE_LIMITED_METHOD",
        "累计差分/DERIVED_Q1_EQUALS_YTD 行须覆盖 MERGER_RETRO（比较期调整会传播进本期单季），"
        "分季度表行须覆盖 QUARTERLY_TABLE_PROVENANCE，比较列行须覆盖 COMPARATIVE_SCOPE",
        "232 格原「溯源/展示」桶清零：source_page→AFFECTS_TRACE_LOCATION、"
        "evidence_label→AFFECTS_ADOPTION_EXPLANATION、slot_id→AFFECTS_PROVENANCE、"
        "status_reason→AFFECTS_QUALIFICATION_REASON，全部转字段级待核",
        "meta_diff 增列 status_B / own_period / evidence_group / scope_required / "
        "scope_covered / scope_missing，供逐项追溯与同质分组",
        "保留 rulings_resolved.json：已裁决解除项恢复 RESOLVED_BY_RULING，不因新判据重开",
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
        "restatement_groups": groups,
        "restatement_group_count": len(groups),
    },
    "extra_meta_diff": {
        "total": len(rows_extra), "by_class": cnt(rows_extra, "class"),
        "by_field": cnt(rows_extra, "meta_field"),
        "by_resolution": cnt(rows_extra, "resolution"),
        "open": len(open_extra), "companies": len({r["security_id"] for r in rows_extra}),
        "document_changed": dict(Counter(r["document_changed"] for r in rows_extra)),
        "period_source_changed": dict(Counter(r["period_source_changed"] for r in rows_extra)),
    },
    "open_total_core": len(open_value) + len(open_key) + len(open_meta),
    "open_total_all": len(open_value) + len(open_key) + len(open_meta) + len(open_extra),
    "restatement_apply_summary": json.loads(P_APPLY.read_text(encoding="utf-8")).get("rows_changed"),
    "known_limits": [
        "未回读 PDF；所有依据来自既有记录",
        "锚定期回退路径的间接依赖仍未覆盖",
        "AFFECTS_QUALIFICATION 类未判定是否影响本次资格，仅登记",
        "本版未包含分层方法抽验结果，抽验见 sampling_v5.csv",
    ],
}
(OUT / "summary.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

print("\n=== V4 汇总 ===")
print("值:", summary["value_diff"]["by_resolution"], "未闭合", len(open_value))
print("键:", summary["key_diff"]["by_resolution"], "未闭合", len(open_key))
print("元数据:", summary["meta_diff"]["by_resolution"], "未闭合", len(open_meta))
print("补充列:", summary["extra_meta_diff"]["by_class"],
      "未闭合", len(open_extra))
print("核心未闭合:", summary["open_total_core"], "含补充列:", summary["open_total_all"])
