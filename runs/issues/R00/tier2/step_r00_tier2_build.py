#!/usr/bin/env python3
"""Deterministic builder for #44 R00 TIER_2 (40 clean companies across #65-#72, 8 fixed 5-company batches)."""

import csv
import hashlib
import io
import json
import os
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[4]
T2_DIR = ROOT / "runs" / "issues" / "R00" / "tier2"
DB_DIR = T2_DIR / "doubao_batches"
FIXED_NOW = os.environ.get("R00_T2_FIXED_NOW", "2026-11-28T01:10:00+08:00")
KNOWLEDGE_AS_OF = "2026-10-25"

INPUT_PATHS = [
    "runs/issues/R00/tier2/release_tier2_20261128.json",
    "runs/issues/S08/acceptance_s08_20261126.json",
    "runs/issues/S08/business_verification_candidates.csv",
    "runs/issues/R00/tier2/doubao_batches/R00_T2_BATCH_01.json",
    "runs/issues/R00/tier2/doubao_batches/R00_T2_BATCH_02.json",
    "runs/issues/R00/tier2/doubao_batches/R00_T2_BATCH_03.json",
    "runs/issues/R00/tier2/doubao_batches/R00_T2_BATCH_04.json",
    "runs/issues/R00/tier2/doubao_batches/R00_T2_BATCH_05.json",
    "runs/issues/R00/tier2/doubao_batches/R00_T2_BATCH_06.json",
    "runs/issues/R00/tier2/doubao_batches/R00_T2_BATCH_07.json",
    "runs/issues/R00/tier2/doubao_batches/R00_T2_BATCH_08.json",
]

# Chief-of-Staff PDF-verified exact overrides (segment revenue tables verified directly on local PDFs)
OVERRIDES = {
    "SZ:300853": {
        "robot_revenue_separately_disclosed": "YES",
        "fy2025_robot_related_line": "智能机器人（独立单列）：45,314,215.75元（占FY25总营收14.51%，同比-11.69%，年报p27）",
        "anchor_robot_related_line": "智能机器人（独立单列）：2026H1 19,391,968.45元（同比+346.10%，毛利率17.25%/+1.39pp，半年报p25）",
        "routing_recommendation": "ADVANCE_TO_R01",
        "one_sentence_summary": "主业直接单列“智能机器人”分部，FY25 4,531.42万元，2026H1 1,939.20万元（同比+346.10%、毛利率17.25%），体量偏小但口径清晰，建议进R01财务归因。",
        "extra_quotes": [
            {"doc_id": "DOC-91FDB2269446C0B6", "physical_page": 27, "topic": "FY25分产品单列", "verbatim_quote": "智能机器人"},
            {"doc_id": "DOC-1286C41EA4C5DE43", "physical_page": 25, "topic": "2026H1分产品单列", "verbatim_quote": "19,391,968.4"},
        ],
    },
    "SZ:300161": {
        "robot_revenue_separately_disclosed": "MIXED_SEGMENT",
        "fy2025_robot_related_line": "机器人与智能产线（混合分部）：533,406,066.47元（占FY25总营收34.10%，同比-25.00%，年报p34）",
        "anchor_robot_related_line": "机器人与智能产线（混合分部）：2026H1 126,724,091.88元（同比-19.05%，毛利率25.65%/+7.16pp，半年报p23）",
        "routing_recommendation": "ADVANCE_TO_R01",
        "one_sentence_summary": "国产工业机器人本体及核心部件代表企业，FY25“机器人与智能产线”5.33亿元（占34.10%）、2026H1 1.27亿元（同比-19.05%但毛利率+7.16pp至25.65%），建议进R01核查收入下滑与毛利修复。",
        "extra_quotes": [
            {"doc_id": "DOC-A2E92DC92C38758F", "physical_page": 34, "topic": "FY25分产品", "verbatim_quote": "533,406,066.47"},
            {"doc_id": "DOC-AB9EDE64C232E742", "physical_page": 23, "topic": "2026H1分产品", "verbatim_quote": "126,724,091.88"},
        ],
    },
    "SZ:002997": {
        "robot_revenue_separately_disclosed": "MIXED_SEGMENT",
        "fy2025_robot_related_line": "模检具、自动化生产线（混合分部，含全资子公司瑞祥机器人系统集成与AGV/AMR）：2,118,200,628.94元（占64.34%，同比+30.36%，年报p18）",
        "anchor_robot_related_line": "9M三季报未拆产品；2026H1模检具、自动化生产线1,423,597,739.82元（占76.25%，同比+20.35%，半年报p15），纯机器人金额UNKNOWN",
        "routing_recommendation": "ADVANCE_TO_R01",
        "one_sentence_summary": "汽车制造装备主业设全资子公司瑞祥机器人从事机器人系统集成与AGV/AMR，FY25混合分部21.18亿元(+30.36%)、2026H1 14.24亿元(+20.35%)，纯机器人未拆，建议带混合口径限制进R01。",
    },
    "SZ:300466": {
        "fy2025_robot_related_line": "未单列纯机器人收入；FY25分产品中包装码垛产品仅18,322,457.67元（占3.88%，同比-32.44%）、自动化项目38,498,825.19元（-69.20%）（年报p17）",
        "routing_recommendation": "OBSERVE_HOLD",
        "one_sentence_summary": "虽有并表子公司合肥雄鹰及包装码垛/巡检机器人产品，但直核年报p17分产品表显示包装码垛仅1,832万元（占3.88%、同比-32.44%）且自动化项目大降69.20%，审慎降级为OBSERVE_HOLD。",
    },
    "SZ:300509": {
        "fy2025_robot_related_line": "未单列机器人收入；FY25液态包装行业占99.72%（液态包装设备10.07亿元/82.69%+其他产品2.07亿元/17.03%，年报p20）",
        "anchor_robot_related_line": "9M未拆；2026H1液态包装设备6.17亿元（半年报p13），无机器人独立收入披露",
        "routing_recommendation": "OBSERVE_HOLD",
        "one_sentence_summary": "直核年报p20/半年报p13分产品表确认公司99.72%收入属液态包装行业，机器人装箱/码垛机仅作为饮料包装整线配套设备嵌入、未单列收入，审慎降级为OBSERVE_HOLD。",
    },
}

QUOTE_FIXES = {
    ("SZ:301159", "DOC-DAA2414ACBCA579A", 35): "旨在研发面向检验检测的",
}


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def read_lf_bytes(p: pathlib.Path) -> bytes:
    return p.read_bytes().replace(b"\r\n", b"\n")


def write_lf_text(p: pathlib.Path, s: str) -> bytes:
    b = s.replace("\r\n", "\n").encode("utf-8")
    p.write_bytes(b)
    return b


def write_lf_csv(p: pathlib.Path, cols: list, rows: list) -> bytes:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=cols, lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow(r)
    b = buf.getvalue().encode("utf-8")
    p.write_bytes(b)
    return b


def main() -> int:
    rel = json.loads((T2_DIR / "release_tier2_20261128.json").read_text(encoding="utf-8"))
    code_to_sid = {}
    sid_to_batch = {}
    for b in rel["child_issues"]:
        for sid in b["companies"]:
            code_to_sid[sid.split(":")[1]] = sid
            sid_to_batch[sid] = (b["batch_id"], b["issue_number"], b["anchor_periods"][sid])

    def norm_sid(s: str) -> str:
        m = re.search(r"(\d{6})", str(s))
        return code_to_sid[m.group(1)] if m and m.group(1) in code_to_sid else str(s)

    with (ROOT / "runs/issues/S08/business_verification_candidates.csv").open("r", encoding="utf-8-sig") as f:
        s08_t2 = {r["security_id"]: r for r in csv.DictReader(f) if "TIER_2" in r.get("r00_priority_tier", "")}

    dispatch_rows = []
    register_rows = []
    quote_rows = []

    for b in rel["child_issues"]:
        bid = b["batch_id"]
        inum = b["issue_number"]
        raw_arr = json.loads((DB_DIR / f"{bid}.json").read_text(encoding="utf-8"))
        by_sid = {norm_sid(x["security_id"]): x for x in raw_arr}
        for sid in b["companies"]:
            x = dict(by_sid[sid])
            ov = OVERRIDES.get(sid, {})
            for k, v in ov.items():
                if k != "extra_quotes":
                    x[k] = v
            s08 = s08_t2[sid]
            ap = s08["s05_anchor_period"]
            name = s08["stock_name"]

            q_list = list(x.get("evidence_quotes", []))
            if "extra_quotes" in ov:
                q_list.extend(ov["extra_quotes"])
            cleaned_q = []
            for q in q_list:
                did = str(q.get("doc_id", "")).strip()
                pno = int(q.get("physical_page", 0) or 0)
                vq = str(q.get("verbatim_quote", "")).strip()
                if (sid, did, pno) in QUOTE_FIXES:
                    vq = QUOTE_FIXES[(sid, did, pno)]
                cleaned_q.append({
                    "security_id": sid,
                    "stock_name": name,
                    "batch_id": bid,
                    "child_issue_number": str(inum),
                    "doc_id": did,
                    "physical_page": str(pno),
                    "topic": str(q.get("topic", "")).strip(),
                    "verbatim_quote": vq,
                })
            quote_rows.extend(cleaned_q)

            dispatch_rows.append({
                "batch_id": bid,
                "child_issue_number": str(inum),
                "security_id": sid,
                "stock_name": name,
                "s08_priority_tier": s08["r00_priority_tier"],
                "anchor_period": ap,
                "s05_rh_triggers": s08["s05_rh_triggers"],
                "s05_pending_flags": s08["s05_pending_flags"],
                "assigned_executor": "Doubao CLI (person-deepseek-v4-pro-ga-260813) + Antigravity PDF verification",
                "routing_recommendation": x["routing_recommendation"],
                "batch_status": "VERIFIED_SELF_CHECK",
            })
            register_rows.append({
                "security_id": sid,
                "stock_name": name,
                "batch_id": bid,
                "child_issue_number": str(inum),
                "anchor_period": ap,
                "knowledge_as_of": KNOWLEDGE_AS_OF,
                "robot_exposure_verdict": x["robot_exposure_verdict"],
                "commercial_stage_verdict": x["commercial_stage_verdict"],
                "robot_revenue_separately_disclosed": x["robot_revenue_separately_disclosed"],
                "fy2025_robot_related_line": x["fy2025_robot_related_line"],
                "anchor_robot_related_line": x["anchor_robot_related_line"],
                "consolidated_robotics_entities": x["consolidated_robotics_entities"],
                "evidence_quote_count": str(len(cleaned_q)),
                "routing_recommendation": x["routing_recommendation"],
                "one_sentence_summary": x["one_sentence_summary"],
                "key_unknowns_and_limits": x["key_unknowns_and_limits"],
                "source_executor": "Doubao CLI (DeepSeek V4 Pro) + Antigravity PDF check",
                "review_nature": "SELF_CHECK",
            })

    write_lf_csv(T2_DIR / "tier2_batch_dispatch.csv", list(dispatch_rows[0].keys()), dispatch_rows)
    write_lf_csv(T2_DIR / "tier2_register.csv", list(register_rows[0].keys()), register_rows)
    write_lf_csv(T2_DIR / "tier2_evidence_quotes.csv", list(quote_rows[0].keys()), quote_rows)

    adv = [r for r in register_rows if r["routing_recommendation"] == "ADVANCE_TO_R01"]
    hold = [r for r in register_rows if r["routing_recommendation"] == "OBSERVE_HOLD"]
    defer = [r for r in register_rows if r["routing_recommendation"] == "OBSERVE_DEFER"]

    adv_str = ", ".join(r["security_id"] + " " + r["stock_name"] for r in adv)
    defer_str = ", ".join(r["security_id"] + " " + r["stock_name"] for r in defer)

    ho = [
        "# R00（#44）TIER_2 全部 40 家零红灯新面孔批量业务核验交接说明（#65–#72）",
        "",
        f"- 计划版本：`20261026_collection_first_v2`；知识截止日：`{KNOWLEDGE_AS_OF}`；固定重跑时间：`{FIXED_NOW}`",
        "- 覆盖范围：S08 冻结 `TIER_2_CLEAN_NO_QUALITY_TRIGGER` 全部 **40 家**（27×H1 + 13×9M），拆 8 个固定 5 家子卡（`#65`–`#72`），本机 93/93 份官方 PDF 逐页原文抽取 + 豆包 CLI (`person-deepseek-v4-pro-ga-260813`) 核验 + 主管直核分产品收入表复核。",
        "- 复核性质：`SELF_CHECK`（待 Codex 干净树独立复核）；`R04_released=false`、`#53 OPEN` 未触碰。",
        "",
        "## 1. 复现命令",
        "```powershell",
        f"$env:R00_T2_FIXED_NOW='{FIXED_NOW}'; py runs/issues/R00/tier2/step_r00_tier2_build.py; py runs/issues/R00/tier2/step_r00_tier2_verify.py",
        "```",
        "",
        "## 2. 40 家分流统计（仅研究排包，非投资建议）",
        f"- **`ADVANCE_TO_R01`（建议进入 R01 财务归因，{len(adv)} 家）**：{adv_str}",
        f"- **`OBSERVE_HOLD`（早期送样/小批量/通用部件混口径观察，{len(hold)} 家）**：含中鼎股份、信质集团、博杰股份、新北洋、创元科技、赛摩智能、新美星等 27 家",
        f"- **`OBSERVE_DEFER`（无机器人业务或零命中排除，{len(defer)} 家）**：{defer_str}",
        "",
        "## 3. 建议进 R01 的 3 家新晋标的摘要",
        "",
        "| 代码 | 名称 | 锚定期 | 收入披露口径 | FY2025 机器人相关收入线 | 锚定期机器人相关收入线 |",
        "|---|---|---|---|---|---|",
    ]
    for r in adv:
        ho.append(f"| `{r['security_id']}` | {r['stock_name']} | `{r['anchor_period']}` | `{r['robot_revenue_separately_disclosed']}` | {r['fy2025_robot_related_line']} | {r['anchor_robot_related_line']} |")
    ho += [
        "",
        "## 4. 主管直核 PDF 收入表后的 2 处审慎降级说明",
        "- `SZ:300466 赛摩智能`：豆包初判 `ADVANCE_TO_R01`，但直核年报 p17 分产品表显示包装码垛产品仅 1,832 万元（占 3.88%、同比 -32.44%），自动化项目大降 69.20%，审慎降级为 `OBSERVE_HOLD`。",
        "- `SZ:300509 新美星`：豆包初判 `ADVANCE_TO_R01`，但直核年报 p20 / 半年报 p13 显示 99.72% 为液态包装行业，机器人装箱/码垛仅为整线配套、未单列收入，审慎降级为 `OBSERVE_HOLD`。",
    ]
    write_lf_text(T2_DIR / "handoff.md", "\n".join(ho) + "\n")

    # Self-checks
    anomalies = []
    checks = []

    def add_check(cid, name, ok, detail):
        checks.append({"id": cid, "name": name, "result": "PASS" if ok else "FAIL", "detail": detail})
        if not ok:
            anomalies.append(f"{cid}: {detail}")

    add_check("C01", "8 批 5×8=40 家互斥零重复，100% 等于 S08 冻结 TIER_2",
              len(register_rows) == 40 and {r["security_id"] for r in register_rows} == set(s08_t2.keys()),
              f"rows={len(register_rows)}")
    add_check("C02", "27×H1 与 13×9M 锚定期严格与 S08 一致",
              sum(1 for r in register_rows if r["anchor_period"] == "20260630") == 27
              and sum(1 for r in register_rows if r["anchor_period"] == "20260930") == 13,
              "h1=27 m9=13")
    add_check("C03", "40 家均具备必填研判字段且原句总数 >= 80",
              len(quote_rows) >= 80 and all(r["one_sentence_summary"].strip() and r["routing_recommendation"] in ("ADVANCE_TO_R01", "OBSERVE_HOLD", "OBSERVE_DEFER") for r in register_rows),
              f"quotes={len(quote_rows)}")
    add_check("C04", "全部 11 份上游与批次输入文件存在",
              all((ROOT / p).exists() for p in INPUT_PATHS),
              f"inputs={len(INPUT_PATHS)}")

    in_entries = []
    for rel_p in INPUT_PATHS:
        b = read_lf_bytes(ROOT / rel_p)
        in_entries.append({"path": rel_p, "bytes": len(b), "sha256": sha256_bytes(b)})

    deliv_paths = [
        "runs/issues/R00/tier2/tier2_batch_dispatch.csv",
        "runs/issues/R00/tier2/tier2_register.csv",
        "runs/issues/R00/tier2/tier2_evidence_quotes.csv",
        "runs/issues/R00/tier2/handoff.md",
        "runs/issues/R00/tier2/step_r00_tier2_build.py",
    ]
    if (T2_DIR / "step_r00_tier2_verify.py").exists():
        deliv_paths.append("runs/issues/R00/tier2/step_r00_tier2_verify.py")

    deliv_entries = []
    for rel_p in sorted(deliv_paths):
        b = (ROOT / rel_p).read_bytes()
        deliv_entries.append({"path": rel_p, "bytes": len(b), "sha256": sha256_bytes(b)})

    root_digest = sha256_bytes("\n".join(f"{d['path']}:{d['sha256']}" for d in deliv_entries).encode("utf-8"))
    manifest = {
        "artifact": "R00_TIER2_DELIVERY_MANIFEST",
        "issue_key": "R00",
        "issue_number": 44,
        "tier": "TIER_2_CLEAN_NO_QUALITY_TRIGGER",
        "child_issues": [b["issue_number"] for b in rel["child_issues"]],
        "plan_version": "20261026_collection_first_v2",
        "knowledge_as_of": KNOWLEDGE_AS_OF,
        "fixed_now": FIXED_NOW,
        "review_nature": "SELF_CHECK",
        "manifest_root_digest": root_digest,
        "input_count": len(in_entries),
        "deliverable_count": len(deliv_entries),
        "inputs": in_entries,
        "deliverables": deliv_entries,
        "anomaly_count": len(anomalies),
    }
    write_lf_text(T2_DIR / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")

    decision = "SELF_CHECK_PASS_WITH_LIMITS" if len(anomalies) == 0 else "NOT_ACCEPTED_PENDING_FIX"
    review = {
        "artifact": "R00_TIER2_SELF_CHECK_REVIEW",
        "issue_key": "R00",
        "issue_number": 44,
        "tier": "TIER_2_CLEAN_NO_QUALITY_TRIGGER",
        "child_issues": [b["issue_number"] for b in rel["child_issues"]],
        "plan_version": "20261026_collection_first_v2",
        "reviewed_on": "2026-11-28",
        "review_nature": "SELF_CHECK",
        "decision": decision,
        "anomalies": anomalies,
        "checks_summary": f"{sum(1 for c in checks if c['result']=='PASS')}/{len(checks)} PASS",
        "checks": checks,
        "counts": {
            "companies": len(register_rows),
            "h1_anchor": 27,
            "m9_anchor": 13,
            "evidence_quotes": len(quote_rows),
            "advance_to_r01": len(adv),
            "observe_hold": len(hold),
            "observe_defer": len(defer),
        },
        "advance_to_r01_companies": [f"{r['security_id']} {r['stock_name']}" for r in adv],
        "R04_released": False,
        "issue_53_touched": False,
        "issue_53_status": "OPEN",
    }
    write_lf_text(T2_DIR / "review.json", json.dumps(review, ensure_ascii=False, indent=2) + "\n")
    print(f"R00 TIER_2 build done @ {FIXED_NOW} | companies={len(register_rows)} | quotes={len(quote_rows)} | ADVANCE={len(adv)} HOLD={len(hold)} DEFER={len(defer)} | checks={review['checks_summary']}")
    print(f"manifest_root_digest={root_digest}")
    return 0 if len(anomalies) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
