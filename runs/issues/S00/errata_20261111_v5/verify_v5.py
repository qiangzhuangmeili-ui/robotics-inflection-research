#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""S00 勘误 V5 自检（SELF_CHECK）

对 Codex 第五轮裁决的整改：
- C14 重写：不再只查「判定等于 B」，改为独立重算证据覆盖范围，
  已解决项必须 scope_covered ⊇ scope_required 且 scope_missing 为空；
- C13/C17 扩到所有已解决标签，不再只查 RESOLVED_NORMALIZED_DELTA；
- C23 扩到全量期间一致性（山东钢铁只作为已知实例之一）；
- C24 改为检查放行所需的证据条件，而不是只禁某个旧标签；
- C25 检查受限表全部行；
- C26 通用范围断言：全量 17,009 条重述差异逐条重算 scope 并与台账比对；
- C27 各目标期父键检查：M01–M12 × 四个锚定期，按状态分别验证父键出现/不出现；
- C28 差异 ID 稳定性与逐项映射；
- C29 禁止「仅凭期间相等」闭合；
- C30 故障注入：V4 台账代入 C26/C14 必须 FAIL。
"""
import csv
import gzip
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

import evidence_scope as es
import l2_core as core

ROOT = core.ROOT
OUT = ROOT / "runs/issues/S00/errata_20261111_v5"
V4 = ROOT / "runs/issues/S00/errata_20261111_v4"
V1 = ROOT / "runs/issues/S00/errata_20261111/superseded_v1"
P_A = ROOT / "runs/issues/S00/financial_normalized.csv"
P_V10 = ROOT / "runs/issues/S02/hangcha_restated_20261101/s00_v10/s00_v10.csv.gz"
P_DELTA = ROOT / "runs/issues/S02/remediation_20261029/normalized_delta.csv"
P_VERIFY = ROOT / "runs/issues/S02/remediation_20261029/restatement_verify/results.csv"
P_REGISTRY = ROOT / "runs/collection/collection_index.csv"
PERIOD_LABEL_TO_KEY = {
    "2025Q1": "20250331", "2025H1": "20250630", "2025Q3": "20250930",
    "FY2025": "20251231", "2026Q1": "20260331", "2026H1": "20260630",
    "2026Q3": "20260930", "FY2024": "20241231", "2024FY": "20241231",
}


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
doc_period = {}
with open(P_REGISTRY, encoding="utf-8-sig", newline="") as f:
    for r in csv.DictReader(f):
        doc_period[r["document_id"]] = PERIOD_LABEL_TO_KEY.get(r.get("period_label", ""), "")
adopt = {}
with open(ROOT / "runs/issues/S02/hangcha_restated_20261101/s00_v10/s00_v10_adoption_audit.csv",
          encoding="utf-8-sig", newline="") as f:
    for r in csv.DictReader(f):
        adopt[(r["security_id"], r["field_id"], r["period_key"])] = r


def read_dir(d):
    def rd(n):
        p = d / n
        if not p.exists():
            return []
        with open(p, encoding="utf-8-sig", newline="") as f:
            return list(csv.DictReader(f))
    return rd("cell_diff.csv"), rd("key_diff.csv"), rd("meta_diff.csv")


# ---------------- 逐项检查器（可对任意版本台账运行，用于故障注入） ----------------

def check_c13(cell):
    """所有已解决值差异都要有可复算依据，不只是 NORMALIZED_DELTA。"""
    bad = []
    for r in cell:
        res = r["resolution"]
        if res.startswith("UNRESOLVED") or res.startswith("PENDING"):
            continue
        k = (r["security_id"], r["field_id"], r["period_key"])
        b = D10.get(k)
        if b is None:
            bad.append((k, "ROW_NOT_IN_B:%s" % res))
            continue
        if not match(r["value_B"], b["value_cny"]):
            bad.append((k, "LEDGER_B_NE_B:%s" % res))
            continue
        if res == "RESOLVED_NORMALIZED_DELTA":
            d = delta.get(k)
            if d is None:
                bad.append((k, "NO_RECORD"))
            elif d["change"] != "UPDATE":
                bad.append((k, "NOT_UPDATE:%s" % d["change"]))
            elif not match(d["new_value"], b["value_cny"]):
                bad.append((k, "VALUE_MISMATCH"))
        elif res == "RESOLVED_RESTATED_ADOPTION":
            if k not in adopt:
                bad.append((k, "NO_ADOPTION_ROW"))
        elif res == "RESOLVED_DERIVED_FROM_PARENT":
            d = delta.get(k)
            if d is None or d["change"] != "UPDATE":
                bad.append((k, "DERIVED_WITHOUT_RECORD"))
        else:
            bad.append((k, "UNKNOWN_RESOLVED_LABEL:%s" % res))
    return bad


def check_c14(meta):
    """已解决重述必须由证据覆盖支撑：独立重算 scope，逐条比对。

    这是 V5 的核心断言。V1/V2/V3/V4 的台账没有 scope 列，会直接在这里失败。
    """
    bad = []
    for r in meta:
        if r["meta_field"] != "restatement_flag":
            continue
        res = r["resolution"]
        if res.startswith("UNRESOLVED") or res.startswith("PENDING"):
            continue
        k = (r["security_id"], r["field_id"], r["period_key"])
        doc = D10.get(k, {}).get("document_id", "")
        rec = vrec.get(doc) if doc else None
        if res == "RESOLVED_BY_RULING":
            if not r.get("evidence"):
                bad.append((k, "RULING_WITHOUT_BASIS"))
            continue
        if res == "RESOLVED_NORMALIZED_DELTA":
            continue  # 由 C17 校验
        if res == "RESOLVED_RESTATEMENT_CONFIRMED":
            if rec is None or rec["verdict"] != r["value_B"] or r["value_B"] != "是":
                bad.append((k, "CONFIRMED_BUT_VERDICT_NE"))
            continue
        if res != "RESOLVED_SCOPE_COVERED":
            bad.append((k, "UNKNOWN_RESOLVED_LABEL:%s" % res))
            continue
        if rec is None:
            bad.append((k, "NO_DOC_RECORD"))
            continue
        if rec["verdict"] != r["value_B"]:
            bad.append((k, "VERDICT_NE:%s" % rec["verdict"]))
            continue
        status = D10.get(k, {}).get("status", "")
        own = doc_period.get(doc, "")
        req = es.required_scope(status, own)
        cov = es.coverage_of(rec)
        missing = req - cov
        if missing:
            bad.append((k, "SCOPE_NOT_COVERED:%s" % ";".join(sorted(missing))))
            continue
        # 台账声明必须与独立重算一致
        if set(filter(None, (r.get("scope_required") or "").split(";"))) != req:
            bad.append((k, "SCOPE_REQUIRED_DRIFT"))
        elif set(filter(None, (r.get("scope_covered") or "").split(";"))) != cov:
            bad.append((k, "SCOPE_COVERED_DRIFT"))
        elif (r.get("scope_missing") or "") != "":
            bad.append((k, "SCOPE_MISSING_NOT_EMPTY"))
        elif (rec.get("method") or "") in es.SCOPE_LIMITED_METHODS and not es.binds_field(rec):
            bad.append((k, "LIMITED_METHOD_COUNTED_RESOLVED"))
        elif (rec.get("method") or "") == "ASSUMED_NO_PENDING_REVIEW":
            bad.append((k, "WEAK_COUNTED_RESOLVED"))
    return bad


def check_c17(meta):
    """所有已解决元数据都要有终值或字段级依据。"""
    bad = []
    for r in meta:
        res = r["resolution"]
        if res.startswith("UNRESOLVED") or res.startswith("PENDING"):
            continue
        k = (r["security_id"], r["field_id"], r["period_key"])
        b = D10.get(k)
        if b is None:
            bad.append((k, "ROW_NOT_IN_B"))
            continue
        if (r["value_B"] or "") != (b.get(r["meta_field"], "") or ""):
            bad.append((k, "LEDGER_B_NE_B:%s" % r["meta_field"]))
            continue
        if r["meta_field"] == "restatement_flag":
            if res not in ("RESOLVED_SCOPE_COVERED", "RESOLVED_BY_RULING",
                           "RESOLVED_RESTATEMENT_CONFIRMED"):
                bad.append((k, "RESTATEMENT_BAD_LABEL:%s" % res))
            continue
        if res != "RESOLVED_NORMALIZED_DELTA":
            bad.append((k, "META_BAD_LABEL:%s" % res))
            continue
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
dledger = list(csv.DictReader(open(OUT / "dispute_ledger.csv", encoding="utf-8-sig", newline="")))
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
n_restate = sum(1 for r in meta if r["meta_field"] == "restatement_flag")
add("C06", "重述差异 17,009", n_restate == 17009, {"count": n_restate})
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
add("C13", "已解决值差异：全部标签均有可复算依据（非仅 NORMALIZED_DELTA）",
    not b13, {"violations": len(b13), "sample": [str(x) for x in b13[:3]],
              "labels": dict(Counter(r["resolution"] for r in cell))})
b14 = check_c14(meta)
add("C14", "已解决重述：证据覆盖范围 ⊇ 必需范围（独立重算）", not b14,
    {"violations": len(b14), "sample": [str(x) for x in b14[:5]]})
b17 = check_c17(meta)
add("C17", "已解决元数据：全部标签均有终值或字段级依据", not b17,
    {"violations": len(b17), "sample": [str(x) for x in b17[:3]]})

# ---- C15/C16：生产依赖函数，四季度口径 ----
four = core.dependency_keys("M03", "20260630")
two = core.dependency_keys("M01", "20260630")
add("C15", "M03 生产依赖为四季（t/t−1q/t−1y/t−1y−1q）",
    {("FIN.REV.SQ", p) for p in ("20260630", "20260331", "20250630", "20250331")} <= four
    and len(two) == 2,
    {"M03_keys": len(four), "M01_keys": len(two)})
synth = ("FIN.REV.SQ", "20250331")
add("C16", "生产依赖命中前季争议（合成键）", synth in four and synth not in two,
    {"synthetic": str(synth), "in_M03": synth in four, "in_M01": synth in two})

# ---- C18：父键递归 ----
parent_key = ("FIN.REV.YTD", "20260630")
add("C18", "单季派生递归展开累计父键（合成 REV.YTD 争议被命中）",
    parent_key in core.dependency_keys("M02", "20260630")
    and parent_key in core.dependency_keys("M03", "20260630"),
    {"parent_key": str(parent_key)})

cols = {r["meta_field"] for r in extra}
add("C19", "19 列 / 1,505 格元数据差异已登记",
    len(cols) == 19 and len(extra) == 1505, {"columns": len(cols), "cells": len(extra)})

need = {"security_id", "stock_name", "snapshot", "snapshot_hash", "ledger_version",
        "ledger_sha256", "anchor_period", "signal_id", "dimension", "metric_id",
        "field_id", "period_key", "status_B", "dispute_count", "dispute_ids",
        "restriction", "allowed_use", "release_condition", "review_status"}
add("C20", "受限表字段完整（含快照哈希、台账版本与差异 ID 列）",
    bool(restr) and set(restr[0].keys()) == need,
    {"rows": len(restr), "cols": len(restr[0]) if restr else 0})

# ---- C21：三项分别拦住 V1 ----
inj_v1 = run_all(V1)
inj_v4 = run_all(V4)
add("C21a", "C13 必须独立拦住 V1", inj_v1 is not None and len(inj_v1["C13_bad"]) > 0,
    {"v1_C13": len(inj_v1["C13_bad"]) if inj_v1 else None})
add("C21b", "C14 必须独立拦住 V1", inj_v1 is not None and len(inj_v1["C14_bad"]) > 0,
    {"v1_C14": len(inj_v1["C14_bad"]) if inj_v1 else None})
add("C21c", "C17 必须独立拦住 V1", inj_v1 is not None and len(inj_v1["C17_bad"]) > 0,
    {"v1_C17": len(inj_v1["C17_bad"]) if inj_v1 else None})
add("C22", "V5 台账代入同一套检查必须全 PASS", run_all(OUT)["pass"], {})

# ---- C23：全量期间一致性（山东钢铁只是已知实例） ----
sd = [r for r in meta if r["security_id"] == "SH:600022" and r["period_key"] == "20250630"
      and r["field_id"] in ("FIN.NPDEDT.SQ", "FIN.NPP.SQ", "FIN.OCF.SQ", "FIN.REV.SQ")]
sd_ok = len(sd) == 4 and all(r["resolution"].startswith("PENDING") for r in sd)
# 全量：凡 own_period 与行期间不等者，不得判 SCOPE_COVERED
mis = [r for r in meta if r["meta_field"] == "restatement_flag"
       and r["resolution"] == "RESOLVED_SCOPE_COVERED"
       and r["own_period"] and r["own_period"] != r["period_key"]]
add("C23", "山东钢铁四条待核 + 全量比较列/分季度表取值不得判已解决",
    sd_ok and not mis,
    {"sd_found": len(sd), "sd_res": sorted({r["resolution"] for r in sd}),
     "comparative_resolved": len(mis)})

# ---- C24：补充元数据放行必须满足证据条件 ----
leak = []
for r in extra:
    if r["resolution"].startswith("UNRESOLVED") or r["resolution"].startswith("PENDING"):
        continue
    if r["resolution"] == "REGISTERED_DISPLAY_ONLY":
        # 仅当文档与期间来源都未变，才允许算展示
        if r["document_changed"] == "YES" or r["period_source_changed"] == "YES":
            leak.append((r["security_id"], r["meta_field"], "DISPLAY_BUT_PROVENANCE_CHANGED"))
    else:
        leak.append((r["security_id"], r["meta_field"], "UNKNOWN_RELEASE:%s" % r["resolution"]))
add("C24", "补充元数据放行须满足证据条件（来源变更不得算展示）", not leak,
    {"leaked": len(leak), "sample": [str(x) for x in leak[:5]],
     "pending": sum(1 for r in extra
                    if r["resolution"] == "PENDING_FIELD_LEVEL_CHECK")})

# ---- C25：受限表全部行的快照哈希 ----
snap = ROOT / "runs/issues/S04/tight_pass.csv"
snap_sha = sha(snap)
add("C25", "受限表全部行 snapshot_hash 与实际快照一致",
    bool(restr) and all(r["snapshot_hash"] == snap_sha for r in restr),
    {"snapshot_sha": snap_sha[:16], "rows_checked": len(restr)})

# ---- C26：通用范围断言（全量重算，不依赖台账自报） ----
drift = []
for r in meta:
    if r["meta_field"] != "restatement_flag":
        continue
    k = (r["security_id"], r["field_id"], r["period_key"])
    doc = D10.get(k, {}).get("document_id", "")
    rec = vrec.get(doc) if doc else None
    status = D10.get(k, {}).get("status", "")
    own = doc_period.get(doc, "")
    req = es.required_scope(status, own)
    cov = es.coverage_of(rec) if rec else set()
    res = r["resolution"]
    if res in ("RESOLVED_BY_RULING", "RESOLVED_RESTATEMENT_CONFIRMED"):
        continue
    covered_enough = (req - cov) == set() and rec is not None \
        and rec["verdict"] == r["value_B"] \
        and (rec.get("method") or "") not in es.SCOPE_LIMITED_METHODS
    if res == "RESOLVED_SCOPE_COVERED" and not covered_enough:
        drift.append((k, "CLAIMED_RESOLVED_BUT_NOT_COVERED"))
    if res.startswith("PENDING") and covered_enough:
        drift.append((k, "COVERED_BUT_PENDING:%s" % res))
add("C26", "通用范围断言：已解决↔覆盖充分双向一致（全量 17,009 条重算）",
    not drift, {"violations": len(drift), "sample": [str(x) for x in drift[:5]]})

# ---- C27：各目标期父键检查 ----
c27 = []
ANCHORS = ("20250331", "20250630", "20250930", "20251231",
           "20260331", "20260630", "20260930")
# (1) 单键语义：按状态直接检验 expand() 的精确输出
for fld in sorted(core.SIMPLE_SQ):
    ytd = fld[:-3] + ".YTD"
    for pk in ANCHORS:
        pq = core.prev_quarter(pk)
        # 分季度表：只依赖自身
        kq = core.expand(fld, pk, lambda f, p: core.QUARTERLY_TABLE)
        if kq != {(fld, pk)}:
            c27.append((fld, pk, "QUARTERLY_TABLE", "EXTRA_KEYS:%d" % len(kq)))
        # Q1：SQ == YTD，不得减上年年末
        k1 = core.expand(fld, pk, lambda f, p: core.Q1_EQUALS_YTD)
        if (ytd, pk) not in k1:
            c27.append((fld, pk, "Q1", "MISSING_YTD_SELF"))
        if (ytd, pq) in k1:
            c27.append((fld, pk, "Q1", "SUBTRACTED_PREV_QUARTER"))
        # 累计差分：必须同时含 YTD(t) 与 YTD(t-1q)。Q1 不适用（日历 Q1 优先）
        kd = core.expand(fld, pk, lambda f, p: "DERIVED_CUMULATIVE_DIFF")
        if (ytd, pk) not in kd:
            c27.append((fld, pk, "CUMULATIVE_DIFF", "MISSING_YTD_SELF"))
        if pk[4:] != "0331" and (ytd, pq) not in kd:
            c27.append((fld, pk, "CUMULATIVE_DIFF", "MISSING_PARENT"))
    # 日历 Q1 无论状态如何都不得减上年年末
    k0331 = core.expand(fld, "20260331", None)
    if (ytd, "20251231") in k0331:
        c27.append((fld, "20260331", "CALENDAR_Q1", "SUBTRACTED_PREV_YE_END"))
# (2) 指标级：默认（状态未知）口径必须是各状态并集的超集
for mid in core.METRIC_FIELDS:
    for a in ANCHORS:
        base = core.dependency_keys(mid, a)
        for fld in core.METRIC_FIELDS[mid]:
            if fld not in core.SIMPLE_SQ:
                continue
            ytd = fld[:-3] + ".YTD"
            if (ytd, a) not in base:
                c27.append((mid, a, fld, "MISSING_YTD_SELF"))
            if a[4:] != "0331" and (ytd, core.prev_quarter(a)) not in base:
                c27.append((mid, a, fld, "MISSING_YTD_PREV_Q"))
# Codex 第五轮点名的具体例子
m07 = core.dependency_keys("M07", "20260630")
c27_ok = (not c27) and ("FIN.NPDEDT.YTD", "20250331") in m07
add("C27", "各目标期父键检查（M01–M12 × 7 锚定期，含 Codex 点名 M07@20260630）",
    c27_ok, {"violations": len(c27), "sample": [str(x) for x in c27[:6]],
             "M07_has_20250331": ("FIN.NPDEDT.YTD", "20250331") in m07})

# ---- C28：差异 ID 稳定性与逐项映射 ----
led_ids = [r["dispute_id"] for r in dledger]
dup = [k for k, v in Counter(led_ids).items() if v > 1]
used = {d for r in restr for d in (r["dispute_ids"] or "").split(";") if d}
unmapped = sorted(used - set(led_ids))
cnt_bad = [r for r in restr if int(r["dispute_count"]) != len([d for d in (r["dispute_ids"] or "").split(";") if d])]
add("C28", "差异 ID 唯一、稳定且受限行逐项可回溯",
    not dup and not unmapped and not cnt_bad,
    {"ledger_ids": len(led_ids), "unique": len(set(led_ids)), "dups": len(dup),
     "used_ids": len(used), "unmapped": len(unmapped), "count_mismatch": len(cnt_bad)})

# ---- C29：禁止仅凭期间相等闭合 ----
eq_only = []
for r in meta:
    if r["meta_field"] != "restatement_flag":
        continue
    if r["resolution"] != "RESOLVED_SCOPE_COVERED":
        continue
    if not (r.get("scope_required") or "") or (r.get("scope_missing") or ""):
        eq_only.append((r["security_id"], r["field_id"], r["period_key"]))
add("C29", "不得存在「仅凭期间相等」的闭合（已解决项必须写明覆盖范围）",
    not eq_only, {"violations": len(eq_only), "sample": [str(x) for x in eq_only[:5]]})

# ---- C30：V4 台账代入 C14/C26 必须 FAIL（新检查有牙齿） ----
v4_meta = read_dir(V4)[2]
v4_c14 = check_c14(v4_meta) if v4_meta else []
v4_limited = sum(1 for r in v4_meta
                 if r["resolution"] == "RESOLVED_RESTATEMENT_OWN_PERIOD"
                 and (vrec.get(D10.get((r["security_id"], r["field_id"], r["period_key"]), {})
                               .get("document_id", ""), {}) or {}).get("method")
                 in es.SCOPE_LIMITED_METHODS)
add("C30", "V4 台账代入新判据必须 FAIL（受限方法自动闭合被拦住）",
    len(v4_c14) >= 5270 and v4_limited >= 5270,
    {"v4_C14_violations": len(v4_c14), "v4_limited_own_period": v4_limited})

# ---- C31：分层方法抽验必须覆盖全部必需风险类型 ----
samp = list(csv.DictReader(open(OUT / "sampling_v5.csv", encoding="utf-8-sig", newline="")))
samp_risk = {s["risk_type"] for s in samp}
REQUIRED_RISK = {"R1_QUARTERLY_TABLE_OWN", "R2_CUMULATIVE_DIFF", "R3_Q1_EQUALS_YTD",
                 "R4_COMPARATIVE_COLUMN", "R5_CAUSE_MERGER_RETRO",
                 "R5_CAUSE_POLICY_CHANGE", "R8_SHANDONG_POSITIVE",
                 "R9_DAHAO_RULED", "R10_HANGCHA_CROSS_SOURCE"}
has_extra = any(k.startswith("R11_") for k in samp_risk)
reread_bad = [s for s in samp if s["page_reread"] in ("NOT_FOUND", "PDF_MISSING",
                                                     "READ_ERROR") or s["page_reread"].startswith("PAGE_OUT")]
add("C31", "分层抽验覆盖全部必需风险类型且原件回读无失配",
    REQUIRED_RISK <= samp_risk and has_extra and not reread_bad,
    {"samples": len(samp), "risk_types": len(samp_risk),
     "missing": sorted(REQUIRED_RISK - samp_risk), "extra_covered": has_extra,
     "reread_bad": len(reread_bad),
     "reread": dict(Counter(s["page_reread"] for s in samp))})

# ---- C32：Codex 点名的三项必须落在预期处置上 ----
dh_s = [s for s in samp if s["risk_type"] == "R9_DAHAO_RULED"]
sd_s = [s for s in samp if s["risk_type"] == "R8_SHANDONG_POSITIVE"]
hc_s = [s for s in samp if s["risk_type"] == "R10_HANGCHA_CROSS_SOURCE"]
add("C32", "大豪科技保持解除、山东钢铁保持待核、杭叉样本带跨来源限制",
    bool(dh_s) and all(s["resolution"] == "RESOLVED_BY_RULING" for s in dh_s)
    and bool(sd_s) and all(s["resolution"].startswith("PENDING") for s in sd_s)
    and bool(hc_s),
    {"dahao": [s["resolution"] for s in dh_s],
     "shandong": [s["resolution"] for s in sd_s],
     "hangcha": len(hc_s)})

passed = sum(1 for c in checks if c["result"] == "PASS")
review = {
    "issue_key": "S00", "stage": "ERRATA", "version": "ERRATA_V5",
    "review_nature": "SELF_CHECK",
    "decision": "SELF_CHECK_PASS_WITH_UNRESOLVED_ITEMS" if passed == len(checks)
                else "SELF_CHECK_FAIL",
    "reviewed_at": "2026-11-12T01:30:00+08:00",
    "checks_pass": passed, "checks_total": len(checks),
    "checks": checks,
    "fault_injection": {"V1": {k: (len(v) if isinstance(v, list) else v)
                               for k, v in (inj_v1 or {}).items()},
                        "V4": {k: (len(v) if isinstance(v, list) else v)
                               for k, v in (inj_v4 or {}).items()},
                        "V5_pass": run_all(OUT)["pass"]},
    "v4_defects_fixed": [
        "取消「行期间==文档自身期间即闭合」→ evidence_scope.required_scope/coverage_of + C14/C26",
        "5,270 条受限方法自动闭合转入待核 → C30 用 V4 台账反向验证",
        "依赖引擎读实际行状态，取消直接分季度表的累计依赖与 Q1 减上年年末 → C27",
        "补充元数据 232 格取消整体展示归类 → C24（来源变更不得算展示）",
        "受限表改为逐条绑定唯一差异 ID 并绑定台账版本 → C20/C28",
        "C13/C17 从单一标签扩到全部已解决标签 → C13/C17",
    ],
    "not_independent": "执行方自检，不构成独立验收；未回读 PDF。",
    "release_S05": False,
}
(OUT / "review.json").write_text(
    json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

for c in checks:
    print("%s %-6s %s" % (c["id"], c["result"], c["name"]))
    if c["result"] == "FAIL":
        print("      ", json.dumps(c["detail"], ensure_ascii=False)[:300])
print("\n%d/%d PASS → %s" % (passed, len(checks), review["decision"]))
