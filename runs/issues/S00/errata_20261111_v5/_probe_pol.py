# -*- coding: utf-8 -*-
"""第十三轮 A 项逐句复验。"""
import sys
sys.path.insert(0, ".")
import evidence_scope as ES

CASES = [
    ("A1 指定句1", "前期差错更正对期初未分配利润影响0.00元，影响净增加100.00元", True),
    ("A2 无逗号同分句", "前期差错更正对期初未分配利润影响0.00元其中营业总收入100.00元", False),
    ("A3 影响增加", "前期差错更正对期初未分配利润影响0.00元，影响增加100.00元", True),
    ("A4 影响共计", "前期差错更正对期初未分配利润影响0.00元，影响共计100.00元", True),
    ("A5 其中应收账款", "前期差错更正对期初未分配利润影响0.00元，其中应收账款确认金额：300.00元", False),
    ("A6 其中研发费用", "前期差错更正对期初未分配利润影响0.00元，其中研发费用合 计400.00元", False),
    ("A7 调减营收", "前期差错更正对期初未分配利润影响0.00元，调减营业总收入100.00元", True),
    ("A8 净减少", "前期差错更正对期初未分配利润影响0.00元，影响净减少100.00元", True),
    ("A9 净增", "前期差错更正对期初未分配利润影响0.00元，净增100.00元", True),
]

for name, sent, want in CASES:
    r = ES.analyse(sent)
    aff = r.get("affirmed") or set()
    ok = ("ERRATA" in aff) == want
    print("%-18s want=%-5s got=%-24s %s" % (name, want, sorted(aff), "OK" if ok else "**MISMATCH**"))
    if not ok:
        print("   detail:", {k: v for k, v in r.items() if k != "affirmed"})
