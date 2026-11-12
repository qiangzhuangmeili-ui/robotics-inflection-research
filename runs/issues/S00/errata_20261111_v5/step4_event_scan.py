#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""第 4 步 · 批次 A：文档级事件确认（只读扫描，不写核证登记表）

目的
----
`meta_diff.csv` 里 4,606 条待核（331 份文档）的 `scope_required` 只有 `ERRATA`，
其余维度都已覆盖。它们卡在同一件事上：**证据没有绑定到字段**（`binds_field()` 为假），
因为上游核验方法是 `IMPORTANT_MATTER_NA` / `NOTE_RETAINED_ERRATA_ZERO` 这类
「整节不适用」的写法。

第 4 步要补的正是「文档级事件确认 → 字段级影响确认」这条链：
先在原件里把**文档对该期是否发生前期差错更正**这句话找出来（页码 + 原文 + 勾选项），
再判断这句话的适用范围能否覆盖到该字段。

本脚本只做第一步：扫描 + 落一份**原始事实清单**，不做任何放行判定。
判定与放行留给 `step4_apply_events.py`（尚未启用），必须等本清单抽样核对通过。

输出
----
- `step4_event_scan.csv`：每份文档一行，含命中位置、页码、原文片段、勾选项、状态
- 控制台摘要：命中率、选项分布、未定位清单

口径纪律
--------
- 引文一律来自原件，`quote` 为**原文连续片段**（去空白后），页码为 PDF 物理页。
- 勾选项解析不出（两个都空框 / 一个都没有）→ `UNPARSED`，不得当作「否」。
- 年报该项标题含「重大」二字，**只覆盖重大会计差错更正**；这条限制写进 `scope_note`，
  不允许在后续判定里被当成「本期无任何差错更正」。
"""
import csv
import io
import json
import pathlib
import re
import sys

OUT = pathlib.Path(__file__).resolve().parent
ORIG = pathlib.Path("D:/StockResearchLab/IndustryInflectionLab/robotics_data/collection/originals")

# 年报：第五节 重要事项 → 五、(二) 公司对重大会计差错更正原因及影响的分析说明
# 半年报：第三节 管理层讨论/附注事项索引 → 3．是否存在前期差错更正
# 附注：前期差错更正 / 重要会计政策、会计估计的变更
LABELS = [
    ("ANNUAL_IMPORTANT", r"公司对重大会计差错更正原因及影响的分析说明"),
    ("HALF_INDEX", r"是否存在前期差错更正"),
    ("NOTE_ERRATA", r"前期差错更正"),
]
CHECKED = "√☑■✓●"
BOX = "□▢◻"
_RE_OPT = re.compile(r"([" + CHECKED + BOX + r"])\s*(不适用|适用|是|否)")

# 命中标签后向前取多少字作为「勾选窗口」——表格里标签与勾选常被换行拆开
WIN = 40


def norm(t):
    return re.sub(r"\s+", "", t or "")


def scan_doc(pdf_path):
    """返回 [(kind, page, quote, option, marker), ...]，按页码升序。"""
    import pymupdf
    hits = []
    d = pymupdf.open(str(pdf_path))
    try:
        pages = [d[i].get_text() for i in range(d.page_count)]
    finally:
        d.close()
    for kind, pat in LABELS:
        rx = re.compile(pat)
        for i, raw in enumerate(pages):
            n = norm(raw)
            for m in rx.finditer(n):
                win = n[m.end():m.end() + WIN]
                # 窗口必须在**下一个子项标题**处截断：`（二）…□适用√不适用（三）与前任…□适用√不适用`
                # 若不截断，窗口里会出现两组勾选，被误判为「多处勾选」。
                cut = re.search(r"[（(][一二三四五六七八九十]", win)
                if cut:
                    win = win[:cut.start()]
                # 「□适用√不适用」是**两个**选项，第一个是空框，勾在第二个上。
                # 只看第一个匹配会把「否」误读成「未解析」——第十五轮同款错误。
                opts = [(x.group(1), x.group(2)) for x in _RE_OPT.finditer(win)]
                if not opts:
                    continue
                ck = [(mk, wd) for mk, wd in opts if mk in CHECKED]
                if len(ck) == 1:
                    marker, word = ck[0]
                    state = "CHECKED"
                elif len(ck) > 1:
                    marker, word, state = "", "", "MULTI_CHECKED"
                else:
                    marker, word = opts[0]
                    state = "BLANK"
                quote = n[max(0, m.start() - 12):min(len(n), m.end() + WIN)]
                hits.append({
                    "kind": kind, "page": i + 1, "quote": quote,
                    "option": word, "marker": marker, "state": state,
                    "label": m.group(0),
                })
                break          # 同一页同一标签只取第一处
            if hits and hits[-1]["kind"] == kind and hits[-1]["page"] == i + 1:
                break          # 同一 kind 只取首处命中
    return hits


def decide(hits):
    """把命中归成一条文档级结论；**不猜**。"""
    imp = [h for h in hits if h["kind"] == "ANNUAL_IMPORTANT"]
    idx = [h for h in hits if h["kind"] == "HALF_INDEX"]
    note = [h for h in hits if h["kind"] == "NOTE_ERRATA"]

    def pick(lst):
        ck = [h for h in lst if h["state"] == "CHECKED"]
        return ck[0] if len(ck) == 1 else (None if not ck else "AMBIG")

    a, b = pick(imp), pick(idx)
    if a == "AMBIG" or b == "AMBIG":
        return "UNPARSED", "", "", "同一标签下多处勾选，需回读原页", None
    if a and a["option"] == "不适用":
        return ("DOC_NO_ERRATA", a["page"], a["quote"], a["marker"],
                "年报重要事项（二）：重大会计差错更正 □适用 √不适用；"
                "**仅覆盖「重大」差错更正**，非重大更正不在该项披露范围", "ANNUAL")
    if a and a["option"] == "适用":
        return ("DOC_HAS_ERRATA", a["page"], a["quote"], a["marker"],
                "年报重要事项（二）勾「适用」：需回读差错更正附注取受影响项目清单", "ANNUAL")
    if b and b["option"] == "否":
        return ("DOC_NO_ERRATA", b["page"], b["quote"], b["marker"],
                "半年报附注事项索引第 3 项「是否存在前期差错更正」勾「否」；"
                "该项未限定「重大」", "HALF")
    if b and b["option"] == "是":
        return ("DOC_HAS_ERRATA", b["page"], b["quote"], b["marker"],
                "半年报附注事项索引第 3 项勾「是」：需回读差错更正附注", "HALF")
    if note:
        h = note[0]
        return ("NOTE_ONLY", h["page"], h["quote"], h["marker"],
                "只找到附注标题，未解析出勾选项", "NOTE")
    return "NOT_FOUND", "", "", "", "未在原件定位到差错更正披露项", None


def main():
    docs = json.loads((OUT / "_step4_docs.json").read_text(encoding="utf-8"))
    rows = []
    for k, d in enumerate(docs, 1):
        sec, doc, pk = d["security_id"], d["document_id"], d["document_period"]
        code = sec.split(":")[-1]
        pdf = next((p for p in (ORIG / code).rglob(doc + ".pdf")), None)
        if pdf is None:
            rows.append({"security_id": sec, "document_id": doc, "period": pk,
                         "status": "NO_ORIGINAL", "page": "", "option": "",
                         "marker": "", "quote": "", "scope_note": "原件不在本地",
                         "source_kind": ""})
            continue
        try:
            hits = scan_doc(pdf)
            st, page, quote, marker, note, src = decide(hits)
        except Exception as e:                                   # noqa: BLE001
            st, page, quote, marker, note, src = (
                "SCAN_ERROR", "", "", "", "读取失败：%s" % str(e)[:60], "")
        rows.append({"security_id": sec, "document_id": doc, "period": pk,
                     "status": st, "page": page, "option": marker,
                     "marker": marker, "quote": quote, "scope_note": note,
                     "source_kind": src})
        if k % 50 == 0:
            print("  ... %d/%d" % (k, len(docs)), flush=True)

    cols = ["security_id", "document_id", "period", "status", "source_kind",
            "page", "marker", "quote", "scope_note"]
    with io.open(OUT / "step4_event_scan.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in cols})

    from collections import Counter
    c = Counter(r["status"] for r in rows)
    print("\n== 文档级扫描结果（%d 份）==" % len(rows))
    for k, v in c.most_common():
        print("  %-22s %4d" % (k, v))
    print("\n== 未定位/异常清单 ==")
    for r in rows:
        if r["status"] in ("NOT_FOUND", "NO_ORIGINAL", "SCAN_ERROR", "UNPARSED"):
            print("  %-12s %-22s %s %s" % (r["security_id"], r["document_id"],
                                           r["status"], r["scope_note"][:40]))
    print("\n输出 step4_event_scan.csv")


if __name__ == "__main__":
    sys.exit(main())
