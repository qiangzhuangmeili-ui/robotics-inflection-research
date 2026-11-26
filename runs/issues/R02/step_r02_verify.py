#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R02 / #46 独立校验（完全离线，不信任构建器布尔值）。

校验内容
--------
V01 3 主题对 R00 主线 277 / 全池 1,054 互斥且完备，并与分派表逐项一致
V02 LAYER_2 严格按 H1/9M 分层，无跨期合并
V03 LAYER_1 披露日 <= 2026-10-25、全部 FACT、每个指标至少两期
V04 LAYER_2 中位数/四分位/改善占比/去 Top1 与原始 all_pool_metrics.csv 独立重算 0 差异
V05 全部输入位于 Git 工作树内、无越界路径
V06 manifest 输入/交付哈希与根摘要逐份一致
V07 全部交付物纯 LF
V08 review.json 的 decision 由 anomalies 动态推导且与实测一致
V09 分派表结构画像（锚定/TIER/申万 Top3）逐项重算一致
V10 未编造细分价格或机器人行业增加值，UNKNOWN 保留
V11 官方快照完整性（9 页 / 披露日 / 原文引文 / 哈希）
V12 逐字节复现：固定 R02_FIXED_NOW 连续两次构建，交付物 SHA-256 完全一致

用法
----
    R02_FIXED_NOW=2026-11-26T15:00:00+08:00 py runs/issues/R02/step_r02_verify.py
    py runs/issues/R02/step_r02_verify.py --negative-test    # 活体篡改测试
    py runs/issues/R02/step_r02_verify.py --root <临时树>     # 校验副本
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
TZ = timezone(timedelta(hours=8))
NOW = os.environ.get("R02_FIXED_NOW") or "2026-11-26T15:00:00+08:00"
CUTOFF = "2026-10-25"

INPUTS = [
    "runs/issues/R02/release_20261126.json",
    "runs/issues/R02/handoff_from_s08_20261126.md",
    "runs/issues/R02/nbs_official_sources_snapshot.json",
    "data/company_master.csv",
    "data/group_summary.csv",
    "runs/issues/S08/acceptance_s08_20261126.json",
    "runs/issues/S08/business_verification_candidates.csv",
    "runs/issues/S08/screen_acceptance.json",
    "runs/issues/S02/hangcha_restated_20261101/s02_v10/all_pool_metrics.csv",
    "runs/issues/S05/quality_flags.csv",
    "runs/issues/S05/quality_decision_log.csv",
]

DELIVERABLES = ["industry_topic_dispatch.csv", "industry_signals.csv", "industry_limits.md", "handoff.md"]
SCRIPTS = ["step_r02_build.py", "step_r02_verify.py", "collect_nbs_snapshot.py"]
MANIFEST_DELIVERABLES = DELIVERABLES + SCRIPTS

TOPIC_GROUPS = {
    "R02_T01": ["G01", "G02", "G03", "G04"],
    "R02_T02": ["G05", "G06"],
    "R02_T03": ["G07", "G08", "G09", "G10"],
}
ISSUE_NO = {"R02_T01": 54, "R02_T02": 55, "R02_T03": 56}
L2_METRICS = {"M01": "ratio", "M04": "pp", "M05": "ratio", "M06": "pp"}
PERIOD_PAIRS = {("20260630", "20250630", "H1"), ("20260930", "20250930", "9M")}
STD_MUST = [
    "申万行业分类 != NBS", "routing_group", "PPI != 企业产品实际售价",
    "行业产量/大盘景气 != 单一公司机器人真实收入", "H1（20260630）与 9M（20260930）严格分层",
    "扣非净利润 != 归母净利润 != NBS 工业利润", "基期 <= 0", "幸存者偏差", "UNKNOWN",
]


# ------------------------------------------------------------ 独立实现

def rd_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def rd_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def exact_sha(path):
    b = path.read_bytes()
    return len(b), hashlib.sha256(b).hexdigest()


def canon_sha(path):
    b = path.read_bytes().replace(b"\r\n", b"\n")
    return len(b), hashlib.sha256(b).hexdigest()


def quantile(values, q):
    """独立实现：类型 7 线性插值。"""
    vs = sorted(values)
    n = len(vs)
    if n == 0:
        return None
    pos = (n - 1) * q
    left = int(pos)
    right = min(left + 1, n - 1)
    if left == right:
        return vs[left]
    return vs[left] + (pos - left) * (vs[right] - vs[left])


def summarize(triples):
    """triples: [(sid, name, value)] -> 期望的 CSV 字符串字段。"""
    if not triples:
        return {
            "valid_paired_count": "0", "improved_count": "0", "improved_share_pct": "UNKNOWN",
            "median_value": "UNKNOWN", "p25_value": "UNKNOWN", "p75_value": "UNKNOWN",
            "top1_contributor_id": "", "top1_contributor_name": "", "top1_contributor_value": "UNKNOWN",
            "ex_top1_improved_share_pct": "UNKNOWN", "ex_top1_median_value": "UNKNOWN",
        }
    vals = [t[2] for t in triples]
    up = [v for v in vals if v > 0]
    ordered = sorted(triples, key=lambda t: (-t[2], t[0]))
    top = ordered[0]
    rest = [t[2] for t in triples if t[0] != top[0]]
    rest_up = [v for v in rest if v > 0]
    return {
        "valid_paired_count": str(len(vals)),
        "improved_count": str(len(up)),
        "improved_share_pct": "%.2f" % (100.0 * len(up) / len(vals)),
        "median_value": "%.6f" % quantile(vals, 0.5),
        "p25_value": "%.6f" % quantile(vals, 0.25),
        "p75_value": "%.6f" % quantile(vals, 0.75),
        "top1_contributor_id": top[0],
        "top1_contributor_name": top[1],
        "top1_contributor_value": "%.6f" % top[2],
        "ex_top1_improved_share_pct": ("%.2f" % (100.0 * len(rest_up) / len(rest))) if rest else "UNKNOWN",
        "ex_top1_median_value": ("%.6f" % quantile(rest, 0.5)) if rest else "UNKNOWN",
    }


# ------------------------------------------------------------ 载入

class Ctx:
    def __init__(self, root: Path):
        self.root = root
        self.master = {r["security_id"]: r for r in rd_csv(root / "data/company_master.csv")}
        self.cand = {r["security_id"]: r for r in rd_csv(root / "runs/issues/S08/business_verification_candidates.csv")}
        self.screen = rd_json(root / "runs/issues/S08/screen_acceptance.json")
        self.accept = rd_json(root / "runs/issues/S08/acceptance_s08_20261126.json")
        self.release = rd_json(root / "runs/issues/R02/release_20261126.json")
        self.snap = rd_json(root / "runs/issues/R02/nbs_official_sources_snapshot.json")
        self.rows = rd_csv(root / "runs/issues/S02/hangcha_restated_20261101/s02_v10/all_pool_metrics.csv")
        self.dispatch = rd_csv(root / "runs/issues/R02/industry_topic_dispatch.csv")
        self.signals = rd_csv(root / "runs/issues/R02/industry_signals.csv")
        self.review = rd_json(root / "runs/issues/R02/review.json")
        self.manifest = rd_json(root / "runs/issues/R02/manifest.json")
        self.idx = {}
        for r in self.rows:
            self.idx[(r["security_id"], r["metric_id"], r["period_key"], r["period_type"])] = r
        self.mainline = {s for s, r in self.cand.items() if r["final_queue"] == "R00_MAINLINE_VERIFY"}
        self.universe = set(self.master)

    def topic_members(self, topic):
        gs = set(TOPIC_GROUPS[topic])
        return [s for s in self.master if self.master[s]["routing_group"] in gs]

    def group(self, topic, denom):
        members = self.topic_members(topic)
        if denom == "R00_MAINLINE":
            return [s for s in members if s in self.mainline]
        if denom == "UNIVERSE_ALL":
            return members
        if denom.startswith("SW_L2:"):
            sw = denom.split(":", 1)[1]
            return [s for s in members if self.master[s]["sw_l2"] == sw]
        raise KeyError(denom)

    def pairs(self, members, mid, period, ptype):
        out = []
        for s in members:
            r = self.idx.get((s, mid, period, ptype))
            if not r or r["metric_status"] != "OK":
                continue
            try:
                out.append((s, self.master[s]["stock_name"], float(r["value"])))
            except ValueError:
                continue
        return out


def fmt_unit(v, unit):
    if v is None:
        return "UNKNOWN"
    if unit == "套":
        return str(int(round(v)))
    if unit in ("%", "index", "pp"):
        return "%.1f" % v
    if abs(v - round(v)) < 1e-12:
        return str(int(round(v)))
    return ("%.6f" % v).rstrip("0").rstrip(".")


def tracked(root: Path, rel: str):
    try:
        p = subprocess.run(["git", "ls-files", "--error-unmatch", rel], cwd=str(root),
                           capture_output=True, text=True)
        return p.returncode == 0
    except Exception:
        return None


# ------------------------------------------------------------ 校验主体

def run_checks(ctx: Ctx):
    checks = []
    bad = []

    def add(cid, name, ok, detail):
        checks.append({"id": cid, "name": name, "result": "PASS" if ok else "FAIL", "detail": detail})
        if not ok:
            bad.append("%s %s: %s" % (cid, name, detail))

    # V01 主题分拆
    counts = {t: len(ctx.topic_members(t)) for t in TOPIC_GROUPS}
    mains = {t: len([s for s in ctx.topic_members(t) if s in ctx.mainline]) for t in TOPIC_GROUPS}
    seen = set()
    dup = 0
    for t in TOPIC_GROUPS:
        s = set(ctx.topic_members(t))
        dup += len(seen & s)
        seen |= s
    dmap = {r["topic_id"]: r for r in ctx.dispatch}
    disp_ok = all(dmap[t]["universe_count"] == str(counts[t]) and dmap[t]["r00_mainline_count"] == str(mains[t])
                  for t in TOPIC_GROUPS)
    add("V01", "3 主题对 277/1,054 互斥完备且与分派表一致",
        sum(counts.values()) == 1054 and sum(mains.values()) == 277 and dup == 0 and disp_ok and len(ctx.dispatch) == 3,
        "universe=%s mainline=%s dup=%d dispatch_rows=%d" % (counts, mains, dup, len(ctx.dispatch)))

    # V02 期别隔离
    l2 = [r for r in ctx.signals if r["signal_layer"] == "LAYER_2_POOL_SAME_PERIOD_BENCHMARK"]
    badp = [r["signal_id"] for r in l2 if (r["period_key"], r["base_period_key"]) not in
            {(p, b) for p, b, _ in PERIOD_PAIRS}]
    combo = Counter((r["topic_id"], r["denominator"], r["metric_id"]) for r in l2)
    add("V02", "LAYER_2 严格 H1/9M 分层，无跨期合并",
        not badp and len(combo) == 60 and set(combo.values()) == {2},
        "rows=%d groups=%d bad=%d period_sets=%s" % (len(l2), len(combo), len(badp), sorted(set(combo.values()))))

    # V03 LAYER_1 事实性
    l1 = [r for r in ctx.signals if r["signal_layer"] == "LAYER_1_NBS_OFFICIAL_MACRO"]
    late = [r["signal_id"] for r in l1 if r["disclosure_date"] > CUTOFF]
    notfact = [r["signal_id"] for r in l1 if r["fact_or_forecast"] != "FACT"]
    per_metric = Counter(r["metric_id"] for r in l1)
    # 与快照交叉核对
    snap_rows = {}
    for s in ctx.snap["sources"]:
        for m in s["parsed_metrics"]:
            snap_rows[(m["metric_key"], m["period_key"])] = (s["disclosure_date"], m)
    csv_keys = {(r["metric_id"], r["period_key"]) for r in l1}
    missing = sorted(k for k in snap_rows if k not in csv_keys)
    extra = sorted(k for k in csv_keys if k not in snap_rows)
    val_bad = []
    for r in l1:
        key = (r["metric_id"], r["period_key"])
        if key not in snap_rows:
            continue
        d, m = snap_rows[key]
        exp_mom = "%.1f" % m["mom_change_pp"] if m["mom_change_pp"] is not None else "UNKNOWN"
        if (r["value"] != fmt_unit(m["value"], m["unit"])
                or r["yoy_pct"] != fmt_unit(m["yoy_pct"], m["unit"])
                or r["mom_change_pp"] != exp_mom
                or r["disclosure_date"] != d
                or r["unit"] != m["unit"]):
            val_bad.append(r["signal_id"])
    add("V03", "LAYER_1 披露日/FACT/期数/原值/单位与快照一一对应",
        not late and not notfact and (not per_metric or min(per_metric.values()) >= 2)
        and not missing and not extra and not val_bad,
        "rows=%d metrics=%d late=%d notfact=%d missing=%d extra=%d val_bad=%d" % (
            len(l1), len(per_metric), len(late), len(notfact), len(missing), len(extra), len(val_bad)))

    # V04 LAYER_2 独立重算
    diffs = []
    for r in l2:
        members = ctx.group(r["topic_id"], r["denominator"])
        ptype = "H1" if r["period_key"] == "20260630" else "9M"
        exp = summarize(ctx.pairs(members, r["metric_id"], r["period_key"], ptype))
        exp["denominator_count"] = str(len(members))
        for k, v in exp.items():
            if r[k] != v:
                diffs.append("%s:%s(%s!=%s)" % (r["signal_id"], k, r[k], v))
        if r["denominator_count"] != str(len(members)):
            diffs.append("%s:denominator_count" % r["signal_id"])
        if r["unit"] != L2_METRICS[r["metric_id"]]:
            diffs.append("%s:unit" % r["signal_id"])
    add("V04", "LAYER_2 统计量与原始指标独立重算 0 差异",
        not diffs, "rows=%d diffs=%d %s" % (len(l2), len(diffs), diffs[:3]))

    # V05 输入位置
    miss = [p for p in INPUTS if not (ctx.root / p).exists()]
    esc = [p for p in INPUTS if p.startswith("/") or ".." in Path(p).parts]
    trk = {p: tracked(ctx.root, p) for p in INPUTS}
    pending = [p for p, v in trk.items() if v is False]
    add("V05", "输入存在且位于仓库工作树内，无越界路径",
        not miss and not esc, "inputs=%d missing=%d escaped=%d pending_first_commit=%d" % (
            len(INPUTS), len(miss), len(esc), len(pending)))

    # V06 manifest
    m = ctx.manifest
    root = ctx.root
    inp_bad, deliv_bad = [], []
    for d in m["inputs"]:
        n, s = canon_sha(root / d["path"])
        if n != d["bytes"] or s != d["sha256"]:
            inp_bad.append(d["path"])
    for d in m["deliverables"]:
        n, s = exact_sha(root / d["path"])
        if n != d["bytes"] or s != d["sha256"]:
            deliv_bad.append(d["path"])
    recomputed = hashlib.sha256(
        "\n".join("%s:%s" % (d["path"], d["sha256"]) for d in sorted(m["deliverables"], key=lambda x: x["path"])).encode()
    ).hexdigest()
    add("V06", "manifest 输入/交付哈希与根摘要一致",
        not inp_bad and not deliv_bad and recomputed == m["manifest_root_digest"]
        and m["input_count"] == len(INPUTS) and m["deliverable_count"] == len(MANIFEST_DELIVERABLES),
        "input_bad=%d deliv_bad=%d root_match=%s" % (len(inp_bad), len(deliv_bad), recomputed == m["manifest_root_digest"]))

    # V07 纯 LF
    crlf = [f for f in DELIVERABLES if b"\r\n" in (root / "runs/issues/R02" / f).read_bytes()]
    add("V07", "交付物纯 LF", not crlf, "crlf=%s" % crlf)

    # V08 review 动态结论
    rev = ctx.review
    derived = "SELF_CHECK_PASS_WITH_LIMITS" if not bad else "NOT_READY_PENDING_FIX"
    add("V08", "review.decision 由 anomalies 动态推导且与实测一致",
        rev["decision"] == derived and rev["anomalies"] == bad
        and rev["release_R00"] is False and rev["release_R03"] is False and rev["issue_53_touched"] is False,
        "review=%s derived=%s anomalies=%d vs %d" % (rev["decision"], derived, len(rev["anomalies"]), len(bad)))

    # V09 结构画像
    mism = []
    for t in TOPIC_GROUPS:
        members = ctx.topic_members(t)
        mains_t = [s for s in members if s in ctx.mainline]
        swc = Counter(ctx.master[s]["sw_l2"] for s in members if ctx.master[s]["sw_l2"]).most_common(3)
        row = dmap[t]
        if int(row["h1_mainline_count"]) != sum(1 for s in mains_t if ctx.cand[s]["s05_anchor_period"] == "20260630"):
            mism.append(t + ":h1")
        if int(row["m9_mainline_count"]) != sum(1 for s in mains_t if ctx.cand[s]["s05_anchor_period"] == "20260930"):
            mism.append(t + ":m9")
        tiers = Counter(ctx.cand[s]["r00_priority_tier"][:6] for s in mains_t)
        for i in (1, 2, 3):
            if row["tier%d_count" % i] != str(tiers["TIER_%d" % i]):
                mism.append("%s:tier%d" % (t, i))
        for i, (name, cnt) in enumerate(swc, start=1):
            if row["sw_l2_top%d" % i] != name or row["sw_l2_top%d_count" % i] != str(cnt):
                mism.append("%s:sw%d" % (t, i))
        if row["issue_number"] != str(ISSUE_NO[t]):
            mism.append(t + ":issue")
        if not row["issue_url"].endswith("/issues/%d" % ISSUE_NO[t]):
            mism.append(t + ":url")
    add("V09", "分派表锚定/TIER/申万Top3/子issue 逐项重算一致", not mism, "mismatch=%s" % mism[:5])

    # V10 UNKNOWN 保留与无编造
    snap_metrics = {m["metric_key"] for s in ctx.snap["sources"] for m in s["parsed_metrics"]}
    fabricated = [r["metric_id"] for r in l1 if r["metric_id"] not in snap_metrics]
    unknown_ok = all(n["status"] == "UNKNOWN" for n in ctx.snap["not_disclosed"]) and bool(ctx.snap["not_disclosed"])
    limits_txt = (root / "runs/issues/R02/industry_limits.md").read_text(encoding="utf-8")
    lacks = [s for s in STD_MUST if s not in limits_txt]
    add("V10", "LAYER_1 指标全部来自官方快照；UNKNOWN 保留；限制条目齐全",
        not fabricated and unknown_ok and not lacks,
        "fabricated=%s unknown=%s lacks=%s" % (fabricated, unknown_ok, lacks))

    # V11 快照完整性
    srcs = ctx.snap["sources"]
    s_bad = []
    for s in srcs:
        if not s.get("exact_quote") or not s.get("source_url", "").startswith("https://www.stats.gov.cn/"):
            s_bad.append(s["source_id"])
        if s["disclosure_date"] > CUTOFF or s["fact_or_forecast"] != "FACT" or s.get("http_status") != 200:
            s_bad.append(s["source_id"])
        if len(s.get("raw_html_sha256", "")) != 64:
            s_bad.append(s["source_id"])
    add("V11", "官方快照 9 页完整、引文非空、披露日合规、原始哈希齐备",
        len(srcs) == 9 and ctx.snap["source_count"] == 9 and not s_bad and ctx.snap["captured_at"] == NOW,
        "sources=%d bad=%s captured_at=%s" % (len(srcs), s_bad, ctx.snap["captured_at"]))

    return checks, bad


# ------------------------------------------------------------ 复现与负例

COPY_FILES = INPUTS + ["runs/issues/R02/" + s for s in SCRIPTS]


def make_temp_tree(dst: Path, root: Path):
    for rel in COPY_FILES:
        tgt = dst / rel
        tgt.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / rel, tgt)
    for f in DELIVERABLES + ["review.json", "manifest.json"]:
        tgt = dst / "runs/issues/R02" / f
        tgt.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / "runs/issues/R02" / f, tgt)


def replay_test(root: Path):
    tmp = Path(tempfile.mkdtemp(prefix="r02_replay_"))
    try:
        make_temp_tree(tmp, root)
        env = dict(os.environ, R02_FIXED_NOW=NOW)
        hashes = []
        for _ in range(2):
            p = subprocess.run([sys.executable, "runs/issues/R02/step_r02_build.py"],
                               cwd=str(tmp), env=env, capture_output=True, text=True)
            if p.returncode != 0:
                return False, "build failed rc=%d %s" % (p.returncode, p.stdout[-300:] + p.stderr[-300:])
            hashes.append({f: exact_sha(tmp / "runs/issues/R02" / f)[1] for f in DELIVERABLES + ["review.json", "manifest.json"]})
        same = hashes[0] == hashes[1]
        repo_hash = {f: exact_sha(root / "runs/issues/R02" / f)[1] for f in DELIVERABLES + ["review.json"]}
        in_sync = repo_hash == {f: hashes[1][f] for f in DELIVERABLES + ["review.json"]}
        return (same and in_sync), "twice_identical=%s repo_in_sync=%s" % (same, in_sync)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def negative_test(root: Path):
    """活体篡改：改一条 LAYER_1 disclosure_date 与一条 LAYER_2 改善占比，确认退出码 1。"""
    tmp = Path(tempfile.mkdtemp(prefix="r02_neg_"))
    try:
        make_temp_tree(tmp, root)
        sig = tmp / "runs/issues/R02/industry_signals.csv"
        with open(sig, encoding="utf-8", newline="") as f:
            rd = csv.DictReader(f)
            fields = rd.fieldnames
            rows = list(rd)
        hit_date = hit_share = False
        for r in rows:
            if not hit_date and r["signal_layer"] == "LAYER_1_NBS_OFFICIAL_MACRO" and r["disclosure_date"]:
                r["disclosure_date"] = "2026-11-01"
                hit_date = True
            elif not hit_share and r["signal_layer"] == "LAYER_2_POOL_SAME_PERIOD_BENCHMARK":
                r["improved_share_pct"] = "99.99"
                hit_share = True
        with open(sig, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields, lineterminator=chr(10))
            w.writeheader()
            w.writerows(rows)
        if not (hit_date and hit_share):
            return False, "tamper target not found"
        p = subprocess.run([sys.executable, "runs/issues/R02/step_r02_verify.py",
                            "--root", str(tmp), "--skip-replay"],
                           cwd=str(tmp), env=dict(os.environ, R02_FIXED_NOW=NOW),
                           capture_output=True, text=True)
        detected = (p.returncode == 1 and "[FAIL] V03" in p.stdout and "[FAIL] V04" in p.stdout)
        return detected, "rc=%d detected=%s" % (p.returncode, detected)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ------------------------------------------------------------ main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(REPO))
    ap.add_argument("--skip-replay", action="store_true")
    ap.add_argument("--negative-test", action="store_true")
    args = ap.parse_args()
    root = Path(args.root).resolve()

    if args.negative_test:
        ok, detail = negative_test(root)
        print("NEGATIVE_TEST", "PASS" if ok else "FAIL", detail)
        return 0 if ok else 1

    ctx = Ctx(root)
    checks, bad = run_checks(ctx)

    if not args.skip_replay:
        ok, detail = replay_test(root)
        checks.append({"id": "V12", "name": "固定时间戳连续两次构建逐字节一致且与仓库交付同步",
                       "result": "PASS" if ok else "FAIL", "detail": detail})
        if not ok:
            bad.append("V12 逐字节复现失败: " + detail)

    passed = sum(1 for c in checks if c["result"] == "PASS")
    print("R02 verify @", NOW, "root=", root)
    for c in checks:
        print("  [%s] %s %s" % (c["result"], c["id"], c["name"]))
        if c["result"] != "PASS":
            print("        ", c["detail"])
    print("checks %d/%d PASS, anomalies=%d" % (passed, len(checks), len(bad)))
    if bad:
        for b in bad:
            print("  ANOMALY", b)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
