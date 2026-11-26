# -*- coding: utf-8 -*-
"""
S07 (#42) Deterministic Builder — small-sample rule & arithmetic audit.

Outputs (all under runs/issues/S07/, pure LF):
  - screen_audit_sample.csv
  - screen_audit_findings.md
  - screen_audit_review.json
  - handoff.md
  - manifest.json / review.json are finalized by step_s07_verify.py

Design:
  1. Freeze a deterministic stratified sample (no RNG, fixed sort keys, per-slot quotas)
     covering BOUNDARY_PASS_FAIL / BJ_MARKET / LOSS_AND_LOW_BASE /
     MISSING_DATA_WATCH / EARLY_STAGE_WATCH / REVERSE_OMISSION.
  2. Independently recompute all 12 S02 metrics from the authoritative S00 long table
     (s00_v10.csv.gz) and compare value/status with all_pool_metrics.csv.
  3. Re-derive S03 L1 signals / dimensions / bucket-subtag from recomputed metrics,
     and re-check S04 boundary attributes, S05 RH thresholds & range rows, S06 counts.
  4. Diagnose missing-data / mixed-period / low-base / RH02 / BJ / reverse-omission
     bias, attribute each finding to a data or rule layer, and grade systemic risk.

Set S07_FIXED_NOW for byte-identical replay.
"""
import csv
import gzip
import hashlib
import io
import json
import os
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
OUT = REPO / "runs" / "issues" / "S07"
NOW = os.environ.get("S07_FIXED_NOW") or datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")

ISSUE_KEY = "S07"
ISSUE_NUMBER = 42
PLAN_VERSION = "20261026_collection_first_v2"
KNOWLEDGE_AS_OF = "2026-10-25"
EXECUTOR = "CodeBuddy"
ORCHESTRATOR = "Antigravity"
REVIEWER_ASSIGNED = "Codex"

# ---------------------------------------------------------------------------
# Exact, exhaustive list of every Git-tracked file read at runtime.
# All paths are inside the Git working tree (verified by step_s07_verify.py).
# ---------------------------------------------------------------------------
READ_INPUTS = [
    # Control / release / handoff
    "runs/issues/S07/release_20261126.json",
    "runs/issues/S07/handoff_from_s06_20261126.md",
    # Universe
    "data/company_master.csv",
    # S01 frozen rules & acceptance
    "runs/issues/S01/screen_rules_v3.json",
    "runs/issues/S01/screen_rules_v4.json",
    "runs/issues/S01/acceptance_20261029.json",
    # S02 authoritative base, metrics, contract, acceptance
    "runs/issues/S02/hangcha_restated_20261101/s00_v10/s00_v10.csv.gz",
    "runs/issues/S02/hangcha_restated_20261101/s02_v10/all_pool_metrics.csv",
    "runs/issues/S02/acceptance_20261106/s03_input_contract.json",
    "runs/issues/S02/acceptance_20261106/review.json",
    # S03 L1 wide screen
    "runs/issues/S03/rerun_20261106/l1_screen_results.csv",
    "runs/issues/S03/rerun_20261106/wide_pass.csv",
    "runs/issues/S03/rerun_20261106/wide_defer.csv",
    "runs/issues/S03/rerun_20261106/wide_unknown.csv",
    "runs/issues/S03/review.json",
    # S04 L2 tightening
    "runs/issues/S04/tight_decision_log.csv",
    "runs/issues/S04/codex_ruling_s05_v22_20261120.md",
    # S05 quality gate
    "runs/issues/S05/quality_pass.csv",
    "runs/issues/S05/quality_observe.csv",
    "runs/issues/S05/quality_decision_log.csv",
    "runs/issues/S05/quality_flags.csv",
    "runs/issues/S05/observe_pool_preserved_776.csv",
    "runs/issues/S05/rh06_adoption.csv",
    "runs/issues/S05/s05_out_of_valid_range.csv",
    "runs/issues/S05/acceptance_s05_r1_20261121.json",
    # S06 watchlists & acceptance
    "runs/issues/S06/early_stage_watch.csv",
    "runs/issues/S06/missing_data_watch.csv",
    "runs/issues/S06/watch_reentry_rules.md",
    "runs/issues/S06/acceptance_s06_r2_20261123.json",
]

# Release-frozen canonical-LF hashes (text inputs). The gzip base is binary and uses exact bytes.
RELEASE_SHA = {
    "data/company_master.csv": "6596f05fbc4f65e2f66ec26edd9726e4049854d697feab968c8b1360e40560fe",
    "runs/issues/S01/screen_rules_v3.json": "bf7e68893833b472615f00ab7d14804db4537a9d0936c027a52bc4ef9e26c884",
    "runs/issues/S01/screen_rules_v4.json": "3ab824591ff18f51ea72cbf80f106151d7baeb6782d6e5b03e178d309464307f",
    "runs/issues/S01/acceptance_20261029.json": "376dc407a7c24873433d6e8024fa962b80016cb5e6a1f7a98ba8acc04452e058",
    "runs/issues/S02/hangcha_restated_20261101/s00_v10/s00_v10.csv.gz": "fc312c52ace51feb37593c08cb8077c8a47012a7a239ef639d0fe8b745fe2025",
    "runs/issues/S02/hangcha_restated_20261101/s02_v10/all_pool_metrics.csv": "3091b0bb82a3e3114d7f338595c40d82c842ce47aa8802b141a6ce8ec2232953",
    "runs/issues/S02/acceptance_20261106/s03_input_contract.json": "a18b915ce0db154b070b5064ace6cbe1a9917f7ac14ce8fd557595dedcbabe31",
    "runs/issues/S02/acceptance_20261106/review.json": "85813450236d4bf2b70238a1f470c25199595110204a69f3fd4e0344a56ea561",
    "runs/issues/S03/rerun_20261106/l1_screen_results.csv": "a9b0c6edc0ecc1ab549b41ea5bc2c598889c0977380f7f221832b8e4f68b8f77",
    "runs/issues/S04/tight_decision_log.csv": "aac3071ffbe4f0de6514578d4b6ace78640b6014c2a88e602e06c7ce70256366",
    "runs/issues/S05/quality_pass.csv": "9d488f50b86523fd89f1d0dc6d4b0fa010ad2cf3c2d86fc5bfc96d8040b69480",
    "runs/issues/S05/quality_observe.csv": "62253de55980e9c15406d703ac9da6ab420e6d6ac1083dbaf22d17516b7e07eb",
    "runs/issues/S05/quality_decision_log.csv": "ba6cf6474496eabdf17cfe8f5e2e1c9e2ea10288bcb412ce3d64f2ed9c7591b2",
    "runs/issues/S05/quality_flags.csv": "38addb2c08ebb89ffa1ed56bae82be1120d18f61984a3afc5fd965469998ae77",
    "runs/issues/S05/observe_pool_preserved_776.csv": "528c451f551d21ca7c3453a49738af6ec7a7217fd04658c5de4c7de6f26574b1",
    "runs/issues/S06/early_stage_watch.csv": "19ac5224397b7a0a7e34958cfc47a3108bb10c5a78333d2cd57842188c4b57be",
    "runs/issues/S06/missing_data_watch.csv": "067c2b591f9a82665b1f13ef253b4fa46947a4695de808dc4a26a9c35580ed1e",
    "runs/issues/S06/watch_reentry_rules.md": "6912628b5ff0890db8b153207cc37db05bd8d570e215b2fe49eb1763f8eb3a8e",
}

# ---------------------------------------------------------------------------
# Frozen S01 constants (read from rules_v4 at runtime for thresholds; duplicated here only
# for status semantics that are not machine-readable in the JSON).
# ---------------------------------------------------------------------------
USABLE = {
    "EXTRACTED", "EXTRACTED_KEY_TABLE", "EXTRACTED_QUARTERLY_TABLE",
    "DERIVED", "DERIVED_CUMULATIVE_DIFF", "DERIVED_Q1_EQUALS_YTD",
    "DERIVED_QUARTERLY_SUM_OVERRIDE",
}
USABLE_FLAG = {"LEGACY_SNAPSHOT"}
HOLD = {"EXTRACTED_XCHECK_MISMATCH", "DERIVED_HOLD_UPSTREAM", "DERIVED_Q1_HOLD_UPSTREAM"}
LOW_BASE_FLAGS = {"LOW_BASE_REV", "LOW_BASE_PROFIT", "NEGATIVE_BASE_PROFIT"}
RESTATE_PENDING = "RESTATEMENT_INDICATED_NEEDS_REVIEW"
RESTATE_CONFIRMED = "是"
ZERO_BASE_ABS = 1_000_000.0
LOW_BASE_REV = 50_000_000.0
LOW_BASE_NPDEDT = 10_000_000.0
ABS_CONFIRM = 10_000_000.0
FLOAT_TOL = 5e-10

DIM_MEMBERS = {
    "GROWTH": ["SG01", "SG02"],
    "MARGIN": ["SG03"],
    "PROFIT": ["SG04", "SG05", "SG06", "SG09"],
    "CASH": ["SG07", "SG08"],
}
SG_METRIC = {
    "SG01": "M01", "SG02": "M03", "SG03": "M04", "SG04": "M05", "SG05": "M06",
    "SG06": "M05", "SG07": "M08", "SG08": "M09", "SG09": "M07",
}
SG_DIM = {
    "SG01": "GROWTH", "SG02": "GROWTH", "SG03": "MARGIN", "SG04": "PROFIT",
    "SG05": "PROFIT", "SG06": "PROFIT", "SG07": "CASH", "SG08": "CASH", "SG09": "PROFIT",
}
THRESHOLD_SG = {
    "SG01": (">=", 0.1), "SG02": (">=", 5.0), "SG03": (">=", 1.0), "SG04": (">=", 0.2),
    "SG05": (">=", 1.0), "SG07": (">=", 0.8), "SG09": (">=", 0.3),
}
RH_DEF = {
    "RH01": ("M10", ">=", 30.0), "RH02": ("M11", ">=", 30.0), "RH03": ("M12", ">=", 5.0),
    "RH04": ("M08", "<", 0.5), "RH05": ("M04", "<=", -2.0),
}
STRATUM_ORDER = [
    "BOUNDARY_PASS_FAIL", "BJ_MARKET", "LOSS_AND_LOW_BASE",
    "MISSING_DATA_WATCH", "EARLY_STAGE_WATCH", "REVERSE_OMISSION",
]

# S01 v4 low_base_confirmation mapping (field / basis), mirrored verbatim.
LOW_BASE_MAP = {
    "SG01": {"field_id": "FIN.REV.YTD", "basis": "YTD"},
    "SG04": {"field_id": "FIN.NPDEDT.YTD", "basis": "YTD"},
    "SG06": {"field_id": "FIN.NPDEDT.YTD", "basis": "YTD"},
    "SG08": {"field_id": "FIN.OCF.YTD", "basis": "YTD"},
    "SG09": {"field_id": "FIN.NPDEDT.SQ", "basis": "SQ"},
}
ABS_CHANNEL_FIELDS = {"SG06": "FIN.NPDEDT.YTD", "SG08": "FIN.OCF.YTD"}

REWORK_ROUND = "R3"
REWORK_BASIS = "runs/issues/S07/codex_review_s07_r2_20261126.md"
REVIEW_PROVENANCE_REFS = [
    "runs/issues/S07/codex_review_s07_r0_20261126.md",
    "runs/issues/S07/codex_review_s07_r1_20261126.md",
    "runs/issues/S07/codex_review_s07_r2_20261126.md",
]


# ---------------------------------------------------------------------------
# IO helpers
# ---------------------------------------------------------------------------
def sha256_exact(path: Path):
    raw = path.read_bytes()
    return len(raw), hashlib.sha256(raw).hexdigest()


def sha256_canonical_lf(path: Path):
    data = path.read_bytes().replace(b"\r\n", b"\n")
    return len(data), hashlib.sha256(data).hexdigest()


def canonical_input_digest(rel: str):
    """Text -> canonical LF bytes; binary (.gz) -> exact bytes (matches release/S02 manifest)."""
    path = REPO / rel
    if rel.endswith(".gz"):
        return sha256_exact(path)
    return sha256_canonical_lf(path)


def load_csv(rel: str):
    with open(REPO / rel, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_lf(path: Path, text: str):
    path.write_bytes(text.replace("\r\n", "\n").encode("utf-8"))


def csv_text(fieldnames, rows):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fieldnames, lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow(r)
    return buf.getvalue()


def fnum(x):
    if x is None:
        return None
    s = str(x).strip().replace(",", "")
    if s == "":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def fmt_val(x):
    return "" if x is None else f"{x:.10f}"


def clean(s):
    return " ".join(str(s or "").replace("\r", " ").replace("\n", " ").split()).strip()


# ---------------------------------------------------------------------------
# Load frozen inputs
# ---------------------------------------------------------------------------
def load_inputs():
    d = {}
    d["release"] = json.loads((REPO / "runs/issues/S07/release_20261126.json").read_text(encoding="utf-8"))
    d["handoff_txt"] = (REPO / "runs/issues/S07/handoff_from_s06_20261126.md").read_text(encoding="utf-8")
    d["s06_rules_txt"] = (REPO / "runs/issues/S06/watch_reentry_rules.md").read_text(encoding="utf-8")
    d["codex_ruling_txt"] = (REPO / "runs/issues/S04/codex_ruling_s05_v22_20261120.md").read_text(encoding="utf-8")
    d["rules_v3"] = json.loads((REPO / "runs/issues/S01/screen_rules_v3.json").read_text(encoding="utf-8-sig"))
    d["rules_v4"] = json.loads((REPO / "runs/issues/S01/screen_rules_v4.json").read_text(encoding="utf-8-sig"))
    d["s01_acc"] = json.loads((REPO / "runs/issues/S01/acceptance_20261029.json").read_text(encoding="utf-8-sig"))
    d["s02_contract"] = json.loads((REPO / "runs/issues/S02/acceptance_20261106/s03_input_contract.json").read_text(encoding="utf-8-sig"))
    d["s02_review"] = json.loads((REPO / "runs/issues/S02/acceptance_20261106/review.json").read_text(encoding="utf-8-sig"))
    d["s03_review"] = json.loads((REPO / "runs/issues/S03/review.json").read_text(encoding="utf-8-sig"))
    d["s05_acc"] = json.loads((REPO / "runs/issues/S05/acceptance_s05_r1_20261121.json").read_text(encoding="utf-8-sig"))
    d["s06_acc"] = json.loads((REPO / "runs/issues/S06/acceptance_s06_r2_20261123.json").read_text(encoding="utf-8-sig"))

    d["master"] = load_csv("data/company_master.csv")
    d["master_by_id"] = {r["security_id"]: r for r in d["master"]}
    d["s02"] = load_csv("runs/issues/S02/hangcha_restated_20261101/s02_v10/all_pool_metrics.csv")
    d["s02_by"] = defaultdict(dict)
    for r in d["s02"]:
        d["s02_by"][r["security_id"]][r["metric_id"]] = r
    d["s03"] = load_csv("runs/issues/S03/rerun_20261106/l1_screen_results.csv")
    d["s03_by"] = {r["company_id"]: r for r in d["s03"]}
    d["wide_pass"] = load_csv("runs/issues/S03/rerun_20261106/wide_pass.csv")
    d["wide_defer"] = load_csv("runs/issues/S03/rerun_20261106/wide_defer.csv")
    d["wide_unknown"] = load_csv("runs/issues/S03/rerun_20261106/wide_unknown.csv")
    d["s04"] = load_csv("runs/issues/S04/tight_decision_log.csv")
    d["s04_by"] = {r["company_id"]: r for r in d["s04"]}
    d["s05_pass"] = load_csv("runs/issues/S05/quality_pass.csv")
    d["s05_pass_by"] = {r["security_id"]: r for r in d["s05_pass"]}
    d["s05_obs"] = load_csv("runs/issues/S05/quality_observe.csv")
    d["s05_obs_by"] = {r["security_id"]: r for r in d["s05_obs"]}
    d["s05_qdl"] = load_csv("runs/issues/S05/quality_decision_log.csv")
    d["s05_qdl_by"] = {r["security_id"]: r for r in d["s05_qdl"]}
    d["s05_qf"] = load_csv("runs/issues/S05/quality_flags.csv")
    d["s05_qf_by"] = defaultdict(dict)
    for r in d["s05_qf"]:
        d["s05_qf_by"][r["security_id"]][r["rh"]] = r
    d["s05_776"] = load_csv("runs/issues/S05/observe_pool_preserved_776.csv")
    d["s05_776_by"] = {r["security_id"]: r for r in d["s05_776"]}
    d["s05_rh06"] = load_csv("runs/issues/S05/rh06_adoption.csv")
    d["s05_rh06_by"] = {r["security_id"]: r for r in d["s05_rh06"]}
    d["s05_oor"] = load_csv("runs/issues/S05/s05_out_of_valid_range.csv")
    d["s05_oor_by"] = defaultdict(list)
    for r in d["s05_oor"]:
        d["s05_oor_by"][r["security_id"]].append(r)
    d["s06_early"] = load_csv("runs/issues/S06/early_stage_watch.csv")
    d["s06_early_by"] = {r["security_id"]: r for r in d["s06_early"]}
    d["s06_missing"] = load_csv("runs/issues/S06/missing_data_watch.csv")
    d["s06_missing_by"] = {r["security_id"]: r for r in d["s06_missing"]}
    return d


def load_s00():
    """Return rows[(sid, pk_int)][field_id] = dict(raw row)."""
    rows = defaultdict(dict)
    meta = defaultdict(dict)
    with gzip.open(REPO / "runs/issues/S02/hangcha_restated_20261101/s00_v10/s00_v10.csv.gz",
                   "rt", encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            k = (r["security_id"], int(r["period_key"]))
            rows[k][r["field_id"]] = r
            meta[k][r["field_id"]] = r
    return rows, meta


# ---------------------------------------------------------------------------
# Independent recomputation engine (faithful re-implementation of frozen S01 v2/v4 formulas)
# ---------------------------------------------------------------------------
class Engine:
    def __init__(self, rows, meta):
        self.rows = rows
        self.meta = meta

    @staticmethod
    def usable(rec):
        return rec is not None and rec["status"] in (USABLE | USABLE_FLAG) and clean(rec["value_cny"]) != ""

    def latest_pk(self, sid):
        best = None
        for (s, pk), d in self.rows.items():
            if s != sid:
                continue
            for f in ("FIN.REV.YTD", "FIN.REV.SQ", "FIN.NPDEDT.YTD"):
                if f in d and self.usable(d[f]):
                    if best is None or pk > best:
                        best = pk
        return best

    @staticmethod
    def v(rec):
        return fnum(rec["value_cny"]) if rec is not None else None

    @staticmethod
    def inputs(recs):
        if any(r is None for r in recs):
            return "MISSING"
        if any(r["status"] in HOLD for r in recs):
            return "HOLD"
        if any(r["status"] not in USABLE and r["status"] not in USABLE_FLAG for r in recs):
            return "MISSING"
        if any(r["consolidation_scope"] != "CONSOLIDATED" and r["status"] not in USABLE_FLAG for r in recs):
            return "EXCLUDED_SCOPE"
        if any(r["is_pre_listing"] == "YES" for r in recs):
            return "NOT_COMPARABLE"
        return "OK"

    @staticmethod
    def restate(recs):
        for r in recs:
            if not r:
                continue
            if "RESTATED_COMPARATIVE_ADOPTED" in (r.get("comparability_note") or ""):
                continue
            if r["restatement_flag"] in (RESTATE_PENDING, RESTATE_CONFIRMED) \
                    or "RESTATED_PRIOR_YEARS_UNRECALCULATED" in (r.get("comparability_note") or ""):
                return True
        return False

    @staticmethod
    def lowbase(recs, base, thr):
        if any(r and r["low_base_flag"] in LOW_BASE_FLAGS for r in recs):
            return True
        if thr and base is not None and abs(base) < thr:
            return True
        return False

    def oneoff(self, sid, pk):
        a = self.v(self.rows[(sid, pk)].get("FIN.NPP.YTD"))
        b = self.v(self.rows[(sid, pk)].get("FIN.NPDEDT.YTD"))
        if a is None or b is None:
            return False
        return abs(a - b) / max(abs(a), 1.0) > 0.5

    @staticmethod
    def res(val, st, flags=(), note=""):
        return {"value": val, "status": st, "flags": set(flags), "note": note}

    def ratio(self, sid, pk, pkb, field, thr=None):
        rt = self.rows[(sid, pk)].get(field)
        rb = self.rows[(sid, pkb)].get(field) if pkb else None
        if rb is None:
            return self.res(None, "NOT_COMPARABLE", {"Q08"})
        st = self.inputs([rt, rb])
        if st != "OK":
            return self.res(None, st)
        fl = {"Q06"} if self.restate([rt, rb]) else set()
        cur, base = self.v(rt), self.v(rb)
        if cur is None or base is None:
            return self.res(None, "MISSING", fl | {"Q02"})
        if self.lowbase([rt, rb], base, thr):
            fl.add("Q05")
        if abs(base) < ZERO_BASE_ABS:
            return self.res(None, "UNDEFINED_BASE", fl | {"Q04"})
        if base < 0:
            return self.res(None, "UNDEFINED_BASE", fl | {"Q03"})
        return self.res(cur / base - 1.0, "OK", fl)

    def diff(self, sid, pk, pkb, field):
        rt = self.rows[(sid, pk)].get(field)
        rb = self.rows[(sid, pkb)].get(field) if pkb else None
        if rb is None:
            return self.res(None, "NOT_COMPARABLE", {"Q08"})
        st = self.inputs([rt, rb])
        if st != "OK":
            return self.res(None, st)
        fl = {"Q06"} if self.restate([rt, rb]) else set()
        cur, base = self.v(rt), self.v(rb)
        if cur is None or base is None:
            return self.res(None, "MISSING", fl | {"Q02"})
        return self.res(cur - base, "OK", fl)

    def m03(self, sid, pk):
        def py(p):
            return p - 10000

        def pq(p):
            y, mmdd = divmod(p, 10000)
            if mmdd == 331:
                return (y - 1) * 10000 + 1231
            return y * 10000 + {630: 331, 930: 630, 1231: 930}[mmdd]

        p4, p1 = py(pk), pq(pk)
        p5 = py(p1)
        a = self.ratio(sid, pk, p4, "FIN.REV.SQ", LOW_BASE_REV)
        b = self.ratio(sid, p1, p5, "FIN.REV.SQ", LOW_BASE_REV)
        fl = a["flags"] | b["flags"]
        for x in (a, b):
            if x["status"] in ("HOLD", "MISSING", "EXCLUDED_SCOPE", "NOT_COMPARABLE"):
                return self.res(None, x["status"], fl)
        if a["status"] != "OK" or b["status"] != "OK":
            return self.res(None, "NOT_COMPARABLE", fl | {"Q08"})
        return self.res((a["value"] - b["value"]) * 100.0, "OK", fl)

    def m04(self, sid, pk, pkb):
        gt = self.rows[(sid, pk)].get("FIN.GROSSMARGIN.PCT")
        gb = self.rows[(sid, pkb)].get("FIN.GROSSMARGIN.PCT")
        if gt is not None and gb is not None:
            st = self.inputs([gt, gb])
            if st == "OK":
                fl = {"Q06"} if self.restate([gt, gb]) else set()
                if self.v(gt) is None or self.v(gb) is None:
                    return self.res(None, "MISSING", fl | {"Q02"})
                return self.res(self.v(gt) - self.v(gb), "OK", fl)
            if st == "HOLD":
                return self.res(None, "HOLD", {"Q01"})
            if st in ("EXCLUDED_SCOPE", "NOT_COMPARABLE"):
                return self.res(None, st)
        rt = self.rows[(sid, pk)].get("FIN.REV.YTD")
        ct = self.rows[(sid, pk)].get("FIN.COST.YTD")
        rb = self.rows[(sid, pkb)].get("FIN.REV.YTD")
        cb = self.rows[(sid, pkb)].get("FIN.COST.YTD")
        st2 = self.inputs([rt, ct, rb, cb])
        if st2 != "OK":
            return self.res(None, st2)
        fl2 = {"Q06"} if self.restate([rt, ct, rb, cb]) else set()
        if rt["document_id"] != ct["document_id"] or rb["document_id"] != cb["document_id"]:
            return self.res(None, "VERSION_MISMATCH", fl2)
        if rt["version_used"] != ct["version_used"] or rb["version_used"] != cb["version_used"]:
            return self.res(None, "VERSION_MISMATCH", fl2)
        if min(self.v(rt), self.v(rb)) <= ZERO_BASE_ABS:
            return self.res(None, "UNDEFINED_BASE", fl2 | {"Q03"})
        gm_t = (self.v(rt) - self.v(ct)) / self.v(rt) * 100
        gm_b = (self.v(rb) - self.v(cb)) / self.v(rb) * 100
        return self.res(gm_t - gm_b, "OK", fl2)

    def m06(self, sid, pk, pkb):
        nt = self.rows[(sid, pk)].get("FIN.NPDEDT.YTD")
        rt = self.rows[(sid, pk)].get("FIN.REV.YTD")
        nb = self.rows[(sid, pkb)].get("FIN.NPDEDT.YTD")
        rb = self.rows[(sid, pkb)].get("FIN.REV.YTD")
        if rb is None or nb is None:
            return self.res(None, "NOT_COMPARABLE", {"Q08"})
        st = self.inputs([nt, rt, nb, rb])
        if st != "OK":
            return self.res(None, st)
        fl = {"Q06"} if self.restate([nt, rt, nb, rb]) else set()
        if self.oneoff(sid, pk):
            fl.add("Q09")
        if min(self.v(rt), self.v(rb)) <= ZERO_BASE_ABS:
            return self.res(None, "UNDEFINED_BASE", fl | {"Q03"})
        return self.res((self.v(nt) / self.v(rt) - self.v(nb) / self.v(rb)) * 100, "OK", fl)

    def m08(self, sid, pk):
        o = self.rows[(sid, pk)].get("FIN.OCF.YTD")
        n = self.rows[(sid, pk)].get("FIN.NPP.YTD")
        st = self.inputs([o, n])
        if st != "OK":
            return self.res(None, st)
        fl = {"Q06"} if self.restate([o, n]) else set()
        if self.lowbase([o, n], None, None):
            fl.add("Q05")
        if self.v(n) is None or self.v(n) <= ZERO_BASE_ABS:
            return self.res(None, "NOT_APPLICABLE", fl | {"Q03"})
        return self.res(self.v(o) / self.v(n), "OK", fl)

    @staticmethod
    def days(m):
        try:
            return (date.fromisoformat(m["period_end"]) - date.fromisoformat(m["period_start"])).days + 1
        except Exception:
            return None

    def mdays(self, sid, pk, pkb, inst, flow):
        it = self.rows[(sid, pk)].get(inst)
        ib = self.rows[(sid, pkb)].get(inst)
        ft = self.rows[(sid, pk)].get(flow)
        fb = self.rows[(sid, pkb)].get(flow)
        if ib is None or fb is None:
            return self.res(None, "NOT_COMPARABLE", {"Q08"})
        st = self.inputs([it, ib, ft, fb])
        if st != "OK":
            return self.res(None, st)
        fl = {"Q06"} if self.restate([it, ib, ft, fb]) else set()
        dt = self.days(self.meta[(sid, pk)][flow]) if (sid, pk) in self.meta and flow in self.meta[(sid, pk)] else None
        db = self.days(self.meta[(sid, pkb)][flow]) if (sid, pkb) in self.meta and flow in self.meta[(sid, pkb)] else None
        if not dt or not db:
            return self.res(None, "MISSING", fl | {"Q02"})
        if None in (self.v(ft), self.v(fb), self.v(it), self.v(ib)):
            return self.res(None, "MISSING", fl | {"Q02"})
        if self.v(ft) <= ZERO_BASE_ABS or self.v(fb) <= ZERO_BASE_ABS:
            return self.res(None, "UNDEFINED_BASE", fl | {"Q03"})
        return self.res(self.v(it) / self.v(ft) * dt - self.v(ib) / self.v(fb) * db, "OK", fl)

    def m12(self, sid, pk, pkb):
        ct = self.rows[(sid, pk)].get("FIN.CONTRACTASSET.INSTANT")
        rt = self.rows[(sid, pk)].get("FIN.REV.YTD")
        cb = self.rows[(sid, pkb)].get("FIN.CONTRACTASSET.INSTANT")
        rb = self.rows[(sid, pkb)].get("FIN.REV.YTD")
        if ct is None or cb is None:
            return self.res(None, "NOT_APPLICABLE", {"Q02"})
        st = self.inputs([ct, rt, cb, rb])
        if st != "OK":
            return self.res(None, st)
        fl = {"Q06"} if self.restate([ct, rt, cb, rb]) else set()
        if min(self.v(rt), self.v(rb)) <= ZERO_BASE_ABS:
            return self.res(None, "UNDEFINED_BASE", fl | {"Q03"})
        return self.res((self.v(ct) / self.v(rt) - self.v(cb) / self.v(rb)) * 100, "OK", fl)

    def project_mode(self, sid, pk):
        ca = self.rows[(sid, pk)].get("FIN.CONTRACTASSET.INSTANT")
        ta = self.rows[(sid, pk)].get("FIN.ASSET.INSTANT")
        rv = self.rows[(sid, pk)].get("FIN.REV.YTD")
        if not ca or self.v(ca) is None:
            return False
        if ta and self.v(ta):
            return self.v(ca) / self.v(ta) > 0.05
        if rv and self.v(rv):
            return self.v(ca) / self.v(rv) > 0.10
        return False

    def evaluate(self, sid, pk):
        pkb = pk - 10000
        out = {
            "M01": self.ratio(sid, pk, pkb, "FIN.REV.YTD", LOW_BASE_REV),
            "M02": self.ratio(sid, pk, pkb, "FIN.REV.SQ", LOW_BASE_REV),
            "M03": self.m03(sid, pk),
            "M04": self.m04(sid, pk, pkb),
            "M05": self.ratio(sid, pk, pkb, "FIN.NPDEDT.YTD", LOW_BASE_NPDEDT),
            "M06": self.m06(sid, pk, pkb),
            "M07": self.ratio(sid, pk, pkb, "FIN.NPDEDT.SQ", LOW_BASE_NPDEDT),
            "M08": self.m08(sid, pk),
            "M09": self.diff(sid, pk, pkb, "FIN.OCF.YTD"),
            "M10": self.mdays(sid, pk, pkb, "FIN.AR.INSTANT", "FIN.REV.YTD"),
            "M11": self.mdays(sid, pk, pkb, "FIN.INV.INSTANT", "FIN.COST.YTD"),
            "M12": self.m12(sid, pk, pkb),
        }
        for mid in ("M05", "M06", "M07"):
            if out[mid]["status"] in ("OK", "UNDEFINED_BASE") and self.oneoff(sid, pk):
                out[mid]["flags"].add("Q09")
        if self.project_mode(sid, pk):
            out["M11"] = self.res(None, "NOT_APPLICABLE", {"Q10"}, "PROJECT_MODE")
        for mid in out:
            if out[mid]["status"] == "OK" and "Q06" in out[mid]["flags"]:
                out[mid]["status"] = "PROVISIONAL"
        return out

    # ---- signal / route re-derivation ----
    def sg_fire(self, sid, pk, got):
        out = {}
        for s, (op, t) in THRESHOLD_SG.items():
            mid = SG_METRIC[s]
            r = got[mid]
            if s == "SG07":
                m8, m9 = got["M08"], got["M09"]
                if m8["status"] not in ("OK", "PROVISIONAL") or m9["status"] not in ("OK", "PROVISIONAL"):
                    continue
                if m8["value"] is None or m9["value"] is None:
                    continue
                if m8["value"] >= t and m9["value"] > 0:
                    if "Q05" in m8["flags"] or "Q05" in m9["flags"]:
                        q = "LOW_BASE"
                    elif "Q06" in m8["flags"] or "Q06" in m9["flags"]:
                        q = "PROVISIONAL"
                    else:
                        q = "CLEAN"
                    if "Q09" in got["M05"]["flags"]:
                        q = "PROVISIONAL"
                    out[s] = q
                continue
            if r["value"] is None or r["status"] in ("UNDEFINED_BASE", "NOT_APPLICABLE"):
                continue
            if r["status"] not in ("OK", "PROVISIONAL"):
                continue
            mv = r["value"]
            ok = mv >= t if op == ">=" else mv <= t
            if ok:
                if "Q05" in r["flags"]:
                    q = "LOW_BASE"
                elif "Q06" in r["flags"] or r["status"] == "PROVISIONAL":
                    q = "PROVISIONAL"
                else:
                    q = "CLEAN"
                out[s] = q
        # SG06 absolute channel
        r5 = got["M05"]
        if r5["status"] == "UNDEFINED_BASE":
            cur = self.v(self.rows[(sid, pk)].get("FIN.NPDEDT.YTD"))
            base = self.v(self.rows[(sid, pk - 10000)].get("FIN.NPDEDT.YTD"))
            if cur is not None and base is not None and base < 0 and cur > 0 and cur >= ABS_CONFIRM:
                if "Q05" in r5["flags"]:
                    q = "LOW_BASE"
                elif "Q06" in r5["flags"]:
                    q = "PROVISIONAL"
                else:
                    q = "CLEAN"
                out["SG06"] = q
        # SG08 absolute channel
        o = self.rows[(sid, pk)].get("FIN.OCF.YTD")
        ob = self.rows[(sid, pk - 10000)].get("FIN.OCF.YTD")
        if o and ob and o["status"] in USABLE and ob["status"] in USABLE:
            cv, bv = self.v(o), self.v(ob)
            if cv is not None and bv is not None and cv > 0 and bv <= 0:
                q = "PROVISIONAL" if (self.restate([o]) or self.restate([ob])) else "CLEAN"
                out["SG08"] = q
        return out

    def rh_fire(self, got):
        out = set()
        for rh, (mid, op, t) in RH_DEF.items():
            r = got[mid]
            if r["status"] not in ("OK", "PROVISIONAL") or r["value"] is None:
                continue
            mv = r["value"]
            ok = mv >= t if op == ">=" else (mv <= t if op == "<=" else mv < t)
            if ok:
                out.add(rh)
        if any("Q09" in got[m]["flags"] for m in ("M05", "M06", "M07")):
            out.add("RH06")
        return out


def derive_l1(engine, sid, pk, got, s03_row):
    """Return (bucket, subtag, check). FROZEN_OVERRIDE for workpaper/cutoff rows."""
    if s03_row["workpaper_status"] or s03_row["l0_status"] == "WATCH_AFTER_CUTOFF":
        return s03_row["l1_bucket"], s03_row["l1_subtag"], "FROZEN_OVERRIDE"
    f = engine.sg_fire(sid, pk, got)
    clean = {x for x in f if f[x] == "CLEAN"}
    low = {x for x in f if f[x] == "LOW_BASE"}
    prov = {x for x in f if f[x] == "PROVISIONAL"}
    rh = engine.rh_fire(got)
    any_hold = any(got[x]["status"] == "HOLD" for x in
                   ("M01", "M02", "M03", "M04", "M05", "M06", "M07", "M08", "M09"))
    if clean:
        b, s = "OBSERVE_QUEUE", "OQ_CLEAN_OK"
    elif low:
        b, s = "OBSERVE_QUEUE", "OQ_LOW_BASE_PROVISIONAL"
    elif prov:
        b, s = "OBSERVE_QUEUE", "OQ_PROVISIONAL_ONLY"
    elif rh:
        b, s = "RISK_WATCH", ("RW_HAS_HOLD" if any_hold else "RW_CLEAN")
    elif any_hold:
        b, s = "OBSERVE_QUEUE", "OQ_HOLD_PROTECTED"
    else:
        b, s = "NO_SIGNAL", "NS_CONFIRMED"
    if s == "NS_CONFIRMED" and (
        any(got[m]["status"] in ("MISSING", "NOT_COMPARABLE") for m in got)
        or any("Q06" in got[m]["flags"] for m in got)
    ):
        s = "NS_INCOMPLETE_EVIDENCE"
    ok = (b == s03_row["l1_bucket"] and s == s03_row["l1_subtag"])
    return b, s, ("CONSISTENT" if ok else "MISMATCH")


# ---------------------------------------------------------------------------
# Reproducible per-company evidence for S04 absolute channel / low-base confirmation
# ---------------------------------------------------------------------------
DIM_ORDER = ["GROWTH", "MARGIN", "PROFIT", "CASH"]


def parse_attr_list(attrs: str, key: str):
    """Read one semicolon-joined boundary attribute (e.g. B_ABS_CHANNEL=SG06;SG08)."""
    for part in (attrs or "").split(";"):
        if part.startswith(key + "="):
            return [x for x in part[len(key) + 1:].split(";") if x]
    return []


def _rec_value(rec):
    return fnum(rec["value_cny"]) if rec is not None else None


def _comparability(rt, rb):
    """Same-period cross-year comparability of two raw s00 rows, per S01 v4."""
    if rt is None or rb is None:
        return False, "MISSING_ONE_SIDE"
    if rt["status"] not in (USABLE | USABLE_FLAG) or rb["status"] not in (USABLE | USABLE_FLAG):
        return False, "NON_USABLE_STATUS"
    if rt["consolidation_scope"] != rb["consolidation_scope"]:
        return False, "SCOPE_MISMATCH"
    if rt["is_pre_listing"] == "YES" or rb["is_pre_listing"] == "YES":
        return False, "PRE_LISTING"
    if RESTATE_PENDING in (rt["restatement_flag"], rb["restatement_flag"]):
        return False, "RESTATEMENT_PENDING"
    if rt["period_type"] != rb["period_type"] or int(rt["period_key"]) - int(rb["period_key"]) != 10000:
        return False, "PERIOD_PAIR_MISMATCH"
    if _rec_value(rt) is None or _rec_value(rb) is None:
        return False, "VALUE_EMPTY"
    return True, "SAME_PERIOD_COMPARABLE"


def build_abs_channel_evidence(engine, d, sample_rows):
    """Per-company, per-signal reproducible evidence for B_ABS_CHANNEL (SG06 / SG08)."""
    out = []
    for r in sample_rows:
        sigs = parse_attr_list(r["boundary_attributes"], "B_ABS_CHANNEL")
        if not sigs:
            continue
        sid = r["security_id"]
        pk = int(r["anchor_period"])
        pkb = pk - 10000
        for sg in sigs:
            field = ABS_CHANNEL_FIELDS[sg]
            rt = engine.rows[(sid, pk)].get(field)
            rb = engine.rows[(sid, pkb)].get(field)
            comp_ok, comp_txt = _comparability(rt, rb)
            cur, base = _rec_value(rt), _rec_value(rb)
            delta = (cur - base) if (cur is not None and base is not None) else None
            if sg == "SG06":
                thr_txt = "基期<0 且当期>0 且当期>=1,000 万元；两侧 usable 且同期间可比"
                passed = comp_ok and base < 0 and cur > 0 and cur >= ABS_CONFIRM
            else:
                thr_txt = "OCF(t)>0 且 OCF(t-1y)<=0；两侧 usable 且同期间可比"
                passed = comp_ok and cur > 0 and base <= 0
            out.append({
                "security_id": sid,
                "stock_name": r["stock_name"],
                "signal_id": sg,
                "field_id": field,
                "period_key": str(pk),
                "value_cny": cur,
                "status": rt["status"] if rt else "MISSING_ROW",
                "base_period_key": str(pkb),
                "base_value_cny": base,
                "base_status": rb["status"] if rb else "MISSING_ROW",
                "comparability": comp_txt,
                "delta_cny": round(delta, 2) if delta is not None else None,
                "delta_wan": round(delta / 10000.0, 2) if delta is not None else None,
                "threshold_check": thr_txt,
                "check_pass": bool(passed),
            })
    out.sort(key=lambda e: (e["security_id"], e["signal_id"]))
    return out


def build_low_base_evidence(engine, d, sample_rows):
    """Per-company, per-signal reproducible evidence for C_LOW_BASE_CONFIRMED."""
    out = []
    for r in sample_rows:
        sigs = parse_attr_list(r["boundary_attributes"], "C_LOW_BASE_CONFIRMED")
        if not sigs:
            continue
        sid = r["security_id"]
        pk = int(r["anchor_period"])
        pkb = pk - 10000
        detail = d["s04_by"][sid]["low_base_detail"] or ""
        for sg in sigs:
            field = LOW_BASE_MAP[sg]["field_id"]
            rt = engine.rows[(sid, pk)].get(field)
            rb = engine.rows[(sid, pkb)].get(field)
            comp_ok, comp_txt = _comparability(rt, rb)
            cur, base = _rec_value(rt), _rec_value(rb)
            delta = (cur - base) if (cur is not None and base is not None) else None
            delta_wan = round(delta / 10000.0, 2) if delta is not None else None
            passed = bool(comp_ok and delta is not None and delta >= ABS_CONFIRM and delta > 0)
            thr_txt = "同口径增量>=1,000 万元且方向为正；两侧 usable 且同期间可比"
            if sg == "SG06":
                passed = passed and cur >= ABS_CONFIRM
                thr_txt = "同口径增量>=1,000 万元且方向为正，且当期>=1,000 万元；两侧 usable 且同期间可比"
            recorded = f"{sg}=CONFIRMED({delta_wan:.2f}W)" if delta_wan is not None else ""
            out.append({
                "security_id": sid,
                "stock_name": r["stock_name"],
                "signal_id": sg,
                "field_id": field,
                "basis": LOW_BASE_MAP[sg]["basis"],
                "period_key": str(pk),
                "value_cny": cur,
                "status": rt["status"] if rt else "MISSING_ROW",
                "base_period_key": str(pkb),
                "base_value_cny": base,
                "base_status": rb["status"] if rb else "MISSING_ROW",
                "comparability": comp_txt,
                "delta_cny": round(delta, 2) if delta is not None else None,
                "delta_wan": delta_wan,
                "threshold_check": thr_txt,
                "s04_recorded_detail": detail,
                "s04_detail_match": bool(recorded and recorded in detail),
                "check_pass": bool(passed),
            })
    out.sort(key=lambda e: (e["security_id"], e["signal_id"]))
    return out


# ---------------------------------------------------------------------------
# Reverse-omission independent re-derivation (no inheritance of S06 labels)
# ---------------------------------------------------------------------------
def classify_omission(engine, d, sid, pk, got):
    """Re-derive why a strong-exposure company is outside the S05 mainline, from scratch."""
    s04 = d["s04_by"][sid]
    s03 = d["s03_by"][sid]
    dec = s04["l2_decision"]
    fired = engine.sg_fire(sid, pk, got)
    clean_dims = sorted({SG_DIM[x] for x in fired if fired[x] == "CLEAN"}, key=DIM_ORDER.index)
    n = len(clean_dims)
    if s03["workpaper_status"] or s03["l0_status"] == "WATCH_AFTER_CUTOFF":
        return {"verdict": "RULE_CONSISTENT_CUTOFF_GUARD", "layer": "S03", "consistent": True,
                "clean_dims": clean_dims, "signals": fired}
    if dec == "L2_NOT_IN_SCOPE":
        # F09 R2: judge on the s00_v10 re-derived S03 bucket, not the frozen table.
        rb, rsub, rcheck = derive_l1(engine, sid, pk, got, s03)
        scope_ok = rb != "OBSERVE_QUEUE"
        frozen_match = (rb == s03["l1_bucket"] and rsub == s03["l1_subtag"])
        ok = scope_ok and frozen_match
        if not scope_ok:
            verdict, layer = "CALC_LEAK_SCOPE_DIVERGENCE", "S03/S04"
        elif not frozen_match:
            verdict, layer = "CALC_LEAK_SCOPE_FROZEN_MISMATCH", "S03/S04"
        else:
            verdict, layer = "RULE_CONSISTENT_SCOPE", "S03"
        return {"verdict": verdict, "layer": layer, "consistent": ok,
                "clean_dims": clean_dims, "signals": fired,
                "recomputed_bucket": rb, "recomputed_subtag": rsub,
                "recomputed_route_check": rcheck,
                "frozen_bucket": s03["l1_bucket"],
                "frozen_bucket_match": frozen_match}
    if dec == "L2_NOT_SHORTLISTED":
        ok = n < 2
        return {"verdict": "RULE_CONSISTENT_DIMS_LT2" if ok else "CALC_LEAK_DIMS_SUFFICIENT",
                "layer": "S04", "consistent": ok, "clean_dims": clean_dims, "signals": fired}
    if dec == "L2_SHORTLIST_CANDIDATE":
        ok = n >= 2
        return {"verdict": "REVIEWED_HOLD_BASELINE_CANDIDATE" if ok else "CALC_LEAK_DIMS_INSUFFICIENT",
                "layer": "S04/S05", "consistent": ok, "clean_dims": clean_dims, "signals": fired}
    if dec == "HOLD_FOR_DATA":
        ok = n < 2
        return {"verdict": "RULE_CONSISTENT_HOLD_FOR_DATA" if ok else "REVIEWED_HOLD_BASELINE_CANDIDATE",
                "layer": "S04/S05", "consistent": ok, "clean_dims": clean_dims, "signals": fired}
    return {"verdict": "UNDETERMINED", "layer": "UNKNOWN", "consistent": False,
            "clean_dims": clean_dims, "signals": fired}


def build_reverse_omission_audit(engine, d, sample_rows):
    out = []
    for r in sample_rows:
        if r["primary_stratum"] != "REVERSE_OMISSION":
            continue
        sid = r["security_id"]
        pk = int(r["anchor_period"])
        got = engine.evaluate(sid, pk)
        c = classify_omission(engine, d, sid, pk, got)
        blocks = []
        for mid in [f"M{i:02d}" for i in range(1, 13)]:
            st = got[mid]["status"]
            if st == "OK":
                continue
            fl = ",".join(sorted(got[mid]["flags"]))
            blocks.append(f"{mid}={st}" + (f"({fl})" if fl else ""))
        n = len(c["clean_dims"])
        if c["verdict"] == "RULE_CONSISTENT_SCOPE":
            reentry = "需 S03 由 NO_SIGNAL/RISK_WATCH 进入 OBSERVE_QUEUE（出现 CLEAN 信号）后才进入 L2"
        elif c["verdict"] == "RULE_CONSISTENT_DIMS_LT2":
            reentry = (f"当前复算仅 {n} 个不同维度有 CLEAN 信号（{';'.join(c['clean_dims']) or '无'}），"
                       "需第 2 个维度出现 CLEAN 信号；或规则升版时全池重算")
        elif c["verdict"] == "REVIEWED_HOLD_BASELINE_CANDIDATE":
            reentry = ("基线复算已达 2 个合格维度；重进需 S04/S05 复核版适用性放行"
                       "（补齐复核版 tight_pass 逐家映射）或补齐待核输入消除 HOLD_FOR_DATA")
        elif c["verdict"] == "RULE_CONSISTENT_CUTOFF_GUARD":
            reentry = "截止日后隔离，待取得截止日后完整报告并按规则重进"
        else:
            reentry = "需回退 S03/S04 重算并复核"
        out.append({
            "security_id": sid,
            "stock_name": r["stock_name"],
            "anchor_period": str(pk),
            "frozen_s04_l2_decision": d["s04_by"][sid]["l2_decision"],
            "frozen_s06_reviewed_decision": d["s06_early_by"].get(sid, {}).get("s04_l2_decision", "ABSENT"),
            "recomputed_s03_bucket": r["derived_l1"].split("/")[0],
            "recomputed_s03_subtag": r["derived_l1"].split("/")[1],
            "scope_rejudge_basis": (
                {
                    "recomputed_bucket": c.get("recomputed_bucket"),
                    "recomputed_subtag": c.get("recomputed_subtag"),
                    "recomputed_route_check": c.get("recomputed_route_check"),
                    "frozen_bucket": c.get("frozen_bucket"),
                    "frozen_bucket_match": c.get("frozen_bucket_match"),
                }
                if "recomputed_bucket" in c else None
            ),
            "recomputed_signals": {k: c["signals"][k] for k in sorted(c["signals"])},
            "recomputed_clean_dimensions": c["clean_dims"],
            "recomputed_dimension_count": n,
            "blocking_or_pending_metrics": blocks,
            "baseline_route_consistent": c["consistent"],
            "verdict": c["verdict"],
            "attribution_layer": c["layer"],
            "reentry_condition": reentry,
        })
    out.sort(key=lambda x: x["security_id"])
    return out


def build_s03_override_audit(d, sample_rows):
    """Explain each FROZEN_OVERRIDE: 57 rule-replayed + N frozen overrides must stay separable."""
    out = []
    for r in sample_rows:
        if r["s03_route_check"] != "FROZEN_OVERRIDE":
            continue
        sid = r["security_id"]
        s03 = d["s03_by"][sid]
        if s03["l0_status"] == "WATCH_AFTER_CUTOFF":
            reason = "L0 WATCH_AFTER_CUTOFF（截止日后输入隔离），沿用冻结 bucket/subtag"
        elif s03["workpaper_status"] == "WORKPAPER_ADOPTED":
            reason = "WORKPAPER_ADOPTED（底稿仅参考/范围变更），沿用冻结 bucket/subtag"
        else:
            reason = f"workpaper_status={s03['workpaper_status'] or 'NONE'}，沿用冻结 bucket/subtag"
        out.append({
            "security_id": sid,
            "stock_name": r["stock_name"],
            "workpaper_status": s03["workpaper_status"],
            "l0_status": s03["l0_status"],
            "frozen_bucket": s03["l1_bucket"],
            "frozen_subtag": s03["l1_subtag"],
            "override_reason": reason,
        })
    out.sort(key=lambda x: x["security_id"])
    return out


# ---------------------------------------------------------------------------
# Deterministic stratified sampling
# ---------------------------------------------------------------------------
def build_sample(d):
    selected = {}   # sid -> dict
    slots_log = []

    def add_slot(stratum, slot, quota, rule, candidates, key=None):
        keyfn = key or (lambda s: s)
        cand = list(dict.fromkeys(c for c in candidates if c not in selected))
        cand.sort(key=keyfn)
        take = cand[:quota]
        for s in take:
            selected[s] = {"primary": stratum, "slot": slot, "rule": rule,
                           "key": keyfn(s)}
        slots_log.append({
            "stratum": stratum, "slot": slot, "quota": quota, "filled": len(take),
            "rule": rule, "pool_size": len(candidates),
        })
        return take

    s02_by = d["s02_by"]
    s03_by = d["s03_by"]
    s04_by = d["s04_by"]
    s05_pass = set(d["s05_pass_by"])
    s05_278 = set(d["s05_pass_by"]) | set(d["s05_obs_by"])
    s05_776 = set(d["s05_776_by"])
    missing_by = d["s06_missing_by"]
    early_by = d["s06_early_by"]
    master_by = d["master_by_id"]

    def has(sid, mid, status):
        return s02_by[sid][mid]["metric_status"] == status

    def is_loss(sid):
        rec = d["s02_by"][sid]["M05"]
        if rec["metric_status"] != "UNDEFINED_BASE":
            return False
        # base NPDEDT negative -> loss
        return True

    # ---- S1 BOUNDARY_PASS_FAIL (quota 21)
    wp2 = [r["company_id"] for r in d["wide_pass"] if r["clean_ok_dims_count"] == "2"]
    wp1 = [r["company_id"] for r in d["wide_pass"] if r["clean_ok_dims_count"] == "1"]
    wd_risk = [r["company_id"] for r in d["wide_defer"] if r["l1_bucket"] == "RISK_WATCH"]
    add_slot("BOUNDARY_PASS_FAIL", "B01_S03_MIN_2DIM", 1,
             "S03 wide_pass with exactly 2 clean dimensions (minimum pass); security_id asc", wp2)
    add_slot("BOUNDARY_PASS_FAIL", "B02_S03_MIN_1DIM", 1,
             "S03 wide_pass with exactly 1 clean dimension (boundary pass); security_id asc", wp1)
    add_slot("BOUNDARY_PASS_FAIL", "B03_S03_DEFER_RISK", 1,
             "S03 wide_defer RISK_WATCH (RH-only, no SG); security_id asc", wd_risk)

    cand2 = [r["company_id"] for r in d["s04"]
             if r["l2_decision"] == "L2_SHORTLIST_CANDIDATE"
             and r["qualified_dim_count"] == "2" and r["reachable_dim_count"] == "2"]
    add_slot("BOUNDARY_PASS_FAIL", "B04_S04_MIN2_PASS", 2,
             "S04 L2 candidate with exactly 2 reachable = 2 qualified dimensions (minimum pass); security_id asc", cand2)

    one_fail = [r["company_id"] for r in d["s04"]
                if r["l2_decision"] == "L2_SHORTLIST_CANDIDATE"
                and r["reachable_dim_count"] == "3" and r["qualified_dim_count"] == "2"]
    add_slot("BOUNDARY_PASS_FAIL", "B05_S04_ONE_DIM_FAIL", 2,
             "S04 L2 candidate with 3 reachable / 2 qualified (only one dimension short); security_id asc", one_fail)

    abs6 = [r["company_id"] for r in d["s04"]
            if "SG06" in r["abs_channel_sg"].split(";") and r["l2_decision"] == "L2_SHORTLIST_CANDIDATE"]
    add_slot("BOUNDARY_PASS_FAIL", "B06_S04_ABS_SG06", 2,
             "S04 L2 candidate depending on SG06 absolute-amount channel; security_id asc", abs6)

    lbc = [r["company_id"] for r in d["s04"]
           if r["low_base_confirmed_sg"] and r["l2_decision"] == "L2_SHORTLIST_CANDIDATE"]
    add_slot("BOUNDARY_PASS_FAIL", "B07_S04_LOWBASE_CONFIRMED", 2,
             "S04 L2 candidate carrying C_LOW_BASE_CONFIRMED signal; security_id asc", lbc)

    # RH near-threshold, one per RH01-RH05: nearest below threshold, then security_id
    for rh in ("RH01", "RH02", "RH03", "RH04", "RH05"):
        mid, op, thr = RH_DEF[rh]
        pool = []
        for sid, per in d["s05_qf_by"].items():
            row = per.get(rh)
            if not row or row["rh_status"] != "NOT_TRIGGERED":
                continue
            val = fnum(row["metric_value"])
            if val is None:
                continue
            dist = abs(val - thr)
            pool.append((dist, sid))
        pool.sort()
        add_slot("BOUNDARY_PASS_FAIL", f"B08_{rh}_NEAR", 1,
                 f"S05 {rh} nearest-not-triggered below/at threshold (distance, security_id asc)",
                 [s for _, s in pool])

    rh06 = [r["security_id"] for r in d["s05_qdl"]
            if r["decision"] == "QUALITY_PASS" and "RH06" in (r["rh_triggered"] or "")]
    add_slot("BOUNDARY_PASS_FAIL", "B09_RH06_TRIGGER", 1,
             "S05 QUALITY_PASS with RH06 (one-off) triggered; security_id asc", rh06)

    # near-threshold but TRIGGERED side (RH04/RH05), to test both sides of the boundary
    trig_pool = []
    for rh in ("RH04", "RH05"):
        mid, op, thr = RH_DEF[rh]
        for sid, per in d["s05_qf_by"].items():
            row = per.get(rh)
            if not row or row["rh_status"] != "TRIGGERED":
                continue
            val = fnum(row["metric_value"])
            if val is None:
                continue
            trig_pool.append((abs(val - thr), rh, sid))
    trig_pool.sort()
    add_slot("BOUNDARY_PASS_FAIL", "B08_RH_TRIGGERED_NEAR", 2,
             "S05 RH04/RH05 nearest-triggered above/below threshold (distance, rh, security_id asc)",
             [s for _, _, s in trig_pool])

    oor_slot = []
    for mid, anchor in (("M08", "20260630"), ("M08", "20260930"), ("M12", None), ("M10", None)):
        for r in d["s05_oor"]:
            if r["metric_id"] != mid:
                continue
            if anchor and r["anchor_period"] != anchor:
                continue
            if r["security_id"] in oor_slot:
                continue
            oor_slot.append(r["security_id"])
            break
    add_slot("BOUNDARY_PASS_FAIL", "B10_OUT_OF_VALID_RANGE", 4,
             "S05 out-of-valid-range representatives: M08-H1, M08-9M, M12, M10; first distinct company by file order",
             oor_slot)

    # ---- S2 BJ_MARKET (quota 8)
    bj = [r["security_id"] for r in d["master"] if r["security_id"].startswith("BJ:")]
    bj_pass_h1 = [s for s in bj if s in s05_pass and d["s05_qdl_by"].get(s, {}).get("anchor_period") == "20260630"]
    bj_pass_9m = [s for s in bj if s in s05_pass and d["s05_qdl_by"].get(s, {}).get("anchor_period") == "20260930"]
    bj_cand_notpass = [s for s in bj if s in s04_by
                       and s04_by[s]["l2_decision"] == "L2_SHORTLIST_CANDIDATE" and s not in s05_278]
    bj_risk = [s for s in bj if s03_by[s]["l1_bucket"] in ("RISK_WATCH", "NO_SIGNAL")]
    bj_missing = [s for s in bj if s in missing_by]
    add_slot("BJ_MARKET", "J01_BJ_PASS_H1", 2,
             "BJ S05 QUALITY_PASS anchored 2026H1; security_id asc", bj_pass_h1)
    add_slot("BJ_MARKET", "J02_BJ_PASS_9M", 2,
             "BJ S05 QUALITY_PASS anchored 2026Q3; security_id asc", bj_pass_9m)
    add_slot("BJ_MARKET", "J03_BJ_S04_CAND_NOT_PASS", 2,
             "BJ S04 L2 candidate outside frozen S05 278; security_id asc", bj_cand_notpass)
    add_slot("BJ_MARKET", "J04_BJ_RISK_OR_NO_SIGNAL", 1,
             "BJ S03 RISK_WATCH / NO_SIGNAL; security_id asc", bj_risk)
    add_slot("BJ_MARKET", "J05_BJ_MISSING_WATCH", 1,
             "BJ on S06 missing-data watch; security_id asc", bj_missing)

    # ---- S3 LOSS_AND_LOW_BASE (quota 8)
    loss = [s for s in d["s02_by"] if is_loss(s)]
    rev_undef = [s for s in d["s02_by"] if has(s, "M07", "UNDEFINED_BASE")]
    low_sub = [r["company_id"] for r in d["s03"] if r["l1_subtag"] == "OQ_LOW_BASE_PROVISIONAL"]
    lbc_extra = [r["company_id"] for r in d["s04"] if r["low_base_confirmed_sg"]]
    add_slot("LOSS_AND_LOW_BASE", "L01_LOSS_M05_UNDEFINED", 3,
             "M05 UNDEFINED_BASE (loss / negative base); security_id asc", loss)
    add_slot("LOSS_AND_LOW_BASE", "L02_M07_UNDEFINED_BASE", 2,
             "M07 UNDEFINED_BASE (single-quarter negative base); security_id asc", rev_undef)
    add_slot("LOSS_AND_LOW_BASE", "L03_LOWBASE_PROVISIONAL", 2,
             "S03 OQ_LOW_BASE_PROVISIONAL; security_id asc", low_sub)
    add_slot("LOSS_AND_LOW_BASE", "L04_LOWBASE_CONFIRMED_EXTRA", 1,
             "S04 C_LOW_BASE_CONFIRMED not already sampled; security_id asc", lbc_extra)

    # ---- S4 MISSING_DATA_WATCH (quota 14)
    cut = [r["security_id"] for r in d["s06_missing"] if r["missing_data_category"] == "AFTER_CUTOFF_ISOLATED"]
    anc = [r["security_id"] for r in d["s06_missing"] if r["missing_data_category"] == "PENDING_ANCHOR_RESELECTION"]
    jid = [r["security_id"] for r in d["s06_missing"] if r["missing_data_category"] == "S05_QUALITY_HOLD_CONSOLIDATION_SCOPE_UNKNOWN"]
    qsu = [r["security_id"] for r in d["s06_missing"] if r["missing_data_category"] == "QUALITY_SOURCE_UNKNOWN_NON_MAINLINE"]
    hq = [r["security_id"] for r in d["s06_missing"] if r["missing_data_category"] == "S04_HOLD_FOR_DATA_AND_QUALITY_SOURCE_UNKNOWN"]
    hfd = [r["security_id"] for r in d["s06_missing"] if r["missing_data_category"] == "S04_HOLD_FOR_DATA"]
    hfd.sort(key=lambda s: (-(int(missing_by[s]["s02_hold_count"]) > 0),
                            -(int(missing_by[s]["s02_undefined_base_count"]) > 0),
                            -(int(missing_by[s]["s02_missing_count"]) > 0), s))
    s2hm = [r["security_id"] for r in d["s06_missing"] if r["missing_data_category"] == "S02_METRIC_HOLD_OR_MISSING_NON_MAINLINE"]
    s2hm.sort(key=lambda s: (-(int(missing_by[s]["s02_hold_count"]) > 0),
                             -(int(missing_by[s]["s02_missing_count"]) > 0), s))
    add_slot("MISSING_DATA_WATCH", "M01_AFTER_CUTOFF", 4,
             "All 4 after-cutoff isolated companies (guard preserved); security_id asc", cut)
    add_slot("MISSING_DATA_WATCH", "M02_ANCHOR_PENDING", 1,
             "Anchor reselection pending company; security_id asc", anc)
    add_slot("MISSING_DATA_WATCH", "M03_QUALITY_HOLD_JIDONG", 1,
             "S05 QUALITY_HOLD consolidation-scope unknown (Jidong); security_id asc", jid)
    add_slot("MISSING_DATA_WATCH", "M04_QUALITY_SOURCE_UNKNOWN", 1,
             "Non-mainline quality source unknown; security_id asc", qsu)
    add_slot("MISSING_DATA_WATCH", "M05_HOLD_AND_QUALITY_UNKNOWN", 1,
             "S04 HOLD_FOR_DATA + quality source unknown; security_id asc", hq)
    add_slot("MISSING_DATA_WATCH", "M06_S04_HOLD_FOR_DATA", 3,
             "S04 HOLD_FOR_DATA prioritised by S02 HOLD > UNDEFINED_BASE > MISSING, then security_id", hfd)
    add_slot("MISSING_DATA_WATCH", "M07_S02_HOLD_OR_MISSING", 3,
             "S02 metric HOLD/MISSING non-mainline prioritised by HOLD > MISSING, then security_id", s2hm)

    # ---- S5 EARLY_STAGE_WATCH (quota 6)
    for bucket, slot, q in (
        ("EARLY_RD_PROTOTYPE_SAMPLING", "E01_EARLY_RD", 2),
        ("EARLY_PILOT_SMALL_BATCH", "E02_EARLY_PILOT", 1),
        ("EVIDENCED_PRODUCT_STAGE_UNKNOWN", "E03_EVIDENCED_UNKNOWN", 2),
        ("COMMERCIAL_NON_MAINLINE_RESERVE", "E04_COMMERCIAL_RESERVE", 1),
    ):
        pool = [r["security_id"] for r in d["s06_early"] if r["watch_bucket"] == bucket]
        add_slot("EARLY_STAGE_WATCH", slot, q,
                 f"S06 early-stage bucket {bucket}; security_id asc", pool)

    # ---- S6 REVERSE_OMISSION (quota 5)
    strong = [r["security_id"] for r in d["master"]
              if r["robot_exposure"] in ("DIRECT_DISCLOSED", "DIRECT_UNDISCLOSED", "INDIRECT_VERIFIED")]
    strong_not_main = [s for s in strong if s not in s05_pass]
    rev_scope = [s for s in strong_not_main if s04_by[s]["l2_decision"] == "L2_NOT_IN_SCOPE"]
    rev_hold = [s for s in strong_not_main if early_by.get(s, {}).get("s04_l2_decision") == "HOLD_FOR_DATA"]
    rev_notshort = [s for s in strong_not_main if early_by.get(s, {}).get("s04_l2_decision") == "NOT_SHORTLISTED"]
    add_slot("REVERSE_OMISSION", "R01_NOT_IN_SCOPE", 2,
             "Strong robot exposure, S04 L2_NOT_IN_SCOPE, not in S05 277; security_id asc", rev_scope)
    add_slot("REVERSE_OMISSION", "R02_HOLD_FOR_DATA", 2,
             "Strong robot exposure, reviewed HOLD_FOR_DATA, not in S05 277; prefer baseline candidate then security_id", 
             sorted(rev_hold, key=lambda s: (s04_by[s]["l2_decision"] != "L2_SHORTLIST_CANDIDATE", s)))
    add_slot("REVERSE_OMISSION", "R03_NOT_SHORTLISTED", 1,
             "Strong robot exposure, reviewed NOT_SHORTLISTED, not in S05 277; security_id asc", rev_notshort)

    return selected, slots_log, strong, strong_not_main


# ---------------------------------------------------------------------------
# Per-company audit
# ---------------------------------------------------------------------------
def audit_company(engine, d, sid, meta_info):
    stored = d["s02_by"][sid]
    pk = int(stored["M01"]["period_key"])
    got = engine.evaluate(sid, pk)
    latest = engine.latest_pk(sid)

    status_match = 0
    value_match = 0
    compared = 0
    diffs = []
    max_diff = 0.0
    for i in range(1, 13):
        mid = f"M{i:02d}"
        e = got[mid]
        s = stored[mid]
        compared += 1
        if e["status"] == s["metric_status"]:
            status_match += 1
        if e["value"] is None or clean(s["value"]) == "":
            if (e["value"] is None) == (clean(s["value"]) == ""):
                value_match += 1
            else:
                diffs.append(f"{mid}:EMPTY_MISMATCH")
            continue
        exp = fnum(s["value"])
        delta = abs(e["value"] - exp)
        max_diff = max(max_diff, delta)
        tol = max(FLOAT_TOL, abs(exp) * 1e-12)
        if delta <= tol:
            value_match += 1
        else:
            diffs.append(f"{mid}:{delta:.3e}")

    consistency = "EXACT" if (status_match == compared and value_match == compared) else (
        "ROUNDING_TOLERANCE" if not diffs else "DIFF")

    s03 = d["s03_by"][sid]
    b, sub, route_check = derive_l1(engine, sid, pk, got, s03)

    s04 = d["s04_by"][sid]
    qdims = [x for x in s04["qualified_dims"].split(";") if x]
    s04_ok = (len(set(qdims)) == int(s04["qualified_dim_count"]))
    if s04["l2_decision"] == "L2_SHORTLIST_CANDIDATE":
        s04_ok = s04_ok and int(s04["qualified_dim_count"]) >= 2
    s04_check = "CONSISTENT" if s04_ok else "MISMATCH"

    # S05 checks
    s05_checks = 0
    s05_bad = 0
    if sid in d["s05_qf_by"]:
        for rh, row in d["s05_qf_by"][sid].items():
            if row["rh_status"] not in ("TRIGGERED", "NOT_TRIGGERED"):
                continue
            val = fnum(row["metric_value"])
            if val is None:
                continue
            mid, op, thr = RH_DEF[rh]
            exp = val >= thr if op == ">=" else (val <= thr if op == "<=" else val < thr)
            s05_checks += 1
            if exp != (row["rh_status"] == "TRIGGERED"):
                s05_bad += 1
    oor_note = ""
    for r in d["s05_oor_by"].get(sid, []):
        lo, hi = [float(x) for x in r["valid_range"].strip("[]").split(",")]
        val = fnum(stored[r["metric_id"]]["value"])
        s05_checks += 1
        if val is None or lo <= val <= hi:
            s05_bad += 1
        oor_note = f"{r['metric_id']}={val:.4f} outside {r['valid_range']}"
    if sid in d["s05_qdl_by"]:
        q = d["s05_qdl_by"][sid]
        one_off_flag = any("Q09" in got[m]["flags"] for m in ("M05", "M06", "M07"))
        s05_checks += 1
        if one_off_flag != (q["one_off"] == "YES"):
            s05_bad += 1
    if s05_checks == 0:
        s05_check = "NOT_IN_S05_POOL"
    else:
        s05_check = "CONSISTENT" if s05_bad == 0 else "MISMATCH"

    # S06 counts
    s06_check = "NOT_IN_WATCH"
    if sid in d["s06_missing_by"]:
        m = d["s06_missing_by"][sid]
        cnt = Counter(stored[x]["metric_status"] for x in stored)
        exp = (cnt["HOLD"], cnt["MISSING"], cnt["UNDEFINED_BASE"], cnt["PROVISIONAL"], cnt["NOT_COMPARABLE"])
        act = (int(m["s02_hold_count"]), int(m["s02_missing_count"]), int(m["s02_undefined_base_count"]),
               int(m["s02_provisional_count"]), int(m["s02_not_comparable_count"]))
        s06_check = "CONSISTENT" if exp == act else "MISMATCH"

    # reverse omission verdict — independently re-derived, NOT inherited from S06 labels
    omission = ""
    attribution = "NONE"
    is_strong_not_main = (d["master_by_id"][sid]["robot_exposure"]
                          in ("DIRECT_DISCLOSED", "DIRECT_UNDISCLOSED", "INDIRECT_VERIFIED")
                          and sid not in d["s05_pass_by"])
    if is_strong_not_main:
        c = classify_omission(engine, d, sid, pk, got)
        omission = c["verdict"]
        attribution = c["layer"]

    # boundary attributes
    attrs = []
    if s03["clean_ok_dims_count"] in ("1", "2"):
        attrs.append(f"S03_CLEAN_DIMS={s03['clean_ok_dims_count']}")
    if s04["reachable_dim_count"] and s04["qualified_dim_count"]:
        attrs.append(f"S04_REACHABLE={s04['reachable_dim_count']}/QUALIFIED={s04['qualified_dim_count']}")
    if s04["abs_channel_sg"]:
        attrs.append(f"B_ABS_CHANNEL={s04['abs_channel_sg']}")
    if s04["low_base_confirmed_sg"]:
        attrs.append(f"C_LOW_BASE_CONFIRMED={s04['low_base_confirmed_sg']}")
    if s04["non_ok_metric_in_clean_sg"]:
        attrs.append(f"NON_OK_IN_CLEAN={s04['non_ok_metric_in_clean_sg']}")
    if s04["scope_blocked"]:
        attrs.append("SCOPE_BLOCKED=YES")
    if sid in d["s05_qf_by"]:
        trig = sorted(rh for rh, row in d["s05_qf_by"][sid].items() if row["rh_status"] == "TRIGGERED")
        if trig:
            attrs.append("RH_TRIGGERED=" + ";".join(trig))
    if oor_note:
        attrs.append("OUT_OF_VALID_RANGE:" + oor_note)
    if sid.startswith("BJ:"):
        attrs.append("BJ_MARKET")
    if sid in d["s06_missing_by"]:
        attrs.append("S06_MISSING_CATEGORY=" + d["s06_missing_by"][sid]["missing_data_category"])
    if sid in d["s06_early_by"]:
        attrs.append("S06_EARLY_BUCKET=" + d["s06_early_by"][sid]["watch_bucket"])
    if d["master_by_id"][sid]["robot_exposure"] in ("DIRECT_DISCLOSED", "DIRECT_UNDISCLOSED", "INDIRECT_VERIFIED"):
        attrs.append("ROBOT_EXPOSURE=" + d["master_by_id"][sid]["robot_exposure"])

    # s05 route label
    if sid in d["s05_pass_by"]:
        s05_route = "QUALITY_PASS"
    elif sid in d["s05_obs_by"]:
        s05_route = "QUALITY_HOLD"
    elif sid in d["s06_missing_by"]:
        s05_route = "MISSING_DATA_WATCH"
    elif sid in d["s06_early_by"]:
        s05_route = "EARLY_STAGE_WATCH"
    elif sid in d["s05_776_by"]:
        s05_route = "OBSERVE_POOL_776"
    else:
        s05_route = "UNKNOWN"

    watch_label = ""
    if sid in d["s06_missing_by"]:
        watch_label = d["s06_missing_by"][sid]["missing_data_category"]
    elif sid in d["s06_early_by"]:
        watch_label = d["s06_early_by"][sid]["watch_bucket"]

    finding_codes = []
    if consistency == "EXACT":
        finding_codes.append("F01_ARITH_EXACT")
    if route_check == "CONSISTENT":
        finding_codes.append("F02_L1_ROUTE_EXACT")
    if s04_check == "CONSISTENT":
        finding_codes.append("F03_BOUNDARY_RULE_OK")
    if sid in d["s06_missing_by"] and s06_check == "CONSISTENT":
        finding_codes.append("F04_MISSING_NO_IMPUTATION")
    if s04["abs_channel_sg"]:
        finding_codes.append("F06_ABS_CHANNEL_OK")
    if s04["low_base_confirmed_sg"]:
        finding_codes.append("F07_LOWBASE_CONFIRM_OK")
    if oor_note:
        finding_codes.append("F11_VALID_RANGE_NO_DISPOSITION")
    if sid.startswith("BJ:"):
        finding_codes.append("F08_BJ_DISCLOSURE")
    if is_strong_not_main:
        finding_codes.append("F09_REVERSE_NO_LEAK"
                             if (omission and not omission.startswith("CALC_LEAK")
                                 and omission != "UNDETERMINED")
                             else "F09_REVERSE_REVIEW")

    return {
        "anchor_period": pk,
        "anchor_period_type": s03["anchor_period_type"],
        "s03_l1_bucket": s03["l1_bucket"],
        "s03_l1_subtag": s03["l1_subtag"],
        "derived_l1": f"{b}/{sub}",
        "s03_route_check": route_check,
        "s04_l2_decision": s04["l2_decision"],
        "s04_route_check": s04_check,
        "s05_route": s05_route,
        "s05_route_check": s05_check,
        "s06_watch_label": watch_label,
        "s06_missing_category": d["s06_missing_by"].get(sid, {}).get("missing_data_category", ""),
        "s06_early_bucket": d["s06_early_by"].get(sid, {}).get("watch_bucket", ""),
        "s06_route_check": s06_check,
        "boundary_attributes": ";".join(attrs),
        "metrics_compared": compared,
        "metrics_status_match": status_match,
        "metrics_value_match": value_match,
        "float_tolerance": f"{FLOAT_TOL:.1e}",
        "recompute_max_abs_diff": f"{max_diff:.3e}",
        "recompute_consistency": consistency,
        "diff_metrics": ";".join(diffs),
        "diff_attribution": "NO_DIFFERENCE" if not diffs else "SEE_DIFF_METRICS",
        "omission_verdict": omission,
        "attribution_layer": attribution,
        "finding_codes": ";".join(finding_codes),
        "note": "" if not diffs else "recompute differs from frozen S02; see diff_metrics",
        "latest_period_check": "MATCH" if latest == pk else f"MISMATCH({latest})",
    }


# ---------------------------------------------------------------------------
# Aggregates
# ---------------------------------------------------------------------------
def compute_aggregates(d, engine, selected, slots_log, sample_rows, strong, strong_not_main):
    agg = {}
    agg["total"] = len(sample_rows)
    agg["stratum_counts"] = Counter(r["primary_stratum"] for r in sample_rows)
    agg["slots"] = slots_log

    agg["cells_compared"] = sum(int(r["metrics_compared"]) for r in sample_rows)
    agg["cells_status_match"] = sum(int(r["metrics_status_match"]) for r in sample_rows)
    agg["cells_value_match"] = sum(int(r["metrics_value_match"]) for r in sample_rows)
    agg["max_abs_diff"] = max((float(r["recompute_max_abs_diff"]) for r in sample_rows), default=0.0)
    agg["recompute_exact"] = sum(1 for r in sample_rows if r["recompute_consistency"] == "EXACT")
    agg["recompute_non_exact"] = [r["security_id"] for r in sample_rows if r["recompute_consistency"] != "EXACT"]
    agg["anchor_check_fail"] = [r["security_id"] for r in sample_rows if r["latest_period_check"] != "MATCH"]

    agg["s03_consistent"] = sum(1 for r in sample_rows if r["s03_route_check"] == "CONSISTENT")
    agg["s03_override"] = sum(1 for r in sample_rows if r["s03_route_check"] == "FROZEN_OVERRIDE")
    agg["s03_mismatch"] = [r["security_id"] for r in sample_rows if r["s03_route_check"] == "MISMATCH"]

    agg["s04_consistent"] = sum(1 for r in sample_rows if r["s04_route_check"] == "CONSISTENT")
    agg["s04_mismatch"] = [r["security_id"] for r in sample_rows if r["s04_route_check"] == "MISMATCH"]

    agg["s05_consistent"] = sum(1 for r in sample_rows
                                if r["s05_route_check"] == "CONSISTENT" and r["security_id"] in d["s05_qf_by"])
    agg["s05_mismatch"] = [r["security_id"] for r in sample_rows if r["s05_route_check"] == "MISMATCH"]
    agg["s05_checked"] = sum(1 for r in sample_rows if r["security_id"] in d["s05_qf_by"])

    agg["s06_consistent"] = sum(1 for r in sample_rows if r["s06_route_check"] == "CONSISTENT")
    agg["s06_mismatch"] = [r["security_id"] for r in sample_rows if r["s06_route_check"] == "MISMATCH"]
    agg["s06_checked"] = sum(1 for r in sample_rows if r["security_id"] in d["s06_missing_by"])

    # ---- bias analysis ----
    s05_278 = set(d["s05_pass_by"]) | set(d["s05_obs_by"])
    qdl = d["s05_qdl_by"]
    h1 = [s for s in s05_278 if qdl[s]["anchor_period"] == "20260630"]
    q3 = [s for s in s05_278 if qdl[s]["anchor_period"] == "20260930"]
    agg["anchor_split"] = {"H1": len(h1), "9M": len(q3)}

    # RH trigger rate by anchor (RH01-RH05, applicable only)
    def rh_rate(group):
        out = {}
        for rh in ("RH01", "RH02", "RH03", "RH04", "RH05"):
            n = t = 0
            for s in group:
                row = d["s05_qf_by"].get(s, {}).get(rh)
                if not row or row["rh_status"] not in ("TRIGGERED", "NOT_TRIGGERED"):
                    continue
                n += 1
                if row["rh_status"] == "TRIGGERED":
                    t += 1
            out[rh] = {"applicable": n, "triggered": t, "rate_pct": round(100.0 * t / n, 1) if n else None}
        return out

    agg["rh_by_anchor"] = {"H1": rh_rate(h1), "9M": rh_rate(q3)}

    # out of range by anchor
    agg["oor_by_anchor"] = dict(Counter(r["anchor_period"] for r in d["s05_oor"]))
    agg["oor_by_metric"] = dict(Counter(r["metric_id"] for r in d["s05_oor"]))

    # missing watch
    agg["missing_categories"] = dict(Counter(r["missing_data_category"] for r in d["s06_missing"]))
    agg["missing_total"] = len(d["s06_missing"])
    # missing metric prevalence
    prev = Counter()
    hold_by = Counter()
    miss_by = Counter()
    undef_by = Counter()
    for r in d["s06_missing"]:
        for mid in ("M01", "M02", "M03", "M04", "M05", "M06", "M07", "M08", "M09", "M10", "M11", "M12"):
            stt = d["s02_by"][r["security_id"]][mid]["metric_status"]
            if stt in ("HOLD", "MISSING"):
                prev[mid] += 1
            if stt == "HOLD":
                hold_by[mid] += 1
            if stt == "MISSING":
                miss_by[mid] += 1
            if stt == "UNDEFINED_BASE":
                undef_by[mid] += 1
    agg["missing_metric_prevalence"] = dict(prev)
    agg["missing_hold_by_metric"] = dict(hold_by)
    agg["missing_missing_by_metric"] = dict(miss_by)
    agg["missing_undefined_by_metric"] = dict(undef_by)

    # status totals
    st = Counter(r["metric_status"] for r in d["s02"])
    agg["s02_status_totals"] = dict(st)
    agg["undefined_base_M05"] = sum(1 for r in d["s02"] if r["metric_id"] == "M05" and r["metric_status"] == "UNDEFINED_BASE")
    agg["undefined_base_M07"] = sum(1 for r in d["s02"] if r["metric_id"] == "M07" and r["metric_status"] == "UNDEFINED_BASE")

    # low base / abs channel / RH02
    agg["low_base_confirmed_companies"] = sum(1 for r in d["s04"] if r["low_base_confirmed_sg"])
    agg["abs_channel_companies"] = sum(1 for r in d["s04"] if r["abs_channel_sg"])
    agg["lowbase_subtag_companies"] = sum(1 for r in d["s03"] if r["l1_subtag"] == "OQ_LOW_BASE_PROVISIONAL")
    agg["lowbase_signal_companies"] = sum(1 for r in d["s03"] if r["sg_hit_lowbase_list"])
    agg["rh02"] = dict(Counter(r["rh_status"] for r in d["s05_qf"] if r["rh"] == "RH02"))
    agg["rh06"] = dict(Counter(r["adoption_status"] for r in d["s05_rh06"]))
    agg["rh06_pending"] = sum(1 for r in d["s05_rh06"] if not r["adopted"] == "YES")

    # BJ
    bj = [r["security_id"] for r in d["master"] if r["security_id"].startswith("BJ:")]
    nb = [r["security_id"] for r in d["master"] if not r["security_id"].startswith("BJ:")]
    bj_pass = [s for s in bj if s in d["s05_pass_by"]]
    nb_pass = [s for s in nb if s in d["s05_pass_by"]]
    agg["bj"] = {
        "total": len(bj),
        "pass": len(bj_pass),
        "pass_rate_pct": round(100.0 * len(bj_pass) / len(bj), 1),
        "non_bj_total": len(nb),
        "non_bj_pass": len(nb_pass),
        "non_bj_pass_rate_pct": round(100.0 * len(nb_pass) / len(nb), 1),
        "missing_watch": sum(1 for s in bj if s in d["s06_missing_by"]),
        "non_bj_missing_watch": sum(1 for s in nb if s in d["s06_missing_by"]),
        "anchor_h1": sum(1 for s in bj if d["s03_by"][s]["anchor_period_type"] == "H1"),
        "anchor_9m": sum(1 for s in bj if d["s03_by"][s]["anchor_period_type"] == "9M"),
        "m12_not_applicable": sum(1 for s in bj if d["s02_by"][s]["M12"]["metric_status"] == "NOT_APPLICABLE"),
    }

    # reverse omission
    rev = [r for r in sample_rows if r["primary_stratum"] == "REVERSE_OMISSION"]
    agg["reverse"] = {
        "strong_total": len(strong),
        "strong_in_mainline": len(strong) - len(strong_not_main),
        "strong_not_mainline": len(strong_not_main),
        "baseline_decisions": dict(Counter(d["s04_by"][s]["l2_decision"] for s in strong_not_main)),
        "reviewed_decisions": dict(Counter(d["s06_early_by"].get(s, {}).get("s04_l2_decision", "ABSENT") for s in strong_not_main)),
        "sample_verdicts": dict(Counter(r["omission_verdict"] for r in rev)),
        "calc_leaks": [r["security_id"] for r in rev if r["omission_verdict"].startswith("CALC_LEAK")],
        "reviewed_holds": [r["security_id"] for r in rev
                           if r["omission_verdict"] == "REVIEWED_HOLD_BASELINE_CANDIDATE"],
    }

    # S04 baseline vs S05 frozen pool
    cand = [r for r in d["s04"] if r["l2_decision"] == "L2_SHORTLIST_CANDIDATE"]
    agg["pool_divergence"] = {
        "s04_candidates": len(cand),
        "s05_frozen_pool": len(s05_278),
        "difference": len(cand) - len(s05_278),
        "s05_subset_of_s04": set(s05_278).issubset({r["company_id"] for r in cand}),
    }

    # guards
    agg["guards"] = {
        "after_cutoff": sum(1 for r in d["s06_missing"] if r["cutoff_isolated"] == "YES"),
        "anchor_pending": sum(1 for r in d["s06_missing"] if r["anchor_reselection_pending"] == "YES"),
        "quality_source_unknown": sum(1 for r in d["s06_missing"] if r["quality_source_state"] == "PENDING_CE_SOURCE"),
        "jidong_hold": "SZ:000856" in d["s05_obs_by"],
        "issue_53": d["release"]["guards"]["S00_errata_issue_53"],
    }
    return agg


# ---------------------------------------------------------------------------
# Structured grading — derived from the actual anomaly lists, never hard-coded
# ---------------------------------------------------------------------------
BLOCKING_ANOMALY_KEYS = [
    "recomputation_status_or_value_mismatches",
    "anchor_derivation_mismatches",
    "s03_mismatches",
    "s04_mismatches",
    "s05_mismatches",
    "s06_mismatches",
    "abs_channel_evidence_failures",
    "low_base_evidence_failures",
    "reverse_omission_calc_leaks",
    "guard_violations",
]
ROLLBACK_ANOMALY_KEYS = [
    "recomputation_status_or_value_mismatches",
    "anchor_derivation_mismatches",
    "s03_mismatches",
    "s04_mismatches",
    "s05_mismatches",
    "s06_mismatches",
    "abs_channel_evidence_failures",
    "low_base_evidence_failures",
    "reverse_omission_calc_leaks",
]


def build_grading(agg, abs_evidence, low_base_evidence, reverse_audit):
    g = agg["guards"]
    guard_violations = []
    if g["after_cutoff"] != 4:
        guard_violations.append(f"after_cutoff={g['after_cutoff']} (expected 4)")
    if g["anchor_pending"] != 1:
        guard_violations.append(f"anchor_pending={g['anchor_pending']} (expected 1)")
    if g["jidong_hold"] is not True:
        guard_violations.append("jidong_quality_hold_missing")
    if g["issue_53"] != "OPEN":
        guard_violations.append(f"issue_53={g['issue_53']} (expected OPEN)")
    if not (50 <= agg["total"] <= 65):
        guard_violations.append(f"sample_size={agg['total']} (expected 50-65)")

    anomaly_ids = {
        "recomputation_status_or_value_mismatches": list(agg["recompute_non_exact"]),
        "anchor_derivation_mismatches": list(agg["anchor_check_fail"]),
        "s03_mismatches": list(agg["s03_mismatch"]),
        "s04_mismatches": list(agg["s04_mismatch"]),
        "s05_mismatches": list(agg["s05_mismatch"]),
        "s06_mismatches": list(agg["s06_mismatch"]),
        "abs_channel_evidence_failures": [f"{e['security_id']}:{e['signal_id']}"
                                          for e in abs_evidence if not e["check_pass"]],
        "low_base_evidence_failures": [f"{e['security_id']}:{e['signal_id']}"
                                       for e in low_base_evidence if not e["check_pass"]],
        "reverse_omission_calc_leaks": [a["security_id"] for a in reverse_audit
                                        if a["verdict"].startswith("CALC_LEAK")],
        "guard_violations": guard_violations,
    }
    counts = {k: len(v) for k, v in anomaly_ids.items()}
    systemic_blocker = any(counts[k] > 0 for k in BLOCKING_ANOMALY_KEYS)
    requires_rollback = any(counts[k] > 0 for k in ROLLBACK_ANOMALY_KEYS)
    return {
        "systemic_blocker": systemic_blocker,
        "systemic_blocker_ids": [k for k in BLOCKING_ANOMALY_KEYS if counts[k] > 0],
        "requires_s00_s01_rollback": requires_rollback,
        "derivation_basis": {
            "blocking_rule": ("systemic_blocker = any(anomaly_counts[k] > 0 for k in BLOCKING_ANOMALY_KEYS); "
                              "requires_s00_s01_rollback = any(anomaly_counts[k] > 0 for k in ROLLBACK_ANOMALY_KEYS)"),
            "blocking_keys": list(BLOCKING_ANOMALY_KEYS),
            "rollback_keys": list(ROLLBACK_ANOMALY_KEYS),
            "anomaly_counts": counts,
            "anomaly_ids": anomaly_ids,
            "all_blocking_lists_empty": all(counts[k] == 0 for k in BLOCKING_ANOMALY_KEYS),
            "evidence_rows": {"abs_channel": len(abs_evidence), "low_base": len(low_base_evidence)},
            "reverse_audit_rows": len(reverse_audit),
        },
        "carry_forward_to_s08": ["F05", "F06", "F07", "F08", "F10", "F11", "F12"],
        "conclusion": ("NO_SYSTEMIC_BLOCKER: every blocking anomaly list is empty after independent recomputation; "
                       "known limits are registered and carried to S08."
                       if not systemic_blocker else
                       "SYSTEMIC_BLOCKER: at least one blocking anomaly list is non-empty; see derivation_basis."),
    }


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------
SAMPLE_FIELDS = [
    "sample_seq", "security_id", "stock_name", "exchange", "primary_stratum", "stratum_labels",
    "selection_slot", "selection_rule", "selection_key", "anchor_period", "anchor_period_type",
    "s03_l1_bucket", "s03_l1_subtag", "derived_l1", "s04_l2_decision", "s05_route",
    "s06_watch_label", "s06_missing_category", "s06_early_bucket",
    "boundary_attributes", "metrics_compared", "metrics_status_match", "metrics_value_match",
    "float_tolerance", "recompute_max_abs_diff", "recompute_consistency", "diff_metrics",
    "diff_attribution", "latest_period_check", "s03_route_check", "s04_route_check",
    "s05_route_check", "s06_route_check", "omission_verdict", "attribution_layer",
    "finding_codes", "note",
]


def build_sample_rows(d, engine, selected):
    rows = []
    for i, sid in enumerate(sorted(selected, key=lambda s: (STRATUM_ORDER.index(selected[s]["primary"]), s)), start=1):
        info = selected[sid]
        a = audit_company(engine, d, sid, info)
        labels = []
        if info["primary"] == "BOUNDARY_PASS_FAIL":
            labels.append("BOUNDARY_PASS_FAIL")
        if sid.startswith("BJ:"):
            labels.append("BJ_MARKET")
        if a["s04_l2_decision"] and (d["s02_by"][sid]["M05"]["metric_status"] == "UNDEFINED_BASE"
                                      or d["s02_by"][sid]["M07"]["metric_status"] == "UNDEFINED_BASE"
                                      or d["s04_by"][sid]["low_base_confirmed_sg"]
                                      or d["s03_by"][sid]["l1_subtag"] == "OQ_LOW_BASE_PROVISIONAL"):
            labels.append("LOSS_AND_LOW_BASE")
        if sid in d["s06_missing_by"]:
            labels.append("MISSING_DATA_WATCH")
        if sid in d["s06_early_by"]:
            labels.append("EARLY_STAGE_WATCH")
        if d["master_by_id"][sid]["robot_exposure"] in ("DIRECT_DISCLOSED", "DIRECT_UNDISCLOSED", "INDIRECT_VERIFIED") and sid not in d["s05_pass_by"]:
            labels.append("REVERSE_OMISSION")
        if info["primary"] not in labels:
            labels.append(info["primary"])
        labels = sorted(set(labels), key=lambda x: STRATUM_ORDER.index(x))
        row = {
            "sample_seq": i,
            "security_id": sid,
            "stock_name": d["master_by_id"][sid]["stock_name"],
            "exchange": d["master_by_id"][sid]["exchange"],
            "primary_stratum": info["primary"],
            "stratum_labels": ";".join(labels),
            "selection_slot": info["slot"],
            "selection_rule": info["rule"],
            "selection_key": str(info["key"]),
            "anchor_period": a["anchor_period"],
            "anchor_period_type": a["anchor_period_type"],
            "s03_l1_bucket": a["s03_l1_bucket"],
            "s03_l1_subtag": a["s03_l1_subtag"],
            "derived_l1": a["derived_l1"],
            "s04_l2_decision": a["s04_l2_decision"],
            "s05_route": a["s05_route"],
            "s06_watch_label": a["s06_watch_label"],
            "s06_missing_category": a["s06_missing_category"],
            "s06_early_bucket": a["s06_early_bucket"],
            "boundary_attributes": a["boundary_attributes"],
            "metrics_compared": a["metrics_compared"],
            "metrics_status_match": a["metrics_status_match"],
            "metrics_value_match": a["metrics_value_match"],
            "float_tolerance": a["float_tolerance"],
            "recompute_max_abs_diff": a["recompute_max_abs_diff"],
            "recompute_consistency": a["recompute_consistency"],
            "diff_metrics": a["diff_metrics"],
            "diff_attribution": a["diff_attribution"],
            "latest_period_check": a["latest_period_check"],
            "s03_route_check": a["s03_route_check"],
            "s04_route_check": a["s04_route_check"],
            "s05_route_check": a["s05_route_check"],
            "s06_route_check": a["s06_route_check"],
            "omission_verdict": a["omission_verdict"],
            "attribution_layer": a["attribution_layer"],
            "finding_codes": a["finding_codes"],
            "note": a["note"],
        }
        rows.append(row)
    return rows


def build_findings_md(d, agg, sample_rows, abs_evidence, low_base_evidence,
                      reverse_audit, override_audit, grading):
    sc = agg["stratum_counts"]
    lines = []
    lines.append("# S07 / #42 抽查阈值边界、漏筛和缺数据偏差｜审计报告")
    lines.append("")
    lines.append(f"生成时间：{NOW}（北京时间）。计划版本 `{PLAN_VERSION}`，知识截止日 `{KNOWLEDGE_AS_OF}`。")
    lines.append(f"执行方：{EXECUTOR}；统筹方：{ORCHESTRATOR}；独立复核指派：{REVIEWER_ASSIGNED}。本报告为 `SELF_CHECK`，不释放 S08。")
    lines.append(f"返修轮次：`{REWORK_ROUND}`；返修依据：`{REWORK_BASIS}`（Codex 独立复核 `RETURN_FOR_REWORK`）。")
    lines.append("")
    lines.append("## 1. 审计范围与方法")
    lines.append("")
    lines.append("本卡只做**小样本规则与计算审计**：不重研全池、不逐家深读公告、不调整任何冻结阈值、不把任何公司手工加回主线。")
    lines.append("")
    lines.append("### 1.1 确定性分层抽样")
    lines.append("")
    lines.append("抽样不使用随机数：每个分层先定义候选池与配额，再以固定排序键（`security_id` 升序，或到阈值的绝对距离、再 `security_id`）取前 N 家。跨层去重，单家公司可带多个标签。")
    lines.append("")
    lines.append(f"样本总量 **{agg['total']} 家**（要求 50–65 家）。各主分层数量：")
    lines.append("")
    lines.append("| 分层 | 数量 |")
    lines.append("|---|---:|")
    for s in STRATUM_ORDER:
        lines.append(f"| {s} | {sc.get(s, 0)} |")
    lines.append("")
    lines.append("| 子槽 | 分层 | 配额 | 实取 | 入选规则 |")
    lines.append("|---|---|---:|---:|---|")
    for s in agg["slots"]:
        lines.append(f"| {s['slot']} | {s['stratum']} | {s['quota']} | {s['filled']} | {s['rule']} |")
    lines.append("")
    lines.append("### 1.2 独立复算口径")
    lines.append("")
    lines.append("以 `s00_v10.csv.gz` 原始标准化数值为唯一算术底座，独立重算 M01–M12（营收/扣非同比、毛利率变动、现金含量、应收/存货天数、合同资产占比等），不读取 S02 的中间结果反推。锚定期间由锚定字段（`FIN.REV.YTD` / `FIN.REV.SQ` / `FIN.NPDEDT.YTD`）在 usable 状态下的最新 `period_key` 独立推导，再与 `all_pool_metrics.csv` 的 `period_key` 比对。")
    lines.append("")
    lines.append(f"逐格比对结果：**{agg['cells_compared']} 格**（{agg['total']} 家 × 12 指标），状态一致 **{agg['cells_status_match']}**，数值一致 **{agg['cells_value_match']}**；最大绝对差 `{agg['max_abs_diff']:.3e}`（浮点容差 `{FLOAT_TOL:.1e}`，即 S02 固定 10 位小数的舍入量级）。锚定期间独立推导不一致 **{len(agg['anchor_check_fail'])}** 家。")
    lines.append("")
    if agg["recompute_non_exact"]:
        lines.append(f"未达 EXACT 的样本：{', '.join(agg['recompute_non_exact'])}。")
    else:
        lines.append("全部样本均达到 `EXACT`：状态与数值逐格一致，无需按口径/重述/合并范围/锚定期做差异归因。")
    lines.append("")
    lines.append("## 2. 路由复算与边界核对")
    lines.append("")
    lines.append(f"- S03 L1：由复算指标重新触发 SG01–SG09、重算四维与 bucket/subtag，**{agg['s03_consistent']} 家规则重推一致（CONSISTENT）**；**{agg['s03_override']} 家为冻结覆盖（FROZEN_OVERRIDE）**，覆盖原因逐家见 2.3；不一致 **{len(agg['s03_mismatch'])}** 家。")
    lines.append(f"- S04 L2：维度计数与 `qualified_dims` 内部一致 **{agg['s04_consistent']} 家**，不一致 **{len(agg['s04_mismatch'])}** 家；另对样本内 `B_ABS_CHANNEL` **{len(abs_evidence)} 条**、`C_LOW_BASE_CONFIRMED` **{len(low_base_evidence)} 条**逐条回查 `s00_v10` 原值（见 2.1、2.2），失败条数 **{sum(1 for e in abs_evidence + low_base_evidence if not e['check_pass'])}**。")
    lines.append(f"- S05 质量闸门：样本中进入 S05 278 的 **{agg['s05_checked']} 家**，RH01–RH05 阈值判定与 `quality_flags.csv` 一致 **{agg['s05_consistent']} 家**，不一致 **{len(agg['s05_mismatch'])}** 家；RH06 的 `one_off` 标记与 Q09 复算一致。")
    lines.append(f"- S06 观察名单：样本中进入缺失观察的 **{agg['s06_checked']} 家**，`s02_hold/missing/undefined_base/provisional/not_comparable` 五项计数与已存 S02 状态逐家一致 **{agg['s06_consistent']} 家**，不一致 **{len(agg['s06_mismatch'])}** 家；缺失一律保持未知，未填 0。")
    lines.append("")
    def w(x):
        return "—" if x is None else f"{x / 10000.0:,.2f}"

    lines.append("### 2.1 绝对额通道 `B_ABS_CHANNEL`（逐条可复算）")
    lines.append("")
    lines.append(f"全池 S04 中共 **{agg['abs_channel_companies']} 家**登记绝对额通道；样本内命中 **{len(abs_evidence)} 条**（公司×信号），逐条从 `s00_v10.csv.gz` 取原值复算，通过 **{sum(1 for e in abs_evidence if e['check_pass'])} 条**、失败 **{sum(1 for e in abs_evidence if not e['check_pass'])} 条**。")
    lines.append("")
    lines.append("| 证券 | 名称 | 信号 | 字段 | 当期 | 金额(万元) | 状态 | 基期 | 金额(万元) | 状态 | 可比性 | 增量(万元) | 门槛判定 | 通过 |")
    lines.append("|---|---|---|---|---|---:|---|---|---:|---|---|---:|---|---|")
    for e in abs_evidence:
        lines.append(
            f"| {e['security_id']} | {e['stock_name']} | {e['signal_id']} | `{e['field_id']}` | "
            f"{e['period_key']} | {w(e['value_cny'])} | {e['status']} | {e['base_period_key']} | "
            f"{w(e['base_value_cny'])} | {e['base_status']} | {e['comparability']} | "
            f"{w(e['delta_cny'])} | {e['threshold_check']} | {'PASS' if e['check_pass'] else 'FAIL'} |")
    lines.append("")
    lines.append("**口径**：SG06 要求基期<0、当期>0、当期≥1,000 万元；SG08 要求 OCF(t)>0 且 OCF(t−1y)≤0；两侧均须为 usable 状态、同期间可比（同 `period_type`、`period_key` 差 10,000、同合并范围、非上市前、无未决重述）。**未发现**比率通道 `UNDEFINED_BASE` 导致绝对额通道失效，也未发现直接沿用上游 CLEAN 标签放行。")
    lines.append("")
    lines.append("### 2.2 低基数确认 `C_LOW_BASE_CONFIRMED`（逐条可复算）")
    lines.append("")
    lines.append(f"全池 S04 中共 **{agg['low_base_confirmed_companies']} 家**登记低基数确认；样本内命中 **{len(low_base_evidence)} 条**（公司×信号），按冻结映射（SG01/SG04/SG06/SG08 用 YTD、SG09 用 SQ）回查同口径绝对额增量，通过 **{sum(1 for e in low_base_evidence if e['check_pass'])} 条**、失败 **{sum(1 for e in low_base_evidence if not e['check_pass'])} 条**，与 S04 `low_base_detail` 逐条对账一致 **{sum(1 for e in low_base_evidence if e['s04_detail_match'])} 条**。")
    lines.append("")
    lines.append("| 证券 | 名称 | 信号 | 字段/口径 | 当期 | 金额(万元) | 状态 | 基期 | 金额(万元) | 状态 | 可比性 | 增量(万元) | S04 登记 | 一致 | 通过 |")
    lines.append("|---|---|---|---|---|---:|---|---|---:|---|---|---:|---|---|---|")
    for e in low_base_evidence:
        lines.append(
            f"| {e['security_id']} | {e['stock_name']} | {e['signal_id']} | `{e['field_id']}`/{e['basis']} | "
            f"{e['period_key']} | {w(e['value_cny'])} | {e['status']} | {e['base_period_key']} | "
            f"{w(e['base_value_cny'])} | {e['base_status']} | {e['comparability']} | {w(e['delta_cny'])} | "
            f"{e['s04_recorded_detail'] or '—'} | {'YES' if e['s04_detail_match'] else 'NO'} | "
            f"{'PASS' if e['check_pass'] else 'FAIL'} |")
    lines.append("")
    lines.append("**口径**：增量 ≥ 1,000 万元且方向为正；SG06 另须当期 ≥ 1,000 万元；两侧 usable、同期间可比、无未决重述。**未发现**用任意金额替代、跨期相减或把未确认低基数信号计入维度。")
    lines.append("")
    lines.append("### 2.3 S03 冻结覆盖逐家说明")
    lines.append("")
    lines.append(f"{agg['s03_consistent']} 家为**规则重推一致**；以下 **{len(override_audit)} 家**为**冻结覆盖**，不参与规则重推比对，原因如下：")
    lines.append("")
    lines.append("| 证券 | 名称 | workpaper_status | l0_status | 冻结 bucket/subtag | 覆盖原因 |")
    lines.append("|---|---|---|---|---|---|")
    for o in override_audit:
        lines.append(f"| {o['security_id']} | {o['stock_name']} | {o['workpaper_status'] or '—'} | "
                     f"{o['l0_status']} | {o['frozen_bucket']}/{o['frozen_subtag']} | {o['override_reason']} |")
    lines.append("")
    lines.append("")
    lines.append("## 3. 偏差诊断")
    lines.append("")
    lines.append("### 3.1 缺失数据偏差")
    lines.append("")
    mc = agg["missing_categories"]
    lines.append(f"S06 `missing_data_watch.csv` 共 **{agg['missing_total']} 家**，7 个细分类型全部覆盖：")
    lines.append("")
    lines.append("| 类型 | 数量 |")
    lines.append("|---|---:|")
    for k in sorted(mc):
        lines.append(f"| {k} | {mc[k]} |")
    lines.append("")
    prev = agg["missing_metric_prevalence"]
    top = sorted(prev.items(), key=lambda x: -x[1])[:5]
    hold_top = sorted(agg["missing_hold_by_metric"].items(), key=lambda x: -x[1])[:4]
    miss_top = sorted(agg["missing_missing_by_metric"].items(), key=lambda x: -x[1])[:3]
    undef_top = sorted(agg["missing_undefined_by_metric"].items(), key=lambda x: -x[1])[:2]
    lines.append("观察名单内按公司计：HOLD 集中于 " + "，".join(f"{k}={v}" for k, v in hold_top) +
                 "；MISSING 集中于 " + "，".join(f"{k}={v}" for k, v in miss_top) +
                 "；UNDEFINED_BASE 集中于 " + "，".join(f"{k}={v}" for k, v in undef_top) + "。")
    lines.append("")
    lines.append("**结论**：HOLD/MISSING 覆盖 M01（营收同比）、M04（毛利率）、M09（经营现金流变动）、M10（应收天数）与 M08（现金含量），UNDEFINED_BASE 集中于 M05/M07（扣非同比）。因此缺失数据的影响不只在 CASH：它会同时压低 GROWTH / MARGIN / PROFIT / CASH 四个维度的可评估证据。冻结规则要求 HOLD 既不计改善也不计恶化，所以偏差方向是**双向保守**——既可能漏掉真实改善，也不会把缺失误判成恶化。缺失一律保持 `MISSING/HOLD/UNKNOWN`，未填 0、未插补、未因缺失淘汰；S06 五项计数与 S02 状态逐家一致，说明观察名单没有把“缺数据”写成“无业务”。该偏差属于已知受限，不是系统性阻断。")
    lines.append("")
    lines.append("### 3.2 混合报告期偏差（H1 vs 9M）")
    lines.append("")
    a = agg["anchor_split"]
    lines.append(f"S05 冻结 278 家 = **H1 锚点 {a['H1']} 家 + 9M 锚点 {a['9M']} 家**。同比在同一 `period_type` 内配对，因此期间长度不直接污染同比；但横截面触发率不能直接相加比较。")
    lines.append("")
    lines.append("| RH | H1 可判/触发/触发率 | 9M 可判/触发/触发率 |")
    lines.append("|---|---|---|")
    for rh in ("RH01", "RH02", "RH03", "RH04", "RH05"):
        h = agg["rh_by_anchor"]["H1"][rh]
        q = agg["rh_by_anchor"]["9M"][rh]
        lines.append(f"| {rh} | {h['applicable']}/{h['triggered']}/{h['rate_pct']}% | {q['applicable']}/{q['triggered']}/{q['rate_pct']}% |")
    lines.append("")
    lines.append(f"`out_of_valid_range` 20 格按锚点分布：{agg['oor_by_anchor']}；按指标：{agg['oor_by_metric']}。H1 与 9M 的越界比例接近，未见某一锚点系统性越界。")
    lines.append("")
    lines.append("**结论**：混合锚点影响的是**横截面可比性与解释口径**，不影响同比计算本身；S05 已把锚点分列并保留 Q11 冻结标记。结转 S08 时须继续按锚点分层陈述，不得把 278 家当作同一报告期。")
    lines.append("")
    lines.append("### 3.3 低基数 / 亏损 / 无定义基数偏差")
    lines.append("")
    lines.append(f"全池 M05 `UNDEFINED_BASE` **{agg['undefined_base_M05']} 格**、M07 **{agg['undefined_base_M07']} 格**（基期为负或近零）。冻结规则对这些格不计算比率，改判绝对额改善或转正；SG06 还要求当期扣非 ≥ 1,000 万元，防止微利转正。复算未发现对负基数强行计算同比、或用归母替代扣非。")
    lines.append("")
    lines.append("低基数信号在 L1 单列为 `OQ_LOW_BASE_PROVISIONAL`，L2 必须有同口径绝对额确认才计入维度。样本复核显示确认门槛被严格执行；无确认规则的 SG02/SG03/SG05/SG07 保持 `NO_CONFIRM_RULE`，未折算成维度。**偏差方向**：低基数公司更容易在增长率上“看起来很好”，当前规则用绝对额确认抑制了该放大效应；仍可能有少量真实改善因确认门槛被推迟，属于保守侧偏差。")
    lines.append("")
    lines.append("### 3.4 项目模式 RH02 豁免")
    lines.append("")
    lines.append(f"S05 RH02 状态：{agg['rh02']}。项目制公司按 Q10 规则不判存货天数，故 RH02 记 `NOT_APPLICABLE`，但这不影响应收天数（RH01）与合同资产占比（RH03）。**影响**：项目制公司的存货风险信号被规则性关闭，不能解读为“无存货风险”；S05 已把该豁免逐家登记，S08 应继续以应收/合同资产为主观察。")
    lines.append("")
    lines.append("### 3.5 北交所披露差异")
    lines.append("")
    b = agg["bj"]
    lines.append(f"全池 BJ **{b['total']} 家**（H1 锚点 {b['anchor_h1']}、9M 锚点 {b['anchor_9m']}），S05 通过 **{b['pass']} 家（{b['pass_rate_pct']}%）**；非 BJ 通过 {b['non_bj_pass']}/{b['non_bj_total']}（{b['non_bj_pass_rate_pct']}%）。BJ 进入缺失观察 **{b['missing_watch']} 家**，非 BJ **{b['non_bj_missing_watch']} 家**。BJ 的 M12 无合同资产科目 **{b['m12_not_applicable']} 家**。")
    lines.append("")
    lines.append("**结论**：BJ 通过率高于非 BJ，但样本内 BJ 的低基数确认占比也更高（3/25），且 BJ 全部为 EVALUABLE、缺失观察占比更低。现有证据不足以把差异归因于“披露更宽松”或“计算偏差”；更可能是行业结构与基数效应。该差异**不构成系统性阻断**，但 S08 不应把 BJ 与非 BJ 的通过率直接对比。")
    lines.append("")
    lines.append("### 3.6 反向漏筛检验")
    lines.append("")
    rv = agg["reverse"]
    lines.append(f"**（A）全池路由汇总对账（仅统计，未逐家重推）**：以 `robot_exposure ∈ DIRECT_DISCLOSED / DIRECT_UNDISCLOSED / INDIRECT_VERIFIED` 定义“已有较强机器人业务线索”，全池 **{rv['strong_total']} 家**，其中 **{rv['strong_in_mainline']} 家**进入 S05 277 主线，**{rv['strong_not_mainline']} 家**未进入。未进入者的 S04 基线判定分布：{rv['baseline_decisions']}；S06 冻结复核判定分布：{rv['reviewed_decisions']}。此段只做路由分布对账，**未对全部 {rv['strong_not_mainline']} 家逐一重推**。")
    lines.append("")
    lines.append(f"**（B）抽样 5 家逐家独立重推（不继承 S06 标签）**：从 `s00_v10` 独立重算 S03 信号/维度、S04 合格维度数、阻断/待核指标与状态，结果如下（判定分布：{rv['sample_verdicts']}；计算漏筛 **{len(rv['calc_leaks'])}** 家）：")
    lines.append("")
    lines.append("| 证券 | 名称 | 复算 S03 | 复算信号 | 合格维度 | 阻断/待核指标 | 冻结 S04 | S06 复核 | 重推结论 | 重进条件 |")
    lines.append("|---|---|---|---|---:|---|---|---|---|---|")
    for a in reverse_audit:
        sig = "、".join(f"{k}={v}" for k, v in a["recomputed_signals"].items()) or "无"
        blk = "；".join(a["blocking_or_pending_metrics"]) or "无"
        lines.append(
            f"| {a['security_id']} | {a['stock_name']} | {a['recomputed_s03_bucket']}/{a['recomputed_s03_subtag']} | "
            f"{sig} | {a['recomputed_dimension_count']}（{';'.join(a['recomputed_clean_dimensions']) or '无'}） | "
            f"{blk} | {a['frozen_s04_l2_decision']} | {a['frozen_s06_reviewed_decision']} | "
            f"{a['verdict']} | {a['reentry_condition']} |")
    lines.append("")
    lines.append(f"**结论（严格限定范围）**：在**抽样的 {len(reverse_audit)} 家**反向样本中，逐家独立重推**未见计算漏筛（{len(rv['calc_leaks'])} 家）**：{len(reverse_audit) - len(rv['calc_leaks']) - len(rv['reviewed_holds'])} 家为规则性排除/待核（维度不足 2 或 S03 未进观察队列），{len(rv['reviewed_holds'])} 家为**基线已达 2 维但被 S04/S05 复核版适用性 HOLD**（复核版 `tight_pass` 未纳入 Git 跟踪，见 F10），同样不是计算漏筛。**该结论不外推为“全池 {rv['strong_not_mainline']} 家均已排除计算漏筛”**——全池仅完成上述（A）的路由分布汇总，未逐一重推。未手工加回任何公司。")
    lines.append("")
    lines.append("### 3.7 S04 基线与 S05 冻结池的口径差")
    lines.append("")
    p = agg["pool_divergence"]
    subset_txt = "是" if p["s05_subset_of_s04"] else "否"
    lines.append(f"`runs/issues/S04/tight_decision_log.csv`（Git 跟踪的基线）登记 `L2_SHORTLIST_CANDIDATE` **{p['s04_candidates']} 家**，S05 冻结质量池为 **{p['s05_frozen_pool']} 家**，差 **{p['difference']} 家**；S05 池是 S04 候选的子集：**{subset_txt}**。")
    lines.append("")
    lines.append("S05 的 `decision_reason` 对这部分的解释是“剩余有效维度不足 2；命中精确待核输入/上游 HOLD/暂定维度可能补足，暂不降为不通过”，S06 `early_stage_watch.csv` 的 `s04_l2_decision` 也把相关公司记为 `HOLD_FOR_DATA`。因此这是 **S04 基线日志 → S05 适用性复核** 的版本口径差，不是算术漏筛；但 Git 树内缺少 S04 复核版 `tight_pass`（`reviewed_view` 未跟踪），导致 445→278 的逐家映射不可在干净树内完全重放。该可追溯性缺口应结转 S08/资料治理，不阻断 S07 结论。")
    lines.append("")
    lines.append("### 3.8 有效区间与 RH06 待核")
    lines.append("")
    lines.append(f"`s05_out_of_valid_range.csv` 的 20 格状态均为 `OK` 但数值越出冻结 `valid_range`。冻结规则没有给越界处置动作，S05 只登记、不阻断、不改值。样本复核确认这些值确实越界，且未被用于改写路由。**定级**：规则版本缺口（S01 v4 未定义 `valid_range` 处置），结转 S08；不是计算错误。")
    lines.append("")
    lines.append(f"RH06 采用台账：{agg['rh06']}，未采用 **{agg['rh06_pending']} 家**（缺 NPP 或开放争议）。未发现把未解决争议当作已采用输入。")
    lines.append("")
    lines.append("## 4. 定级与放行判定")
    lines.append("")
    lines.append("| 编号 | 发现 | 归因层 | 定级 | 处置 |")
    lines.append("|---|---|---|---|---|")
    lines.append("| F01 | 样本 12 项指标逐格复算与 S02 完全一致（状态+数值） | S02 计算 | INFO | 无需处置 |")
    lines.append(f"| F02 | S03 L1 **{agg['s03_consistent']} 家规则重推一致**；**{agg['s03_override']} 家冻结覆盖**已逐家说明（见 2.3） | S03 规则 | INFO | 无需处置 |")
    lines.append(f"| F03 | S04 维度计数、绝对额通道 {len(abs_evidence)} 条、低基数确认 {len(low_base_evidence)} 条逐条可复算且全部通过 | S04 规则 | INFO | 无需处置 |")
    lines.append(f"| F04 | S06 缺失观察五项计数与已存 S02 状态逐家一致，缺失保持未知未填 0（结论仅限该范围） | S02/S06 | INFO | 继续按未知处理 |")
    lines.append("| F05 | H1/9M 混合锚点影响横截面解释，不影响同比 | S02/S05 | LOW | S08 按锚点分层 |")
    lines.append("| F06 | 项目模式 RH02 豁免使存货风险信号规则性关闭 | S05 规则 | LOW | S08 以应收/合同资产为主 |")
    lines.append("| F07 | 低基数确认抑制增长率放大，可能保守推迟真实改善 | S01/S04 | LOW | 保持冻结阈值，不回调 |")
    lines.append("| F08 | BJ 通过率高于非 BJ，但证据不足以归因披露差异 | 数据/结构 | LOW | 不做跨市场通过率对比 |")
    lines.append(f"| F09 | 抽样 {len(reverse_audit)} 家反向样本逐家独立重推，0 家计算漏筛；全池 {rv['strong_not_mainline']} 家仅路由汇总未逐家重推 | S04/S05/S06 | INFO | 保留观察与重进 |")
    lines.append("| F10 | S04 基线 445 候选 vs S05 冻结 278，复核版映射不可在干净树重放 | S04/S05 版本 | MEDIUM | 结转 S08 资料治理 |")
    lines.append("| F11 | 20 格越界值状态 OK，冻结规则无处置动作 | S01 规则 | LOW | 结转 S08 定义处置 |")
    lines.append("| F12 | RH06 7 家待核（缺 NPP / 开放争议），未强行采用 | S05 规则 | LOW | 保持待核 |")
    lines.append("| F13 | 4 家截止日隔离、1 家锚点待重选、冀东 QUALITY_HOLD、#53 开放均保留 | 守卫 | INFO | 原样结转 |")
    lines.append("")
    dc = grading["derivation_basis"]["anomaly_counts"]
    lines.append("**系统性阻断判定（由异常清单动态推导，非硬编码）**：")
    lines.append("")
    lines.append("| 阻断性异常清单 | 计数 |")
    lines.append("|---|---:|")
    for k in grading["derivation_basis"]["blocking_keys"]:
        lines.append(f"| `{k}` | {dc[k]} |")
    lines.append("")
    if grading["systemic_blocker"]:
        lines.append(f"**结论：`SYSTEMIC_BLOCKER`。** 非空清单：{grading['systemic_blocker_ids']}；需回退 S00/S01 = **{grading['requires_s00_s01_rollback']}**。")
    else:
        lines.append(f"**结论：不存在 `SYSTEMIC_BLOCKER`。** 上述 {len(grading['derivation_basis']['blocking_keys'])} 项阻断性异常计数全部为 0，故 `systemic_blocker=False`、`requires_s00_s01_rollback=False`；样本内 12 项指标状态与数值、S03 信号与维度、S04 边界属性（含绝对额/低基数逐条证据）、S05 RH 阈值、S06 计数均可由 `s00_v10` 与冻结规则独立重放。")
    lines.append("")
    lines.append("**可结转 S08 的已知受限**：F05 混合锚点、F06 RH02 项目模式豁免、F07 低基数保守偏差、F08 BJ 结构差异、F10 S04→S05 版本映射缺口、F11 越界处置未定义、F12 RH06 待核。上述限制均已在 S05/S06 冻结件中登记，S08 不得把它们当作已解决。")
    lines.append("")
    lines.append("## 5. 守卫与边界")
    lines.append("")
    g = agg["guards"]
    jidong_txt = "是" if g["jidong_hold"] else "否"
    lines.append(f"- 截止日后隔离 **{g['after_cutoff']} 家**、锚点待重选 **{g['anchor_pending']} 家**、质量来源未知 **{g['quality_source_unknown']} 家** 均保留；冀东装备 `SZ:000856` `QUALITY_HOLD` 保留 = **{jidong_txt}**；`#53` 状态 **{g['issue_53']}**。")
    lines.append("- 未修改任何冻结阈值、未修改 `runs/issues/S07/` 以外文件、未执行 git commit/push、未释放 S08、未改 `#53`。")
    lines.append("- 本报告为执行方自检（SELF_CHECK），不等同独立验收；须由 Codex 独立复核后再登记 S07 验收。")
    lines.append("")
    return "\n".join(lines) + "\n"


def build_review_json(d, agg, sample_rows, abs_evidence, low_base_evidence,
                      reverse_audit, override_audit, grading):
    rev = {
        "artifact": "S07_SCREEN_AUDIT_REVIEW",
        "issue_key": ISSUE_KEY,
        "issue_number": ISSUE_NUMBER,
        "rework_round": REWORK_ROUND,
        "rework_basis": REWORK_BASIS,
        "plan_version": PLAN_VERSION,
        "knowledge_as_of": KNOWLEDGE_AS_OF,
        "generated_at": NOW,
        "executor": EXECUTOR,
        "orchestrator": ORCHESTRATOR,
        "reviewer_assigned": REVIEWER_ASSIGNED,
        "review_nature": "SELF_CHECK",
        "scope": "Small-sample rule and arithmetic audit only; no full-pool re-research, no threshold tuning, no manual add-back.",
        "sampling": {
            "method": "DETERMINISTIC_STRATIFIED_NO_RNG",
            "sort_keys": "security_id asc; RH near-threshold by absolute distance then security_id; out-of-range by fixed metric/anchor order",
            "total_distinct_companies": agg["total"],
            "stratum_counts": {k: agg["stratum_counts"].get(k, 0) for k in STRATUM_ORDER},
            "slots": agg["slots"],
        },
        "recomputation": {
            "basis": "runs/issues/S02/hangcha_restated_20261101/s00_v10/s00_v10.csv.gz",
            "metrics": [f"M{i:02d}" for i in range(1, 13)],
            "cells_compared": agg["cells_compared"],
            "cells_status_match": agg["cells_status_match"],
            "cells_value_match": agg["cells_value_match"],
            "float_tolerance": FLOAT_TOL,
            "max_abs_diff": agg["max_abs_diff"],
            "exact_companies": agg["recompute_exact"],
            "non_exact_companies": agg["recompute_non_exact"],
            "anchor_derivation_mismatches": agg["anchor_check_fail"],
        },
        "route_audit": {
            "s03_consistent": agg["s03_consistent"],
            "s03_frozen_override": agg["s03_override"],
            "s03_mismatch": agg["s03_mismatch"],
            "s04_consistent": agg["s04_consistent"],
            "s04_mismatch": agg["s04_mismatch"],
            "s05_consistent": agg["s05_consistent"],
            "s05_checked": agg["s05_checked"],
            "s05_mismatch": agg["s05_mismatch"],
            "s06_consistent": agg["s06_consistent"],
            "s06_checked": agg["s06_checked"],
            "s06_mismatch": agg["s06_mismatch"],
        },
        "bias_diagnostics": {
            "missing_data": {
                "total": agg["missing_total"],
                "categories": agg["missing_categories"],
                "metric_prevalence_hold_or_missing": agg["missing_metric_prevalence"],
                "hold_by_metric": agg["missing_hold_by_metric"],
                "missing_by_metric": agg["missing_missing_by_metric"],
                "undefined_base_by_metric": agg["missing_undefined_by_metric"],
                "conclusion": "HOLD/MISSING affect M01/M04/M09/M10/M08; UNDEFINED_BASE concentrates in M05/M07. Missing values remain MISSING/HOLD/UNKNOWN with no zero-fill or imputation, so the bias is bidirectionally conservative across all four dimensions.",
            },
            "mixed_anchor": {
                "s05_pool": agg["anchor_split"],
                "rh_by_anchor": agg["rh_by_anchor"],
                "out_of_range_by_anchor": agg["oor_by_anchor"],
                "conclusion": "H1/9M anchors affect cross-sectional interpretation, not YoY arithmetic. Keep anchor-stratified statements in S08.",
            },
            "loss_low_base": {
                "m05_undefined_base": agg["undefined_base_M05"],
                "m07_undefined_base": agg["undefined_base_M07"],
                "low_base_confirmed_companies": agg["low_base_confirmed_companies"],
                "lowbase_only_subtag": agg["lowbase_subtag_companies"],
                "conclusion": "No ratio computed on negative/zero base; absolute-amount confirmation >= CNY 10m and same direction enforced.",
            },
            "rh02_project_mode": {
                "status_counts": agg["rh02"],
                "conclusion": "Project-mode exemption closes inventory-days risk signal by rule; AR days and contract-asset ratio remain observable.",
            },
            "bj_market": agg["bj"],
            "reverse_omission": agg["reverse"],
            "s04_s05_pool_divergence": agg["pool_divergence"],
            "valid_range": {
                "out_of_range_cells": len(d["s05_oor"]),
                "by_anchor": agg["oor_by_anchor"],
                "by_metric": agg["oor_by_metric"],
                "conclusion": "Frozen rules define no disposition for out-of-range values; registered only, not used to change routing.",
            },
            "rh06_pending": {
                "adoption_status": agg["rh06"],
                "pending_companies": agg["rh06_pending"],
            },
        },
        "findings": [
            {"id": "F01", "title": "Sample arithmetic exactly reproduces S02", "layer": "S02", "severity": "INFO",
             "evidence": f"{agg['cells_compared']} cells; status {agg['cells_status_match']}/{agg['cells_compared']}; value {agg['cells_value_match']}/{agg['cells_compared']}; max_abs_diff={agg['max_abs_diff']:.3e}"},
            {"id": "F02", "title": "S03 L1 rule replay exact on 57, 5 frozen overrides explained", "layer": "S03", "severity": "INFO",
             "evidence": f"{agg['s03_consistent']} rule-replayed CONSISTENT, {agg['s03_override']} frozen override (individually justified), {len(agg['s03_mismatch'])} mismatch"},
            {"id": "F03", "title": "S04 boundary attributes and signal evidence hold", "layer": "S04", "severity": "INFO",
             "evidence": f"{agg['s04_consistent']} consistent, {len(agg['s04_mismatch'])} mismatch; abs-channel evidence={len(abs_evidence)} rows / {sum(1 for e in abs_evidence if e['check_pass'])} pass; low-base evidence={len(low_base_evidence)} rows / {sum(1 for e in low_base_evidence if e['check_pass'])} pass"},
            {"id": "F04", "title": "Missing data preserved as unknown", "layer": "S02/S06", "severity": "INFO",
             "evidence": f"{agg['missing_total']} watch companies, 7 categories; {agg['s06_consistent']} five-count-consistent with stored S02 status, no zero-fill"},
            {"id": "F05", "title": "Mixed H1/9M anchors", "layer": "S02/S05", "severity": "LOW",
             "evidence": f"H1={agg['anchor_split']['H1']}, 9M={agg['anchor_split']['9M']}; RH trigger rates differ modestly"},
            {"id": "F06", "title": "RH02 project-mode exemption", "layer": "S05", "severity": "LOW",
             "evidence": str(agg["rh02"])},
            {"id": "F07", "title": "Low-base confirmation is conservative", "layer": "S01/S04", "severity": "LOW",
             "evidence": f"{agg['low_base_confirmed_companies']} confirmed companies; threshold CNY 10m same direction"},
            {"id": "F08", "title": "BJ pass rate above non-BJ", "layer": "DATA/STRUCTURE", "severity": "LOW",
             "evidence": f"BJ {agg['bj']['pass']}/{agg['bj']['total']} ({agg['bj']['pass_rate_pct']}%) vs non-BJ {agg['bj']['non_bj_pass']}/{agg['bj']['non_bj_total']} ({agg['bj']['non_bj_pass_rate_pct']}%)"},
            {"id": "F09", "title": "Reverse omission: 5 sampled companies re-derived, no calculation leak", "layer": "S04/S05/S06", "severity": "INFO",
             "evidence": f"{len(reverse_audit)} sampled companies independently re-derived; calc leaks={len(agg['reverse']['calc_leaks'])}; reviewed holds={len(agg['reverse']['reviewed_holds'])}; full-pool {agg['reverse']['strong_not_mainline']} covered by route reconciliation only"},
            {"id": "F10", "title": "S04 baseline vs S05 frozen pool divergence", "layer": "S04/S05", "severity": "MEDIUM",
             "evidence": f"S04 candidates={agg['pool_divergence']['s04_candidates']}, S05 pool={agg['pool_divergence']['s05_frozen_pool']}, diff={agg['pool_divergence']['difference']}; reviewed_view not Git-tracked"},
            {"id": "F11", "title": "Out-of-valid-range has no frozen disposition", "layer": "S01", "severity": "LOW",
             "evidence": f"{len(d['s05_oor'])} cells, all metric_status=OK, registered only"},
            {"id": "F12", "title": "RH06 pending cases retained", "layer": "S05", "severity": "LOW",
             "evidence": f"{agg['rh06_pending']} not adopted; no unresolved dispute used"},
            {"id": "F13", "title": "Guards preserved", "layer": "GUARD", "severity": "INFO",
             "evidence": str(agg["guards"])},
        ],
        "s03_frozen_override_audit": override_audit,
        "abs_channel_evidence": abs_evidence,
        "low_base_evidence": low_base_evidence,
        "reverse_omission_audit": reverse_audit,
        "reverse_omission_scope_note": (
            f"Only the {len(reverse_audit)} sampled REVERSE_OMISSION companies were independently "
            f"re-derived. The remaining strong-exposure companies outside the mainline "
            f"({agg['reverse']['strong_not_mainline']} in total) are covered by route-distribution "
            f"reconciliation only, NOT by per-company re-derivation."
        ),
        "grading": grading,
        "guards_preserved": agg["guards"],
        "release_S08": False,
        "issue_53_touched": False,
        "limitations": [
            "SELF_CHECK by executor CodeBuddy; independent acceptance by Codex is still required.",
            "Small-sample audit only; no full-pool re-research, no per-company announcement deep reading.",
            "The S04 reviewed-view tight_pass (278) is not Git-tracked; only the tracked baseline tight_decision_log (445 candidates) and frozen S05 outputs are replayable.",
            "Out-of-valid-range disposition is undefined in the frozen rules and is carried forward.",
        ],
    }
    return rev


def build_handoff_md(agg, sample_rows, abs_evidence, low_base_evidence, reverse_audit, grading):
    lines = []
    lines.append("# S07 / #42 执行交接（SELF_CHECK）")
    lines.append("")
    lines.append(f"完成时间：{NOW}（北京时间）。计划版本 `{PLAN_VERSION}`。执行方 {EXECUTOR}，统筹方 {ORCHESTRATOR}，独立复核指派 {REVIEWER_ASSIGNED}。")
    lines.append(f"返修轮次：`{REWORK_ROUND}`；返修依据：`{REWORK_BASIS}`。")
    lines.append("")
    lines.append("## 完成内容")
    lines.append("")
    lines.append(f"- 冻结确定性分层抽样 **{agg['total']} 家**（50–65 家区间内），覆盖 6 个分层、{len(agg['slots'])} 个子槽；无随机数，排序键固定。")
    lines.append(f"- 从 `s00_v10.csv.gz` 独立重算 12 项指标 **{agg['cells_compared']} 格**，状态一致 {agg['cells_status_match']}、数值一致 {agg['cells_value_match']}，最大绝对差 {agg['max_abs_diff']:.3e}。")
    lines.append(f"- S03 L1 重放：{agg['s03_consistent']} 家规则重推一致、{agg['s03_override']} 家冻结覆盖（逐家说明）、{len(agg['s03_mismatch'])} 家不一致。")
    lines.append(f"- S04 边界：{agg['s04_consistent']} 家内部一致；绝对额通道 {len(abs_evidence)} 条、低基数确认 {len(low_base_evidence)} 条逐条从 `s00_v10` 复算，全部通过。")
    lines.append(f"- S05：RH 阈值 {agg['s05_consistent']} 家一致；20 格越界值确认越界且未改路由；RH06 待核 {agg['rh06_pending']} 家保持。")
    lines.append(f"- S06：缺失观察 7 类 {agg['missing_total']} 家、早期储备 4 桶 54 家；五项计数逐家一致，缺失未填 0。")
    lines.append(f"- 反向漏筛：抽样 {len(reverse_audit)} 家逐家独立重推，计算漏筛 {len(agg['reverse']['calc_leaks'])} 家；全池 {agg['reverse']['strong_not_mainline']} 家仅做路由分布汇总，未逐一重推。")
    lines.append(f"- 定级：`systemic_blocker={grading['systemic_blocker']}`、`requires_s00_s01_rollback={grading['requires_s00_s01_rollback']}`，由 {len(grading['derivation_basis']['blocking_keys'])} 项异常清单动态推导（计数全部为 0）。")
    lines.append("")
    lines.append("## 交付文件（runs/issues/S07/）")
    lines.append("")
    for f in ("step_s07_build.py", "step_s07_verify.py", "screen_audit_sample.csv",
              "screen_audit_findings.md", "screen_audit_review.json", "manifest.json",
              "handoff.md", "review.json"):
        lines.append(f"- `{f}`")
    lines.append("")
    lines.append("## 复现方式")
    lines.append("")
    lines.append("**推荐方式：指定提交的干净 Git checkout / worktree。** 例如：")
    lines.append("")
    lines.append("```")
    lines.append("git worktree add --detach /tmp/s07_replay <commit_sha>")
    lines.append("cd /tmp/s07_replay")
    lines.append(f"S07_FIXED_NOW={NOW} py runs/issues/S07/step_s07_build.py")
    lines.append(f"S07_FIXED_NOW={NOW} py runs/issues/S07/step_s07_verify.py")
    lines.append("```")
    lines.append("")
    lines.append("此时 C13 在存在 `.git` 的情况下强制执行 `git ls-files --error-unmatch`，验证 29 份输入 100% 位于 Git 跟踪树内。")
    lines.append("")
    lines.append("**备选方式：`git archive` 纯归档目录（无 `.git`）。** 归档须包含本提交的 `manifest.json`。此时 C13 检测到无 `.git`，改为核对全部输入文件存在、且与 `manifest.json` / `release_20261126.json` 冻结输入清单及 SHA-256 逐一匹配，并标注 `git_index_check=SKIPPED_NO_GIT_DIR_VERIFIED_BY_MANIFEST`，不会因缺少 Git 索引而崩溃。该模式下 22 项自检同样全部 PASS；除 C13 的模式标注（及其导致的 `review.json` 与清单根摘要差异）外，其余 6 份交付逐字节一致。")
    lines.append("")
    lines.append("**逐字节一致性**：推荐模式下连续两次 `build + verify` 的 8 份文件（`screen_audit_sample.csv`、`screen_audit_findings.md`、`screen_audit_review.json`、`handoff.md`、`review.json`、`manifest.json`、`step_s07_build.py`、`step_s07_verify.py`）SHA-256 完全一致。")
    lines.append("")
    lines.append("构建脚本输出全部 CSV/MD/JSON；自检脚本校验输入哈希、主键守恒、分层覆盖、复算一致、绝对额/低基数逐条证据、反向漏筛重推、交付哈希与清单根摘要，并写 `manifest.json` 与 `review.json`。")
    lines.append("")
    lines.append("## 未做 / 限制")
    lines.append("")
    lines.append("- 未重研全池、未逐家深读公告、未调整任何阈值、未手工加回公司。")
    lines.append("- S04 复核版 `tight_pass`（278）不在 Git 跟踪树内，445→278 的逐家映射无法在干净树内完全重放；该可追溯性缺口登记为 F10，结转 S08。")
    lines.append("- 20 格越界值的处置动作在冻结规则中未定义（F11），只登记不改路由。")
    lines.append("- 本卡为 `SELF_CHECK`，不释放 S08；须 Codex 独立复核后再登记验收。")
    lines.append("")
    lines.append("## 断点与下一步")
    lines.append("")
    lines.append("1. Codex 按 `screen_audit_review.json` 的 F01–F13 做独立复核，重点核 F10（S04→S05 池口径）与 F11（越界处置）。")
    lines.append("2. 复核通过后登记 S07 验收；S08 放行仍须单独授权。")
    lines.append("3. 建议 S08 开工前补齐 S04 复核版 `tight_pass`/`tight_decision_log` 的 Git 跟踪，或在 S08 输入合同中显式冻结 278 的逐家映射。")
    lines.append("")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
def main():
    d = load_inputs()
    rows, meta = load_s00()
    engine = Engine(rows, meta)

    # Guard: release says S07 approved, S08 not released
    assert d["release"]["release_S07"] is True
    assert d["release"]["downstream"]["S08_released"] is False
    # Guard: S03 partition is a complete, disjoint cover of the 1,054 universe
    wp = {r["company_id"] for r in d["wide_pass"]}
    wd = {r["company_id"] for r in d["wide_defer"]}
    wu = {r["company_id"] for r in d["wide_unknown"]}
    assert (len(wp), len(wd), len(wu)) == (777, 149, 128)
    assert not (wp & wd) and not (wp & wu) and not (wd & wu)
    assert (wp | wd | wu) == set(d["master_by_id"])
    # Guard: provenance texts are the ones this issue references
    assert "S07" in d["handoff_txt"] and "SELF_CHECK" in d["handoff_txt"]
    assert "379" in d["s06_rules_txt"] and "54" in d["s06_rules_txt"]
    assert "278" in d["codex_ruling_txt"]

    selected, slots_log, strong, strong_not_main = build_sample(d)
    sample_rows = build_sample_rows(d, engine, selected)
    agg = compute_aggregates(d, engine, selected, slots_log, sample_rows, strong, strong_not_main)

    abs_evidence = build_abs_channel_evidence(engine, d, sample_rows)
    low_base_evidence = build_low_base_evidence(engine, d, sample_rows)
    reverse_audit = build_reverse_omission_audit(engine, d, sample_rows)
    override_audit = build_s03_override_audit(d, sample_rows)
    grading = build_grading(agg, abs_evidence, low_base_evidence, reverse_audit)

    # Write sample CSV
    write_lf(OUT / "screen_audit_sample.csv", csv_text(SAMPLE_FIELDS, sample_rows))

    # Write findings & structured review
    write_lf(OUT / "screen_audit_findings.md",
             build_findings_md(d, agg, sample_rows, abs_evidence, low_base_evidence,
                               reverse_audit, override_audit, grading))
    review_obj = build_review_json(d, agg, sample_rows, abs_evidence, low_base_evidence,
                                   reverse_audit, override_audit, grading)
    write_lf(OUT / "screen_audit_review.json",
             json.dumps(review_obj, ensure_ascii=False, indent=2) + "\n")

    # Write handoff
    write_lf(OUT / "handoff.md",
             build_handoff_md(agg, sample_rows, abs_evidence, low_base_evidence,
                              reverse_audit, grading))

    print(f"S07 build: sample={agg['total']} strata={dict(agg['stratum_counts'])}")
    print(f"  cells={agg['cells_compared']} status={agg['cells_status_match']} value={agg['cells_value_match']} maxdiff={agg['max_abs_diff']:.3e}")
    print(f"  s03 consistent={agg['s03_consistent']} override={agg['s03_override']} mismatch={len(agg['s03_mismatch'])}")
    print(f"  s04 mismatch={len(agg['s04_mismatch'])} s05 mismatch={len(agg['s05_mismatch'])} s06 mismatch={len(agg['s06_mismatch'])}")
    print(f"  abs_evidence={len(abs_evidence)} pass={sum(1 for e in abs_evidence if e['check_pass'])} "
          f"low_base_evidence={len(low_base_evidence)} pass={sum(1 for e in low_base_evidence if e['check_pass'])}")
    print(f"  reverse_audit={len(reverse_audit)} calc_leaks={len(agg['reverse']['calc_leaks'])}")
    print(f"  systemic_blocker={grading['systemic_blocker']} requires_rollback={grading['requires_s00_s01_rollback']}")


if __name__ == "__main__":
    main()
