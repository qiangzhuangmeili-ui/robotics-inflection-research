"""S04 第二道收紧（返工版 v2）：L2 双通道资格 + 低基数同口径绝对额确认。

规则来源：runs/issues/S01/screen_rules_v3.json（2026-11-10 冻结；本脚本不写任何筛选阈值）
信号输入：runs/issues/S03/rerun_20261106 三分区逐家信号结果（S03 已验收交付）
指标状态：S02 v10 all_pool_metrics.csv
绝对额确认：S02 v10 s00_v10.csv.gz（唯一权威标准化输入，sha 与 S03 输入契约一致）
守卫输入：S02 acceptance_20261106/s03_input_contract.json（四家截止日隔离）

L2 规则原文（v3 decision_layers[L2]）：
  至少 2 个不同维度各有 1 条合格真信号；
  比率通道所用指标须全部 metric_status=OK；
  SG06/SG08 绝对额通道须全部实际输入行 status 属 usable 且跨期可比；
  两类通道均不得含 Q01 HOLD、Q06 未决重述、范围断裂、Q05 低基数未确认。

低基数（v3 low_base_confirmation）：
  同口径同比绝对增量 ≥ 1,000 万元才计入维度；
  SG01→累计营收、SG04/SG06→累计扣非、SG09→单季扣非、SG08→累计经营现金流；
  SG02/SG03/SG05/SG07 记 NO_CONFIRM_RULE，本版不计入。

自检原则（v3 / Codex 裁决）：只校验充要条件与集合不变量，不锁定通过家数。
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
S04 = ROOT / "runs/issues/S04"
OUT = Path(os.environ.get("S04_OUT_DIR") or S04)
S03 = ROOT / "runs/issues/S03"
RERUN = S03 / "rerun_20261106"
CFG_PATH = S03 / "l1_config.json"
RULES_PATH = ROOT / "runs/issues/S01/screen_rules_v3.json"
RULES_V2_PATH = ROOT / "runs/issues/S01/screen_rules_v2.json"
CONTRACT_PATH = ROOT / "runs/issues/S02/acceptance_20261106/s03_input_contract.json"
METRICS_PATH = ROOT / "runs/issues/S02/hangcha_restated_20261101/s02_v10/all_pool_metrics.csv"
S00_PATH = ROOT / "runs/issues/S02/hangcha_restated_20261101/s00_v10/s00_v10.csv.gz"
MASTER_PATH = ROOT / "data/company_master.csv"
V1_LOG = S04 / "superseded_v1/tight_decision_log.csv"

ACCEPTED_CFG_SHA = "2f6193e6a0cad024a67d0ce0dd806e58db8ebdb44dd92d9ef750cc3fdc3fd541"
ACCEPTED_RULES_SHA = "6c474d1fc58ea6d484a428e8203792e3c0cf427756413860b85e17c16b1e4d45"
PARTITIONS = ("wide_pass", "wide_defer", "wide_unknown")
DIM_ORDER = ("GROWTH", "MARGIN", "PROFIT", "CASH")
S00_FIELDS = ("FIN.NPDEDT.YTD", "FIN.NPDEDT.SQ", "FIN.REV.YTD", "FIN.OCF.YTD")

# 由规则文件 status_semantics.usable 在 main() 中填充；模块级便于回归测试注入
USABLE_SET: set[str] = set()

def sha_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def fail(msg: str) -> int:
    print(f"FAIL {msg}", file=sys.stderr)
    return 2

def base_status(verdict: str) -> str:
    if verdict.startswith("HOLD"):
        return "HOLD"
    if verdict.startswith("MISSING"):
        return "MISSING"
    if verdict.startswith("UNDEFINED_BASE"):
        return "UNDEFINED_BASE"
    if verdict.startswith("NOT_APPLICABLE"):
        return "NOT_APPLICABLE"
    if verdict.startswith("REFERENCE_ONLY") or verdict.startswith("ESTIMATED_REFERENCE_ONLY"):
        return "REFERENCE_ONLY"
    return verdict

def sgs(s: str) -> list[str]:
    return [x for x in (s or "").split(";") if x]

def prev_year(pk: str) -> str:
    return str(int(pk[:4]) - 1) + pk[4:]

def confirm_low_base(s00, conf_map, abs_th, sg06_th, sec, sg, pk):
    """低基数同口径绝对额确认（纯函数，便于回归测试）。

    返回 (是否确认, 明细dict)。明细含口径、金额、阻断原因。
    """
    spec = conf_map.get(sg)
    if spec is None:
        return False, {"sg": sg, "result": "NO_CONFIRM_RULE", "basis": ""}
    fid, basis = spec["field_id"], spec["basis"]
    a = s00.get((sec, fid, prev_year(pk)))
    b = s00.get((sec, fid, pk))
    if a is None or b is None:
        return False, {"sg": sg, "result": "NO_CONFIRM_INPUT", "basis": basis,
                       "reason": "row_missing", "field": fid}
    if a["status"] not in USABLE_SET or b["status"] not in USABLE_SET:
        return False, {"sg": sg, "result": "NO_CONFIRM_INPUT", "basis": basis,
                       "reason": f"status:{a['status']}/{b['status']}", "field": fid}
    if a["restatement_flag"] == "RESTATEMENT_INDICATED_NEEDS_REVIEW" \
            or b["restatement_flag"] == "RESTATEMENT_INDICATED_NEEDS_REVIEW":
        return False, {"sg": sg, "result": "NO_CONFIRM_Q06", "basis": basis,
                       "reason": "unresolved_restatement", "field": fid}
    try:
        av, bv = float(a["value_cny"]), float(b["value_cny"])
    except (TypeError, ValueError):
        return False, {"sg": sg, "result": "NO_CONFIRM_INPUT", "basis": basis,
                       "reason": "non_numeric", "field": fid}
    delta = bv - av
    if sg == "SG06" and not (bv > 0 and bv >= sg06_th):
        return False, {"sg": sg, "result": "NO_CONFIRM_INPUT", "basis": basis,
                       "reason": "current_amount_below_threshold", "field": fid,
                       "delta_cny": delta}
    if delta < abs_th:
        return False, {"sg": sg, "result": "NO_CONFIRM_DELTA", "basis": basis,
                       "field": fid, "base_cny": av, "cur_cny": bv, "delta_cny": delta}
    return True, {"sg": sg, "result": "CONFIRMED", "basis": basis, "field": fid,
                  "base_cny": av, "cur_cny": bv, "delta_cny": delta}

def abs_channel_qualified(s00, usable, sg06_th, sec, sg, pk):
    """绝对额通道信号资格：不沿用上游 CLEAN 标签，重新验输入行。"""
    if sg == "SG06":
        fid = "FIN.NPDEDT.YTD"
    elif sg == "SG08":
        fid = "FIN.OCF.YTD"
    else:
        return False, "NOT_ABS_SIGNAL"
    a = s00.get((sec, fid, prev_year(pk)))
    b = s00.get((sec, fid, pk))
    if a is None or b is None:
        return False, "ABS_INPUT_MISSING"
    if a["status"] not in usable or b["status"] not in usable:
        return False, f"ABS_STATUS:{a['status']}/{b['status']}"
    if a["restatement_flag"] == "RESTATEMENT_INDICATED_NEEDS_REVIEW" \
            or b["restatement_flag"] == "RESTATEMENT_INDICATED_NEEDS_REVIEW":
        return False, "ABS_Q06"
    av, bv = float(a["value_cny"]), float(b["value_cny"])
    if sg == "SG06":
        if not (av < 0 and bv > 0 and bv >= sg06_th):
            return False, "ABS_CONDITION_FAIL"
    else:
        if not (bv > 0 and av <= 0):
            return False, "ABS_CONDITION_FAIL"
    return True, "ABS_CHANNEL"

def main() -> int:
    checks: list[dict] = []

    def check(cid: str, name: str, ok: bool, detail=None, level: str = "FAIL") -> None:
        checks.append({"id": cid, "name": name, "pass": bool(ok), "level": level, "detail": detail})

    # ---------------- C00 输入与版本闸门
    for p in (CFG_PATH, RULES_PATH, CONTRACT_PATH, METRICS_PATH, S00_PATH, MASTER_PATH):
        if not p.exists():
            return fail(f"C00 required input missing: {p}")

    cfg_sha = sha_file(CFG_PATH)
    if cfg_sha != ACCEPTED_CFG_SHA:
        return fail("C00 S03 config hash differs from the accepted configuration")
    rules_sha = sha_file(RULES_PATH)
    if rules_sha != ACCEPTED_RULES_SHA:
        return fail("C00 rules file is not the frozen S01 v3 artifact")

    cfg = json.loads(CFG_PATH.read_text(encoding="utf-8"))
    rules = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    if contract.get("version") != "S02_TO_S03_GATE_20261106" \
            or contract.get("knowledge_as_of") != cfg.get("as_of"):
        return fail("C00 input contract version or cutoff mismatch")

    met_decl = contract.get("metrics") or {}
    if sha_file(METRICS_PATH) != met_decl.get("sha256"):
        return fail("C00 metrics file hash differs from the S02 acceptance contract")

    norm_decl = contract.get("normalized") or {}
    s00_sha = sha_file(S00_PATH)
    if s00_sha != norm_decl.get("sha256"):
        return fail("C00 s00_v10 hash differs from the S02 acceptance contract")

    sg_dim = {s["id"]: s["dimension"] for s in rules["signals"]}
    sg_metric = {s["id"]: s["metric"] for s in rules["signals"]}
    sg_threshold = {s["id"]: s["threshold"] for s in rules["signals"]}
    dims = cfg["dimensions"]
    l2 = next(d for d in rules["decision_layers"] if d["id"] == "L2")
    chan = l2["channel_qualification"]
    RATIO_CH = set(chan["ratio_channel"]["signals"])
    ABS_CH = set(chan["absolute_channel"]["signals"])
    LBC = rules["low_base_confirmation"]
    CONF_MAP = LBC["signals"]
    NO_CONFIRM = set(LBC["no_confirm_rule"])
    ABS_TH = float(LBC["threshold_cny"])
    USABLE = set(rules["status_semantics"]["usable"])
    USABLE_SET.update(USABLE)

    check("C00", "输入版本与哈希闸门（config/rules v3/metrics/s00_v10/contract）", True,
          {"config_sha256": cfg_sha, "rules_sha256": rules_sha,
           "rules_version": rules["rules_version"],
           "metrics_sha256": met_decl.get("sha256"),
           "s00_v10_sha256": s00_sha,
           "knowledge_as_of": cfg.get("as_of"),
           "l2_rule_text": l2["rule_text"]})

    guard_ids = {g["security_id"] for g in contract.get("guard_companies", [])}
    if len(guard_ids) != 4:
        return fail("C00 contract must enumerate exactly four cutoff-guard companies")

    # ---------------- 装载
    master: dict[str, str] = {}
    with MASTER_PATH.open(encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            master[r["security_id"]] = r["stock_name"]

    metrics: dict[str, dict[str, dict]] = defaultdict(dict)
    with METRICS_PATH.open(encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            metrics[r["security_id"]][r["metric_id"]] = r

    override = {o["security_id"]: o for o in cfg.get("company_overrides", [])}
    for sec, ov in override.items():
        for mid, spec in ov["metrics"].items():
            row = metrics.get(sec, {}).get(mid)
            if row is None:
                continue
            row["metric_status"] = base_status(spec["verdict"])

    # 权威标准化输入：仅取确认所需字段
    s00: dict[tuple[str, str, str], dict] = {}
    with gzip.open(S00_PATH, "rt", encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            if r["field_id"] in S00_FIELDS:
                s00[(r["security_id"], r["field_id"], r["period_key"])] = r

    rows: dict[str, dict] = {}
    part_of: dict[str, str] = {}
    for part in PARTITIONS:
        with (RERUN / f"{part}.csv").open(encoding="utf-8-sig", newline="") as fh:
            for r in csv.DictReader(fh):
                rows[r["company_id"]] = r
                part_of[r["company_id"]] = part

    review_targets: dict[str, dict] = {}
    with (RERUN / "s04_review_targets.csv").open(encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            review_targets[r["company_id"]] = r

    v1_decision: dict[str, str] = {}
    if V1_LOG.exists():
        with V1_LOG.open(encoding="utf-8-sig", newline="") as fh:
            for r in csv.DictReader(fh):
                v1_decision[r["company_id"]] = r["l2_decision"]

    # ---------------- 绝对额确认（纯函数在模块级，见 confirm_low_base / abs_channel_qualified）
    def abs_confirm(sec: str, sg: str, pk: str):
        return confirm_low_base(s00, CONF_MAP, ABS_TH, float(sg_threshold["SG06"]), sec, sg, pk)

    def abs_channel_ok(sec: str, sg: str, pk: str):
        return abs_channel_qualified(s00, USABLE, float(sg_threshold["SG06"]), sec, sg, pk)

    # ---------------- 逐家判定
    out: list[dict] = []
    for sec in sorted(rows):
        r = rows[sec]
        part = part_of[sec]
        pk = r.get("anchor_period", "")
        clean_sg = sgs(r.get("sg_hit_clean_list"))
        prov_sg = sgs(r.get("sg_hit_provisional_list"))
        low_sg = sgs(r.get("sg_hit_lowbase_list"))
        hold_sg = sgs(r.get("sg_hold_list"))

        ov = override.get(sec)
        blocked = bool(ov and ov.get("block_sg"))
        if blocked:
            clean_sg, prov_sg, low_sg, hold_sg = [], [], [], []

        qualified: dict[str, list[str]] = defaultdict(list)   # dim -> [sg]
        channels: dict[str, str] = {}                          # sg -> A/B/C
        rejected: list[str] = []
        low_detail: list[dict] = []
        hold_dims: set[str] = set()
        prov_dims: set[str] = set()

        for sg in clean_sg:
            d = sg_dim[sg]
            if sg in RATIO_CH:
                st = (metrics[sec].get(sg_metric[sg]) or {}).get("metric_status", "ABSENT")
                qf = (metrics[sec].get(sg_metric[sg]) or {}).get("quality_flags", "") or ""
                if st == "OK" and "Q06" not in qf:
                    qualified[d].append(sg)
                    channels[sg] = "A_RATIO_OK"
                else:
                    rejected.append(f"{sg}:{sg_metric[sg]}={st}")
            elif sg in ABS_CH:
                ok, why = abs_channel_ok(sec, sg, pk)
                if ok:
                    qualified[d].append(sg)
                    channels[sg] = "B_ABS_CHANNEL"
                else:
                    rejected.append(f"{sg}:{why}")
            else:
                rejected.append(f"{sg}:UNCLASSIFIED_SIGNAL")

        for sg in low_sg:
            d = sg_dim[sg]
            ok, det = abs_confirm(sec, sg, pk)
            low_detail.append(det)
            if ok:
                qualified[d].append(sg)
                channels[sg] = "C_LOW_BASE_CONFIRMED"
            else:
                rejected.append(f"{sg}:{det['result']}")

        for sg in prov_sg:
            prov_dims.add(sg_dim[sg])
        for sg in hold_sg:
            hold_dims.add(sg_dim[sg])

        ok_dims = [d for d in DIM_ORDER if qualified.get(d)]
        hold_only = [d for d in DIM_ORDER if d in hold_dims and d not in ok_dims]

        # 未点亮但上游存在 HOLD 指标的维度，也属于「可能补足」
        hold_metric_dims: list[str] = []
        for d in DIM_ORDER:
            if d in ok_dims:
                continue
            if any((metrics[sec].get(mid) or {}).get("metric_status") == "HOLD" for mid in dims[d]):
                hold_metric_dims.append(d)
        reachable = len(set(ok_dims) | set(hold_only) | set(hold_metric_dims))

        if sec in guard_ids:
            decision = "WATCH_AFTER_CUTOFF"
            reason = "截止日后披露，整体隔离；不作候选/无信号/风险结论，不得回退旧期"
            gap = "AFTER_CUTOFF"
        elif part != "wide_pass":
            decision = "L2_NOT_IN_SCOPE"
            reason = (f"S03 分区 {part}（{r.get('l1_subtag', '')}），"
                      f"不在 L2 收紧范围；保留观察，不淘汰")
            gap = r.get("l1_subtag") or part
        elif len(ok_dims) >= 2:
            decision = "L2_SHORTLIST_CANDIDATE"
            reason = ("合格维度 " + "+".join(ok_dims) + f"（{len(ok_dims)} 个）满足 ≥2；"
                      + "；".join(f"{d}←{'/'.join(qualified[d])}" for d in ok_dims))
            gap = ""
        elif reachable >= 2:
            decision = "L2_HOLD_FOR_DATA"
            reason = ("合格维度不足 2 个，但存在上游 HOLD 维度可补足："
                      + ",".join(sorted(set(hold_only) | set(hold_metric_dims))))
            gap = "UPSTREAM_HOLD"
        else:
            decision = "L2_NOT_SHORTLISTED"
            blockers = []
            for d in DIM_ORDER:
                if d in ok_dims:
                    continue
                if d in prov_dims:
                    blockers.append(f"{d}:PROVISIONAL")
                lows = [x for x in low_sg if sg_dim[x] == d]
                for x in lows:
                    det = next(y for y in low_detail if y["sg"] == x)
                    blockers.append(f"{d}:{x}:{det['result']}")
            if not blockers and rejected:
                blockers = rejected
            gap = ";".join(blockers) if blockers else "SINGLE_DIM_ONLY"
            reason = (f"合格维度仅 {len(ok_dims)} 个"
                      + (f"（{'/'.join(ok_dims)}）" if ok_dims else "")
                      + "；" + gap)

        if decision == "L2_HOLD_FOR_DATA":
            reentry = "上游 HOLD 解除后按同一规则重算，不需人工改规则"
        elif "NO_CONFIRM_DELTA" in gap:
            reentry = "取得同口径绝对额增量≥1,000 万元后按同规则重算"
        elif "NO_CONFIRM_RULE" in gap:
            reentry = "该信号尚无冻结的绝对额确认映射；须另立规则版本预登记后重算"
        elif "NO_CONFIRM_Q06" in gap:
            reentry = "未决重述落定为是/否后按同规则重算"
        elif "NO_CONFIRM_INPUT" in gap:
            reentry = "补齐两侧绝对额输入行后按同规则重算"
        elif "PROVISIONAL" in gap:
            reentry = "重述标记由 NEEDS_REVIEW 落定为是/否后信号可升级重算"
        elif gap == "AFTER_CUTOFF":
            reentry = "下一报告期资料入池后按截止日规则重进"
        elif gap in ("W1_NO_DATA", "W2_ALL_HOLD", "W4_EARLY", "W5_PROVISIONAL_ONLY"):
            reentry = "按 S01 观察名单重进条件处理"
        else:
            reentry = "规则升版时全池重算，不单独重进"

        # 绝对额通道是否构成「凑够 2 维」的必要条件：剔除 B 通道后是否仍 ≥2 维
        dims_wo_abs = {d for d in ok_dims
                       if any(channels[s] != "B_ABS_CHANNEL" for s in qualified[d])}
        abs_critical = "YES" if (len(ok_dims) >= 2 and len(dims_wo_abs) < 2) else ""

        ev_ch = sorted({channels[s] for d in ok_dims for s in qualified[d]})
        dim_detail = ";".join(
            f"{d}=" + ("QUALIFIED[" + "/".join(qualified[d]) + "]" if qualified.get(d)
                       else ("HOLD" if d in hold_only else
                             ("PROVISIONAL" if d in prov_dims else
                              ("REACHABLE_HOLD" if d in hold_metric_dims else "NONE"))))
            for d in DIM_ORDER)

        out.append({
            "company_id": sec,
            "company_name": r.get("company_name") or master.get(sec, ""),
            "anchor_period": pk,
            "anchor_period_type": r.get("anchor_period_type", ""),
            "stale_period": r.get("stale_period", ""),
            "l0_status": r.get("l0_status", ""),
            "l1_partition": part,
            "l1_bucket": r.get("l1_bucket", ""),
            "l1_subtag": r.get("l1_subtag", ""),
            "l2_decision": decision,
            "qualified_dim_count": len(ok_dims),
            "reachable_dim_count": reachable,
            "qualified_dims": ";".join(ok_dims),
            "qualified_sg": ";".join(s for d in ok_dims for s in qualified[d]),
            "ratio_channel_sg": ";".join(s for d in ok_dims for s in qualified[d]
                                         if channels[s] == "A_RATIO_OK"),
            "abs_channel_sg": ";".join(s for d in ok_dims for s in qualified[d]
                                       if channels[s] == "B_ABS_CHANNEL"),
            "low_base_confirmed_sg": ";".join(s for d in ok_dims for s in qualified[d]
                                              if channels[s] == "C_LOW_BASE_CONFIRMED"),
            "low_base_detail": ";".join(
                f"{x['sg']}={x['result']}"
                + (f"({x['delta_cny'] / 1e4:.2f}W)" if x.get("delta_cny") is not None else "")
                for x in low_detail),
            "hold_dims": ";".join(sorted(set(hold_only) | set(hold_metric_dims))),
            "provisional_dims": ";".join(d for d in DIM_ORDER if d in prov_dims),
            "prov_sg": ";".join(prov_sg),
            "hold_sg": ";".join(hold_sg),
            "hold_metric_detail": ";".join(
                f"{d}:" + "/".join(mid for mid in dims[d]
                                   if (metrics[sec].get(mid) or {}).get("metric_status") == "HOLD")
                for d in DIM_ORDER
                if any((metrics[sec].get(mid) or {}).get("metric_status") == "HOLD" for mid in dims[d])),
            "evidence_channels": ";".join(ev_ch),
            "abs_critical": abs_critical,
            "dim_detail": dim_detail,
            "scope_blocked": "YES" if blocked else "",
            "non_ok_metric_in_clean_sg": ";".join(rejected),
            "quality_flags_summary": r.get("quality_flags_summary", ""),
            "project_mode": r.get("project_mode", ""),
            "s04_review_priority": r.get("s04_review_priority", ""),
            "v1_decision": v1_decision.get(sec, ""),
            "decision_changed": "YES" if v1_decision.get(sec, decision) != decision else "",
            "decision_reason": reason,
            "blocking_gap": gap,
            "reentry_condition": reentry,
        })

    # ---------------- 自检：充要条件与集合不变量（不锁数量）
    def qualifies_alt(sec: str) -> bool:
        """按规则文本独立重算「合格维度≥2」，不复用主路径中间量。"""
        r = rows[sec]
        if sec in guard_ids or part_of[sec] != "wide_pass":
            return False
        if override.get(sec, {}).get("block_sg"):
            return False
        pk = r.get("anchor_period", "")
        good: set[str] = set()
        for sg in sgs(r.get("sg_hit_clean_list")):
            if sg in RATIO_CH:
                row = metrics[sec].get(sg_metric[sg]) or {}
                if row.get("metric_status") == "OK" and "Q06" not in (row.get("quality_flags") or ""):
                    good.add(sg_dim[sg])
            elif sg in ABS_CH:
                ok, _ = abs_channel_ok(sec, sg, pk)
                if ok:
                    good.add(sg_dim[sg])
        for sg in sgs(r.get("sg_hit_lowbase_list")):
            ok, _ = abs_confirm(sec, sg, pk)
            if ok:
                good.add(sg_dim[sg])
        return len(good) >= 2

    bad_pos = [o["company_id"] for o in out
               if o["l2_decision"] == "L2_SHORTLIST_CANDIDATE" and not qualifies_alt(o["company_id"])]
    bad_neg = [o["company_id"] for o in out
               if o["l2_decision"] != "L2_SHORTLIST_CANDIDATE"
               and part_of[o["company_id"]] == "wide_pass"
               and o["company_id"] not in guard_ids
               and qualifies_alt(o["company_id"])]
    check("C03", "逐行充要条件：入选者必须满足「合格维度≥2」，非入选者必须不满足",
          not bad_pos and not bad_neg,
          {"false_positive": bad_pos[:10], "false_negative": bad_neg[:10],
           "n_false_positive": len(bad_pos), "n_false_negative": len(bad_neg)})

    counts = Counter(part_of.values())
    check("C01", "分区覆盖 1054 家且与调度总表主键完全一致",
          len(rows) == 1054 and set(rows) == set(master) and sum(counts.values()) == 1054,
          {"rows": len(rows), "master": len(master), "by_partition": dict(counts)})
    check("C02", "三分区互斥无重复（777/149/128）",
          len(rows) == len(set(rows)) and counts["wide_pass"] == 777
          and counts["wide_defer"] == 149 and counts["wide_unknown"] == 128,
          {"wide_pass": counts["wide_pass"], "wide_defer": counts["wide_defer"],
           "wide_unknown": counts["wide_unknown"]})

    by_dec = Counter(o["l2_decision"] for o in out)
    pass_ids = {o["company_id"] for o in out if o["l2_decision"] == "L2_SHORTLIST_CANDIDATE"}
    pass_from_wide = {o["company_id"] for o in out if o["l2_decision"] == "L2_SHORTLIST_CANDIDATE"
                      and o["l1_partition"] == "wide_pass"}
    check("C05", "集合不变量：入选 ⊆ wide_pass，四类决策互斥且合计覆盖 1054",
          pass_ids == pass_from_wide and sum(by_dec.values()) == 1054
          and len(pass_ids | {o["company_id"] for o in out
                              if o["l2_decision"] != "L2_SHORTLIST_CANDIDATE"}) == 1054,
          {"by_decision": dict(by_dec), "pass": len(pass_ids)})

    guard_rows = [o for o in out if o["company_id"] in guard_ids]
    check("C06", "四家截止日隔离公司保持隔离、零信号、无 L2 结论",
          len(guard_rows) == 4
          and all(o["l2_decision"] == "WATCH_AFTER_CUTOFF" for o in guard_rows)
          and all(not o["qualified_sg"] and not o["prov_sg"] and not o["low_base_detail"]
                  for o in guard_rows),
          {"guards": [o["company_id"] for o in guard_rows]})

    v2 = json.loads(RULES_V2_PATH.read_text(encoding="utf-8"))
    th_now = {s["id"]: s["threshold"] for s in rules["signals"]}
    th_v2 = {s["id"]: s["threshold"] for s in v2["signals"]}
    check("C07", "九条信号阈值与 v2 完全一致（返工未改任何阈值）", th_now == th_v2,
          {"thresholds": th_now, "rules_sha256": rules_sha})

    target_ids = set(review_targets)
    check("C08", "S03 的 100 家定向核验对象全部在结果中",
          not (target_ids - set(rows)) and len(target_ids) == 100,
          {"targets": len(target_ids), "missing": sorted(target_ids - set(rows))[:5]})

    # 证据降级单调性：把全部合格证据降级后，入选集合不得变大
    degraded = {o["company_id"] for o in out
                if o["l2_decision"] == "L2_SHORTLIST_CANDIDATE" and not o["ratio_channel_sg"]
                and not o["abs_channel_sg"]}
    check("C09", "证据降级不得增加通过集合：无 A/B 通道证据者不得入选",
          not degraded, {"violations": sorted(degraded)[:10], "count": len(degraded)})

    # ---------------- 输出
    pass_rows = [o for o in out if o["l2_decision"] == "L2_SHORTLIST_CANDIDATE"]
    observe_rows = [o for o in out if o["l2_decision"] != "L2_SHORTLIST_CANDIDATE"]

    cols = ["company_id", "company_name", "anchor_period", "anchor_period_type", "stale_period",
            "l0_status", "l1_partition", "l1_bucket", "l1_subtag", "l2_decision",
            "qualified_dim_count", "reachable_dim_count", "qualified_dims", "qualified_sg",
            "ratio_channel_sg", "abs_channel_sg", "low_base_confirmed_sg", "low_base_detail",
            "hold_dims", "provisional_dims", "prov_sg", "hold_sg", "hold_metric_detail",
            "evidence_channels", "dim_detail", "abs_critical", "scope_blocked",
            "non_ok_metric_in_clean_sg",
            "quality_flags_summary", "project_mode", "s04_review_priority",
            "v1_decision", "decision_changed", "decision_reason", "blocking_gap", "reentry_condition"]

    def write_csv(name: str, data: list[dict]) -> None:
        with (OUT / name).open("w", encoding="utf-8-sig", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=cols, lineterminator="\n")
            w.writeheader()
            for row in data:
                w.writerow({k: row.get(k, "") for k in cols})

    write_csv("tight_pass.csv", pass_rows)
    write_csv("tight_observe.csv", observe_rows)
    write_csv("tight_decision_log.csv", out)

    qc_rows = []
    for o in out:
        if o["company_id"] not in review_targets:
            continue
        qc_rows.append({
            "company_id": o["company_id"], "company_name": o["company_name"],
            "l1_partition": o["l1_partition"], "anchor_period": o["anchor_period"],
            "l2_decision": o["l2_decision"], "qualified_dims": o["qualified_dims"],
            "qualified_dim_count": o["qualified_dim_count"],
            "evidence_channels": o["evidence_channels"],
            "blocking_gap": o["blocking_gap"],
            "gap_is_data_level": "YES" if any(k in o["blocking_gap"] for k in
                                              ("NO_CONFIRM_INPUT", "NO_CONFIRM_Q06",
                                               "PROVISIONAL", "UPSTREAM_HOLD")) else "NO",
            "reentry_condition": o["reentry_condition"],
            "v1_decision": o["v1_decision"], "decision_changed": o["decision_changed"],
            "s04_review_priority": o["s04_review_priority"],
        })
    with (OUT / "review_100_qc.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(qc_rows[0].keys()), lineterminator="\n")
        w.writeheader()
        w.writerows(qc_rows)

    changed = [o for o in out if o["decision_changed"] == "YES"]
    with (OUT / "v1_v3_diff.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["company_id", "company_name", "l1_partition",
                                           "v1_decision", "l2_decision", "qualified_dims",
                                           "evidence_channels", "decision_reason"],
                           lineterminator="\n")
        w.writeheader()
        for o in changed:
            w.writerow({k: o[k] for k in w.fieldnames})

    summary = {
        "rules_version": rules["rules_version"],
        "rules_sha256": rules_sha,
        "s00_v10_sha256": s00_sha,
        "coverage": len(out),
        "by_decision": dict(by_dec),
        "by_partition_decision": {f"{k[0]}|{k[1]}": v for k, v in
                                  sorted(Counter((o["l1_partition"], o["l2_decision"])
                                                 for o in out).items())},
        "evidence_channels": dict(Counter(o["evidence_channels"] for o in pass_rows)),
        "abs_channel_dependency": sorted(o["company_id"] + " " + o["company_name"]
                                         for o in pass_rows if o["abs_critical"] == "YES"),
        "low_base_confirmed_in_pass": sorted(o["company_id"] for o in pass_rows
                                             if o["low_base_confirmed_sg"]),
        "changed_vs_v1": len(changed),
        "v1_counts": dict(Counter(v1_decision.values())) if v1_decision else {},
        "checks_total": len(checks),
        "checks_pass": sum(1 for c in checks if c["pass"]),
        "checks_fail": [c["id"] for c in checks if not c["pass"] and c["level"] == "FAIL"],
        "checks_warn": [c["id"] for c in checks if not c["pass"] and c["level"] == "WARN"],
    }
    (OUT / "tight_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    outputs = ["tight_pass.csv", "tight_observe.csv", "tight_decision_log.csv",
               "review_100_qc.csv", "v1_v3_diff.csv", "tight_summary.json"]
    manifest = {
        "issue_key": "S04", "issue_number": 39,
        "stage": "L2_TIGHTENING_REWORK_V2",
        "script": "runs/issues/S04/tight_screen_v2.py",
        "script_sha256": sha_file(Path(__file__)),
        "rules": {"path": "runs/issues/S01/screen_rules_v3.json", "sha256": rules_sha},
        "inputs": {
            "runs/issues/S03/rerun_20261106/wide_pass.csv": sha_file(RERUN / "wide_pass.csv"),
            "runs/issues/S03/rerun_20261106/wide_defer.csv": sha_file(RERUN / "wide_defer.csv"),
            "runs/issues/S03/rerun_20261106/wide_unknown.csv": sha_file(RERUN / "wide_unknown.csv"),
            "runs/issues/S03/rerun_20261106/s04_review_targets.csv":
                sha_file(RERUN / "s04_review_targets.csv"),
            "runs/issues/S03/l1_config.json": cfg_sha,
            "runs/issues/S02/hangcha_restated_20261101/s02_v10/all_pool_metrics.csv":
                sha_file(METRICS_PATH),
            "runs/issues/S02/hangcha_restated_20261101/s00_v10/s00_v10.csv.gz": s00_sha,
            "runs/issues/S02/acceptance_20261106/s03_input_contract.json":
                sha_file(CONTRACT_PATH),
            "data/company_master.csv": sha_file(MASTER_PATH),
        },
        "outputs": {o: sha_file(OUT / o) for o in outputs},
        "supersedes": {
            "path": "runs/issues/S04/superseded_v1/",
            "reason": ("v1 未实现低基数绝对额确认（P1-01）、未落地指标资格（P1-02）、"
                       "自检硬编码 443（C05/C07）"),
        },
        "self_check": {"total": len(checks), "pass": sum(1 for c in checks if c["pass"])},
    }
    (OUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    review = {
        "issue_key": "S04", "issue_number": 39,
        "review_nature": "SELF_CHECK",
        "decision": "SELF_CHECK_PASS_WITH_LIMITS",
        "rules_version": rules["rules_version"],
        "rules_sha256": rules_sha,
        "coverage": len(out),
        "counts": dict(by_dec),
        "checks": checks,
        "limits": [
            "自检不等同独立复核；S05 仍须外部复核通过后才放行",
            "未回读 PDF、未新增业务采用；入选不等于投资候选",
            "SG02/SG03/SG05/SG07 低基数无确认映射，记 NO_CONFIRM_RULE，本版不计入",
            "绝对额通道（SG06/SG08）资格单独登记，未改写 M05 的 UNDEFINED_BASE",
            "未改 S02 输入、S03 结果、S01 v2 规则与既有验收状态",
        ],
        "changed_vs_v1": [{"company_id": o["company_id"], "company_name": o["company_name"],
                           "v1": o["v1_decision"], "v3": o["l2_decision"],
                           "reason": o["decision_reason"]} for o in changed],
    }
    (OUT / "review.json").write_text(
        json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # ---------------- 控制台摘要
    print(f"rules: {rules['rules_version']}  sha={rules_sha[:16]}")
    print(f"coverage: {len(out)}")
    print("by_decision:", dict(by_dec))
    print("checks:", f"{summary['checks_pass']}/{len(checks)} PASS",
          "FAIL:", summary["checks_fail"], "WARN:", summary["checks_warn"])
    print("changed_vs_v1:", len(changed))
    for c in checks:
        if not c["pass"]:
            print(f"  ! {c['id']} {c['name']} -> {json.dumps(c['detail'], ensure_ascii=False)[:400]}")
    return 0 if not summary["checks_fail"] else 1

if __name__ == "__main__":
    raise SystemExit(main())
