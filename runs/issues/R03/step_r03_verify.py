#!/usr/bin/env python3
"""Independent verifier for #47 R03 (#63 R03_BATCH_01 + #64 R03_BATCH_02)."""

import csv
import hashlib
import json
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
R03_DIR = ROOT / "runs" / "issues" / "R03"


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

    manifest = json.loads((R03_DIR / "manifest.json").read_text(encoding="utf-8"))
    review = json.loads((R03_DIR / "review.json").read_text(encoding="utf-8"))
    rel = json.loads((R03_DIR / "release_20261127.json").read_text(encoding="utf-8"))
    r01_acc = json.loads((ROOT / "runs/issues/R01/acceptance_r01_20261126.json").read_text(encoding="utf-8"))
    r02_acc = json.loads((ROOT / "runs/issues/R02/acceptance_r02_20261126.json").read_text(encoding="utf-8"))
    r01_attr = json.loads((ROOT / "runs/issues/R01/attribution_review.json").read_text(encoding="utf-8"))
    r01_by_sid = {c["security_id"]: c for c in r01_attr["companies"]}

    disp = load_csv(R03_DIR / "inflection_batch_dispatch.csv")
    cases = load_csv(R03_DIR / "inflection_cases.csv")
    ce_txt = (R03_DIR / "counter_evidence.md").read_text(encoding="utf-8")

    print(f"R03 verify @ {manifest.get('fixed_now')} root= {ROOT}")

    # V01: Fixed 3+3 companies, zero overlap, match R01 R03_PRIORITY_A, upstream accepted
    b1 = set(rel["child_issues"][0]["companies"])
    b2 = set(rel["child_issues"][1]["companies"])
    pa = {c["security_id"] for c in r01_attr["companies"] if c["r03_priority_bucket"] == "R03_PRIORITY_A"}
    d_ids = {r["security_id"] for r in disp}
    c_ids = {r["security_id"] for r in cases}
    check("V01", "两批 3+3 家互斥零重复，与 R01 R03_PRIORITY_A 一致且上游均已验收",
          len(b1) == 3 and len(b2) == 3 and not (b1 & b2) and (b1 | b2) == pa == d_ids == c_ids
          and len(disp) == 6 and len(cases) == 6
          and r01_acc.get("decision") == "ACCEPTED_WITH_LIMITS" and r02_acc.get("decision") == "ACCEPTED_WITH_LIMITS",
          f"b1={len(b1)} b2={len(b2)} d={len(disp)} c={len(cases)}")

    # V02: Cutoff 2026-10-25 and H1(4) vs 9M(2) separation
    h1 = {r["security_id"] for r in cases if r["anchor_period"] == "20260630"}
    m9 = {r["security_id"] for r in cases if r["anchor_period"] == "20260930"}
    ap_bad = [r["security_id"] for r in cases if r["anchor_period"] != r01_by_sid[r["security_id"]]["anchor_period"]]
    check("V02", "知识截止日 2026-10-25，4×H1 与 2×9M(雷赛/天准) 严格分离",
          all(r["knowledge_as_of"] == "2026-10-25" for r in cases) and len(h1) == 4 and m9 == {"SZ:002979", "SH:688003"} and not ap_bad,
          f"h1={len(h1)} m9={sorted(m9)} ap_bad={ap_bad}")

    # V03: Required inflection reasoning fields & counter-evidence coverage
    missing_fields = [
        f"{r['security_id']}:{k}"
        for r in cases
        for k in ("product_line_separation", "two_period_comparable_facts", "alternative_explanations", "falsifiers", "evidence_gaps", "r04_scenario_constraints")
        if not r[k].strip()
    ]
    missing_ce = [r["security_id"] for r in cases if r["security_id"] not in ce_txt or "F1：" not in r["falsifiers"]]
    check("V03", "6 家均具备产品线分层、两期事实、替代解释、可推翻信号、缺证条件与R04边界，并写入 counter_evidence.md",
          not missing_fields and not missing_ce, f"missing_fields={missing_fields} missing_ce={missing_ce}")

    # V04: No trade advice & no fabricated pure-body claims
    forbidden = ["强烈推荐", "买入评级", "目标价", "贡献约4.40亿元收入", "收入下限"]
    hits = [w for w in forbidden if w in ce_txt or any(w in str(r.values()) for r in cases)]
    check("V04", "无买卖建议/目标价且无禁用口径回退", not hits, f"hits={hits}")

    # V05: R02 industry boundary preserved & denominator separated
    no_bound = [r["security_id"] for r in cases if "口径边界" not in r["r02_industry_signal_ref"] or "有效配对覆盖" not in r["r02_industry_signal_ref"]]
    check("V05", "6 家均挂接 R02 同锚定期行业信号（区分改善率分母与有效配对覆盖）并保留口径边界", not no_bound, f"no_bound={no_bound}")

    # V06: Manifest SHA-256, root digest, pure LF, no BOM
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
    check("V06", "manifest 输入/交付 SHA-256 与根摘要精确匹配，全部纯 LF 无 BOM",
          not in_bad and not deliv_bad and not crlf_bad and not bom_bad and root_ok,
          f"in_bad={in_bad} deliv_bad={deliv_bad} root_ok={root_ok}")

    # V07: Release guardrails
    check("V07", "放行边界：SELF_CHECK 不冒充独立验收，R04_released=False，#53 OPEN 未触碰",
          review.get("review_nature") == "SELF_CHECK" and review.get("R04_released") is False
          and review.get("issue_53_touched") is False and review.get("issue_53_status") == "OPEN",
          f"review_nature={review.get('review_nature')}")

    # V08: Byte-identical fixed-timestamp rebuild
    env = os.environ.copy()
    env["R03_FIXED_NOW"] = manifest["fixed_now"]
    before = {d["path"]: (ROOT / d["path"]).read_bytes() for d in manifest["deliverables"]}
    before["runs/issues/R03/manifest.json"] = (R03_DIR / "manifest.json").read_bytes()
    before["runs/issues/R03/review.json"] = (R03_DIR / "review.json").read_bytes()
    proc = subprocess.run([sys.executable, str(R03_DIR / "step_r03_build.py")], env=env, capture_output=True, text=True)
    diffs = [k for k, v in before.items() if (ROOT / k).read_bytes() != v]
    check("V08", "固定时间戳重跑构建逐字节一致", proc.returncode == 0 and not diffs, f"rc={proc.returncode} diffs={diffs}")

    passed = sum(1 for r in results if r[2])
    print(f"checks {passed}/{len(results)} PASS, anomalies={len(anomalies)}")
    return 0 if len(anomalies) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
