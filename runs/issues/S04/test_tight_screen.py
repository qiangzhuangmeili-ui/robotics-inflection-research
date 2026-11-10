"""S04 返工版回归测试。

覆盖 Codex 裁决要求的三类测试：
  1. 低基数门槛边界（999.99 万 / 1,000 万）
  2. SG06 非正基期与当期金额门槛
  3. 证据降级不得增加通过集合（在交付数据上做 iff 与单调性校验）

另含四家边界公司（公元股份、同兴达、和林微纳、南天信息）的端到端断言。
运行：python runs/issues/S04/test_tight_screen.py
"""
from __future__ import annotations

import csv
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "runs/issues/S04"))

import tight_screen_v2 as ts  # noqa: E402

RULES = json.loads((ROOT / "runs/issues/S01/screen_rules_v3.json").read_text(encoding="utf-8"))
CONF = RULES["low_base_confirmation"]["signals"]
ABS_TH = float(RULES["low_base_confirmation"]["threshold_cny"])
SG06_TH = float(next(s for s in RULES["signals"] if s["id"] == "SG06")["threshold"])
ts.USABLE_SET.update(RULES["status_semantics"]["usable"])

PK = "20260630"
PY = "20250630"


def row(v, status="EXTRACTED_KEY_TABLE", rs="否"):
    return {"value_cny": str(v), "status": status, "restatement_flag": rs}


class TestLowBaseBoundary(unittest.TestCase):
    def test_exact_threshold_confirms(self):
        s00 = {("X", "FIN.NPDEDT.YTD", PY): row(0),
               ("X", "FIN.NPDEDT.YTD", PK): row(10_000_000)}
        ok, det = ts.confirm_low_base(s00, CONF, ABS_TH, SG06_TH, "X", "SG04", PK)
        self.assertTrue(ok, det)
        self.assertEqual(det["result"], "CONFIRMED")

    def test_one_yuan_below_threshold_rejects(self):
        s00 = {("X", "FIN.NPDEDT.YTD", PY): row(0),
               ("X", "FIN.NPDEDT.YTD", PK): row(9_999_999)}
        ok, det = ts.confirm_low_base(s00, CONF, ABS_TH, SG06_TH, "X", "SG04", PK)
        self.assertFalse(ok)
        self.assertEqual(det["result"], "NO_CONFIRM_DELTA")

    def test_single_quarter_uses_sq_field(self):
        # 累计口径达标、单季口径不达标：SG09 必须按单季判定，不得借用累计
        s00 = {
            ("X", "FIN.NPDEDT.YTD", PY): row(0), ("X", "FIN.NPDEDT.YTD", PK): row(50_000_000),
            ("X", "FIN.NPDEDT.SQ", PY): row(0), ("X", "FIN.NPDEDT.SQ", PK): row(2_000_000),
        }
        ok_sq, det = ts.confirm_low_base(s00, CONF, ABS_TH, SG06_TH, "X", "SG09", PK)
        ok_ytd, _ = ts.confirm_low_base(s00, CONF, ABS_TH, SG06_TH, "X", "SG04", PK)
        self.assertFalse(ok_sq)
        self.assertEqual(det["field"], "FIN.NPDEDT.SQ")
        self.assertTrue(ok_ytd)

    def test_ratio_signal_has_no_confirm_rule(self):
        for sg in RULES["low_base_confirmation"]["no_confirm_rule"]:
            ok, det = ts.confirm_low_base({}, CONF, ABS_TH, SG06_TH, "X", sg, PK)
            self.assertFalse(ok)
            self.assertEqual(det["result"], "NO_CONFIRM_RULE", sg)

    def test_unresolved_restatement_blocks(self):
        s00 = {("X", "FIN.NPDEDT.YTD", PY): row(0, rs="RESTATEMENT_INDICATED_NEEDS_REVIEW"),
               ("X", "FIN.NPDEDT.YTD", PK): row(50_000_000)}
        ok, det = ts.confirm_low_base(s00, CONF, ABS_TH, SG06_TH, "X", "SG04", PK)
        self.assertFalse(ok)
        self.assertEqual(det["result"], "NO_CONFIRM_Q06")

    def test_hold_status_blocks(self):
        s00 = {("X", "FIN.NPDEDT.YTD", PY): row(0, status="EXTRACTED_XCHECK_MISMATCH"),
               ("X", "FIN.NPDEDT.YTD", PK): row(50_000_000)}
        ok, det = ts.confirm_low_base(s00, CONF, ABS_TH, SG06_TH, "X", "SG04", PK)
        self.assertFalse(ok)
        self.assertEqual(det["result"], "NO_CONFIRM_INPUT")


class TestAbsChannel(unittest.TestCase):
    def test_sg06_positive_base_rejected(self):
        s00 = {("X", "FIN.NPDEDT.YTD", PY): row(5_000_000),
               ("X", "FIN.NPDEDT.YTD", PK): row(50_000_000)}
        ok, why = ts.abs_channel_qualified(s00, ts.USABLE_SET, SG06_TH, "X", "SG06", PK)
        self.assertFalse(ok)
        self.assertEqual(why, "ABS_CONDITION_FAIL")

    def test_sg06_current_below_threshold_rejected(self):
        s00 = {("X", "FIN.NPDEDT.YTD", PY): row(-20_000_000),
               ("X", "FIN.NPDEDT.YTD", PK): row(9_000_000)}
        ok, why = ts.abs_channel_qualified(s00, ts.USABLE_SET, SG06_TH, "X", "SG06", PK)
        self.assertFalse(ok)
        self.assertEqual(why, "ABS_CONDITION_FAIL")

    def test_sg06_turn_positive_accepted(self):
        s00 = {("X", "FIN.NPDEDT.YTD", PY): row(-20_000_000),
               ("X", "FIN.NPDEDT.YTD", PK): row(15_000_000)}
        ok, why = ts.abs_channel_qualified(s00, ts.USABLE_SET, SG06_TH, "X", "SG06", PK)
        self.assertTrue(ok, why)

    def test_sg08_turn_positive(self):
        s00 = {("X", "FIN.OCF.YTD", PY): row(-5_000_000),
               ("X", "FIN.OCF.YTD", PK): row(3_000_000)}
        ok, why = ts.abs_channel_qualified(s00, ts.USABLE_SET, SG06_TH, "X", "SG08", PK)
        self.assertTrue(ok, why)

    def test_sg08_already_positive_rejected(self):
        s00 = {("X", "FIN.OCF.YTD", PY): row(5_000_000),
               ("X", "FIN.OCF.YTD", PK): row(9_000_000)}
        ok, why = ts.abs_channel_qualified(s00, ts.USABLE_SET, SG06_TH, "X", "SG08", PK)
        self.assertFalse(ok)
        self.assertEqual(why, "ABS_CONDITION_FAIL")


class TestDeliveredOutput(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        p = ROOT / "runs/issues/S04/tight_decision_log.csv"
        if not p.exists():
            raise unittest.SkipTest("先运行 tight_screen_v2.py 生成交付")
        with p.open(encoding="utf-8-sig", newline="") as fh:
            cls.rows = {r["company_id"]: r for r in csv.DictReader(fh)}
        cls.sg_dim = {s["id"]: s["dimension"] for s in RULES["signals"]}

    def dims_of(self, r, field):
        return {self.sg_dim[s] for s in (r[field] or "").split(";") if s}

    def test_iff_condition_holds_for_every_row(self):
        """入选 ⟺ 三类证据覆盖的维度数 ≥2（逐行充要条件）。"""
        bad = []
        for sec, r in self.rows.items():
            dims = (self.dims_of(r, "ratio_channel_sg") | self.dims_of(r, "abs_channel_sg")
                    | self.dims_of(r, "low_base_confirmed_sg"))
            expect = len(dims) >= 2
            actual = r["l2_decision"] == "L2_SHORTLIST_CANDIDATE"
            if expect != actual:
                bad.append((sec, r["l2_decision"], len(dims)))
        self.assertEqual(bad, [])

    def test_evidence_downgrade_cannot_add_passes(self):
        """剔除低基数确认证据后，通过集合只能是原集合的子集。"""
        full = {s for s, r in self.rows.items() if r["l2_decision"] == "L2_SHORTLIST_CANDIDATE"}
        ab_only = {s for s, r in self.rows.items()
                   if len(self.dims_of(r, "ratio_channel_sg") | self.dims_of(r, "abs_channel_sg")) >= 2}
        self.assertTrue(ab_only <= full, sorted(ab_only - full)[:5])
        self.assertLessEqual(len(ab_only), len(full))

    def test_no_pass_without_ratio_or_abs_evidence(self):
        bad = [s for s, r in self.rows.items()
               if r["l2_decision"] == "L2_SHORTLIST_CANDIDATE"
               and not (r["ratio_channel_sg"] or r["abs_channel_sg"])]
        self.assertEqual(bad, [])

    def test_boundary_companies(self):
        g = self.rows["SZ:002641"]      # 公元股份：累计 +2,253.57 万
        t = self.rows["SZ:002845"]      # 同兴达：单季 +3,977.51 万
        l = self.rows["SH:688661"]      # 和林微纳：单季仅 +232.91 万
        n = self.rows["SZ:000948"]      # 南天信息：SG06 绝对额通道
        self.assertEqual(g["l2_decision"], "L2_SHORTLIST_CANDIDATE")
        self.assertEqual(t["l2_decision"], "L2_SHORTLIST_CANDIDATE")
        self.assertIn("CONFIRMED", g["low_base_detail"])
        self.assertIn("CONFIRMED", t["low_base_detail"])

        self.assertNotEqual(l["l2_decision"], "L2_SHORTLIST_CANDIDATE")
        self.assertIn("NO_CONFIRM_DELTA", l["low_base_detail"])

        self.assertEqual(n["l2_decision"], "L2_SHORTLIST_CANDIDATE")
        self.assertIn("SG06", n["abs_channel_sg"])
        self.assertEqual(n["abs_critical"], "YES")

    def test_guard_companies_isolated(self):
        guards = [r for r in self.rows.values() if r["l2_decision"] == "WATCH_AFTER_CUTOFF"]
        self.assertEqual(len(guards), 4)
        for r in guards:
            self.assertEqual(r["qualified_sg"], "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
