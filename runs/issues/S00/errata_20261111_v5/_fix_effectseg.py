# -*- coding: utf-8 -*-
"""第十三轮 A 项第二处：影响动词必须在**未剥离**的片段上判。

`_head_noun` 的作用就是把影响动词（调减/冲减/影响…）从中心语里剥掉，
所以在 `head` 上做 `_RE_EFFECT_VERB.search()` 永远是 False——那段分支是死代码。
实测：`…影响0.00元，其中应收账款调减100.00元` 仍被拒。
"""
import sys
from pathlib import Path

P = Path(__file__).with_name("evidence_scope.py")
with open(P, "r", encoding="utf-8", newline="") as f:
    src = f.read()
lines = src.split("\r\n")


def find(sub, start=0):
    for i in range(start, len(lines)):
        if sub in lines[i]:
            return i
    return -1


# ---- 1) 抽出 _seg()，让 _head_noun / _new_subject / _bind_amount 共用同一窗口 ----
i = find("def _head_noun(clause, st, span=24, start=None):")
if i < 0:
    print("FAIL: _head_noun not found")
    sys.exit(1)
seg_fn = [
    "def _seg(clause, st, span=24, start=None):",
    '    """金额左侧的判定窗口：本分句内、上一笔金额结束之后、至多 span 字。',
    "",
    "    窗口单独抽出来，是因为「影响动词」必须在**未剥离**的文本上看：",
    "    `_head_noun` 的职责恰恰是把影响动词剥掉，在剥完的中心语上找动词永远找不到。",
    '    """',
    "    _lo = max(0, st - span) if start is None else max(start, st - span)",
    "    return clause[_lo:st]",
    "",
    "",
]
lines[i:i] = seg_fn

# ---- 2) _head_noun 内部改用 _seg ----
i = find("def _head_noun(clause, st, span=24, start=None):")
j = find("    _lo = max(0, st - span) if start is None else max(start, st - span)", i)
if j < 0:
    print("FAIL: _lo line not found")
    sys.exit(1)
lines[j] = "    tail = _seg(clause, st, span, start)"
# 下一行原为 tail = clause[_lo:st]，删掉
if lines[j + 1].strip().startswith("tail = clause[_lo:st]"):
    del lines[j + 1]

# ---- 3) _new_subject：动词改在窗口上判 ----
i = find("def _new_subject(clause, st, span=24, start=None):")
if i < 0:
    print("FAIL: _new_subject not found")
    sys.exit(1)
k = find("    if _RE_EFFECT_VERB.search(head):", i)
if k < 0:
    print("FAIL: effect-verb line in _new_subject not found")
    sys.exit(1)
lines[k] = "    if _RE_EFFECT_VERB.search(_seg(clause, st, span, start)):"

# ---- 4) _bind_amount：tgt 分支同样改窗口 ----
m = find("                    or _RE_EFFECT_VERB.search(head)):")
if m < 0:
    print("FAIL: tgt effect-verb line not found")
    sys.exit(1)
lines[m] = "                    or _RE_EFFECT_VERB.search(seg)):"
# 在 head/new_subj 计算处补 seg
n = find("        head = _head_noun(c, st, start=prev_end)")
if n < 0:
    print("FAIL: head= line not found")
    sys.exit(1)
lines.insert(n, "        seg = _seg(c, st, start=prev_end)")

out = "\r\n".join(lines)
with open(P, "w", encoding="utf-8", newline="") as f:
    f.write(out)
print("patched; lines=%d" % len(lines))
