#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""重算 manifest.json：逐文件 sha256 + 字节数。

第十二轮 H 项的延伸：清单里的版本号不再手写，取自 review.json 的 self_check_version。
"""
import hashlib
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent

FILES = [
    # 代码
    "evidence_scope.py", "meta_classes.py", "l2_core.py", "parent_verify.py",
    "polarity_cases.py", "build_errata_v5.py", "check_l2_v5.py", "sampling_v5.py",
    "replay_polarity_v5.py", "verify_v5.py",
    "step4_event_scan.py", "step4_apply_events.py",
    # 台账与登记表
    "rulings_resolved.json", "cell_diff.csv", "key_diff.csv", "meta_diff.csv",
    "extra_meta_diff.csv", "evidence_conflicts.csv", "content_reviews.csv",
    "parent_verifications.csv", "scope_verifications.csv", "ruling_scope.csv",
    "event_verifications.csv", "step4_event_scan.csv",
    "dispute_ledger.csv", "restricted_claims.csv", "l2_dependency_check.csv",
    # 抽样
    "sampling_v5.csv", "l2_dependency_summary.json", "sampling_v5.json",
    "sampling_keys_baseline.csv", "sampling_keys_diff.csv", "replay_polarity_v5.json",
    # 汇总
    "summary.json", "review.json", "REPORT.md", "handoff.md",
    "acceptance_round16.json",
    # 往来
    "report_to_codex_round11.md", "report_to_codex_round12.md",
    "report_to_codex_round13.md", "report_to_codex_round14.md",
    "report_to_codex_round15.md", "report_to_codex_round16.md",
    "report_to_codex_round17.md", "report_to_codex_round18.md",
    "_codex_prompt_round11.txt", "_codex_prompt_round12.txt",
    "_codex_prompt_round13.txt", "_codex_prompt_round14.txt",
    "_codex_prompt_round15.txt", "_codex_prompt_round16.txt",
    "_codex_prompt_round17.txt", "_codex_prompt_round18.txt",
    "codex_ruling_round5.md",
    "_codex_out_round10.txt", "_codex_out_round11.txt", "_codex_out_round12.txt",
    "_codex_out_round13.txt", "_codex_out_round14.txt", "_codex_out_round15.txt",
    "_codex_out_round16.txt",
]

rev = json.loads((OUT / "review.json").read_text(encoding="utf-8"))
missing = [f for f in FILES if not (OUT / f).exists()]
if missing:
    raise SystemExit("missing: %s" % missing)

man = {
    "version": "ERRATA_V5",
    "self_check_version": rev["self_check_version"],
    "generated_at": "2026-11-12T00:50:00+08:00",
    "issue": "S00",
    "stage": "ERRATA",
    "nature": "SELF_CHECK",
    "reproduce": ["build_errata_v5.py", "check_l2_v5.py", "sampling_v5.py",
                  "replay_polarity_v5.py", "verify_v5.py"],
    "upstream_ruling": [
        "codex_ruling_round5.md",
        "第十轮 RETURN_FOR_REWORK（_codex_out_round10.txt）",
        "第十一轮 RETURN_FOR_REWORK（_codex_out_round11.txt，H 通过 / A–G 不通过）",
        "第十二轮 RETURN_FOR_REWORK（_codex_out_round12.txt，G 通过 / A、B、C、D、E、F、H 不通过）",
        "第十三轮 RETURN_FOR_REWORK（_codex_out_round13.txt，D、E、G 通过 / A、B、C、F、H 不通过）",
        "第十四轮 RETURN_FOR_REWORK（_codex_out_round14.txt，F 通过 / A、B、C、H 不通过）",
    ],
    "files": [],
}
for f in FILES:
    b = (OUT / f).read_bytes()
    man["files"].append({"path": f, "bytes": len(b),
                         "sha256": hashlib.sha256(b).hexdigest()})
# EOL 自己管：HEAD 里 manifest.json 是 **CRLF + indent=1**。用 write_text(indent=2)
# 会被 Windows 转成 CRLF 且缩进变形，diff 会变成「全文件重写」。
(OUT / "manifest.json").write_bytes(
    (json.dumps(man, ensure_ascii=False, indent=1) + "\n")
    .encode("utf-8").replace(b"\n", b"\r\n"))
print("%d files, self_check_version=%s" % (len(man["files"]), man["self_check_version"]))
