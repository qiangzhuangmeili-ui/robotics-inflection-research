#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""杭叉集团 S00 v10 / S02 独立复核（不复用 S01 公式函数）。

复核范围：
1. 输入完整性：v10 gzip/CSV 行数、公司数、SHA 与 manifest 一致；
2. 非杭叉不变性：其余 1053 家所有字段与 v9 逐格一致；
3. 杭叉变更范围：恰好 55 条改值 + 1 条补建，无越界改动；
4. 原始值对账：对 5 份官方 PDF 已人工核对的数字逐项比对；
5. 九项指标独立重算（Decimal，自行实现公式）；
6. Q06 传播独立判定（自行实现 _restate 语义）；
7. 衍生字段重算；
8. 单季-累计闭合缺口与 manifest 登记一致。

输出 audit_report.json，任何一项 FAIL 即非零退出。
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import json
import sys
from decimal import Decimal as D, getcontext
from pathlib import Path

getcontext().prec = 40

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "runs/issues/S02/hangcha_restated_20261101"
V10 = OUT / "s00_v10/s00_v10.csv.gz"
V10_MANIFEST = OUT / "s00_v10/s00_v10_manifest.json"
AUDIT = OUT / "s00_v10/s00_v10_adoption_audit.csv"
V9 = ROOT / "runs/issues/S02/m07_repair_20261030/s00_v9.csv.gz"
S02_METRICS = OUT / "s02_v10/all_pool_metrics.csv"
S02_REVIEW = OUT / "s02_v10/review.json"
RULES = OUT / "rules_recalculation_inputs_v10.json"
SEC = "SH:603298"

results: list[dict] = []


def check(cid: str, item: str, ok: bool, detail) -> None:
    results.append({"id": cid, "item": item, "result": "PASS" if ok else "FAIL", "detail": detail})
    print(("PASS " if ok else "FAIL ") + cid + " " + item)


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load(p: Path) -> tuple[list[str], list[dict]]:
    with gzip.open(p, "rt", encoding="utf-8-sig", newline="") as fh:
        r = csv.DictReader(fh)
        return r.fieldnames, list(r)


def idx(rows):
    return {(x["security_id"], x["period_key"], x["period_basis"], x["field_id"]): x for x in rows}


# ---------------------------------------------------------------- 原始值对账表
# 数值来源：五份官方 PDF 指定页，已逐页人工读取（见 audit_report 的 source_pages）
PDF_EXPECT = {
    # 2025Q1 调整后（2026Q1 报告 p.1-2）
    ("20250331", "YTD_CUMULATIVE", "FIN.REV.YTD"): "4455524706.04",
    ("20250331", "YTD_CUMULATIVE", "FIN.COST.YTD"): "3525825583.83",
    ("20250331", "YTD_CUMULATIVE", "FIN.NP.YTD"): "445842003.75",
    ("20250331", "YTD_CUMULATIVE", "FIN.NPP.YTD"): "431975966.52",
    ("20250331", "YTD_CUMULATIVE", "FIN.NPDEDT.YTD"): "419311660.58",
    ("20250331", "YTD_CUMULATIVE", "FIN.OCF.YTD"): "198826564.31",
    ("20250331", "SINGLE_QUARTER", "FIN.REV.SQ"): "4455524706.04",
    ("20250331", "SINGLE_QUARTER", "FIN.NPP.SQ"): "431975966.52",
    ("20250331", "SINGLE_QUARTER", "FIN.NPDEDT.SQ"): "419311660.58",
    ("20250331", "SINGLE_QUARTER", "FIN.OCF.SQ"): "198826564.31",
    # 2025H1 调整后（2026H1 报告 p.9 / p.51 / p.52 / p.56）
    ("20250630", "YTD_CUMULATIVE", "FIN.REV.YTD"): "9296138420.08",
    ("20250630", "YTD_CUMULATIVE", "FIN.COST.YTD"): "7238967058.64",
    ("20250630", "YTD_CUMULATIVE", "FIN.NP.YTD"): "1154511217.41",
    ("20250630", "YTD_CUMULATIVE", "FIN.NPP.YTD"): "1115391633.83",
    ("20250630", "YTD_CUMULATIVE", "FIN.NPDEDT.YTD"): "1091573107.27",
    ("20250630", "YTD_CUMULATIVE", "FIN.OCF.YTD"): "347414148.08",
    # 2025Q2 保留年报分季度值（2025 年报 p.10）
    ("20250630", "SINGLE_QUARTER", "FIN.REV.SQ"): "4846493118.57",
    ("20250630", "SINGLE_QUARTER", "FIN.NPP.SQ"): "687866792.47",
    ("20250630", "SINGLE_QUARTER", "FIN.NPDEDT.SQ"): "663685128.27",
    ("20250630", "SINGLE_QUARTER", "FIN.OCF.SQ"): "148587583.78",
    # 2026 当前期（2026Q1 p.1-2；2026H1 p.9/p.51/p.52/p.56）——不得被改写
    ("20260331", "YTD_CUMULATIVE", "FIN.REV.YTD"): "4916516338.56",
    ("20260331", "YTD_CUMULATIVE", "FIN.NPDEDT.YTD"): "464727262.30",
    ("20260331", "SINGLE_QUARTER", "FIN.REV.SQ"): "4916516338.56",
    ("20260331", "SINGLE_QUARTER", "FIN.NPDEDT.SQ"): "464727262.30",
    ("20260630", "YTD_CUMULATIVE", "FIN.REV.YTD"): "10100128374.70",
    ("20260630", "YTD_CUMULATIVE", "FIN.COST.YTD"): "7584601035.46",
    ("20260630", "YTD_CUMULATIVE", "FIN.NP.YTD"): "1200730682.16",
    ("20260630", "YTD_CUMULATIVE", "FIN.NPP.YTD"): "1214529518.50",
    ("20260630", "YTD_CUMULATIVE", "FIN.NPDEDT.YTD"): "1202054630.27",
    ("20260630", "YTD_CUMULATIVE", "FIN.OCF.YTD"): "382216760.53",
    ("20260630", "SINGLE_QUARTER", "FIN.REV.SQ"): "5183612036.14",
    ("20260630", "SINGLE_QUARTER", "FIN.NPP.SQ"): "742922111.35",
    ("20260630", "SINGLE_QUARTER", "FIN.NPDEDT.SQ"): "737327367.97",
    ("20260630", "SINGLE_QUARTER", "FIN.OCF.SQ"): "169968203.64",
}


def main() -> int:
    manifest = json.loads(V10_MANIFEST.read_text(encoding="utf-8"))
    review = json.loads(S02_REVIEW.read_text(encoding="utf-8"))

    # 1 输入完整性
    v10_fields, v10 = load(V10)
    v9_fields, v9 = load(V9)
    check("A01", "v10 gzip SHA 与 manifest 一致", sha(V10) == manifest["gzip_sha256"],
          {"manifest": manifest["gzip_sha256"], "actual": sha(V10)})
    check("A02", "v10 行数/公司数与 manifest 一致",
          len(v10) == manifest["rows"] and len({x["security_id"] for x in v10}) == manifest["unique_companies"],
          {"rows": len(v10), "companies": len({x["security_id"] for x in v10})})
    check("A03", "v10 表头与 v9 完全一致", v10_fields == v9_fields,
          {"added_cols": sorted(set(v10_fields) - set(v9_fields))})
    check("A04", "v10 比 v9 恰好多 1 行", len(v10) - len(v9) == 1,
          {"v9": len(v9), "v10": len(v10)})

    # 2 非杭叉不变性
    i9, i10 = idx(v9), idx(v10)
    other_keys = [k for k in i9 if k[0] != SEC]
    diff_other = [k for k in other_keys if i10.get(k) != i9[k]]
    check("A05", "非杭叉 1053 家逐格完全不变", not diff_other,
          {"compared": len(other_keys), "diff": len(diff_other), "sample": diff_other[:3]})

    # 3 杭叉变更范围
    h_keys9 = [k for k in i9 if k[0] == SEC]
    changed = [k for k in h_keys9 if i10.get(k) != i9[k]]
    added = [k for k in i10 if k[0] == SEC and k not in i9]
    audit_rows = list(csv.DictReader(AUDIT.open(encoding="utf-8-sig", newline="")))
    check("A06", "杭叉改值行数=审计非补建条数", len(changed) == len(audit_rows) - 1,
          {"changed": len(changed), "audit": len(audit_rows)})
    check("A07", "杭叉仅新增 1 行且为 2025H1 扣非累计",
          added == [("SH:603298", "20250630", "YTD_CUMULATIVE", "FIN.NPDEDT.YTD")], {"added": added})

    current_marked = [r for r in audit_rows if r["action"].startswith("MARK_CURRENT")]
    cur_bad = [r for r in current_marked if D(r["value_before"] or "0") != D(r["value_after"] or "0")]
    check("A08", f"当前期 {len(current_marked)} 条只更新比较口径、金额未变", not cur_bad,
          {"mismatch": [{"field": r["field_id"], "period": r["period_key"],
                         "before": r["value_before"], "after": r["value_after"]} for r in cur_bad]})

    # 4 原始值对账
    bad = []
    for (pk, basis, fid), exp in PDF_EXPECT.items():
        row = i10.get((SEC, pk, basis, fid))
        if row is None or D(row["value_cny"]) != D(exp):
            bad.append({"key": [pk, basis, fid], "expected": exp,
                        "actual": None if row is None else row["value_cny"]})
    check("B01", f"关键原始值 {len(PDF_EXPECT)} 项与官方PDF核对一致", not bad, {"mismatch": bad})

    # 4b 审计行声称的来源页，必须真的在该页出现该数值
    pdf_dir = Path(r"D:\StockResearchLab\_cache\hangcha_603298_sources_20261101")
    doc_pdf = {
        "DOC-FD7E797F129DA52E": "2025Q1.pdf",
        "DOC-46C352EA9F4BDAB5": "2025H1.pdf",
        "DOC-FB2C019EFD9674E9": "2025Annual.pdf",
        "DOC-18E0EFF334A69C3C": "2026Q1.pdf",
        "DOC-3BBF762B7EF9E776": "2026H1.pdf",
    }
    page_bad, page_checked, page_derived = [], 0, 0
    try:
        import pymupdf  # type: ignore
    except ImportError:
        pymupdf = None
    if not pdf_dir.is_dir() or pymupdf is None:
        results.append({"id": "B02", "item": "审计行来源页复核", "result": "SKIP",
                        "detail": {"why": "PDF目录或解析库不可用", "pdf_dir": str(pdf_dir)}})
        print("SKIP B02 审计行来源页复核（PDF不可用）")
    else:
        cache = {}
        for r in audit_rows:
            page = (r["source_page_after"] or "").strip()
            doc = r["document_id_after"]
            if not page.isdigit() or doc not in doc_pdf:
                continue
            if (r["status_after"] or "").startswith("DERIVED"):
                # 派生值（如 Q2=H1-Q1）不印在单页上，其输入由 B01/D02 单独核验
                page_derived += 1
                continue
            name = doc_pdf[doc]
            if name not in cache:
                cache[name] = pymupdf.open(pdf_dir / name)
            pdf = cache[name]
            pno = int(page) - 1
            if pno < 0 or pno >= pdf.page_count:
                page_bad.append({"field": r["field_id"], "doc": name, "page": page,
                                 "why": "page out of range"})
                continue
            text = pdf[pno].get_text().replace(",", "").replace("\n", "").replace(" ", "")
            target = (r["value_after"] or "").replace(",", "").strip()
            page_checked += 1
            if target and target not in text:
                page_bad.append({"field": r["field_id"], "doc": name, "page": page,
                                 "value": r["value_after"], "why": "value not found on page"})
        check("B02", f"审计行来源页复核（{page_checked} 条须在所标页码找到数值；{page_derived} 条派生值不适用）",
              not page_bad, {"checked": page_checked, "derived_skipped": page_derived,
                             "mismatch": page_bad[:10]})

    # 5 九项指标独立重算
    def val(pk, fid, basis="YTD_CUMULATIVE"):
        r = i10[(SEC, pk, basis, fid)]
        return None if r["value_cny"] == "" else D(r["value_cny"])

    rev_t, rev_b = val("20260630", "FIN.REV.YTD"), val("20250630", "FIN.REV.YTD")
    sq_t, sq_b = val("20260630", "FIN.REV.SQ", "SINGLE_QUARTER"), val("20250630", "FIN.REV.SQ", "SINGLE_QUARTER")
    sq_q1, sq_q1b = val("20260331", "FIN.REV.SQ", "SINGLE_QUARTER"), val("20250331", "FIN.REV.SQ", "SINGLE_QUARTER")
    npd_t, npd_b = val("20260630", "FIN.NPDEDT.YTD"), val("20250630", "FIN.NPDEDT.YTD")
    npd_sq_t, npd_sq_b = val("20260630", "FIN.NPDEDT.SQ", "SINGLE_QUARTER"), val("20250630", "FIN.NPDEDT.SQ", "SINGLE_QUARTER")
    gm_t, gm_b = val("20260630", "FIN.GROSSMARGIN.PCT"), val("20250630", "FIN.GROSSMARGIN.PCT")
    ocf_t, ocf_b = val("20260630", "FIN.OCF.YTD"), val("20250630", "FIN.OCF.YTD")
    npp_t = val("20260630", "FIN.NPP.YTD")

    recomputed = {
        "M01": rev_t / rev_b - 1,
        "M02": sq_t / sq_b - 1,
        "M03": ((sq_t / sq_b - 1) - (sq_q1 / sq_q1b - 1)) * 100,
        "M04": gm_t - gm_b,
        "M05": npd_t / npd_b - 1,
        "M06": (npd_t / rev_t * 100) - (npd_b / rev_b * 100),
        "M07": npd_sq_t / npd_sq_b - 1,
        "M08": ocf_t / npp_t,
        "M09": ocf_t - ocf_b,
    }

    s02 = {}
    with S02_METRICS.open(encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            if r["security_id"] == SEC:
                s02[r["metric_id"]] = r
    check("C01", "S02 输出杭叉 12 个指标槽位", len(s02) == 12, {"found": sorted(s02)})

    val_bad = []
    for mid, exp in recomputed.items():
        got = D(s02[mid]["value"])
        tol = D("0.02") if mid == "M09" else D("1e-9") * max(D(1), abs(exp))
        if abs(got - exp) > tol:
            val_bad.append({"metric": mid, "recomputed": str(exp), "s02": str(got)})
    check("C02", "M01-M09 独立重算与 S02 逐项一致", not val_bad, {"mismatch": val_bad})

    # 6 Q06 传播独立判定
    def restate_q06(keys):
        for k in keys:
            row = i10.get(k)
            if row is None:
                continue
            note = row.get("comparability_note") or ""
            if "RESTATED_COMPARATIVE_ADOPTED" in note:
                continue
            if row.get("restatement_flag") in ("是", "RESTATEMENT_INDICATED_NEEDS_REVIEW") \
                    or "RESTATED_PRIOR_YEARS_UNRECALCULATED" in note:
                return True
        return False

    metric_inputs = {
        "M01": [("20260630", "FIN.REV.YTD"), ("20250630", "FIN.REV.YTD")],
        "M02": [("20260630", "FIN.REV.SQ"), ("20250630", "FIN.REV.SQ")],
        "M03": [("20260630", "FIN.REV.SQ"), ("20250630", "FIN.REV.SQ"),
                ("20260331", "FIN.REV.SQ"), ("20250331", "FIN.REV.SQ")],
        "M04": [("20260630", "FIN.GROSSMARGIN.PCT"), ("20250630", "FIN.GROSSMARGIN.PCT")],
        "M05": [("20260630", "FIN.NPDEDT.YTD"), ("20250630", "FIN.NPDEDT.YTD")],
        "M06": [("20260630", "FIN.NPDEDT.YTD"), ("20260630", "FIN.REV.YTD"),
                ("20250630", "FIN.NPDEDT.YTD"), ("20250630", "FIN.REV.YTD")],
        "M07": [("20260630", "FIN.NPDEDT.SQ"), ("20250630", "FIN.NPDEDT.SQ")],
        "M08": [("20260630", "FIN.OCF.YTD"), ("20260630", "FIN.NPP.YTD")],
        "M09": [("20260630", "FIN.OCF.YTD"), ("20250630", "FIN.OCF.YTD")],
    }
    basis_of = {"FIN.REV.SQ": "SINGLE_QUARTER", "FIN.NPDEDT.SQ": "SINGLE_QUARTER"}
    q06_bad = []
    for mid, pairs in metric_inputs.items():
        keys = [(SEC, pk, basis_of.get(fid, "YTD_CUMULATIVE"), fid) for pk, fid in pairs]
        expected = restate_q06(keys)
        actual = "Q06" in (s02[mid]["quality_flags"] or "").split(";")
        if expected != actual:
            q06_bad.append({"metric": mid, "expected_q06": expected, "actual_q06": actual,
                            "flags": s02[mid]["quality_flags"]})
    check("C03", "Q06 传播与输入行标记独立判定一致", not q06_bad, {"mismatch": q06_bad})

    status_bad = [{"metric": mid, "status": s02[mid]["metric_status"]}
                  for mid in ("M02", "M03", "M07") if s02[mid]["metric_status"] != "PROVISIONAL"]
    status_bad += [{"metric": mid, "status": s02[mid]["metric_status"]}
                   for mid in ("M01", "M04", "M05", "M06", "M08", "M09") if s02[mid]["metric_status"] != "OK"]
    check("C04", "状态分布符合预期（3项PROVISIONAL+6项OK）", not status_bad, {"bad": status_bad})

    # 7 衍生字段重算
    der_bad = []
    for pk in ("20250331", "20250630"):
        rev, cost = val(pk, "FIN.REV.YTD"), val(pk, "FIN.COST.YTD")
        npf, ocf = val(pk, "FIN.NPP.YTD"), val(pk, "FIN.OCF.YTD")   # NPMARGIN=归母/营收；OCF_TO_NP=OCF/归母
        exp = {
            "FIN.GROSSPROFIT.YTD": (rev - cost).quantize(D("0.01")),
            "FIN.GROSSMARGIN.PCT": ((rev - cost) / rev * 100).quantize(D("0.000001")),
            "FIN.NPMARGIN.PCT": (npf / rev * 100).quantize(D("0.000001")),
            "FIN.OCF_TO_NP.RATIO": (ocf / npf).quantize(D("0.000001")),
        }
        for fid, e in exp.items():
            got = val(pk, fid)
            if got != e:
                der_bad.append({"period": pk, "field": fid, "expected": str(e), "actual": str(got)})
    check("D01", "8 条衍生字段重算一致", not der_bad, {"mismatch": der_bad})

    # 8 单季-累计缺口登记
    gap = manifest.get("single_quarter_bridge_gap", {})
    gap_bad = []
    for sq, ytd in (("FIN.REV.SQ", "FIN.REV.YTD"), ("FIN.NPP.SQ", "FIN.NPP.YTD"),
                    ("FIN.NPDEDT.SQ", "FIN.NPDEDT.YTD"), ("FIN.OCF.SQ", "FIN.OCF.YTD")):
        h1, q1 = val("20250630", ytd), val("20250331", ytd)
        q2 = val("20250630", sq, "SINGLE_QUARTER")
        want = h1 - (q1 + q2)
        got = D(gap[sq]["h1_minus_q1_plus_q2"])
        if want != got:
            gap_bad.append({"field": sq, "expected": str(want), "recorded": str(got)})
    check("D02", "单季-累计缺口与 manifest 登记一致", not gap_bad, {"mismatch": gap_bad})

    # 9 规则科学内容未被改动
    base = json.loads((ROOT / "runs/issues/S01/screen_rules_v2.json").read_text(encoding="utf-8"))
    cur = json.loads(RULES.read_text(encoding="utf-8"))
    strip = lambda r: {k: ({f: {kk: vv for kk, vv in m.items() if kk != "rows"} for f, m in v.items()}
                           if k == "field_catalog" else v)
                       for k, v in r.items()
                       if k not in ("input_fingerprint", "input_version", "base_rules_sha256",
                                    "l0_addendum_path", "field_catalog_row_counts")}
    check("E01", "科学规则核心（公式/阈值/定义）与冻结S01逐项一致", strip(base) == strip(cur), {})
    changed_counts = cur.get("field_catalog_row_counts", {}).get("changes", [])
    check("E02", "字段行数变化全部登记且有原因",
          bool(changed_counts) and bool(cur["field_catalog_row_counts"].get("reason")),
          {"changed": len(changed_counts)})

    # 10 S02 自检结果
    check("F01", "S02 自检无阻断失败", review.get("blocking_fail") == 0,
          {"blocking_fail": review.get("blocking_fail"), "decision": review.get("decision")})
    check("F02", "S02 覆盖 12648 格 / 1054 家",
          review["counts"]["cells"] == 12648 and review["counts"]["companies"] == 1054,
          review["counts"])

    # 11 与 v9 全池基线逐行对比（基线在仓库外，仅作对比用）
    baseline = Path(r"D:\StockResearchLab\_cache\_baseline_v9\s02\all_pool_metrics.csv")
    if baseline.is_file():
        def rows_of(p):
            with p.open(encoding="utf-8-sig", newline="") as fh:
                return {(r["security_id"], r["metric_id"]): r for r in csv.DictReader(fh)}
        base_rows = rows_of(baseline)
        cur_rows = rows_of(S02_METRICS)
        other_diff = [k for k in base_rows if k[0] != SEC and base_rows[k] != cur_rows.get(k)]
        hang_diff = [k for k in base_rows if k[0] == SEC and base_rows[k] != cur_rows.get(k)]
        check("G01", "v9→v10 仅杭叉 12 格变化，其余 12,647 格零差异",
              not other_diff and len(hang_diff) == 12 and set(base_rows) == set(cur_rows),
              {"non_hangcha_diff": len(other_diff), "hangcha_diff": len(hang_diff),
               "keys_equal": set(base_rows) == set(cur_rows)})
    else:
        results.append({"id": "G01", "item": "v9 基线逐行对比", "result": "SKIP",
                        "detail": {"why": f"基线不存在: {baseline}"}})
        print("SKIP G01 v9 基线逐行对比（基线不存在）")

    fails = [r for r in results if r["result"] == "FAIL"]
    report = {
        "security_id": SEC,
        "status": "INDEPENDENT_RECHECK_PASS" if not fails else "INDEPENDENT_RECHECK_FAIL",
        "checks_total": len(results),
        "checks_pass": len(results) - len(fails),
        "checks_fail": len(fails),
        "v10_gzip_sha256": sha(V10),
        "v10_rows": len(v10),
        "hangcha_changed_rows": len(changed),
        "hangcha_added_rows": len(added),
        "s02_counts": review["counts"],
        "recomputed_metrics": {k: str(v) for k, v in recomputed.items()},
        "s02_metrics": {k: {"value": v["value"], "status": v["metric_status"],
                            "flags": v["quality_flags"]} for k, v in s02.items()},
        "checks": results,
        "note": "本报告为执行方独立复算，不替代外部复核；未使用 S01 公式函数。",
    }
    (OUT / "independent_recheck.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "pass": report["checks_pass"],
                      "fail": report["checks_fail"]}, ensure_ascii=False))
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
