# -*- coding: utf-8 -*-
import evidence_scope as es
CASES = [
 ("A1 单符号跨行(不适用)", "前期差错更正\n√\n不适用"),
 ("A2 单符号跨行(适用)",   "前期差错更正\n√\n适用"),
 ("A3 含符号的原因标签",   "前期差错更正□\n√适用□不适用"),
 ("A4 无关收入金额承接",   "未发生前期差错更正，营业收入100.00元"),
 ("A5 长句超半径",         "前期差错更正对期初未分配利润影响经重新核算并经董事会和监事会审核后确认为100.00元"),
]
for n,t in CASES:
    p=es.analyse({"evidence":t})
    print("%-22s %s" % (n, es.polarity_str(p)))
    print("    clauses=%r" % (es._clauses(t),))
