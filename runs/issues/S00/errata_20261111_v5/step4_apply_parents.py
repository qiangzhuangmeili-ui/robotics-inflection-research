#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""第 4 步批次 B：把**两侧证据完整**的父输入待核行登记为 COMPATIBLE。

输入 `step4_parent_scan.csv`（证据扫描的原始事实），输出 `parent_verifications.csv`
（27 列，与既有表头一致）。

只写 `verdict == EVIDENCE_OK` 的行；其余保留待核，并在 `step4_parent_scan.csv`
里留下确切原因。**不因为「差一条」就降级登记**：Codex 第十八轮裁决要求
「引文须实际支持指定行、期间表头及数值」「单纯填满列不能替代核证；不满足时保留待核」。

自验角色写 `SELF_CHECK`（同一执行 AI 自验），审查人写 `WorkBuddy-Agent`。
"""
import csv
import datetime
import io
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import parent_verify as pv          # noqa: E402

OUT = HERE
TODAY = datetime.date.today().isoformat()
REVIEWER = "WorkBuddy-Agent"

SCOPE_NOTE = ("两期父数均取自同一文档集的合并报表；单位与币种取自 s00_v10 的 "
              "unit_scale/currency，两期相等；登记页为原件中「该数值与期间表头同页」"
              "的那一页，数值与 s00_v10 采用值逐位相等，故可直接相减。")


def _basis(rec):
    """口径依据：把「为什么两期可比」写成可核对的句子，而不是一句「已核」。"""
    return ("%s：两期均为 %s、币种 %s、unit_scale=%s；"
            "p1 取 %s 第 %s 页「%s」列，值 %s；"
            "p2 取 %s 第 %s 页「%s」列，值 %s。"
            "两处数值分别等于 s00_v10 的采用值，故 %s 与 %s 两期累计同口径可直接相减。"
            % (rec["stock_name"], rec["p1_scope"], rec["p1_cur"], rec["p1_unit"],
               rec["p1_doc"], rec["p1_evidence_page"], rec["p1_column"],
               rec["p1_value"], rec["p2_doc"], rec["p2_evidence_page"],
               rec["p2_column"], rec["p2_value"],
               rec["p1_period"], rec["p2_period"]))


def _version_basis(rec):
    return ("p1/p2 的 s00_v10 version_used 均为 %s（ver_class=%s）；"
            "两段引文均不含「调整后/重述后/更正后」，即两期都取原版列，"
            "不存在跨版本相减。" % (rec["p1_ver"], pv.ver_class(rec["p1_ver"])))


def main():
    rows = list(csv.DictReader(io.open(OUT / "step4_parent_scan.csv",
                                       encoding="utf-8-sig", newline="")))
    out = []
    for r in rows:
        if r["verdict"] != "EVIDENCE_OK":
            continue
        v1, v2 = pv.ver_class(r["p1_ver"]), pv.ver_class(r["p2_ver"])
        if v1 is None or v1 != v2:
            continue
        out.append({
            "security_id": r["security_id"],
            "field_id": r["field_id"],
            "period_key": r["period_key"],
            "ytd_field": r["ytd_field"],
            "p1_period": r["p1_period"],
            "p2_period": r["p2_period"],
            "p1_doc": r["p1_doc"],
            "p2_doc": r["p2_doc"],
            "p1_value": r["p1_value"],
            "p2_value": r["p2_value"],
            "p1_page": r["p1_evidence_page"],
            "p2_page": r["p2_evidence_page"],
            "p1_quote": r["p1_quote"],
            "p2_quote": r["p2_quote"],
            "p1_column": r["p1_column"],
            "p2_column": r["p2_column"],
            "p1_adjust_version": v1,
            "p2_adjust_version": v2,
            "consolidation_scope": r["p1_scope"],
            "unit_scale": r["p1_unit"],
            "currency": r["p1_cur"],
            "scope_basis": _basis(r),
            "version_basis": _version_basis(r),
            "conclusion": "COMPATIBLE",
            "review_role": "SELF_CHECK",
            "reviewer": REVIEWER,
            "reviewed_at": TODAY,
        })
    with io.open(OUT / "parent_verifications.csv", "w",
                 encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=pv.COLS)
        w.writeheader()
        w.writerows(out)
    print("registered", len(out), "of", len(rows))
    print("by field:", sorted({r["field_id"] for r in out}))


if __name__ == "__main__":
    main()
