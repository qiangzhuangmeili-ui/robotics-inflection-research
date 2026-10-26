#!/usr/bin/env python3
"""P00 冻结：从 data/company_master.csv 复算候选池指纹与采集合同。

只读输入，只写 runs/issues/P00/ 下三份交付。不联网、不下载、不筛公司。

用法：
    python tools/p00_freeze_scope.py

可复算性：除 generated_at / base_commit 外，输出完全由输入文件内容决定。
canonical_sha256 只覆盖 (security_id, stock_code, stock_name, exchange) 的规范序列化，
不含时间戳，任何人重跑应得到同一哈希。
"""
from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs" / "issues" / "P00"
MASTER = ROOT / "data" / "company_master.csv"
QUEUE = ROOT / "data" / "intake_company_queue.csv"
REGISTRY = ROOT / "data" / "document_registry.csv"
BATCH_INDEX = ROOT / "data" / "intake_batch_index.csv"
PROJECT_STATE = ROOT / "PROJECT_STATE.json"

PLAN_VERSION = "20261026_collection_first_v2"
ISSUE_NUMBER = 11
ISSUE_KEY = "P00"
EXECUTOR = "WorkBuddy AI (executor=AI, review=SELF_CHECK)"
COLLECTION_DATE = "2026-10-26"

# 六个核心全文槽：1054 × 6 = 6324 只是槽位上界，不是应有文件数。
CORE_SLOTS = [
    ("annual_2023", "ANNUAL_REPORT", "FY2023", "2023-01-01", "2023-12-31", "2024-04-30"),
    ("annual_2024", "ANNUAL_REPORT", "FY2024", "2024-01-01", "2024-12-31", "2025-04-30"),
    ("annual_2025", "ANNUAL_REPORT", "FY2025", "2025-01-01", "2025-12-31", "2026-04-30"),
    ("h1_2024", "SEMI_ANNUAL_REPORT", "2024H1", "2024-01-01", "2024-06-30", "2024-08-31"),
    ("h1_2025", "SEMI_ANNUAL_REPORT", "2025H1", "2025-01-01", "2025-06-30", "2025-08-31"),
    ("h1_2026", "SEMI_ANNUAL_REPORT", "2026H1", "2026-01-01", "2026-06-30", "2026-08-31"),
]

# A股定期报告体系里没有单独的一季报/三季报之外的季度报告：
# Q2 由半年报覆盖、Q4 由年报覆盖，因此季度槽只有 Q1 与 Q3。
QUARTERLY_SLOTS = [
    ("q1_2024", "2024Q1", "2024-01-01", "2024-03-31", "2024-04-30"),
    ("q3_2024", "2024Q3", "2024-07-01", "2024-09-30", "2024-10-31"),
    ("q1_2025", "2025Q1", "2025-01-01", "2025-03-31", "2025-04-30"),
    ("q3_2025", "2025Q3", "2025-07-01", "2025-09-30", "2025-10-31"),
    ("q1_2026", "2026Q1", "2026-01-01", "2026-03-31", "2026-04-30"),
    ("q3_2026", "2026Q3", "2026-07-01", "2026-09-30", "2026-10-31"),
]

STATUS_VOCAB = [
    ("COLLECTED_IDENTITY_VERIFIED", "文件已取得，且公司主体/报告期/全文身份已核；不含业务结论核读。"),
    ("COLLECTED_PENDING_IDENTITY", "文件已取得，但身份尚未核（下载成功不等于身份正确）。"),
    ("NOT_APPLICABLE_PRE_LISTING", "报告期结束日早于该公司上市日，不存在上市公司定期报告；必须有可核上市日支撑。"),
    ("SUBSTITUTED_BY_PROSPECTUS", "报告期落在上市前，改用招股书对应期间章节；document_type 必须记为 PROSPECTUS，不得冒充年报。"),
    ("NOT_DISCLOSED_BY_ISSUER", "已到法定披露期且公司应披露但查无该期报告；须附检索记录，不能凭一次失败断言。"),
    ("AFTER_CUTOFF_DISCLOSED", "披露日晚于 knowledge_as_of，本轮不得作为证据使用，仅登记为后续增量候选。"),
    ("NOT_YET_DISCLOSED", "在 knowledge_as_of 时点法定披露期尚未届满（如 2026Q3 于 2026-10-25）。"),
    ("SOURCE_FAILED", "已实际请求并有限重试后源站失败/超时/格式损坏；须有请求记录与重试次数。"),
    ("ACCESS_BLOCKED", "权限、付费墙或登录限制导致无法取得；不是公司未披露。"),
    ("NOT_TRIED", "尚未尝试。禁止计入完成，禁止作为人工补件理由。"),
]

STATUS_MAPPING = {
    "PENDING_EXISTING_ARCHIVE_MATCH": "NOT_TRIED",
    "NOT_REQUESTED": "NOT_TRIED",
    "NOT_STARTED": "NOT_TRIED",
    "DO_NOT_REQUEST_BEFORE_AUTOMATIC_PASS_COMPLETE": "NOT_TRIED",
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_csv(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def git_head() -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout.strip()
    except Exception:
        return None


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    base_commit = git_head()

    master = read_csv(MASTER)
    queue = read_csv(QUEUE)
    registry = read_csv(REGISTRY)
    batch_index = read_csv(BATCH_INDEX)
    project_state = json.loads(PROJECT_STATE.read_text(encoding="utf-8-sig"))

    ids = [r["security_id"] for r in master]
    codes = [r["stock_code"] for r in master]
    names = [r["stock_name"] for r in master]
    exchanges = [r["exchange"] for r in master]

    # ---------- 规范序列化与指纹 ----------
    ordered = sorted(master, key=lambda r: r["security_id"])
    canonical_rows = [
        "\t".join([r["security_id"], r["stock_code"], r["stock_name"], r["exchange"]]) for r in ordered
    ]
    canonical_text = "\n".join(canonical_rows) + "\n"
    canonical_sha256 = sha256_text(canonical_text)
    canonical_ids_sha256 = sha256_text("\n".join(sorted(ids)) + "\n")

    exchange_counts = Counter(exchanges)
    prelisting_counts = Counter(r["prelisting_flag"] for r in master)
    data_status_counts = Counter(r["data_status"] for r in master)
    listing_date_counts = Counter(r["listing_date"] for r in master)
    leading_zero = [c for c in codes if c.startswith("0")]

    # 队列批次与主表互斥覆盖校验
    queue_ids = [r["security_id"] for r in queue]
    batch_counts = Counter(r["batch_id"] for r in queue)
    batch_expected = {r["batch_id"]: int(r["company_count"]) for r in batch_index}

    checks = [
        {"check": "master_row_count_1054", "pass": len(master) == 1054, "actual": len(master)},
        {"check": "security_id_unique", "pass": len(set(ids)) == 1054, "actual": len(set(ids))},
        {"check": "stock_code_unique", "pass": len(set(codes)) == 1054, "actual": len(set(codes))},
        {
            "check": "stock_code_all_six_digit_text",
            "pass": all(len(c) == 6 and c.isdigit() for c in codes),
            "actual": f"{sum(1 for c in codes if len(c) == 6 and c.isdigit())}/1054",
        },
        {
            "check": "security_id_equals_exchange_colon_code",
            "pass": all(r["security_id"] == f"{r['exchange']}:{r['stock_code']}" for r in master),
            "actual": "all match",
        },
        {"check": "no_empty_stock_name", "pass": all(n.strip() for n in names), "actual": sum(1 for n in names if not n.strip())},
        {"check": "queue_covers_master_once", "pass": sorted(queue_ids) == sorted(ids), "actual": f"queue={len(queue_ids)} unique={len(set(queue_ids))}"},
        {
            "check": "batch_partition_matches_index",
            "pass": dict(batch_counts) == batch_expected and sum(batch_counts.values()) == 1054,
            "actual": dict(sorted(batch_counts.items())),
        },
        {
            "check": "no_company_dropped_by_legacy_partition",
            "pass": len(master) == 1054,
            "actual": "旧53采用/7待源/10样本/984未筛仅作路由线索，未剔除任何证券",
        },
    ]

    universe_fingerprint = {
        "fingerprint_version": 1,
        "plan_version": PLAN_VERSION,
        "issue_number": ISSUE_NUMBER,
        "issue_key": ISSUE_KEY,
        "generated_at_utc": generated_at,
        "base_commit": base_commit,
        "purpose": "冻结本轮候选池名单版本，供后续所有采集/筛选环节复算比对。",
        "source_file": {
            "path": "data/company_master.csv",
            "sha256": sha256_file(MASTER),
            "row_count": len(master),
        },
        "canonical_form": {
            "algorithm": "按 security_id 升序；每行按 security_id\\tstock_code\\tstock_name\\texchange 拼接；行间 \\n；末尾补一个 \\n；UTF-8 编码后取 SHA-256。",
            "canonical_sha256": canonical_sha256,
            "security_id_only_sha256": canonical_ids_sha256,
            "note": "哈希不含时间戳与任何状态字段，任何人重跑应得到同一值。",
        },
        "counts": {
            "total_securities": len(master),
            "unique_security_id": len(set(ids)),
            "unique_stock_code": len(set(codes)),
            "unique_stock_name": len(set(names)),
            "duplicate_stock_name_rows": sorted(n for n, c in Counter(names).items() if c > 1),
            "stock_code_leading_zero": len(leading_zero),
        },
        "distribution": {
            "exchange": dict(sorted(exchange_counts.items())),
            "prelisting_flag": dict(sorted(prelisting_counts.items())),
            "data_status": dict(sorted(data_status_counts.items())),
            "listing_date": dict(sorted(listing_date_counts.items())),
        },
        "cross_tabs": {
            "prelisting_vs_data_status": {
                f"{p}|{d}": c
                for (p, d), c in sorted(
                    Counter((r["prelisting_flag"], r["data_status"]) for r in master).items()
                )
            },
        },
        "batch_coverage": {
            "source": "data/intake_company_queue.csv",
            "batch_counts": dict(sorted(batch_counts.items())),
            "declared_in_index": dict(sorted(batch_expected.items())),
            "total": sum(batch_counts.values()),
            "mutually_exclusive": sorted(queue_ids) == sorted(ids) and len(set(queue_ids)) == 1054,
        },
        "existing_documents": {
            "source": "data/document_registry.csv",
            "rows": len(registry),
            "unique_document_id": len(set(r["document_id"] for r in registry)),
            "companies_with_any_document": len(set(r["security_id"] for r in registry)),
            "coverage_ratio": round(len(set(r["security_id"] for r in registry)) / len(master), 4),
            "archive_status": dict(sorted(Counter(r["archive_status"] for r in registry).items())),
            "note": "已有原文只覆盖少数公司，且多数仅 UPLOADED_UNVERIFIED；不构成资料轮完成。",
        },
        "checks": checks,
        "all_checks_pass": all(c["pass"] for c in checks),
        "exclusions": {
            "count": 0,
            "rule": "本轮不因旧53采用、概念标签、行业分组、财务缺失或上市前标记剔除任何证券。",
        },
        "known_input_gaps": [
            {
                "field": "listing_date",
                "status": "ALL_UNKNOWN",
                "affected_rows": listing_date_counts.get("UNKNOWN", 0),
                "impact": "无法逐家判定定期报告槽是否属于上市前不适用；在取得可核上市日前，槽位一律保持 NOT_TRIED，不得填 NOT_APPLICABLE。",
                "unblock_owner": "P02/P03 取得交易所上市日期后回填；P00 只冻结判定规则。",
            }
        ],
    }

    # ---------- 采集合同 ----------
    knowledge_as_of = project_state.get("knowledge_as_of")
    master_as_of = sorted(set(r["research_as_of"] for r in master))

    report_slots = [
        {
            "slot_id": sid,
            "report_type": rtype,
            "period_label": period,
            "period_start": start,
            "period_end": end,
            "statutory_deadline": deadline,
            "required_form": "FULL_PDF",
            "summary_acceptable": False,
            "core_slot": True,
            "deadline_before_cutoff": deadline < knowledge_as_of,
        }
        for sid, rtype, period, start, end, deadline in CORE_SLOTS
    ]

    quarterly_slots = [
        {
            "slot_id": sid,
            "report_type": "QUARTERLY_REPORT",
            "period_label": period,
            "period_start": start,
            "period_end": end,
            "statutory_deadline": deadline,
            "required_form": "STRUCTURED_FINANCIAL_PLUS_PDF_IF_AUTOMATIC",
            "core_slot": False,
            "deadline_before_cutoff": deadline < knowledge_as_of,
            "as_of_cutoff_status": "NOT_YET_DISCLOSED_PARTIAL" if deadline >= knowledge_as_of else "APPLICABLE",
        }
        for sid, period, start, end, deadline in QUARTERLY_SLOTS
    ]

    collection_scope = {
        "scope_version": 1,
        "plan_version": PLAN_VERSION,
        "issue_number": ISSUE_NUMBER,
        "issue_key": ISSUE_KEY,
        "frozen_at_utc": generated_at,
        "base_commit": base_commit,
        "executor": EXECUTOR,
        "scope_statement": "只冻结本轮采集合同：名单、截止日、报告槽、字段、状态口径与容量规则。不下载全池、不筛公司、不做业务判断、不估值。",
        "time_axis": {
            "knowledge_as_of": knowledge_as_of,
            "knowledge_as_of_semantics": "研究截止日。披露日晚于此日的任何文件不得作为本轮证据；可作为后续增量候选登记。",
            "knowledge_as_of_source": "PROJECT_STATE.json（issue #11 指定以最新 PROJECT_STATE 为准）",
            "collection_date": COLLECTION_DATE,
            "collection_date_semantics": "实际取件日，仅用于记录取件时间与源站快照，不改变研究截止日。",
            "date_conflicts": [
                {
                    "conflict": "knowledge_as_of 与 company_master.research_as_of 不一致",
                    "values": {"PROJECT_STATE.knowledge_as_of": knowledge_as_of, "company_master.research_as_of": master_as_of},
                    "resolution": "冻结 knowledge_as_of 为研究截止日；research_as_of 为行级研究时点标记，早于截止日属正常，保留原值不回填、不改写。",
                    "status": "RESOLVED_BY_DEFINITION",
                },
                {
                    "conflict": "tools/validate_plan.py 与 packages/*/TASK.md 仍写死 2026-10-24",
                    "values": {"validator_expected": "2026-10-24", "frozen": knowledge_as_of},
                    "resolution": "属旧体系遗留断言，不在 P00 修改（避免改动既有校验与他卡输入）；登记为后续待办，由 P01 或专门卡把校验器改为读取本文件冻结值。",
                    "status": "LOGGED_NOT_CHANGED",
                },
            ],
            "cutoff_rules": [
                "文件披露日 ≤ knowledge_as_of 才可进入本轮证据链。",
                "披露日晚于截止日的文件记为 AFTER_CUTOFF_DISCLOSED，只做增量候选，不参与本轮筛选。",
                "季度报告在截止日时点尚未到法定披露期的，记 NOT_YET_DISCLOSED，不计缺口、不派人工补件。",
            ],
        },
        "universe": {
            "count": len(master),
            "fingerprint_file": "runs/issues/P00/universe_fingerprint.json",
            "canonical_sha256": canonical_sha256,
            "source": "data/company_master.csv",
            "exclusion_rule": "零剔除。旧53采用/7待源/10样本/984未筛只是路由线索，不作预筛淘汰条件。",
        },
        "report_slots": report_slots,
        "quarterly_slots": quarterly_slots,
        "supplementary_materials": [
            {
                "id": "announcement_ir_index",
                "scope": "研究截止日前两年（2024-10-26 至 2026-10-25）的公告与正式 IR 目录，含分页与公司代码",
                "required_form": "INDEX_THEN_SELECTIVE_ORIGINALS",
                "coverage": "全候选池目录先行覆盖；关键词命中的原件再批量归档",
                "not_evidence_for": "关键词只用于取件排序，不能当作机器人业务证据",
            },
            {
                "id": "keyword_originals",
                "scope": "机器人/人形/减速器/执行器/传感器/送样/量产/谐波/丝杠/灵巧手/伺服/关节模组等命中原件",
                "required_form": "ORIGINAL_PDF",
                "coverage": "仅命中项，不做全量抓取",
            },
            {
                "id": "financial_corrections",
                "scope": "与上述报告及机器人业务有关的更正、重述、并购、主体变更材料",
                "required_form": "ORIGINAL_PDF_PLUS_LINK_TO_SUPERSEDED",
                "coverage": "保留原始版与更正版并建立关联，不覆盖追溯原件",
            },
        ],
        "financial_field_requirements": {
            "note": "字段口径的最终冻结在 P04；此处只列本轮必须覆盖的字段清单，避免采集时漏抓。",
            "period_fields": [
                "营业收入（本期/上年同期）",
                "营业成本或毛利（本期/上年同期）",
                "归属于母公司股东的扣除非经常性损益的净利润",
                "经营活动产生的现金流量净额",
                "应收账款（含合同资产，分列）",
                "存货",
            ],
            "dimension_fields": ["公司主体（含历史名称/代码变更）", "报告期", "单季度 vs 年初至今累计", "单位", "实际披露日", "数据来源与原文定位"],
            "prohibitions": [
                "单季度与累计不得混用。",
                "归母净利与扣非净利不得互相替代。",
                "缺失不得填 0；未披露与取件失败必须分开。",
                "公司总收入不得冒充机器人业务收入。",
            ],
        },
        "status_taxonomy": [{"code": code, "definition": definition} for code, definition in STATUS_VOCAB],
        "legacy_value_mapping": STATUS_MAPPING,
        "not_applicable_decision_table": {
            "input": "listing_date（当前 1054/1054 为 UNKNOWN）",
            "rules": [
                {"condition": "listing_date == UNKNOWN", "slot_status": "NOT_TRIED", "reason": "无法判定，保持未知；禁止默认按不适用处理。"},
                {"condition": "listing_date > period_end", "slot_status": "NOT_APPLICABLE_PRE_LISTING", "reason": "报告期结束时尚未上市，不存在上市公司定期报告。"},
                {"condition": "listing_date <= period_end", "slot_status": "APPLICABLE", "reason": "报告期覆盖上市后期间，应取得该期定期报告。"},
                {"condition": "北交所公司上市前曾在股转系统挂牌", "slot_status": "APPLICABLE_WITH_DIFFERENT_PLATFORM", "reason": "挂牌期间年报存在但披露平台与主体口径不同，需记录平台，不得因平台不同判不适用。"},
                {"condition": "公司更名/代码变更/借壳", "slot_status": "APPLICABLE_WITH_ENTITY_MAPPING", "reason": "需先建立历史主体映射，映射表由 P01/P02 产出；P00 只登记该需求。"},
            ],
            "prospectus_substitution": {
                "allowed_when": "slot_status == NOT_APPLICABLE_PRE_LISTING",
                "resulting_status": "SUBSTITUTED_BY_PROSPECTUS",
                "constraint": "document_type 必须记为 PROSPECTUS，不得计入年报槽完成数。",
                "affected_candidates": prelisting_counts.get("PRE_LISTING_PROSPECTUS_DATA", 0)
                + prelisting_counts.get("PRE_LISTING_BACKFILL_CONFIRMED", 0),
            },
        },
        "capacity_rule": {
            "core_slot_upper_bound": len(master) * len(CORE_SLOTS),
            "core_slot_upper_bound_formula": "1054 × 6 = 6324",
            "meaning": "只是核心报告槽的数学上界，不是应有文件数；须扣除上市前不适用、未披露、修订合并等情况。",
            "estimation_method": "总容量 = Σ(各槽实际尝试数 × 该槽单位文件字节中位数)；单位大小以 P07 十家校准实测为准。",
            "pre_calibration_state": "UNMEASURED",
            "pre_calibration_placeholder": "在 P07 取得实测中位数前，不对外给出总 GB 数，避免把经验带宽当成事实。",
            "extra_materials": "季度结构化数据、公告目录、关键词原件另计，不并入 6324。",
        },
        "out_of_scope": [
            "不下载全池（本卡不发起任何批量请求）",
            "不做指标计算、不筛公司、不调阈值",
            "不做业务判断、不追合同履约、不估值",
            "不修改既有研究采用状态与他人结果",
            "不修改历史输入表（company_master 等）",
        ],
        "stop_conditions": [
            "名单或日期口径出现未解决冲突时，不得启动全池请求。",
            "发现候选池不是 1054 或存在重复键时，立即停止并回退到名单核对。",
        ],
    }

    # ---------- 覆盖与验收规则 ----------
    coverage_rules = {
        "rules_version": 1,
        "plan_version": PLAN_VERSION,
        "issue_number": ISSUE_NUMBER,
        "issue_key": ISSUE_KEY,
        "frozen_at_utc": generated_at,
        "principle": "完成不等于放行；未尝试不等于缺件；缺数据不等于无业务；不得为凑目标公司数改规则。",
        "slot_completion_definition": {
            "COLLECTED_IDENTITY_VERIFIED": "计入已取得",
            "COLLECTED_PENDING_IDENTITY": "不计入已取得，计入待核",
            "SUBSTITUTED_BY_PROSPECTUS": "计入已覆盖（替代来源），不计入年报槽完成数",
            "NOT_APPLICABLE_PRE_LISTING": "计入不适用，须有可核上市日",
            "NOT_YET_DISCLOSED": "计入未到期，不计缺口",
            "AFTER_CUTOFF_DISCLOSED": "计入截止日后，不计本轮覆盖",
            "NOT_DISCLOSED_BY_ISSUER": "计入真实缺口，须附检索证据",
            "SOURCE_FAILED": "计入失败，进入自动重试队列",
            "ACCESS_BLOCKED": "计入访问受阻，不归因于公司",
            "NOT_TRIED": "不计入任何完成口径，禁止出现在完成统计里",
        },
        "round_completion_definition": {
            "statement": "当且仅当全池每个槽位都处于上述非 NOT_TRIED 的任一状态，且每条状态都有可追溯记录（请求日志/原文ID/检索证据）时，资料轮才算完成。",
            "allowed_gaps": "允许存在有明确限制的缺口：NOT_APPLICABLE_PRE_LISTING、NOT_YET_DISCLOSED、NOT_DISCLOSED_BY_ISSUER、SOURCE_FAILED、ACCESS_BLOCKED 均属合法终态。",
            "forbidden": "NOT_TRIED 不得作为终态出现在 A00/A04 的完成统计中。",
        },
        "forbidden_patterns": [
            "把 NOT_TRIED 写成已尝试或已完成",
            "把取件失败当成公司未披露或无业务",
            "缺失财务字段填 0",
            "用摘要代替全文并计入全文槽",
            "用关键词命中代替业务证据",
            "为达到某个公司数量调整筛选阈值",
            "把 UPLOADED 当作业务证据已验收",
        ],
        "acceptance_checks": [
            {"id": "AC01", "check": "全池证券数 == 冻结指纹中的 total_securities", "expected": "1054"},
            {"id": "AC02", "check": "每批次实际处理数 == intake_batch_index 声明数", "expected": "10×100 + 54"},
            {"id": "AC03", "check": "11 批并集 == 冻结名单，且无重复", "expected": "集合相等"},
            {"id": "AC04", "check": "每个 (security_id, slot_id) 都有且仅有一个终态", "expected": "无空值、无冲突"},
            {"id": "AC05", "check": "NOT_TRIED 数量 == 0（A04 时点）", "expected": "0"},
            {"id": "AC06", "check": "NOT_APPLICABLE_PRE_LISTING 每行都有可核上市日", "expected": "100% 有据"},
            {"id": "AC07", "check": "COLLECTED_IDENTITY_VERIFIED 每行都有 document_id 与官方URL", "expected": "100% 可追溯"},
            {"id": "AC08", "check": "SOURCE_FAILED 每行都有请求记录与重试次数", "expected": "100%"},
            {"id": "AC09", "check": "人工补缺清单只包含自动尝试且失败/确无的项", "expected": "不含 NOT_TRIED"},
            {"id": "AC10", "check": "披露日晚于 knowledge_as_of 的文件未进入本轮证据", "expected": "0 违规"},
        ],
        "gap_classification": [
            {"code": "GAP_NOT_YET_DISCLOSED", "action": "等待，不派补件"},
            {"code": "GAP_NOT_APPLICABLE", "action": "关闭，须附上市日"},
            {"code": "GAP_PARTIALLY_OBTAINED", "action": "补缺剩余部分"},
            {"code": "GAP_SOURCE_FAILED", "action": "自动重试/换官方源"},
            {"code": "GAP_ACCESS_BLOCKED", "action": "记录权限问题，不催用户"},
            {"code": "GAP_FIELD_NOT_DISCLOSED", "action": "保留未知，不填 0"},
            {"code": "GAP_NOT_TRIED", "action": "禁止派单，先跑自动采集"},
        ],
        "human_request_policy": {
            "trigger": "仅在自动整轮 + 有限重试 + 备用官方源都试过之后，由 A02 一次性汇总。",
            "grouping": "按网站/软件、报告期、可共同下载的批次分组。",
            "template": "templates/整轮采集人工补缺.csv",
            "must_include": ["缺哪些文件/字段", "尝试过什么", "一次怎样导出", "放到哪个本地/Drive 目录"],
            "forbidden": ["逐家发补件请求", "把未尝试项列成缺件", "把全局源故障转成 1054 条手补"],
        },
        "review_policy": {
            "self_check_allowed_for": "技术/格式/可复算类检查",
            "independent_review_required_for": "业务结论采用、证据原句与物理页核验",
            "labeling": "同一 AI 执行并自检时须显式标 SELF_CHECK，不得称为独立验收",
            "closing_issue": "关闭 issue 不替代验收记录；以 runs/issues/<key>/review.json 为准",
        },
        "deliverable_requirements": {
            "per_issue": ["专用结果文件", "manifest.json", "handoff.md", "review.json"],
            "manifest_fields": ["files", "sha256", "generated_at", "inputs"],
        },
        "capacity_acceptance": {
            "upper_bound": 6324,
            "rule": "6324 只用于容量上界与进度分母，不得当作应有文件数写入完成率分母之外的地方。",
        },
    }

    (OUT / "universe_fingerprint.json").write_text(
        json.dumps(universe_fingerprint, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (OUT / "collection_scope.json").write_text(
        json.dumps(collection_scope, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (OUT / "coverage_acceptance_rules.json").write_text(
        json.dumps(coverage_rules, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(json.dumps({
        "outputs": [
            "runs/issues/P00/universe_fingerprint.json",
            "runs/issues/P00/collection_scope.json",
            "runs/issues/P00/coverage_acceptance_rules.json",
        ],
        "canonical_sha256": canonical_sha256,
        "all_checks_pass": universe_fingerprint["all_checks_pass"],
        "knowledge_as_of": knowledge_as_of,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
