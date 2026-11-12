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

SCOPE_WORD = {"CONSOLIDATED": "合并", "PARENT": "母公司", "PARENT_ONLY": "母公司"}
UNIT_WORD = {"1": "元", "1000": "千元", "10000": "万元"}
CUR_WORD = {"CNY": "人民币", "RMB": "人民币", "USD": "美元", "HKD": "港元"}


def _basis(rec):
    """口径依据：把「为什么两期可比」写成可核对的句子，而不是一句「已核」。

    第十九轮 D4：C41 现在会验这句话的**内容**——必须点到合并范围、金额单位、
    币种和至少一个具体期间。所以这里不能只写代码值（`CONSOLIDATED`/`1`/`CNY`），
    要把它们连同中文口径名一起写出来。
    """
    scope = SCOPE_WORD.get(rec["p1_scope"], rec["p1_scope"])
    unit = UNIT_WORD.get(rec["p1_unit"], rec["p1_unit"])
    cur = CUR_WORD.get(rec["p1_cur"], rec["p1_cur"])
    return ("%s：两期均为%s口径（%s）、币种 %s（%s）、金额单位 %s（unit_scale=%s）；"
            "p1 取 %s 第 %s 页「%s」列，值 %s（期间 %s）；"
            "p2 取 %s 第 %s 页「%s」列，值 %s（期间 %s）。"
            "两处数值分别等于 s00_v10 的采用值，故 %s 与 %s 两期累计同口径可直接相减。"
            % (rec["stock_name"], scope, rec["p1_scope"], cur, rec["p1_cur"],
               unit, rec["p1_unit"],
               rec["p1_doc"], rec["p1_evidence_page"], rec["p1_column"],
               rec["p1_value"], rec["p1_period"],
               rec["p2_doc"], rec["p2_evidence_page"],
               rec["p2_column"], rec["p2_value"], rec["p2_period"],
               rec["p1_period"], rec["p2_period"]))


def _version_basis(rec):
    """版本依据：必须写出**两侧各自的**版本归类，且句子内容与事实相符。

    第十九轮 D4：原实现无论两侧是不是 RESTATED，都写「两段引文均不含
    「调整后/重述后/更正后」，即两期都取原版列」——版本是 RESTATED 时这句话
    本身是假的。C41 现在会验这句话的内容，写假话就过不了。
    """
    v1, v2 = pv.ver_class(rec["p1_ver"]), pv.ver_class(rec["p2_ver"])
    seg = []
    for side, v in (("p1", v1), ("p2", v2)):
        if v == "RESTATED":
            seg.append("%s 的 s00_v10 version_used 为 %s，取重述/调整后列"
                       "（引文含「调整后/重述后/更正后」标记）" % (side, rec[side + "_ver"]))
        else:
            seg.append("%s 的 s00_v10 version_used 为 %s，取原版列"
                       "（引文不含「调整后/重述后/更正后」）" % (side, rec[side + "_ver"]))
    return "；".join(seg) + "。两期版本归类一致，不存在跨版本相减。"


def main():
    rows = list(csv.DictReader(io.open(OUT / "step4_parent_scan.csv",
                                       encoding="utf-8-sig", newline="")))
    # 第十九轮裁决：独立列身份旁证必须通过才登记。旁证走另一套几何
    # （数字右边界格 + 中点分列），不调用取列函数。
    wit = {}
    p_wit = OUT / "step4_column_witness.csv"
    if p_wit.exists():
        for r in csv.DictReader(io.open(p_wit, encoding="utf-8-sig", newline="")):
            wit[(r["security_id"], r["field_id"], r["period_key"])] = r["verdict"]
    out = []
    skipped = {"not_evidence_ok": 0, "version_inconsistent": 0, "witness_fail": 0}
    for r in rows:
        if r["verdict"] != "EVIDENCE_OK":
            skipped["not_evidence_ok"] += 1
            continue
        if wit.get((r["security_id"], r["field_id"], r["period_key"])) != "WITNESS_OK":
            skipped["witness_fail"] += 1
            continue
        v1, v2 = pv.ver_class(r["p1_ver"]), pv.ver_class(r["p2_ver"])
        if v1 is None or v1 != v2:
            skipped["version_inconsistent"] += 1
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
    print("skipped", skipped)
    print("by field:", sorted({r["field_id"] for r in out}))


if __name__ == "__main__":
    main()
