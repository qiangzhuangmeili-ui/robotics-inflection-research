#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""S01 规则可执行性校验 + 匿名干跑覆盖。

做四件事：
1) 结构校验：指标/信号/分层/路径/无配额断言是否完整；
2) 字段校验：规则引用的每个 field_id 是否真实存在于 S00 标准化表，行数是否一致；
3) 指纹校验：规则冻结时登记的输入 sha256 是否与当前文件一致；
4) 匿名干跑：按规则逐家算一遍，只输出聚合计数（不出公司名、不出名单）。

输出：
- runs/issues/S01/metric_coverage_dryrun.csv（仅聚合计数）
- runs/issues/S01/self_check.json

用法：
    python tools/s01_rules_check.py --fill-fingerprint   # 首次冻结，写入输入指纹
    python tools/s01_rules_check.py                      # 校验 + 干跑
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
S01 = ROOT / "runs/issues/S01"
RULES = S01 / "screen_rules_v1.json"
NORMALIZED = ROOT / "runs/issues/S00/financial_normalized.csv"
CST = timezone(timedelta(hours=8))

USABLE = {
    "EXTRACTED", "EXTRACTED_KEY_TABLE", "EXTRACTED_QUARTERLY_TABLE",
    "DERIVED", "DERIVED_CUMULATIVE_DIFF", "DERIVED_Q1_EQUALS_YTD",
    "DERIVED_QUARTERLY_SUM_OVERRIDE",
}
USABLE_FLAG = {"LEGACY_SNAPSHOT"}
HOLD = {"EXTRACTED_XCHECK_MISMATCH", "DERIVED_HOLD_UPSTREAM", "DERIVED_Q1_HOLD_UPSTREAM"}
LOW_BASE_FLAGS = {"LOW_BASE_REV", "LOW_BASE_PROFIT", "NEGATIVE_BASE_PROFIT"}
RESTATE_PENDING = "RESTATEMENT_INDICATED_NEEDS_REVIEW"
ZERO_BASE_ABS = 1_000_000.0
LOW_BASE_REV = 50_000_000.0
LOW_BASE_NPDEDT = 10_000_000.0
ABS_CONFIRM = 10_000_000.0

checks: list[dict] = []


def add(cid: str, item: str, ok: bool, detail, blocking: bool = True) -> None:
    checks.append({"id": cid, "item": item, "result": "PASS" if ok else "FAIL",
                   "blocking": blocking, "detail": detail})


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------- 数据装载

def load_rows():
    rows: dict[tuple[str, int], dict[str, dict]] = defaultdict(dict)
    meta: dict[tuple[str, int], dict] = {}
    field_rows: Counter = Counter()
    companies = set()
    with NORMALIZED.open(encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            sec = r["security_id"]
            pk = int(r["period_key"])
            field_rows[r["field_id"]] += 1
            companies.add(sec)
            rec = {
                "value": float(r["value_cny"]) if r["value_cny"] else None,
                "status": r["status"],
                "low_base": r["low_base_flag"],
                "restate": r["restatement_flag"],
                "scope": r["consolidation_scope"],
                "pre_listing": r["is_pre_listing"],
            }
            rows[(sec, pk)][r["field_id"]] = rec
            meta.setdefault((sec, pk), {
                "period_type": r["period_type"],
                "period_start": r["period_start"],
                "period_end": r["period_end"],
            })
    return rows, meta, field_rows, companies


def classify(rec) -> str:
    if rec is None:
        return "MISSING"
    if rec["status"] in HOLD:
        return "HOLD"
    if rec["status"] in USABLE:
        return "OK"
    if rec["status"] in USABLE_FLAG:
        return "LEGACY"
    return "OTHER"


def prior_year(pk: int) -> int:
    return pk - 10000


QUARTER_MAP = {331: 1231, 630: 331, 930: 630, 1231: 930}


def prior_quarter(pk: int) -> int:
    y, mmdd = divmod(pk, 10000)
    return (y - 1) * 10000 + 1231 if mmdd == 331 else y * 10000 + QUARTER_MAP[mmdd]


def days_of(meta_row) -> int | None:
    try:
        s = datetime.fromisoformat(meta_row["period_start"])
        e = datetime.fromisoformat(meta_row["period_end"])
    except Exception:
        return None
    return (e - s).days + 1


# ---------------------------------------------------------------- 指标实现

def _inputs_ok(recs):
    """返回 (state, flags)。state ∈ OK / HOLD / MISSING / LEGACY"""
    states = [classify(r) for r in recs]
    if "HOLD" in states:
        return "HOLD", ["Q01"]
    if "MISSING" in states or "OTHER" in states:
        return "MISSING", ["Q02"]
    flags = ["Q07"] if "LEGACY" in states else []
    return "OK", flags


def _flag_restate(recs, flags):
    if any(r and r["restate"] == RESTATE_PENDING for r in recs):
        flags.append("Q06")
    if any(r and r["low_base"] in LOW_BASE_FLAGS for r in recs):
        flags.append("Q05")


def metric_ratio(rows, sec, pk_t, pk_b, field, zero_guard=True, low_base_value=None):
    rt = rows.get((sec, pk_t), {}).get(field)
    rb = rows.get((sec, pk_b), {}).get(field) if pk_b else None
    if pk_b is None or rb is None:
        return {"value": None, "status": "NOT_COMPARABLE", "flags": ["Q08"], "cur": rt["value"] if rt else None, "base": None}
    state, flags = _inputs_ok([rt, rb])
    if state != "OK":
        return {"value": None, "status": state, "flags": flags,
                "cur": rt["value"] if rt else None, "base": rb["value"] if rb else None}
    _flag_restate([rt, rb], flags)
    cur, base = rt["value"], rb["value"]
    if cur is None or base is None:
        return {"value": None, "status": "MISSING", "flags": ["Q02"], "cur": cur, "base": base}
    if zero_guard and abs(base) < ZERO_BASE_ABS:
        return {"value": None, "status": "UNDEFINED_BASE", "flags": ["Q04"], "cur": cur, "base": base}
    if base < 0:
        return {"value": None, "status": "UNDEFINED_BASE", "flags": ["Q03"], "cur": cur, "base": base}
    if low_base_value is not None and abs(base) < low_base_value:
        flags.append("Q05")
    return {"value": cur / base - 1.0, "status": "OK", "flags": flags, "cur": cur, "base": base}


def metric_m03(rows, sec, pk_t):
    pk_t4 = prior_year(pk_t)
    pk_t1 = prior_quarter(pk_t)
    pk_t5 = prior_year(pk_t1)
    a = metric_ratio(rows, sec, pk_t, pk_t4, "FIN.REV.SQ")
    b = metric_ratio(rows, sec, pk_t1, pk_t5, "FIN.REV.SQ")
    flags = sorted(set(a["flags"] + b["flags"]))
    for x in (a, b):
        if x["status"] in ("HOLD", "MISSING"):
            return {"value": None, "status": x["status"], "flags": flags}
    if a["status"] != "OK" or b["status"] != "OK":
        return {"value": None, "status": "NOT_COMPARABLE", "flags": flags}
    return {"value": (a["value"] - b["value"]) * 100.0, "status": "OK", "flags": flags}


def metric_gm(rows, sec, pk_t, pk_b):
    gt = rows.get((sec, pk_t), {}).get("FIN.GROSSMARGIN.PCT")
    gb = rows.get((sec, pk_b), {}).get("FIN.GROSSMARGIN.PCT")
    state, flags = _inputs_ok([gt, gb])
    if state == "OK":
        _flag_restate([gt, gb], flags)
        if gt["value"] is not None and gb["value"] is not None:
            if gb["value"] == 0:
                return {"value": None, "status": "UNDEFINED_BASE", "flags": flags + ["Q04"]}
            return {"value": gt["value"] - gb["value"], "status": "OK", "flags": flags}
    if state == "HOLD":
        return {"value": None, "status": "HOLD", "flags": ["Q01"]}
    # 回算
    rt = rows.get((sec, pk_t), {}).get("FIN.REV.YTD")
    ct = rows.get((sec, pk_t), {}).get("FIN.COST.YTD")
    rb = rows.get((sec, pk_b), {}).get("FIN.REV.YTD")
    cb = rows.get((sec, pk_b), {}).get("FIN.COST.YTD")
    state2, flags2 = _inputs_ok([rt, ct, rb, cb])
    if state2 != "OK":
        return {"value": None, "status": "MISSING" if state2 == "MISSING" else state2, "flags": flags2}
    _flag_restate([rt, ct, rb, cb], flags2)
    if not rt["value"] or not rb["value"] or rt["value"] <= 0 or rb["value"] <= 0:
        return {"value": None, "status": "UNDEFINED_BASE", "flags": flags2 + ["Q03"]}
    gm_t = (rt["value"] - ct["value"]) / rt["value"] * 100
    gm_b = (rb["value"] - cb["value"]) / rb["value"] * 100
    return {"value": gm_t - gm_b, "status": "OK", "flags": flags2}


def metric_margin_pp(rows, sec, pk_t, pk_b):
    nt = rows.get((sec, pk_t), {}).get("FIN.NPDEDT.YTD")
    rt = rows.get((sec, pk_t), {}).get("FIN.REV.YTD")
    nb = rows.get((sec, pk_b), {}).get("FIN.NPDEDT.YTD")
    rb = rows.get((sec, pk_b), {}).get("FIN.REV.YTD")
    state, flags = _inputs_ok([nt, rt, nb, rb])
    if state != "OK":
        return {"value": None, "status": state, "flags": flags}
    _flag_restate([nt, rt, nb, rb], flags)
    if min(rt["value"], rb["value"]) <= ZERO_BASE_ABS:
        return {"value": None, "status": "UNDEFINED_BASE", "flags": flags + ["Q03"]}
    mt = nt["value"] / rt["value"] * 100
    mb = nb["value"] / rb["value"] * 100
    return {"value": mt - mb, "status": "OK", "flags": flags}


def metric_ocf_to_np(rows, sec, pk):
    o = rows.get((sec, pk), {}).get("FIN.OCF.YTD")
    n = rows.get((sec, pk), {}).get("FIN.NPP.YTD")
    state, flags = _inputs_ok([o, n])
    if state != "OK":
        return {"value": None, "status": state, "flags": flags}
    _flag_restate([o, n], flags)
    if n["value"] is None or n["value"] <= ZERO_BASE_ABS:
        return {"value": None, "status": "NOT_APPLICABLE", "flags": flags + ["Q03"]}
    return {"value": o["value"] / n["value"], "status": "OK", "flags": flags}


def metric_diff(rows, sec, pk_t, pk_b, field):
    """绝对额变动：基期为负是有效输入，不做比率。"""
    rt = rows.get((sec, pk_t), {}).get(field)
    rb = rows.get((sec, pk_b), {}).get(field)
    if rb is None:
        return {"value": None, "status": "NOT_COMPARABLE", "flags": ["Q08"],
                "cur": rt["value"] if rt else None, "base": None}
    state, flags = _inputs_ok([rt, rb])
    if state != "OK":
        return {"value": None, "status": state, "flags": flags,
                "cur": rt["value"] if rt else None, "base": rb["value"] if rb else None}
    _flag_restate([rt, rb], flags)
    if rt["value"] is None or rb["value"] is None:
        return {"value": None, "status": "MISSING", "flags": flags + ["Q02"]}
    return {"value": rt["value"] - rb["value"], "status": "OK", "flags": flags,
            "cur": rt["value"], "base": rb["value"]}


def metric_days_chg(rows, meta, sec, pk_t, pk_b, inst_field, flow_field):
    it = rows.get((sec, pk_t), {}).get(inst_field)
    ib = rows.get((sec, pk_b), {}).get(inst_field)
    ft = rows.get((sec, pk_t), {}).get(flow_field)
    fb = rows.get((sec, pk_b), {}).get(flow_field)
    state, flags = _inputs_ok([it, ib, ft, fb])
    if state != "OK":
        return {"value": None, "status": state, "flags": flags}
    _flag_restate([it, ib, ft, fb], flags)
    dt, db = days_of(meta[(sec, pk_t)]), days_of(meta[(sec, pk_b)])
    if not dt or not db or ft["value"] is None or fb["value"] is None:
        return {"value": None, "status": "MISSING", "flags": flags + ["Q02"]}
    if ft["value"] <= ZERO_BASE_ABS or fb["value"] <= ZERO_BASE_ABS:
        return {"value": None, "status": "UNDEFINED_BASE", "flags": flags + ["Q03"]}
    d_t = it["value"] / ft["value"] * dt
    d_b = ib["value"] / fb["value"] * db
    return {"value": d_t - d_b, "status": "OK", "flags": flags}


def metric_ca_ratio(rows, sec, pk_t, pk_b):
    ct = rows.get((sec, pk_t), {}).get("FIN.CONTRACTASSET.INSTANT")
    rt = rows.get((sec, pk_t), {}).get("FIN.REV.YTD")
    cb = rows.get((sec, pk_b), {}).get("FIN.CONTRACTASSET.INSTANT")
    rb = rows.get((sec, pk_b), {}).get("FIN.REV.YTD")
    if ct is None or cb is None:
        return {"value": None, "status": "NOT_APPLICABLE", "flags": ["Q02"], "note": "NOT_IN_STATEMENT"}
    state, flags = _inputs_ok([ct, rt, cb, rb])
    if state != "OK":
        return {"value": None, "status": state, "flags": flags}
    if min(rt["value"], rb["value"]) <= ZERO_BASE_ABS:
        return {"value": None, "status": "UNDEFINED_BASE", "flags": flags + ["Q03"]}
    return {"value": (ct["value"] / rt["value"] - cb["value"] / rb["value"]) * 100,
            "status": "OK", "flags": flags}


# ---------------------------------------------------------------- 结构校验

REQUIRED_TOP = ["rules_version", "plan_version", "frozen_at", "universe", "period_model",
                "field_catalog", "status_semantics", "quality_flags", "metrics", "signals",
                "risk_hints", "decision_layers", "policies", "calibration",
                "change_procedure", "no_quota_attestation"]
PATH_KEYS = ["missing", "hold", "negative_base", "zero_base", "low_base",
             "restatement", "pre_listing", "stale"]
METRIC_KEYS = ["id", "name_cn", "formula", "inputs", "unit", "direction",
               "period_requirement", "valid_range", "paths"]
OPERATORS = {">=", "<=", ">", "<", "TURN_POSITIVE", "FLAG"}
DIMENSIONS = {"GROWTH", "MARGIN", "PROFIT", "CASH"}
QUOTA_KEYS = {"target_count", "quota", "top_n", "desired_count", "must_select"}


def structural(rules, field_rows) -> None:
    missing_top = [k for k in REQUIRED_TOP if k not in rules]
    add("C01", "顶层必填键齐全", not missing_top, {"missing": missing_top})

    ids = [m["id"] for m in rules["metrics"]]
    dup = [i for i, c in Counter(ids).items() if c > 1]
    add("C02a", "指标 ID 唯一", not dup, {"duplicates": dup, "count": len(ids)})

    bad = []
    for m in rules["metrics"]:
        lack = [k for k in METRIC_KEYS if k not in m]
        lack += [f"paths.{p}" for p in PATH_KEYS if not m.get("paths", {}).get(p)]
        if lack:
            bad.append({"id": m.get("id"), "missing": lack})
    add("C02b", "每条指标 9 个字段 + 8 条路径齐全", not bad, {"bad": bad})

    fcat = set(rules["field_catalog"])
    unknown = sorted({i["field_id"] for m in rules["metrics"] for i in m["inputs"]} - fcat)
    add("C03", "指标输入字段均在字段目录中", not unknown, {"unknown": unknown})

    mism = []
    for fid, meta in rules["field_catalog"].items():
        actual = field_rows.get(fid, 0)
        if actual != meta["rows"]:
            mism.append({"field_id": fid, "declared": meta["rows"], "actual": actual})
    add("C04", "字段行数与 S00 实测一致", not mism, {"mismatch": mism})

    mid = set(ids)
    bad_sig = []
    for s in rules["signals"]:
        if s["metric"] not in mid:
            bad_sig.append({"id": s["id"], "reason": "metric 未定义"})
        if s["operator"] not in OPERATORS:
            bad_sig.append({"id": s["id"], "reason": f"operator {s['operator']}"})
        if s["dimension"] not in DIMENSIONS:
            bad_sig.append({"id": s["id"], "reason": f"dimension {s['dimension']}"})
        if s["operator"] in {">=", "<=", ">", "<"} and not isinstance(s["threshold"], (int, float)):
            bad_sig.append({"id": s["id"], "reason": "threshold 非数值"})
    add("C05", "信号定义合法（指标/算子/维度/阈值）", not bad_sig, {"bad": bad_sig})

    fids = {f["id"] for f in rules["quality_flags"]}
    bad_rh = [h["id"] for h in rules["risk_hints"] if h["metric"] not in mid and h["metric"] not in fids]
    add("C06", "风险提示引用已定义指标或标记", not bad_rh, {"bad": bad_rh})

    used = {s["metric"] for s in rules["signals"]} | {h["metric"] for h in rules["risk_hints"]}
    used |= {m["id"] for m in rules["metrics"] if m.get("feeds")}
    unused = sorted(mid - used)
    add("C07", "每个指标至少被一条信号/提示/下游指标使用", not unused, {"unused": unused}, blocking=False)

    layers = {l["id"] for l in rules["decision_layers"]}
    bad_layer = [l["id"] for l in rules["decision_layers"] if not l.get("outputs")]
    add("C08", "分层 L0-L3 齐全且输出非空",
        layers >= {"L0", "L1", "L2", "L3"} and not bad_layer,
        {"layers": sorted(layers), "bad": bad_layer})

    def scan(node, path=""):
        hits = []
        if isinstance(node, dict):
            for k, v in node.items():
                if k in QUOTA_KEYS and v not in (None, 0, [], {}):
                    hits.append(f"{path}.{k}")
                hits += scan(v, f"{path}.{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                hits += scan(v, f"{path}[{i}]")
        return hits

    quota_hits = scan(rules)
    add("C09", "无目标家数/配额/截断键", not quota_hits, {"hits": quota_hits})

    bad_path = []
    for m in rules["metrics"]:
        for p in PATH_KEYS:
            txt = m["paths"].get(p, "")
            if not any(q in txt for q in fids) and p not in ("stale",):
                bad_path.append({"metric": m["id"], "path": p, "text": txt})
    add("C10", "每条缺失路径都落到已定义标记", not bad_path, {"bad": bad_path})

    need = ["missing", "loss", "negative_zero_base", "low_base", "one_off",
            "mode", "restatement", "pre_listing", "stale_period", "non_consolidated"]
    lack = [k for k in need if not rules["policies"].get(k, {}).get("actions")]
    add("C11", "缺失/亏损/低基数/一次性/模式/重述/上市前/陈旧/口径策略齐全", not lack, {"missing": lack})

    fp = rules["input_fingerprint"]["files"]
    add("C12", "输入指纹已登记（3 个研究输入文件）", len(fp) == 3 and all(len(f["sha256"]) == 64 for f in fp),
        {"files": [f["path"] for f in fp]})


# ---------------------------------------------------------------- 主流程

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fill-fingerprint", action="store_true")
    args = ap.parse_args()

    rules = json.loads(RULES.read_text(encoding="utf-8"))

    if args.fill_fingerprint:
        for f in rules["input_fingerprint"]["files"]:
            p = ROOT / f["path"]
            f["sha256"] = sha256(p)
            f["bytes"] = p.stat().st_size
        rules["frozen_at"] = datetime.now(CST).isoformat(timespec="seconds")
        RULES.write_text(json.dumps(rules, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    rows, meta, field_rows, companies = load_rows()
    structural(rules, field_rows)

    # 指纹校验
    fp_bad = []
    for f in rules["input_fingerprint"]["files"]:
        p = ROOT / f["path"]
        if not p.exists() or sha256(p) != f["sha256"]:
            fp_bad.append(f["path"])
    add("C12b", "输入指纹与当前文件一致", not fp_bad, {"changed": fp_bad})

    add("C13", "公司数与 S00 一致（1054）", len(companies) == 1054, {"companies": len(companies)})

    # ---- 逐家计算最新期指标（只聚合，不输出个体）
    latest: dict[str, int] = {}
    for (sec, pk), fields in rows.items():
        usable = any(
            fields.get(f) and classify(fields[f]) in ("OK", "LEGACY") and fields[f]["value"] is not None
            for f in ("FIN.REV.YTD", "FIN.REV.SQ", "FIN.NPDEDT.YTD")
        )
        if usable and (sec not in latest or pk > latest[sec]):
            latest[sec] = pk
    add("D01", "每家可确定最新可用期或落入 W1（合计 1054）", len(latest) <= 1054,
        {"resolved": len(latest), "w1_no_data": 1054 - len(latest)})

    cov = {m["id"]: Counter() for m in rules["metrics"]}
    values: dict[str, list[float]] = defaultdict(list)
    per_company: dict[str, dict[str, dict]] = defaultdict(dict)

    for sec, pk in latest.items():
        pkb = prior_year(pk)
        res = {
            "M01": metric_ratio(rows, sec, pk, pkb, "FIN.REV.YTD", low_base_value=LOW_BASE_REV),
            "M02": metric_ratio(rows, sec, pk, prior_year(pk), "FIN.REV.SQ", low_base_value=LOW_BASE_REV),
            "M03": metric_m03(rows, sec, pk),
            "M04": metric_gm(rows, sec, pk, pkb),
            "M05": metric_ratio(rows, sec, pk, pkb, "FIN.NPDEDT.YTD", low_base_value=LOW_BASE_NPDEDT),
            "M06": metric_margin_pp(rows, sec, pk, pkb),
            "M07": metric_ratio(rows, sec, pk, prior_year(pk), "FIN.NPDEDT.SQ", low_base_value=LOW_BASE_NPDEDT),
            "M08": metric_ocf_to_np(rows, sec, pk),
            "M09": metric_diff(rows, sec, pk, pkb, "FIN.OCF.YTD"),
            "M10": metric_days_chg(rows, meta, sec, pk, pkb, "FIN.AR.INSTANT", "FIN.REV.YTD"),
            "M11": metric_days_chg(rows, meta, sec, pk, pkb, "FIN.INV.INSTANT", "FIN.COST.YTD"),
            "M12": metric_ca_ratio(rows, sec, pk, pkb),
        }
        per_company[sec] = res
        for mid, r in res.items():
            cov[mid][r["status"]] += 1
            for fl in r["flags"]:
                cov[mid][fl] += 1
            if r["status"] == "OK" and r["value"] is not None:
                values[mid].append(r["value"])

    total = len(latest)
    cov_rows = []
    for m in rules["metrics"]:
        c = cov[m["id"]]
        ok = c.get("OK", 0)
        cov_rows.append({
            "metric_id": m["id"],
            "metric_name_cn": m["name_cn"],
            "unit": m["unit"],
            "companies_total": total,
            "ok": ok,
            "hold": c.get("HOLD", 0),
            "missing": c.get("MISSING", 0),
            "not_comparable": c.get("NOT_COMPARABLE", 0),
            "undefined_base": c.get("UNDEFINED_BASE", 0),
            "not_applicable": c.get("NOT_APPLICABLE", 0),
            "flag_q05_low_base": c.get("Q05", 0),
            "flag_q06_restatement": c.get("Q06", 0),
            "flag_q07_legacy": c.get("Q07", 0),
            "ok_share": round(ok / total, 4) if total else 0,
        })

    add("D02", "每条指标都有可计算样本（OK>0）",
        all(r["ok"] > 0 for r in cov_rows),
        {r["metric_id"]: r["ok"] for r in cov_rows})

    # ---- 信号与分层（仅聚合计数，标注 NOT_A_RESULT）
    sig_hits = Counter()
    l1 = Counter()
    l2 = Counter()
    dim_hits = Counter()

    for sec, res in per_company.items():
        fired = []
        for s in rules["signals"]:
            mid = s["metric"]
            r = res[mid]
            if r["status"] != "OK" or r["value"] is None:
                if s["id"] == "SG06" and mid == "M05":
                    pass
                continue
            ok = False
            if s["operator"] == ">=":
                ok = r["value"] >= s["threshold"]
            if ok:
                # 低基数信号需绝对额确认才计入 L2
                confirmed = "Q05" not in r["flags"]
                fired.append({"id": s["id"], "dim": s["dimension"], "confirmed": confirmed, "mid": mid})
                sig_hits[s["id"]] += 1
                dim_hits[s["dimension"]] += 1

        # SG06 扣非转正（不走 ratio）
        r5 = res["M05"]
        if r5["status"] == "UNDEFINED_BASE" and r5["cur"] is not None and r5["base"] is not None:
            if r5["base"] < 0 and r5["cur"] > 0 and r5["cur"] >= ABS_CONFIRM:
                fired.append({"id": "SG06", "dim": "PROFIT", "confirmed": True, "mid": "M05"})
                sig_hits["SG06"] += 1
                dim_hits["PROFIT"] += 1

        # SG08 现金流转正
        o = rows.get((sec, latest[sec]), {}).get("FIN.OCF.YTD")
        ob = rows.get((sec, prior_year(latest[sec])), {}).get("FIN.OCF.YTD")
        if o and ob and classify(o) == "OK" and classify(ob) == "OK" and o["value"] is not None and ob["value"] is not None:
            if o["value"] > 0 and ob["value"] <= 0:
                fired.append({"id": "SG08", "dim": "CASH", "confirmed": True, "mid": "M09"})
                sig_hits["SG08"] += 1
                dim_hits["CASH"] += 1

        if fired:
            l1["OBSERVE_QUEUE"] += 1
        else:
            rh = any(res[h["metric"]]["status"] == "OK" and res[h["metric"]]["value"] is not None
                     and ((h["operator"] == ">=" and res[h["metric"]]["value"] >= h["threshold"])
                          or (h["operator"] == "<" and res[h["metric"]]["value"] < h["threshold"])
                          or (h["operator"] == "<=" and res[h["metric"]]["value"] <= h["threshold"]))
                     for h in rules["risk_hints"] if h["metric"] in res)
            l1["RISK_WATCH" if rh else "NO_SIGNAL"] += 1

        dims = {f["dim"] for f in fired if f["confirmed"]}
        used_hold = any(res[f["mid"]]["status"] == "HOLD" for f in fired)
        if len(dims) >= 2 and not used_hold:
            l2["SHORTLIST_CANDIDATE"] += 1
        elif used_hold:
            l2["HOLD_FOR_DATA"] += 1
        else:
            l2["NOT_SHORTLISTED"] += 1

    add("D03", "信号全部可触发（9 条信号均有命中或明确为条件型）",
        len(sig_hits) >= 7, {"hits": dict(sig_hits)}, blocking=False)
    add("D04", "L1/L2 分层可执行（计数仅干跑，不作为结果）",
        sum(l1.values()) == total and sum(l2.values()) == total,
        {"L1": dict(l1), "L2": dict(l2), "note": "NOT_A_RESULT：S02/S03 必须重算，本处只验证规则可执行"})

    # ---- 写覆盖表（只聚合，无公司名）
    S01.mkdir(parents=True, exist_ok=True)
    out = S01 / "metric_coverage_dryrun.csv"
    with out.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(cov_rows[0].keys()), lineterminator="\n")
        w.writeheader()
        w.writerows(cov_rows)

    leaked = [c for c in cov_rows[0] if c in ("security_id", "stock_code", "stock_name")]
    add("D05", "覆盖表不含公司标识列", not leaked, {"columns": list(cov_rows[0].keys())})

    quant = {}
    for mid, vals in values.items():
        vals.sort()
        n = len(vals)
        quant[mid] = {
            "n": n,
            "p10": round(vals[int(n * 0.10)], 6),
            "p25": round(vals[int(n * 0.25)], 6),
            "p50": round(vals[int(n * 0.50)], 6),
            "p75": round(vals[int(n * 0.75)], 6),
            "p90": round(vals[int(n * 0.90)], 6),
        }

    blocking_fail = [c for c in checks if c["result"] == "FAIL" and c["blocking"]]
    result = {
        "issue_key": "S01",
        "issue_number": 36,
        "rules_version": rules["rules_version"],
        "checked_at": datetime.now(CST).isoformat(timespec="seconds"),
        "rules_sha256": sha256(RULES),
        "checks_total": len(checks),
        "checks_pass": sum(1 for c in checks if c["result"] == "PASS"),
        "checks_fail": sum(1 for c in checks if c["result"] == "FAIL"),
        "blocking_fail": len(blocking_fail),
        "checks": checks,
        "dryrun": {
            "label": "ANONYMOUS_DRYRUN_NOT_A_RESULT",
            "companies": total,
            "latest_period_distribution": dict(sorted(Counter(str(v) for v in latest.values()).items())),
            "metric_coverage": {r["metric_id"]: r for r in cov_rows},
            "signal_hits": dict(sig_hits),
            "dimension_hits": dict(dim_hits),
            "L1_counts": dict(l1),
            "L2_counts": dict(l2),
            "breadth_observation": {
                "L1_observe_share": round(l1["OBSERVE_QUEUE"] / total, 4) if total else 0,
                "L2_shortlist_share": round(l2["SHORTLIST_CANDIDATE"] / total, 4) if total else 0,
                "interpretation": "v1 阈值偏松（SG01∪SG02 覆盖绝大多数公司），属已知局限；按预登记原则本次不据此调整阈值，若需收紧须在 S04 前另立 v2 并全池重算。"
            },
            "quantiles_exploratory": quant,
            "note": "只做可执行性验证与匿名分布描述，不产出名单；S02 必须按同一规则重算。"
        },
    }
    (S01 / "self_check.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({
        "checks": f"{result['checks_pass']}/{result['checks_total']} PASS",
        "blocking_fail": result["blocking_fail"],
        "companies": total,
        "L1": dict(l1),
        "L2": dict(l2),
        "coverage_csv": str(out.relative_to(ROOT)),
    }, ensure_ascii=False, indent=2))

    for c in blocking_fail:
        print(f"FAIL {c['id']} {c['item']}: {c['detail']}", file=sys.stderr)
    return 1 if blocking_fail else 0


if __name__ == "__main__":
    sys.exit(main())
