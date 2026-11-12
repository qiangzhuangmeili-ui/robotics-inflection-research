#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""第 4 步 · 批次 A：把扫描结果写成**文档级事件确认登记表**

输入：`step4_event_scan.csv`（原件扫描的原始事实，只读产物）
输出：`event_verifications.csv`（核证登记表，`build_errata_v5.py` 与自检共同消费）

只登记 `DOC_NO_ERRATA` 一类：原件里**明确写着**该文档该期不存在（重大）前期差错更正。
其余状态（NOT_FOUND / NOTE_ONLY / DOC_HAS_ERRATA / NO_ORIGINAL / UNPARSED）一律不登记——
「没找到」不等于「没有」，这类必须继续待核。

登记内容刻意保持「一条文档一行」，不按字段展开：
- 事实是文档级的，按字段抄 4,606 行会把一条证据伪装成 4,606 条独立证据；
- 字段映射规则写在 `scope` / `scope_note` 里，由 `evidence_scope.judge()` 统一执行。

口径（务必与 judge 的注释一致）
--------------------------------
- `cause` 只有 `ERRATA`：会计政策变更、同一控制下合并范围变更都不在本条证据范围内。
- `scope` = `WHOLE_STATEMENT`：覆盖该文档该期**全部财务报表项目**（同质字段组）。
- `scope_note` 必须写明「年报该项只要求披露**重大**会计差错更正」这条限制。
"""
import csv
import io
import pathlib
import sys

OUT = pathlib.Path(__file__).resolve().parent

STATEMENT = {
    "ANNUAL": "公司对重大会计差错更正原因及影响的分析说明",
    "HALF": "是否存在前期差错更正",
}
REVIEWER = "workbuddy-agent:step4-batchA"
REVIEWED_AT = "2026-11-12T19:50:00+08:00"

COLS = ["document_id", "security_id", "period", "source_page", "quote",
        "statement", "option", "cause", "scope", "scope_note",
        "evidence_class", "reviewer", "reviewed_at"]


def main():
    src = list(csv.DictReader(io.open(OUT / "step4_event_scan.csv", encoding="utf-8-sig")))
    rows = []
    for r in src:
        if r["status"] != "DOC_NO_ERRATA":
            continue
        kind = r["source_kind"]
        stmt = STATEMENT.get(kind)
        if not stmt:
            continue
        note = r["scope_note"]
        rows.append({
            "document_id": r["document_id"],
            "security_id": r["security_id"],
            "period": r["period"],
            "source_page": r["page"],
            "quote": r["quote"],
            "statement": stmt,
            "option": "不适用" if kind == "ANNUAL" else "否",
            "cause": "ERRATA",
            "scope": "WHOLE_STATEMENT",
            "scope_note": note,
            "evidence_class": "DOC_LEVEL_EVENT_CONFIRMATION",
            "reviewer": REVIEWER,
            "reviewed_at": REVIEWED_AT,
        })
    with io.open(OUT / "event_verifications.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        w.writerows(rows)
    print("登记 %d 份文档（DOC_NO_ERRATA）→ event_verifications.csv" % len(rows))
    skipped = len(src) - len(rows)
    print("未登记 %d 份（NOT_FOUND / NOTE_ONLY / DOC_HAS_ERRATA / NO_ORIGINAL 等），继续待核" % skipped)


if __name__ == "__main__":
    sys.exit(main())
