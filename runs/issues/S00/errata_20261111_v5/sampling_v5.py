#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""S00 勘误 V5 分层方法抽验

Codex 第五轮裁决第十节第 2 步：

> 做分层方法抽验：覆盖直接季度表、累计差分、Q1、比较列、不同重述原因及补充字段；
> 包含山东钢铁正例、大豪科技已解除实例和杭叉跨来源限制。约 20 条可作为起点，
> 验收标准是风险类型覆盖。

本脚本按风险类型确定性抽样（不是随机抽样），并对每条样本回读原件物理页，
检验「核验记录的页码 + 证据文本 + 文档身份」是否真的对得上。

输出 sampling_v5.csv / sampling_v5.json。
"""
import csv
import gzip
import json
import re
from collections import Counter
from pathlib import Path

import evidence_scope as es

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "runs/issues/S00/errata_20261111_v5"
ORIG = Path("D:/StockResearchLab/IndustryInflectionLab/robotics_data/collection/originals")
P_V10 = ROOT / "runs/issues/S02/hangcha_restated_20261101/s00_v10/s00_v10.csv.gz"
P_VERIFY = ROOT / "runs/issues/S02/remediation_20261029/restatement_verify/results.csv"
P_REGISTRY = ROOT / "runs/collection/collection_index.csv"
PERIOD_LABEL_TO_KEY = {
    "2025Q1": "20250331", "2025H1": "20250630", "2025Q3": "20250930",
    "FY2025": "20251231", "2026Q1": "20260331", "2026H1": "20260630",
    "2026Q3": "20260930", "FY2024": "20241231", "2024FY": "20241231",
}

D10 = {}
with gzip.open(P_V10, "rt", encoding="utf-8-sig", newline="") as f:
    for r in csv.DictReader(f):
        D10[(r["security_id"], r["field_id"], r["period_key"])] = r
vrec = {}
with open(P_VERIFY, encoding="utf-8-sig", newline="") as f:
    for r in csv.DictReader(f):
        vrec[r["document_id"]] = r
doc_period = {}
with open(P_REGISTRY, encoding="utf-8-sig", newline="") as f:
    for r in csv.DictReader(f):
        doc_period[r["document_id"]] = PERIOD_LABEL_TO_KEY.get(r.get("period_label", ""), "")

meta = [r for r in csv.DictReader(open(OUT / "meta_diff.csv", encoding="utf-8-sig", newline=""))
        if r["meta_field"] == "restatement_flag"]
extra = list(csv.DictReader(open(OUT / "extra_meta_diff.csv", encoding="utf-8-sig", newline="")))


def norm(s):
    return re.sub(r"\s+", "", s or "")


def page_match(sec, doc, page, evidence):
    """回读原件物理页，检验证据文本是否真的出现在该页。"""
    code = sec.split(":")[1]
    base = ORIG / code
    if not base.exists():
        return "COMPANY_DIR_MISSING", 0.0, ""
    pdf = None
    for p in base.rglob(doc + ".pdf"):
        pdf = p
        break
    if pdf is None:
        return "PDF_MISSING", 0.0, ""
    if not str(page).strip():
        return "NO_PAGE_RECORDED", 0.0, ""
    try:
        import pymupdf
        d = pymupdf.open(str(pdf))
        idx = int(page) - 1
        if idx < 0 or idx >= d.page_count:
            return "PAGE_OUT_OF_RANGE(%d/%d)" % (idx + 1, d.page_count), 0.0, ""
        txt = norm(d[idx].get_text())
        d.close()
    except Exception as e:
        return "READ_ERROR:%s" % e, 0.0, ""
    if not txt:
        return "NO_TEXT_LAYER", 0.0, ""
    ev = norm(evidence)
    if not ev:
        return "NO_EVIDENCE_TEXT", 0.0, txt[:120]
    wins = [ev[i:i + 10] for i in range(0, max(1, len(ev) - 9), 5)]
    hit = sum(1 for w in wins if w in txt)
    ratio = hit / max(1, len(wins))
    return ("MATCH" if ratio >= 0.5 else "PARTIAL" if ratio > 0 else "NOT_FOUND"), round(ratio, 3), txt[:120]


def pick(pred, n=1, need_rec=True, distinct_company=True):
    got, seen = [], set()
    for r in meta:
        if len(got) >= n:
            break
        if not pred(r):
            continue
        if need_rec:
            doc = D10.get((r["security_id"], r["field_id"], r["period_key"]), {}).get("document_id", "")
            if doc not in vrec:
                continue
        if distinct_company and r["security_id"] in seen:
            continue
        seen.add(r["security_id"])
        got.append(r)
    return got


FIELD_REQ = {
    "source_page": "核物理页定位：同文档内页码变化须回读新页确认取数位置",
    "evidence_label": "核采用解释：新增/变更标签须对应真实采用理由",
    "slot_id": "核供给槽位：槽位变化须确认供给文档与期间未变",
    "status_reason": "核资格理由：理由文本变化须确认不改变本次资格判断",
    "value_raw": "核数值：记录覆盖该字段且终值/规范化转换结果与 B 一致",
    "unit_scale": "核单位：缩放系数变化须与 unit_raw/币种一致",
    "period_source": "核期间归属：来源期间变化须确认 period_key 不变",
    "published_on": "核披露时点：与文档真实披露日一致",
    "comparability_note": "核可比性说明：内容是否完整表达限制",
    "upstream_hold_fields": "核 HOLD 传播：变更须对应上游状态",
    "low_base_flag": "核低基数标记：变更须对应冻结规则",
    "quarterly_inputs": "核分季度输入：变更须对应父输入行",
    "version_used": "核版本：须对应采用审计记录",
    "original_document_id": "核原始文档身份：须与登记表一致",
    "currency": "核币种：须与单位/金额一致",
    "value_before_adoption": "核采用前值：须对应采用审计",
    "source_kind": "核来源类型：须与登记表一致",
    "adoption_reason": "核采用理由：须对应采用审计",
}

samples = []


def add_sample(risk, why, r, extra_cols=None, meta_row=None):
    k = (r["security_id"], r["field_id"], r["period_key"])
    doc = D10.get(k, {}).get("document_id", "")
    rec = vrec.get(doc)
    status = D10.get(k, {}).get("status", "")
    own = doc_period.get(doc, "")
    req = es.required_scope(status, own)
    cov = es.coverage_of(rec) if rec else set()
    row = {
        "sample_id": "S%02d" % (len(samples) + 1),
        "risk_type": risk,
        "why_selected": why,
        "security_id": r["security_id"], "stock_name": r.get("stock_name", ""),
        "field_id": r["field_id"], "period_key": r["period_key"],
        "meta_field": (meta_row or {}).get("meta_field", "restatement_flag"),
        "status_B": status, "own_period": own,
        "method": (rec or {}).get("method", ""),
        "verdict": (rec or {}).get("verdict", ""),
        "page": (rec or {}).get("page", ""),
        "scope_required": ";".join(sorted(req)),
        "scope_covered": ";".join(sorted(cov)),
        "scope_missing": ";".join(sorted(req - cov)),
        "resolution": (meta_row or r)["resolution"],
        "evidence_head": norm((rec or {}).get("evidence", ""))[:100],
    }
    if risk.startswith("R11"):
        row["page_reread"] = "NOT_APPLICABLE_EXTRA_FIELD"
        row["page_match_ratio"] = ""
        row["page_excerpt"] = ""
        row["field_check_requirement"] = FIELD_REQ.get(row["meta_field"], "按字段类型核验")
    else:
        st, ratio, excerpt = page_match(r["security_id"], doc, (rec or {}).get("page", ""),
                                        (rec or {}).get("evidence", ""))
        row["page_reread"] = st
        row["page_match_ratio"] = ratio
        row["page_excerpt"] = excerpt
        row["field_check_requirement"] = ""
        if st == "PARTIAL" and "附注" in (rec or {}).get("evidence", ""):
            row["page_excerpt"] = ("证据为核验者写的汇总注（非原文逐字），"
                                   "部分命中属预期；须回读原注所在页确认金额") + excerpt
    samples.append(row)


# R1 直接季度表 + 自身期间
for r in pick(lambda x: x["status_B"] == "EXTRACTED_QUARTERLY_TABLE"
              and x["own_period"] == x["period_key"]
              and x["resolution"].startswith("PENDING"), 3):
    add_sample("R1_QUARTERLY_TABLE_OWN", "分季度表直接取值且为文档自身期间，NA 证据不涉该表", r)

# R2 累计差分
for r in pick(lambda x: x["status_B"] == "DERIVED_CUMULATIVE_DIFF"
              and x["resolution"] == "RESOLVED_SCOPE_COVERED", 3):
    add_sample("R2_CUMULATIVE_DIFF", "单季由累计差分得到，须核 YTD(t)/YTD(t−1q) 父输入", r)

# R3 Q1
for r in pick(lambda x: x["status_B"] == "DERIVED_Q1_EQUALS_YTD", 2, need_rec=False):
    add_sample("R3_Q1_EQUALS_YTD",
               "Q1 单季即累计，不应减上年年末；口径本身由 C27 单键检验，"
               "本行属供给文档不在核验清单的实例", r)

# R4 比较列（行期间≠文档自身期间）
for r in pick(lambda x: x["own_period"] and x["own_period"] != x["period_key"]
              and x["resolution"].startswith("PENDING"), 3):
    add_sample("R4_COMPARATIVE_COLUMN", "行期间≠文档自身期间，取值来自比较列/分季度表", r)

# R5 不同重述原因：证据含 MERGER_RETRO
for r in pick(lambda x: "MERGER_RETRO" in (x["scope_covered"] or ""), 2):
    add_sample("R5_CAUSE_MERGER_RETRO", "证据正文明确排除同一控制下合并追溯", r)
# R5b 证据含 POLICY_CHANGE
for r in pick(lambda x: "POLICY_CHANGE" in (x["scope_covered"] or "")
              and "MERGER_RETRO" not in (x["scope_covered"] or ""), 2):
    add_sample("R5_CAUSE_POLICY_CHANGE", "证据正文含会计政策变更，但未排除同一控制下合并", r)

# R6 假设方法
for r in pick(lambda x: x["resolution"] == "PENDING_WEAK_ASSUMPTION", 2):
    add_sample("R6_WEAK_ASSUMPTION", "方法为假设，未查原文", r)

# R7 证据与断言冲突
for r in pick(lambda x: x["resolution"] == "UNRESOLVED_EVIDENCE_CONTRADICTS", 2):
    add_sample("R7_EVIDENCE_CONTRADICTS", "证据披露非零差错更正，与「未被重述」冲突", r)

# R8 山东钢铁正例（Codex 点名）
sd = [r for r in meta if r["security_id"] == "SH:600022" and r["period_key"] == "20250630"
      and r["field_id"] == "FIN.REV.SQ"]
for r in sd:
    add_sample("R8_SHANDONG_POSITIVE", "Codex 第四轮认定应重开的正例", r)

# R9 大豪科技已解除（Codex 点名）
dh = [r for r in meta if r["security_id"] == "SH:603025" and r["period_key"] == "20250331"
      and r["field_id"] == "FIN.REV.SQ"]
for r in dh:
    add_sample("R9_DAHAO_RULED", "Codex 第四轮已裁决解除，V5 须保持解除", r)

# R10 杭叉跨来源限制（Codex 点名）
hc = [r for r in meta if r["security_id"] == "SH:603298"][:2]
for r in hc:
    add_sample("R10_HANGCHA_CROSS_SOURCE", "杭叉采用审计为候选待复核，不能自证独立验收", r)

# R11 补充字段：来源页 / 采用解释 / 槽位 / 资格理由
for fld in ("source_page", "evidence_label", "slot_id", "status_reason", "value_raw", "unit_scale"):
    cand = [r for r in extra if r["meta_field"] == fld]
    if cand:
        e = cand[0]
        add_sample("R11_EXTRA_%s" % fld.upper(), "补充元数据字段级核验（原被归为展示）",
                   {"security_id": e["security_id"], "stock_name": e["stock_name"],
                    "field_id": e["field_id"], "period_key": e["period_key"],
                    "resolution": e["resolution"]},
                   meta_row=e)

with open(OUT / "sampling_v5.csv", "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(samples[0].keys()), lineterminator="\n")
    w.writeheader()
    w.writerows(samples)

risk_cnt = Counter(s["risk_type"] for s in samples)
reread = Counter(s["page_reread"] for s in samples)
summary = {
    "scope": "分层方法抽验（按风险类型确定性抽样 + 原件物理页回读）",
    "samples": len(samples),
    "risk_types": len(risk_cnt),
    "by_risk": dict(risk_cnt.most_common()),
    "page_reread": dict(reread.most_common()),
    "covered_requirements": {
        "直接季度表": any(k.startswith("R1") for k in risk_cnt),
        "累计差分": any(k.startswith("R2") for k in risk_cnt),
        "Q1": any(k.startswith("R3") for k in risk_cnt),
        "比较列": any(k.startswith("R4") for k in risk_cnt),
        "不同重述原因": any(k.startswith("R5") for k in risk_cnt),
        "补充字段": any(k.startswith("R11") for k in risk_cnt),
        "山东钢铁正例": any(k.startswith("R8") for k in risk_cnt),
        "大豪科技已解除": any(k.startswith("R9") for k in risk_cnt),
        "杭叉跨来源限制": any(k.startswith("R10") for k in risk_cnt),
    },
    "note": "抽验是方法覆盖性检验，不构成全量核证；page_reread=MATCH 表示证据文本确实出现在该物理页。",
}
(OUT / "sampling_v5.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

for s in samples:
    print("%s %-24s %-11s %-16s %-9s %-24s p.%-4s %-22s %s" % (
        s["sample_id"], s["risk_type"], s["security_id"], s["field_id"],
        s["period_key"], s["resolution"][:24], s["page"] or "-", s["page_reread"],
        s["page_match_ratio"]))
print()
print(json.dumps(summary["by_risk"], ensure_ascii=False, indent=1))
print("page_reread:", dict(reread))
