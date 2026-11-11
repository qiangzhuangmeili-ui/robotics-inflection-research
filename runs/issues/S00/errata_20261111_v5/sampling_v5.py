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

# 采用审计：父输入是否采用同一修订文档（第七轮 C 项：不能只凭 version_used 相同）
adopt = {}
_p_adopt = ROOT / "runs/issues/S02/hangcha_restated_20261101/s00_v10/s00_v10_adoption_audit.csv"
if _p_adopt.exists():
    with open(_p_adopt, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            adopt[(r["security_id"], r["field_id"], r["period_key"])] = r
doc_period = {}
with open(P_REGISTRY, encoding="utf-8-sig", newline="") as f:
    for r in csv.DictReader(f):
        doc_period[r["document_id"]] = PERIOD_LABEL_TO_KEY.get(r.get("period_label", ""), "")

meta = [r for r in csv.DictReader(open(OUT / "meta_diff.csv", encoding="utf-8-sig", newline=""))
        if r["meta_field"] == "restatement_flag"]
extra = list(csv.DictReader(open(OUT / "extra_meta_diff.csv", encoding="utf-8-sig", newline="")))


def norm(s):
    return re.sub(r"\s+", "", s or "")


QMAP = {"0331": "1231", "0630": "0331", "0930": "0630", "1231": "0930"}


def prev_quarter(pk):
    tail = pk[4:]
    if tail == "0331":
        return str(int(pk[:4]) - 1) + "1231"
    return pk[:4] + QMAP[tail]


def cross_doc_parent(sec, fld, pk):
    """累计差分行的两个父输入是否来自不同文档（第六轮裁决要求单独抽验的情形）。"""
    if fld not in es.SIMPLE_SQ:
        return None
    ytd = fld[:-3] + ".YTD"
    p1 = D10.get((sec, ytd, pk))
    p2 = D10.get((sec, ytd, prev_quarter(pk)))
    if not p1 or not p2:
        return None
    d1, d2 = p1.get("document_id", ""), p2.get("document_id", "")
    return (d1 != d2, d1, d2)


def locate_in_doc(sec, doc, evidence, near=None):
    """全文定位：PARTIAL 样本必须在原件里找到原文所在物理页，而不是停在「部分命中」。"""
    code = sec.split(":")[1]
    pdf = None
    for p in (ORIG / code).rglob(doc + ".pdf"):
        pdf = p
        break
    if pdf is None:
        return "PDF_MISSING", 0, ""
    try:
        import pymupdf
        d = pymupdf.open(str(pdf))
        ev = norm(evidence)
        pages = [norm(d[i].get_text()) for i in range(d.page_count)]
        d.close()
    except Exception as e:
        return "READ_ERROR:%s" % e, 0, ""
    if not ev:
        return "NO_EVIDENCE_TEXT", 0, ""
    # 判据改为「最长连续原文片段」：证据常是多页文字拼接，按整段命中率算会把
    # 真实逐字命中误判成弱定位。任一片段 ≥20 字逐字出现在某页即视为已定位。
    best_page, best_len, best_txt = 0, 0, ""
    for w in (60, 40, 30, 20):
        if len(ev) < w:
            continue
        step = 4 if w >= 30 else 2
        for i in range(0, len(ev) - w + 1, step):
            frag = ev[i:i + w]
            for pi, t in enumerate(pages):
                if t and frag in t:
                    if w > best_len:
                        best_page, best_len, best_txt = pi + 1, w, t[:120]
        if best_len >= 20:
            break
    if best_len >= 20:
        return ("LOCATED(p.%d)" % best_page), round(min(1.0, best_len / max(20, len(ev))), 3), best_txt
    # 退而求其次：12 字窗命中率
    wins = [ev[i:i + 12] for i in range(0, max(1, len(ev) - 11), 6)]
    best, best_n = 0, 0
    for pi, t in enumerate(pages):
        if not t:
            continue
        n = sum(1 for w2 in wins if w2 in t)
        if n > best_n:
            best, best_n = pi + 1, n
    if best_n <= 0:
        return "NOT_FOUND_IN_DOC", 0, ""
    return ("WEAK_LOCATE(p.%d)" % best), round(best_n / max(1, len(wins)), 3), pages[best - 1][:120]



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


def rec_of(r):
    k = (r["security_id"], r["field_id"], r["period_key"])
    return vrec.get(D10.get(k, {}).get("document_id", ""))


def mentioned(r):
    rec = rec_of(r)
    return es.analyse(rec)[3] if rec else set()


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
    # 第六轮裁决：期间参数必须显式三态传入，不能传文档期间字符串当布尔用
    if (r.get("scope_required") or ""):
        # 第七轮 F 项：采样表原先用 coverage_of 重算，丢掉 parent_ok 这一维，
        # 出现「S20/S21 一边写父兼容缺失、一边保留 RESOLVED」的自相矛盾。
        # 采样表展示台账声明值；覆盖是否正确由 C29 独立重算另判。
        req_s, cov_s = r["scope_required"], r.get("scope_covered") or ""
        mis_s = r.get("scope_missing") or ""
    else:
        req = es.required_scope(status, own, r["period_key"])
        cov = es.coverage_of(rec) if rec else set()
        req_s = ";".join(sorted(req))
        cov_s = ";".join(sorted(cov))
        mis_s = ";".join(sorted(req - cov))
    row = {
        "sample_id": "S%02d" % (len(samples) + 1),
        "risk_type": risk,
        "why_selected": why,
        "security_id": r["security_id"], "stock_name": r.get("stock_name", ""),
        "field_id": r["field_id"], "period_key": r["period_key"],
        "meta_field": (meta_row or {}).get("meta_field", "restatement_flag"),
        "status_B": status, "own_period": own,
        "is_own_period": {True: "YES", False: "NO", None: "UNKNOWN"}[
            es.is_own_period(own, r["period_key"])],
        "parent_cross_doc": (
            lambda x: "NA" if x is None else ("YES" if x[0] else "NO")
        )(cross_doc_parent(r["security_id"], r["field_id"], r["period_key"])),
        "method": (rec or {}).get("method", ""),
        "verdict": (rec or {}).get("verdict", ""),
        "page": (rec or {}).get("page", ""),
        "scope_required": req_s,
        "scope_covered": cov_s,
        "scope_missing": mis_s,
        "resolution": (meta_row or r)["resolution"],
        "evidence_head": norm((rec or {}).get("evidence", ""))[:100],
        "located_conclusion": "",
        "locate_status": "",
        "parent_p1": "", "parent_p2": "",
        "parent_p1_doc": "", "parent_p2_doc": "",
        "parent_scope_unit_cur": "", "parent_doc_verdict": "",
        "parent_compatible": "",
    }
    if extra_cols:
        row.update(extra_cols)
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
for r in pick(lambda x: x["status_B"] == "DERIVED_CUMULATIVE_DIFF", 3):
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

# R5 不同重述原因
# 第六轮裁决第三节的后果：极性改为三分后，「同一控制合并范围变更0.00元」只对期初
# 未分配利润给出零值，不再算作对本字段的排除。因此 MERGER_RETRO 在全量中已无
# 「明确排除」实例，样本改为抽「提到但未排除」——正是旧判据误当排除的那一类。
for r in pick(lambda x: "MERGER_RETRO" in mentioned(x), 2):
    add_sample("R5_CAUSE_MERGER_RETRO",
               "证据提到同一控制/合并范围，但只对特定权益项目给零值，未排除对本字段的影响"
               "（旧判据在此误判为排除）", r)
# R5b 证据含 POLICY_CHANGE
for r in pick(lambda x: "POLICY_CHANGE" in (x["scope_covered"] or "")
              and "MERGER_RETRO" not in (x["scope_covered"] or ""), 2):
    add_sample("R5_CAUSE_POLICY_CHANGE", "证据正文含会计政策变更，但未排除同一控制下合并", r)

# R5c 肯定发生（第六轮裁决第三节：极性不能把「提到」当「排除」）
# 两类样本：B=否 但证据确认发生（冲突，须停在未闭合）；B=是 且事件已确认
# 但来源维度未核（事件层已确认、字段层仍开）。
for r in pick(lambda x: "affirmed=-" not in (x["polarity"] or "")
              and x["resolution"].startswith(("UNRESOLVED", "PENDING")), 2):
    add_sample("R5_CAUSE_AFFIRMED",
               "证据确认发生调整（肯定极性），不得按「未提及」或「零值」闭合", r)
for r in pick(lambda x: x["resolution"] == "PENDING_CONFIRMED_EVENT_FIELD_OPEN", 2):
    add_sample("R5_CAUSE_AFFIRMED",
               "B=是 且事件已由证据确认，但来源维度（分季度表/比较列/父输入）尚未核", r)

def parent_detail(sec, fld, pk):
    """交付两个父输入各自的核证结论，而不只是「存在跨文档」这一事实。"""
    if fld not in es.SIMPLE_SQ or es.is_q1(pk):
        return {}
    ytd = fld[:-3] + ".YTD"
    k1, k2 = (sec, ytd, pk), (sec, ytd, prev_quarter(pk))
    r1, r2 = D10.get(k1, {}), D10.get(k2, {})
    d1, d2 = r1.get("document_id", ""), r2.get("document_id", "")
    return {
        "parent_p1": "%s@%s" % (ytd, pk),
        "parent_p2": "%s@%s" % (ytd, prev_quarter(pk)),
        "parent_p1_doc": d1, "parent_p2_doc": d2,
        "parent_scope_unit_cur": "%s/%s/%s | %s/%s/%s" % (
            r1.get("consolidation_scope", ""), r1.get("unit_scale", ""), r1.get("currency", ""),
            r2.get("consolidation_scope", ""), r2.get("unit_scale", ""), r2.get("currency", "")),
        "parent_doc_verdict": "%s/%s" % (
            (vrec.get(d1) or {}).get("verdict", "NA"), (vrec.get(d2) or {}).get("verdict", "NA")),
        "parent_compatible": {True: "YES", False: "NO", None: "NA"}[
            _pc((sec, fld, pk))],
    }


def _pc(k):
    sec, fld, pk = k
    if fld not in es.SIMPLE_SQ or es.is_q1(pk):
        return None
    ytd = fld[:-3] + ".YTD"
    k1, k2 = (sec, ytd, pk), (sec, ytd, prev_quarter(pk))
    r1, r2 = D10.get(k1), D10.get(k2)
    if not r1 or not r2:
        return False
    for f in ("consolidation_scope", "unit_scale", "currency"):
        v1, v2 = (r1.get(f) or "").strip(), (r2.get(f) or "").strip()
        if not v1 or v1 != v2:
            return False
    d1, d2 = r1.get("document_id", ""), r2.get("document_id", "")
    if d1 and d1 == d2:
        return True
    if ((vrec.get(d1) or {}).get("verdict") or "") == "否" and             ((vrec.get(d2) or {}).get("verdict") or "") == "否":
        return True
    a1, a2 = adopt.get(k1), adopt.get(k2)
    if a1 and a2:
        x1 = (a1.get("document_id_after") or "").strip()
        x2 = (a2.get("document_id_after") or "").strip()
        if x1 and x1 == x2:
            return True
    return False


# R6 跨文档父输入（第七轮 C 项：必须交付两父输入各自的核证结论）
for r in pick(lambda x: x["status_B"] in ("DERIVED_CUMULATIVE_DIFF",
                                          "DERIVED_QUARTERLY_SUM_OVERRIDE")
              and cross_doc_parent(x["security_id"], x["field_id"], x["period_key"]) is not None
              and cross_doc_parent(x["security_id"], x["field_id"], x["period_key"])[0], 3):
    x = cross_doc_parent(r["security_id"], r["field_id"], r["period_key"])
    add_sample("R6_CROSS_DOC_PARENT",
               "单季由两期累计相减得到，两父输入来自不同文档（%s / %s），"
               "须核文档/版本/合并范围/单位兼容" % (x[1][:16], x[2][:16]), r,
               extra_cols=parent_detail(r["security_id"], r["field_id"], r["period_key"]))

# R6 假设方法
for r in pick(lambda x: x["resolution"] == "PENDING_WEAK_ASSUMPTION", 2):
    add_sample("R14_WEAK_ASSUMPTION", "方法为假设，未查原文（不得计入已闭合）", r)

# R7 证据与断言冲突
for r in pick(lambda x: x["resolution"] == "UNRESOLVED_EVIDENCE_MISMATCH", 2):
    add_sample("R15_EVIDENCE_MISMATCH",
               "旧核验判定与 B 相反，须先判旧判据范围是否不足，不能直接认定 B 错", r)

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

# R7 PARTIAL 原文定位（第六轮裁决第十节第 2 步：2 条 PARTIAL 必须给出原文位置）
# 做法：把已出现的 PARTIAL 样本复制一份，改标 R7_PARTIAL_LOCATED，
# 并在原件全文里定位证据实际所在页，不满足于「该页只命中一部分」。
_partial, _seen7 = [], set()
for s in samples:
    if s["page_reread"] != "PARTIAL":
        continue
    kk = (s["security_id"], s["field_id"], s["period_key"])
    if kk in _seen7:
        continue
    _seen7.add(kk)
    _partial.append(s)
# 第七轮 F 项：不能把「弱定位/未找到」也算作「已完成原文定位」。
# 先把候选池跑完，优先收 VERIFIED，凑满 3 条且至少 1 条 VERIFIED。
_r7_cand = []
for s in _partial[:10]:
    k = (s["security_id"], s["field_id"], s["period_key"])
    doc = D10.get(k, {}).get("document_id", "")
    rec = vrec.get(doc) or {}
    st, ratio, excerpt = locate_in_doc(s["security_id"], doc, rec.get("evidence", ""))
    if st.startswith("LOCATED"):
        concl, ls = "VERBATIM_ORIGINAL", "VERIFIED"
    elif st.startswith("WEAK_LOCATE"):
        concl, ls = ("SUMMARY_NOTE_NOT_VERBATIM：证据为核验者汇总注，全文最佳匹配页仅部分命中，"
                     "不能作为字段级原文证据"), "WEAK"
    elif st.startswith("NOT_FOUND"):
        concl, ls = "NOT_FOUND：原件全文未检索到证据文本（不等于原件中不存在）", "NOT_LOCATED"
    else:
        concl, ls = "LOCATE_ERROR：%s" % st, "NOT_LOCATED"
    _r7_cand.append((ls, s, st, ratio, excerpt, concl))
_r7_cand.sort(key=lambda x: {"VERIFIED": 0, "WEAK": 1, "NOT_LOCATED": 2}[x[0]])
for ls, s, st, ratio, excerpt, concl in _r7_cand[:3]:
    row = dict(s)
    row["sample_id"] = "S%02d" % (len(samples) + 1)
    row["risk_type"] = "R7_PARTIAL_LOCATED"
    row["why_selected"] = ("原样本 %s 在记录页仅部分命中，须在全文定位证据实际所在页"
                           % s["sample_id"])
    row["page_reread"] = st
    row["page_match_ratio"] = ratio
    row["page_excerpt"] = excerpt
    row["located_conclusion"] = concl
    row["locate_status"] = ls
    samples.append(row)


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
        "肯定发生（极性非「提及即排除」）": any(k == "R5_CAUSE_AFFIRMED" for k in risk_cnt),
        "跨文档父输入": any(k.startswith("R6_CROSS_DOC") for k in risk_cnt),
        "PARTIAL 原文定位": any(k.startswith("R7_PARTIAL") for k in risk_cnt),
        "原文定位已核（VERIFIED）": sum(1 for x in samples
                                       if x["risk_type"].startswith("R7_")
                                       and x["locate_status"] == "VERIFIED") > 0,
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
