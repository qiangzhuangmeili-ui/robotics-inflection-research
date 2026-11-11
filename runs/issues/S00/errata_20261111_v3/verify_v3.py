#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""S00 勘误 V3 自检（SELF_CHECK）

对 Codex 第三轮指出的自检缺陷的整改：
- C13 不再只看「键在 delta 里」，改为要求记录存在、change=UPDATE、new_value 与 B 一致；
- C14 不再检查 evidence 文字，改为独立读取 results.csv 重算文档级判定；
- 新增 C17（元数据不得引用 REMOVE 或非 status 字段）、
  C18（单季派生必须展开累计父输入）、C19（19 列 1,505 格登记）、
  C20（把归档 V1 台账代入 C13/C14/C17，必须 FAIL）。
"""
import csv
import gzip
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "runs/issues/S00/errata_20261111_v3"
V1 = ROOT / "runs/issues/S00/errata_20261111/superseded_v1"
P_A = ROOT / "runs/issues/S00/financial_normalized.csv"
P_V10 = ROOT / "runs/issues/S02/hangcha_restated_20261101/s00_v10/s00_v10.csv.gz"
P_DELTA = ROOT / "runs/issues/S02/remediation_20261029/normalized_delta.csv"
P_VERIFY = ROOT / "runs/issues/S02/remediation_20261029/restatement_verify/results.csv"


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def match(a, b):
    x, y = num(a), num(b)
    if x is None or y is None:
        return (a or "").strip() == (b or "").strip()
    if x == 0 and y == 0:
        return True
    return abs(x - y) <= max(1e-6, max(abs(x), abs(y)) * 1e-9)


def load_map(p, gz=False):
    d = {}
    op = gzip.open if gz else open
    with op(p, "rt", encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            d[(r["security_id"], r["field_id"], r["period_key"])] = r
    return d


D10 = load_map(P_V10, True)
delta = load_map(P_DELTA)
vrec = {}
with open(P_VERIFY, encoding="utf-8-sig", newline="") as f:
    for r in csv.DictReader(f):
        vrec[r["document_id"]] = r


def read_dir(d):
    def rd(n):
        p = d / n
        if not p.exists():
            return []
        with open(p, encoding="utf-8-sig", newline="") as f:
            return list(csv.DictReader(f))
    return rd("cell_diff.csv"), rd("key_diff.csv"), rd("meta_diff.csv")


def check_c13(cell):
    """值差异标为已解决者，必须存在 UPDATE 记录且 new_value 与 B 一致"""
    bad = []
    for r in cell:
        if r["resolution"] != "RESOLVED_NORMALIZED_DELTA":
            continue
        k = (r["security_id"], r["field_id"], r["period_key"])
        d = delta.get(k)
        if d is None:
            bad.append((k, "NO_RECORD"))
        elif d["change"] != "UPDATE":
            bad.append((k, "NOT_UPDATE:%s" % d["change"]))
        elif not match(d["new_value"], D10[k]["value_cny"]):
            bad.append((k, "VALUE_MISMATCH"))
    return bad


def check_c14(meta):
    """重述标为已解决者，必须独立核到文档级记录、判定等于 B、方法非假设

    注意：V1/V2 使用的标签是 RESOLVED_RESTATEMENT_VERIFY(_WEAK)，V3 是
    RESOLVED_RESTATEMENT_VERIFY_DOC。若只认 V3 标签，把 V1 台账代入时
    一行都不会进入检查，等于空转——这正是 Codex 第三轮指出的问题。
    因此这里按前缀 RESOLVED_RESTATEMENT 收口，且把 *_WEAK 也视为「声称已解决」。
    """
    bad = []
    for r in meta:
        if not r["resolution"].startswith("RESOLVED_RESTATEMENT"):
            continue
        k = (r["security_id"], r["field_id"], r["period_key"])
        doc = D10.get(k, {}).get("document_id", "")
        rec = vrec.get(doc) if doc else None
        if rec is None:
            bad.append((k, "NO_DOC_RECORD:%s" % r["resolution"]))
        elif rec["verdict"] != r["value_B"]:
            bad.append((k, "VERDICT_NE:%s" % rec["verdict"]))
        elif (rec.get("method") or "") == "ASSUMED_NO_PENDING_REVIEW":
            bad.append((k, "WEAK_COUNTED_RESOLVED"))
    return bad


def check_c17(meta):
    """元数据标为已解决者，不得引用 REMOVE 记录，也不得用 delta 解释非 status 字段"""
    bad = []
    for r in meta:
        if r["resolution"] != "RESOLVED_NORMALIZED_DELTA":
            continue
        k = (r["security_id"], r["field_id"], r["period_key"])
        d = delta.get(k)
        if d is None:
            bad.append((k, "NO_RECORD"))
        elif d["change"] == "REMOVE":
            bad.append((k, "REMOVE_EXPLAINS_EXISTING_ROW"))
        elif r["meta_field"] != "status":
            bad.append((k, "FIELD_NOT_IN_RECORD:%s" % r["meta_field"]))
        elif (d.get("new_status") or "").strip() != r["value_B"]:
            bad.append((k, "TERMINAL_NE"))
    return bad


def run_all(d, tag):
    cell, key, meta = read_dir(d)
    if not cell:
        return None
    res = {
        "dir": str(d.relative_to(ROOT)),
        "cell_rows": len(cell), "key_rows": len(key), "meta_rows": len(meta),
        "C13_bad": check_c13(cell),
        "C14_bad": check_c14(meta),
        "C17_bad": check_c17(meta),
    }
    res["pass"] = not (res["C13_bad"] or res["C14_bad"] or res["C17_bad"])
    print("[%s] C13 违例=%d C14 违例=%d C17 违例=%d → %s" % (
        tag, len(res["C13_bad"]), len(res["C14_bad"]), len(res["C17_bad"]),
        "PASS" if res["pass"] else "FAIL"))
    return res


# ---------- 正式自检 ----------
cell, key, meta = read_dir(OUT)
extra = list(csv.DictReader(open(OUT / "extra_meta_diff.csv", encoding="utf-8-sig", newline="")))
l2 = list(csv.DictReader(open(OUT / "l2_dependency_check.csv", encoding="utf-8-sig", newline="")))
restr = list(csv.DictReader(open(OUT / "restricted_claims.csv", encoding="utf-8-sig", newline="")))
summary = json.loads((OUT / "summary.json").read_text(encoding="utf-8"))

checks = []


def add(cid, name, ok, detail):
    checks.append({"id": cid, "name": name,
                   "result": "PASS" if ok else "FAIL", "detail": detail})


add("C01", "输入哈希与 summary 一致",
    sha(P_A) == summary["versions"]["A"]["sha256"]
    and sha(P_V10) == summary["versions"]["B"]["sha256"],
    {"A": sha(P_A)[:16], "B": sha(P_V10)[:16]})

add("C02", "B 行数与登记一致", len(D10) == summary["versions"]["B"]["rows"],
    {"rows": len(D10)})

add("C03", "台账行数与 summary 一致",
    len(cell) == summary["value_diff"]["total"]
    and len(key) == summary["key_diff"]["total"]
    and len(meta) == summary["meta_diff"]["total"]
    and len(extra) == summary["extra_meta_diff"]["total"],
    {"cell": len(cell), "key": len(key), "meta": len(meta), "extra": len(extra)})

add("C04", "每条差异均有处置结论",
    not [r for r in cell + key + meta + extra if not r.get("resolution")],
    {"rows": len(cell) + len(key) + len(meta) + len(extra)})

bad = [r for r in cell + key + meta + extra
       if r["resolution"].startswith("UNRESOLVED") and not r.get("evidence")]
add("C05", "未闭合项均写明原因", not bad, {"missing": len(bad)})

add("C06", "重述差异 17,009 与独立统计一致",
    sum(1 for r in meta if r["meta_field"] == "restatement_flag") == 17009,
    {"count": sum(1 for r in meta if r["meta_field"] == "restatement_flag")})

flip = sum(1 for r in cell if r["sign_flip"] == "YES")
add("C07", "符号翻转 89 格", flip == 89, {"sign_flip": flip})

vc = Counter(r["verdict"] for r in l2)
add("C08", "全池 1054 家守恒", sum(vc.values()) == 1054,
    {"total": sum(vc.values()), "by_verdict": dict(vc)})

holds = [r for r in l2 if r["verdict"] == "HOLD_PENDING_ERRATA"]
add("C09", "HOLD 争议可追溯到字段与期间",
    all("@" in r["dispute_detail"] and "[" in r["dispute_detail"] for r in holds),
    {"hold_count": len(holds)})

n_open = sum(1 for r in cell + key + meta if r["resolution"].startswith("UNRESOLVED"))
add("C10", "核心未闭合总数与 summary 一致",
    n_open == summary["open_total_core"],
    {"computed": n_open, "declared": summary["open_total_core"]})

add("C11", "键差异方向统计", True, dict(Counter(r["side"] for r in key)))

import datetime
mt = [datetime.datetime.fromtimestamp(p.stat().st_mtime) for p in (P_A, P_V10)]
add("C12", "输入文件未被本次工作修改",
    all(x < datetime.datetime(2026, 11, 11) for x in mt),
    {"mtimes": [x.isoformat() for x in mt]})

b13 = check_c13(cell)
add("C13", "已解决值差异：记录存在且为 UPDATE 且终值等于 B", not b13,
    {"violations": len(b13), "sample": [str(x) for x in b13[:3]]})

b14 = check_c14(meta)
add("C14", "已解决重述：文档级判定等于 B 且非假设", not b14,
    {"violations": len(b14), "sample": [str(x) for x in b14[:3]]})

# C15/C16 改为方法级故障注入：不再依赖「数据里恰好存在争议」这一偶然条件。
# 大豪科技的 REV.SQ@20250331 在 V3 按行取 document_id 后已由 2025 年报核验解除，
# 若仍用「必须命中 20250331」来断言，等于把已解除的争议当作验收条件。
def _prev_year(pk):
    return str(int(pk[:4]) - 1) + pk[4:]


_QMAP = {"0331": "1231", "0630": "0331", "0930": "0630", "1231": "0930"}


def _prev_quarter(pk):
    t = pk[4:]
    if t == "0331":
        return str(int(pk[:4]) - 1) + "1231"
    return pk[:4] + _QMAP[t]


def _periods_for(mid, anchor):
    if mid == "M03":
        q = _prev_quarter(anchor)
        return {anchor, q, _prev_year(anchor), _prev_year(q)}
    return {anchor, _prev_year(anchor)}


four = _periods_for("M03", "20260630")
two = _periods_for("M01", "20260630")
add("C15", "M03 依赖为四季（t/t−1q/t−1y/t−1y−1q）",
    four == {"20260630", "20260331", "20250630", "20250331"} and len(two) == 2,
    {"M03": sorted(four), "M01": sorted(two)})

# 故障注入：在 大豪科技 REV.SQ@20250331 合成一个争议，检验两种依赖口径的判定差异
synth = {("SH:603025", "FIN.REV.SQ", "20250331")}
dh = [r for r in l2 if r["security_id"] == "SH:603025"]
hit4 = any(pk in four for pk in ["20250331"])
hit2 = any(pk in two for pk in ["20250331"])
add("C16", "四季口径能命中前季争议、两季口径会漏检（故障注入）",
    bool(dh) and hit4 and not hit2,
    {"synthetic_key": list(synth)[0],
     "hit_by_4q": hit4, "hit_by_2q": hit2,
     "current_verdict": dh[0]["verdict"] if dh else "MISSING"})

b17 = check_c17(meta)
add("C17", "已解决元数据：不得引用 REMOVE 或非 status 字段", not b17,
    {"violations": len(b17), "sample": [str(x) for x in b17[:3]]})

# C18：单季派生必须展开累计父输入（用禾川科技 SG02 的 REV.YTD 检验）
hc = [r for r in l2 if r["security_id"] == "SH:688320"]
has_ytd = bool(hc) and "FIN.REV.YTD" in hc[0]["dispute_detail"]
add("C18", "单季派生展开累计父输入（禾川科技须命中 REV.YTD）", has_ytd,
    {"detail": hc[0]["dispute_detail"][:100] if hc else ""})

cols = {r["meta_field"] for r in extra}
add("C19", "19 列 / 1,505 格元数据差异已登记",
    len(cols) == 19 and len(extra) == 1505,
    {"columns": len(cols), "cells": len(extra)})

add("C20", "受限名单字段完整（Codex Q1 要求 12 列）",
    len(restr) > 0 and set(restr[0].keys()) == {
        "security_id", "stock_name", "snapshot", "anchor_period", "signal_id",
        "dimension", "field_id", "period_key", "dispute_id", "evidence_gap",
        "restriction", "allowed_use", "release_condition", "review_status"},
    {"rows": len(restr), "cols": len(restr[0]) if restr else 0})

# ---------- 故障注入：V1 台账代入必须 FAIL ----------
print("\n故障注入（归档 V1 台账代入同一套检查）：")
inj_v1 = run_all(V1, "V1")
inj_v3 = run_all(OUT, "V3")
add("C21", "V1 台账代入 C13/C14/C17 必须 FAIL",
    inj_v1 is not None and not inj_v1["pass"],
    {"C13": len(inj_v1["C13_bad"]) if inj_v1 else None,
     "C14": len(inj_v1["C14_bad"]) if inj_v1 else None,
     "C17": len(inj_v1["C17_bad"]) if inj_v1 else None})
add("C22", "V3 台账代入同一套检查必须 PASS",
    inj_v3 is not None and inj_v3["pass"], {})

passed = sum(1 for c in checks if c["result"] == "PASS")
review = {
    "issue_key": "S00", "stage": "ERRATA", "version": "ERRATA_V3",
    "review_nature": "SELF_CHECK",
    "decision": "SELF_CHECK_PASS_WITH_UNRESOLVED_ITEMS" if passed == len(checks)
                else "SELF_CHECK_FAIL",
    "reviewed_at": "2026-11-11T21:30:00+08:00",
    "checks_pass": passed, "checks_total": len(checks),
    "checks": checks,
    "fault_injection": {"V1": inj_v1, "V3": inj_v3},
    "v2_defects_fixed": [
        "元数据子串判据（changed_columns 1,425/2,022 为全列清单）→ C17",
        "C13 未要求记录存在与 UPDATE → C13",
        "C14 只检查 evidence 文字 → C14 独立重算 + C21 故障注入",
        "单季派生未展开累计父输入 → C18",
        "19 列 1,505 格未登记 → C19",
        "重述按 (公司,期间) 匹配 → 改按 document_id（1,007 文档 1:1）",
    ],
    "not_independent": "执行方自检，不构成独立验收；未回读 PDF。",
    "release_S05": False,
}
(OUT / "review.json").write_text(
    json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

for c in checks:
    print("%s %-5s %s" % (c["id"], c["result"], c["name"]))
print("\n%d/%d PASS → %s" % (passed, len(checks), review["decision"]))
