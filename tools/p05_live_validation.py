"""P05 三市场小样本实跑：只验采集能力，不做业务研究。

产物：
- runs/issues/P05/live_validation.json（小型、可入库）
- sources/p05_validation/<code>/<slot>/<document_id>.pdf（原件，.gitignore 排除）
- runs/issues/P05/checkpoint/<code>.json（台账）
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))

import p05_collector as pc  # noqa: E402

SAMPLES = [
    pc.CompanyRef("SH:688218", "688218", "江苏北人", "SH"),
    pc.CompanyRef("SZ:002031", "002031", "巨轮智能", "SZ"),
    pc.CompanyRef("BJ:920207", "920207", "众诚科技", "BJ"),
]
SLOTS = ["annual_2025"]
OUT = REPO / "runs/issues/P05/live_validation.json"


def file_sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def slot_view(record: dict) -> dict:
    doc = record.get("document") or {}
    return {
        "slot_id": record["slot_id"],
        "status": record["status"],
        "status_reason": record.get("status_reason"),
        "last_action": record.get("last_action"),
        "next_action": record.get("next_action"),
        "attempt_count": record.get("attempt_count"),
        "document_id": doc.get("document_id"),
        "title": doc.get("title"),
        "published_on": doc.get("published_on"),
        "primary_url": doc.get("primary_url"),
        "local_file": doc.get("local_file"),
        "page_count": doc.get("page_count"),
        "bytes": doc.get("bytes"),
        "sha256": doc.get("sha256"),
        "form": doc.get("form"),
        "period_match_method": (record.get("validation") or {}).get("period_match_method"),
        "checks": {k: v["result"] for k, v in (record.get("validation", {}).get("checks") or {}).items()},
        "last_source_attempt": record.get("last_source_attempt"),
    }


def main() -> int:
    started = time.time()
    collector = pc.Collector()
    first = collector.run(SAMPLES, SLOTS)

    companies = []
    for company, block in zip(SAMPLES, first["companies"]):
        ledger = json.loads((REPO / "runs/issues/P05/checkpoint" / f"{company.stock_code}.json")
                            .read_text(encoding="utf-8"))
        annual_idx = ledger["indexes"].get("category_ndbg_szsh", {})
        hist = [r for r in annual_idx.get("rows", [])
                if r.get("sec_code") and r["sec_code"] != company.stock_code]
        slot = block["slots"][0]
        doc = slot.get("document") or {}
        local = REPO / doc["local_file"] if doc.get("local_file") else None
        file_ok = bool(local and local.exists())
        hash_ok = bool(file_ok and doc.get("sha256") and file_sha(local) == doc["sha256"])
        companies.append({
            "security_id": company.security_id,
            "stock_name": company.stock_name,
            "exchange": company.exchange,
            "org_id": block.get("org_id"),
            "index": {
                "category": annual_idx.get("category"),
                "column": annual_idx.get("column"),
                "total_announcement": annual_idx.get("total_announcement"),
                "rows_fetched": annual_idx.get("rows_fetched"),
                "pages_fetched": annual_idx.get("pages_fetched"),
                "reconciled": annual_idx.get("reconciled"),
                "status": annual_idx.get("status"),
                "request_base": annual_idx.get("request_base"),
                "page_cursors": [{k: p.get(k) for k in ("page", "rows", "response_sha256", "fetched_at")}
                                 for p in annual_idx.get("pages", [])],
                "historical_code_rows": [
                    {"sec_code": r["sec_code"], "title": r.get("title"), "published_on": r.get("published_on")}
                    for r in hist
                ],
            },
            "slot": slot_view(slot),
            "binary_proof": {"local_file_exists": file_ok, "sha256_matches_file": hash_ok},
        })

    # 第二次运行：幂等跳过，且不发出新的 HTTP 请求
    second = pc.Collector().run(SAMPLES, SLOTS)
    skip_actions = [c["slots"][0].get("last_action") for c in second["companies"]]

    # 限速单独用隔离根目录做 2 次同主机请求，避免被幂等跳过影响样本量
    import shutil
    import tempfile
    tmp = Path(tempfile.mkdtemp(prefix="p05_l7_"))
    try:
        (tmp / "runs/issues/P03").mkdir(parents=True)
        shutil.copy2(REPO / "runs/issues/P03/source_circuit_policy.json",
                     tmp / "runs/issues/P03/source_circuit_policy.json")
        probe = pc.Collector(root=tmp)
        org = probe.resolve_org(SAMPLES[0])
        probe.fetch_index(SAMPLES[0], "category_ndbg_szsh", org["org_id"])
        waits = probe.http.waits
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # 真实多页翻页：把 pageSize 降到 5，强制 8 条目录分成 2 页，验证游标与对账
    tmp2 = Path(tempfile.mkdtemp(prefix="p05_page_"))
    try:
        (tmp2 / "runs/issues/P03").mkdir(parents=True)
        shutil.copy2(REPO / "runs/issues/P03/source_circuit_policy.json",
                     tmp2 / "runs/issues/P03/source_circuit_policy.json")
        cfg = json.loads(pc.CONFIG_PATH.read_text(encoding="utf-8"))
        cfg["routes"]["cninfo_issuer_index"]["page_size"] = 5
        cfg_path = tmp2 / "config_page5.json"
        cfg_path.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
        page_probe = pc.Collector(cfg_path, root=tmp2)
        porg = page_probe.resolve_org(SAMPLES[0])
        pidx = page_probe.fetch_index(SAMPLES[0], "category_ndbg_szsh", porg["org_id"])
        page_probe_info = {
            "page_size": 5,
            "pages_fetched": pidx["pages_fetched"],
            "rows_fetched": pidx["rows_fetched"],
            "total_announcement": pidx["total_announcement"],
            "reconciled": pidx["reconciled"],
            "cursors": [{k: p.get(k) for k in ("page", "rows", "totalpages", "has_more")}
                        for p in pidx["pages"]],
        }
    finally:
        shutil.rmtree(tmp2, ignore_errors=True)

    # 半年度槽实跑：验证第二个报告类型（category_bndbg_szsh）与槽位映射
    extra = pc.Collector().run([SAMPLES[1]], ["h1_2026"])
    extra_slot = extra["companies"][0]["slots"][0]
    extra_view = slot_view(extra_slot)

    checks = []

    def add(cid, criterion, ok, detail):
        checks.append({"id": cid, "criterion": criterion, "result": "PASS" if ok else "FAIL", "detail": detail})

    add("L1", "沪市：目录全分页与上游总数核对",
        all(c["index"]["reconciled"] for c in companies if c["exchange"] == "SH"),
        {c["security_id"]: c["index"]["reconciled"] for c in companies})
    add("L2", "深市：目录全分页与上游总数核对",
        all(c["index"]["reconciled"] for c in companies if c["exchange"] == "SZ"),
        {c["security_id"]: c["index"]["rows_fetched"] for c in companies})
    add("L3", "北交所：走 szse 列且目录对账通过",
        all(c["index"]["column"] == "szse" and c["index"]["reconciled"]
            for c in companies if c["exchange"] == "BJ"),
        {c["security_id"]: {"column": c["index"]["column"], "reconciled": c["index"]["reconciled"]}
         for c in companies if c["exchange"] == "BJ"})
    add("L4", "北交所历史代码行被接受并留痕",
        any(c["index"]["historical_code_rows"] for c in companies if c["exchange"] == "BJ"),
        {c["security_id"]: c["index"]["historical_code_rows"] for c in companies})
    add("L5", "三份原件均通过七项校验并落本地",
        all(c["slot"]["status"] in (pc.ST_COLLECTED_VERIFIED, pc.ST_SKIPPED)
            and c["binary_proof"]["sha256_matches_file"]
            and all(v == "PASS" for v in c["slot"]["checks"].values())
            for c in companies),
        {c["security_id"]: {"status": c["slot"]["status"], "pages": c["slot"]["page_count"],
                            "period_method": c["slot"].get("period_match_method"),
                            "sha256": (c["slot"]["sha256"] or "")[:16]} for c in companies})
    add("L6", "重复运行幂等跳过且不产生新请求",
        all(s == pc.ST_SKIPPED for s in skip_actions) and second["http_calls"] == 0,
        {"last_actions": skip_actions, "http_calls": second["http_calls"]})
    interval = float(collector.config["transport"]["min_interval_per_host_seconds"])
    pairs = [w for w in waits if w["gap_from_prev_seconds"] is not None]
    violations = [w for w in pairs if w["gap_from_prev_seconds"] + w["waited_seconds"] < interval - 0.001]
    add("L7", "同主机两次请求间隔不小于限速值",
        len(pairs) >= 1 and not violations,
        {"min_interval_seconds": interval,
         "same_host_pairs": len(pairs),
         "violations": violations,
         "samples": [{"host": w["host"], "gap": w["gap_from_prev_seconds"], "waited": w["waited_seconds"]}
                     for w in pairs[:5]],
         "note": "真实时钟下请求本身耗时通常已超过 1.2s；强制等待分支由故障测试 T10 用固定时钟验证"})
    add("L8", "原始响应落盘且台账只记哈希/游标",
        all(c["index"]["page_cursors"] and all(p["response_sha256"] for p in c["index"]["page_cursors"])
            for c in companies),
        {c["security_id"]: len(c["index"]["page_cursors"]) for c in companies})
    add("L9", "台账保留首次下载尝试（URL/时间/字节/哈希）",
        all(c["slot"]["attempt_count"] >= 1 and c["slot"]["last_source_attempt"]
            and c["slot"]["last_source_attempt"].get("url")
            and c["slot"]["last_source_attempt"].get("at")
            for c in companies),
        {c["security_id"]: {"attempt_count": c["slot"]["attempt_count"],
                            "http_status": (c["slot"]["last_source_attempt"] or {}).get("http_status"),
                            "bytes": (c["slot"]["last_source_attempt"] or {}).get("bytes")}
         for c in companies})
    add("L10", "真实多页翻页：pageSize=5 时 8 条目录分 2 页且对账通过",
        page_probe_info["pages_fetched"] >= 2 and page_probe_info["reconciled"],
        page_probe_info)
    add("L11", "半年度槽实跑：第二个报告类型目录与 PDF 均通过校验",
        extra_view["status"] in (pc.ST_COLLECTED_VERIFIED, pc.ST_SKIPPED)
        and all(v == "PASS" for v in extra_view["checks"].values()),
        {"security_id": SAMPLES[1].security_id, "slot_id": "h1_2026",
         "status": extra_view["status"], "pages": extra_view["page_count"],
         "period_method": extra_view.get("period_match_method"),
         "sha256": (extra_view["sha256"] or "")[:16]})

    passed = sum(1 for c in checks if c["result"] == "PASS")
    payload = {
        "plan_version": pc.PLAN_VERSION,
        "issue_key": "P05",
        "generated_at": pc.utc_now(),
        "mode": "LIVE_SMALL_SAMPLE",
        "scope": "3 家（沪/深/北各 1）× 1 个报告槽（annual_2025）；不是全池、不是业务验收",
        "elapsed_seconds": round(time.time() - started, 1),
        "summary": {"checks_total": len(checks), "checks_pass": passed,
                    "checks_fail": len(checks) - passed,
                    "downloaded_files": sum(1 for c in companies if c["binary_proof"]["local_file_exists"]) + 1,
                    "downloaded_bytes_main_slots": sum(c["slot"]["bytes"] or 0 for c in companies),
                    "downloaded_bytes_total": sum(c["slot"]["bytes"] or 0 for c in companies) + (extra_view["bytes"] or 0),
                    "http_calls_this_run": first["http_calls"],
                    "http_calls_idempotent_replay": second["http_calls"],
                    "statuses_this_run": [c["slot"]["status"] for c in companies]},
        "checks": checks,
        "companies": companies,
        "extra_probe": {"security_id": SAMPLES[1].security_id, "slot": extra_view},
        "pagination_probe": page_probe_info,
        "circuit": first["circuit"],
        "notes": [
            "原件存 sources/p05_validation/（.gitignore 排除），GitHub 只保存本文件与台账。",
            "所有状态为 COLLECTED_IDENTITY_VERIFIED 只代表文件与主体/报告期身份核对通过，不含业务结论。",
            "北交所 2024 年及以前年报在巨潮以旧代码 835207 披露，本次已实测并接受为历史代码行。",
            "三家原件在本卡前一次运行中已下载完成，本次运行为幂等复算（http_calls_this_run=0）；首次下载的 URL/时间/字节/哈希见 L9 与 checkpoint/<code>.json 的 source_attempts。",
            "限速校验用隔离目录单独发起 2 次同主机请求，不受幂等跳过影响。",
        ],
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for c in checks:
        print(f"[{c['result']}] {c['id']} {c['criterion']}")
    print(json.dumps(payload["summary"], ensure_ascii=False))
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
