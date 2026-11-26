#!/usr/bin/env python3
"""Independent verifier for #45 R01 (#59 R01_BATCH_01 + #60 R01_BATCH_02)."""

import csv
import hashlib
import json
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
R01_DIR = ROOT / "runs" / "issues" / "R01"

FORBIDDEN_PHRASES = [
    "贡献约4.40亿元收入",
    "收入下限",
    "可佐证的下限",
    "只能作下限参考",
    "参股灵博12%",
    "均为参股不并表",
    "思哲睿/灵博（权益法）",
]


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

    def check(vid: str, name: str, ok: bool, detail: str):
        results.append((vid, name, ok, detail))
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {vid} {name}")
        if not ok:
            print(f"         {detail}")
            anomalies.append(f"{vid}: {detail}")

    manifest = json.loads((R01_DIR / "manifest.json").read_text(encoding="utf-8"))
    review = json.loads((R01_DIR / "review.json").read_text(encoding="utf-8"))
    release = json.loads((R01_DIR / "release_20261126.json").read_text(encoding="utf-8"))
    r00_acc = json.loads((ROOT / "runs/issues/R00/acceptance_r00_batch01_02_20261126.json").read_text(encoding="utf-8"))
    r00_reg = {r["security_id"]: r for r in load_csv(ROOT / "runs/issues/R00/business_review_register.csv")}
    s08_map = {r["security_id"]: r for r in load_csv(ROOT / "runs/issues/S08/business_verification_candidates.csv")}
    s05_flags = {}
    for row in load_csv(ROOT / "runs/issues/S05/quality_flags.csv"):
        s05_flags.setdefault(row["security_id"], {})[row["metric_id"]] = row

    disp = load_csv(R01_DIR / "financial_attribution_dispatch.csv")
    scope = load_csv(R01_DIR / "robot_revenue_scope.csv")
    attr = json.loads((R01_DIR / "attribution_review.json").read_text(encoding="utf-8"))

    print(f"R01 verify @ {manifest.get('fixed_now')} root= {ROOT}")

    # V01: Fixed 10 companies across #59 & #60, zero overlap, match R00 accepted
    b1 = set(release["child_issues"][0]["companies"])
    b2 = set(release["child_issues"][1]["companies"])
    disp_ids = [r["security_id"] for r in disp]
    scope_ids = [r["security_id"] for r in scope]
    attr_ids = [c["security_id"] for c in attr["companies"]]
    v01_ok = (
        len(b1) == 5 and len(b2) == 5 and len(b1 & b2) == 0
        and set(disp_ids) == (b1 | b2) == set(scope_ids) == set(attr_ids) == set(r00_reg.keys())
        and len(disp_ids) == 10 and r00_acc.get("decision") == "ACCEPTED_WITH_LIMITS"
    )
    check("V01", "10 家名单与 #59/#60 及 R00 验收名单 100% 一致且互斥零重复", v01_ok, f"b1={len(b1)} b2={len(b2)} overlap={len(b1&b2)}")

    # V02: Knowledge cutoff & H1(8) vs 9M(2) strict anchor separation
    h1_ids = {c["security_id"] for c in attr["companies"] if c["anchor_period"] == "20260630"}
    m9_ids = {c["security_id"] for c in attr["companies"] if c["anchor_period"] == "20260930"}
    anchor_mismatch = [
        c["security_id"] for c in attr["companies"]
        if c["anchor_period"] != s08_map[c["security_id"]]["s05_anchor_period"]
        or c["anchor_period"] != r00_reg[c["security_id"]]["anchor_period"]
    ]
    v02_ok = (
        attr.get("knowledge_as_of") == "2026-10-25"
        and len(h1_ids) == 8 and m9_ids == {"SZ:002979", "SH:688003"}
        and len(anchor_mismatch) == 0
        and all(r["knowledge_as_of"] == "2026-10-25" for r in scope)
    )
    check("V02", "知识截止日 2026-10-25，8 家 H1 与 2 家 9M 锚定期严格分离", v02_ok, f"h1={len(h1_ids)} m9={sorted(m9_ids)} mismatch={anchor_mismatch}")

    # V03: Pure robot revenue anti-pollution
    bad_anchor_pure = [r["security_id"] for r in scope if r["anchor_pure_robot_rev_cny"] != "UNKNOWN"]
    fy25_disclosed = {r["security_id"]: r["fy2025_pure_robot_rev_cny"] for r in scope if r["fy2025_pure_robot_rev_cny"] != "UNKNOWN"}
    v03_ok = len(bad_anchor_pure) == 0 and fy25_disclosed == {"SZ:300607": "300432856.32"}
    check("V03", "收入范围防污染：锚定期纯本体全 UNKNOWN，FY2025 仅拓斯达单列", v03_ok, f"bad_anchor={bad_anchor_pure} fy25={fy25_disclosed}")

    # V04: Zero-regression forbidden prose guard
    bad_hits = []
    for fname in ["robot_revenue_scope.csv", "attribution_review.json", "handoff.md", "financial_attribution_dispatch.csv"]:
        txt = (R01_DIR / fname).read_text(encoding="utf-8")
        for p in FORBIDDEN_PHRASES:
            if p in txt:
                bad_hits.append(f"{fname}:{p}")
    check("V04", "口径零回退守卫（双环/丰光/博实禁用表述 0 命中）", len(bad_hits) == 0, f"hits={bad_hits}")

    # V05: Exact S05 quality_flags reconciliation
    s05_diffs = []
    for c in attr["companies"]:
        sid = c["security_id"]
        qf = c["financial_metrics_from_s02_s05"]["s05_quality_flags"]
        for mid in ("M04", "M08", "M10", "M11", "M12"):
            ref = s05_flags[sid][mid]
            got = qf.get(mid, {})
            if got.get("metric_value") != ref["metric_value"] or got.get("rh_status") != ref["rh_status"] or got.get("metric_status") != ref["metric_status"]:
                s05_diffs.append(f"{sid}:{mid}")
    check("V05", "S05 五项质量指标(M04/M08/M10/M11/M12)与冻结表逐格一致", len(s05_diffs) == 0, f"diffs={s05_diffs}")

    # V06: Leading indicators & non-consolidated exclusions
    li_bad = []
    excl_bad = []
    must_excl = {
        "SZ:002747": ["酷卓"],
        "BJ:920593": ["脉塔", "中科灵犀"],
        "BJ:920491": ["奥感微"],
        "SH:688003": ["矽行"],
        "SZ:002698": ["思哲睿", "灵博"],
        "BJ:920510": ["唯实深蓝"],
    }
    scope_by_id = {r["security_id"]: r for r in scope}
    for c in attr["companies"]:
        sid = c["security_id"]
        li = c["leading_indicators_check"]
        for k in ("contract_liabilities", "backlog_orders", "cip_robot_capacity"):
            if not str(li.get(k, "")).strip():
                li_bad.append(f"{sid}:{k}")
        for kw in must_excl.get(sid, []):
            combined = scope_by_id[sid]["non_consolidated_excluded"] + " " + scope_by_id[sid]["consolidation_boundary_note"]
            if kw not in combined:
                excl_bad.append(f"{sid}:{kw}")
    check("V06", "先行指标完备且参股/拟投资不并表主体全部显式排除", len(li_bad) == 0 and len(excl_bad) == 0, f"li_bad={li_bad} excl_bad={excl_bad}")

    # V07: Manifest SHA-256, root digest, pure LF, no BOM
    in_bad, deliv_bad, crlf_bad, bom_bad = [], [], [], []
    for item in manifest["inputs"]:
        p = ROOT / item["path"]
        if not p.exists():
            in_bad.append(item["path"])
        else:
            b = read_lf_bytes(p)
            if len(b) != item["bytes"] or sha256_bytes(b) != item["sha256"]:
                in_bad.append(item["path"])
    for item in manifest["deliverables"]:
        p = ROOT / item["path"]
        if not p.exists():
            deliv_bad.append(item["path"])
        else:
            b = p.read_bytes()
            if b"\r\n" in b:
                crlf_bad.append(item["path"])
            if b.startswith(b"\xef\xbb\xbf"):
                bom_bad.append(item["path"])
            if len(b) != item["bytes"] or sha256_bytes(b) != item["sha256"]:
                deliv_bad.append(item["path"])
    recomputed_root = sha256_bytes(
        "\n".join(f"{d['path']}:{d['sha256']}" for d in sorted(manifest["deliverables"], key=lambda x: x["path"])).encode("utf-8")
    )
    root_ok = recomputed_root == manifest["manifest_root_digest"]
    check("V07", "manifest 输入/交付 SHA-256 与根摘要精确匹配，全部纯 LF 无 BOM",
          not in_bad and not deliv_bad and not crlf_bad and not bom_bad and root_ok,
          f"in_bad={in_bad} deliv_bad={deliv_bad} root_ok={root_ok} crlf={crlf_bad} bom={bom_bad}")

    # V08: Release guardrails
    v08_ok = (
        review.get("review_nature") == "SELF_CHECK"
        and review.get("R03_released") is False
        and review.get("R04_started") is False
        and review.get("issue_53_touched") is False
        and review.get("issue_53_status") == "OPEN"
    )
    check("V08", "放行边界：SELF_CHECK 不冒充独立验收，不放行 R03/R04，不触碰 #53", v08_ok, f"review_nature={review.get('review_nature')}")

    # V09: Byte-identical rebuild under fixed timestamp
    env = os.environ.copy()
    env["R01_FIXED_NOW"] = manifest["fixed_now"]
    before = {d["path"]: (ROOT / d["path"]).read_bytes() for d in manifest["deliverables"]}
    before["runs/issues/R01/manifest.json"] = (R01_DIR / "manifest.json").read_bytes()
    before["runs/issues/R01/review.json"] = (R01_DIR / "review.json").read_bytes()
    proc = subprocess.run([sys.executable, str(R01_DIR / "step_r01_build.py")], env=env, capture_output=True, text=True)
    after_diffs = [k for k, v in before.items() if (ROOT / k).read_bytes() != v]
    v09_ok = proc.returncode == 0 and len(after_diffs) == 0
    check("V09", "固定时间戳重跑构建逐字节一致", v09_ok, f"rc={proc.returncode} diffs={after_diffs}")

    # V10: Consistency of review decision with anomalies
    derived = "SELF_CHECK_PASS_WITH_LIMITS" if len(anomalies) == 0 else "NOT_ACCEPTED_PENDING_FIX"
    v10_ok = review.get("decision") == derived
    check("V10", "review.json 结论与独立重算异常清单一致", v10_ok, f"review={review.get('decision')} derived={derived}")

    passed = sum(1 for r in results if r[2])
    print(f"checks {passed}/{len(results)} PASS, anomalies={len(anomalies)}")
    return 0 if len(anomalies) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
