#!/usr/bin/env python
"""A04R 收口：把季度补采与公告目录结果写成 review.json / handoff.md / manifest.json。

只读共享台账与 A04R 产物，不改任何原始输入。判定标准全部来自 P00 冻结规则：
- 12 个报告槽 × 1054 家 = 12648 个 (security_id, slot_id) 必须有且仅有一个终态；
- NOT_TRIED = 0；
- 公告/IR 目录 1054/1054 覆盖且分页累计 == totalAnnouncement。
"""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs/issues/A04R"
TARGET = ["q1_2024", "q3_2024", "q1_2025", "q3_2025", "q3_2026"]


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def rows(rel: str) -> list[dict]:
    with (ROOT / rel).open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def main() -> int:
    scope = json.loads((ROOT / "runs/issues/P00/collection_scope.json").read_text(encoding="utf-8"))
    slots = [s["slot_id"] for s in scope["report_slots"] + scope["quarterly_slots"]]
    master = rows("data/company_master.csv")
    ids = {r["security_id"] for r in master}
    ledger = rows("runs/collection/collection_index.csv")
    pairs = Counter((r["security_id"], r["slot_id"]) for r in ledger)
    by_slot = defaultdict(list)
    for r in ledger:
        by_slot[r["slot_id"]].append(r)

    coverage = []
    for s in slots:
        rr = by_slot.get(s, [])
        c = Counter(r["status"] for r in rr)
        present = {r["security_id"] for r in rr}
        coverage.append({
            "slot_id": s, "ledger_rows": len(rr), "absent": len(ids - present),
            "verified": c.get("COLLECTED_IDENTITY_VERIFIED", 0),
            "pending_identity": c.get("COLLECTED_PENDING_IDENTITY", 0),
            "na_pre_listing": c.get("NOT_APPLICABLE_PRE_LISTING", 0),
            "not_disclosed": c.get("NOT_DISCLOSED_BY_ISSUER", 0),
            "not_yet_disclosed": c.get("NOT_YET_DISCLOSED", 0),
            "after_cutoff": c.get("AFTER_CUTOFF_DISCLOSED", 0),
            "source_failed": c.get("SOURCE_FAILED", 0),
            "not_tried": c.get("NOT_TRIED", 0),
        })
    with (OUT / "slot_coverage_final.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(coverage[0].keys()))
        w.writeheader()
        w.writerows(coverage)

    absent = sum(c["absent"] for c in coverage)
    not_tried = sum(c["not_tried"] for c in coverage)
    dup = sum(1 for v in pairs.values() if v > 1)
    status = Counter(r["status"] for r in ledger)

    ann = []
    ann_path = OUT / "announcement_index.jsonl"
    if ann_path.exists():
        for line in ann_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                ann.append(json.loads(line))
    ann_codes = {a["stock_code"] for a in ann}
    ann_ok = sum(1 for a in ann if a["reconciled"])
    hits = sum(len(a["keyword_hits"]) for a in ann)
    revs = sum(len(a["revision_rows"]) for a in ann)
    irs = sum(len(a["ir_rows"]) for a in ann)
    rev_bd = {}
    rev_path = OUT / "revision_chain_breakdown.json"
    if rev_path.exists():
        rev_bd = json.loads(rev_path.read_text(encoding="utf-8"))
    chain = {}
    chain_path = OUT / "correction_chains.json"
    if chain_path.exists():
        chain = json.loads(chain_path.read_text(encoding="utf-8"))
    hit_dl = 0
    hit_manifest = OUT / "keyword_originals.jsonl"
    if hit_manifest.exists():
        hit_dl = sum(1 for line in hit_manifest.read_text(encoding="utf-8").splitlines()
                     if line.strip() and json.loads(line).get("status") == "DOWNLOADED")

    cutoff = scope["time_axis"]["knowledge_as_of"]
    late_used = [{"security_id": r["security_id"], "slot_id": r["slot_id"], "published_on": r["published_on"]}
                 for r in ledger
                 if str(r["status"]).startswith("COLLECTED") and r["published_on"]
                 and r["published_on"] > cutoff]
    checks = [
        {"id": "AC04", "item": "12 槽 × 1054 家全部有且仅有一个终态（NOT_TRIED 不算终态）",
         "result": "PASS" if absent == 0 and dup == 0 and not_tried == 0 else "FAIL",
         "evidence": {"expected_pairs": len(slots) * len(ids), "ledger_pairs": len(pairs),
                      "absent": absent, "duplicate": dup, "not_tried": not_tried}},
        {"id": "AC05", "item": "NOT_TRIED = 0",
         "result": "PASS" if not_tried == 0 else "FAIL",
         "evidence": {"not_tried": not_tried,
                      "by_slot": {c["slot_id"]: c["not_tried"] for c in coverage if c["not_tried"]}}},
        {"id": "AC10", "item": "截止日后披露不作为本轮证据",
         "result": "PASS" if not late_used else "FAIL",
         "evidence": {"collected_rows_with_publish_after_cutoff": len(late_used),
                      "late_samples": late_used[:5],
                      "after_cutoff_registered": status.get("AFTER_CUTOFF_DISCLOSED", 0),
                      "cutoff": scope["time_axis"]["knowledge_as_of"]}},
        {"id": "AC11", "item": "近两年公告/IR 目录全池覆盖且分页对账",
         "result": "PASS" if len(ann_codes) == len(ids) and ann_ok == len(ids) else "FAIL",
         "evidence": {"companies": len(ids), "companies_with_index": len(ann_codes),
                      "reconciled": ann_ok, "keyword_hits": hits,
                      "keyword_originals_downloaded": hit_dl,
                      "revision_rows": revs, "ir_rows": irs}},
    ]
    passed = all(c["result"] == "PASS" for c in checks)
    decision = "SELF_CHECK_PASS" if passed else "SELF_CHECK_INCOMPLETE"

    review = {
        "issue_key": "A04R", "issue_number": 50,
        "plan_version": scope["plan_version"],
        "executor": "WorkBuddy AI", "reviewer": "WorkBuddy AI",
        "review_nature": "SELF_CHECK",
        "reviewed_at": datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds"),
        "decision": decision,
        "checks": checks,
        "coverage": coverage,
        "status_counts": dict(status),
        "limits": [
            "本卡只做采集与文件身份校验，不做财务精读、不做业务结论、不估值。",
            "自检由执行者本人完成，不等于独立审计。",
            "关键词命中只用于取件排序，不构成机器人业务证据。",
            "Drive 无真实上传与回读回执，archive_status 不写 VERIFIED，本地原件保留。",
            "COLLECTED_PENDING_IDENTITY 为正文抽取不足（图片版/字形贴片），待人工看封面。",
        ],
        "allows_next_stage_scope": "放行 A04 复验；不放行业务结论/指标筛选/估值",
    }
    (OUT / "review.json").write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    total_bytes = sum(int(r["bytes"]) for r in ledger if str(r["bytes"]).isdigit())
    lines = [
        "# A04R 交接：冻结范围补齐采集（A04 返工专用卡）",
        "",
        f"- **issue**：#{50} / A04R，plan_version `{scope['plan_version']}`",
        "- **执行者/自检者**：WorkBuddy AI（`review_nature=SELF_CHECK`，不冒充独立审计）",
        f"- **结论**：`{decision}`",
        "- **本卡不做**：财务精读、业务结论、指标筛选、估值、Drive 归档核验",
        "",
        "## 一、报告槽终态",
        "",
        f"12 槽 × 1054 家 = **{len(slots) * len(ids)}** 个 (security_id, slot_id)："
        f"台账 {len(pairs)} 条，缺失 {absent}，重复 {dup}，NOT_TRIED {not_tried}。",
        "",
        "| 槽位 | 台账行 | 缺失 | 已核 | 待核 | 上市前不适用 | 未披露 | 未到期 | 截止日后 | 失败 | 未尝试 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for c in coverage:
        lines.append(f"| {c['slot_id']} | {c['ledger_rows']} | {c['absent']} | {c['verified']} | "
                     f"{c['pending_identity']} | {c['na_pre_listing']} | {c['not_disclosed']} | "
                     f"{c['not_yet_disclosed']} | {c['after_cutoff']} | {c['source_failed']} | {c['not_tried']} |")
    lines += [
        "",
        "## 二、q3_2026 截止日判定",
        "",
        f"研究截止日 `{scope['time_axis']['knowledge_as_of']}`；q3_2026 法定披露期 2026-10-31 晚于截止日。"
        f"逐项判定结果：已核 {by_slot_q3(by_slot, 'COLLECTED_IDENTITY_VERIFIED')}、"
        f"截止日后登记 {by_slot_q3(by_slot, 'AFTER_CUTOFF_DISCLOSED')}、"
        f"未到期 {by_slot_q3(by_slot, 'NOT_YET_DISCLOSED')}。"
        "截止日后披露的文件只登记为增量候选，未计入本轮证据。",
        "",
        "## 三、公告/IR 目录与关键词",
        "",
        f"- 覆盖公司 {len(ann_codes)}/1054，分页对账通过 {ann_ok}/1054（累计行数 == totalAnnouncement）。",
        f"- 关键词命中行 {hits}，已下载原件 {hit_dl}；更正/修订行 {revs}；IR 类行 {irs}。",
        (f"- 更正/修订拆分：财务更正或重述 {rev_bd.get('financial_correction_or_restatement')}、"
         f"交易文件修订稿 {rev_bd.get('transaction_document_revision')}、其他补充 {rev_bd.get('other_revision_supplement')}；"
         "「修订稿」不是财务重述，引用时不得混算。" if rev_bd else "- 更正/修订拆分：未生成。"),
        "- 关键词只用于取件排序，不作为机器人业务证据；未命中不等于无业务。",
        "",
        "## 三之二、复核后的两项补充",
        "",
        "- **北交所适用性改用真实股转挂牌日**：15 家挂牌日取自本地年报「挂牌时间」页"
        "（`runs/issues/A04R/neeq_listing_dates.json`），50 槽重判后不适用 12→8、未披露 34→38，"
        "4 槽由「不适用」改判「未披露」。原「最早定期报告披露日」推断已废弃。",
        (f"- **财务更正版本链**：{chain.get('pairs', 0)} 组原版—更正版（或更正公告）闭环，"
         f"缺口 {len(chain.get('gap_rows', []))}；发现规则已并入「修订版/修订公告」，"
         f"财务更正行 {rev_bd.get('financial_correction_or_restatement', 'NA')} 条"
         f"（v3 口径，剔除预案/股东大会/摘要等非财报更正）。"
         if chain else "- **财务更正版本链**：未生成。"),
        "",
        "## 四、限制与未解决",
        "",
        "- 全局来源故障仍回 P03；本卡未把任何未尝试项写成缺件。",
        "- 北交所挂牌期季度槽另按股转索引判定，证据单独落盘。",
        "- 原件在 D 盘 `sources/collection/originals`，Drive 未归档不写 VERIFIED。",
        "",
        "## 五、复算",
        "",
        "```bash",
        "python tools/a04r_scope_backfill.py --dry-run      # 待补槽统计",
        "python tools/a04r_announcement_index.py --resume   # 公告目录续跑",
        "python tools/a04r_finalize.py                      # 重写本卡 review/handoff/manifest",
        "```",
    ]
    (OUT / "handoff.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    files = []
    for name in ["card.json", "progress.json", "run_result.json", "announcement_index.jsonl",
                 "keyword_originals.jsonl", "slot_coverage_final.csv", "review.json", "handoff.md"]:
        p = OUT / name
        if p.exists():
            files.append({"path": p.relative_to(ROOT).as_posix(), "bytes": p.stat().st_size, "sha256": sha(p)})
    manifest = {
        "issue_key": "A04R", "issue_number": 50,
        "generated_at": datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds"),
        "review_nature": "SELF_CHECK",
        "files": files,
        "inputs": {
            "runs/collection/collection_index.csv": sha(ROOT / "runs/collection/collection_index.csv"),
            "runs/issues/P00/collection_scope.json": sha(ROOT / "runs/issues/P00/collection_scope.json"),
            "runs/issues/A01/collection_config_v2.json": sha(ROOT / "runs/issues/A01/collection_config_v2.json"),
            "data/company_master.csv": sha(ROOT / "data/company_master.csv"),
            "data/company_listing_dates.csv": sha(ROOT / "data/company_listing_dates.csv"),
        },
        "bytes_total_originals": total_bytes,
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"decision": decision, "checks": {c["id"]: c["result"] for c in checks},
                      "absent": absent, "not_tried": not_tried, "pairs": len(pairs)}, ensure_ascii=False, indent=1))
    return 0


def by_slot_q3(by_slot, status: str) -> int:
    return sum(1 for r in by_slot.get("q3_2026", []) if r["status"] == status)


if __name__ == "__main__":
    raise SystemExit(main())
