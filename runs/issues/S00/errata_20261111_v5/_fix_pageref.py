# -*- coding: utf-8 -*-
"""第十三轮 C 项补丁：页码/表号正则漏 `表格1.2`，且 seg 窗口把尾部 `节` 截掉。"""
import sys
from pathlib import Path

P = Path(__file__).with_name("verify_v5.py")
raw = P.read_bytes()

OLD1 = ('    r"|(?:表|图)\\s*\\d+[.．]\\d+"\r\n').encode("utf-8")
NEW1 = ('    r"|(?:表|图)格?\\s*\\d+[.．]\\d+"\r\n').encode("utf-8")
if raw.count(OLD1) != 1:
    print("FAIL step1 count=%d" % raw.count(OLD1))
    sys.exit(1)
raw = raw.replace(OLD1, NEW1)

OLD2 = b"            seg = frag[max(0, m.start(1) - 6):m.end(1)]"
NEW2 = b"            seg = frag[max(0, m.start(1) - 6):min(len(frag), m.end(1) + 4)]"
if raw.count(OLD2) != 1:
    print("FAIL step2 count=%d" % raw.count(OLD2))
    sys.exit(1)
raw = raw.replace(OLD2, NEW2)

P.write_bytes(raw)
print("patched OK")
