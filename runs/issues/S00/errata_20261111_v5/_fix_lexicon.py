# -*- coding: utf-8 -*-
"""第十三轮 A 项结构性修复：影响动词改为唯一词表，剥词表与判据表同源。

Codex 指出的「净增加 仍暴露闭集剥词的漏词问题」，根因不是词不够多，而是
**同一个概念写了两份词表**（`_TAIL_STRIP` 有「净增加」、`_RE_EFFECT_VERB` 没有）。
现在只保留 `_EFFECT_WORDS` 一处，两个正则都从它派生。
"""
import sys
from pathlib import Path

P = Path(__file__).with_name("evidence_scope.py")
with open(P, "r", encoding="utf-8", newline="") as f:
    src = f.read()
if "\r\n" not in src:
    print("WARN: no CRLF found")
lines = src.split("\r\n")


def find(pred, start=0):
    for i in range(start, len(lines)):
        if pred(lines[i]):
            return i
    return -1


# ---- 1) 替换 _TAIL_STRIP 块 ----
i0 = find(lambda s: s.startswith("_TAIL_STRIP = re.compile("))
if i0 < 0:
    print("FAIL: _TAIL_STRIP not found")
    sys.exit(1)
i1 = find(lambda s: s.endswith(')$")') and "\\d.," in s, i0)
if i1 < 0:
    print("FAIL: _TAIL_STRIP end not found")
    sys.exit(1)

NEW_STRIP = [
    '# 影响动词：**唯一词表**。中心语剥离与「这笔金额是不是该原因造成的」判据都从这里派生。',
    '# 第十二轮把它写成两份（剥词表里有「净增加」、判据表里没有），于是「影响净增加100.00元」',
    '# 被剥成「影响净」→ 判成新主语。词表只能有一处，这是结构问题，不是补词问题。',
    '_EFFECT_WORDS = ("净增加", "净减少", "净增", "净减",',
    '                 "冲减", "冲回", "调减", "调增", "增加", "减少", "调整", "重述",',
    '                 "计入", "转入", "转出", "计提", "转回", "影响", "核减", "补提", "摊销")',
    '_RE_EFFECT_VERB = re.compile("|".join(_EFFECT_WORDS))',
    '_TAIL_STRIP = re.compile(',
    '    r"(?:" + "|".join(_EFFECT_WORDS) + r"|"',
    '    r"净额|净|金额|差额|合计|总额|小计|确认|核算|审核|评估|"',
    '    r"复核|批准|审议|核准|备案|审计|经|为|是|达|计|约|共|有|发生|存在|采用|"',
    '    r"的|后|元|万元|千元|及|和|与|或|之|其|该|上述|前述|本期|本年|年初|期末|期初|"',
    '    r"累计|其中|对|将|把|按|以|所|者|数|值|上|下|内|中|"',
    '    r"[\\s，,。；;：:、（）()\\[\\]\\"\'“”‘’\\-−+*]|[\\d.,]+)$")',
]
lines[i0:i1 + 1] = NEW_STRIP

# ---- 2) 删除旧的 _RE_EFFECT_VERB 块（含其上 3 行说明旧实现的注释）----
j0 = find(lambda s: s.startswith("_RE_EFFECT_VERB = re.compile("), i0 + len(NEW_STRIP))
if j0 < 0:
    print("FAIL: old _RE_EFFECT_VERB not found")
    sys.exit(1)
j1 = j0
while not lines[j1].endswith('摊销")'):
    j1 += 1
    if j1 - j0 > 5:
        print("FAIL: _RE_EFFECT_VERB end not found")
        sys.exit(1)
k = j0
while k - 1 >= 0 and lines[k - 1].startswith("#"):
    k -= 1
del lines[k:j1 + 1]

out = "\r\n".join(lines)
with open(P, "w", encoding="utf-8", newline="") as f:
    f.write(out)

print("patched evidence_scope.py; lines=%d" % len(lines))
