#!/usr/bin/env python3
"""Independent verifier for R00 Batch 03 (#61) + Batch 04 (#62) and full 18/18 TIER_1 completion."""

import csv
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[4]
OUT_DIR = ROOT / "runs" / "issues" / "R00" / "tier1_completion"


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def read_lf_bytes(path: pathlib.Path) -> bytes:
    return path.read_bytes().replace(b"\r\n", b"\n")


def load_csv(path: pathlib.Path) -> list:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def main() -> int:
    anomalies = []
    results = []

    def check(vid, name, ok, detail):
        results.append((vid, name, ok, detail))
        print(f"  [{'PASS' if ok else 'FAIL'}] {vid} {name}")
        if not ok:
            print(f"         {detail}")
            anomalies.append(f"{vid}: {detail}")

    manifest = json.loads((OUT_DIR / "manifest.json").read_text(encoding="utf-8"))
    review = json.loads((OUT_DIR / "review.json").read_text(encoding="utf-8"))
    rel = json.loads((OUT_DIR / "release_batch03_04_20261127.json").read_text(encoding="utf-8"))

    s08 = load_csv(ROOT / "runs/issues/S08/business_verification_candidates.csv")
    s08_t1 = {r["security_id"]: r for r in s08 if (r.get("r00_priority_tier") or "").startswith("TIER_1")}
    b12_disp = load_csv(ROOT / "runs/issues/R00/business_batch_dispatch.csv")
    b34_disp = load_csv(OUT_DIR / "batch03_04_dispatch.csv")
    b34_reg = load_csv(OUT_DIR / "batch03_04_register.csv")
    t18 = load_csv(OUT_DIR / "tier1_18_complete_register.csv")
    q3 = load_csv(OUT_DIR / "batch03_evidence_quotes.csv")
    q4 = load_csv(OUT_DIR / "batch04_evidence_quotes.csv")

    print(f"R00 TIER_1 completion verify @ {manifest.get('fixed_now')} root= {ROOT}")

    # V01: Exact 18/18 TIER_1 partition (10 prior + 5 B03 + 3 B04), zero overlap
    s12 = {r["security_id"] for r in b12_disp}
    s3 = set(rel["child_issues"][0]["companies"])
    s4 = set(rel["child_issues"][1]["companies"])
    s34 = {r["security_id"] for r in b34_disp}
    s18 = {r["security_id"] for r in t18}
    v01 = (len(s12) == 10 and len(s3) == 5 and len(s4) == 3 and len(s3 & s4) == 0 and len(s12 & s34) == 0
           and s34 == (s3 | s4) and s18 == set(s08_t1.keys()) and len(t18) == 18)
    check("V01", "18/18 S08 冻结 TIER_1 完整互斥覆盖（10+5+3=18，零重复零漏项）", v01,
          f"s12={len(s12)} s34={len(s34)} s18={len(s18)} s08_t1={len(s08_t1)}")

    # V02: Disclosure cutoff <= 2026-10-25 and H1(7) vs 9M(1 国恩) separation
    b3_doc = yaml.safe_load((ROOT / "runs/issues/R00/inputs_batch03/batch03_5companies_business_review.yaml").read_text(encoding="utf-8"))
    b4_doc = yaml.safe_load((ROOT / "runs/issues/R00/inputs_batch04/batch04_3companies_business_review.yaml").read_text(encoding="utf-8"))
    late, q3_bad, ap_bad = [], [], []
    for doc in (b3_doc, b4_doc):
        for item in doc["companies"]:
            c = item["company"]
            sid = c["security_id"]
            ap = s08_t1[sid]["s05_anchor_period"]
            if str(c["knowledge_as_of"]) != "2026-10-25":
                late.append(f"{sid}:cutoff")
            for s in c["sources_actually_read"]:
                if str(s["disclosure_date"]) > "2026-10-25":
                    late.append(f"{sid}:{s['doc_id']}:{s['disclosure_date']}")
                if ap == "20260630" and "三季报" in str(s["report_name"]):
                    q3_bad.append(f"{sid}:{s['doc_id']}")
    for r in b34_reg:
        if r["anchor_period"] != s08_t1[r["security_id"]]["s05_anchor_period"]:
            ap_bad.append(r["security_id"])
    check("V02", "知识截止日 2026-10-25 无越界，7×H1 与 1×9M(国恩) 锚定期严格对齐",
          not late and not q3_bad and not ap_bad, f"late={late} q3_bad={q3_bad} ap_bad={ap_bad}")

    # V03: Quotes integrity
    all_q = q3 + q4
    bad_q = [q for q in all_q if int(q["physical_page"]) <= 0 or not q["verbatim_quote"].strip()]
    counts = {}
    for q in all_q:
        counts[q["security_id"]] = counts.get(q["security_id"], 0) + 1
    check("V03", "8 家引文覆盖完整（每家>=10 条、1-based physical_page>0、逐字非空）",
          not bad_q and set(counts.keys()) == s34 and all(v >= 10 for v in counts.values()),
          f"total={len(all_q)} counts={counts} bad={len(bad_q)}")

    # V04: Legacy boundary & no auto-promotion
    check("V04", "8 家 legacy_auto_promoted=False 且不虚标单列纯机器人收入",
          all(r["legacy_auto_promoted"] == "False" for r in b34_disp)
          and all(r["robot_revenue_separately_disclosed"] == "False" for r in b34_reg),
          "legacy_auto_promoted_ok")

    # V05: Manifest SHA-256, root digest, pure LF, no BOM
    in_bad, deliv_bad, crlf_bad, bom_bad = [], [], [], []
    for item in manifest["inputs"]:
        p = ROOT / item["path"]
        b = read_lf_bytes(p)
        if len(b) != item["bytes"] or sha256_bytes(b) != item["sha256"]:
            in_bad.append(item["path"])
    for item in manifest["deliverables"]:
        p = ROOT / item["path"]
        b = p.read_bytes()
        if b"\r\n" in b:
            crlf_bad.append(item["path"])
        if b.startswith(b"\xef\xbb\xbf"):
            bom_bad.append(item["path"])
        if len(b) != item["bytes"] or sha256_bytes(b) != item["sha256"]:
            deliv_bad.append(item["path"])
    root_ok = sha256_bytes("\n".join(f"{d['path']}:{d['sha256']}" for d in sorted(manifest["deliverables"], key=lambda x: x["path"])).encode("utf-8")) == manifest["manifest_root_digest"]
    check("V05", "manifest 输入/交付 SHA-256 与根摘要精确匹配，全部纯 LF 无 BOM",
          not in_bad and not deliv_bad and not crlf_bad and not bom_bad and root_ok,
          f"in_bad={in_bad} deliv_bad={deliv_bad} root_ok={root_ok}")

    # V06: Release guardrails
    check("V06", "放行边界：SELF_CHECK 不冒充独立验收，不放行 R03，不触碰 #53",
          review.get("review_nature") == "SELF_CHECK" and review.get("R03_released") is False
          and review.get("issue_53_touched") is False and review.get("issue_53_status") == "OPEN",
          f"review_nature={review.get('review_nature')}")

    # V07: Byte-identical fixed-timestamp rebuild
    env = os.environ.copy()
    env["R00_T1_FIXED_NOW"] = manifest["fixed_now"]
    before = {d["path"]: (ROOT / d["path"]).read_bytes() for d in manifest["deliverables"]}
    before["runs/issues/R00/tier1_completion/manifest.json"] = (OUT_DIR / "manifest.json").read_bytes()
    before["runs/issues/R00/tier1_completion/review.json"] = (OUT_DIR / "review.json").read_bytes()
    proc = subprocess.run([sys.executable, str(OUT_DIR / "step_build.py")], env=env, capture_output=True, text=True)
    diffs = [k for k, v in before.items() if (ROOT / k).read_bytes() != v]
    check("V07", "固定时间戳重跑构建逐字节一致", proc.returncode == 0 and not diffs, f"rc={proc.returncode} diffs={diffs}")

    passed = sum(1 for r in results if r[2])
    print(f"checks {passed}/{len(results)} PASS, anomalies={len(anomalies)}")
    return 0 if len(anomalies) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
