"""A04 返工复验收口：把 rework/ 下的复算结果写成 review.json / handoff.md / manifest.json。

不改写首次验收产物（runs/issues/A04/review.json、intake_acceptance.json 等保持不变）。
"""
from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def load(name: str) -> dict:
    return json.loads((OUT / name).read_text(encoding="utf-8"))


checks = load("checks.json")["checks"]
summary = load("rework_summary.json")
field = load("field_denominators.json")
sup = load("supplementary_scope_summary.json")
cutoff = load("cutoff_hold_resolution.json")
erratum = load("handoff_correction.json")
existing = load("existing_assets_check.json")
chain_path = ROOT / "runs/issues/A04R/correction_chains.json"
chain = json.loads(chain_path.read_text(encoding="utf-8")) if chain_path.exists() else {}
chain_pairs = chain.get("pairs", 0)
chain_complete = chain.get("complete", 0)
chain_gaps = chain.get("gap_rows", [])
notice_only = sum(1 for r in chain.get("rows", []) if r.get("corrected_full_text_missing"))
coverage = list(csv.DictReader((OUT / "frozen_scope_coverage.csv").open(encoding="utf-8-sig")))

by_id = {c["id"]: c for c in checks}
required = ["AC01", "AC02", "AC03", "AC04", "AC05", "AC06", "AC07", "AC08", "AC09", "AC10",
            "AC11_SUPPLEMENTARY", "AC12_CORRECTION_CHAIN"]
results = {c["id"]: c["result"] for c in checks}
failed = [k for k in required if results.get(k) != "PASS"]
if not failed:
    decision = "ACCEPTED_WITH_LIMITS"
    release = True
elif any(results.get(k) == "HOLD" for k in required):
    decision = "HOLD"
    release = False
else:
    decision = "RETURN_FOR_REWORK"
    release = False

now = datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")
review = {
    "issue_key": "A04", "issue_number": 34,
    "plan_version": "20261026_collection_first_v2",
    "review_round": "REWORK_20261027",
    "executor": "WorkBuddy AI", "reviewer": "WorkBuddy AI",
    "review_nature": "SELF_CHECK",
    "reviewed_at": now,
    "prior_review_preserved": "runs/issues/A04/review.json (RETURN_FOR_REWORK, 2026-10-27T20:30:41+08:00)",
    "decision": decision,
    "release_S00": release,
    "allows_next_stage": release,
    "checks": checks,
    "release_gate": {"required": required, "failed": failed,
                     "rule": "全部必需项 PASS 才放行；任一 FAIL/HOLD 均不放行"},
    "scope_reconciliation": {
        "frozen_slots": len(coverage),
        "frozen_pairs": len(coverage) * 1054,
        "ledger_pairs": summary["slots_with_terminal"] + summary["non_terminal_rows"],
        "absent_pairs": summary["absent_pairs"],
        "not_tried": summary["status_counts"].get("NOT_TRIED", 0),
        "status_counts": summary["status_counts"],
    },
    "field_layer": {
        "diagnostic_documents": field["diagnostic_documents"],
        "documents_with_field_rows": field["documents_with_field_rows"],
        "difference": field["difference"],
        "difference_documents": field["difference_documents"],
        "extracted_pairs": field["extracted_pairs"],
        "rate_field_rows_denominator": field["rate_field_rows_denominator"],
        "rate_diagnostic_denominator": field["rate_diagnostic_denominator"],
        "four_quarter_completeness": field["four_quarter_completeness"],
        "unit_consistency": field["unit_consistency"],
        "missing_not_zero_filled": field["missing_not_zero_filled"],
        "crosscheck_documents": field["crosscheck_documents"],
    },
    "supplementary_scope": sup,
    "correction_chain": {"pairs": chain_pairs, "complete": chain_complete,
                         "gaps": len(chain_gaps), "notice_only": notice_only},
    "cutoff_hold": {"documents": cutoff["documents"],
                    "resolved_within_cutoff": cutoff["resolved_within_cutoff"],
                    "after_cutoff": cutoff["after_cutoff"],
                    "unresolved": cutoff["unresolved"]},
    "handoff_correction": erratum["actual"],
    "existing_assets": existing["decision"],
    "limits": [
        "本结论为 SELF_CHECK：执行者与自检者为同一主体，不是独立审计。",
        "字段层只覆盖年报（3081 份有字段行）；半年报与季报字段未抽取，仍为缺口。",
        "1528 条字段待办（960 重述待复核 + 568 未抽取）保留；119 份交叉校验不匹配、54 份单位不一致保留 HOLD。",
        "EXTRACTED_ANY 只代表抽到至少一个期次值，不代表四季齐全；缺失一律不填 0。",
        "Drive 无真实上传与回读回执，archive_status 不写 VERIFIED；本地原件保留在 D 盘。",
        "公告目录只证明目录覆盖，不等于逐份原文已读；关键词命中不作为机器人业务证据。",
        "7162 份台账文档未进 document_registry、71 同件双 ID、3 同槽异 binary 等版本限制继续保留。",
    ],
    "next": ("放行 S00（标准化全池财务，保留原值/单位/版本），不得直接跳业务深研或估值；"
             if release else "继续修复未通过项后再复验；S00 保持 WAITING_DEPENDENCIES。"),
}
(OUT / "review.json").write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

lines = [
    "# A04 返工复验交接（保留首次验收报告）",
    "",
    f"- **issue**：#34 / A04，plan_version `20261026_collection_first_v2`",
    "- **执行者/自检者**：WorkBuddy AI（`review_nature=SELF_CHECK`）",
    f"- **复验结论**：`{decision}`，`release_S00={str(release).lower()}`",
    "- **首次验收**：`runs/issues/A04/review.json`（RETURN_FOR_REWORK）原样保留，本目录为返工复验记录",
    "- **本轮不做**：业务结论、指标筛选、估值；不重置 M00/A00—A03 验收",
    "",
    "## 一、逐项修复",
    "",
    "| 退回项 | 处理 | 结果 |",
    "|---|---|---|",
    f"| 4216 个到期季度槽无终态 | A04R #50 自动补采 q1_2024/q3_2024/q1_2025/q3_2025（复用台账与目录缓存） | 见 AC04/AC05 |",
    f"| q3_2026 1054 槽未按截止日判定 | 逐项按披露日判定：≤2026-10-25 取件；>截止日登记 AFTER_CUTOFF；无行且未到期记 NOT_YET_DISCLOSED | 登记 {summary['after_cutoff_rows']} 条截止日后披露（不计本轮证据） |",
    f"| 公告/IR 目录无覆盖证据 | 全池两年目录补采 + 分页对账 + 关键词/更正行登记 | 覆盖 {sup['companies_with_index']}/1054，对账 {sup['pagination_reconciled']}/1054 |",
    f"| 7 份披露日 UNKNOWN | 用落盘官方目录原始响应补日期并做字节量级校验 | {cutoff['resolved_within_cutoff']}/{cutoff['documents']} 在截止日内 |",
    f"| 3082 vs 3081 分母 | 差额 1 份为图片版无文字层（{', '.join(field['difference_documents'])}） | 已说明，未填 0 |",
    f"| A03 handoff 计数 226 | 另存更正记录，不改原文件 | 实际 {erratum['actual']['rows']} 行 |",
    "",
    "### 复核后追加的三项修正（Codex 2026-10-28 复核）",
    "",
    f"1. **北交所不适用判定改用真实股转挂牌日**：原用「最早定期报告披露日」推断挂牌状态，已废弃。"
    f"15 家挂牌日从本地年报「挂牌时间」页逐家提取（`runs/issues/A04R/neeq_listing_dates.json`），"
    f"50 槽重判后：上市前不适用 12→8、自愿未披露 34→38，4 槽由「不适用」改判「未披露」"
    f"（920096 2024Q1、920211 2024Q3/2025Q1、920238 2025Q1）。",
    f"2. **AC06 与放行门槛**：AC06 改为逐行比较「报告期结束 < 实际挂牌日」（北交所用股转挂牌日、沪/深用交易所上市日），"
    f"当前 {by_id['AC06']['evidence']['na_rows']} 条不适用行、违规 0 条（明细 `na_applicability_audit.csv`）；"
    f"放行门槛改为 12 项全部必需，任一 FAIL/HOLD 均不放行（`release_gate`）。",
    f"3. **财务更正版本链**：{chain_pairs} 组原版—更正版（或更正公告）已闭环，"
    f"其中 {notice_only} 组公司只发更正公告未重发全文；每组含原版/更正版两个 document_id、supersedes 关联与本地 sha256"
    f"（`runs/issues/A04R/correction_chains.json`）。原「576 条财务更正」把发行预案、股东大会通知算进来，"
    f"已按「年度/半年度/季度报告 + 更正/重述/勘误」重算为 207 条。",
    "",
    "## 二、12 个冻结报告槽复算",
    "",
    "| 槽位 | 台账行 | 缺失 | 已核 | 待核 | 不适用 | 未披露 | 未到期 | 截止日后 | 失败 | 未尝试 |",
    "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
]
for c in coverage:
    lines.append(f"| {c['slot_id']} | {c['ledger_rows']} | {c['absent_from_ledger']} | "
                 f"{c['collected_identity_verified']} | {c['collected_pending_identity']} | "
                 f"{c['not_applicable_pre_listing']} | {c['not_disclosed_by_issuer']} | "
                 f"{c['not_yet_disclosed']} | {c['after_cutoff_disclosed']} | "
                 f"{c['source_failed']} | {c['not_tried']} |")
lines += [
    "",
    f"合计：12 × 1054 = **{len(coverage) * 1054}** 个 (security_id, slot_id)；"
    f"台账 {summary['slots_with_terminal'] + summary['non_terminal_rows']} 条，"
    f"缺失 {summary['absent_pairs']}，NOT_TRIED {summary['status_counts'].get('NOT_TRIED', 0)}。",
    "",
    "## 三、字段层",
    "",
    f"- 诊断文档 {field['diagnostic_documents']}，有字段行 {field['documents_with_field_rows']}，"
    f"差额 {field['difference']}（图片版无文字层，仍在诊断表留痕）。",
    f"- 16 字段 × {field['documents_with_field_rows']} = {field['field_pairs_field_rows_denominator']}；"
    f"已抽 {field['extracted_pairs']}（{field['rate_field_rows_denominator']:.2%}）。"
    f"若把图片版也放进分母（{field['field_pairs_diagnostic_denominator']}），"
    f"则为 {field['rate_diagnostic_denominator']:.2%}。",
    f"- 四季齐全：分季度加总≠年初至今的文档数 REV {field['four_quarter_completeness']['REV'].get('INCOMPLETE_QUARTERS', 0)}、"
    f"NPP {field['four_quarter_completeness']['NPP'].get('INCOMPLETE_QUARTERS', 0)}、"
    f"NPDEDT {field['four_quarter_completeness']['NPDEDT'].get('INCOMPLETE_QUARTERS', 0)}、"
    f"OCF {field['four_quarter_completeness']['OCF'].get('INCOMPLETE_QUARTERS', 0)}；"
    "因此「抽到任意季度值」不得当作四季齐全。",
    f"- 缺失未填 0：非 EXTRACTED 行带值 {field['non_extracted_rows_with_value']} 条；"
    f"单位一致 {field['unit_consistency'].get('YES', 0)}/不一致 {field['unit_consistency'].get('NO', 0)}；"
    f"交叉校验 {field['crosscheck_documents']}。",
    "",
    "## 四、补充材料",
    "",
    f"- 公告/IR 目录窗口 {sup['window']}，覆盖 {sup['companies_with_index']}/1054，"
    f"对账通过 {sup['pagination_reconciled']}，累计声明行 {sup['total_announcement_rows']}，"
    f"实取 {sup['rows_fetched']}。",
    f"- 关键词命中 {sup['keyword_hit_rows']} 行，已下载原件见 `runs/issues/A04R/keyword_originals.jsonl`；"
    f"更正/修订 {sup['revision_rows']} 行，IR 类 {sup['ir_rows']} 行。",
    f"- 存量资产核查：{existing['decision']}（旧库 {existing['existing_library']['registered_documents']} 份登记文档，无公告目录资产）。",
    "",
    "## 五、检查项",
    "",
    "| 检查 | 结果 |",
    "|---|---|",
]
for c in checks:
    lines.append(f"| {c['id']} | {c['result']} |")
lines += [
    "",
    "## 六、限制（必须随结论一起读）",
    "",
    *[f"- {x}" for x in review["limits"]],
    "",
    "## 七、复算",
    "",
    "```bash",
    "python runs/issues/A04/rework/audit_rework.py     # 重算本目录 checks/coverage/字段分母",
    "python runs/issues/A04/rework/finalize_rework.py  # 重写 review/handoff/manifest",
    "```",
]
(OUT / "handoff.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

files = []
for p in sorted(OUT.iterdir()):
    if p.is_file() and p.name != "manifest.json":
        files.append({"path": p.relative_to(ROOT).as_posix(), "bytes": p.stat().st_size, "sha256": sha(p)})
manifest = {
    "issue_key": "A04", "issue_number": 34, "review_round": "REWORK_20261027",
    "generated_at": now, "review_nature": "SELF_CHECK",
    "decision": decision, "release_S00": release,
    "files": files,
    "inputs": json.loads((OUT / "input_fingerprints.json").read_text(encoding="utf-8")),
    "preserved_prior_review": {
        "path": "runs/issues/A04/review.json",
        "sha256": sha(ROOT / "runs/issues/A04/review.json"),
    },
}
(OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"decision": decision, "release_S00": release,
                  "checks": results, "files": len(files)}, ensure_ascii=False, indent=1))
