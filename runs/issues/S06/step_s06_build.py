# -*- coding: utf-8 -*-
"""
S06 (#41) Deterministic Builder:
  - early_stage_watch.csv
  - missing_data_watch.csv
  - watch_reentry_rules.md
  - handoff.md
  - manifest.json
  - review.json

Scope:
  Strictly follows runs/issues/S06/release_20261122.json,
  runs/issues/S06/handoff_from_s05_20261122.md,
  and data/methodology_decision_20261107.json (METHOD_20261107_LEADING_INDICATORS).
  Reuses existing traceable evidence only; no new full-pool scraping or deep research.
"""
import csv
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
OUT = REPO / "runs" / "issues" / "S06"
NOW = datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")

KNOWLEDGE_AS_OF = "2026-10-25"
PLAN_VERSION = "20261026_collection_first_v2"
AUX_METHOD_VERSION = "S06_AUX_LEAD_V1"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_csv(rel: str):
    with open(REPO / rel, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def clean_str(val) -> str:
    if val is None:
        return ""
    return " ".join(str(val).replace("\r", " ").replace("\n", " ").split()).strip()


def truncate(s: str, n: int = 180) -> str:
    s = clean_str(s)
    return s if len(s) <= n else s[: n - 3] + "..."


def main():
    # ------------------------------------------------------------------
    # 1. Load frozen baselines & verify primary key conservation (1,054)
    # ------------------------------------------------------------------
    master_rows = load_csv("data/company_master.csv")
    master = {r["security_id"]: r for r in master_rows}

    s05_pass_rows = load_csv("runs/issues/S05/quality_pass.csv")
    s05_obs_rows = load_csv("runs/issues/S05/quality_observe.csv")
    s05_776_rows = load_csv("runs/issues/S05/observe_pool_preserved_776.csv")

    s05_pass = {r["security_id"]: r for r in s05_pass_rows}
    s05_obs = {r["security_id"]: r for r in s05_obs_rows}
    s05_776 = {r["security_id"]: r for r in s05_776_rows}
    s05_mainline_278 = set(s05_pass) | set(s05_obs)

    assert len(master) == 1054, f"master={len(master)}"
    assert len(s05_pass) == 277, f"s05_pass={len(s05_pass)}"
    assert len(s05_obs) == 1, f"s05_obs={len(s05_obs)}"
    assert len(s05_776) == 776, f"s05_776={len(s05_776)}"
    assert not (set(s05_pass) & set(s05_obs))
    assert not (s05_mainline_278 & set(s05_776))
    assert (s05_mainline_278 | set(s05_776)) == set(master)

    # Verify S02 metrics SHA-256
    s02_rel = "runs/issues/S02/hangcha_restated_20261101/s02_v10/all_pool_metrics.csv"
    s02_sha = sha256_file(REPO / s02_rel)
    assert s02_sha == "3091b0bb82a3e3114d7f338595c40d82c842ce47aa8802b141a6ce8ec2232953", f"S02 sha mismatch: {s02_sha}"

    s02_rows = load_csv(s02_rel)
    assert len(s02_rows) == 12648
    s02_by_co = defaultdict(list)
    s02_status_by_co = defaultdict(Counter)
    for r in s02_rows:
        sid = r["security_id"]
        s02_by_co[sid].append(r)
        s02_status_by_co[sid][r["metric_status"]] += 1

    # Load S04 tight_decision_log for supplementary context
    s04_log = {r["company_id"]: r for r in load_csv("runs/issues/S04/tight_decision_log.csv")}

    # Load A04R keyword_originals.jsonl (locator ONLY, not verified business fact)
    a04r_kw_by_co = defaultdict(list)
    for line in (REPO / "runs/issues/A04R/keyword_originals.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        obj = json.loads(line)
        a04r_kw_by_co[obj["security_id"]].append(obj)

    # ------------------------------------------------------------------
    # 2. Load ALL existing traceable evidence registers
    # ------------------------------------------------------------------
    # Archive 53 adopted (4 sub-batches)
    archive_batches = [
        (
            "ARCHIVE_R1_BATCH01",
            "archive/R1_batch01_parent_reviewed_20261024/classification_reviewed.csv",
            "archive/R1_batch01_parent_reviewed_20261024/product_line_stages.csv",
            "archive/R1_batch01_parent_reviewed_20261024/evidence_register.csv",
        ),
        (
            "ARCHIVE_R1_02A",
            "archive/R1_02A_parent_reviewed_20261024/classification_reviewed.csv",
            "archive/R1_02A_parent_reviewed_20261024/product_line_stages_reviewed.csv",
            "archive/R1_02A_parent_reviewed_20261024/evidence_register_reviewed.csv",
        ),
        (
            "ARCHIVE_R1_02A_SUPP",
            "archive/02A_supplement/classification_reviewed.csv",
            "archive/02A_supplement/product_line_stages_reviewed.csv",
            "archive/02A_supplement/evidence_register_reviewed.csv",
        ),
        (
            "ARCHIVE_R1_02B",
            "archive/02B/classification_reviewed.csv",
            "archive/02B/product_line_stages_reviewed.csv",
            "archive/02B/evidence_register_reviewed.csv",
        ),
    ]

    arch_cls = {}
    arch_pls = defaultdict(list)
    arch_ev_by_id = {}
    arch_ev_by_co = defaultdict(list)
    arch_pkg_by_co = {}

    for pkg_tag, cls_p, pls_p, ev_p in archive_batches:
        for r in load_csv(cls_p):
            sid = r["security_id"]
            arch_cls[sid] = (pkg_tag, r)
            arch_pkg_by_co[sid] = pkg_tag
        for r in load_csv(pls_p):
            sid = r["security_id"]
            arch_pls[sid].append((pkg_tag, r))
            arch_pkg_by_co.setdefault(sid, pkg_tag)
        for r in load_csv(ev_p):
            eid = r["evidence_id"]
            arch_ev_by_id[eid] = (pkg_tag, r)
            arch_ev_by_co[r["security_id"]].append((pkg_tag, r))

    # Archive early samples (10)
    early_samp_prop = {r["security_id"]: r for r in load_csv("archive/early_sample_proposals.csv")}
    early_samp_ev = {r["security_id"]: r for r in load_csv("archive/early_sample_evidence.csv")}

    # Packages B00 / C00 / D00
    c00_scr = {r["security_id"]: r for r in load_csv("packages/C00_PILOT_01/results/screening.csv")}
    c00_ev = defaultdict(list)
    for r in load_csv("packages/C00_PILOT_01/results/evidence.csv"):
        c00_ev[r["security_id"]].append(r)

    b00_scr = {}
    b00_ev = defaultdict(list)
    for bpkg in ["B00_SOURCE_01", "B00_SOURCE_02"]:
        for r in load_csv(f"packages/{bpkg}/results/screening.csv"):
            b00_scr[r["security_id"]] = (bpkg, r)
        for r in load_csv(f"packages/{bpkg}/results/evidence.csv"):
            b00_ev[r["security_id"]].append((bpkg, r))

    # ------------------------------------------------------------------
    # 3. Build early_stage_watch.csv (strictly non-mainline 776, evidence-gated)
    # ------------------------------------------------------------------
    # Explicit exclusions among reviewed non-mainline companies (no verified robot R&D/product fact):
    REVIEWED_EXCLUDED_NON_MAINLINE = {
        "BJ:920198": ("B00_SOURCE_01", "2025年报及2026H1全文未命中机器人关键词，主业为交通监控信息化，无机器人产品或研发事实"),
        "BJ:920263": ("B00_SOURCE_01", "2025年报仅披露战略合作意向及唐山地块储备，无研发成果、样机、送样或合同事实"),
        "BJ:920002": ("ARCHIVE_EARLY_SAMPLE", "2024年报抽查段落仅列叉车轴承与回转支承，未见机器人专属产品或研发证据（证据不足记UNKNOWN）"),
        "SH:600699": ("ARCHIVE_R1_02B", "2025新设并表子公司未见产品或收入，人形机器人关联主体为非并表关联方，无上市公司产品/研发事实"),
        "SH:603466": ("ARCHIVE_R1_02B", "仅2026经营计划与文旅合作探索，未核实已完成的研发、样机或产品事实"),
        "SH:688327": ("ARCHIVE_R1_02B", "前瞻生态布局，无自研机器人本体/产品/收入；财报所提机器人为RPA软件"),
    }

    # Helper to rank stages for primary fact tier
    STAGE_PRIORITY = {"S0": 1, "S1": 2, "S2": 3, "S3": 4, "S4": 5, "UNKNOWN": 9}

    def pick_archive_evidence(sid, lines):
        # Prefer evidence IDs referenced by the selected lines
        eids = []
        for _, l in lines:
            raw = clean_str(l.get("stage_evidence_ids", ""))
            for eid in raw.replace(",", ";").split(";"):
                eid = eid.strip()
                if eid and eid not in eids:
                    eids.append(eid)
        ev_objs = [arch_ev_by_id[e][1] for e in eids if e in arch_ev_by_id]
        if not ev_objs and sid in arch_ev_by_co:
            ev_objs = [x[1] for x in arch_ev_by_co[sid][:2]]
            eids = [clean_str(x.get("evidence_id", "")) for x in ev_objs]
        urls = []
        dates = []
        pages = []
        quotes = []
        for eo in ev_objs[:3]:
            u = clean_str(eo.get("primary_url", ""))
            if u and u not in urls:
                urls.append(u)
            d = clean_str(eo.get("published_on", ""))
            if d and d not in dates:
                dates.append(d)
            pg = clean_str(eo.get("page_or_section", ""))
            if pg and pg not in pages:
                pages.append(pg)
            q = clean_str(eo.get("quoted_excerpt", "") or eo.get("claim_text", ""))
            if q:
                quotes.append(truncate(q, 110))
        return (
            ";".join(eids[:5]) or "UNKNOWN",
            ";".join(urls[:2]) or "UNKNOWN",
            ";".join(dates[:2]) or "UNKNOWN",
            ";".join(pages[:2]) or "UNKNOWN",
            " | ".join(quotes[:2]) or "UNKNOWN",
        )

    def build_reentry_condition(sid, bucket, fact_tier, l2_dec, cutoff_flag, has_s02_gap):
        parts = []
        if cutoff_flag == "YES":
            parts.append("等待冻结截止日(2026-10-25)后的增量版本(R05)纳入2026-10-25之后披露的正式财报并重算S02-S05")
        if l2_dec == "HOLD_FOR_DATA":
            parts.append("先在S07/S00勘误(#53)中闭合导致HOLD_FOR_DATA的财务来源/重述/合并口径缺口并重算L2")
        elif l2_dec == "PENDING_ANCHOR_RESELECTION":
            parts.append("完成锚定期重选与S02/S04复算")
        elif l2_dec in ("NOT_SHORTLISTED", "L2_NOT_IN_SCOPE"):
            parts.append("后续定期报告(2026年报/2027Q1等)经冻结S01/S04规则复算出现至少2个干净维度改善信号")

        if bucket == "EARLY_RD_PROTOTYPE_SAMPLING":
            if fact_tier.startswith("S0"):
                parts.append("业务重进：正式公告/定期报告披露完成工程样机试制(S1)或客户送样验证(S2)且明确上市主体/并表范围")
            elif fact_tier.startswith("S1"):
                parts.append("业务重进：正式公告/定期报告披露通过外部客户送样测试(S2)或获得可核验的外部付费试点/小批量交付(S3)")
            else:
                parts.append("业务重进：正式公告/定期报告披露通过客户验证并进入付费试点/小批量交付(S3)且可核验主体与交付期")
        elif bucket == "EARLY_PILOT_SMALL_BATCH":
            parts.append("业务重进：正式定期报告披露小批量转批量交付(S4)或机器人产品线独立收入/销量连续两期可比增长")
        else:
            parts.append("业务重进：正式定期报告单列机器人分部/产品线收入与毛利且合并口径财务满足S04/S05主线门槛")

        if has_s02_gap:
            parts.append("同步核销S02指标HOLD/MISSING或PROVISIONAL项")
        return "；".join(parts)

    early_rows = []
    mainline_dedup_records = []
    out_of_universe_records = []

    # Collect all reviewed candidate security_ids across archive (53+7), early_sample (10), C00 (10), B00 (7)
    all_reviewed_sids = sorted(
        set(arch_cls.keys())
        | set(arch_pls.keys())
        | set(early_samp_prop.keys())
        | set(c00_scr.keys())
        | set(b00_scr.keys())
    )

    for sid in all_reviewed_sids:
        if sid not in master:
            out_of_universe_records.append((sid, "NOT_IN_FROZEN_1054_COMPANY_MASTER"))
            continue

        # Deduplicate against S05 278 mainline
        if sid in s05_mainline_278:
            route = "S05_QUALITY_PASS" if sid in s05_pass else "S05_QUALITY_OBSERVE"
            srcs = []
            if sid in arch_pkg_by_co: srcs.append(arch_pkg_by_co[sid])
            if sid in early_samp_prop: srcs.append("ARCHIVE_EARLY_SAMPLE")
            if sid in c00_scr: srcs.append("C00_PILOT_01")
            if sid in b00_scr: srcs.append(b00_scr[sid][0])
            mainline_dedup_records.append({
                "security_id": sid,
                "stock_name": master[sid]["stock_name"],
                "s05_route": route,
                "existing_evidence_sources": ";".join(srcs),
            })
            continue

        # Exclude explicitly reviewed concept/intent/no-evidence companies
        if sid in REVIEWED_EXCLUDED_NON_MAINLINE:
            continue

        # Must be in observe_pool_preserved_776
        assert sid in s05_776, f"{sid} not in 776"
        r776 = s05_776[sid]
        l2_dec = r776["l2_decision"]
        cutoff_flag = r776["cutoff_isolated"]
        s02_cnt = s02_status_by_co[sid]
        has_s02_gap = (s02_cnt["HOLD"] > 0 or s02_cnt["MISSING"] > 0)

        # Determine authoritative evidence source & fact tier
        # Priority: archive adopted (53) -> C00_PILOT_01 -> early_sample (10)
        if sid in arch_cls or sid in arch_pls:
            pkg_tag = arch_pkg_by_co[sid]
            cls_r = arch_cls[sid][1] if sid in arch_cls else {}
            lines = arch_pls.get(sid, [])
            # Keep lines from the latest/authoritative batch if duplicated (02A_supp supersedes 02A for BJ:920100/920124/920418)
            if any(t == "ARCHIVE_R1_02A_SUPP" for t, _ in lines):
                lines = [(t, l) for t, l in lines if t == "ARCHIVE_R1_02A_SUPP"]
                pkg_tag = "ARCHIVE_R1_02A_SUPP"

            stages = [clean_str(l.get("stage", "UNKNOWN")) or "UNKNOWN" for _, l in lines]
            # Check if there is an explicit early stage S0/S1/S2
            early_lines = [(t, l) for t, l in lines if clean_str(l.get("stage")) in ("S0", "S1", "S2")]
            s3_lines = [(t, l) for t, l in lines if clean_str(l.get("stage")) == "S3"]
            s4_lines = [(t, l) for t, l in lines if clean_str(l.get("stage")) == "S4"]

            if early_lines:
                # Pick highest progressed among S0/S1/S2 (S2 > S1 > S0) as primary early fact, while preserving all early lines
                early_lines_sorted = sorted(early_lines, key=lambda x: STAGE_PRIORITY.get(clean_str(x[1].get("stage")), 9), reverse=True)
                top_st = clean_str(early_lines_sorted[0][1].get("stage"))
                bucket = "EARLY_RD_PROTOTYPE_SAMPLING"
                fact_tier = {"S0": "S0_RD", "S1": "S1_PROTOTYPE", "S2": "S2_SAMPLING"}[top_st]
                chosen_lines = early_lines_sorted
                prio = "P1_HIGH" if top_st in ("S2", "S1") else "P2_MEDIUM"
            elif sid == "BJ:920100":
                # 三协电机: 2025年12月完成无框力矩电机系列化研发，样机/送样未披露 -> S0_RD_COMPLETED_STAGE_UNKNOWN
                bucket = "EARLY_RD_PROTOTYPE_SAMPLING"
                fact_tier = "S0_RD_STAGE_UNKNOWN"
                chosen_lines = lines
                prio = "P2_MEDIUM"
            elif s3_lines:
                bucket = "EARLY_PILOT_SMALL_BATCH"
                fact_tier = "S3_SMALL_BATCH_PILOT"
                chosen_lines = s3_lines
                prio = "P1_HIGH"
            elif s4_lines:
                bucket = "COMMERCIAL_NON_MAINLINE_RESERVE"
                fact_tier = "S4_BATCH_NON_MAINLINE"
                chosen_lines = s4_lines
                prio = "P1_HIGH"
            else:
                bucket = "EVIDENCED_PRODUCT_STAGE_UNKNOWN"
                fact_tier = "DIRECT_OR_INDIRECT_STAGE_UNKNOWN"
                chosen_lines = lines
                prio = "P2_MEDIUM"

            prod_line = "; ".join(clean_str(l.get("product_line", "")) for _, l in chosen_lines[:2])
            fact_sum = "; ".join(
                f"[{clean_str(l.get('stage','UNKNOWN'))}] {clean_str(l.get('commercial_fact',''))}"
                for _, l in chosen_lines[:2]
            )
            eids, urls, dates, pages, quotes = pick_archive_evidence(sid, chosen_lines)
            robot_exp = clean_str(cls_r.get("robot_exposure", "UNKNOWN")) or "UNKNOWN"
            rev_status = "ARCHIVE_ADOPTED_WITH_LIMITS"
            limits = "沿用archive旧分类附限制采用（53家口径）；非投资建议，不代表已商业化或已通过S05主线"

        elif sid in c00_scr:
            pkg_tag = "C00_PILOT_01"
            r = c00_scr[sid]
            evs = c00_ev.get(sid, [])
            dec = clean_str(r.get("screening_decision", ""))
            exp_prop = clean_str(r.get("robot_exposure_proposal", "UNKNOWN"))
            prod_line = clean_str(r.get("specific_robot_product", ""))
            fact_sum = clean_str(r.get("decision_reason", ""))

            # Map C00 recorded facts strictly to S0/S1/S2/S3/S4
            if sid == "SH:688698":  # 伟创电气: 产品线已列示但无出货证明
                bucket, fact_tier, prio = "EARLY_RD_PROTOTYPE_SAMPLING", "S0_RD_PRODUCT_UNVERIFIED_SHIPMENT", "P2_MEDIUM"
            elif sid == "SH:600845":  # 宝信软件: 样机试制与装配入库830台，外部交付未证
                bucket, fact_tier, prio = "EARLY_RD_PROTOTYPE_SAMPLING", "S1_PROTOTYPE_UNVERIFIED_DELIVERY", "P1_HIGH"
            elif sid == "SH:600366":  # 宁波韵升: 2026H1 新兴应用项目开发或交样
                bucket, fact_tier, prio = "EARLY_RD_PROTOTYPE_SAMPLING", "S2_SAMPLING", "P1_HIGH"
            elif sid == "SH:603933":  # 睿能科技: 2026H1 头部客户小批量供货/交付
                bucket, fact_tier, prio = "EARLY_PILOT_SMALL_BATCH", "S3_SMALL_BATCH_PILOT", "P1_HIGH"
            elif sid == "SH:605555":  # 德昌股份: 2026H1 割草机器人新品推进量产（收入/交付未证）
                bucket, fact_tier, prio = "EARLY_PILOT_SMALL_BATCH", "S3_RAMP_UNVERIFIED_REVENUE", "P2_MEDIUM"
            else:  # SZ:002031 巨轮智能, BJ:920579 机科股份, BJ:920211 新睿电子
                bucket, fact_tier, prio = "COMMERCIAL_NON_MAINLINE_RESERVE", "S4_OR_COMMERCIAL_NON_MAINLINE_C00", "P1_HIGH"

            eids = ";".join(clean_str(e.get("evidence_id", "")) for e in evs[:4]) or "UNKNOWN"
            urls = ";".join(
                dict.fromkeys(
                    clean_str(e.get("document_id", "") or e.get("primary_url", ""))
                    for e in evs[:3]
                    if clean_str(e.get("document_id", "") or e.get("primary_url", ""))
                )
            ) or "UNKNOWN"
            dates = ";".join(dict.fromkeys(clean_str(e.get("published_on", "")) for e in evs[:3] if clean_str(e.get("published_on", "")))) or "UNKNOWN"
            pages = ";".join(dict.fromkeys(clean_str(e.get("page_physical", "")) for e in evs[:3] if clean_str(e.get("page_physical", "")))) or "UNKNOWN"
            quotes = " | ".join(truncate(e.get("quoted_excerpt", "") or e.get("claim", ""), 110) for e in evs[:2]) or "UNKNOWN"
            robot_exp = exp_prop
            rev_status = "C00_SELF_CHECK_PENDING_INDEPENDENT_REVIEW"
            limits = "C00试点自检完成、独立验收待完成（含新睿电子年报官方来源链待核）；非投资建议"

        elif sid in early_samp_prop:
            pkg_tag = "ARCHIVE_EARLY_SAMPLE"
            rp = early_samp_prop[sid]
            re = early_samp_ev.get(sid, {})
            bucket = "EVIDENCED_PRODUCT_STAGE_UNKNOWN"
            fact_tier = "DIRECT_PRODUCT_STAGE_UNKNOWN"
            prio = "P2_MEDIUM"
            prod_line = clean_str(re.get("quoted_excerpt", "") or rp.get("end_market_tags", ""))
            fact_sum = clean_str(re.get("claim_text", ""))
            eids = clean_str(re.get("evidence_id", "UNKNOWN"))
            urls = clean_str(re.get("primary_url", "UNKNOWN"))
            dates = clean_str(re.get("published_on", "UNKNOWN"))
            pages = clean_str(re.get("page_or_section", "UNKNOWN"))
            quotes = truncate(re.get("quoted_excerpt", "") or re.get("claim_text", ""), 140)
            robot_exp = clean_str(rp.get("robot_exposure", "UNKNOWN"))
            rev_status = "EARLY_SAMPLE_CLAIM_ONLY_PENDING_FULL_CLASSIFICATION"
            limits = "10家早期样本仅局部业务存在性断言已核读，完整分类与产品线阶段仍UNKNOWN；非投资建议"
        else:
            continue

        # A04R keyword locator count (locator only!)
        a04r_cnt = len(a04r_kw_by_co.get(sid, []))

        watch_reason = (
            f"未入S05主线(278家)，当前位于776保留观察池({l2_dec})；"
            f"但已有可追溯证据({pkg_tag}/{fact_tier})记录机器人业务/研发/样机/送样或小批量事实，按S06保留观察不因未盈利或财务缺口漏筛。"
        )
        reentry = build_reentry_condition(sid, bucket, fact_tier, l2_dec, cutoff_flag, has_s02_gap)

        early_rows.append({
            "security_id": sid,
            "stock_code": master[sid]["stock_code"],
            "stock_name": master[sid]["stock_name"],
            "s05_mainline_dedup_status": "NON_MAINLINE_776",
            "s04_l2_decision": l2_dec,
            "s05_anchor_period": r776["anchor_period"],
            "cutoff_guard_flag": cutoff_flag,
            "watch_bucket": bucket,
            "fact_tier": fact_tier,
            "robot_exposure": robot_exp,
            "product_line": truncate(prod_line, 160),
            "disclosed_fact_summary": truncate(fact_sum, 220),
            "evidence_source_package": pkg_tag,
            "evidence_ids": eids,
            "document_id_or_url": urls,
            "published_on": dates,
            "physical_page_or_section": pages,
            "quoted_excerpt": quotes,
            "evidence_review_status": rev_status,
            "a04r_keyword_locator_count": str(a04r_cnt),
            "aux_method_version": AUX_METHOD_VERSION,
            "contract_liability_aux_status": "UNKNOWN",
            "contract_liability_aux_note": "NOT_IN_FROZEN_S00_SCHEMA（合同负债未入P04/S00冻结字段，合同资产已分列；未作全池补抽）",
            "order_backlog_aux_status": "UNKNOWN",
            "order_backlog_aux_note": "NO_VERIFIED_STRUCTURED_BACKLOG_IN_EXISTING_RECORDS（缺可核主体/时点/金额口径的正式在手订单披露）",
            "watch_reason": watch_reason,
            "reentry_trigger_conditions": reentry,
            "verification_priority": prio,
            "limitations": limits,
        })

    # Sort early_stage_watch deterministically by bucket, priority, security_id
    bucket_order = {
        "EARLY_RD_PROTOTYPE_SAMPLING": 1,
        "EARLY_PILOT_SMALL_BATCH": 2,
        "COMMERCIAL_NON_MAINLINE_RESERVE": 3,
        "EVIDENCED_PRODUCT_STAGE_UNKNOWN": 4,
    }
    early_rows.sort(key=lambda r: (bucket_order[r["watch_bucket"]], r["verification_priority"], r["security_id"]))
    early_sids = {r["security_id"] for r in early_rows}

    # ------------------------------------------------------------------
    # 4. Build missing_data_watch.csv
    # ------------------------------------------------------------------
    # Scope:
    #   (A) Non-mainline 776 pool:
    #       - HOLD_FOR_DATA (328)
    #       - WATCH_AFTER_CUTOFF (4)
    #       - PENDING_ANCHOR_RESELECTION (1)
    #       - Any NOT_SHORTLISTED / L2_NOT_IN_SCOPE with PENDING_CE_SOURCE (6) OR S02 HOLD/MISSING
    #   (B) Mainline S05 quality_observe carryover (1):
    #       - SZ:000856 冀东装备 (explicitly marked MAINLINE_S05_OBSERVE_DO_NOT_DOUBLE_COUNT)
    #   (C) Zero overlap with S05 quality_pass (277)!
    missing_rows = []

    def s02_gap_detail(sid):
        rows = s02_by_co[sid]
        hold_m = sorted({r["metric_id"] for r in rows if r["metric_status"] == "HOLD"})
        miss_m = sorted({r["metric_id"] for r in rows if r["metric_status"] == "MISSING"})
        prov_m = sorted({r["metric_id"] for r in rows if r["metric_status"] == "PROVISIONAL"})
        nc_m = sorted({r["metric_id"] for r in rows if r["metric_status"] == "NOT_COMPARABLE"})
        ub_m = sorted({r["metric_id"] for r in rows if r["metric_status"] == "UNDEFINED_BASE"})
        return hold_m, miss_m, prov_m, nc_m, ub_m

    # (A) Non-mainline 776
    for sid in sorted(s05_776.keys()):
        r776 = s05_776[sid]
        l2_dec = r776["l2_decision"]
        qs_state = r776["quality_source_state"]
        cutoff_flag = r776["cutoff_isolated"]
        anchor_flag = r776["anchor_reselection_pending"]
        pm_unk = r776["project_mode_source_unknown"]
        hold_m, miss_m, prov_m, nc_m, ub_m = s02_gap_detail(sid)

        in_scope = (
            l2_dec in ("HOLD_FOR_DATA", "WATCH_AFTER_CUTOFF", "PENDING_ANCHOR_RESELECTION")
            or qs_state == "PENDING_CE_SOURCE"
            or len(hold_m) > 0
            or len(miss_m) > 0
        )
        if not in_scope:
            continue

        # Primary missing_data_category
        if cutoff_flag == "YES" or l2_dec == "WATCH_AFTER_CUTOFF":
            cat = "AFTER_CUTOFF_ISOLATED"
            prio = "P1_HIGH"
            reason = "资料披露晚于冻结研究截止日(2026-10-25)，按S02合同(s03_input_contract.json)强制隔离，不准入干净信号。"
            reentry = "待冻结截止日升级后的增量版本(R05)纳入2026-10-25之后正式定期报告并全链路重算S02-S05。"
        elif anchor_flag == "YES" or l2_dec == "PENDING_ANCHOR_RESELECTION":
            cat = "PENDING_ANCHOR_RESELECTION"
            prio = "P1_HIGH"
            reason = "锚定期选定待重选（S04/S05延续守卫），当前锚点与基期对齐未冻结。"
            reentry = "完成锚定期重选与对应正式报告原文核验，重算S02/S04指标并复核是否进入S05主线。"
        elif l2_dec == "HOLD_FOR_DATA":
            cat = "S04_HOLD_FOR_DATA"
            if qs_state == "PENDING_CE_SOURCE":
                cat = "S04_HOLD_FOR_DATA_AND_QUALITY_SOURCE_UNKNOWN"
            prio = "P1_HIGH" if (sid in early_sids or qs_state == "PENDING_CE_SOURCE" or len(hold_m) > 0 or len(miss_m) > 0) else "P2_MEDIUM"
            sub_reasons = []
            sub_reasons.append("S04 L2判定HOLD_FOR_DATA（存在未闭合S00勘误/来源待核/重述待核或关键指标缺口）")
            if qs_state == "PENDING_CE_SOURCE":
                sub_reasons.append(f"带S05延续质量来源未知({r776['quality_source_pending_metrics']})")
            if hold_m:
                sub_reasons.append(f"S02 HOLD指标={','.join(hold_m)}")
            if miss_m:
                sub_reasons.append(f"S02 MISSING指标={','.join(miss_m)}")
            if prov_m:
                sub_reasons.append(f"S02 PROVISIONAL指标数={len(prov_m)}")
            reason = "；".join(sub_reasons) + "。"
            reentry = "在S07抽查或S00勘误(#53)中核验对应正式定期报告原页并闭合HOLD/MISSING/来源待核项，再按冻结S01/S04规则重算。"
        elif qs_state == "PENDING_CE_SOURCE":
            cat = "QUALITY_SOURCE_UNKNOWN_NON_MAINLINE"
            prio = "P1_HIGH"
            reason = f"位于776保留池({l2_dec})且存在质量来源未知({r776['quality_source_pending_metrics']})；" + (
                f"S02 HOLD={','.join(hold_m) or 'NONE'}, MISSING={','.join(miss_m) or 'NONE'}。"
            )
            reentry = "核验对应质量指标(M04/M08/M10/M11/M12)官方报告原页来源，闭合PENDING_CE_SOURCE并在后续报告期满足L2双干净维度。"
        else:
            cat = "S02_METRIC_HOLD_OR_MISSING_NON_MAINLINE"
            prio = "P2_MEDIUM" if sid in early_sids else "P3_LOW"
            reason = f"位于776保留池({l2_dec})但S02存在指标级缺口：HOLD={','.join(hold_m) or 'NONE'}，MISSING={','.join(miss_m) or 'NONE'}。"
            reentry = "补齐或核验S02 HOLD/MISSING所涉官方报告单元格，重算S02指标并复核是否触发L1/L2改善信号。"

        missing_rows.append({
            "security_id": sid,
            "stock_code": master[sid]["stock_code"],
            "stock_name": master[sid]["stock_name"],
            "mainline_dedup_status": "NON_MAINLINE_776",
            "s05_route": "OBSERVE_POOL_PRESERVED_776",
            "s04_l2_decision": l2_dec,
            "s05_anchor_period": r776["anchor_period"],
            "missing_data_category": cat,
            "cutoff_isolated": cutoff_flag,
            "anchor_reselection_pending": anchor_flag,
            "quality_source_state": qs_state,
            "quality_source_pending_metrics": r776["quality_source_pending_metrics"] or "NONE",
            "project_mode_source_unknown": pm_unk or "NOT_EVALUATED_IN_776",
            "s02_hold_count": str(len(hold_m)),
            "s02_missing_count": str(len(miss_m)),
            "s02_provisional_count": str(len(prov_m)),
            "s02_not_comparable_count": str(len(nc_m)),
            "s02_undefined_base_count": str(len(ub_m)),
            "s02_hold_metrics": ";".join(hold_m) or "NONE",
            "s02_missing_metrics": ";".join(miss_m) or "NONE",
            "in_early_stage_watch": "YES" if sid in early_sids else "NO",
            "source_locator": "runs/issues/S05/observe_pool_preserved_776.csv; runs/issues/S02/hangcha_restated_20261101/s02_v10/all_pool_metrics.csv",
            "watch_reason": reason,
            "reentry_trigger_conditions": reentry,
            "data_remediation_priority": prio,
            "limitations": "缺数据不等于无业务、不填零；#53未决事项保持开放，本表不闭合S00勘误或改写S05验收。",
        })

    # (B) Mainline S05 quality_observe carryover (1: SZ:000856 冀东装备)
    for sid, r_obs in sorted(s05_obs.items()):
        hold_m, miss_m, prov_m, nc_m, ub_m = s02_gap_detail(sid)
        missing_rows.append({
            "security_id": sid,
            "stock_code": master[sid]["stock_code"],
            "stock_name": master[sid]["stock_name"],
            "mainline_dedup_status": "MAINLINE_S05_OBSERVE_CARRYOVER_DO_NOT_DOUBLE_COUNT",
            "s05_route": "S05_QUALITY_OBSERVE",
            "s04_l2_decision": "L2_SHORTLIST_CANDIDATE_WITHDRAWN_IN_S05",
            "s05_anchor_period": r_obs["anchor_period"],
            "missing_data_category": "S05_QUALITY_HOLD_CONSOLIDATION_SCOPE_UNKNOWN",
            "cutoff_isolated": "NO",
            "anchor_reselection_pending": "NO",
            "quality_source_state": "CONSOLIDATION_SCOPE_UNKNOWN_M07_SG09",
            "quality_source_pending_metrics": "M07(SG09)",
            "project_mode_source_unknown": "NO",
            "s02_hold_count": str(len(hold_m)),
            "s02_missing_count": str(len(miss_m)),
            "s02_provisional_count": str(len(prov_m)),
            "s02_not_comparable_count": str(len(nc_m)),
            "s02_undefined_base_count": str(len(ub_m)),
            "s02_hold_metrics": ";".join(hold_m) or "NONE",
            "s02_missing_metrics": ";".join(miss_m) or "NONE",
            "in_early_stage_watch": "NO",
            "source_locator": "runs/issues/S05/quality_observe.csv; runs/issues/S05/acceptance_s05_r1_20261121.json",
            "watch_reason": "S05主线278家对照中的1家QUALITY_HOLD（不与776重复计数）：M07/SG09因合并口径UNKNOWN被撤回，仅剩CASH维度(SG08)，维度数不足进入观察。",
            "reentry_trigger_conditions": "核验对应报告期合并范围并补齐M07/SG09同口径来源，或在后续定期报告中新增至少1个干净非CASH维度信号并通过S05质量闸门。",
            "data_remediation_priority": "P1_HIGH",
            "limitations": "归属S05主线观察对照（278家之一），统计总观察规模时须按mainline_dedup_status去重，不得重复计入776侧。",
        })

    # Sort missing_data_watch deterministically
    cat_order = {
        "S05_QUALITY_HOLD_CONSOLIDATION_SCOPE_UNKNOWN": 1,
        "AFTER_CUTOFF_ISOLATED": 2,
        "PENDING_ANCHOR_RESELECTION": 3,
        "S04_HOLD_FOR_DATA_AND_QUALITY_SOURCE_UNKNOWN": 4,
        "QUALITY_SOURCE_UNKNOWN_NON_MAINLINE": 5,
        "S04_HOLD_FOR_DATA": 6,
        "S02_METRIC_HOLD_OR_MISSING_NON_MAINLINE": 7,
    }
    missing_rows.sort(key=lambda r: (cat_order[r["missing_data_category"]], r["data_remediation_priority"], r["security_id"]))

    # ------------------------------------------------------------------
    # 5. Write CSV outputs
    # ------------------------------------------------------------------
    early_path = OUT / "early_stage_watch.csv"
    with open(early_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(early_rows[0].keys()), lineterminator="\n")
        w.writeheader()
        w.writerows(early_rows)

    missing_path = OUT / "missing_data_watch.csv"
    with open(missing_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(missing_rows[0].keys()), lineterminator="\n")
        w.writeheader()
        w.writerows(missing_rows)

    # Compute exact summary counts for prose / review.json
    early_bucket_cnt = Counter(r["watch_bucket"] for r in early_rows)
    early_tier_cnt = Counter(r["fact_tier"] for r in early_rows)
    early_pkg_cnt = Counter(r["evidence_source_package"] for r in early_rows)
    early_l2_cnt = Counter(r["s04_l2_decision"] for r in early_rows)
    missing_cat_cnt = Counter(r["missing_data_category"] for r in missing_rows)
    missing_dedup_cnt = Counter(r["mainline_dedup_status"] for r in missing_rows)
    overlap_early_missing = len(early_sids & {r["security_id"] for r in missing_rows})
    non_mainline_missing_cnt = missing_dedup_cnt["NON_MAINLINE_776"]
    mainline_observe_missing_cnt = missing_dedup_cnt["MAINLINE_S05_OBSERVE_CARRYOVER_DO_NOT_DOUBLE_COUNT"]
    union_non_mainline_watch = len(early_sids | {r["security_id"] for r in missing_rows if r["mainline_dedup_status"] == "NON_MAINLINE_776"})

    # ------------------------------------------------------------------
    # 6. Write watch_reentry_rules.md
    # ------------------------------------------------------------------
    reentry_md = f"""# S06 观察名单准入、去重、辅助观察口径与重进规则

- 任务编号：S06（GitHub #41）
- 计划版本：`{PLAN_VERSION}`
- 知识截止日：`{KNOWLEDGE_AS_OF}`（冻结不变）
- 放行依据：`runs/issues/S06/release_20261122.json`、`runs/issues/S06/handoff_from_s05_20261122.md`
- 需求先行指标方法依据：`METHOD_20261107_LEADING_INDICATORS`（`docs/需求先行指标分工_20261107.md`、`data/methodology_decision_20261107.json`）
- 辅助观察版本：`{AUX_METHOD_VERSION}`
- 生成时间：`{NOW}`

---

## 一、主线去重与全池主键守恒规则

1. **权威主键基线**：`data/company_master.csv` 共 1,054 家唯一 `security_id`，与 S05 验收分区完全互斥且覆盖：
   - S05 主线通过对照（`runs/issues/S05/quality_pass.csv`）：**277 家**
   - S05 主线观察对照（`runs/issues/S05/quality_observe.csv`）：**1 家**（`SZ:000856` 冀东装备）
   - 上游保留观察入口（`runs/issues/S05/observe_pool_preserved_776.csv`）：**776 家**
   - 合计：`277 + 1 + 776 = 1,054` 家，主键 0 重复、0 遗漏。
2. **严格去重原则**：
   - `early_stage_watch.csv`（共 **{len(early_rows)} 家**）**全部来自 776 非主线池**，与 S05 278 主线（277 通过 + 1 观察）**0 重叠**。已有历史证据但已进入 S05 主线的 **{len(mainline_dedup_records)} 家**公司不重复计入早期观察，仅在 `handoff.md` 与 `review.json` 中按主键列明对照。
   - `missing_data_watch.csv`（共 **{len(missing_rows)} 家**）由 **{non_mainline_missing_cnt} 家**非主线 776 缺数据/守卫公司（`NON_MAINLINE_776`）与 **{mainline_observe_missing_cnt} 家** S05 主线观察结转（`SZ:000856` 冀东装备，`MAINLINE_S05_OBSERVE_CARRYOVER_DO_NOT_DOUBLE_COUNT`）构成，与 S05 277 `quality_pass.csv` **0 重叠**。
   - 两张观察表之间的交集为 **{overlap_early_missing} 家**（已在 `missing_data_watch.csv` 的 `in_early_stage_watch=YES` 显式标出，统计总覆盖时按 `security_id` 去重，非主线观察并集共 **{union_non_mainline_watch} 家**）。
   - S05 `quality_pass.csv`（277 家）内部已登记的专门待核项（RH02 待核 129、RH03 待核 19、RH06 待核 7、既有待核隔离 4 家在 pass + 1 家在 observe、越界观察 20 格）继续由 S05 原表承接，不在此重复造表。

---

## 二、早期储备观察（`early_stage_watch.csv`）准入与事实分层

1. **硬证据门槛（杜绝概念污染）**：
   - 仅复用已有可追溯证据（`archive/` 53 家旧分类附限制采用、10 家早期样本局部断言、`packages/B00_SOURCE_01/02`、`packages/C00_PILOT_01`、`packages/D00_B00_ADVANCE_01`），**不扩大全池采集或新增企业深研**。
   - `runs/issues/A04R/keyword_originals.jsonl` 与 `announcement_index.jsonl` **仅作原文定位器（locator）**，不单独构成业务事实准入依据。
   - 已有核查但结论为无机器人产品/仅合作意向/仅经营计划/仅 RPA 软件/证据不足的 **{len(REVIEWED_EXCLUDED_NON_MAINLINE)} 家**非主线公司（`BJ:920198` 微创光电、`BJ:920263` 中航泰达、`BJ:920002` 万达轴承、`SH:600699` 均胜电子、`SH:603466` 风语筑、`SH:688327` 云从科技）**明确不纳入**。
   - 其余未做业务精读的非主线公司一律保留业务证据 `UNKNOWN`，**不凭概念标签纳入**，也**不从来源覆盖反推精确的“无业务公司数”**。
   - 不在冻结 1,054 主表内的历史记录（如 `BJ:920007` 酉立智能）明确剔除。
2. **四类观察分桶（`watch_bucket`）与事实层级（`fact_tier`）**：
   - `EARLY_RD_PROTOTYPE_SAMPLING`（**{early_bucket_cnt['EARLY_RD_PROTOTYPE_SAMPLING']} 家**）：已记录研发（`S0`）、样机（`S1`）或客户送样测试（`S2`）事实，不强制要求盈利。
   - `EARLY_PILOT_SMALL_BATCH`（**{early_bucket_cnt['EARLY_PILOT_SMALL_BATCH']} 家**）：已记录付费试点/小批量交付或新品量产推进（`S3`）但未进 S05 主线。
   - `COMMERCIAL_NON_MAINLINE_RESERVE`（**{early_bucket_cnt['COMMERCIAL_NON_MAINLINE_RESERVE']} 家**）：已记录批量交付/直接机器人主业（`S4` 或 C00 确认主业），因未盈利、`HOLD_FOR_DATA`、`L2_NOT_IN_SCOPE` 或 `WATCH_AFTER_CUTOFF` 未进 S05 主线。
   - `EVIDENCED_PRODUCT_STAGE_UNKNOWN`（**{early_bucket_cnt['EVIDENCED_PRODUCT_STAGE_UNKNOWN']} 家**）：已核实存在直接/间接机器人产品或业务，但原复核记录中产品线商业阶段为 `UNKNOWN`。
3. **非推荐边界**：观察名单**不是**买入推荐、投资候选或已商业化认定，不得跳过 S07/S08 直接进入估值。

---

## 三、缺数据观察（`missing_data_watch.csv`）准入与守卫结转

1. **纳入范围**（共 **{len(missing_rows)} 家** = **{non_mainline_missing_cnt} 家非主线** + **1 家 S05 主线观察**）：
   - `S05_QUALITY_HOLD_CONSOLIDATION_SCOPE_UNKNOWN`（**{missing_cat_cnt['S05_QUALITY_HOLD_CONSOLIDATION_SCOPE_UNKNOWN']} 家**）：`SZ:000856` 冀东装备（S05 主线观察结转）。
   - `AFTER_CUTOFF_ISOLATED`（**{missing_cat_cnt['AFTER_CUTOFF_ISOLATED']} 家**）：`SH:603448` {master['SH:603448']['stock_name']}、`SH:688836` {master['SH:688836']['stock_name']}、`SZ:301348` {master['SZ:301348']['stock_name']}、`SZ:301699` {master['SZ:301699']['stock_name']}（沿用 S02 截止日后强制隔离）。
   - `PENDING_ANCHOR_RESELECTION`（**{missing_cat_cnt['PENDING_ANCHOR_RESELECTION']} 家**）：`SZ:002083` {master['SZ:002083']['stock_name']}（锚定期待重选）。
   - `S04_HOLD_FOR_DATA_AND_QUALITY_SOURCE_UNKNOWN`（**{missing_cat_cnt['S04_HOLD_FOR_DATA_AND_QUALITY_SOURCE_UNKNOWN']} 家**）：同时处于 `HOLD_FOR_DATA` 与 15 家质量来源未知（`PENDING_CE_SOURCE`）交集。
   - `QUALITY_SOURCE_UNKNOWN_NON_MAINLINE`（**{missing_cat_cnt['QUALITY_SOURCE_UNKNOWN_NON_MAINLINE']} 家**）：位于 `L2_NOT_IN_SCOPE` 但带 `PENDING_CE_SOURCE`（与上一类合计严格等于 **15 家**质量来源未知）。
   - `S04_HOLD_FOR_DATA`（**{missing_cat_cnt['S04_HOLD_FOR_DATA']} 家**）：其余 S04 `HOLD_FOR_DATA`（与上面 9 家合计严格等于 **328 家**）。
   - `S02_METRIC_HOLD_OR_MISSING_NON_MAINLINE`（**{missing_cat_cnt['S02_METRIC_HOLD_OR_MISSING_NON_MAINLINE']} 家**）：虽未判 `HOLD_FOR_DATA`，但 S02 冻结指标表存在至少 1 个 `HOLD` 或 `MISSING` 单元格的非主线公司。
2. **未决守卫原样结转**：
   - 4 家截止日后隔离、1 家锚点待重选、15 家质量来源未知、8 项未采用父链提议（`#53` 开放）、S05 已登记专门待核全部原样保留，不擅自闭合 `#53`，不把 `44/231/378` 历史未冻结统计当作当前派工名单。
   - **缺数据不填零**：`HOLD`、`MISSING`、`PROVISIONAL`、`NOT_COMPARABLE`、`UNDEFINED_BASE` 严格分列，均不视作 0 或无业务。

---

## 四、需求先行辅助观察口径登记（`{AUX_METHOD_VERSION}`）

依据 `METHOD_20261107_LEADING_INDICATORS`（`data/methodology_decision_20261107.json`），在首次采用合同负债与可信在手订单作为 S06 辅助观察前，预先登记版本 `{AUX_METHOD_VERSION}` 如下：

| 登记项 | 合同负债（`AUX.CONTRACT_LIAB`） | 可信在手订单（`AUX.VERIFIED_BACKLOG`） |
|---|---|---|
| **辅助观察版本** | `{AUX_METHOD_VERSION}`（独立辅助观察标签，不改 S01/S04/S05 冻结硬门槛） | `{AUX_METHOD_VERSION}`（独立辅助观察标签，不改 S01/S04/S05 冻结硬门槛） |
| **字段定义** | 合并资产负债表“合同负债”期末余额（人民币元），须与合同资产（`FIN.CONTRACTASSET.INSTANT`）严格分列，禁止混用 | 正式公告/定期报告明确披露的已生效在手合同/订单金额，须区分生效合同、框架/意向协议、已履行部分及取消/变更风险 |
| **权威来源与期间** | 合并资产负债表原页（与公司锚定期及上年同期同口径配对）；**当前状态：不在 P04/S00 冻结标准化字段内** | 交易所正式定期报告、重大合同签约公告原页（含物理页码与主体范围）；`A04R` 公告目录仅作定位器 |
| **适用业务模式** | 项目型系统集成（`PROJECT`）、定制设备/预收款模式优先参考；消费零售/标准品短账期模式须结合付款条款解释，增减不自动判好坏 | 项目型（`PROJECT`）与大额配套/运维服务合同；框架协议或按实际发生额结算合同（如主线对照 `BJ:920207` 众诚科技数采中心合同）不得当作确定收入 |
| **当前版本取值与缺失语义** | 非主线观察名单统一记 `UNKNOWN`（原因：`NOT_IN_FROZEN_S00_SCHEMA`），**不填 0、不据此淘汰**；不作全池补抽 | 非主线观察名单统一记 `UNKNOWN`（原因：`NO_VERIFIED_STRUCTURED_BACKLOG_IN_EXISTING_RECORDS`），**不填 0、不据此淘汰** |
| **既有可定位线索对照（不重复计入非主线）** | `packages/D00_B00_ADVANCE_01` 已记录主线公司 `BJ:920578` 巨能股份 2026H1 合同负债较期初下降 34.59%（主线参考，留 R00/R01 核验） | `packages/D00_B00_ADVANCE_01` 已记录主线公司 `BJ:920207` 众诚科技 2026-07-15 签约数采中心合同（83,123,260 元/年、36 个月、按实际下单与发生额结算，实际订单/验收待核） |
| **重进/升级条件** | 在后续定向核验或增量版中对具体观察对象回读已归档报告合并资产负债表原页，登记同期与上期合同负债、付款条款及交付节奏后再解除 `UNKNOWN` | 取得正式公告/定期报告原页并核实合同主体、签署/统计时点、生效状态、金额口径与履约进展后，方可转为已核辅助观察线索；订单转化与在建工程产能归属留 R00/R01 核验 |

---

## 五、可验证的重进条件（Re-entry Rules）总则

每家观察公司均在 CSV 的 `reentry_trigger_conditions` 列写明具体触发条件，汇总遵循四条统一硬原则：

1. **时间隔离重进（4 家 `WATCH_AFTER_CUTOFF`）**：严禁在 `2026-10-25` 冻结口径下放行；仅在增量版本（R05）上调截止日后，纳入新披露正式财报重算 S02–S05。
2. **数据缺口重进（`HOLD_FOR_DATA` / `PENDING_ANCHOR_RESELECTION` / `PENDING_CE_SOURCE` / `S05_QUALITY_HOLD` / S02 `HOLD`/`MISSING`）**：必须由正式定期报告原页核验闭合对应缺失或争议单元格（含合并范围、重述版本、父键口径），并按冻结 S01/S04/S05 规则全量重算通过，禁止手工加回。
3. **早期业务重进（`S0`→`S1`→`S2`→`S3`→`S4`）**：按“研发→样机→送样→小批量/付费试点→批量交付/独立收入”逐级提供可核验的正式披露原文（含主体、产品线、物理页码、期间与金额/数量口径），不得将概念、意向或库存入库视作外部交付收入。
4. **盈利与主线重进**：未盈利早期企业可保留在 S06 早期观察并随后续定期报告跟踪；若要进入主线候选用池，仍须经 S07 抽查与 S08 名单验收，并按冻结规则满足相应信号与质量要求。
"""
    (OUT / "watch_reentry_rules.md").write_text(reentry_md, encoding="utf-8")

    # ------------------------------------------------------------------
    # 7. Write handoff.md
    # ------------------------------------------------------------------
    mainline_list_md = "\n".join(
        f"| `{m['security_id']}` | {m['stock_name']} | `{m['s05_route']}` | `{m['existing_evidence_sources']}` |"
        for m in mainline_dedup_records
    )
    excluded_list_md = "\n".join(
        f"| `{sid}` | {master[sid]['stock_name']} | `{pkg}` | {why} |"
        for sid, (pkg, why) in sorted(REVIEWED_EXCLUDED_NON_MAINLINE.items())
    )

    handoff_md = f"""# S06 早期储备与缺数据观察交接（#41）

- 执行者：Antigravity
- 复核方：Codex（待独立复核）
- 计划版本：`{PLAN_VERSION}`
- 知识截止日：`{KNOWLEDGE_AS_OF}`
- 放行依据：`runs/issues/S06/release_20261122.json`、`runs/issues/S06/handoff_from_s05_20261122.md`
- 性质：执行方自检（`SELF_CHECK`），**不等同独立验收**；待 Codex 独立复核后决定是否放行 S07。

---

## 一、核心结果汇总

1. **全池 1,054 家主键守恒与去重**：
   - S05 主线对照 **278 家** = `quality_pass.csv` **277 家** + `quality_observe.csv` **1 家**（`SZ:000856` 冀东装备）。
   - 上游保留观察入口 `observe_pool_preserved_776.csv` **776 家**。
   - `277 + 1 + 776 = 1,054`，与 `data/company_master.csv` 完全一致。
2. **早期储备观察（`early_stage_watch.csv`）**：共 **{len(early_rows)} 家**（全部来自 776 非主线池，与 S05 278 主线 **0 重叠**）：
   - `EARLY_RD_PROTOTYPE_SAMPLING`（研发 S0 / 样机 S1 / 送样 S2）：**{early_bucket_cnt['EARLY_RD_PROTOTYPE_SAMPLING']} 家**
   - `EARLY_PILOT_SMALL_BATCH`（付费试点 / 小批量 S3）：**{early_bucket_cnt['EARLY_PILOT_SMALL_BATCH']} 家**
   - `COMMERCIAL_NON_MAINLINE_RESERVE`（已记录 S4 / 商业化产品但未入主线）：**{early_bucket_cnt['COMMERCIAL_NON_MAINLINE_RESERVE']} 家**
   - `EVIDENCED_PRODUCT_STAGE_UNKNOWN`（已核实直接/间接产品存在，阶段标 UNKNOWN）：**{early_bucket_cnt['EVIDENCED_PRODUCT_STAGE_UNKNOWN']} 家**
3. **缺数据观察（`missing_data_watch.csv`）**：共 **{len(missing_rows)} 家** = **{non_mainline_missing_cnt} 家非主线 776** + **{mainline_observe_missing_cnt} 家 S05 主线观察结转**（`SZ:000856` 冀东装备，显式标明不与 776 重复计数；与 S05 277 `quality_pass.csv` **0 重叠**）：
   - `S05_QUALITY_HOLD_CONSOLIDATION_SCOPE_UNKNOWN`：**{missing_cat_cnt['S05_QUALITY_HOLD_CONSOLIDATION_SCOPE_UNKNOWN']} 家**（`SZ:000856`）
   - `AFTER_CUTOFF_ISOLATED`：**{missing_cat_cnt['AFTER_CUTOFF_ISOLATED']} 家**（`SH:603448`、`SH:688836`、`SZ:301348`、`SZ:301699`）
   - `PENDING_ANCHOR_RESELECTION`：**{missing_cat_cnt['PENDING_ANCHOR_RESELECTION']} 家**（`SZ:002083`）
   - `S04_HOLD_FOR_DATA_AND_QUALITY_SOURCE_UNKNOWN`：**{missing_cat_cnt['S04_HOLD_FOR_DATA_AND_QUALITY_SOURCE_UNKNOWN']} 家**
   - `QUALITY_SOURCE_UNKNOWN_NON_MAINLINE`：**{missing_cat_cnt['QUALITY_SOURCE_UNKNOWN_NON_MAINLINE']} 家**（与上一类合计 = **15 家**质量来源未知）
   - `S04_HOLD_FOR_DATA`：**{missing_cat_cnt['S04_HOLD_FOR_DATA']} 家**（与上面 9 家合计 = **328 家** `HOLD_FOR_DATA`）
   - `S02_METRIC_HOLD_OR_MISSING_NON_MAINLINE`：**{missing_cat_cnt['S02_METRIC_HOLD_OR_MISSING_NON_MAINLINE']} 家**
4. **两表交集与去重并集**：
   - `early_stage_watch.csv` 与 `missing_data_watch.csv` 交集为 **{overlap_early_missing} 家**（已在 `missing_data_watch.csv` 的 `in_early_stage_watch=YES` 标明）。
   - 非主线观察去重并集为 **{union_non_mainline_watch} 家**（全部属于 776 非主线池）。

---

## 二、与 S05 主线去重清单（已入主线，不重复计入 `early_stage_watch.csv`）

共 **{len(mainline_dedup_records)} 家**在历史证据包（`archive/`、B00/C00/D00、早期样本）中有记录但已进入 S05 主线（`S05_QUALITY_PASS`），已按主键去重：

| security_id | 公司简称 | S05 主线路由 | 已有证据来源 |
|---|---|---|---|
{mainline_list_md}

---

## 三、已核查但因概念/意向/证据不足未纳入早期储备的非主线公司（{len(REVIEWED_EXCLUDED_NON_MAINLINE)} 家）

| security_id | 公司简称 | 核查来源 | 不纳入理由 |
|---|---|---|---|
{excluded_list_md}

另：历史 `archive/R1_batch01_parent_reviewed_20261024` 中的 `BJ:920007`（酉立智能）不在冻结 1,054 家 `company_master.csv` 主表内，已剔除。其余未经过业务精读的非主线公司保持 `UNKNOWN`，不凭概念标签纳入，也不反推精确的“无业务公司数”。

---

## 四、需求先行辅助观察与未决守卫结转

1. **合同负债与可信在手订单（`{AUX_METHOD_VERSION}`）**：已按 `METHOD_20261107_LEADING_INDICATORS` 在 `watch_reentry_rules.md` 第四节登记字段定义、来源、期间、适用业务模式、缺失语义与重进条件。因合同负债不在 P04/S00 冻结标准化字段内且无全池结构化在手订单台账，非主线观察行全部如实记 `UNKNOWN`，不填 0、不作全池补抽；合同资产继续与合同负债分列。
2. **未决守卫与 #53 开放态**：4 家截止日后隔离、1 家锚点待重选、15 家质量来源未知、8 项未采用父链提议、S05 专门待核（RH02 129、RH03 19、RH06 7、既有待核 5 家、越界 20 格）全部原样结转；`#53` 保持 OPEN，不采纳 `44/231/378` 历史未冻结统计作为当前派工名单。

---

## 五、限制、环境备注与下一步

1. **限制**：
   - 本轮仅复用已有可追溯证据与 S02/S05 冻结产物，未新增全池采集或逐家企业深研；`archive/` 53 家旧采用、10 家早期样本及 B00/C00/D00 各自保留原有限制与待核状态。
   - 观察名单不是买入推荐或已商业化认定，不跳过 S07/S08 进入估值。
   - 执行方自检（`SELF_CHECK`）不等同独立验收。
2. **环境备注**：本机 git 默认代理 `127.0.0.1:7890` 未启动，拉取/推送远端时临时清代理直连；`gh api` 直连正常。
3. **下一步建议**：提交 Codex 独立复核（核对主键去重、证据定位与事实分层、时间隔离、未决项结转、辅助观察口径登记及每家重进条件）；待 Codex 验收并新增明确放行记录后再推进 S07（#42）。
"""
    (OUT / "handoff.md").write_text(handoff_md, encoding="utf-8")

    # Save build summary stats for verify script & review/manifest
    summary = {
        "generated_at": NOW,
        "plan_version": PLAN_VERSION,
        "knowledge_as_of": KNOWLEDGE_AS_OF,
        "aux_method_version": AUX_METHOD_VERSION,
        "universe": 1054,
        "s05_mainline_pass": 277,
        "s05_mainline_observe": 1,
        "s05_carryover_776": 776,
        "early_stage_watch_count": len(early_rows),
        "early_stage_by_bucket": dict(early_bucket_cnt),
        "early_stage_by_fact_tier": dict(early_tier_cnt),
        "early_stage_by_source_package": dict(early_pkg_cnt),
        "early_stage_by_s04_l2": dict(early_l2_cnt),
        "missing_data_watch_count": len(missing_rows),
        "missing_data_non_mainline_count": non_mainline_missing_cnt,
        "missing_data_mainline_observe_count": mainline_observe_missing_cnt,
        "missing_data_by_category": dict(missing_cat_cnt),
        "overlap_early_and_missing": overlap_early_missing,
        "union_non_mainline_watch": union_non_mainline_watch,
        "mainline_dedup_excluded_from_early": len(mainline_dedup_records),
        "reviewed_concept_or_insufficient_excluded": len(REVIEWED_EXCLUDED_NON_MAINLINE),
        "out_of_universe_excluded": len(out_of_universe_records),
        "guards_preserved": {
            "after_cutoff_companies": 4,
            "anchor_reselection_pending": 1,
            "quality_source_unknown_companies": 15,
            "unadopted_parent_members": 8,
            "s05_quality_observe_jidong": 1,
            "s00_errata_issue_53": "OPEN",
        },
        "mainline_dedup_list": mainline_dedup_records,
        "reviewed_excluded_list": [
            {"security_id": sid, "stock_name": master[sid]["stock_name"], "source": pkg, "reason": why}
            for sid, (pkg, why) in sorted(REVIEWED_EXCLUDED_NON_MAINLINE.items())
        ],
    }

    print(json.dumps({k: v for k, v in summary.items() if k not in ("mainline_dedup_list", "reviewed_excluded_list")}, ensure_ascii=False, indent=2))

    # Write temporary summary for review/manifest generation (will be folded into review.json/manifest.json, not left stray)
    return summary


if __name__ == "__main__":
    main()
