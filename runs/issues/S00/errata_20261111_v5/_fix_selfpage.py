# -*- coding: utf-8 -*-
"""修复 verify_v5.py 中 self_page_ok 三处跨行字符串（heredoc 把 \\n 吃成真换行）。"""
import io
import sys
from pathlib import Path

P = Path(__file__).with_name("verify_v5.py")
raw = P.read_bytes()

START = b"self_page_ok = ("
END = b"\r\n)\r\n"

i = raw.find(START)
if i < 0:
    print("FAIL: start marker not found")
    sys.exit(1)
j = raw.find(END, i)
if j < 0:
    print("FAIL: end marker not found")
    sys.exit(1)

old = raw[i:j + len(END)]

NEW = (
    "self_page_ok = (\r\n"
    "    not self_page_line_ok(\"\u67d0\u67d0\u516c\u53f8 2025 \u5e74\u534a\u5e74\u5ea6\u62a5\u544a\\n"
    "\u2026\u5408\u8ba1 100.00\\n\u8425\u4e1a\u6536\u5165 200.00\",\r\n"
    "                          \"100.00\", [\"\u8425\u4e1a\u6536\u5165\"])\r\n"
    "    and self_page_line_ok(\"\u67d0\u67d0\u516c\u53f8 2025 \u5e74\u534a\u5e74\u5ea6\u62a5\u544a\\n"
    "\u8425\u4e1a\u6536\u5165 100.00 100.00\",\r\n"
    "                          \"100.00\", [\"\u8425\u4e1a\u6536\u5165\"])\r\n"
    "    and not self_page_line_ok(\"\u8425\u4e1a\u6536\u5165 200.00\", \"100.00\", [\"\u8425\u4e1a\u6536\u5165\"])\r\n"
    ")\r\n"
).encode("utf-8")

raw2 = raw[:i] + NEW + raw[j + len(END):]
P.write_bytes(raw2)

print("old_bytes=%d new_bytes=%d" % (len(old), len(NEW)))
print("OLD_REPR:", repr(old[:400]))
print("NEW_REPR:", repr(NEW[:400]))
