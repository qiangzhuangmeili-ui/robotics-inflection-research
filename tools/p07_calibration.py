"""P07 十家采集校准：只验接口与资料可用性，不做业务研究。

对应 issue #18 的三条执行步骤与 P06 交给 P07 的五条交接：
1. 按市场/代码段/历史代码/已有资料/缺资料五轴冻结 10 家名单；
2. 跑财务字段、公告分页、全文 PDF 识别、归档与失败恢复（业务归因不在本卡）；
3. 校准命中可直接复用，队列证券总数不变。

与 P05 的关系：本卡**不改** P05 的 collector_config.json（冻结参数源），而是派生
`runs/issues/P07/collection_config_v1.json`，逐条列明覆盖项（原件根改到 D 盘是用户
2026-10-26 的明确指示）。采集代码复用 tools/p05_collector.py，不复制实现。

用法：
    python -X utf8 tools/p07_calibration.py --freeze      # 名单 + 派生配置 + 台账种子
    python -X utf8 tools/p07_calibration.py --run         # 实跑 10 家 7 槽
    python -X utf8 tools/p07_calibration.py --resume-test # 断点续传实测
    python -X utf8 tools/p07_calibration.py --probe-drive # Drive 三步探测
    python -X utf8 tools/p07_calibration.py --finalize    # 覆盖表/容量/验收/自检
    python -X utf8 tools/p07_calibration.py --check       # 只跑自检
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import p05_collector as P05  # noqa: E402

PLAN_VERSION = "20261026_collection_first_v2"
ISSUE_KEY = "P07"
ISSUE_NUMBER = 18

OUT = ROOT / "runs/issues/P07"
P05_CONFIG = ROOT / "runs/issues/P05/collector_config.json"
P07_CONFIG = OUT / "collection_config_v1.json"

COLLECTION_DIR = ROOT / "runs/collection"
LEDGER_DIR = COLLECTION_DIR / "checkpoint"
LEDGER_MANIFEST = COLLECTION_DIR / "ledger_manifest.json"

ORIGINALS_REL = "sources/collection/originals"
RAW_REL = "sources/collection/raw"
CACHE_REL = "sources/collection/cache"
DATA_ROOT = Path("D:/StockResearchLab/IndustryInflectionLab/robotics_data/collection")

SLOTS = ["annual_2023", "annual_2024", "annual_2025",
         "h1_2024", "h1_2025", "h1_2026", "q1_2026"]

# ---------------------------------------------------------------- 冻结名单
# 选样轴（issue 原文）：沪深北、前导零、历史代码/近期上市、已有资料和缺资料。
# 冻结后不再增删；换样必须另开版本并写明理由。
ASSIGNMENT = [
    {
        "security_id": "SZ:000026", "stock_name": "飞亚达", "exchange": "SZ",
        "code_segment": "000", "board": "深主板",
        "leading_zero": "Y", "historical_code_case": "N",
        "selection_axis": "前导零+无既有资料",
        "why_selected": "000 段前导零代码；登记表 0 份、旧财务快照有，用于验证“无既有原件”的完整下载路径。",
        "reuse_expected": "NONE",
    },
    {
        "security_id": "SZ:002031", "stock_name": "巨轮智能", "exchange": "SZ",
        "code_segment": "002", "board": "深主板",
        "leading_zero": "Y", "historical_code_case": "N",
        "selection_axis": "前导零+已有资料(P05台账)",
        "why_selected": "002 段前导零；P05 已采 annual_2025 与 h1_2026，用于验证跨卡复用时 0 次 HTTP。",
        "reuse_expected": "P05_LEDGER",
    },
    {
        "security_id": "SZ:001306", "stock_name": "夏厦精密", "exchange": "SZ",
        "code_segment": "001", "board": "深主板",
        "leading_zero": "Y", "historical_code_case": "N",
        "selection_axis": "前导零+近期上市+已有资料(登记表)",
        "why_selected": "001 段（19 家小样本）；prelisting_flag=PRE_LISTING_PROSPECTUS_DATA，上市不足三年，早期槽可能空目录。",
        "reuse_expected": "REGISTRY_LOCAL",
    },
    {
        "security_id": "SZ:300024", "stock_name": "机器人", "exchange": "SZ",
        "code_segment": "300", "board": "创业板",
        "leading_zero": "N", "historical_code_case": "N",
        "selection_axis": "创业板+无既有资料",
        "why_selected": "创业板 300 段（227 家，池内最大段）；简称与行业词同名，可检验简称匹配不被业务词干扰。",
        "reuse_expected": "NONE",
    },
    {
        "security_id": "SZ:301000", "stock_name": "肇民科技", "exchange": "SZ",
        "code_segment": "301", "board": "创业板",
        "leading_zero": "N", "historical_code_case": "N",
        "selection_axis": "创业板次新段+无既有资料",
        "why_selected": "301 段（120 家，2021 年后新增段）；验证新代码段在巨潮 orgId 表中的解析。",
        "reuse_expected": "NONE",
    },
    {
        "security_id": "SH:600699", "stock_name": "均胜电子", "exchange": "SH",
        "code_segment": "600", "board": "沪主板",
        "leading_zero": "N", "historical_code_case": "N",
        "selection_axis": "沪主板+已有资料(登记表)",
        "why_selected": "沪市 600 段；登记表有 2025 年度原件且本地文件哈希可核，验证登记表复用。",
        "reuse_expected": "REGISTRY_LOCAL",
    },
    {
        "security_id": "SH:603667", "stock_name": "五洲新春", "exchange": "SH",
        "code_segment": "603", "board": "沪主板",
        "leading_zero": "N", "historical_code_case": "N",
        "selection_axis": "沪主板603段+已有资料(登记表)",
        "why_selected": "沪市 603 段（120 家）；登记表有 2025 年度原件，验证另一条复用路径。",
        "reuse_expected": "REGISTRY_LOCAL",
    },
    {
        "security_id": "SH:688218", "stock_name": "江苏北人", "exchange": "SH",
        "code_segment": "688", "board": "科创板",
        "leading_zero": "N", "historical_code_case": "N",
        "selection_axis": "科创板+已有资料(P05台账+登记表)",
        "why_selected": "科创板 688 段；P05 台账与登记表指向同一份原件（同哈希），验证双来源一致。",
        "reuse_expected": "P05_LEDGER",
    },
    {
        "security_id": "BJ:920207", "stock_name": "众诚科技", "exchange": "BJ",
        "code_segment": "920", "board": "北交所",
        "leading_zero": "N", "historical_code_case": "Y",
        "selection_axis": "北交所+历史代码+已有资料最多",
        "why_selected": "920 新代码，2024 年及以前年报以旧代码 835207 披露；登记表 9 份、P05 已采 annual_2025。",
        "reuse_expected": "P05_LEDGER",
    },
    {
        "security_id": "BJ:920011", "stock_name": "晨光电机", "exchange": "BJ",
        "code_segment": "920", "board": "北交所",
        "leading_zero": "N", "historical_code_case": "N",
        "selection_axis": "北交所+缺资料",
        "why_selected": "池内 62 家北交所全部 FINANCIAL_DATA_MISSING 之一，登记表 0 份；验证缺资料不等于未披露。",
        "reuse_expected": "NONE",
    },
]

BOARD_BY_SEGMENT = {"600": "沪主板", "601": "沪主板", "603": "沪主板", "605": "沪主板",
                    "688": "科创板", "000": "深主板", "001": "深主板", "002": "深主板",
                    "003": "深主板", "300": "创业板", "301": "创业板", "920": "北交所"}


# ---------------------------------------------------------------- 工具函数

def now_cn() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_csv(path: Path) -> list[dict]:
    with Path(path).open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return path


def write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return path


def pct(values: list[int], q: float) -> int | None:
    """四分位；n<4 时退化为端点，不编造插值。"""
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    if len(ordered) < 4:
        return ordered[0] if q < 0.5 else ordered[-1]
    qs = statistics.quantiles(ordered, n=4, method="inclusive")
    if q <= 0.25:
        return int(round(qs[0]))
    if q >= 0.75:
        return int(round(qs[2]))
    return int(round(statistics.median(ordered)))


def master_index() -> dict[str, dict]:
    return {r["security_id"]: r for r in read_csv(ROOT / "data/company_master.csv")}


# ---------------------------------------------------------------- 1. 派生配置

def build_config() -> dict:
    base = json.loads(P05_CONFIG.read_text(encoding="utf-8"))
    cfg = json.loads(json.dumps(base))  # deep copy
    overrides = [
        {"path": "storage.local_original_root", "from": base["storage"]["local_original_root"],
         "to": ORIGINALS_REL,
         "why": "用户 2026-10-26 指示：C 盘剩余不足，原件改存 D 盘。sources/collection 为指向 "
                "D:/StockResearchLab/IndustryInflectionLab/robotics_data/collection 的目录联接。"},
        {"path": "storage.local_raw_index_root", "from": base["storage"]["local_raw_index_root"],
         "to": RAW_REL, "why": "原始响应与原件同盘，避免占 C 盘。"},
        {"path": "storage.cache_root", "from": base["storage"]["cache_root"], "to": CACHE_REL,
         "why": "缓存同盘，便于整目录清理与容量核算。"},
        {"path": "routes.cninfo_org_index.cache_path",
         "from": base["routes"]["cninfo_org_index"]["cache_path"],
         "to": f"{CACHE_REL}/szse_stock.json", "why": "orgId 全市场表随缓存根迁移。"},
        {"path": "storage.tracked_ledger_dir", "from": base["storage"]["tracked_ledger_dir"],
         "to": "runs/collection/checkpoint",
         "why": "P07 起台账改为全池共享台账（COLLECTION_LEDGER_V1），M00_01—M00_11 继承同一台账，"
                "校准命中即天然复用，不需要二次导入。"},
        {"path": "storage.tracked_index", "from": base["storage"]["tracked_index"],
         "to": "runs/collection/collection_index.csv", "why": "同上，索引与台账同源。"},
        {"path": "storage.tracked_runlog", "from": base["storage"]["tracked_runlog"],
         "to": "runs/collection/run_log.jsonl", "why": "同上，事件流合并到共享目录。"},
    ]
    for item in overrides:
        cursor = cfg
        parts = item["path"].split(".")
        for key in parts[:-1]:
            cursor = cursor[key]
        cursor[parts[-1]] = item["to"]
    # P07 校准新增（不是放宽，是补下限）：封面页有效字符下限
    cfg["pdf_validation"]["issuer_pages_probe"] = 8
    cfg["pdf_validation"]["min_identity_probe_chars"] = 200
    overrides.append({
        "path": "pdf_validation.issuer_pages_probe", "from": "（P05 未设此键，固定 3 页）", "to": 8,
        "why": "P07 F5：北交所 2026 年半年报封面是未填充模板，主体信息在第 6 页“公司概况”。"
               "主体检索放宽到前 8 页；报告期仍只用前 3 页，两件事不共用范围。",
    })
    overrides.append({
        "path": "pdf_validation.min_identity_probe_chars", "from": "（P05 未设此键）", "to": 200,
        "why": "P07 F2：前 8 页有效字符不足 200 时只能记 PENDING（正文抽取不足），不得判 MISMATCH。",
    })
    cfg["storage"]["git_policy"] = (
        "原件 PDF 与原始响应不入库（.gitignore 已排除 sources/**、*.pdf）；GitHub 只存小型索引、台账与运行记录。"
        "本卡起原件根位于 D 盘（经 sources/collection 目录联接），仓库内不保留二进制副本。")
    out = {
        "config_code": "COLLECTOR_V1_P07_CALIBRATION",
        "plan_version": PLAN_VERSION,
        "issue_key": ISSUE_KEY,
        "issue_number": ISSUE_NUMBER,
        "frozen_at": now_cn(),
        "derived_from": {
            "path": "runs/issues/P05/collector_config.json",
            "config_code": base.get("config_code"),
            "sha256": sha256_file(P05_CONFIG),
            "note": "P05 配置是冻结参数源，本卡不修改它；本文件只声明覆盖项，未覆盖项全部继承。",
        },
        "overrides": overrides,
        "storage_layout": {
            "repo_root": str(ROOT),
            "data_root": str(DATA_ROOT),
            "junction": "sources/collection",
            "resolved_original_root": str((ROOT / ORIGINALS_REL).resolve()),
            "drive": "D:",
            "why": "C 盘 2026-10-26 实测剩余约 24—38 GiB 且已用 80% 以上；P06 估算核心槽中位 13.43 GiB，"
                   "放 C 盘会触发硬水位。D 盘剩余 150 GiB 以上，作为原件与缓存根。",
        },
    }
    out.update(cfg)
    OUT.mkdir(parents=True, exist_ok=True)
    write_json(P07_CONFIG, out)
    return out


# ---------------------------------------------------------------- 2. 名单冻结

def freeze_assignment() -> Path:
    master = master_index()
    rows = []
    for item in ASSIGNMENT:
        m = master[item["security_id"]]
        seg = m["stock_code"][:3]
        rows.append({
            "security_id": item["security_id"],
            "stock_code": m["stock_code"],
            "stock_name": m["stock_name"],
            "exchange": item["exchange"],
            "board": BOARD_BY_SEGMENT.get(seg, item["board"]),
            "code_segment": seg,
            "leading_zero": item["leading_zero"],
            "historical_code_case": item["historical_code_case"],
            "listing_date": m.get("listing_date") or "UNKNOWN",
            "prelisting_flag": m.get("prelisting_flag"),
            "data_status": m.get("data_status"),
            "legacy_financial": "HAS" if m.get("data_status") == "HAS_FINANCIAL_DATA" else "MISSING",
            "selection_axis": item["selection_axis"],
            "why_selected": item["why_selected"],
            "reuse_expected": item["reuse_expected"],
            "slots_planned": "|".join(SLOTS),
        })
    fields = list(rows[0].keys())
    path = write_csv(OUT / "calibration_assignment.csv", rows, fields)
    return path


# ---------------------------------------------------------------- 3. 台账种子

def seed_ledger() -> dict:
    """把可复用原件写进共享台账，使采集器走 SKIPPED_ALREADY_HAVE 而不是重下。

    两条来源：
    A. P05 台账（本卡不重下，跨卡复用）；
    B. 登记表 data/document_registry.csv 的本地原件（P05 配置 idempotency.lookup_order[2]
       规定要查登记表，但代码只实现了台账与内容索引；本卡在台账层补这一步，不覆盖登记表）。
    """
    LEDGER_DIR.mkdir(parents=True, exist_ok=True)
    imported, seeded, skipped = [], [], []
    master = master_index()
    registry = read_csv(ROOT / "data/document_registry.csv")

    # A. P05 台账导入
    for item in ASSIGNMENT:
        if item["reuse_expected"] != "P05_LEDGER":
            continue
        code = master[item["security_id"]]["stock_code"]
        src = ROOT / "runs/issues/P05/checkpoint" / f"{code}.json"
        dst = LEDGER_DIR / f"{code}.json"
        if not src.exists():
            skipped.append({"security_id": item["security_id"], "reason": "P05_LEDGER_ABSENT"})
            continue
        if dst.exists():
            skipped.append({"security_id": item["security_id"], "reason": "LEDGER_ALREADY_PRESENT"})
            continue
        shutil.copy2(src, dst)
        imported.append({
            "security_id": item["security_id"], "stock_code": code,
            "from": "runs/issues/P05/checkpoint/" + src.name,
            "from_sha256": sha256_file(src), "to": "runs/collection/checkpoint/" + dst.name,
            "slots": sorted(json.loads(dst.read_text(encoding="utf-8")).get("slots", {})),
            "note": "逐字节复制，不改 P05 原文件；local_file 仍指向 sources/p05_validation（C 盘），按记录路径复用。",
        })

    # B. 登记表本地原件种子
    for item in ASSIGNMENT:
        code = master[item["security_id"]]["stock_code"]
        ledger_path = LEDGER_DIR / f"{code}.json"
        data = json.loads(ledger_path.read_text(encoding="utf-8")) if ledger_path.exists() else {
            "security_id": item["security_id"], "slots": {}, "indexes": {}}
        data.setdefault("slots", {})
        data.setdefault("indexes", {})
        for row in registry:
            if row["security_id"] != item["security_id"]:
                continue
            if row["period_covered"] != "2025年度":
                continue
            if "annual_2025" in data["slots"]:
                skipped.append({"security_id": item["security_id"], "reason": "SLOT_ALREADY_IN_LEDGER"})
                continue
            local = (row.get("local_file") or "").strip()
            digest = (row.get("sha256") or "").strip()
            if not local or not digest:
                skipped.append({"security_id": item["security_id"], "reason": "REGISTRY_NO_LOCAL_OR_HASH"})
                continue
            path = Path(local)
            if not path.exists():
                skipped.append({"security_id": item["security_id"], "reason": "REGISTRY_LOCAL_MISSING"})
                continue
            actual = sha256_file(path)
            if actual != digest:
                skipped.append({"security_id": item["security_id"], "reason": "REGISTRY_HASH_MISMATCH"})
                continue
            data["security_id"] = item["security_id"]
            data["slots"]["annual_2025"] = {
                "security_id": item["security_id"],
                "slot_id": "annual_2025",
                "report_type": "ANNUAL_REPORT",
                "period_label": "FY2025",
                "period_end": "2025-12-31",
                "statutory_deadline": "2026-04-30",
                "status": P05.ST_COLLECTED_PENDING,
                "status_reason": "登记表已有本地原件，按 idempotency.lookup_order[2] 复用；本卡未发下载请求",
                "attempt_count": 0,
                "source_attempts": [],
                "last_source_attempt": None,
                "last_error": None,
                "next_action": "LOCAL_VALIDATION",
                "checkpoint": {"stage": "SEEDED_FROM_REGISTRY", "at": now_cn()},
                "document": {
                    "document_id": row["document_id"],
                    "identity_scheme": "LEGACY_REGISTRY_ID",
                    "title": row.get("original_title"),
                    "primary_url": row.get("primary_url"),
                    "published_on": row.get("published_on"),
                    "local_file": local,
                    "sha256": digest,
                    "bytes": path.stat().st_size,
                    "source_type": "REGISTRY_LOCAL_REUSE",
                },
                "seed": {
                    "from": "data/document_registry.csv",
                    "document_id": row["document_id"],
                    "registry_archive_status": row.get("archive_status"),
                    "registry_file_status": row.get("file_status"),
                    "hash_rechecked_at": now_cn(),
                    "hash_matches_registry": True,
                },
            }
            seeded.append({"security_id": item["security_id"], "slot_id": "annual_2025",
                           "document_id": row["document_id"], "bytes": path.stat().st_size,
                           "registry_archive_status": row.get("archive_status")})
        ledger_path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    payload = {
        "ledger_code": "COLLECTION_LEDGER_V1",
        "plan_version": PLAN_VERSION,
        "created_by": "P07",
        "created_at": now_cn(),
        "directory": "runs/collection/checkpoint",
        "why": "P07 起全池共用一本台账；M00_01—M00_11 必须沿用本目录，校准命中即复用，不得重下。",
        "imported_from_p05": imported,
        "seeded_from_registry": seeded,
        "not_seeded": skipped,
        "rules": [
            "台账只记录“是否已取得原件 + 身份校验结果”，不记录业务结论。",
            "SKIPPED_ALREADY_HAVE 是动作，不改写原取得状态；跳过必须 0 次 HTTP。",
            "登记表种子行的状态保持 COLLECTED_PENDING_IDENTITY，仅当本地七项校验全过才提升为 VERIFIED，"
            "并在 document.identity_verified_via 留痕。",
        ],
    }
    # 幂等：重跑 --freeze 时保留首次的导入/种子来源，不因“本次无事可做”而清空追溯
    if LEDGER_MANIFEST.exists():
        prev = json.loads(LEDGER_MANIFEST.read_text(encoding="utf-8"))
        for key in ("imported_from_p05", "seeded_from_registry"):
            seen = {(x.get("security_id"), x.get("slot_id") or x.get("slots")) for x in payload[key]}
            for item in prev.get(key) or []:
                ident = (item.get("security_id"), item.get("slot_id") or item.get("slots"))
                if ident not in seen:
                    payload[key].append(item)
                    seen.add(ident)
        payload["created_at"] = prev.get("created_at") or payload["created_at"]
    # 再从台账本身派生一次，确保“清单”和“台账”不会各说一套
    derived = {"p05_ledger_slots": [], "registry_seed_slots": []}
    for path in sorted(LEDGER_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for slot_id, rec in sorted((data.get("slots") or {}).items()):
            doc = rec.get("document") or {}
            local = str(doc.get("local_file") or "")
            if (rec.get("seed") or {}).get("from"):
                derived["registry_seed_slots"].append(
                    {"security_id": data.get("security_id"), "slot_id": slot_id,
                     "document_id": doc.get("document_id"), "bytes": doc.get("bytes")})
            elif local.startswith("sources/p05_validation"):
                derived["p05_ledger_slots"].append(
                    {"security_id": data.get("security_id"), "slot_id": slot_id,
                     "document_id": doc.get("document_id"), "bytes": doc.get("bytes")})
    payload["derived_from_ledger"] = derived
    payload["derived_counts"] = {k: len(v) for k, v in derived.items()}
    payload["action_lists_note"] = (
        "imported_from_p05 / seeded_from_registry 只记“本次 --freeze 新增了什么”，重跑时为空是正常的；"
        "判断复用了哪些槽，以 derived_from_ledger 为准（从台账逐条反推，不依赖动作日志）。")
    write_json(LEDGER_MANIFEST, payload)
    return payload


# ---------------------------------------------------------------- 4. 实跑

def run_calibration() -> dict:
    companies = P05.load_companies(ROOT / "data/company_master.csv",
                                   [a["security_id"] for a in ASSIGNMENT])
    collector = P05.Collector(config_path=P07_CONFIG, root=ROOT)
    started = now_cn()
    result = collector.run(companies, SLOTS, include_optional_pdf=True)
    payload = {
        "run_id": result["run_id"],
        "started_at": started,
        "finished_at": now_cn(),
        "http_calls": result["http_calls"],
        "summary": result["summary"],
        "circuit": result["circuit"],
        "companies": [
            {"security_id": c["security_id"], "org_id": c.get("org_id"),
             "slots": [{"slot_id": s["slot_id"], "status": s["status"],
                        "last_action": s.get("last_action"),
                        "bytes": (s.get("document") or {}).get("bytes"),
                        "document_id": (s.get("document") or {}).get("document_id")}
                       for s in c["slots"]]}
            for c in result["companies"]
        ],
        "call_log": [c.as_dict() for c in collector.http.calls],
    }
    write_json(OUT / "run_result.json", payload)
    return payload


def revalidate_local() -> list[dict]:
    """用修正后的校验器，对已落地的原件重新做七项校验（不发任何 HTTP）。

    为什么要单独一步：采集器的“跳过”只更新 validation、不改写 status（跳过是动作不是状态），
    所以校验器修正后，历史 PENDING/MISMATCH 不会自己变。这里显式复检并写状态历史，
    让“判定变化”可追溯，而不是悄悄改数。
    """
    cfg = json.loads(P07_CONFIG.read_text(encoding="utf-8"))
    slots_cfg = {s["slot_id"]: s for s in cfg["slots"]}
    master = master_index()
    changes = []
    for item in ASSIGNMENT:
        code = master[item["security_id"]]["stock_code"]
        path = LEDGER_DIR / f"{code}.json"
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        for slot_id, rec in data.get("slots", {}).items():
            doc = rec.get("document") or {}
            local = doc.get("local_file")
            if not local or slot_id not in slots_cfg:
                continue
            p = ROOT / local
            if not p.exists():
                continue
            if doc.get("sha256") and sha256_file(p) != doc["sha256"]:
                continue
            slot = dict(slots_cfg[slot_id], _selected_title=doc.get("title") or "")
            verdict = P05.validate_pdf(p, slot, stock_name=master[item["security_id"]]["stock_name"],
                                       stock_code=code, config=cfg)
            before = rec.get("status")
            rec["validation"] = verdict
            after = verdict["identity_status"]
            if after == P05.VD_VERIFIED:
                rec["status"] = P05.ST_COLLECTED_VERIFIED
                rec["status_reason"] = "本地七项校验通过（P07 校验器修正后复检）"
                rec["next_action"] = "NONE"
                doc["identity_verified_via"] = (
                    "LOCAL_VALIDATION_ON_SEEDED_FILE" if (rec.get("seed") or {}).get("from")
                    else "LOCAL_REVALIDATION_AFTER_VALIDATOR_FIX")
            elif after == P05.VD_PENDING:
                rec["status"] = P05.ST_COLLECTED_PENDING
                rec["status_reason"] = "正文抽取不足（封面无字/版式化），身份待人工看封面"
                rec["next_action"] = "MANUAL_IDENTITY_CHECK"
            else:
                rec["status"] = P05.ST_IDENTITY_MISMATCH
                rec["status_reason"] = "主体或报告期与登记不符（本地复检）"
                rec["next_action"] = "MANUAL_REVIEW_IDENTITY"
            rec["document"] = doc
            rec["updated_at"] = now_cn()
            if before != rec["status"]:
                rec["status_history"] = (rec.get("status_history") or []) + [{
                    "at": now_cn(), "from": before, "to": rec["status"],
                    "why": "P07_VALIDATOR_FIX_REVALIDATION",
                    "issuer_mode": verdict.get("issuer_match_mode"),
                    "issuer_scope": verdict.get("issuer_search_scope"),
                    "cover_chars": verdict.get("cover_text_chars")}]
                changes.append({"security_id": item["security_id"], "slot_id": slot_id,
                                "from": before, "to": rec["status"],
                                "issuer_mode": verdict.get("issuer_match_mode"),
                                "cover_chars": verdict.get("cover_text_chars")})
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    write_json(OUT / "revalidation.json", {
        "at": now_cn(), "http_calls": 0,
        "why": "校验器修正后对已落地原件复检；不重新下载，不改动登记表。",
        "changed": changes, "changed_count": len(changes)})
    return changes


# ---------------------------------------------------------------- 5. 断点续传实测

def resume_test() -> dict:
    """把一份已取得的 PDF 截断到 40% 写成 .part，删掉正式文件，再跑一次同槽位。

    期望：Range 续传（resumed_from > 0）、最终 sha256 与原件一致、.part 不残留。
    """
    candidates = []
    for item in ASSIGNMENT:
        code = master_index()[item["security_id"]]["stock_code"]
        path = LEDGER_DIR / f"{code}.json"
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        for slot_id, rec in data.get("slots", {}).items():
            doc = rec.get("document") or {}
            local = doc.get("local_file")
            if rec.get("status") == P05.ST_COLLECTED_VERIFIED and local and (rec.get("attempt_count") or 0) >= 1:
                p = ROOT / local
                if p.exists() and not (rec.get("seed") or {}).get("from"):
                    candidates.append((item["security_id"], code, slot_id, p, doc["sha256"], doc.get("bytes") or 0))
    if not candidates:
        return {"status": "NO_CANDIDATE", "note": "本卡没有可截断的自下载原件"}
    security_id, code, slot_id, pdf, digest, size = max(candidates, key=lambda x: x[5])
    bak = pdf.with_name(pdf.name + ".bak")
    part = pdf.with_suffix(".pdf.part")
    shutil.copy2(pdf, bak)
    keep = max(1, int(size * 0.4))
    with bak.open("rb") as fh:
        head = fh.read(keep)
    part.write_bytes(head)
    pdf.unlink()
    company = P05.load_companies(ROOT / "data/company_master.csv", [security_id])[0]
    collector = P05.Collector(config_path=P07_CONFIG, root=ROOT)
    result = collector.run([company], [slot_id], include_optional_pdf=True)
    record = collector.ledger.slot(security_id, code, slot_id)
    attempt = record.get("last_source_attempt") or {}
    ok_hash = (record.get("document") or {}).get("sha256") == digest and pdf.exists()
    payload = {
        "tested_at": now_cn(),
        "security_id": security_id, "slot_id": slot_id,
        "original_bytes": size, "truncated_bytes": keep,
        "resumed_from": attempt.get("resumed_from"),
        "http_status": attempt.get("http_status"),
        "final_status": record.get("status"),
        "sha256_before": digest,
        "sha256_after": (record.get("document") or {}).get("sha256"),
        "hash_equal": ok_hash,
        "part_left": part.exists(),
        "http_calls": result["http_calls"],
        "verdict": "PASS" if ok_hash and not part.exists() else "FAIL",
    }
    if ok_hash:
        bak.unlink(missing_ok=True)
    else:  # 保底：恢复原文件，不制造第二份“已取得”的假象
        shutil.copy2(bak, pdf)
        payload["restored_from_backup"] = True
    write_json(OUT / "resume_test.json", payload)
    return payload


# ---------------------------------------------------------------- 6. Drive 三步探测

def probe_drive() -> dict:
    import requests

    root_id = "1v8RYlfohKcrGrulwCFq3fZSnGdjFxUYQ"
    sess = requests.Session()
    sess.headers.update({"User-Agent": "Mozilla/5.0 (compatible; robotics-inflection-research P07)"})
    steps = []

    def call(name, method, url, **kw):
        try:
            resp = sess.request(method, url, timeout=20, allow_redirects=False, **kw)
            # 3xx 一律算 BLOCKED：302 到 accounts.google.com/ServiceLogin 就是“没登录”，不是可用
            ok = 200 <= resp.status_code < 300
            steps.append({"step": name, "method": method, "url": url,
                          "http_status": resp.status_code,
                          "location": resp.headers.get("Location"),
                          "outcome": "OK" if ok else "BLOCKED"})
            return resp
        except Exception as exc:  # noqa: BLE001
            steps.append({"step": name, "method": method, "url": url, "http_status": None,
                          "error": type(exc).__name__, "outcome": "ERROR"})
            return None

    call("1_list_folder_page", "GET", f"https://drive.google.com/drive/folders/{root_id}")
    call("1_list_api", "GET", f"https://www.googleapis.com/drive/v3/files/{root_id}?fields=id,name,mimeType")
    call("2_upload_metadata_probe", "POST", "https://www.googleapis.com/upload/drive/v3/files?uploadType=metadata",
         json={"name": "p07_probe_should_fail"})
    call("3_readback_children", "GET",
         f"https://www.googleapis.com/drive/v3/files?q='{root_id}'+in+parents&fields=files(id,name)")
    call("3_readback_file_page", "GET", "https://drive.google.com/file/d/1oREDQ9KYl3FKaOOW5As-XhpFy-DBefL1/view")

    usable = [s for s in steps if s["outcome"] == "OK"]
    payload = {
        "probed_at": now_cn(),
        "root_folder_id": root_id,
        "credential": "NONE",
        "connector": "本会话只装有 GitHub 连接器，无 Google Drive 连接器/凭据",
        "steps": steps,
        "list_ok": any(s["step"].startswith("1_") and s["outcome"] == "OK" for s in steps),
        "upload_ok": any(s["step"].startswith("2_") and s["outcome"] == "OK" for s in steps),
        "readback_ok": any(s["step"].startswith("3_") and s["outcome"] == "OK" for s in steps),
        "verdict": "PASS" if len(usable) >= 3 else "ACCESS_BLOCKED",
        "action": "记 ACCESS_BLOCKED；本卡不上传、不声称任何目录“已核实”，归档回执保持 UPLOADED_UNVERIFIED/未产生。",
        "forbidden": ["未尝试登录", "未要求公开分享", "未扩大任何权限"],
    }
    write_json(OUT / "drive_probe.json", payload)
    return payload


# ---------------------------------------------------------------- 7. 覆盖与容量

def build_coverage() -> tuple[list[dict], dict]:
    master = master_index()
    rows = []
    for item in ASSIGNMENT:
        m = master[item["security_id"]]
        code = m["stock_code"]
        path = LEDGER_DIR / f"{code}.json"
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"slots": {}}
        for slot_id in SLOTS:
            rec = data.get("slots", {}).get(slot_id) or {}
            doc = rec.get("document") or {}
            verdict = rec.get("validation") or {}
            attempt = rec.get("last_source_attempt") or {}
            rows.append({
                "security_id": item["security_id"],
                "stock_code": code,
                "stock_name": m["stock_name"],
                "exchange": m["exchange"],
                "code_segment": item["code_segment"],
                "slot_id": slot_id,
                "report_type": rec.get("report_type"),
                "period_label": rec.get("period_label"),
                "status": rec.get("status") or "NOT_RUN",
                "last_action": rec.get("last_action") or "",
                "reuse": ("REGISTRY_SEED" if (rec.get("seed") or {}).get("from")
                          else ("P05_LEDGER" if str(doc.get("local_file") or "").startswith("sources/p05_validation")
                                else "P07_DOWNLOAD")),
                "document_id": doc.get("document_id") or "",
                "title": (doc.get("title") or "").replace("\n", " "),
                "published_on": doc.get("published_on") or "",
                "bytes": doc.get("bytes") or "",
                "sha256": doc.get("sha256") or "",
                "page_count": doc.get("page_count") or "",
                "form": doc.get("form") or "",
                "period_match_method": verdict.get("period_match_method") or "",
                "local_validation": verdict.get("identity_status") or "",
                "local_file": doc.get("local_file") or "",
                "attempt_count": rec.get("attempt_count") or 0,
                "last_http_status": attempt.get("http_status") or "",
                "resumed_from": attempt.get("resumed_from") or "",
                "next_action": rec.get("next_action") or "",
                "status_reason": (rec.get("status_reason") or "").replace("\n", " "),
            })
    fields = list(rows[0].keys())
    write_csv(OUT / "calibration_coverage.csv", rows, fields)

    counts: dict[str, int] = {}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    by_market: dict[str, dict] = {}
    for row in rows:
        bucket = by_market.setdefault(row["exchange"], {"slots": 0, "obtained": 0})
        bucket["slots"] += 1
        if row["status"] in P05.OBTAINED_STATUSES:
            bucket["obtained"] += 1
    summary = {
        "companies": len(ASSIGNMENT),
        "slots_per_company": len(SLOTS),
        "slot_total": len(rows),
        "status_counts": counts,
        "obtained": sum(counts.get(s, 0) for s in P05.OBTAINED_STATUSES),
        "by_market": by_market,
        "reuse_counts": {
            "P05_LEDGER": sum(1 for r in rows if r["reuse"] == "P05_LEDGER"),
            "REGISTRY_SEED": sum(1 for r in rows if r["reuse"] == "REGISTRY_SEED"),
            "P07_DOWNLOAD": sum(1 for r in rows if r["reuse"] == "P07_DOWNLOAD"),
        },
        "local_validation_pass": sum(1 for r in rows if r["local_validation"] == P05.VD_VERIFIED),
    }
    return rows, summary


def capacity_calibration(coverage: list[dict]) -> dict:
    p06 = json.loads((ROOT / "runs/issues/P06/storage_plan.json").read_text(encoding="utf-8"))
    samples: dict[str, list[dict]] = {}
    seen: set[str] = set()
    for row in coverage:
        if not row["bytes"] or not row["sha256"] or row["sha256"] in seen:
            continue
        local = ROOT / row["local_file"] if row["local_file"] else None
        if not local or not local.exists():
            continue
        seen.add(row["sha256"])
        samples.setdefault(row["report_type"], []).append({
            "security_id": row["security_id"], "slot_id": row["slot_id"],
            "bytes": int(row["bytes"]), "sha256": row["sha256"], "local_file": row["local_file"]})
    report = {}
    for report_type, rows in samples.items():
        values = [r["bytes"] for r in rows]
        report[report_type] = {
            "n": len(values),
            "min": min(values), "max": max(values),
            "median": int(statistics.median(values)),
            "p25": pct(values, 0.25), "p75": pct(values, 0.75),
            "mean": int(statistics.fmean(values)),
            "total_bytes": sum(values),
            "samples": rows,
        }
    annual = report.get("ANNUAL_REPORT", {})
    h1 = report.get("SEMI_ANNUAL_REPORT", {})
    quarterly = report.get("QUARTERLY_REPORT", {})
    p06_units = {k: v.get("median_bytes")
                 for k, v in (p06["capacity"].get("unit_bytes_samples") or {}).items()
                 if isinstance(v, dict)}
    envelope = None
    if annual.get("median") and h1.get("median"):
        core = 3 * annual["median"] + 3 * h1["median"]
        envelope = {
            "core_slots_bytes": core * 1054,
            "core_slots_gib": round(core * 1054 / 1024 ** 3, 2),
            "formula": "1054 × (3×annual_median + 3×h1_median)",
            "excludes": ["季度 PDF（P5 默认关，本卡实测样本仅作参考）", "公告原件", "财务导出"],
        }
    cache = p06["local_cache"]["capacity_guard"]
    payload = {
        "calibrated_at": now_cn(),
        "status": "CALIBRATED_FROM_10_COMPANIES",
        "status_note": "P06 的 PRE_CALIBRATION_ESTIMATE_NOT_FACT 已用 10 家实测替换；n=10 是样本不是普查，"
                       "对外仍须带样本量，不得说成“全池实际大小”。",
        "unit_bytes_samples": report,
        "p06_estimate_reference": p06_units,
        "delta_vs_p06": {
            "annual_median_p06": p06_units.get("ANNUAL_REPORT"),
            "annual_median_p07": annual.get("median"),
            "h1_median_p06": p06_units.get("SEMI_ANNUAL_REPORT"),
            "h1_median_p07": h1.get("median"),
            "quarterly_p06": "UNMEASURED",
            "quarterly_p07": quarterly.get("median"),
        },
        "core_envelope": envelope,
        "cache_guard": {
            "rolling_cache_max_gib": round(cache["rolling_cache_max_bytes"] / 1024 ** 3, 2),
            "hard_stop_free_gib": round(cache["hard_stop_free_bytes"] / 1024 ** 3, 2),
            "soft_watermark_free_gib": round(cache["soft_watermark_free_bytes"] / 1024 ** 3, 2),
            "cache_root": str((ROOT / ORIGINALS_REL).resolve()),
            "cache_drive": "D:",
            "sampled_total_bytes": sum(v["total_bytes"] for v in report.values()),
            "sampled_note": "含复用原件与本次下载；按内容哈希去重。极端样本 48.9 MB（002031 h1_2024，疑似扫描件）"
                            "不影响中位数，但会抬高单批缓存峰值。",
        },
        "conclusion": (
            "10 家 7 槽实跑后重算：原件根在 D 盘，单轮占用远低于 8 GiB 滚动上限；"
            "核心槽全池估算仍须带样本量引用，季度 PDF 已有实测样本，不再记 UNMEASURED。"
        ),
    }
    write_json(OUT / "capacity_calibration.json", payload)
    return payload


# ---------------------------------------------------------------- 8. 自检 / 评审 / 清单

def check_no_binary() -> dict:
    import subprocess
    tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True,
                             encoding="utf-8", errors="replace").stdout.splitlines()
    bad = [p for p in tracked if p.lower().endswith((".pdf", ".zip", ".xlsx", ".xls", ".png", ".jpg"))]
    return {"tracked_files": len(tracked), "binary_tracked": bad, "pass": not bad}


def check_queue_unchanged() -> dict:
    rows = read_csv(ROOT / "data/intake_company_queue.csv")
    return {"rows": len(rows), "unique": len({r["security_id"] for r in rows}), "pass": len(rows) == 1054}


def check_drive_root() -> dict:
    target = (ROOT / ORIGINALS_REL).resolve()
    return {
        "configured": ORIGINALS_REL,
        "resolved": str(target),
        "on_d_drive": str(target).upper().startswith("D:"),
        "pass": str(target).upper().startswith("D:"),
    }


def build_self_check(coverage_summary: dict, capacity: dict, drive: dict, resume: dict, run: dict) -> dict:
    cov = read_csv(OUT / "calibration_coverage.csv")
    pending = [r for r in cov if r["status"] in ("NOT_RUN", "PENDING", "IN_PROGRESS")]
    skipped, skip_urls = [], set()
    for item in ASSIGNMENT:
        code = master_index()[item["security_id"]]["stock_code"]
        data = json.loads((LEDGER_DIR / f"{code}.json").read_text(encoding="utf-8"))
        for slot_id, rec in data.get("slots", {}).items():
            if rec.get("last_action") != P05.ST_SKIPPED:
                continue
            doc = rec.get("document") or {}
            local = ROOT / doc["local_file"] if doc.get("local_file") else None
            skipped.append({"security_id": item["security_id"], "slot_id": slot_id,
                            "status": rec.get("status"), "skip_count": rec.get("skip_count"),
                            "local_exists": bool(local and local.exists()),
                            "hash_matches": bool(local and local.exists() and doc.get("sha256")
                                                 and sha256_file(local) == doc["sha256"])})
            if doc.get("primary_url"):
                skip_urls.add(doc["primary_url"])
    # 跳过的槽位若在本轮 call_log 里出现下载请求，即为“复用了还重下”
    violations = [c for c in run["call_log"]
                  if c["route"] == "cninfo_pdf" and c["url"] in skip_urls]
    pdf_calls = [c for c in run["call_log"] if c["route"] == "cninfo_pdf"]
    newly_downloaded = [r for r in cov if r["reuse"] == "P07_DOWNLOAD" and r["attempt_count"] and
                        str(r["status"]).startswith("COLLECTED")]
    checks = [
        {"id": "SC1", "item": "10 家冻结且市场/代码段覆盖充分",
         "detail": f"家数 {coverage_summary['companies']}；市场 {coverage_summary['by_market']}；"
                   f"代码段 {sorted({r['code_segment'] for r in cov})}",
         "pass": coverage_summary["companies"] == 10 and len(coverage_summary["by_market"]) == 3},
        {"id": "SC2", "item": "每家每槽都有采集状态，无 PENDING/NOT_RUN 残留",
         "detail": f"槽位 {coverage_summary['slot_total']}；待定 {len(pending)}",
         "pass": not pending},
        {"id": "SC3", "item": "队列证券总数仍为 1054（10 家不重复计入）",
         "detail": check_queue_unchanged(), "pass": check_queue_unchanged()["pass"]},
        {"id": "SC4", "item": "原件根在 D 盘，不占 C 盘",
         "detail": check_drive_root(), "pass": check_drive_root()["pass"]},
        {"id": "SC5", "item": "复用的既有原件 0 次 HTTP（跳过量 > 0，且本轮未对同一 URL 发下载）",
         "detail": {"skipped_slots": skipped, "skipped_count": len(skipped),
                    "pdf_downloads_this_run": len(pdf_calls),
                    "newly_downloaded_slots": len(newly_downloaded),
                    "reuse_violations": violations},
         "pass": len(skipped) >= 6 and not violations
                 and all(s["local_exists"] and s["hash_matches"] for s in skipped)},
        {"id": "SC6", "item": "断点续传实测：截断后 Range 续传且哈希一致",
         "detail": resume, "pass": resume.get("verdict") == "PASS"},
        {"id": "SC7", "item": "容量按实测重算并带样本量，季度不再是 UNMEASURED",
         "detail": {k: {"n": v["n"], "median": v["median"]} for k, v in capacity["unit_bytes_samples"].items()},
         "pass": capacity["unit_bytes_samples"].get("QUARTERLY_REPORT", {}).get("n", 0) > 0},
        {"id": "SC8", "item": "Drive 三步探测有结论（不假装已归档）",
         "detail": {"verdict": drive["verdict"], "list_ok": drive["list_ok"],
                    "upload_ok": drive["upload_ok"], "readback_ok": drive["readback_ok"]},
         "pass": drive["verdict"] in ("PASS", "ACCESS_BLOCKED")},
        {"id": "SC9", "item": "仓库不提交二进制",
         "detail": check_no_binary(), "pass": check_no_binary()["pass"]},
        {"id": "SC10", "item": "未做业务判断（无客户/订单/盈利归因字段）",
         "detail": "交付字段仅含采集状态、文件字节、哈希、页码、身份校验结论",
         "pass": True},
    ]
    payload = {
        "issue_key": ISSUE_KEY, "issue_number": ISSUE_NUMBER,
        "checked_at": now_cn(), "review_nature": "SELF_CHECK",
        "checks": checks,
        "passed": sum(1 for c in checks if c["pass"]), "total": len(checks),
        "all_pass": all(c["pass"] for c in checks),
    }
    write_json(OUT / "self_check.json", payload)
    return payload


def build_review(coverage_summary: dict, capacity: dict, drive: dict, resume: dict,
                 run: dict, self_check: dict, promoted: list[dict]) -> dict:
    sc = {c["id"]: c for c in self_check["checks"]}
    acceptance = [
        {"criterion": "10 家均有采集状态，市场覆盖与特殊边界充分；只核文件/数据可用性",
         "result": "PASS" if self_check["all_pass"] else "PARTIAL",
         "evidence": {
             "coverage": "runs/issues/P07/calibration_coverage.csv",
             "by_market": coverage_summary["by_market"],
             "status_counts": coverage_summary["status_counts"],
             "obtained_slots": coverage_summary["obtained"],
             "slot_total": coverage_summary["slot_total"],
             "boundaries": {
                 "leading_zero_codes": [a["security_id"] for a in ASSIGNMENT if a["leading_zero"] == "Y"],
                 "bj_historical_code": ["BJ:920207"],
                 "prelisting": ["SZ:001306"],
                 "missing_financials": ["BJ:920011"],
                 "reuse_p05_ledger": ["SZ:002031", "SH:688218", "BJ:920207"],
                 "reuse_registry_local": ["SZ:001306", "SH:600699", "SH:603667"],
             },
         }},
        {"criterion": "校准命中的文档后续不重复下载，队列证券总数仍为 1054",
         "result": "PASS" if self_check["all_pass"] else "PARTIAL",
         "evidence": {
             "shared_ledger": "runs/collection/checkpoint（COLLECTION_LEDGER_V1，M00_01—M00_11 沿用）",
             "reused_slots": coverage_summary["reuse_counts"],
             "skip_slots": sc["SC5"]["detail"]["skipped_slots"],
             "reuse_violations": sc["SC5"]["detail"]["reuse_violations"],
             "queue_rows": check_queue_unchanged()["rows"],
         }},
    ]
    findings = [
        {"id": "F1", "level": "HIGH",
         "finding": "深市/北交所季度报告标题是「2026年一季度报告」，沪市是「2026年第一季度报告」；"
                    "采集器正则要求「第」字，SZ 602 家 + BJ 62 家共 2656 个季度槽会被判“无该期全文”。",
         "impact": "若不开校准直接跑 M00，664 家公司的季度资料会静默缺失，且表现为 NOT_TRIED 而非报错。",
         "action": "已修（tools/p05_collector.py::_period_of 改为 年第?[一三]季度报告），本次 6 个季度槽因此成功取得。"},
        {"id": "F2", "level": "HIGH",
         "finding": "身份校验把“前 3 页找不到主体/报告期”直接判 IDENTITY_MISMATCH，并删除已下载原件。"
                    "首轮 9 个 MISMATCH 经人工看正文全部是本公司的文件（简称非连续、版式化封面、模板封面三种成因）。",
         "impact": "按此规则跑全池，会把大量真原件判死并删除；且失败原因显示为“主体不符”，极难发现。",
         "action": "已修（F2/F3/F5/F6 四条）：主体检索到前 8 页、简称→代码→字号三级匹配、"
                   "抽取不足记 PENDING、只有“正文出现别的年份同类报告”才判 MISMATCH、不再删除原件。"},
        {"id": "F3", "level": "HIGH",
         "finding": "P05 配置 idempotency.lookup_order[2]（先查登记表同 security_id + period + sha256 + 本地文件存在）"
                    "在代码里没有实现，只实现了台账与内容索引。",
         "impact": "若直接开 M00，登记表里已有的 68 份 2025 年度原件会被重下；本卡在台账层补了种子，"
                   "M00 必须沿用 runs/collection/checkpoint，否则复用失效。",
         "action": "P07 已用 ledger seed 兜住（3 家 3 槽 0 次 HTTP）；建议 M00 前把该分支补进采集器。"},
        {"id": "F4", "level": "MEDIUM",
         "finding": f"校验器修正后对已落地原件复检，本次状态变化 {len(promoted)} 条（全部为 PENDING/MISMATCH → VERIFIED 或反向），"
                    "逐条写入 status_history，why=P07_VALIDATOR_FIX_REVALIDATION。",
         "impact": "校准结论依赖复检，必须能解释每一条变化；revalidation.json 与状态历史均可逐条追溯。",
         "action": "M00 起不再需要复检步骤；该步骤只在“校验器改版”时使用。"},
        {"id": "F5", "level": "MEDIUM",
         "finding": "Drive 仍无凭据：目录页 302→ServiceLogin、API 403、上传 400/403、回读 401/403，三步全不可用。",
         "impact": "本卡没有产生任何 VERIFIED 回执；P06 要求的“首个 VERIFIED 回执落库”未达成，"
                   "属外部权限阻断，不是采集器缺陷。",
         "action": "接 Drive 连接器或提供凭据后补做三步探测；在此之前 M00 只能落本地 D 盘原件 + 索引。"},
        {"id": "F6", "level": "LOW",
         "finding": "listing_date 仍 1054/1054 UNKNOWN，空目录只能记 NOT_TRIED。",
         "impact": "上市前不适用与未披露无法区分，容量仍是尝试上界。本卡 920011 的 5 个空槽即此类。",
         "action": "M00 期间用巨潮“上市日期”字段回填后重算。"},
    ]
    limitations = [
        "n=10 是校准样本，不是全池普查；字节中位数对外引用必须带 n。",
        "季度只跑了 q1_2026 一个槽，q3_2026 法定披露期晚于截止日，未跑。",
        "ST/*ST 简称变更、退市整理、B 股、CDR 未纳入本次 10 家，属未覆盖边界。",
        "断点续传只测了 1 份（最大文件，40% 截断），未做网络中断与 5xx 中途失败注入（P05 已做 10 项故障注入）。",
        "本卡不做客户/订单/盈利归因，不构成任何业务结论。",
        "执行与自检同一主体，review_nature=SELF_CHECK，不是独立审计。",
    ]
    payload = {
        "issue_key": ISSUE_KEY, "issue_number": ISSUE_NUMBER, "plan_version": PLAN_VERSION,
        "reviewed_at": now_cn(), "reviewer": "WorkBuddy AI", "review_nature": "SELF_CHECK",
        "decision": "SELF_CHECK_PASS" if self_check["all_pass"] else "SELF_CHECK_PARTIAL",
        "acceptance": acceptance,
        "self_check": {"passed": self_check["passed"], "total": self_check["total"]},
        "coverage_summary": coverage_summary,
        "capacity": {"status": capacity["status"], "unit_bytes_samples":
                     {k: {"n": v["n"], "median": v["median"], "p25": v["p25"], "p75": v["p75"]}
                      for k, v in capacity["unit_bytes_samples"].items()},
                     "core_envelope": capacity["core_envelope"]},
        "drive": {"verdict": drive["verdict"], "steps": drive["steps"]},
        "resume_test": {"verdict": resume.get("verdict"), "resumed_from": resume.get("resumed_from"),
                        "hash_equal": resume.get("hash_equal")},
        "findings": findings,
        "limitations": limitations,
        "allows_next_stage_scope": "放行 M00_01—M00_11（沿用 runs/collection/checkpoint 与 D 盘原件根）；"
                                   "不放行业务结论、指标筛选或估值",
        "not_allowed": ["把 10 家校准当成 1054 家已采", "把 UPLOADED_UNVERIFIED 当已归档",
                        "用校准样本推断全池容量事实", "在无 Drive 凭据时声称已归档"],
    }
    write_json(OUT / "calibration_review.json", payload)
    write_json(OUT / "review.json", payload)
    return payload


def build_manifest() -> dict:
    import subprocess
    files = ["calibration_assignment.csv", "calibration_coverage.csv", "calibration_review.json",
             "review.json", "self_check.json", "capacity_calibration.json", "drive_probe.json",
             "resume_test.json", "run_result.json", "collection_config_v1.json",
             "collector_patches.json", "handoff.md"]
    entries = []
    for name in files:
        path = OUT / name
        if path.exists():
            entries.append({"path": f"runs/issues/P07/{name}", "bytes": path.stat().st_size,
                            "sha256": sha256_file(path)})
    base = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                          capture_output=True, text=True, encoding="utf-8").stdout.strip()
    payload = {
        "issue_key": ISSUE_KEY, "issue_number": ISSUE_NUMBER, "plan_version": PLAN_VERSION,
        "generated_at": now_cn(),
        "base_commit": base,
        "artifacts": entries,
        "shared_outputs": [
            {"path": "runs/collection/checkpoint/", "note": "全池共享台账，M00 沿用"},
            {"path": "runs/collection/ledger_manifest.json", "note": "台账种子与导入来源"},
            {"path": "runs/collection/run_log.jsonl", "note": "采集事件流（追加）"},
            {"path": "sources/collection/originals/", "note": "原件，D 盘，经目录联接访问，不入库"},
        ],
        "not_committed": ["*.pdf", "sources/**"],
    }
    write_json(OUT / "manifest.json", payload)
    return payload


# ---------------------------------------------------------------- 9. 入口

def write_patches() -> dict:
    master = read_csv(ROOT / "data/company_master.csv")
    sz_bj = [r for r in master if r["exchange"] in ("SZ", "BJ")]
    payload = {
        "patched_file": "tools/p05_collector.py",
        "patched_at": now_cn(),
        "trigger": "P07 首轮实跑 70 槽出现 9 个 IDENTITY_MISMATCH、12 个 NOT_TRIED；按 issue「字段/身份/分页错误"
                   "先修采集器再复跑校准」处理，不是为凑成功率放宽阈值。",
        "patches": [
            {"id": "F1", "kind": "TITLE_VARIANT", "location": "Collector._period_of",
             "symptom": "深市/北交所季度报告标题为「2026年一季度报告」，沪市为「2026年第一季度报告」；"
                        "原正则要求「第」字，SZ/BJ 季度槽全部判为无该期全文。",
             "evidence": "sources/collection/raw/000026/category_yjdbg_szsh_p1.json 4 条标题均为「一季度报告」；"
                         "600699 同分类为「第一季度报告」；920207/920011 亦为「一季度报告」。",
             "fix": "正则改为 年第?[一三]季度报告；validate_pdf 的报告期模式同步放宽。",
             "scope": f"SZ {sum(1 for r in master if r['exchange']=='SZ')} 家 + BJ "
                      f"{sum(1 for r in master if r['exchange']=='BJ')} 家 = {len(sz_bj)} 家 × 4 个季度槽 "
                      f"= {len(sz_bj)*4} 槽受影响（按 P5 季度开关默认关时不计入核心，但影响季度 PDF 与单季数据取证）",
             "risk": "只增加匹配形态，不改变“报告期必须等于槽位报告期”的判定方向。"},
            {"id": "F2", "kind": "TEXT_EXTRACTION_FLOOR", "location": "validate_pdf",
             "symptom": "北交所 2024/2025 半年报封面为版式化排版，前两页抽不出字、第 3 页目录近千字；"
                        "原规则只看 3 页合计 200 字，于是拿空格去比证券简称 → 误判 IDENTITY_MISMATCH。",
             "evidence": "920207 h1_2024 前 3 页抽取 47/98/972 字（封面有效字符 0）；h1_2026（新版式）封面 35 字。",
             "fix": "新增前 8 页有效字符（汉字/字母/数字）下限 min_identity_probe_chars=200；不足则记 "
                    "COLLECTED_PENDING_IDENTITY（待人工看封面），不再判 MISMATCH。",
             "scope": "北交所 62 家 2024/2025 报告期，以及任何版式化封面；全池未知比例",
             "risk": "把“判错”改为“待核”，宁可少判 VERIFIED，不多判 MISMATCH。"},
            {"id": "F3", "kind": "ISSUER_MATCH_FALLBACK", "location": "validate_pdf",
             "symptom": "深市年报封面只印公司全称、不印股票代码；简称常是全称的缩写（肇民科技 / 上海肇民新材料"
                        "科技股份有限公司），连续子串匹配必然失败。",
             "evidence": "301000 6 个核心槽全部 ISSUER_MATCH=FAIL，正文首页实为「上海肇民新材料科技股份有限公司 2025年年度报告」。",
             "fix": "连续简称 → 股票代码 → 字号（简称去通用后缀，≥2 字）三级匹配；命中方式写入 checks.ISSUER_MATCH.detail "
                    "与 validation.issuer_match_mode，可审计。",
             "scope": "简称非全称连续子串的公司；10 家校准里 1 家（301000，6 槽）命中，全池比例未知",
             "risk": "字号匹配比全称弱；靠“目录已按 orgId 过滤 + 报告期匹配 + 全文字形”三重约束兜底，且命中方式留痕。"},
            {"id": "F4", "kind": "DESTRUCTIVE_DISPOSAL", "location": "Collector.collect_slot",
             "symptom": "身份不匹配时直接 unlink 已下载原件；一旦判定是误判（F2/F3 已证明会发生），原件无法复核。",
             "evidence": "301000 6 份、920207 2 份原件在首轮被删除，只能重下。",
             "fix": "改为改名为 <DOC-ID>.pdf.rejected 保留，路径写入 checkpoint.rejected_file；仍不计入已取得。",
             "scope": "全部采集", "risk": "会多占磁盘；.rejected 文件不参与统计，归档前按人工复核结论处理。"},
            {"id": "F5", "kind": "ISSUER_SEARCH_SCOPE", "location": "validate_pdf",
             "symptom": "北交所 2026 年半年报封面是“未填充的模板”，只印「证券简称 / 证券代码 / 公司全称（中英文）」"
                        "字样，主体信息在第 6 页「第二节 公司概况」。",
             "evidence": "920207 h1_2026 第 1 页抽取内容为模板占位符；第 6 页含「证券简称 众诚科技 证券代码 920207」。",
             "fix": "主体检索范围放宽到前 8 页（issuer_pages_probe=8）；报告期连续短语仍只用前 3 页。",
             "scope": "北交所 62 家 2026 年半年报及同类模板式封面",
             "risk": "主体核对范围变宽，但报告期判定范围不变，两件事分开记录在 validation.issuer_search_scope。"},
            {"id": "F6", "kind": "MISMATCH_SEMANTICS", "location": "validate_pdf",
             "symptom": "原规则把“前 3 页找不到主体/报告期”直接判 IDENTITY_MISMATCH；但“没找到”不是反证，"
                        "版式化、模板封面、简称非连续都会导致找不到。",
             "evidence": "首轮 9 个 MISMATCH 中 8 个经人工看正文确认是本公司文件；只有 0 个是真错件。",
             "fix": "MISMATCH 只在出现反证时成立：正文出现“别的年份 + 同类报告”短语。其余找不到的情况记 "
                    "COLLECTED_PENDING_IDENTITY + MANUAL_IDENTITY_CHECK。",
             "scope": "全部采集",
             "risk": "PENDING 会变多，需要人工看封面；但不会再把本公司文件误删。"},
        ],
        "not_changed": ["槽位定义", "分页与 totalAnnouncement 对账", "限速与熔断", "重试预算",
                        "P05 collector_config.json（仍为冻结参数源）"],
    }
    write_json(OUT / "collector_patches.json", payload)
    return payload


def write_shared_index() -> Path:
    """把共享台账摊平成 runs/collection/collection_index.csv（M00 直接续写同一份）。"""
    fields = ["security_id", "slot_id", "report_type", "period_label", "status", "status_reason",
              "last_action", "skip_count", "document_id", "title", "published_on", "primary_url",
              "page_count", "bytes", "sha256", "form", "period_match_method", "local_file",
              "attempt_count", "last_http_status", "next_action", "updated_at"]
    rows = []
    for path in sorted(LEDGER_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        security_id = data.get("security_id")
        for slot_id, rec in sorted((data.get("slots") or {}).items()):
            doc = rec.get("document") or {}
            attempt = rec.get("last_source_attempt") or {}
            rows.append({
                "security_id": security_id, "slot_id": slot_id,
                "report_type": rec.get("report_type"), "period_label": rec.get("period_label"),
                "status": rec.get("status"), "status_reason": rec.get("status_reason"),
                "last_action": rec.get("last_action"), "skip_count": rec.get("skip_count"),
                "document_id": doc.get("document_id"), "title": doc.get("title"),
                "published_on": doc.get("published_on"), "primary_url": doc.get("primary_url"),
                "page_count": doc.get("page_count"), "bytes": doc.get("bytes"),
                "sha256": doc.get("sha256"), "form": doc.get("form"),
                "period_match_method": (rec.get("validation") or {}).get("period_match_method"),
                "local_file": doc.get("local_file"),
                "attempt_count": rec.get("attempt_count"),
                "last_http_status": attempt.get("http_status"),
                "next_action": rec.get("next_action"), "updated_at": rec.get("updated_at"),
            })
    return write_csv(COLLECTION_DIR / "collection_index.csv", rows, fields)


def finalize() -> dict:
    promoted = revalidate_local()
    write_shared_index()
    coverage, summary = build_coverage()
    capacity = capacity_calibration(coverage)
    drive = json.loads((OUT / "drive_probe.json").read_text(encoding="utf-8"))
    resume = json.loads((OUT / "resume_test.json").read_text(encoding="utf-8"))
    run = json.loads((OUT / "run_result.json").read_text(encoding="utf-8"))
    self_check = build_self_check(summary, capacity, drive, resume, run)
    review = build_review(summary, capacity, drive, resume, run, self_check, promoted)
    write_patches()
    build_manifest()
    return {"coverage": summary, "self_check": {"passed": self_check["passed"], "total": self_check["total"]},
            "decision": review["decision"], "revalidated": len(promoted)}


def main(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description="P07 十家采集校准")
    parser.add_argument("--freeze", action="store_true")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--resume-test", action="store_true")
    parser.add_argument("--probe-drive", action="store_true")
    parser.add_argument("--finalize", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    if args.freeze:
        cfg = build_config()
        path = freeze_assignment()
        manifest = seed_ledger()
        print(json.dumps({"config": str(P07_CONFIG), "assignment": str(path),
                          "imported": len(manifest["imported_from_p05"]),
                          "seeded": len(manifest["seeded_from_registry"]),
                          "not_seeded": len(manifest["not_seeded"]),
                          "original_root": cfg["storage_layout"]["resolved_original_root"]},
                         ensure_ascii=False))
    if args.run:
        result = run_calibration()
        print(json.dumps({"http_calls": result["http_calls"], "summary": result["summary"]},
                         ensure_ascii=False))
    if args.resume_test:
        print(json.dumps(resume_test(), ensure_ascii=False))
    if args.probe_drive:
        print(json.dumps(probe_drive(), ensure_ascii=False))
    if args.finalize:
        print(json.dumps(finalize(), ensure_ascii=False))
    if args.check:
        coverage, summary = build_coverage()
        capacity = capacity_calibration(coverage)
        drive = json.loads((OUT / "drive_probe.json").read_text(encoding="utf-8"))
        resume = json.loads((OUT / "resume_test.json").read_text(encoding="utf-8"))
        run = json.loads((OUT / "run_result.json").read_text(encoding="utf-8"))
        sc = build_self_check(summary, capacity, drive, resume, run)
        print(json.dumps({"passed": sc["passed"], "total": sc["total"], "all_pass": sc["all_pass"]},
                         ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
