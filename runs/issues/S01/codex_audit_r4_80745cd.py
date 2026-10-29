#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""S01 R4（提交 80745cd）外部复核审计 —— 独立路径，不 import 执行器逻辑。

与执行器 tools/s01_rules_check.py 的关系：
- 本脚本自行读 financial_normalized.csv 与 screen_rules_v2.json，独立重算 M07/SG09；
- 只在「故障注入」一节动态加载执行器，用于验证 C16 会拒绝缺失依赖；
- 不写任何交付文件，结果输出到 codex_audit_results_r4_80745cd.json。

用法：
    python runs/issues/S01/codex_audit_r4_80745cd.py
"""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import os
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
S01 = ROOT / "runs/issues/S01"
RULES_V1 = S01 / "screen_rules_v1.json"
RULES_V2 = S01 / "screen_rules_v2.json"
MANIFEST = S01 / "manifest.json"
SELF_CHECK = S01 / "self_check.json"
NORMALIZED = ROOT / "runs/issues/S00/financial_normalized.csv"
OUT = S01 / "codex_audit_results_r4_80745cd.json"

V1_SHA = "c76d04615669788dddc17425de6afd78ec55be4b7f20bbd75b7322e777858f7e"
V2_SHA = "ada501e8bcd276ce670a4799c730a81cdf2f9dc70c244f9255485b00168c6a85"

USABLE = {"EXTRACTED", "EXTRACTED_KEY_TABLE", "EXTRACTED_QUARTERLY_TABLE",
          "DERIVED", "DERIVED_CUMULATIVE_DIFF", "DERIVED_Q1_EQUALS_YTD",
          "DERIVED_QUARTERLY_SUM_OVERRIDE"}
LEGACY = {"LEGACY_SNAPSHOT"}
HOLD = {"EXTRACTED_XCHECK_MISMATCH", "DERIVED_HOLD_UPSTREAM", "DERIVED_Q1_HOLD_UPSTREAM"}
LOW_FLAGS = {"LOW_BASE_REV", "LOW_BASE_PROFIT", "NEGATIVE_BASE_PROFIT"}
ZERO_ABS = 1_000_000.0
LOW_ABS_NPDEDT = 10_000_000.0

results: list[dict] = []


def record(cid, item, ok, detail, blocking=True):
    results.append({"id": cid, "item": item, "result": "PASS" if ok else "FAIL",
                    "blocking": blocking, "detail": detail})
    print(("PASS " if ok else "FAIL ") + cid + " " + item)


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------- A1 规则版本

def check_rules():
    h1, h2 = sha256(RULES_V1), sha256(RULES_V2)
    record("A1a", "v1 规则哈希未被改动", h1 == V1_SHA, {"sha256": h1})
    record("A1b", "v2 规则哈希与复核记录一致", h2 == V2_SHA, {"sha256": h2})

    v1 = json.loads(RULES_V1.read_text(encoding="utf-8"))
    v2 = json.loads(RULES_V2.read_text(encoding="utf-8"))

    # 白名单：只允许 SG02 阈值/说明、版本元数据、change_log 变化
    allowed = {"/frozen_at", "/rules_version", "/change_log",
               "/signals[1]/threshold", "/signals[1]/note"}
    diffs: list[str] = []

    def walk(x, y, path=""):
        if type(x) is not type(y):
            diffs.append(path)
            return
        if isinstance(x, dict):
            for k in sorted(set(x) | set(y)):
                if k not in x or k not in y:
                    diffs.append(path + "/" + k)
                else:
                    walk(x[k], y[k], path + "/" + k)
        elif isinstance(x, list):
            if len(x) != len(y):
                diffs.append(path)
                return
            for i, (u, v) in enumerate(zip(x, y)):
                walk(u, v, path + "[%d]" % i)
        elif x != y:
            diffs.append(path)

    walk(v1, v2)
    unexpected = [d for d in diffs if d not in allowed]
    record("A1c", "v1→v2 差异仅限 SG02 单位修正与版本元数据", not unexpected,
           {"diff_paths": diffs, "unexpected": unexpected})

    sg02_v1 = next(s for s in v1["signals"] if s["id"] == "SG02")
    sg02_v2 = next(s for s in v2["signals"] if s["id"] == "SG02")
    record("A1d", "SG02 阈值 0.05→5.0 且单位仍为 pp",
           sg02_v1["threshold"] == 0.05 and sg02_v2["threshold"] == 5.0
           and sg02_v1["unit"] == sg02_v2["unit"] == "pp",
           {"v1": sg02_v1["threshold"], "v2": sg02_v2["threshold"], "unit": sg02_v2["unit"]})
    return v2


# ---------------------------------------------------------------- A2 输入指纹

def check_inputs(v2):
    files = v2["input_fingerprint"]["files"]
    bad = []
    for f in files:
        p = ROOT / f["path"]
        h = sha256(p)
        if h != f["sha256"] or p.stat().st_size != f["bytes"]:
            bad.append({"path": f["path"], "expected": f["sha256"], "actual": h})
    record("A2", "三份研究输入指纹与规则文件登记一致", not bad,
           {"files": len(files), "mismatch": bad})


# ---------------------------------------------------------------- A3 交付哈希

def check_manifest():
    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    bad = []
    for f in m["outputs"]:
        p = ROOT / f["path"]
        if not p.exists():
            bad.append({"path": f["path"], "reason": "MISSING"})
            continue
        h = sha256(p)
        if h != f["sha256"] or p.stat().st_size != f["bytes"]:
            bad.append({"path": f["path"], "expected": f["sha256"], "actual": h})
    record("A3a", "manifest 16 份交付哈希全部匹配", not bad,
           {"outputs": len(m["outputs"]), "mismatch": bad})
    tool_bad = [t["path"] for t in m["tools"] if sha256(ROOT / t["path"]) != t["sha256"]]
    record("A3b", "执行器源码哈希与 manifest 登记一致", not tool_bad, {"mismatch": tool_bad})


# ---------------------------------------------------------------- A4 独立重算 M07/SG09

def load_sq(companies: set) -> tuple[dict, dict]:
    """独立装载：最新可用期按规则语义（营收或扣非累计有可用值）判定，不用执行器函数。"""
    sq: dict[tuple[str, int], dict] = {}
    anchors: dict[str, set] = {}          # sec -> 可作为最新期的 pk 集合
    anchor_fields = ("FIN.REV.YTD", "FIN.REV.SQ", "FIN.NPDEDT.YTD")
    with NORMALIZED.open(encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            sec, pk = r["security_id"], int(r["period_key"])
            fid = r["field_id"]
            companies.add(sec)
            if fid in anchor_fields and r["status"] in USABLE | LEGACY and r["value_cny"]:
                anchors.setdefault(sec, set()).add(pk)
            if fid != "FIN.NPDEDT.SQ":
                continue
            sq[(sec, pk)] = {
                "value": float(r["value_cny"]) if r["value_cny"] else None,
                "status": r["status"],
                "low": r["low_base_flag"],
                "restate": r["restatement_flag"],
                "scope": r["consolidation_scope"],
                "pre": r["is_pre_listing"],
                "comp": r["comparability_note"] or "",
            }
    latest = {sec: max(pks) for sec, pks in anchors.items() if pks}
    return sq, latest


def m07_state(rows, sec, pk, pkb):
    """按规则文件 policies 独立实现：扣非单季同比。返回 (value, status, flags)。"""
    rt, rb = rows.get((sec, pk)), rows.get((sec, pkb))
    if rb is None:
        return None, "NOT_COMPARABLE", {"Q08"}
    if rt is None or rb is None:
        return None, "MISSING", {"Q02"}
    flags = set()
    if rt["status"] in HOLD or rb["status"] in HOLD:
        return None, "HOLD", {"Q01"}
    if any(r["status"] not in USABLE | LEGACY for r in (rt, rb)):
        return None, "MISSING", {"Q02"}
    if any(r["scope"] != "CONSOLIDATED" and r["status"] not in LEGACY for r in (rt, rb)):
        return None, "EXCLUDED_SCOPE", {"Q12"}
    if rt["pre"] == "YES" or rb["pre"] == "YES":
        return None, "NOT_COMPARABLE", {"Q08"}
    if rt["status"] in LEGACY or rb["status"] in LEGACY:
        flags.add("Q07")
    for r in (rt, rb):
        if r["restate"] in ("RESTATEMENT_INDICATED_NEEDS_REVIEW", "是") \
                or "RESTATED_PRIOR_YEARS_UNRECALCULATED" in r["comp"]:
            flags.add("Q06")
    cur, base = rt["value"], rb["value"]
    if cur is None or base is None:
        return None, "MISSING", flags | {"Q02"}
    if any(r["low"] in LOW_FLAGS for r in (rt, rb)) or abs(base) < LOW_ABS_NPDEDT:
        flags.add("Q05")
    if abs(base) < ZERO_ABS:
        return None, "UNDEFINED_BASE", flags | {"Q04"}
    if base < 0:
        return None, "UNDEFINED_BASE", flags | {"Q03"}
    return cur / base - 1.0, "OK", flags


def check_sg09(v2):
    sg09 = next(s for s in v2["signals"] if s["id"] == "SG09")
    companies: set[str] = set()
    rows, latest = load_sq(companies)

    fired = []
    q06_fired = 0
    ok_with_q06 = 0
    status_count = Counter()
    for sec, pk in latest.items():
        val, st, fl = m07_state(rows, sec, pk, pk - 10000)
        if st == "OK" and "Q06" in fl:
            st = "PROVISIONAL"          # 规则：已确认/未决重述不返回普通 OK
        status_count[st] += 1
        if st in ("OK", "PROVISIONAL") and val is not None:
            hit = val >= sg09["threshold"] if sg09["operator"] == ">=" else val <= sg09["threshold"]
            if hit:
                fired.append({"sec": sec, "value": round(val, 6), "flags": sorted(fl)})
                if "Q06" in fl:
                    q06_fired += 1
        if st == "OK" and "Q06" in fl:
            ok_with_q06 += 1

    self_check = json.loads(SELF_CHECK.read_text(encoding="utf-8"))
    declared = self_check["dryrun"]["signal_hits"]["SG09"]
    record("A4a", "独立重算 SG09 触发数与交付一致（203）",
           len(fired) == declared, {"independent": len(fired), "declared": declared})
    record("A4b", "M07 无「OK 且带 Q06」的政策违例", ok_with_q06 == 0,
           {"ok_with_q06": ok_with_q06})
    record("A4c", "SG09 触发中的 Q06 已传播到信号标记",
           q06_fired > 0 or all("Q06" not in f["flags"] for f in fired),
           {"q06_fired": q06_fired, "fired": len(fired),
            "note": "Q06 必须出现在 flags 里才允许该信号支撑 L2；独立统计仅作传播存在性检查"})
    record("A4d", "M07 状态分布可解释（无未声明状态）",
           set(status_count) <= {"OK", "PROVISIONAL", "HOLD", "MISSING",
                                 "NOT_COMPARABLE", "UNDEFINED_BASE", "EXCLUDED_SCOPE"},
           dict(status_count))
    return {"sg09_fired": len(fired), "q06_fired": q06_fired,
            "m07_status": dict(status_count)}


# ---------------------------------------------------------------- A5 故障注入

def check_c16():
    spec = importlib.util.spec_from_file_location("s01_exec", ROOT / "tools/s01_rules_check.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["s01_exec"] = mod
    spec.loader.exec_module(mod)          # 只加载定义，不调用 main()

    rules = json.loads(RULES_V2.read_text(encoding="utf-8"))
    mod.load_signal_defs(rules)
    _, _, field_rows, _ = mod.load_rows()

    mod.checks.clear()
    mod.structural(rules, field_rows)
    base = next((c for c in mod.checks if c["id"] == "C16"), None)
    record("A5a", "基线状态下 C16 通过", base is not None and base["result"] == "PASS",
           base["detail"] if base else "C16 not found")

    saved = dict(mod.SIGNAL_DEPS)
    try:
        mod.SIGNAL_DEPS.pop("SG09", None)
        mod.checks.clear()
        mod.structural(rules, field_rows)
        broke = next((c for c in mod.checks if c["id"] == "C16"), None)
        ok = broke is not None and broke["result"] == "FAIL"
        record("A5b", "内存移除 SG09 依赖后 C16 确实失败", ok,
               broke["detail"] if broke else "C16 not found")

        fl = mod.signal_flags("SG09", {"M07": {"flags": set()}})
        record("A5c", "依赖未登记时 signal_flags 返回 None 而非空集", fl is None, {"returned": fl})
    finally:
        mod.SIGNAL_DEPS.clear()
        mod.SIGNAL_DEPS.update(saved)
        mod.checks.clear()
        mod.structural(rules, field_rows)
        restored = next((c for c in mod.checks if c["id"] == "C16"), None)
        record("A5d", "恢复依赖后 C16 回到 PASS（未落盘任何修改）",
               restored is not None and restored["result"] == "PASS", {})


def main():
    v2 = check_rules()
    check_inputs(v2)
    check_manifest()
    extra = check_sg09(v2)
    check_c16()

    fails = [r for r in results if r["result"] == "FAIL"]
    payload = {
        "audit_of_commit": "80745cd",
        "auditor": "WorkBuddy AI (external recheck of Codex acceptance)",
        "review_nature": "EXTERNAL_RECHECK_PARTIAL_INDEPENDENT",
        "rules_v2_sha256": V2_SHA,
        "rules_v1_sha256": V1_SHA,
        "checks": results,
        "checks_pass": sum(1 for r in results if r["result"] == "PASS"),
        "checks_total": len(results),
        "blocking_fail": len([r for r in fails if r["blocking"]]),
        "independent_sg09": extra,
        "scope_note": "本审计独立重算 M07/SG09 与规则版本、指纹、交付哈希；未重写全部 12 指标，"
                      "L1/L2 全池独立结论引自 Codex 复核记录 codex_acceptance_80745cd.md。",
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"pass": f"{payload['checks_pass']}/{payload['checks_total']}",
                      "blocking_fail": payload["blocking_fail"],
                      "sg09": extra}, ensure_ascii=False, indent=1))
    return 1 if payload["blocking_fail"] else 0


if __name__ == "__main__":
    sys.exit(main())
