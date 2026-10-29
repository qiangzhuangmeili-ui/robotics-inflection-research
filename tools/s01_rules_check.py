#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""S01 规则可执行性校验 + 匿名干跑覆盖 + 政策合成测试（实现 R3）。

对应三轮复核：
R1 四项阻断（Q06 进 L2 / 低基数确认 / 质量边界 / 毛利率 pp 边界）
R2 三项剩余（SG07 质量并集 / SG02 单位矛盾 / UNKNOWN 口径）

设计原则：**信号与阈值从规则文件读，不在代码里另写一份**，避免单位漂移。
规则版本：screen_rules_v2.json（v1 原冻结文件保留不改，差异登记在 change_log 与勘误文件）。

用法：
    python tools/s01_rules_check.py
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
S01 = ROOT / "runs/issues/S01"
RULES = S01 / "screen_rules_v2.json"
RULES_V1 = S01 / "screen_rules_v1.json"
NORMALIZED = ROOT / "runs/issues/S00/financial_normalized.csv"
CST = timezone(timedelta(hours=8))
V1_SHA_EXPECTED = "c76d04615669788dddc17425de6afd78ec55be4b7f20bbd75b7322e777858f7e"

USABLE = {
    "EXTRACTED", "EXTRACTED_KEY_TABLE", "EXTRACTED_QUARTERLY_TABLE",
    "DERIVED", "DERIVED_CUMULATIVE_DIFF", "DERIVED_Q1_EQUALS_YTD",
    "DERIVED_QUARTERLY_SUM_OVERRIDE",
}
USABLE_FLAG = {"LEGACY_SNAPSHOT"}
HOLD = {"EXTRACTED_XCHECK_MISMATCH", "DERIVED_HOLD_UPSTREAM", "DERIVED_Q1_HOLD_UPSTREAM"}
LOW_BASE_FLAGS = {"LOW_BASE_REV", "LOW_BASE_PROFIT", "NEGATIVE_BASE_PROFIT"}
RESTATE_PENDING = "RESTATEMENT_INDICATED_NEEDS_REVIEW"
RESTATE_CONFIRMED = "是"
ZERO_BASE_ABS = 1_000_000.0
LOW_BASE_REV = 50_000_000.0
LOW_BASE_NPDEDT = 10_000_000.0
ABS_CONFIRM = 10_000_000.0

CONFIRMABLE = {"M01": "AMOUNT", "M02": "AMOUNT", "M05": "AMOUNT",
               "M07": "AMOUNT", "M09": "AMOUNT"}

# 复合信号的全部必需指标：SG07 需要 M08 与 M09，SG08 需要 M09
SIGNAL_DEPS = {"SG01": ["M01"], "SG02": ["M03"], "SG03": ["M04"], "SG04": ["M05"],
               "SG05": ["M06"], "SG06": ["M05"], "SG07": ["M08", "M09"], "SG08": ["M09"]}

checks: list[dict] = []
tests: list[dict] = []
SIGNALS: list[dict] = []
RISK: list[dict] = []


def add(cid, item, ok, detail, blocking=True):
    checks.append({"id": cid, "item": item, "result": "PASS" if ok else "FAIL",
                   "blocking": blocking, "detail": detail})


def add_test(tid, name, expected, actual, ok, note=""):
    tests.append({"id": tid, "name": name, "expected": expected, "actual": actual,
                  "result": "PASS" if ok else "FAIL", "note": note})


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def res(value, status, flags, cur=None, base=None, note=None):
    return {"value": value, "status": status, "flags": set(flags),
            "cur": cur, "base": base, "note": note}


def _v(rec):
    return rec["value"] if rec else None


def load_signal_defs(rules):
    """信号与阈值一律从规则文件读，代码不另写阈值。"""
    global SIGNALS, RISK
    SIGNALS = [{"id": s["id"], "metric": s["metric"], "op": s["operator"],
                "thr": s["threshold"], "dim": s["dimension"]} for s in rules["signals"]]
    RISK = [{"id": h["id"], "metric": h["metric"], "op": h["operator"], "thr": h["threshold"]}
            for h in rules["risk_hints"] if h["operator"] in {">=", "<", "<="}]


# ---------------------------------------------------------------- 装载

def load_rows():
    rows = defaultdict(dict)
    meta = defaultdict(dict)
    field_rows = Counter()
    companies = set()
    with NORMALIZED.open(encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            sec, pk, fid = r["security_id"], int(r["period_key"]), r["field_id"]
            field_rows[fid] += 1
            companies.add(sec)
            rows[(sec, pk)][fid] = {
                "value": float(r["value_cny"]) if r["value_cny"] else None,
                "status": r["status"],
                "low_base": r["low_base_flag"],
                "restate": r["restatement_flag"],
                "scope": r["consolidation_scope"],
                "pre_listing": r["is_pre_listing"],
                "document_id": r["document_id"],
                "version_used": r["version_used"],
                "comparability": r["comparability_note"],
            }
            meta[(sec, pk)][fid] = {
                "period_type": r["period_type"],
                "period_start": r["period_start"],
                "period_end": r["period_end"],
            }
    return rows, meta, field_rows, companies


def prior_year(pk):
    return pk - 10000


QUARTER_MAP = {331: 1231, 630: 331, 930: 630, 1231: 930}


def prior_quarter(pk):
    y, mmdd = divmod(pk, 10000)
    return (y - 1) * 10000 + 1231 if mmdd == 331 else y * 10000 + QUARTER_MAP[mmdd]


def days_of(m):
    try:
        s = date.fromisoformat(m["period_start"])
        e = date.fromisoformat(m["period_end"])
    except Exception:
        return None
    return (e - s).days + 1


# ---------------------------------------------------------------- 质量判定

def _inputs(recs):
    """OK / HOLD / MISSING / EXCLUDED_SCOPE / NOT_COMPARABLE。

    非旧快照必须明确 CONSOLIDATED；UNKNOWN 只有 LEGACY_SNAPSHOT 行可放行（记 Q07）。
    """
    if any(r is None for r in recs):
        return "MISSING", {"Q02"}
    if any(r["status"] in HOLD for r in recs):
        return "HOLD", {"Q01"}
    if any(r["status"] not in USABLE and r["status"] not in USABLE_FLAG for r in recs):
        return "MISSING", {"Q02"}
    if any(r["scope"] != "CONSOLIDATED" and r["status"] not in USABLE_FLAG for r in recs):
        return "EXCLUDED_SCOPE", {"Q12"}
    if any(r["pre_listing"] == "YES" for r in recs):
        return "NOT_COMPARABLE", {"Q08"}
    flags = {"Q07"} if any(r["status"] in USABLE_FLAG for r in recs) else set()
    return "OK", flags


def _restate(recs):
    f = set()
    for r in recs:
        if not r:
            continue
        if r["restate"] in (RESTATE_PENDING, RESTATE_CONFIRMED):
            f.add("Q06")
        elif "RESTATED_PRIOR_YEARS_UNRECALCULATED" in (r["comparability"] or ""):
            f.add("Q06")
    return f


def _low_base(recs, base_value, threshold):
    if any(r and r["low_base"] in LOW_BASE_FLAGS for r in recs):
        return True
    if threshold and base_value is not None and abs(base_value) < threshold:
        return True
    return False


def _one_off(rows, sec, pk):
    npp = rows.get((sec, pk), {}).get("FIN.NPP.YTD")
    dedt = rows.get((sec, pk), {}).get("FIN.NPDEDT.YTD")
    if not npp or not dedt or npp["value"] is None or dedt["value"] is None:
        return False
    return abs(npp["value"] - dedt["value"]) / max(abs(npp["value"]), 1.0) > 0.5


# ---------------------------------------------------------------- 指标

def _ratio(rows, sec, pk, pkb, field, low_base_thr=None):
    rt = rows.get((sec, pk), {}).get(field)
    rb = rows.get((sec, pkb), {}).get(field) if pkb else None
    if rb is None:
        return res(None, "NOT_COMPARABLE", {"Q08"}, cur=_v(rt))
    st, fl = _inputs([rt, rb])
    if st != "OK":
        return res(None, st, fl, cur=_v(rt), base=_v(rb))
    fl |= _restate([rt, rb])
    cur, base = _v(rt), _v(rb)
    if cur is None or base is None:
        return res(None, "MISSING", fl | {"Q02"}, cur, base)
    if _low_base([rt, rb], base, low_base_thr):
        fl.add("Q05")
    if abs(base) < ZERO_BASE_ABS:
        return res(None, "UNDEFINED_BASE", fl | {"Q04"}, cur, base)
    if base < 0:
        return res(None, "UNDEFINED_BASE", fl | {"Q03"}, cur, base)
    return res(cur / base - 1.0, "OK", fl, cur, base)


def _diff(rows, sec, pk, pkb, field):
    rt = rows.get((sec, pk), {}).get(field)
    rb = rows.get((sec, pkb), {}).get(field) if pkb else None
    if rb is None:
        return res(None, "NOT_COMPARABLE", {"Q08"}, cur=_v(rt))
    st, fl = _inputs([rt, rb])
    if st != "OK":
        return res(None, st, fl, cur=_v(rt), base=_v(rb))
    fl |= _restate([rt, rb])
    cur, base = _v(rt), _v(rb)
    if cur is None or base is None:
        return res(None, "MISSING", fl | {"Q02"}, cur, base)
    return res(cur - base, "OK", fl, cur, base)


def m03(rows, sec, pk):
    pkt4, pkt1 = prior_year(pk), prior_quarter(pk)
    pkt5 = prior_year(pkt1)
    a = _ratio(rows, sec, pk, pkt4, "FIN.REV.SQ", LOW_BASE_REV)
    b = _ratio(rows, sec, pkt1, pkt5, "FIN.REV.SQ", LOW_BASE_REV)
    fl = a["flags"] | b["flags"]
    for x in (a, b):
        if x["status"] in ("HOLD", "MISSING", "EXCLUDED_SCOPE", "NOT_COMPARABLE"):
            return res(None, x["status"], fl)
    if a["status"] != "OK" or b["status"] != "OK":
        return res(None, "NOT_COMPARABLE", fl | {"Q08"})
    return res((a["value"] - b["value"]) * 100.0, "OK", fl)   # 单位：pp


def m04(rows, sec, pk, pkb):
    gt = rows.get((sec, pk), {}).get("FIN.GROSSMARGIN.PCT")
    gb = rows.get((sec, pkb), {}).get("FIN.GROSSMARGIN.PCT")
    if gt is not None and gb is not None:
        st, fl = _inputs([gt, gb])
        if st == "OK":
            fl |= _restate([gt, gb])
            if gt["value"] is None or gb["value"] is None:
                return res(None, "MISSING", fl | {"Q02"})
            return res(gt["value"] - gb["value"], "OK", fl)   # 百分点差分，不以基期为分母
        if st == "HOLD":
            return res(None, "HOLD", {"Q01"})
        if st in ("EXCLUDED_SCOPE", "NOT_COMPARABLE"):
            return res(None, st, fl)
    rt = rows.get((sec, pk), {}).get("FIN.REV.YTD")
    ct = rows.get((sec, pk), {}).get("FIN.COST.YTD")
    rb = rows.get((sec, pkb), {}).get("FIN.REV.YTD")
    cb = rows.get((sec, pkb), {}).get("FIN.COST.YTD")
    st2, fl2 = _inputs([rt, ct, rb, cb])
    if st2 != "OK":
        return res(None, st2, fl2)
    fl2 |= _restate([rt, ct, rb, cb])
    if rt["document_id"] != ct["document_id"] or rb["document_id"] != cb["document_id"]:
        return res(None, "VERSION_MISMATCH", fl2, note="回算要求 REV 与 COST 同期同版本")
    if rt["version_used"] != ct["version_used"] or rb["version_used"] != cb["version_used"]:
        return res(None, "VERSION_MISMATCH", fl2, note="回算要求 REV 与 COST 同版本")
    if min(rt["value"], rb["value"]) <= ZERO_BASE_ABS:
        return res(None, "UNDEFINED_BASE", fl2 | {"Q03"})
    gm_t = (rt["value"] - ct["value"]) / rt["value"] * 100
    gm_b = (rb["value"] - cb["value"]) / rb["value"] * 100
    return res(gm_t - gm_b, "OK", fl2, note="RECOMPUTED_FROM_STATEMENT")


def m06(rows, sec, pk, pkb):
    nt = rows.get((sec, pk), {}).get("FIN.NPDEDT.YTD")
    rt = rows.get((sec, pk), {}).get("FIN.REV.YTD")
    nb = rows.get((sec, pkb), {}).get("FIN.NPDEDT.YTD")
    rb = rows.get((sec, pkb), {}).get("FIN.REV.YTD")
    if rb is None or nb is None:
        return res(None, "NOT_COMPARABLE", {"Q08"})
    st, fl = _inputs([nt, rt, nb, rb])
    if st != "OK":
        return res(None, st, fl)
    fl |= _restate([nt, rt, nb, rb])
    if _one_off(rows, sec, pk):
        fl.add("Q09")
    if min(rt["value"], rb["value"]) <= ZERO_BASE_ABS:
        return res(None, "UNDEFINED_BASE", fl | {"Q03"})
    return res((nt["value"] / rt["value"] - nb["value"] / rb["value"]) * 100, "OK", fl)


def m08(rows, sec, pk):
    """现金含量：Q05 必须从原始 OCF / 归母输入传播（没有绝对额确认口径）。"""
    o = rows.get((sec, pk), {}).get("FIN.OCF.YTD")
    n = rows.get((sec, pk), {}).get("FIN.NPP.YTD")
    st, fl = _inputs([o, n])
    if st != "OK":
        return res(None, st, fl)
    fl |= _restate([o, n])
    if _low_base([o, n], None, None):
        fl.add("Q05")
    if n["value"] is None or n["value"] <= ZERO_BASE_ABS:
        return res(None, "NOT_APPLICABLE", fl | {"Q03"})
    return res(o["value"] / n["value"], "OK", fl)


def m_days(rows, meta, sec, pk, pkb, inst, flow):
    it = rows.get((sec, pk), {}).get(inst)
    ib = rows.get((sec, pkb), {}).get(inst)
    ft = rows.get((sec, pk), {}).get(flow)
    fb = rows.get((sec, pkb), {}).get(flow)
    if ib is None or fb is None:
        return res(None, "NOT_COMPARABLE", {"Q08"})
    st, fl = _inputs([it, ib, ft, fb])
    if st != "OK":
        return res(None, st, fl)
    fl |= _restate([it, ib, ft, fb])
    mt = meta.get((sec, pk), {}).get(flow)
    mb = meta.get((sec, pkb), {}).get(flow)
    dt = days_of(mt) if mt else None
    db = days_of(mb) if mb else None
    if not dt or not db:
        return res(None, "MISSING", fl | {"Q02"})
    if None in (ft["value"], fb["value"], it["value"], ib["value"]):
        return res(None, "MISSING", fl | {"Q02"})
    if ft["value"] <= ZERO_BASE_ABS or fb["value"] <= ZERO_BASE_ABS:
        return res(None, "UNDEFINED_BASE", fl | {"Q03"})
    return res(it["value"] / ft["value"] * dt - ib["value"] / fb["value"] * db, "OK", fl)


def m12(rows, sec, pk, pkb):
    ct = rows.get((sec, pk), {}).get("FIN.CONTRACTASSET.INSTANT")
    rt = rows.get((sec, pk), {}).get("FIN.REV.YTD")
    cb = rows.get((sec, pkb), {}).get("FIN.CONTRACTASSET.INSTANT")
    rb = rows.get((sec, pkb), {}).get("FIN.REV.YTD")
    if ct is None or cb is None:
        return res(None, "NOT_APPLICABLE", {"Q02"}, note="NOT_IN_STATEMENT")
    st, fl = _inputs([ct, rt, cb, rb])
    if st != "OK":
        return res(None, st, fl)
    fl |= _restate([ct, rt, cb, rb])
    if min(rt["value"], rb["value"]) <= ZERO_BASE_ABS:
        return res(None, "UNDEFINED_BASE", fl | {"Q03"})
    return res((ct["value"] / rt["value"] - cb["value"] / rb["value"]) * 100, "OK", fl)


def project_mode(rows, sec, pk):
    ca = rows.get((sec, pk), {}).get("FIN.CONTRACTASSET.INSTANT")
    ta = rows.get((sec, pk), {}).get("FIN.ASSET.INSTANT")
    rv = rows.get((sec, pk), {}).get("FIN.REV.YTD")
    if not ca or ca["value"] is None:
        return False
    if ta and ta["value"]:
        return ca["value"] / ta["value"] > 0.05
    if rv and rv["value"]:
        return ca["value"] / rv["value"] > 0.10
    return False


def evaluate(rows, meta, sec, pk, stale=False):
    pkb = prior_year(pk)
    pm = project_mode(rows, sec, pk)
    out = {
        "M01": _ratio(rows, sec, pk, pkb, "FIN.REV.YTD", LOW_BASE_REV),
        "M02": _ratio(rows, sec, pk, pkb, "FIN.REV.SQ", LOW_BASE_REV),
        "M03": m03(rows, sec, pk),
        "M04": m04(rows, sec, pk, pkb),
        "M05": _ratio(rows, sec, pk, pkb, "FIN.NPDEDT.YTD", LOW_BASE_NPDEDT),
        "M06": m06(rows, sec, pk, pkb),
        "M07": _ratio(rows, sec, pk, pkb, "FIN.NPDEDT.SQ", LOW_BASE_NPDEDT),
        "M08": m08(rows, sec, pk),
        "M09": _diff(rows, sec, pk, pkb, "FIN.OCF.YTD"),
        "M10": m_days(rows, meta, sec, pk, pkb, "FIN.AR.INSTANT", "FIN.REV.YTD"),
        "M11": m_days(rows, meta, sec, pk, pkb, "FIN.INV.INSTANT", "FIN.COST.YTD"),
        "M12": m12(rows, sec, pk, pkb),
    }
    for mid in ("M05", "M06", "M07"):
        if out[mid]["status"] in ("OK", "UNDEFINED_BASE") and _one_off(rows, sec, pk):
            out[mid]["flags"].add("Q09")
    if pm:
        out["M11"] = res(None, "NOT_APPLICABLE", {"Q10"}, note="PROJECT_MODE")
    if stale:
        for r in out.values():
            r["flags"].add("Q11")
    for r in out.values():
        if r["status"] == "OK" and "Q06" in r["flags"]:
            r["status"] = "PROVISIONAL"
    return out, pm


EVALUABLE = ("OK", "PROVISIONAL")


# ---------------------------------------------------------------- 信号与分层

def signal_flags(sid, res_map):
    """从原始指标结果重新取依赖标记，不信任信号自报的 flags。"""
    fl = set()
    for m in SIGNAL_DEPS.get(sid, []):
        fl |= res_map[m]["flags"]
    return fl


def confirm_low_base(mid, flags, cur, base):
    if "Q05" not in flags:
        return True, "NO_LOW_BASE"
    if CONFIRMABLE.get(mid) is None:
        return False, "NO_CONFIRM_INPUT"
    if cur is None or base is None:
        return False, "NO_CONFIRM_INPUT"
    inc = cur - base
    return (inc >= ABS_CONFIRM), ("CONFIRMED_ABS" if inc >= ABS_CONFIRM else "ABS_BELOW_THRESHOLD")


def signals_of(rows, sec, pk, res_map):
    fired = []
    for s in SIGNALS:
        if s["op"] not in (">=", "<", "<="):
            continue                                   # TURN_POSITIVE 走下面的专门分支
        r = res_map[s["metric"]]
        if r["status"] not in EVALUABLE or r["value"] is None:
            continue
        ok = r["value"] >= s["thr"] if s["op"] == ">=" else r["value"] <= s["thr"]
        if s["id"] == "SG07":
            m9 = res_map["M09"]
            ok = ok and m9["status"] in EVALUABLE and m9["value"] is not None and m9["value"] > 0
        if ok:
            fired.append({"id": s["id"], "dim": s["dim"], "metric": s["metric"],
                          "value": r["value"], "deps": SIGNAL_DEPS.get(s["id"], [s["metric"]])})

    r5 = res_map["M05"]
    if r5["status"] == "UNDEFINED_BASE" and r5["cur"] is not None and r5["base"] is not None:
        if r5["base"] < 0 and r5["cur"] > 0 and r5["cur"] >= ABS_CONFIRM:
            fired.append({"id": "SG06", "dim": "PROFIT", "metric": "M05",
                          "value": r5["cur"], "deps": ["M05"]})

    o = rows.get((sec, pk), {}).get("FIN.OCF.YTD")
    ob = rows.get((sec, prior_year(pk)), {}).get("FIN.OCF.YTD")
    if o and ob and o["status"] in USABLE | USABLE_FLAG and ob["status"] in USABLE | USABLE_FLAG \
            and o["value"] is not None and ob["value"] is not None:
        if o["value"] > 0 and ob["value"] <= 0:
            fired.append({"id": "SG08", "dim": "CASH", "metric": "M09",
                          "value": o["value"] - ob["value"], "deps": ["M09"]})

    for f in fired:
        fl = signal_flags(f["id"], res_map)
        f["flags"] = fl
        cur = res_map[f["metric"]]["cur"]
        base = res_map[f["metric"]]["base"]
        if f["id"] == "SG06":
            conf, why = True, "CONFIRMED_ABS"
        elif f["id"] == "SG08":
            conf, why = confirm_low_base("M09", fl, o["value"], ob["value"])
        else:
            conf, why = confirm_low_base(f["metric"], fl, cur, base)
        f["confirmed"], f["confirm"] = conf, why
    return fired


def layers(fired, res_map):
    if fired:
        l1 = "OBSERVE_QUEUE"
    else:
        rh = any(res_map[h["metric"]]["status"] in EVALUABLE and res_map[h["metric"]]["value"] is not None
                 and ((h["op"] == ">=" and res_map[h["metric"]]["value"] >= h["thr"])
                      or (h["op"] == "<" and res_map[h["metric"]]["value"] < h["thr"])
                      or (h["op"] == "<=" and res_map[h["metric"]]["value"] <= h["thr"]))
                 for h in RISK)
        l1 = "RISK_WATCH" if rh else "NO_SIGNAL"

    def clean(f):
        return "Q06" not in signal_flags(f["id"], res_map) and f["confirmed"]

    eligible = [f for f in fired if clean(f)]
    dims = {f["dim"] for f in eligible}
    dims_all = {f["dim"] for f in fired if f["confirmed"]}
    dim_hold = [d for d, ms in {"GROWTH": ["M01", "M02", "M03"], "MARGIN": ["M04"],
                                "PROFIT": ["M05", "M06", "M07"], "CASH": ["M08", "M09"]}.items()
                if all(res_map[m]["status"] == "HOLD" for m in ms)]
    if dim_hold:
        l2 = "HOLD_FOR_DATA"
    elif len(dims) >= 2:
        l2 = "SHORTLIST_CANDIDATE"
    else:
        l2 = "NOT_SHORTLISTED"
    flip = 1 if (len(dims_all) >= 2 and len(dims) < 2) else 0
    return l1, l2, dims, len(fired) - len(eligible), flip


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


def structural(rules, field_rows):
    add("C01", "顶层必填键齐全", not [k for k in REQUIRED_TOP if k not in rules],
        {"missing": [k for k in REQUIRED_TOP if k not in rules]})

    ids = [m["id"] for m in rules["metrics"]]
    dup = [i for i, c in Counter(ids).items() if c > 1]
    add("C02a", "指标 ID 唯一", not dup, {"duplicates": dup, "count": len(ids)})

    bad = []
    for m in rules["metrics"]:
        lack = [k for k in METRIC_KEYS if k not in m]
        lack += [f"paths.{p}" for p in PATH_KEYS if not m.get("paths", {}).get(p)]
        if lack:
            bad.append({"id": m.get("id"), "missing": lack})
    add("C02b", "每条指标 9 字段 + 8 路径齐全", not bad, {"bad": bad})

    fcat = set(rules["field_catalog"])
    unknown = sorted({i["field_id"] for m in rules["metrics"] for i in m["inputs"]} - fcat)
    add("C03", "指标输入字段均在字段目录中", not unknown, {"unknown": unknown})

    mism = [{"field_id": f, "declared": m["rows"], "actual": field_rows.get(f, 0)}
            for f, m in rules["field_catalog"].items() if field_rows.get(f, 0) != m["rows"]]
    add("C04", "字段行数与 S00 实测一致", not mism, {"mismatch": mism})

    mid = set(ids)
    bad_sig = []
    for s in rules["signals"]:
        if s["metric"] not in mid:
            bad_sig.append({"id": s["id"], "reason": "metric 未定义"})
        if s["operator"] not in OPERATORS:
            bad_sig.append({"id": s["id"], "reason": "operator"})
        if s["dimension"] not in DIMENSIONS:
            bad_sig.append({"id": s["id"], "reason": "dimension"})
    add("C05", "信号定义合法", not bad_sig, {"bad": bad_sig})

    fids = {f["id"] for f in rules["quality_flags"]}
    bad_rh = [h["id"] for h in rules["risk_hints"] if h["metric"] not in mid and h["metric"] not in fids]
    add("C06", "风险提示引用已定义指标或标记", not bad_rh, {"bad": bad_rh})

    used = {s["metric"] for s in rules["signals"]} | {h["metric"] for h in rules["risk_hints"]}
    used |= {m["id"] for m in rules["metrics"] if m.get("feeds")}
    add("C07", "每个指标至少被信号/提示/下游使用", not sorted(mid - used),
        {"unused": sorted(mid - used)}, blocking=False)

    layers_ = {l["id"] for l in rules["decision_layers"]}
    add("C08", "分层 L0-L3 齐全且输出非空",
        layers_ >= {"L0", "L1", "L2", "L3"} and not [l["id"] for l in rules["decision_layers"] if not l.get("outputs")],
        {"layers": sorted(layers_)})

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

    add("C09", "无目标家数/配额/截断键", not scan(rules), {"hits": scan(rules)})

    bad_path = []
    for m in rules["metrics"]:
        for p in PATH_KEYS:
            txt = m["paths"].get(p, "")
            if not any(q in txt for q in fids) and p != "stale":
                bad_path.append({"metric": m["id"], "path": p})
    add("C10", "每条缺失路径落到已定义标记", not bad_path, {"bad": bad_path})

    need = ["missing", "loss", "negative_zero_base", "low_base", "one_off",
            "mode", "restatement", "pre_listing", "stale_period", "non_consolidated"]
    lack = [k for k in need if not rules["policies"].get(k, {}).get("actions")]
    add("C11", "九类策略齐全", not lack, {"missing": lack})

    fp = rules["input_fingerprint"]["files"]
    add("C12", "输入指纹已登记（3 个研究输入）",
        len(fp) == 3 and all(len(f["sha256"]) == 64 for f in fp),
        {"files": [f["path"] for f in fp]})

    # 版本纪律：v1 原冻结文件不得改动；v1→v2 差异必须只在登记项
    v1_sha = sha256(RULES_V1) if RULES_V1.exists() else ""
    add("C14", "v1 原冻结文件未被改动", v1_sha == V1_SHA_EXPECTED,
        {"v1_sha256": v1_sha, "expected": V1_SHA_EXPECTED})

    v1 = json.loads(RULES_V1.read_text(encoding="utf-8"))
    diffs = []
    idx = {s["id"]: i for i, s in enumerate(v1["signals"])}

    def walk(a, b, path=""):
        if type(a) is not type(b):
            diffs.append(path)
            return
        if isinstance(a, dict):
            for k in set(a) | set(b):
                if k not in a or k not in b:
                    diffs.append(f"{path}.{k}".lstrip("."))
                else:
                    walk(a[k], b[k], f"{path}.{k}".lstrip("."))
        elif isinstance(a, list):
            if len(a) != len(b):
                diffs.append(path)
            else:
                for i, (x, y) in enumerate(zip(a, b)):
                    walk(x, y, f"{path}[{i}]")
        elif a != b:
            diffs.append(path)

    walk(v1, rules)
    allowed = {"rules_version", "frozen_at", "change_log",
               f"signals[{idx['SG02']}].threshold", f"signals[{idx['SG02']}].note"}
    extra = sorted(set(diffs) - allowed)
    add("C15", "v1→v2 差异仅限 SG02 单位与版本元数据", not extra,
        {"diffs": sorted(set(diffs)), "unexpected": extra})


# ---------------------------------------------------------------- 合成测试

def _mk(rows, meta, sec, pk, fid, value, status="EXTRACTED", restate="", low="",
        scope="CONSOLIDATED", pre="NO", doc="DOC-A", ver="ORIGINAL", comp="", ptype="H1"):
    rows[(sec, pk)][fid] = {"value": value, "status": status, "low_base": low,
                            "restate": restate, "scope": scope, "pre_listing": pre,
                            "document_id": doc, "version_used": ver, "comparability": comp}
    y = pk // 10000
    if ptype == "H1":
        s, e = date(y, 1, 1), date(y, 6, 30)
    elif ptype == "Q3":
        s, e = date(y, 7, 1), date(y, 9, 30)
    else:
        s, e = date(y, 1, 1), date(y, 12, 31)
    meta[(sec, pk)][fid] = {"period_type": ptype, "period_start": s.isoformat(),
                            "period_end": e.isoformat()}


def _base(sec, pk=20260630, pkb=20250630, rev=(100e6, 90e6), gm=(20.0, 19.0),
          npdedt=(20e6, 15e6), npp=(20e6, 15e6), ocf=(20e6, 15e6), ar=(30e6, 28e6),
          inv=(20e6, 18e6), cost=(80e6, 73e6), ca=(0.0, 0.0), ta=(500e6, 480e6)):
    rows, meta = defaultdict(dict), defaultdict(dict)
    for i, pk_ in enumerate((pk, pkb)):
        _mk(rows, meta, sec, pk_, "FIN.REV.YTD", rev[i])
        _mk(rows, meta, sec, pk_, "FIN.COST.YTD", cost[i])
        _mk(rows, meta, sec, pk_, "FIN.GROSSMARGIN.PCT", gm[i])
        _mk(rows, meta, sec, pk_, "FIN.NPDEDT.YTD", npdedt[i])
        _mk(rows, meta, sec, pk_, "FIN.NPP.YTD", npp[i])
        _mk(rows, meta, sec, pk_, "FIN.OCF.YTD", ocf[i])
        _mk(rows, meta, sec, pk_, "FIN.AR.INSTANT", ar[i])
        _mk(rows, meta, sec, pk_, "FIN.INV.INSTANT", inv[i])
        _mk(rows, meta, sec, pk_, "FIN.CONTRACTASSET.INSTANT", ca[i])
        _mk(rows, meta, sec, pk_, "FIN.ASSET.INSTANT", ta[i])
    return rows, meta


def _sq(sec, accel_pp, a=0.10):
    """构造 M03 = accel_pp 的单季数据：本季同比 a，上季同比 a - accel/100。"""
    rows, meta = defaultdict(dict), defaultdict(dict)
    b = a - accel_pp / 100.0
    base = 100e6
    _mk(rows, meta, sec, 20260630, "FIN.REV.SQ", base * (1 + a))
    _mk(rows, meta, sec, 20250630, "FIN.REV.SQ", base)
    _mk(rows, meta, sec, 20260331, "FIN.REV.SQ", base * (1 + b))
    _mk(rows, meta, sec, 20250331, "FIN.REV.SQ", base)
    return rows, meta


def synthetic_tests(rules):
    load_signal_defs(rules)

    r, m = _base("T1", gm=(1.0, 0.0))
    x, _ = evaluate(r, m, "T1", 20260630)
    add_test("T1", "毛利率 0%→1% 应为 +1pp", "+1.0pp / OK",
             f"{x['M04']['value']} / {x['M04']['status']}",
             x["M04"]["status"] == "OK" and abs(x["M04"]["value"] - 1.0) < 1e-9)

    r, m = _base("T2", gm=(-2.0, -5.0))
    x, _ = evaluate(r, m, "T2", 20260630)
    add_test("T2", "负毛利率 −5%→−2% 应为 +3pp", "+3.0pp / OK",
             f"{x['M04']['value']} / {x['M04']['status']}",
             x["M04"]["status"] == "OK" and abs(x["M04"]["value"] - 3.0) < 1e-9)

    r, m = _base("T3", rev=(100e6, 0.0))
    x, _ = evaluate(r, m, "T3", 20260630)
    add_test("T3", "营收基期 0 → UNDEFINED_BASE + Q04", "UNDEFINED_BASE/Q04",
             f"{x['M01']['status']}/{sorted(x['M01']['flags'])}",
             x["M01"]["status"] == "UNDEFINED_BASE" and "Q04" in x["M01"]["flags"])

    r, m = _base("T4", npdedt=(5e6, -10e6))
    x, _ = evaluate(r, m, "T4", 20260630)
    add_test("T4", "扣非基期 −1,000 万 → UNDEFINED_BASE + Q03", "UNDEFINED_BASE/Q03",
             f"{x['M05']['status']}/{sorted(x['M05']['flags'])}",
             x["M05"]["status"] == "UNDEFINED_BASE" and "Q03" in x["M05"]["flags"])

    r, m = _base("T5", rev=(142.2e6, 100e6), gm=(20.0, 19.5))
    r[("T5", 20250630)]["FIN.REV.YTD"]["low_base"] = "LOW_BASE_REV"
    x, _ = evaluate(r, m, "T5", 20260630)
    g = [f for f in signals_of(r, "T5", 20260630, x) if f["id"] == "SG01"]
    add_test("T5", "低基数但增量 4,224 万 → SG01 确认", "confirmed=True/CONFIRMED_ABS",
             f"{g[0]['confirmed']}/{g[0]['confirm']}" if g else "no-fire",
             bool(g) and g[0]["confirmed"] and g[0]["confirm"] == "CONFIRMED_ABS")

    r, m = _base("T6", rev=(89e6, 80e6), gm=(20.0, 19.5))
    r[("T6", 20250630)]["FIN.REV.YTD"]["low_base"] = "LOW_BASE_REV"
    x, _ = evaluate(r, m, "T6", 20260630)
    g = [f for f in signals_of(r, "T6", 20260630, x) if f["id"] == "SG01"]
    add_test("T6", "低基数且增量 900 万 → 不确认", "confirmed=False/ABS_BELOW_THRESHOLD",
             f"{g[0]['confirmed']}/{g[0]['confirm']}" if g else "no-fire",
             bool(g) and not g[0]["confirmed"])

    r, m = _base("T7", rev=(120e6, 90e6), gm=(21.0, 19.0),
                 npdedt=(15e6, 15e6), npp=(15e6, 15e6), ocf=(15e6, 15e6))
    r[("T7", 20250630)]["FIN.REV.YTD"]["restate"] = RESTATE_PENDING
    x, _ = evaluate(r, m, "T7", 20260630)
    l1, l2, dims, _, _ = layers(signals_of(r, "T7", 20260630, x), x)
    add_test("T7", "Q06 信号进 L1 不进 L2", "L1=OBSERVE_QUEUE / L2=NOT_SHORTLISTED",
             f"L1={l1} / L2={l2} / dims={sorted(dims)}",
             l1 == "OBSERVE_QUEUE" and l2 == "NOT_SHORTLISTED")

    r, m = _base("T8", ocf=(5e6, 20e6))
    x, _ = evaluate(r, m, "T8", 20260630)
    fired = signals_of(r, "T8", 20260630, x)
    add_test("T8", "现金含量达标但现金流同比为负 → SG07 不触发", "no SG07",
             ",".join(f["id"] for f in fired), not any(f["id"] == "SG07" for f in fired))

    r, m = _base("T9", rev=(120e6, 90e6))
    r[("T9", 20250630)]["FIN.REV.YTD"]["restate"] = RESTATE_CONFIRMED
    r[("T9", 20250630)]["FIN.REV.YTD"]["comparability"] = "RESTATED_PRIOR_YEARS_UNRECALCULATED"
    x, _ = evaluate(r, m, "T9", 20260630)
    add_test("T9", "已确认重述未重算 → 标 Q06", "Q06 in flags",
             f"{x['M01']['status']}/{sorted(x['M01']['flags'])}", "Q06" in x["M01"]["flags"])

    r, m = _base("T10")
    r[("T10", 20260630)]["FIN.REV.YTD"]["pre_listing"] = "YES"
    x, _ = evaluate(r, m, "T10", 20260630)
    add_test("T10", "上市前输入 → NOT_COMPARABLE/Q08", "NOT_COMPARABLE/Q08",
             f"{x['M01']['status']}/{sorted(x['M01']['flags'])}",
             x["M01"]["status"] == "NOT_COMPARABLE" and "Q08" in x["M01"]["flags"])

    r, m = _base("T11")
    r[("T11", 20260630)]["FIN.REV.YTD"]["scope"] = "PARENT_ONLY"
    x, _ = evaluate(r, m, "T11", 20260630)
    add_test("T11", "母公司口径 → EXCLUDED_SCOPE/Q12", "EXCLUDED_SCOPE/Q12",
             f"{x['M01']['status']}/{sorted(x['M01']['flags'])}",
             x["M01"]["status"] == "EXCLUDED_SCOPE" and "Q12" in x["M01"]["flags"])

    r, m = _base("T12", ca=(40e6, 38e6))
    x, pm = evaluate(r, m, "T12", 20260630)
    add_test("T12", "合同资产占比>5% → 项目制，M11 不判", "NOT_APPLICABLE/Q10",
             f"pm={pm} {x['M11']['status']}/{sorted(x['M11']['flags'])}",
             pm and x["M11"]["status"] == "NOT_APPLICABLE" and "Q10" in x["M11"]["flags"])

    r, m = _base("T13")
    x, _ = evaluate(r, m, "T13", 20260630, stale=True)
    add_test("T13", "最新期落后 → 全指标标 Q11", "Q11 in flags",
             sorted(x["M01"]["flags"]), "Q11" in x["M01"]["flags"])

    r, m = _base("T14")
    del r[("T14", 20260630)]["FIN.GROSSMARGIN.PCT"]
    del r[("T14", 20250630)]["FIN.GROSSMARGIN.PCT"]
    r[("T14", 20260630)]["FIN.COST.YTD"]["document_id"] = "DOC-B"
    x, _ = evaluate(r, m, "T14", 20260630)
    add_test("T14", "回算毛利率 REV/COST 不同文档 → VERSION_MISMATCH", "VERSION_MISMATCH",
             x["M04"]["status"], x["M04"]["status"] == "VERSION_MISMATCH")

    r, m = _base("T15", npdedt=(12e6, -5e6), npp=(-3e6, -8e6))
    x, _ = evaluate(r, m, "T15", 20260630)
    fired = signals_of(r, "T15", 20260630, x)
    add_test("T15", "扣非由负转正且≥1,000 万 → SG06 触发", "SG06 fired",
             ",".join(f["id"] for f in fired), any(f["id"] == "SG06" for f in fired))

    r, m = _base("T16", rev=(150e6, 90e6), gm=(23.0, 19.0),
                 npdedt=(15e6, 15e6), npp=(15e6, 15e6), ocf=(15e6, 15e6))
    r[("T16", 20250630)]["FIN.REV.YTD"]["restate"] = RESTATE_CONFIRMED
    x, _ = evaluate(r, m, "T16", 20260630)
    l1, l2, dims, _, flip = layers(signals_of(r, "T16", 20260630, x), x)
    add_test("T16", "Q06 增长 + 干净毛利 → 只剩 1 维，不得进 L2", "NOT_SHORTLISTED/flip=1",
             f"L2={l2} / dims={sorted(dims)} / flip={flip}",
             l2 == "NOT_SHORTLISTED" and flip == 1)

    # T17 UNKNOWN 非旧快照 → EXCLUDED_SCOPE
    r, m = _base("T17")
    r[("T17", 20260630)]["FIN.REV.YTD"]["scope"] = "UNKNOWN"
    x, _ = evaluate(r, m, "T17", 20260630)
    add_test("T17", "UNKNOWN 非旧快照 → EXCLUDED_SCOPE/Q12", "EXCLUDED_SCOPE/Q12",
             f"{x['M01']['status']}/{sorted(x['M01']['flags'])}",
             x["M01"]["status"] == "EXCLUDED_SCOPE" and "Q12" in x["M01"]["flags"])

    # T17b UNKNOWN 旧快照 → 放行但记 Q07
    r, m = _base("T17b")
    for pk_ in (20260630, 20250630):
        r[("T17b", pk_)]["FIN.REV.YTD"]["scope"] = "UNKNOWN"
        r[("T17b", pk_)]["FIN.REV.YTD"]["status"] = "LEGACY_SNAPSHOT"
    x, _ = evaluate(r, m, "T17b", 20260630)
    add_test("T17b", "UNKNOWN 旧快照 → OK + Q07（单列例外）", "OK/Q07",
             f"{x['M01']['status']}/{sorted(x['M01']['flags'])}",
             x["M01"]["status"] == "OK" and "Q07" in x["M01"]["flags"])

    # T18 M08 干净、M09 带 Q06 → SG07 必须继承 Q06
    r, m = _base("T18", rev=(100e6, 95e6), gm=(20.0, 19.8),
                 npdedt=(15e6, 15e6), npp=(20e6, 20e6), ocf=(20e6, 5e6))
    r[("T18", 20250630)]["FIN.OCF.YTD"]["restate"] = RESTATE_CONFIRMED
    x, _ = evaluate(r, m, "T18", 20260630)
    fired = signals_of(r, "T18", 20260630, x)
    g = [f for f in fired if f["id"] == "SG07"]
    l1, l2, dims, _, _ = layers(fired, x)
    add_test("T18", "M08 干净但 M09 有 Q06 → SG07 继承 Q06、不进 L2", "Q06 in SG07 flags / L2 非 SHORTLIST",
             f"SG07 flags={sorted(g[0]['flags']) if g else 'no-fire'} / L2={l2}",
             bool(g) and "Q06" in g[0]["flags"] and l2 != "SHORTLIST_CANDIDATE")

    # T19 M08 原始输入带低基数 → Q05 且无绝对额确认
    r, m = _base("T19", rev=(100e6, 95e6), gm=(20.0, 19.8),
                 npdedt=(15e6, 15e6), npp=(20e6, 20e6), ocf=(20e6, 5e6))
    r[("T19", 20260630)]["FIN.OCF.YTD"]["low_base"] = "LOW_BASE_PROFIT"
    x, _ = evaluate(r, m, "T19", 20260630)
    g = [f for f in signals_of(r, "T19", 20260630, x) if f["id"] == "SG07"]
    add_test("T19", "M08 原始输入带低基数 → Q05 + NO_CONFIRM_INPUT", "Q05 / NO_CONFIRM_INPUT",
             f"{sorted(g[0]['flags'])} / {g[0]['confirm']}" if g else "no-fire",
             bool(g) and "Q05" in g[0]["flags"] and g[0]["confirm"] == "NO_CONFIRM_INPUT")

    # T20 SG02 单位：1pp 不触发，6pp 触发
    r, m = _sq("T20a", 1.0)
    x, _ = evaluate(r, m, "T20a", 20260630)
    fire_a = any(f["id"] == "SG02" for f in signals_of(r, "T20a", 20260630, x))
    r, m = _sq("T20b", 6.0)
    x, _ = evaluate(r, m, "T20b", 20260630)
    fire_b = any(f["id"] == "SG02" for f in signals_of(r, "T20b", 20260630, x))
    add_test("T20", "SG02 阈值 5pp：1pp 不触发、6pp 触发", "False / True",
             f"{fire_a} / {fire_b}", (not fire_a) and fire_b)


# ---------------------------------------------------------------- 主流程

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fill-fingerprint", action="store_true")
    args = ap.parse_args()

    rules = json.loads(RULES.read_text(encoding="utf-8"))
    if args.fill_fingerprint:
        for f in rules["input_fingerprint"]["files"]:
            p = ROOT / f["path"]
            f["sha256"] = sha256(p)
            f["bytes"] = p.stat().st_size
        RULES.write_text(json.dumps(rules, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    load_signal_defs(rules)

    rows, meta, field_rows, companies = load_rows()
    structural(rules, field_rows)

    fp_bad = [f["path"] for f in rules["input_fingerprint"]["files"]
              if not (ROOT / f["path"]).exists() or sha256(ROOT / f["path"]) != f["sha256"]]
    add("C12b", "输入指纹与当前文件一致", not fp_bad, {"changed": fp_bad})
    add("C13", "公司数与 S00 一致（1054）", len(companies) == 1054, {"companies": len(companies)})

    latest = {}
    for (sec, pk), fields in rows.items():
        if any(fields.get(f) and fields[f]["status"] in USABLE | USABLE_FLAG
               and fields[f]["value"] is not None
               for f in ("FIN.REV.YTD", "FIN.REV.SQ", "FIN.NPDEDT.YTD")):
            if sec not in latest or pk > latest[sec]:
                latest[sec] = pk
    add("D01", "每家可确定最新可用期或落 W1", len(latest) <= 1054,
        {"resolved": len(latest), "w1_no_data": 1054 - len(latest)})

    stale_cut = prior_quarter(max(latest.values()))

    cov = {m["id"]: Counter() for m in rules["metrics"]}
    values = defaultdict(list)
    l1 = Counter(); l2 = Counter()
    sig_hits = Counter(); dim_hits = Counter()
    viol = Counter()
    growth_union = 0

    for sec, pk in latest.items():
        res_map, _pm = evaluate(rows, meta, sec, pk, stale=pk < stale_cut)
        for mid, r in res_map.items():
            cov[mid][r["status"]] += 1
            for fl in r["flags"]:
                cov[mid][fl] += 1
            if r["status"] == "OK" and r["value"] is not None:
                values[mid].append(r["value"])
            if r["status"] == "OK" and "Q06" in r["flags"]:
                viol["ok_with_q06"] += 1
            if r["status"] == "OK" and "Q12" in r["flags"]:
                viol["ok_with_q12"] += 1

        fired = signals_of(rows, sec, pk, res_map)
        for f in fired:
            sig_hits[f["id"]] += 1
            dim_hits[f["dim"]] += 1
            if not signal_flags(f["id"], res_map) <= f["flags"]:
                viol["signal_flags_missing_dep"] += 1
            if "Q06" in signal_flags(f["id"], res_map):
                viol["q06_signal_fired"] += 1
            if "Q05" in signal_flags(f["id"], res_map):
                if f["confirmed"]:
                    viol["q05_confirmed"] += 1
                else:
                    viol["q05_unconfirmed"] += 1
                    if f["confirm"] == "NO_CONFIRM_INPUT":
                        viol["q05_no_confirm_input"] += 1
        y1, y2, dims, _ex, flip = layers(fired, res_map)
        l1[y1] += 1
        l2[y2] += 1
        viol["q06_dimension_flip"] += flip
        if y1 == "OBSERVE_QUEUE" and any(f["id"] in ("SG01", "SG02") for f in fired):
            growth_union += 1
        clean_dims = {f["dim"] for f in fired
                      if "Q06" not in signal_flags(f["id"], res_map) and f["confirmed"]}
        if y2 == "SHORTLIST_CANDIDATE" and len(clean_dims) < 2:
            viol["l2_without_two_clean_dims"] += 1

    total = len(latest)
    cov_rows = []
    for m in rules["metrics"]:
        c = cov[m["id"]]
        ok = c.get("OK", 0)
        cov_rows.append({
            "metric_id": m["id"], "metric_name_cn": m["name_cn"], "unit": m["unit"],
            "companies_total": total, "ok": ok,
            "provisional": c.get("PROVISIONAL", 0),
            "hold": c.get("HOLD", 0), "missing": c.get("MISSING", 0),
            "not_comparable": c.get("NOT_COMPARABLE", 0),
            "undefined_base": c.get("UNDEFINED_BASE", 0),
            "not_applicable": c.get("NOT_APPLICABLE", 0),
            "excluded_scope": c.get("EXCLUDED_SCOPE", 0),
            "version_mismatch": c.get("VERSION_MISMATCH", 0),
            "flag_q05_low_base": c.get("Q05", 0),
            "flag_q06_restatement": c.get("Q06", 0),
            "flag_q07_legacy": c.get("Q07", 0),
            "flag_q09_one_off": c.get("Q09", 0),
            "flag_q10_project": c.get("Q10", 0),
            "flag_q11_stale": c.get("Q11", 0),
            "ok_share": round(ok / total, 4) if total else 0,
        })
    add("D02", "每条指标都有可计算样本（OK>0）", all(r["ok"] > 0 for r in cov_rows),
        {r["metric_id"]: r["ok"] for r in cov_rows})

    synthetic_tests(rules)
    test_fail = [t for t in tests if t["result"] == "FAIL"]
    add("D03", f"合成政策测试 {len(tests)} 项全部通过", not test_fail, {"fail": test_fail})

    add("D04", "L2 只由干净（无 Q06）且已确认的维度支撑",
        viol["l2_without_two_clean_dims"] == 0,
        {"q06_signal_fired": viol["q06_signal_fired"],
         "q06_dimension_flip": viol["q06_dimension_flip"],
         "l2_without_two_clean_dims": viol["l2_without_two_clean_dims"]})
    add("D05", "Q05 信号按绝对额确认处理",
        viol["q05_confirmed"] + viol["q05_unconfirmed"] > 0,
        {"confirmed": viol["q05_confirmed"], "unconfirmed": viol["q05_unconfirmed"],
         "no_confirm_input": viol["q05_no_confirm_input"]})
    add("D06", "已确认/未决重述输入不返回普通 OK", viol["ok_with_q06"] == 0,
        {"ok_with_q06": viol["ok_with_q06"]})
    add("D07", "非合并口径（含 UNKNOWN 非旧快照）不返回普通 OK", viol["ok_with_q12"] == 0,
        {"ok_with_q12": viol["ok_with_q12"]})
    add("D08", "L1/L2 分层可执行（计数仅干跑，不作为结果）",
        sum(l1.values()) == total and sum(l2.values()) == total,
        {"L1": dict(l1), "L2": dict(l2), "note": "NOT_A_RESULT"})

    S01.mkdir(parents=True, exist_ok=True)
    out = S01 / "metric_coverage_dryrun.csv"
    with out.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(cov_rows[0].keys()), lineterminator="\n")
        w.writeheader()
        w.writerows(cov_rows)
    add("D10", "信号对象携带全部依赖指标的质量标记", viol["signal_flags_missing_dep"] == 0,
        {"signal_flags_missing_dep": viol["signal_flags_missing_dep"]})
    add("D09", "覆盖表不含公司标识列",
        not [c for c in cov_rows[0] if c in ("security_id", "stock_code", "stock_name")],
        {"columns": list(cov_rows[0].keys())})

    quant = {}
    for mid, vals in values.items():
        vals.sort(); n = len(vals)
        quant[mid] = {"n": n, **{f"p{q}": round(vals[int(n * q / 100)], 6) for q in (10, 25, 50, 75, 90)}}

    blocking_fail = [c for c in checks if c["result"] == "FAIL" and c["blocking"]]
    result = {
        "issue_key": "S01", "issue_number": 36,
        "rules_version": rules["rules_version"],
        "rules_file": "runs/issues/S01/screen_rules_v2.json",
        "rules_sha256": sha256(RULES),
        "rules_v1_sha256": sha256(RULES_V1),
        "checked_at": datetime.now(CST).isoformat(timespec="seconds"),
        "implementation_revision": "R3_AFTER_CODEX_ASSESSMENT_522e1cd",
        "checks_total": len(checks),
        "checks_pass": sum(1 for c in checks if c["result"] == "PASS"),
        "checks_fail": sum(1 for c in checks if c["result"] == "FAIL"),
        "blocking_fail": len(blocking_fail),
        "checks": checks,
        "synthetic_tests": tests,
        "policy_violations": {k: viol.get(k, 0) for k in [
            "ok_with_q06", "ok_with_q12", "l2_without_two_clean_dims",
            "signal_flags_missing_dep", "q06_signal_fired", "q06_dimension_flip",
            "q05_confirmed", "q05_unconfirmed", "q05_no_confirm_input"]},
        "dryrun": {
            "label": "ANONYMOUS_DRYRUN_NOT_A_RESULT",
            "companies": total,
            "latest_period_distribution": dict(sorted(Counter(str(v) for v in latest.values()).items())),
            "metric_coverage": {r["metric_id"]: r for r in cov_rows},
            "signal_hits": dict(sig_hits), "dimension_hits": dict(dim_hits),
            "L1_counts": dict(l1), "L2_counts": dict(l2),
            "breadth_observation": {
                "L1_observe_share": round(l1["OBSERVE_QUEUE"] / total, 4) if total else 0,
                "growth_signal_union": growth_union,
                "growth_signal_union_share": round(growth_union / total, 4) if total else 0,
                "L2_shortlist_share": round(l2["SHORTLIST_CANDIDATE"] / total, 4) if total else 0,
                "interpretation": "v1 阈值偏松属已声明限制；本次只修实现与 SG02 单位，未按命中率调阈值。"
            },
            "quantiles_exploratory": quant,
            "note": "只做可执行性验证与匿名分布描述，不产出名单。"
        },
    }
    (S01 / "self_check.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({
        "checks": f"{result['checks_pass']}/{result['checks_total']} PASS",
        "tests": f"{len(tests) - len(test_fail)}/{len(tests)} PASS",
        "blocking_fail": result["blocking_fail"],
        "policy_violations": result["policy_violations"],
        "signal_hits": dict(sig_hits),
        "L1": dict(l1), "L2": dict(l2),
    }, ensure_ascii=False, indent=2))
    for c in blocking_fail:
        print(f"FAIL {c['id']} {c['item']}: {c['detail']}", file=sys.stderr)
    for t in test_fail:
        print(f"TEST FAIL {t['id']} {t['name']}: expected {t['expected']} got {t['actual']}", file=sys.stderr)
    return 1 if blocking_fail or test_fail else 0


if __name__ == "__main__":
    sys.exit(main())
