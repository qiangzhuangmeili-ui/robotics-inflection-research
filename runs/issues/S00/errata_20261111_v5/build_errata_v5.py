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
import re
from collections import Counter, defaultdict
from pathlib import Path

import evidence_scope as es
import parent_verify as pv
import meta_classes as mc

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "runs/issues/S00/errata_20261111_v5"
OUT.mkdir(parents=True, exist_ok=True)

ORIG = Path("D:/StockResearchLab/IndustryInflectionLab/robotics_data/collection/originals")


_PDF_PAGES = {}


def _pdf_page(sec, doc, page):
    """原件**指定物理页**的文本（去空白）；页号非法或不可用返回空串。

    第十轮裁决 B3 / E：登记给了 `p1_page` / `source_page`，但生产侧仍拿
    `results.csv.evidence`（上游摘录）当引文源，页号从未被核对。这里改为按
    登记页回读原件——引文必须落在该页，否则一律 `PARENT_QUOTE_NOT_LOCATED`。
    """
    try:
        n = int(str(page).strip())
    except (TypeError, ValueError):
        return ""
    if n < 1:
        return ""
    key = (doc, n)
    if key in _PDF_PAGES:
        return _PDF_PAGES[key]
    txt = ""
    code = (sec or "").split(":")[-1]
    pdf = next((p for p in (ORIG / code).rglob(doc + ".pdf")), None) if doc else None
    if pdf is not None:
        try:
            import pymupdf
            d = pymupdf.open(str(pdf))
            if n <= d.page_count:
                txt = re.sub(r"\s+", "", d[n - 1].get_text())
            d.close()
        except Exception:
            txt = ""
    _PDF_PAGES[key] = txt
    return txt

_PDF_PATHS = {}


def _pdf_path(sec, doc):
    """原件路径（按证券代码目录 + 文档 ID 查找），找不到返回 None。"""
    if not doc:
        return None
    key = (sec, doc)
    if key in _PDF_PATHS:
        return _PDF_PATHS[key]
    code = (sec or "").split(":")[-1]
    pdf = next((p for p in (ORIG / code).rglob(doc + ".pdf")), None)
    _PDF_PATHS[key] = pdf
    return pdf


def _col_of(sec):
    """按词坐标取「该金额所在列」的期间列头（第十一轮 B 项，第十二轮绑定目标行）。"""
    def f(doc, page, value, label=None):
        pdf = _pdf_path(sec, doc)
        if pdf is None:
            return None, "NO_WORDS"
        words = pv.page_words(pdf, page)
        if not words:
            return None, "NO_WORDS"
        col, _amt, st = pv.column_of_amount_ex(words, value, label=label)
        return col, st
    return f


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
# 字段影响分类唯一来源：meta_classes.py（第七轮 E 项——分类不能由台账自报决定）
AFFECTS_VALUE = mc.AFFECTS_VALUE
AFFECTS_QUALIFICATION = mc.AFFECTS_QUALIFICATION
AFFECTS_TIMING_OR_PROVENANCE = mc.AFFECTS_TIMING_OR_PROVENANCE
AFFECTS_TRACE_LOCATION = mc.AFFECTS_TRACE_LOCATION
AFFECTS_ADOPTION_EXPLANATION = mc.AFFECTS_ADOPTION_EXPLANATION
AFFECTS_PROVENANCE = mc.AFFECTS_PROVENANCE
AFFECTS_QUALIFICATION_REASON = mc.AFFECTS_QUALIFICATION_REASON
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

# 父输入兼容性核证登记表（唯一 YES 来源）
PARENT_VERIFS = pv.load(OUT / "parent_verifications.csv")
print("父输入核证登记项:", len(PARENT_VERIFS))
# 来源维度核证登记表（比较范围 / 季度表来源）：judge 的结构化核证入口
SCOPE_VERIFS = pv.load_scope(OUT / "scope_verifications.csv")
print("来源维度核证登记项:", len(SCOPE_VERIFS))

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

# 内容审查登记表：放行补充元数据差异必须有真实审查记录（第八轮 E 项）
P_REVIEWS = OUT / "content_reviews.csv"
REVIEWS = {}
if P_REVIEWS.exists():
    with open(P_REVIEWS, encoding="utf-8-sig", newline="") as f:
        for _r in csv.DictReader(f):
            REVIEWS[(_r["security_id"], _r["field_id"], _r["period_key"],
                     _r["meta_field"])] = _r
    print("内容审查登记项:", len(REVIEWS))

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


def _parent_basis(kp):
    """父输入的「口径」：文档 + 期间 + 合并范围 + 单位 + 币种 + 版本 + 终值。"""
    r = D10.get(kp)
    if not r:
        return None
    return {"doc": (r.get("document_id") or "").strip(),
            "period": kp[2],
            "scope": (r.get("consolidation_scope") or "").strip(),
            "unit": (r.get("unit_scale") or "").strip(),
            "cur": (r.get("currency") or "").strip(),
            "ver": (r.get("version_used") or "").strip(),
            "val": (r.get("value_cny") or "").strip()}


def _expect(k1, k2, b1, b2):
    """核证登记必须逐项对应的实际父输入（第九轮 C 项 / 第十轮 B 项）。

    第十轮 B2：新增 `adjust_version`——登记声明的调整前后版本必须等于该父
    实际采用的 `version_used` 归类，不能只验枚举与两父相等。
    """
    return {"field": k1[1],
            "p1": {"doc": b1["doc"], "period": k1[2], "value": b1["val"],
                   "consolidation_scope": b1["scope"], "unit_scale": b1["unit"],
                   "currency": b1["cur"], "adjust_version": b1["ver"]},
            "p2": {"doc": b2["doc"], "period": k2[2], "value": b2["val"],
                   "consolidation_scope": b2["scope"], "unit_scale": b2["unit"],
                   "currency": b2["cur"], "adjust_version": b2["ver"]}}


def _doc_verdict(doc):
    return ((vrec.get(doc) or {}).get("verdict") or "").strip()


def parent_compatible(k):
    """父输入兼容性：**只认核证登记表**（第八轮 C 项）。

    Codex 第八轮否掉两条自动判据：同文档不能自动证明兼容（同一报告可能含
    调整前后列或混合来源）；上游「双否」不能直接证明兼容（三协电机已证明
    verdict 可能与原文相反，只能作待核线索）。因此本函数只剩两道门：
      1. 口径三元组（合并范围/单位/币种）必须非空且一致——必要条件；
      2. parent_verifications.csv 给出两个实际累计父数、原文引文与审查结论
         ——充分条件。登记表为空时，全部累计差分停在待核。
    """
    sec, fld, pk = k
    if fld not in es.SIMPLE_SQ:
        return None
    if es.is_q1(pk):
        return None          # Q1 单季 = Q1 累计，单父输入，无相减
    ytd = fld[:-3] + ".YTD"
    k1, k2 = (sec, ytd, pk), (sec, ytd, prev_quarter(pk))
    b1, b2 = _parent_basis(k1), _parent_basis(k2)
    if not b1 or not b2:
        return False
    for f in ("scope", "unit", "cur"):
        if not b1[f] or b1[f] != b2[f]:
            return False
    return pv.gap(PARENT_VERIFS.get(k), _expect(k1, k2, b1, b2),
                  lambda d, p, _s=sec: _pdf_page(_s, d, p),
                  col_of=_col_of(sec)) is None


def parent_gap(k):
    """兼容性判定依据，写入台账供逐条追溯。"""
    sec, fld, pk = k
    if fld not in es.SIMPLE_SQ or es.is_q1(pk):
        return "NA"
    ytd = fld[:-3] + ".YTD"
    k1, k2 = (sec, ytd, pk), (sec, ytd, prev_quarter(pk))
    b1, b2 = _parent_basis(k1), _parent_basis(k2)
    if not b1 or not b2:
        return "PARENT_MISSING"
    for f in ("scope", "unit", "cur"):
        if not b1[f] or b1[f] != b2[f]:
            return "SCOPE_UNIT_CURRENCY_MISMATCH"
    g = pv.gap(PARENT_VERIFS.get(k), _expect(k1, k2, b1, b2),
               lambda d, p, _s=sec: _pdf_page(_s, d, p),
               col_of=_col_of(sec))
    return "VERIFIED" if g is None else g


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
            _sok = pv.scope_dims(SCOPE_VERIFS, k,
                                 lambda d, p, _s=k[0]: _pdf_page(_s, d, p),
                                 expect_doc=doc)
            # 判据：证据实际覆盖该行断言。document_period 与 row_period 分开传，
            # 由 evidence_scope 内部判定 is_own，不再用字符串真值。
            if rk in RULED:
                r = es.judge(rec, doc, status_b, own, k[2], ruled=RULED[rk],
                             bval=bval, parent_ok=pok, scope_ok=_sok)
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
                r = es.judge(rec, doc, status_b, own, k[2], bval=bval,
                             parent_ok=pok, scope_ok=_sok)
            resolution = r["resolution"]
            scope_req, scope_cov = r["scope_required"], r["scope_covered"]
            scope_mis, evidence = r["scope_missing"], r["evidence_note"]
            polarity = r["polarity"]
            if rec is not None:
                _pol = es.analyse(rec)
                _ex, _af = _pol.excluded, _pol.affirmed
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
            "parent_basis": parent_gap(k) if fld == "restatement_flag" else "",
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

# ---------- 3b. 上游判定与原文极性相冲突的登记（第八轮 B 项）----------
# 裁决要求：不能只改分析器而保留旧解除结果。凡 results.csv 的 verdict 与原文
# 极性相反，逐行登记为证据冲突，并给出该文档在 B 中的传播范围。
_conf_docs = {r["document_id"] for r in rows_meta
              if r["resolution"] == "UNRESOLVED_EVIDENCE_CONTRADICTS"}
_prop = Counter()
for _r in rows_meta:
    if _r["document_id"] in _conf_docs:
        _prop[_r["document_id"]] += 1
rows_conf = []
for r in rows_meta:
    if r["document_id"] not in _conf_docs:
        continue
    rec = vrec.get(r["document_id"]) or {}
    rows_conf.append({
        "document_id": r["document_id"],
        "security_id": r["security_id"], "stock_name": r["stock_name"],
        "period_key": r["period_key"], "field_id": r["field_id"],
        "value_B": r["value_B"],
        "upstream_verdict": rec.get("verdict", ""),
        "upstream_method": rec.get("method", ""),
        "source_page": rec.get("page", ""),
        "original_polarity": r["polarity"],
        "scope_required": r["scope_required"],
        "rows_in_document": _prop[r["document_id"]],
        "propagation_scope": "该文档在 B 中供给 %d 个元数据槽，全部转证据冲突"
                             % _prop[r["document_id"]],
        "resolution": "UNRESOLVED_EVIDENCE_CONTRADICTS",
        "required_action": "回读原页确认勾选后修正上游 verdict；修正前不得按 否 解除",
    })
if rows_conf:
    with open(OUT / "evidence_conflicts.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows_conf[0].keys()), lineterminator="\n")
        w.writeheader()
        w.writerows(rows_conf)
    print("evidence_conflicts.csv: %d 行 / %d 份文档" % (len(rows_conf), len(_conf_docs)))
else:
    print("evidence_conflicts.csv: 0 行")

# ---------- 4. 其余 19 列元数据差异 ----------
rows_extra = []
all_cols = list(DA[next(iter(DA))].keys())
covered = set(META_FIELDS) | {"security_id", "field_id", "period_key", "value_cny"}
for fld in [c for c in all_cols if c not in covered]:
    for k in sorted(common):
        if (DA[k].get(fld) or "") == (D10[k].get(fld) or ""):
            continue
        cls = mc.expected_class(fld)
        d = delta.get(k)
        if cls == "DISPLAY_ONLY":
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
            "content_review": (REVIEWS.get((k[0], k[1], k[2], fld), {}).get("conclusion") or ""),
            "content_review_ref": ("|".join([k[0], k[1], k[2], fld])
                                   if (k[0], k[1], k[2], fld) in REVIEWS else ""),
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
        "累计差分（非 Q1）行须证父输入兼容（PARENT_COMPATIBILITY）；Q1 单季=Q1 累计，单父输入不套相减，"
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
