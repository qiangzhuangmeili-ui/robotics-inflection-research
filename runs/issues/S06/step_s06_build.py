# -*- coding: utf-8 -*-
"""
S06 (#41) Deterministic Builder — Rework Round R1 (post Codex review 2026-11-22):
  - early_stage_watch.csv
  - missing_data_watch.csv
  - watch_reentry_rules.md
  - handoff.md
  - manifest.json / review.json (finalized by step_s06_verify.py)

Targeted fixes applied in R1 per runs/issues/S06/codex_review_s06_20261122.md:
  1.1 Stage/fact/entity-scope fixes:
      - SH:605555 德昌股份: moved out of S3/EARLY_PILOT_SMALL_BATCH into EVIDENCED_PRODUCT_STAGE_UNKNOWN
        (PRODUCT_RAMP_DELIVERY_STAGE_UNKNOWN), using C00-EV-605555-03 physical page 12 (not page 11).
      - SH:600366 宁波韵升: primary fact updated to C00-EV-600366-03 physical page 11 (long-term agreement,
        sample delivery & supply in humanoid robotics; customer/scale/revenue/margin remain UNKNOWN;
        no presumption of S3/S4 or quantified order backlog).
      - Multi-line companies (SH:603296, SH:603583, SH:688165, SZ:002527 and all archive companies):
        preserve every recorded product line, stage, entity/ownership scope & evidence ID in
        `all_recorded_product_lines` and `other_verified_stages`, with explicit `bucket_selection_rule`.
      - SH:603219 富佳股份: listed-parent ODM line (R1B1-PL046, stage=UNKNOWN) separated from
        unconsolidated associate 芯禾机器人 lines (R1B1-PL047 S3 / R1B1-PL048 S1, indirect observation only);
        routed by listed-parent scope to EVIDENCED_PRODUCT_STAGE_UNKNOWN.
  1.2 Source locators & adoption boundary:
      - Read both `page_or_section` and `page_physical` (plus `page_printed` when present), recovering
        all 24 previously-UNKNOWN physical pages.
      - Exclude any evidence row marked `DO_NOT_ADOPT` (e.g., BJ:920124 R1A02-E001) from adopted
        `evidence_ids`, placing it in `non_adopted_historical_locators`.
      - Add 1-to-1 `primary_evidence_binding` column.
  1.3 Complete input manifest:
      - Remove unused reads (s04_log, b00_ev) and export exact `READ_INPUTS` list for manifest.json.
  1.4 Re-entry conditions & cutoff diagnostic scope:
      - Split mainline re-entry (frozen rules) vs business verification goal per fact_tier/exposure.
      - Add `s02_gap_diagnostic_scope` to missing_data_watch.csv so the 4 after-cutoff companies'
        raw S02 counts are explicitly tagged as isolation-period diagnostics only.
"""
import csv
import hashlib
import json
import os
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
OUT = REPO / "runs" / "issues" / "S06"
NOW = os.environ.get("S06_FIXED_NOW") or datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")

KNOWLEDGE_AS_OF = "2026-10-25"
PLAN_VERSION = "20261026_collection_first_v2"
AUX_METHOD_VERSION = "S06_AUX_LEAD_V1"
REWORK_ROUND = "R2"

# Exact, exhaustive list of every Git-tracked file read or referenced at runtime by S06 (33 files, all in Git tree)
READ_INPUTS = [
    # Control, release & methodology
    "runs/issues/S06/release_20261122.json",
    "runs/issues/S06/handoff_from_s05_20261122.md",
    "runs/issues/S01/acceptance_20261029.json",
    "runs/issues/S02/acceptance_20261106/review.json",
    "runs/issues/S02/acceptance_20261106/s03_input_contract.json",
    "runs/issues/S02/hangcha_restated_20261101/s02_v10/all_pool_metrics.csv",
    "runs/issues/S05/acceptance_s05_r1_20261121.json",
    "runs/issues/S05/quality_pass.csv",
    "runs/issues/S05/quality_observe.csv",
    "runs/issues/S05/observe_pool_preserved_776.csv",
    "data/company_master.csv",
    "data/document_registry.csv",
    "data/methodology_decision_20261107.json",
    # Archive 53 adopted + 10 early samples (14 CSVs)
    "archive/R1_batch01_parent_reviewed_20261024/classification_reviewed.csv",
    "archive/R1_batch01_parent_reviewed_20261024/product_line_stages.csv",
    "archive/R1_batch01_parent_reviewed_20261024/evidence_register.csv",
    "archive/R1_02A_parent_reviewed_20261024/classification_reviewed.csv",
    "archive/R1_02A_parent_reviewed_20261024/product_line_stages_reviewed.csv",
    "archive/R1_02A_parent_reviewed_20261024/evidence_register_reviewed.csv",
    "archive/02A_supplement/classification_reviewed.csv",
    "archive/02A_supplement/product_line_stages_reviewed.csv",
    "archive/02A_supplement/evidence_register_reviewed.csv",
    "archive/02B/classification_reviewed.csv",
    "archive/02B/product_line_stages_reviewed.csv",
    "archive/02B/evidence_register_reviewed.csv",
    "archive/early_sample_proposals.csv",
    "archive/early_sample_evidence.csv",
    # Packages B00 / C00 / D00 actually consumed or referenced
    "packages/B00_SOURCE_01/results/screening.csv",
    "packages/B00_SOURCE_02/results/screening.csv",
    "packages/C00_PILOT_01/results/screening.csv",
    "packages/C00_PILOT_01/results/evidence.csv",
    "packages/D00_B00_ADVANCE_01/results/evidence.csv",
    # A04R keyword locator index (locator only)
    "runs/issues/A04R/keyword_originals.jsonl",
]

# Local-only independent review records (provenance references, NOT runtime inputs required for clean-commit replay)
REVIEW_PROVENANCE_REFS = [
    "runs/issues/S06/codex_review_s06_20261122.md",
    "runs/issues/S06/codex_review_s06_r1_20261123.md",
]


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_canonical_lf(path: Path) -> tuple[int, str]:
    """Canonical LF-normalized byte length & SHA-256 matching Git blob bytes across OS line endings."""
    data = path.read_bytes().replace(b"\r\n", b"\n")
    return len(data), hashlib.sha256(data).hexdigest()


def load_csv(rel: str):
    with open(REPO / rel, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def clean_str(val) -> str:
    if val is None:
        return ""
    return " ".join(str(val).replace("\r", " ").replace("\n", " ").split()).strip()


def truncate(s: str, n: int = 200) -> str:
    s = clean_str(s)
    return s if len(s) <= n else s[: n - 3] + "..."


def extract_page(ev_row: dict) -> str:
    """Read both `page_physical` and `page_or_section` (plus `page_printed` if helpful)."""
    pg_sec = clean_str(ev_row.get("page_or_section", ""))
    pg_phy = clean_str(ev_row.get("page_physical", ""))
    pg_prt = clean_str(ev_row.get("page_printed", ""))
    if pg_sec and pg_sec.upper() != "UNKNOWN":
        return pg_sec
    if pg_phy and pg_phy.upper() != "UNKNOWN":
        out = f"物理第{pg_phy}页" if pg_phy.isdigit() else pg_phy
        if pg_prt and pg_prt.upper() not in ("UNKNOWN", "", "NONE") and pg_prt != pg_phy:
            out += f"（印刷第{pg_prt}页）" if pg_prt.isdigit() else f"（{pg_prt}）"
        return out
    return "UNKNOWN"


def is_non_adopted_evidence(ev_row: dict) -> bool:
    rs = clean_str(ev_row.get("review_status", "")).upper()
    psr = clean_str(ev_row.get("parent_source_review", "")).upper()
    return ("DO_NOT_ADOPT" in rs) or ("DO_NOT_ADOPT" in psr)


def main():
    # ------------------------------------------------------------------
    # 1. Load frozen baselines & verify primary key conservation (1,054)
    # ------------------------------------------------------------------
    master = {r["security_id"]: r for r in load_csv("data/company_master.csv")}
    s05_pass = {r["security_id"]: r for r in load_csv("runs/issues/S05/quality_pass.csv")}
    s05_obs = {r["security_id"]: r for r in load_csv("runs/issues/S05/quality_observe.csv")}
    s05_776 = {r["security_id"]: r for r in load_csv("runs/issues/S05/observe_pool_preserved_776.csv")}
    s05_mainline_278 = set(s05_pass) | set(s05_obs)

    assert len(master) == 1054
    assert len(s05_pass) == 277
    assert len(s05_obs) == 1
    assert len(s05_776) == 776
    assert not (set(s05_pass) & set(s05_obs))
    assert not (s05_mainline_278 & set(s05_776))
    assert (s05_mainline_278 | set(s05_776)) == set(master)

    # Verify S02 metrics SHA-256 (canonical LF bytes matching Git blob)
    s02_rel = "runs/issues/S02/hangcha_restated_20261101/s02_v10/all_pool_metrics.csv"
    _, s02_sha = sha256_canonical_lf(REPO / s02_rel)
    assert s02_sha == "3091b0bb82a3e3114d7f338595c40d82c842ce47aa8802b141a6ce8ec2232953"

    # Load document_registry for verified original PDF SHA-256 binding (e.g. SH:688165 DOC-586ED2C18DB28CDE)
    doc_reg = {r["document_id"]: r for r in load_csv("data/document_registry.csv")}
    efort_doc = doc_reg["DOC-586ED2C18DB28CDE"]
    assert efort_doc["security_id"] == "SH:688165"
    assert efort_doc["sha256"] == "586ed2c18db28cdeb8b2df23bc9dc8ff995ec33bc37895c885b5e9aa8e426517"

    s02_rows = load_csv(s02_rel)
    assert len(s02_rows) == 12648
    s02_by_co = defaultdict(list)
    s02_status_by_co = defaultdict(Counter)
    for r in s02_rows:
        sid = r["security_id"]
        s02_by_co[sid].append(r)
        s02_status_by_co[sid][r["metric_status"]] += 1

    # Load A04R keyword_originals.jsonl (locator ONLY)
    a04r_kw_by_co = defaultdict(list)
    for line in (REPO / "runs/issues/A04R/keyword_originals.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            obj = json.loads(line)
            a04r_kw_by_co[obj["security_id"]].append(obj)

    # ------------------------------------------------------------------
    # 2. Load ALL existing traceable evidence registers
    # ------------------------------------------------------------------
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
            eid = r["evidence_id"].strip()
            arch_ev_by_id[eid] = (pkg_tag, r)
            arch_ev_by_co[r["security_id"]].append((pkg_tag, r))

    early_samp_prop = {r["security_id"]: r for r in load_csv("archive/early_sample_proposals.csv")}
    early_samp_ev = {r["security_id"]: r for r in load_csv("archive/early_sample_evidence.csv")}

    c00_scr = {r["security_id"]: r for r in load_csv("packages/C00_PILOT_01/results/screening.csv")}
    c00_ev = defaultdict(list)
    c00_ev_by_id = {}
    for r in load_csv("packages/C00_PILOT_01/results/evidence.csv"):
        c00_ev[r["security_id"]].append(r)
        c00_ev_by_id[r["evidence_id"].strip()] = r

    b00_scr = {}
    for bpkg in ["B00_SOURCE_01", "B00_SOURCE_02"]:
        for r in load_csv(f"packages/{bpkg}/results/screening.csv"):
            b00_scr[r["security_id"]] = (bpkg, r)

    # ------------------------------------------------------------------
    # 3. Build early_stage_watch.csv (strictly non-mainline 776, evidence-gated)
    # ------------------------------------------------------------------
    REVIEWED_EXCLUDED_NON_MAINLINE = {
        "BJ:920198": ("B00_SOURCE_01", "2025年报及2026H1全文未命中机器人关键词，主业为交通监控信息化，无机器人产品或研发事实"),
        "BJ:920263": ("B00_SOURCE_01", "2025年报仅披露战略合作意向及唐山地块储备，无研发成果、样机、送样或合同事实"),
        "BJ:920002": ("ARCHIVE_EARLY_SAMPLE", "2024年报抽查段落仅列叉车轴承与回转支承，未见机器人专属产品或研发证据（证据不足记UNKNOWN）"),
        "SH:600699": ("ARCHIVE_R1_02B", "2025新设并表子公司未见产品或收入，人形机器人关联主体为非并表关联方，无上市公司产品/研发事实"),
        "SH:603466": ("ARCHIVE_R1_02B", "仅2026经营计划与文旅合作探索，未核实已完成的研发、样机或产品事实"),
        "SH:688327": ("ARCHIVE_R1_02B", "前瞻生态布局，无自研机器人本体/产品/收入；财报所提机器人为RPA软件"),
    }

    STAGE_ORDER_EARLY = {"S2": 3, "S1": 2, "S0": 1}

    def format_line_record(l: dict) -> str:
        lid = clean_str(l.get("line_id", ""))
        pl = clean_str(l.get("product_line", ""))
        ent = clean_str(l.get("entity_scope", "UNKNOWN"))
        own = clean_str(l.get("ownership_scope", "UNKNOWN"))
        st = clean_str(l.get("stage", "UNKNOWN")) or "UNKNOWN"
        # Filter out DO_NOT_ADOPT evidence IDs inside line listing too
        raw_eids = [e.strip() for e in clean_str(l.get("stage_evidence_ids", "")).replace(",", ";").split(";") if e.strip()]
        kept_eids = [e for e in raw_eids if not (e in arch_ev_by_id and is_non_adopted_evidence(arch_ev_by_id[e][1]))]
        ev_str = ";".join(kept_eids) or "NONE"
        fact = truncate(l.get("commercial_fact", ""), 70)
        return f"{lid}|{pl}|{ent}({own})|stage={st}|ev={ev_str}|{fact}"

    def bind_archive_evidence(sid, chosen_lines):
        raw_eids = []
        for _, l in chosen_lines:
            for eid in clean_str(l.get("stage_evidence_ids", "")).replace(",", ";").split(";"):
                eid = eid.strip()
                if eid and eid not in raw_eids:
                    raw_eids.append(eid)

        adopted_evs = []
        non_adopted = []
        for eid in raw_eids:
            if eid in arch_ev_by_id:
                eo = arch_ev_by_id[eid][1]
                if is_non_adopted_evidence(eo):
                    tag_st = clean_str(eo.get("parent_source_review") or eo.get("review_status") or "DO_NOT_ADOPT")
                    non_adopted.append(f"{eid}({tag_st})")
                else:
                    adopted_evs.append(eo)

        if not adopted_evs and sid in arch_ev_by_co:
            for _, eo in arch_ev_by_co[sid]:
                if not is_non_adopted_evidence(eo):
                    adopted_evs.append(eo)
                    if len(adopted_evs) >= 2:
                        break

        eids = [clean_str(eo.get("evidence_id", "")) for eo in adopted_evs]
        urls = list(dict.fromkeys(clean_str(eo.get("primary_url", "")) for eo in adopted_evs if clean_str(eo.get("primary_url", ""))))
        dates = list(dict.fromkeys(clean_str(eo.get("published_on", "")) for eo in adopted_evs if clean_str(eo.get("published_on", ""))))
        pages = list(dict.fromkeys(extract_page(eo) for eo in adopted_evs if extract_page(eo) != "UNKNOWN"))
        quotes = [truncate(eo.get("quoted_excerpt", "") or eo.get("claim_text", ""), 115) for eo in adopted_evs[:3]]
        bindings = [
            f"{clean_str(eo.get('evidence_id'))}|{clean_str(eo.get('primary_url','UNKNOWN'))}|{clean_str(eo.get('published_on','UNKNOWN'))}|{extract_page(eo)}|{clean_str(eo.get('review_status','UNKNOWN'))}"
            for eo in adopted_evs[:3]
        ]
        return (
            ";".join(eids) or "UNKNOWN",
            ";".join(non_adopted) or "NONE",
            ";".join(urls[:3]) or "UNKNOWN",
            ";".join(dates[:3]) or "UNKNOWN",
            ";".join(pages[:3]) or "UNKNOWN",
            " | ".join(quotes) or "UNKNOWN",
            " || ".join(bindings) or "UNKNOWN",
        )

    def build_reentry_condition(bucket, fact_tier, l2_dec, cutoff_flag, has_s02_gap, robot_exp):
        # Part 1: Mainline financial re-entry (strictly per frozen rules)
        fin_parts = []
        if cutoff_flag == "YES":
            fin_parts.append("【主线重进】受2026-10-25冻结截止日隔离；须待增量版本(R05)上调截止日后纳入2026-10-25之后正式定期报告并全链路重算S02-S05")
        elif l2_dec == "HOLD_FOR_DATA":
            fin_parts.append("【主线重进】须在S07或S00勘误(#53)闭合导致HOLD_FOR_DATA的财务来源/重述/合并口径缺口，按冻结S01/S04规则重算L2并通过S05质量闸门")
        elif l2_dec == "PENDING_ANCHOR_RESELECTION":
            fin_parts.append("【主线重进】完成锚定期重选与S02/S04复算并通过S05质量闸门")
        else:
            fin_parts.append("【主线重进】后续正式定期报告按冻结S01/S04规则复算达到至少2个干净维度改善信号并通过S05质量闸门")
        if has_s02_gap and cutoff_flag != "YES":
            fin_parts.append("同步核销S02 HOLD/MISSING项")

        # Part 2: Business verification goal (tailored, NOT forcing uniform revenue-split template)
        if fact_tier in ("S0_RD", "S0_RD_STAGE_UNKNOWN", "S0_RD_PRODUCT_UNVERIFIED_SHIPMENT"):
            biz = "【业务核证目标】正式公告或定期报告披露完成工程样机试制(S1)或外部客户送样测试(S2)，并明确上市并表主体范围"
        elif fact_tier in ("S1_PROTOTYPE", "S1_PROTOTYPE_UNVERIFIED_DELIVERY"):
            biz = "【业务核证目标】正式公告或定期报告披露通过外部客户送样测试(S2)或可核验的外部付费试点/小批量交付(S3)，区分内部入库与外部销售"
        elif fact_tier == "S2_SAMPLING":
            biz = "【业务核证目标】正式公告或定期报告披露通过客户验证并转入付费试点/小批量交付(S3)，明确交付主体与期间"
        elif fact_tier == "SAMPLING_AND_SUPPLY_SCALE_UNKNOWN":
            biz = "【业务核证目标】在已核2026H1长期协议及样品交付/供货基础上，核实供货规模、客户属性、交付节奏及机器人收入/毛利归属，区分长期协议与量化在手订单"
        elif fact_tier == "PRODUCT_RAMP_DELIVERY_STAGE_UNKNOWN":
            biz = "【业务核证目标】核实割草机器人等新品是否完成外部客户交付并形成可确认销售收入，避免将量产推进直接等同于已实现外部收入"
        elif fact_tier == "LISTED_PARENT_STAGE_UNKNOWN_WITH_ASSOCIATE_EARLY_OBSERVE":
            biz = "【业务核证目标】分别核实上市母公司扫地机器人ODM的商业阶段与收入归属；参股公司芯禾机器人(S1/S3)仅作非并表间接观察，不混入上市主体营收"
        elif fact_tier == "S3_SMALL_BATCH_PILOT":
            biz = "【业务核证目标】核实小批量/试点是否转为持续批量交付(S4)，并跟踪机器人产品线销量或收入的连续可比变化"
        elif fact_tier in ("S4_BATCH_NON_MAINLINE", "S4_OR_COMMERCIAL_NON_MAINLINE_C00"):
            biz = "【业务核证目标】已在既有台账核实批量交付或主营机器人产品；后续进入R00/R01时核验产线/产品线盈利质量、客户集中度与财务归因"
        else:
            biz = "【业务核证目标】核实已披露机器人产品线的商业化阶段(S0-S4)、并表主体范围及收入口径归属（未要求强行拆出未披露的独立分部毛利）"

        return "；".join(fin_parts) + "；" + biz

    early_rows = []
    mainline_dedup_records = []
    out_of_universe_records = []

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

        if sid in REVIEWED_EXCLUDED_NON_MAINLINE:
            continue

        assert sid in s05_776, f"{sid} not in 776"
        r776 = s05_776[sid]
        l2_dec = r776["l2_decision"]
        cutoff_flag = r776["cutoff_isolated"]
        s02_cnt = s02_status_by_co[sid]
        has_s02_gap = (s02_cnt["HOLD"] > 0 or s02_cnt["MISSING"] > 0)

        non_adopted_loc = "NONE"
        other_stages = "NONE"
        all_lines_str = "NONE"
        entity_scope_str = "UNKNOWN"
        bucket_rule = "SINGLE_PRIMARY_SOURCE"

        if sid in arch_cls or sid in arch_pls:
            pkg_tag = arch_pkg_by_co[sid]
            cls_r = arch_cls[sid][1] if sid in arch_cls else {}
            lines = arch_pls.get(sid, [])
            if any(t == "ARCHIVE_R1_02A_SUPP" for t, _ in lines):
                lines = [(t, l) for t, l in lines if t == "ARCHIVE_R1_02A_SUPP"]
                pkg_tag = "ARCHIVE_R1_02A_SUPP"

            # Preserve ALL recorded product lines for S07 visibility
            all_lines_str = " || ".join(format_line_record(l) for _, l in lines) if lines else "NONE"

            # Separate consolidated/listed-parent lines vs unconsolidated associate lines
            cons_lines = [
                (t, l) for t, l in lines
                if clean_str(l.get("ownership_scope", "")).upper() != "ASSOCIATE_NOT_CONSOLIDATED"
            ]
            assoc_lines = [
                (t, l) for t, l in lines
                if clean_str(l.get("ownership_scope", "")).upper() == "ASSOCIATE_NOT_CONSOLIDATED"
            ]

            early_cons = [(t, l) for t, l in cons_lines if clean_str(l.get("stage")) in ("S0", "S1", "S2")]
            s3_cons = [(t, l) for t, l in cons_lines if clean_str(l.get("stage")) == "S3"]
            s4_cons = [(t, l) for t, l in cons_lines if clean_str(l.get("stage")) == "S4"]

            if sid == "SH:603219":
                # 富佳股份: listed-parent ODM is UNKNOWN; associate 芯禾机器人 S1/S3 kept as indirect observation
                bucket = "EVIDENCED_PRODUCT_STAGE_UNKNOWN"
                fact_tier = "LISTED_PARENT_STAGE_UNKNOWN_WITH_ASSOCIATE_EARLY_OBSERVE"
                chosen_lines = cons_lines if cons_lines else lines
                prio = "P2_MEDIUM"
                entity_scope_str = "LISTED_PARENT(扫地机器人ODM,stage=UNKNOWN); ASSOCIATE_NOT_CONSOLIDATED(芯禾机器人,S1/S3间接观察)"
                other_stages = "ASSOCIATE_ONLY:S3;ASSOCIATE_ONLY:S1"
                bucket_rule = "LISTED_PARENT_SCOPE_BOUND_ASSOCIATE_SEPARATED"
            elif early_cons:
                early_sorted = sorted(early_cons, key=lambda x: STAGE_ORDER_EARLY[clean_str(x[1].get("stage"))], reverse=True)
                top_st = clean_str(early_sorted[0][1].get("stage"))
                bucket = "EARLY_RD_PROTOTYPE_SAMPLING"
                fact_tier = {"S0": "S0_RD", "S1": "S1_PROTOTYPE", "S2": "S2_SAMPLING"}[top_st]
                chosen_lines = early_sorted
                prio = "P1_HIGH" if top_st in ("S2", "S1") else "P2_MEDIUM"
                other_st_list = sorted({
                    clean_str(l.get("stage")) for _, l in cons_lines
                    if clean_str(l.get("stage")) in ("S3", "S4")
                })
                if assoc_lines:
                    for _, l in assoc_lines:
                        ast = clean_str(l.get("stage", "UNKNOWN"))
                        if ast != "UNKNOWN":
                            other_st_list.append(f"ASSOCIATE_ONLY:{ast}")
                other_stages = ";".join(other_st_list) or "NONE"
                entity_scope_str = "; ".join(
                    dict.fromkeys(f"{clean_str(l.get('entity_scope','UNKNOWN'))}({clean_str(l.get('ownership_scope','UNKNOWN'))})" for _, l in chosen_lines)
                )
                bucket_rule = (
                    "PRIMARY_BUCKET_EARLY_S0_S2_FIRST_WITH_OTHER_STAGES_PRESERVED"
                    if other_st_list else "SINGLE_STAGE_EARLY_S0_S2"
                )
            elif sid == "BJ:920100":
                bucket = "EARLY_RD_PROTOTYPE_SAMPLING"
                fact_tier = "S0_RD_STAGE_UNKNOWN"
                chosen_lines = cons_lines or lines
                prio = "P2_MEDIUM"
                entity_scope_str = "; ".join(
                    dict.fromkeys(f"{clean_str(l.get('entity_scope','UNKNOWN'))}({clean_str(l.get('ownership_scope','UNKNOWN'))})" for _, l in chosen_lines)
                )
                bucket_rule = "RD_COMPLETED_STAGE_UNKNOWN_EARLY_RESERVE"
            elif s3_cons:
                bucket = "EARLY_PILOT_SMALL_BATCH"
                fact_tier = "S3_SMALL_BATCH_PILOT"
                chosen_lines = s3_cons
                prio = "P1_HIGH"
                entity_scope_str = "; ".join(
                    dict.fromkeys(f"{clean_str(l.get('entity_scope','UNKNOWN'))}({clean_str(l.get('ownership_scope','UNKNOWN'))})" for _, l in chosen_lines)
                )
                bucket_rule = "CONSOLIDATED_S3_SMALL_BATCH"
            elif s4_cons:
                bucket = "COMMERCIAL_NON_MAINLINE_RESERVE"
                fact_tier = "S4_BATCH_NON_MAINLINE"
                chosen_lines = s4_cons
                prio = "P1_HIGH"
                entity_scope_str = "; ".join(
                    dict.fromkeys(f"{clean_str(l.get('entity_scope','UNKNOWN'))}({clean_str(l.get('ownership_scope','UNKNOWN'))})" for _, l in chosen_lines)
                )
                bucket_rule = "CONSOLIDATED_S4_NON_MAINLINE"
            else:
                bucket = "EVIDENCED_PRODUCT_STAGE_UNKNOWN"
                fact_tier = "DIRECT_OR_INDIRECT_STAGE_UNKNOWN"
                chosen_lines = cons_lines or lines
                prio = "P2_MEDIUM"
                entity_scope_str = "; ".join(
                    dict.fromkeys(f"{clean_str(l.get('entity_scope','UNKNOWN'))}({clean_str(l.get('ownership_scope','UNKNOWN'))})" for _, l in chosen_lines)
                )
                bucket_rule = "EVIDENCED_PRODUCT_STAGE_UNKNOWN"

            prod_line = "; ".join(clean_str(l.get("product_line", "")) for _, l in chosen_lines[:2])
            if sid == "SH:603219":
                fact_sum = (
                    "上市母公司(富佳股份)：扫地机器人ODM代工，收入并入清洁类小家电，商业阶段UNKNOWN(R1B1-PL046/R1B1-E061)；"
                    "非并表参股公司(芯禾机器人)：LD05虫情设备小批量(S3)与粮仓平粮机器人样机测试(S1)仅作间接观察(R1B1-PL047/048)。"
                )
            elif other_stages != "NONE" and bucket == "EARLY_RD_PROTOTYPE_SAMPLING":
                other_desc = "; ".join(
                    f"{clean_str(l.get('line_id'))}:{clean_str(l.get('product_line'))}[{clean_str(l.get('stage'))}]"
                    for _, l in cons_lines if clean_str(l.get("stage")) in ("S3", "S4")
                )
                fact_sum = (
                    f"早期主观察线："
                    + "; ".join(f"[{clean_str(l.get('stage','UNKNOWN'))}] {clean_str(l.get('product_line'))}:{clean_str(l.get('commercial_fact',''))}" for _, l in chosen_lines[:2])
                    + (f"；同公司另存较高阶段产品线：{other_desc}" if other_desc else "")
                )
            else:
                fact_sum = "; ".join(
                    f"[{clean_str(l.get('stage','UNKNOWN'))}] {clean_str(l.get('commercial_fact',''))}"
                    for _, l in chosen_lines[:2]
                )

            eids, non_adopted_loc, urls, dates, pages, quotes, binding_str = bind_archive_evidence(sid, chosen_lines)
            robot_exp = clean_str(cls_r.get("robot_exposure", "UNKNOWN")) or "UNKNOWN"
            rev_status = "ARCHIVE_ADOPTED_WITH_LIMITS"
            limits = "沿用archive旧分类附限制采用（53家口径）；非投资建议，不代表已商业化或已通过S05主线"

            if sid == "SH:688165":
                # Codex R1 item 2: bind Efort Yobot R1 decisive S1 release page 32, award page 25,
                # and R1B1-E001 page 19 non-mass-production boundary from DOC-586ED2C18DB28CDE
                ef_url = clean_str(efort_doc["primary_url"])
                ef_pub = clean_str(efort_doc["published_on"])
                fact_sum = (
                    "早期主观察线：[S1]人形机器人Yobot R1（控股子公司启智机器人）—2025年报(DOC-586ED2C18DB28CDE)物理/印刷第32页记载"
                    "2025年2月发布第一款人形机器人Yobot R1和Yobot W1并配具名产品图（S1决定性原页）；第25页记载获安徽省第十二届工业设计大赛金奖；"
                    "第19页(R1B1-E001)界定截至2025-12-31尚未量产（不支持外部试点、销售或量产）。同公司另存较高阶段产品线：R1B1-PL001:工业机器人整机[S4]"
                )
                urls = f"DOC-586ED2C18DB28CDE;{ef_url}"
                dates = ef_pub
                pages = "物理/印刷第32页(S1发布决定性原页);物理/印刷第25页(获奖);物理/印刷第19页(R1B1-E001量产边界)"
                quotes = (
                    "[P32] 2025年2月，公司发布了第一款人形机器人Yobot R1和Yobot W1，在此基础上进行迭代和研发（配具名产品图） | "
                    "[P25] 双足人形机器人Yobot R1均荣获安徽省第十二届工业设计大赛金奖 | "
                    "[P19/R1B1-E001] 注：截至2025年12月31日，智能机器人通用技术底座、复合机器人、人形机器人、智能机器人解决方案及工作站尚未量产。"
                )
                binding_str = (
                    f"DOC-586ED2C18DB28CDE(P32_S1_DECISIVE)|{ef_url}|{ef_pub}|物理/印刷第32页|S06_DIRECT_PDF_READ_SHA256_586ed2c1 || "
                    f"DOC-586ED2C18DB28CDE(P25_AWARD)|{ef_url}|{ef_pub}|物理/印刷第25页|S06_DIRECT_PDF_READ_SHA256_586ed2c1 || "
                    f"R1B1-E001(P19_MASS_PROD_BOUNDARY)|{ef_url}|{ef_pub}|物理/印刷第19页|ARCHIVE_ADOPTED_WITH_LIMITS"
                )
                limits = (
                    "Yobot R1的S1样机发布由2025年报DOC-586ED2C18DB28CDE(SHA-256 586ed2c1...)物理/印刷第32页支撑、获奖见第25页、"
                    "第19页(R1B1-E001)界定截至2025-12-31尚未量产；该证据不支持外部试点、销售或该型号量产；工业机器人整机S4另行保留；非投资建议"
                )

        elif sid in c00_scr:
            pkg_tag = "C00_PILOT_01"
            r = c00_scr[sid]
            evs = c00_ev.get(sid, [])
            exp_prop = clean_str(r.get("robot_exposure_proposal", "UNKNOWN"))
            prod_line = clean_str(r.get("specific_robot_product", ""))

            if sid == "SH:605555":
                # Codex 1.1: 德昌股份 moved OUT of S3; use C00-EV-605555-03 physical page 12
                bucket = "EVIDENCED_PRODUCT_STAGE_UNKNOWN"
                fact_tier = "PRODUCT_RAMP_DELIVERY_STAGE_UNKNOWN"
                prio = "P2_MEDIUM"
                prod_line = "割草机器人（2026H1园林工具新品推进量产，交付与收入阶段待核）"
                fact_sum = (
                    "2026H1物理第12/165页(C00-EV-605555-03)披露割草机器人、翻土机等园林工具新品顺利推进量产；"
                    "未披露外部客户、付费试点、小批量供货或机器人销售收入，交付阶段留作待核，不计入S3。"
                )
                primary_evs = [c00_ev_by_id["C00-EV-605555-03"]]
                entity_scope_str = "LISTED_PARENT_PRODUCT_SCOPE_TO_VERIFY"
                bucket_rule = "C00_PRODUCT_RAMP_DELIVERY_UNVERIFIED_NOT_S3"
            elif sid == "SH:600366":
                # Codex 1.1: 宁波韵升 primary fact MUST adopt C00-EV-600366-03 physical page 11
                bucket = "EARLY_RD_PROTOTYPE_SAMPLING"
                fact_tier = "SAMPLING_AND_SUPPLY_SCALE_UNKNOWN"
                prio = "P1_HIGH"
                prod_line = "钕铁硼永磁材料（人形机器人领域长期协议、样品交付与供货；规模/收入/毛利UNKNOWN）"
                fact_sum = (
                    "2026H1物理第11/178页(C00-EV-600366-03)明确披露在人形机器人领域与头部企业绑定、签订长期协议、完成样品交付与供货；"
                    "同报告物理第9页(C00-EV-600366-02)亦提及新兴应用市场数个项目开发或交样。"
                    "未知边界：客户身份、供货规模、机器人收入与毛利均未披露，不推定S3/S4或量化在手订单金额。"
                )
                primary_evs = [c00_ev_by_id["C00-EV-600366-03"], c00_ev_by_id["C00-EV-600366-02"]]
                entity_scope_str = "LISTED_PARENT"
                bucket_rule = "C00_REVIEW_UPDATED_PAGE11_SUPPLY_SCALE_UNKNOWN"
            elif sid == "SH:688698":
                bucket, fact_tier, prio = "EARLY_RD_PROTOTYPE_SAMPLING", "S0_RD_PRODUCT_UNVERIFIED_SHIPMENT", "P2_MEDIUM"
                fact_sum = clean_str(r.get("decision_reason", ""))
                primary_evs = evs
                entity_scope_str = clean_str(r.get("entity_scope", "LISTED_PARENT"))
                bucket_rule = "C00_PRODUCT_LINE_UNVERIFIED_SHIPMENT"
            elif sid == "SH:600845":
                bucket, fact_tier, prio = "EARLY_RD_PROTOTYPE_SAMPLING", "S1_PROTOTYPE_UNVERIFIED_DELIVERY", "P1_HIGH"
                fact_sum = clean_str(r.get("decision_reason", ""))
                primary_evs = evs
                entity_scope_str = clean_str(r.get("entity_scope", "LISTED_PARENT"))
                bucket_rule = "C00_PROTOTYPE_WAREHOUSED_UNVERIFIED_EXTERNAL_DELIVERY"
            elif sid == "SH:603933":
                bucket, fact_tier, prio = "EARLY_PILOT_SMALL_BATCH", "S3_SMALL_BATCH_PILOT", "P1_HIGH"
                fact_sum = clean_str(r.get("decision_reason", ""))
                primary_evs = sorted(evs, key=lambda x: x["evidence_id"], reverse=True)
                entity_scope_str = clean_str(r.get("entity_scope", "LISTED_PARENT"))
                bucket_rule = "C00_SMALL_BATCH_DELIVERY_CONFIRMED_SELF_CHECK"
            else:
                bucket, fact_tier, prio = "COMMERCIAL_NON_MAINLINE_RESERVE", "S4_OR_COMMERCIAL_NON_MAINLINE_C00", "P1_HIGH"
                fact_sum = clean_str(r.get("decision_reason", ""))
                primary_evs = evs
                entity_scope_str = clean_str(r.get("entity_scope", "LISTED_PARENT"))
                bucket_rule = "C00_COMMERCIAL_NON_MAINLINE"

            eids = ";".join(clean_str(e.get("evidence_id", "")) for e in primary_evs) or "UNKNOWN"
            urls = ";".join(
                dict.fromkeys(
                    clean_str(e.get("document_id", "") or e.get("primary_url", ""))
                    for e in primary_evs
                    if clean_str(e.get("document_id", "") or e.get("primary_url", ""))
                )
            ) or "UNKNOWN"
            dates = ";".join(
                dict.fromkeys(clean_str(e.get("published_on", "")) for e in primary_evs if clean_str(e.get("published_on", "")))
            ) or "UNKNOWN"
            pages = ";".join(
                dict.fromkeys(extract_page(e) for e in primary_evs if extract_page(e) != "UNKNOWN")
            ) or "UNKNOWN"
            quotes = " | ".join(truncate(e.get("quoted_excerpt", "") or e.get("claim", ""), 120) for e in primary_evs[:3]) or "UNKNOWN"
            binding_str = " || ".join(
                f"{clean_str(e.get('evidence_id'))}|{clean_str(e.get('document_id') or e.get('primary_url'))}|{clean_str(e.get('published_on','UNKNOWN'))}|{extract_page(e)}|{clean_str(e.get('review_status','UNKNOWN'))}"
                for e in primary_evs[:3]
            )
            all_lines_str = f"C00_SINGLE_LINE|{truncate(prod_line, 90)}|{entity_scope_str}|fact_tier={fact_tier}|ev={eids}"
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
            pages = extract_page(re)
            quotes = truncate(re.get("quoted_excerpt", "") or re.get("claim_text", ""), 140)
            binding_str = f"{eids}|{urls}|{dates}|{pages}|{clean_str(re.get('review_status','UNKNOWN'))}"
            entity_scope_str = "LISTED_CONSOLIDATED_CLAIM_ONLY"
            all_lines_str = f"EARLY_SAMPLE|{truncate(prod_line, 80)}|{entity_scope_str}|stage=UNKNOWN|ev={eids}"
            bucket_rule = "EARLY_SAMPLE_DIRECT_PRODUCT_STAGE_UNKNOWN"
            robot_exp = clean_str(rp.get("robot_exposure", "UNKNOWN"))
            rev_status = "EARLY_SAMPLE_CLAIM_ONLY_PENDING_FULL_CLASSIFICATION"
            limits = "10家早期样本仅局部业务存在性断言已核读，完整分类与产品线阶段仍UNKNOWN；非投资建议"
        else:
            continue

        a04r_cnt = len(a04r_kw_by_co.get(sid, []))
        watch_reason = (
            f"未入S05主线(278家)，当前位于776保留观察池({l2_dec})；"
            f"已有可追溯证据({pkg_tag}/{fact_tier})记录机器人相关业务/研发/样机/送样或小批量事实，按S06保留观察不因未盈利或财务缺口漏筛。"
        )
        reentry = build_reentry_condition(bucket, fact_tier, l2_dec, cutoff_flag, has_s02_gap, robot_exp)

        order_aux_note = (
            "NO_VERIFIED_QUANTIFIED_BACKLOG（2026H1物理第11页披露人形机器人长期协议与供货，但未披露可量化订单金额/交付期，按口径保持UNKNOWN）"
            if sid == "SH:600366"
            else "NO_VERIFIED_STRUCTURED_BACKLOG_IN_EXISTING_RECORDS（缺可核主体/时点/金额口径的正式在手订单披露）"
        )

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
            "bucket_selection_rule": bucket_rule,
            "other_verified_stages": other_stages,
            "entity_scope_and_ownership": entity_scope_str,
            "robot_exposure": robot_exp,
            "product_line": truncate(prod_line, 160),
            "disclosed_fact_summary": truncate(fact_sum, 260),
            "all_recorded_product_lines": all_lines_str,
            "evidence_source_package": pkg_tag,
            "evidence_ids": eids,
            "non_adopted_historical_locators": non_adopted_loc,
            "primary_evidence_binding": binding_str,
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
            "order_backlog_aux_note": order_aux_note,
            "watch_reason": watch_reason,
            "reentry_trigger_conditions": reentry,
            "verification_priority": prio,
            "limitations": limits,
        })

    bucket_order = {
        "EARLY_RD_PROTOTYPE_SAMPLING": 1,
        "EARLY_PILOT_SMALL_BATCH": 2,
        "COMMERCIAL_NON_MAINLINE_RESERVE": 3,
        "EVIDENCED_PRODUCT_STAGE_UNKNOWN": 4,
    }
    early_rows.sort(key=lambda r: (bucket_order[r["watch_bucket"]], r["verification_priority"], r["security_id"]))
    early_sids = {r["security_id"] for r in early_rows}

    # ------------------------------------------------------------------
    # 4. Build missing_data_watch.csv (baseline verified by Codex + 1.4 diagnostic scope)
    # ------------------------------------------------------------------
    missing_rows = []

    def s02_gap_detail(sid):
        rows = s02_by_co[sid]
        hold_m = sorted({r["metric_id"] for r in rows if r["metric_status"] == "HOLD"})
        miss_m = sorted({r["metric_id"] for r in rows if r["metric_status"] == "MISSING"})
        prov_m = sorted({r["metric_id"] for r in rows if r["metric_status"] == "PROVISIONAL"})
        nc_m = sorted({r["metric_id"] for r in rows if r["metric_status"] == "NOT_COMPARABLE"})
        ub_m = sorted({r["metric_id"] for r in rows if r["metric_status"] == "UNDEFINED_BASE"})
        return hold_m, miss_m, prov_m, nc_m, ub_m

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

        diag_scope = "FROZEN_CUTOFF_20261025_DIAGNOSTIC"
        if cutoff_flag == "YES" or l2_dec == "WATCH_AFTER_CUTOFF":
            cat = "AFTER_CUTOFF_ISOLATED"
            prio = "P1_HIGH"
            diag_scope = "AFTER_CUTOFF_ISOLATED_DIAGNOSTIC_ONLY_NOT_ADMISSIBLE_BEFORE_R05"
            reason = (
                "资料披露晚于冻结研究截止日(2026-10-25)，按S02合同(s03_input_contract.json)强制隔离，不准入干净信号；"
                "本行所列S02裸状态/缺口计数仅为隔离期诊断参考，S07抽样须继续执行截止日约束。"
            )
            reentry = "待冻结截止日升级后的增量版本(R05)纳入2026-10-25之后正式定期报告并全链路重算S02-S05。"
        elif anchor_flag == "YES" or l2_dec == "PENDING_ANCHOR_RESELECTION":
            cat = "PENDING_ANCHOR_RESELECTION"
            prio = "P1_HIGH"
            reason = "锚定期选定待重选（S04/S05延续守卫），当前锚点与基期对齐未冻结。"
            reentry = "完成锚定期重选与对应正式报告原文核验，重算S02/S04指标并复核是否进入S05主线。"
        elif l2_dec == "HOLD_FOR_DATA":
            cat = "S04_HOLD_FOR_DATA_AND_QUALITY_SOURCE_UNKNOWN" if qs_state == "PENDING_CE_SOURCE" else "S04_HOLD_FOR_DATA"
            prio = "P1_HIGH" if (sid in early_sids or qs_state == "PENDING_CE_SOURCE" or len(hold_m) > 0 or len(miss_m) > 0) else "P2_MEDIUM"
            sub_reasons = ["S04 L2判定HOLD_FOR_DATA（存在未闭合S00勘误/来源待核/重述待核或关键指标缺口）"]
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
            reason = f"位于776保留池({l2_dec})且存在质量来源未知({r776['quality_source_pending_metrics']})；S02 HOLD={','.join(hold_m) or 'NONE'}, MISSING={','.join(miss_m) or 'NONE'}。"
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
            "s02_gap_diagnostic_scope": diag_scope,
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
            "s02_gap_diagnostic_scope": "FROZEN_CUTOFF_20261025_DIAGNOSTIC",
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
    with open(OUT / "early_stage_watch.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(early_rows[0].keys()), lineterminator="\n")
        w.writeheader()
        w.writerows(early_rows)

    with open(OUT / "missing_data_watch.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(missing_rows[0].keys()), lineterminator="\n")
        w.writeheader()
        w.writerows(missing_rows)

    early_bucket_cnt = Counter(r["watch_bucket"] for r in early_rows)
    early_tier_cnt = Counter(r["fact_tier"] for r in early_rows)
    missing_cat_cnt = Counter(r["missing_data_category"] for r in missing_rows)
    missing_dedup_cnt = Counter(r["mainline_dedup_status"] for r in missing_rows)
    overlap_early_missing = len(early_sids & {r["security_id"] for r in missing_rows})
    non_mainline_missing_cnt = missing_dedup_cnt["NON_MAINLINE_776"]
    mainline_observe_missing_cnt = missing_dedup_cnt["MAINLINE_S05_OBSERVE_CARRYOVER_DO_NOT_DOUBLE_COUNT"]
    union_non_mainline_watch = len(early_sids | {r["security_id"] for r in missing_rows if r["mainline_dedup_status"] == "NON_MAINLINE_776"})

    # ------------------------------------------------------------------
    # 6. Write watch_reentry_rules.md
    # ------------------------------------------------------------------
    reentry_md = f"""# S06 观察名单准入、去重、辅助观察口径与重进规则（返修轮 {REWORK_ROUND}）

- 任务编号：S06（GitHub #41）
- 计划版本：`{PLAN_VERSION}`
- 知识截止日：`{KNOWLEDGE_AS_OF}`（冻结不变）
- 放行依据：`runs/issues/S06/release_20261122.json`、`runs/issues/S06/handoff_from_s05_20261122.md`
- 返修依据：`runs/issues/S06/codex_review_s06_20261122.md`、`runs/issues/S06/codex_review_s06_r1_20261123.md`（本地复核溯源引用，非运行必需输入）
- 需求先行指标方法依据：`METHOD_20261107_LEADING_INDICATORS`（`docs/需求先行指标分工_20261107.md`、`data/methodology_decision_20261107.json`）
- 辅助观察版本：`{AUX_METHOD_VERSION}`
- 生成时间：`{NOW}`

---

## 一、主线去重与全池主键守恒规则

1. **权威主键基线**：`data/company_master.csv` 共 1,054 家唯一 `security_id`，与 S05 验收分区完全互斥且覆盖：
   - S05 主线通过对照（`runs/issues/S05/quality_pass.csv`）：**277 家**
   - S05 主线观察对照（`runs/issues/S05/quality_observe.csv`）：**1 家**（`SZ:000856` {master['SZ:000856']['stock_name']}）
   - 上游保留观察入口（`runs/issues/S05/observe_pool_preserved_776.csv`）：**776 家**
   - 合计：`277 + 1 + 776 = 1,054` 家，主键 0 重复、0 遗漏。
2. **严格去重原则**：
   - `early_stage_watch.csv`（共 **{len(early_rows)} 家**）**全部来自 776 非主线池**，与 S05 278 主线（277 通过 + 1 观察）**0 重叠**。已有历史证据但已进入 S05 主线的 **{len(mainline_dedup_records)} 家**公司不重复计入早期观察，仅在 `handoff.md` 列明对照。
   - `missing_data_watch.csv`（共 **{len(missing_rows)} 家**）由 **{non_mainline_missing_cnt} 家**非主线 776 缺数据/守卫公司（`NON_MAINLINE_776`）与 **{mainline_observe_missing_cnt} 家** S05 主线观察结转（`SZ:000856` {master['SZ:000856']['stock_name']}，`MAINLINE_S05_OBSERVE_CARRYOVER_DO_NOT_DOUBLE_COUNT`）构成，与 S05 277 `quality_pass.csv` **0 重叠**。
   - 两张观察表之间的交集为 **{overlap_early_missing} 家**（已在 `missing_data_watch.csv` 的 `in_early_stage_watch=YES` 显式标出，非主线观察去重并集共 **{union_non_mainline_watch} 家**）。

---

## 二、早期储备观察（`early_stage_watch.csv`）准入、主体绑定与多产品线规则

1. **硬证据门槛（杜绝概念污染与误采用）**：
   - 仅复用已有可追溯证据（`archive/` 53 家旧分类附限制采用、10 家早期样本局部断言、`packages/B00_SOURCE_01/02`、`packages/C00_PILOT_01`），**不扩大全池采集或新增企业深研**。
   - 凡源登记标为 `DO_NOT_ADOPT`（如 `BJ:920124` 南特科技旧镜像 `R1A02-E001`）的记录**严禁列入采用 `evidence_ids`**，仅降格记录在 `non_adopted_historical_locators`。
   - `runs/issues/A04R/keyword_originals.jsonl` 仅作原文定位器（locator），不单独构成业务事实准入依据。
   - 已有核查但为无机器人产品/仅意向/仅计划/仅 RPA/证据不足的 **{len(REVIEWED_EXCLUDED_NON_MAINLINE)} 家**非主线公司与主表外 1 家（`BJ:920007`）**明确不纳入**；其余未深研非主线公司保持 `UNKNOWN`，不凭概念纳入，也不反推精确的“无业务公司数”。
2. **主体绑定与多产品线保留规则（R1 修订重点）**：
   - **主体严格分离**：非并表参股公司产品线（`ASSOCIATE_NOT_CONSOLIDATED`）不得决定上市主体主桶；例如 `SH:603219` 富佳股份按上市母公司扫地机器人 ODM（`stage=UNKNOWN`）归入 `EVIDENCED_PRODUCT_STAGE_UNKNOWN`，参股公司芯禾机器人（`S1`/`S3`）仅作为间接观察保留在 `all_recorded_product_lines` 与 `other_verified_stages`。
   - **多产品线全量保留**：公司按 `security_id` 去重为一行；当并表/上市主体同时存在早期线（`S0`–`S2`）与较高阶段线（`S3`/`S4`）时，主桶优先服务早期观察（`bucket_selection_rule=PRIMARY_BUCKET_EARLY_S0_S2_FIRST_WITH_OTHER_STAGES_PRESERVED`），同时在 `all_recorded_product_lines` 与 `other_verified_stages` 中完整保留全部已核产品线、阶段、主体与证据 ID（涵盖华勤技术 `R1B02-PL041` S4、捷昌驱动 `R1A02-PL013` S4、埃夫特 `R1B1-PL001` S4、新时达 `R1B1-PL006/007` S3），确保 S07 分层抽样同步取到全部阶段证据。
3. **四类观察分桶（R1 重算结果，共 {len(early_rows)} 家）**：
   - `EARLY_RD_PROTOTYPE_SAMPLING`（**{early_bucket_cnt['EARLY_RD_PROTOTYPE_SAMPLING']} 家**）：并表/上市主体已记录研发（`S0`）、样机（`S1`）、送样（`S2`）或供货规模待核的早期线索（含宁波韵升 2026H1 物理第 11 页长期协议/样品交付与供货，规模与收入未知）。
   - `EARLY_PILOT_SMALL_BATCH`（**{early_bucket_cnt['EARLY_PILOT_SMALL_BATCH']} 家**）：并表/上市主体已记录付费试点/小批量交付（`S3`）；德昌股份因未证外部交付已移出本桶。
   - `COMMERCIAL_NON_MAINLINE_RESERVE`（**{early_bucket_cnt['COMMERCIAL_NON_MAINLINE_RESERVE']} 家**）：已记录 `S4` 批量交付或 C00 确认商业化主业，但因财务指标、`HOLD_FOR_DATA` 或截止日后隔离未进 S05 主线。
   - `EVIDENCED_PRODUCT_STAGE_UNKNOWN`（**{early_bucket_cnt['EVIDENCED_PRODUCT_STAGE_UNKNOWN']} 家**）：已核实存在机器人产品/业务或量产推进，但交付/商业阶段为 `UNKNOWN`（含富佳股份上市母公司口径、德昌股份物理第 12 页量产推进未证外部交付）。
4. **非推荐边界**：观察名单不是买入推荐、投资候选或已商业化认定，不跳过 S07/S08 进入估值。

---

## 三、缺数据观察（`missing_data_watch.csv`）与截止日诊断约束

1. **纳入范围**（共 **{len(missing_rows)} 家** = **{non_mainline_missing_cnt} 家非主线** + **1 家 S05 主线观察**）：
   - `S05_QUALITY_HOLD_CONSOLIDATION_SCOPE_UNKNOWN`（**{missing_cat_cnt['S05_QUALITY_HOLD_CONSOLIDATION_SCOPE_UNKNOWN']} 家**）：`SZ:000856` {master['SZ:000856']['stock_name']}。
   - `AFTER_CUTOFF_ISOLATED`（**{missing_cat_cnt['AFTER_CUTOFF_ISOLATED']} 家**）：`SH:603448` {master['SH:603448']['stock_name']}、`SH:688836` {master['SH:688836']['stock_name']}、`SZ:301348` {master['SZ:301348']['stock_name']}、`SZ:301699` {master['SZ:301699']['stock_name']}。**这 4 家的 `s02_gap_diagnostic_scope` 明确标注为 `AFTER_CUTOFF_ISOLATED_DIAGNOSTIC_ONLY_NOT_ADMISSIBLE_BEFORE_R05`**，其 S02 裸状态计数仅作隔离期诊断，S07 抽样须继续严格执行 `2026-10-25` 截止日隔离。
   - `PENDING_ANCHOR_RESELECTION`（**{missing_cat_cnt['PENDING_ANCHOR_RESELECTION']} 家**）：`SZ:002083` {master['SZ:002083']['stock_name']}。
   - `S04_HOLD_FOR_DATA_AND_QUALITY_SOURCE_UNKNOWN`（**{missing_cat_cnt['S04_HOLD_FOR_DATA_AND_QUALITY_SOURCE_UNKNOWN']} 家**）与 `QUALITY_SOURCE_UNKNOWN_NON_MAINLINE`（**{missing_cat_cnt['QUALITY_SOURCE_UNKNOWN_NON_MAINLINE']} 家**）：合计严格等于 **15 家**质量来源未知（`PENDING_CE_SOURCE`）。
   - `S04_HOLD_FOR_DATA`（**{missing_cat_cnt['S04_HOLD_FOR_DATA']} 家**）：与上面 9 家合计严格等于 **328 家** `HOLD_FOR_DATA`。
   - `S02_METRIC_HOLD_OR_MISSING_NON_MAINLINE`（**{missing_cat_cnt['S02_METRIC_HOLD_OR_MISSING_NON_MAINLINE']} 家**）。
2. **未决守卫结转**：4 家截止日后隔离、1 家锚点待重选、15 家质量来源未知、8 项未采用父链提议（`#53` 开放）、S05 专门待核均原样保留；缺数据不填零。

---

## 四、需求先行辅助观察口径登记（`{AUX_METHOD_VERSION}`）

依据 `METHOD_20261107_LEADING_INDICATORS`（`data/methodology_decision_20261107.json`），预先登记 `{AUX_METHOD_VERSION}`：

| 登记项 | 合同负债（`AUX.CONTRACT_LIAB`） | 可信在手订单（`AUX.VERIFIED_BACKLOG`） |
|---|---|---|
| **辅助观察版本** | `{AUX_METHOD_VERSION}`（独立辅助观察标签，不改 S01/S04/S05 冻结硬门槛） | `{AUX_METHOD_VERSION}`（独立辅助观察标签，不改 S01/S04/S05 冻结硬门槛） |
| **字段定义** | 合并资产负债表“合同负债”期末余额（人民币元），须与合同资产（`FIN.CONTRACTASSET.INSTANT`）严格分列 | 正式公告/定期报告明确披露的已生效且可量化在手合同/订单金额，须区分生效订单、长期框架协议、已履行部分及取消/变更风险 |
| **来源与期间** | 合并资产负债表原页（锚定期与上年同期同口径配对）；当前不在 P04/S00 冻结标准化字段内 | 交易所正式定期报告、重大合同签约公告原页（含物理页码与主体范围）；`A04R` 仅作定位器 |
| **适用业务模式** | 项目型系统集成（`PROJECT`）、定制设备/预收款模式优先参考；结合付款条款解释 | 项目型与大额配套/运维服务合同；框架协议或长期协议（如 `SH:600366` 宁波韵升 2026H1 第 11 页长期协议、主线对照 `BJ:920207` 众诚科技按实际下单结算合同）不推定为确定在手订单金额 |
| **当前取值与缺失语义** | 非主线观察名单统一记 `UNKNOWN`（`NOT_IN_FROZEN_S00_SCHEMA`），不填 0、不淘汰 | 非主线观察名单统一记 `UNKNOWN`，不填 0、不淘汰 |
| **既有主线参考（不重复计入非主线）** | `packages/D00_B00_ADVANCE_01/results/evidence.csv` 记录主线 `BJ:920578` 巨能股份 2026H1 合同负债较期初下降 34.59% | `packages/D00_B00_ADVANCE_01/results/evidence.csv` 记录主线 `BJ:920207` 众诚科技数采中心合同（83,123,260 元/年、按实际下单结算，实际履约待核） |
| **重进/升级条件** | 对特定观察对象定向回读已归档报告合并资产负债表原页并登记同口径对比后解除 `UNKNOWN` | 取得正式原文核实主体、统计时点、生效状态与可量化金额口径后方可转为已核辅助观察；订单转化与在建工程留 R00/R01 核验 |

---

## 五、可验证的重进条件（主线准入与业务核证分离）

每家公司均在 `reentry_trigger_conditions` 中分列两部分：
1. **【主线重进】**：严格按冻结 S01/S04/S05/R05 规则执行（截止日隔离→R05 增量重算；`HOLD_FOR_DATA`→闭合财务/来源/重述缺口后重算 L2；未入围→后续定期报告出现至少 2 个干净维度改善信号并通过 S05），禁止手工加回。
2. **【业务核证目标】**：按各自 `fact_tier` 与主体范围写明具体可验证节点（`S0`→`S1`/`S2`、`S1`→`S2`/`S3`、`S2`→`S3`、`S3`→`S4`、宁波韵升→核供货规模与收入归属、德昌股份→核外部交付、富佳股份→母公司与参股分核），不强行套用“必须单列独立分部毛利”的一刀切模板。
"""
    (OUT / "watch_reentry_rules.md").write_bytes(reentry_md.replace("\r\n", "\n").encode("utf-8"))

    # ------------------------------------------------------------------
    # 7. Write handoff.md (R1)
    # ------------------------------------------------------------------
    mainline_list_md = "\n".join(
        f"| `{m['security_id']}` | {m['stock_name']} | `{m['s05_route']}` | `{m['existing_evidence_sources']}` |"
        for m in mainline_dedup_records
    )
    excluded_list_md = "\n".join(
        f"| `{sid}` | {master[sid]['stock_name']} | `{pkg}` | {why} |"
        for sid, (pkg, why) in sorted(REVIEWED_EXCLUDED_NON_MAINLINE.items())
    )

    handoff_md = f"""# S06 早期储备与缺数据观察交接（#41，返修轮 {REWORK_ROUND}）

- 执行者：Antigravity
- 复核方：Codex（待 R2 独立复核）
- 计划版本：`{PLAN_VERSION}`
- 知识截止日：`{KNOWLEDGE_AS_OF}`
- 放行依据：`runs/issues/S06/release_20261122.json`、`runs/issues/S06/handoff_from_s05_20261122.md`
- 返修依据：`runs/issues/S06/codex_review_s06_20261122.md`、`runs/issues/S06/codex_review_s06_r1_20261123.md`（本地复核溯源引用，非运行必需输入）
- 性质：执行方自检（`SELF_CHECK`），**不等同独立验收**；待 Codex 复核通过后再决定是否验收与放行 S07。

---

## 一、本轮针对 Codex 复核意见的逐项修订（R1 + R2）

1. **R2 发布复现与哈希口径修正（对应 R1 复核第 1 节）**：
   - 将未进入 Git 提交的本地复核记录移出运行必需输入清单，转入 `manifest.json` 的 `review_provenance_refs`；运行时实际读取的全部 **{len(READ_INPUTS)} 份输入文件**（含 `data/document_registry.csv`）100% 位于目标 Git 提交树内。
   - `manifest.json` 显式采用 `input_hash_basis = CANONICAL_LF_BYTES`（对文本输入统一按 `\r\n -> \n` 规范化字节计算字节数与 SHA-256，消除 Git blob 与 Windows CRLF 检出换行差异），全部交付文件以纯 LF 写入（`deliverable_hash_basis = EXACT_BYTES_LF`），支持从干净 Git 提交独立重放 `step_s06_build.py` 与 `step_s06_verify.py` 逐字节复现全部交付、清单与根摘要。
2. **R2 埃夫特 `SH:688165` Yobot R1 原页绑定修正（对应 R1 复核第 2 节）**：
   - 直接核读本地归档 2025 年报原文 `DOC-586ED2C18DB28CDE`（277 页，SHA-256 `586ed2c18db28cdeb8b2df23bc9dc8ff995ec33bc37895c885b5e9aa8e426517`，与 `data/document_registry.csv` 一致）：绑定**物理/印刷第 32 页**（2025 年 2 月发布第一款人形机器人 Yobot R1 和 Yobot W1 并配具名产品图）为 S1 样机观察的决定性原页；绑定**物理/印刷第 25 页**支撑安徽省第十二届工业设计大赛金奖事实；保留**物理/印刷第 19 页（`R1B1-E001`）**作为截至 2025-12-31 尚未量产的状态边界（不支持外部试点、销售或该型号量产）；工业机器人整机 S4（`R1B1-PL001`）继续作为单独已核产品线保留。
3. **沿用已复核通过的 R1 修订（1.1–1.4）**：
   - 德昌股份 `SH:605555`（移出 S3，采用物理第 12 页 `C00-EV-605555-03`）、宁波韵升 `SH:600366`（同步采用物理第 11 页 `C00-EV-600366-03`，规模/收入/订单金额留 `UNKNOWN`）、富佳股份 `SH:603219`（上市母公司 ODM 与参股芯禾分离）、华勤/捷昌/埃夫特/新时达多产品线全量保留、24 家物理页码补齐、南特科技 `BJ:920124` 仅采用官方原文 `R1A02S-E001`（物理第 41 页）、重进条件分列主线重进与业务核证目标、4 家截止日后隔离公司显式标明隔离期诊断。

---

## 二、R2 重算结果汇总

1. **全池 1,054 家主键守恒与去重**：
   - S05 主线对照 **278 家** = `quality_pass.csv` **277 家** + `quality_observe.csv` **1 家**（`SZ:000856` {master['SZ:000856']['stock_name']}）。
   - 上游保留观察入口 `observe_pool_preserved_776.csv` **776 家**。
   - `277 + 1 + 776 = 1,054`，互斥且等于 `company_master.csv`。
2. **早期储备观察（`early_stage_watch.csv`：共 {len(early_rows)} 家，全部来自 776 非主线池，与 S05 278 主线 0 重叠）**：
   - `EARLY_RD_PROTOTYPE_SAMPLING`：**{early_bucket_cnt['EARLY_RD_PROTOTYPE_SAMPLING']} 家**（较初版 16 减 1：富佳股份按上市母公司口径移至阶段待核）
   - `EARLY_PILOT_SMALL_BATCH`：**{early_bucket_cnt['EARLY_PILOT_SMALL_BATCH']} 家**（较初版 7 减 1：德昌股份移出 S3 计数）
   - `COMMERCIAL_NON_MAINLINE_RESERVE`：**{early_bucket_cnt['COMMERCIAL_NON_MAINLINE_RESERVE']} 家**（不变）
   - `EVIDENCED_PRODUCT_STAGE_UNKNOWN`：**{early_bucket_cnt['EVIDENCED_PRODUCT_STAGE_UNKNOWN']} 家**（较初版 20 增 2：承接富佳股份与德昌股份）
3. **缺数据观察（`missing_data_watch.csv`：共 {len(missing_rows)} 家 = {non_mainline_missing_cnt} 家非主线 776 + {mainline_observe_missing_cnt} 家 S05 主线观察结转，与 S05 277 `quality_pass.csv` 0 重叠）**：
   - 7 类分布与初版完全一致（已由 Codex 独立复算 12,648 格验证通过）：冀东装备 1、截止日后隔离 4、锚点待重选 1、S04 待核且质量来源未知 9、非主线质量来源未知 6、其余 S04 待核 319、其余 S02 HOLD/MISSING 39。
4. **两表交集与并集**：交集 **{overlap_early_missing} 家**，776 池内去重并集 **{union_non_mainline_watch} 家**。

---

## 三、与 S05 主线去重清单（{len(mainline_dedup_records)} 家，不重复计入 `early_stage_watch.csv`）

| security_id | 公司简称 | S05 主线路由 | 已有证据来源 |
|---|---|---|---|
{mainline_list_md}

---

## 四、已核查但未纳入早期储备的非主线公司（{len(REVIEWED_EXCLUDED_NON_MAINLINE)} 家）

| security_id | 公司简称 | 核查来源 | 不纳入理由 |
|---|---|---|---|
{excluded_list_md}

另：历史 `BJ:920007`（酉立智能）不在冻结 1,054 主表内，已剔除。其余未深研非主线公司保持 `UNKNOWN`。

---

## 五、限制与下一步

- 本轮仍为执行方自检（`SELF_CHECK`），不等同独立验收；不释放 S07/S08，不改动 `#53` 残余结论。
- 合同负债与可信在手订单按 `S06_AUX_LEAD_V1` 保持 `UNKNOWN`，不填 0，合同资产分列。
- 下一步：提交 Codex 进行 R1 独立复核。
"""
    (OUT / "handoff.md").write_bytes(handoff_md.replace("\r\n", "\n").encode("utf-8"))

    print(json.dumps({
        "rework_round": REWORK_ROUND,
        "early_stage_watch_count": len(early_rows),
        "early_stage_by_bucket": dict(early_bucket_cnt),
        "early_stage_by_fact_tier": dict(early_tier_cnt),
        "missing_data_watch_count": len(missing_rows),
        "overlap_early_and_missing": overlap_early_missing,
        "union_non_mainline_watch": union_non_mainline_watch,
        "read_inputs_count": len(READ_INPUTS),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
