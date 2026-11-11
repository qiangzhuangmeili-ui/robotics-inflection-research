#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""极性反例集的独立执行入口（与 verify_v5.py 的 C34 消费同一份 CASES）。"""
import polarity_cases as pc

bad = pc.check_all()
for b in bad:
    print("FAIL  %s" % b["case"])
    print("      文本: %r" % b["text"])
    print("      得到: %s" % b["got"])
    print("      期望: %s" % b["want"])
print("\n%d/%d PASS" % (len(pc.CASES) - len(bad), len(pc.CASES)))
raise SystemExit(1 if bad else 0)
