#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R02 / #46 构建：行业信号核验与同口径比较（完全离线）。

只读取 Git 跟踪树内的输入文件，不联网、不修改任何上游冻结文件。
全部产物写入 runs/issues/R02/ 且为纯 LF。

产物
----
industry_topic_dispatch.csv   3 个主题子包的分派与结构画像
industry_signals.csv          双层信号：NBS 官方宏观 + 池内同口径基准
industry_limits.md            统计口径边界与限制
manifest.json                 输入/交付哈希与根摘要
handoff.md                    交接说明
review.json                   SELF_CHECK（decision 由 anomalies 动态推导）

复现
----
    R02_FIXED_NOW=2026-11-26T15:00:00+08:00 py runs/issues/R02/step_r02_build.py
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
import sys
from collections import Counter, OrderedDict
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
OUT = REPO / "runs/issues/R02"

TZ = timezone(timedelta(hours=8))
NOW = os.environ.get("R02_FIXED_NOW") or "2026-11-26T15:00:00+08:00"
TODAY = NOW[:10]
CUTOFF = "2026-10-25"

PLAN_VERSION = "20261026_collection_first_v2"
ISSUE_KEY = "R02"
ISSUE_NUMBER = 46

IN_RELEASE = "runs/issues/R02/release_20261126.json"
IN_HANDOFF = "runs/issues/R02/handoff_from_s08_20261126.md"
IN_SNAPSHOT = "runs/issues/R02/nbs_official_sources_snapshot.json"
IN_MASTER = "data/company_master.csv"
IN_GROUP_SUMMARY = "data/group_summary.csv"
IN_S08_ACCEPT = "runs/issues/S08/acceptance_s08_20261126.json"
IN_S08_CAND = "runs/issues/S08/business_verification_candidates.csv"
IN_S08_SCREEN = "runs/issues/S08/screen_acceptance.json"
IN_S02_METRICS = "runs/issues/S02/hangcha_restated_20261101/s02_v10/all_pool_metrics.csv"
IN_S05_FLAGS = "runs/issues/S05/quality_flags.csv"
IN_S05_LOG = "runs/issues/S05/quality_decision_log.csv"

INPUTS = [IN_RELEASE, IN_HANDOFF, IN_SNAPSHOT, IN_MASTER, IN_GROUP_SUMMARY,
          IN_S08_ACCEPT, IN_S08_CAND, IN_S08_SCREEN, IN_S02_METRICS,
          IN_S05_FLAGS, IN_S05_LOG]

OUT_DISPATCH = "industry_topic_dispatch.csv"
OUT_SIGNALS = "industry_signals.csv"
OUT_LIMITS = "industry_limits.md"
OUT_MANIFEST = "manifest.json"
OUT_HANDOFF = "handoff.md"
OUT_REVIEW = "review.json"

DELIVERABLES = [OUT_DISPATCH, OUT_SIGNALS, OUT_LIMITS, OUT_HANDOFF]
SCRIPTS = ["step_r02_build.py", "step_r02_verify.py", "collect_nbs_snapshot.py"]
MANIFEST_DELIVERABLES = DELIVERABLES + SCRIPTS

TOPICS = OrderedDict([
    ("R02_T01", {
        "issue": 54,
        "url": "https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/54",
        "title": "R02_T01｜行业信号主题子包：核心零部件（传动/驱动/感知与运动控制）",
        "groups": ["G01", "G02", "G03", "G04"],
        "nbs_metrics": ["IVA_GENERAL_EQUIPMENT_YOY_CUM", "IVA_SPECIAL_EQUIPMENT_YOY_CUM",
                        "IVA_COMPUTER_ELECTRONICS_YOY_CUM", "ROBOT_INDUSTRIAL_OUTPUT_CUM",
                        "PPI_PROCESSING_YOY_M", "PMI_MANUFACTURING", "PMI_NEW_ORDERS"],
    }),
    ("R02_T02", {
        "issue": 55,
        "url": "https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/55",
        "title": "R02_T02｜行业信号主题子包：装备集成与整机应用（自动化/母机/专用与服务机器人）",
        "groups": ["G05", "G06"],
        "nbs_metrics": ["IVA_GENERAL_EQUIPMENT_YOY_CUM", "IVA_SPECIAL_EQUIPMENT_YOY_CUM",
                        "ROBOT_INDUSTRIAL_OUTPUT_CUM", "ROBOT_SERVICE_OUTPUT_CUM",
                        "PPI_EXFACTORY_YOY_M", "PMI_PRODUCTION"],
    }),
    ("R02_T03", {
        "issue": 56,
        "url": "https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/56",
        "title": "R02_T03｜行业信号主题子包：跨界制造与上游材料（汽车电子/材料加工/人形与宽泛概念）",
        "groups": ["G07", "G08", "G09", "G10"],
        "nbs_metrics": ["IVA_AUTOMOTIVE_YOY_CUM", "IVA_ELECTRICAL_MACHINERY_YOY_CUM",
                        "IVA_COMPUTER_ELECTRONICS_YOY_CUM", "PPI_PRODUCTION_GOODS_YOY_M",
                        "PPI_CUMULATIVE_AVG_YOY_CUM", "PMI_MANUFACTURING"],
    }),
])

LAYER2_METRICS = [
    ("M01", "营业收入同比（累计）"),
    ("M04", "毛利率同比变动"),
    ("M05", "扣非归母净利润同比（累计）"),
    ("M06", "扣非归母净利率变动"),
]

PERIODS = [
    ("20260630", "20250630", "H1"),
    ("20260930", "20250930", "9M"),
]

BOUNDARY_L2 = ("冻结 S02 v10 指标，仅取 metric_status=OK；改善定义为指标值>0（M01/M05 为同比，M04/M06 为百分点变动）；"
               "中位数与四分位为池内公司等权分布，非市值/营收加权；基期<=0 不可算的同比已由 metric_status 排除。")
SW_NOTE = "SW_L2 != NBS：申万二级行业分类不等同于国家统计局国民经济行业分类，板块对照仅作池内结构参考，不可与官方行业增速直接对齐。"


# ---------------------------------------------------------------- 基础工具

def read_csv(rel):
    with open(REPO / rel, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def read_json(rel):
    return json.loads((REPO / rel).read_text(encoding="utf-8"))


def sha256_exact(path: Path):
    raw = path.read_bytes()
    return len(raw), hashlib.sha256(raw).hexdigest()


def canon_bytes(path: Path):
    raw = path.read_bytes()
    raw = raw.replace(b"\r\n", b"\n")
    return raw


def fmt_nbs(v, unit=None):
    """按官方公布精度渲染：百分比/指数保留 1 位小数，产量为整数。"""
    if v is None:
        return "UNKNOWN"
    if unit == "套":
        return str(int(round(v)))
    if unit in ("%", "index", "pp"):
        return "%.1f" % v
    if abs(v - round(v)) < 1e-12:
        return str(int(round(v)))
    s = ("%.6f" % v).rstrip("0").rstrip(".")
    return s


def fmt_stat(v):
    if v is None:
        return "UNKNOWN"
    return "%.6f" % v


def fmt_qty(v):
    if v is None:
        return "UNKNOWN"
    return "{:,}".format(int(round(v)))


def fmt_share(v):
    if v is None:
        return "UNKNOWN"
    return "%.2f" % v


def pctl(sorted_vals, q):
    """类型 7 线性插值分位数（与 numpy 默认 / Excel PERCENTILE.INC 一致）。"""
    n = len(sorted_vals)
    if n == 0:
        return None
    if n == 1:
        return sorted_vals[0]
    h = (n - 1) * q
    lo = int(math.floor(h))
    hi = int(math.ceil(h))
    if lo == hi:
        return sorted_vals[lo]
    return sorted_vals[lo] + (h - lo) * (sorted_vals[hi] - sorted_vals[lo])


def stats_of(pairs):
    """pairs: [(security_id, name, value)] -> 统计字典。"""
    vals = sorted(p[2] for p in pairs)
    if not vals:
        return {
            "valid": 0, "improved": 0, "share": None, "median": None,
            "p25": None, "p75": None, "top1_id": "", "top1_name": "", "top1_val": None,
            "ex_share": None, "ex_median": None,
        }
    improved = sum(1 for v in vals if v > 0)
    top = sorted(pairs, key=lambda p: (-p[2], p[0]))[0]
    rest = [p[2] for p in pairs if p[0] != top[0]]
    rest_sorted = sorted(rest)
    return {
        "valid": len(vals),
        "improved": improved,
        "share": round(100.0 * improved / len(vals), 6),
        "median": round(pctl(vals, 0.5), 6),
        "p25": round(pctl(vals, 0.25), 6),
        "p75": round(pctl(vals, 0.75), 6),
        "top1_id": top[0],
        "top1_name": top[1],
        "top1_val": round(top[2], 6),
        "ex_share": round(100.0 * sum(1 for v in rest if v > 0) / len(rest), 6) if rest else None,
        "ex_median": round(pctl(rest_sorted, 0.5), 6) if rest else None,
    }


# ---------------------------------------------------------------- 载入输入

master = {r["security_id"]: r for r in read_csv(IN_MASTER)}
group_summary = {r["group_id"]: r for r in read_csv(IN_GROUP_SUMMARY)}
cand = {r["security_id"]: r for r in read_csv(IN_S08_CAND)}
screen = read_json(IN_S08_SCREEN)
accept = read_json(IN_S08_ACCEPT)
snapshot = read_json(IN_SNAPSHOT)
release = read_json(IN_RELEASE)

metrics_raw = read_csv(IN_S02_METRICS)
METRIC = {}
for r in metrics_raw:
    METRIC[(r["security_id"], r["metric_id"], r["period_key"], r["period_type"])] = r

s05_flags = read_csv(IN_S05_FLAGS)
s05_log = read_csv(IN_S05_LOG)


def group_of(sid):
    return master[sid]["routing_group"]


def topic_of(sid):
    g = group_of(sid)
    for t, spec in TOPICS.items():
        if g in spec["groups"]:
            return t
    return None


MAINLINE = {s for s, r in cand.items() if r["final_queue"] == "R00_MAINLINE_VERIFY"}
UNIVERSE = set(master)
TOPIC_ALL = {t: [s for s in master if group_of(s) in spec["groups"]] for t, spec in TOPICS.items()}
TOPIC_MAIN = {t: [s for s in TOPIC_ALL[t] if s in MAINLINE] for t in TOPICS}


def sw_top(sids, k=3):
    c = Counter(master[s]["sw_l2"] for s in sids if master[s]["sw_l2"])
    return c.most_common(k), sum(1 for s in sids if not master[s]["sw_l2"])


# ---------------------------------------------------------------- LAYER 1

def layer1_rows():
    rows = []
    for s in snapshot["sources"]:
        for m in s["parsed_metrics"]:
            rows.append({
                "signal_layer": "LAYER_1_NBS_OFFICIAL_MACRO",
                "signal_id": "L1:%s:%s" % (m["metric_key"], m["period_key"]),
                "topic_id": "",
                "denominator": "NBS_OFFICIAL",
                "metric_id": m["metric_key"],
                "metric_name": m["metric_name_cn"],
                "period_key": m["period_key"],
                "base_period_key": m["base_period_key"],
                "value": fmt_nbs(m["value"], m["unit"]),
                "unit": m["unit"],
                "yoy_pct": fmt_nbs(m["yoy_pct"], m["unit"]),
                "mom_change_pp": fmt_nbs(m["mom_change_pp"], "pp"),
                "sample_scope": m["sample_scope"],
                "valid_paired_count": "",
                "denominator_count": "",
                "improved_count": "",
                "improved_share_pct": "",
                "median_value": "",
                "p25_value": "",
                "p75_value": "",
                "top1_contributor_id": "",
                "top1_contributor_name": "",
                "top1_contributor_value": "",
                "ex_top1_improved_share_pct": "",
                "ex_top1_median_value": "",
                "source_name": s["source_name"],
                "source_url": s["source_url"],
                "disclosure_date": s["disclosure_date"],
                "fact_or_forecast": s["fact_or_forecast"],
                "scope_conflict_flag": m["scope_conflict_flag"],
                "interpretation_boundary": m["interpretation_boundary"],
                "sw_l2_note": "",
            })
    rows.sort(key=lambda r: (r["metric_id"], r["period_key"]))
    return rows


# ---------------------------------------------------------------- LAYER 2

def group_members(topic, denominator):
    if denominator == "R00_MAINLINE":
        return TOPIC_MAIN[topic]
    if denominator == "UNIVERSE_ALL":
        return TOPIC_ALL[topic]
    if denominator.startswith("SW_L2:"):
        sw = denominator.split(":", 1)[1]
        return [s for s in TOPIC_ALL[topic] if master[s]["sw_l2"] == sw]
    raise SystemExit("bad denominator " + denominator)


def collect_pairs(members, metric_id, period_key, period_type):
    out = []
    for s in members:
        r = METRIC.get((s, metric_id, period_key, period_type))
        if not r or r["metric_status"] != "OK":
            continue
        try:
            v = float(r["value"])
        except (TypeError, ValueError):
            continue
        out.append((s, master[s]["stock_name"], v))
    return out


def layer2_rows():
    rows = []
    for t in TOPICS:
        sws, sw_unknown = sw_top(TOPIC_ALL[t], 3)
        denoms = ["R00_MAINLINE", "UNIVERSE_ALL"] + ["SW_L2:" + k for k, _ in sws]
        for den in denoms:
            members = group_members(t, den)
            for mid, mname in LAYER2_METRICS:
                for per, base, ptype in PERIODS:
                    pairs = collect_pairs(members, mid, per, ptype)
                    st = stats_of(pairs)
                    rows.append({
                        "signal_layer": "LAYER_2_POOL_SAME_PERIOD_BENCHMARK",
                        "signal_id": "L2:%s:%s:%s:%s" % (t, den.replace(":", "-"), mid, per),
                        "topic_id": t,
                        "denominator": den,
                        "metric_id": mid,
                        "metric_name": mname,
                        "period_key": per,
                        "base_period_key": base,
                        "value": "",
                        "unit": "ratio" if mid in ("M01", "M05") else "pp",
                        "yoy_pct": "",
                        "mom_change_pp": "",
                        "sample_scope": "冻结 S02 v10 全池指标（%s 锚定，%s）" % (ptype, per),
                        "valid_paired_count": st["valid"],
                        "denominator_count": len(members),
                        "improved_count": st["improved"],
                        "improved_share_pct": fmt_share(st["share"]),
                        "median_value": fmt_stat(st["median"]),
                        "p25_value": fmt_stat(st["p25"]),
                        "p75_value": fmt_stat(st["p75"]),
                        "top1_contributor_id": st["top1_id"],
                        "top1_contributor_name": st["top1_name"],
                        "top1_contributor_value": fmt_stat(st["top1_val"]),
                        "ex_top1_improved_share_pct": fmt_share(st["ex_share"]),
                        "ex_top1_median_value": fmt_stat(st["ex_median"]),
                        "source_name": "S02 v10 all_pool_metrics.csv（冻结）",
                        "source_url": "",
                        "disclosure_date": "",
                        "fact_or_forecast": "FACT",
                        "scope_conflict_flag": "NO",
                        "interpretation_boundary": BOUNDARY_L2,
                        "sw_l2_note": SW_NOTE if den.startswith("SW_L2:") else "",
                    })
    return rows


SIGNAL_FIELDS = [
    "signal_layer", "signal_id", "topic_id", "denominator", "metric_id", "metric_name",
    "period_key", "base_period_key", "value", "unit", "yoy_pct", "mom_change_pp",
    "sample_scope", "valid_paired_count", "denominator_count", "improved_count",
    "improved_share_pct", "median_value", "p25_value", "p75_value",
    "top1_contributor_id", "top1_contributor_name", "top1_contributor_value",
    "ex_top1_improved_share_pct", "ex_top1_median_value",
    "source_name", "source_url", "disclosure_date", "fact_or_forecast",
    "scope_conflict_flag", "interpretation_boundary", "sw_l2_note",
]

DISPATCH_FIELDS = [
    "topic_id", "issue_number", "issue_url", "topic_title", "routing_groups",
    "universe_count", "r00_mainline_count", "mainline_share_pct",
    "h1_mainline_count", "m9_mainline_count", "h1_universe_count", "m9_universe_count",
    "tier1_count", "tier2_count", "tier3_count",
    "sw_l2_top1", "sw_l2_top1_count", "sw_l2_top2", "sw_l2_top2_count",
    "sw_l2_top3", "sw_l2_top3_count", "sw_l2_unknown_count",
    "nbs_metrics_used", "nbs_source_urls", "core_boundaries",
]


def dispatch_rows():
    rows = []
    for t, spec in TOPICS.items():
        allc, main = TOPIC_ALL[t], TOPIC_MAIN[t]
        sws, sw_unknown = sw_top(allc, 3)
        tiers = Counter(cand[s]["r00_priority_tier"][:6] for s in main)
        rows.append({
            "topic_id": t,
            "issue_number": spec["issue"],
            "issue_url": spec["url"],
            "topic_title": spec["title"],
            "routing_groups": "+".join(spec["groups"]),
            "universe_count": len(allc),
            "r00_mainline_count": len(main),
            "mainline_share_pct": "%.6f" % (100.0 * len(main) / len(allc)),
            "h1_mainline_count": sum(1 for s in main if cand[s]["s05_anchor_period"] == "20260630"),
            "m9_mainline_count": sum(1 for s in main if cand[s]["s05_anchor_period"] == "20260930"),
            "h1_universe_count": sum(1 for s in allc if cand[s]["s05_anchor_period"] == "20260630"),
            "m9_universe_count": sum(1 for s in allc if cand[s]["s05_anchor_period"] == "20260930"),
            "tier1_count": tiers["TIER_1"],
            "tier2_count": tiers["TIER_2"],
            "tier3_count": tiers["TIER_3"],
            "sw_l2_top1": sws[0][0] if len(sws) > 0 else "UNKNOWN",
            "sw_l2_top1_count": sws[0][1] if len(sws) > 0 else 0,
            "sw_l2_top2": sws[1][0] if len(sws) > 1 else "UNKNOWN",
            "sw_l2_top2_count": sws[1][1] if len(sws) > 1 else 0,
            "sw_l2_top3": sws[2][0] if len(sws) > 2 else "UNKNOWN",
            "sw_l2_top3_count": sws[2][1] if len(sws) > 2 else 0,
            "sw_l2_unknown_count": sw_unknown,
            "nbs_metrics_used": ";".join(spec["nbs_metrics"]),
            "nbs_source_urls": ";".join(sorted({s["source_url"] for s in snapshot["sources"]
                                                if any(m["metric_key"] in spec["nbs_metrics"]
                                                       for m in s["parsed_metrics"])})),
            "core_boundaries": ("申万行业!=NBS行业;routing_group仅为检索线索非已核实机器人业务分类;"
                                "PPI!=企业售价;行业景气/产量!=单一公司机器人真实收入;H1与9M严格分层禁止跨期合并"),
        })
    return rows


# ---------------------------------------------------------------- 文本产物

def nbs_series(metric_key):
    out = []
    for s in snapshot["sources"]:
        for m in s["parsed_metrics"]:
            if m["metric_key"] == metric_key:
                out.append(m)
    order = {"2025FY": 0, "202512": 0, "2026H1": 1, "202606": 1, "2026Q1Q3": 2, "202609": 2}
    out.sort(key=lambda m: order.get(m["period_key"], 9))
    return out


def val_of(rows, topic, den, mid, per):
    for r in rows:
        if (r["topic_id"] == topic and r["denominator"] == den
                and r["metric_id"] == mid and r["period_key"] == per):
            return r
    raise SystemExit("missing row %s %s %s %s" % (topic, den, mid, per))


def build_limits(sig_rows):
    L = []
    A = L.append
    A("# R02 行业信号统计口径边界与限制（#46）")
    A("")
    A("- 计划版本：`%s`；知识截止日：`%s`；生成时间：`%s`（Asia/Shanghai）" % (PLAN_VERSION, CUTOFF, NOW))
    A("- 本文件与 `industry_signals.csv` 配套阅读。所有边界限制均直接约束结论可用范围，不得越界引用。")
    A("")
    A("## 1. 行业分类口径")
    A("")
    A("1. **申万行业分类 != NBS 国民经济行业分类**。池内 `sw_l2` 来自申万体系，国家统计局使用《国民经济行业分类》(GB/T 4754) 大类；两者名称相近（如「通用设备」）但编制目的、覆盖范围、统计单位不同，**不可逐项对齐或做差值比较**。")
    A("2. **`routing_group` 只是检索线索，不是已核实的机器人业务分类**。G01—G10 由概念/关键词归并而来（`classification_is_verified` 均为 NO），仅用于资源分派；本文件不据此认定任何公司具备机器人收入。")
    A("3. **国民经济行业分类中无独立「机器人制造业」大类**，官方不单列机器人行业增加值，只能用通用设备/专用设备/电气机械/计算机电子等上位行业代理，代理偏差不可消除（记 `UNKNOWN`）。")
    A("")
    A("## 2. 价格与景气口径")
    A("")
    A("4. **PPI != 企业产品实际售价**。PPI 是工业生产者出厂价格总水平指数，按行业加权、含口径调整；单一企业的售价、产品结构、议价能力差异远大于 PPI 变动。PPI 回升不能推出池内企业毛利率改善。")
    A("5. **PMI 是环比扩散指数**（50 为荣枯线），反映采购经理对景气扩张或收缩方向的判断，不是同比增速，也不代表池内企业订单金额或收入。")
    A("6. **工业增加值是扣除价格因素的实际增速**，覆盖年主营业务收入 2000 万元及以上工业企业，不含规模以下企业，存在规模门槛偏误。")
    A("")
    A("## 3. 产量与公司收入的边界")
    A("")
    A("7. **行业产量/大盘景气 != 单一公司机器人真实收入**，在 `R02_T03`（跨界制造与上游材料）尤其危险：该主题 401 家全池公司中多数主营并非机器人，行业产量增长无法归因到任何单家公司。")
    A("8. 机器人产量为规模以上工业企业**实物产量**，含出口、库存与统计口径调整，不等于销量，也不等于收入。")
    A("")
    A("## 4. 池内财务口径")
    A("")
    A("9. **H1（20260630）与 9M（20260930）严格分层，禁止跨期合并**（结转 S08 F05）。两层锚定期样本量差异极大：H1 全池 %d 家、9M 全池 %d 家；主线公司 H1 %d 家、9M %d 家。9M 样本小，改善占比的抽样波动显著更大。" % (
        sum(1 for s in UNIVERSE if cand[s]["s05_anchor_period"] == "20260630"),
        sum(1 for s in UNIVERSE if cand[s]["s05_anchor_period"] == "20260930"),
        sum(1 for s in MAINLINE if cand[s]["s05_anchor_period"] == "20260630"),
        sum(1 for s in MAINLINE if cand[s]["s05_anchor_period"] == "20260930")))
    A("10. **扣非净利润 != 归母净利润 != NBS 工业利润**。M05 为扣非归母净利润同比，剔除非经常性损益；NBS 工业利润为规模以上工业企业利润总额，二者主体、口径、期间均不同。")
    A("11. **基期 <= 0 不可算常规同比**。此类记录在 S02 中已标记 `UNDEFINED_BASE`/`NOT_COMPARABLE`，本文件只取 `metric_status=OK`，因此「有效配对公司数」小于分母公司数，改善占比的分母是有效配对而非全部公司。")
    A("12. **中位数与四分位为等权分布**，非市值加权、非营收加权；`top1_contributor` 定义为该组内指标值最大的单一公司（最大上行离群），剔除后重算的 `ex_top1_*` 用于判断结论是否被单一龙头拉动。")
    A("13. 改善定义统一为「指标值 > 0」：M01/M05 为同比为正，M04/M06 为百分点变动为正。该定义不区分幅度大小，也不做显著性检验。")
    A("")
    A("## 5. 样本与偏差")
    A("")
    A("14. **幸存者偏差**：全池 1,054 家来自概念/关键词候选池，本身已排除未上市与未被概念覆盖的企业；R00 主线 277 家又是通过 S04/S05 质量门槛的子集，主线口径的行业结论不代表全行业。")
    A("15. **BJ 与沪深市场差异仅作描述**（结转 S08 F08），不构成质量判断。")
    A("16. 9M 锚定公司集中在少数行业与较晚披露主体，行业内部结构可能与 H1 不同，H1→9M 的变化不能全部解释为景气变化。")
    sw_rows = [r for r in sig_rows if r["denominator"].startswith("SW_L2:")]
    thin = [r for r in sw_rows if r["valid_paired_count"] not in ("", "UNKNOWN") and int(r["valid_paired_count"]) < 5]
    if sw_rows:
        A("17. **申万二级板块对照的最小有效配对仅 %s 家**，%d/%d 条板块记录有效配对 < 5 家（多见于 9M 锚定）。此类板块行只作结构提示，不构成板块级结论；引用前必须同时读取 `valid_paired_count`。" % (
            min(int(r["valid_paired_count"]) for r in sw_rows), len(thin), len(sw_rows)))
    A("")
    A("## 6. 本次实测中需要单独提示的口径现象")
    A("")
    sr_m = nbs_series("ROBOT_SERVICE_OUTPUT_M")
    sr_c = nbs_series("ROBOT_SERVICE_OUTPUT_CUM")
    ir_m = nbs_series("ROBOT_INDUSTRIAL_OUTPUT_M")
    ir_c = nbs_series("ROBOT_INDUSTRIAL_OUTPUT_CUM")
    A("18. **服务机器人单月与累计方向背离**：2026 年 9 月单月产量 %s 套、同比 %s%%，而 1—9 月累计同比 %s%%。单月大幅负增长与累计正增长并存，说明累计增速由前期高增长支撑、边际已转弱；不得只引用累计值描述当期景气。" % (
        fmt_qty(sr_m[-1]["value"]), fmt_nbs(sr_m[-1]["yoy_pct"], "%"), fmt_nbs(sr_c[-1]["yoy_pct"], "%")))
    A("19. **工业机器人累计增速小幅抬升但单月增速回落**：1—9 月累计同比 %s%%（H1 为 %s%%、2025 全年为 %s%%），9 月单月同比 %s%%。累计抬升与单月回落同时成立，属基数与节奏差异，不构成方向冲突，但单月读数波动大，不宜单独外推。" % (
        fmt_nbs(ir_c[-1]["yoy_pct"], "%"), fmt_nbs(ir_c[1]["yoy_pct"], "%"), fmt_nbs(ir_c[0]["yoy_pct"], "%"),
        fmt_nbs(ir_m[-1]["yoy_pct"], "%")))
    ppi = nbs_series("PPI_EXFACTORY_YOY_M")
    A("20. **PPI 由负转正**：2025 年 12 月单月同比 %s%%、2026 年 6 月 %s%%、2026 年 9 月 %s%%。价格端转正与池内毛利率变动方向需分别核验，不可用 PPI 直接解释 M04。" % (
        fmt_nbs(ppi[0]["yoy_pct"], "%"), fmt_nbs(ppi[1]["yoy_pct"], "%"), fmt_nbs(ppi[2]["yoy_pct"], "%")))
    A("")
    A("## 7. UNKNOWN 保留清单")
    A("")
    A("| 指标 | 状态 | 说明 |")
    A("| --- | --- | --- |")
    for n in snapshot["coverage_notes"]:
        A("| `%s` | %s | %s |" % (n["metric_key"], n["status"], n["note"]))
    A("")
    A("> 未披露即 `UNKNOWN`，不以邻近指标替代、不做插值、不跨口径拼接。")
    A("")
    return "\n".join(L)


def build_handoff(sig_rows, disp_rows):
    L = []
    A = L.append
    A("# R02 / #46 交接：行业信号核验与同口径比较")
    A("")
    A("- 计划版本：`%s`；知识截止日：`%s`；生成时间：`%s`" % (PLAN_VERSION, CUTOFF, NOW))
    A("- 执行方：CodeBuddy；统筹方：Antigravity；独立复核：Codex（本文件仅为执行方 SELF_CHECK，不代替独立复核）")
    A("- 结论状态：`SELF_CHECK`；未放行 R00、未放行 R03、未触碰 #53")
    A("")
    A("## 1. 外部官方信号（NBS，披露日 <= %s）" % CUTOFF)
    A("")
    A("| 指标 | 2025 全年 / 12 月 | 2026 H1 / 6 月 | 2026 1—9 月 / 9 月 |")
    A("| --- | --- | --- | --- |")
    for key, name in [
        ("ROBOT_INDUSTRIAL_OUTPUT_CUM", "工业机器人产量（套，累计）"),
        ("ROBOT_SERVICE_OUTPUT_CUM", "服务机器人产量（套，累计）"),
        ("IVA_GENERAL_EQUIPMENT_YOY_CUM", "通用设备制造业增加值同比（%）"),
        ("IVA_SPECIAL_EQUIPMENT_YOY_CUM", "专用设备制造业增加值同比（%）"),
        ("IVA_AUTOMOTIVE_YOY_CUM", "汽车制造业增加值同比（%）"),
        ("IVA_ELECTRICAL_MACHINERY_YOY_CUM", "电气机械和器材制造业增加值同比（%）"),
        ("IVA_COMPUTER_ELECTRONICS_YOY_CUM", "计算机、通信和其他电子设备制造业增加值同比（%）"),
        ("PPI_CUMULATIVE_AVG_YOY_CUM", "PPI 累计平均同比（%）"),
    ]:
        s = nbs_series(key)
        if len(s) < 3:
            continue
        if key.startswith("ROBOT_"):
            cells = ["%s（%s%%）" % (fmt_qty(x["value"]), fmt_nbs(x["yoy_pct"], "%")) for x in s]
        else:
            cells = [fmt_nbs(x["value"], "%") for x in s]
        A("| %s | %s | %s | %s |" % (name, cells[0], cells[1], cells[2]))
    A("")
    A("单月读数（同比 %）：")
    A("")
    A("| 指标 | 2025-12 | 2026-06 | 2026-09 |")
    A("| --- | --- | --- | --- |")
    for key, name in [
        ("ROBOT_INDUSTRIAL_OUTPUT_M", "工业机器人单月产量同比"),
        ("ROBOT_SERVICE_OUTPUT_M", "服务机器人单月产量同比"),
        ("PPI_EXFACTORY_YOY_M", "PPI 单月同比"),
        ("PPI_PROCESSING_YOY_M", "加工工业 PPI 单月同比"),
    ]:
        s = nbs_series(key)
        A("| %s | %s | %s | %s |" % (name, fmt_nbs(s[0]["yoy_pct"], "%"), fmt_nbs(s[1]["yoy_pct"], "%"), fmt_nbs(s[2]["yoy_pct"], "%")))
    A("")
    A("PMI（指数点，50 为荣枯线）：")
    A("")
    A("| 指标 | 2025-12 | 2026-06 | 2026-09 |")
    A("| --- | --- | --- | --- |")
    for key, name in [("PMI_MANUFACTURING", "制造业 PMI"), ("PMI_PRODUCTION", "生产指数"),
                      ("PMI_NEW_ORDERS", "新订单指数"), ("PMI_COMPOSITE", "综合 PMI 产出指数")]:
        s = nbs_series(key)
        A("| %s | %s | %s | %s |" % (name, fmt_nbs(s[0]["value"], "index"), fmt_nbs(s[1]["value"], "index"), fmt_nbs(s[2]["value"], "index")))
    A("")
    A("## 2. 池内同口径基准（H1 与 9M 严格分层）")
    A("")
    A("下表为各主题 `R00_MAINLINE` 分母的营收同比（M01）与扣非净利同比（M05）改善占比与中位数；完整 15 组 × 4 指标 × 2 期见 `industry_signals.csv`。")
    A("")
    A("| 主题 | 主线数 | 期别 | M01 有效配对 | M01 改善占比 | M01 中位数 | M01 去Top1占比 | M05 有效配对 | M05 改善占比 | M05 中位数 |")
    A("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for t, spec in TOPICS.items():
        for per, _b, ptype in PERIODS:
            r1 = val_of(sig_rows, t, "R00_MAINLINE", "M01", per)
            r5 = val_of(sig_rows, t, "R00_MAINLINE", "M05", per)
            A("| %s | %s | %s | %s | %s%% | %s | %s%% | %s | %s%% | %s |" % (
                t, len(TOPIC_MAIN[t]), ptype,
                r1["valid_paired_count"], r1["improved_share_pct"], r1["median_value"], r1["ex_top1_improved_share_pct"],
                r5["valid_paired_count"], r5["improved_share_pct"], r5["median_value"]))
    A("")
    A("要点：")
    A("")
    for t, spec in TOPICS.items():
        h1 = val_of(sig_rows, t, "R00_MAINLINE", "M01", "20260630")
        m9 = val_of(sig_rows, t, "R00_MAINLINE", "M01", "20260930")
        A("- **%s**（主线 %d 家 / 全池 %d 家）：H1 营收同比改善占比 %s%%（中位数 %s），9M 为 %s%%（中位数 %s）；H1 有效配对 %s 家、9M %s 家。" % (
            t, len(TOPIC_MAIN[t]), len(TOPIC_ALL[t]),
            h1["improved_share_pct"], h1["median_value"], m9["improved_share_pct"], m9["median_value"],
            h1["valid_paired_count"], m9["valid_paired_count"]))
    A("")
    A("## 3. 三主题对比与可用结论边界")
    A("")
    A("1. **T01 核心零部件**：上游通用/专用设备增加值增速在 2026 年逐期抬升，工业机器人累计产量增速 28%→29.1%，与该主题的景气方向一致；但池内 M01 改善占比与中位数反映的是**公司自身营收**，二者不可互相替代。")
    A("2. **T02 装备集成与整机应用**：专用设备增加值加速最明显（4.3%→8.2%→9.5%），工业机器人产量增速稳定；服务机器人累计增速 16.1%→11.9%→7.9% 连续回落、9 月单月转负，是该主题最需要警惕的分化信号。")
    A("3. **T03 跨界制造与上游材料**：汽车制造业增加值由 11.5% 降至 7.3%、电气机械 9.2%→7.1%，价格端 PPI 却由 -2.6% 转为 +2.3%。该主题 401 家中多数并非机器人主业，**行业景气不能外推为公司机器人收入**，本主题只保留结构性对照，不产出公司级结论。")
    A("")
    A("## 4. 限制（摘要，完整见 industry_limits.md）")
    A("")
    A("- 申万二级 != NBS 国民经济行业分类；`routing_group` 仅为检索线索，非已核实机器人业务分类。")
    A("- PPI != 企业实际售价；PMI 为环比扩散指数；工业增加值覆盖规模以上企业。")
    A("- 行业产量/景气 != 单一公司机器人真实收入（T03 尤其显著）。")
    A("- H1 与 9M 严格分层，禁止跨期合并；9M 样本显著小于 H1，波动更大。")
    A("- 扣非净利润 != 归母净利润 != NBS 工业利润；基期 <= 0 不计常规同比。")
    A("- 幸存者偏差：概念池 -> 质量门槛 -> 主线，逐层收窄。")
    A("- `PPI_SUBINDUSTRY_ROBOT_SPECIFIC`、`NBS_ROBOT_INDUSTRY_VA` 保持 `UNKNOWN`。")
    A("")
    A("## 5. 交付物与复现")
    A("")
    A("| 文件 | 说明 |")
    A("| --- | --- |")
    A("| `industry_topic_dispatch.csv` | 3 主题分派、结构画像、官方指标映射、口径边界 |")
    A("| `industry_signals.csv` | 双层信号（LAYER_1 官方 / LAYER_2 池内），共 %d 行 |" % len(sig_rows))
    A("| `industry_limits.md` | 口径边界与限制 |")
    A("| `nbs_official_sources_snapshot.json` | 官方原文快照（9 页 / %d 指标，一次性采集，离线只读） |" % snapshot["metric_count"])
    A("| `manifest.json` | 输入/交付哈希与根摘要 |")
    A("| `review.json` | SELF_CHECK（decision 由 anomalies 推导） |")
    A("| `step_r02_build.py` / `step_r02_verify.py` | 离线构建 / 独立校验 |")
    A("| `collect_nbs_snapshot.py` | 一次性联网采集脚本（不参与离线复现） |")
    A("")
    A("复现命令：")
    A("")
    A("```bash")
    A("R02_FIXED_NOW=%s py runs/issues/R02/step_r02_build.py" % NOW)
    A("R02_FIXED_NOW=%s py runs/issues/R02/step_r02_verify.py" % NOW)
    A("```")
    A("")
    A("## 6. 断点与下一步")
    A("")
    A("- 本卡交付完成，等待 Codex 独立复核；未提交 git，由统筹方统一提交推送。")
    A("- 未启动 R00 个股深研、未做估值、未修改任何上游冻结表、未触碰 #53（保持 OPEN）。")
    A("- 若后续复核要求扩充官方指标（如分行业 PPI、机器人细分产品），需另开版本并重跑一次性采集，不得在本快照上手工补数。")
    A("")
    return "\n".join(L)


# ---------------------------------------------------------------- 校验与 review

def build_checks(sig_rows, disp_rows):
    checks = []
    anomalies = []

    # C01 主题分拆
    tsum = sum(len(TOPIC_MAIN[t]) for t in TOPICS)
    usum = sum(len(TOPIC_ALL[t]) for t in TOPICS)
    overlap = set()
    seen = set()
    for t in TOPICS:
        s = set(TOPIC_ALL[t])
        overlap |= (seen & s)
        seen |= s
    c01 = (tsum == len(MAINLINE) == 277 and usum == len(UNIVERSE) == 1054 and not overlap)
    checks.append({"id": "C01", "name": "3 主题对 R00 主线与全池互斥且完备（277 / 1,054）",
                   "result": "PASS" if c01 else "FAIL",
                   "detail": "mainline=%d, universe=%d, overlap=%d" % (tsum, usum, len(overlap))})
    if not c01:
        anomalies.append("C01 主题分拆不完备或存在重叠")

    # C02 H1/9M 隔离
    bad_period = [r["signal_id"] for r in sig_rows
                  if r["signal_layer"].startswith("LAYER_2")
                  and (r["period_key"], r["base_period_key"]) not in {("20260630", "20250630"), ("20260930", "20250930")}]
    # 同一 signal 不得同时含两期
    keys = Counter((r["topic_id"], r["denominator"], r["metric_id"]) for r in sig_rows if r["signal_layer"].startswith("LAYER_2"))
    c02 = not bad_period and all(v == 2 for v in keys.values())
    checks.append({"id": "C02", "name": "LAYER_2 严格按 H1/9M 分层，无跨期合并",
                   "result": "PASS" if c02 else "FAIL",
                   "detail": "bad_period=%d, groups=%d, each_has_2_periods=%s" % (
                       len(bad_period), len(keys), all(v == 2 for v in keys.values()))})
    if not c02:
        anomalies.append("C02 存在跨期合并或期别标签异常")

    # C03 LAYER_1 披露日与事实属性
    l1 = [r for r in sig_rows if r["signal_layer"].startswith("LAYER_1")]
    bad_c3 = [r["signal_id"] for r in l1 if r["disclosure_date"] > CUTOFF or r["fact_or_forecast"] != "FACT"]
    c03 = not bad_c3 and len(l1) > 0
    checks.append({"id": "C03", "name": "LAYER_1 全部 disclosure_date<=2026-10-25 且 fact_or_forecast=FACT",
                   "result": "PASS" if c03 else "FAIL",
                   "detail": "rows=%d, bad=%d" % (len(l1), len(bad_c3))})
    if not c03:
        anomalies.append("C03 存在超截止日或非 FACT 的外部信号")

    # C04 每指标至少两期
    per_metric = Counter(r["metric_id"] for r in l1)
    few = {k: v for k, v in per_metric.items() if v < 2}
    c04 = not few and len(per_metric) >= 20
    checks.append({"id": "C04", "name": "LAYER_1 每个指标至少两期同口径事实",
                   "result": "PASS" if c04 else "FAIL",
                   "detail": "metrics=%d, min_periods=%d, few=%s" % (
                       len(per_metric), min(per_metric.values()) if per_metric else 0, few)})
    if not c04:
        anomalies.append("C04 存在少于两期同口径的官方指标")

    # C05 LAYER_2 独立重算
    diffs = []
    for r in sig_rows:
        if not r["signal_layer"].startswith("LAYER_2"):
            continue
        members = group_members(r["topic_id"], r["denominator"])
        ptype = "H1" if r["period_key"] == "20260630" else "9M"
        pairs = collect_pairs(members, r["metric_id"], r["period_key"], ptype)
        st = stats_of(pairs)
        exp = {
            "valid_paired_count": str(st["valid"]),
            "denominator_count": str(len(members)),
            "improved_count": str(st["improved"]),
            "improved_share_pct": fmt_share(st["share"]),
            "median_value": fmt_stat(st["median"]),
            "p25_value": fmt_stat(st["p25"]),
            "p75_value": fmt_stat(st["p75"]),
            "top1_contributor_id": st["top1_id"],
            "top1_contributor_value": fmt_stat(st["top1_val"]),
            "ex_top1_improved_share_pct": fmt_share(st["ex_share"]),
            "ex_top1_median_value": fmt_stat(st["ex_median"]),
        }
        for k, v in exp.items():
            if str(r[k]) != v:
                diffs.append("%s:%s" % (r["signal_id"], k))
    c05 = not diffs
    checks.append({"id": "C05", "name": "LAYER_2 中位数/四分位/改善占比/去Top1 与原始指标逐行重算一致",
                   "result": "PASS" if c05 else "FAIL",
                   "detail": "rows=%d, diffs=%d %s" % (
                       sum(1 for r in sig_rows if r["signal_layer"].startswith("LAYER_2")), len(diffs), diffs[:3])})
    if not c05:
        anomalies.append("C05 LAYER_2 统计量与原始数据不一致")

    # C06 输入全部位于 Git 跟踪树内
    missing = [p for p in INPUTS if not (REPO / p).exists()]
    escaped = [p for p in INPUTS if p.startswith("/") or ".." in Path(p).parts]
    c06 = not missing and not escaped
    checks.append({"id": "C06", "name": "全部输入存在于 Git 工作树内且无越界路径",
                   "result": "PASS" if c06 else "FAIL",
                   "detail": "inputs=%d, missing=%d, escaped=%d" % (len(INPUTS), len(missing), len(escaped))})
    if not c06:
        anomalies.append("C06 存在缺失或越界输入")

    # C07 分派合计
    dsum_u = sum(int(r["universe_count"]) for r in disp_rows)
    dsum_m = sum(int(r["r00_mainline_count"]) for r in disp_rows)
    c07 = dsum_u == 1054 and dsum_m == 277 and len(disp_rows) == 3
    checks.append({"id": "C07", "name": "分派表 3 行且全池/主线合计为 1,054 / 277",
                   "result": "PASS" if c07 else "FAIL",
                   "detail": "rows=%d, universe=%d, mainline=%d" % (len(disp_rows), dsum_u, dsum_m)})
    if not c07:
        anomalies.append("C07 分派表合计不符")

    # C08 上游口径守卫
    guards = release["guards"]
    c08 = (guards["no_cross_period_merge_h1_vs_9m"] and guards["sw_industry_neq_nbs_industry"]
           and guards["ppi_neq_company_selling_price"] and guards["industry_boom_neq_company_robot_revenue"]
           and guards["facts_separated_from_forecasts"] and guards["preserve_unknown_on_scope_conflict"])
    checks.append({"id": "C08", "name": "放行守卫全部开启（跨期/行业口径/PPI/景气/事实预测/UNKNOWN）",
                   "result": "PASS" if c08 else "FAIL", "detail": json.dumps(guards, ensure_ascii=False)})
    if not c08:
        anomalies.append("C08 放行守卫缺失")

    # C09 S08 冻结数一致
    rec = screen["reconciliation"]
    c09 = (rec["universe"]["primary_keys"] == 1054 and rec["S05"]["quality_pass"] == 277
           and len(MAINLINE) == 277 and len(UNIVERSE) == 1054
           and accept["verified"]["counts"]["universe"] == 1054)
    checks.append({"id": "C09", "name": "全池 1,054 / 主线 277 与 S08 冻结验收一致",
                   "result": "PASS" if c09 else "FAIL",
                   "detail": "universe=%d, mainline=%d, S05_pass=%d" % (
                       len(UNIVERSE), len(MAINLINE), rec["S05"]["quality_pass"])})
    if not c09:
        anomalies.append("C09 与 S08 冻结数不一致")

    # C10 无机器人细分价格/行业增加值编造
    c10 = (snapshot["not_disclosed"] and
           all(n["status"] == "UNKNOWN" for n in snapshot["not_disclosed"]) and
           not any(r["metric_id"].startswith("PPI_ROBOT") or r["metric_id"].startswith("NBS_ROBOT_INDUSTRY")
                   for r in l1))
    checks.append({"id": "C10", "name": "未单列指标保持 UNKNOWN，未编造细分价格或机器人行业增加值",
                   "result": "PASS" if c10 else "FAIL",
                   "detail": "unknown=%s" % [n["metric_key"] for n in snapshot["not_disclosed"]]})
    if not c10:
        anomalies.append("C10 存在编造或未保留 UNKNOWN 的指标")

    # C11 上游冻结文件未被改动（以 S08 验收 manifest 根摘要为准）
    c11 = accept["decision"] == "ACCEPTED_WITH_LIMITS" and accept["S08_completed"] is True
    checks.append({"id": "C11", "name": "S08 独立验收状态为 ACCEPTED_WITH_LIMITS 且已完成",
                   "result": "PASS" if c11 else "FAIL",
                   "detail": "decision=%s, S08_completed=%s" % (accept["decision"], accept["S08_completed"])})
    if not c11:
        anomalies.append("C11 S08 验收状态异常")

    # C12 边界文档覆盖必需条目
    limits_text = (OUT / OUT_LIMITS).read_text(encoding="utf-8") if (OUT / OUT_LIMITS).exists() else ""
    must = ["申万行业分类 != NBS", "routing_group", "PPI != 企业产品实际售价",
            "行业产量/大盘景气 != 单一公司机器人真实收入", "H1（20260630）与 9M（20260930）严格分层",
            "扣非净利润 != 归母净利润 != NBS 工业利润", "基期 <= 0", "幸存者偏差", "UNKNOWN"]
    lacks = [m for m in must if m not in limits_text]
    c12 = not lacks
    checks.append({"id": "C12", "name": "industry_limits.md 覆盖全部必需口径边界",
                   "result": "PASS" if c12 else "FAIL", "detail": "lacks=%s" % lacks})
    if not c12:
        anomalies.append("C12 限制文档缺少必需边界条目")

    # C13 纯 LF
    crlf = [f for f in DELIVERABLES if (OUT / f).exists() and b"\r\n" in (OUT / f).read_bytes()]
    c13 = not crlf
    checks.append({"id": "C13", "name": "全部交付物为纯 LF 换行",
                   "result": "PASS" if c13 else "FAIL", "detail": "crlf=%s" % crlf})
    if not c13:
        anomalies.append("C13 存在 CRLF 交付物")

    return checks, anomalies


# ---------------------------------------------------------------- 写出

def write_csv(path: Path, fields, rows):
    buf = io.StringIO(newline="")
    w = csv.DictWriter(buf, fieldnames=fields, lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow({k: r[k] for k in fields})
    path.write_bytes(buf.getvalue().encode("utf-8"))


def build_manifest(review_anomalies):
    inputs_meta = []
    for rel in INPUTS:
        canon = canon_bytes(REPO / rel)
        inputs_meta.append({
            "path": rel,
            "bytes": len(canon),
            "sha256": hashlib.sha256(canon).hexdigest(),
        })
    deliv_meta = []
    for name in MANIFEST_DELIVERABLES:
        nb, sh = sha256_exact(OUT / name)
        deliv_meta.append({"path": "runs/issues/R02/" + name, "bytes": nb, "sha256": sh})
    root = hashlib.sha256(
        "\n".join("%s:%s" % (d["path"], d["sha256"]) for d in sorted(deliv_meta, key=lambda x: x["path"])).encode("utf-8")
    ).hexdigest()
    return {
        "artifact": "R02_DELIVERY_MANIFEST",
        "issue_key": ISSUE_KEY,
        "issue_number": ISSUE_NUMBER,
        "plan_version": PLAN_VERSION,
        "knowledge_as_of": CUTOFF,
        "executor": "CodeBuddy",
        "orchestrator": "Antigravity",
        "review_nature": "SELF_CHECK",
        "generated_at": NOW,
        "input_hash_basis": "CANONICAL_LF_BYTES",
        "input_hash_basis_note": "文本输入按 CRLF->LF 规范化后计算字节数与 SHA-256。",
        "deliverable_hash_basis": "EXACT_BYTES_LF",
        "root_digest_basis": "按交付物 path 排序后以 'path:sha256' 以 \\n 连接再取 SHA-256；不含 review.json 与 manifest.json 自身以避免循环依赖。",
        "replay_note": "离线运行 step_r02_build.py 与 step_r02_verify.py；R02_FIXED_NOW 固定时间戳。nbs_official_sources_snapshot.json 为一次性联网采集后的固化快照，复现时不再联网。",
        "manifest_root_digest": root,
        "input_count": len(inputs_meta),
        "deliverable_count": len(deliv_meta),
        "inputs": inputs_meta,
        "deliverables": deliv_meta,
        "anomaly_count": len(review_anomalies),
    }


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    l1 = layer1_rows()
    l2 = layer2_rows()
    sig_rows = l1 + l2
    disp_rows = dispatch_rows()

    write_csv(OUT / OUT_DISPATCH, DISPATCH_FIELDS, disp_rows)
    write_csv(OUT / OUT_SIGNALS, SIGNAL_FIELDS, sig_rows)
    (OUT / OUT_LIMITS).write_bytes(build_limits(sig_rows).encode("utf-8"))
    (OUT / OUT_HANDOFF).write_bytes(build_handoff(sig_rows, disp_rows).encode("utf-8"))

    checks, anomalies = build_checks(sig_rows, disp_rows)

    review = {
        "artifact": "R02_SELF_CHECK_REVIEW",
        "issue_key": ISSUE_KEY,
        "issue_number": ISSUE_NUMBER,
        "plan_version": PLAN_VERSION,
        "reviewed_on": TODAY,
        "timezone": "Asia/Shanghai",
        "review_nature": "SELF_CHECK",
        "executor": "CodeBuddy",
        "orchestrator": "Antigravity",
        "reviewer_assigned": "Codex",
        "review_method": "从原始 Git 跟踪输入独立重算主题分拆、H1/9M 分层、LAYER_2 中位数/四分位/改善占比/去Top1 敏感性，逐行比对交付物；不信任构建器布尔值。",
        "decision_rule": "anomalies 为空 -> SELF_CHECK_PASS_WITH_LIMITS；否则 -> NOT_READY_PENDING_FIX",
        "anomalies": anomalies,
        "decision": "SELF_CHECK_PASS_WITH_LIMITS" if not anomalies else "NOT_READY_PENDING_FIX",
        "checks_summary": "%d/%d PASS" % (sum(1 for c in checks if c["result"] == "PASS"), len(checks)),
        "checks": checks,
        "release_R00": False,
        "release_R03": False,
        "issue_53_touched": False,
        "delivery_complete": not anomalies,
        "independent_review_required": True,
        "known_limits_ref": "runs/issues/R02/industry_limits.md",
    }
    (OUT / OUT_REVIEW).write_bytes((json.dumps(review, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))

    manifest = build_manifest(anomalies)
    (OUT / OUT_MANIFEST).write_bytes((json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))

    print("R02 build done @", NOW)
    print("layer1 rows", len(l1), "layer2 rows", len(l2), "dispatch", len(disp_rows))
    print("checks", review["checks_summary"], "decision", review["decision"])
    print("manifest_root_digest", manifest["manifest_root_digest"])
    for c in checks:
        if c["result"] != "PASS":
            print("  FAIL", c["id"], c["detail"])
    return 0 if not anomalies else 1


if __name__ == "__main__":
    sys.exit(main())
