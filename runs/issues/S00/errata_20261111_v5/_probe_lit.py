# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, ".")
import verify_v5 as V

fs = V._field_support
cases = [
    ("1 page", ("LITERAL", "营业总收入", "营业总收入", "1",
                "2025年上半年营业总收入见第12页附表说明文字为索引",
                {"meta_field": "evidence_label"}), False),
    ("2 qty", ("LITERAL", "营业总收入", "营业总收入", "1",
               "2025年上半年营业总收入100.00元，较上年同期增长",
               {"meta_field": "evidence_label"}), True),
    ("3 currency", ("LITERAL", "人民币", "CNY", "1",
                    "金额单位：人民币元；记账本位币：人民币",
                    {"meta_field": "currency"}), True),
    ("4a t1.2", ("LITERAL", "营业总收入", "营业总收入", "1",
                 "2025年上半年营业总收入见表格1.2", {"meta_field": "evidence_label"}), False),
    ("4b t3.1", ("LITERAL", "营业总收入", "营业总收入", "1",
                 "2025年上半年营业总收入参见表3.1", {"meta_field": "evidence_label"}), False),
    ("4c s12.1", ("LITERAL", "营业总收入", "营业总收入", "1",
                  "2025年上半年营业总收入参见12.1节", {"meta_field": "evidence_label"}), False),
    ("5a 100.00元", ("LITERAL", "营业总收入", "营业总收入", "1",
                     "2025年上半年营业总收入100.00元，较上年同期增长", {"meta_field": "evidence_label"}), True),
    ("5b 100万元", ("LITERAL", "营业总收入", "营业总收入", "1",
                    "2025年上半年营业总收入100万元", {"meta_field": "evidence_label"}), True),
    ("5c 12.50%", ("LITERAL", "营业总收入", "营业总收入", "1",
                   "2025年上半年营业总收入12.50%", {"meta_field": "evidence_label"}), True),
]
for name, args, want in cases:
    got = fs(*args)[0]
    print("%-14s want=%-5s got=%-5s %s" % (name, want, got, "OK" if got == want else "**MISMATCH**"))

print("self_page_ok =", V.self_page_ok if hasattr(V, "self_page_ok") else "n/a")
