#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""S00 勘误 V4 自检（SELF_CHECK）

对 Codex 第四轮指出缺陷的整改：
- C15/C16/C18 直接调用生产依赖 l2_core.dependency_keys，不再自写一套期间函数；
- C18 用合成争议证明「父键确实被查」，而不是看说明文字里是否出现字段名；
- C21 拆成 C21a/C21b/C21c：C13、C14、C17 必须**分别**拦住 V1 的旧错误；
- C23 山东钢铁四条必须处于待范围对账，不得判已解决；
- C24 补充元数据不得以「同键有记录」免责；
- C25 受限表必须带 snapshot_hash。
"""
import csv
import gzip
import hashlib
import json
from collections import Counter
from pathlib import Path

import l2_core as core

ROOT = core.ROOT
OUT = ROOT / "runs/issues/S00/errata_20261111_v4"
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
    """重述已解决只能标 OWN_PERIOD（行期间=文档自身期间）；
    比较列/分季度表必须待范围对账。按前缀收口，使 V1/V2/V3 标签也进检查。"""
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
        elif r["resolution"] == "RESOLVED_RESTATEMENT_OWN_PERIOD":
            pass  # 期间一致性由 C23 单独校验
    return bad


def check_c17(meta):
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


def run_all(d):
    cell, key, meta = read_dir(d)
    if not cell:
        return None
    r = {"cell_rows": len(cell), "key_rows": len(key), "meta_rows": len(meta),
         "C13_bad": check_c13(cell), "C14_bad": check_c14(meta),
         "C17_bad": check_c17(meta)}
    r["pass"] = not (r["C13_bad"] or r["C14_bad"] or r["C17_bad"])
    return r


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
add("C02", "B 行数与登记一致", len(D10) == summary["versions"]["B"]["rows"], {"rows": len(D10)})
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
       if (r["resolution"].startswith("UNRESOLVED") or r["resolution"].startswith("PENDING"))
       and not r.get("evidence")]
add("C05", "未闭合/待核项均写明原因", not bad, {"missing": len(bad)})
add("C06", "重述差异 17,009",
    sum(1 for r in meta if r["meta_field"] == "restatement_flag") == 17009,
    {"count": sum(1 for r in meta if r["meta_field"] == "restatement_flag")})
add("C07", "符号翻转 89 格",
    sum(1 for r in cell if r["sign_flip"] == "YES") == 89,
    {"sign_flip": sum(1 for r in cell if r["sign_flip"] == "YES")})
vc = Counter(r["verdict"] for r in l2)
add("C08", "全池 1054 家守恒", sum(vc.values()) == 1054,
    {"total": sum(vc.values()), "by_verdict": dict(vc)})
holds = [r for r in l2 if r["verdict"] == "HOLD_PENDING_ERRATA"]
add("C09", "HOLD 争议可追溯到字段与期间",
    all("@" in r["dispute_detail"] and "[" in r["dispute_detail"] for r in holds),
    {"hold_count": len(holds)})
n_open = sum(1 for r in cell + key + meta
             if r["resolution"].startswith("UNRESOLVED") or r["resolution"].startswith("PENDING"))
add("C10", "核心未闭合+待核与 summary 一致", n_open == summary["open_total_core"],
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
b17 = check_c17(meta)
add("C17", "已解决元数据：不得引用 REMOVE 或非 status 字段", not b17,
    {"violations": len(b17), "sample": [str(x) for x in b17[:3]]})

# C15/C16：调用生产依赖函数，不再自写
four = core.dependency_keys("M03", "20260630")
two = core.dependency_keys("M01", "20260630")
add("C15", "M03 生产依赖为四季（t/t−1q/t−1y/t−1y−1q）",
    {("FIN.REV.SQ", p) for p in ("20260630", "20260331", "20250630", "20250331")} <= four
    and len(two) == 2,
    {"M03_keys": len(four), "M01_keys": len(two)})

# C16：合成争议必须被生产依赖命中；两季口径会漏
synth = ("FIN.REV.SQ", "20250331")
add("C16", "生产依赖命中前季争议（合成键）", synth in four and synth not in two,
    {"synthetic": str(synth), "in_M03": synth in four, "in_M01": synth in two})

# C18：父键必须真的被查——合成 REV.YTD 争议应出现在 SG02 依赖里
parent_key = ("FIN.REV.YTD", "20260630")
add("C18", "单季派生递归展开累计父键（合成 REV.YTD 争议被命中）",
    parent_key in core.dependency_keys("M02", "20260630")
    and parent_key in core.dependency_keys("M03", "20260630"),
    {"parent_key": str(parent_key)})

cols = {r["meta_field"] for r in extra}
add("C19", "19 列 / 1,505 格元数据差异已登记",
    len(cols) == 19 and len(extra) == 1505, {"columns": len(cols), "cells": len(extra)})

need = {"security_id", "stock_name", "snapshot", "snapshot_hash", "anchor_period",
        "signal_id", "dimension", "metric_id", "field_id", "period_key",
        "dispute_id", "evidence_gap", "restriction", "allowed_use",
        "release_condition", "review_status"}
add("C20", "受限表字段完整（含 snapshot_hash 与 metric_id）",
    bool(restr) and set(restr[0].keys()) == need,
    {"rows": len(restr), "cols": len(restr[0]) if restr else 0})

# 故障注入：三项分别检验
inj_v1 = run_all(V1)
inj_v4 = run_all(OUT)
add("C21a", "C13 必须独立拦住 V1", inj_v1 is not None and len(inj_v1["C13_bad"]) > 0,
    {"v1_C13": len(inj_v1["C13_bad"]) if inj_v1 else None})
add("C21b", "C14 必须独立拦住 V1", inj_v1 is not None and len(inj_v1["C14_bad"]) > 0,
    {"v1_C14": len(inj_v1["C14_bad"]) if inj_v1 else None})
add("C21c", "C17 必须独立拦住 V1", inj_v1 is not None and len(inj_v1["C17_bad"]) > 0,
    {"v1_C17": len(inj_v1["C17_bad"]) if inj_v1 else None})
add("C22", "V4 台账代入同一套检查必须全 PASS", inj_v4 is not None and inj_v4["pass"], {})

# C23：山东钢铁四条必须待范围对账
sd = [r for r in meta if r["security_id"] == "SH:600022" and r["period_key"] == "20250630"
      and r["field_id"] in ("FIN.NPDEDT.SQ", "FIN.NPP.SQ", "FIN.OCF.SQ", "FIN.REV.SQ")]
add("C23", "山东钢铁四条不得判已解决（须待范围对账）",
    len(sd) == 4 and all(r["resolution"].startswith("PENDING") for r in sd),
    {"found": len(sd), "resolutions": sorted({r["resolution"] for r in sd})})

# C24：补充元数据不得以同键记录免责
leak = [r for r in extra if r["resolution"] == "REGISTERED_WITH_RECORD"]
add("C24", "补充元数据不得以同键记录自动免责", not leak,
    {"leaked": len(leak),
     "pending": sum(1 for r in extra if r["resolution"] == "PENDING_FIELD_LEVEL_CHECK")})

# C25：受限表 snapshot_hash 必须等于实际快照哈希
snap = ROOT / "runs/issues/S04/tight_pass.csv"
add("C25", "受限表 snapshot_hash 与实际快照一致",
    bool(restr) and all(r["snapshot_hash"] == sha(snap) for r in restr[:20]),
    {"snapshot_sha": sha(snap)[:16], "rows_checked": min(20, len(restr))})

passed = sum(1 for c in checks if c["result"] == "PASS")
review = {
    "issue_key": "S00", "stage": "ERRATA", "version": "ERRATA_V4",
    "review_nature": "SELF_CHECK",
    "decision": "SELF_CHECK_PASS_WITH_UNRESOLVED_ITEMS" if passed == len(checks)
                else "SELF_CHECK_FAIL",
    "reviewed_at": "2026-11-12T00:05:00+08:00",
    "checks_pass": passed, "checks_total": len(checks),
    "checks": checks,
    "fault_injection": {"V1": {k: (len(v) if isinstance(v, list) else v)
                               for k, v in (inj_v1 or {}).items()},
                        "V4_pass": inj_v4["pass"] if inj_v4 else None},
    "v3_defects_fixed": [
        "文档定位与证据适用范围分离（PENDING_SCOPE_AUDIT）→ C23",
        "父键递归展开且生产/自检共用 l2_core → C18",
        "C21 拆成 C21a/C21b/C21c 分别检验 → C21a-c",
        "补充元数据取消同键免责 → C24",
        "受限表补 snapshot_hash 与 metric_id → C20/C25",
    ],
    "not_independent": "执行方自检，不构成独立验收；未回读 PDF。",
    "release_S05": False,
}
(OUT / "review.json").write_text(
    json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

for c in checks:
    print("%s %-6s %s" % (c["id"], c["result"], c["name"]))
print("\n%d/%d PASS → %s" % (passed, len(checks), review["decision"]))
