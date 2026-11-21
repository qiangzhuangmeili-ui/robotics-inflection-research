#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 S05 manifest.json。必须在自检与数字校验之后运行；运行后不得再改交付文件。"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent

ROLE = {
    "quality_flags.csv": "deliverable:公司×指标质量标记与证据链",
    "quality_pass.csv": "deliverable:通过名单",
    "quality_observe.csv": "deliverable:本轮观察名单",
    "quality_decision_log.csv": "deliverable:逐公司决策",
    "source_eligibility.csv": "deliverable:来源资格与实际采用字段",
    "rh06_adoption.csv": "deliverable:RH06/Q09 逐公司采用台账（输入、原文位置、开放争议、采用状态）",
    "observe_pool_preserved_776.csv": "deliverable:776 家观察入口原样携带",
    "s05_out_of_valid_range.csv": "finding:超出冻结 valid_range 的值（非阻断）",
    "input_contract.json": "deliverable:输入合同",
    "handoff.md": "deliverable:交接说明",
    "review.json": "deliverable:工作单元复核记录",
    "s05_self_check.json": "evidence:结构自检（项数见文件 checks_total）",
    "s05_prose_numcheck.json": "evidence:说明文档数字校验（项数见文件 checks_total）",
    "s05_build_summary.json": "evidence:构建汇总",
    "step_s05_build.py": "producer:构建脚本",
    "step_s05_verify.py": "producer:自检脚本",
    "step_s05_numcheck.py": "producer:数字校验脚本",
    "step_s05_contract.py": "producer:输入合同生成脚本",
    "step_s05_review.py": "producer:复核记录生成脚本",
    "step_s05_manifest.py": "producer:清单生成脚本",
    "claim_40.py": "process:#40 领取脚本",
    "claim_comment.md": "process:#40 领取回执",
    "handoff_from_s04_20261120.md": "process:S04→S05 交接原文",
    "release_20261120.json": "process:放行记录",
    "codex_review_s05_20261121.md": "review:Codex 独立复核意见（返修依据）",
}


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def main():
    files = []
    for p in sorted(HERE.iterdir()):
        if not p.is_file() or p.name == "manifest.json" or p.name.startswith("."):
            continue
        files.append({
            "file": p.name,
            "role": ROLE.get(p.name, "unclassified"),
            "bytes": p.stat().st_size,
            "sha256": sha256(p),
        })
    digest_src = "\n".join(f"{f['file']}\t{f['sha256']}" for f in files)
    root = hashlib.sha256(digest_src.encode("utf-8")).hexdigest()
    manifest = {
        "artifact": "S05_MANIFEST",
        "issue": "S05 / #40",
        "executor": "WorkBuddy AI",
        "plan_version": "20261026_collection_first_v2",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "file_count": len(files),
        "root_digest": root,
        "hash_discipline": "构建 → 自检 → 数字校验 → 哈希；哈希后不再运行任何自检或改写交付文件",
        "files": files,
    }
    with open(HERE / "manifest.json", "w", encoding="utf-8", newline="\n") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"{len(files)} files, root={root[:16]}")


if __name__ == "__main__":
    main()
