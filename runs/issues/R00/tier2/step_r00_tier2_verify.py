#!/usr/bin/env python3
"""Independent verifier for #44 R00 TIER_2 (40 clean companies across #65-#72)."""

import csv
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys

try:
    import pymupdf
except ImportError:
    pymupdf = None

ROOT = pathlib.Path(__file__).resolve().parents[4]
T2_DIR = ROOT / "runs" / "issues" / "R00" / "tier2"


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def read_lf_bytes(p: pathlib.Path) -> bytes:
    return p.read_bytes().replace(b"\r\n", b"\n")


def load_csv(p: pathlib.Path) -> list:
    with p.open("r", encoding="utf-8-sig", newline="") as f:
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

    manifest = json.loads((T2_DIR / "manifest.json").read_text(encoding="utf-8"))
    review = json.loads((T2_DIR / "review.json").read_text(encoding="utf-8"))
    rel = json.loads((T2_DIR / "release_tier2_20261128.json").read_text(encoding="utf-8"))
    s08_t2 = {r["security_id"]: r for r in load_csv(ROOT / "runs/issues/S08/business_verification_candidates.csv") if "TIER_2" in r.get("r00_priority_tier", "")}

    disp = load_csv(T2_DIR / "tier2_batch_dispatch.csv")
    reg = load_csv(T2_DIR / "tier2_register.csv")
    quotes = load_csv(T2_DIR / "tier2_evidence_quotes.csv")

    print(f"R00 TIER_2 verify @ {manifest.get('fixed_now')} root= {ROOT}")

    # V01: Exact 40 TIER_2 companies across 8x5 batches
    b_sids = [sid for b in rel["child_issues"] for sid in b["companies"]]
    check("V01", "8 批 5×8=40 家互斥零重复，100% 等于 S08 冻结 TIER_2",
          len(b_sids) == 40 and len(set(b_sids)) == 40 and set(b_sids) == set(s08_t2.keys())
          and {r["security_id"] for r in disp} == set(s08_t2.keys())
          and {r["security_id"] for r in reg} == set(s08_t2.keys()),
          f"disp={len(disp)} reg={len(reg)}")

    # V02: Cutoff 2026-10-25 & 27 H1 + 13 9M separation
    h1 = sum(1 for r in reg if r["anchor_period"] == "20260630")
    m9 = sum(1 for r in reg if r["anchor_period"] == "20260930")
    ap_bad = [r["security_id"] for r in reg if r["anchor_period"] != s08_t2[r["security_id"]]["s05_anchor_period"]]
    check("V02", "知识截止日 2026-10-25，27×H1 与 13×9M 锚定期严格与 S08 一致",
          all(r["knowledge_as_of"] == "2026-10-25" for r in reg) and h1 == 27 and m9 == 13 and not ap_bad,
          f"h1={h1} m9={m9} ap_bad={ap_bad}")

    # V03: Valid enums & routing counts match review.json
    adv = sum(1 for r in reg if r["routing_recommendation"] == "ADVANCE_TO_R01")
    hold = sum(1 for r in reg if r["routing_recommendation"] == "OBSERVE_HOLD")
    defer = sum(1 for r in reg if r["routing_recommendation"] == "OBSERVE_DEFER")
    c = review["counts"]
    check("V03", "分流枚举合法且计数与 review.json 精确一致",
          adv == c["advance_to_r01"] and hold == c["observe_hold"] and defer == c["observe_defer"] and (adv + hold + defer == 40),
          f"adv={adv} hold={hold} defer={defer}")

    # V04: 100% verbatim quote verification against local official PDF physical pages (when local PDFs present)
    doc_files = {}
    ci_path = ROOT / "runs/collection/collection_index.csv"
    if ci_path.exists():
        for r in load_csv(ci_path):
            if r["document_id"] and r["local_file"] and pathlib.Path(r["local_file"]).exists():
                doc_files[r["document_id"]] = r["local_file"]
    if pymupdf is not None and doc_files:
        cache = {}
        mismatches = []
        for q in quotes:
            did = q["doc_id"]
            pno = int(q["physical_page"])
            qt = re.sub(r"\s+", "", q["verbatim_quote"])
            if did not in doc_files:
                mismatches.append(f"{q['security_id']}:{did}:NO_LOCAL_PDF")
                continue
            key = (did, pno)
            if key not in cache:
                doc = pymupdf.open(doc_files[did])
                cache[key] = re.sub(r"\s+", "", doc[pno - 1].get_text("text") or "") if 1 <= pno <= len(doc) else ""
                doc.close()
            if not qt or qt not in cache[key]:
                mismatches.append(f"{q['security_id']}:{did}:p{pno}")
        check("V04", f"全部 {len(quotes)} 条引文在本地官方 PDF 对应 1-based 物理页 100% 逐字命中",
              len(mismatches) == 0 and len(quotes) >= 80,
              f"mismatches={mismatches[:5]}")
    else:
        check("V04", "全部引文具非空 doc_id/物理页/短引文（无本地 PDF 时做结构校验）",
              len(quotes) >= 80 and all(q["doc_id"] and int(q["physical_page"]) >= 1 and q["verbatim_quote"].strip() for q in quotes),
              f"quotes={len(quotes)}")

    # V05: No trade advice or target prices
    forbidden = ["强烈推荐", "买入评级", "目标价"]
    ho_txt = (T2_DIR / "handoff.md").read_text(encoding="utf-8")
    hits = [w for w in forbidden if w in ho_txt or any(w in str(r.values()) for r in reg)]
    check("V05", "无买卖建议或目标价", not hits, f"hits={hits}")

    # V06: Manifest SHA-256, root digest, pure LF, no BOM
    in_bad, deliv_bad, crlf_bad, bom_bad = [], [], [], []
    for item in manifest["inputs"]:
        b = read_lf_bytes(ROOT / item["path"])
        if len(b) != item["bytes"] or sha256_bytes(b) != item["sha256"]:
            in_bad.append(item["path"])
    for item in manifest["deliverables"]:
        b = (ROOT / item["path"]).read_bytes()
        if b"\r\n" in b:
            crlf_bad.append(item["path"])
        if b.startswith(b"\xef\xbb\xbf"):
            bom_bad.append(item["path"])
        if len(b) != item["bytes"] or sha256_bytes(b) != item["sha256"]:
            deliv_bad.append(item["path"])
    root_ok = sha256_bytes("\n".join(f"{d['path']}:{d['sha256']}" for d in sorted(manifest["deliverables"], key=lambda x: x["path"])).encode("utf-8")) == manifest["manifest_root_digest"]
    check("V06", "manifest 输入/交付 SHA-256 与根摘要精确匹配，全部纯 LF 无 BOM",
          not in_bad and not deliv_bad and not crlf_bad and not bom_bad and root_ok,
          f"in_bad={in_bad} deliv_bad={deliv_bad} crlf={crlf_bad} root_ok={root_ok}")

    # V07: Release guardrails
    check("V07", "放行边界：SELF_CHECK 不冒充独立验收，R04_released=False，#53 OPEN 未触碰",
          review.get("review_nature") == "SELF_CHECK" and review.get("R04_released") is False
          and review.get("issue_53_touched") is False and review.get("issue_53_status") == "OPEN",
          f"review_nature={review.get('review_nature')}")

    # V08: Fixed-timestamp byte-identical rebuild
    env = os.environ.copy()
    env["R00_T2_FIXED_NOW"] = manifest["fixed_now"]
    before = {d["path"]: (ROOT / d["path"]).read_bytes() for d in manifest["deliverables"]}
    before["runs/issues/R00/tier2/manifest.json"] = (T2_DIR / "manifest.json").read_bytes()
    before["runs/issues/R00/tier2/review.json"] = (T2_DIR / "review.json").read_bytes()
    proc = subprocess.run([sys.executable, str(T2_DIR / "step_r00_tier2_build.py")], env=env, capture_output=True, text=True)
    diffs = [k for k, v in before.items() if (ROOT / k).read_bytes() != v]
    check("V08", "固定时间戳重跑构建逐字节一致", proc.returncode == 0 and not diffs, f"rc={proc.returncode} diffs={diffs}")

    passed = sum(1 for r in results if r[2])
    print(f"checks {passed}/{len(results)} PASS, anomalies={len(anomalies)}")
    return 0 if len(anomalies) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
