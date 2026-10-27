#!/usr/bin/env python
"""A04R 冻结范围补齐采集：4 类到期季度槽 + q3_2026 逐项截止日登记。

背景：A04 首次验收（RETURN_FOR_REWORK）发现 P00 冻结的 12 个报告槽里，实际采集只落实了
6 个核心槽 + q1_2026，另有 q1_2024 / q3_2024 / q1_2025 / q3_2025 共 4216 个到期季度槽
和 q3_2026 的 1054 个截止日待判定槽没有终态记录。

本工具不新建采集器、不改 P05 冻结参数，只做三件事：
1. 复用共享台账（runs/collection/checkpoint）与已取得原件，已是终态的不再发请求；
2. 对缺失的季度槽调用现有 Collector 的 collect_company（季度 PDF 走 include_optional_pdf）；
3. q3_2026 不做一刀切：法定披露期 2026-10-31 晚于研究截止日 2026-10-25，
   目录有行且披露日 <= 截止日 → 正常取件；披露日 > 截止日 → AFTER_CUTOFF_DISCLOSED；
   目录无行 → NOT_YET_DISCLOSED（由 Collector 的 _no_row_status 判定）。

断点续跑：每完成一家写 runs/issues/A04R/progress.json；中断后重跑自动跳过已终态槽。
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import m00_batch as M00  # noqa: E402
import p05_collector as P05  # noqa: E402

CONFIG_PATH = ROOT / "runs/issues/A01/collection_config_v2.json"
OUT_DIR = ROOT / "runs/issues/A04R"
PROGRESS = OUT_DIR / "progress.json"

TARGET_SLOTS = ["q1_2024", "q3_2024", "q1_2025", "q3_2025", "q3_2026"]

# 本轮回填视为“已可不再请求”的状态（NOT_TRIED / SOURCE_FAILED 仍要重试一次）
SETTLED = {
    P05.ST_COLLECTED_VERIFIED, P05.ST_COLLECTED_PENDING, P05.ST_SKIPPED,
    P05.ST_NOT_APPLICABLE, P05.ST_NOT_DISCLOSED, P05.ST_NOT_YET_DISCLOSED,
    P05.ST_AFTER_CUTOFF, P05.ST_DUPLICATE, P05.ST_SUMMARY_ONLY,
}


def read_csv(path: Path) -> list[dict]:
    with Path(path).open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def companies() -> list[P05.CompanyRef]:
    dates = M00.listing_date_map()
    refs = []
    for row in read_csv(ROOT / "data/company_master.csv"):
        refs.append(P05.CompanyRef(
            security_id=row["security_id"], stock_code=row["stock_code"],
            stock_name=row["stock_name"], exchange=row["security_id"].split(":")[0],
            listing_date=dates.get(row["security_id"]) or None,
        ))
    return refs


def ledger_status(collector: P05.Collector, security_id: str, slot_id: str) -> str:
    rec = collector.ledger.slot(security_id, "", slot_id) or {}
    return rec.get("status") or ""


def pending_slots(collector: P05.Collector, company: P05.CompanyRef) -> list[str]:
    out = []
    for slot_id in TARGET_SLOTS:
        rec = collector.ledger.slot(company.security_id, company.stock_code, slot_id) or {}
        status = rec.get("status")
        if status in SETTLED:
            continue
        if status == P05.ST_SOURCE_FAILED and int(rec.get("attempt_count") or 0) >= 3:
            continue
        out.append(slot_id)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--code", action="append", default=None, help="只跑指定股票代码，可多次")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    refs = companies()
    if args.code:
        want = set(args.code)
        refs = [c for c in refs if c.stock_code in want]
    if args.limit:
        refs = refs[: args.limit]

    collector = P05.Collector(config_path=CONFIG_PATH, root=ROOT)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    progress = json.loads(PROGRESS.read_text(encoding="utf-8")) if PROGRESS.exists() else {}
    done: dict[str, dict] = progress.get("companies", {})
    errors: list[dict] = progress.get("company_errors", [])

    todo = [(c, pending_slots(collector, c)) for c in refs]
    todo = [(c, s) for c, s in todo if s]
    print(f"目标公司 {len(refs)}，待补槽公司 {len(todo)}，待补槽位 {sum(len(s) for _, s in todo)}", flush=True)
    if args.dry_run:
        for c, s in todo[:20]:
            print(" ", c.stock_code, c.stock_name, s)
        return 0

    t0 = time.time()
    cooldown = float(json.loads(CONFIG_PATH.read_text(encoding="utf-8"))["transport"].get("cooldown_seconds")
                     or collector.http.policy["cooldown_seconds"])
    circuit_waits = 0
    for idx, (company, slots) in enumerate(todo, 1):
        t1 = time.time()
        attempt = 0
        while True:
            attempt += 1
            try:
                res = collector.collect_company(company, slots, include_optional_pdf=True)
            except Exception as exc:  # 一家异常不拖垮整轮
                errors.append({"security_id": company.security_id, "stock_code": company.stock_code,
                               "error": f"{type(exc).__name__}: {exc}", "at": P05.utc_now()})
                print(f"[{idx}/{len(todo)}] {company.stock_code} ERROR {type(exc).__name__}: {exc}", flush=True)
                res = None
                break
            # 熔断一旦打开，P05 的 Circuit.allow 在本进程内不会自动恢复（需 half-open 已知良好探针）。
            # 这里按 policy 冷却到期后重置状态再重试同一家，等价于把该次请求当作探针。
            opened = [v["opened_at"] for v in collector.http.circuit_snapshot().values() if v["opened_at"]]
            bad = [s for s in res["slots"] if s["status"] in (P05.ST_NOT_TRIED, P05.ST_ACCESS_BLOCKED)]
            if bad and opened and circuit_waits < 5:
                wait = max(5.0, cooldown - (time.time() - max(opened)) + 5)
                circuit_waits += 1
                print(f"[{idx}/{len(todo)}] {company.stock_code} 源熔断，冷却 {wait:.0f}s 后重试"
                      f"（第 {circuit_waits}/5 次）", flush=True)
                time.sleep(wait)
                collector.http.states.clear()
                continue
            break
        if res is None:
            continue
        counts: dict[str, int] = {}
        for slot in res["slots"]:
            counts[slot["status"]] = counts.get(slot["status"], 0) + 1
        done[company.security_id] = {"stock_code": company.stock_code, "slots": slots,
                                     "counts": counts, "at": P05.utc_now()}
        print(f"[{idx}/{len(todo)}] {company.stock_code} {company.stock_name} "
              f"{len(slots)}槽 {counts} {time.time() - t1:.1f}s 累计{time.time() - t0:.0f}s", flush=True)
        if idx % 5 == 0 or idx == len(todo):
            PROGRESS.write_text(json.dumps({
                "scope": "A04R_FROZEN_SCOPE_BACKFILL", "config": CONFIG_PATH.relative_to(ROOT).as_posix(),
                "target_slots": TARGET_SLOTS, "updated_at": P05.utc_now(),
                "companies_total": len(todo), "companies_done": len(done),
                "company_errors": errors, "companies": done,
            }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    M00.write_shared_index()
    collector.flush_events()
    payload = {
        "scope": "A04R_FROZEN_SCOPE_BACKFILL", "config": CONFIG_PATH.relative_to(ROOT).as_posix(),
        "target_slots": TARGET_SLOTS, "finished_at": P05.utc_now(),
        "elapsed_seconds": round(time.time() - t0, 1),
        "companies_total": len(todo), "companies_done": len(done),
        "company_errors": errors, "http_calls": len(collector.http.calls),
        "companies": done,
    }
    (OUT_DIR / "run_result.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                                             encoding="utf-8")
    print(f"DONE {len(done)}/{len(todo)} errors={len(errors)} {time.time() - t0:.0f}s", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
