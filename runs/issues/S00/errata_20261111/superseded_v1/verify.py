#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""S00 勘误台账自检（SELF_CHECK）

逐项验证台账内部一致性、与独立统计的吻合度、以及对输入文件的零修改。
输出 review.json。这不是独立验收，检查项全部为机械可复算的守恒与对账。
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
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read(name):
    with open(OUT / name, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


cell = read("cell_diff.csv")
key = read("key_diff.csv")
meta = read("meta_diff.csv")
impact = read("downstream_impact.csv")
l2 = read("l2_dependency_check.csv")
summary = json.loads((OUT / "summary.json").read_text(encoding="utf-8"))
sup = json.loads((ROOT / "runs/issues/S00/supersession.json").read_text(encoding="utf-8"))

checks = []


def add(cid, name, ok, detail):
    checks.append({"id": cid, "name": name, "result": "PASS" if ok else "FAIL",
                   "detail": detail})


# C01 输入哈希与登记表一致
a_sha = sha(P_A)
b_sha = sha(P_V10)
ok = (a_sha == sup["superseded"][0]["sha256"] and b_sha == sup["authoritative"]["sha256"])
add("C01", "输入哈希与 supersession.json 一致", ok,
    {"A": a_sha[:16], "B": b_sha[:16]})

# C02 行数与登记表一致
def count_rows(p, gz=False):
    n = 0
    op = gzip.open if gz else open
    with op(p, "rt", encoding="utf-8-sig", newline="") as f:
        for _ in csv.DictReader(f):
            n += 1
    return n


ra, rb = count_rows(P_A), count_rows(P_V10, gz=True)
add("C02", "行数与登记表一致", ra == sup["superseded"][0]["rows"] and rb == sup["authoritative"]["rows"],
    {"A_rows": ra, "B_rows": rb})

# C03 台账总数与 summary 一致
add("C03", "台账行数与 summary 一致",
    len(cell) == summary["value_diff"]["total"]
    and len(key) == summary["key_diff"]["total"]
    and len(meta) == summary["meta_diff"]["total"],
    {"cell": len(cell), "key": len(key), "meta": len(meta)})

# C04 每行都有 resolution
bad = [r for r in cell + key + meta if not r.get("resolution")]
add("C04", "每条差异均有处置结论", not bad, {"missing_resolution": len(bad)})

# C05 UNRESOLVED 均有 evidence 说明
bad = [r for r in cell + key + meta
       if r["resolution"].startswith("UNRESOLVED") and not r.get("evidence")]
add("C05", "未解决项均写明原因", not bad, {"unresolved_without_evidence": len(bad)})

# C06 重述差异与独立统计一致
restate = [r for r in meta if r["meta_field"] == "restatement_flag"]
add("C06", "重述差异 17,009 与独立统计一致", len(restate) == 17009, {"count": len(restate)})

# C07 值差异符号翻转与独立统计一致
flip = sum(1 for r in cell if r["sign_flip"] == "YES")
add("C07", "符号翻转 89 格与独立统计一致", flip == 89, {"sign_flip": flip})

# C08 445 家判定守恒
vc = Counter(r["verdict"] for r in l2)
add("C08", "445 家判定守恒", sum(vc.values()) == 445,
    {"total": sum(vc.values()), "by_verdict": dict(vc)})

# C09 HOLD 家的争议可追溯到具体格
holds = [r for r in l2 if r["verdict"] == "HOLD_PENDING_ERRATA"]
traceable = all(r["dispute_detail"] and "@" in r["dispute_detail"] for r in holds)
add("C09", "HOLD 家争议可追溯到具体字段与期间", traceable,
    {"hold_count": len(holds), "ids": [r["security_id"] for r in holds]})

# C10 未解决总数对账
n_unres = sum(1 for r in cell + key + meta if r["resolution"].startswith("UNRESOLVED"))
declared = sum(sup["errata"]["unresolved_breakdown"].values())
add("C10", "未解决总数与登记表一致", n_unres == declared,
    {"computed": n_unres, "declared": declared})

# C11 仅 B 有 / 仅 A 有 方向统计
sides = Counter(r["side"] for r in key)
add("C11", "键差异方向统计", True, dict(sides))

# C12 输入文件未被修改（mtime 早于本次运行）
import datetime
mt_a = datetime.datetime.fromtimestamp(P_A.stat().st_mtime)
mt_b = datetime.datetime.fromtimestamp(P_V10.stat().st_mtime)
add("C12", "输入文件未被本次工作修改",
    mt_a < datetime.datetime(2026, 11, 11) and mt_b < datetime.datetime(2026, 11, 11),
    {"A_mtime": mt_a.isoformat(), "B_mtime": mt_b.isoformat()})

passed = sum(1 for c in checks if c["result"] == "PASS")
review = {
    "issue_key": "S00",
    "stage": "ERRATA",
    "review_nature": "SELF_CHECK",
    "decision": "SELF_CHECK_PASS_WITH_UNRESOLVED_ITEMS" if passed == len(checks)
                else "SELF_CHECK_FAIL",
    "reviewed_at": "2026-11-11T16:20:00+08:00",
    "checks_pass": passed,
    "checks_total": len(checks),
    "checks": checks,
    "not_independent": ("本记录由执行方自检产生，不构成独立验收；"
                        "5,700 条未解决项未做原文核验。"),
    "release_S05": False,
    "release_note": "S04 第二轮复核与 S00 补充验收均未完成，S05 不得放行",
}
(OUT / "review.json").write_text(
    json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

for c in checks:
    print("%s %-6s %s" % (c["id"], c["result"], c["name"]))
print("\n%d/%d PASS → %s" % (passed, len(checks), review["decision"]))
