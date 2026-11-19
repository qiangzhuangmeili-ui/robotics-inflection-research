#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""步骤A：接手与版本对齐的机器校验（只读）。

不修改任何冻结文件、控制文件或既有验收。只在
runs/issues/S04/workbuddy_handoff_20261119/ 下写 takeover_receipt.json 与
baseline_manifest.json。

校验项：
  A1 归档 ZIP 字节数 + SHA256 与 11-16 在线回执一致
  A2 归档 344 成员逐个对清单哈希（readback_verified_members）
  A3 reviewed_view 三表哈希对 manifest
  A4 分区守恒 278 + 776 = 1054、唯一主键、互斥
  A5 六档决策计数与正式 review.json 一致
  A6 强制守卫在位：4 家截止日后、1 家锚点待重选、3 家项目模式 UNKNOWN、15 家 CE 质量未知
  A7 正式文件指纹（peer / 来源补充 / 资格 manifest / scope_contract / REPORT / 权威 B）
  A8 控制文件未被本工作单元改动（git status 白名单）
"""
import csv
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone, timedelta

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
OUT = os.path.join(REPO, "runs", "issues", "S04", "workbuddy_handoff_20261119")
PKG = os.path.join(REPO, "runs", "issues", "S04", "completion_20261114", "package_20261116")
FD = os.path.join(REPO, "runs", "issues", "S04", "completion_20261114", "final_delivery_20261116")
QUAL = os.path.join(REPO, "runs", "issues", "S04", "completion_20261114", "qualification_v3_20261115")
ZIP = os.path.join(PKG, "S04_completion_20261116_final_artifacts.zip")
READBACK = os.path.join(PKG, "drive_readback_20261116.zip")

EXPECTED_ZIP = {
    "bytes": 24347716,
    "sha256": "87f4f4ee8bb884cdfb9203a0e4958e53148b710681948e7957663bef9e9294d6",
}
EXPECTED_FINGERPRINTS = {
    "runs/issues/S04/completion_20261114/final_peer_review_20261116/peer_review.json":
        "ab249f1806e1997fb0f938b216aaeb17def7f460b03a08b694acafd7d2e7c924",
    "runs/issues/S00/completion_20261114/formal_gate_review_20261115/review.json":
        "d906efffa47321b68dec8e847c15122ca87cde17667cad59e75360396b42d2d1",
    "runs/issues/S04/completion_20261114/qualification_v3_20261115/manifest.json":
        "2be3081c47a634e960709bb16e9bf2327e109057bfbfd5509e5ce8fb27785144",
    "runs/issues/S04/completion_20261114/qualification_v3_20261115/scope_contract.json":
        "a856b9684458ac8461d28a399b422204b37c5a2726412096aa373ae868d33242",
    "runs/issues/S04/completion_20261114/final_delivery_20261116/REPORT.md":
        "494c59f686fcd73b193330d9e52205dcfad04206931fd4bbde89b0498e862adf",
    "runs/issues/S02/hangcha_restated_20261101/s00_v10/s00_v10.csv.gz":
        "fc312c52ace51feb37593c08cb8077c8a47012a7a239ef639d0fe8b745fe2025",
}
EXPECTED_DECISIONS = {
    "SHORTLIST_CANDIDATE_LIMITED": 278,
    "HOLD_FOR_DATA": 328,
    "NOT_SHORTLISTED": 171,
    "L2_NOT_IN_SCOPE": 272,
    "WATCH_AFTER_CUTOFF": 4,
    "PENDING_ANCHOR_RESELECTION": 1,
}
EXPECTED_CUTOFF = ["SH:603448", "SH:688836", "SZ:301348", "SZ:301699"]
EXPECTED_ANCHOR_PENDING = ["SZ:002083"]
EXPECTED_PROJECT_MODE_UNKNOWN = ["SZ:000988", "SZ:001208", "SZ:002530"]
EXPECTED_CE_15 = ["SZ:000801", "SZ:000967", "SZ:000988", "SZ:001208", "SZ:001311",
                  "SZ:002035", "SZ:002171", "SZ:002245", "SZ:002284", "SZ:002530",
                  "SZ:002705", "SZ:002765", "SZ:002801", "SZ:300611", "SZ:301584"]

CHECKS = []


def check(cid, name, ok, detail=None):
    CHECKS.append({"id": cid, "name": name, "pass": bool(ok), "detail": detail})
    return bool(ok)


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def read_rows(p):
    with open(p, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def main():
    os.makedirs(OUT, exist_ok=True)
    now = datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")

    # ---- A1 归档字节与哈希 ----
    zb = os.path.getsize(ZIP)
    zh = sha256_file(ZIP)
    check("A1a", "归档ZIP字节数与11-16在线回执一致", zb == EXPECTED_ZIP["bytes"],
          {"bytes": zb, "expected": EXPECTED_ZIP["bytes"]})
    check("A1b", "归档ZIP SHA256与11-16在线回执一致", zh == EXPECTED_ZIP["sha256"],
          {"sha256": zh, "expected": EXPECTED_ZIP["sha256"]})
    rb_ok = False
    rb = {"present": os.path.exists(READBACK)}
    if rb["present"]:
        rb["bytes"] = os.path.getsize(READBACK)
        rb["sha256"] = sha256_file(READBACK)
        rb_ok = (rb["bytes"] == EXPECTED_ZIP["bytes"] and rb["sha256"] == EXPECTED_ZIP["sha256"])
    check("A1c", "11-16 Drive 回读副本与本地归档逐字节相同", rb_ok, rb)

    # ---- A2 成员逐个哈希 ----
    import zipfile
    man = json.load(open(os.path.join(PKG, "S04_completion_20261116_final_artifacts.manifest.json"),
                         encoding="utf-8"))
    exp = {x["path"]: x for x in man["readback_verified_members"]}
    zf = zipfile.ZipFile(ZIP)
    names = zf.namelist()
    missing = sorted(set(exp) - set(names))
    extra = sorted(set(names) - set(exp))
    bad = []
    for n in names:
        if n not in exp:
            continue
        data = zf.read(n)
        if hashlib.sha256(data).hexdigest() != exp[n]["sha256"] or len(data) != exp[n]["bytes"]:
            bad.append(n)
    check("A2a", "归档成员集合与清单一致（无缺失/无多余）", not missing and not extra,
          {"members": len(names), "expected": len(exp), "missing": missing[:5], "extra": extra[:5]})
    check("A2b", "归档成员逐个SHA256与字节数匹配", not bad,
          {"verified": len(names) - len(bad), "bad": bad[:5]})

    # ---- A3 reviewed_view 哈希 ----
    rvman = json.load(open(os.path.join(FD, "reviewed_view", "manifest.json"), encoding="utf-8"))
    rv_bad = []
    for f in rvman["files"]:
        p = os.path.join(FD, "reviewed_view", os.path.basename(f["path"]))
        if sha256_file(p) != f["sha256"] or os.path.getsize(p) != f["bytes"]:
            rv_bad.append(f["path"])
    check("A3a", "reviewed_view 三表哈希与自身manifest一致", not rv_bad, {"bad": rv_bad})
    check("A3b", "reviewed_view manifest 指向11-16正式peer指纹",
          rvman.get("formal_review_sha256") == EXPECTED_FINGERPRINTS[
              "runs/issues/S04/completion_20261114/final_peer_review_20261116/peer_review.json"],
          {"formal_review_sha256": rvman.get("formal_review_sha256")})

    # ---- A4/A5 分区与决策 ----
    tp = read_rows(os.path.join(FD, "reviewed_view", "tight_pass.csv"))
    ob = read_rows(os.path.join(FD, "reviewed_view", "tight_observe.csv"))
    dl = read_rows(os.path.join(FD, "reviewed_view", "tight_decision_log.csv"))
    pid = [r["security_id"] for r in tp]
    oid = [r["security_id"] for r in ob]
    did = [r["security_id"] for r in dl]
    check("A4a", "tight_pass=278 / tight_observe=776 / decision_log=1054",
          len(tp) == 278 and len(ob) == 776 and len(dl) == 1054,
          {"pass": len(tp), "observe": len(ob), "log": len(dl)})
    check("A4b", "1054 唯一主键", len(set(did)) == 1054, {"unique": len(set(did))})
    check("A4c", "两分区互斥且并集等于全表", not (set(pid) & set(oid)) and (set(pid) | set(oid)) == set(did),
          {"overlap": len(set(pid) & set(oid)), "union_eq_log": (set(pid) | set(oid)) == set(did)})
    counts = {}
    for r in dl:
        counts[r["l2_decision"]] = counts.get(r["l2_decision"], 0) + 1
    check("A5a", "六档决策计数与正式review.json一致", counts == EXPECTED_DECISIONS,
          {"observed": counts, "expected": EXPECTED_DECISIONS})
    review = json.load(open(os.path.join(FD, "review.json"), encoding="utf-8"))
    check("A5b", "review.json 记录的分档与重算一致", review["decisions"] == EXPECTED_DECISIONS,
          {"review_decisions": review["decisions"]})

    # ---- A6 强制守卫 ----
    def ids_where(col, val="YES"):
        return sorted(r["security_id"] for r in dl if r[col].strip().upper() == val)

    cutoff = ids_where("cutoff_isolated")
    anchor = ids_where("anchor_reselection_pending")
    pmode = ids_where("project_mode_source_unknown")
    ce15 = sorted(r["security_id"] for r in dl if r["quality_source_state"] == "PENDING_CE_SOURCE")
    check("A6a", "4家截止日后隔离在位", cutoff == sorted(EXPECTED_CUTOFF), {"observed": cutoff})
    check("A6b", "1家锚点待重选在位（孚日股份）", anchor == EXPECTED_ANCHOR_PENDING, {"observed": anchor})
    check("A6c", "3家项目模式UNKNOWN在位", pmode == sorted(EXPECTED_PROJECT_MODE_UNKNOWN), {"observed": pmode})
    check("A6d", "15家CE质量未知在位且全部不在候选池", ce15 == sorted(EXPECTED_CE_15) and not (set(ce15) & set(pid)),
          {"observed": ce15, "in_pass": sorted(set(ce15) & set(pid))})

    # ---- A7 正式文件指纹 ----
    fp = {}
    fp_bad = []
    for rel, exp_sha in EXPECTED_FINGERPRINTS.items():
        p = os.path.join(REPO, rel.replace("/", os.sep))
        got = sha256_file(p)
        fp[rel] = got
        if got != exp_sha:
            fp_bad.append(rel)
    check("A7a", "六份正式文件/权威输入指纹全部匹配", not fp_bad, {"bad": fp_bad, "verified": len(fp)})

    # ---- A8 控制文件未被本工作单元写入；与在线差异如实登记 ----
    # 注意：工作区控制文件在本轮开始前就与 origin/main 不一致（11-16 遗留副本），
    # 因此判据不是「git status 干净」，而是「本轮未写入」+「差异如实登记、以在线为准」。
    session_start = datetime(2026, 11, 19, 20, 20, 0, tzinfo=timezone(timedelta(hours=8)))
    ctl = ["PROJECT_STATE.json", "data/active_issue.json"]
    mtimes = {}
    written = []
    for rel in ctl:
        p = os.path.join(REPO, rel.replace("/", os.sep))
        mt = datetime.fromtimestamp(os.path.getmtime(p), timezone(timedelta(hours=8)))
        mtimes[rel] = mt.isoformat(timespec="seconds")
        if mt >= session_start:
            written.append(rel)
    check("A8a", "控制文件在本轮开始前即未被写入（mtime 早于本工作单元）", not written,
          {"mtimes": mtimes, "written_this_run": written})

    diverged = {}
    try:
        for rel in ctl:
            local = json.loads(open(os.path.join(REPO, rel.replace("/", os.sep)), encoding="utf-8").read())
            online = json.loads(subprocess.run(["git", "show", "origin/main:" + rel], cwd=REPO,
                                               capture_output=True, text=True, encoding="utf-8").stdout)
            if local != online:
                only_local = sorted(set(local) - set(online))
                diff_keys = sorted(k for k in set(local) & set(online) if local[k] != online[k])
                diverged[rel] = {"only_local_keys": only_local, "differing_keys": diff_keys}
        check("A8b", "工作区控制文件与在线 main 的差异已定位（以在线为准，不覆盖）", True,
              {"diverged": diverged,
               "authority": "ONLINE_MAIN_READ_THIS_RUN",
               "action": "不写入、不覆盖；在线 blob 作为唯一控制依据"})
    except Exception as e:  # pragma: no cover
        check("A8b", "工作区控制文件与在线 main 的差异已定位", False, {"error": str(e)})

    ok = all(c["pass"] for c in CHECKS)
    receipt = {
        "artifact": "WORKBUDDY_S04_TAKEOVER_RECEIPT",
        "generated_at": now,
        "plan_version": "20261026_collection_first_v2",
        "actor": "WorkBuddy AI",
        "review_nature": "SELF_CHECK",
        "read_only_scope": True,
        "issue_claim": "NOT_CLAIMED",
        "lease_holder": "Codex / #53",
        "handoff_status": "NO_EXPLICIT_HANDOFF_RECORDED_READ_ONLY_PREP_ONLY",
        "online_control_read_at": now,
        "online_control_blobs": {
            "data/active_issue.json": "a8195c81d4ff2aab630c08bc843ef043eaf4350d",
            "PROJECT_STATE.json": "a334c5693c0cd7a10f874b4efa33ab993288048a",
            "data/issue_execution_plan.csv": "89aebf385b40bc92e932107110d01959ca84c264",
        },
        "online_main_commit": {
            "sha": "a308fab19c17ea0184df0d730f2a5723760f2ef4",
            "committed_at": "2026-11-16T02:43:15Z",
            "message": "Point current issue plan to verified scoped S04 handoff",
        },
        "control_state": {
            "active_issue_number": 53,
            "active_issue_key": "S00_ERRATA_REVIEW",
            "executor": "Codex",
            "current_gate": "S04_FORMAL_REVIEW_ARCHIVED_WITH_LIMITS_S05_LOCKED",
            "release_S04": True,
            "release_S04_scope": "TECHNICAL_MULTIMETRIC_SCREEN_AND_TARGETED_QC_ONLY",
            "release_S05": False,
            "issue_39_state": "OPEN",
            "issue_53_state": "OPEN",
        },
        "archive": {
            "local_zip": "runs/issues/S04/completion_20261114/package_20261116/S04_completion_20261116_final_artifacts.zip",
            "bytes": zb,
            "sha256": zh,
            "drive_file_id": "1VrpWyQct6xI5PpRdGNs6KFZmubbspYEA",
            "drive_url": "https://drive.google.com/file/d/1VrpWyQct6xI5PpRdGNs6KFZmubbspYEA/view?usp=drivesdk",
            "parent_folder_id": "13oqd9t1Lv2GgDIMUVZbzaDbmLuTa7CWa",
            "live_drive_fetch": "ACCESS_BLOCKED",
            "live_drive_probe": {
                "uc_download": "303 -> drive.usercontent.google.com -> 200 text/html Google sign-in (971,576 bytes)",
                "api_v3_files_get": "403",
                "interpretation": "无 Drive 凭据，无法在本轮重新下载远端二进制；不使用任何绕过登录的方式",
            },
            "verification_mode": "OFFLINE_SNAPSHOT_MATCHING_VERIFIED_REMOTE_RECEIPT",
            "remote_binary_evidence": "11-16 回执记录的 Drive 回读副本 drive_readback_20261116.zip 与本归档逐字节相同",
            "members_verified": len(names) - len(bad),
            "members_expected": len(exp),
        },
        "formal_records_read": [
            "runs/issues/S04/completion_20261114/final_delivery_20261116/review.json",
            "runs/issues/S04/completion_20261114/final_delivery_20261116/REPORT.md",
            "runs/issues/S04/completion_20261114/final_delivery_20261116/reviewed_view/manifest.json",
            "runs/issues/S04/completion_20261114/final_peer_review_20261116/peer_review.json",
            "runs/issues/S00/completion_20261114/formal_gate_review_20261115/review.json",
            "runs/issues/S04/completion_20261114/qualification_v3_20261115/scope_contract.json",
            "runs/issues/S00/errata_20261111_v5/codex_ruling_round5.md",
        ],
        "checks": CHECKS,
        "checks_passed": "%d/%d" % (sum(1 for c in CHECKS if c["pass"]), len(CHECKS)),
        "decision": "TAKEOVER_VERIFIED_READ_ONLY" if ok else "STOP_AT_TAKEOVER",
        "blocking_failures": [c["id"] for c in CHECKS if not c["pass"]],
        "S05_release": False,
        "notes": [
            "本回执是自检，不是独立验收；不替代 11-16 正式审查与 peer 记录。",
            "未领取 #39/#53，未改动 PROJECT_STATE.json 与 data/active_issue.json。",
            "未重新下载 Drive 二进制；归档核验建立在 11-16 已 VERIFIED 回执与本机逐字节回读副本之上。",
        ],
    }
    with open(os.path.join(OUT, "takeover_receipt.json"), "w", encoding="utf-8") as f:
        json.dump(receipt, f, ensure_ascii=False, indent=2)

    baseline = {
        "artifact": "S04_HANDOFF_BASELINE_MANIFEST",
        "generated_at": now,
        "plan_version": "20261026_collection_first_v2",
        "frozen_inputs": {rel: {"sha256": sha} for rel, sha in fp.items()},
        "frozen_delivery": {
            "tight_pass_rows": len(tp),
            "tight_observe_rows": len(ob),
            "decision_log_rows": len(dl),
            "decisions": counts,
            "reviewed_view_manifest_sha256": sha256_file(os.path.join(FD, "reviewed_view", "manifest.json")),
            "final_delivery_review_sha256": sha256_file(os.path.join(FD, "review.json")),
            "data_manifest_sha256": sha256_file(os.path.join(FD, "data_manifest.json")),
        },
        "rules": {
            "effective_rules_version": "S01_SCREEN_RULES_V3_PROVENANCE_20261114",
            "effective_rules_sha256": sha256_file(
                os.path.join(REPO, "runs/issues/S01/screen_rules_v3_provenance_20261114.json")),
            "immutable_v3_sha256": sha256_file(os.path.join(REPO, "runs/issues/S01/screen_rules_v3.json")),
            "knowledge_as_of": "2026-10-25",
            "thresholds_changed": False,
            "cutoff_changed": False,
        },
        "guards": {
            "cutoff_isolated": cutoff,
            "anchor_reselection_pending": anchor,
            "project_mode_unknown": pmode,
            "quality_source_pending_ce": ce15,
        },
        "not_modified": [
            "PROJECT_STATE.json", "data/active_issue.json",
            "runs/issues/S04/completion_20261114/**", "runs/issues/S00/**",
            "runs/issues/S01/screen_rules_v3*.json",
            "runs/issues/S02/hangcha_restated_20261101/s00_v10/**",
        ],
    }
    with open(os.path.join(OUT, "baseline_manifest.json"), "w", encoding="utf-8") as f:
        json.dump(baseline, f, ensure_ascii=False, indent=2)

    print(json.dumps({"checks_passed": receipt["checks_passed"],
                      "decision": receipt["decision"],
                      "blocking": receipt["blocking_failures"]}, ensure_ascii=False))
    for c in CHECKS:
        if not c["pass"]:
            print("FAIL", c["id"], c["name"], json.dumps(c["detail"], ensure_ascii=False)[:300])
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
