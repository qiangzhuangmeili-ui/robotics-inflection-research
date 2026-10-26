"""M00 批次完成后的状态发布：只改状态源，不碰采集结果。

用法：python tools/m00_publish.py --batch M00_01

更新范围：
1. data/issue_execution_plan.csv：本批 SELF_CHECK_PASS，下一批 READY
2. data/issue_execution_plan.json：next_recommended_issue / execution_started
3. PROJECT_STATE.json：status、issue_plan.last_completed_issue、m00_batches
4. data/active_issue.json：清空活跃卡、写 last_completed 与下一张建议

不修改任何原始输入（company_master / document_registry / intake 队列）。
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLAN_CSV = ROOT / "data/issue_execution_plan.csv"
PLAN_JSON = ROOT / "data/issue_execution_plan.json"
STATE = ROOT / "PROJECT_STATE.json"
ACTIVE = ROOT / "data/active_issue.json"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_csv(path: Path) -> tuple[list[str], list[dict]]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        return list(reader.fieldnames or []), list(reader)


def write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def publish(batch: str) -> dict:
    out = ROOT / "runs/issues" / batch
    review = read_json(out / "review.json")
    checkpoint = read_json(out / "checkpoint.json")
    run = read_json(out / "run_result.json")
    freeze_info = read_json(out / "assignment_freeze.json")
    summary = review["coverage_summary"]

    fields, rows = read_csv(PLAN_CSV)
    order = [r["key"] for r in rows]
    idx = order.index(batch)
    rows[idx]["status"] = review["decision"]
    next_key = order[idx + 1] if idx + 1 < len(order) else None
    next_number = None
    if next_key:
        if rows[idx + 1]["status"] == "WAITING_DEPENDENCIES" and rows[idx + 1]["dependency_keys"] == batch:
            rows[idx + 1]["status"] = "READY"
        next_number = int(rows[idx + 1]["issue_number"])
    write_csv(PLAN_CSV, fields, rows)

    plan_json = read_json(PLAN_JSON)
    plan_json["execution_started"] = True
    if next_number:
        plan_json["next_recommended_issue"] = next_number
    write_json(PLAN_JSON, plan_json)

    state = read_json(STATE)
    state["status"] = f"{batch}_{review['decision']}"
    state.setdefault("issue_plan", {})
    state["issue_plan"]["last_completed_issue"] = {
        "issue_number": freeze_info["issue_number"],
        "issue_key": batch,
        "completed_at": checkpoint["updated_at"],
        "review_file": f"runs/issues/{batch}/review.json",
        "decision": review["decision"],
        "acceptance": f"{sum(1 for a in review['acceptance'] if a['result'] == 'PASS')}/{len(review['acceptance'])}",
        "slot_total": summary["slot_total"],
        "obtained": summary["obtained"],
        "companies": checkpoint["companies_total"],
        "allows_next_stage_scope": review["allows_next_stage_scope"],
    }
    if next_number:
        state["issue_plan"]["next_recommended_issue"] = (
            f"https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/{next_number}")
    state.setdefault("m00_batches", {})[batch] = {
        "issue_number": freeze_info["issue_number"],
        "companies": freeze_info["company_count"],
        "slots_per_company": len(freeze_info["planned_slots"]),
        "slot_total": summary["slot_total"],
        "status_counts": summary["status_counts"],
        "obtained": summary["obtained"],
        "bytes": sum(int(r["bytes"]) for r in csv.DictReader(
            (out / "coverage.csv").open(encoding="utf-8-sig")) if str(r["bytes"]).isdigit()),
        "assignment_sha256": freeze_info["assignment_sha256"],
        "elapsed_seconds": run.get("elapsed_seconds"),
        "review_nature": review["review_nature"],
        "drive": "NOT_ARCHIVED_NO_DRIVE_CONNECTOR",
    }
    write_json(STATE, state)

    active = read_json(ACTIVE)
    active["active_issue_number"] = None
    active["active_issue_key"] = None
    active["executor"] = None
    active["started_at"] = None
    active["status"] = f"IDLE_{batch}_{review['decision']}"
    active["claim_note"] = (
        f"{batch} 已完成：{checkpoint['companies_total']} 家 × {len(freeze_info['planned_slots'])} 槽 = "
        f"{summary['slot_total']} 槽，取得 {summary['obtained']}；原件落 D 盘，Drive 未连接不写 VERIFIED。"
    )
    active["last_completed"] = {
        "issue_number": freeze_info["issue_number"],
        "issue_key": batch,
        "completed_at": checkpoint["updated_at"],
        "review_file": f"runs/issues/{batch}/review.json",
        "decision": review["decision"],
        "acceptance": f"{sum(1 for a in review['acceptance'] if a['result'] == 'PASS')}/{len(review['acceptance'])}",
        "self_check": f"{summary['slot_total']} 槽逐槽有状态，取得 {summary['obtained']}",
    }
    if next_number:
        active["next_recommended_issue_number"] = next_number
        active["next_recommended_issue_key"] = next_key
        active["next_recommended_reason"] = (
            f"{batch} 自检通过；{next_key} 依赖已满足。沿用同一台账与配置，名单取 "
            f"data/intake_batches/{next_key}/assignment.csv。")
    write_json(ACTIVE, active)
    return {"batch": batch, "decision": review["decision"], "next": next_key,
            "slot_total": summary["slot_total"], "obtained": summary["obtained"]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="M00 批次状态发布")
    parser.add_argument("--batch", required=True)
    args = parser.parse_args(argv)
    print(json.dumps(publish(args.batch), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
