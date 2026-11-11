#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""S00 勘误 V5 → 全池影响判定（1054 家）

对 Codex 第五轮裁决的落实：
- 依赖引擎改为「读实际行状态」：直接分季度表不加累计父键、Q1 不减上年年末、
  累计差分才展开 YTD(t)/YTD(t−1q)；按公司注入真实 status。
- 受限声明改为逐条绑定唯一源台账记录：dispute_id 由
  sha1(台账版本|台账|公司|字段|期间|元数据字段|方向) 生成，稳定且可回溯；
  一行可绑定多条，用 dispute_ids / dispute_count 表达，不再把多标签拼成一个 id。
- 分层新增 R3_PENDING（有争议但不对应任何候选指标依赖），与 R1_NO_LINK 区分。
"""
import csv
import gzip
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

import l2_core as core

ROOT = core.ROOT
OUT = ROOT / "runs/issues/S00/errata_20261111_v5"
SNAPSHOT = ROOT / "runs/issues/S04/tight_pass.csv"
SNAPSHOT_SHA = hashlib.sha256(SNAPSHOT.read_bytes()).hexdigest()
P_B = ROOT / "runs/issues/S02/hangcha_restated_20261101/s00_v10/s00_v10.csv.gz"

LEDGER_VERSION = "ERRATA_V5"
LEDGER_FILES = ["cell_diff.csv", "key_diff.csv", "meta_diff.csv", "extra_meta_diff.csv"]
LEDGER_SHA = {f: hashlib.sha256((OUT / f).read_bytes()).hexdigest() for f in LEDGER_FILES}

SG_METRIC, SG_DIM = core.load_rules(ROOT / "runs/issues/S01/screen_rules_v2.json")
ALARM = ("HOLD", "MISMATCH", "PROVISIONAL", "CONFLICT", "MISSING", "ABSENT", "UNDEFINED")
EXTRA_CLASSES = {"AFFECTS_VALUE", "AFFECTS_QUALIFICATION", "AFFECTS_TIMING_OR_PROVENANCE",
                 "AFFECTS_TRACE_LOCATION", "AFFECTS_ADOPTION_EXPLANATION",
                 "AFFECTS_PROVENANCE", "AFFECTS_QUALIFICATION_REASON"}


def is_open(res):
    return res.startswith("UNRESOLVED") or res.startswith("PENDING")


def is_alarm(v):
    return any(a in (v or "").upper() for a in ALARM)


def dispute_id(ledger, sec, fld, pk, meta_field, direction):
    raw = "|".join([LEDGER_VERSION, ledger, sec, fld, pk, meta_field or "", direction])
    return "D-" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


# ---------- 争议台账：每条差异一个稳定 id ----------
ledger = {}                 # dispute_id -> 描述
by_key = defaultdict(list)  # (sec, fld, pk) -> [dispute_id]

with open(OUT / "cell_diff.csv", encoding="utf-8-sig", newline="") as f:
    for r in csv.DictReader(f):
        if not is_open(r["resolution"]):
            continue
        d = dispute_id("cell", r["security_id"], r["field_id"], r["period_key"], "", r["resolution"])
        ledger[d] = "cell_diff:%s:%s@%s:%s" % (r["stock_name"], r["field_id"], r["period_key"], r["resolution"])
        by_key[(r["security_id"], r["field_id"], r["period_key"])].append(d)

with open(OUT / "key_diff.csv", encoding="utf-8-sig", newline="") as f:
    for r in csv.DictReader(f):
        if not is_open(r["resolution"]):
            continue
        d = dispute_id("key", r["security_id"], r["field_id"], r["period_key"], "", r["side"] + ":" + r["resolution"])
        ledger[d] = "key_diff:%s:%s@%s:%s:%s" % (r["stock_name"], r["field_id"], r["period_key"], r["side"], r["resolution"])
        by_key[(r["security_id"], r["field_id"], r["period_key"])].append(d)

with open(OUT / "meta_diff.csv", encoding="utf-8-sig", newline="") as f:
    for r in csv.DictReader(f):
        if not is_open(r["resolution"]):
            continue
        direction = r["resolution"]
        if r["meta_field"] != "restatement_flag":
            direction = ("RELEASE" if is_alarm(r["value_A"]) and not is_alarm(r["value_B"])
                         else "META")
        d = dispute_id("meta", r["security_id"], r["field_id"], r["period_key"], r["meta_field"], direction)
        ledger[d] = "meta_diff:%s:%s@%s:%s:%s" % (r["stock_name"], r["field_id"], r["period_key"], r["meta_field"], direction)
        by_key[(r["security_id"], r["field_id"], r["period_key"])].append(d)

with open(OUT / "extra_meta_diff.csv", encoding="utf-8-sig", newline="") as f:
    for r in csv.DictReader(f):
        if r["class"] not in EXTRA_CLASSES or not is_open(r["resolution"]):
            continue
        d = dispute_id("extra", r["security_id"], r["field_id"], r["period_key"], r["meta_field"], r["class"])
        ledger[d] = "extra_meta_diff:%s:%s@%s:%s:%s" % (r["stock_name"], r["field_id"], r["period_key"], r["meta_field"], r["class"])
        by_key[(r["security_id"], r["field_id"], r["period_key"])].append(d)

print("争议键:", len(by_key), "唯一差异 ID:", len(ledger))

with open(OUT / "dispute_ledger.csv", "w", encoding="utf-8-sig", newline="") as f:
    w = csv.writer(f, lineterminator="\n")
    w.writerow(["dispute_id", "ledger_version", "ledger", "description"])
    for d in sorted(ledger):
        w.writerow([d, LEDGER_VERSION, ledger[d].split(":")[0], ledger[d]])

# ---------- B 的实际行状态（按公司注入依赖引擎） ----------
STATUS = {}
with gzip.open(P_B, "rt", encoding="utf-8-sig", newline="") as f:
    for r in csv.DictReader(f):
        STATUS[(r["security_id"], r["field_id"], r["period_key"])] = r["status"]
print("B 状态索引:", len(STATUS))

universe = {}
for part in ("wide_pass", "wide_defer", "wide_unknown"):
    with open(ROOT / f"runs/issues/S03/rerun_20261106/{part}.csv",
              encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            universe[r["company_id"]] = {"name": r.get("company_name", ""),
                                         "anchor": r.get("anchor_period", ""),
                                         "partition": part}

pass_rows = {}
with open(SNAPSHOT, encoding="utf-8-sig", newline="") as f:
    for r in csv.DictReader(f):
        pass_rows[r["company_id"]] = r

rows, restricted = [], []
for sec in sorted(universe):
    anchor = universe[sec]["anchor"]
    so = core.status_of_for(STATUS, sec)
    p = pass_rows.get(sec)
    if p:
        sgs = [x for x in (p.get("qualified_sg") or "").split(";") if x]
        ok_dims, hit_dims, detail = set(), set(), []
        for sg in sgs:
            mid = SG_METRIC.get(sg, "")
            hits, dids = [], []
            for fld, pk in sorted(core.dependency_keys(mid, anchor, so)):
                if (sec, fld, pk) in by_key:
                    ids = sorted(set(by_key[(sec, fld, pk)]))
                    hits.append("%s@%s" % (fld, pk))
                    dids.extend(ids)
                    restricted.append({
                        "security_id": sec, "stock_name": universe[sec]["name"],
                        "snapshot": "runs/issues/S04/tight_pass.csv",
                        "snapshot_hash": SNAPSHOT_SHA,
                        "ledger_version": LEDGER_VERSION,
                        "ledger_sha256": LEDGER_SHA["meta_diff.csv"],
                        "anchor_period": anchor,
                        "signal_id": sg, "dimension": SG_DIM.get(sg, ""),
                        "metric_id": mid,
                        "field_id": fld, "period_key": pk,
                        "status_B": STATUS.get((sec, fld, pk), ""),
                        "dispute_count": len(ids),
                        "dispute_ids": ";".join(ids),
                        "restriction": "该结论不得作为 S05 有效输入或名单验收依据",
                        "allowed_use": "历史复现；不作为入选/漏筛判定依据",
                        "release_condition": "争议字段取得可复核依据并经独立验收",
                        "review_status": "PENDING",
                    })
            if hits:
                hit_dims.add(SG_DIM.get(sg, ""))
                detail.append("%s=%s[%d]" % (sg, "|".join(hits), len(set(dids))))
            else:
                ok_dims.add(SG_DIM.get(sg, ""))
        if not hit_dims:
            verdict = "NOT_AFFECTED"
        elif len(ok_dims) >= 2:
            verdict = "STILL_PASSES_WITHOUT"
        else:
            verdict = "HOLD_PENDING_ERRATA"
        rows.append({
            "security_id": sec, "stock_name": universe[sec]["name"],
            "in_s04_pass": "YES", "anchor_period": anchor,
            "qualified_sg": p.get("qualified_sg", ""),
            "qualified_dims": p.get("qualified_dims", ""),
            "n_dims_undisputed": len(ok_dims),
            "disputed_dims": ";".join(sorted(x for x in hit_dims if x)),
            "dispute_detail": ";".join(detail),
            "verdict": verdict,
        })
    else:
        linked = unlinked = 0
        for k in by_key:
            if k[0] != sec:
                continue
            fld, pk = k[1], k[2]
            hit = any((fld, pk) in core.dependency_keys(mid, anchor, so)
                      for mid in core.METRIC_FIELDS)
            if hit:
                linked += 1
            else:
                unlinked += 1
        if linked:
            verdict = "R2_MAY_CHANGE"
        elif unlinked:
            verdict = "R3_PENDING"
        else:
            verdict = "R1_NO_LINK"
        rows.append({
            "security_id": sec, "stock_name": universe[sec]["name"],
            "in_s04_pass": "NO", "anchor_period": anchor,
            "qualified_sg": "", "qualified_dims": "",
            "n_dims_undisputed": 0, "disputed_dims": "",
            "dispute_detail": "linked=%d unlinked=%d" % (linked, unlinked),
            "verdict": verdict,
        })

with open(OUT / "l2_dependency_check.csv", "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()), lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
with open(OUT / "restricted_claims.csv", "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(restricted[0].keys()), lineterminator="\n")
    w.writeheader()
    w.writerows(restricted)

c = Counter(r["verdict"] for r in rows)
print("全池 %d 家:" % len(rows), dict(c))
print("受限声明行:", len(restricted),
      "涉及唯一差异 ID:", len({d for r in restricted for d in r["dispute_ids"].split(";") if d}))
print("\nHOLD:")
for r in rows:
    if r["verdict"] == "HOLD_PENDING_ERRATA":
        print("  %-11s %-8s %-16s %s" % (r["security_id"], r["stock_name"],
                                         r["disputed_dims"], r["dispute_detail"][:90]))

summary = {
    "scope": "全池 1054 家 vs S00 V5 未闭合/待核差异（含 24 列元数据）",
    "generated_at": "2026-11-12T01:10:00+08:00",
    "nature": "SELF_CHECK",
    "ledger_version": LEDGER_VERSION,
    "ledger_sha256": LEDGER_SHA,
    "snapshot": {"path": "runs/issues/S04/tight_pass.csv", "sha256": SNAPSHOT_SHA,
                 "companies": len(pass_rows)},
    "dependency": {
        "engine": "runs/issues/S00/errata_20261111_v5/l2_core.py:dependency_keys",
        "period_rule": {"M03": "t, t-1q, t-1y, t-1y-1q", "others": "t, t-1y"},
        "parent_rule": ("按 B 实际 status：EXTRACTED_QUARTERLY_TABLE 不加累计父键；"
                        "DERIVED_Q1_EQUALS_YTD 或 Q1 只加本期累计；"
                        "DERIVED_CUMULATIVE_DIFF 加 YTD(t) 与 YTD(t-1q)"),
        "status_injected": True,
        "extra_meta_included": True,
    },
    "verdicts": dict(c),
    "hold_list": [{"security_id": r["security_id"], "stock_name": r["stock_name"],
                   "disputed_dims": r["disputed_dims"], "detail": r["dispute_detail"]}
                  for r in rows if r["verdict"] == "HOLD_PENDING_ERRATA"],
    "still_passes": [r["security_id"] for r in rows if r["verdict"] == "STILL_PASSES_WITHOUT"],
    "restricted_claim_rows": len(restricted),
    "restricted_unique_disputes": len({d for r in restricted
                                       for d in r["dispute_ids"].split(";") if d}),
    "note": ("未闭合含 PENDING_*（待核不计已闭合）；未回读原文；"
             "未覆盖锚定期回退与上游准入的间接依赖。SELF_CHECK。"),
}
(OUT / "l2_dependency_summary.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("\n已写 l2_dependency_check.csv / restricted_claims.csv / dispute_ledger.csv / l2_dependency_summary.json")
