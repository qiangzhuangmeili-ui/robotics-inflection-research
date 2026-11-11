#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""S00 勘误台账自检 v2（SELF_CHECK）

在 v1 的 12 项之外，增加 4 项针对 Codex 第二轮指出缺陷的回归检查：
C13 UPDATE 记录值一致性、C14 重述多记录无歧义、C15 M03 四季度依赖、C16 大豪科技不再误判。
"""
import csv
import gzip
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "runs/issues/S00/errata_20261111"
P_A = ROOT / "runs/issues/S00/financial_normalized.csv"
P_V10 = ROOT / "runs/issues/S02/hangcha_restated_20261101/s00_v10/s00_v10.csv.gz"


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def read(name):
    with open(OUT / name, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


cell, key, meta = read("cell_diff.csv"), read("key_diff.csv"), read("meta_diff.csv")
l2 = read("l2_dependency_check.csv")
summary = json.loads((OUT / "summary.json").read_text(encoding="utf-8"))
sup = json.loads((ROOT / "runs/issues/S00/supersession.json").read_text(encoding="utf-8"))

checks = []


def add(cid, name, ok, detail):
    checks.append({"id": cid, "name": name,
                   "result": "PASS" if ok else "FAIL", "detail": detail})


def load(p, gz=False):
    d = {}
    op = gzip.open if gz else open
    with op(p, "rt", encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            d[(r["security_id"], r["field_id"], r["period_key"])] = r
    return d


D10 = load(P_V10, gz=True)
delta = {}
with open(ROOT / "runs/issues/S02/remediation_20261029/normalized_delta.csv",
          encoding="utf-8-sig", newline="") as f:
    for r in csv.DictReader(f):
        delta[(r["security_id"], r["field_id"], r["period_key"])] = r


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


# C01 输入哈希
add("C01", "输入哈希与 supersession.json 一致",
    sha(P_A) == sup["superseded"][0]["sha256"]
    and sha(P_V10) == sup["authoritative"]["sha256"],
    {"A": sha(P_A)[:16], "B": sha(P_V10)[:16]})

# C02 行数
add("C02", "行数与登记表一致",
    len(D10) == sup["authoritative"]["rows"], {"B_rows": len(D10)})

# C03 台账与 summary 一致
add("C03", "台账行数与 summary 一致",
    len(cell) == summary["value_diff"]["total"]
    and len(key) == summary["key_diff"]["total"]
    and len(meta) == summary["meta_diff"]["total"],
    {"cell": len(cell), "key": len(key), "meta": len(meta)})

# C04 每行有处置
add("C04", "每条差异均有处置结论",
    not [r for r in cell + key + meta if not r.get("resolution")],
    {"rows": len(cell) + len(key) + len(meta)})

# C05 未闭合有原因
bad = [r for r in cell + key + meta
       if r["resolution"].startswith("UNRESOLVED") and not r.get("evidence")]
add("C05", "未闭合项均写明原因", not bad, {"missing": len(bad)})

# C06 重述差异总数
add("C06", "重述差异 17,009 与独立统计一致",
    sum(1 for r in meta if r["meta_field"] == "restatement_flag") == 17009,
    {"count": sum(1 for r in meta if r["meta_field"] == "restatement_flag")})

# C07 符号翻转
flip = sum(1 for r in cell if r["sign_flip"] == "YES")
add("C07", "符号翻转 89 格与独立统计一致", flip == 89, {"sign_flip": flip})

# C08 全池守恒
vc = Counter(r["verdict"] for r in l2)
add("C08", "全池 1054 家判定守恒", sum(vc.values()) == 1054,
    {"total": sum(vc.values()), "by_verdict": dict(vc)})

# C09 HOLD 可追溯
holds = [r for r in l2 if r["verdict"] == "HOLD_PENDING_ERRATA"]
add("C09", "HOLD 家争议可追溯到具体字段与期间",
    all("@" in r["dispute_detail"] and "[" in r["dispute_detail"] for r in holds),
    {"hold_count": len(holds)})

# C10 未闭合总数
n_open = sum(1 for r in cell + key + meta
             if r["resolution"].startswith("UNRESOLVED") or r["resolution"].endswith("_WEAK"))
add("C10", "未闭合总数与 summary 一致", n_open == summary["open_total"],
    {"computed": n_open, "declared": summary["open_total"]})

# C11 键方向
add("C11", "键差异方向统计", True, dict(Counter(r["side"] for r in key)))

# C12 输入未被修改
import datetime
mt = [datetime.datetime.fromtimestamp(p.stat().st_mtime) for p in (P_A, P_V10)]
add("C12", "输入文件未被本次工作修改",
    all(x < datetime.datetime(2026, 11, 11) for x in mt),
    {"mtimes": [x.isoformat() for x in mt]})

# C13 UPDATE 记录值一致性（v1 缺陷回归）
bad = []
for r in cell:
    if r["resolution"] != "RESOLVED_NORMALIZED_DELTA":
        continue
    k = (r["security_id"], r["field_id"], r["period_key"])
    if k in delta and not match(delta[k]["new_value"], D10[k]["value_cny"]):
        bad.append(k)
add("C13", "标为已解决的值差异，其记录值与实际值一致", not bad,
    {"inconsistent": len(bad), "sample": bad[:3]})

# C14 重述多记录无歧义
bad = [r for r in meta if r["resolution"] == "UNRESOLVED_AMBIGUOUS_MULTI_RECORD"]
leaked = [r for r in meta if r["resolution"].startswith("RESOLVED_RESTATEMENT")
          and r["evidence"].startswith("核验判定=")]
add("C14", "重述多记录互斥者未被标为已解决", not leaked,
    {"ambiguous_marked": len(bad), "leaked": len(leaked)})

# C15 M03 四季度依赖（大豪科技必须命中）
dh = [r for r in l2 if r["security_id"] == "SH:603025"]
hit_2025q1 = bool(dh) and "20250331" in dh[0]["dispute_detail"]
add("C15", "SG02(M03) 覆盖前季与上年同期", hit_2025q1,
    {"SH:603025_verdict": dh[0]["verdict"] if dh else "MISSING",
     "detail": dh[0]["dispute_detail"][:80] if dh else ""})

# C16 大豪科技不再误判 NOT_AFFECTED
add("C16", "大豪科技不再被误判为未受影响",
    bool(dh) and dh[0]["verdict"] != "NOT_AFFECTED",
    {"verdict": dh[0]["verdict"] if dh else "MISSING"})

passed = sum(1 for c in checks if c["result"] == "PASS")
review = {
    "issue_key": "S00", "stage": "ERRATA", "version": "ERRATA_V2",
    "review_nature": "SELF_CHECK",
    "decision": "SELF_CHECK_PASS_WITH_UNRESOLVED_ITEMS" if passed == len(checks)
                else "SELF_CHECK_FAIL",
    "reviewed_at": "2026-11-11T19:00:00+08:00",
    "checks_pass": passed, "checks_total": len(checks),
    "checks": checks,
    "v1_defects_fixed": [
        "UPDATE new_value 未校验（6 格）→ C13",
        "元数据同键兜底（19 条）→ 改为 changed_columns 必须含该字段",
        "重述多记录取首条（47 条不一致）→ C14 + AMBIGUOUS 标记",
        "SG02 依赖期间漏前季（大豪科技）→ C15/C16",
    ],
    "not_independent": "执行方自检，不构成独立验收；未回读 PDF。",
    "release_S05": False,
}
(OUT / "review.json").write_text(
    json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

for c in checks:
    print("%s %-5s %s" % (c["id"], c["result"], c["name"]))
print("\n%d/%d PASS → %s" % (passed, len(checks), review["decision"]))
